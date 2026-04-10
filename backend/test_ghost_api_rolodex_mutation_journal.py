import unittest
from unittest.mock import AsyncMock, patch

import ghost_api


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.candidates = []


class _FakeConn:
    def __init__(self):
        self._rows = [
            None,
            {
                "person_key": "operator",
                "display_name": "Operator",
                "interaction_count": 3,
                "mention_count": 1,
                "confidence": 0.9,
                "metadata": {"source": "ghost_agency"},
            },
            None,
            {
                "id": 42,
                "person_key": "operator",
                "fact_type": "location",
                "fact_value": "Allen, Texas",
                "confidence": 0.9,
                "source_role": "ghost",
                "evidence_text": "Ghost-initiated social modeling.",
                "observation_count": 1,
                "metadata": {"source": "ghost_agency"},
            },
        ]

    async def fetchrow(self, *_args, **_kwargs):
        return self._rows.pop(0) if self._rows else None


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self):
        self.conn = _FakeConn()

    def acquire(self):
        return _Acquire(self.conn)


class _FakeMindService:
    def __init__(self):
        self._pool = _FakePool()


class GhostApiRolodexMutationJournalTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_profile_and_set_fact_emit_mutation_journal(self):
        generator = AsyncMock(
            return_value=_FakeResponse(
                "Updating now. [ROLODEX:set_profile:operator:Operator] [ROLODEX:set_fact:operator:location:Allen, Texas]"
            )
        )
        append_mock = AsyncMock(return_value="idem")

        with patch.object(ghost_api, "build_system_prompt", return_value="sys"), patch.object(
            ghost_api,
            "_generate_with_retry",
            new=generator,
        ), patch.object(
            ghost_api.settings,
            "TTS_ENABLED",
            False,
        ), patch(
            "person_rolodex._upsert_person_profile",
            new=AsyncMock(return_value=None),
        ), patch(
            "person_rolodex._upsert_fact",
            new=AsyncMock(return_value=True),
        ), patch(
            "mutation_journal.append_mutation",
            new=append_mock,
        ):
            events = []
            async for item in ghost_api.ghost_stream(
                user_message="Update social model.",
                conversation_history=[],
                somatic={},
                monologues=[],
                mind_service=_FakeMindService(),
            ):
                events.append(item)

        self.assertGreaterEqual(append_mock.await_count, 2)
        emitted_actions = [call.kwargs.get("action") for call in append_mock.await_args_list]
        self.assertIn("set_profile", emitted_actions)
        self.assertIn("set_fact", emitted_actions)
        rolodex_updates = [e for e in events if isinstance(e, dict) and e.get("event") == "rolodex_update"]
        self.assertEqual(len(rolodex_updates), 2)


if __name__ == "__main__":
    unittest.main()
