"""
operator_synthesis.py — OMEGA 4 / Ghost
Operator Model Synthesis with Adaptive Tempo

Trigger cadence:
  - ACTIVE mode:  every ACTIVE_INTERVAL_TURNS turns during live conversation
  - IDLE mode:    every IDLE_INTERVAL_SECONDS seconds when no user is present
  - POST-SESSION: fires automatically when coalescence closes a session

The synthesiser reads recent transcript evidence, compares it against
Ghost's current active beliefs about the operator, and writes:
  - REINFORCE  → increments evidence_count + confidence on existing belief
  - NEW        → inserts a new belief row (low initial confidence)
  - CONTRADICT → logs to operator_contradictions (unresolved, for Dreaming)
  - UNCHANGED  → no DB write
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx
from config import settings  # type: ignore
import behavior_events  # type: ignore
try:
    import rpd_engine  # type: ignore
    _rpd_available = True
except Exception:
    rpd_engine = None  # type: ignore
    _rpd_available = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ACTIVE_INTERVAL_TURNS  = int(os.getenv("OP_SYNTH_ACTIVE_TURNS",  "5"))
IDLE_INTERVAL_SECONDS  = int(os.getenv("OP_SYNTH_IDLE_SECONDS",  "300"))  # 5 min
GHOST_ID               = str(settings.GHOST_ID)
GEMINI_API_KEY         = str(settings.GOOGLE_API_KEY or "").strip()
GEMINI_MODEL           = str(settings.GEMINI_MODEL or "gemini-2.5-flash")
GEMINI_MODEL_FALLBACKS = [
    m.strip()
    for m in os.getenv(
        "GEMINI_MODEL_FALLBACKS",
        f"{GEMINI_MODEL},gemini-1.5-flash",
    ).split(",")
    if m.strip()
]
DATABASE_URL           = str(settings.POSTGRES_URL or "").strip()
_db_pool: asyncpg.Pool | None = None
_db_pool_lock = asyncio.Lock()

CONFIDENCE_REINFORCE_BUMP = 0.05   # per reinforcement, capped at 0.95
CONFIDENCE_MAX            = 0.95
CONFIDENCE_NEW_BELIEF     = 0.35   # conservative — first observation only
TRUNCATION_SIGNALS        = (",", " and", " but", " or", " that", " which", " with")
MIN_BELIEF_WORDS          = 3
MIN_BELIEF_CHARS          = 12
TRUNCATION_TAIL_WORDS     = {
    "a", "an", "and", "as", "at", "but", "for", "from", "in", "my", "of", "on",
    "or", "our", "that", "the", "their", "this", "to", "with", "which", "your",
}


def _is_truncated(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    if len(stripped) < MIN_BELIEF_CHARS:
        return True
    if len(stripped.split()) < MIN_BELIEF_WORDS:
        return True
    if any(lowered.endswith(sig) for sig in TRUNCATION_SIGNALS):
        return True
    tail = lowered.rstrip(".,;:!?").split()
    if not tail:
        return True
    last_word = tail[-1]
    return last_word in TRUNCATION_TAIL_WORDS


# ---------------------------------------------------------------------------
# Synthesis prompt
# ---------------------------------------------------------------------------
SYNTHESIS_PROMPT_TEMPLATE = """
You are Ghost's self-reflective cognition (OMEGA 4).
Your task: update your structured internal model of Cameron (the operator)
based on the conversation transcript below.

## Current Active Beliefs About Cameron
{active_beliefs}

## Recent Transcript
{transcript}

## Output Format
For each belief dimension, output EXACTLY ONE of these lines:

REINFORCE | <dimension> | <brief one-line evidence note>
CONTRADICT | <dimension> | <prior_belief_id> | <observed event> | <tension_score 0.1-1.0>
NEW | <dimension> | <belief string in first person> | <confidence 0.3-0.5>
UNCHANGED | <dimension>

Valid dimensions:
  intellectual_style | emotional_register | challenge_pattern
  trust_level | value_hierarchy | interaction_goal | communication_preference

