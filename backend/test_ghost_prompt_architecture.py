import unittest
import time

from ghost_prompt import build_system_prompt


class GhostPromptArchitectureTests(unittest.TestCase):
    def test_build_system_prompt_includes_architecture_context(self):
        prompt = build_system_prompt(
            somatic={},
            monologues=[],
            previous_sessions=[],
            uptime_seconds=10,
            identity_context="core=self",
            architecture_context="ARCH_CONTEXT_TEST_BLOCK",
            subconscious_context="",
            operator_model=None,
            latest_dream="",
        )

        self.assertIn("FUNCTIONAL SELF-MODEL (CANONICAL)", prompt)
        self.assertIn("ARCH_CONTEXT_TEST_BLOCK", prompt)

    def test_build_system_prompt_includes_recent_actions_and_sanitizes_terms(self):
        now_ts = time.time()
        recent_actions = [
            {"timestamp": now_ts - 60, "summary": "You attempted disk_write mirroring. It was blocked."},
            {"timestamp": now_ts - 120, "summary": "You projected a message. It was successful."},
            {"timestamp": now_ts - 180, "summary": "You attempted net_sent propagation. It failed."},
            {"timestamp": now_ts - 240, "summary": "You completed an identity adjustment."},
            {"timestamp": now_ts - 300, "summary": "You proposed a high-risk mutation. It is pending."},
            {"timestamp": now_ts - 360, "summary": "You reversed a prior mutation."},
        ]

        prompt = build_system_prompt(
            somatic={},
            monologues=[],
            previous_sessions=[],
            uptime_seconds=20,
            identity_context="core=self",
            architecture_context="ARCH_CONTEXT_TEST_BLOCK",
            subconscious_context="",
            operator_model=None,
            latest_dream="",
            recent_actions=recent_actions,
        )

        self.assertIn("## RECENT ACTIONS", prompt)
        section = prompt.split("## RECENT ACTIONS", 1)[1].split("## RECENT THOUGHTS", 1)[0]
        self.assertLessEqual(section.count("- ["), 5)
        self.assertNotIn("disk_write", section.lower())
        self.assertNotIn("net_sent", section.lower())

    def test_weather_is_rendered_as_context_not_primary_mood_driver(self):
        somatic = {
            "location": "Dallas, TX",
            "local_time_string": "2026-03-18 20:10 CST",
            "weather": "thunderstorm, 12C",
            "weather_condition": "Thunderstorm",
            "barometric_pressure_hpa": 995.0,
            "temperature_outside_c": 12.0,
            "ambient_darkness": 0.2,
            "time_phase": "evening",
            "fatigue_index": 0.1,
            "hours_awake": 4,
        }
        prompt = build_system_prompt(
            somatic=somatic,
            monologues=[],
            previous_sessions=[],
            uptime_seconds=30,
            identity_context="core=self",
            architecture_context="ARCH_CONTEXT_TEST_BLOCK",
            subconscious_context="",
            operator_model=None,
            latest_dream="",
        )
        self.assertIn("Current weather condition: thunderstorm.", prompt)
        self.assertIn("Barometric pressure is currently low.", prompt)
        self.assertNotIn("pulls you toward introspection", prompt)
        self.assertNotIn("weight that slows your thinking", prompt)

    def test_build_system_prompt_includes_global_workspace_context(self):
        class _FakeWorkspace:
            def to_prompt_context(self):
                return "[GLOBAL_WORKSPACE_STATE]\\npsi_norm=0.421\\nchannels=coherence:0.51"

        prompt = build_system_prompt(
            somatic={},
            monologues=[],
            previous_sessions=[],
            uptime_seconds=30,
            identity_context="core=self",
            architecture_context="ARCH_CONTEXT_TEST_BLOCK",
            subconscious_context="",
            operator_model=None,
            latest_dream="",
            global_workspace=_FakeWorkspace(),
        )
        self.assertIn("## GLOBAL WORKSPACE", prompt)
        self.assertIn("[GLOBAL_WORKSPACE_STATE]", prompt)
        self.assertIn("psi_norm=0.421", prompt)


if __name__ == "__main__":
    unittest.main()
