import asyncio
import logging
import threading
import wave
from pathlib import Path
from typing import Optional

from config import settings

try:
    from piper.config import SynthesisConfig
    from piper.download_voices import download_voice
    from piper.voice import PiperVoice

    _PIPER_AVAILABLE = True
    _PIPER_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - import-time platform variability
    SynthesisConfig = None  # type: ignore[assignment]
    download_voice = None  # type: ignore[assignment]
    PiperVoice = None  # type: ignore[assignment]
    _PIPER_AVAILABLE = False
    _PIPER_IMPORT_ERROR = exc

logger = logging.getLogger("omega.tts_local_piper")

_voice_lock = threading.Lock()
_voice_cache: dict[tuple[str, str], "PiperVoice"] = {}


def _normalize_rate(rate: float) -> float:
    safe_rate = max(0.25, min(float(rate or 1.0), 3.0))
    # Piper's length_scale is inverse of common speech-rate multiplier.
    return max(0.25, min(1.0 / safe_rate, 4.0))


def _normalize_volume(volume: float) -> float:
    return max(0.0, min(float(volume or 1.0), 2.0))


def _resolve_model_dir(model_dir: Optional[str]) -> Path:
    root = model_dir or settings.LOCAL_TTS_MODEL_DIR
    path = Path(root).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_model_files(
    model_id: str,
    model_dir: Path,
    auto_download: bool,
) -> tuple[Path, Path]:
    model_path = model_dir / f"{model_id}.onnx"
    config_path = model_dir / f"{model_id}.onnx.json"

    if model_path.exists() and config_path.exists():
        return model_path, config_path

    if auto_download:
        if not _PIPER_AVAILABLE or download_voice is None:
            raise RuntimeError("Piper download support is unavailable")
        logger.info("Downloading Piper voice model '%s' into %s", model_id, model_dir)
        download_voice(model_id, model_dir)

    if not model_path.exists() or not config_path.exists():
        raise FileNotFoundError(
            f"Piper model files not found for '{model_id}' in '{model_dir}'. "
            "Set LOCAL_TTS_AUTO_DOWNLOAD=true or pre-seed model files."
        )

    return model_path, config_path


def _load_voice_locked(model_path: Path, config_path: Path, model_dir: Path) -> "PiperVoice":
    key = (str(model_path), str(config_path))
    voice = _voice_cache.get(key)
    if voice is None:
        if not _PIPER_AVAILABLE or PiperVoice is None:
            detail = f": {_PIPER_IMPORT_ERROR}" if _PIPER_IMPORT_ERROR else ""
            raise RuntimeError(f"Piper is unavailable{detail}")
        voice = PiperVoice.load(
            model_path=model_path,
            config_path=config_path,
            download_dir=model_dir,
        )
        _voice_cache[key] = voice
    return voice


def synthesize_to_wav(
    text: str,
    output_path: str,
    model_id: Optional[str] = None,
    model_dir: Optional[str] = None,
    auto_download: Optional[bool] = None,
    rate: Optional[float] = None,
    volume: Optional[float] = None,
) -> None:
    if not text or not text.strip():
        raise ValueError("Cannot synthesize empty text")

    model_id = (model_id or settings.LOCAL_TTS_MODEL_ID).strip()
    if not model_id:
        raise ValueError("LOCAL_TTS_MODEL_ID is empty")

    local_model_dir = _resolve_model_dir(model_dir)
    allow_download = settings.LOCAL_TTS_AUTO_DOWNLOAD if auto_download is None else bool(auto_download)
    local_rate = settings.LOCAL_TTS_RATE if rate is None else float(rate)
    local_volume = settings.LOCAL_TTS_VOLUME if volume is None else float(volume)

    model_path, config_path = _ensure_model_files(
        model_id=model_id,
        model_dir=local_model_dir,
        auto_download=allow_download,
    )

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with _voice_lock:
        voice = _load_voice_locked(model_path, config_path, local_model_dir)
        syn_config = SynthesisConfig(
            length_scale=_normalize_rate(local_rate),
            volume=_normalize_volume(local_volume),
        )
        with wave.open(str(out_path), "wb") as wav_file:
            voice.synthesize_wav(text, wav_file, syn_config=syn_config)


async def synthesize_to_wav_async(
    text: str,
    output_path: str,
    model_id: Optional[str] = None,
    model_dir: Optional[str] = None,
    auto_download: Optional[bool] = None,
    rate: Optional[float] = None,
    volume: Optional[float] = None,
) -> None:
    await asyncio.to_thread(
        synthesize_to_wav,
        text,
        output_path,
        model_id,
        model_dir,
        auto_download,
        rate,
        volume,
    )
