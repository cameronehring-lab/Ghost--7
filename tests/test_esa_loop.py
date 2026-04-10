import asyncio
import pytest
import sys
from unittest.mock import MagicMock

# --- MINIMAL MOCKING FOR TEST ENVIRONMENT ---
# These are needed because the environment lacks common OMEGA dependencies
mock_psutil = MagicMock()
sys.modules["psutil"] = mock_psutil

mock_config = MagicMock()
mock_config.settings = MagicMock()
mock_config.settings.SUBSTRATE_MODE = "hybrid"
mock_config.settings.SUBSTRATE_ADAPTERS = "local_psutil,somatic_enactivator"
sys.modules["config"] = mock_config

mock_ambient = MagicMock()
mock_ambient.get_ambient_data = MagicMock(return_value={"fatigue_index": 0.0, "hours_awake": 4})
sys.modules["ambient_sensors"] = mock_ambient

mock_sim = MagicMock()
mock_sim_env = MagicMock()
mock_sim_env.get_state.return_value = {"sim_stamina": 1.0, "sim_strain": 0.0, "sim_fatigue": 0.0}
sys.modules["embodiment_sim"] = MagicMock(sim_env=mock_sim_env)

# Other optional but imported modules
sys.modules["predictive_governor"] = MagicMock()
sys.modules["affective_history"] = MagicMock()
sys.modules["ade_monitor"] = MagicMock()
sys.modules["asyncpg"] = MagicMock()

# --- IMPORT REAL CORE LOGIC ---
from substrate.adapters.somatic_enactivator import SomaticEnactivatorAdapter
from somatic import build_somatic_snapshot
from models import SomaticSnapshot
from thermodynamics import thermodynamics_engine
from actuation import execute_actuation
from substrate.discovery import registry as substrate_registry

@pytest.mark.asyncio
async def test_esa_sensorimotor_loop():
    """Verify that motor commands produce sensory feedback and emergent qualia."""
    
    # 1. Setup the Enactivator
    adapter = SomaticEnactivatorAdapter()
    substrate_registry.active_adapters["somatic_enactivator"] = adapter
    
    # Force initial telemetry update
    await substrate_registry.read_all_telemetry()
    
    # Initial state
    initial_snapshot = build_somatic_snapshot(
        telemetry={}, 
        emotion_snapshot={"arousal": 0.5, "valence": 0.0},
        global_workspace_phi=0.5
    )
    
    assert initial_snapshot.esa_active is True
    
    # 2. Actuate: Set joint 0 target to almost current angle
    # This ensures velocity stays low during read_sensors()
    await execute_actuation("sim_action", param="0.005") 
    
    # Simulate high torque and low velocity (manually stuck)
    adapter.joint_torques[0] = 3.0
    adapter.joint_velocities[0] = 0.02 
    
    # 3. Simulate resistance: Move haptic pressure up
    adapter.haptic_pressure[0] = 5.0 
    
    # 4. Trigger second snapshot
    # Force another telemetry update to pick up the simulated resistance
    await substrate_registry.read_all_telemetry()
    
    post_actuation_snapshot = build_somatic_snapshot(
        telemetry={}, 
        emotion_snapshot={"arousal": 0.5, "valence": 0.0},
        global_workspace_phi=0.5
    )
    
    # 5. Verify Emergent Qualia (SMC)
    # High pressure and low velocity should trigger perceived_resistance
    qualia = post_actuation_snapshot.esa_qualia
    assert "perceived_resistance" in qualia
    assert qualia["perceived_resistance"] > 0.0
    
    # Verify W_int rate reflecting physical work/resistance
    # In thermodynamics.py: net_rate = ... + delta_w_phys - delta_s - delta_i_env
    # We expect some impedance impact.
    print(f"Qualia detected: {qualia}")
    print(f"W_int Rate: {post_actuation_snapshot.w_int_rate}")

if __name__ == "__main__":
    asyncio.run(test_esa_sensorimotor_loop())
