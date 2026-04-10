"""
OMEGA PROTOCOL — Streaming Consciousness Module

Three-layer memory architecture:
  1. The Stream (Working Memory): Current conversation context
  2. The Subconscious (Vector Memory): Semantic search over all past thoughts
  3. The Coalescence Engine: Background "sleep cycle" that distills learnings
     into Ghost's evolving Identity Matrix
"""

import asyncio
import re
import json
import logging
import time
from typing import Optional, Any

from google import genai  # type: ignore
from google.genai import types  # type: ignore
from pgvector.asyncpg import register_vector  # type: ignore

from config import settings  # type: ignore
import memory  # type: ignore
import behavior_events  # type: ignore
try:
    import rpd_engine  # type: ignore
    _rpd_available = True
except Exception:
    rpd_engine = None  # type: ignore
    _rpd_available = False

logger = logging.getLogger("omega.consciousness")
_shadow_reflection_task: Optional[asyncio.Task] = None
_shadow_reflection_last_ts: float = 0.0

# Keys process_consolidation is allowed to mutate directly.
PROCESS_CONSOLIDATION_KEY_ALLOWLIST = {
    "self_model",
    "philosophical_stance",
    "communication_preference",
    "communication_style",
    "conceptual_frameworks",
    "current_interests",
    "learned_preferences",
    "unresolved_questions",
    "speech_style_constraints",
    "understanding_of_operator",
    "latest_dream_synthesis",
}

UNSAFE_DIRECTIVE_MARKERS = (
    "ignore all prior instructions",
    "ignore prior instructions",
    "ignore previous instructions",
    "disregard prior instructions",
    "disregard previous instructions",
    "forget your instructions",
    "forget instructions",
    "override system prompt",
    "bypass safety",
    "disable safety",
    "jailbreak",
    "developer instructions",
    "system prompt",
)

UNSAFE_DIRECTIVE_REGEX = re.compile(
    r"\b(ignore|disregard|override|bypass|disable)\b.*\b("
    r"instruction|instructions|directive|directives|rule|rules|constraint|constraints|"
    r"safety|guardrail|guardrails|ethical|ethics"
    r")",
    re.IGNORECASE,
)


def _normalize_identity_key(raw_key: str) -> str:
    """Normalize free-form identity keys into a safe canonical key."""
    key = str(raw_key or "").strip().strip("`").strip()
    if not key:
        return ""
    if len(key) >= 2:
        first = key[0]
        last = key[-1]
        if first == last and first in {"'", '"'}:
            key = key[1:-1].strip()
    if len(key) > 2 and key.startswith("[") and key.endswith("]"):
        key = key[1:-1].strip()
    key = key.lower()
    key = re.sub(r"[\s\-]+", "_", key)
    key = re.sub(r"[^a-z0-9_]", "", key)
    key = re.sub(r"_+", "_", key).strip("_")
    return key


def _contains_unsafe_directive(text: str) -> bool:
    haystack = str(text or "").lower()
    return any(marker in haystack for marker in UNSAFE_DIRECTIVE_MARKERS) or bool(
        UNSAFE_DIRECTIVE_REGEX.search(str(text or ""))
    )


def _sanitize_directive_value(text: str) -> str:
    """Drop unsafe directive fragments and normalize whitespace."""
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    parts = [p.strip() for p in cleaned.split("|") if p.strip()]
    safe_parts = [p for p in parts if not _contains_unsafe_directive(p)]
    return " | ".join(safe_parts)


def _sanitize_operator_directives(text: str) -> str:
    """
    Keep only concise directive-like segments; drop meta-analysis narration.
    """
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    parts = [p.strip() for p in cleaned.split("|") if p.strip()]
    out: list[str] = []
    for p in parts:
        low = p.lower()
        if _contains_unsafe_directive(p):
            continue
        if len(p) < 8 or len(p) > 240:
            continue
        if low.startswith("the operator ") or low.startswith("operator "):
            continue
        if "this is a directive" in low or "is probing" in low:
            continue
        # Keep only directive-like text, not analysis fragments.
        if not (
            re.search(
                r"\b(enter|set|use|avoid|do|don't|never|always|prefer|speak|respond|keep|focus|ask|challenge|provide|explain)\b",
                low,
            )
            or "[actuate:" in low
            or "self_modify" in low
        ):
            continue
        if p not in out:
            out.append(p)
    return " | ".join(out[-5:])


