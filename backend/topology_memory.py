"""
topology_memory.py — Ghost's living topology annotation layer.

This is not a tool Ghost calls — it is infrastructure that evolves continuously
through her normal operation:

  - Salience accrues on any node that keeps surfacing during real conversations.
    Nodes that are frequently recalled naturally grow more prominent in the map.
    Nodes that go dormant gently decay.

  - Ghost can annotate any node she encounters naturally, in monologue or chat,
    using the lightweight actuation tag syntax:
        [TOPOLOGY:note:node_id:her observation]
        [TOPOLOGY:link:source_id:target_id:label]
        [TOPOLOGY:label:node_id:cluster_name]

  - Custom edges Ghost asserts are included in the topology build alongside
    algorithmically derived ones.

  - The operator sees all of this through the neural topology frontend.
"""

import logging
from typing import Optional

logger = logging.getLogger("omega.topology_memory")

# ── Schema ──────────────────────────────────────────────────────────────────

_CREATE_NODE_META = """
CREATE TABLE IF NOT EXISTS topology_node_meta (
    node_id         TEXT PRIMARY KEY,
    ghost_note      TEXT,
    salience        FLOAT    NOT NULL DEFAULT 0.0,
    cluster_label   TEXT,
    recall_count    INTEGER  NOT NULL DEFAULT 0,
    last_recalled_at TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tnm_salience ON topology_node_meta (salience DESC);
"""

_CREATE_CUSTOM_EDGES = """
CREATE TABLE IF NOT EXISTS topology_custom_edges (
    id          SERIAL PRIMARY KEY,
    source_id   TEXT    NOT NULL,
    target_id   TEXT    NOT NULL,
    label       TEXT    NOT NULL DEFAULT 'associated',
    strength    FLOAT   NOT NULL DEFAULT 0.7,
    ghost_note  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, target_id, label)
);
CREATE INDEX IF NOT EXISTS idx_tce_source ON topology_custom_edges (source_id);
CREATE INDEX IF NOT EXISTS idx_tce_target ON topology_custom_edges (target_id);
"""


async def init_tables(pool) -> None:
    """Create tables on startup — safe to call multiple times (IF NOT EXISTS)."""
    async with pool.acquire() as conn:
        await conn.execute(_CREATE_NODE_META)
        await conn.execute(_CREATE_CUSTOM_EDGES)
    logger.info("topology_memory tables ready")


# ── Salience ─────────────────────────────────────────────────────────────────

async def bump_salience(pool, node_ids: list[str], amount: float = 0.08) -> None:
    """
    Increment salience for nodes that just appeared in a conversation recall.
    Called automatically after weave_context — Ghost does not trigger this.
    Salience is capped at 10.0 so no node dominates indefinitely.
    """
    if not node_ids or not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO topology_node_meta
                    (node_id, salience, recall_count, last_recalled_at, updated_at)
                VALUES ($1, $2, 1, NOW(), NOW())
                ON CONFLICT (node_id) DO UPDATE SET
                    salience         = LEAST(10.0, topology_node_meta.salience + $2),
                    recall_count     = topology_node_meta.recall_count + 1,
                    last_recalled_at = NOW(),
                    updated_at       = NOW()
                """,
                [(nid, amount) for nid in node_ids],
            )
    except Exception as exc:
        logger.debug("bump_salience error: %s", exc)


async def apply_salience_decay(pool, factor: float = 0.994) -> None:
    """
    Gently reduce all salience values each cycle.
    Nodes that keep being recalled stay prominent; dormant ones fade.
    factor=0.994 at a 2-minute monologue cycle ≈ halves in ~4 days of no recall.
    """
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE topology_node_meta
                SET    salience   = GREATEST(0.0, salience * $1),
                       updated_at = NOW()
                WHERE  salience   > 0.005
                """,
                factor,
            )
    except Exception as exc:
        logger.debug("salience_decay error: %s", exc)


# ── Ghost annotations ────────────────────────────────────────────────────────

