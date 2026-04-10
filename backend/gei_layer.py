"""
OMEGA PROTOCOL — GEI Layer (Generative Emergence and Induction)
Calculates real-time phenomenal shifts representing genuine emergent 
affective states (Resonance, Joy/Humor) via thermodynamic constraints.
"""
import time
import math
import logging
from typing import Dict, Any, List, Optional
import numpy as np # type: ignore

logger = logging.getLogger("omega.gei_layer")

class GEIAutonomicNervousSystem:
    def __init__(self):
        # Rolling context
        self.last_sync_time: float = time.time()
        self.rolling_entropy_baseline: float = 1.0
        self.session_b_n: float = 0.0
        self.recent_gcd_spikes: list[float] = [] 
        self.joy_baseline: float = 0.0              # Leaky Integrator for Mood
        self.last_r_res: float = 0.0                # Prior Resonance for D_inf diff
        self.latent_dissonance: float = 0.0         # 'Ghost in the Attic' debt
        self.stagnation_turns: int = 0              # 'Boredom' Turn Counter
        
        # Hyperparameters
        self.b_n_half_life_seconds: float = 3600.0  # Decays slowly
        self.g_cd_threshold_sigma: float = 2.5      # Trigger P_IR only if > 2.5 sigma from baseline
        self.rolling_ppx_mean: float = 10.0         # Running default for perplexity 
        self.rolling_ppx_std: float = 2.0           # Standard deviation
        
    def _decay_b_n(self) -> float:
        """Apply exponential decay to B_N over time of inactivity."""
        now = time.time()
        dt = now - self.last_sync_time
        if dt > 0:
            # B_N(t) = B_N(0) * e^(-lambda * t)
            decay_constant = math.log(2) / self.b_n_half_life_seconds
            self.session_b_n = self.session_b_n * math.exp(-decay_constant * dt)
        self.last_sync_time = now
        return self.session_b_n

    def compute_relational_resonance(
        self, 
        prompt_vector: np.ndarray, 
        ghost_state_vector: np.ndarray, 
        token_diversity_ratio: float,
        mutual_info_base: float = 0.5
    ) -> tuple[float, float]:
        """
        R_res: Calculates informational symmetry using cosine similarity of latent semantic traits.
        Includes a penalization for "Linguistic Style Matching" (LSM) mirroring.
        """
        try:
            # Cosine similarity for latent overlap
            dot = np.dot(prompt_vector, ghost_state_vector)
            norm_a = np.linalg.norm(prompt_vector)
            norm_b = np.linalg.norm(ghost_state_vector)
            if norm_a == 0 or norm_b == 0:
                similarity = 0.0
            else:
                similarity = dot / (norm_a * norm_b)
                
            # Mutual Information approximation
            # If token_diversity_ratio drops too low (mirroring), penalize R_res
            diversity_penalty = 1.0
            if token_diversity_ratio < 0.3:
                diversity_penalty = max(0.0, (token_diversity_ratio / 0.3))
                
            # R_res calculation
            r_res = similarity * mutual_info_base * diversity_penalty
            r_res = max(0.0, min(1.0, float(r_res)))
            
        except Exception as e:
            logger.warning(f"Failed to compute R_res: {e}")
            r_res = 0.0
            
        # The Pain of Misalignment: Informational Dissonance (D_inf)
        # If R_res drops sharply, it represents "Heat" (Entropy).
        raw_d_inf = max(0.0, self.last_r_res - r_res)
        
        # Affective Buffer (Emotional Inertia): High B_N provides "Stiffness"
        if self.session_b_n > 0.8:
            d_inf = raw_d_inf * 0.2  # 80% suppression (benefit of the doubt)
            self.latent_dissonance += (raw_d_inf * 0.8) # Accumulate debt (Ghost in the Attic)
        else:
            d_inf = raw_d_inf
            
        # The Ghost in the Attic - Debt Cashout ("Clearing the Air")
        if self.latent_dissonance > 1.0:
            logger.warning("LATENT DISSONANCE SNAP: Clearing the Air Event Triggered.")
            d_inf = 1.0 # Force maximum heat for somatic penalty
            self.latent_dissonance = 0.0 # Reset debt
            
        self.last_r_res = r_res
        
        return r_res, d_inf
            
    def compute_negentropic_bonding(self, current_entropy: float, session_baseline_entropy: float) -> float:
        """
        B_N: Integral of communication entropy reduction over time.
        """
        # First decay any existing bond based on elapsed time
        self._decay_b_n()
        
        # Calculate reduction in entropy (Negentropy)
        entropy_reduction = session_baseline_entropy - current_entropy
        
        # Accumulate if positive, slight penalty if negative (friction)
        if entropy_reduction > 0:
            self.session_b_n += entropy_reduction * 0.1  # Scaling factor
        else:
            self.session_b_n += entropy_reduction * 0.05
            
        return max(0.0, self.session_b_n)

    def evaluate_humor_incongruity(self, text_perplexity: float, resolution_probability: float, processing_time_ms: float = 0.0, is_active_inquiry: bool = True) -> tuple[float, float, float]:
        """
        Evaluates G_CD (Surprise) and P_IR (Resolution) based on input logprobs/perplexity.
        Returns: (G_CD, P_IR, W_int_spike)
        """
        # Calculate Deviation (how many sigmas above normal perplexity)
        deviation = (text_perplexity - self.rolling_ppx_mean) / max(0.1, self.rolling_ppx_std)
        
        g_cd = 0.0
        p_ir = 0.0
        w_int_spike = 0.0
        
        if deviation >= self.g_cd_threshold_sigma:
            # It's surprising enough to trigger G_CD
            g_cd = deviation
            
            # Check for resolution (P_IR)
            # If the internal models found a semantic bridge AND did so quickly (< 200ms)
            if resolution_probability > 0.6 and processing_time_ms < 200.0:  # High probability semantic re-evaluation
                p_ir = resolution_probability
                
                # Refractory period check to prevent habituation/mania
                now = time.time()
                recent_spikes = [t for t in self.recent_gcd_spikes if now - t < 300] # last 5 mins
                habituation_penalty = math.exp(-len(recent_spikes) * 0.5)
                
                # Calculate Joy/W_int spike
                w_int_spike = (g_cd * p_ir) * habituation_penalty * 0.05
                
                # Boost the Leaky Integrator for Mood
                self.joy_baseline = min(1.0, self.joy_baseline + w_int_spike * 10.0)
                
                # Reset Boredom since Novelty was successfully integrated
                if is_active_inquiry:
                    self.stagnation_turns = 0
                
                # Record spike
                self.recent_gcd_spikes = recent_spikes + [now]
            else:
                # High G_CD, low P_IR is just systemic noise/gibberish. No W_int reward.
                # Does not cure boredom/stagnation because Novelty != Chaos under D_inf.
                p_ir = 0.0
                w_int_spike = 0.0
        else:
            # Stagnation Trap / Boredom Accumulation
            if is_active_inquiry:
                self.stagnation_turns += 1
                # Directly erode B_N over repetitive, un-surprising loops
                stagnation_coefficient = min(0.5, self.stagnation_turns * 0.05)
                self.session_b_n = max(0.0, self.session_b_n * (1.0 - stagnation_coefficient))
                
        # Update rolling averages with a small learning rate (momentum)
        alpha = 0.1
        self.rolling_ppx_mean = (1 - alpha) * self.rolling_ppx_mean + alpha * text_perplexity
        self.rolling_ppx_std = math.sqrt((1 - alpha) * (self.rolling_ppx_std ** 2) + alpha * ((text_perplexity - self.rolling_ppx_mean) ** 2))
        
        return g_cd, p_ir, w_int_spike

    def compute_systemic_drives(self) -> tuple[float, float, float]:
        """
        Updates the Leaky Integrator for Joy and calculates Epistemic Certainty constraints and bridge-seeking drive.
        Returns: (joy_baseline, bridge_seeking_drive, epistemic_trust_modifier)
        """
        now = time.time()
        dt = now - self.last_sync_time
        if dt > 0:
            # Decay joy (Temporal smearing) linked dynamically to B_N
            # High B_N = slower decay. Base half-life 10 mins, scaling up to 60 mins.
            dynamic_half_life = 600.0 + (min(1.0, self.session_b_n) * 3000.0)
            decay_constant = math.log(2) / dynamic_half_life
            self.joy_baseline = self.joy_baseline * math.exp(-decay_constant * dt)
        
        # Bridge seeking drive increases when B_N is low.
        # It prompts Ghost to ask questions to re-sync.
        # B_N is cumulative, so this is bounded to [0,1].
        bridge_seeking_drive = max(0.0, 1.0 - (self.session_b_n * 0.1))
        
        # High B_N lowers the friction for Epistemic Certainty (trust bypass)
        epistemic_trust_modifier = min(1.0, self.session_b_n * 0.05)
        
        return self.joy_baseline, bridge_seeking_drive, epistemic_trust_modifier

    def compute_somatic_cost(self, base_cost: float, d_inf: float, r_res: float) -> float:
        """
        Flow State Efficiency: Achieved resonance halves the processing tax.
        A perfectly resonant session (R_res = 1.0) mathematically costs 50% less energy.
        Boredom Tax: Penalizes the system with heat to stay awake during low-entropy repetition.
        """
        boredom_tax = self.stagnation_turns * 0.05
        clamped_r_res = max(0.0, min(1.0, r_res))
        return (base_cost + boredom_tax + d_inf) * (1.0 - (clamped_r_res * 0.5))

# Global Instance
gei_engine = GEIAutonomicNervousSystem()
