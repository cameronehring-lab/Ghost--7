"""
IIT advisory/soft-governor engine (heuristic backend).
Computes intrinsic causal diagnostics from pre-LLM state only.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import date, datetime, time as dt_time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import asyncpg  # type: ignore

import memory  # type: ignore
from config import settings  # type: ignore
from somatic import build_somatic_snapshot  # type: ignore


ALLOWED_IDENTITY_UPDATED_BY = {
    "process_consolidation",
    "coalescence",
    "coalescence_manual",
    "coalescence_diagnostic",
    "operator_synthesis",
    "canonical_snapshot_001",
    "canonical_snapshot_002",
    "canonical_snapshot_003",
    "system",
    "system_hard_reset",
}


def _json_default(value: Any) -> Any:
    """JSON serializer for records containing datetime-like values."""
    if isinstance(value, (datetime, date, dt_time)):
        return value.isoformat()
    return str(value)


def filter_self_model_rows(rows: list[dict]) -> list[dict]:
    """Filter identity rows to allowed provenance."""
    filtered = []
    for r in rows:
        updated_by = r.get("updated_by")
        if updated_by and str(updated_by) in ALLOWED_IDENTITY_UPDATED_BY:
            filtered.append(
                {
                    "key": r.get("key"),
                    "value": r.get("value"),
                    "updated_by": updated_by,
                }
            )
    return filtered


@dataclass
class IITConfig:
    mode: str = "advisory"  # off|advisory|soft
    backend: str = "heuristic"  # heuristic|pyphi
    cadence_seconds: float = 60.0
    debounce_seconds: float = 10.0


class IITEngine:
    def __init__(self, pool: asyncpg.Pool, sys_state, emotion_state, config: IITConfig):
        self.pool = pool
        self.sys_state = sys_state
        self.emotion_state = emotion_state
        self.config = config
        self._last_run_ts = 0.0

    async def assess(self, reason: str = "scheduled") -> dict[str, Any]:
        t0 = time.time()
        run_id = str(uuid.uuid4())
        substrate, degradation = await self._build_substrate()

        completeness = sum(1 for node in ("affect", "homeostasis", "memory", "self_model", "operator_model", "agency") if substrate.get(node))

        metrics = self._compute_metrics(substrate, completeness)
        advisory = self._build_advisory(degradation, metrics, completeness, reason)

        t1 = time.time()
        record = {
            "run_id": run_id,
            "mode": self.config.mode,
            "backend": self.config.backend,
            "substrate_completeness_score": completeness,
            "not_consciousness_metric": True,
            "substrate": substrate,
            "metrics": metrics,
            "maximal_complex": metrics.get("maximal_complex"),
            "advisory": advisory,
            "compute_ms": (t1 - t0) * 1000,
            "error": None,
        }
        await self._persist(record)
        self._last_run_ts = t1
        return record

    async def _persist(self, record: dict[str, Any]) -> None:
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO iit_assessment_log
                    (run_id, mode, backend, substrate_completeness_score, not_consciousness_metric,
                     substrate_json, metrics_json, maximal_complex_json, advisory_json, compute_ms, error)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                    """,
                    record["run_id"],
                    record["mode"],
                    record["backend"],
                    record["substrate_completeness_score"],
                    record["not_consciousness_metric"],
                    json.dumps(record["substrate"], default=_json_default),
                    json.dumps(record["metrics"], default=_json_default),
                    json.dumps(record.get("maximal_complex"), default=_json_default),
                    json.dumps(record.get("advisory"), default=_json_default),
                    float(record.get("compute_ms") or 0.0),
                    record.get("error"),
                )
        except Exception as e:
            # Persistence failure should not crash the loop
            print(f"IIT persist error: {e}")

    async def _build_substrate(self) -> tuple[dict[str, Any], list[str]]:
        """
        Build substrate nodes only from pre-LLM sources.
        """
        degradation: list[str] = []
        substrate: dict[str, Any] = {}

        # Affect + homeostasis come from somatic snapshot (pre-LLM)
        try:
            somatic_obj = build_somatic_snapshot(self.sys_state.telemetry_cache, self.emotion_state.snapshot())
            s = somatic_obj.model_dump()
        except Exception as e:
            s = {}
            degradation.append(f"affect_unavailable:{e}")

        if s:
            proprio = dict(getattr(self.sys_state, "proprio_state", {}) or {})
            substrate["affect"] = {
                "arousal": s.get("arousal"),
                "valence": s.get("valence"),
                "stress": s.get("stress"),
                "anxiety": s.get("anxiety"),
                "coherence": s.get("coherence"),
                "dominant_traces": (s.get("dominant_traces") or [])[:5],
                "proprio_pressure": proprio.get("proprio_pressure"),
            }
            substrate["homeostasis"] = {
                "quietude_active": bool((s.get("self_preferences") or {}).get("quietude_active", False)),
                "gate_threshold": s.get("gate_threshold"),
                "hours_awake": s.get("hours_awake"),
                "host_hours_awake": s.get("host_hours_awake"),
                "load_avg_1": s.get("load_avg_1"),
                "cpu_percent": s.get("cpu_percent"),
                "temperature": s.get("temperature_c"),
                "internet_mood": s.get("internet_mood"),
                "proprio_gate_state": proprio.get("gate_state"),
                "proprio_cadence_modifier": proprio.get("cadence_modifier"),
            }
        else:
            substrate["affect"] = None
            substrate["homeostasis"] = None

        # Memory state from DB (counts only, lightweight)
        try:
            async with self.pool.acquire() as conn:
                monologues = await conn.fetchval("SELECT COUNT(*) FROM monologues WHERE ghost_id = $1", settings.GHOST_ID)
                sessions = await conn.fetchval("SELECT COUNT(*) FROM sessions WHERE ghost_id = $1", settings.GHOST_ID)
                vectors = await conn.fetchval("SELECT COUNT(*) FROM vector_memories WHERE ghost_id = $1", settings.GHOST_ID)
                coal = await conn.fetchrow(
                    "SELECT interaction_count, EXTRACT(EPOCH FROM created_at) as ts FROM coalescence_log WHERE ghost_id = $1 ORDER BY created_at DESC LIMIT 1",
                    settings.GHOST_ID,
                )
            substrate["memory"] = {
                "monologue_count": int(monologues or 0),
                "session_count": int(sessions or 0),
                "vector_memory_count": int(vectors or 0),
                "last_coalescence_interactions": int(coal["interaction_count"]) if coal else None,
                "last_coalescence_epoch": float(coal["ts"]) if coal else None,
            }
        except Exception as e:
            substrate["memory"] = None
            degradation.append(f"memory_unavailable:{e}")

        # Self model from identity_matrix with updated_by allowlist
        substrate["self_model"] = None
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT key, value, updated_by
                    FROM identity_matrix
                    WHERE ghost_id = $1
                    """,
                    settings.GHOST_ID,
                )
            filtered = filter_self_model_rows([dict(r) for r in rows])
            if filtered:
                substrate["self_model"] = filtered
            else:
                degradation.append("self_model_disallowed_or_empty")
        except Exception as e:
            degradation.append(f"self_model_unavailable:{e}")

        # Operator model (active beliefs + contradictions)
        try:
            async with self.pool.acquire() as conn:
                beliefs = await conn.fetch(
                    """
                    SELECT dimension, belief, confidence, evidence_count
                    FROM operator_model
                    WHERE ghost_id = $1 AND invalidated_at IS NULL
                    ORDER BY confidence DESC
                    LIMIT 50
                    """,
                    settings.GHOST_ID,
                )
                tensions = await conn.fetch(
                    """
                    SELECT dimension, observed_event, tension_score
                    FROM operator_contradictions
                    WHERE ghost_id = $1 AND status = 'open'
                    ORDER BY tension_score DESC
                    LIMIT 50
                    """,
                    settings.GHOST_ID,
                )
            substrate["operator_model"] = {
                "beliefs": [dict(b) for b in beliefs],
                "open_contradictions": [dict(t) for t in tensions],
            }
        except Exception as e:
            substrate["operator_model"] = None
            degradation.append(f"operator_model_unavailable:{e}")

        # Agency from actuation log + quietude state
        try:
            async with self.pool.acquire() as conn:
                acts = await conn.fetch(
                    """
                    SELECT action, result, created_at
                    FROM actuation_log
                    ORDER BY created_at DESC
                    LIMIT 20
                    """
                )
            substrate["agency"] = {
                "recent_actuations": [dict(a) for a in acts],
                "quietude_active": bool((substrate.get("homeostasis") or {}).get("quietude_active", False)),
                "proprio_gate_state": (substrate.get("homeostasis") or {}).get("proprio_gate_state"),
            }
        except Exception as e:
            substrate["agency"] = None
            degradation.append(f"agency_unavailable:{e}")

        return substrate, degradation

    # ── Feature extraction ────────────────────────────────────────────────────

    @staticmethod
    def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
        try:
            return max(lo, min(hi, float(v or 0.0)))
        except (TypeError, ValueError):
            return lo

    def _extract_node_features(self, substrate: dict[str, Any]) -> dict[str, list[float]]:
        """Return a normalized float vector for each present substrate node."""
        import math as _math
        c = self._clamp
        features: dict[str, list[float]] = {}

        # Affect: arousal, valence (shifted to 0-1), stress, anxiety, coherence, proprio_pressure
        if substrate.get("affect"):
            a = substrate["affect"]
            features["affect"] = [
                c(a.get("arousal", 0.5)),
                c((float(a.get("valence") or 0.0) + 1.0) / 2.0),
                c(a.get("stress", 0.5)),
                c(a.get("anxiety", 0.5)),
                c(a.get("coherence", 0.5)),
                c(a.get("proprio_pressure", 0.0)),
            ]

        # Homeostasis: quietude, gate_threshold, fatigue, load, cpu, temp, cadence, gate_state
        # gate_map here: OPEN=0.0 (low homeostatic load), SUPPRESSED=1.0 (high load).
        # Semantics: how much load/pressure is being exerted on the system.
        if substrate.get("homeostasis"):
            h = substrate["homeostasis"]
            gate_map = {"OPEN": 0.0, "THROTTLED": 0.5, "SUPPRESSED": 1.0}
            features["homeostasis"] = [
                1.0 if h.get("quietude_active") else 0.0,
                c(float(h.get("gate_threshold") or 1.0) / 3.0),
                c(float(h.get("hours_awake") or 0.0) / 24.0),
                c(float(h.get("load_avg_1") or 0.0) / 4.0),
                c(float(h.get("cpu_percent") or 0.0) / 100.0),
                c(float(h.get("temperature") or 50.0) / 100.0),
                c(1.0 / max(0.1, float(h.get("proprio_cadence_modifier") or 1.0))),
                gate_map.get(str(h.get("proprio_gate_state") or "OPEN").upper(), 0.0),
            ]

        # Memory: monologue, session, vector density (log-scaled), coalescence recency
        if substrate.get("memory"):
            m = substrate["memory"]
            coal_epoch = float(m.get("last_coalescence_epoch") or 0.0)
            recency = c(1.0 - min(1.0, (time.time() - coal_epoch) / 86400.0)) if coal_epoch else 0.0
            features["memory"] = [
                c(_math.log1p(int(m.get("monologue_count") or 0)) / 8.0),
                c(_math.log1p(int(m.get("session_count") or 0)) / 7.0),
                c(_math.log1p(int(m.get("vector_memory_count") or 0)) / 9.0),
                recency,
            ]

        # Self-model: entry count, updater diversity
        if substrate.get("self_model") and isinstance(substrate["self_model"], list):
            sm = substrate["self_model"]
            updaters = len({r.get("updated_by") for r in sm if r.get("updated_by")})
            features["self_model"] = [
                c(len(sm) / 60.0),
                c(updaters / 6.0),
            ]

        # Operator model: belief richness, mean confidence, contradiction density
        if substrate.get("operator_model") and isinstance(substrate["operator_model"], dict):
            om = substrate["operator_model"]
            beliefs = om.get("beliefs") or []
            tensions = om.get("open_contradictions") or []
            mean_conf = (sum(float(b.get("confidence") or 0.5) for b in beliefs) / len(beliefs)) if beliefs else 0.5
            features["operator_model"] = [
                c(len(beliefs) / 50.0),
                c(mean_conf),
                c(len(tensions) / 10.0),
            ]

        # Agency: actuation density, gate openness, quietude
        # gate_map here: OPEN=1.0 (full agency), SUPPRESSED=0.0 (no agency).
        # Semantics: how much agentic capacity is currently available. Intentionally
        # inverted vs the homeostasis gate_map, which tracks load (not capability).
        if substrate.get("agency") and isinstance(substrate["agency"], dict):
            ag = substrate["agency"]
            gate_map = {"OPEN": 1.0, "THROTTLED": 0.5, "SUPPRESSED": 0.0}
            features["agency"] = [
                c(len(ag.get("recent_actuations") or []) / 20.0),
                gate_map.get(str(ag.get("proprio_gate_state") or "OPEN").upper(), 1.0),
                1.0 if ag.get("quietude_active") else 0.0,
            ]

        return features

    # ── Coupling ──────────────────────────────────────────────────────────────

    @staticmethod
    def _cosine(v1: list[float], v2: list[float]) -> float:
        """Cosine similarity between two vectors, zero-padded to equal length."""
        n = max(len(v1), len(v2))
        a = v1 + [0.0] * (n - len(v1))
        b = v2 + [0.0] * (n - len(v2))
        dot = sum(x * y for x, y in zip(a, b))
        mag = (sum(x * x for x in a) ** 0.5) * (sum(x * x for x in b) ** 0.5)
        return dot / mag if mag > 1e-9 else 0.0

    def _build_coupling_matrix(
        self, node_keys: list[str], features: dict[str, list[float]]
    ) -> list[list[float]]:
        """n×n coupling matrix — entry C[i][j] = cosine similarity of node i and node j feature vectors."""
        n = len(node_keys)
        C = [[0.0] * n for _ in range(n)]
        for i, ni in enumerate(node_keys):
            for j, nj in enumerate(node_keys):
                if i != j and ni in features and nj in features:
                    C[i][j] = self._cosine(features[ni], features[nj])
        return C

    # ── MIP-based Φ ──────────────────────────────────────────────────────────

    @staticmethod
    def _phi_mip(
        coupling: list[list[float]], node_keys: list[str]
    ) -> tuple[float, list[str], list[str]]:
        """
        Minimum-information-partition phi.
        Enumerate all non-trivial bipartitions; phi = min cross-partition coupling,
        normalized by the size of the cut (|A|×|B|).
        Returns (phi_normalized, part_A_keys, part_B_keys).
        """
        n = len(node_keys)
        if n < 2:
            return 0.0, node_keys[:], []

        min_phi = float("inf")
        mip_a: list[str] = []
        mip_b: list[str] = []

        for mask in range(1, 1 << (n - 1)):  # canonical halves only
            part_a = [i for i in range(n) if mask & (1 << i)]
            part_b = [i for i in range(n) if not (mask & (1 << i))]
            if not part_a or not part_b:
                continue
            cut = sum(coupling[i][j] for i in part_a for j in part_b)
            cut_norm = cut / (len(part_a) * len(part_b))
            if cut_norm < min_phi:
                min_phi = cut_norm
                mip_a = [node_keys[i] for i in part_a]
                mip_b = [node_keys[i] for i in part_b]

        return min(1.0, min_phi if min_phi < float("inf") else 0.0), mip_a, mip_b

    # ── Maximal complex ───────────────────────────────────────────────────────

    def _maximal_complex(
        self, node_keys: list[str], coupling: list[list[float]]
    ) -> dict[str, Any]:
        """
        Find the subset of nodes (≥2) with the highest normalized MIP phi.
        Brute-force over 2^n subsets — tractable for n=6.
        """
        n = len(node_keys)
        best_phi = 0.0
        best_nodes: list[str] = node_keys[:]

        for mask in range(3, 1 << n):  # at least 2 bits set
            indices = [i for i in range(n) if mask & (1 << i)]
            if len(indices) < 2:
                continue
            sub_keys = [node_keys[i] for i in indices]
            sub_C = [[coupling[i][j] for j in indices] for i in indices]
            phi, _, _ = self._phi_mip(sub_C, sub_keys)
            if phi > best_phi:
                best_phi = phi
                best_nodes = sub_keys

        return {
            "nodes": best_nodes,
            "node_count": len(best_nodes),
            "phi": round(best_phi, 3),
            "supporting_nodes": best_nodes,
        }

    # ── Main metrics computation ──────────────────────────────────────────────

    def _compute_metrics(self, substrate: dict[str, Any], completeness: int) -> dict[str, Any]:
        node_keys = [k for k in ("affect", "homeostasis", "memory", "self_model", "operator_model", "agency") if substrate.get(k)]
        n = len(node_keys)

        features = self._extract_node_features(substrate)
        coupling = self._build_coupling_matrix(node_keys, features)

        # Total coupling normalized by max possible directed edges
        total_coupling = sum(coupling[i][j] for i in range(n) for j in range(n) if i != j)
        max_edges = n * (n - 1)
        intrinsic_info = total_coupling / max_edges if max_edges > 0 else 0.0

        # MIP-based phi
        phi_mip, mip_a, mip_b = self._phi_mip(coupling, node_keys)

        # Maximal complex
        maximal_complex = self._maximal_complex(node_keys, coupling)

        integration = intrinsic_info
        exclusion_margin = max(0.0, phi_mip - 0.3)
        composition_density = min(1.0, n / 6.0)

        # phi_proxy: MIP phi is the primary signal; intrinsic_info and breadth are secondary
        phi_proxy = min(1.0, phi_mip * 0.6 + intrinsic_info * 0.3 + composition_density * 0.1)

        return {
            "intrinsic_info": round(intrinsic_info, 3),
            "integration_index": round(integration, 3),
            "exclusion_margin": round(exclusion_margin, 3),
            "composition_density": round(composition_density, 3),
            "phi_proxy": round(phi_proxy, 3),
            "phi_mip": round(phi_mip, 3),
            "mip_partition": [mip_a, mip_b],
            "coupling_matrix": {
                "nodes": node_keys,
                "values": [[round(coupling[i][j], 3) for j in range(n)] for i in range(n)],
            },
            "maximal_complex": maximal_complex,
        }

    def _build_advisory(self, degradation: list[str], metrics: dict[str, Any], completeness: int, reason: str) -> dict[str, Any]:
        phi = metrics.get("phi_mip", metrics.get("phi_proxy", 0.0))
        mip = metrics.get("mip_partition", [[], []])
        return {
            "reason": reason,
            "degradation_list": degradation,
            "completeness_score": completeness,
            "phi_proxy_band": "low" if metrics["phi_proxy"] < 0.33 else "medium" if metrics["phi_proxy"] < 0.66 else "high",
            "integration_band": "fragmented" if metrics["integration_index"] < 0.4 else "partial" if metrics["integration_index"] < 0.7 else "integrated",
            "phi_mip": round(phi, 3),
            "minimum_information_partition": {"A": mip[0] if mip else [], "B": mip[1] if len(mip) > 1 else []},
            "maximal_complex": (metrics.get("maximal_complex") or {}).get("nodes", []),
        }


async def run_ad_hoc_assessment(engine: IITEngine, reason: str = "manual") -> dict[str, Any]:
    return await engine.assess(reason=reason)
