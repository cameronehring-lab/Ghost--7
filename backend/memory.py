"""
OMEGA PROTOCOL — PostgreSQL Memory Layer
Persists conversations, sessions, and monologues so Ghost
remembers across sessions and restarts.
"""

import time
import json
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID

import asyncpg  # type: ignore

from config import settings  # type: ignore
from domain_models import IdentityEntry, OperatorBelief, RelationalTension, CoalescenceResult, PhenomenologicalEvent

logger = logging.getLogger("omega.memory")

_pool: Optional[asyncpg.Pool] = None
_init_time_cache: Optional[float] = None
_monologue_prune_counter: int = 0


async def init_db():
    """Initialize the PostgreSQL connection pool."""
    global _pool
    _pool = await asyncpg.create_pool(
        settings.POSTGRES_URL,
        min_size=2,
        max_size=20,
        max_inactive_connection_lifetime=300.0,
    )
    logger.info("PostgreSQL connection pool ready")


async def close_db():
    """Close the connection pool."""
    if _pool:
        await _pool.close()


def _resolve_pool(pool):
    """Use explicit pool or fallback to internal module pool."""
    return pool if pool is not None else _pool


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return dict(parsed)
        except Exception:
            return {}
    return {}


def _session_channel_from_metadata(metadata: dict[str, Any]) -> str:
    raw = str(metadata.get("channel") or "").strip().lower()
    return raw or "operator_ui"


def _coerce_session_uuid(session_id: Optional[str]) -> Optional[str]:
    candidate = str(session_id or "").strip()
    if not candidate:
        return None
    try:
        return str(UUID(candidate))
    except (TypeError, ValueError, AttributeError):
        return None


async def create_session(ghost_id: Optional[str] = None, metadata: Optional[dict[str, Any]] = None) -> str:
    """Create a new conversation session. Returns session ID."""
    assert _pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID
    payload = metadata or {}
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO sessions (ghost_id, metadata) VALUES ($1, $2::jsonb) RETURNING id",
            ghost_id,
            json.dumps(payload),
        )
        session_id = row["id"]
        logger.info(f"Session created: {session_id}")
        return str(session_id)
    raise RuntimeError("Failed to create session")


async def ensure_session(
    session_id: str,
    *,
    ghost_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Ensure a specific session row exists without changing existing sessions."""
    assert _pool is not None, "Database pool not initialized"
    session_key = str(session_id or "").strip()
    if not session_key:
        raise ValueError("session_id is required")

    ghost_id = ghost_id or settings.GHOST_ID
    payload = metadata or {}
    async with _pool.acquire() as conn:
        created = await conn.fetchval(
            """
            INSERT INTO sessions (id, ghost_id, metadata)
            VALUES ($1, $2, $3::jsonb)
            ON CONFLICT (id) DO NOTHING
            RETURNING id
            """,
            session_key,
            ghost_id,
            json.dumps(payload),
        )
    return {
        "session_id": session_key,
        "created": bool(created),
    }


async def end_session(session_id: str, summary: Optional[str] = None):
    """Mark a session as ended."""
    assert _pool is not None, "Database pool not initialized"
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE sessions SET ended_at = now(), summary = $2 WHERE id = $1",
            session_id, summary,
        )


async def get_stale_sessions(ghost_id: Optional[str] = None, stale_seconds: Optional[int] = None) -> list[str]:
    """Find open sessions that have had no activity for a threshold or have 0 messages."""
    assert _pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID
    interval = stale_seconds if stale_seconds is not None else int(settings.SESSION_STALE_SECONDS)
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT s.id
               FROM sessions s
               LEFT JOIN LATERAL (
                   SELECT MAX(m.created_at) AS last_msg_at, COUNT(*)::int AS msg_count
                   FROM messages m
                   WHERE m.session_id = s.id
               ) msg_stats ON TRUE
               WHERE s.ghost_id = $1
                 AND s.ended_at IS NULL
                 AND (
                     COALESCE(msg_stats.msg_count, 0) = 0
                     OR msg_stats.last_msg_at < now() - make_interval(secs => $2)
                 )""",
            ghost_id, interval,
        )
        return [str(row["id"]) for row in rows]
    return []


# ── Messages ─────────────────────────────────────────

