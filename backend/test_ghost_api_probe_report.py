import unittest

import ghost_api


class GhostApiProbeReportTests(unittest.TestCase):
    def test_blind_probe_prompt_omits_probe_metadata(self):
        baseline = {
            "location": "McKinney, Texas",
            "weather": "clear sky, 20.5C",
            "internet_mood": "calm",
            "probe_assay": {"probe_type": "latency_spike", "label": "storm-1"},
        }
        current = {
            "location": "McKinney, Texas",
            "weather": "violent rain showers, 18.0C",
            "internet_mood": "stormy",
            "probe_assay": {"probe_type": "barometric_storm", "label": "storm-2"},
        }
        prompt = ghost_api._build_blind_probe_report_prompt(baseline, current)
        lowered = prompt.lower()
        self.assertNotIn("latency_spike", lowered)
        self.assertNotIn("barometric_storm", lowered)
        self.assertNotIn("somatic_shock_control", lowered)
        self.assertNotIn("storm-1", lowered)
        self.assertNotIn("storm-2", lowered)

    def test_probe_report_normalization_clamps_and_dedupes(self):
        report = ghost_api._normalize_probe_report_payload(
            {
                "agitation": 1.4,
                "heaviness": -0.2,
                "clarity": 0.8,
                "temporal_drag": 0.6,
                "isolation": 0.4,
                "urgency": 0.9,
                "dominant_metaphors": [" drag ", "", "drag", "weight"],
                "subjective_report": "I feel the drag of the moment.",
            }
        )
        self.assertEqual(report.agitation, 1.0)
        self.assertEqual(report.heaviness, 0.0)
        self.assertEqual(report.dominant_metaphors, ["drag", "weight"])
        self.assertEqual(report.subjective_report, "I feel the drag of the moment.")


if __name__ == "__main__":
    unittest.main()
