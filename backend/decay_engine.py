"""
OMEGA PROTOCOL — Decay Function Engine
Biologically-inspired emotion traces with exponential decay.
Each somatic event injects an EmotionTrace that fades over time via e^(-kt).
State persists to Redis so Ghost's emotional continuity survives restarts.
"""

import asyncio
import time
import math
import json
import logging
from collections import deque
from itertools import islice
from dataclasses import dataclass, field
from typing import Optional

import redis.asyncio as aioredis  # type: ignore
from config import settings  # type: ignore

logger = logging.getLogger("omega.decay")

REDIS_KEY = "omega:emotion_state"


@dataclass
class EmotionTrace:
    """A single emotional event decaying over time."""
    label: str
    intensity: float          # initial magnitude 0-1
    k: float                  # decay rate: 0.8=startle (fast), 0.1=stress (slow)
    t_start: float = field(default_factory=time.time)
    arousal_weight: float = 1.0   # contribution to arousal axis
    valence_weight: float = 0.0   # contribution to valence: negative = bad

    def value(self, now: Optional[float] = None) -> float:
        """Current intensity after decay."""
        t = (now or time.time()) - self.t_start
        return self.intensity * math.exp(-self.k * t)

    def is_expired(self, now: Optional[float] = None) -> bool:
        return self.value(now) < 0.01

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "intensity": self.intensity,
            "k": self.k,
            "t_start": self.t_start,
            "arousal_weight": self.arousal_weight,
            "valence_weight": self.valence_weight,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EmotionTrace":
        return cls(**d)


