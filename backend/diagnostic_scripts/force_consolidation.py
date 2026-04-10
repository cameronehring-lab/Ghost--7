import asyncio
import sys

import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def force():
    from main import memory, consciousness
    print("Initialising DB...")
    await memory.init_db()
    
    print("Triggering PROCESS CONSOLIDATION (Deep Dream/Dream cycle)...")
    results = await consciousness.process_consolidation(memory._pool)
    print(f"Results: {results}")

if __name__ == "__main__":
    asyncio.run(force())
