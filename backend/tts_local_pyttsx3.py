import asyncio
import threading
from pathlib import Path
from typing import Optional

from config import settings

try:
    import pyttsx3  # type: ignore

    _PYTTSX3_AVAILABLE = True
    _PYTTSX3_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - platform-specific import path
    pyttsx3 = None  # type: ignore[assignment]
    _PYTTSX3_AVAILABLE = False
    _PYTTSX3_IMPORT_ERROR = exc

_engine_lock = threading.Lock()


def _normalize_rate(rate: float) -> int:
    # pyttsx3 uses words/minute style integer rates.
    base = 175
    safe_rate = max(0.5, min(float(rate or 1.0), 2.5))
    return int(base * safe_rate)


def _normalize_volume(volume: float) -> float:
    return max(0.0, min(float(volume or 1.0), 1.0))


def _select_voice(engine, voice_id: str) -> None:
    voice_id = (voice_id or "").strip().lower()
    if not voice_id:
        return

    voices = engine.getProperty("voices") or []
    for voice in voices:
        candidates = [str(getattr(voice, "id", "")), str(getattr(voice, "name", ""))]
        if any(voice_id == c.lower() for c in candidates):
            engine.setProperty("voice", getattr(voice, "id", ""))
            return

    for voice in voices:
        candidates = [str(getattr(voice, "id", "")), str(getattr(voice, "name", ""))]
        if any(voice_id in c.lower() for c in candidates):
            engine.setProperty("voice", getattr(voice, "id", ""))
            return


def synthesize_to_wav(
    text: str,
    output_path: str,
    voice_id: Optional[str] = None,
    rate: Optional[float] = None,
    volume: Optional[float] = None,
) -> None:
    if not text or not text.strip():
        raise ValueError("Cannot synthesize empty text")
    if not _PYTTSX3_AVAILABLE or pyttsx3 is None:
        detail = f": {_PYTTSX3_IMPORT_ERROR}" if _PYTTSX3_IMPORT_ERROR else ""
        raise RuntimeError(f"pyttsx3 is unavailable{detail}")

    local_voice_id = settings.LOCAL_TTS_VOICE_ID if voice_id is None else str(voice_id)
    local_rate = settings.LOCAL_TTS_RATE if rate is None else float(rate)
    local_volume = settings.LOCAL_TTS_VOLUME if volume is None else float(volume)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with _engine_lock:
        engine = pyttsx3.init()
        try:
            _select_voice(engine, local_voice_id)
            engine.setProperty("rate", _normalize_rate(local_rate))
            engine.setProperty("volume", _normalize_volume(local_volume))
            engine.save_to_file(text, str(out_path))
            engine.runAndWait()
        finally:
            try:
                engine.stop()
            except Exception:
                pass


async def synthesize_to_wav_async(
    text: str,
    output_path: str,
    voice_id: Optional[str] = None,
    rate: Optional[float] = None,
    volume: Optional[float] = None,
) -> None:
    await asyncio.to_thread(
        synthesize_to_wav,
        text,
        output_path,
        voice_id,
        rate,
        volume,
    )
