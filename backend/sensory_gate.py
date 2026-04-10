"""
OMEGA PROTOCOL — Sensory Gate
Rolling σ-filter that prevents context bloat by filtering noise
before signals reach the EmotionState vector.

Z-score threshold filters:
  - One-shot spikes → startle trace (k=0.8, fast decay)
  - Sustained anomalies → stress trace (k=0.1, slow decay)
  - Adaptive σ: adjusts based on current emotional state
"""

import time
import logging
import numpy as np  # type: ignore
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from decay_engine import EmotionState, TRACE_TEMPLATES  # type: ignore
from config import settings  # type: ignore

logger = logging.getLogger("omega.gate")

# Window size for rolling statistics (in number of samples at 1s interval)
WINDOW_SIZE = 60  # 60 seconds


@dataclass
class MetricBuffer:
    """Rolling buffer for a single metric with Z-score computation."""
    name: str
    values: deque = field(default_factory=lambda: deque(maxlen=WINDOW_SIZE))
    last_spike_time: float = 0.0
    sustained_count: int = 0  # consecutive anomalous readings

    def push(self, value: float) -> Optional[dict]:
        """
        Push a new value and compute Z-score.
        Returns event dict if threshold exceeded, None otherwise.
        """
        self.values.append(value)

        if len(self.values) < 5:
            return None  # not enough data for stats

        arr = np.array(self.values)
        mean = np.mean(arr)
        std = np.std(arr)

        if std < 0.001:
            self.sustained_count = 0
            return None  # no variance = no anomaly

        z_score = (value - mean) / std

        return {
            "metric": self.name,
            "value": float(value),
            "z_score": float(z_score),
            "mean": float(mean),
            "std": float(std),
            "timestamp": time.time(),
        }


