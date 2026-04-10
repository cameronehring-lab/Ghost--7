import unittest
from unittest.mock import AsyncMock, patch

from google.genai import types  # type: ignore

import ghost_api


class _FakeCandidate:
    def __init__(self, content):
        self.content = content
        self.grounding_metadata = None


class _FakeResponse:
    def __init__(self, text: str, parts=None):
        self.text = text
        if parts is None:
            self.candidates = []
        else:
            content = types.Content(role="model", parts=list(parts))
            self.candidates = [_FakeCandidate(content)]


class GhostApiThoughtSimulationTests(unittest.IsolatedAsyncioTestCase):
    def test_math_prompt_is_detected_as_tool_intent(self) -> None:
        self.assertTrue(ghost_api._is_tool_intent_message("Simulate a 5x5 rotation matrix"))
        self.assertTrue(ghost_api._is_tool_intent_message("Solve the standard heat diffusion differential equation"))
        self.assertFalse(ghost_api._is_tool_intent_message("What is a rotation matrix?"))

    def test_tool_probe_prompt_guides_multiline_thought_simulation(self) -> None:
        prompt = ghost_api._build_unified_followup_prompt(
            user_message="Build the Schwarzschild metric and solve the Einstein field equations",
            fetched_blocks=[],
            action_feedback_lines=[],
            tool_feedback_lines=[],
            tool_probe_hint=True,
        )
        self.assertIn("call thought_simulation now", prompt.lower())
        self.assertIn("multi-line python", prompt.lower())
        self.assertIn("do not compress code with semicolons", prompt.lower())

    async def test_missing_code_fails_cleanly(self) -> None:
        result = await ghost_api._execute_named_tool_call(
            "thought_simulation",
            {"objective": "rotation matrix", "code": ""},
            freedom_policy=None,
            mind_service=None,
        )
        self.assertEqual(result["payload"]["status"], "failed")
        self.assertEqual(result["payload"]["reason"], "missing_code")
        self.assertEqual(result["event"]["event"], "thought_simulation")

    async def test_math_prompt_uses_tool_round_and_emits_output_event(self) -> None:
        function_part = types.Part.from_function_call(
            name="thought_simulation",
            args={
                "objective": "rotation matrix",
                "code": "print('[[0,-1],[1,0]]')",
            },
        )
        generator = AsyncMock(
            side_effect=[
                _FakeResponse("", parts=[function_part]),
                _FakeResponse("Computed the rotation matrix and returned it."),
            ]
        )
        runner = AsyncMock(
            return_value={
                "status": "success",
                "reason": "ok",
                "objective": "rotation matrix",
                "output": "[[0,-1],[1,0]]\n",
                "truncated": False,
            }
        )

        with patch.object(ghost_api, "build_system_prompt", return_value="sys"), patch.object(
            ghost_api, "_generate_with_retry", new=generator
        ), patch.object(
            ghost_api, "_run_thought_simulation_runner", new=runner
        ), patch.object(ghost_api.settings, "TTS_ENABLED", False):
            events = []
            async for item in ghost_api.ghost_stream(
                user_message="Simulate a 5x5 rotation matrix",
                conversation_history=[],
                somatic={},
                monologues=[],
                mind_service=None,
                actuation_callback=None,
            ):
                events.append(item)

        first_config = generator.await_args_list[0].kwargs["config"]
        self.assertTrue(first_config.tools and first_config.tools[0].function_declarations)
        thought_events = [e for e in events if isinstance(e, dict) and e.get("event") == "thought_simulation"]
        self.assertEqual(len(thought_events), 1)
        self.assertEqual(thought_events[0]["status"], "success")
        self.assertIn("[[0,-1],[1,0]]", thought_events[0]["output"])
        output_text = "".join(e for e in events if isinstance(e, str)).lower()
        self.assertIn("rotation matrix", output_text)


if __name__ == "__main__":
    unittest.main()
