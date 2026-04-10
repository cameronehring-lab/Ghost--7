import unittest
from unittest.mock import patch

from fastapi import HTTPException

import main


class ObserverEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_observer_reports_supports_daily_kind(self):
        fake_rows = [{"json_path": "/tmp/observer_daily_2026-03-10.json"}]
        with patch.object(main.observer_report, "list_report_artifacts", return_value=fake_rows) as mocked:
            payload = await main.list_observer_reports(limit=10, kind="daily")
        mocked.assert_called_once()
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs.get("kind"), "daily")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["kind"], "daily")

    async def test_list_observer_reports_rejects_invalid_kind(self):
        with self.assertRaises(HTTPException) as ctx:
            await main.list_observer_reports(limit=10, kind="weekly")
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
