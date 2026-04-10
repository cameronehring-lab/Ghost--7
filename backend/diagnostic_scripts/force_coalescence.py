import asyncio
import sys

import os

# Ensure we're in the right directory to import project modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def force():
    from main import memory
    from mind_service import MindService

    print("Initializing DB...")
    await memory.init_db()

    print("Triggering COALESCENCE (Dreaming)...")
    try:
        if memory._pool is None:
            raise RuntimeError("Database pool unavailable")
        mind = MindService(memory._pool)
        summary = await mind.trigger_coalescence()
        print(f"Coalescence summary: {summary}")
    finally:
        await memory.close_db()

if __name__ == "__main__":
    asyncio.run(force())
