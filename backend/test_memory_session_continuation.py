import unittest
from datetime import datetime, timedelta

import memory


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


class _FakeConn:
    def __init__(self):
        t0 = datetime(2026, 3, 13, 11, 0, 0)
        self.ghost_id = "omega-7"
        self.uuid_parent = "123e4567-e89b-12d3-a456-426614174000"
        self.sessions = {
            "root": {
                "id": "root",
                "started_at": t0,
                "ended_at": t0 + timedelta(minutes=2),
                "summary": "Root summary",
                "metadata": {"channel": "operator_ui"},
            },
            "mid": {
                "id": "mid",
                "started_at": t0 + timedelta(minutes=3),
                "ended_at": t0 + timedelta(minutes=7),
                "summary": "Mid summary",
                "metadata": {
                    "channel": "operator_ui",
                    "continuation_parent_session_id": "root",
                    "continuation_root_session_id": "root",
                    "resumed_at": (t0 + timedelta(minutes=3)).timestamp(),
                },
            },
            "leaf": {
                "id": "leaf",
                "started_at": t0 + timedelta(minutes=8),
                "ended_at": t0 + timedelta(minutes=11),
                "summary": "Leaf summary",
                "metadata": {
                    "channel": "operator_ui",
                    "continuation_parent_session_id": "mid",
                    "continuation_root_session_id": "root",
                    "resumed_at": (t0 + timedelta(minutes=8)).timestamp(),
                },
            },
            "cycle_a": {
                "id": "cycle_a",
                "started_at": t0 + timedelta(minutes=12),
                "ended_at": t0 + timedelta(minutes=13),
                "summary": "Cycle A",
                "metadata": {
                    "channel": "operator_ui",
                    "continuation_parent_session_id": "cycle_b",
                },
            },
            "cycle_b": {
                "id": "cycle_b",
                "started_at": t0 + timedelta(minutes=14),
                "ended_at": t0 + timedelta(minutes=15),
                "summary": "Cycle B",
                "metadata": {
                    "channel": "operator_ui",
                    "continuation_parent_session_id": "cycle_a",
                },
            },
            "single": {
                "id": "single",
                "started_at": t0 + timedelta(minutes=16),
                "ended_at": t0 + timedelta(minutes=17),
                "summary": "Single",
                "metadata": {"channel": "operator_ui"},
            },
            "imessage_parent": {
                "id": "imessage_parent",
                "started_at": t0 + timedelta(minutes=18),
                "ended_at": t0 + timedelta(minutes=20),
                "summary": "SMS chat",
                "metadata": {"channel": "imessage"},
            },
            "active_parent": {
                "id": "active_parent",
                "started_at": t0 + timedelta(minutes=21),
                "ended_at": None,
                "summary": None,
                "metadata": {"channel": "operator_ui"},
            },
            self.uuid_parent: {
                "id": self.uuid_parent,
                "started_at": t0 + timedelta(minutes=22),
                "ended_at": t0 + timedelta(minutes=24),
                "summary": "UUID parent",
                "metadata": {"channel": "operator_ui"},
            },
        }
        self.messages = [
            {
                "id": 10,
                "session_id": "root",
                "role": "user",
                "content": "root user",
                "created_at": t0 + timedelta(seconds=1),
                "token_count": 3,
            },
            {
                "id": 11,
                "session_id": "root",
                "role": "model",
                "content": "root model",
                "created_at": t0 + timedelta(seconds=2),
                "token_count": 4,
            },
            {
                "id": 20,
                "session_id": "mid",
                "role": "user",
                "content": "mid user",
                "created_at": t0 + timedelta(minutes=3, seconds=1),
                "token_count": 5,
            },
            {
                "id": 21,
                "session_id": "mid",
                "role": "model",
                "content": "mid model",
                "created_at": t0 + timedelta(minutes=3, seconds=2),
                "token_count": 6,
            },
            {
                "id": 30,
                "session_id": "leaf",
                "role": "user",
                "content": "leaf user",
                "created_at": t0 + timedelta(minutes=8, seconds=2),
                "token_count": 7,
            },
            {
                "id": 31,
                "session_id": "leaf",
                "role": "model",
                "content": "leaf model",
                "created_at": t0 + timedelta(minutes=8, seconds=2),
                "token_count": 8,
            },
        ]
        self._child_count = 0
        self.bindings = {
            "leaf": {"person_key": "operator", "confidence": 0.61},
            self.uuid_parent: {"person_key": "operator", "confidence": 0.72},
        }

    def transaction(self):
        return _Txn()

    async def fetchrow(self, sql, *args):
        q = sql.lower()
        if "from sessions" in q and "where ghost_id = $1 and id = $2" in q:
            ghost_id = str(args[0])
            session_id = str(args[1])
            if ghost_id != self.ghost_id:
                return None
            return self.sessions.get(session_id)
        if "insert into sessions" in q and "returning id" in q:
            self._child_count += 1
            metadata = memory._json_obj(args[1])
            parent_id = str(metadata.get("continuation_parent_session_id") or "").strip()
            if parent_id == self.uuid_parent:
                child_id = "123e4567-e89b-12d3-a456-426614174001"
            else:
                child_id = f"child_{self._child_count}"
            now = datetime(2026, 3, 13, 12, 0, 0) + timedelta(seconds=self._child_count)
            self.sessions[child_id] = {
                "id": child_id,
                "started_at": now,
                "ended_at": None,
                "summary": None,
                "metadata": metadata,
            }
            return {"id": child_id}
        return None

    async def fetch(self, sql, *args):
        q = sql.lower()
        if "from messages" in q and "session_id = any" in q:
            session_ids = set(args[0])
            rows = [m for m in self.messages if str(m["session_id"]) in session_ids]
            rows.sort(key=lambda row: (row["created_at"], int(row["id"])))
            return rows
        if "with filtered_sessions as" in q and "from sessions" in q:
            ghost_id = str(args[0])
            channel = str(args[1]).strip().lower()
            limit = int(args[2])
            if ghost_id != self.ghost_id:
                return []
            rows = []
            for sess in sorted(self.sessions.values(), key=lambda r: r["started_at"], reverse=True):
                metadata = memory._json_obj(sess.get("metadata"))
                sess_channel = memory._session_channel_from_metadata(metadata)
                if sess_channel != channel:
                    continue
                msg_count = sum(1 for m in self.messages if str(m["session_id"]) == str(sess["id"]))
                rows.append(
                    {
                        "id": sess["id"],
                        "started_at": sess["started_at"],
                        "ended_at": sess["ended_at"],
                        "summary": sess["summary"],
                        "metadata": metadata,
                        "msg_count": msg_count,
                    }
                )
                if len(rows) >= limit:
                    break
            return rows
        return []

    async def execute(self, sql, *args):
        q = sql.lower()
        if "insert into person_session_binding" in q and "select ghost_id, $3::uuid" in q:
            parent_session = str(args[1])
            child_session = str(args[2])
            parent_binding = self.bindings.get(parent_session)
            if not parent_binding:
                return "INSERT 0 0"
            self.bindings[child_session] = {
                "person_key": str(parent_binding["person_key"]),
                "confidence": float(parent_binding["confidence"]),
            }
            return "INSERT 0 1"
        return "INSERT 0 0"


class MemoryContinuationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = _FakeConn()
        self.pool = _FakePool(self.conn)

    async def test_thread_history_returns_full_lineage_and_ordered_messages(self):
        payload = await memory.load_thread_history(
            "leaf",
            ghost_id="omega-7",
            pool=self.pool,
            max_depth=32,
        )

        self.assertTrue(payload["found"])
        self.assertEqual([x["session_id"] for x in payload["lineage"]], ["root", "mid", "leaf"])
        self.assertFalse(payload["cycle_detected"])
        self.assertFalse(payload["truncated"])
        self.assertEqual(
            [m["content"] for m in payload["messages"]],
            ["root user", "root model", "mid user", "mid model", "leaf user", "leaf model"],
        )
        self.assertEqual(
            [m["message_id"] for m in payload["messages"] if m["content"].startswith("leaf")],
            [30, 31],
        )

    async def test_thread_history_cycle_guard_prevents_infinite_walk(self):
        payload = await memory.load_thread_history(
            "cycle_a",
            ghost_id="omega-7",
            pool=self.pool,
            max_depth=20,
        )
        self.assertTrue(payload["found"])
        self.assertTrue(payload["cycle_detected"])
        self.assertGreaterEqual(len(payload["lineage"]), 1)

    async def test_thread_history_single_session_without_parent(self):
        payload = await memory.load_thread_history(
            "single",
            ghost_id="omega-7",
            pool=self.pool,
            max_depth=20,
        )
        self.assertTrue(payload["found"])
        self.assertEqual(len(payload["lineage"]), 1)
        self.assertEqual(payload["lineage"][0]["session_id"], "single")
        self.assertFalse(payload["cycle_detected"])

    async def test_resume_operator_session_skips_binding_inheritance_for_non_uuid_parent_ids(self):
        result = await memory.resume_operator_session(
            "leaf",
            ghost_id="omega-7",
            pool=self.pool,
        )

        self.assertTrue(result["ok"])
        child_id = str(result["session_id"])
        self.assertIn(child_id, self.conn.sessions)
        self.assertEqual(result["continuation_parent_session_id"], "leaf")
        self.assertEqual(result["continuation_root_session_id"], "root")
        self.assertEqual(result["channel"], "operator_ui")
        self.assertFalse(result["binding_inherited"])
        self.assertNotIn(child_id, self.conn.bindings)

    async def test_resume_operator_session_inherits_binding_for_uuid_parent_ids(self):
        result = await memory.resume_operator_session(
            self.conn.uuid_parent,
            ghost_id="omega-7",
            pool=self.pool,
        )

        self.assertTrue(result["ok"])
        child_id = str(result["session_id"])
        self.assertEqual(result["continuation_parent_session_id"], self.conn.uuid_parent)
        self.assertTrue(result["binding_inherited"])
        self.assertIn(child_id, self.conn.bindings)
        self.assertEqual(self.conn.bindings[child_id]["person_key"], "operator")

    async def test_resume_rejects_non_resumable_channel(self):
        result = await memory.resume_operator_session(
            "imessage_parent",
            ghost_id="omega-7",
            pool=self.pool,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "non_resumable_channel")

    async def test_resume_rejects_active_parent(self):
        result = await memory.resume_operator_session(
            "active_parent",
            ghost_id="omega-7",
            pool=self.pool,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "session_not_closed")

    async def test_load_sessions_for_channel_sets_resumable_and_lineage_fields(self):
        rows = await memory.load_sessions_for_channel(
            limit=20,
            channel="operator_ui",
            ghost_id="omega-7",
            pool=self.pool,
        )
        self.assertTrue(rows)
        by_id = {row["session_id"]: row for row in rows}
        self.assertIn("leaf", by_id)
        self.assertIn("active_parent", by_id)
        self.assertNotIn("imessage_parent", by_id)
        self.assertTrue(by_id["leaf"]["resumable"])
        self.assertFalse(by_id["active_parent"]["resumable"])
        self.assertEqual(by_id["leaf"]["continuation_parent_session_id"], "mid")
        self.assertEqual(by_id["leaf"]["continuation_root_session_id"], "root")


if __name__ == "__main__":
    unittest.main()
