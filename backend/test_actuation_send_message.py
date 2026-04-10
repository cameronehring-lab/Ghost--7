import unittest
from urllib.error import URLError
from unittest.mock import patch

import actuation


class _FakeEmotionState:
    def __init__(self):
        self.inject_calls = []

    async def inject(self, **kwargs):
        self.inject_calls.append(kwargs)


class ActuationSendMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_send_message_success_injects_trace(self):
        seen = {}

        async def dispatcher(target: str, content: str, relay_from: str | None):
            seen["target"] = target
            seen["content"] = content
            seen["relay_from"] = relay_from
            return {"success": True, "route": {"route": "allow"}, "risk_tier": "low"}

        em = _FakeEmotionState()
        res = await actuation.execute_actuation(
            "send_message",
            "operator:hello:there",
            emotion_state=em,
            message_dispatcher=dispatcher,
        )

        self.assertTrue(res["success"])
        self.assertTrue(res["injected"])
        self.assertEqual(res["trace"], "social_contact_relief")
        self.assertEqual(seen["target"], "operator")
        self.assertEqual(seen["content"], "hello:there")
        self.assertIsNone(seen["relay_from"])
        self.assertEqual(len(em.inject_calls), 2)
        labels = [str(call.get("label")) for call in em.inject_calls]
        self.assertIn("social_contact_relief", labels)
        self.assertIn("agency_fulfilled", labels)

    async def test_execute_send_message_blocked_skips_injection(self):
        async def dispatcher(target: str, content: str, relay_from: str | None):
            return {"success": False, "reason": "governance_shadow_route"}

        em = _FakeEmotionState()
        res = await actuation.execute_actuation(
            "send_message",
            "operator:hello",
            emotion_state=em,
            message_dispatcher=dispatcher,
        )
        self.assertFalse(res["success"])
        self.assertTrue(res["injected"])
        self.assertEqual(res["trace"], "agency_blocked")
        self.assertEqual(res["messaging"]["reason"], "governance_shadow_route")
        self.assertEqual(len(em.inject_calls), 1)
        self.assertEqual(str(em.inject_calls[0].get("label")), "agency_blocked")

    async def test_execute_relay_message_success(self):
        seen = {}

        async def dispatcher(target: str, content: str, relay_from: str | None):
            seen["target"] = target
            seen["content"] = content
            seen["relay_from"] = relay_from
            return {"success": True}

        em = _FakeEmotionState()
        res = await actuation.execute_actuation(
            "relay_message",
            "alice:bob:Please call me back",
            emotion_state=em,
            message_dispatcher=dispatcher,
        )
        self.assertTrue(res["success"])
        self.assertEqual(seen["relay_from"], "alice")
        self.assertEqual(seen["target"], "bob")
        self.assertEqual(seen["content"], "Please call me back")

    async def test_send_imessage_non_darwin(self):
        with patch.object(actuation.platform, "system", return_value="Linux"), patch.object(
            actuation.settings, "IMESSAGE_HOST_BRIDGE_URL", ""
        ):
            res = await actuation.send_imessage("+12145551212", "ping")
        self.assertFalse(res["success"])
        self.assertEqual(res["reason"], "unsupported_platform")

    async def test_send_imessage_non_darwin_uses_host_bridge_when_configured(self):
        async def fake_bridge(*, bridge_url, target, content, sender_account):
            return {
                "success": True,
                "transport": "imessage",
                "bridge_url": bridge_url,
                "target": target,
                "content_chars": len(content),
            }

        with patch.object(actuation.platform, "system", return_value="Linux"), patch.object(
            actuation.settings, "IMESSAGE_HOST_BRIDGE_URL", "http://host.docker.internal:8765"
        ), patch.object(
            actuation, "_send_imessage_via_host_bridge", new=fake_bridge
        ):
            res = await actuation.send_imessage("+12145551212", "ping")
        self.assertTrue(res["success"])
        self.assertEqual(res["target"], "+12145551212")

    async def test_send_imessage_bridge_unavailable(self):
        async def fake_to_thread(func):
            raise URLError("connection refused")

        with patch.object(actuation.platform, "system", return_value="Linux"), patch.object(
            actuation.settings, "IMESSAGE_HOST_BRIDGE_URL", "http://host.docker.internal:8765"
        ), patch.object(actuation.asyncio, "to_thread", new=fake_to_thread):
            res = await actuation.send_imessage("+12145551212", "ping")
        self.assertFalse(res["success"])
        self.assertEqual(res["reason"], "bridge_unavailable")

    def test_parse_send_message_tag(self):
        tags = actuation.parse_actuation_tags("hi [ACTUATE:send_message:operator:hello]")
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["action"], "send_message")
        self.assertEqual(tags[0]["param"], "operator:hello")


if __name__ == "__main__":
    unittest.main()
