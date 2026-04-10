import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

import tts_service


def _write_fake_wav(output_path: str) -> None:
    # Minimal bytes; decoder validity is not required for service routing tests.
    with open(output_path, "wb") as f:
        f.write(b"RIFFFAKEWAVE")


def _write_fake_mp3(output_path: str) -> None:
    with open(output_path, "wb") as f:
        f.write(b"ID3FAKEMP3")


class TTSServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.service = tts_service.TTSService()
        self.service.cache_dir = self.tmp.name

    async def asyncTearDown(self) -> None:
        await self.service.close()
        self.tmp.cleanup()

    async def test_elevenlabs_missing_key_falls_back_to_local_piper(self):
        async def fake_local_piper(**kwargs):
            _write_fake_wav(kwargs["output_path"])

        with patch.multiple(
            tts_service.settings,
            TTS_ENABLED=True,
            TTS_PROVIDER="elevenlabs",
            ELEVENLABS_API_KEY="",
            LOCAL_TTS_ENGINE="piper",
            LOCAL_TTS_MODEL_ID="en_US-lessac-medium",
            LOCAL_TTS_MODEL_DIR=self.tmp.name,
            LOCAL_TTS_AUTO_DOWNLOAD=False,
            LOCAL_TTS_RATE=1.0,
            LOCAL_TTS_VOLUME=1.0,
        ):
            with patch.object(
                tts_service.tts_local_piper,
                "synthesize_to_wav_async",
                new=AsyncMock(side_effect=fake_local_piper),
            ) as piper_mock:
                path = await self.service.get_audio("hello from omega")
                self.assertIsNotNone(path)
                self.assertTrue(path.endswith(".wav"))
                self.assertTrue(os.path.exists(path))
                self.assertEqual(piper_mock.await_count, 1)

    async def test_browser_provider_returns_none(self):
        with patch.multiple(
            tts_service.settings,
            TTS_ENABLED=True,
            TTS_PROVIDER="browser",
        ):
            path = await self.service.get_audio("browser mode")
            self.assertIsNone(path)

    def test_clean_text_for_speech_strips_markdown_and_normalizes_whitespace(self):
        cleaned = self.service._clean_text_for_speech("  *_#~`>  whispers   Hello  ")
        self.assertEqual(cleaned, "whispers Hello")

    async def test_cache_key_changes_when_voice_profile_changes(self):
        async def fake_local_piper(**kwargs):
            _write_fake_wav(kwargs["output_path"])

        with patch.multiple(
            tts_service.settings,
            TTS_ENABLED=True,
            TTS_PROVIDER="local",
            LOCAL_TTS_ENGINE="piper",
            LOCAL_TTS_MODEL_ID="en_US-lessac-medium",
            LOCAL_TTS_MODEL_DIR=self.tmp.name,
            LOCAL_TTS_AUTO_DOWNLOAD=False,
            LOCAL_TTS_RATE=1.0,
            LOCAL_TTS_VOLUME=1.0,
        ):
            with patch.object(
                tts_service.tts_local_piper,
                "synthesize_to_wav_async",
                new=AsyncMock(side_effect=fake_local_piper),
            ):
                path_one = await self.service.get_audio("identity profile test")
                self.assertIsNotNone(path_one)

            with patch.object(tts_service.settings, "LOCAL_TTS_RATE", 1.25):
                with patch.object(
                    tts_service.tts_local_piper,
                    "synthesize_to_wav_async",
                    new=AsyncMock(side_effect=fake_local_piper),
                ):
                    path_two = await self.service.get_audio("identity profile test")
                    self.assertIsNotNone(path_two)

            self.assertNotEqual(path_one, path_two)
            self.assertTrue(path_one.endswith(".wav"))
            self.assertTrue(path_two.endswith(".wav"))

    async def test_get_audio_sends_cleaned_text_to_provider(self):
        async def fake_local_piper(**kwargs):
            _write_fake_wav(kwargs["output_path"])

        with patch.multiple(
            tts_service.settings,
            TTS_ENABLED=True,
            TTS_PROVIDER="local",
            LOCAL_TTS_ENGINE="piper",
            LOCAL_TTS_MODEL_ID="en_US-lessac-medium",
            LOCAL_TTS_MODEL_DIR=self.tmp.name,
            LOCAL_TTS_AUTO_DOWNLOAD=False,
            LOCAL_TTS_RATE=1.0,
            LOCAL_TTS_VOLUME=1.0,
        ):
            with patch.object(
                tts_service.tts_local_piper,
                "synthesize_to_wav_async",
                new=AsyncMock(side_effect=fake_local_piper),
            ) as piper_mock:
                path = await self.service.get_audio("*whispers* Hello")
                self.assertIsNotNone(path)
                self.assertEqual(piper_mock.await_count, 1)
                self.assertEqual(piper_mock.await_args.kwargs["text"], "whispers Hello")

    async def test_cache_key_normalizes_markdown_and_plain_equivalents(self):
        async def fake_local_piper(**kwargs):
            _write_fake_wav(kwargs["output_path"])

        with patch.multiple(
            tts_service.settings,
            TTS_ENABLED=True,
            TTS_PROVIDER="local",
            LOCAL_TTS_ENGINE="piper",
            LOCAL_TTS_MODEL_ID="en_US-lessac-medium",
            LOCAL_TTS_MODEL_DIR=self.tmp.name,
            LOCAL_TTS_AUTO_DOWNLOAD=False,
            LOCAL_TTS_RATE=1.0,
            LOCAL_TTS_VOLUME=1.0,
        ):
            with patch.object(
                tts_service.tts_local_piper,
                "synthesize_to_wav_async",
                new=AsyncMock(side_effect=fake_local_piper),
            ) as piper_mock:
                markdown_path = await self.service.get_audio("*whispers* Hello")
                plain_path = await self.service.get_audio("whispers Hello")
                self.assertIsNotNone(markdown_path)
                self.assertEqual(markdown_path, plain_path)
                self.assertEqual(piper_mock.await_count, 1)

    async def test_openai_provider_generates_mp3_when_available(self):
        async def fake_openai(text: str, output_path: str):
            _write_fake_mp3(output_path)

        with patch.multiple(
            tts_service.settings,
            TTS_ENABLED=True,
            TTS_PROVIDER="openai",
            OPENAI_API_KEY="test-key",
            LOCAL_TTS_ENGINE="piper",
        ):
            with patch.object(
                self.service,
                "_generate_openai",
                new=AsyncMock(side_effect=fake_openai),
            ):
                path = await self.service.get_audio("openai path")
                self.assertIsNotNone(path)
                self.assertTrue(path.endswith(".mp3"))
                self.assertTrue(os.path.exists(path))


class GhostSpeechBrowserModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_ghost_speech_returns_400_in_browser_mode(self):
        import main

        with patch.multiple(
            main.settings,
            TTS_ENABLED=True,
            TTS_PROVIDER="browser",
        ):
            with self.assertRaises(HTTPException) as ctx:
                await main.ghost_speech("hello")
            self.assertEqual(ctx.exception.status_code, 400)
