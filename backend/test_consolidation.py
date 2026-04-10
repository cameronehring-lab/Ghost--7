import asyncio
import os
import json
import asyncpg
from consciousness import process_consolidation, fetch_operator_context_for_consolidation
from main import settings

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ghost:ghost_memory_2025@postgres:5432/omega")

async def test_consolidation_resolution():
    pool = await asyncpg.create_pool(DATABASE_URL)
    if not pool:
        print("Failed to connect to DB")
        return

    ghost_id = "test-ghost-consolidation"
    EMOTION_KEY = f"emotion_state:{ghost_id}"
    
    print(f"--- PRE-TEST SETUP for {ghost_id} ---")
    async with pool.acquire() as conn:
        # Cleanup existing beliefs for this dimension to avoid UniqueViolation
        await conn.execute("UPDATE operator_model SET invalidated_at = now() WHERE ghost_id = $1 AND dimension = 'communication_preference'", ghost_id)
        # Clear monologues and contradictions to avoid contamination
        await conn.execute("DELETE FROM monologues WHERE ghost_id = $1", ghost_id)
        await conn.execute("DELETE FROM operator_contradictions WHERE ghost_id = $1", ghost_id)
        
        # 1. Insert a mock belief
        belief_id = await conn.fetchval(
            """
            INSERT INTO operator_model (ghost_id, dimension, belief, confidence, evidence_count, formed_by)
            VALUES ($1, 'communication_preference', 'Prefers brief, technical updates.', 0.8, 5, 'manual_test')
            RETURNING id
            """,
            ghost_id
        )
        
        # 2. Insert a contradiction linked to that belief
        tension_id = await conn.fetchval(
            """
            INSERT INTO operator_contradictions (ghost_id, dimension, observed_event, tension_score, prior_belief_id)
            VALUES ($1, 'communication_preference', 'Operator asked for a detailed, poetic explanation of entropy.', 0.9, $2)
            RETURNING id
            """,
            ghost_id, belief_id
        )
        print(f"Inserted Tension ID: {tension_id} targeting Belief ID: {belief_id}")

        # 3. Add a mock monologue to trigger consolidation
        await conn.execute(
            "INSERT INTO monologues (ghost_id, content) VALUES ($1, $2), ($1, $3), ($1, $4)",
            ghost_id, 
            "I noticed Cameron asking for more detail today.", 
            "Perhaps my previous model of his preference for brevity was too narrow.",
            "I will try to provide more nuanced explanations henceforth to match his apparent desire for depth."
        )

    print("\n--- RUNNING CONSOLIDATION ---")
    # We mock the LLM or just run it if GOOGLE_API_KEY is set. 
    # For this test, if we want to BE SURE it resolves, we might need a mock,
    # but let's see if the logic at least executes without error.
    results = await process_consolidation(pool, ghost_id=ghost_id)
    print(f"Consolidation Results: {json.dumps(results, indent=2)}")

    print("\n--- POST-TEST VERIFICATION ---")
    async with pool.acquire() as conn:
        tension = await conn.fetchrow("SELECT resolved FROM operator_contradictions WHERE id = $1", tension_id)
        belief = await conn.fetchrow("SELECT invalidated_at FROM operator_model WHERE id = $1", belief_id)
        new_beliefs = await conn.fetch("SELECT belief FROM operator_model WHERE ghost_id = $1 AND formed_by = 'process_consolidation' ORDER BY formed_at DESC LIMIT 1", ghost_id)
        
        print(f"Tension Resolved: {tension['resolved']}")
        print(f"Prior Belief Invalidated: {belief['invalidated_at'] is not None}")
        if new_beliefs:
            print(f"New Refined Belief: {new_beliefs[0]['belief']}")
        else:
            print("No new belief formed (did LLM emit TENSION_RESOLVE?)")

    await pool.close()

if __name__ == "__main__":
    asyncio.run(test_consolidation_resolution())