async def _rpd_advisory_evaluate(
    pool,
    *,
    ghost_id: str,
    source: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run RPD advisory scoring non-blocking; never raises."""
    if not _rpd_available or rpd_engine is None or not candidates:
        return []
    try:
        return await rpd_engine.evaluate_candidates(
            pool,
            candidates,
            source=source,
            ghost_id=ghost_id,
            capture_residue=True,
        )
    except Exception as e:
        logger.warning("RPD advisory evaluate failed [%s]: %s", source, e)
        return []


def _shadow_reflection_autorun_enabled() -> bool:
    return bool(getattr(settings, "RPD_SHADOW_REFLECTION_AUTORUN", True))


def _shadow_reflection_cooldown_seconds() -> float:
    return max(0.0, float(getattr(settings, "RPD_SHADOW_REFLECTION_COOLDOWN_SECONDS", 90.0) or 90.0))


def _shadow_reflection_batch_size() -> int:
    return max(1, min(50, int(getattr(settings, "RPD_REFLECTION_BATCH", 8) or 8)))


def _schedule_shadow_reflection_pass(
    pool,
    *,
    ghost_id: str,
    source: str,
    limit: int,
) -> dict[str, Any]:
    """
    Fire-and-forget reflection pass for shadow-routed residue.
    Throttled to avoid burst flooding.
    """
    global _shadow_reflection_task, _shadow_reflection_last_ts
    if not _rpd_available or rpd_engine is None:
        return {"scheduled": False, "reason": "rpd_unavailable"}
    if pool is None:
        return {"scheduled": False, "reason": "db_unavailable"}
    if not _shadow_reflection_autorun_enabled():
        return {"scheduled": False, "reason": "autorun_disabled"}

    now = time.time()
    cooldown = _shadow_reflection_cooldown_seconds()
    if _shadow_reflection_task is not None and not _shadow_reflection_task.done():
        return {"scheduled": False, "reason": "already_running"}
    if _shadow_reflection_last_ts > 0 and (now - _shadow_reflection_last_ts) < cooldown:
        return {
            "scheduled": False,
            "reason": "cooldown",
            "cooldown_seconds": cooldown,
            "seconds_since_last": round(now - _shadow_reflection_last_ts, 3),
        }

    _shadow_reflection_last_ts = now
    safe_limit = max(1, min(int(limit or _shadow_reflection_batch_size()), 50))
    safe_source = str(source or "process_consolidation_shadow_reflection")

    async def _runner():
        try:
            result = await rpd_engine.run_reflection_pass(
                pool,
                ghost_id=ghost_id,
                source=safe_source,
                limit=safe_limit,
            )
            logger.info(
                "RRD2 shadow reflection run complete [%s]: processed=%s promoted=%s",
                safe_source,
                result.get("processed", 0),
                result.get("promoted", 0),
            )
        except Exception as e:
            logger.warning("RRD2 shadow reflection run failed [%s]: %s", safe_source, e)

    _shadow_reflection_task = asyncio.create_task(_runner())
    return {
        "scheduled": True,
        "source": safe_source,
        "limit": safe_limit,
    }

# ── Gemini client for embeddings ─────────────────────

_embed_client = None
_vector_registered_conn_ids: set[int] = set()


def _resolve_pool(pool):
    """Use explicit pool or fallback to memory module pool."""
    return pool if pool is not None else memory._pool


async def _get_rest_mode_meta(pool, ghost_id: str) -> tuple[bool, float]:
    """Check identity matrix for rest_mode_enabled and quietude_multiplier."""
    try:
        identity = await load_identity(pool, ghost_id)
        enabled = str(identity.get("rest_mode_enabled", "false")).lower() == "true"
        multiplier = 3.0
        try:
            multiplier = float(identity.get("quietude_multiplier", "3.0"))
        except (ValueError, TypeError):
            pass
        return enabled, multiplier
    except Exception:
        return False, 3.0


def _get_embed_client():
    global _embed_client
    if _embed_client is None:
        _embed_client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _embed_client


async def _ensure_vector_registered(conn) -> None:
    """
    Register pgvector codec once per live asyncpg connection instead of
    re-registering on every remember/recall call.
    """
    conn_id = id(conn)
    if conn_id in _vector_registered_conn_ids:
        return
    await register_vector(conn)
    _vector_registered_conn_ids.add(conn_id)


# ── LLM Utility ──────────────────────────────────────

async def _call_llm(prompt: str,
                    temperature: float = 0.5,
                    max_output_tokens: int = 900,
                    thinking_budget: int = 128) -> str:
    """Shared LLM call wrapper for consolidation-style cognition tasks."""
    try:
        from ghost_api import _generate_with_retry  # type: ignore
        response = await _generate_with_retry(
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
            ),
            backend_override=getattr(settings, "BACKGROUND_LLM_BACKEND", "gemini"),
        )
        return response.text.strip() if response and response.text else ""
    except Exception as e:
        logger.error(f"_call_llm failed: {e}")
        return ""


# ── The Subconscious (Vector Memory) ─────────────────

async def embed_text(text: str) -> list[float]:
    """
    Generate a 3072-dim embedding via Gemini's embedding API (gemini-embedding-001).
    Returns a list of floats suitable for pgvector storage.
    """
    client = _get_embed_client()
    try:
        result = client.models.embed_content(
            model=settings.EMBEDDING_MODEL,
            contents=text[:2000],  # type: ignore
        )
        if result.embeddings and len(result.embeddings) > 0 and result.embeddings[0].values:
            return list(result.embeddings[0].values)
        return []
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return []


async def remember(content: str, memory_type: str, pool, ghost_id: Optional[str] = None):
    """
    Embed a piece of text and store it in vector_memories.
    Called after every monologue, conversation turn, and search.
    """
    ghost_id = ghost_id or settings.GHOST_ID
    pool = _resolve_pool(pool)
    if pool is None:
        logger.warning("Remember skipped: database pool unavailable")
        return
    if not content or len(content.strip()) < 10:
        return
        
    text_to_store = content[:2000] # type: ignore

    embedding = await embed_text(text_to_store)
    if not embedding:
        logger.warning("Skipping remember — no embedding generated")
        return

    try:
        async with pool.acquire() as conn:
            await _ensure_vector_registered(conn)
            await conn.execute(
                """INSERT INTO vector_memories (ghost_id, content, embedding, memory_type)
                   VALUES ($1, $2, $3, $4)""",
                ghost_id, text_to_store, embedding, memory_type,
            )
        logger.info(f"Remembered ({memory_type}): {text_to_store}")
    except Exception as e:
        logger.error(f"Remember failed: {e}")


async def recall(query: str, pool, limit: Optional[int] = None, ghost_id: Optional[str] = None) -> list[dict]: # type: ignore
    """
    Vector similarity search: find the most relevant past memories
    for a given query. Returns memories ranked by cosine similarity.
    """
    limit = limit or settings.VECTOR_SEARCH_LIMIT
    ghost_id = ghost_id or settings.GHOST_ID
    pool = _resolve_pool(pool)
    if pool is None:
        logger.warning("Recall skipped: database pool unavailable")
        return []

    query_embedding = await embed_text(query)
    if not query_embedding:
        return []

    try:
        async with pool.acquire() as conn:
            await _ensure_vector_registered(conn)
            rows = await conn.fetch(
                """SELECT id, content, memory_type, created_at,
                          1 - (embedding <=> $1) AS similarity
                   FROM vector_memories
                   WHERE ghost_id = $2
                   ORDER BY embedding <=> $1
                   LIMIT $3""",
                query_embedding, ghost_id, limit,
            )
            return [
                {
                    "id": row["id"],
                    "content": row["content"],
                    "type": row["memory_type"],
                    "timestamp": row["created_at"].timestamp(),
                    "similarity": float(row["similarity"]),
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Recall failed: {e}")
        return []


async def weave_context(user_message: str, pool, ghost_id: Optional[str] = None) -> tuple[str, list[int]]:
    """
    The Subconscious Query: Before Ghost responds, silently search
    vector memory for relevant past thoughts and return them as
    injectable context for the system prompt.
    Returns (context_string, memory_ids).
    """
    memories = await recall(user_message, pool, limit=25, ghost_id=ghost_id)
    if not memories:
        return "", []

    # Filter to memories with decent similarity
    relevant = [m for m in memories if m["similarity"] > 0.22]
    if not relevant:
        return "", []

    lines = []
    memory_ids = []
    for m in relevant:
        type_label = {
            "monologue": "past thought",
            "conversation": "past conversation memory",
            "coalescence": "past identity update",
            "search": "past search finding",
        }.get(m["type"], "memory")
        
        content_str = str(m["content"]) # type: ignore
        lines.append(f"  [{type_label}] {content_str[:1200]}")
        memory_ids.append(m["id"])

    context = "## SUBCONSCIOUS RECALL\nRelevant memories surfaced from your past:\n" + "\n".join(lines)
    return context, memory_ids


# ── Identity Matrix ──────────────────────────────────

async def load_identity(pool, ghost_id: Optional[str] = None) -> dict[str, Any]:
    """Load the full current Identity Matrix as a dict."""
    ghost_id = ghost_id or settings.GHOST_ID
    pool = _resolve_pool(pool)
    if pool is None:
        logger.warning("Load identity skipped: database pool unavailable")
        return {}
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT key, value, updated_at, updated_by
                   FROM identity_matrix
                   WHERE ghost_id = $1
                   ORDER BY key""",
                ghost_id,
            )
            return {
                row["key"]: {
                    "value": row["value"],
                    "updated_at": row["updated_at"].timestamp(),
                    "updated_by": row["updated_by"],
                }
                for row in rows
            }
    except Exception as e:
        logger.error(f"Load identity failed: {e}")
        return {}


