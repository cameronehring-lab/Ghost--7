import asyncio
import asyncpg
import json
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))
from config import settings

async def test_db():
    print(f"Connecting to {settings.POSTGRES_URL}...")
    conn = await asyncpg.connect(settings.POSTGRES_URL)
    try:
        # Check if table exists
        exists = await conn.fetchval("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'gei_projections')")
        print(f"Table gei_projections exists: {exists}")
        
        if exists:
            # Insert a mock projection
            await conn.execute(
                """
                INSERT INTO gei_projections (summary, probability, intensity, causal_graph_json)
                VALUES ($1, $2, $3, $4::jsonb)
                """,
                "Superposition A: Galactic Peace", 0.75, 1.8, json.dumps({"nodes": ["Peace"], "edges": []})
            )
            print("Mock projection inserted.")
            
            # Fetch it back
            row = await conn.fetchrow("SELECT * FROM gei_projections ORDER BY created_at DESC LIMIT 1")
            print(f"Fetched: {row['summary']} (Prob: {row['probability']})")
            
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_db())
