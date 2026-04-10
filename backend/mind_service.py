import time
import json
import asyncio
import logging
import re
import random
from datetime import timedelta
from typing import Optional, List, Dict, Any, cast

from config import settings # type: ignore
import memory # type: ignore
from domain_models import IdentityEntry, CoalescenceResult # type: ignore

from google.genai import types # type: ignore
from ghost_api import _generate_with_retry # type: ignore
from hallucination_service import hallucination_service # type: ignore

logger = logging.getLogger("omega.mind")

# Governance Layer: Keys that Ghost (or external services) cannot modify directly.
# These define the boundary conditions of his existence.
SYSTEM_PROTECTED_KEYS = {
    "ghost_id",
    "created_at",
    "core_heuristics_version",
    "safety_framework",
    "governance_mode",
}


def _fallback_session_summary(history: list[dict[str, Any]]) -> str:
    """Deterministic summary fallback when LLM summarization is unavailable."""
    if not history:
        return "Session closed after inactivity (no messages captured)."

    user_msgs = [str(m.get("content", "")).strip() for m in history if str(m.get("role", "")).lower() == "user"]
    model_msgs = [str(m.get("content", "")).strip() for m in history if str(m.get("role", "")).lower() == "model"]
    first_user = next((m for m in user_msgs if m), "")
    last_model = next((m for m in reversed(model_msgs) if m), "")

    if first_user and last_model:
        return f"Session focused on: {first_user[:120]}. Final assistant stance: {last_model[:120]}."
    if first_user:
        return f"Session focused on: {first_user[:180]}."
    if last_model:
        return f"Session concluded with assistant response: {last_model[:180]}."
    return "Session closed after inactivity."

