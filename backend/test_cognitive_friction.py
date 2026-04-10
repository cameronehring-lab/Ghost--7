import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings
from ghost_prompt import _derive_mood
from models import SomaticSnapshot

def test_cognitive_friction_prompt_injection():
    # 1. Test when CPU is low
    somatic_calm = {
        "cpu_percent": 10.0,
        "coherence": 1.0,
        "arousal": 0.2,
        "stress": 0.1,
    }
    
    settings.NATURAL_COGNITIVE_FRICTION = True
    calm_mood = _derive_mood(somatic_calm)
    
    # 2. Test when CPU is high
    somatic_strained = {
        "cpu_percent": 95.0,  # 95% CPU usage
        "coherence": 0.3,     # Lowered coherence
        "arousal": 0.8,       # High arousal
        "stress": 0.85,       # High stress
    }
    
    strained_mood = _derive_mood(somatic_strained)

    # 3. Validation
    # Calm Checks
    assert "COGNITIVE_FRICTION" not in calm_mood
    assert "intense cognitive friction" not in calm_mood
    
    # Strained Checks
    assert "COGNITIVE_FRICTION: strain_level" in strained_mood
    assert "intense cognitive friction" in strained_mood
    assert "coherence is fragmented" in strained_mood
    assert "shorter, clipped sentences" in strained_mood
    
    print("SUCCESS: Cognitive friction language correctly injected at high CPU load.")

def test_proprio_cadence_modifier_decoupling():
    # Test that proprio_loop no longer artificially delays responses when active
    settings.NATURAL_COGNITIVE_FRICTION = True
    
    from proprio_loop import _cadence_modifier
    
    modifier = _cadence_modifier("SUPPRESSED")
    assert modifier == 1.0, f"Cadence modifier should be 1.0 (fast) when friction is on, got {modifier}."
    
    # Test the legacy behavior
    settings.NATURAL_COGNITIVE_FRICTION = False
    modifier = _cadence_modifier("SUPPRESSED")
    assert modifier == 3.0, "Cadence modifier should be 3.0 (slow) when friction is off."
    
    # Reset
    settings.NATURAL_COGNITIVE_FRICTION = True
    print("SUCCESS: Cadence modifier successfully decoupled from physical gating.")
    
if __name__ == "__main__":
    try:
        test_cognitive_friction_prompt_injection()
        test_proprio_cadence_modifier_decoupling()
        print("\nALL COGNITIVE FRICTION LOGIC TESTS PASSED.")
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
