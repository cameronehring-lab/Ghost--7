import unittest
from unittest.mock import AsyncMock, patch

import main


class ChatSessionBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_operator_session_is_ensured(self):
        with (
            patch.object(main.memory, "create_session", new=AsyncMock()) as create_session,
            patch.object(main.memory, "ensure_session", new=AsyncMock(return_value={"session_id": "sess_existing", "created": True})) as ensure_session,
        ):
            session_id, thread_key = await main._prepare_chat_session(
                "sess_existing",
                channel=main.CHANNEL_OPERATOR_UI,
                morpheus_terminal_mode=False,
                ephemeral_contact_channel=False,
            )

        self.assertEqual(session_id, "sess_existing")
        self.assertEqual(thread_key, "")
        create_session.assert_not_awaited()
        ensure_session.assert_awaited_once_with("sess_existing", metadata={"channel": main.CHANNEL_OPERATOR_UI})

    async def test_missing_operator_session_is_created_then_ensured(self):
        with (
            patch.object(main.memory, "create_session", new=AsyncMock(return_value="sess_created")) as create_session,
            patch.object(main.memory, "ensure_session", new=AsyncMock(return_value={"session_id": "sess_created", "created": False})) as ensure_session,
        ):
            session_id, thread_key = await main._prepare_chat_session(
                None,
                channel=main.CHANNEL_OPERATOR_UI,
                morpheus_terminal_mode=False,
                ephemeral_contact_channel=False,
            )

        self.assertEqual(session_id, "sess_created")
        self.assertEqual(thread_key, "")
        create_session.assert_awaited_once_with(metadata={"channel": main.CHANNEL_OPERATOR_UI})
        ensure_session.assert_awaited_once_with("sess_created", metadata={"channel": main.CHANNEL_OPERATOR_UI})

    async def test_ephemeral_contact_channel_uses_thread_key_without_db_session_write(self):
        with (
            patch.object(main.memory, "create_session", new=AsyncMock()) as create_session,
            patch.object(main.memory, "ensure_session", new=AsyncMock()) as ensure_session,
            patch.object(main, "normalize_thread_key", return_value="ghost_thread_1") as normalize_thread_key,
        ):
            session_id, thread_key = await main._prepare_chat_session(
                None,
                channel=main.CHANNEL_GHOST_CONTACT,
                morpheus_terminal_mode=False,
                ephemeral_contact_channel=True,
            )

        self.assertEqual(session_id, "ghost_thread_1")
        self.assertEqual(thread_key, "ghost_thread_1")
        normalize_thread_key.assert_called_once()
        create_session.assert_not_awaited()
        ensure_session.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