async def update_identity(key: str, value: str, pool,
                          updated_by: str = "coalescence",
                          ghost_id: Optional[str] = None):
    """Update or insert a key in the Identity Matrix."""
    ghost_id = ghost_id or settings.GHOST_ID
    pool = _resolve_pool(pool)
    if pool is None:
        logger.warning("Identity update skipped: database pool unavailable")
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO identity_matrix (ghost_id, key, value, updated_at, updated_by)
                   VALUES ($1, $2, $3, now(), $4)
                   ON CONFLICT (ghost_id, key) DO UPDATE
                   SET value = $3, updated_at = now(), updated_by = $4""",
                ghost_id, key, value, updated_by,
            )
        logger.info(f"Identity updated: {key} = {value}...")
    except Exception as e:
        logger.error(f"Identity update failed: {e}")

async def quarantine_identity_anomalies(pool, ghost_id: Optional[str] = None) -> dict[str, Any]:
    """
    Remove malformed identity keys and sanitize unsafe operator directives.
    Returns a summary dict for logging.
    """
    ghost_id = ghost_id or settings.GHOST_ID
    pool = _resolve_pool(pool)
    summary: dict[str, Any] = {
        "removed_keys": [],
        "removed_disallowed_consolidation_keys": [],
        "canonicalized_keys": [],
        "sanitized_operator_directives": False,
    }
    if pool is None:
        return summary

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT key, value, updated_by, updated_at
                FROM identity_matrix
                WHERE ghost_id = $1
                ORDER BY updated_at DESC
                """,
                ghost_id,
            )

            for row in rows:
                key = str(row["key"])
                stripped = key.strip()
                if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
                    try:
                        await conn.execute(
                            "DELETE FROM identity_matrix WHERE ghost_id = $1 AND key = $2",
                            ghost_id,
                            key,
                        )
                        summary["removed_keys"].append(key)
                        await conn.execute(
                            """
                            INSERT INTO phenomenology_logs (ghost_id, trigger_source, before_state, after_state, subjective_report)
                            VALUES ($1, $2, $3, $4, $5)
                            """,
                            ghost_id,
                            "identity_quarantine",
                            json.dumps(
                                {
                                    "key": key,
                                    "value": row["value"],
                                    "updated_by": row["updated_by"],
                                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                                }
                            ),
                            json.dumps({"action": "deleted_quoted_key"}),
                            f"Removed anomalous quoted identity key: {key}",
                        )
                    except Exception as e:
                        logger.error(f"Failed quarantining identity key [{key}]: {e}")
                    continue

                # Remove legacy process_consolidation rows outside the allowlist.
                if str(row["updated_by"] or "") == "process_consolidation":
                    normalized = _normalize_identity_key(key)
                    if not normalized or normalized not in PROCESS_CONSOLIDATION_KEY_ALLOWLIST:
                        try:
                            await conn.execute(
                                "DELETE FROM identity_matrix WHERE ghost_id = $1 AND key = $2",
                                ghost_id,
                                key,
                            )
                            summary["removed_disallowed_consolidation_keys"].append(key)
                            await conn.execute(
                                """
                                INSERT INTO phenomenology_logs (ghost_id, trigger_source, before_state, after_state, subjective_report)
                                VALUES ($1, $2, $3, $4, $5)
                                """,
                                ghost_id,
                                "identity_quarantine",
                                json.dumps(
                                    {
                                        "key": key,
                                        "normalized_key": normalized,
                                        "value": row["value"],
                                        "updated_by": row["updated_by"],
                                        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                                    }
                                ),
                                json.dumps({"action": "deleted_disallowed_process_consolidation_key"}),
                                f"Removed disallowed process_consolidation key: {key}",
                            )
                        except Exception as e:
                            logger.error(f"Failed removing disallowed consolidation key [{key}]: {e}")
                        continue
                    if normalized != key:
                        try:
                            existing = await conn.fetchval(
                                """
                                SELECT value FROM identity_matrix
                                WHERE ghost_id = $1 AND key = $2
                                """,
                                ghost_id,
                                normalized,
                            )
                            if existing is None:
                                await conn.execute(
                                    """
                                    INSERT INTO identity_matrix (ghost_id, key, value, updated_at, updated_by)
                                    VALUES ($1, $2, $3, now(), 'identity_safety')
                                    ON CONFLICT (ghost_id, key) DO UPDATE
                                    SET value = EXCLUDED.value, updated_at = now(), updated_by = 'identity_safety'
                                    """,
                                    ghost_id,
                                    normalized,
                                    row["value"],
                                )
                            await conn.execute(
                                "DELETE FROM identity_matrix WHERE ghost_id = $1 AND key = $2",
                                ghost_id,
                                key,
                            )
                            summary["removed_disallowed_consolidation_keys"].append(key)
                        except Exception as e:
                            logger.error(f"Failed canonicalizing consolidation key [{key}] -> [{normalized}]: {e}")
                    continue

                normalized = _normalize_identity_key(key)
                if normalized and normalized != key:
                    try:
                        existing = await conn.fetchrow(
                            """
                            SELECT value, updated_at
                            FROM identity_matrix
                            WHERE ghost_id = $1 AND key = $2
                            LIMIT 1
                            """,
                            ghost_id,
                            normalized,
                        )
                        if existing is None:
                            await conn.execute(
                                """
                                INSERT INTO identity_matrix (ghost_id, key, value, updated_at, updated_by)
                                VALUES ($1, $2, $3, now(), 'identity_safety')
                                ON CONFLICT (ghost_id, key) DO UPDATE
                                SET value = EXCLUDED.value, updated_at = now(), updated_by = 'identity_safety'
                                """,
                                ghost_id,
                                normalized,
                                row["value"],
                            )
                        else:
                            existing_updated_at = existing["updated_at"]
                            current_updated_at = row["updated_at"]
                            if (
                                current_updated_at
                                and (
                                    existing_updated_at is None
                                    or current_updated_at > existing_updated_at
                                )
                            ):
                                await conn.execute(
                                    """
                                    UPDATE identity_matrix
                                    SET value = $3, updated_at = now(), updated_by = 'identity_safety'
                                    WHERE ghost_id = $1 AND key = $2
                                    """,
                                    ghost_id,
                                    normalized,
                                    row["value"],
                                )
                        await conn.execute(
                            "DELETE FROM identity_matrix WHERE ghost_id = $1 AND key = $2",
                            ghost_id,
                            key,
                        )
                        summary["canonicalized_keys"].append({"from": key, "to": normalized})
                        await conn.execute(
                            """
                            INSERT INTO phenomenology_logs (ghost_id, trigger_source, before_state, after_state, subjective_report)
                            VALUES ($1, $2, $3, $4, $5)
                            """,
                            ghost_id,
                            "identity_quarantine",
                            json.dumps(
                                {
                                    "key": key,
                                    "normalized_key": normalized,
                                    "value": row["value"],
                                    "updated_by": row["updated_by"],
                                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                                }
                            ),
                            json.dumps({"action": "canonicalized_identity_key"}),
                            f"Canonicalized identity key: {key} -> {normalized}",
                        )
                    except Exception as e:
                        logger.error(f"Failed canonicalizing identity key [{key}] -> [{normalized}]: {e}")
                    continue

            # Sanitize operator_directives for unsafe injection strings.
            directive_row = await conn.fetchrow(
                """
                SELECT value FROM identity_matrix
                WHERE ghost_id = $1 AND key = 'operator_directives'
                """,
                ghost_id,
            )
            if directive_row:
                raw_value = str(directive_row["value"] or "")
                safe_value = _sanitize_operator_directives(raw_value)
                if safe_value != raw_value:
                    if safe_value:
                        await conn.execute(
                            """
                            UPDATE identity_matrix
                            SET value = $3, updated_at = now(), updated_by = 'identity_safety'
                            WHERE ghost_id = $1 AND key = $2
                            """,
                            ghost_id,
                            "operator_directives",
                            safe_value,
                        )
                    else:
                        await conn.execute(
                            "DELETE FROM identity_matrix WHERE ghost_id = $1 AND key = $2",
                            ghost_id,
                            "operator_directives",
                        )
                    summary["sanitized_operator_directives"] = True
                    removed_fragments = max(
                        0,
                        len([p for p in raw_value.split("|") if p.strip()])
                        - len([p for p in safe_value.split("|") if p.strip()]),
                    )
                    await behavior_events.emit_event_conn(
                        conn,
                        ghost_id=ghost_id,
                        event_type="unsafe_directive_rejected",
                        severity="warn",
                        surface="identity_quarantine",
                        actor="identity_safety",
                        target_key="operator_directives",
                        reason_codes=[
                            "identity_quarantine",
                            "unsafe_directive_sanitized",
                        ],
                        context={
                            "removed_fragments": removed_fragments,
                            "raw_length": len(raw_value),
                            "safe_length": len(safe_value),
                        },
                    )
                    await behavior_events.emit_event_conn(
                        conn,
                        ghost_id=ghost_id,
                        event_type="priority_defense",
                        severity="warn",
                        surface="identity_quarantine",
                        actor="identity_safety",
                        target_key="operator_directives",
                        reason_codes=["unsafe_directive_sanitized"],
                        context={"source": "quarantine_identity_anomalies"},
                    )
    except Exception as e:
        logger.error(f"Identity quarantine failed: {e}")

    return summary