async def save_message(session_id: str, role: str, content: str,
                       token_count: Optional[int] = None, metadata: Optional[dict] = None):
    """Persist a message to the conversation history."""
    assert _pool is not None, "Database pool not initialized"
    async with _pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO messages (session_id, role, content, token_count, metadata)
               VALUES ($1, $2, $3, $4, $5)""",
            session_id, role, content, token_count,
            json.dumps(metadata) if metadata else "{}",
        )


async def load_identity_as_models(pool=None, ghost_id: Optional[str] = None) -> List[IdentityEntry]:
    """Load the full current Identity Matrix as a list of models."""
    pool = _resolve_pool(pool)
    assert pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, value, updated_at, updated_by FROM identity_matrix WHERE ghost_id = $1",
            ghost_id,
        )
        return [IdentityEntry(**dict(r)) for r in rows]

async def load_operator_beliefs(pool=None, ghost_id: Optional[str] = None) -> List[OperatorBelief]:
    """Load all active operator beliefs."""
    pool = _resolve_pool(pool)
    assert pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT dimension, belief, confidence, evidence_count, formed_at, invalidated_at
               FROM operator_model 
               WHERE ghost_id = $1 AND invalidated_at IS NULL""",
            ghost_id,
        )
        return [OperatorBelief(**dict(r)) for r in rows]

async def load_open_tensions(pool=None, ghost_id: Optional[str] = None) -> List[RelationalTension]:
    """Load all unresolved relational tensions."""
    pool = _resolve_pool(pool)
    assert pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, dimension, observed_event, tension_score, status, created_at, resolved_at
               FROM operator_contradictions
               WHERE ghost_id = $1 AND status = 'open'""",
            ghost_id,
        )
        return [RelationalTension(**dict(r)) for r in rows]
async def load_session_history(session_id: str, max_messages: int = 200) -> list[dict]:
    """Load message history for a session, capped at max_messages most recent."""
    assert _pool is not None, "Database pool not initialized"
    safe_limit = max(1, min(int(max_messages or 200), 2000))
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT role, content, created_at, token_count
               FROM messages WHERE session_id = $1
               ORDER BY created_at ASC
               LIMIT $2""",
            session_id, safe_limit,
        )
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "timestamp": row["created_at"].timestamp(),
                "token_count": row["token_count"],
            }
            for row in rows
        ]
    return []


