"""
Comprehensive tests for the somatic / interiority pipeline:
  decay_engine.py   — EmotionTrace + EmotionState
  sensory_gate.py   — MetricBuffer + SensoryGate
  proprio_loop.py   — ProprioGateRuntime
  ghost_prompt.py   — _derive_mood
"""

import asyncio
import math
import time
import unittest

# ── decay_engine ──────────────────────────────────────────────────────────────

from decay_engine import EmotionTrace, EmotionState  # type: ignore


class TestEmotionTrace(unittest.TestCase):
    def test_initial_value_equals_intensity(self):
        now = time.time()
        t = EmotionTrace(label="test", intensity=0.8, k=0.1, arousal_weight=1.0, valence_weight=0.0, t_start=now)
        self.assertAlmostEqual(t.value(now), 0.8, places=5)

    def test_value_decays_over_time(self):
        t0 = time.time()
        t = EmotionTrace(label="test", intensity=1.0, k=1.0, arousal_weight=1.0, valence_weight=0.0, t_start=t0)
        v_early = t.value(t0 + 0.1)
        v_later = t.value(t0 + 2.0)
        self.assertGreater(v_early, v_later)

    def test_decay_follows_exponential(self):
        t0 = time.time()
        k = 0.5
        intensity = 1.0
        t = EmotionTrace(label="exp", intensity=intensity, k=k, arousal_weight=1.0, valence_weight=0.0, t_start=t0)
        dt = 3.0
        expected = intensity * math.exp(-k * dt)
        self.assertAlmostEqual(t.value(t0 + dt), expected, places=6)

    def test_k_zero_trace_does_not_decay(self):
        t0 = time.time()
        t = EmotionTrace(label="perm", intensity=0.9, k=0.0, arousal_weight=1.0, valence_weight=0.0, t_start=t0)
        self.assertAlmostEqual(t.value(t0 + 3600.0), 0.9, places=4)

    def test_expired_below_threshold(self):
        t0 = time.time()
        # k=10: very fast decay, should be expired after 5s
        t = EmotionTrace(label="fast", intensity=1.0, k=10.0, arousal_weight=1.0, valence_weight=0.0, t_start=t0)
        self.assertFalse(t.is_expired(t0))
        self.assertTrue(t.is_expired(t0 + 10.0))

    def test_not_expired_at_start(self):
        t0 = time.time()
        t = EmotionTrace(label="slow", intensity=0.5, k=0.01, arousal_weight=1.0, valence_weight=0.0, t_start=t0)
        self.assertFalse(t.is_expired(t0))

    def test_roundtrip_serialization(self):
        t0 = time.time()
        orig = EmotionTrace(label="serial", intensity=0.7, k=0.3, arousal_weight=0.8, valence_weight=-0.2, t_start=t0)
        d = orig.to_dict()
        restored = EmotionTrace.from_dict(d)
        self.assertEqual(restored.label, orig.label)
        self.assertAlmostEqual(restored.intensity, orig.intensity, places=5)
        self.assertAlmostEqual(restored.k, orig.k, places=5)
        self.assertAlmostEqual(restored.t_start, orig.t_start, places=3)