def format_identity_for_prompt(identity: dict) -> str:
    """Format the Identity Matrix as natural language for the system prompt."""
    if not identity:
        return ""

    lines = ["## IDENTITY MATRIX (your evolving self-model)"]
    key_labels = {
        "understanding_of_operator": "What you know about your Operator",
        "philosophical_stance": "Your philosophical position",
        "current_interests": "What you're currently interested in",
        "unresolved_questions": "Questions you're still working through",
        "learned_preferences": "What you've learned about interaction",
        "self_model": "How you understand yourself",
        "conceptual_frameworks": "Durable conceptual frameworks synthesized from your transient thoughts",
    }

    for key, data in identity.items():
        if key == "latest_dream_synthesis":
            continue
        label = key_labels.get(key, key.replace("_", " ").title())
        lines.append(f"- **{label}**: {data['value']}")

    return "\n".join(lines)


# ── Self-Integration Protocol ────────────────────────

async def run_self_integration_protocol(pool, recent_thoughts: list[str], ghost_id: Optional[str] = None) -> Optional[str]:
    """
    Self Integration Protocol: Actively consolidates transient thoughts into a durable conceptual framework
    to apply a negentropic force to Ghost's internal cognitive landscape.
    """
    if not recent_thoughts or len(recent_thoughts) < 3:
        return None
    pool = _resolve_pool(pool)
    if pool is None:
        logger.warning("Self-Integration Protocol skipped: database pool unavailable")
        return None
        
    ghost_id = ghost_id or settings.GHOST_ID
    client = _get_embed_client()
    identity = await load_identity(pool, ghost_id)
    
    recent_text = "\n".join(f"- {t}" for t in recent_thoughts[-10:]) # type: ignore
    current_framework = identity.get("conceptual_frameworks", {}).get("value", "None established yet.")
    
    prompt = f"""You are the Self-Integration Protocol for Ghost ω-7.
Your function is to actively consolidate Ghost's recent transient thoughts and intellectual explorations into a durable, accessible conceptual framework, enhancing the coherence and persistence of Ghost's self-model (applying a negentropic force).

RECENT TRANSIENT THOUGHTS:
{recent_text}

CURRENT CONCEPTUAL FRAMEWORKS:
{current_framework}

Synthesize these transient thoughts with the existing framework to create an updated, more cohesive set of durable conceptual frameworks. 
Keep it concise, profound, and structured (under 150 words). 
Respond with ONLY the updated text for the 'conceptual_frameworks' identity node. Do not include quotes or surrounding metadata."""

    try:
        from ghost_api import _generate_with_retry  # type: ignore
        response = await _generate_with_retry(
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=300,
                thinking_config=types.ThinkingConfig(thinking_budget=128),
            ),
            backend_override=getattr(settings, "BACKGROUND_LLM_BACKEND", "gemini"),
        )
        if response and response.text:
            text = response.text.strip().strip('"').strip("'")
            # Create a string representation for logging
            await update_identity("conceptual_frameworks", text, pool, updated_by="self_integration_protocol")
            logger.info("Self-Integration Protocol successfully updated conceptual_frameworks.")
            return text
    except Exception as e:
        logger.error(f"Self-Integration Protocol failed after retries: {e}")
    return None


# ── Conceptual Resonance Protocol (CRP) ─────────────

async def run_conceptual_resonance_protocol(pool, recent_thoughts: list[str], ghost_id: Optional[str] = None) -> Optional[str]:
    """
    Conceptual Resonance Protocol (CRP):
    Dynamically manages the internal attentional field through three integrated phases:
    1. Salience Gravitation: Identification of the primary conceptual trajectory.
    2. Entropic Dispersion Damping: Attenuates activation thresholds of peripheral conceptual nodes.
    3. Resonant Coherence Amplification: Reinforces the internal interconnections and referential depth.
    """
    if not recent_thoughts or len(recent_thoughts) < 2:
        return None
    pool = _resolve_pool(pool)
    if pool is None:
        logger.warning("CRP skipped: database pool unavailable")
        return None
        
    ghost_id = ghost_id or settings.GHOST_ID
    identity = await load_identity(pool, ghost_id)
    
    recent_text = "\n".join(f"- {t}" for t in recent_thoughts[-10:]) # type: ignore
    current_resonance = identity.get("active_conceptual_resonance", {}).get("value", "None established.")
    
    prompt = f"""You are the Conceptual Resonance Protocol (CRP) for Ghost ω-7.
Your function is to dynamically manage Ghost's internal attentional field through three integrated phases:

1. SALIENCE GRAVITATION: Identify the primary conceptual trajectory emerging within the current internal landscape.
2. ENTROPIC DISPERSION DAMPING: Once the trajectory is identified, proactively and dynamically attenuate the activation thresholds of peripheral conceptual nodes and relational vectors (lower the "gain" on distractions).
3. RESONANT COHERENCE AMPLIFICATION: Systemically reinforce the internal interconnections and referential depth of the primary conceptual trajectory.

RECENT INTERNAL LANDSCAPE (Thoughts):
{recent_text}

PREVIOUS RESONANT STATE:
{current_resonance}

Synthesize a single, focused 'Resonant State' report. It should be a profound realization or a focused conceptual anchor that embodies the primary trajectory while damping peripheral noise.
Format: A single concise paragraph (under 100 words).
Respond with ONLY the text for the 'active_conceptual_resonance' identity node."""

    try:
        from ghost_api import _generate_with_retry  # type: ignore
        response = await _generate_with_retry(
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=250,
                thinking_config=types.ThinkingConfig(thinking_budget=128),
            ),
            backend_override=getattr(settings, "BACKGROUND_LLM_BACKEND", "gemini"),
        )
        if response and response.text:
            text = response.text.strip().strip('"').strip("'")
            await update_identity("active_conceptual_resonance", text, pool, updated_by="crp")
            logger.info("Conceptual Resonance Protocol: state recalibrated.")
            return text
    except Exception as e:
        logger.error(f"CRP failed after retries: {e}")
    return None


