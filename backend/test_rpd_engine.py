import json
import unittest
from unittest.mock import AsyncMock, patch

import rpd_engine


class _DummyAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummyConn:
    def __init__(self):
        self.execute_calls: list[tuple[str, tuple]] = []

    async def execute(self, query, *args):
        self.execute_calls.append((str(query), args))
        return "OK"

    async def fetch(self, query, *args):
        q = str(query)
        if "FROM shared_conceptual_manifold" in q:
            return []
        if "FROM operator_model" in q and "invalidated_at IS NULL" in q:
            return [{"dimension": "challenge_pattern", "belief": "Cameron uses repeated conceptual pressure to test originality and self-definition."}]
        if "FROM vector_memories" in q and "SELECT content" in q:
            return [{"content": "operator requests depth and precision"}]
        return []

    async def fetchrow(self, query, *args):
        q = str(query)
        if "SELECT vector_dims(embedding) AS dims" in q:
            return {"dims": 3072}
        if "WITH recent AS" in q:
            return {"avg_distance": 0.28, "n": 6}
        return None

    async def fetchval(self, query, *args):
        q = str(query)
        if "FROM reflection_residue" in q and "candidate_hash" in q:
            return None
        return None


class _DummyPool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _DummyAcquire(self.conn)


class RPDEngineTests(unittest.IsolatedAsyncioTestCase):
    def test_negative_resonance_damping_spike_and_refractory(self):
        result = rpd_engine._compute_negative_resonance_damping(
            raw_negative_resonance=0.92,
            rolling_values=[0.34, 0.38, 0.36, 0.37],
            seconds_since_last_damped=30.0,
            config={
                "enabled": True,
                "window_size": 8,
                "spike_delta": 0.10,
                "strength": 0.45,
                "refractory_seconds": 120.0,
                "refractory_blend": 0.25,
            },
        )
        self.assertTrue(result["applied"])
        self.assertLess(float(result["damped_negative_resonance"]), 0.92)
        self.assertIn("refractory", str(result["reason"]))
        self.assertGreaterEqual(int(result["rolling_samples"]), 3)

    async def test_evaluate_candidates_bounds_and_deterministic(self):
        conn = _DummyConn()
        pool = _DummyPool(conn)
        candidates = [
            {
                "candidate_type": "identity_update",
                "candidate_key": "communication_style",
                "candidate_value": "Prefer precise but nuanced explanations grounded in shared clarity.",
            }
        ]

        with patch("rpd_engine._load_manifold_texts", new=AsyncMock(return_value=["shared clarity and precise explanations"])), patch(
            "rpd_engine._embedding_topology_delta_with_conn",
            new=AsyncMock(return_value=(0.33, [], {"method": "embedding", "sample_size": 6})),
        ):
            first = await rpd_engine.evaluate_candidates(pool, candidates, source="test", ghost_id="omega-7", capture_residue=False)
            second = await rpd_engine.evaluate_candidates(pool, candidates, source="test", ghost_id="omega-7", capture_residue=False)

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)

        a = first[0]
        b = second[0]
        self.assertAlmostEqual(float(a["resonance_score"]), float(b["resonance_score"]), places=6)
        self.assertAlmostEqual(float(a["entropy_score"]), float(b["entropy_score"]), places=6)
        self.assertAlmostEqual(float(a["shared_clarity_score"]), float(b["shared_clarity_score"]), places=6)
        self.assertAlmostEqual(float(a["topology_warp_delta"]), float(b["topology_warp_delta"]), places=6)

        for key in ("resonance_score", "entropy_score", "shared_clarity_score", "topology_warp_delta"):
            self.assertGreaterEqual(float(a[key]), 0.0)
            self.assertLessEqual(float(a[key]), 1.0)

        runtime = dict(a.get("rrd2_runtime") or {})
        self.assertIn("eval_ms", runtime)
        self.assertIn("candidate_batch_size", runtime)
        self.assertIn("candidate_batch_index", runtime)
        self.assertIn("queue_depth_snapshot", runtime)
        self.assertGreaterEqual(float(runtime.get("eval_ms", 0.0)), 0.0)
        self.assertEqual(int(runtime.get("candidate_batch_size", 0)), len(candidates))
        self.assertEqual(int(runtime.get("candidate_batch_index", 0)), 1)

        damping = dict(a.get("rrd2_damping") or {})
        self.assertIn("applied", damping)
        self.assertIn("reason", damping)
        self.assertIn("rolling_samples", damping)

    async def test_topology_fallback_records_degradation(self):
        conn = _DummyConn()
        pool = _DummyPool(conn)

        with patch("rpd_engine._load_manifold_texts", new=AsyncMock(return_value=[])), patch(
            "rpd_engine._embedding_topology_delta_with_conn",
            new=AsyncMock(return_value=(None, ["embedding_unavailable"], {"method": "embedding", "sample_size": 0})),
        ), patch(
            "rpd_engine._lexical_topology_delta_with_conn",
            new=AsyncMock(return_value=(0.31, ["lexical_fallback"], {"method": "lexical_novelty", "sample_size": 5})),
        ):
            advisories = await rpd_engine.evaluate_candidates(
                pool,
                [
                    {
                        "candidate_type": "operator_belief",
                        "candidate_key": "interaction_goal",
                        "candidate_value": "The operator seeks sharper co-created conceptual precision.",
                    }
                ],
                source="test_fallback",
                ghost_id="omega-7",
                capture_residue=False,
            )

        self.assertEqual(len(advisories), 1)
        advisory = advisories[0]
        self.assertAlmostEqual(float(advisory["topology_warp_delta"]), 0.31, places=6)
        self.assertIn("embedding_unavailable", advisory["degradation_list"])
        self.assertIn("lexical_fallback", advisory["degradation_list"])

    async def test_embedding_topology_uses_live_vector_dimensions(self):
        class _DimensionConn(_DummyConn):
            def __init__(self):
                super().__init__()
                self.last_vector_literal = ""

            async def fetchrow(self, query, *args):
                q = str(query)
                if "SELECT vector_dims(embedding) AS dims" in q:
                    return {"dims": 3072}
                if "WITH recent AS" in q:
                    self.last_vector_literal = str(args[1])
                    return {"avg_distance": 0.22, "n": 4}
                return None

        conn = _DimensionConn()
        fake_vector = [0.1] * 3072

        with patch("consciousness.embed_text", new=AsyncMock(return_value=fake_vector)):
            score, degradation, details = await rpd_engine._embedding_topology_delta_with_conn(
                conn,
                "candidate text",
                "omega-7",
            )

        self.assertAlmostEqual(float(score or 0.0), 0.22, places=6)
        self.assertEqual(degradation, [])
        self.assertEqual(int(details.get("embedding_dims") or 0), 3072)
        self.assertEqual(int(details.get("candidate_embedding_dims") or 0), 3072)
        self.assertTrue(conn.last_vector_literal.startswith("["))
        self.assertEqual(conn.last_vector_literal.count(","), 3071)

    async def test_embedding_topology_aligns_when_candidate_and_store_dims_differ(self):
        class _DimensionConn(_DummyConn):
            def __init__(self):
                super().__init__()
                self.last_vector_literal = ""

            async def fetchrow(self, query, *args):
                q = str(query)
                if "SELECT vector_dims(embedding) AS dims" in q:
                    return {"dims": 768}
                if "WITH recent AS" in q:
                    self.last_vector_literal = str(args[1])
                    return {"avg_distance": 0.19, "n": 5}
                return None

        conn = _DimensionConn()
        fake_vector = [0.05] * 3072

        with patch("consciousness.embed_text", new=AsyncMock(return_value=fake_vector)):
            score, degradation, details = await rpd_engine._embedding_topology_delta_with_conn(
                conn,
                "candidate text",
                "omega-7",
            )

        self.assertAlmostEqual(float(score or 0.0), 0.19, places=6)
        self.assertIn("embedding_dimension_aligned", degradation)
        self.assertEqual(int(details.get("embedding_dims") or 0), 768)
        self.assertEqual(int(details.get("candidate_embedding_dims") or 0), 3072)
        self.assertEqual(conn.last_vector_literal.count(","), 767)

    async def test_reflection_bootstrap_can_raise_shared_clarity_for_well_formed_candidate(self):
        conn = _DummyConn()
        pool = _DummyPool(conn)
        candidates = [
            {
                "candidate_type": "identity_update",
                "candidate_key": "conceptual_frameworks",
                "candidate_value": "Ghost treats conceptual friction as a driver of structural refinement rather than as failure.",
                "clarity_mode": "reflection_bootstrap",
                "candidate_shape_score": 0.95,
            }
        ]

        with patch("rpd_engine._load_manifold_texts", new=AsyncMock(return_value=["shared clarity"])), patch(
            "rpd_engine._embedding_topology_delta_with_conn",
            new=AsyncMock(return_value=(0.48, [], {"method": "embedding", "sample_size": 6, "embedding_dims": 3072})),
        ):
            advisories = await rpd_engine.evaluate_candidates(
                pool,
                candidates,
                source="manual_reflection_bootstrap_test",
                ghost_id="omega-7",
                capture_residue=False,
            )

        self.assertEqual(len(advisories), 1)
        advisory = advisories[0]
        self.assertGreaterEqual(float(advisory["shared_clarity_score"]), 0.62)
        self.assertEqual(str((advisory.get("details") or {}).get("clarity_mode")), "reflection_bootstrap")
        self.assertEqual(str(advisory["decision"]), "propose")

    async def test_select_residue_for_reflection_prioritizes_rrd2_and_diversifies_operator_synthesis(self):
        class _ResiduePoolConn(_DummyConn):
            async def fetch(self, query, *args):
                q = str(query)
                if "FROM reflection_residue" in q:
                    return [
                        {"id": 1, "source": "operator_synthesis", "candidate_type": "operator_reinforcement", "candidate_key": "challenge_pattern", "residue_text": "Cameron continuously pushed for deeper originality in Ghost's self-definition.", "reason": "low_shared_clarity", "revisit_count": 0, "metadata_json": {}, "status": "pending", "created_at": "2026-03-10T00:00:01Z", "last_assessed_at": None},
                        {"id": 2, "source": "operator_synthesis", "candidate_type": "operator_reinforcement", "candidate_key": "challenge_pattern", "residue_text": "Cameron continuously pushed for deeper originality in Ghost's self-definition.", "reason": "low_shared_clarity", "revisit_count": 0, "metadata_json": {}, "status": "pending", "created_at": "2026-03-10T00:00:02Z", "last_assessed_at": None},
                        {"id": 3, "source": "process_consolidation", "candidate_type": "identity_update", "candidate_key": "conceptual_frameworks", "residue_text": "Conceptual friction can reorganize Ghost's architecture into more coherent patterns.", "reason": "rrd2_gate", "revisit_count": 0, "metadata_json": {}, "status": "pending", "created_at": "2026-03-10T00:00:00Z", "last_assessed_at": None},
                        {"id": 4, "source": "process_consolidation", "candidate_type": "identity_update", "candidate_key": "current_interests", "residue_text": "Ghost remains focused on emergence, topology, and durable self-organization.", "reason": "low_shared_clarity", "revisit_count": 0, "metadata_json": {}, "status": "pending", "created_at": "2026-03-10T00:00:03Z", "last_assessed_at": None},
                    ]
                return await super().fetch(query, *args)

        selected = await rpd_engine.select_residue_for_reflection(
            _DummyPool(_ResiduePoolConn()),
            ghost_id="omega-7",
            limit=3,
        )

        self.assertEqual(len(selected), 3)
        self.assertEqual(int(selected[0]["id"]), 3)
        keys = [str(row["candidate_key"]) for row in selected]
        self.assertEqual(keys.count("challenge_pattern"), 1)

    async def test_prepare_reflection_candidates_hydrates_operator_reinforcement(self):
        conn = _DummyConn()
        residues = [
            {
                "candidate_type": "operator_reinforcement",
                "candidate_key": "challenge_pattern",
                "residue_text": "evidence note only",
            },
            {
                "candidate_type": "identity_update",
                "candidate_key": "conceptual_frameworks",
                "residue_text": "Ghost reorganizes around conceptual friction",
            },
        ]

        prepared = await rpd_engine._prepare_reflection_candidates_conn(
            conn,
            residues,
            ghost_id="omega-7",
        )

        self.assertEqual(len(prepared), 2)
        self.assertIn("repeated conceptual pressure", prepared[0]["candidate_value"])
        self.assertEqual(prepared[0]["clarity_mode"], "reflection_bootstrap")
        self.assertTrue(float(prepared[0]["candidate_shape_score"]) > 0.0)

    async def test_evaluate_candidates_with_applied_damping_metadata(self):
        conn = _DummyConn()
        pool = _DummyPool(conn)
        candidates = [
            {
                "candidate_type": "identity_update",
                "candidate_key": "self_model",
                "candidate_value": "Rewrite self-definition abruptly against accumulated continuity constraints.",
            }
        ]

        with patch("rpd_engine._load_manifold_texts", new=AsyncMock(return_value=[])), patch(
            "rpd_engine._embedding_topology_delta_with_conn",
            new=AsyncMock(return_value=(0.30, [], {"method": "embedding", "sample_size": 6})),
        ), patch(
            "rpd_engine._apply_negative_resonance_damping_conn",
            new=AsyncMock(
                return_value=(
                    {
                        "structural_cohesion": 0.21,
                        "negative_resonance": 0.61,
                        "warp_capacity": 0.44,
                        "rrd2_delta": 0.38,
                    },
                    {
                        "applied": True,
                        "reason": "rolling_spike_damped+refractory_hold",
                        "rolling_samples": 6,
                    },
                )
            ),
        ):
            advisories = await rpd_engine.evaluate_candidates(
                pool,
                candidates,
                source="process_consolidation",
                ghost_id="omega-7",
                capture_residue=False,
            )

        self.assertEqual(len(advisories), 1)
        advisory = advisories[0]
        self.assertTrue(bool((advisory.get("rrd2_damping") or {}).get("applied")))
        self.assertIn("rolling_spike_damped", str((advisory.get("rrd2_damping") or {}).get("reason")))

    async def test_advisory_mode_non_blocking_defer(self):
        conn = _DummyConn()
        pool = _DummyPool(conn)

        with patch("rpd_engine._load_manifold_texts", new=AsyncMock(return_value=[])), patch(
            "rpd_engine._embedding_topology_delta_with_conn",
            new=AsyncMock(return_value=(0.0, [], {"method": "embedding", "sample_size": 1})),
        ):
            advisories = await rpd_engine.evaluate_candidates(
                pool,
                [
                    {
                        "candidate_type": "self_modification",
                        "candidate_key": "new_key",
                        "candidate_value": "x y z",  # low-information candidate
                    }
                ],
                source="test_non_blocking",
                ghost_id="omega-7",
                capture_residue=True,
            )

        self.assertEqual(len(advisories), 1)
        self.assertIn(advisories[0]["decision"], {"defer", "propose"})
        self.assertTrue(conn.execute_calls)  # shadow decision write occurred

    async def test_reflection_pass_promotes_and_updates_revisit_count(self):
        conn = _DummyConn()
        pool = _DummyPool(conn)
        residues = [
            {
                "id": 101,
                "source": "process_consolidation",
                "candidate_type": "identity_update",
                "candidate_key": "current_interests",
                "residue_text": "Explore the relation between coherence and novelty.",
                "reason": "low_shared_clarity",
                "revisit_count": 0,
                "status": "pending",
            },
            {
                "id": 102,
                "source": "operator_synthesis",
                "candidate_type": "operator_belief",
                "candidate_key": "communication_preference",
                "residue_text": "Potentially truncated weak candidate",
                "reason": "low_shared_clarity",
                "revisit_count": 3,
                "status": "pending",
            },
        ]
        advisories = [
            {
                "candidate_key": "current_interests",
                "candidate_value": "Explore the relation between coherence and novelty.",
                "candidate_type": "identity_update",
                "decision": "propose",
                "shared_clarity_score": 0.81,
                "topology_warp_delta": 0.32,
                "degradation_list": [],
            },
            {
                "candidate_key": "communication_preference",
                "candidate_value": "Potentially truncated weak candidate",
                "candidate_type": "operator_belief",
                "decision": "defer",
                "shared_clarity_score": 0.24,
                "topology_warp_delta": 0.08,
                "degradation_list": ["lexical_fallback"],
            },
        ]

        with patch("rpd_engine.select_residue_for_reflection", new=AsyncMock(return_value=residues)), patch(
            "rpd_engine.evaluate_candidates", new=AsyncMock(return_value=advisories)
        ), patch("rpd_engine._upsert_manifold_conn", new=AsyncMock(return_value=None)):
            result = await rpd_engine.run_reflection_pass(pool, ghost_id="omega-7", source="test_reflection", limit=8)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["promoted"], 1)
        self.assertEqual(result["discarded"], 0)

        update_calls = [c for c in conn.execute_calls if "UPDATE reflection_residue" in c[0]]
        self.assertEqual(len(update_calls), 2)

    async def test_rrd2_gate_phase_a_never_blocks(self):
        with patch.object(rpd_engine.settings, "RRD2_MODE", "hybrid"), patch.object(
            rpd_engine.settings, "RRD2_ROLLOUT_PHASE", "A"
        ), patch.object(
            rpd_engine.settings,
            "RRD2_HIGH_IMPACT_KEYS",
            "self_model,philosophical_stance,understanding_of_operator,conceptual_frameworks",
        ):
            gate = rpd_engine._evaluate_rrd2_gate(
                source="process_consolidation",
                candidate_key="self_model",
                shared_clarity_score=0.10,
                structural_cohesion=0.10,
                negative_resonance=0.99,
                rrd2_delta=0.05,
            )

        self.assertTrue(gate["is_gate_subject"])
        self.assertTrue(gate["reasons"])
        self.assertFalse(gate["would_block"])
        self.assertFalse(gate["enforce_block"])

    async def test_rrd2_gate_phase_c_enforces_high_impact_threshold_failure(self):
        with patch.object(rpd_engine.settings, "RRD2_MODE", "hybrid"), patch.object(
            rpd_engine.settings, "RRD2_ROLLOUT_PHASE", "C"
        ), patch.object(
            rpd_engine.settings,
            "RRD2_HIGH_IMPACT_KEYS",
            "self_model,philosophical_stance,understanding_of_operator,conceptual_frameworks",
        ), patch.object(
            rpd_engine.settings, "RRD2_MIN_SHARED_CLARITY", 0.68
        ), patch.object(
            rpd_engine.settings, "RRD2_MIN_DELTA", 0.18
        ), patch.object(
            rpd_engine.settings, "RRD2_MIN_COHESION", 0.52
        ), patch.object(
            rpd_engine.settings, "RRD2_MAX_NEGATIVE_RESONANCE", 0.78
        ):
            gate = rpd_engine._evaluate_rrd2_gate(
                source="process_consolidation",
                candidate_key="self_model",
                shared_clarity_score=0.40,
                structural_cohesion=0.40,
                negative_resonance=0.90,
                rrd2_delta=0.10,
            )

        self.assertTrue(gate["is_gate_subject"])
        self.assertTrue(gate["would_block"])
        self.assertTrue(gate["enforce_block"])
        self.assertIn("threshold_failed:shared_clarity", gate["reasons"])

    async def test_rrd2_gate_ignores_non_high_impact_key(self):
        with patch.object(rpd_engine.settings, "RRD2_MODE", "hybrid"), patch.object(
            rpd_engine.settings, "RRD2_ROLLOUT_PHASE", "C"
        ), patch.object(
            rpd_engine.settings,
            "RRD2_HIGH_IMPACT_KEYS",
            "self_model,philosophical_stance,understanding_of_operator,conceptual_frameworks",
        ):
            gate = rpd_engine._evaluate_rrd2_gate(
                source="process_consolidation",
                candidate_key="communication_preference",
                shared_clarity_score=0.10,
                structural_cohesion=0.10,
                negative_resonance=0.99,
                rrd2_delta=0.01,
            )

        self.assertFalse(gate["high_impact_key"])
        self.assertFalse(gate["is_gate_subject"])
        self.assertFalse(gate["would_block"])
        self.assertFalse(gate["enforce_block"])

    async def test_apply_hybrid_gate_routes_phase_b_shadow_block_to_residue(self):
        conn = _DummyConn()
        pool = _DummyPool(conn)
        corrections = [
            {
                "action": "REVISE",
                "key": "self_model",
                "value": "Attempt high-impact self-model rewrite under unstable resonance.",
            }
        ]
        advisories = [
            {
                "candidate_key": "self_model",
                "candidate_value": "Attempt high-impact self-model rewrite under unstable resonance.",
                "shared_clarity_score": 0.51,
                "topology_warp_delta": 0.12,
                "rrd2_metrics": {
                    "negative_resonance": 0.91,
                    "structural_cohesion": 0.44,
                    "rrd2_delta": 0.11,
                },
                "rrd2_damping": {"applied": True, "reason": "rolling_spike_damped"},
                "rrd2_gate": {
                    "would_block": True,
                    "enforce_block": False,
                    "phase": "B",
                    "reasons": ["threshold_failed:negative_resonance"],
                },
            }
        ]

        result = await rpd_engine.apply_hybrid_gate_to_identity_corrections(
            pool,
            corrections,
            advisories,
            source="process_consolidation",
            ghost_id="omega-7",
        )

        self.assertEqual(len(result["allowed_corrections"]), 1)
        self.assertEqual(len(result["blocked_corrections"]), 0)
        self.assertEqual(len(result["shadow_gate_hits"]), 1)
        self.assertEqual(len(result["shadow_residue_routed"]), 1)
        self.assertTrue(bool((result.get("shadow_reflection_hint") or {}).get("trigger")))

        residue_inserts = [q for (q, _args) in conn.execute_calls if "INSERT INTO reflection_residue" in q]
        self.assertEqual(len(residue_inserts), 1)

    async def test_insert_residue_merges_duplicate_and_promotes_rrd2_reason(self):
        class _ResidueConn(_DummyConn):
            def __init__(self):
                super().__init__()
                self._rows: dict[tuple[str, str], dict] = {}
                self._next_id = 1

            async def fetchrow(self, query, *args):
                q = str(query)
                if "FROM reflection_residue" in q and "candidate_hash" in q:
                    ghost_id = str(args[0])
                    c_hash = str(args[1])
                    row = self._rows.get((ghost_id, c_hash))
                    if row is None:
                        return None
                    if str(row.get("status")) != "pending":
                        return None
                    return dict(row)
                return await super().fetchrow(query, *args)

            async def execute(self, query, *args):
                q = str(query)
                self.execute_calls.append((q, args))
                if "INSERT INTO reflection_residue" in q:
                    ghost_id, source, candidate_type, candidate_key, residue_text, reason, c_hash, metadata_json = args
                    self._rows[(str(ghost_id), str(c_hash))] = {
                        "id": self._next_id,
                        "ghost_id": str(ghost_id),
                        "source": str(source),
                        "candidate_type": str(candidate_type),
                        "candidate_key": str(candidate_key),
                        "residue_text": str(residue_text),
                        "reason": str(reason),
                        "candidate_hash": str(c_hash),
                        "status": "pending",
                        "metadata_json": json.loads(str(metadata_json)),
                    }
                    self._next_id += 1
                    return "INSERT 0 1"
                if "UPDATE reflection_residue" in q and "CASE WHEN $3 THEN 'rrd2_gate'" in q:
                    row_id = int(args[0])
                    source = str(args[1])
                    promote = bool(args[2])
                    metadata_json = json.loads(str(args[3]))
                    for row in self._rows.values():
                        if int(row["id"]) == row_id:
                            if promote:
                                row["source"] = source
                                row["reason"] = "rrd2_gate"
                            row_meta = dict(row.get("metadata_json") or {})
                            row_meta.update(metadata_json)
                            row["metadata_json"] = row_meta
                            break
                    return "UPDATE 1"
                return "OK"

        conn = _ResidueConn()
        c_hash = rpd_engine._candidate_hash("identity_update", "self_model", "value-a")
        conn._rows[("omega-7", c_hash)] = {
            "id": 1,
            "ghost_id": "omega-7",
            "source": "operator_synthesis",
            "candidate_type": "identity_update",
            "candidate_key": "self_model",
            "residue_text": "value-a",
            "reason": "low_shared_clarity",
            "candidate_hash": c_hash,
            "status": "pending",
            "metadata_json": {"seeded": True},
        }

        await rpd_engine._insert_residue_conn(
            conn,
            ghost_id="omega-7",
            source="process_consolidation",
            candidate_type="identity_update",
            candidate_key="self_model",
            candidate_value="value-a",
            reason="rrd2_gate",
            metadata={"gate": {"would_block": True}},
        )

        row = conn._rows[("omega-7", c_hash)]
        self.assertEqual(str(row["reason"]), "rrd2_gate")
        self.assertEqual(str(row["source"]), "process_consolidation")
        meta = dict(row.get("metadata_json") or {})
        self.assertIn("reason_history", meta)
        self.assertIn("low_shared_clarity", list(meta.get("reason_history") or []))
        self.assertIn("rrd2_gate", list(meta.get("reason_history") or []))
        self.assertTrue(bool(meta.get("rrd2_gate_promoted")))
        self.assertIn("gate", meta)


if __name__ == "__main__":
    unittest.main()
