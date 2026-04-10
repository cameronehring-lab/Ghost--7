import unittest
from unittest.mock import AsyncMock, patch

import main


class GovernanceRouteLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_allow_route_logs_decision_without_behavior_event(self):
        log_mock = AsyncMock()
        emit_mock = AsyncMock()
        with patch.object(
            main, "_latest_rrd2_gate_signal", new=AsyncMock(return_value={"phase": "A"})
        ), patch.object(
            main, "route_for_surface", return_value={"route": "allow", "reasons": []}
        ), patch.object(
            main, "_log_governance_route_decision", new=log_mock
        ), patch.object(
            main, "_emit_behavior_event", new=emit_mock
        ):
            route = await main._governance_route("messaging")
        self.assertEqual(route.get("route"), "allow")
        log_mock.assert_awaited_once()
        emit_mock.assert_not_awaited()

    async def test_shadow_route_logs_and_emits_behavior_event(self):
        log_mock = AsyncMock()
        emit_mock = AsyncMock()
        with patch.object(
            main, "_latest_rrd2_gate_signal", new=AsyncMock(return_value={"phase": "A"})
        ), patch.object(
            main, "route_for_surface", return_value={"route": "shadow-route", "reasons": ["rrd2_shadow"]}
        ), patch.object(
            main, "_log_governance_route_decision", new=log_mock
        ), patch.object(
            main, "_emit_behavior_event", new=emit_mock
        ):
            route = await main._governance_route("messaging")
        self.assertEqual(route.get("route"), "shadow-route")
        log_mock.assert_awaited_once()
        emit_mock.assert_awaited_once()
        event_kwargs = emit_mock.await_args.kwargs
        self.assertEqual(event_kwargs.get("event_type"), "governance_shadow_route")
        self.assertIn("rrd2_shadow", list(event_kwargs.get("reason_codes") or []))


if __name__ == "__main__":
    unittest.main()
