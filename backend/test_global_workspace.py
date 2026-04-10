import unittest

from global_workspace import GlobalWorkspace


class GlobalWorkspaceTests(unittest.TestCase):
    def test_write_and_read_updates_named_channels(self):
        ws = GlobalWorkspace(dim=32)
        ws.write_named(
            "somatic_loop",
            {
                "arousal": 0.4,
                "valence": -0.2,
                "stress": 0.5,
                "coherence": 0.7,
                "anxiety": 0.3,
            },
            weight=1.0,
        )
        psi = ws.read()
        self.assertEqual(len(psi), 32)
        self.assertGreater(float(abs(psi[0])), 0.0)
        self.assertGreater(float(abs(psi[3])), 0.0)

    def test_decay_and_interactions_keep_workspace_bounded(self):
        ws = GlobalWorkspace(dim=32)
        ws.write_named(
            "predictive_governor",
            {
                "prediction_error_drive": 0.9,
                "agency_impetus": 0.8,
                "structural_cohesion": 0.7,
            },
            weight=1.0,
        )
        before = ws.read()
        ws.apply_interactions()
        ws.decay(dt=1.0)
        after = ws.read()
        self.assertEqual(len(before), len(after))
        self.assertLessEqual(float(max(abs(v) for v in after)), ws.max_abs)

    def test_to_prompt_context_emits_state_block(self):
        ws = GlobalWorkspace(dim=32)
        ws.write_named("iit_engine", {"phi_proxy": 0.61}, weight=0.7)
        text = ws.to_prompt_context()
        self.assertIn("[GLOBAL_WORKSPACE_STATE]", text)
        self.assertIn("psi_norm=", text)


if __name__ == "__main__":
    unittest.main()
