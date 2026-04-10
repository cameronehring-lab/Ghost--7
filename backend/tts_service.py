import hashlib
import json
import logging
import os
import re
from typing import Any, Optional

import httpx

from config import settings
import tts_local_piper
import tts_local_pyttsx3

logger = logging.getLogger("omega.tts_service")


class ProviderConfigurationError(RuntimeError):
    """Raised when provider configuration is intentionally missing."""


class TTSService:
    def __init__(self):
        self.cache_dir = settings.TTS_CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
        self.client = httpx.AsyncClient(timeout=30.0)

    def _clean_text_for_speech(self, text: str) -> str:
        """Strip markdown and special characters that shouldn't be vocalized."""
        t = str(text or "").strip()
        if not t:
            return ""
        # Strip common markdown: *italics*, **bold**, _underline_, # headers, ~strikethrough~, > quotes, `code`
        t = re.sub(r"[\*_#~`>]", " ", t)
        # Strip [links](urls) but keep the link text [text]
        t = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", t)
        # Strip standalone brackets
        t = re.sub(r"[\[\]]", " ", t)
        # Normalize whitespace
        return re.sub(r"\s+", " ", t).strip()

    async def get_audio(self, text: str, provider: Optional[str] = None) -> Optional[str]:
        """
        Generate audio for text and return the local cache path.
        Returns None when TTS is disabled, provider is browser mode, or all providers fail.
        """
        if not settings.TTS_ENABLED:
            return None

        text = self._clean_text_for_speech(text)
        if not text:
            return None

        requested_provider = self._normalize_provider(provider or settings.TTS_PROVIDER)
        if requested_provider == "browser":
            logger.info("TTS provider is 'browser'; backend synthesis skipped.")
            return None

        provider_chain = self._provider_chain(requested_provider)
        for effective_provider in provider_chain:
            ext = ".mp3" if effective_provider in {"elevenlabs", "openai"} else ".wav"
            identity = self._voice_identity(effective_provider)
            cache_path = self._cache_path(
                text=text,
                effective_provider=effective_provider,
                extension=ext,
                identity=identity,
            )
            if os.path.exists(cache_path):
                logger.info("TTS cache hit [%s] for text: %s...", effective_provider, text[:30])
                return cache_path

            try:
                await self._generate_with_provider(effective_provider, text, cache_path)
                if os.path.exists(cache_path):
                    logger.info("TTS generated via %s: %s", effective_provider, cache_path)
                    return cache_path
                raise RuntimeError(f"TTS provider '{effective_provider}' did not produce output")
            except Exception as exc:
                self._log_provider_failure(effective_provider, exc)
                continue

        logger.warning("All TTS providers failed for request provider='%s'", requested_provider)
        return None


    def _normalize_provider(self, provider: str) -> str:
        value = str(provider or "").strip().lower()
        if value in {"elevenlabs", "openai", "local", "browser"}:
            return value
        logger.warning("Unknown TTS provider '%s'; defaulting to local fallback chain.", provider)
        return "local"

    def _local_engine_chain(self) -> list[str]:
        preferred = str(settings.LOCAL_TTS_ENGINE or "piper").strip().lower()
        if preferred == "pyttsx3":
            return ["local_pyttsx3", "local_piper"]
        return ["local_piper", "local_pyttsx3"]

    def _provider_chain(self, requested_provider: str) -> list[str]:
        local_chain = self._local_engine_chain()
        if requested_provider == "elevenlabs":
            return ["elevenlabs", *local_chain]
        if requested_provider == "openai":
            return ["openai", *local_chain]
        if requested_provider == "local":
            return local_chain
        return []

    def _voice_identity(self, effective_provider: str) -> dict[str, Any]:
        if effective_provider == "elevenlabs":
            return {
                "provider": "elevenlabs",
                "voice_id": settings.ELEVENLABS_VOICE_ID or "default",
                "model_id": "eleven_monolingual_v1",
            }
        if effective_provider == "openai":
            return {
                "provider": "openai",
                "voice_id": "alloy",
                "model_id": "tts-1",
            }
        if effective_provider == "local_piper":
            return {
                "provider": "local",
                "engine": "piper",
                "model_id": settings.LOCAL_TTS_MODEL_ID,
                "rate": float(settings.LOCAL_TTS_RATE),
                "volume": float(settings.LOCAL_TTS_VOLUME),
                "auto_download": bool(settings.LOCAL_TTS_AUTO_DOWNLOAD),
            }
        return {
            "provider": "local",
            "engine": "pyttsx3",
            "voice_id": settings.LOCAL_TTS_VOICE_ID or "",
            "rate": float(settings.LOCAL_TTS_RATE),
            "volume": float(settings.LOCAL_TTS_VOLUME),
        }

    def _cache_path(
        self,
        text: str,
        effective_provider: str,
        extension: str,
        identity: dict[str, Any],
    ) -> str:
        payload = json.dumps(
            {
                "text": text,
                "effective_provider": effective_provider,
                "identity": identity,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        text_hash = hashlib.md5(payload.encode("utf-8")).hexdigest()
        safe_provider = effective_provider.replace("-", "_")
        return os.path.join(self.cache_dir, f"{safe_provider}_{text_hash}{extension}")

    async def _generate_with_provider(self, provider: str, text: str, output_path: str) -> None:
        if provider == "elevenlabs":
            await self._generate_elevenlabs(text, output_path)
            return
        if provider == "openai":
            await self._generate_openai(text, output_path)
            return
        if provider == "local_piper":
            await tts_local_piper.synthesize_to_wav_async(
                text=text,
                output_path=output_path,
                model_id=settings.LOCAL_TTS_MODEL_ID,
                model_dir=settings.LOCAL_TTS_MODEL_DIR,
                auto_download=bool(settings.LOCAL_TTS_AUTO_DOWNLOAD),
                rate=float(settings.LOCAL_TTS_RATE),
                volume=float(settings.LOCAL_TTS_VOLUME),
            )
            return
        if provider == "local_pyttsx3":
            await tts_local_pyttsx3.synthesize_to_wav_async(
                text=text,
                output_path=output_path,
                voice_id=settings.LOCAL_TTS_VOICE_ID,
                rate=float(settings.LOCAL_TTS_RATE),
                volume=float(settings.LOCAL_TTS_VOLUME),
            )
            return
        raise RuntimeError(f"Unsupported effective TTS provider: {provider}")

    async def _generate_elevenlabs(self, text: str, output_path: str) -> None:
        if not settings.ELEVENLABS_API_KEY:
            raise ProviderConfigurationError("ELEVENLABS_API_KEY is not set")

        voice_id = settings.ELEVENLABS_VOICE_ID or "pNInz6obpg8nEmeW1Gwd"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": settings.ELEVENLABS_API_KEY,
        }
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }

        response = await self.client.post(url, json=data, headers=headers)
        response.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(response.content)

    async def _generate_openai(self, text: str, output_path: str) -> None:
        if not settings.OPENAI_API_KEY:
            raise ProviderConfigurationError("OPENAI_API_KEY is not set")

        url = "https://api.openai.com/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "tts-1",
            "voice": "alloy",
            "input": text,
        }

        response = await self.client.post(url, json=data, headers=headers)
        response.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(response.content)

    def _log_provider_failure(self, provider: str, exc: Exception) -> None:
        if isinstance(exc, ProviderConfigurationError):
            logger.info("TTS provider '%s' skipped: %s", provider, exc)
            return
        logger.warning("TTS provider '%s' failed: %s", provider, exc)

    async def close(self) -> None:
        await self.client.aclose()


tts_service = TTSService()
