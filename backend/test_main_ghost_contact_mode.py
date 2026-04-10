import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import main
from imessage_bridge import IMessageBridgeRecord


class _FakeStore:
    def __init__(self):
        self.append_turn = AsyncMock(return_value={})
        self.build_history = AsyncMock(return_value=[{"role": "user", "content": "hello", "timestamp": 1.0}])


class MainGhostContactModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_imessage_ingest_ephemeral_mode_skips_db_persistence(self):
        record = IMessageBridgeRecord(
            rowid=12,
            guid="abc-12",
            text="hello ghost",
            handle="+12145551212",
            service="iMessage",
            raw_date=12345,
        )
        store = _FakeStore()
        queue = asyncio.Queue()
        wake_event = asyncio.Event()

        with patch.object(main.memory, "_pool", object()), patch(
            "person_rolodex.fetch_person_by_contact_handle",
            new=AsyncMock(return_value={"person_key": "cameron", "contact_handle": "+12145551212"}),
        ), patch.object(
            main, "_ghost_contact_ephemeral_enabled", return_value=True
        ), patch.object(
            main, "_ghost_contact_store", return_value=store
        ), patch.object(
            main, "_schedule_ghost_contact_response"
        ) as schedule_mock, patch.object(
            main.memory, "save_message", new=AsyncMock()
        ) as save_mock, patch.object(
            main, "_ensure_imessage_session", new=AsyncMock()
        ) as ensure_session_mock, patch(
            "person_rolodex.ingest_bound_message", new=AsyncMock()
        ) as ingest_mock, patch.object(
            main, "_publish_push_notice", new=AsyncMock()
        ), patch.object(
            main.sys_state, "external_event_queue", queue
        ), patch.object(
            main.sys_state, "ghost_wake_event", wake_event
        ):
            await main._handle_imessage_ingest(record)

        save_mock.assert_not_awaited()
        ensure_session_mock.assert_not_awaited()
        ingest_mock.assert_not_awaited()
        store.append_turn.assert_awaited_once()
        schedule_mock.assert_called_once()
        self.assertTrue(wake_event.is_set())

    async def test_imessage_ingest_unknown_handle_is_ignored(self):
        record = IMessageBridgeRecord(
            rowid=77,
            guid="abc-77",
            text="unknown hello",
            handle="+12145559999",
            service="iMessage",
            raw_date=12345,
        )
        store = _FakeStore()

        with patch.object(main.memory, "_pool", object()), patch(
            "person_rolodex.fetch_person_by_contact_handle",
            new=AsyncMock(return_value=None),
        ), patch.object(
            main, "_ghost_contact_ephemeral_enabled", return_value=True
        ), patch.object(
            main, "_ghost_contact_store", return_value=store
        ), patch.object(
            main, "_schedule_ghost_contact_response"
        ) as schedule_mock:
            await main._handle_imessage_ingest(record)

        store.append_turn.assert_not_awaited()
        schedule_mock.assert_not_called()

    async def test_contact_responder_dispatches_to_same_person_and_records_outbound(self):
        store = _FakeStore()
        store.build_history = AsyncMock(
            return_value=[
                {"role": "model", "content": "[COMPACT_THREAD_SUMMARY]\nEarlier context", "timestamp": 1.0},
                {"role": "user", "content": "hello", "timestamp": 2.0},
            ]
        )
        store.append_turn = AsyncMock(return_value={})

        async def fake_ghost_stream(*args, **kwargs):
            yield "Ghost"
            yield " says hi"

        with patch.object(main, "_ghost_contact_store", return_value=store), patch.object(
            main.memory, "get_monologue_buffer", new=AsyncMock(return_value=[])
        ), patch.object(
            main.memory, "_pool", None
        ), patch.object(
            main.consciousness, "weave_context", new=AsyncMock(return_value=("", []))
        ), patch.object(
            main.consciousness, "load_identity", new=AsyncMock(return_value={})
        ), patch.object(
            main, "ghost_stream", new=fake_ghost_stream
        ), patch.object(
            main, "_dispatch_governed_message",
            new=AsyncMock(return_value={"success": True, "rendered_content": "Ghost: Ghost says hi", "route": {"route": "allow"}}),
        ) as dispatch_mock, patch.object(
            main, "_publish_push_notice", new=AsyncMock()
        ):
            await main._respond_to_ghost_contact_turn(
                thread_key="+12145551212",
                person_key="cameron",
                contact_handle="+12145551212",
                inbound_text="hello",
            )

        dispatch_mock.assert_awaited_once_with("cameron", "Ghost says hi", requested_by="ghost_contact")
        store.append_turn.assert_awaited_once()
        kwargs = store.append_turn.await_args.kwargs
        self.assertEqual(kwargs["thread_key"], "+12145551212")
        self.assertEqual(kwargs["direction"], "outbound")
        self.assertIn("Ghost:", kwargs["text"])


if __name__ == "__main__":
    unittest.main()
