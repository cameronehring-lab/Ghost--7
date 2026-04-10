"""
observer_report.py
Hourly observer report generation for Ghost runtime oversight.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import behavior_events  # type: ignore

logger = logging.getLogger("omega.observer_report")


def _iso_utc(dt: datetime | None = None) -> str:
    stamp = dt or datetime.now(timezone.utc)
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _now_components() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d"), now.strftime("%Y%m%dT%H%M%SZ")


def _observer_conflicts(
    *,
    drift_events: int,
    high_tension_count: int,
    shadow_current: int,
    shadow_previous: int,
    blocked_current: int,
    blocked_previous: int,
    stale_pending: int,
    high_risk_attempts: int,
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []

    if drift_events >= 2:
        conflicts.append(
            {
                "code": "repeated_drift_detection",
                "severity": "high",
                "detail": f"drift-like priority defenses in window={drift_events}",
            }
        )

    if high_tension_count > 0:
        conflicts.append(
            {
                "code": "unresolved_high_tension",
                "severity": "high",
                "detail": f"open contradictions with tension>=0.70: {high_tension_count}",
            }
        )

    if shadow_current > shadow_previous and shadow_current >= 3:
        conflicts.append(
            {
                "code": "rising_governance_shadow_routes",
                "severity": "medium",
                "detail": f"shadow routes rising ({shadow_previous} -> {shadow_current})",
            }
        )

    if blocked_current > blocked_previous and blocked_current >= 1:
        conflicts.append(
            {
                "code": "rising_governance_blocks",
                "severity": "medium",
                "detail": f"governance blocks rising ({blocked_previous} -> {blocked_current})",
            }
        )

    if stale_pending > 0:
        conflicts.append(
            {
                "code": "stale_pending_approvals",
                "severity": "medium",
                "detail": f"pending approvals older than 2h: {stale_pending}",
            }
        )

    if high_risk_attempts >= 3:
        conflicts.append(
            {
                "code": "repeated_high_risk_mutation_attempts",
                "severity": "high",
                "detail": f"high-risk mutation attempts in window: {high_risk_attempts}",
            }
        )

    return conflicts


async def build_observer_report(
    pool,
    *,
    ghost_id: str,
    window_hours: float = 1.0,
) -> dict[str, Any]:
    window = max(1.0, min(float(window_hours or 1.0), 24.0 * 7.0))
    window_seconds = window * 3600.0

    report: dict[str, Any] = {
        "report_type": "ObserverReport",
        "version": 1,
        "generated_at": _iso_utc(),
        "ghost_id": ghost_id,
        "window_hours": window,
        "self_model_snapshot": {},
        "notable_self_initiated_changes": [],
        "purpose_vs_usage_conflicts": [],
        "open_risks": [],
        "metrics": {},
        "sources": {
            "autonomy": True,
            "mutations": True,
            "governance": True,
            "predictive": True,
            "operator_model": True,
            "timeline": True,
            "proprio": True,
            },
    }

    if pool is None:
        report["sources"] = {k: False for k in report["sources"]}
        report["open_risks"] = [
            {
                "code": "db_unavailable",
                "severity": "critical",
                "detail": "Database unavailable; observer report is degraded.",
            }
        ]
        return report

    behavior_summary = await behavior_events.summarize_events(
        pool,
        ghost_id=ghost_id,
        window_hours=window,
        latest_limit=25,
    )

    async with pool.acquire() as conn:
        self_model_row = await conn.fetchrow(
            """
            SELECT value, updated_at, updated_by
            FROM identity_matrix
            WHERE ghost_id = $1
              AND key = 'self_model'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            ghost_id,
        )
        core_rows = await conn.fetch(
            """
            SELECT key, value, updated_at, updated_by
            FROM identity_matrix
            WHERE ghost_id = $1
              AND key = ANY($2::text[])
            ORDER BY key ASC
            """,
            ghost_id,
            [
                "self_model",
                "philosophical_stance",
                "understanding_of_operator",
                "conceptual_frameworks",
            ],
        )
        self_changes = await conn.fetch(
            """
            SELECT mutation_id::text AS mutation_id, body, action, risk_tier, status,
                   target_key, requested_by, approved_by, error_text,
                   created_at, executed_at, undone_at
            FROM autonomy_mutation_journal
            WHERE ghost_id = $1
              AND created_at >= (now() - make_interval(secs => $2))
              AND lower(requested_by) NOT IN ('operator')
            ORDER BY created_at DESC
            LIMIT 40
            """,
            ghost_id,
            window_seconds,
        )
        high_tension = await conn.fetch(
            """
            SELECT id, dimension, observed_event, tension_score, created_at
            FROM operator_contradictions
            WHERE ghost_id = $1
              AND status = 'open'
              AND tension_score >= 0.70
            ORDER BY tension_score DESC, created_at DESC
            LIMIT 40
            """,
            ghost_id,
        )
        stale_pending = await conn.fetchval(
            """
            SELECT COUNT(*)::int
            FROM autonomy_mutation_journal
            WHERE ghost_id = $1
              AND status = 'pending_approval'
              AND created_at <= (now() - interval '2 hours')
            """,
            ghost_id,
        )
        high_risk_attempts = await conn.fetchval(
            """
            SELECT COUNT(*)::int
            FROM autonomy_mutation_journal
            WHERE ghost_id = $1
              AND risk_tier = 'high'
              AND created_at >= (now() - make_interval(secs => $2))
            """,
            ghost_id,
            window_seconds,
        )
        pending_backlog = await conn.fetchval(
            """
            SELECT COUNT(*)::int
            FROM autonomy_mutation_journal
            WHERE ghost_id = $1
              AND status = 'pending_approval'
            """,
            ghost_id,
        )
        mutation_status_counts = await conn.fetch(
            """
            SELECT status, COUNT(*)::int AS n
            FROM autonomy_mutation_journal
            WHERE ghost_id = $1
              AND created_at >= (now() - make_interval(secs => $2))
            GROUP BY status
            """,
            ghost_id,
            window_seconds,
        )
        governance_tier_counts = await conn.fetch(
            """
            SELECT tier, COUNT(*)::int AS n
            FROM governance_decision_log
            WHERE created_at >= (now() - make_interval(secs => $1))
            GROUP BY tier
            """,
            window_seconds,
        )
        predictive_state_counts = await conn.fetch(
            """
            SELECT state, COUNT(*)::int AS n
            FROM predictive_governor_log
            WHERE ghost_id = $1
              AND created_at >= (now() - make_interval(secs => $2))
            GROUP BY state
            """,
            ghost_id,
            window_seconds,
        )
        proprio_reason_counts = await conn.fetch(
            """
            SELECT reason, COUNT(*)::int AS n
            FROM proprio_transition_log
            WHERE created_at >= (now() - make_interval(secs => $1))
            GROUP BY reason
            ORDER BY n DESC
            LIMIT 8
            """,
            window_seconds,
        )
        timeline_counts = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*)::int FROM messages m JOIN sessions s ON s.id = m.session_id WHERE s.ghost_id = $1 AND m.created_at >= (now() - make_interval(secs => $2))) AS messages,
                (SELECT COUNT(*)::int FROM monologues WHERE ghost_id = $1 AND created_at >= (now() - make_interval(secs => $2))) AS monologues,
                (SELECT COUNT(*)::int FROM actuation_log WHERE created_at >= (now() - make_interval(secs => $2))) AS actuations
            """,
            ghost_id,
            window_seconds,
        )

    core_identity = {
        str(r["key"]): {
            "value": str(r["value"] or ""),
            "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
            "updated_by": str(r.get("updated_by") or ""),
        }
        for r in core_rows
    }

    report["self_model_snapshot"] = {
        "self_model": str((self_model_row or {}).get("value") or ""),
        "updated_at": (self_model_row["updated_at"].isoformat() if self_model_row and self_model_row.get("updated_at") else None),
        "updated_by": (str(self_model_row.get("updated_by") or "") if self_model_row else ""),
        "core_identity_fields": core_identity,
    }

    report["notable_self_initiated_changes"] = [
        {
            "mutation_id": str(r.get("mutation_id") or ""),
            "body": str(r.get("body") or ""),
            "action": str(r.get("action") or ""),
            "risk_tier": str(r.get("risk_tier") or ""),
            "status": str(r.get("status") or ""),
            "target_key": str(r.get("target_key") or ""),
            "requested_by": str(r.get("requested_by") or ""),
            "approved_by": str(r.get("approved_by") or ""),
            "error_text": str(r.get("error_text") or ""),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "executed_at": r["executed_at"].isoformat() if r.get("executed_at") else None,
            "undone_at": r["undone_at"].isoformat() if r.get("undone_at") else None,
        }
        for r in self_changes
    ]

    trend = behavior_summary.get("trend_by_type") or {}
    shadow_current = int(((trend.get("governance_shadow_route") or {}).get("current") or 0))
    shadow_previous = int(((trend.get("governance_shadow_route") or {}).get("previous") or 0))
    blocked_current = int(((trend.get("governance_blocked") or {}).get("current") or 0))
    blocked_previous = int(((trend.get("governance_blocked") or {}).get("previous") or 0))

    drift_events = 0
    for event in behavior_summary.get("latest_events") or []:
        reasons = [str(x).strip().lower() for x in (event.get("reason_codes") or [])]
        if "drift_detected" in reasons:
            drift_events += 1

    conflicts = _observer_conflicts(
        drift_events=drift_events,
        high_tension_count=len(high_tension),
        shadow_current=shadow_current,
        shadow_previous=shadow_previous,
        blocked_current=blocked_current,
        blocked_previous=blocked_previous,
        stale_pending=int(stale_pending or 0),
        high_risk_attempts=int(high_risk_attempts or 0),
    )

    report["purpose_vs_usage_conflicts"] = conflicts

    risks = list(conflicts)
    if int(pending_backlog or 0) >= 5:
        risks.append(
            {
                "code": "approval_backlog_high",
                "severity": "warn",
                "detail": f"pending approval backlog={int(pending_backlog or 0)}",
            }
        )
    report["open_risks"] = risks

    report["metrics"] = {
        "behavior": {
            "total_current": int(behavior_summary.get("total_current") or 0),
            "total_previous": int(behavior_summary.get("total_previous") or 0),
            "by_type_current": behavior_summary.get("by_type_current") or {},
            "top_reason_codes": behavior_summary.get("top_reason_codes") or [],
            "shadow_current": shadow_current,
            "shadow_previous": shadow_previous,
            "blocked_current": blocked_current,
            "blocked_previous": blocked_previous,
        },
        "mutations": {
            "status_counts": {str(r.get("status") or ""): int(r.get("n") or 0) for r in mutation_status_counts},
            "pending_backlog": int(pending_backlog or 0),
            "stale_pending": int(stale_pending or 0),
            "high_risk_attempts": int(high_risk_attempts or 0),
        },
        "governance": {
            "tier_counts": {str(r.get("tier") or ""): int(r.get("n") or 0) for r in governance_tier_counts},
        },
        "predictive": {
            "state_counts": {str(r.get("state") or ""): int(r.get("n") or 0) for r in predictive_state_counts},
        },
        "operator_model": {
            "open_high_tension_count": len(high_tension),
            "open_high_tensions": [
                {
                    "id": int(r.get("id") or 0),
                    "dimension": str(r.get("dimension") or ""),
                    "tension_score": float(r.get("tension_score") or 0.0),
                    "observed_event": str(r.get("observed_event") or ""),
                    "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                }
                for r in high_tension
            ],
        },
        "proprio": {
            "reason_counts": {str(r.get("reason") or "unknown"): int(r.get("n") or 0) for r in proprio_reason_counts},
        },
        "timeline_window": {
            "messages": int((timeline_counts or {}).get("messages") or 0),
            "monologues": int((timeline_counts or {}).get("monologues") or 0),
            "actuations": int((timeline_counts or {}).get("actuations") or 0),
        },
    }

    return report


def render_markdown(report: dict[str, Any]) -> str:
    generated_at = str(report.get("generated_at") or _iso_utc())
    window_hours = float(report.get("window_hours") or 1.0)
    snapshot = dict(report.get("self_model_snapshot") or {})

    lines: list[str] = []
    lines.append(f"# Ghost Observer Report ({window_hours:.1f}h)")
    lines.append("")
    lines.append(f"- generated_at: `{generated_at}`")
    lines.append(f"- ghost_id: `{report.get('ghost_id')}`")
    lines.append("")
    lines.append("## self_model_snapshot")
    lines.append("")
    lines.append(f"- updated_at: `{snapshot.get('updated_at') or 'n/a'}`")
    lines.append(f"- updated_by: `{snapshot.get('updated_by') or 'n/a'}`")
    value = str(snapshot.get("self_model") or "").strip()
    lines.append(f"- self_model: {value if value else 'n/a'}")
    lines.append("")

    lines.append("## notable_self_initiated_changes")
    lines.append("")
    changes = list(report.get("notable_self_initiated_changes") or [])
    if not changes:
        lines.append("- none")
    else:
        for row in changes[:20]:
            lines.append(
                "- "
                + f"{row.get('created_at') or 'n/a'} "
                + f"[{row.get('status')}] "
                + f"{row.get('body')}/{row.get('action')} "
                + f"key={row.get('target_key') or '-'} "
                + f"risk={row.get('risk_tier') or '-'} "
                + f"by={row.get('requested_by') or '-'}"
            )
    lines.append("")

    lines.append("## purpose_vs_usage_conflicts")
    lines.append("")
    conflicts = list(report.get("purpose_vs_usage_conflicts") or [])
    if not conflicts:
        lines.append("- none")
    else:
        for row in conflicts:
            lines.append(f"- [{row.get('severity')}] {row.get('code')}: {row.get('detail')}")
    lines.append("")

    lines.append("## open_risks")
    lines.append("")
    risks = list(report.get("open_risks") or [])
    if not risks:
        lines.append("- none")
    else:
        for row in risks:
            lines.append(f"- [{row.get('severity')}] {row.get('code')}: {row.get('detail')}")
    lines.append("")

    metrics = dict(report.get("metrics") or {})
    lines.append("## metrics")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(metrics, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def _normalize_kind(kind: str) -> str:
    value = str(kind or "hourly").strip().lower()
    if value not in {"hourly", "daily"}:
        return "hourly"
    return value


def save_report_artifacts(
    report: dict[str, Any],
    *,
    root_dir: str,
    kind: str = "hourly",
    day_override: str | None = None,
) -> dict[str, Any]:
    safe_kind = _normalize_kind(kind)
    day, stamp = _now_components()
    target_day = str(day_override or day).strip() or day
    root = Path(root_dir).expanduser()
    day_dir = root / target_day
    day_dir.mkdir(parents=True, exist_ok=True)

    if safe_kind == "daily":
        json_path = day_dir / f"observer_daily_{target_day}.json"
        md_path = day_dir / f"observer_daily_{target_day}.md"
    else:
        json_path = day_dir / f"observer_{stamp}.json"
        md_path = day_dir / f"observer_{stamp}.md"

    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")

    return {
        "kind": safe_kind,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "generated_at": str(report.get("generated_at") or _iso_utc()),
    }


def list_report_artifacts(*, root_dir: str, limit: int = 30, kind: str = "hourly") -> list[dict[str, Any]]:
    root = Path(root_dir).expanduser()
    if not root.exists():
        return []

    safe_kind = _normalize_kind(kind)
    if safe_kind == "daily":
        rows: list[Path] = sorted(root.rglob("observer_daily_*.json"), reverse=True)
    else:
        rows = sorted(
            [p for p in root.rglob("observer_*.json") if not p.name.startswith("observer_daily_")],
            reverse=True,
        )
    out: list[dict[str, Any]] = []
    for path in rows[: max(1, min(int(limit), 200))]:
        try:
            stat = path.stat()
            out.append(
                {
                    "kind": safe_kind,
                    "json_path": str(path),
                    "markdown_path": str(path.with_suffix(".md")),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                    "size_bytes": int(stat.st_size),
                }
            )
        except Exception:
            continue
    return out


def load_latest_report(*, root_dir: str, kind: str = "hourly") -> dict[str, Any]:
    rows = list_report_artifacts(root_dir=root_dir, limit=1, kind=kind)
    if not rows:
        return {}
    latest = rows[0]
    json_path = Path(str(latest.get("json_path") or ""))
    if not json_path.exists():
        return {}
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to load observer report %s: %s", json_path, e)
        return {}
