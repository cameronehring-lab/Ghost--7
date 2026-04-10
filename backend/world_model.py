"""
Compatibility shim for `world_model`.

The source file disappeared from the workspace, but runtime bytecode still exists
under `__pycache__/`. This shim loads the bytecode module and applies a narrow
idempotency patch for duplicate-key upserts.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from functools import wraps
from importlib.machinery import SourcelessFileLoader
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("omega.world_model")


def _candidate_bytecode_paths() -> list[Path]:
    cache_dir = Path(__file__).resolve().parent / "__pycache__"
    tag = f"cpython-{sys.version_info.major}{sys.version_info.minor}"
    preferred_legacy = cache_dir / f"world_model_legacy.{tag}.pyc"
    preferred = cache_dir / f"world_model.{tag}.pyc"
    candidates: list[Path] = [preferred_legacy, preferred]
    candidates.extend(sorted(cache_dir.glob("world_model_legacy.cpython-*.pyc")))
    candidates.extend(sorted(cache_dir.glob("world_model.cpython-*.pyc")))
    unique: list[Path] = []
    for path in candidates:
        if path.exists() and path not in unique:
            unique.append(path)
    return unique


def _load_legacy_module() -> Any:
    errors: list[str] = []
    for path in _candidate_bytecode_paths():
        try:
            loader = SourcelessFileLoader("_world_model_legacy", str(path))
            spec = importlib.util.spec_from_loader("_world_model_legacy", loader)
            if spec is None:
                continue
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)
            return module
        except Exception as exc:  # pragma: no cover - startup fallback path
            errors.append(f"{path.name}: {exc}")
    details = "; ".join(errors) if errors else "no candidate bytecode files"
    raise ImportError(f"Unable to load legacy world_model bytecode ({details})")


_legacy = _load_legacy_module()

_DUPLICATE_HINTS = (
    "duplicated primary key value",
    "duplicate primary key",
    "already exists",
)


def _is_duplicate_key_error(exc: Exception) -> bool:
    text = str(exc).strip().lower()
    return any(hint in text for hint in _DUPLICATE_HINTS)


def _fallback_node_id(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    if args:
        return str(args[0])
    node_id = kwargs.get("node_id")
    return str(node_id) if node_id is not None else ""


def _install_duplicate_safe_upserts() -> None:
    cls = getattr(_legacy, "WorldModel", None)
    if cls is None:
        return

    str_returning = {
        "upsert_belief",
        "upsert_concept",
        "upsert_identity_node",
        "upsert_observation",
        "upsert_somatic_state",
    }
    none_returning = {
        "upsert_precedes",
        "upsert_during",
        "upsert_derived_from",
    }

    for method_name in sorted(str_returning | none_returning):
        method = getattr(cls, method_name, None)
        if not callable(method):
            continue

        @wraps(method)
        def _wrapped(
            self: Any,
            *args: Any,
            __method: Callable[..., Any] = method,
            __name: str = method_name,
            **kwargs: Any,
        ) -> Any:
            try:
                return __method(self, *args, **kwargs)
            except Exception as exc:
                if not _is_duplicate_key_error(exc):
                    raise
                node_id = _fallback_node_id(args, kwargs)
                logger.info(
                    "WorldModel idempotent upsert skip for %s(%s): %s",
                    __name,
                    node_id or "-",
                    exc,
                )
                if __name in str_returning:
                    return node_id
                return None

        setattr(cls, method_name, _wrapped)


_install_duplicate_safe_upserts()

# Re-export public names from the legacy module so existing imports keep working.
for _name in dir(_legacy):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_legacy, _name)

__all__ = [name for name in dir(_legacy) if not name.startswith("_")]
