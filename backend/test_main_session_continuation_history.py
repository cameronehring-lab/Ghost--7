import unittest
from unittest.mock import AsyncMock, patch

import main


class MainSessionContinuationHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_load_operator_chat_history_uses_thread_for_continuation(self):
        with patch.object(
            main.memory,
            "get_session_metadata",
            new=AsyncMock(return_value={"continuation_parent_session_id": "parent_1"}),
        ), patch.object(
            main.memory,
            "load_thread_history",
            new=AsyncMock(return_value={"messages": [{"role": "user", "content": "inherited"}]}),
        ) as thread_loader, patch.object(
            main.memory,
            "load_session_history",
            new=AsyncMock(return_value=[]),
        ) as session_loader:
            history, used_thread = await main._load_operator_chat_history("child_1")

        self.assertTrue(used_thread)
        self.assertEqual(len(history), 1)
        thread_loader.assert_awaited_once_with("child_1", max_depth=80)
        session_loader.assert_not_awaited()

    async def test_load_operator_chat_history_uses_session_history_when_not_continuation(self):
        with patch.object(
            main.memory,
            "get_session_metadata",
            new=AsyncMock(return_value={"continuation_parent_session_id": None}),
        ), patch.object(
            main.memory,
            "load_thread_history",
            new=AsyncMock(return_value={"messages": [{"role": "user", "content": "wrong"}]}),
        ) as thread_loader, patch.object(
            main.memory,
            "load_session_history",
            new=AsyncMock(return_value=[{"role": "user", "content": "single"}]),
        ) as session_loader:
            history, used_thread = await main._load_operator_chat_history("session_1")

        self.assertFalse(used_thread)
        self.assertEqual(history[0]["content"], "single")
        thread_loader.assert_not_awaited()
        session_loader.assert_awaited_once_with("session_1")


if __name__ == "__main__":
    unittest.main()