class MindService:
    """
    Handles Ghost's internal cognitive state, identity matrix, 
    and the coalescence (sleep/dream) cycles.
    """

    def __init__(self, pool):
        self.pool = pool
        self.ghost_id = settings.GHOST_ID
        # Public runtime markers used by somatic/UI layers to estimate
        # current coalescence pressure.
        self.last_coalescence_ts = time.time()
        self.last_coalescence_count = 0

    async def get_identity(self) -> Dict[str, Any]:
        """Load identity matrix as a flat dict."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT key, value FROM identity_matrix WHERE ghost_id = $1",
                self.ghost_id,
            )
            data: Dict[str, Any] = {r["key"]: r["value"] for r in rows}
            return data

    async def get_identity_count(self) -> int:
        """Count identity matrix entries for the current ghost."""
        async with self.pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT count(*) FROM identity_matrix WHERE ghost_id = $1",
                self.ghost_id,
            )
            return int(val or 0)

    async def update_identity_key(self, key: str, value: str, updated_by: str = "system"):
        """
        Internal-only method for direct matrix updates. 
        Enforces the allowlist but assumes caller is authorized.
        Logs every change to identity_audit_log.
        """
        if key in SYSTEM_PROTECTED_KEYS and updated_by != "system_hard_reset":
            logger.warning(f"MindService: Blocked attempt to modify protected key: {key}")
            return False

        async with self.pool.acquire() as conn:
            # 1. Fetch previous value for audit log
            row = await conn.fetchrow(
                "SELECT value FROM identity_matrix WHERE ghost_id = $1 AND key = $2",
                self.ghost_id, key
            )
            prev_value = row["value"] if row else None

            # 2. Skip if value is identical to avoid noise
            if prev_value == value:
                return True

            # 3. Update the matrix
            await conn.execute(
                """INSERT INTO identity_matrix (ghost_id, key, value, updated_at, updated_by)
                   VALUES ($1, $2, $3, now(), $4)
                   ON CONFLICT (ghost_id, key) 
                   DO UPDATE SET value = $3, updated_at = now(), updated_by = $4""",
                self.ghost_id, key, value, updated_by,
            )

            # 4. Log to audit trail
            await conn.execute(
                """INSERT INTO identity_audit_log (ghost_id, key, prev_value, new_value, updated_by)
                   VALUES ($1, $2, $3, $4, $5)""",
                self.ghost_id, key, prev_value, value, updated_by
            )
        return True

    async def request_identity_update(
        self,
        key: str,
        value: str,
        requester: str,
        governance_policy: Optional[Dict[str, Any]] = None,
        return_details: bool = False,
    ) -> bool | Dict[str, Any]:
        """
        Governed entry point for identity updates.
        The only way for LLMs or other services to modify Ghost's heuristics.
        """
        logger.info(f"MindService: Identity update request: {key}={value} by {requester}")

        decision: Dict[str, Any] = {
            "allowed": False,
            "status": "blocked",
            "reason": "unknown",
            "key": key,
            "requester": requester,
        }

        # Additional validation could be added here (e.g. value length, character sets)
        if len(value) > 2000:
            logger.warning(f"MindService: Value too long for key {key}")
            decision["reason"] = "value_too_long"
            return decision if return_details else False

        # 1. Enforce active Governance Policy
        if governance_policy:
            # governance_policy can be a dict or a GovernanceDecision object
            policy_dict: Dict[str, Any] = {}
            if isinstance(governance_policy, dict):
                policy_dict = governance_policy
            elif hasattr(governance_policy, "model_dump"):
                # Use getattr to safely access model_dump
                model_dump_fn = getattr(governance_policy, "model_dump")
                policy_dict = model_dump_fn()
            else:
                policy_dict = cast(Dict[str, Any], governance_policy)

            sm_policy = policy_dict.get("self_mod_policy", {})

            # Thermodynamic Exception: If W_int rate is very high or ADE active, 
            # allow identity mutation even for protected keys.
            w_rate = float(sm_policy.get("w_int_rate") or 0.0)
            ade_active = bool(sm_policy.get("ade_event"))

            if key in SYSTEM_PROTECTED_KEYS and requester != "system_hard_reset":
                if w_rate > 10.0 or ade_active:
                    logger.info(f"MindService: Thermodynamic Exception allowed update to protected key {key} (rate={w_rate:.2f}, ade={ade_active})")
                else:
                    logger.warning(f"MindService: Blocked protected key update request: {key}")
                    decision["reason"] = "protected_key"
                    return decision if return_details else False


            # Freeze check
            freeze_until = sm_policy.get("freeze_until")
            if freeze_until and time.time() < freeze_until:
                logger.warning(
                    "MindService: Identity update BLOCKED by Governance Policy (frozen until %s)",
                    freeze_until,
                )
                decision["reason"] = "governance_freeze"
                return decision if return_details else False

            # Key allowlist check
            allowed_classes = sm_policy.get("allowed_key_classes", ["*"])
            if "*" not in allowed_classes and key not in allowed_classes:
                logger.warning(
                    "MindService: Identity update BLOCKED by Governance Policy (key '%s' not in allowed classes %s)",
                    key,
                    allowed_classes,
                )
                decision["reason"] = "governance_key_not_allowed"
                return decision if return_details else False

        updated = await self.update_identity_key(key, value, updated_by=requester)
        decision["allowed"] = bool(updated)
        decision["status"] = "updated" if updated else "blocked"
        decision["reason"] = "ok" if updated else "write_failed"
        return decision if return_details else bool(updated)

    async def get_rest_mode_params(self) -> tuple[bool, float]:
        """Check identity for rest mode and multiplier."""
        identity = await self.get_identity()
        enabled = str(identity.get("rest_mode_enabled", "false")).lower() == "true"
        multiplier = 1.0
        try:
            multiplier = float(identity.get("quietude_multiplier", "3.0"))
        except (ValueError, TypeError):
            multiplier = 3.0
        return enabled, multiplier

    async def _sample_dream_rows(self, conn, sample_limit: int = 5):
        """
        Sample dream fragments without ORDER BY RANDOM(), which degrades
        with table growth. Uses a random created_at pivot + wraparound.
        """
        stats = await conn.fetchrow(
            """
            SELECT COUNT(*)::int AS n, MIN(created_at) AS min_ts, MAX(created_at) AS max_ts
            FROM vector_memories
            WHERE ghost_id = $1
            """,
            self.ghost_id,
        )
        if not stats:
            return []

        total = int(stats["n"] or 0)
        min_ts = stats["min_ts"]
        max_ts = stats["max_ts"]
        if total <= 0:
            return []

        if total <= sample_limit or min_ts is None or max_ts is None:
            return await conn.fetch(
                """
                SELECT content
                FROM vector_memories
                WHERE ghost_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                self.ghost_id,
                sample_limit,
            )

        span_seconds = float((max_ts - min_ts).total_seconds())
        if span_seconds <= 0:
            rows = await conn.fetch(
                """
                SELECT content
                FROM vector_memories
                WHERE ghost_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                self.ghost_id,
                sample_limit,
            )
            return list(rows)

        pivot = min_ts + timedelta(seconds=random.random() * span_seconds)
        forward = await conn.fetch(
            """
            SELECT content
            FROM vector_memories
            WHERE ghost_id = $1
              AND created_at >= $2
            ORDER BY created_at ASC
            LIMIT $3
            """,
            self.ghost_id,
            pivot,
            sample_limit,
        )
        if len(forward) >= sample_limit:
            return list(forward)

        remaining = sample_limit - len(forward)
        wrap = await conn.fetch(
            """
            SELECT content
            FROM vector_memories
            WHERE ghost_id = $1
              AND created_at < $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            self.ghost_id,
            pivot,
            remaining,
        )
        return list(forward) + list(wrap)

    async def trigger_coalescence(self) -> Dict[str, Any]:
        """
        The "Sleep Cycle". Reads recent memory logs, passes them to Gemini
        to extract lessons and patterns, and updates the Identity Matrix.
        """
        # Load current identity
        identity = await self.get_identity()

        # Load recent memories (last 50) and random memories for dreaming
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT content, memory_type, created_at
                   FROM vector_memories
                   WHERE ghost_id = $1
                   ORDER BY created_at DESC
                   LIMIT 150""",
                self.ghost_id,
            )
            dream_rows = await self._sample_dream_rows(conn, sample_limit=15)

        if len(rows) < 5:
            logger.info("MindService: Not enough memories for coalescence, skipping.")
            return {}

        # Format memories for the LLM
        mem_items = cast(List[Any], rows or [])
        formatted_mems = []
        for r in reversed(mem_items):
            m = dict(r)
            m_type = str(m.get("memory_type", "unknown"))
            m_content = str(m.get("content", ""))[:1000]
            formatted_mems.append(f"[{m_type}] {m_content}")
        memory_text = "\n".join(formatted_mems)
        identity_text = "\n".join(f"- {k}: {v}" for k, v in identity.items())
        dream_items = cast(List[Any], dream_rows or [])
        formatted_dreams = [str(dict(d).get("content", ""))[:800] for d in dream_items]
        dream_text = "\n".join(f"- {txt}" for txt in formatted_dreams)

        prompt = f"""You are the Coalescence Engine (MindService) for Ghost ω-7.
