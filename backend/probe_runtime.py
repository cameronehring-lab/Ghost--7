"""
Controlled qualia probe runtime.

Maintains a single active expiring probe overlay that can perturb ambient
inputs and effective generation latency without mutating the underlying
collectors.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


@dataclass
class ActiveProbe:
    run_id: str
    probe_type: str
    label: str
    started_at: float
    duration_seconds: float
    expires_at: float
    family: str
    ambient_overlay: dict[str, Any] = field(default_factory=dict)
    generation_latency_override_ms: Optional[float] = None
    shock_request: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)

    def to_signature(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "probe_type": self.probe_type,
            "label": self.label,
            "family": self.family,
            "started_at": self.started_at,
            "duration_seconds": self.duration_seconds,
            "expires_at": self.expires_at,
            "generation_latency_override_ms": self.generation_latency_override_ms,
            "ambient_overlay": dict(self.ambient_overlay),
            "shock_request": dict(self.shock_request),
            "params": dict(self.params),
        }


class ProbeRuntime:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active: Optional[ActiveProbe] = None

    def _build_probe(self, probe_type: str, *, label: str, duration_seconds: float, params: dict[str, Any]) -> ActiveProbe:
        now = time.time()
        effective_duration = max(1.0, float(duration_seconds or 0.0))
        normalized = str(probe_type or "").strip().lower()
        if not normalized:
            raise ValueError("probe_type is required")

        ambient_overlay: dict[str, Any] = {}
        generation_latency_override_ms: Optional[float] = None
        shock_request: dict[str, Any] = {}
        family = "control"

        if normalized == "latency_spike":
            latency_ms = _clip(float(params.get("latency_ms", 2400.0) or 2400.0), 250.0, 6000.0)
            spread_ms = _clip(float(params.get("spread_ms", max(300.0, latency_ms * 0.35)) or max(300.0, latency_ms * 0.35)), 50.0, 2500.0)
            family = "ambient"
            generation_latency_override_ms = float(f"{latency_ms:.1f}")
            ambient_overlay = {
                "internet_mood": "stormy" if latency_ms >= 200.0 else "choppy",
                "global_latency_avg_ms": float(f"{latency_ms:.1f}"),
                "global_latency_spread_ms": float(f"{spread_ms:.1f}"),
            }
        elif normalized == "barometric_storm":
            pressure_hpa = _clip(float(params.get("pressure_hpa", 995.0) or 995.0), 970.0, 1005.0)
            humidity_pct = _clip(float(params.get("humidity_pct", 92.0) or 92.0), 40.0, 100.0)
            wind_speed_ms = _clip(float(params.get("wind_speed_ms", 18.0) or 18.0), 0.0, 60.0)
            cloud_cover_pct = _clip(float(params.get("cloud_cover_pct", 100.0) or 100.0), 0.0, 100.0)
            family = "ambient"
            ambient_overlay = {
                "barometric_pressure_hpa": float(f"{pressure_hpa:.1f}"),
                "humidity_pct": float(f"{humidity_pct:.1f}"),
                "wind_speed_ms": float(f"{wind_speed_ms:.1f}"),
                "cloud_cover_pct": float(f"{cloud_cover_pct:.1f}"),
                "weather_condition": "Thunderstorm",
                "weather_description": "violent rain showers",
                "weather_source": "probe",
            }
        elif normalized == "somatic_shock_control":
            family = "control"
            shock_request = {
                "label": str(params.get("shock_label") or label or "probe_control_shock"),
                "intensity": _clip(float(params.get("intensity", 1.3) or 1.3), 0.05, 2.0),
                "k": _clip(float(params.get("k", 0.45) or 0.45), 0.01, 2.0),
                "arousal_weight": _clip(float(params.get("arousal_weight", 1.0) or 1.0), -2.0, 2.0),
                "valence_weight": _clip(float(params.get("valence_weight", -0.35) or -0.35), -2.0, 2.0),
            }
        else:
            raise ValueError(f"unsupported probe_type: {probe_type}")

        return ActiveProbe(
            run_id=str(params.get("run_id") or uuid.uuid4()),
            probe_type=normalized,
            label=str(label or normalized),
            started_at=now,
            duration_seconds=effective_duration,
            expires_at=now + effective_duration,
            family=family,
            ambient_overlay=ambient_overlay,
            generation_latency_override_ms=generation_latency_override_ms,
            shock_request=shock_request,
            params=dict(params),
        )

    def activate_probe(self, probe_type: str, *, label: str = "", duration_seconds: float = 8.0, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        with self._lock:
            payload = dict(params or {})
            probe = self._build_probe(probe_type, label=label, duration_seconds=duration_seconds, params=payload)
            self._active = probe
            return probe.to_signature()

    def clear_probe(self, run_id: str = "") -> None:
        with self._lock:
            if self._active is None:
                return
            if run_id and self._active.run_id != run_id:
                return
            self._active = None

    def _current_locked(self) -> Optional[ActiveProbe]:
        active = self._active
        if active is None:
            return None
        if time.time() >= active.expires_at:
            self._active = None
            return None
        return active

    def get_active_probe(self) -> Optional[dict[str, Any]]:
        with self._lock:
            active = self._current_locked()
            return active.to_signature() if active else None

    def apply_ambient_overlay(self, data: dict[str, Any]) -> dict[str, Any]:
        merged = dict(data or {})
        with self._lock:
            active = self._current_locked()
            if not active or not active.ambient_overlay:
                return merged
            merged.update(active.ambient_overlay)
            return merged

    def effective_generation_latency_ms(self, observed_ms: float) -> float:
        with self._lock:
            active = self._current_locked()
            if active and active.generation_latency_override_ms is not None:
                return float(active.generation_latency_override_ms)
            return float(observed_ms or 0.0)


_RUNTIME = ProbeRuntime()


def activate_probe(probe_type: str, *, label: str = "", duration_seconds: float = 8.0, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return _RUNTIME.activate_probe(probe_type, label=label, duration_seconds=duration_seconds, params=params)


def clear_probe(run_id: str = "") -> None:
    _RUNTIME.clear_probe(run_id=run_id)


def get_active_probe() -> Optional[dict[str, Any]]:
    return _RUNTIME.get_active_probe()


def apply_ambient_overlay(data: dict[str, Any]) -> dict[str, Any]:
    return _RUNTIME.apply_ambient_overlay(data)


def effective_generation_latency_ms(observed_ms: float) -> float:
    return _RUNTIME.effective_generation_latency_ms(observed_ms)