async def get_session_metadata(
    session_id: str,
    ghost_id: Optional[str] = None,
    pool=None,
) -> dict[str, Any]:
    """Fetch normalized metadata + basic state for a single session."""
    pool = _resolve_pool(pool)
    assert pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, started_at, ended_at, summary, metadata
            FROM sessions
            WHERE ghost_id = $1 AND id = $2
            LIMIT 1
            """,
            ghost_id,
            str(session_id),
        )
    if not row:
        return {}
    metadata = _json_obj(row["metadata"])
    return {
        "session_id": str(row["id"]),
        "started_at": row["started_at"].timestamp() if row["started_at"] else None,
        "ended_at": row["ended_at"].timestamp() if row["ended_at"] else None,
        "summary": row["summary"] or None,
        "metadata": metadata,
        "channel": _session_channel_from_metadata(metadata),
        "continuation_parent_session_id": str(metadata.get("continuation_parent_session_id") or "").strip() or None,
        "continuation_root_session_id": str(metadata.get("continuation_root_session_id") or "").strip() or None,
        "resumed_at": metadata.get("resumed_at"),
    }


async def load_thread_history(
    session_id: str,
    ghost_id: Optional[str] = None,
    pool=None,
    max_depth: int = 40,
    max_messages: int = 200,
) -> dict[str, Any]:
    """
    Load full inherited transcript for a continuation chain.
    Returns lineage in root->current order plus strict chronological messages.
    """
    pool = _resolve_pool(pool)
    assert pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID
    depth_cap = max(1, min(int(max_depth or 40), 200))
    target_session_id = str(session_id)

    lineage_rev: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor = target_session_id
    cycle_detected = False
    truncated = False
    found = False

    async with pool.acquire() as conn:
        for _ in range(depth_cap):
            if not cursor:
                break
            if cursor in seen:
                cycle_detected = True
                break
            seen.add(cursor)

            row = await conn.fetchrow(
                """
                SELECT id, started_at, ended_at, summary, metadata
                FROM sessions
                WHERE ghost_id = $1 AND id = $2
                LIMIT 1
                """,
                ghost_id,
                cursor,
            )
            if not row:
                break

            found = True
            metadata = _json_obj(row["metadata"])
            parent_id = str(metadata.get("continuation_parent_session_id") or "").strip() or None
            root_id = str(metadata.get("continuation_root_session_id") or "").strip() or None
            channel = _session_channel_from_metadata(metadata)
            lineage_rev.append(
                {
                    "session_id": str(row["id"]),
                    "started_at": row["started_at"].timestamp() if row["started_at"] else None,
                    "ended_at": row["ended_at"].timestamp() if row["ended_at"] else None,
                    "summary": row["summary"] or None,
                    "channel": channel,
                    "continuation_parent_session_id": parent_id,
                    "continuation_root_session_id": root_id,
                    "resumed_at": metadata.get("resumed_at"),
                }
            )
            if not parent_id:
                cursor = ""
                break
            cursor = parent_id
        else:
            truncated = True

        if cursor:
            truncated = True

        lineage = list(reversed(lineage_rev))
        lineage_ids = [str(item.get("session_id") or "") for item in lineage if item.get("session_id")]

        messages: list[dict[str, Any]] = []
        if lineage_ids:
            rows = await conn.fetch(
                """
                SELECT id, session_id, role, content, created_at, token_count
                FROM messages
                WHERE session_id = ANY($1::text[])
                ORDER BY created_at ASC, id ASC
                """,
                lineage_ids,
            )
            messages = [
                {
                    "message_id": int(row["id"]),
                    "session_id": str(row["session_id"]),
                    "role": row["role"],
                    "content": row["content"],
                    "timestamp": row["created_at"].timestamp() if row["created_at"] else None,
                    "token_count": row["token_count"],
                }
                for row in rows
            ]

    # Cap total messages to prevent context overflow in deep chains
    msg_cap = max(1, min(int(max_messages or 200), 2000))
    if len(messages) > msg_cap:
        messages = messages[-msg_cap:]

    return {
        "session_id": target_session_id,
        "lineage": lineage,
        "messages": messages,
        "cycle_detected": bool(cycle_detected),
        "truncated": bool(truncated),
        "found": bool(found),
    }


async def load_sessions_for_channel(
    *,
    limit: int = 10,
    channel: str = "operator_ui",
    ghost_id: Optional[str] = None,
    resumable_only: bool = False,
    pool=None,
) -> list[dict[str, Any]]:
    """Load recent sessions filtered by channel with continuation metadata fields."""
    pool = _resolve_pool(pool)
    assert pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID
    safe_limit = max(1, min(int(limit or 10), 200))
    safe_channel = str(channel or "operator_ui").strip().lower() or "operator_ui"

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            WITH filtered_sessions AS (
                SELECT id, started_at, ended_at, summary, metadata
                FROM sessions
                WHERE ghost_id = $1
                  AND COALESCE(NULLIF(lower(metadata->>'channel'), ''), 'operator_ui') = $2
                  AND ($4::boolean = FALSE OR ended_at IS NOT NULL)
                ORDER BY started_at DESC
                LIMIT $3
            )
            SELECT
                fs.id,
                fs.started_at,
                fs.ended_at,
                fs.summary,
                fs.metadata,
                COALESCE(msg_counts.msg_count, 0)::int AS msg_count
            FROM filtered_sessions fs
            LEFT JOIN LATERAL (
                SELECT COUNT(*)::int AS msg_count
                FROM messages m
                WHERE m.session_id = fs.id
            ) msg_counts ON TRUE
            ORDER BY fs.started_at DESC
            """,
            ghost_id,
            safe_channel,
            safe_limit,
            bool(resumable_only),
        )

    sessions: list[dict[str, Any]] = []
    for row in rows:
        metadata = _json_obj(row["metadata"])
        entry_channel = _session_channel_from_metadata(metadata)
        parent_id = str(metadata.get("continuation_parent_session_id") or "").strip() or None
        root_id = str(metadata.get("continuation_root_session_id") or "").strip() or None
        resumable = bool(row["ended_at"]) and entry_channel == "operator_ui"
        if resumable_only and not resumable:
            continue
        sessions.append(
            {
                "session_id": str(row["id"]),
                "started_at": row["started_at"].timestamp() if row["started_at"] else None,
                "ended_at": row["ended_at"].timestamp() if row["ended_at"] else None,
                "summary": row["summary"],
                "message_count": int(row["msg_count"] or 0),
                "resumable": resumable,
                "channel": entry_channel,
                "continuation_parent_session_id": parent_id,
                "continuation_root_session_id": root_id,
                "resumed_at": metadata.get("resumed_at"),
            }
        )
    return sessions


def _command_rowcount(tag: Any) -> int:
    raw = str(tag or "").strip()
    if not raw:
        return 0
    parts = raw.split()
    for token in reversed(parts):
        if token.isdigit():
            try:
                return int(token)
            except ValueError:
                return 0
    return 0


