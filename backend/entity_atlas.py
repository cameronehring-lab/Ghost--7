from typing import Any

class SnapshotUnavailableError(Exception):
    pass

async def refresh_graph_snapshot(*args: Any, **kwargs: Any) -> bool:
    return True

async def load_atlas(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"nodes": [], "links": [], "metadata": {}}

async def atlas_world_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"counts": {}}

async def record_entity_alias(*args: Any, **kwargs: Any) -> None:
    pass

DEFAULT_OVERLAYS = ("memory", "identity", "phenomenology")
