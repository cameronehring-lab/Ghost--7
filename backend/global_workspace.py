"""
global_workspace.py
Continuous shared state vector (psi) for cross-subsystem signal integration.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


class GlobalWorkspace:
    """
    Continuous high-dimensional shared state psi.
    All subsystems write signals; generation can read and write back.
    """

    def __init__(
        self,
        *,
        dim: int = 64,
        decay_half_life_seconds: float = 45.0,
        max_abs: float = 4.0,
    ):
        self.dim = max(16, int(dim))
        self.decay_half_life_seconds = max(1.0, float(decay_half_life_seconds))
        self.max_abs = max(0.5, float(max_abs))
        self._psi = np.zeros((self.dim,), dtype=np.float32)
        self._lock = threading.Lock()
        self._source_activity: dict[str, float] = {}

        # Canonical channels occupy stable low-index dimensions.
        self.channel_index: dict[str, int] = {
            "arousal": 0,
            "valence": 1,
            "stress": 2,
            "coherence": 3,
            "anxiety": 4,
            "proprio_pressure": 5,
            "prediction_error_drive": 6,
            "forecast_instability": 7,
            "phi_proxy": 8,
            "structural_cohesion": 9,
            "negative_resonance": 10,
            "agency_impetus": 11,
            "linguistic_crystallization": 12,
            "social_context": 13,
        }

    def _dict_to_vector(self, signal: dict[str, Any]) -> np.ndarray:
        vec = np.zeros((self.dim,), dtype=np.float32)
        for key, value in dict(signal or {}).items():
            idx = self.channel_index.get(str(key))
            if idx is None or idx >= self.dim:
                continue
            try:
                vec[idx] = float(value)
            except Exception:
                continue
        return vec

    def _to_vector(self, signal: Any) -> np.ndarray:
        if signal is None:
            return np.zeros((self.dim,), dtype=np.float32)
        if isinstance(signal, dict):
            return self._dict_to_vector(signal)
        if isinstance(signal, (list, tuple, np.ndarray)):
            arr = np.asarray(signal, dtype=np.float32).flatten()
            if arr.size == 0:
                return np.zeros((self.dim,), dtype=np.float32)
            if arr.size >= self.dim:
                return arr[: self.dim].astype(np.float32)
            out = np.zeros((self.dim,), dtype=np.float32)
            out[: arr.size] = arr
            return out
        return np.zeros((self.dim,), dtype=np.float32)

    def write(self, source: str, signal: Any, weight: float = 1.0) -> dict[str, Any]:
        src = str(source or "unknown")
        w = _clip(float(weight), -4.0, 4.0)
        vec = self._to_vector(signal) * w
        with self._lock:
            self._psi = np.clip(self._psi + vec, -self.max_abs, self.max_abs).astype(np.float32)
            self._source_activity[src] = time.time()
            norm = float(np.linalg.norm(self._psi))
        return {
            "source": src,
            "weight": w,
            "signal_norm": float(np.linalg.norm(vec)),
            "psi_norm": norm,
        }

    def write_named(self, source: str, signal: dict[str, Any], weight: float = 1.0) -> dict[str, Any]:
        return self.write(source=source, signal=signal, weight=weight)

    def read(self) -> np.ndarray:
        with self._lock:
            return self._psi.copy()

    def magnitude(self) -> float:
        with self._lock:
            return float(np.linalg.norm(self._psi))

    def linguistic_magnitude(self) -> float:
        idx = self.channel_index.get("linguistic_crystallization", 12)
        with self._lock:
            if idx >= len(self._psi):
                return 0.0
            return float(abs(self._psi[idx]))

    def decay(self, dt: float) -> None:
        d = max(0.0, float(dt))
        if d <= 0.0:
            return
        factor = float(0.5 ** (d / self.decay_half_life_seconds))
        with self._lock:
            self._psi = (self._psi * factor).astype(np.float32)

    def apply_interactions(self) -> dict[str, float]:
        pred_idx = self.channel_index.get("prediction_error_drive", 6)
        coh_idx = self.channel_index.get("structural_cohesion", 9)
        agency_idx = self.channel_index.get("agency_impetus", 11)
        ling_idx = self.channel_index.get("linguistic_crystallization", 12)

        with self._lock:
            pred = float(max(0.0, self._psi[pred_idx] if pred_idx < self.dim else 0.0))
            agency = float(max(0.0, self._psi[agency_idx] if agency_idx < self.dim else 0.0))

            cohesion_delta = pred * 0.06
            linguistic_delta = agency * 0.05

            if coh_idx < self.dim:
                self._psi[coh_idx] = float(np.clip(self._psi[coh_idx] - cohesion_delta, -self.max_abs, self.max_abs))
            if ling_idx < self.dim:
                self._psi[ling_idx] = float(np.clip(self._psi[ling_idx] + linguistic_delta, -self.max_abs, self.max_abs))

            norm = float(np.linalg.norm(self._psi))

        return {
            "cohesion_delta": float(cohesion_delta),
            "linguistic_delta": float(linguistic_delta),
            "psi_norm": norm,
        }

    def to_prompt_context(self, max_dims: int = 8) -> str:
        limit = max(3, min(int(max_dims), 16))
        with self._lock:
            psi = self._psi.copy()
            activity = dict(self._source_activity)
        now = time.time()

        norm = float(np.linalg.norm(psi))
        if norm < 1e-6:
            return "[GLOBAL_WORKSPACE_STATE]\npsi_norm=0.000\nstate=quiescent"

        order = list(np.argsort(np.abs(psi))[::-1][:limit])
        dominant = [f"d{idx}={float(psi[idx]):.3f}" for idx in order]

        named_view = []
        for key, idx in self.channel_index.items():
            if idx >= len(psi):
                continue
            val = float(psi[idx])
            if abs(val) >= 0.05:
                named_view.append((key, val))
        named_view.sort(key=lambda kv: abs(kv[1]), reverse=True)

        source_view = []
        for src, ts in sorted(activity.items(), key=lambda kv: kv[1], reverse=True)[:5]:
            age = max(0.0, now - float(ts or now))
            source_view.append(f"{src}:{age:.1f}s")

        lines = [
            "[GLOBAL_WORKSPACE_STATE]",
            f"psi_norm={norm:.3f}",
            "dominant_dims=" + ", ".join(dominant),
        ]
        if named_view:
            lines.append(
                "channels="
                + ", ".join(f"{k}:{v:.3f}" for k, v in named_view[:8])
            )
        if source_view:
            lines.append("recent_sources=" + ", ".join(source_view))
        return "\n".join(lines)
