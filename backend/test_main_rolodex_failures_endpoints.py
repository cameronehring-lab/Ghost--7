import unittest
from unittest.mock import AsyncMock, patch

from starlette.requests import Request

import main


def _fake_request(path: str) -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "headers": []})


class RolodexFailuresEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_failures_returns_entries(self):
        req = _fake_request("/ghost/rolodex/failures")
        rows = [{"id": 1, "role": "user", "source": "ingest_message"}]
        with patch.object(main, "_require_ops_access", return_value=None), patch.object(
            main.memory, "_pool", object()
        ), patch(
            "person_rolodex.list_ingest_failures",
            new=AsyncMock(return_value=rows),
        ):
            result = await main.get_rolodex_failures(req, limit=25, unresolved_only=True)
        self.assertEqual(result["count"], 1)
        self.assertTrue(result["unresolved_only"])
        self.assertEqual(result["entries"][0]["id"], 1)

    async def test_retry_failures_runs_reprocessor(self):
        req = _fake_request("/ghost/rolodex/retry-failures")
        payload = {"ok": True, "retried": 2, "recovered": 1, "still_failed": 1, "details": []}
        with patch.object(main, "_require_ops_access", return_value=None), patch.object(
            main.memory, "_pool", object()
        ), patch(
            "person_rolodex.retry_ingest_failures",
            new=AsyncMock(return_value=payload),
        ):
            result = await main.post_rolodex_retry_failures(req, limit=20)
        self.assertEqual(result["retried"], 2)
        self.assertEqual(result["recovered"], 1)


if __name__ == "__main__":
    unittest.main()
