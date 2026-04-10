import unittest
from unittest.mock import AsyncMock, patch

import consciousness


class _DummyAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummyConn:
    def __init__(self):
        self.execute_calls: list[tuple[str, tuple]] = []

    async def execute(self, query, *args):
        self.execute_calls.append((str(query), args))
        return "OK"


class _DummyPool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _DummyAcquire(self.conn)


class ConsolidationShadowReflectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_consolidation_schedules_shadow_reflection_from_gate_hint(self):
        pool = _DummyPool(_DummyConn())
        findings = {
            "patterns": [],
            "contradictions": [{"thought_a": "a", "thought_b": "b", "tension": "t"}],
            "drifts": [{"key": "self_model", "direction": "toward drift", "correction": "revise"}],
            "insights": [],
            "tensions_resolved": [],
        }
        corrections = [{"action": "REVISE", "key": "self_model", "value": "Revised self model."}]
        gate_result = {
            "allowed_corrections": corrections,
            "blocked_corrections": [],
            "shadow_gate_hits": [
                {
                    "key": "self_model",
                    "value": "Revised self model.",
                    "phase": "B",
                    "reasons": ["threshold_failed:negative_resonance"],
                }
            ],
            "shadow_residue_routed": [
                {
                    "key": "self_model",
                    "value": "Revised self model.",
                    "phase": "B",
                    "reasons": ["threshold_failed:negative_resonance"],
                }
            ],
            "shadow_reflection_hint": {
                "trigger": True,
                "source": "process_consolidation_shadow_reflection",
                "suggested_limit": 5,
            },
        }

        with patch("consciousness._rpd_available", True), patch(
            "consciousness.fetch_recent_monologue_texts",
            new=AsyncMock(return_value=["thought one", "thought two"]),
        ), patch(
            "consciousness.fetch_operator_context_for_consolidation",
            new=AsyncMock(return_value=""),
        ), patch(
            "consciousness.load_identity",
            new=AsyncMock(return_value={}),
        ), patch(
            "consciousness._call_llm",
            new=AsyncMock(side_effect=["consolidation llm output", "correction llm output"]),
        ), patch(
            "consciousness._parse_consolidation_output",
            return_value=findings,
        ), patch(
            "consciousness._parse_correction_output",
            return_value=corrections,
        ), patch(
            "consciousness._rpd_advisory_evaluate",
            new=AsyncMock(return_value=[]),
        ), patch(
            "consciousness.rpd_engine.apply_hybrid_gate_to_identity_corrections",
            new=AsyncMock(return_value=gate_result),
        ), patch(
            "consciousness._apply_identity_correction",
            new=AsyncMock(return_value=True),
        ), patch(
            "consciousness._schedule_shadow_reflection_pass",
            return_value={"scheduled": True, "source": "process_consolidation_shadow_reflection", "limit": 5},
        ) as schedule_mock:
            result = await consciousness.process_consolidation(pool, ghost_id="omega-7")

        schedule_mock.assert_called_once()
        _, kwargs = schedule_mock.call_args
        self.assertEqual(kwargs["source"], "process_consolidation_shadow_reflection")
        self.assertEqual(kwargs["limit"], 5)
        self.assertEqual(kwargs["ghost_id"], "omega-7")

        self.assertEqual(len(result["rrd2_shadow_residue_routed"]), 1)
        self.assertTrue(bool((result.get("rrd2_shadow_reflection") or {}).get("scheduled")))


if __name__ == "__main__":
    unittest.main()
