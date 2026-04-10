import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from tpcv_repository import sync_master_draft
from config import settings

async def run_sync():
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        print(f"Syncing Master Draft for ghost: {settings.GHOST_ID}...")
        res = await sync_master_draft(conn, settings.GHOST_ID)
        print(f"Sync result: {res}")

if __name__ == '__main__':
    asyncio.run(run_sync())
