"""
test_operator_synthesis.py — OMEGA 4 / Ghost
Full test suite for the Operator Model Synthesis feature.

Usage:
    python test_operator_synthesis.py
    python test_operator_synthesis.py --live   # also runs DB round-trip tests
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Minimal stubs so the module imports without a live DB/Gemini
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL",  "postgresql://ghost:ghost@localhost:5432/ghost")
os.environ.setdefault("POSTGRES_URL",  "postgresql://ghost:ghost@localhost:5432/ghost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("GHOST_ID",       "omega-7")

from operator_synthesis import (
    ACTIVE_INTERVAL_TURNS,
    CONFIDENCE_MAX,
    CONFIDENCE_NEW_BELIEF,
    CONFIDENCE_REINFORCE_BUMP,
    OperatorSynthesisLoop,
    _parse_synthesis_output,
    run_synthesis,
)

logging.basicConfig(level=logging.WARNING)


# ===========================================================================
# 1. Parser unit tests (no DB, no LLM)
# ===========================================================================
class TestParser(unittest.TestCase):

    def test_reinforce_parsed(self):
        line = "REINFORCE | intellectual_style | Probed Ghost's reasoning process directly"
        actions = _parse_synthesis_output(line)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "REINFORCE")
        self.assertEqual(actions[0]["dimension"], "intellectual_style")

    def test_new_parsed_confidence_clamped(self):
        # Confidence above 0.5 should be clamped to 0.5
        line = "NEW | trust_level | Cameron gives Ghost latitude to assert its own views | 0.9"
        actions = _parse_synthesis_output(line)
        self.assertEqual(actions[0]["type"], "NEW")
        self.assertLessEqual(actions[0]["confidence"], 0.5)
        self.assertGreaterEqual(actions[0]["confidence"], 0.3)

    def test_new_parsed_confidence_floor(self):
        # Confidence below 0.3 should be raised to 0.3
        line = "NEW | emotional_register | Cameron is detached | 0.1"
        actions = _parse_synthesis_output(line)
        self.assertGreaterEqual(actions[0]["confidence"], 0.3)

    def test_contradict_parsed(self):
        line = "CONTRADICT | trust_level | 42 | Cameron rejected Ghost's assertion directly | 0.7"
        actions = _parse_synthesis_output(line)
        self.assertEqual(actions[0]["type"], "CONTRADICT")
        self.assertEqual(actions[0]["prior_belief_id"], 42)
        self.assertAlmostEqual(actions[0]["tension_score"], 0.7)

    def test_unchanged_produces_no_action(self):
        line = "UNCHANGED | value_hierarchy"
        actions = _parse_synthesis_output(line)
        self.assertEqual(len(actions), 0)

    def test_malformed_line_skipped(self):
        text = "GARBAGE | no | enough | fields\nREINFORCE | intellectual_style | valid note"
        actions = _parse_synthesis_output(text)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "REINFORCE")

    def test_multiline_mixed(self):
        text = """
