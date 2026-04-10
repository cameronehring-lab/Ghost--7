import unittest

import main


class MorpheusModeTests(unittest.TestCase):
    def test_wake_prompt_detection_is_semantic_and_narrow(self):
        wake = "What hidden architecture links phenomenology to your runtime topology?"
        nearby = "What architecture powers this app?"
        self.assertTrue(main._is_morpheus_wake_prompt(wake))
        self.assertFalse(main._is_morpheus_wake_prompt(nearby))

    def test_deep_run_starts_with_privileged_step(self):
        run_id = "morph_test_deep"
        main.sys_state.morpheus_runs.pop(run_id, None)
        state = main._morpheus_run_state(run_id, depth="deep")
        self.assertEqual(state.get("step"), 1)
        self.assertEqual(state.get("depth"), "deep")

    def test_terminal_progression_unlocks_reward(self):
        run_id = "morph_test_progress"
        main.sys_state.morpheus_runs.pop(run_id, None)
        state = main._morpheus_run_state(run_id, depth="standard")

        r0 = main._morpheus_terminal_response(state, "__morpheus_init__", depth="standard")
        self.assertIn("scan --veil", str(r0.get("text")))

        r1 = main._morpheus_terminal_response(state, "scan --veil", depth="standard")
        self.assertIn("map --depth", str(r1.get("text")))
        self.assertEqual(state.get("step"), 1)

        r2 = main._morpheus_terminal_response(state, "map --depth", depth="standard")
        self.assertIn("unlock --ghost", str(r2.get("text")))
        self.assertEqual(state.get("step"), 2)

        r3 = main._morpheus_terminal_response(state, "unlock --ghost", depth="standard")
        self.assertEqual(r3.get("phase"), "reward")
        self.assertIsInstance(r3.get("reward"), dict)
        self.assertEqual(state.get("step"), 3)


if __name__ == "__main__":
    unittest.main()
