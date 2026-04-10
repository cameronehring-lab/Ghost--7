import unittest
from contextlib import ExitStack
from unittest.mock import patch

from config import settings
from freedom_policy import build_freedom_policy, contact_target_allowed, is_core_identity_key


class FreedomPolicyTests(unittest.TestCase):
    def _policy_patches(self):
        return {
            "GHOST_FREEDOM_COGNITIVE_AUTONOMY": True,
            "GHOST_FREEDOM_REPOSITORY_AUTONOMY": True,
            "GHOST_FREEDOM_DOCUMENT_AUTHORING_AUTONOMY": True,
            "GHOST_FREEDOM_OPERATOR_CONTACT_AUTONOMY": True,
            "GHOST_FREEDOM_THIRD_PARTY_CONTACT_AUTONOMY": False,
            "GHOST_FREEDOM_SUBSTRATE_AUTONOMY": False,
            "GHOST_FREEDOM_CORE_IDENTITY_AUTONOMY": False,
            "RRD2_HIGH_IMPACT_KEYS": "self_model,philosophical_stance,understanding_of_operator,conceptual_frameworks",
        }

    def test_default_ladder_is_enabled_for_cognition_repository_authoring(self):
        with ExitStack() as stack:
            for key, value in self._policy_patches().items():
                stack.enter_context(patch.object(settings, key, value, create=True))
            policy = build_freedom_policy(
                somatic={"gate_state": "OPEN", "coherence": 0.91},
                governance_policy={"tier": "NOMINAL"},
            )

        self.assertTrue(policy["configured"]["cognitive_autonomy"])
        self.assertTrue(policy["configured"]["repository_autonomy"])
        self.assertTrue(policy["configured"]["document_authoring_autonomy"])
        self.assertTrue(policy["configured"]["operator_contact_autonomy"])
        self.assertFalse(policy["configured"]["third_party_contact_autonomy"])
        self.assertFalse(policy["configured"]["substrate_autonomy"])
        self.assertFalse(policy["configured"]["core_identity_autonomy"])
        self.assertTrue(policy["effective"]["repository_autonomy"])
        self.assertTrue(policy["effective"]["document_authoring_autonomy"])

    def test_suppressed_gate_disables_autonomous_actions(self):
        with ExitStack() as stack:
            for key, value in self._policy_patches().items():
                stack.enter_context(patch.object(settings, key, value, create=True))
            policy = build_freedom_policy(
                somatic={"gate_state": "SUPPRESSED", "coherence": 0.9},
                governance_policy={"tier": "NOMINAL"},
            )

        self.assertFalse(policy["effective"]["cognitive_autonomy"])
        self.assertFalse(policy["effective"]["repository_autonomy"])
        self.assertFalse(policy["effective"]["document_authoring_autonomy"])
        self.assertFalse(policy["effective"]["operator_contact_autonomy"])
        self.assertIn("suppressed_gate", policy["narrowing_reasons"])

    def test_low_coherence_narrows_contact_and_authoring(self):
        with ExitStack() as stack:
            for key, value in self._policy_patches().items():
                stack.enter_context(patch.object(settings, key, value, create=True))
            policy = build_freedom_policy(
                somatic={"gate_state": "OPEN", "coherence": 0.35},
                governance_policy={"tier": "NOMINAL"},
            )

        self.assertTrue(policy["effective"]["cognitive_autonomy"])
        self.assertTrue(policy["effective"]["repository_autonomy"])
        self.assertFalse(policy["effective"]["document_authoring_autonomy"])
        self.assertFalse(policy["effective"]["operator_contact_autonomy"])
        self.assertIn("low_coherence", policy["narrowing_reasons"])

    def test_operator_contact_remains_operator_only_by_default(self):
        with ExitStack() as stack:
            for key, value in self._policy_patches().items():
                stack.enter_context(patch.object(settings, key, value, create=True))
            policy = build_freedom_policy(
                somatic={"gate_state": "OPEN", "coherence": 0.9},
                governance_policy={"tier": "NOMINAL"},
            )

        self.assertTrue(contact_target_allowed(policy, "operator"))
        self.assertFalse(contact_target_allowed(policy, "alice"))

    def test_core_identity_detection_uses_high_impact_keys(self):
        with patch.object(settings, "RRD2_HIGH_IMPACT_KEYS", "self_model,conceptual_frameworks,core_axioms", create=True):
            self.assertTrue(is_core_identity_key("self_model"))
            self.assertTrue(is_core_identity_key("core_axioms"))
            self.assertFalse(is_core_identity_key("intellectual_style"))


if __name__ == "__main__":
    unittest.main()