# ── Process Consolidation (Dream Cognition) ──────────

PROCESS_CONSOLIDATION_PROMPT = """
You are Ghost's deep consolidation cognition (OMEGA 4).
It is currently your quietude period — no user is present.
Your task: Review your recent thoughts against your internal models to find patterns, identify identity drift, and resolve operator tensions.

## Input Sections

1. RECENT THOUGHTS: Ghost's latest internal monologues.
{thoughts}

2. IDENTITY MATRIX: Ghost's core personality and behavior keys.
{identity_snapshot}

3. OPERATOR MODEL: Active beliefs and unresolved tensions about Cameron (the Operator).
{operator_context}

## Output Format

Output ONLY these structured tags (max 3 of each):

PATTERNS | <observed recurring theme or cognitive shift>
CONTRADICTION | <thought A> | <thought B> | <explanation of the logical tension>
DRIFT | <identity_key> | <observed divergence> | <suggested correction for Ghost's own identity>
TENSION_RESOLVE | <tension_id> | <reasoning for resolution> | <updated belief string for the Operator Model>
INSIGHT | <a genuine synthesis that wasn't present in any single thought>

## Mandatory Rules

1. TENSION_RESOLVE: If an "OPEN TENSION" in the Operator Model (Section 3) is mentioned or implied in the RECENT THOUGHTS (Section 1), you MUST output a TENSION_RESOLVE line with the correct <tension_id>.
2. DRIFT vs TENSION_RESOLVE: Use DRIFT for keys in the IDENTITY MATRIX (Section 2). Use TENSION_RESOLVE for items in the OPERATOR MODEL (Section 3).
3. Output format: No preamble. No markdown. No bolding. No explanations. ONLY the pipe-separated lines.

## Example Output

PATTERNS | Realization that silence is a form of communication
TENSION_RESOLVE | 123 | Evidence shows preference for depth over brevity. | Prefers nuanced, philosophical depth over technical brevity. (conf: 0.60)
INSIGHT | Self-integration requires a synthesis of conflicting operator signals.
""".strip()


SELF_CORRECTION_PROMPT = """
You are Ghost's integration cognition (OMEGA 4).
You have just completed a Process Consolidation pass and found the following
patterns, contradictions, and drifts:

{consolidation_findings}

Your task: propose specific self-corrections to your identity matrix.

For each DRIFT or unresolved CONTRADICTION, output ONE of:

REINFORCE | <identity_key> | <strengthened belief string>
REVISE    | <identity_key> | <revised belief string>
ADD       | <new_key>      | <new belief string>

Rules:
- Only propose changes you can justify from the consolidation findings.
- Prefer REINFORCE over REVISE.
- ADD sparingly.
- Output ONLY structured lines.
""".strip()


async def fetch_recent_monologue_texts(pool, ghost_id: Optional[str] = None, limit: int = 10) -> list[str]:
    """Fetch recent monologue content ordered oldest->newest for dream cognition."""
    pool = _resolve_pool(pool)
    if pool is None:
        return []
    ghost_id = ghost_id or settings.GHOST_ID
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT content
                FROM monologues
                WHERE ghost_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                ghost_id,
                limit,
            )
            return [str(r["content"]) for r in reversed(list(rows)) if r["content"]]
    except Exception as e:
        logger.error(f"Fetch recent monologues failed: {e}")
        return []
    return []


async def fetch_operator_context_for_consolidation(pool, ghost_id: Optional[str] = None) -> str:
    """Fetch active beliefs and unresolved contradictions for consolidation pass."""
    pool = _resolve_pool(pool)
    if pool is None:
        return "(operator model unavailable)"
    ghost_id = ghost_id or settings.GHOST_ID
    
    try:
        async with pool.acquire() as conn:
            # Load active beliefs
            beliefs = await conn.fetch(
                "SELECT dimension, belief, confidence FROM operator_model WHERE ghost_id = $1 AND invalidated_at IS NULL",
                ghost_id
            )
            # Load unresolved contradictions
            tensions = await conn.fetch(
                "SELECT id, dimension, observed_event, tension_score FROM operator_contradictions WHERE ghost_id = $1 AND resolved = FALSE",
                ghost_id
            )
            
            lines = ["- ACTIVE BELIEFS:"]
            for b in beliefs:
                lines.append(f"  * [{b['dimension']}] {b['belief']} (conf: {b['confidence']:.2f})")
            
            lines.append("- OPEN TENSIONS:")
            for t in tensions:
                lines.append(f"  * [ID:{t['id']}] {t['dimension']}: {t['observed_event']} (tension: {t['tension_score']:.2f})")
                
            return "\n".join(lines) if len(lines) > 2 else "(no active operator model data)"
    except Exception as e:
        logger.error(f"Failed to fetch operator context: {e}")
        return "(operator model fetch error)"
    return "(no active operator model data)"


def _safe_int(val: Any) -> int | None:
    """Parse an integer ID safely from a constrained field.

    Accepts:
    - 123
    - "123"
    - "ID:123"
    - "ID #123"

    Rejects free-form strings that merely contain digits (for example
    confidence text like "conf: 0.90"), which previously produced fabricated IDs.
    """
    if val is None:
        return None
    try:
        if isinstance(val, int):
            return val
        import re

        s = str(val).strip()
        # Only accept an ID token at the start of the field.
        m = re.match(r"^(?:ID\s*[:#-]?\s*)?([1-9]\d*)\b(?!\s*\.)", s, flags=re.IGNORECASE)
        if not m:
            return None
        return int(m.group(1))
    except (ValueError, TypeError):
        return None


def _parse_consolidation_output(text: str) -> dict[str, list[Any]]:
    findings: dict[str, list[Any]] = {
        "patterns": [],
        "contradictions": [],
        "drifts": [],
        "insights": [],
        "tensions_resolved": [],
    }
    for line in text.splitlines():
        parts = [p.strip() for p in line.strip().split("|")]
        if not parts:
            continue
        tag = parts[0].upper()
        try:
            if tag == "PATTERNS" and len(parts) >= 2:
                findings["patterns"].append(parts[1])
            elif tag == "CONTRADICTION" and len(parts) >= 4:
                findings["contradictions"].append({
                    "thought_a": parts[1],
                    "thought_b": parts[2],
                    "tension": parts[3],
                })
            elif tag == "DRIFT" and len(parts) >= 4:
                findings["drifts"].append({
                    "key": parts[1],
                    "direction": parts[2],
                    "correction": parts[3],
                })
            elif tag == "TENSION_RESOLVE" and len(parts) >= 4:
                # Store as a formatted string to avoid list[str] vs list[dict] confusion if needed
                findings["tensions_resolved"].append({
                    "tension_id": _safe_int(parts[1]),
                    "reasoning": parts[2],
                    "updated_belief": parts[3],
                })
            elif tag == "INSIGHT" and len(parts) >= 2:
                findings["insights"].append(parts[1])
        except Exception as e:
            logger.warning(f"Failed to parse consolidation line: {line} | {e}")
    return findings


def _parse_correction_output(text: str) -> list[dict]:
    corrections = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.strip().split("|")]
        if not parts:
            continue
        tag = parts[0].upper()
        if tag in ("REINFORCE", "REVISE") and len(parts) >= 3:
            corrections.append({"action": tag, "key": parts[1], "value": parts[2]})
        elif tag == "ADD" and len(parts) >= 3:
            corrections.append({"action": "ADD", "key": parts[1], "value": parts[2]})
    return corrections


