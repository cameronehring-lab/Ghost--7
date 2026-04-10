import unittest
from unittest.mock import AsyncMock, patch

import ghost_api


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.candidates = []


class GhostApiTTSTests(unittest.IsolatedAsyncioTestCase):
    async def test_ghost_stream_emits_tts_ready_when_audio_generated(self):
        with patch.object(ghost_api, "build_system_prompt", return_value="sys"), patch.object(
            ghost_api,
            "_generate_with_retry",
            new=AsyncMock(return_value=_FakeResponse("hello world")),
        ), patch.object(
            ghost_api.tts_service,
            "get_audio",
            new=AsyncMock(return_value="/tmp/omega_tts_cache/fake.wav"),
        ), patch.object(ghost_api.settings, "TTS_ENABLED", True):
            events = []
            async for item in ghost_api.ghost_stream(
                user_message="hello",
                conversation_history=[],
                somatic={},
                monologues=[],
                mind_service=None,
            ):
                events.append(item)

        tts_events = [e for e in events if isinstance(e, dict) and e.get("event") == "tts_ready"]
        self.assertEqual(len(tts_events), 1)
        self.assertEqual(tts_events[0].get("url"), "/tts_cache/fake.wav")

