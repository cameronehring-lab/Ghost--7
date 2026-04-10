import unittest
from unittest.mock import AsyncMock, patch

import person_rolodex


class _Txn:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.txn_entered += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.conn.txn_rolled_back = True
        return False


class _Conn:
    def __init__(self):
        self.txn_entered = 0
        self.txn_rolled_back = False

    def transaction(self):
        return _Txn(self)


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


class RolodexDeadLetterTests(unittest.IsolatedAsyncioTestCase):
    async def test_ingest_message_records_dead_letter_on_failure(self):
        conn = _Conn()
        pool = _Pool(conn)
        session_id = "123e4567-e89b-12d3-a456-426614174000"

        with patch.object(
            person_rolodex,
            "parse_message_signals",
            return_value={
                "speaker_name": None,
                "self_facts": [{"fact_type": "location", "fact_value": "Allen, Texas", "confidence": 0.7}],
                "mentions": [],
            },
        ), patch.object(
            person_rolodex,
            "_resolve_session_person_key",
            new=AsyncMock(return_value=None),
        ), patch.object(
            person_rolodex,
            "_upsert_session_binding",
            new=AsyncMock(return_value=None),
        ), patch.object(
            person_rolodex,
            "_upsert_person_profile",
            new=AsyncMock(return_value=None),
        ), patch.object(
            person_rolodex,
            "_upsert_fact",
            new=AsyncMock(side_effect=RuntimeError("db_write_failed")),
        ), patch.object(
            person_rolodex,
            "_promote_fact_entity",
            new=AsyncMock(return_value=None),
        ), patch.object(
            person_rolodex,
            "_record_ingest_failure",
            new=AsyncMock(return_value=None),
        ) as dead_letter_mock:
            result = await person_rolodex.ingest_message(
                pool,
                message_text="I live in Allen, Texas.",
                session_id=session_id,
                role="user",
                ghost_id="omega-7",
            )

        self.assertFalse(result["ingested"])
        self.assertEqual(result["reason"], "ingest_exception")
        self.assertEqual(conn.txn_entered, 1)
        self.assertTrue(conn.txn_rolled_back)
        dead_letter_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
