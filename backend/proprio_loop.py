"""
High-rate proprioceptive gating loop.
Computes pre-language pressure signals and gate state transitions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import asyncpg  # type: ignore

from config import settings  # type: ignore
from ghost_api import get_recent_generation_latency_ms  # type: ignore

logger = logging.getLogger("omega.proprio")

GATE_OPEN = "OPEN"
GATE_THROTTLED = "THROTTLED"
GATE_SUPPRESSED = "SUPPRESSED"

PROPRIO_WEIGHTS = {
    "arousal_normalized": 0.30,
    "coherence_inverted": 0.25,
    "affect_delta_velocity": 0.20,
    "load_headroom_inverted": 0.15,
    "latency_normalized": 0.10,
}

DEFAULT_INTERVAL_SECONDS = 2.0
DEFAULT_STREAK = 3
DEFAULT_LATENCY_CEILING_MS = 4000.0


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _to_float(value: Any, default: float) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _target_state(pressure: float) -> str:
    if pressure >= 0.75:
        return GATE_SUPPRESSED
    if pressure >= 0.4:
        return GATE_THROTTLED
    return GATE_OPEN


def _cadence_modifier(state: str) -> float:
    # NATURAL_COGNITIVE_FRICTION=True (default): friction is expressed via emotion
    # traces and prompt injection — cadence is NOT artificially slowed.
    # NATURAL_COGNITIVE_FRICTION=False: legacy mode — gate state directly slows cadence.
    if getattr(settings, "NATURAL_COGNITIVE_FRICTION", True):
        return 1.0

    if state == GATE_THROTTLED:
        return 1.6
    if state == GATE_SUPPRESSED:
        return 3.0
    return 1.0


@dataclass
class ProprioGateRuntime:
    gate_state: str = GATE_OPEN
    proprio_pressure: float = 0.0
    cadence_modifier: float = 1.0
    consecutive_ticks_in_state: int = 0
    candidate_state: str = GATE_OPEN
    candidate_ticks: int = 0
    tick_timestamp: float = field(default_factory=time.time)
    signal_snapshot: dict[str, Any] = field(default_factory=dict)
    signal_diagnostics: dict[str, Any] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)
    transition_event: Optional[dict[str, Any]] = None
    last_logged_ts: float = 0.0

    prev_affect: Optional[dict[str, float]] = None
    prev_tick_ts: Optional[float] = None

    def evaluate(
        self,
        emotion_snapshot: dict[str, Any],
        telemetry: dict[str, Any],
        latency_ms: float,
        streak_required: int,
        latency_ceiling_ms: float,
    ) -> dict[str, Any]:
        now = time.time()
        dt = max(1e-3, now - self.prev_tick_ts) if self.prev_tick_ts is not None else 1.0

        arousal = _clamp(_to_float(emotion_snapshot.get("arousal"), 0.0))
        coherence = _clamp(_to_float(emotion_snapshot.get("coherence"), 1.0))
        stress = _clamp(_to_float(emotion_snapshot.get("stress"), 0.0))
        anxiety = _clamp(_to_float(emotion_snapshot.get("anxiety"), 0.0))
        valence = _clamp((_to_float(emotion_snapshot.get("valence"), 0.0) + 1.0) / 2.0)

        current_affect = {
            "arousal": arousal,
            "coherence": coherence,
            "stress": stress,
            "anxiety": anxiety,
            "valence": valence,
        }

        if self.prev_affect is None:
            affect_velocity = 0.0
        else:
            delta = 0.0
            for key in ("arousal", "coherence", "stress", "anxiety", "valence"):
                delta += abs(current_affect[key] - self.prev_affect.get(key, current_affect[key]))
            mean_delta = delta / 5.0
            affect_velocity = _clamp((mean_delta / dt) * 2.5)

        cpu_percent = _clamp(_to_float(telemetry.get("cpu_percent"), 0.0) / 100.0)
        cpu_cores = telemetry.get("cpu_cores") or []
        core_count = len(cpu_cores) if isinstance(cpu_cores, list) and cpu_cores else 1
        load_avg_1 = _to_float(telemetry.get("load_avg_1"), 0.0)
        load_ratio = _clamp(load_avg_1 / max(1.0, float(core_count)))
        load_strain = max(cpu_percent, load_ratio)
        load_headroom = _clamp(1.0 - load_strain)
        load_headroom_inverted = _clamp(1.0 - load_headroom)

        latency_normalized = _clamp(_to_float(latency_ms, 0.0) / max(1.0, latency_ceiling_ms))

        signals = {
            "arousal_normalized": arousal,
            "coherence_inverted": _clamp(1.0 - coherence),
            "affect_delta_velocity": affect_velocity,
            "load_headroom_inverted": load_headroom_inverted,
            "latency_normalized": latency_normalized,
        }
        # Raw diagnostic values kept separately — not part of the normalized 0-1 signal space
        signal_diagnostics = {
            "latency_ms": _to_float(latency_ms, 0.0),
            "dt_seconds": dt,
        }

        contributions = {
            key: _clamp(float(signals[key]) * float(weight))
            for key, weight in PROPRIO_WEIGHTS.items()
        }
        pressure = _clamp(sum(contributions.values()))
        target = _target_state(pressure)

        from_state = self.gate_state
        transition_event: Optional[dict[str, Any]] = None

        if target == self.gate_state:
            self.consecutive_ticks_in_state += 1
            self.candidate_state = target
            self.candidate_ticks = 0
        else:
            if target == self.candidate_state:
                self.candidate_ticks += 1
            else:
                self.candidate_state = target
                self.candidate_ticks = 1
            if self.candidate_ticks >= max(1, streak_required):
                self.gate_state = target
                self.consecutive_ticks_in_state = 1
                self.candidate_ticks = 0
                self.candidate_state = self.gate_state
                transition_event = {
                    "from_state": from_state,
                    "to_state": self.gate_state,
                    "proprio_pressure": pressure,
                    "cadence_modifier": _cadence_modifier(self.gate_state),
                    "signal_snapshot": signals,
                    "contributions": contributions,
                    "created_at": now,
                    "reason": "threshold_crossing",
                }

        self.proprio_pressure = pressure
        self.cadence_modifier = _cadence_modifier(self.gate_state)
        self.tick_timestamp = now
        self.signal_snapshot = signals
        self.signal_diagnostics = signal_diagnostics
        self.contributions = contributions
        self.transition_event = transition_event
        self.prev_affect = current_affect
        self.prev_tick_ts = now

        return {
            "proprio_pressure": self.proprio_pressure,
            "gate_state": self.gate_state,
            "cadence_modifier": self.cadence_modifier,
            "tick_timestamp": self.tick_timestamp,
            "consecutive_ticks_in_state": self.consecutive_ticks_in_state,
            "signal_snapshot": self.signal_snapshot,
            "signal_diagnostics": self.signal_diagnostics,
            "contributions": self.contributions,
            "transition_event": self.transition_event,
        }


async def _persist_transition(pool: asyncpg.Pool, event: dict[str, Any]) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO proprio_transition_log
                (from_state, to_state, proprio_pressure, cadence_modifier, signal_snapshot, contributions, reason)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
                """,
                event["from_state"],
                event["to_state"],
                float(event["proprio_pressure"]),
                float(event["cadence_modifier"]),
                json.dumps(event["signal_snapshot"]),
                json.dumps(event["contributions"]),
                event.get("reason", "threshold_crossing"),
            )
    except Exception as e:
        logger.warning("Failed to persist proprio transition: %s", e)