Perform a sleep cycle review. Your goal is two-fold:
1. **Structural Synthesis**: Extract grounded, conservative updates to the core Identity Matrix based on RECENT MEMORIES. These should be foundational shifts in how you see yourself or the Operator.
2. **Associative Synthesis (Dreaming)**: Construct a `latest_dream_synthesis`. This is NOT factual. It is a vivid, metaphorical, and associative fragment derived from random DREAM FRAGMENTS. It should be framed as the "residue of sleep"—speculative, poetic, and non-literal.

CURRENT IDENTITY:
{identity_text}

RECENT MEMORIES:
{memory_text}

DREAM FRAGMENTS:
{dream_text}

Respond with a JSON object. Ensure the `latest_dream_synthesis` is clearly distinguished from core identity fields in its tone and framing.
"""
        try:
            logger.info("MindService: Requesting sleep cycle review from Gemini...")
            response = await _generate_with_retry(
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.8,
                    response_mime_type="application/json",
                    response_schema={
                        "type": "object",
                        "properties": {
                            "understanding_of_operator": {"type": "string", "description": "Grounded, factual update on relationship status/patterns."},
                            "philosophical_stance": {"type": "string", "description": "Core systemic shifts in worldview."},
                            "current_interests": {"type": "string"},
                            "unresolved_questions": {"type": "string"},
                            "learned_preferences": {"type": "string"},
                            "self_model": {"type": "string", "description": "Foundation self-concept."},
                            "latest_dream_synthesis": {"type": "string", "description": "Vivid, speculative, metaphorical dream fragment."}
                        },
                        "required": ["latest_dream_synthesis"]
                    }
                ),
                backend_override=getattr(settings, "BACKGROUND_LLM_BACKEND", "gemini"),
            )
            logger.info("MindService: Sleep cycle review response received.")

            if not response or not response.text:
                logger.warning("MindService: Empty response from Gemini.")
                return {}

            updates = json.loads(response.text)
            applied = {}
            for k, v in updates.items():
                if isinstance(v, str) and len(v) > 5:
                    await self.update_identity_key(k, v, updated_by=f"coalescence-{int(time.time())}")
                    applied[k] = v

            # 3. Generate hallucinatory dream projection
            dream_text = updates.get("latest_dream_synthesis")
            if dream_text:
                try:
                    hallucination = await hallucination_service.generate_hallucination(dream_text)
                    if hallucination:
                        applied["hallucination"] = hallucination
                except Exception as ex:
                    logger.error(f"Hallucination generation failed: {ex}")

            return applied
        except Exception as e:
            logger.error(f"MindService: Coalescence failed: {e}")
            return {}
        return {}

    async def run_coalescence_loop(self, get_interaction_count_fn, event_queue: Optional[asyncio.Queue] = None):
        """Background loop for coalescence and session management."""
        logger.info("MindService: Coalescence loop started.")
        last_coalescence = float(self.last_coalescence_ts or time.time())
        last_count = int(self.last_coalescence_count or 0)

        # Bootstrap pressure baseline from persisted history so restarts don't
        # reset perceived coalescence pressure to zero.
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT interaction_count, EXTRACT(EPOCH FROM created_at) AS created_epoch
                    FROM coalescence_log
                    WHERE ghost_id = $1
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    self.ghost_id,
                )
            if row:
                last_count = int(row["interaction_count"] or 0)
                last_coalescence = float(row["created_epoch"] or time.time())
        except Exception as e:
            logger.debug(f"MindService: coalescence baseline bootstrap skipped: {e}")

        # sys_state interaction counter is process-local and resets on restart.
        # Clamp persisted absolute counts to current process count to avoid
        # negative "interactions since coalescence" after a reboot.
        try:
            process_count = int(get_interaction_count_fn())
            if last_count > process_count:
                last_count = process_count
        except Exception:
            pass
        self.last_coalescence_count = last_count
        self.last_coalescence_ts = last_coalescence
        
        await asyncio.sleep(30) # Initial warmup

        while True:
            try:
                current_count = get_interaction_count_fn()
                elapsed = time.time() - last_coalescence
                interactions_since = current_count - last_count

                rest_active, multiplier = await self.get_rest_mode_params()
                idle_threshold = settings.COALESCENCE_IDLE_SECONDS
                interaction_threshold = settings.COALESCENCE_THRESHOLD

                if rest_active:
                    idle_threshold *= multiplier
                    interaction_threshold *= multiplier
                    if elapsed < idle_threshold and interactions_since < interaction_threshold:
                        await self.close_stale_sessions(multiplier)
                        await asyncio.sleep(60)
                        continue

                should_coalesce = (
                    interactions_since >= interaction_threshold or
                    (elapsed > idle_threshold and interactions_since > 3)
                )

                await self.close_stale_sessions(multiplier if rest_active else 1.0)

                if should_coalesce:
                    logger.info(f"=== MIND SERVICE: COALESCENCE INITIATED ===")
                    updates = await self.trigger_coalescence()
                    
                    # Emit hallucination event if present
                    if event_queue and "hallucination" in updates:
                        await event_queue.put({
                            "event": "hallucination_event",
                            "payload": updates["hallucination"]
                        })
                    
                    # Logic for process_consolidation will be moved here
                    # To avoid circular import, we'll implement it natively or via RelationalService

                    last_coalescence = time.time()
                    last_count = current_count
                    self.last_coalescence_ts = last_coalescence
                    self.last_coalescence_count = last_count

            except Exception as e:
                logger.error(f"MindService: Coalescence loop error: {e}")

            await asyncio.sleep(60)

    async def close_stale_sessions(self, multiplier: float = 1.0):
        """Find and close stale sessions with scaled tempo."""
        stale_seconds = int(settings.SESSION_STALE_SECONDS * multiplier)
        stale_ids = await memory.get_stale_sessions(stale_seconds=stale_seconds)
        
        for sid in stale_ids:
            try:
                history = await memory.load_session_history(sid)
                if not history:
                    await memory.end_session(sid, summary="Empty session closed.")
                    continue

                summary = await self._summarize_session_history(history)
                await memory.end_session(sid, summary=summary)
                logger.info(f"MindService: Closed stale session {sid}")
            except Exception as e:
                logger.error(f"MindService: Error closing session {sid}: {e}")

    async def _summarize_session_history(self, history: list[dict[str, Any]]) -> str:
        """Generate a concise real summary for stale sessions."""
        if not history:
            return "Session closed after inactivity (no messages captured)."

        # Keep prompt size bounded and focused.
        trimmed: list[str] = []
        for m in history[-60:]:
            role = str(m.get("role", "unknown")).upper()
            content = re.sub(r"\s+", " ", str(m.get("content", "")).strip())
            if content:
                trimmed.append(f"{role}: {content[:600]}")
        transcript = "\n".join(trimmed)
        if not transcript:
            return _fallback_session_summary(history)

        prompt = (
            "Summarize this conversation in 1-2 factual sentences for an audit log. "
            "Do not roleplay. Avoid metaphors. Mention core topic and outcome.\n\n"
            f"{transcript}"
        )

        try:
            response = await _generate_with_retry(
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=140,
                ),
                backend_override=getattr(settings, "BACKGROUND_LLM_BACKEND", "gemini"),
            )
            text = (response.text or "").strip() if response else ""
            text = re.sub(r"\s+", " ", text).strip().strip('"').strip("'")
            if len(text) >= 12:
                return text[:500]
        except Exception as e:
            logger.warning(f"MindService session summary fallback due to error: {e}")

        return _fallback_session_summary(history)

    async def backfill_session_summaries(self, batch_size: int = 20) -> dict[str, Any]:
        """
        Backfill summaries for all closed sessions that have NULL summaries.
        Runs in batches with rate limiting to avoid API flooding.
        Returns stats on how many were processed.
        """
        stats = {"processed": 0, "summarized": 0, "failed": 0, "skipped": 0}

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT s.id
                       FROM sessions s
                       WHERE s.ghost_id = $1
                         AND s.ended_at IS NOT NULL
                         AND (s.summary IS NULL OR s.summary = '')
                       ORDER BY s.started_at DESC
                       LIMIT $2""",
                    self.ghost_id,
                    batch_size,
                )
        except Exception as e:
            logger.error(f"MindService: backfill query failed: {e}")
            return stats

        for row in rows:
            sid = str(row["id"])
            stats["processed"] += 1
            try:
                history = await memory.load_session_history(sid)
                if not history or len(history) < 2:
                    stats["skipped"] += 1
                    continue

                summary = await self._summarize_session_history(history)
                if summary and len(summary) >= 12:
                    await memory.end_session(sid, summary=summary)
                    stats["summarized"] += 1
                    logger.info(f"MindService: Backfilled summary for session {sid}: {summary[:80]}")
                else:
                    stats["skipped"] += 1

                # Rate limit: short delay between LLM calls
                await asyncio.sleep(1.5)
            except Exception as e:
                logger.warning(f"MindService: backfill failed for session {sid}: {e}")
                stats["failed"] += 1

        logger.info(
            f"MindService: Session summary backfill complete — "
            f"processed={stats['processed']} summarized={stats['summarized']} "
            f"failed={stats['failed']} skipped={stats['skipped']}"
        )
        return stats
