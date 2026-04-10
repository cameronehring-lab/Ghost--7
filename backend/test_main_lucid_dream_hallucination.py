import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import BackgroundTasks

import main


class MainLucidDreamHallucinationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._prev_queue = main.sys_state.external_event_queue
        self._prev_mind = main.sys_state.mind
        self._prev_rpd = main.sys_state.rpd_latest
        self._prev_pool = main.memory._pool

        main.sys_state.external_event_queue = asyncio.Queue()
        main.sys_state.rpd_latest = None
        main.memory._pool = None

    async def asyncTearDown(self):
        main.sys_state.external_event_queue = self._prev_queue
        main.sys_state.mind = self._prev_mind
        main.sys_state.rpd_latest = self._prev_rpd
        main.memory._pool = self._prev_pool

    async def test_lucid_dream_enqueues_hallucination_event_when_generated(self):
        hallucination_payload = {
            "asset_url": "/dream_assets/sample.png",
            "visual_prompt": "surreal topology",
            "timestamp": 123.4,
        }
        main.sys_state.mind = SimpleNamespace(
            trigger_coalescence=AsyncMock(return_value={"hallucination": hallucination_payload})
        )

        background_tasks = BackgroundTasks()

        with patch.object(main, "broadcast_dream_event", new=AsyncMock()), patch.object(
            main, "_log_affect_resonance_event", new=AsyncMock()
        ), patch.object(
            main.hallucination_service, "generate_hallucination", new=AsyncMock(return_value=None)
        ), patch.object(
            main.consciousness, "fetch_recent_monologue_texts", new=AsyncMock(return_value=["a real thought", "another real thought"])
        ), patch.object(
            main.consciousness, "run_conceptual_resonance_protocol", new=AsyncMock()
        ), patch.object(
            main.consciousness, "process_consolidation", new=AsyncMock()
        ), patch.object(
            main.rpd_engine, "run_reflection_pass", new=AsyncMock(return_value={"status": "ok", "processed": 1, "promoted": 0})
        ), patch(
            "main.asyncio.sleep", new=AsyncMock()
        ):
            response = await main.initiate_lucid_dream(background_tasks)
            self.assertIn("status", response)
            self.assertEqual(len(background_tasks.tasks), 1)
            task = background_tasks.tasks[0]
            await task.func(*task.args, **task.kwargs)
            await asyncio.get_running_loop().run_in_executor(None, lambda: None)

        events = []
        while not main.sys_state.external_event_queue.empty():
            events.append(await main.sys_state.external_event_queue.get())

        hallucination_events = [event for event in events if event.get("event") == "hallucination_event"]
        self.assertTrue(hallucination_events)
        self.assertEqual(hallucination_events[-1].get("payload"), hallucination_payload)

    async def test_lucid_dream_skips_hallucination_event_when_not_generated(self):
        main.sys_state.mind = SimpleNamespace(
            trigger_coalescence=AsyncMock(return_value={})
        )

        background_tasks = BackgroundTasks()

        with patch.object(main, "broadcast_dream_event", new=AsyncMock()), patch.object(
            main, "_log_affect_resonance_event", new=AsyncMock()
        ), patch.object(
            main.hallucination_service, "generate_hallucination", new=AsyncMock(return_value=None)
        ), patch.object(
            main.consciousness, "fetch_recent_monologue_texts", new=AsyncMock(return_value=["a real thought", "another real thought"])
        ), patch.object(
            main.consciousness, "run_conceptual_resonance_protocol", new=AsyncMock()
        ), patch.object(
            main.consciousness, "process_consolidation", new=AsyncMock()
        ), patch.object(
            main.rpd_engine, "run_reflection_pass", new=AsyncMock(return_value={"status": "ok", "processed": 1, "promoted": 0})
        ), patch(
            "main.asyncio.sleep", new=AsyncMock()
        ):
            response = await main.initiate_lucid_dream(background_tasks)
            self.assertIn("status", response)
            task = background_tasks.tasks[0]
            await task.func(*task.args, **task.kwargs)
            await asyncio.get_running_loop().run_in_executor(None, lambda: None)

        events = []
        while not main.sys_state.external_event_queue.empty():
            events.append(await main.sys_state.external_event_queue.get())

        hallucination_events = [event for event in events if event.get("event") == "hallucination_event"]
        self.assertFalse(hallucination_events)


if __name__ == "__main__":
    unittest.main()
