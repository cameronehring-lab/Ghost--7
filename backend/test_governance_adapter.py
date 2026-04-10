import unittest
from unittest.mock import patch

import governance_adapter


class GovernanceAdapterTests(unittest.TestCase):
    def test_route_enforce_block_in_phase_c_when_soft_active(self):
        with patch.object(governance_adapter.settings, "IIT_MODE", "soft"), patch.object(
            governance_adapter.settings,
            "GOVERNANCE_ENFORCEMENT_SURFACES",
            "generation,actuation,entity_writes",
        ):
            route = governance_adapter.route_for_surface(
                "entity_writes",
                governance_policy={"applied": True},
                rrd2_gate={"phase": "C", "would_block": True, "enforce_block": True},
            )
            self.assertEqual(route["route"], governance_adapter.ENFORCE_BLOCK)
            self.assertTrue(route["scoped"])

    def test_route_shadow_only_when_soft_inactive(self):
        with patch.object(governance_adapter.settings, "IIT_MODE", "advisory"), patch.object(
            governance_adapter.settings,
            "GOVERNANCE_ENFORCEMENT_SURFACES",
            "generation,actuation",
        ):
            route = governance_adapter.route_for_surface(
                "generation",
                governance_policy={"applied": False},
                rrd2_gate={"phase": "C", "would_block": True, "enforce_block": True},
            )
            self.assertEqual(route["route"], governance_adapter.SHADOW_ROUTE)

    def test_surface_out_of_scope_allows(self):
        with patch.object(governance_adapter.settings, "IIT_MODE", "soft"), patch.object(
            governance_adapter.settings,
            "GOVERNANCE_ENFORCEMENT_SURFACES",
            "generation",
        ):
            route = governance_adapter.route_for_surface(
                "entity_writes",
                governance_policy={"applied": True},
                rrd2_gate={"phase": "C", "would_block": True, "enforce_block": True},
            )
            self.assertEqual(route["route"], governance_adapter.ALLOW)
            self.assertFalse(route["scoped"])

    def test_freeze_until_blocks_in_soft_mode(self):
        """freeze_until in the future must return ENFORCE_BLOCK when soft mode is active."""
        future_ts = __import__("time").time() + 3600
        with patch.object(governance_adapter.settings, "IIT_MODE", "soft"), patch.object(
            governance_adapter.settings,
            "GOVERNANCE_ENFORCEMENT_SURFACES",
            "generation,actuation,entity_writes",
        ):
            route = governance_adapter.route_for_surface(
                "generation",
                governance_policy={"applied": True, "freeze_until": future_ts},
                rrd2_gate={"phase": "A"},
            )
            self.assertEqual(route["route"], governance_adapter.ENFORCE_BLOCK)
            self.assertIn("governance_freeze_active", route["reasons"])

    def test_freeze_until_shadow_routes_when_soft_inactive(self):
        """freeze_until in the future must return SHADOW_ROUTE when soft mode is inactive."""
        future_ts = __import__("time").time() + 3600
        with patch.object(governance_adapter.settings, "IIT_MODE", "advisory"), patch.object(
            governance_adapter.settings,
            "GOVERNANCE_ENFORCEMENT_SURFACES",
            "generation,actuation",
        ):
            route = governance_adapter.route_for_surface(
                "actuation",
                governance_policy={"applied": False, "freeze_until": future_ts},
                rrd2_gate={"phase": "A"},
            )
            self.assertEqual(route["route"], governance_adapter.SHADOW_ROUTE)
            self.assertIn("governance_freeze_active", route["reasons"])

    def test_freeze_until_expired_does_not_block(self):
        """freeze_until in the past must not trigger a freeze."""
        past_ts = __import__("time").time() - 1
        with patch.object(governance_adapter.settings, "IIT_MODE", "advisory"), patch.object(
            governance_adapter.settings,
            "GOVERNANCE_ENFORCEMENT_SURFACES",
            "generation",
        ):
            route = governance_adapter.route_for_surface(
                "generation",
                governance_policy={"applied": False, "freeze_until": past_ts},
                rrd2_gate={"phase": "A"},
            )
            self.assertNotIn("governance_freeze_active", route["reasons"])

    def test_messaging_alias_maps_to_surface(self):
        with patch.object(governance_adapter.settings, "IIT_MODE", "soft"), patch.object(
            governance_adapter.settings,
            "GOVERNANCE_ENFORCEMENT_SURFACES",
            "generation,messaging",
        ):
            route = governance_adapter.route_for_surface(
                "messages",
                governance_policy={"applied": True},
                rrd2_gate={"phase": "A", "would_block": False, "enforce_block": False},
            )
            self.assertEqual(route["surface"], "messaging")
            self.assertTrue(route["scoped"])


if __name__ == "__main__":
    unittest.main()
