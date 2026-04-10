import unittest
from unittest.mock import AsyncMock, patch

import person_rolodex
from person_rolodex import normalize_contact_handle, normalize_person_key, parse_message_signals


class TestPersonRolodexParsing(unittest.TestCase):
    def test_normalize_person_key(self):
        self.assertEqual(normalize_person_key("Cameron Allen Ehring"), "cameron_allen_ehring")
        self.assertEqual(normalize_person_key("  John-Doe  "), "john_doe")

    def test_extract_self_identification(self):
        signals = parse_message_signals("Hello Ghost, my name is Cameron Allen Ehring.")
        self.assertEqual(signals["speaker_name"], "Cameron Allen Ehring")

    def test_reject_non_name_identification(self):
        signals = parse_message_signals("I am operator.")
        self.assertIsNone(signals["speaker_name"])

    def test_reject_trait_phrase_for_name(self):
        signals = parse_message_signals("I am curious about this architecture.")
        self.assertIsNone(signals["speaker_name"])

    def test_extract_name_when_followed_by_clause(self):
        signals = parse_message_signals("I am Alice and my brother Mark loves coding.")
        self.assertEqual(signals["speaker_name"], "Alice")

    def test_extract_name_stops_before_and_clause(self):
        signals = parse_message_signals("My name is Test Person and my dad John likes philosophy.")
        self.assertEqual(signals["speaker_name"], "Test Person")

    def test_extract_relationship_mentions(self):
        signals = parse_message_signals("My dad John asked me to show him this interface.")
        mentions = signals["mentions"]
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0]["display_name"], "John")
        self.assertEqual(mentions[0]["relation"], "dad")

    def test_extract_extended_relationship_mentions(self):
        signals = parse_message_signals("My girlfriend Sarah said hello.")
        mentions = signals["mentions"]
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0]["display_name"], "Sarah")
        self.assertEqual(mentions[0]["relation"], "girlfriend")

    def test_extract_self_facts(self):
        signals = parse_message_signals("I like deep philosophical writing. I live in Allen, Texas.")
        fact_types = {f["fact_type"] for f in signals["self_facts"]}
        self.assertIn("preference", fact_types)
        self.assertIn("location", fact_types)

    def test_extract_workplace_and_age_and_alias(self):
        signals = parse_message_signals("I work at Google. I'm 28 years old. I go by Cam.")
        by_type = {f["fact_type"]: f["fact_value"] for f in signals["self_facts"]}
        self.assertEqual(by_type.get("occupation"), "Google")
        self.assertEqual(by_type.get("age"), "28")
        self.assertEqual(by_type.get("self_identification"), "Cam")

    def test_occupation_filter_rejects_emotional_phrase(self):
        signals = parse_message_signals("I am an absolute mess right now.")
        occupations = [f for f in signals["self_facts"] if f["fact_type"] == "occupation"]
        self.assertEqual(occupations, [])

    def test_normalize_contact_handle_phone(self):
        self.assertEqual(normalize_contact_handle("(214) 555-1212"), "+12145551212")
        self.assertEqual(normalize_contact_handle("+1 214-555-1212"), "+12145551212")

    def test_normalize_contact_handle_email(self):
        self.assertEqual(normalize_contact_handle("Test.User@Example.COM"), "test.user@example.com")

    def test_location_stops_before_follow_on_clause(self):
        signals = parse_message_signals(
            "My name is Cameron Test. I live in Allen, Texas and I like long-form philosophy."
        )
        loc_values = [f["fact_value"] for f in signals["self_facts"] if f["fact_type"] == "location"]
        self.assertIn("Allen, Texas", loc_values)
        self.assertNotIn("Allen, Texas and I like long-form philosophy", loc_values)


class _DummyAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _IntegrityConn:
    async def fetch(self, query, *args):
        sql = str(query)
        if "FROM person_session_binding b" in sql:
            if "JOIN sessions s ON s.id = b.session_id::text" not in sql:
                raise AssertionError("stale binding query must cast binding session_id to text")
            return []
        if "FROM person_memory_facts f" in sql:
            return []
        if "FROM person_rolodex p" in sql:
            return []
        return []


class _DummyPool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _DummyAcquire(self.conn)


class _Txn:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.txn_entered += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _NoSessionBindingConn:
    def __init__(self):
        self.txn_entered = 0

    def transaction(self):
        return _Txn(self)

    async def execute(self, query, *args):
        raise AssertionError(f"unexpected execute: {query}")

    async def fetchrow(self, query, *args):
        raise AssertionError(f"unexpected fetchrow: {query}")


class TestPersonRolodexIntegrity(unittest.IsolatedAsyncioTestCase):
    async def test_integrity_check_casts_session_binding_uuid_for_sessions_join(self):
        report = await person_rolodex.integrity_check(
            _DummyPool(_IntegrityConn()),
            ghost_id="omega-7",
            include_samples=False,
        )
        self.assertTrue(report["ok"])
        self.assertEqual(report["counts"]["stale_bindings"], 0)

    async def test_ingest_message_skips_session_binding_for_non_uuid_session_ids(self):
        pool = _DummyPool(_NoSessionBindingConn())
        with (
            patch.object(
                person_rolodex,
                "parse_message_signals",
                return_value={"speaker_name": None, "self_facts": [], "mentions": []},
            ),
            patch.object(person_rolodex, "_upsert_person_profile", new=AsyncMock(return_value=None)) as profile_mock,
            patch.object(person_rolodex, "_record_ingest_failure", new=AsyncMock(return_value=None)) as dead_letter_mock,
        ):
            result = await person_rolodex.ingest_message(
                pool,
                message_text="just testing session bootstrap",
                session_id="codex_test_session",
                role="user",
                ghost_id="omega-7",
            )

        self.assertTrue(result["ingested"])
        self.assertEqual(result["speaker_key"], person_rolodex.OPERATOR_FALLBACK_KEY)
        profile_mock.assert_awaited_once()
        dead_letter_mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