REINFORCE | intellectual_style | Asked probing architecture questions
NEW | challenge_pattern | Cameron pushes back when Ghost hedges | 0.4
UNCHANGED | emotional_register
CONTRADICT | trust_level | 7 | Cameron overrode Ghost's suggestion without explanation | 0.6
"""
        actions = _parse_synthesis_output(text)
        types = [a["type"] for a in actions]
        self.assertIn("REINFORCE",  types)
        self.assertIn("NEW",        types)
        self.assertIn("CONTRADICT", types)

    def test_tension_score_clamped(self):
        line = "CONTRADICT | trust_level | 1 | some event | 99.0"
        actions = _parse_synthesis_output(line)
        self.assertLessEqual(actions[0]["tension_score"], 1.0)

    def test_tension_score_floor(self):
        line = "CONTRADICT | trust_level | 1 | some event | -5.0"
        actions = _parse_synthesis_output(line)
        self.assertGreaterEqual(actions[0]["tension_score"], 0.1)


# ===========================================================================
# 2. Adaptive tempo unit tests (no DB, no LLM)
# ===========================================================================
class TestAdaptiveTempo(unittest.IsolatedAsyncioTestCase):

    async def test_turn_counter_fires_at_interval(self):
        loop = OperatorSynthesisLoop()
        fired = []

        async def fake_run(trigger):
            fired.append(trigger)

        loop._run = fake_run

        for _ in range(ACTIVE_INTERVAL_TURNS - 1):
            loop.record_turn()

        await asyncio.sleep(0.01)
        self.assertEqual(len(fired), 0, "Should not fire before interval")

        loop.record_turn()
        await asyncio.sleep(0.05)
        self.assertEqual(len(fired), 1, "Should fire exactly once at interval")

    async def test_set_inactive_fires_post_session(self):
        loop = OperatorSynthesisLoop()
        fired = []

        async def fake_run(trigger):
            fired.append(trigger)

        loop._run = fake_run
        loop.set_active(False)
        await asyncio.sleep(0.05)

        self.assertIn("post_session", fired)

    async def test_set_active_cancels_idle_task(self):
        loop = OperatorSynthesisLoop()
        loop.set_active(False)           # starts idle task
        self.assertIsNotNone(loop._idle_task)

        loop.set_active(True)            # should cancel it
        await asyncio.sleep(0.05)
        self.assertTrue(
            loop._idle_task is None or loop._idle_task.cancelled()
        )

    async def test_turn_counter_resets_after_fire(self):
        loop = OperatorSynthesisLoop()
        loop._run = AsyncMock()

        for _ in range(ACTIVE_INTERVAL_TURNS):
            loop.record_turn()
        await asyncio.sleep(0.05)

        self.assertEqual(loop._turn_counter, 0, "Counter should reset after firing")


# ===========================================================================
# 3. DB round-trip tests (requires --live flag and running Postgres)
# ===========================================================================
class TestDBRoundTrip(unittest.IsolatedAsyncioTestCase):
    """
    These tests write and clean up real rows.
    Only runs when script is invoked with --live.
    """

    @classmethod
    def setUpClass(cls):
        if not RUN_LIVE:
            raise unittest.SkipTest("Skipping live DB tests (run with --live)")

    async def asyncSetUp(self) -> None:
        import asyncpg
        self.conn = await asyncpg.connect(os.environ["POSTGRES_URL"])
        await self.conn.execute(
            "DELETE FROM operator_model WHERE ghost_id = 'test-ghost'"
        )
        await self.conn.execute(
            "DELETE FROM operator_contradictions WHERE ghost_id = 'test-ghost'"
        )

    async def asyncTearDown(self) -> None:
        await self.conn.execute(
            "DELETE FROM operator_model WHERE ghost_id = 'test-ghost'"
        )
        await self.conn.execute(
            "DELETE FROM operator_contradictions WHERE ghost_id = 'test-ghost'"
        )
        await self.conn.close()

    async def test_new_belief_inserted(self):
        from operator_synthesis import _insert_new_belief
        with patch("operator_synthesis.GHOST_ID", "test-ghost"):
            await _insert_new_belief(
                self.conn,
                "intellectual_style",
                "Test belief string",
                0.4,
            )
        row = await self.conn.fetchrow(
            "SELECT * FROM operator_model WHERE ghost_id='test-ghost'"
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["belief"], "Test belief string")
        self.assertAlmostEqual(row["confidence"], 0.4)
        self.assertEqual(row["evidence_count"], 1)

    async def test_reinforce_increments_count_and_confidence(self):
        from operator_synthesis import _insert_new_belief, _reinforce_belief
        with patch("operator_synthesis.GHOST_ID", "test-ghost"):
            await _insert_new_belief(
                self.conn, "trust_level", "Initial belief", 0.4
            )
            await _reinforce_belief(
                self.conn, "trust_level", "Reinforcing evidence"
            )
        row = await self.conn.fetchrow(
            "SELECT evidence_count, confidence FROM operator_model "
            "WHERE ghost_id='test-ghost' AND invalidated_at IS NULL"
        )
        self.assertEqual(row["evidence_count"], 2)
        self.assertGreater(row["confidence"], 0.4)

    async def test_contradiction_logged(self):
        from operator_synthesis import _insert_new_belief, _log_contradiction
        with patch("operator_synthesis.GHOST_ID", "test-ghost"):
            await _insert_new_belief(
                self.conn, "challenge_pattern", "Some belief", 0.4
            )
            belief_id = await self.conn.fetchval(
                "SELECT id FROM operator_model WHERE ghost_id='test-ghost'"
            )
            await _log_contradiction(
                self.conn, "challenge_pattern", belief_id,
                "Observed contradicting behaviour", 0.7
            )
        row = await self.conn.fetchrow(
            "SELECT * FROM operator_contradictions WHERE ghost_id='test-ghost'"
        )
        self.assertIsNotNone(row)
        self.assertFalse(row["resolved"])
        self.assertAlmostEqual(row["tension_score"], 0.7)

    async def test_confidence_capped_at_max(self):
        from operator_synthesis import (
            CONFIDENCE_MAX,
            _insert_new_belief,
            _reinforce_belief,
        )
        with patch("operator_synthesis.GHOST_ID", "test-ghost"):
            await _insert_new_belief(
                self.conn, "value_hierarchy", "Near-max belief", 0.93
            )
            for _ in range(10):
                await _reinforce_belief(
                    self.conn, "value_hierarchy", "more evidence"
                )
        row = await self.conn.fetchrow(
            "SELECT confidence FROM operator_model "
            "WHERE ghost_id='test-ghost' AND invalidated_at IS NULL"
        )
        self.assertLessEqual(row["confidence"], CONFIDENCE_MAX)


# ===========================================================================
# 4. Prompt injection shape test
# ===========================================================================
class TestPromptInjection(unittest.IsolatedAsyncioTestCase):

    async def test_load_operator_model_context_shape(self):
        from ghost_prompt import load_operator_model_context
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {"dimension": "intellectual_style", "belief": "Test", "confidence": 0.8},
            {"dimension": "trust_level",        "belief": "Test", "confidence": 0.4},
        ]
        mock_conn.fetchval.return_value = 2

        ctx = await load_operator_model_context(mock_conn)

        self.assertIn("established", ctx)
        self.assertIn("tentative",   ctx)
        self.assertIn("open_tensions", ctx)
        self.assertEqual(len(ctx["established"]), 1)
        self.assertEqual(len(ctx["tentative"]),   1)
        self.assertEqual(ctx["open_tensions"],    2)


# ===========================================================================
# Entry point
# ===========================================================================
RUN_LIVE = False

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args, remaining = parser.parse_known_args()
    RUN_LIVE = args.live
    sys.argv = [sys.argv[0]] + remaining
    unittest.main(verbosity=2)
