import unittest
from unittest.mock import AsyncMock, patch

import ghost_api


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.candidates = []


class _FakeMindService:
    def __init__(self):
        self._pool = object()


class GhostApiRolodexFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_ghost_stream_reinjects_fetch_data_same_turn(self):
        generator = AsyncMock(
            side_effect=[
                _FakeResponse("Let me check. [ROLODEX:fetch:operator]"),
                _FakeResponse("Operator profile confirms Allen, Texas."),
            ]
        )
        fetched_profile = {
            "person_key": "operator",
            "display_name": "Operator",
            "confidence": 0.8,
            "interaction_count": 9,
            "mention_count": 0,
            "facts": [
                {
                    "fact_type": "location",
                    "fact_value": "Allen, Texas",
                    "confidence": 0.7,
                    "observation_count": 2,
                }
            ],
        }

        with patch.object(ghost_api, "build_system_prompt", return_value="sys"), patch.object(
            ghost_api,
            "_generate_with_retry",
            new=generator,
        ), patch.object(
            ghost_api.settings,
            "TTS_ENABLED",
            False,
        ), patch(
            "person_rolodex.fetch_person_details",
            new=AsyncMock(return_value=fetched_profile),
        ):
            events = []
            async for item in ghost_api.ghost_stream(
                user_message="Do you remember where I live?",
                conversation_history=[],
                somatic={},
                monologues=[],
                mind_service=_FakeMindService(),
            ):
                events.append(item)

        self.assertEqual(generator.await_count, 2)
        rolodex_events = [e for e in events if isinstance(e, dict) and e.get("event") == "rolodex_data"]
        self.assertEqual(len(rolodex_events), 1)
        self.assertEqual(rolodex_events[0].get("person_key"), "operator")

        # Ensure the final visible response came from the reinjected second pass.
        text_output = "".join(e for e in events if isinstance(e, str))
        self.assertIn("Operator profile confirms Allen, Texas.", text_output)
        self.assertNotIn("[ROLODEX:fetch:operator]", text_output)

        # Verify second model call received fetched profile context.
        second_call = generator.await_args_list[1]
        second_contents = second_call.kwargs["contents"]
        self.assertGreaterEqual(len(second_contents), 3)
        followup_text = second_contents[-1].parts[0].text
        self.assertIn("FETCHED ROLODEX DATA", followup_text)
        self.assertIn("Allen, Texas", followup_text)


if __name__ == "__main__":
    unittest.main()
