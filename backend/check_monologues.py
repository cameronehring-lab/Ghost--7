import asyncio
import asyncpg
import json
import os

async def main():
    dsn = os.environ.get("POSTGRES_URL")
    if not dsn:
        print("POSTGRES_URL not set")
        return
    pool = await asyncpg.create_pool(dsn)
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT content FROM monologues ORDER BY created_at DESC LIMIT 5")
        for r in rows:
            print(f"--- {r['content'][:80]}...")
    await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