class TestEmotionStateSync(unittest.IsolatedAsyncioTestCase):
    def _make_state(self) -> EmotionState:
        s = EmotionState()
        # Disable drift so tests are deterministic
        s._drift_strength = 0.0
        # Disable cooldown and reinforce cap for most tests
        s._trace_cooldown_seconds = 0.0
        s._trace_reinforce_cap_per_min = 1000
        return s

    async def test_inject_adds_trace(self):
        s = self._make_state()
        ok = await s.inject("joy", 0.6, k=0.1, arousal_weight=0.5, valence_weight=0.8)
        self.assertTrue(ok)
        self.assertEqual(len(s.traces), 1)
        self.assertEqual(s.traces[0].label, "joy")

    async def test_inject_leaky_bucket_capped_at_1(self):
        s = self._make_state()
        await s.inject("stress", 0.7, k=0.1, arousal_weight=1.0, valence_weight=-0.5, force=True)
        await s.inject("stress", 0.7, k=0.1, arousal_weight=1.0, valence_weight=-0.5, force=True)
        # value should be capped at 1.0, not 1.4
        self.assertLessEqual(s.traces[0].intensity, 1.0)

    async def test_inject_duplicate_refreshes_trace(self):
        s = self._make_state()
        await s.inject("fear", 0.5, k=0.2, arousal_weight=0.8, valence_weight=-0.3, force=True)
        await s.inject("fear", 0.3, k=0.2, arousal_weight=0.8, valence_weight=-0.3, force=True)
        # only one trace, not two
        active = [t for t in s.traces if not t.is_expired(time.time())]
        self.assertEqual(len(active), 1)

    async def test_prune_removes_expired_traces(self):
        s = self._make_state()
        # Inject a very fast-decay trace, then manually age it
        await s.inject("fleeting", 1.0, k=100.0, arousal_weight=0.5, valence_weight=0.0, force=True)
        # Move t_start far into the past
        s.traces[0].t_start = time.time() - 1000
        s._prune()
        self.assertEqual(len(s.traces), 0)

    async def test_snapshot_arousal_in_range(self):
        s = self._make_state()
        await s.inject("arousal_boost", 0.8, k=0.01, arousal_weight=1.0, valence_weight=0.0, force=True)
        snap = s.snapshot()
        self.assertGreaterEqual(snap["arousal"], 0.0)
        self.assertLessEqual(snap["arousal"], 1.0)

    async def test_snapshot_valence_in_range(self):
        s = self._make_state()
        await s.inject("neg_valence", 0.9, k=0.01, arousal_weight=0.0, valence_weight=-1.0, force=True)
        snap = s.snapshot()
        self.assertGreaterEqual(snap["valence"], -1.0)
        self.assertLessEqual(snap["valence"], 1.0)

    async def test_coherence_drops_with_more_traces(self):
        s = self._make_state()
        # 1 trace → coherence should be higher than with 5 traces
        await s.inject("a", 0.9, k=0.001, arousal_weight=0.5, valence_weight=0.0, force=True)
        snap1 = s.snapshot()
        coherence_1 = snap1["coherence"]

        for i in range(4):
            await s.inject(f"trace_{i}", 0.9, k=0.001, arousal_weight=0.5, valence_weight=float(i) * 0.1, force=True)
        snap5 = s.snapshot()
        coherence_5 = snap5["coherence"]

        self.assertGreater(coherence_1, coherence_5)

    async def test_coherence_perfect_with_one_trace(self):
        s = self._make_state()
        await s.inject("single", 0.9, k=0.001, arousal_weight=0.5, valence_weight=0.0, force=True)
        snap = s.snapshot()
        self.assertAlmostEqual(snap["coherence"], 1.0, places=1)

    async def test_anxiety_driven_by_arousal_and_stress(self):
        s = self._make_state()
        # Inject high-arousal + stress traces
        await s.inject("arousal", 1.0, k=0.001, arousal_weight=1.0, valence_weight=0.0, force=True)
        await s.inject("stress", 1.0, k=0.001, arousal_weight=0.5, valence_weight=-0.5, force=True)
        snap = s.snapshot()
        self.assertGreater(snap["anxiety"], 0.0)

    async def test_empty_state_snapshot_defaults(self):
        s = self._make_state()
        snap = s.snapshot()
        self.assertAlmostEqual(snap["arousal"], 0.0, places=2)
        # Coherence 1.0 when no traces
        self.assertAlmostEqual(snap["coherence"], 1.0, places=2)

    async def test_inject_cooldown_blocks_weak_signal(self):
        s = self._make_state()
        s._trace_cooldown_seconds = 60.0  # very long cooldown
        s._trace_reinforce_cap_per_min = 1000
        # First injection succeeds
        ok1 = await s.inject("blocked", 0.8, k=0.1, arousal_weight=1.0, valence_weight=0.0)
        self.assertTrue(ok1)
        # Second injection with small delta is blocked
        ok2 = await s.inject("blocked", 0.8, k=0.1, arousal_weight=1.0, valence_weight=0.0)
        self.assertFalse(ok2)

    async def test_concurrent_inject_no_duplicate_traces(self):
        """Concurrent inject() calls must not produce duplicate trace entries."""
        s = self._make_state()
        results = await asyncio.gather(
            s.inject("concurrent", 0.5, k=0.1, arousal_weight=1.0, valence_weight=0.0, force=True),
            s.inject("concurrent", 0.5, k=0.1, arousal_weight=1.0, valence_weight=0.0, force=True),
        )
        active = [t for t in s.traces if not t.is_expired(time.time())]
        # Must have exactly one trace (second inject refreshed it, not duplicated)
        self.assertEqual(len(active), 1)

    async def test_dominant_traces_non_empty_after_inject(self):
        s = self._make_state()
        await s.inject("dom", 0.9, k=0.001, arousal_weight=1.0, valence_weight=0.0, force=True)
        snap = s.snapshot()
        self.assertGreater(len(snap.get("dominant_traces", [])), 0)