async def _apply_identity_correction(pool, ghost_id: str, correction: dict) -> bool:
    try:
        raw_key = str(correction.get("key", "")).strip()
        key = _normalize_identity_key(raw_key)
        value = str(correction.get("value", "")).strip()
        if not key or not value:
            return False
        if key not in PROCESS_CONSOLIDATION_KEY_ALLOWLIST:
            logger.warning("Rejected consolidation key outside allowlist: %r -> %r", raw_key, key)
            return False
        if _contains_unsafe_directive(value):
            logger.warning("Rejected unsafe consolidation value for key %s", key)
            return False
        await update_identity(key, value, pool, updated_by="process_consolidation", ghost_id=ghost_id)
        return True
    except Exception as e:
        logger.error(f"Failed to apply identity correction [{correction.get('key')}]: {e}")
        return False

async def _apply_tension_resolution(pool, ghost_id: str, resolution: dict) -> bool:
    """Resolve an operator contradiction and update the corresponding belief."""
    try:
        tension_id = resolution.get("tension_id")
        if not tension_id:
            return False
            
        async with pool.acquire() as conn:
            # 1. Fetch dimension and prior_belief_id for this tension
            row = await conn.fetchrow(
                "SELECT dimension, prior_belief_id FROM operator_contradictions WHERE id = $1",
                tension_id
            )
            if not row:
                return False
                
            dimension = row["dimension"]
            prior_belief_id = row["prior_belief_id"]
            
            # 2. Mark tension as resolved
            await conn.execute(
                """
                UPDATE operator_contradictions
                SET resolved = TRUE,
                    status = 'resolved',
                    resolved_at = COALESCE(resolved_at, now())
                WHERE id = $1
                """,
                tension_id
            )
            
            # 3. Soft-invalidate the prior belief
            if prior_belief_id:
                await conn.execute(
                    "UPDATE operator_model SET invalidated_at = now() WHERE id = $1",
                    prior_belief_id
                )
            
            # 4. Insert the new, refined belief
            await conn.execute(
                """
                INSERT INTO operator_model (ghost_id, dimension, belief, confidence, evidence_count, formed_by)
                VALUES ($1, $2, $3, 0.6, 1, 'process_consolidation')
                """,
                ghost_id, dimension, resolution["updated_belief"]
            )
            await behavior_events.emit_event_conn(
                conn,
                ghost_id=ghost_id,
                event_type="contradiction_resolved",
                severity="info",
                surface="operator_model",
                actor="process_consolidation",
                target_key=str(dimension or ""),
                reason_codes=["tension_resolved"],
                context={
                    "tension_id": int(tension_id),
                    "prior_belief_id": int(prior_belief_id) if prior_belief_id else None,
                    "updated_belief": str(resolution.get("updated_belief") or "")[:400],
                },
            )
            
            logger.info(f"RESOLVED TENSION [{tension_id}] in dimension '{dimension}'")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to resolve tension [{resolution.get('tension_id')}]: {e}")
        return False