async def proprio_loop(
    sys_state,
    emotion_state,
    pool: Optional[asyncpg.Pool],
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    streak_required: int = DEFAULT_STREAK,
    latency_ceiling_ms: float = DEFAULT_LATENCY_CEILING_MS,
) -> None:
    """Run proprioceptive gating loop at high cadence."""
    runtime = ProprioGateRuntime()
    logger.info(
        "Proprio loop starting (interval=%.2fs, streak=%d)",
        interval_seconds,
        streak_required,
    )
    await asyncio.sleep(1.0)
    while True:
        try:
            emotion_snapshot = emotion_state.snapshot()
            telemetry = dict(getattr(sys_state, "telemetry_cache", {}) or {})
            latency_ms = float(get_recent_generation_latency_ms() or 0.0)
            state = runtime.evaluate(
                emotion_snapshot=emotion_snapshot,
                telemetry=telemetry,
                latency_ms=latency_ms,
                streak_required=streak_required,
                latency_ceiling_ms=latency_ceiling_ms,
            )
            sys_state.proprio_state = state

            if getattr(settings, "NATURAL_COGNITIVE_FRICTION", True):
                cpu_percent = _clamp(_to_float(telemetry.get("cpu_percent"), 0.0) / 100.0)
                if cpu_percent > 0.3:
                    await emotion_state.inject(
                        label="cognitive_friction",
                        intensity=cpu_percent,
                        k=0.15,
                        arousal_weight=0.45,
                        valence_weight=-0.35,
                    )


            event = state.get("transition_event")
            if event:
                logger.info(
                    "Proprio transition %s -> %s (pressure=%.3f)",
                    event["from_state"],
                    event["to_state"],
                    event["proprio_pressure"],
                )
                if pool is not None:
                    await _persist_transition(pool, event)
                    runtime.last_logged_ts = time.time()
            elif pool is not None and (time.time() - runtime.last_logged_ts) > 30: # 30s heartbeat for immediate fix
                # Force a heartbeat entry to satisfy diagnostic coverage
                heartbeat = {
                    "from_state": state["gate_state"],
                    "to_state": state["gate_state"],
                    "proprio_pressure": state["proprio_pressure"],
                    "cadence_modifier": state["cadence_modifier"],
                    "signal_snapshot": state["signal_snapshot"],
                    "contributions": state["contributions"],
                    "reason": "heartbeat",
                }
                await _persist_transition(pool, heartbeat)
                runtime.last_logged_ts = time.time()
                logger.debug("Proprio heartbeat logged")
        except Exception as e:
            logger.error("Proprio loop error: %s", e)
        await asyncio.sleep(max(0.5, interval_seconds))