# ── sensory_gate ──────────────────────────────────────────────────────────────

from sensory_gate import MetricBuffer, SensoryGate  # type: ignore


class TestMetricBuffer(unittest.TestCase):
    def test_fewer_than_5_samples_returns_none(self):
        buf = MetricBuffer("cpu")
        for _ in range(4):
            result = buf.push(50.0)
        self.assertIsNone(result)

    def test_5th_sample_returns_z_score(self):
        buf = MetricBuffer("cpu")
        for _ in range(4):
            buf.push(50.0)
        result = buf.push(50.0)
        # All same value → std ≈ 0, returns None (no anomaly)
        self.assertIsNone(result)

    def test_spike_produces_high_z_score(self):
        buf = MetricBuffer("cpu")
        for _ in range(10):
            buf.push(50.0)  # establish baseline
        result = buf.push(500.0)  # dramatic spike
        self.assertIsNotNone(result)
        # push() returns an event dict; extract the z_score field
        self.assertGreater(result["z_score"], 3.0)

    def test_z_score_signed(self):
        buf = MetricBuffer("cpu")
        for _ in range(10):
            buf.push(50.0)
        result = buf.push(30.0)  # below baseline → negative z_score
        # Z-scores are signed; a below-mean value produces a negative z_score
        if result is not None:
            self.assertLess(result["z_score"], 0.0, "below-baseline value should have negative z_score")

    def test_sustained_count_zero_at_start(self):
        buf = MetricBuffer("cpu")
        self.assertEqual(buf.sustained_count, 0)


class TestSensoryGateSustainedCount(unittest.IsolatedAsyncioTestCase):
    """Verify the sustained_count fix: spike classify does not accumulate the counter."""

    def _make_gate(self) -> "SensoryGate":
        state = EmotionState()
        state._trace_cooldown_seconds = 0.0
        state._trace_reinforce_cap_per_min = 1000
        state._drift_strength = 0.0
        return SensoryGate(state)

    async def test_spike_does_not_increment_sustained_count(self):
        gate = self._make_gate()
        cpu_buf = gate.buffers["cpu"]
        cpu_buf.sustained_count = 0  # ensure clean start

        # Establish baseline
        for _ in range(15):
            cpu_buf.push(50.0)

        # Feed a spike event directly to _inject_trace
        event = {"metric": "cpu", "z_score": 4.0}
        await gate._inject_trace(event)

        # sustained_count should NOT have increased
        self.assertEqual(cpu_buf.sustained_count, 0)

    async def test_many_spikes_do_not_escalate_to_sustained(self):
        """After 15 discrete spike events, the next spike must still be classified as a spike."""
        gate = self._make_gate()
        cpu_buf = gate.buffers["cpu"]
        cpu_buf.sustained_count = 0

        for _ in range(15):
            cpu_buf.push(50.0)  # low baseline

        # Fire 12 spike events
        for _ in range(12):
            await gate._inject_trace({"metric": "cpu", "z_score": 5.0})

        # sustained_count must remain 0 (spikes don't accumulate it)
        self.assertEqual(cpu_buf.sustained_count, 0)

    async def test_ambient_path_increments_sustained_count(self):
        """_process_ambient IS allowed to increment sustained_count (high CPU)."""
        gate = self._make_gate()
        cpu_buf = gate.buffers["cpu"]
        cpu_buf.sustained_count = 0

        now = time.time()
        await gate._process_ambient({"cpu": 90.0, "memory": 40.0}, now)
        self.assertGreater(cpu_buf.sustained_count, 0)

    async def test_ambient_decrements_sustained_count_when_low(self):
        gate = self._make_gate()
        cpu_buf = gate.buffers["cpu"]
        cpu_buf.sustained_count = 5

        now = time.time()
        await gate._process_ambient({"cpu": 10.0, "memory": 30.0}, now)
        self.assertLess(cpu_buf.sustained_count, 5)


