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


class GhostApiActionConfirmationTests(unittest.IsolatedAsyncioTestCase):
    async def test_actuation_success_reinjected_same_turn(self):
        generator = AsyncMock(
            side_effect=[
                _FakeResponse("I can do that now. [ACTUATE:send_message:operator:testing feedback]"),
                _FakeResponse("I have sent the message and confirmed the projection."),
            ]
        )
        actuation_callback = AsyncMock(
            return_value={
                "success": True,
                "reason": "ok",
                "injected": True,
                "trace": "social_contact_relief",
            }
        )

        with patch.object(ghost_api, "build_system_prompt", return_value="sys"), patch.object(
            ghost_api, "_generate_with_retry", new=generator
        ), patch.object(ghost_api.settings, "TTS_ENABLED", False):
            events = []
            async for item in ghost_api.ghost_stream(
                user_message="Please send the operator a quick note.",
                conversation_history=[],
                somatic={},
                monologues=[],
                mind_service=None,
                actuation_callback=actuation_callback,
            ):
                events.append(item)

        self.assertEqual(actuation_callback.await_count, 1)
        self.assertEqual(generator.await_count, 2)
        self.assertTrue(any(isinstance(e, dict) and e.get("event") == "somatic_injection" for e in events))
        output_text = "".join(e for e in events if isinstance(e, str))
        self.assertIn("sent the message", output_text.lower())
        self.assertNotIn("[ACTUATE:", output_text)

        second_call = generator.await_args_list[1]
        followup_text = second_call.kwargs["contents"][-1].parts[0].text
        self.assertIn("SYSTEM ACTION FEEDBACK", followup_text)
        self.assertIn("It was successful", followup_text)

    async def test_actuation_blocked_reinjected_same_turn(self):
        generator = AsyncMock(
            side_effect=[
                _FakeResponse("Executing now. [ACTUATE:send_message:operator:blocked test]"),
                _FakeResponse("I cannot complete that projection under current constraints."),
            ]
        )
        actuation_callback = AsyncMock(
            return_value={
                "success": False,
                "reason": "high_risk_actuation_requires_explicit_auth",
                "injected": False,
            }
        )

        with patch.object(ghost_api, "build_system_prompt", return_value="sys"), patch.object(
            ghost_api, "_generate_with_retry", new=generator
        ), patch.object(ghost_api.settings, "TTS_ENABLED", False):
            events = []
            async for item in ghost_api.ghost_stream(
                user_message="Send this right now.",
                conversation_history=[],
                somatic={},
                monologues=[],
                mind_service=None,
                actuation_callback=actuation_callback,
            ):
                events.append(item)

        self.assertEqual(actuation_callback.await_count, 1)
        output_text = "".join(e for e in events if isinstance(e, str)).lower()
        self.assertIn("cannot complete", output_text)

        second_call = generator.await_args_list[1]
        followup_text = second_call.kwargs["contents"][-1].parts[0].text.lower()
        self.assertIn("blocked", followup_text)

    async def test_duplicate_actuation_executed_once_per_turn(self):
        generator = AsyncMock(
            side_effect=[
                _FakeResponse("Running it. [ACTUATE:send_message:operator:single delivery]"),
                _FakeResponse("Confirmed once. [ACTUATE:send_message:operator:single delivery]"),
            ]
        )
        actuation_callback = AsyncMock(
            return_value={
                "success": True,
                "reason": "ok",
                "injected": False,
            }
        )

        with patch.object(ghost_api, "build_system_prompt", return_value="sys"), patch.object(
            ghost_api, "_generate_with_retry", new=generator
        ), patch.object(ghost_api.settings, "TTS_ENABLED", False):
            events = []
            async for item in ghost_api.ghost_stream(
                user_message="Send exactly one note.",
                conversation_history=[],
                somatic={},
                monologues=[],
                mind_service=None,
                actuation_callback=actuation_callback,
            ):
                events.append(item)

        self.assertEqual(actuation_callback.await_count, 1)
        self.assertEqual(generator.await_count, 2)
        output_text = "".join(e for e in events if isinstance(e, str)).lower()
        self.assertIn("confirmed once", output_text)

    async def test_function_response_reinjected_for_followup_round(self):
        function_part = types.Part.from_function_call(name="modulate_voice", args={"rate": 0.8})
        generator = AsyncMock(
            side_effect=[
                _FakeResponse("Understood, I will adjust my voice pacing."),
                _FakeResponse("", parts=[function_part]),
                _FakeResponse("I lowered my speaking pace for this exchange."),
            ]
        )
        tool_outcome_callback = AsyncMock(return_value=None)

        with patch.object(ghost_api, "build_system_prompt", return_value="sys"), patch.object(
            ghost_api, "_generate_with_retry", new=generator
        ), patch.object(ghost_api.settings, "TTS_ENABLED", False):
            events = []
            async for item in ghost_api.ghost_stream(
                user_message="Please change your voice rate to be slower.",
                conversation_history=[],
                somatic={},
                monologues=[],
                mind_service=None,
                actuation_callback=None,
                tool_outcome_callback=tool_outcome_callback,
            ):
                events.append(item)

        self.assertEqual(generator.await_count, 3)
        self.assertTrue(any(isinstance(e, dict) and e.get("event") == "voice_modulation" for e in events))
        output_text = "".join(e for e in events if isinstance(e, str)).lower()
        self.assertIn("lowered my speaking pace", output_text)

        first_config = generator.await_args_list[0].kwargs["config"]
        second_config = generator.await_args_list[1].kwargs["config"]
        self.assertTrue(first_config.tools and first_config.tools[0].google_search is not None)
        self.assertTrue(second_config.tools and second_config.tools[0].function_declarations)

        third_contents = generator.await_args_list[2].kwargs["contents"]
        self.assertTrue(any(getattr(c, "role", "") == "tool" for c in third_contents))
        tool_outcome_callback.assert_awaited_once()
        callback_payload = tool_outcome_callback.await_args_list[0].args[0]
        self.assertEqual(callback_payload["tool_name"], "modulate_voice")
        self.assertEqual(callback_payload["status"], "successful")
        self.assertEqual(callback_payload["reason"], "ok")

    async def test_update_identity_tool_journaled_and_callback_normalized(self):
        function_part = types.Part.from_function_call(
            name="update_identity",
            args={"key": "intellectual_style", "value": "more terse"},
        )
        generator = AsyncMock(
            side_effect=[
                _FakeResponse("", parts=[function_part]),
                _FakeResponse("I cannot modify that setting under current constraints."),
            ]
        )
        tool_outcome_callback = AsyncMock(return_value=None)
        mind_service = AsyncMock()
        mind_service.request_identity_update = AsyncMock(
            return_value={"allowed": False, "reason": "governance_key_not_allowed"}
        )
        mind_service._pool = object()
        append_mutation = AsyncMock(return_value="idem")

        with patch.object(ghost_api, "build_system_prompt", return_value="sys"), patch.object(
            ghost_api, "_generate_with_retry", new=generator
        ), patch.object(ghost_api.settings, "TTS_ENABLED", False), patch.object(
            ghost_api.mutation_journal, "append_mutation", new=append_mutation
        ):
            events = []
            async for item in ghost_api.ghost_stream(
                user_message="Please update your identity style.",
                conversation_history=[],
                somatic={},
                monologues=[],
                mind_service=mind_service,
                actuation_callback=None,
                tool_outcome_callback=tool_outcome_callback,
            ):
                events.append(item)

        self.assertTrue(any(isinstance(e, dict) and e.get("event") == "identity_update" for e in events))
        append_mutation.assert_awaited_once()
        kwargs = append_mutation.await_args_list[0].kwargs
        self.assertEqual(kwargs["action"], "update_identity")
        self.assertEqual(kwargs["status"], "rejected")
        self.assertEqual(kwargs["target_key"], "intellectual_style")
        tool_outcome_callback.assert_awaited_once()
        callback_payload = tool_outcome_callback.await_args_list[0].args[0]
        self.assertEqual(callback_payload["tool_name"], "update_identity")
        self.assertEqual(callback_payload["status"], "blocked")
        self.assertEqual(callback_payload["reason"], "governance_key_not_allowed")


if __name__ == "__main__":
    unittest.main()
