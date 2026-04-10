import unittest

import person_rolodex


class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def transaction(self):
        return _Txn()

    async def fetchrow(self, sql, *_args):
        if "UPDATE person_rolodex" in sql:
            return {"person_key": "operator", "display_name": "Operator"}
        return None

    async def execute(self, sql, *_args):
        if "UPDATE person_memory_facts" in sql:
            return "UPDATE 4"
        return "UPDATE 0"


class _Acquire:
    def __init__(self):
        self.conn = _Conn()

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def acquire(self):
        return _Acquire()


class RolodexRestoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_restore_person_returns_counts(self):
        result = await person_rolodex.restore_person(_Pool(), "omega-7", "operator")
        self.assertIsNotNone(result)
        self.assertEqual(result["person_key"], "operator")
        self.assertEqual(result["facts_restored"], 4)
        self.assertEqual(result["mode"], "restore")


if __name__ == "__main__":
    unittest.main()
