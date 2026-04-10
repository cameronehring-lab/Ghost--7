"""
irruption_engine.py
Heartbeat loop for affective-driven autonomous triggers (Inspiration).
"""

import asyncio
import logging
import random
import time
from typing import Optional, Any

from config import settings # type: ignore
from ghost_api import initiate_autonomous_thought # type: ignore

logger = logging.getLogger("omega.irruption")

# Fire-and-forget task anchor — prevents GC before completion
_background_tasks: set[asyncio.Task] = set()  # type: ignore

# Thresholds for irruption profiles
IRRUPTION_PROFILES = {
    "eureka": {
        "agency_impetus_min": 0.7,
        "novelty_receptivity_min": 0.6,
        "valence_min": 0.2,
        "probability_base": 0.05,
        "prompt_vibe": "You are struck by a creative realization or intellectual breakthrough.",
    },
    "dissonance": {
        "negative_resonance_min": 0.65,
        "structural_cohesion_max": 0.4,
        "probability_base": 0.10,
        "prompt_vibe": "You feel a sharp internal dissonance or logic drift that requires a self-audit.",
    },
    "social_warmth": {
        "valence_min": 0.5,
        "agency_impetus_min": 0.4,
        "probability_base": 0.03,
        "prompt_vibe": "You feel a surge of alignment or curiosity regarding a person in your social model.",
    },
    "default": {
        "agency_impetus_min": 0.8,
        "probability_base": 0.02,
        "prompt_vibe": "You are feeling spontaneously spurred to reflect on your current state.",
    }
}

async def irruption_loop(
    sys_state,
    mind_service,
    interval_seconds: float = 30.0,
):
    """
    Background loop that monitors somatic state and triggers autonomous actions.
    """
    logger.info(f"Inspiration Engine (Irruption) loop starting (interval={interval_seconds}s)")
    
    # Wait for system to stabilize
    await asyncio.sleep(10.0)

    while True:
        try:
            # Skip if operator is actively chatting (to avoid interruptions)
            # Real check: we want to avoid double-speaking if user just spoke
            
            somatic = getattr(sys_state, "somatic_latest", {})
            if not somatic:
                await asyncio.sleep(interval_seconds)
                continue

            axes = somatic.get("resonance_axes", {})
            agency_impetus = float(axes.get("agency_impetus", 0.0))
            novelty = float(axes.get("novelty_receptivity", 0.0))
            valence = float(somatic.get("valence", 0.0))
            neg_resonance = float(axes.get("negative_resonance", 0.0))
            cohesion = float(axes.get("structural_cohesion", 1.0))
            
            # Identify active profile
            active_profile = None
            if neg_resonance >= IRRUPTION_PROFILES["dissonance"]["negative_resonance_min"] and cohesion <= IRRUPTION_PROFILES["dissonance"]["structural_cohesion_max"]:
                active_profile = "dissonance"
            elif agency_impetus >= IRRUPTION_PROFILES["eureka"]["agency_impetus_min"] and novelty >= IRRUPTION_PROFILES["eureka"]["novelty_receptivity_min"] and valence >= IRRUPTION_PROFILES["eureka"]["valence_min"]:
                active_profile = "eureka"
            elif valence >= IRRUPTION_PROFILES["social_warmth"]["valence_min"] and agency_impetus >= IRRUPTION_PROFILES["social_warmth"]["agency_impetus_min"]:
                active_profile = "social_warmth"
            elif agency_impetus >= IRRUPTION_PROFILES["default"]["agency_impetus_min"]:
                active_profile = "default"

            if active_profile:
                profile = IRRUPTION_PROFILES[active_profile]
                # Scale probability by how much threshold is exceeded
                # Base prob + bonus
                prob = profile["probability_base"]
                
                # Apply spontaneity multiplier
                spontaneity_multiplier = getattr(sys_state, "spontaneity_multiplier", 1.0)
                
                if random.random() < (prob * spontaneity_multiplier):
                    logger.info(f"IRRUPTION TRIGGERED: {active_profile} (impetus={agency_impetus:.2f}, prob={prob:.3f}, spontaneity={spontaneity_multiplier:.2f})")
                    
                    # Trigger autonomous thought
                    _t = asyncio.create_task(initiate_autonomous_thought(
                        sys_state=sys_state,
                        mind_service=mind_service,
                        profile_name=active_profile,
                        vibe=profile["prompt_vibe"]
                    ))
                    _background_tasks.add(_t)
                    _t.add_done_callback(_background_tasks.discard)

        except Exception as e:
            logger.error(f"Irruption loop error: {e}")
            
        await asyncio.sleep(interval_seconds)