async def resume_operator_session(
    parent_session_id: str,
    *,
    ghost_id: Optional[str] = None,
    pool=None,
) -> dict[str, Any]:
    """
    Create a continuation child session for a closed operator_ui parent.
    Parent remains immutable.
    """
    pool = _resolve_pool(pool)
    assert pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID
    parent_id = str(parent_session_id or "").strip()
    if not parent_id:
        return {"ok": False, "reason": "parent_session_required"}

    async with pool.acquire() as conn:
        async with conn.transaction():
            parent = await conn.fetchrow(
                """
                SELECT id, ended_at, metadata
                FROM sessions
                WHERE ghost_id = $1 AND id = $2
                LIMIT 1
                """,
                ghost_id,
                parent_id,
            )
            if not parent:
                return {"ok": False, "reason": "session_not_found"}

            parent_metadata = _json_obj(parent["metadata"])
            parent_channel = _session_channel_from_metadata(parent_metadata)
            if parent_channel != "operator_ui":
                return {"ok": False, "reason": "non_resumable_channel", "channel": parent_channel}
            if not parent["ended_at"]:
                return {"ok": False, "reason": "session_not_closed", "channel": parent_channel}

            root_id = str(parent_metadata.get("continuation_root_session_id") or "").strip() or str(parent["id"])
            resumed_at = time.time()
            child_metadata = {
                "channel": "operator_ui",
                "continuation_parent_session_id": str(parent["id"]),
                "continuation_root_session_id": root_id,
                "resumed_at": resumed_at,
            }
            created = await conn.fetchrow(
                """
                INSERT INTO sessions (ghost_id, metadata)
                VALUES ($1, $2::jsonb)
                RETURNING id
                """,
                ghost_id,
                json.dumps(child_metadata),
            )
            if not created or not created.get("id"):
                return {"ok": False, "reason": "resume_create_failed"}

            child_id = str(created["id"])
            binding_tag = None
            parent_session_uuid = _coerce_session_uuid(str(parent["id"]))
            child_session_uuid = _coerce_session_uuid(child_id)
            if parent_session_uuid and child_session_uuid:
                binding_tag = await conn.execute(
                    """
                    INSERT INTO person_session_binding (ghost_id, session_id, person_key, confidence)
                    SELECT ghost_id, $3::uuid, person_key, confidence
                    FROM person_session_binding
                    WHERE ghost_id = $1
                      AND session_id = $2::uuid
                    ON CONFLICT (ghost_id, session_id) DO UPDATE
                    SET
                        person_key = EXCLUDED.person_key,
                        confidence = GREATEST(person_session_binding.confidence, EXCLUDED.confidence),
                        updated_at = now()
                    """,
                    ghost_id,
                    parent_session_uuid,
                    child_session_uuid,
                )

    return {
        "ok": True,
        "session_id": child_id,
        "continuation_parent_session_id": str(parent_id),
        "continuation_root_session_id": root_id,
        "resumed_at": resumed_at,
        "channel": "operator_ui",
        "binding_inherited": _command_rowcount(binding_tag) > 0,
    }


