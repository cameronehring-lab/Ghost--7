"""
behavior_events.py
Unified behavior-level event logging + summaries.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("omega.behavior_events")

ALLOWED_EVENT_TYPES = {
    "priority_defense",
    "unsafe_directive_rejected",
    "operator_fact_correction",
    "quietude_requested",
    "quietude_entered",
    "quietude_exited",
    "governance_shadow_route",
    "governance_blocked",
    "mutation_proposed",
    "mutation_pending_approval",
    "mutation_executed",
    "mutation_failed",
    "mutation_undone",
    "contradiction_opened",
    "contradiction_resolved",
}

SEVERITY_LEVELS = {"info", "warn", "error", "critical"}


def _safe_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _norm_event_type(value: str) -> str:
    key = str(value or "").strip().lower()
    if not key:
        return "priority_defense"
    if key in ALLOWED_EVENT_TYPES:
        return key
    return "priority_defense"


def _norm_severity(value: str) -> str:
    key = str(value or "").strip().lower()
    if key in SEVERITY_LEVELS:
        return key
    return "info"


def classify_mutation_status(status: str) -> tuple[str, str]:
    """Map mutation journal status to a behavior event + severity."""
    key = str(status or "").strip().lower()
    if key == "proposed":
        return "mutation_proposed", "info"
    if key == "pending_approval":
        return "mutation_pending_approval", "warn"
    if key == "executed":
        return "mutation_executed", "info"
    if key == "undone":
        return "mutation_undone", "warn"
    if key in {"failed", "rejected"}:
        return "mutation_failed", "error"
    return "mutation_proposed", "info"


def _normalize_reasons(values: Optional[list[str]]) -> list[str]:
    out: list[str] = []
    for raw in values or []:
        token = str(raw or "").strip().lower().replace(" ", "_")
        if not token:
            continue
        if token in out:
            continue
        out.append(token[:80])
        if len(out) >= 16:
            break
    return out


async def emit_event_conn(
    conn,
    *,
    ghost_id: str,
    event_type: str,
    severity: str = "info",
    surface: str = "runtime",
    actor: str = "system",
    target_key: str = "",
    reason_codes: Optional[list[str]] = None,
    context: Optional[dict[str, Any]] = None,
) -> bool:
    et = _norm_event_type(event_type)
    sev = _norm_severity(severity)
    reason_payload = _normalize_reasons(reason_codes)
    ctx = dict(context or {})

    try:
        await conn.execute(
            """
            INSERT INTO behavior_event_log (
                ghost_id,
                event_type,
                severity,
                surface,
                actor,
                target_key,
                reason_codes_json,
                context_json
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                $7::jsonb,
                $8::jsonb
            )
            """,
            str(ghost_id or "omega-7"),
            et,
            sev,
            str(surface or "runtime")[:64],
            str(actor or "system")[:80],
            str(target_key or "")[:200],
            json.dumps(reason_payload),
            json.dumps(ctx),
        )
        return True
    except Exception as e:
        logger.debug("behavior event write skipped (%s): %s", et, e)
        return False


async def emit_event(
    pool,
    *,
    ghost_id: str,
    event_type: str,
    severity: str = "info",
    surface: str = "runtime",
    actor: str = "system",
    target_key: str = "",
    reason_codes: Optional[list[str]] = None,
    context: Optional[dict[str, Any]] = None,
) -> bool:
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            return await emit_event_conn(
                conn,
                ghost_id=ghost_id,
                event_type=event_type,
                severity=severity,
                surface=surface,
                actor=actor,
                target_key=target_key,
                reason_codes=reason_codes,
                context=context,
            )
    except Exception as e:
        logger.debug("behavior event write skipped (pool): %s", e)
        return False


def _row_to_event(row: Any) -> dict[str, Any]:
    out = dict(row or {})
    out["reason_codes"] = _safe_json(out.pop("reason_codes_json", [])) or []
    out["context"] = _safe_json(out.pop("context_json", {})) or {}
    ts = out.get("created_at")
    out["created_at"] = ts.isoformat() if hasattr(ts, "isoformat") else ts
    if out.get("event_id") is not None:
        out["event_id"] = str(out["event_id"])
    return out


async def list_events(
    pool,
    *,
    ghost_id: str,
    limit: int = 100,
    event_type: str = "",
    actor: str = "",
    surface: str = "",
    hours: float = 0.0,
) -> list[dict[str, Any]]:
    if pool is None:
        return []

    cap = max(1, min(int(limit), 500))
    params: list[Any] = [ghost_id]
    where = ["ghost_id = $1"]

    et = str(event_type or "").strip().lower()
    if et:
        params.append(_norm_event_type(et))
        where.append(f"event_type = ${len(params)}")

    ac = str(actor or "").strip().lower()
    if ac:
        params.append(ac)
        where.append(f"lower(actor) = ${len(params)}")

    sf = str(surface or "").strip().lower()
    if sf:
        params.append(sf)
        where.append(f"lower(surface) = ${len(params)}")

    h = float(hours or 0.0)
    if h > 0.0:
        params.append(max(60.0, h * 3600.0))
        where.append(f"created_at >= (now() - make_interval(secs => ${len(params)}))")

    params.append(cap)
    sql = (
        "SELECT event_id::text AS event_id, ghost_id, event_type, severity, surface, actor, "
        "target_key, reason_codes_json, context_json, created_at "
        "FROM behavior_event_log "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY created_at DESC "
        f"LIMIT ${len(params)}"
    )

    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [_row_to_event(r) for r in rows]


async def summarize_events(
    pool,
    *,
    ghost_id: str,
    window_hours: float = 24.0,
    latest_limit: int = 20,
) -> dict[str, Any]:
    window = max(1.0, min(float(window_hours or 24.0), 24.0 * 30.0))
    window_seconds = window * 3600.0

    out: dict[str, Any] = {
        "ghost_id": ghost_id,
        "window_hours": window,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "total_current": 0,
        "total_previous": 0,
        "by_type_current": {},
        "by_type_previous": {},
        "by_severity_current": {},
        "trend_by_type": {},
        "top_reason_codes": [],
        "latest_events": [],
    }
    if pool is None:
        return out

    async with pool.acquire() as conn:
        counts = await conn.fetch(
            """
            SELECT
                CASE
                    WHEN created_at >= (now() - make_interval(secs => $2)) THEN 'current'
                    ELSE 'previous'
                END AS bucket,
                event_type,
                severity,
                COUNT(*)::int AS n
            FROM behavior_event_log
            WHERE ghost_id = $1
              AND created_at >= (now() - make_interval(secs => $3))
            GROUP BY bucket, event_type, severity
            """,
            ghost_id,
            window_seconds,
            window_seconds * 2.0,
        )
        reasons = await conn.fetch(
            """
            SELECT reason_code, COUNT(*)::int AS n
            FROM (
                SELECT jsonb_array_elements_text(reason_codes_json) AS reason_code
                FROM behavior_event_log
                WHERE ghost_id = $1
                  AND created_at >= (now() - make_interval(secs => $2))
            ) x
            GROUP BY reason_code
            ORDER BY n DESC, reason_code ASC
            LIMIT 16
            """,
            ghost_id,
            window_seconds,
        )
        latest_rows = await conn.fetch(
            """
            SELECT event_id::text AS event_id, ghost_id, event_type, severity, surface, actor,
                   target_key, reason_codes_json, context_json, created_at
            FROM behavior_event_log
            WHERE ghost_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            ghost_id,
            max(1, min(int(latest_limit), 100)),
        )

    by_type_current: Counter[str] = Counter()
    by_type_previous: Counter[str] = Counter()
    by_sev_current: Counter[str] = Counter()

    for row in counts:
        bucket = str(row.get("bucket") or "")
        event_type = str(row.get("event_type") or "")
        severity = str(row.get("severity") or "")
        n = int(row.get("n") or 0)
        if bucket == "current":
            by_type_current[event_type] += n
            by_sev_current[severity] += n
        elif bucket == "previous":
            by_type_previous[event_type] += n

    all_types = sorted(set(by_type_current.keys()) | set(by_type_previous.keys()))
    trend = {}
    for event_type in all_types:
        curr = int(by_type_current.get(event_type, 0))
        prev = int(by_type_previous.get(event_type, 0))
        delta = curr - prev
        direction = "flat"
        if delta > 0:
            direction = "up"
        elif delta < 0:
            direction = "down"
        trend[event_type] = {
            "current": curr,
            "previous": prev,
            "delta": delta,
            "direction": direction,
        }

    out["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    out["total_current"] = int(sum(by_type_current.values()))
    out["total_previous"] = int(sum(by_type_previous.values()))
    out["by_type_current"] = dict(by_type_current)
    out["by_type_previous"] = dict(by_type_previous)
    out["by_severity_current"] = dict(by_sev_current)
    out["trend_by_type"] = trend
    out["top_reason_codes"] = [
        {"reason_code": str(r.get("reason_code") or ""), "count": int(r.get("n") or 0)}
        for r in reasons
        if str(r.get("reason_code") or "").strip()
    ]
    out["latest_events"] = [_row_to_event(r) for r in latest_rows]

    return out