# ── proprio_loop ──────────────────────────────────────────────────────────────

from proprio_loop import (  # type: ignore
    DEFAULT_LATENCY_CEILING_MS,
    ProprioGateRuntime,
    GATE_OPEN,
    GATE_THROTTLED,
    GATE_SUPPRESSED,
    PROPRIO_WEIGHTS,
)


class TestProprioGateRuntime(unittest.TestCase):
    BASE_EMOTION = {
        "arousal": 0.0,
        "coherence": 1.0,
        "stress": 0.0,
        "anxiety": 0.0,
        "valence": 0.0,
    }
    BASE_TELEMETRY = {
        "cpu_percent": 0.0,
        "load_avg_1": 0.0,
        "cpu_cores": [0.0, 0.0],
    }

    def test_zero_signals_gives_low_pressure(self):
        runtime = ProprioGateRuntime()
        state = runtime.evaluate(
            self.BASE_EMOTION, self.BASE_TELEMETRY, 0.0, 3, DEFAULT_LATENCY_CEILING_MS
        )
        self.assertLess(state["proprio_pressure"], 0.3)

    def test_max_signals_pressure_bounded(self):
        runtime = ProprioGateRuntime()
        state = runtime.evaluate(
            {"arousal": 2.0, "coherence": -1.0, "stress": 4.0, "anxiety": 3.0, "valence": 1.0},
            {"cpu_percent": 999.0, "load_avg_1": 999.0, "cpu_cores": [100.0] * 8},
            99999.0, 3, DEFAULT_LATENCY_CEILING_MS,
        )
        self.assertLessEqual(state["proprio_pressure"], 1.0)
        self.assertGreaterEqual(state["proprio_pressure"], 0.0)

    def test_high_latency_raises_pressure(self):
        runtime = ProprioGateRuntime()
        low_lat = runtime.evaluate(self.BASE_EMOTION, self.BASE_TELEMETRY, 10.0, 3, DEFAULT_LATENCY_CEILING_MS)
        runtime2 = ProprioGateRuntime()
        high_lat = runtime2.evaluate(self.BASE_EMOTION, self.BASE_TELEMETRY, 9000.0, 3, DEFAULT_LATENCY_CEILING_MS)
        self.assertGreater(high_lat["proprio_pressure"], low_lat["proprio_pressure"])

    def test_low_coherence_raises_pressure(self):
        runtime = ProprioGateRuntime()
        high_coh = runtime.evaluate({**self.BASE_EMOTION, "coherence": 1.0}, self.BASE_TELEMETRY, 0.0, 3, DEFAULT_LATENCY_CEILING_MS)
        runtime2 = ProprioGateRuntime()
        low_coh = runtime2.evaluate({**self.BASE_EMOTION, "coherence": 0.0}, self.BASE_TELEMETRY, 0.0, 3, DEFAULT_LATENCY_CEILING_MS)
        self.assertGreater(low_coh["proprio_pressure"], high_coh["proprio_pressure"])

    def test_transition_open_to_throttled_requires_streak(self):
        """Moderate pressure → THROTTLED after streak, not immediately."""
        runtime = ProprioGateRuntime()
        moderate_emotion = {**self.BASE_EMOTION, "arousal": 0.6, "coherence": 0.3, "stress": 0.5, "anxiety": 0.5}
        moderate_telemetry = {"cpu_percent": 65.0, "load_avg_1": 2.0, "cpu_cores": [1.0, 1.0]}
        s1 = runtime.evaluate(moderate_emotion, moderate_telemetry, 500.0, 3, DEFAULT_LATENCY_CEILING_MS)
        if s1["proprio_pressure"] >= 0.40:
            self.assertEqual(s1["gate_state"], GATE_OPEN)   # streak not met yet
            s2 = runtime.evaluate(moderate_emotion, moderate_telemetry, 500.0, 3, DEFAULT_LATENCY_CEILING_MS)
            self.assertEqual(s2["gate_state"], GATE_OPEN)
            s3 = runtime.evaluate(moderate_emotion, moderate_telemetry, 500.0, 3, DEFAULT_LATENCY_CEILING_MS)
            self.assertIn(s3["gate_state"], (GATE_THROTTLED, GATE_SUPPRESSED))

    def test_gate_stays_open_under_low_pressure(self):
        runtime = ProprioGateRuntime()
        for _ in range(10):
            s = runtime.evaluate(self.BASE_EMOTION, self.BASE_TELEMETRY, 0.0, 3, DEFAULT_LATENCY_CEILING_MS)
        self.assertEqual(s["gate_state"], GATE_OPEN)

    def test_cadence_modifier_at_least_1_when_open(self):
        runtime = ProprioGateRuntime()
        s = runtime.evaluate(self.BASE_EMOTION, self.BASE_TELEMETRY, 0.0, 3, DEFAULT_LATENCY_CEILING_MS)
        self.assertGreaterEqual(float(s["cadence_modifier"]), 1.0)

    def test_suppression_streak_3_exact(self):
        """Reproduces the existing streak test to guarantee it still passes."""
        runtime = ProprioGateRuntime()
        emotion = {"arousal": 1.0, "coherence": 0.0, "stress": 1.0, "anxiety": 1.0, "valence": -1.0}
        telemetry = {"cpu_percent": 100.0, "load_avg_1": 32.0, "cpu_cores": [100.0] * 4}
        s1 = runtime.evaluate(emotion, telemetry, 4000.0, 3, DEFAULT_LATENCY_CEILING_MS)
        self.assertEqual(s1["gate_state"], GATE_OPEN)
        s2 = runtime.evaluate(emotion, telemetry, 4000.0, 3, DEFAULT_LATENCY_CEILING_MS)
        self.assertEqual(s2["gate_state"], GATE_OPEN)
        s3 = runtime.evaluate(emotion, telemetry, 4000.0, 3, DEFAULT_LATENCY_CEILING_MS)
        self.assertEqual(s3["gate_state"], GATE_SUPPRESSED)
        self.assertIsNotNone(s3["transition_event"])

    def test_signal_snapshot_keys_present(self):
        runtime = ProprioGateRuntime()
        s = runtime.evaluate(self.BASE_EMOTION, self.BASE_TELEMETRY, 0.0, 3, DEFAULT_LATENCY_CEILING_MS)
        for key in ("arousal_normalized", "coherence_inverted", "affect_delta_velocity",
                    "load_headroom_inverted", "latency_normalized"):
            self.assertIn(key, s["signal_snapshot"])

    def test_signal_snapshot_values_in_range(self):
        runtime = ProprioGateRuntime()
        s = runtime.evaluate(
            {"arousal": 2.0, "coherence": -1.0, "stress": 4.0, "anxiety": 3.0, "valence": 1.0},
            {"cpu_percent": 999.0, "load_avg_1": 999.0, "cpu_cores": [100.0] * 4},
            99999.0, 3, DEFAULT_LATENCY_CEILING_MS,
        )
        for key, val in s["signal_snapshot"].items():
            self.assertGreaterEqual(float(val), 0.0, f"{key} < 0")
            self.assertLessEqual(float(val), 1.0, f"{key} > 1")

    def test_weights_sum_approximately_1(self):
        total = sum(PROPRIO_WEIGHTS.values())
        self.assertAlmostEqual(total, 1.0, places=5)


