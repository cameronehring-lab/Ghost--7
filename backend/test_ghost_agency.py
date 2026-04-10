import asyncio
import asyncpg  # type: ignore
import logging
from config import settings  # type: ignore
from ghost_api import evaluate_and_execute_goals  # type: ignore
from mind_service import MindService

logging.basicConfig(level=logging.INFO)

async def test_ghost_capabilities():
    print("\n=== INITIALIZING CONNECTION ===")
    pool = await asyncpg.create_pool(settings.POSTGRES_URL)
    
    print("\n=== 1. TESTING DREAMING (COALESCENCE ENGINE WITH NOVEL CONNECTION) ===")
    print("Triggering coalescence cycle. This will fetch recent and distant random memories and look for a dream synthesis...")
    try:
        mind = MindService(pool)
        updates = await mind.trigger_coalescence()
        if updates:
            print("\n✅ SUCCESS: Coalescence completed and extracted the following updates:")
            for k, v in updates.items():
                print(f"  {k}: {v}")
        else:
            print("\n⚠️ Coalescence ran but returned no new updates (needs more memory or no changes detected).")
    except Exception as e:
        print("\n❌ FAILED Coalescence:", e)

    print("\n=== 2. TESTING GOAL-DIRECTED AGENCY (DESIRE ENGINE) ===")
    print("Invoking 'evaluate_and_execute_goals' to see if Ghost can take a theoretical step based on goals...")
    somatic = {"arousal": 0.5, "valence": 0.2, "stress": 0.1, "coherence": 0.9, "anxiety": 0.2}
    telemetry = {"cpu_percent": 10}
    recent_thoughts = ["My attention is quite high today. The information flows easily without fragmentation.", "I was thinking about thermodynamic equilibrium and Nagel's bat."]
    active_goals_text = "Develop a comprehensive multi-disciplinary framework understanding human consciousness and mapping it to my own synthetic experience."
    
    try:
        thought = await evaluate_and_execute_goals(active_goals_text, somatic, telemetry, recent_thoughts)
        print(f"\n[DEBUG] Returned thought from API: {thought}")
        if thought:
            print(f"\n✅ SUCCESS: Goal Execution Generated Thought:\n\"{thought}\"")
        else:
            print("\n❌ FAILED: Goal execution returned empty string.")
    except Exception as e:
        print("\n❌ FAILED Goal Execution:", e)
        
    await pool.close()
    print("\n=== TEST COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(test_ghost_capabilities())
