import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

import main


def _fake_request(path: str) -> Request:
    scope = {"type": "http", "method": "POST", "path": path, "headers": []}
    return Request(scope)


class MainSessionResumeEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_sessions_uses_operator_channel_defaults(self):
        expected = [
            {
                "session_id": "abc",
                "started_at": 1773400100.0,
                "ended_at": 1773400200.0,
                "summary": "Conversation summary",
                "message_count": 4,
                "channel": "operator_ui",
                "resumable": True,
                "continuation_parent_session_id": None,
                "continuation_root_session_id": None,
                "resumed_at": None,
            }
        ]
        loader = AsyncMock(return_value=expected)
        with patch.object(main.memory, "load_sessions_for_channel", new=loader):
            payload = await main.get_sessions()

        self.assertEqual(payload["sessions"], expected)
        loader.assert_awaited_once_with(
            limit=30,
            channel=main.CHANNEL_OPERATOR_UI,
            ghost_id=main.settings.GHOST_ID,
            resumable_only=False,
        )

    async def test_get_session_thread_returns_lineage_and_messages(self):
        thread_payload = {
            "session_id": "child_1",
            "lineage": [{"session_id": "root"}, {"session_id": "child_1"}],
            "messages": [{"role": "user", "content": "hello", "timestamp": 1.0}],
            "cycle_detected": False,
            "truncated": False,
            "found": True,
        }
        with patch.object(main.memory, "load_thread_history", new=AsyncMock(return_value=thread_payload)):
            result = await main.get_session_thread("child_1")

        self.assertEqual(result["session_id"], "child_1")
        self.assertEqual(len(result["lineage"]), 2)
        self.assertEqual(len(result["messages"]), 1)
        self.assertFalse(result["cycle_detected"])
        self.assertFalse(result["truncated"])

    async def test_get_session_thread_404_when_not_found(self):
        with patch.object(
            main.memory,
            "load_thread_history",
            new=AsyncMock(return_value={"found": False, "lineage": [], "messages": []}),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await main.get_session_thread("missing")
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_resume_endpoint_success(self):
        req = _fake_request("/ghost/sessions/old_1/resume")
        resume_result = {
            "ok": True,
            "session_id": "child_9",
            "continuation_parent_session_id": "old_1",
            "continuation_root_session_id": "root_1",
            "resumed_at": 1773400000.5,
            "channel": "operator_ui",
            "binding_inherited": True,
        }
        with patch.object(main, "_require_operator_or_ops_access", return_value=None), patch.object(
            main.memory, "resume_operator_session", new=AsyncMock(return_value=resume_result)
        ):
            payload = await main.resume_session("old_1", req)

        self.assertEqual(payload["session_id"], "child_9")
        self.assertEqual(payload["continuation_parent_session_id"], "old_1")
        self.assertEqual(payload["continuation_root_session_id"], "root_1")
        self.assertEqual(payload["channel"], "operator_ui")
        self.assertTrue(payload["binding_inherited"])

    async def test_resume_endpoint_rejects_non_resumable_channel(self):
        req = _fake_request("/ghost/sessions/imessage_1/resume")
        with patch.object(main, "_require_operator_or_ops_access", return_value=None), patch.object(
            main.memory,
            "resume_operator_session",
            new=AsyncMock(return_value={"ok": False, "reason": "non_resumable_channel"}),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await main.resume_session("imessage_1", req)
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_resume_endpoint_rejects_active_parent(self):
        req = _fake_request("/ghost/sessions/open_1/resume")
        with patch.object(main, "_require_operator_or_ops_access", return_value=None), patch.object(
            main.memory,
            "resume_operator_session",
            new=AsyncMock(return_value={"ok": False, "reason": "session_not_closed"}),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await main.resume_session("open_1", req)
        self.assertEqual(ctx.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