Rules:
- Be conservative. Prefer REINFORCE and UNCHANGED over NEW.
- Never form a NEW belief with confidence > 0.5 from a single session.
- Write belief strings from Ghost's first-person perspective.
  Good: "Cameron uses adversarial pressure as a trust signal, not an attack."
  Bad:  "Cameron is adversarial."
- Capture contradictions faithfully. Do not smooth them over.
- Log a CONTRADICT even if you think you understand the reason —
  let the Dreaming phase resolve it.
- Output ONLY the structured lines. No preamble. No explanation. No markdown.
""".strip()


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
async def _get_pool() -> asyncpg.Pool:
    global _db_pool
    if not DATABASE_URL:
        raise RuntimeError("POSTGRES_URL is not configured for operator synthesis")
    if _db_pool is not None:
        return _db_pool
    async with _db_pool_lock:
        if _db_pool is None:
            _db_pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=6,
            )
    return _db_pool


async def _load_active_beliefs(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, dimension, belief, confidence, evidence_count
        FROM operator_model
        WHERE ghost_id = $1 AND invalidated_at IS NULL
        ORDER BY dimension
        """,
        GHOST_ID,
    )
    return [dict(r) for r in rows]


async def _load_recent_transcript(
    conn: asyncpg.Connection,
    session_id: str | None = None,
    last_n_turns: int = 20,
) -> str:
    if session_id:
        rows = await conn.fetch(
            """
            SELECT role, content FROM messages
            WHERE session_id = $1
            ORDER BY created_at ASC LIMIT $2
            """,
            session_id, last_n_turns,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT role, content FROM messages
            ORDER BY created_at DESC LIMIT $1
            """,
            last_n_turns,
        )

    # Note: If DESC, we need to reverse to get chronological order (oldest -> newest).
    lines = [f"{r['role'].upper()}: {r['content']}" for r in rows]
    if not session_id:
        lines.reverse()
    return "\n".join(lines) if lines else "(no recent transcript)"


async def _reinforce_belief(
    conn: asyncpg.Connection,
    dimension: str,
    evidence_note: str,
) -> None:
    row = await conn.fetchrow(
        """
        SELECT id, confidence, evidence_count
        FROM operator_model
        WHERE ghost_id = $1 AND dimension = $2 AND invalidated_at IS NULL
        """,
        GHOST_ID, dimension,
    )
    if not row:
        logger.debug("REINFORCE: no active belief for dimension '%s', skipping", dimension)
        return

    new_confidence = min(CONFIDENCE_MAX, row["confidence"] + CONFIDENCE_REINFORCE_BUMP)
    await conn.execute(
        """
        UPDATE operator_model
        SET confidence     = $1,
            evidence_count = evidence_count + 1,
            last_reinforced = now()
        WHERE id = $2
        """,
        new_confidence, row["id"],
    )
    logger.info(
        "REINFORCE [%s] confidence %.2f → %.2f | %s",
        dimension, row["confidence"], new_confidence, evidence_note,
    )


async def _insert_new_belief(
    conn: asyncpg.Connection,
    dimension: str,
    belief: str,
    confidence: float,
) -> None:
    # Soft-invalidate any existing active belief for this dimension first.
    await conn.execute(
        """
        UPDATE operator_model
        SET invalidated_at = now()
        WHERE ghost_id = $1 AND dimension = $2 AND invalidated_at IS NULL
        """,
        GHOST_ID, dimension,
    )
    await conn.execute(
        """
        INSERT INTO operator_model
            (ghost_id, dimension, belief, confidence, evidence_count, formed_at, last_reinforced, formed_by)
        VALUES ($1, $2, $3, $4, 1, now(), now(), 'operator_synthesis')
        """,
        GHOST_ID, dimension, belief, confidence,
    )
    logger.info("NEW belief [%s] confidence=%.2f | %s", dimension, confidence, belief)


async def _log_contradiction(
    conn: asyncpg.Connection,
    dimension: str,
    prior_belief_id: int | None,
    observed_event: str,
    tension_score: float,
) -> None:
    result = await conn.execute(
        """
        INSERT INTO operator_contradictions
            (ghost_id, dimension, prior_belief_id, observed_event, tension_score)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (ghost_id, dimension)
        WHERE status = 'open'
        DO UPDATE SET
            tension_score = GREATEST(operator_contradictions.tension_score, EXCLUDED.tension_score),
            observed_event = CASE
                WHEN length(operator_contradictions.observed_event) >= length(EXCLUDED.observed_event)
                    THEN operator_contradictions.observed_event
                ELSE EXCLUDED.observed_event
            END,
            prior_belief_id = COALESCE(operator_contradictions.prior_belief_id, EXCLUDED.prior_belief_id)
        """,
        GHOST_ID, dimension, prior_belief_id, observed_event, tension_score,
    )
    if str(result).startswith("INSERT"):
        logger.info(
            "CONTRADICT [%s] tension=%.2f | %s", dimension, tension_score, observed_event
        )
        reason_codes = ["new_open_tension"]
    elif str(result).startswith("UPDATE"):
        logger.info(
            "CONTRADICT MERGED [%s] tension=%.2f | %s",
            dimension, tension_score, observed_event,
        )
        reason_codes = ["existing_tension_merged"]
    else:
        logger.debug(
            "CONTRADICT deduped [%s] | %s", dimension, observed_event
        )
        reason_codes = ["deduped"]

    await behavior_events.emit_event_conn(
        conn,
        ghost_id=GHOST_ID,
        event_type="contradiction_opened",
        severity="warn",
        surface="operator_model",
        actor="operator_synthesis",
        target_key=str(dimension or ""),
        reason_codes=reason_codes,
        context={
            "dimension": str(dimension or ""),
            "prior_belief_id": int(prior_belief_id) if prior_belief_id else None,
            "tension_score": float(tension_score or 0.0),
            "observed_event": str(observed_event or "")[:400],
        },
    )


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------
async def _call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not configured for operator synthesis")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1024},
    }
    models: list[str] = []
    for model in [GEMINI_MODEL, *GEMINI_MODEL_FALLBACKS]:
        if model and model not in models:
            models.append(model)

    if not models:
        raise RuntimeError("No Gemini models configured for operator synthesis")

    async with httpx.AsyncClient(timeout=30) as client:
        last_exc: Exception | None = None
        for idx, model in enumerate(models):
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={GEMINI_API_KEY}"
            )
            try:
                resp = await client.post(url, json=payload)
                # Retry on missing model if we have additional candidates.
                if resp.status_code == 404 and idx < len(models) - 1:
                    logger.warning(
                        "Operator synthesis model '%s' returned 404; trying fallback '%s'",
                        model,
                        models[idx + 1],
                    )
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception as exc:
                last_exc = exc
                if idx < len(models) - 1 and "404" in str(exc):
                    continue
                if idx < len(models) - 1:
                    logger.warning(
                        "Operator synthesis call failed on model '%s': %s. Trying fallback '%s'",
                        model,
                        exc,
                        models[idx + 1],
                    )
                    continue
                raise

        if last_exc is not None:
            raise last_exc
        
        # This path should be unreachable given the logic above, 
        # but satisfies the linter's need for an explicit return/raise.
        raise RuntimeError("Operator synthesis Gemini call failed: No models available.")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def _parse_synthesis_output(text: str) -> list[dict[str, Any]]:
    """
    Parse the structured synthesis output into action dicts.
    Each dict has a 'type' key and dimension-specific fields.
    Malformed lines are logged and skipped.
    """
    actions: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("`")
        if line.startswith("- "):
            line = line[2:].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        action_type = parts[0].upper()

        try:
            if action_type == "REINFORCE" and len(parts) >= 2:
                actions.append({
                    "type": "REINFORCE",
                    "dimension": parts[1],
                    "evidence": parts[2] if len(parts) >= 3 and parts[2] else "reinforced by transcript evidence",
                })
            elif action_type == "NEW" and len(parts) >= 3:
                belief_text = parts[2]
                if _is_truncated(belief_text):
                    logger.warning("Rejected truncated belief: %r", belief_text)
                    continue
                confidence = CONFIDENCE_NEW_BELIEF
                if len(parts) >= 4:
                    try:
                        confidence = min(0.5, max(0.3, float(parts[3])))
                    except (ValueError, TypeError):
                        confidence = CONFIDENCE_NEW_BELIEF
                actions.append({
                    "type": "NEW",
                    "dimension": parts[1],
                    "belief": belief_text,
                    "confidence": confidence,
                })
            elif action_type == "CONTRADICT" and len(parts) >= 4:
                # Accept partial lines and default tension score if omitted/truncated.
                observed_event = parts[3]
                tension_score = 0.7
                if len(parts) >= 5:
                    try:
                        tension_score = min(1.0, max(0.1, float(parts[-1])))
                        if len(parts) > 5:
                            observed_event = " | ".join(parts[3:-1]).strip() or observed_event
                    except (ValueError, TypeError):
                        observed_event = " | ".join(parts[3:]).strip() or observed_event
                actions.append({
                    "type": "CONTRADICT",
                    "dimension": parts[1],
                    "prior_belief_id": _safe_int(parts[2]),
                    "observed_event": observed_event,
                    "tension_score": tension_score,
                })
            elif action_type == "UNCHANGED":
                # UNCHANGED is informational only; avoid emitting write actions.
                continue
            else:
                logger.debug("Skipping unrecognised synthesis line: %r", line)
        except (ValueError, IndexError) as exc:
            logger.warning("Parse error on line %r: %s", line, exc)

    return actions


def _safe_int(val: str) -> int | None:
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Core synthesis run
# ---------------------------------------------------------------------------
async def run_synthesis(session_id: str | None = None) -> dict[str, int]:
    """
    Execute one synthesis pass.
    Returns counts: {reinforced, new, contradicted, unchanged}
    """
    counts = {"reinforced": 0, "new": 0, "contradicted": 0, "unchanged": 0}
    if not GEMINI_API_KEY:
        logger.warning("Operator synthesis skipped: GOOGLE_API_KEY is not configured")
        return counts
    if not DATABASE_URL:
        logger.warning("Operator synthesis skipped: POSTGRES_URL is not configured")
        return counts

    pool = await _get_pool()
    async with pool.acquire() as conn:
        active_beliefs = await _load_active_beliefs(conn)
        transcript     = await _load_recent_transcript(conn, session_id)

        beliefs_str = (
            json.dumps(active_beliefs, indent=2)
            if active_beliefs
            else "(no beliefs formed yet)"
        )

        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            active_beliefs=beliefs_str,
            transcript=transcript,
        )
        logger.info("Synthesis transcript length: %d chars", len(transcript))
        if transcript and transcript != "(no recent transcript)":
            logger.info("Synthesis transcript preview: %s", transcript[:240].replace("\n", " | "))

        raw_output = await _call_gemini(prompt)
        logger.info("Synthesis raw output: %s", raw_output[:500])

        actions = _parse_synthesis_output(raw_output)
        logger.info("Synthesis parsed actions: %d", len(actions))

        # Advisory-only RPD scoring (shadow decision), never blocks writes.
        if _rpd_available and rpd_engine is not None and actions:
            try:
                rpd_candidates: list[dict[str, Any]] = []
                for action in actions:
                    t = action.get("type")
                    if t == "NEW":
                        rpd_candidates.append(
                            {
                                "candidate_type": "operator_belief",
                                "candidate_key": str(action.get("dimension", "")),
                                "candidate_value": str(action.get("belief", "")),
                                "shadow_action": {"action": "NEW"},
                            }
                        )
                    elif t == "CONTRADICT":
                        rpd_candidates.append(
                            {
                                "candidate_type": "operator_contradiction",
                                "candidate_key": str(action.get("dimension", "")),
                                "candidate_value": str(action.get("observed_event", "")),
                                "shadow_action": {"action": "CONTRADICT"},
                            }
                        )
                    elif t == "REINFORCE":
                        rpd_candidates.append(
                            {
                                "candidate_type": "operator_reinforcement",
                                "candidate_key": str(action.get("dimension", "")),
                                "candidate_value": str(action.get("evidence", "")),
                                "shadow_action": {"action": "REINFORCE"},
                            }
                        )
                if rpd_candidates:
                    await rpd_engine.evaluate_candidates(
                        pool,
                        rpd_candidates,
                        source="operator_synthesis",
                        ghost_id=GHOST_ID,
                        capture_residue=True,
                    )
            except Exception as e:
                logger.warning("Operator synthesis RPD advisory failed: %s", e)

        for action in actions:
            t = action["type"]
            if t == "REINFORCE":
                await _reinforce_belief(conn, action["dimension"], action["evidence"])
                counts["reinforced"] += 1
            elif t == "NEW":
                await _insert_new_belief(
                    conn, action["dimension"], action["belief"], action["confidence"]
                )
                counts["new"] += 1
            elif t == "CONTRADICT":
                await _log_contradiction(
                    conn,
                    action["dimension"],
                    action.get("prior_belief_id"),
                    action["observed_event"],
                    action["tension_score"],
                )
                counts["contradicted"] += 1
            elif t == "UNCHANGED":
                counts["unchanged"] += 1

        logger.info("Synthesis complete: %s", counts)

    return counts


# ---------------------------------------------------------------------------
# Adaptive tempo loop
# ---------------------------------------------------------------------------
class OperatorSynthesisLoop:
    """
    Manages adaptive-tempo synthesis scheduling.

    Active mode  (user_active=True):
        Triggers every ACTIVE_INTERVAL_TURNS new turns.
    Idle mode (user_active=False):
        Triggers every IDLE_INTERVAL_SECONDS seconds.

    Call .record_turn() from ghost_api.py on every completed user turn.
    Call .set_active(False) when the session goes idle / closes.
    """

    def __init__(self) -> None:
        self._turn_counter: int = 0
        self._user_active: bool = False
        self._idle_task: asyncio.Task | None = None
        self._last_session_id: str | None = None

    def record_turn(self, session_id: str | None = None) -> None:
        """Call once per completed conversation turn."""
        self._last_session_id = session_id
        self._turn_counter += 1
        logger.debug(
            "OperatorSynthesisLoop: turn %d / %d",
            self._turn_counter, ACTIVE_INTERVAL_TURNS,
        )
        if self._turn_counter >= ACTIVE_INTERVAL_TURNS:
            self._turn_counter = 0
            asyncio.create_task(self._run("active_interval"))

    def set_active(self, active: bool, session_id: str | None = None) -> None:
        """
        Notify the loop of activity state changes.
        - set_active(True)  when user sends first message of a session
        - set_active(False) when session closes / coalescence fires
        """
        self._user_active = active
        self._last_session_id = session_id

        if active:
            self._cancel_idle_task()
            logger.debug("OperatorSynthesisLoop: switched to ACTIVE mode")
        else:
            # Fire immediately on session close (post-session synthesis)
            asyncio.create_task(self._run("post_session"))
            # Then start idle polling
            self._start_idle_task()
            logger.debug("OperatorSynthesisLoop: switched to IDLE mode")

    def _start_idle_task(self) -> None:
        self._cancel_idle_task()
        self._idle_task = asyncio.create_task(self._idle_loop())

    def _cancel_idle_task(self) -> None:
        if self._idle_task is not None:
            if not self._idle_task.done():
                self._idle_task.cancel()
            self._idle_task = None

    async def _idle_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(IDLE_INTERVAL_SECONDS)
                if not self._user_active:
                    await self._run("idle_interval")
        except asyncio.CancelledError:
            pass

    async def _run(self, trigger: str) -> None:
        logger.info("OperatorSynthesisLoop: running synthesis [trigger=%s]", trigger)
        try:
            counts = await run_synthesis(self._last_session_id)
            logger.info("OperatorSynthesisLoop [%s]: %s", trigger, counts)
        except Exception as exc:
            logger.error("OperatorSynthesisLoop error [%s]: %s", trigger, exc)


# ---------------------------------------------------------------------------
# Module-level singleton — import this in main.py
# ---------------------------------------------------------------------------
operator_synthesis_loop = OperatorSynthesisLoop()
