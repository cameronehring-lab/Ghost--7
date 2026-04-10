import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import neural_topology


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


class _FakeConn:
    def __init__(self):
        t0 = datetime(2026, 3, 11, 12, 0, 0)
        self.memory_rows = [
            {
                "id": 1,
                "content": "self_model continuity marker in active memory",
                "memory_type": "monologue",
                "created_at": t0 + timedelta(seconds=300),
                "embedding": [1.0, 0.0],
                "somatic_state": {},
                "monologue_source": "monologue",
                "phen_state": None,
                "phen_source": None,
            },
            {
                "id": 2,
                "content": "long-range continuity pattern around self_model constraints",
                "memory_type": "monologue",
                "created_at": t0 + timedelta(seconds=360),
                "embedding": [0.99, 0.01],
                "somatic_state": {},
                "monologue_source": "monologue",
                "phen_state": None,
                "phen_source": None,
            },
        ]
        self.identity_rows = [
            {
                "id": 11,
                "key": "self_model",
                "value": "coherent process continuity",
                "updated_at": t0 - timedelta(seconds=120),
                "updated_by": "system",
            },
            {
                "id": 12,
                "key": "detached_trait",
                "value": "isolated shard",
                "updated_at": t0 - timedelta(seconds=600),
                "updated_by": "system",
            },
        ]
        self.audit_rows = [
            {
                "key": "self_model",
                "prev_value": "old",
                "new_value": "new",
                "created_at": t0 + timedelta(seconds=450),
                "updated_by": "operator",
            },
            {
                "key": "self_model",
                "prev_value": "new",
                "new_value": "newer",
                "created_at": t0 + timedelta(seconds=500),
                "updated_by": "operator",
            },
        ]
        self.phen_rows = [
            {
                "id": 21,
                "trigger_source": "probe:latency_spike",
                "subjective_report": "my self model feels coherent and process-like tonight",
                "created_at": t0,
                "before_state": {},
            }
        ]

    async def fetch(self, sql, *args):
        q = sql.lower()
        if "from vector_memories v" in q:
            return self.memory_rows
        if "from identity_matrix" in q:
            return self.identity_rows
        if "from identity_audit_log" in q:
            return self.audit_rows
        if "from phenomenology_logs" in q:
            return self.phen_rows
        if "from operator_model" in q:
            return []
        if "from operator_contradictions" in q:
            return []
        if "from person_rolodex" in q:
            return []
        if "from person_memory_facts" in q:
            return []
        if "from person_session_binding" in q:
            return []
        if "from place_entities" in q:
            return []
        if "from thing_entities" in q:
            return []
        if "from person_place_associations" in q:
            return []
        if "from person_thing_associations" in q:
            return []
        if "from idea_entity_associations" in q:
            return []
        if "from shared_conceptual_manifold" in q:
            return []
        return []

    async def fetchval(self, sql, *args):
        q = sql.lower()
        if "to_regclass('identity_audit_log')" in q:
            return "identity_audit_log"
        if "metrics_json->>'phi_proxy'" in q:
            return None
        return None


class NeuralTopologyRelationshipTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.pool = _FakePool(_FakeConn())

    async def _build_graph(self):
        with patch.object(
            neural_topology.consciousness,
            "_ensure_vector_registered",
            new=AsyncMock(return_value=None),
        ):
            return await neural_topology.build_topology_graph(
                self.pool,
                "omega-7",
                similarity_threshold=0.65,
            )

    async def test_identity_and_phenomenology_relationships_are_linked_and_anchored(self):
        graph = await self._build_graph()
        links = list(graph.get("links") or [])
        align = ((graph.get("metadata") or {}).get("rolodex_alignment") or {})

        alignment_edges = [
            l for l in links
            if str(l.get("type") or "") == "phenomenology_identity_alignment"
        ]
        self.assertTrue(alignment_edges, "Expected phenomenology_identity_alignment edges")
        self.assertTrue(
            any(
                str(l.get("source") or "") == "phen_21" and str(l.get("target") or "") == "id_11"
                for l in alignment_edges
            )
        )

        self.assertTrue(
            any(
                str(l.get("type") or "") == "phenomenological"
                and str(l.get("source") or "") == "phen_21"
                and str(l.get("target") or "") == "id_11"
                and str(l.get("label") or "") == "axiomatic_grounding"
                for l in links
            ),
            "Expected phenomenology orphan fallback edge to self_model",
        )

        self.assertTrue(
            any(
                str(l.get("type") or "") == "identity_activity_anchor"
                and str(l.get("source") or "") == "id_12"
                and str(l.get("target") or "").startswith("mem_")
                for l in links
            ),
            "Expected identity orphan recovery edge",
        )

        self.assertEqual(int(align.get("identity_nodes") or 0), 2)
        self.assertEqual(int(align.get("phenomenology_nodes") or 0), 1)
        self.assertGreaterEqual(int(align.get("identity_phenomenology_edges") or 0), 1)
        self.assertEqual(int(align.get("identity_orphan_count") or 0), 0)
        self.assertEqual(int(align.get("phenomenology_orphan_count") or 0), 0)
        self.assertGreaterEqual(float(align.get("identity_link_coverage") or 0.0), 1.0)
        self.assertGreaterEqual(float(align.get("phenomenology_link_coverage") or 0.0), 1.0)

    async def test_regression_existing_edges_and_dedupe_remain_intact(self):
        graph = await self._build_graph()
        links = list(graph.get("links") or [])

        self.assertTrue(any(str(l.get("type") or "") == "similarity" for l in links))
        self.assertTrue(any(str(l.get("type") or "") == "semantic_grounding" for l in links))

        consolidation = [
            l for l in links
            if str(l.get("type") or "") == "consolidation"
            and str(l.get("source") or "") == "mem_1"
            and str(l.get("target") or "") == "id_11"
        ]
        self.assertEqual(len(consolidation), 1, "Expected deduped consolidation edge for mem_1 -> id_11")


if __name__ == "__main__":
    unittest.main()