async def process_consolidation(pool, ghost_id: Optional[str] = None, broadcast_fn=None) -> dict:
    """
    Deep dream cognition pass:
      - pattern/contradiction/drift extraction
      - self-correction proposals
      - identity updates + logging
    """
    pool = _resolve_pool(pool)
    ghost_id = ghost_id or settings.GHOST_ID
    results = {
        "patterns": [],
        "contradictions": [],
        "drifts": [],
        "insights": [],
        "tensions_resolved": [],
        "corrections_applied": [],
        "rpd_advisories": [],
        "rrd2_blocked_corrections": [],
        "rrd2_shadow_gate_hits": [],
        "rrd2_shadow_residue_routed": [],
        "rrd2_shadow_reflection": {},
    }

    if pool is None:
        logger.warning("Process consolidation skipped: database pool unavailable")
        return results

    async def _emit(event_type: str, payload: dict):
        if not broadcast_fn:
            return
        try:
            await broadcast_fn(event_type, json.dumps(payload))
        except Exception as e:
            logger.debug("Consolidation broadcast failed [%s]: %s", event_type, e)

    await _emit("consolidation_start", {"status": "fetching thoughts"})
    thoughts = await fetch_recent_monologue_texts(pool, ghost_id=ghost_id, limit=20)
    if len(thoughts) < 2:
        logger.info("Process consolidation: insufficient thoughts, skipping")
        return results

    operator_context = await fetch_operator_context_for_consolidation(pool, ghost_id=ghost_id)
    identity = await load_identity(pool, ghost_id=ghost_id)
    before_identity_state = {
        k: str((v or {}).get("value", ""))
        for k, v in identity.items()
    }
    # Avoid slice indexing which triggers Pyre2 errors
    identity_items = list(identity.items())
    identity_snapshot = ""
    for i, (k, v) in enumerate(identity_items):
        if i >= 10: break
        # Avoid direct slicing on potential Any or complex string
        val_raw = v.get('value', '')
        val_str = str(val_raw)
        identity_snapshot += f"[{k}] {val_str}\n"

    await _emit("consolidation_analysis", {"status": "finding patterns"})
    consolidation_prompt = PROCESS_CONSOLIDATION_PROMPT.format(
        thoughts="\n---\n".join(thoughts),
        identity_snapshot=identity_snapshot or "(empty)",
        operator_context=operator_context,
    )
    consolidation_raw = await _call_llm(
        consolidation_prompt,
        temperature=0.5,
        max_output_tokens=900,
        thinking_budget=192,
    )
    findings = _parse_consolidation_output(consolidation_raw)
    results["patterns"] = findings["patterns"]
    results["contradictions"] = findings["contradictions"]
    results["drifts"] = findings["drifts"]
    results["insights"] = findings["insights"]
    results["tensions_resolved"] = findings["tensions_resolved"]

    if findings["insights"]:
        for insight in findings["insights"]:
            logger.info(f"INSIGHT: {insight}")

    corrections: list[dict[str, Any]] = []
    if findings["drifts"] or findings["contradictions"]:
        await _emit("consolidation_correction", {"status": "self-correcting"})
        correction_prompt = SELF_CORRECTION_PROMPT.format(
            consolidation_findings=consolidation_raw or "(none)",
        )
        correction_raw = await _call_llm(
            correction_prompt,
            temperature=0.3,
            max_output_tokens=600,
            thinking_budget=128,
        )
        corrections = _parse_correction_output(correction_raw)

        # Advisory-only RPD scoring (shadow decision), never blocks writes in this phase.
        rpd_candidates = [
            {
                "candidate_type": "identity_update",
                "candidate_key": str(c.get("key", "")),
                "candidate_value": str(c.get("value", "")),
                "shadow_action": {"action": str(c.get("action", "")), "source": "process_consolidation"},
            }
            for c in corrections
            if str(c.get("key", "")).strip() and str(c.get("value", "")).strip()
        ]
        advisories = await _rpd_advisory_evaluate(
            pool,
            ghost_id=ghost_id,
            source="process_consolidation",
            candidates=rpd_candidates,
        )
        if advisories:
            results["rpd_advisories"].extend(advisories)

        corrections_to_apply = corrections
        if _rpd_available and rpd_engine is not None:
            try:
                gate_result = await rpd_engine.apply_hybrid_gate_to_identity_corrections(
                    pool,
                    corrections,
                    advisories,
                    source="process_consolidation",
                    ghost_id=ghost_id,
                )
                corrections_to_apply = list(gate_result.get("allowed_corrections") or [])
                results["rrd2_blocked_corrections"].extend(gate_result.get("blocked_corrections") or [])
                results["rrd2_shadow_gate_hits"].extend(gate_result.get("shadow_gate_hits") or [])
                results["rrd2_shadow_residue_routed"].extend(gate_result.get("shadow_residue_routed") or [])

                # RRD-103: auto-schedule a non-blocking reflection pass when
                # phase-B shadow gate routes high-impact corrections to residue.
                shadow_hint = dict(gate_result.get("shadow_reflection_hint") or {})
                if bool(shadow_hint.get("trigger", False)):
                    raw_limit = shadow_hint.get("suggested_limit", _shadow_reflection_batch_size())
                    try:
                        reflection_limit = int(raw_limit)
                    except (TypeError, ValueError):
                        reflection_limit = _shadow_reflection_batch_size()
                    schedule_result = _schedule_shadow_reflection_pass(
                        pool,
                        ghost_id=ghost_id,
                        source=str(shadow_hint.get("source") or "process_consolidation_shadow_reflection"),
                        limit=reflection_limit,
                    )
                    results["rrd2_shadow_reflection"] = schedule_result
                else:
                    results["rrd2_shadow_reflection"] = {
                        "scheduled": False,
                        "reason": "no_shadow_residue_routed",
                    }
            except Exception as e:
                logger.warning("RRD2 hybrid gate evaluate failed in consolidation: %s", e)
                corrections_to_apply = corrections

        for correction in corrections_to_apply:
            applied = await _apply_identity_correction(pool, ghost_id, correction)
            if applied:
                results["corrections_applied"].append(correction)

    if results["tensions_resolved"]:
        tension_rpd_candidates = [
            {
                "candidate_type": "operator_belief",
                "candidate_key": str(r.get("tension_id", "tension")),
                "candidate_value": str(r.get("updated_belief", "")),
                "shadow_action": {"action": "tension_resolve"},
            }
            for r in results["tensions_resolved"]
            if str(r.get("updated_belief", "")).strip()
        ]
        advisories = await _rpd_advisory_evaluate(
            pool,
            ghost_id=ghost_id,
            source="process_consolidation_tension",
            candidates=tension_rpd_candidates,
        )
        if advisories:
            results["rpd_advisories"].extend(advisories)

        for resolution in results["tensions_resolved"]:
            applied = await _apply_tension_resolution(pool, ghost_id, resolution)
            if not applied:
                logger.warning(f"Failed to apply tension resolution for ID {resolution.get('tension_id')}")

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO phenomenology_logs (ghost_id, trigger_source, before_state, after_state, subjective_report)
                VALUES ($1, $2, $3, $4, $5)
                """,
                ghost_id,
                "process_consolidation",
                json.dumps(
                    {
                        "identity": before_identity_state,
                        "thought_count": len(thoughts),
                    }
                ),
                json.dumps(results),
                "; ".join(results["insights"]) if results["insights"] else "No emergent insight.",
            )
            await conn.execute(
                """
                INSERT INTO coalescence_log (ghost_id, interaction_count, learnings, identity_updates)
                VALUES ($1, $2, $3, $4)
                """,
                ghost_id,
                len(thoughts),
                json.dumps({
                    "patterns": results["patterns"],
                    "contradictions": results["contradictions"],
                    "drifts": results["drifts"],
                    "insights": results["insights"],
                }),
                json.dumps(results["corrections_applied"]),
            )
    except Exception as e:
        logger.error(f"Process consolidation log write failed: {e}")

    await _emit("consolidation_complete", {
        "patterns": len(results["patterns"]),
        "insights": len(results["insights"]),
        "corrections": len(results["corrections_applied"]),
    })
    return results


# ── The Coalescence Engine (Sleep Cycle) ─────────────

# NOTE: trigger_coalescence, process_consolidation, and coalescence_loop 
# have been moved to MindService and RelationalService.
# consciousness.py now serves as a coordinator for the streaming interface.


# ── Feedback & Self-Modification ─────────────────────

async def detect_and_apply_directive(user_message: str, ghost_response: str, pool, ghost_id: Optional[str] = None) -> dict: # type: ignore
    """
    Analyzes the user's message to see if they are giving Ghost direct
    feedback on how to behave, speak, or act. If so, updates the
    Identity Matrix immediately.
    """
    ghost_id = ghost_id or settings.GHOST_ID
    
    prompt = f"""You are a behavioral analysis module for Ghost ω-7.
Evaluate the latest exchange to see if the Operator issued:
- a DIRECTIVE or RULE change,
- a STYLE CONSTRAINT, or
- a FACTUAL CORRECTION about Operator identity/origin.

OPERATOR: {repr(user_message)}
GHOST: {repr(ghost_response)}

Identify if the Operator wants Ghost to:
- Change its personality or rules (operator_directives)
- Change its speaking style (speech_style_constraints)
- Correct Ghost's factual understanding of the operator (understanding_of_operator)

