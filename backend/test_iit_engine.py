import asyncio
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT))

try:
    from iit_engine import IITEngine, IITConfig, filter_self_model_rows  # type: ignore
except ModuleNotFoundError:
    import sys
    print("SKIP iit_engine tests: asyncpg not installed")
    sys.exit(0)


class DummyEngine(IITEngine):
    def __init__(self, substrate):
        self._substrate = substrate
        self._last_run_ts = 0.0
        self.config = IITConfig()
        self.pool = None
        self.sys_state = None
        self.emotion_state = None

    async def _build_substrate(self):
        return self._substrate, []

    async def _persist(self, record):
        return None


class IITEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_completeness_counts_present_nodes(self):
        if IITEngine is None:
            self.skipTest("asyncpg/iit_engine deps unavailable")
        substrate = {
            "affect": {"arousal": 0.2},
            "homeostasis": {"quietude_active": False},
            "memory": {"monologue_count": 10},
            "self_model": None,
            "operator_model": {"beliefs": []},
            "agency": {"recent_actuations": []},
        }
        eng = DummyEngine(substrate)
        res = await eng.assess(reason="test")
        self.assertEqual(res["substrate_completeness_score"], 5)
        self.assertTrue(res["not_consciousness_metric"])

    def test_self_model_allowlist(self):
        if filter_self_model_rows is None:
            self.skipTest("iit_engine unavailable")
        rows = [
            {"key": "self_model", "value": "ok", "updated_by": "process_consolidation"},
            {"key": "bad", "value": "nope", "updated_by": "user_prompt"},
            {"key": "missing", "value": "nope", "updated_by": None},
        ]
        filtered = filter_self_model_rows(rows)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["key"], "self_model")


if __name__ == "__main__":
    unittest.main()
