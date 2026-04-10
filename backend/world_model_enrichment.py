"""
Compatibility shim for `world_model_enrichment`.

Loads the bytecode-only implementation from `__pycache__` and re-exports its
public API. Adds a narrow duplicate-key guard so retro enrichment is idempotent.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from importlib.machinery import SourcelessFileLoader
from pathlib import Path
from typing import Any

logger = logging.getLogger("omega.world_model_enrichment")


def _candidate_bytecode_paths() -> list[Path]:
    cache_dir = Path(__file__).resolve().parent / "__pycache__"
    tag = f"cpython-{sys.version_info.major}{sys.version_info.minor}"
    preferred_legacy = cache_dir / f"world_model_enrichment_legacy.{tag}.pyc"
    preferred = cache_dir / f"world_model_enrichment.{tag}.pyc"
    candidates: list[Path] = [preferred_legacy, preferred]
    candidates.extend(sorted(cache_dir.glob("world_model_enrichment_legacy.cpython-*.pyc")))
    candidates.extend(sorted(cache_dir.glob("world_model_enrichment.cpython-*.pyc")))
    unique: list[Path] = []
    for path in candidates:
        if path.exists() and path not in unique:
            unique.append(path)
    return unique


def _load_legacy_module() -> Any:
    errors: list[str] = []
    for path in _candidate_bytecode_paths():
        try:
            loader = SourcelessFileLoader("_world_model_enrichment_legacy", str(path))
            spec = importlib.util.spec_from_loader("_world_model_enrichment_legacy", loader)
            if spec is None:
                continue
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)
            return module
        except Exception as exc:  # pragma: no cover - startup fallback path
            errors.append(f"{path.name}: {exc}")
    details = "; ".join(errors) if errors else "no candidate bytecode files"
    raise ImportError(f"Unable to load legacy world_model_enrichment bytecode ({details})")


_legacy = _load_legacy_module()

_DUPLICATE_HINTS = (
    "duplicated primary key value",
    "duplicate primary key",
    "already exists",
)


def _looks_like_duplicate_error(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return any(hint in text for hint in _DUPLICATE_HINTS)


def retro_enrich_world_model(
    pool: Any,
    ghost_id: str,
    *,
    db_path: str | None = None,
    max_rows: int = 2000,
) -> dict[str, Any]:
    try:
        result = _legacy.retro_enrich_world_model(
            pool,
            ghost_id,
            db_path=db_path,
            max_rows=max_rows,
        )
    except Exception as exc:
        if not _looks_like_duplicate_error(exc):
            raise
        logger.warning("Retro enrichment duplicate key suppressed: %s", exc)
        return {
            "ok": True,
            "duplicate_suppressed": True,
            "warnings": [f"duplicate key suppressed: {exc}"],
            "error": None,
        }

    if isinstance(result, dict):
        err = result.get("error")
        if (not result.get("ok")) and _looks_like_duplicate_error(err):
            warnings = list(result.get("warnings") or [])
            warnings.append(f"duplicate key suppressed: {err}")
            result["ok"] = True
            result["error"] = None
            result["warnings"] = warnings
            result["duplicate_suppressed"] = True
    return result


for _name in dir(_legacy):
    if _name.startswith("__") or _name == "retro_enrich_world_model":
        continue
    globals()[_name] = getattr(_legacy, _name)

_public = [name for name in dir(_legacy) if not name.startswith("_")]
if "retro_enrich_world_model" not in _public:
    _public.append("retro_enrich_world_model")
__all__ = _public

