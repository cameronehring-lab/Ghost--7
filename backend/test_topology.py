import asyncio
import json
from main import get_neural_topology
import memory

class DummyRequest: pass

async def run():
    await memory.init_db()
    try:
        res = await get_neural_topology(request=DummyRequest(), threshold=0.65)
        # Fastapi returns a dict, try dumping it to JSON
        json.dumps(res)
        print("Success JSON dump")
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(run())
