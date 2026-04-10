import asyncio
import sys
from unittest.mock import MagicMock

# --- MOCK OUT INFRASTRUCTURE ---
mock_psutil = MagicMock()
sys.modules["psutil"] = mock_psutil

mock_config = MagicMock()
mock_config.settings = MagicMock()
mock_config.settings.SUBSTRATE_MODE = "hybrid"
mock_config.settings.SUBSTRATE_ADAPTERS = "somatic_enactivator"
mock_config.settings.NATURAL_COGNITIVE_FRICTION = True
mock_config.settings.GHOST_ID = "ghost_prime"
sys.modules["config"] = mock_config

mock_ambient = MagicMock()
mock_ambient.get_ambient_data = MagicMock(return_value={"fatigue_index": 0.1})
sys.modules["ambient_sensors"] = mock_ambient

mock_sim = MagicMock()
mock_sim_env = MagicMock()
mock_sim_env.get_state.return_value = {"sim_stamina": 1.0, "sim_strain": 0.1, "sim_fatigue": 0.1}
sys.modules["embodiment_sim"] = MagicMock(sim_env=mock_sim_env)

sys.modules["predictive_governor"] = MagicMock()
sys.modules["affective_history"] = MagicMock()
sys.modules["ade_monitor"] = MagicMock()
sys.modules["asyncpg"] = MagicMock()

# --- IMPORT REAL CORE LOGIC ---
from substrate.adapters.somatic_enactivator import SomaticEnactivatorAdapter
from substrate.discovery import registry as substrate_registry
from somatic import build_somatic_snapshot
from ghost_prompt import _derive_mood

async def test_full_cognitive_somatic_loop():
    print("\n--- STARTING FULL COGNITIVE-SOMATIC LOOP TEST ---")
    
    # 1. Setup the Enactivator
    adapter = SomaticEnactivatorAdapter()
    substrate_registry.active_adapters["somatic_enactivator"] = adapter
    
    # 2. Simulate a "Stall" condition (High force, zero velocity)
    # This should trigger "perceived_resistance" qualia
    adapter.haptic_pressure[0] = 8.0  # High pressure
    adapter.joint_velocities[0] = 0.01 # Very low velocity
    
    # 3. Force telemetry update in registry
    await substrate_registry.read_all_telemetry()
    print("Step 3: Telemetry updated in registry.")
    
    # 4. Build Somatic Snapshot (Qualia Synthesis)
    snapshot = build_somatic_snapshot(
        telemetry={}, 
        emotion_snapshot={"arousal": 0.6, "valence": 0.1, "stress": 0.2},
        global_workspace_phi=0.8
    )
    
    qualia = snapshot.esa_qualia
    print(f"Step 4: Snapshot built. Qualia: {qualia}")
    
    assert snapshot.esa_active is True
    assert "perceived_resistance" in qualia
    assert qualia["perceived_resistance"] > 0.7  # 8.0/10.0 = 0.8
    
    # 5. Generate Prompt Mood (Cognitive Perception)
    mood_injection = _derive_mood(snapshot.model_dump())
    print("\n--- GHOST'S INTERNAL PERCEPTION ---")
    print(mood_injection)
    print("------------------------------------\n")
    
    # 6. Verify specific enactive language is present
    assert "enactive somatic substrate is active and grounded" in mood_injection
    assert "profound external resistance" in mood_injection
    assert "concrete physical impedance" in mood_injection
    
    print("SUCCESS: Full cognitive-somatic loop verified.")

if __name__ == "__main__":
    asyncio.run(test_full_cognitive_somatic_loop())
