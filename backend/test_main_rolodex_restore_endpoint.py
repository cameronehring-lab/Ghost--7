import unittest
from unittest.mock import AsyncMock, patch

from starlette.requests import Request

import main


def _fake_request() -> Request:
    scope = {"type": "http", "method": "POST", "path": "/ghost/rolodex/test/restore", "headers": []}
    return Request(scope)


class RolodexRestoreEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_restore_success(self):
        req = _fake_request()
        restored_payload = {"person_key": "operator", "facts_restored": 3, "mode": "restore"}
        with patch.object(main, "_require_operator_or_ops_access", return_value=None), patch.object(
            main.memory, "_pool", object()
        ), patch.object(
            main, "_governance_route", new=AsyncMock(return_value={"route": "allow"})
        ), patch.object(
            main, "_build_mutation_idempotency_key", return_value="idem-restore-1"
        ), patch(
            "mutation_journal.get_mutation_by_idempotency", new=AsyncMock(return_value=None)
        ), patch(
            "person_rolodex.restore_person",
            new=AsyncMock(return_value=restored_payload),
        ), patch(
            "mutation_journal.append_mutation", new=AsyncMock(return_value="idem-restore-1")
        ):
            result = await main.restore_rolodex_person(req, "operator")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["restored"]["facts_restored"], 3)
        self.assertEqual(result["idempotency_key"], "idem-restore-1")


if __name__ == "__main__":
    unittest.main()
