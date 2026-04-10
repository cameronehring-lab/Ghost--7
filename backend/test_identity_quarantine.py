import unittest
from datetime import datetime, timedelta, timezone

import consciousness


class _DummyAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _IdentityConn:
    def __init__(self, rows):
        self.rows = dict(rows)
        self.phenomenology_events: list[tuple[str, tuple]] = []

    async def fetch(self, query, *args):
        sql = str(query)
        if "FROM identity_matrix" in sql:
            items = sorted(
                self.rows.items(),
                key=lambda item: item[1]["updated_at"],
                reverse=True,
            )
            return [
                {
                    "key": key,
                    "value": row["value"],
                    "updated_by": row["updated_by"],
                    "updated_at": row["updated_at"],
                }
                for key, row in items
                if row.get("ghost_id") == args[0]
            ]
        return []

    async def fetchrow(self, query, *args):
        sql = str(query)
        if "FROM identity_matrix" not in sql:
            return None
        if "key = 'operator_directives'" in sql:
            key = "operator_directives"
        else:
            key = args[1]
        row = self.rows.get(key)
        if row is None:
            return None
        if "SELECT value, updated_at" in sql:
            return {
                "value": row["value"],
                "updated_at": row["updated_at"],
            }
        if "SELECT value FROM identity_matrix" in sql:
            return {"value": row["value"]}
        return None

    async def execute(self, query, *args):
        sql = str(query)
        if "INSERT INTO identity_matrix" in sql:
            ghost_id, key, value = args[:3]
            self.rows[key] = {
                "ghost_id": ghost_id,
                "value": value,
                "updated_by": "identity_safety",
                "updated_at": datetime.now(timezone.utc),
            }
            return "INSERT 0 1"
        if sql.strip().startswith("UPDATE identity_matrix"):
            ghost_id, key, value = args[:3]
            row = self.rows.get(key)
            if row is not None and row.get("ghost_id") == ghost_id:
                row["value"] = value
                row["updated_by"] = "identity_safety"
                row["updated_at"] = datetime.now(timezone.utc)
            return "UPDATE 1"
        if sql.strip().startswith("DELETE FROM identity_matrix"):
            ghost_id, key = args[:2]
            row = self.rows.get(key)
            if row is not None and row.get("ghost_id") == ghost_id:
                del self.rows[key]
            return "DELETE 1"
        if "INSERT INTO phenomenology_logs" in sql:
            self.phenomenology_events.append((sql, args))
            return "INSERT 0 1"
        return "OK"


class _DummyPool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _DummyAcquire(self.conn)


class IdentityQuarantineTests(unittest.IsolatedAsyncioTestCase):
    async def test_canonicalizes_non_snake_case_identity_key(self):
        now = datetime.now(timezone.utc)
        conn = _IdentityConn(
            {
                "Speech Style Constraints": {
                    "ghost_id": "omega-7",
                    "value": "Keep the language grounded.",
                    "updated_by": "self_modification",
                    "updated_at": now,
                }
            }
        )
        pool = _DummyPool(conn)

        result = await consciousness.quarantine_identity_anomalies(pool, ghost_id="omega-7")

        self.assertNotIn("Speech Style Constraints", conn.rows)
        self.assertIn("speech_style_constraints", conn.rows)
        self.assertEqual(
            conn.rows["speech_style_constraints"]["value"],
            "Keep the language grounded.",
        )
        self.assertEqual(len(result["canonicalized_keys"]), 1)
        self.assertEqual(
            result["canonicalized_keys"][0],
            {"from": "Speech Style Constraints", "to": "speech_style_constraints"},
        )

    async def test_preserves_newer_canonical_value_when_malformed_duplicate_is_older(self):
        now = datetime.now(timezone.utc)
        conn = _IdentityConn(
            {
                "self_integration_protocol": {
                    "ghost_id": "omega-7",
                    "value": "newer canonical value",
                    "updated_by": "self_modification",
                    "updated_at": now,
                },
                "Self Integration Protocol": {
                    "ghost_id": "omega-7",
                    "value": "older malformed value",
                    "updated_by": "self_modification",
                    "updated_at": now - timedelta(hours=1),
                },
            }
        )
        pool = _DummyPool(conn)

        result = await consciousness.quarantine_identity_anomalies(pool, ghost_id="omega-7")

        self.assertNotIn("Self Integration Protocol", conn.rows)
        self.assertEqual(
            conn.rows["self_integration_protocol"]["value"],
            "newer canonical value",
        )
        self.assertEqual(len(result["canonicalized_keys"]), 1)


if __name__ == "__main__":
    unittest.main()