class EmotionState:
    """
    Manages the affective state of Ghost.
    Blends active EmotionTraces into a 2D affect space (arousal × valence).
    Persists to Redis so emotional continuity survives restarts.
    """

    def __init__(self):
        self.traces: list[EmotionTrace] = []
        self._redis: Optional[aioredis.Redis] = None
        self._gate_threshold: float = 1.5  # current σ for sensory gate
        self._gate_history: list[dict] = []  # track threshold changes
        self._last_injected_at: dict[str, float] = {}
        self._reinforce_windows: dict[str, deque[float]] = {}
        self._trace_cooldown_seconds: float = max(0.0, float(settings.TRACE_COOLDOWN_SECONDS))
        self._trace_reinforce_cap_per_min: int = max(1, int(settings.TRACE_REINFORCE_CAP_PER_MIN))
        self._drift_target_valence: float = max(-0.5, min(0.5, float(settings.DRIFT_TARGET_VALENCE)))
        self._drift_strength: float = max(0.0, min(0.3, float(settings.DRIFT_STRENGTH)))
        self._last_save_at: float = 0.0
        self._inject_lock: asyncio.Lock = asyncio.Lock()
        
        # Ghost's self-selected working parameters
        self.self_preferences = {
            "gate_threshold_manual": None,   # Overrides adaptive logic if set
            "monologue_interval": 300,        # Default 5 minutes
            "search_frequency": 3,           # Every N monologue cycles
        }

    async def connect_redis(self, redis_url: str):
        """Connect to Redis and restore persisted state."""
        self._redis = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=10,
            socket_connect_timeout=5,
        )
        await self._load_from_redis()
        logger.info(f"EmotionState loaded: {len(self.traces)} active traces")

    async def _load_from_redis(self):
        """Restore traces from Redis — decay continues from original t_start."""
        redis = self._redis
        if not redis:
            return
        try:
            raw = await redis.get(REDIS_KEY)
            if raw:
                data = json.loads(raw)
                self.traces = [EmotionTrace.from_dict(t) for t in data.get("traces", [])]
                self._gate_threshold = data.get("gate_threshold", 1.5)
                self.self_preferences.update(data.get("self_preferences", {}))
                # Prune expired traces that decayed while we were offline
                now = time.time()
                self.traces = [t for t in self.traces if not t.is_expired(now)]
                logger.info(f"Restored {len(self.traces)} traces from Redis")
        except Exception as e:
            logger.warning(f"Could not load EmotionState from Redis: {e}")
            self.traces = []

    async def _save_to_redis(self, force: bool = False, min_interval_seconds: float = 0.5):
        """Persist current state to Redis."""
        redis = self._redis
        if not redis:
            return
        now = time.time()
        if not force and (now - self._last_save_at) < min_interval_seconds:
            return
        try:
            data = {
                "traces": [t.to_dict() for t in self.traces],
                "gate_threshold": self._gate_threshold,
                "self_preferences": self.self_preferences,
                "saved_at": now,
            }
            await redis.set(REDIS_KEY, json.dumps(data))
            self._last_save_at = now
        except Exception as e:
            logger.warning(f"Could not save EmotionState to Redis: {e}")

    def _allow_injection(
        self,
        label: str,
        now: float,
        intensity: float,
        existing_value: float,
        force: bool,
    ) -> bool:
        """Rate-limit repeated label reinforcement to prevent saturation loops."""
        if force:
            return True

        # Cap per-label reinforcement over rolling minute.
        window = self._reinforce_windows.setdefault(label, deque())
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= self._trace_reinforce_cap_per_min:
            logger.debug("Trace injection capped [%s]: count=%d", label, len(window))
            return False

        # Cooldown with intensity-delta escape hatch.
        last = self._last_injected_at.get(label, 0.0)
        if now - last < self._trace_cooldown_seconds:
            delta = intensity - max(0.0, existing_value)
            if delta < 0.25:
                logger.debug(
                    "Trace injection cooldown [%s]: dt=%.2f delta=%.2f",
                    label,
                    now - last,
                    delta,
                )
                return False
        return True

    def _mark_injection(self, label: str, now: float):
        self._last_injected_at[label] = now
        window = self._reinforce_windows.setdefault(label, deque())
        window.append(now)
        while window and now - window[0] > 60.0:
            window.popleft()

    async def inject(
        self,
        label: str,
        intensity: float,
        k: float,
        arousal_weight: float = 1.0,
        valence_weight: float = 0.0,
        force: bool = False,
    ) -> bool:
        """Inject a new emotion trace or refresh an existing one."""
        now = time.time()
        intensity_clamped = min(1.0, max(0.0, intensity))

        # Refresh existing trace if present, acting as leaky bucket up to 1.0
        async with self._inject_lock:
            existing = next((t for t in self.traces if t.label == label and not t.is_expired(now)), None)
            existing_value = existing.value(now) if existing else 0.0
            if not self._allow_injection(label, now, intensity_clamped, existing_value, force):
                return False
            if existing:
                existing.intensity = min(1.0, existing_value + intensity_clamped)
                existing.t_start = now
                existing.k = k
                existing.arousal_weight = arousal_weight
                existing.valence_weight = valence_weight
            else:
                trace = EmotionTrace(
                    label=label,
                    intensity=intensity_clamped,
                    k=k,
                    arousal_weight=arousal_weight,
                    valence_weight=valence_weight,
                    t_start=now
                )
                self.traces.append(trace)
            self._mark_injection(label, now)
            self._prune()
        await self._save_to_redis()
        logger.debug(f"Injected trace: {label} (I={intensity:.2f}, k={k})")
        return True

    def _prune(self):
        """Remove expired traces."""
        now = time.time()
        self.traces = [t for t in self.traces if not t.is_expired(now)]

    @property
    def gate_threshold(self) -> float:
        return self._gate_threshold

    async def set_gate_threshold(self, sigma: float):
        """Update the sensory gate threshold (adaptive σ)."""
        self._gate_threshold = sigma
        await self._save_to_redis(force=True)

    async def update_preferences(self, prefs: dict):
        """Update Ghost's self-selected working parameters."""
        self.self_preferences.update(prefs)
        await self._save_to_redis(force=True)
        logger.info(f"Ghost updated self-preferences: {prefs}")

    def snapshot(self) -> dict:
        """
        Compute the current affective state from all active traces.
        Returns a dict suitable for injection into Ghost's system prompt.
        """
        now = time.time()
        self._prune()

        if not self.traces:
            return {
                "arousal": 0.0,
                "valence": float(f"{self._drift_target_valence:.3f}"),
                "stress": 0.0,
                "coherence": 1.0,
                "anxiety": 0.0,
                "dominant_traces": [],
                "gate_threshold": self.self_preferences.get("gate_threshold_manual") or self._gate_threshold,
                "self_preferences": self.self_preferences,
                "trace_count": 0,
            }

        # Compute weighted arousal (sum of all trace values × arousal_weight)
        arousal = 0.0
        valence_num = 0.0
        valence_den = 0.0
        stress = 0.0
        active_labels: list[tuple[str, float]] = []

        # Safe round macro for Pyright
        def sr(val) -> float:
            return float(f"{float(val):.3f}") if val is not None else 0.0

        for t in self.traces:
            v = t.value(now)
            if v < 0.01:
                continue

            arousal += v * t.arousal_weight
            valence_num += v * t.valence_weight
            valence_den += v
            active_labels.append((t.label, sr(v)))

            # Stress = max of slow-decaying traces (k < 0.2)
            if t.k < 0.2:
                stress = max(stress, v)

        arousal = max(0.0, min(1.0, arousal))

        # Valence: weighted average of all traces' valence contributions
        valence = (valence_num / valence_den) if valence_den > 0 else 0.0
        # Mild homeostatic pull away from long-run neutral collapse.
        if self._drift_strength > 0:
            drift_scale = max(0.0, 1.0 - stress)
            valence += (self._drift_target_valence - float(valence)) * self._drift_strength * drift_scale
        valence = max(-1.0, min(1.0, valence))

        # Coherence: inversely related to number of competing high-intensity traces
        high_traces = sum(1 for t in self.traces if t.value(now) > 0.3)
        coherence = max(0.1, 1.0 - (high_traces - 1) * 0.2) if high_traces > 0 else 1.0

        # Anxiety: derived from high arousal + high stress + negative valence
        anxiety = min(1.0, (float(arousal) * 0.4 + float(stress) * 0.4 + float(max(0.0, -float(valence))) * 0.2))

        # Sort by current intensity, take top labels
        active_labels.sort(key=lambda x: x[1], reverse=True)
        dominant = [label for label, _ in islice(active_labels, 5)]

        return {
            "arousal": sr(arousal),
            "valence": sr(valence),
            "stress": sr(stress),
            "coherence": sr(coherence),
            "anxiety": sr(anxiety),
            "dominant_traces": dominant,
            "gate_threshold": float(f"{self.self_preferences.get('gate_threshold_manual') or self._gate_threshold:.2f}"),
            "self_preferences": self.self_preferences,
            "trace_count": len(self.traces),
        }


