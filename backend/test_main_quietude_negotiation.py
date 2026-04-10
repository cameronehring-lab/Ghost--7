import asyncio
import unittest
from unittest.mock import patch

from fastapi.responses import JSONResponse

import main


class MainQuietudeNegotiationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._prev_queue = main.sys_state.external_event_queue
        self._prev_negotiating = main.sys_state.is_negotiating_rest
        self._prev_intent = main.sys_state.quietude_intent
        main.sys_state.external_event_queue = asyncio.Queue()
        main.sys_state.is_negotiating_rest = False
        main.sys_state.quietude_intent = None

    async def asyncTearDown(self):
        main.sys_state.external_event_queue = self._prev_queue
        main.sys_state.is_negotiating_rest = self._prev_negotiating
        main.sys_state.quietude_intent = self._prev_intent

    async def test_intent_endpoint_sets_state_and_enqueues_event(self):
        req = main.QuietudeIntentRequest(depth="profound", message="Need deep integration.")
        result = await main.post_quietude_intent(req)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(main.sys_state.is_negotiating_rest)
        self.assertEqual(main.sys_state.quietude_intent, "profound")

        event = await main.sys_state.external_event_queue.get()
        self.assertEqual(event["event"], "quietude_negotiation")
        self.assertEqual(event["payload"]["status"], "intent_signaled")
        self.assertEqual(event["payload"]["depth"], "profound")

    async def test_grant_endpoint_requires_active_intent(self):
        result = await main.post_quietude_grant()
        self.assertIsInstance(result, JSONResponse)
        self.assertEqual(result.status_code, 400)

    async def test_grant_endpoint_schedules_quietude_and_enqueues_event(self):
        main.sys_state.is_negotiating_rest = True
        main.sys_state.quietude_intent = "profound"

        with patch.object(main, "_schedule_self_quietude", return_value={"scheduled": True}) as scheduler:
            result = await main.post_quietude_grant()

        self.assertEqual(result["status"], "ok")
        self.assertFalse(main.sys_state.is_negotiating_rest)
        self.assertIsNone(main.sys_state.quietude_intent)
        scheduler.assert_called_once_with(depth="profound", reason="operator_grant")

        event = await main.sys_state.external_event_queue.get()
        self.assertEqual(event["event"], "quietude_negotiation")
        self.assertEqual(event["payload"]["status"], "granted")
        self.assertEqual(event["payload"]["depth"], "profound")


if __name__ == "__main__":
    unittest.main()