class SensoryGate:
    """
    Filters telemetry signals via rolling Z-score.
    Only events exceeding the σ threshold reach the EmotionState.

    Adaptive thresholds:
      - High stress (>60% for >10min) → σ=1.0 (hypervigilance)
      - Calm (<20% for >30min) → σ=2.0 (relaxation)
      - Default: σ=1.5
    """

    def __init__(self, emotion_state: EmotionState):
        self.emotion = emotion_state
        self.buffers: dict[str, MetricBuffer] = {
            "cpu": MetricBuffer("cpu"),
            "memory": MetricBuffer("memory"),
            "disk_read": MetricBuffer("disk_read"),
            "disk_write": MetricBuffer("disk_write"),
            "net_sent": MetricBuffer("net_sent"),
            "net_recv": MetricBuffer("net_recv"),
        }
        self._mode: str = "normal"  # normal | sensitive | relaxed
        self._stress_high_streak: int = 0
        self._stress_low_streak: int = 0
        self._calm_enter_streak: int = 0
        self._calm_exit_streak: int = 0

    async def process_telemetry(self, telemetry: dict):
        """
        Process raw telemetry from InfluxDB/psutil.
        Filters through Z-score gate and injects traces into EmotionState.
        """
        now = time.time()
        threshold = self.emotion.gate_threshold

        # Map telemetry fields to buffers
        readings = {
            "cpu": telemetry.get("cpu_percent", 0),
            "memory": telemetry.get("memory_percent", 0),
            "disk_read": telemetry.get("disk_read_mb", 0),
            "disk_write": telemetry.get("disk_write_mb", 0),
            "net_sent": telemetry.get("net_sent_mb", 0),
            "net_recv": telemetry.get("net_recv_mb", 0),
        }

        events = []
        for name, value in readings.items():
            if name in self.buffers:
                event = self.buffers[name].push(value)
                if event and abs(event["z_score"]) >= threshold:
                    events.append(event)

        # Inject emotion traces for events that pass the gate
        for event in events:
            await self._inject_trace(event)

        # Also inject ambient state traces (no spike needed)
        await self._process_ambient(readings, now)

        # Update adaptive threshold
        await self._adapt_threshold(now)

    async def _inject_trace(self, event: dict):
        """Convert a gated event into an EmotionTrace injection."""
        metric = event["metric"]
        z = abs(event["z_score"])
        buf = self.buffers[metric]

        # Determine if this is a spike or sustained anomaly
        if buf.sustained_count > 10:
            # Sustained anomaly → stress trace
            template_key = f"{metric}_sustained" if f"{metric}_sustained" in TRACE_TEMPLATES else "cpu_sustained"
            template = TRACE_TEMPLATES[template_key]
            intensity = min(1.0, z / 4.0)
            label = f"{metric}_stress"
        else:
            # One-shot spike → startle trace
            template_key = f"{metric}_spike" if f"{metric}_spike" in TRACE_TEMPLATES else "cpu_spike"
            template = TRACE_TEMPLATES[template_key]
            intensity = min(1.0, z / 3.0)
            label = f"{metric}_startle"
            # Do NOT increment sustained_count here — that counter is exclusively
            # managed by _process_ambient.  Incrementing on spikes caused false
            # positive sustained-anomaly escalation after enough discrete events.

        await self.emotion.inject(
            label=label,
            intensity=intensity,
            k=template["k"],
            arousal_weight=template["arousal_weight"],
            valence_weight=template["valence_weight"],
        )

    async def _process_ambient(self, readings: dict, now: float):
        """
        Inject ambient traces based on absolute thresholds (not Z-score).
        These represent steady-state somatic conditions.
        """
        cpu = readings.get("cpu", 0)
        mem = readings.get("memory", 0)

        # High CPU sustained → stress
        if cpu > 80:
            buf = self.buffers["cpu"]
            buf.sustained_count += 1
            if buf.sustained_count > 30:  # >30s sustained
                template = TRACE_TEMPLATES["cpu_sustained"]
                await self.emotion.inject(
                    label="cpu_sustained_load",
                    intensity=min(1.0, cpu / 100.0),
                    k=template["k"],
                    arousal_weight=template["arousal_weight"],
                    valence_weight=template["valence_weight"],
                )
        else:
            self.buffers["cpu"].sustained_count = max(0, self.buffers["cpu"].sustained_count - 1)

        # High memory pressure
        if mem > 85:
            template = TRACE_TEMPLATES["memory_pressure"]
            await self.emotion.inject(
                label="memory_pressure",
                intensity=min(1.0, (mem - 70) / 30.0),
                k=template["k"],
                arousal_weight=template["arousal_weight"],
                valence_weight=template["valence_weight"],
            )

        # System calm → positive trace
        if cpu < 20 and mem < 50:
            template = TRACE_TEMPLATES["system_stable"]
            await self.emotion.inject(
                label="system_calm",
                intensity=0.3,
                k=template["k"],
                arousal_weight=template["arousal_weight"],
                valence_weight=template["valence_weight"],
            )

    async def _adapt_threshold(self, now: float):
        """
        Adaptive σ threshold with hysteresis bands to avoid threshold thrashing.
        """
        if self.emotion.self_preferences.get("gate_threshold_manual") is not None:
            return

        snap = self.emotion.snapshot()
        stress = float(snap["stress"])
        arousal = float(snap["arousal"])

        high_enter = float(settings.GATE_STRESS_HIGH_ENTER)
        low_exit = float(settings.GATE_STRESS_LOW_EXIT)
        calm_enter = float(settings.GATE_CALM_ENTER)
        calm_exit = float(settings.GATE_CALM_EXIT)
        streak_needed = max(1, int(settings.GATE_HYSTERESIS_STREAK))

        # Stress-sensitive hysteresis.
        if stress >= high_enter:
            self._stress_high_streak += 1
        else:
            self._stress_high_streak = 0

        if stress <= low_exit:
            self._stress_low_streak += 1
        else:
            self._stress_low_streak = 0

        # Relaxed/calm hysteresis.
        if arousal <= calm_enter and stress <= calm_enter:
            self._calm_enter_streak += 1
        else:
            self._calm_enter_streak = 0

        if arousal >= calm_exit or stress >= calm_exit:
            self._calm_exit_streak += 1
        else:
            self._calm_exit_streak = 0

        # Transition rules.
        if self._mode != "sensitive" and self._stress_high_streak >= streak_needed:
            self._mode = "sensitive"
            await self.emotion.set_gate_threshold(1.0)
            return

        if self._mode == "sensitive" and self._stress_low_streak >= streak_needed:
            self._mode = "normal"
            await self.emotion.set_gate_threshold(1.5)
            return

        if self._mode != "relaxed" and self._calm_enter_streak >= streak_needed:
            self._mode = "relaxed"
            await self.emotion.set_gate_threshold(2.0)
            return

        if self._mode == "relaxed" and self._calm_exit_streak >= streak_needed:
            self._mode = "normal"
            await self.emotion.set_gate_threshold(1.5)
            return