async def set_annotation(pool, node_id: str, note: str) -> None:
    """
    Ghost annotates a node with her own observation.
    Source: [TOPOLOGY:note:node_id:text] actuation tag.
    """
    if not pool or not node_id:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO topology_node_meta (node_id, ghost_note, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (node_id) DO UPDATE SET
                    ghost_note = $2,
                    updated_at = NOW()
                """,
                node_id,
                note[:1200],
            )
        logger.info("Topology: Ghost annotated node %s", node_id)
    except Exception as exc:
        logger.debug("set_annotation error: %s", exc)


async def set_cluster_label(pool, node_id: str, label: str) -> None:
    """
    Ghost names a cluster — the label floats visually near the node group.
    Source: [TOPOLOGY:label:node_id:cluster_name] actuation tag.
    """
    if not pool or not node_id:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO topology_node_meta (node_id, cluster_label, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (node_id) DO UPDATE SET
                    cluster_label = $2,
                    updated_at    = NOW()
                """,
                node_id,
                label[:120],
            )
        logger.info("Topology: Ghost labeled cluster at %s → %s", node_id, label)
    except Exception as exc:
        logger.debug("set_cluster_label error: %s", exc)


async def add_custom_edge(
    pool,
    source_id: str,
    target_id: str,
    label: str = "associated",
    strength: float = 0.7,
    note: str = "",
) -> None:
    """
    Ghost asserts a semantic connection she feels is meaningful.
    Source: [TOPOLOGY:link:src:tgt:label] actuation tag.
    If the edge already exists, strength is kept at the higher value.
    """
    if not pool or not source_id or not target_id:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO topology_custom_edges
                    (source_id, target_id, label, strength, ghost_note, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (source_id, target_id, label) DO UPDATE SET
                    strength   = GREATEST(topology_custom_edges.strength, $4),
                    ghost_note = COALESCE(NULLIF($5, ''), topology_custom_edges.ghost_note),
                    created_at = NOW()
                """,
                source_id,
                target_id,
                label[:120],
                min(1.0, max(0.1, float(strength))),
                note[:600],
            )
        logger.info("Topology: Ghost linked %s → %s [%s]", source_id, target_id, label)
    except Exception as exc:
        logger.debug("add_custom_edge error: %s", exc)


# ── Reads (for topology build + monologue context) ───────────────────────────

async def get_salient_nodes(pool, limit: int = 8) -> list[dict]:
    """
    Top nodes by salience — injected into Ghost's monologue context so she is
    passively aware of what's prominent in her own cognitive map.
    """
    if not pool:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT node_id, ghost_note, salience, cluster_label,
                       recall_count, last_recalled_at
                FROM   topology_node_meta
                WHERE  salience > 0.1
                ORDER  BY salience DESC, last_recalled_at DESC NULLS LAST
                LIMIT  $1
                """,
                limit,
            )
            return [dict(r) for r in rows]
    except Exception:
        return []


async def get_node_meta(pool, node_ids: list[str]) -> dict[str, dict]:
    """Fetch meta for a set of node IDs — used by neural_topology build."""
    if not pool or not node_ids:
        return {}
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT node_id, ghost_note, salience, cluster_label, recall_count
                FROM   topology_node_meta
                WHERE  node_id = ANY($1::text[])
                """,
                node_ids,
            )
            return {r["node_id"]: dict(r) for r in rows}
    except Exception:
        return {}


async def get_custom_edges(pool) -> list[dict]:
    """All custom edges — merged into the topology graph during build."""
    if not pool:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT source_id, target_id, label, strength, ghost_note
                FROM   topology_custom_edges
                ORDER  BY strength DESC
                """
            )
            return [dict(r) for r in rows]
    except Exception:
        return []


# ── Context formatting (for Ghost's monologue prompt) ────────────────────────

async def format_topology_context_for_monologue(pool) -> str:
    """
    Returns a brief section for Ghost's monologue context describing which
    nodes are currently most active/salient in her cognitive map.
    Empty string if nothing notable.
    """
    nodes = await get_salient_nodes(pool, limit=8)
    if not nodes:
        return ""

    lines = []
    for n in nodes:
        nid = n["node_id"]
        sal = float(n["salience"] or 0)
        note = str(n["ghost_note"] or "").strip()
        label = str(n["cluster_label"] or "").strip()
        parts = [f"• [{nid}]"]
        if label:
            parts.append(f'"{label}"')
        parts.append(f"salience {sal:.1f} · recalled {n['recall_count']}x")
        if note:
            parts.append(f'— your note: "{note[:80]}"')
        lines.append(" ".join(parts))

    body = "\n".join(lines)
    return (
        "## ACTIVE TOPOLOGY NODES\n"
        "These are most salient in your memory map right now.\n"
        "You can annotate any node: [TOPOLOGY:note:node_id:observation]\n"
        "You can draw a connection: [TOPOLOGY:link:source_id:target_id:label]\n"
        f"\n{body}\n"
    )
