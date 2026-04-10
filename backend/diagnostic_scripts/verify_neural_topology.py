import asyncio
import json
import logging
import sys
import os

# Add current directory to path to import local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from neural_topology import build_topology_graph
from config import settings
import memory

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("verify_topology")

async def verify():
    logger.info("Initializing DB connection...")
    try:
        await memory.init_db()
        pool = memory._pool
        if not pool:
            logger.error("Failed to initialize DB pool.")
            return False
    except Exception as e:
        logger.error(f"DB initialization failed: {e}")
        return False
    
    ghost_id = settings.GHOST_ID
    logger.info(f"Building topology graph for ghost_id: {ghost_id}")
    
    try:
        # Test with threshold 0.65
        graph = await build_topology_graph(pool, ghost_id, similarity_threshold=0.65)
        
        if "error" in graph:
            logger.error(f"Graph construction reported error: {graph['error']}")
            return False
        
        nodes = graph.get("nodes", [])
        links = graph.get("links", [])
        metadata = graph.get("metadata", {})
        align = (metadata or {}).get("rolodex_alignment") or {}
        ext = (metadata or {}).get("entity_expansion") or {}
        
        logger.info(f"Graph Stats: {len(nodes)} nodes, {len(links)} links")
        logger.info(f"Metadata: {json.dumps(metadata, indent=2)}")
        if align:
            logger.info(
                "Rolodex alignment: ok=%s profiles=%s/%s facts=%s/%s gaps=%s mismatches=%s ideas=%s/%s cov(all/place/thing/person)=%s/%s/%s/%s",
                bool(align.get("alignment_ok")),
                align.get("profiles_count"),
                align.get("profile_nodes"),
                align.get("facts_count"),
                align.get("fact_nodes"),
                align.get("profile_association_gap_count"),
                len(align.get("profile_fact_mismatches") or []),
                align.get("ideas_with_connectors"),
                align.get("idea_nodes"),
                align.get("idea_connector_coverage"),
                align.get("idea_place_coverage"),
                align.get("idea_thing_coverage"),
                align.get("idea_person_coverage"),
            )
        if ext:
            logger.info(
                "Entity expansion: place=%s thing=%s idea=%s connectors(place/thing/person)=%s/%s/%s",
                ext.get("place_nodes"),
                ext.get("thing_nodes"),
                ext.get("emergent_idea_nodes"),
                ext.get("idea_place_edges"),
                ext.get("idea_thing_edges"),
                ext.get("idea_person_edges"),
            )
        
        # Check node types
        node_types = {}
        for n in nodes:
            t = n.get("type")
            node_types[t] = node_types.get(t, 0) + 1
        logger.info(f"Node types breakdown: {node_types}")
        
        # Check link types
        link_types = {}
        for l in links:
            t = l.get("type")
            link_types[t] = link_types.get(t, 0) + 1
        logger.info(f"Link types breakdown: {link_types}")
        
        if len(nodes) > 0 and (not align or bool(align.get("alignment_ok"))):
            logger.info("✅ BACKEND VERIFICATION PASSED: Graph data successfully generated.")
            return True
        if len(nodes) > 0 and align and not bool(align.get("alignment_ok")):
            logger.error("❌ Rolodex -> topology alignment failed integrity checks.")
            return False
        else:
            logger.warning("⚠️ BACKEND WARNING: Graph is empty. Verify that the 'vector_memories' table contains data for this GHOST_ID.")
            return True # Not a code failure
            
    except Exception as e:
        logger.error(f"Unexpected error during verification: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(verify())
    if success:
        sys.exit(0)
    else:
        sys.exit(1)
