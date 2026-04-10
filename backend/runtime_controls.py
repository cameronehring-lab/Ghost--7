"""
runtime_controls.py
Runtime feature toggles used by diagnostics/ablation tooling.
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from config import settings  # type: ignore


_DEFAULTS: dict[str, bool] = {
    "reactive_governor_enabled": True,
    "predictive_governor_enabled": bool(getattr(settings, "PREDICTIVE_GOVERNOR_ENABLED", True)),
    "rrd2_gate_enabled": True,
    "rrd2_damping_enabled": bool(getattr(settings, "RRD2_DAMPING_ENABLED", True)),
}

_LOCK = Lock()
_FLAGS: dict[str, bool] = dict(_DEFAULTS)


def snapshot() -> dict[str, bool]:
    with _LOCK:
        return dict(_FLAGS)


def get_flag(name: str, default: bool = False) -> bool:
    with _LOCK:
        return bool(_FLAGS.get(str(name), default))


def set_flags(updates: dict[str, Any]) -> dict[str, bool]:
    if not isinstance(updates, dict):
        return snapshot()
    with _LOCK:
        for key, value in updates.items():
            k = str(key or "").strip()
            if not k or k not in _FLAGS:
                continue
            _FLAGS[k] = bool(value)
        return dict(_FLAGS)


def reset_defaults() -> dict[str, bool]:
    with _LOCK:
        _FLAGS.clear()
        _FLAGS.update(_DEFAULTS)
        return dict(_FLAGS)