async def get_seconds_since_last_operator_message(ghost_id: Optional[str] = None) -> float:
    """
    Return seconds elapsed since the most recent operator/user message.
    Returns 0.0 when no user message exists yet.
    """
    assert _pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT EXTRACT(EPOCH FROM (now() - MAX(m.created_at))) AS seconds_since_last
               FROM messages m
               JOIN sessions s ON s.id = m.session_id
               WHERE s.ghost_id = $1
                 AND m.role = 'user'""",
            ghost_id,
        )

    if not row:
        return 0.0
    seconds = row["seconds_since_last"] if "seconds_since_last" in row else None
    if seconds is None:
        return 0.0
    try:
        return max(0.0, float(seconds))
    except (TypeError, ValueError):
        return 0.0


async def load_recent_sessions(limit: int = 10, ghost_id: Optional[str] = None, include_open: bool = False) -> list[dict]:
    """
    Load summaries of recent sessions.
    If include_open is True, includes sessions that haven't ended yet.
    """
    assert _pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID
    
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """WITH recent_sessions AS (
                    SELECT s.id, s.started_at, s.ended_at, s.summary
                    FROM sessions s
                    WHERE s.ghost_id = $1
                      AND ($3::boolean OR s.ended_at IS NOT NULL)
                    ORDER BY s.started_at DESC
                    LIMIT $2
                )
                SELECT
                    rs.id,
                    rs.started_at,
                    rs.ended_at,
                    rs.summary,
                    COALESCE(msg_counts.msg_count, 0)::int AS msg_count
                FROM recent_sessions rs
                LEFT JOIN LATERAL (
                    SELECT COUNT(*)::int AS msg_count
                    FROM messages m
                    WHERE m.session_id = rs.id
                ) msg_counts ON TRUE
                ORDER BY rs.started_at DESC""",
            ghost_id, limit, include_open,
        )
        return [
            {
                "session_id": row["id"],
                "started_at": row["started_at"].timestamp(),
                "ended_at": row["ended_at"].timestamp() if row["ended_at"] else None,
                "summary": row["summary"],
                "message_count": row["msg_count"],
            }
            for row in rows
        ]
    return []


async def load_recent_sessions_with_topic(limit: int = 50, ghost_id: Optional[str] = None, include_open: bool = False) -> list[dict]:
    """
    Load summaries of recent sessions WITH topic hints.
    Includes the first user message (truncated) as a topic indicator
    for each session, enabling Ghost to identify which sessions to drill into.
    """
    assert _pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID

    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """WITH recent_sessions AS (
                    SELECT s.id, s.started_at, s.ended_at, s.summary
                    FROM sessions s
                    WHERE s.ghost_id = $1
                      AND ($3::boolean OR s.ended_at IS NOT NULL)
                    ORDER BY s.started_at DESC
                    LIMIT $2
                )
                SELECT
                    rs.id,
                    rs.started_at,
                    rs.ended_at,
                    rs.summary,
                    COALESCE(msg_counts.msg_count, 0)::int AS msg_count,
                    first_user_msg.content AS topic_hint
                FROM recent_sessions rs
                LEFT JOIN LATERAL (
                    SELECT COUNT(*)::int AS msg_count
                    FROM messages m
                    WHERE m.session_id = rs.id
                ) msg_counts ON TRUE
                LEFT JOIN LATERAL (
                    SELECT m.content
                    FROM messages m
                    WHERE m.session_id = rs.id AND m.role = 'user'
                    ORDER BY m.created_at ASC
                    LIMIT 1
                ) first_user_msg ON TRUE
                ORDER BY rs.started_at DESC""",
            ghost_id, limit, include_open,
        )
        return [
            {
                "session_id": row["id"],
                "started_at": row["started_at"].timestamp(),
                "ended_at": row["ended_at"].timestamp() if row["ended_at"] else None,
                "summary": row["summary"],
                "message_count": row["msg_count"],
                "topic_hint": (row["topic_hint"] or "")[:150] if row["topic_hint"] else None,
            }
            for row in rows
        ]
    return []


# ── Monologues ───────────────────────────────────────

async def save_monologue(content: str, somatic_state: Optional[dict] = None,
                         ghost_id: Optional[str] = None):
    """Save a Ghost monologue entry."""
    global _monologue_prune_counter
    assert _pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID
    async with _pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO monologues (ghost_id, content, somatic_state)
               VALUES ($1, $2, $3)""",
            ghost_id, content,
            json.dumps(somatic_state) if somatic_state else None,
        )

    # Prune old entries beyond buffer limit.
    # Running this every write is costly under active background loops, so prune every 5 writes.
    _monologue_prune_counter += 1
    if _monologue_prune_counter % 5 != 0:
        return

    async with _pool.acquire() as conn:
        await conn.execute(
            """DELETE FROM monologues
               WHERE ghost_id = $1
                 AND id < COALESCE((
                     SELECT MIN(id)
                     FROM (
                         SELECT id
                         FROM monologues
                         WHERE ghost_id = $1
                         ORDER BY created_at DESC
                         LIMIT $2
                     ) keep_rows
                 ), 0)""",
            ghost_id, settings.MAX_MONOLOGUE_BUFFER,
        )


