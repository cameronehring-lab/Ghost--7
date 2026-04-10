import logging
from typing import Optional, List

from config import settings # type: ignore
import memory # type: ignore
import entity_store  # type: ignore
from domain_models import OperatorBelief, RelationalTension # type: ignore

logger = logging.getLogger("omega.relational")

class RelationalService:
    """
    Handles Ghost's understanding of the Operator (Cameron), 
    belief formation, and tension resolution.
    """

    def __init__(self, pool):
        self.pool = pool
        self.ghost_id = settings.GHOST_ID

    async def get_active_beliefs(self) -> List[OperatorBelief]:
        """Load all non-invalidated beliefs."""
        return await memory.load_operator_beliefs(self.pool, self.ghost_id)

    async def get_open_tensions(self) -> List[RelationalTension]:
        """Load all unresolved tensions."""
        return await memory.load_open_tensions(self.pool, self.ghost_id)

    async def resolve_tension(self, tension_id: int, resolution_summary: str, session_id: Optional[str] = None):
        """Mark a tension as resolved and update the operator model."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """UPDATE operator_contradictions 
                   SET status = 'resolved', resolved_at = now()
                   WHERE id = $1""",
                tension_id
            )
            # Log the resolution
            logger.info(
                "RelationalService: Resolved tension %s (session=%s): %s",
                tension_id,
                session_id,
                resolution_summary,
            )

    async def initiate_synthesis(self, session_id: str):
        """Trigger the operator synthesis loop for a specific session."""
        from operator_synthesis import run_synthesis # type: ignore
        await run_synthesis(session_id=session_id)

    async def list_relational_snapshot(self, limit: int = 120) -> dict:
        """
        Unified relational primitives snapshot for operator inspection.
        """
        cap = max(10, min(int(limit), 500))
        places_limit = max(10, min(cap, 200))
        things_limit = max(10, min(cap, 200))
        assoc_limit = max(20, min(cap * 2, 600))
        places = await entity_store.list_places(self.pool, ghost_id=self.ghost_id, limit=places_limit)
        things = await entity_store.list_things(self.pool, ghost_id=self.ghost_id, limit=things_limit)
        associations = await entity_store.list_associations(self.pool, ghost_id=self.ghost_id, limit=assoc_limit)
        return {
            "ghost_id": self.ghost_id,
            "counts": {
                "places": len(places),
                "things": len(things),
                "person_place": len((associations or {}).get("person_place") or []),
                "person_thing": len((associations or {}).get("person_thing") or []),
                "idea_links": len((associations or {}).get("idea_links") or []),
            },
            "places": places,
            "things": things,
            "associations": associations,
        }
