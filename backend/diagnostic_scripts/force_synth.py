import asyncio
import sys

import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def force():
    from main import memory
    from operator_synthesis import run_synthesis

    print("Initializing DB...")
    await memory.init_db()

    try:
        print("Checking for stale sessions...")
        stale_ids = await memory.get_stale_sessions()
        print(f"Found stale sessions: {stale_ids}")

        if stale_ids:
            print("Closing stale sessions before synthesis...")
            for sid in stale_ids:
                await memory.end_session(
                    sid,
                    summary="[forced close] session closed by force_synth",
                )

        print("Running operator synthesis...")
        result = await run_synthesis(session_id=None)
        print(f"Synthesis result: {result}")
    finally:
        await memory.close_db()

if __name__ == "__main__":
    asyncio.run(force())
