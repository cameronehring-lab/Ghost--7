import unittest
from unittest.mock import AsyncMock, patch

from starlette.requests import Request

import main
from models import RolodexContactHandleRequest


def _fake_request() -> Request:
    scope = {"type": "http", "method": "PATCH", "path": "/ghost/rolodex/test/contact-handle", "headers": []}
    return Request(scope)


class RolodexContactHandleEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_patch_contact_handle_success(self):
        req = _fake_request()
        payload = RolodexContactHandleRequest(contact_handle="+1 (214) 555-1212")
        updated_person = {
            "person_key": "cameron",
            "display_name": "Cameron",
            "contact_handle": "+12145551212",
            "updated_at": 123.0,
        }
        with patch.object(main, "_require_operator_or_ops_access", return_value=None), patch.object(
            main.memory, "_pool", object()
        ), patch.object(
            main, "_governance_route", new=AsyncMock(return_value={"route": "allow"})
        ), patch.object(
            main, "_build_mutation_idempotency_key", return_value="idem-1"
        ), patch(
            "mutation_journal.get_mutation_by_idempotency", new=AsyncMock(return_value=None)
        ), patch(
            "mutation_journal.append_mutation", new=AsyncMock(return_value="idem-1")
        ), patch(
            "person_rolodex.update_person_contact_handle",
            new=AsyncMock(return_value=updated_person),
        ):
            result = await main.patch_rolodex_person_contact_handle(req, "cameron", payload)
        self.assertEqual(result["person"]["contact_handle"], "+12145551212")
        self.assertEqual(result["idempotency_key"], "idem-1")

    async def test_patch_contact_handle_shadow_route(self):
        req = _fake_request()
        payload = RolodexContactHandleRequest(contact_handle="test@example.com")
        with patch.object(main, "_require_operator_or_ops_access", return_value=None), patch.object(
            main.memory, "_pool", object()
        ), patch.object(
            main, "_governance_route", new=AsyncMock(return_value={"route": "shadow-route"})
        ), patch.object(
            main, "_build_mutation_idempotency_key", return_value="idem-2"
        ), patch(
            "mutation_journal.get_mutation_by_idempotency", new=AsyncMock(return_value=None)
        ), patch(
            "mutation_journal.append_mutation", new=AsyncMock(return_value="idem-2")
        ):
            result = await main.patch_rolodex_person_contact_handle(req, "cameron", payload)
        self.assertEqual(result["status"], "shadow_route")
        self.assertEqual(result["idempotency_key"], "idem-2")


if __name__ == "__main__":
    unittest.main()
