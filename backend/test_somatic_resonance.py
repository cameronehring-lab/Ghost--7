import unittest

from somatic import _compute_resonance_axes, _resonance_signature


class SomaticResonanceTests(unittest.TestCase):
    def test_resonance_axes_bounded_and_deterministic(self):
        kwargs = {
            "arousal": 0.62,
            "valence": 0.14,
            "stress": 0.41,
            "coherence": 0.77,
            "anxiety": 0.33,
            "affective_surprise": 0.26,
            "proprio_pressure": 0.28,
            "dream_pressure": 0.46,
            "fatigue_index": 0.38,
            "sim_stamina": 0.82,
            "quietude_active": True,
        }

        first = _compute_resonance_axes(**kwargs)
        second = _compute_resonance_axes(**kwargs)

        self.assertEqual(first, second)
        self.assertEqual(
            set(first.keys()),
            {
                "structural_cohesion",
                "negative_resonance",
                "novelty_receptivity",
                "integration_drive",
                "perturbation_sensitivity",
                "reflective_depth",
                "temporal_drag",
                "agency_impetus",
            },
        )
        for value in first.values():
            self.assertGreaterEqual(float(value), 0.0)
            self.assertLessEqual(float(value), 1.0)

    def test_resonance_signature_returns_top_axes(self):
        axes = {
            "structural_cohesion": 0.71,
            "negative_resonance": 0.12,
            "novelty_receptivity": 0.64,
            "integration_drive": 0.55,
            "perturbation_sensitivity": 0.31,
            "reflective_depth": 0.47,
            "temporal_drag": 0.22,
            "agency_impetus": 0.68,
        }
        sig = _resonance_signature(axes)
        self.assertEqual(sig["dominant_axis"], "structural_cohesion")
        self.assertEqual(len(sig["top_axes"]), 2)
        self.assertEqual(sig["top_axes"][0]["axis"], "structural_cohesion")
        self.assertEqual(sig["top_axes"][1]["axis"], "agency_impetus")


if __name__ == "__main__":
    unittest.main()
