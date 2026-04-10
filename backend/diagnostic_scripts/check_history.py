
import asyncio
import json
from memory import init_db, load_recent_sessions, get_monologue_buffer

async def check():
    await init_db()
    sessions = await load_recent_sessions(limit=5, include_open=True)
    print("--- RECENT SESSIONS ---")
    for s in sessions:
        print(f"ID: {s['session_id']} | Summary: {s['summary']} | Count: {s['message_count']}")
    
    monologues = await get_monologue_buffer(limit=10)
    print("\n--- RECENT MONOLOGUES ---")
    for m in monologues:
        print(f"[{m['timestamp']}] {m['content'][:100]}...")

if __name__ == "__main__":
    asyncio.run(check())
