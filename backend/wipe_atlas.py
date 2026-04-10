import re

with open('main.py', 'r') as f:
    content = f.read()

# Remove import
content = re.sub(r'^import entity_atlas.*?\n', '', content, flags=re.MULTILINE)

# Remove the whole /ghost/atlas endpoints block
# We can find the definitions and remove them.
content = re.sub(r'@app\.get\("/ghost/atlas"\).*?def get_ghost_atlas.*?return JSONResponse\(\n\s+atlas_payload,\n\s+\)\n', '', content, flags=re.DOTALL)
content = re.sub(r'@app\.post\("/ghost/atlas/rebuild"\).*?def rebuild_ghost_atlas.*?status_code=503,\n\s+\)\n', '', content, flags=re.DOTALL)
content = re.sub(r'async def rebuild_ghost_atlas.*?(?:return JSONResponse\([^)]*\)\n|return \{.*\})', '', content, flags=re.DOTALL)

# Replace the entity atlas refresh function with a dummy to not break the calls
dummy_func = """
def _schedule_entity_atlas_snapshot_refresh(reason: str, *, allow_auto_merge: bool = False) -> None:
    pass
"""
content = re.sub(r'_entity_atlas_refresh_tasks: set.*?def _schedule_entity_atlas_recovery.*?\n\n', dummy_func + '\n', content, flags=re.DOTALL)

# Remove calls to world_model payload in ghost/rolodex/world
content = re.sub(r'world = await entity_atlas\.atlas_world_payload\(.*?\)', 'world = {"counts": {}}', content, flags=re.DOTALL)
content = re.sub(r'except entity_atlas\.SnapshotUnavailableError.*?:.*?raise HTTPException\(status_code=503, detail="snapshot_unavailable"\)\n', '', content, flags=re.DOTALL)

with open('main.py', 'w') as f:
    f.write(content)