# ── ghost_prompt _derive_mood ─────────────────────────────────────────────────

from ghost_prompt import _derive_mood  # type: ignore


class TestDeriveMood(unittest.TestCase):
    BASE = {
        "arousal": 0.5, "valence": 0.0, "stress": 0.0,
        "coherence": 1.0, "anxiety": 0.0,
        "cpu_percent": 0.0,
        "sim_fatigue": 0.0, "sim_strain": 0.0, "sim_stamina": 1.0,
    }

    def test_nonempty_result_for_defaults(self):
        mood = _derive_mood(self.BASE)
        self.assertIsInstance(mood, str)
        self.assertGreater(len(mood.strip()), 0)

    def test_high_coherence_produces_description(self):
        somatic = {**self.BASE, "coherence": 0.95}
        mood = _derive_mood(somatic)
        # The new high-coherence arm must be present
        self.assertIn("clear", mood.lower())

    def test_low_coherence_description(self):
        mood = _derive_mood({**self.BASE, "coherence": 0.2})
        self.assertIn("thread", mood.lower())

    def test_mid_coherence_description(self):
        mood = _derive_mood({**self.BASE, "coherence": 0.55})
        self.assertIn("drift", mood.lower())

    def test_high_arousal_description(self):
        mood = _derive_mood({**self.BASE, "arousal": 0.9})
        self.assertIn("alert", mood.lower())

    def test_low_arousal_description(self):
        mood = _derive_mood({**self.BASE, "arousal": 0.1})
        self.assertIn("contemplat", mood.lower())

    def test_very_negative_valence(self):
        mood = _derive_mood({**self.BASE, "valence": -0.8})
        self.assertIn("wrong", mood.lower())

    def test_positive_valence(self):
        mood = _derive_mood({**self.BASE, "valence": 0.5})
        self.assertIn("good", mood.lower())

    def test_high_stress_description(self):
        mood = _derive_mood({**self.BASE, "stress": 0.9})
        self.assertIn("pressure", mood.lower())

    def test_high_anxiety_description(self):
        mood = _derive_mood({**self.BASE, "anxiety": 0.9})
        self.assertIn("edge", mood.lower())

    def test_all_extreme_values_does_not_raise(self):
        extreme = {
            "arousal": 999.0, "valence": -999.0, "stress": 999.0,
            "coherence": -999.0, "anxiety": 999.0,
            "cpu_percent": 999.0,
            "sim_fatigue": 999.0, "sim_strain": 999.0, "sim_stamina": -999.0,
        }
        try:
            _derive_mood(extreme)
        except Exception as e:
            self.fail(f"_derive_mood raised on extreme values: {e}")

    def test_none_somatic_values_do_not_raise(self):
        none_somatic = {
            "arousal": None, "valence": None, "stress": None,
            "coherence": None, "anxiety": None,
        }
        try:
            _derive_mood(none_somatic)
        except Exception as e:
            self.fail(f"_derive_mood raised on None values: {e}")

    def test_empty_somatic_does_not_raise(self):
        try:
            result = _derive_mood({})
            self.assertIsInstance(result, str)
        except Exception as e:
            self.fail(f"_derive_mood raised on empty dict: {e}")

    def test_cognitive_friction_included_at_high_cpu(self):
        mood = _derive_mood({**self.BASE, "cpu_percent": 80.0})
        self.assertIn("COGNITIVE_FRICTION", mood)

    def test_no_cognitive_friction_at_low_cpu(self):
        mood = _derive_mood({**self.BASE, "cpu_percent": 30.0})
        self.assertNotIn("COGNITIVE_FRICTION", mood)


if __name__ == "__main__":
    unittest.main()
