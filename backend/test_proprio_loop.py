import unittest

from proprio_loop import (
    DEFAULT_LATENCY_CEILING_MS,
    ProprioGateRuntime,
    GATE_OPEN,
    GATE_SUPPRESSED,
)


class ProprioLoopTests(unittest.TestCase):
    def test_pressure_is_bounded(self):
        runtime = ProprioGateRuntime()
        state = runtime.evaluate(
            emotion_snapshot={
                "arousal": 2.0,
                "coherence": -1.0,
                "stress": 4.0,
                "anxiety": 3.0,
                "valence": 1.0,
            },
            telemetry={
                "cpu_percent": 900.0,
                "load_avg_1": 999.0,
                "cpu_cores": [100.0, 100.0],
            },
            latency_ms=99999.0,
            streak_required=3,
            latency_ceiling_ms=DEFAULT_LATENCY_CEILING_MS,
        )
        self.assertGreaterEqual(state["proprio_pressure"], 0.0)
        self.assertLessEqual(state["proprio_pressure"], 1.0)

    def test_transition_requires_streak(self):
        runtime = ProprioGateRuntime()
        emotion = {
            "arousal": 1.0,
            "coherence": 0.0,
            "stress": 1.0,
            "anxiety": 1.0,
            "valence": -1.0,
        }
        telemetry = {
            "cpu_percent": 100.0,
            "load_avg_1": 32.0,
            "cpu_cores": [100.0, 100.0, 100.0, 100.0],
        }

        s1 = runtime.evaluate(emotion, telemetry, 4000.0, 3, DEFAULT_LATENCY_CEILING_MS)
        self.assertEqual(s1["gate_state"], GATE_OPEN)
        s2 = runtime.evaluate(emotion, telemetry, 4000.0, 3, DEFAULT_LATENCY_CEILING_MS)
        self.assertEqual(s2["gate_state"], GATE_OPEN)
        s3 = runtime.evaluate(emotion, telemetry, 4000.0, 3, DEFAULT_LATENCY_CEILING_MS)
        self.assertEqual(s3["gate_state"], GATE_SUPPRESSED)
        self.assertIsNotNone(s3["transition_event"])
        self.assertGreaterEqual(float(s3["cadence_modifier"]), 1.0)


if __name__ == "__main__":
    unittest.main()