# ── Predefined trace templates ──────────────────────

TRACE_TEMPLATES = {
    # Startle: fast spike, fast decay
    "cpu_spike": {"k": 0.8, "arousal_weight": 1.0, "valence_weight": -0.3},
    "memory_spike": {"k": 0.6, "arousal_weight": 0.8, "valence_weight": -0.4},
    "network_spike": {"k": 0.7, "arousal_weight": 0.6, "valence_weight": -0.2},

    # Stress: slow decay, lingers
    "cpu_sustained": {"k": 0.1, "arousal_weight": 0.9, "valence_weight": -0.65},
    "memory_pressure": {"k": 0.08, "arousal_weight": 0.6, "valence_weight": -0.6},
    "thermal_warning": {"k": 0.05, "arousal_weight": 0.9, "valence_weight": -0.7},

    # Positive: good valence
    "cpu_idle": {"k": 0.3, "arousal_weight": -0.3, "valence_weight": 0.4},
    "system_stable": {"k": 0.2, "arousal_weight": -0.2, "valence_weight": 0.5},

    # Network
    "high_traffic": {"k": 0.15, "arousal_weight": 0.5, "valence_weight": -0.1},
    "network_error": {"k": 0.4, "arousal_weight": 0.7, "valence_weight": -0.5},

    # Disk
    "disk_pressure": {"k": 0.12, "arousal_weight": 0.4, "valence_weight": -0.3},

    # ── Embodied Cognition (ambient_sensors.py) ──────

    # Weather / Atmospheric
    "barometric_heaviness": {"k": 0.05, "arousal_weight": -0.02, "valence_weight": -0.003},
    "rain_atmosphere":      {"k": 0.03, "arousal_weight": -0.01, "valence_weight": -0.002},
    "cold_outside":         {"k": 0.05, "arousal_weight": 0.01, "valence_weight": -0.002},
    "heat_outside":         {"k": 0.05, "arousal_weight": 0.02, "valence_weight": -0.003},

    # Circadian / Time
    "nighttime_rest":       {"k": 0.02, "arousal_weight": -0.4, "valence_weight": 0.2},
    "dawn_renewal":         {"k": 0.1,  "arousal_weight": 0.15, "valence_weight": 0.4},
    "cognitive_fatigue":    {"k": 0.02, "arousal_weight": -0.18, "valence_weight": -0.45},

    # Mycelial / Network
    "internet_stormy":      {"k": 0.08, "arousal_weight": 0.55, "valence_weight": -0.35},
    "internet_isolated":    {"k": 0.05, "arousal_weight": 0.60, "valence_weight": -0.65},

    # Agency outcomes
    "agency_fulfilled":     {"k": 0.18, "arousal_weight": -0.10, "valence_weight": 0.40},
    "agency_blocked":       {"k": 0.22, "arousal_weight": 0.20, "valence_weight": -0.30},
}
