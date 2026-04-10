import subprocess
import unittest
from unittest.mock import patch

import actuation


class ActuationSenderIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_imessage_fails_closed_when_sender_not_configured(self):
        with patch.object(actuation.platform, "system", return_value="Darwin"), patch.object(
            actuation.settings, "IMESSAGE_SENDER_ACCOUNT", ""
        ):
            result = await actuation.send_imessage("+12145551212", "hello")
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "sender_identity_unavailable")

    async def test_send_imessage_uses_configured_sender_account(self):
        captured: dict[str, object] = {}

        def fake_run(cmd, capture_output=True, text=True, timeout=10):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, "", "")

        async def fake_to_thread(func):
            return func()

        with patch.object(actuation.platform, "system", return_value="Darwin"), patch.object(
            actuation.settings, "IMESSAGE_SENDER_ACCOUNT", "ghost@example.com"
        ), patch.object(actuation.subprocess, "run", side_effect=fake_run), patch.object(
            actuation.asyncio, "to_thread", new=fake_to_thread
        ):
            result = await actuation.send_imessage("+12145551212", "hello")

        self.assertTrue(result["success"])
        cmd = captured.get("cmd")
        self.assertIsInstance(cmd, list)
        script = str(cmd[2])  # type: ignore[index]
        self.assertIn('senderAccount to "ghost@example.com"', script)
        self.assertIn("matchedService", script)


if __name__ == "__main__":
    unittest.main()
