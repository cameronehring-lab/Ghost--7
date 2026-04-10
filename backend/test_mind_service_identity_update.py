import unittest

from mind_service import MindService


class TestMindServiceIdentityUpdate(unittest.IsolatedAsyncioTestCase):
    async def test_protected_key_blocked_with_reason(self):
        svc = MindService(pool=None)
        result = await svc.request_identity_update(
            key="ghost_id",
            value="x",
            requester="ghost_self",
            return_details=True,
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "protected_key")

    async def test_governance_allowlist_block_reason(self):
        svc = MindService(pool=None)
        result = await svc.request_identity_update(
            key="self_model",
            value="v",
            requester="ghost_self",
            governance_policy={"self_mod": {"allowed_key_classes": ["rest_mode_enabled"]}},
            return_details=True,
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "governance_key_not_allowed")

    async def test_success_returns_details_and_bool_compat(self):
        svc = MindService(pool=None)

        async def _ok_update_identity_key(key, value, updated_by="system"):
            return True

        svc.update_identity_key = _ok_update_identity_key  # type: ignore

        detail = await svc.request_identity_update(
            key="communication_style",
            value="concise",
            requester="ghost_self",
            return_details=True,
        )
        self.assertTrue(detail["allowed"])
        self.assertEqual(detail["status"], "updated")
        self.assertEqual(detail["reason"], "ok")

        ok = await svc.request_identity_update(
            key="communication_style",
            value="concise",
            requester="ghost_self",
        )
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
