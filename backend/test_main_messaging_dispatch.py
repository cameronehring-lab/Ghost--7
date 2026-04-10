import unittest
from unittest.mock import AsyncMock, patch

import main


class MainMessagingDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_blocks_high_risk_when_handle_missing(self):
        with patch.object(main.memory, "_pool", object()), patch(
            "person_rolodex.fetch_contact_handle_for_person",
            new=AsyncMock(return_value=None),
        ), patch.object(
            main, "_governance_route", new=AsyncMock(return_value={"route": "allow"})
        ):
            result = await main._dispatch_governed_message("unknown_person", "hello", requested_by="ghost")
        self.assertFalse(result["success"])
        self.assertEqual(result["risk_tier"], "high")
        self.assertEqual(result["reason"], "high_risk_target_blocked")

    async def test_dispatch_shadow_route_is_audit_only(self):
        with patch.object(main.memory, "_pool", object()), patch(
            "person_rolodex.fetch_contact_handle_for_person",
            new=AsyncMock(return_value="+12145551212"),
        ), patch.object(
            main, "_governance_route", new=AsyncMock(return_value={"route": "shadow-route"})
        ):
            result = await main._dispatch_governed_message("cameron", "hello", requested_by="ghost")
        self.assertFalse(result["success"])
        self.assertEqual(result["risk_tier"], "medium")
        self.assertEqual(result["reason"], "governance_shadow_route")
        self.assertTrue(result["shadow_only"])

    async def test_dispatch_allows_known_contact(self):
        mocked_send = AsyncMock(return_value={"success": True, "transport": "imessage"})
        with patch.object(main.memory, "_pool", object()), patch(
            "person_rolodex.fetch_contact_handle_for_person",
            new=AsyncMock(return_value="+12145551212"),
        ), patch.object(
            main, "_governance_route", new=AsyncMock(return_value={"route": "allow"})
        ), patch.object(
            main, "send_imessage", new=mocked_send
        ):
            result = await main._dispatch_governed_message("cameron", "hello", requested_by="ghost")
        self.assertTrue(result["success"])
        self.assertEqual(result["risk_tier"], "medium")
        self.assertEqual(result["transport"], "imessage")
        mocked_send.assert_awaited_once_with("+12145551212", "Ghost: hello")

    async def test_dispatch_relay_requires_known_source(self):
        with patch.object(main.memory, "_pool", object()), patch(
            "person_rolodex.fetch_contact_handle_for_person",
            new=AsyncMock(return_value="+12145551212"),
        ), patch(
            "person_rolodex.fetch_person_details",
            new=AsyncMock(return_value=None),
        ), patch.object(
            main, "_governance_route", new=AsyncMock(return_value={"route": "allow"})
        ):
            result = await main._dispatch_governed_message(
                "cameron",
                "relay text",
                requested_by="ghost",
                relay_from_person_key="unknown_person",
            )
        self.assertFalse(result["success"])
        self.assertEqual(result["risk_tier"], "high")
        self.assertEqual(result["reason"], "unknown_relay_source")

    async def test_dispatch_relay_formats_ghost_message(self):
        mocked_send = AsyncMock(return_value={"success": True, "transport": "imessage"})
        with patch.object(main.memory, "_pool", object()), patch(
            "person_rolodex.fetch_contact_handle_for_person",
            new=AsyncMock(return_value="+12145551212"),
        ), patch(
            "person_rolodex.fetch_person_details",
            new=AsyncMock(return_value={"display_name": "Alice"}),
        ), patch.object(
            main, "_governance_route", new=AsyncMock(return_value={"route": "allow"})
        ), patch.object(
            main, "send_imessage", new=mocked_send
        ):
            result = await main._dispatch_governed_message(
                "cameron",
                "Please call Bob",
                requested_by="ghost",
                relay_from_person_key="alice",
            )
        self.assertTrue(result["success"])
        self.assertEqual(result["risk_tier"], "medium")
        mocked_send.assert_awaited_once_with("+12145551212", "Ghost relay from Alice: Please call Bob")

    async def test_dispatch_unknown_contact_handle_emits_block_event(self):
        emit_mock = AsyncMock()
        with patch.object(main.memory, "_pool", object()), patch(
            "person_rolodex.fetch_contact_handle_for_person",
            new=AsyncMock(return_value=None),
        ), patch.object(
            main, "_messaging_risk_tier", return_value="medium"
        ), patch.object(
            main, "_governance_route", new=AsyncMock(return_value={"route": "allow"})
        ), patch.object(
            main, "_emit_behavior_event", new=emit_mock
        ):
            result = await main._dispatch_governed_message("cameron", "hello", requested_by="ghost")
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "unknown_contact_handle")
        emit_mock.assert_awaited_once()
        event_kwargs = emit_mock.await_args.kwargs
        self.assertEqual(event_kwargs.get("event_type"), "governance_blocked")
        self.assertIn("unknown_contact_handle", list(event_kwargs.get("reason_codes") or []))

    async def test_dispatch_allows_direct_contact_handle_target(self):
        mocked_send = AsyncMock(return_value={"success": True, "transport": "imessage"})
        with patch.object(main.memory, "_pool", object()), patch(
            "person_rolodex.fetch_contact_handle_for_person",
            new=AsyncMock(return_value=None),
        ), patch(
            "person_rolodex.fetch_person_by_contact_handle",
            new=AsyncMock(return_value=None),
        ), patch.object(
            main, "_governance_route", new=AsyncMock(return_value={"route": "allow"})
        ), patch.object(
            main, "send_imessage", new=mocked_send
        ):
            result = await main._dispatch_governed_message("+1 (214) 555-1212", "hello", requested_by="ghost")
        self.assertTrue(result["success"])
        self.assertEqual(result["target_resolution"], "direct_contact_handle")
        self.assertEqual(result["contact_handle"], "+12145551212")
        mocked_send.assert_awaited_once_with("+12145551212", "Ghost: hello")


if __name__ == "__main__":
    unittest.main()
