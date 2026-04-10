import unittest

import memory


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


class _FakeConn:
    def __init__(self):
        self.sessions: dict[str, dict[str, object]] = {}

    async def fetchval(self, sql, *args):
        session_id = str(args[0])
        ghost_id = str(args[1])
        metadata = memory._json_obj(args[2])
        if session_id in self.sessions:
            return None
        self.sessions[session_id] = {
            "id": session_id,
            "ghost_id": ghost_id,
            "metadata": metadata,
        }
        return session_id


class MemorySessionBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._old_pool = memory._pool
        self.conn = _FakeConn()
        memory._pool = _FakePool(self.conn)

    async def asyncTearDown(self):
        memory._pool = self._old_pool

    async def test_ensure_session_creates_specific_session_id_once(self):
        created = await memory.ensure_session("custom_session", metadata={"channel": "operator_ui"})
        existing = await memory.ensure_session("custom_session", metadata={"channel": "operator_ui"})

        self.assertTrue(created["created"])
        self.assertFalse(existing["created"])
        self.assertIn("custom_session", self.conn.sessions)
        self.assertEqual(self.conn.sessions["custom_session"]["metadata"], {"channel": "operator_ui"})


if __name__ == "__main__":
    unittest.main()
