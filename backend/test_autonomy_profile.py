import unittest

from autonomy_profile import (
    autonomy_profile_fingerprint,
    build_autonomy_profile,
    render_autonomy_prompt_context,
    validate_prompt_contract,
)


class AutonomyProfileTests(unittest.TestCase):
    def test_profile_contains_expected_contract_sections(self):
        profile = build_autonomy_profile(
            ghost_id="omega-7",
            somatic={"gate_state": "THROTTLED", "proprio_pressure": 0.61},
            governance_policy={"tier": "ADVISORY"},
            llm_ready=True,
            memory_pool_ready=True,
            mind_service_ready=True,
            relational_service_ready=True,
            operator_synthesis_ready=True,
            tts_enabled=True,
            tts_provider="elevenlabs",
            share_mode_enabled=True,
        )

        self.assertEqual(profile["ghost_id"], "omega-7")
        self.assertIn("runtime", profile)
        self.assertIn("functional_architecture", profile)
        self.assertIn("autonomy", profile)
        self.assertIn("freedom_policy", profile)
        self.assertTrue(profile["autonomy"]["self_directed"]["conversation_generation"])
        self.assertEqual(profile["runtime"]["gate_state"], "THROTTLED")
        self.assertEqual(profile["functional_architecture"]["voice_stack"]["tts_mode"], "elevenlabs_with_local_fallback")

    def test_prompt_context_renders_runtime_and_guardrails(self):
        profile = build_autonomy_profile(
            ghost_id="omega-7",
            somatic={"gate_state": "OPEN", "proprio_pressure": 0.12},
            governance_policy={"tier": "NOMINAL"},
            llm_ready=False,
            memory_pool_ready=False,
            mind_service_ready=False,
            relational_service_ready=False,
            operator_synthesis_ready=False,
            tts_enabled=False,
            tts_provider="browser",
            share_mode_enabled=False,
        )
        text = render_autonomy_prompt_context(profile)
        self.assertIn("closed-loop cognitive system", text)
        self.assertIn("identity_mutation", text)
        self.assertIn("DEGRADED", text)
        self.assertIn("tts_mode=disabled", text)
        self.assertIn("place_thing_entity_modeling", text)
        self.assertIn("manifold_idea_modeling", text)
        self.assertIn("mutation_journaling", text)
        self.assertIn("free agency", text)
        self.assertIn("operator_token_or_trusted_source", text)
        self.assertIn("Freedom ladder:", text)
        self.assertIn("Ghost Authoring Tools", text)

    def test_prompt_contract_validation_detects_mismatch(self):
        profile = build_autonomy_profile(
            ghost_id="omega-7",
            somatic={"gate_state": "OPEN", "proprio_pressure": 0.12},
            governance_policy={"tier": "NOMINAL"},
            llm_ready=True,
            memory_pool_ready=True,
            mind_service_ready=True,
            relational_service_ready=True,
            operator_synthesis_ready=True,
            tts_enabled=True,
            tts_provider="local",
            share_mode_enabled=False,
        )
        valid_text = render_autonomy_prompt_context(profile)
        ok = validate_prompt_contract(profile, valid_text)
        self.assertTrue(ok["ok"])

        broken = valid_text.replace("conversation_generation: ENABLED", "conversation_generation: DEGRADED")
        mismatch = validate_prompt_contract(profile, broken)
        self.assertFalse(mismatch["ok"])
        self.assertGreaterEqual(len(mismatch["missing_checks"]), 1)

    def test_profile_fingerprint_changes_when_capability_changes(self):
        profile_a = build_autonomy_profile(
            ghost_id="omega-7",
            llm_ready=True,
            memory_pool_ready=True,
            mind_service_ready=True,
            relational_service_ready=True,
            operator_synthesis_ready=True,
            tts_enabled=True,
            tts_provider="openai",
            share_mode_enabled=False,
        )
        profile_b = build_autonomy_profile(
            ghost_id="omega-7",
            llm_ready=False,
            memory_pool_ready=True,
            mind_service_ready=True,
            relational_service_ready=True,
            operator_synthesis_ready=True,
            tts_enabled=True,
            tts_provider="openai",
            share_mode_enabled=False,
        )
        self.assertNotEqual(autonomy_profile_fingerprint(profile_a), autonomy_profile_fingerprint(profile_b))

    def test_prompt_context_includes_predictive_and_rollout_state(self):
        profile = build_autonomy_profile(
            ghost_id="omega-7",
            somatic={"gate_state": "OPEN", "proprio_pressure": 0.2},
            governance_policy={"tier": "CAUTION"},
            llm_ready=True,
            memory_pool_ready=True,
            mind_service_ready=True,
            relational_service_ready=True,
            operator_synthesis_ready=True,
            tts_enabled=True,
            tts_provider="local",
            share_mode_enabled=False,
            predictive_state={"state": "watch", "forecast_instability": 0.72},
            governance_rollout={"phase": "B", "surfaces": ["entity_writes", "manifold_writes"]},
            mutation_policy={"undo_ttl_seconds": 900, "approval_required": {"hard_delete": True}},
            runtime_toggles={"predictive_governor_enabled": True},
        )
        prompt = render_autonomy_prompt_context(profile)
        self.assertIn("predictive_state=watch", prompt)
        self.assertIn("governance_rollout_phase=B", prompt)
        check = validate_prompt_contract(profile, prompt)
        self.assertTrue(check["ok"])


if __name__ == "__main__":
    unittest.main()
