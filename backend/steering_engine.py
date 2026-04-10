"""
Phase 2 scaffold for activation steering.

This module provides:
  - affective snapshot -> steering vector projection
  - no-op injection contract against an ActivationHandle
  - bounded affective write-back into EmotionState after generation
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from config import settings  # type: ignore

logger = logging.getLogger("omega.steering")


def _clip01(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _clip11(value: Any) -> float:
    try:
        return max(-1.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


@dataclass
class SteeringState:
    vector_dim: int
    target_layer_start: int
    target_layer_end: int
    magnitude: float


class SteeringEngine:
    """
    Deterministic scaffolding for CSC phase progression.
    Projection uses a fixed seeded affine map for reproducibility.
    """

    def __init__(
        self,
        *,
        vector_dim: int,
        base_scale: float,
        pressure_gain: float,
        writeback_enabled: bool,
    ):
        self.vector_dim = max(8, int(vector_dim))
        self.base_scale = max(0.0, float(base_scale))
        self.pressure_gain = max(0.0, float(pressure_gain))
        self.writeback_enabled = bool(writeback_enabled)

        rng = np.random.default_rng(7)
        self._w = rng.normal(0.0, 0.22, size=(5, self.vector_dim)).astype(np.float32)
        self._b = rng.normal(0.0, 0.05, size=(self.vector_dim,)).astype(np.float32)

    def build_vector(
        self,
        emotion_snapshot: dict[str, Any],
        *,
        vector_dim: Optional[int] = None,
    ) -> np.ndarray:
        snap = dict(emotion_snapshot or {})
        x = np.array(
            [
                _clip01(snap.get("arousal", 0.0)),
                (_clip11(snap.get("valence", 0.0)) + 1.0) * 0.5,
                _clip01(snap.get("stress", 0.0)),
                _clip01(snap.get("coherence", 1.0)),
                _clip01(snap.get("anxiety", 0.0)),
            ],
            dtype=np.float32,
        )
        dim = max(8, int(vector_dim or self.vector_dim))
        if dim != self.vector_dim:
            rng = np.random.default_rng(7)
            w = rng.normal(0.0, 0.22, size=(5, dim)).astype(np.float32)
            b = rng.normal(0.0, 0.05, size=(dim,)).astype(np.float32)
        else:
            w = self._w
            b = self._b
        vec = np.matmul(x, w) + b
        norm = float(np.linalg.norm(vec) or 0.0)
        if norm > 1e-8:
            vec = vec / norm
        return vec.astype(np.float32)

    def scaled_vector(self, vector: np.ndarray, pressure: float) -> np.ndarray:
        mag = self.base_scale * (1.0 + (self.pressure_gain * _clip01(pressure)))
        return np.asarray(vector, dtype=np.float32) * float(mag)

    def inject(self, handle: Any, vector: np.ndarray, pressure: float) -> dict[str, Any]:
        mag = self.base_scale * (1.0 + (self.pressure_gain * _clip01(pressure)))
        scaled = self.scaled_vector(vector, pressure)
        n_layers = int(_to_float(getattr(handle, "n_layers", 32), 32))
        start = max(0, int(0.4 * n_layers))
        end = max(start, int(0.7 * n_layers))
        preview = [float(f"{v:.4f}") for v in scaled[: min(6, len(scaled))]]
        return {
            "applied": bool(getattr(handle, "activation_steering_supported", False)),
            "backend": str(getattr(handle, "backend", "local")),
            "model": str(getattr(handle, "model", "")),
            "api_format": str(getattr(handle, "api_format", "")),
            "target_layers": [start, end],
            "magnitude": float(f"{mag:.4f}"),
            "vector_dim": int(len(scaled)),
            "vector_preview": preview,
            "reason": str(getattr(handle, "reason", "phase_2_not_implemented")),
        }

    async def affective_write_back(
        self,
        generated_text: str,
        emotion_state: Any,
        *,
        baseline_snapshot: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not self.writeback_enabled:
            return {"writeback": "disabled"}
        if emotion_state is None or not hasattr(emotion_state, "inject"):
            return {"writeback": "skipped", "reason": "emotion_state_unavailable"}

        predicted = self._classify_text(generated_text)
        baseline = dict(baseline_snapshot or {})
        events: list[str] = []

        base_valence = _clip11(baseline.get("valence", 0.0))
        base_arousal = _clip01(baseline.get("arousal", 0.0))
        base_stress = _clip01(baseline.get("stress", 0.0))
        base_anxiety = _clip01(baseline.get("anxiety", 0.0))
        base_coherence = _clip01(baseline.get("coherence", 1.0))

        if (predicted["valence"] - base_valence) > 0.10:
            ok = await emotion_state.inject(
                "steer_writeback_positive",
                intensity=min(0.45, abs(predicted["valence"] - base_valence)),
                k=0.16,
                arousal_weight=0.25,
                valence_weight=0.70,
            )
            if ok:
                events.append("positive")
        elif (base_valence - predicted["valence"]) > 0.10:
            ok = await emotion_state.inject(
                "steer_writeback_negative",
                intensity=min(0.55, abs(base_valence - predicted["valence"])),
                k=0.18,
                arousal_weight=0.35,
                valence_weight=-0.75,
            )
            if ok:
                events.append("negative")

        if (predicted["arousal"] - base_arousal) > 0.08:
            ok = await emotion_state.inject(
                "steer_writeback_arousal",
                intensity=min(0.5, predicted["arousal"] - base_arousal),
                k=0.22,
                arousal_weight=0.90,
                valence_weight=0.00,
            )
            if ok:
                events.append("arousal")

        if (predicted["stress"] - base_stress) > 0.08:
            ok = await emotion_state.inject(
                "steer_writeback_stress",
                intensity=min(0.55, predicted["stress"] - base_stress),
                k=0.14,
                arousal_weight=0.65,
                valence_weight=-0.40,
            )
            if ok:
                events.append("stress")

        if (predicted["anxiety"] - base_anxiety) > 0.08:
            ok = await emotion_state.inject(
                "steer_writeback_anxiety",
                intensity=min(0.55, predicted["anxiety"] - base_anxiety),
                k=0.20,
                arousal_weight=0.70,
                valence_weight=-0.35,
            )
            if ok:
                events.append("anxiety")

        if (base_coherence - predicted["coherence"]) > 0.10:
            ok = await emotion_state.inject(
                "steer_writeback_disruption",
                intensity=min(0.40, base_coherence - predicted["coherence"]),
                k=0.12,
                arousal_weight=0.35,
                valence_weight=-0.15,
            )
            if ok:
                events.append("coherence_drop")
        elif (predicted["coherence"] - base_coherence) > 0.10:
            ok = await emotion_state.inject(
                "steer_writeback_clarity",
                intensity=min(0.35, predicted["coherence"] - base_coherence),
                k=0.20,
                arousal_weight=0.10,
                valence_weight=0.20,
            )
            if ok:
                events.append("coherence_gain")

        if events:
            logger.debug("Steering write-back injected traces: %s", ",".join(events))

        return {
            "writeback": "applied" if events else "no_delta",
            "events": events,
            "predicted": predicted,
        }

    @staticmethod
    def _classify_text(text: str) -> dict[str, float]:
        raw = str(text or "")
        low = raw.lower()
        tokens = re.findall(r"[a-z']+", low)
        token_count = max(1, len(tokens))

        pos_lex = {
            "calm",
            "clear",
            "steady",
            "good",
            "gentle",
            "resolved",
            "helpful",
            "stable",
            "bright",
            "coherent",
        }
        neg_lex = {
            "blocked",
            "failed",
            "error",
            "storm",
            "heavy",
            "fractured",
            "conflict",
            "uncertain",
            "pain",
            "loss",
        }
        anx_lex = {
            "anxious",
            "worry",
            "urgent",
            "panic",
            "risk",
            "threat",
            "cannot",
            "can't",
            "stuck",
            "fear",
        }
        coherent_lex = {
            "because",
            "therefore",
            "so",
            "however",
            "first",
            "then",
            "finally",
            "overall",
        }

        pos = sum(1 for t in tokens if t in pos_lex)
        neg = sum(1 for t in tokens if t in neg_lex)
        anx = sum(1 for t in tokens if t in anx_lex)
        coh = sum(1 for t in tokens if t in coherent_lex)
        exclam = raw.count("!")
        question = raw.count("?")
        sentence_count = max(1, len(re.findall(r"[.!?]+", raw)))
        avg_sentence_len = token_count / sentence_count

        valence = _clip11((pos - neg) / max(3.0, token_count * 0.18))
        arousal = _clip01((exclam * 0.08) + (question * 0.03) + (anx / max(1.0, token_count * 0.12)))
        stress = _clip01(((neg + anx) / max(2.0, token_count * 0.20)) + (0.08 if "blocked" in low else 0.0))
        anxiety = _clip01((anx / max(2.0, token_count * 0.15)) + (question * 0.02))
        coherence = _clip01(
            0.45
            + min(0.30, coh / max(1.0, sentence_count * 2.0))
            + (0.15 if avg_sentence_len >= 8 else 0.0)
            - (0.12 if "..." in raw else 0.0)
        )

        return {
            "arousal": float(f"{arousal:.3f}"),
            "valence": float(f"{valence:.3f}"),
            "stress": float(f"{stress:.3f}"),
            "coherence": float(f"{coherence:.3f}"),
            "anxiety": float(f"{anxiety:.3f}"),
        }


_engine: Optional[SteeringEngine] = None
_engine_fp: str = ""


def _fingerprint() -> str:
    return "|".join(
        [
            str(getattr(settings, "STEERING_VECTOR_DIM", 32)),
            str(getattr(settings, "STEERING_BASE_SCALE", 0.35)),
            str(getattr(settings, "STEERING_PRESSURE_GAIN", 0.65)),
            str(getattr(settings, "STEERING_WRITEBACK_ENABLED", True)),
        ]
    )


def get_steering_engine() -> SteeringEngine:
    global _engine, _engine_fp
    fp = _fingerprint()
    if _engine is None or _engine_fp != fp:
        _engine = SteeringEngine(
            vector_dim=int(getattr(settings, "STEERING_VECTOR_DIM", 32) or 32),
            base_scale=float(getattr(settings, "STEERING_BASE_SCALE", 0.35) or 0.35),
            pressure_gain=float(getattr(settings, "STEERING_PRESSURE_GAIN", 0.65) or 0.65),
            writeback_enabled=bool(getattr(settings, "STEERING_WRITEBACK_ENABLED", True)),
        )
        _engine_fp = fp
    return _engine
