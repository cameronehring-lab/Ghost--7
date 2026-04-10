import asyncio
import time
import math
import logging
from ambient_sensors import _collect_circadian, apply_rest_credit, get_ambient_data, _runtime_started_at
from models import SomaticSnapshot

logging.basicConfig(level=logging.INFO)

async def test_fatigue_reset():
    print("--- Starting Fatigue Reset Test ---")
    
    class MockEmotionState:
        def __init__(self):
            self.self_preferences = {"quietude_active": False}
    
    em_state = MockEmotionState()
    
    # 1. Simulate some awake time (manually override the start time for the test)
    # Let's say we've been awake for 20 hours.
    # runtime_awake_seconds = now - _runtime_started_at
    import ambient_sensors
    ambient_sensors._runtime_started_at = time.time() - (20 * 3600)
    
    await _collect_circadian(em_state)
    data_before = get_ambient_data()
    fatigue_before = data_before["fatigue_index"]
    hours_before = data_before["hours_awake"]
    print(f"Before Reset: hours_awake={hours_before:.2f}, fatigue_index={fatigue_before:.3f}")
    
    # 2. Apply 4 hours of rest credit
    print("Applying 4.0 hours of rest credit...")
    apply_rest_credit(4.0)
    
    # 3. Collect circadian again
    await _collect_circadian(em_state)
    data_after = get_ambient_data()
    fatigue_after = data_after["fatigue_index"]
    hours_after = data_after["hours_awake"]
    print(f"After Reset: hours_awake={hours_after:.2f}, fatigue_index={fatigue_after:.3f}")
    
    # 4. Assertions
    expected_hours = hours_before - 4.0
    if abs(hours_after - expected_hours) < 0.1:
        print("SUCCESS: Hours awake reduced correctly.")
    else:
        print(f"FAILURE: Expected approx {expected_hours:.2f} hours, got {hours_after:.2f}")
        
    if fatigue_after < fatigue_before:
        print(f"SUCCESS: Fatigue index dropped from {fatigue_before} to {fatigue_after}")
    else:
        print("FAILURE: Fatigue index did not drop.")

if __name__ == "__main__":
    asyncio.run(test_fatigue_reset())
