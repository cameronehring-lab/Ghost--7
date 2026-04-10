import json
import unittest

import entity_store


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


class _Conn:
    def __init__(self, *, active_person_keys=None, alias_map=None):
        self.active_person_keys = set(active_person_keys or [])
        self.alias_map = dict(alias_map or {})
        self.exec_calls = []

    async def fetchval(self, query, *args):
        q = str(query or "").lower()
        if "from person_rolodex" in q:
            target_key = str(args[1] if len(args) > 1 else "")
            return target_key if target_key in self.active_person_keys else None
        if "from entity_aliases" in q:
            alias_key = str(args[1] if len(args) > 1 else "")
            return self.alias_map.get(alias_key)
        return None

    async def execute(self, query, *args):
        self.exec_calls.append((str(query), tuple(args)))
        return "INSERT 0 1"


class EntityStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_upsert_idea_entity_assoc_rejects_unresolved_person_target(self):
        pool = _Pool(_Conn(active_person_keys={"operator"}))
        ok = await entity_store.upsert_idea_entity_assoc(
            pool,
            ghost_id="omega-7",
            concept_key="continuity",
            target_type="person",
            target_key="missing_person",
            confidence=0.7,
            source="test",
            metadata={},
        )
        self.assertFalse(ok)
        self.assertEqual(len(pool._conn.exec_calls), 0)

    async def test_upsert_idea_entity_assoc_remaps_legacy_operator_key(self):
        conn = _Conn(active_person_keys={"operator"})
        pool = _Pool(conn)
        ok = await entity_store.upsert_idea_entity_assoc(
            pool,
            ghost_id="omega-7",
            concept_key="continuity",
            target_type="person",
            target_key="omega-7",
            confidence=0.7,
            source="test",
            metadata={},
        )
        self.assertTrue(ok)
        self.assertEqual(len(conn.exec_calls), 1)
        _query, params = conn.exec_calls[0]
        self.assertEqual(str(params[3]), "operator")
        metadata = json.loads(str(params[6]))
        resolution = metadata.get("target_resolution") or {}
        self.assertEqual(str(resolution.get("resolution")), "legacy_operator_remap")
        self.assertEqual(str(resolution.get("resolved_target_key")), "operator")


if __name__ == "__main__":
    unittest.main()