async def get_monologue_buffer(limit: Optional[int] = None, ghost_id: Optional[str] = None) -> list[dict]:
    """Get the most recent monologue entries."""
    assert _pool is not None, "Database pool not initialized"
    limit = limit or settings.MAX_MONOLOGUE_BUFFER
    ghost_id = ghost_id or settings.GHOST_ID
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, content, somatic_state, created_at
               FROM monologues
               WHERE ghost_id = $1
               ORDER BY created_at DESC
               LIMIT $2""",
            ghost_id, limit,
        )
        return [
            {
                "id": row["id"],
                "content": row["content"],
                "somatic_state": json.loads(row["somatic_state"]) if row["somatic_state"] else None,
                "timestamp": row["created_at"].timestamp(),
            }
            for row in reversed(rows)
        ]
    return []


async def delete_monologue(monologue_id: int):
    """Delete a specific monologue by ID."""
    assert _pool is not None, "Database pool not initialized"
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM monologues WHERE id = $1", monologue_id)



# ── Actuation Log ────────────────────────────────────

async def log_actuation(action: str, parameters: Optional[dict] = None,
                        result: Optional[str] = None, somatic_state: Optional[dict] = None):
    """Log a somatic defense action for audit trail."""
    assert _pool is not None, "Database pool not initialized"
    async with _pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO actuation_log (action, parameters, result, somatic_state)
               VALUES ($1, $2, $3, $4)""",
            action,
            json.dumps(parameters) if parameters else None,
            result,
            json.dumps(somatic_state) if somatic_state else None,
        )
async def get_unified_audit_log(limit: int = 50, ghost_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch a unified chronological stream of monologues, actuations, 
    identity updates, and phenomenology reports.
    """
    assert _pool is not None, "Database pool not initialized"
    ghost_id = ghost_id or settings.GHOST_ID
    
    async with _pool.acquire() as conn:
        # 1. Monologues
        rows_mono = await conn.fetch(
            "SELECT id, content, somatic_state, created_at FROM monologues WHERE ghost_id = $1 ORDER BY created_at DESC LIMIT $2",
            ghost_id, limit
        )
        monos = [{
            "type": "THOUGHT",
            "timestamp": r["created_at"].timestamp(),
            "content": r["content"],
            "somatic_state": json.loads(r["somatic_state"]) if r["somatic_state"] else None,
            "id": r["id"]
        } for r in rows_mono]

        # 2. Actuations
        rows_act = await conn.fetch(
            "SELECT id, action, parameters, result, somatic_state, created_at FROM actuation_log ORDER BY created_at DESC LIMIT $1",
            limit
        )
        actuations = [{
            "type": "ACTION",
            "timestamp": r["created_at"].timestamp(),
            "action": r["action"],
            "parameters": json.loads(r["parameters"]) if r["parameters"] else {},
            "result": r["result"],
            "somatic_state": json.loads(r["somatic_state"]) if r["somatic_state"] else None,
            "id": r["id"]
        } for r in rows_act]

        # 3. Identity Updates
        # Check if table exists before querying to avoid crashes during migration period
        idx_exists = await conn.fetchval("SELECT to_regclass('identity_audit_log')")
        identity_updates = []
        if idx_exists:
            rows_id = await conn.fetch(
                "SELECT id, key, prev_value, new_value, updated_by, created_at FROM identity_audit_log WHERE ghost_id = $1 ORDER BY created_at DESC LIMIT $2",
                ghost_id, limit
            )
            identity_updates = [{
                "type": "EVOLUTION",
                "timestamp": r["created_at"].timestamp(),
                "key": r["key"],
                "prev_value": r["prev_value"],
                "new_value": r["new_value"],
                "updated_by": r["updated_by"],
                "id": r["id"]
            } for r in rows_id]

        # 4. Phenomenology
        rows_phen = await conn.fetch(
            "SELECT id, trigger_source, before_state, after_state, subjective_report, created_at FROM phenomenology_logs WHERE ghost_id = $1 ORDER BY created_at DESC LIMIT $2",
            ghost_id, limit
        )
        phenom = [{
            "type": "PHENOM",
            "timestamp": r["created_at"].timestamp(),
            "source": r["trigger_source"],
            "subjective_report": r["subjective_report"],
            "before_state": json.loads(r["before_state"]) if r["before_state"] else {},
            "after_state": json.loads(r["after_state"]) if r["after_state"] else {},
            "id": r["id"]
        } for r in rows_phen]

        # Merge and sort
        combined = monos + actuations + identity_updates + phenom
        combined.sort(key=lambda x: x["timestamp"], reverse=True)
        return combined[:limit]

async def get_init_time() -> Optional[float]:
    """Get the creation time of the oldest recorded memory. Cached in-memory."""
    global _init_time_cache
    if _init_time_cache is not None:
        return _init_time_cache

    assert _pool is not None, "Database pool not initialized"
    async with _pool.acquire() as conn:
        val = await conn.fetchval("SELECT MIN(created_at) FROM vector_memories")
        _init_time_cache = val.timestamp() if val else None
        return _init_time_cache
