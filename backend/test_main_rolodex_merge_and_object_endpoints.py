import unittest
from unittest.mock import AsyncMock, patch

from starlette.requests import Request

import main
from models import RolodexMergeRequest, RolodexObjectBuildRequest


def _fake_request(path: str) -> Request:
    scope = {"type": "http", "method": "POST", "path": path, "headers": []}
    return Request(scope)


class RolodexMergeAndObjectEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_post_rolodex_merge_success(self):
        req = _fake_request("/ghost/rolodex/merge")
        body = RolodexMergeRequest(
            source_person_key="cameron_allen_ehring",
            target_person_key="operator",
            reason="same_operator_identity",
        )
        merge_payload = {
            "ok": True,
            "source_person_key": "cameron_allen_ehring",
            "target_person_key": "operator",
            "target_profile": {"person_key": "operator", "display_name": "Operator"},
            "merged_counts": {"facts": 4, "session_bindings": 2, "person_place": 1, "person_thing": 1, "idea_person_links": 1},
            "source_archived": True,
            "reconcile": {"ok": True, "promoted_places": 1, "promoted_things": 1},
        }
        with patch.object(main, "_require_operator_or_ops_access", return_value=None), patch.object(
            main.memory, "_pool", object()
        ), patch.object(
            main, "_governance_route", new=AsyncMock(return_value={"route": "allow"})
        ), patch.object(
            main, "_build_mutation_idempotency_key", return_value="idem-merge-1"
        ), patch(
            "mutation_journal.get_mutation_by_idempotency", new=AsyncMock(return_value=None)
        ), patch(
            "mutation_journal.append_mutation", new=AsyncMock(return_value="idem-merge-1")
        ), patch(
            "person_rolodex.fetch_person_details", new=AsyncMock(return_value={})
        ), patch(
            "person_rolodex.merge_people", new=AsyncMock(return_value=merge_payload)
        ):
            result = await main.post_rolodex_merge(req, body)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["idempotency_key"], "idem-merge-1")
        self.assertEqual(result["merge"]["target_person_key"], "operator")

    async def test_post_rolodex_merge_shadow_route(self):
        req = _fake_request("/ghost/rolodex/merge")
        body = RolodexMergeRequest(
            source_person_key="cameron_allen_ehring",
            target_person_key="operator",
            reason="same_operator_identity",
        )
        with patch.object(main, "_require_operator_or_ops_access", return_value=None), patch.object(
            main.memory, "_pool", object()
        ), patch.object(
            main, "_governance_route", new=AsyncMock(return_value={"route": "shadow-route"})
        ), patch.object(
            main, "_build_mutation_idempotency_key", return_value="idem-merge-2"
        ), patch(
            "mutation_journal.get_mutation_by_idempotency", new=AsyncMock(return_value=None)
        ), patch(
            "mutation_journal.append_mutation", new=AsyncMock(return_value="idem-merge-2")
        ):
            result = await main.post_rolodex_merge(req, body)

        self.assertEqual(result["status"], "shadow_route")
        self.assertEqual(result["idempotency_key"], "idem-merge-2")

    async def test_post_rolodex_build_object_associates_person(self):
        req = _fake_request("/ghost/rolodex/objects/build")
        body = RolodexObjectBuildRequest(
            object_name="Field Recorder",
            person_key="operator",
            confidence=0.72,
            notes="portable capture rig",
            metadata={"origin": "test"},
        )
        thing_payload = {
            "thing_key": "field_recorder",
            "display_name": "Field Recorder",
            "confidence": 0.72,
            "status": "active",
            "provenance": "rolodex_builder",
        }
        with patch.object(main, "_require_operator_or_ops_access", return_value=None), patch.object(
            main.memory, "_pool", object()
        ), patch.object(
            main, "_governance_route", new=AsyncMock(return_value={"route": "allow"})
        ), patch.object(
            main, "_build_mutation_idempotency_key", return_value="idem-object-1"
        ), patch(
            "mutation_journal.get_mutation_by_idempotency", new=AsyncMock(return_value=None)
        ), patch(
            "mutation_journal.append_mutation", new=AsyncMock(return_value="idem-object-1")
        ), patch(
            "entity_store.upsert_thing", new=AsyncMock(return_value=thing_payload)
        ), patch(
            "entity_store.upsert_person_thing_assoc", new=AsyncMock(return_value=True)
        ):
            result = await main.post_rolodex_build_object(req, body)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["thing_key"], "field_recorder")
        self.assertTrue(result["association_ok"])
        self.assertEqual(result["idempotency_key"], "idem-object-1")


if __name__ == "__main__":
    unittest.main()
