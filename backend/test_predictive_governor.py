import unittest

import predictive_governor


class PredictiveGovernorTests(unittest.TestCase):
    def test_build_sample_bounds_values(self):
        sample = predictive_governor.build_sample(
            somatic={
                "coherence": 0.42,
                "stress": 0.71,
                "proprio_pressure": 0.54,
                "gate_state": "THROTTLED",
            },
            iit_record={"metrics": {"phi_proxy": 0.63}},
            proprio_state={"proprio_pressure": 0.54, "gate_state": "THROTTLED"},
            timestamp=100.0,
        )
        self.assertGreaterEqual(float(sample["instability"]), 0.0)
        self.assertLessEqual(float(sample["instability"]), 1.0)
        self.assertEqual(sample["gate_state"], "THROTTLED")

    def test_forecast_reaches_preempt_with_rising_instability(self):
        history = []
        ts = 100.0
        for idx in range(8):
            history.append({"timestamp": ts + idx * 5.0, "instability": 0.40 + (idx * 0.05)})
        pred = predictive_governor.evaluate_forecast(
            history,
            horizon_seconds=120.0,
            watch_threshold=0.58,
            preempt_threshold=0.76,
        )
        self.assertIn(pred["state"], {"watch", "preempt"})
        self.assertGreaterEqual(float(pred["forecast_instability"]), 0.58)

    def test_policy_adjustment_preemptive_caps(self):
        adj = predictive_governor.policy_adjustment({"state": "preempt"})
        generation = adj.get("generation") or {}
        self.assertTrue(adj.get("preemptive"))
        self.assertLessEqual(float(generation.get("temperature_cap", 1.0)), 0.45)
        self.assertLessEqual(int(generation.get("max_tokens_cap", 9999)), 1000)

    def test_predict_next_affect_returns_bounded_axes(self):
        history = [
            {"timestamp": 1.0, "arousal": 0.20, "valence": 0.00, "stress": 0.25, "coherence": 0.82, "anxiety": 0.18},
            {"timestamp": 2.0, "arousal": 0.28, "valence": 0.04, "stress": 0.31, "coherence": 0.79, "anxiety": 0.22},
            {"timestamp": 3.0, "arousal": 0.34, "valence": 0.06, "stress": 0.37, "coherence": 0.75, "anxiety": 0.28},
        ]
        pred = predictive_governor.predict_next_affect(history)
        self.assertEqual(set(pred.keys()), {"arousal", "valence", "stress", "coherence", "anxiety"})
        self.assertGreaterEqual(float(pred["arousal"]), 0.0)
        self.assertLessEqual(float(pred["arousal"]), 1.0)
        self.assertGreaterEqual(float(pred["valence"]), -1.0)
        self.assertLessEqual(float(pred["valence"]), 1.0)

    def test_prediction_error_drive_increases_with_error_magnitude(self):
        predicted = {"arousal": 0.20, "valence": 0.00, "stress": 0.25, "coherence": 0.85, "anxiety": 0.18}
        actual_small = {"arousal": 0.22, "valence": 0.01, "stress": 0.27, "coherence": 0.84, "anxiety": 0.19}
        actual_large = {"arousal": 0.65, "valence": -0.55, "stress": 0.70, "coherence": 0.32, "anxiety": 0.64}
        small_error = predictive_governor.compute_prediction_error(predicted, actual_small)
        large_error = predictive_governor.compute_prediction_error(predicted, actual_large)
        small_drive = predictive_governor.error_to_drive(small_error)
        large_drive = predictive_governor.error_to_drive(large_error)
        self.assertGreaterEqual(float(large_drive), float(small_drive))


if __name__ == "__main__":
    unittest.main()
