"""
OMEGA PROTOCOL — Governance Engine
Calculates system tiers and policies based on IIT and somatic telemetry.
"""

import time
import logging
from typing import List, Optional, Dict, Any
from models import GovernanceTier, GovernanceDecision, GenerationPolicy, ActuationPolicy, SelfModPolicy, GateState

logger = logging.getLogger("omega.governance")

class GovernanceEngine:
    def __init__(self, settings):
        self.settings = settings
        self.history: List[GovernanceDecision] = []
        self.max_history = 20
        self.current_tier = GovernanceTier.NOMINAL
        self._bad_windows = 0
        self._good_windows = 0
        self._promotion_threshold = 2  # cycles to promote to more restrictive tier
        self._demotion_threshold = 5   # cycles to demote to less restrictive tier
        
    def assess(self, iit_record: Dict[str, Any], somatic: Dict[str, Any], run_id: str) -> GovernanceDecision:
        """
        Calculates the system governance tier based on IIT, somatic, and proprio stats.
        Implements hysteresis to prevent oscillation.
        """
        # 1. Selection Logic (Raw target)
        metrics = iit_record.get("metrics", {})
        phi_proxy = metrics.get("phi_proxy", 1.0)
        completeness = iit_record.get("substrate_completeness_score", 6)
        
        coherence = somatic.get("coherence", 1.0)
        stress = somatic.get("stress", 0.0)
        mental_strain = max(
            float(somatic.get("mental_strain", 0.0) or 0.0),
            float(somatic.get("sim_strain", 0.0) or 0.0),
        )
        effective_strain = max(float(stress or 0.0), mental_strain)
        # Handle dict or string for gate_state
        gate_state_raw = somatic.get("gate_state", "OPEN")
        if isinstance(gate_state_raw, GateState):
            gate_state = gate_state_raw.value
        else:
            gate_state = str(gate_state_raw).upper()
            
        raw_target = GovernanceTier.NOMINAL
        reasons = []
        
        # Check for RECOVERY conditions (highest priority)
        if coherence < 0.2 or gate_state == "SUPPRESSED" or phi_proxy < 0.2 or mental_strain > 0.92:
            raw_target = GovernanceTier.RECOVERY
            reasons.append(
                "Critical instability "
                f"(coher:{coherence:.2f}, gate:{gate_state}, phi:{phi_proxy:.2f}, strain:{mental_strain:.2f})"
            )
        # Check for STABILIZE conditions
        elif coherence < 0.4 or gate_state == "THROTTLED" or effective_strain > 0.8:
            raw_target = GovernanceTier.STABILIZE
            reasons.append(
                "Significant strain "
                f"(coher:{coherence:.2f}, gate:{gate_state}, stress:{stress:.2f}, mental:{mental_strain:.2f})"
            )
        # Check for CAUTION conditions
        elif effective_strain > 0.6 or completeness < 4 or phi_proxy < 0.5:
            raw_target = GovernanceTier.CAUTION
            reasons.append(
                "Degraded state or elevated strain "
                f"(stress:{stress:.2f}, mental:{mental_strain:.2f}, compl:{completeness}, phi:{phi_proxy:.2f})"
            )
            
        # 2. Hysteresis Logic
        # Promotion (to more restrictive tiers) is faster than demotion.
        tier_order = {
            GovernanceTier.NOMINAL: 0,
            GovernanceTier.CAUTION: 1,
            GovernanceTier.STABILIZE: 2,
            GovernanceTier.RECOVERY: 3
        }
        
        current_val = tier_order[self.current_tier]
        target_val = tier_order[raw_target]
        
        final_tier = self.current_tier
        
        if target_val > current_val:
            self._bad_windows += 1
            self._good_windows = 0
            if self._bad_windows >= self._promotion_threshold:
                final_tier = raw_target
                logger.warning(f"Governance PROMOTION: {self.current_tier} -> {final_tier} (reasons: {reasons})")
                self._bad_windows = 0
        elif target_val < current_val:
            self._good_windows += 1
            self._bad_windows = 0
            if self._good_windows >= self._demotion_threshold:
                final_tier = raw_target
                logger.info(f"Governance DEMOTION: {self.current_tier} -> {final_tier}")
                self._good_windows = 0
        else:
            self._bad_windows = 0
            self._good_windows = 0
            
        self.current_tier = final_tier
        
        # 3. Generate Policies
        gen_policy = self._build_generation_policy(final_tier)
        act_policy = self._build_actuation_policy(final_tier)
        sm_policy = self._build_self_mod_policy(final_tier, somatic)
        
        decision = GovernanceDecision(
            run_id=run_id,
            mode=self.settings.IIT_MODE,
            tier=final_tier,
            applied=(self.settings.IIT_MODE == "soft"),
            reasons=reasons,
            generation_policy=gen_policy,
            actuation_policy=act_policy,
            self_mod_policy=sm_policy,
            ttl_seconds=60.0
        )
        
        self.history.append(decision)
        if len(self.history) > self.max_history:
            self.history.pop(0)
            
        return decision

    def _build_generation_policy(self, tier: GovernanceTier) -> GenerationPolicy:
        if tier == GovernanceTier.NOMINAL:
            return GenerationPolicy()
        elif tier == GovernanceTier.CAUTION:
            return GenerationPolicy(temperature_cap=0.75, max_tokens_cap=4096)
        elif tier == GovernanceTier.STABILIZE:
            return GenerationPolicy(temperature_cap=0.5, max_tokens_cap=1200, max_sentences=4)
        elif tier == GovernanceTier.RECOVERY:
            return GenerationPolicy(temperature_cap=0.2, max_tokens_cap=400, max_sentences=2, require_literal_mode=True)
        return GenerationPolicy()

    def _build_actuation_policy(self, tier: GovernanceTier) -> ActuationPolicy:
        if tier == GovernanceTier.NOMINAL:
            return ActuationPolicy()
        elif tier == GovernanceTier.CAUTION:
            return ActuationPolicy(denylist=["cpu_governor", "kill_process"])
        elif tier == GovernanceTier.STABILIZE:
            return ActuationPolicy(allowlist=["power_save", "enter_quietude", "exit_quietude"])
        elif tier == GovernanceTier.RECOVERY:
            return ActuationPolicy(allowlist=["enter_quietude"], auto_actions=["enter_quietude"])
        return ActuationPolicy()

    def _build_self_mod_policy(self, tier: GovernanceTier, somatic: Dict[str, Any]) -> SelfModPolicy:
        w_rate = float(somatic.get("w_int_rate") or 0.0)
        ade = somatic.get("ade_event")
        
        # Base policy with thermodynamic markers
        policy = SelfModPolicy(w_int_rate=w_rate, ade_event=ade)
        
        if tier == GovernanceTier.NOMINAL:
            pass
        elif tier == GovernanceTier.CAUTION:
            policy.writes_per_hour_cap = 10
        elif tier == GovernanceTier.STABILIZE:
            policy.writes_per_hour_cap = 2
            policy.allowed_key_classes = ["communication_style", "communication_preference"]
        elif tier == GovernanceTier.RECOVERY:
            policy.writes_per_hour_cap = 0
            policy.freeze_until = time.time() + 600
        return policy
