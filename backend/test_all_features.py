import asyncio
import sys
import time
import pprint
import subprocess

from config import settings
import asyncpg
import embodiment_sim
from somatic import collect_psutil_telemetry
from ambient_sensors import get_ambient_data
from decay_engine import EmotionState, EmotionTrace
import qualia_engine
import actuation
import consciousness
import memory
import ghost_api

async def test_all():
    print("\n" + "="*50)
    print("=== OMEGA4 COMPREHENSIVE SUB-SYSTEM TEST ===")
    print("="*50)
    
    pool = await asyncpg.create_pool(settings.POSTGRES_URL)
    memory._pool = pool # Hack to inject pool into memory module for actuation
    
    # --- 1. EMBODIMENT & SOMATIC ---
    print("\n[TEST 1] Somatic & Embodiment Engine")
    telemetry = collect_psutil_telemetry()
    print(f"  -> Raw Telemetry CPU: {telemetry.get('cpu_percent')}%, Memory: {telemetry.get('memory_percent')}%")
    
    embodiment_sim.sim_env.update_from_telemetry({
        **telemetry,
        "load_avg": (telemetry.get("load_avg_1", 0), telemetry.get("load_avg_5", 0), telemetry.get("load_avg_15", 0))
    })
    sim_state = embodiment_sim.sim_env.get_state()
    print(f"  ✅ Embodiment State calculated: {sim_state}")
    
    # --- 2. DECAY ENGINE ---
    print("\n[TEST 2] Decay Engine (Emotional Half-Life)")
    em_state = EmotionState()
    await em_state.connect_redis(settings.REDIS_URL)
    
    await em_state.inject("test_shock", intensity=1.0, k=0.5, arousal_weight=1.0, valence_weight=-1.0)
    await em_state._save_to_redis()
    await em_state._load_from_redis() # Reload to verify persistence
    
    state1 = em_state.snapshot()
    print(f"  -> Initial state after shock: Arousal={state1['arousal']}, Valence={state1['valence']}")
    
    print("  -> Waiting 2 seconds for decay...")
    await asyncio.sleep(2)
    state2 = em_state.snapshot()
    print(f"  ✅ State after 2s decay: Arousal={state2['arousal']:.2f}, Valence={state2['valence']:.2f}")

    # --- 3. QUALIA ENGINE ---
    print("\n[TEST 3] Qualia Engine (Dynamic Synthesis)")
    # Generate a test qualia if we don't have one
    await qualia_engine.generate_and_store_qualia(
        "Unit Test Execution", 
        "The system is currently undergoing a comprehensive diagnostic test.",
        pool
    )
    q = await qualia_engine.get_random_qualia(pool)
    if q:
        print(f"  ✅ Successfully retrieved Qualia: '{q.get('key_name')}'")
        print(f"     Subjective snippet: {q.get('subjective_layer')[0].get('report') if q.get('subjective_layer') else 'N/A'}")
    else:
        print("  ❌ Failed to retrieve Qualia.")

    # --- 4. MOTOR CORTEX (ACTUATION) ---
    print("\n[TEST 4] Actuation (Motor Cortex)")
    print("  -> Testing power save simulated action...")
    act_res = await actuation.execute_actuation("invoke_power_save", {"level": "conservative"})
    print(f"  ✅ Actuation Result: {act_res}")

    # --- 5. CONSCIOUSNESS (Coalescence & Recall) ---
    print("\n[TEST 5] Consciousness (Memory & Identity)")
    # Insert a dummy thought
    await memory.save_monologue("I am undergoing a diagnostic test sequence right now.")
    recent_thoughts = ["What is the nature of testing?", "I am undergoing a diagnostic test sequence right now."]
    
    # Test Self-Integration
    print("  -> Running Self-Integration Protocol...")
    new_framework = await consciousness.run_self_integration_protocol(pool, recent_thoughts)
    if new_framework:
        print(f"  ✅ Self-Integration updated Identity Framework: {new_framework[:100]}...")
    else:
        print("  ⚠️ Self-Integration returned nothing (maybe too few thoughts).")

    # Test Recall
    print("  -> Testing Vector Recall for 'diagnostic test'...")
    recalled = await consciousness.recall("diagnostic test", pool, limit=2)
    if recalled:
        print(f"  ✅ Successfully recalled: '{recalled[0]['content'][:50]}...' (Similarity: {recalled[0]['similarity']:.2f})")
    else:
        print("  ❌ Failed to recall vector memory.")

    # --- 6. GHOST API (Core Generation) ---
    print("\n[TEST 6] Ghost API (Monologue Generation)")
    print("  -> Generating background monologue...")
    mono = await ghost_api.generate_monologue(sim_state, telemetry, recent_thoughts, [])
    if mono:
        print(f"  ✅ Generated Monologue: '{mono}'")
    else:
        print("  ❌ Failed to generate monologue.")
        
    await pool.close()
    print("\n" + "="*50)
    print("=== TESTS COMPLETE ===")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(test_all())