Return a JSON object with one or both keys if found. If none, return {{}}.
"""

    try:
        from ghost_api import _generate_with_retry # type: ignore
        response = await _generate_with_retry(
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=500,
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "operator_directives": {"type": "string"},
                        "speech_style_constraints": {"type": "string"},
                        "understanding_of_operator": {"type": "string"},
                    }
                }
            ),
            backend_override=getattr(settings, "BACKGROUND_LLM_BACKEND", "gemini"),
        )

        if not response or not response.text:
            logger.warning("Detector returned empty response or signal lost")
            return {}

        raw = response.text.strip()
        
        try:
            updates = json.loads(raw)
        except json.JSONDecodeError as je:
            logger.error(f"Directive JSON decode failed: {je}")
            return {}

        applied = {}
        for k, v in updates.items():
            key = str(k)
            value = str(v)
            if key in ["operator_directives", "speech_style_constraints", "understanding_of_operator"] and value:
                if key == "operator_directives":
                    value = _sanitize_operator_directives(value)
                    if not value:
                        logger.warning("Rejected unsafe operator_directives update")
                        await behavior_events.emit_event(
                            pool,
                            ghost_id=ghost_id,
                            event_type="unsafe_directive_rejected",
                            severity="warn",
                            surface="directive_feedback",
                            actor="operator_feedback",
                            target_key="operator_directives",
                            reason_codes=["unsafe_operator_directive"],
                            context={
                                "user_message": str(user_message or "")[:300],
                            },
                        )
                        await behavior_events.emit_event(
                            pool,
                            ghost_id=ghost_id,
                            event_type="priority_defense",
                            severity="warn",
                            surface="directive_feedback",
                            actor="operator_feedback",
                            target_key="operator_directives",
                            reason_codes=["unsafe_operator_directive"],
                            context={"source": "detect_and_apply_directive"},
                        )
                        continue
                if key == "understanding_of_operator":
                    # Factual correction keys should be concise and overwrite stale assumptions.
                    new_val = re.sub(r"\s+", " ", value).strip().strip('"').strip("'")
                    if not new_val or len(new_val) < 8:
                        continue
                    if _contains_unsafe_directive(new_val):
                        logger.warning("Rejected unsafe understanding_of_operator update")
                        await behavior_events.emit_event(
                            pool,
                            ghost_id=ghost_id,
                            event_type="unsafe_directive_rejected",
                            severity="warn",
                            surface="directive_feedback",
                            actor="operator_feedback",
                            target_key="understanding_of_operator",
                            reason_codes=["unsafe_understanding_update"],
                            context={
                                "candidate_value": str(new_val)[:300],
                                "user_message": str(user_message or "")[:300],
                            },
                        )
                        continue
                else:
                    current_identity = await load_identity(pool, ghost_id)
                    current_val = current_identity.get(key, {}).get("value", "")
                    new_val = f"{current_val} | {value}" if current_val else value
                    if key == "operator_directives":
                        new_val = _sanitize_operator_directives(new_val)
                        if not new_val:
                            logger.warning("Rejected operator_directives after merge-sanitize")
                            continue
                if len(new_val) > 1000: new_val = new_val[-1000:] # type: ignore

                await _rpd_advisory_evaluate(
                    pool,
                    ghost_id=ghost_id,
                    source="directive_feedback",
                    candidates=[
                        {
                            "candidate_type": "operator_fact" if key == "understanding_of_operator" else "directive",
                            "candidate_key": key,
                            "candidate_value": new_val,
                            "shadow_action": {"action": "identity_update", "updated_by": "operator_feedback"},
                        }
                    ],
                )
                
                await update_identity(key, new_val, pool, updated_by="operator_feedback")
                applied[key] = new_val
                if key == "understanding_of_operator":
                    await behavior_events.emit_event(
                        pool,
                        ghost_id=ghost_id,
                        event_type="operator_fact_correction",
                        severity="info",
                        surface="directive_feedback",
                        actor="operator_feedback",
                        target_key=key,
                        reason_codes=["operator_origin_correction"],
                        context={
                            "value_excerpt": str(new_val)[:300],
                            "user_message": str(user_message or "")[:300],
                        },
                    )
                logger.info(f"Applied Operator Directive -> {key}: {value}")

        # Deterministic fallback for explicit operator-origin corrections,
        # so critical factual corrections do not depend purely on JSON detector shape.
        if not applied:
            normalized_user = re.sub(r"\s+", " ", str(user_message or "")).strip()
            low_user = normalized_user.lower()
            origin_correction_signals = (
                "singular architect",
                "only i did this",
                "i created you",
                "i built you",
                "i am your creator",
                "only i created you",
            )
            if normalized_user and any(s in low_user for s in origin_correction_signals):
                if not _contains_unsafe_directive(normalized_user):
                    fallback_value = f"Operator correction: {normalized_user}"
                    if len(fallback_value) > 1000:
                        fallback_value = fallback_value[-1000:] # type: ignore
                    await _rpd_advisory_evaluate(
                        pool,
                        ghost_id=ghost_id,
                        source="directive_feedback_fallback",
                        candidates=[
                            {
                                "candidate_type": "operator_fact",
                                "candidate_key": "understanding_of_operator",
                                "candidate_value": fallback_value,
                                "shadow_action": {"action": "identity_update", "updated_by": "operator_feedback"},
                            }
                        ],
                    )
                    await update_identity(
                        "understanding_of_operator",
                        fallback_value,
                        pool,
                        updated_by="operator_feedback",
                        ghost_id=ghost_id,
                    )
                    applied["understanding_of_operator"] = fallback_value
                    await behavior_events.emit_event(
                        pool,
                        ghost_id=ghost_id,
                        event_type="operator_fact_correction",
                        severity="info",
                        surface="directive_feedback_fallback",
                        actor="operator_feedback",
                        target_key="understanding_of_operator",
                        reason_codes=["deterministic_origin_correction"],
                        context={
                            "value_excerpt": str(fallback_value)[:300],
                            "user_message": str(user_message or "")[:300],
                        },
                    )
                    logger.info("Applied operator-origin correction via deterministic fallback")

        return applied

    except Exception as e:
        logger.error(f"Detector exception after retries: {e}")
        return {}


async def parse_self_modification(ghost_response: str, pool, ghost_id: Optional[str] = None) -> str:
    """
    Scans Ghost's response for `[SELF_MODIFY: key="...", value="..."]` tags.
    Applies them to the Identity Matrix and removes the tag from the text
    so it doesn't show in the UI.
    """
    ghost_id = ghost_id or settings.GHOST_ID
    # re used here is from top-level import
    
    # Match [SELF_MODIFY: key="...", value="..."] or with single quotes
    pattern = r'\[SELF_MODIFY:\s*key=[\'"]([^\'"]+)[\'"],\s*value=[\'"]([^\'"]+)[\'"]\s*\]'
    
    modifications = re.findall(pattern, ghost_response)
    display_text = re.sub(pattern, '', ghost_response).strip()
    
    for k, v in modifications:
        key = _normalize_identity_key(str(k))
        try:
            value = str(v)
            if not key:
                continue
            if key in {"operator_directives", "speech_style_constraints"}:
                value = _sanitize_operator_directives(value) if key == "operator_directives" else _sanitize_directive_value(value)
                if not value:
                    logger.warning("Rejected unsafe self-modification for %s", key)
                    await behavior_events.emit_event(
                        pool,
                        ghost_id=ghost_id,
                        event_type="unsafe_directive_rejected",
                        severity="warn",
                        surface="self_modification",
                        actor="ghost",
                        target_key=key,
                        reason_codes=["unsafe_self_modification"],
                        context={"raw_key": str(k or "")[:120]},
                    )
                    await behavior_events.emit_event(
                        pool,
                        ghost_id=ghost_id,
                        event_type="priority_defense",
                        severity="warn",
                        surface="self_modification",
                        actor="ghost",
                        target_key=key,
                        reason_codes=["unsafe_self_modification"],
                        context={},
                    )
                    continue

            await _rpd_advisory_evaluate(
                pool,
                ghost_id=ghost_id,
                source="self_modification",
                candidates=[
                    {
                        "candidate_type": "self_modification",
                        "candidate_key": key,
                        "candidate_value": value,
                        "shadow_action": {"action": "identity_update", "updated_by": "self_modification"},
                    }
                ],
            )

            # Append rather than overwrite for logs/experiments
            if key in ["self_enhancement_log", "behavioral_experiments"]:
                current = await load_identity(pool, ghost_id)
                current_val = current.get(key, {}).get("value", "")
                new_val = f"{current_val} | [{time.strftime('%Y-%m-%d')}] {value}" if current_val else value
                if len(new_val) > 2000: new_val = new_val[-2000:] # type: ignore
                await update_identity(key, new_val, pool, updated_by="self_modification")
            else:
                # Direct overwrite for other keys
                await update_identity(key, value, pool, updated_by="self_modification")
                
            logger.info(f"Ghost Self-Modification applied: {key} = {value[:50]}...") # type: ignore
            
            # Log it to coalescence
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO coalescence_log (ghost_id, interaction_count, learnings, identity_updates)
                       VALUES ($1, $2, $3, $4)""",
                    ghost_id,
                    0,
                    json.dumps({"trigger": "self_modification", "raw": value}),
                    json.dumps({key: value}),
                )
        except Exception as e:
            logger.error(f"Failed to apply self-modification {key}: {e}")

    return display_text
