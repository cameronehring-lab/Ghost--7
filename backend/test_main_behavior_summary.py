import unittest
from unittest.mock import AsyncMock, patch

import main


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


class _FakeConn:
    async def fetch(self, sql, *args):
        if "FROM autonomy_mutation_journal" in sql and "GROUP BY status" in sql:
            return [{"status": "executed", "n": 4}, {"status": "failed", "n": 1}]
        if "FROM governance_decision_log" in sql and "GROUP BY tier" in sql:
            return [{"tier": "nominal", "n": 5}]
        if "FROM governance_route_log" in sql:
            return [{"bucket": "current", "route": "allow", "n": 5}]
        if "FROM predictive_governor_log" in sql and "GROUP BY state" in sql:
            return [{"state": "stable", "n": 3}]
        if "FROM proprio_transition_log" in sql and "GROUP BY reason" in sql:
            return [{"reason": "threshold_crossing", "n": 2}]
        if "jsonb_each(t.contributions)" in sql:
            return [{"key": "arousal_normalized", "weight": 1.2}]
        if "FROM operator_contradictions" in sql and "GROUP BY dimension" in sql:
            return [{"dimension": "trust", "n": 1}]
        if "FROM world_model_node_count_log" in sql:
            return [{"label": "Observation", "current_count": 10, "previous_count": 8}]
        if "WITH bounds AS" in sql:
            return [{"bucket": "2026-03-11T00:00:00Z", "total": 1, "blocked": 0, "shadow": 0}]
        return []

    async def fetchrow(self, sql, *args):
        if "stale_pending_count" in sql:
            return {"stale_pending_count": 1, "oldest_pending_age_seconds": 120.0}
        if "executed_count" in sql and "approval_latency_seconds" not in sql:
            return {"executed_count": 2, "avg_seconds": 12.0, "p95_seconds": 20.0}
        if "COUNT(*) FILTER (WHERE status = 'undone')" in sql:
            return {"undone": 1, "executed": 2}
        if "COUNT(*)::int AS total" in sql and "governance_decision_log" in sql:
            return {"total": 3, "applied_total": 2}
        if "sample_present" in sql:
            return {"total": 3, "sample_present": 2, "avg_abs_forecast_error": 0.12}
        if "COUNT(*)::int AS transitions" in sql:
            return {"transitions": 2}
        if "event_type = 'quietude_requested'" in sql:
            return {"requested": 1, "entered": 1, "exited": 1}
        if "FROM pairs" in sql:
            return {"samples": 1, "avg_seconds": 90.0, "p95_seconds": 90.0}
        if "event_source = 'quietude_enter'" in sql:
            return {"enter_pressure": 0.8, "exit_pressure": 0.5}
        if "FROM world_model_ingest_log" in sql:
            return {"total": 2, "success_total": 2, "failure_total": 0, "last_applied_at": None}
        if "FROM operator_contradictions" in sql and "resolved_total" in sql:
            return {"open_total": 1, "resolved_total": 2, "avg_resolution_seconds": 33.0}
        if "FROM identity_topology_warp_log" in sql:
            return {
                "samples": 2,
                "p50_eval_ms": 10.0,
                "p95_eval_ms": 25.0,
                "avg_queue_depth": 1.5,
                "p95_queue_depth": 3.0,
                "damping_applied_total": 1,
            }
        return {}

    async def fetchval(self, sql, *args):
        if "status = 'pending_approval'" in sql:
            return 2
        if "reason_codes_json ? 'idempotent_replay'" in sql:
            return 1
        if "FROM autonomy_mutation_journal" in sql and "COUNT(*)::int" in sql:
            return 5
        return 0


class BehaviorSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_populates_previous_placeholder_fields(self):
        fake_pool = _FakePool(_FakeConn())
        summary_stub = {
            "total_current": 4,
            "total_previous": 3,
            "by_type_current": {"priority_defense": 1},
            "by_type_previous": {},
            "trend_by_type": {},
            "top_reason_codes": [],
            "latest_events": [],
        }
        with patch.object(main.memory, "_pool", fake_pool), patch.object(
            main.behavior_events, "summarize_events", new=AsyncMock(return_value=summary_stub)
        ), patch.object(
            main, "_get_world_model_client", return_value=(None, None)
        ):
            payload = await main.get_behavior_summary(window_hours=24)

        metrics = payload.get("metrics") or {}
        self.assertIsNotNone(metrics.get("mutation_layer", {}).get("idempotent_replay_rate"))
        self.assertIsNotNone(metrics.get("governance_layer", {}).get("route_distribution", {}).get("allow"))
        self.assertIsInstance(metrics.get("proprio_layer", {}).get("dominant_contribution_mix"), dict)
        self.assertIn("avg", metrics.get("quietude_layer", {}).get("recovery_time_seconds", {}))
        self.assertIsInstance(metrics.get("world_model_layer", {}).get("node_growth_by_label"), dict)


if __name__ == "__main__":
    unittest.main()
