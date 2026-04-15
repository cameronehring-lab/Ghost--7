"""
OMEGA PROTOCOL — Neural Topology Service
Constructs the graph structure for 3D visualization of Ghost's cognitive mapping.
"""

import json
import logging
import math
import re
import traceback
from collections import defaultdict
from datetime import datetime
from typing import Any

import consciousness
from config import settings

logger = logging.getLogger("omega.neural_topology")


def cosine_similarity(v1: Any, v2: Any) -> float:
    """Calculate cosine similarity between two vectors. Handles list, numpy array, or string input."""
    if isinstance(v1, str):
        try:
            v1 = json.loads(v1)
        except (ValueError, TypeError):
            return 0.0
    if isinstance(v2, str):
        try:
            v2 = json.loads(v2)
        except (ValueError, TypeError):
            return 0.0

    if not hasattr(v1, "__iter__") or not hasattr(v2, "__iter__"):
        return 0.0

    dot_product = sum(float(a) * float(b) for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(float(a) * float(a) for a in v1))
    mag2 = math.sqrt(sum(float(a) * float(a) for a in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot_product / (mag1 * mag2)


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(value: Any) -> set[str]:
    text = _normalize_text(value)
    if not text:
        return set()
    return {t for t in text.split(" ") if len(t) >= 2}


def _safe_ts(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return value.timestamp()
    except Exception:
        return None


def _link_dedupe_key(link: dict[str, Any]) -> tuple[str, str, str]:
    source = str(link.get("source") or "")
    target = str(link.get("target") or "")
    edge_type = str(link.get("type") or "")
    return (source, target, edge_type)


def _merge_link(best: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    out = dict(best)
    in_strength = float(incoming.get("strength") or 0.0)
    best_strength = float(best.get("strength") or 0.0)
    if in_strength > best_strength:
        out["strength"] = in_strength
    if not out.get("label") and incoming.get("label"):
        out["label"] = incoming.get("label")
    if "curvature" not in out and "curvature" in incoming:
        out["curvature"] = incoming["curvature"]
    if "particle_speed" not in out and "particle_speed" in incoming:
        out["particle_speed"] = incoming["particle_speed"]
    if "color" not in out and "color" in incoming:
        out["color"] = incoming["color"]
    return out


def _dedupe_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for link in links:
        key = _link_dedupe_key(link)
        if not key[0] or not key[1] or not key[2]:
            continue
        if key not in deduped:
            deduped[key] = dict(link)
        else:
            deduped[key] = _merge_link(deduped[key], link)
    return list(deduped.values())


def _rolodex_memory_match_score(
    *,
    memory_text_norm: str,
    memory_tokens: set[str],
    person_display_norm: str,
    person_key_phrase_norm: str,
    person_tokens: set[str],
    fact_value_norm: str,
    evidence_text_norm: str,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    if person_display_norm and len(person_display_norm) >= 3 and person_display_norm in memory_text_norm:
        score += 0.44
        reasons.append("person_display")
    if person_key_phrase_norm and len(person_key_phrase_norm) >= 3 and person_key_phrase_norm in memory_text_norm:
        score += 0.31
        reasons.append("person_key")

    token_hits = len(person_tokens.intersection(memory_tokens))
    if token_hits >= 2:
        score += 0.26
        reasons.append("person_tokens")
    elif token_hits == 1:
        score += 0.14
        reasons.append("person_token")

    if fact_value_norm and len(fact_value_norm) >= 4 and fact_value_norm in memory_text_norm:
        score += 0.30
        reasons.append("fact_value")

    if evidence_text_norm and len(evidence_text_norm) >= 18:
        snippet = evidence_text_norm[:96]
        if snippet and snippet in memory_text_norm:
            score += 0.56
            reasons.append("evidence_snippet")
        else:
            evidence_tokens = _tokenize(evidence_text_norm)
            overlap = len(evidence_tokens.intersection(memory_tokens))
            if overlap >= 3:
                score += 0.18
                reasons.append("evidence_tokens")

    return (min(1.0, score), reasons)


async def build_topology_graph(pool, ghost_id: str, similarity_threshold: float = 0.65) -> dict[str, Any]:
    """
    Builds a high-rigor node/edge graph for diagnostic visualization.
    Integrates explicit audit trails, somatic signatures, and person-rolodex alignment.
    """
    ghost_id = ghost_id or settings.GHOST_ID
    if pool is None:
        return {"nodes": [], "links": [], "error": "Database pool unavailable"}

    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    rolodex_alignment: dict[str, Any] = {
        "profiles_count": 0,
        "facts_count": 0,
        "profile_nodes": 0,
        "fact_nodes": 0,
        "missing_profile_nodes": 0,
        "missing_fact_nodes": 0,
        "synthetic_profile_nodes": 0,
        "orphan_fact_rows_count": 0,
        "orphan_fact_rows_sample": [],
        "session_bindings_total": 0,
        "profiles_with_session_binding": 0,
        "profile_association_gap_count": 0,
        "profile_association_gaps": [],
        "association_coverage": 1.0,
        "person_fact_edges": 0,
        "person_relation_edges": 0,
        "memory_person_edges": 0,
        "memory_person_reference_edges": 0,
        "person_activity_anchor_edges": 0,
        "memory_fact_edges": 0,
        "connector_idea_edges": 0,
        "idea_nodes": 0,
        "ideas_with_connectors": 0,
        "idea_connector_coverage": 1.0,
        "idea_place_coverage": 1.0,
        "idea_thing_coverage": 1.0,
        "idea_person_coverage": 1.0,
        "identity_nodes": 0,
        "phenomenology_nodes": 0,
        "identity_phenomenology_edges": 0,
        "identity_link_coverage": 1.0,
        "phenomenology_link_coverage": 1.0,
        "identity_orphan_count": 0,
        "phenomenology_orphan_count": 0,
        "profile_fact_mismatches": [],
        "mapping_ok": False,
        "alignment_ok": False,
    }
    entity_expansion: dict[str, Any] = {
        "place_nodes": 0,
        "thing_nodes": 0,
        "emergent_idea_nodes": 0,
        "person_place_edges": 0,
        "person_thing_edges": 0,
        "memory_place_edges": 0,
        "memory_thing_edges": 0,
        "memory_idea_edges": 0,
        "idea_identity_edges": 0,
        "idea_place_edges": 0,
        "idea_thing_edges": 0,
        "idea_person_edges": 0,
    }

    try:
        async with pool.acquire() as conn:
            if hasattr(consciousness, "_ensure_vector_registered"):
                await consciousness._ensure_vector_registered(conn)

            # 1. Fetch memories and nearby somatic context.
            memory_rows = await conn.fetch(
                """
                SELECT v.id, v.content, v.memory_type, v.created_at, v.embedding,
                       m.somatic_state, m.source_tag AS monologue_source,
                       p.before_state as phen_state, p.trigger_source as phen_source
                FROM vector_memories v
                LEFT JOIN LATERAL (
                    SELECT m.somatic_state, 'monologue'::text AS source_tag
                    FROM monologues m
                    WHERE m.ghost_id = v.ghost_id
                      AND ABS(EXTRACT(EPOCH FROM v.created_at) - EXTRACT(EPOCH FROM m.created_at)) < 10
                    ORDER BY ABS(EXTRACT(EPOCH FROM v.created_at) - EXTRACT(EPOCH FROM m.created_at)) ASC
                    LIMIT 1
                ) m ON TRUE
                LEFT JOIN LATERAL (
                    SELECT p.before_state, p.trigger_source
                    FROM phenomenology_logs p
                    WHERE p.ghost_id = v.ghost_id
                      AND ABS(EXTRACT(EPOCH FROM v.created_at) - EXTRACT(EPOCH FROM p.created_at)) < 10
                    ORDER BY ABS(EXTRACT(EPOCH FROM v.created_at) - EXTRACT(EPOCH FROM p.created_at)) ASC
                    LIMIT 1
                ) p ON TRUE
                WHERE v.ghost_id = $1
                ORDER BY v.created_at DESC
                LIMIT 150
                """,
                ghost_id,
            )

            mem_lookup: list[dict[str, Any]] = []
            for r in memory_rows:
                m_id = f"mem_{r['id']}"
                somatic = r["somatic_state"] or r["phen_state"]
                if isinstance(somatic, str):
                    try:
                        somatic = json.loads(somatic)
                    except Exception:
                        somatic = {}
                content_text = str(r["content"] or "")
                content_norm = _normalize_text(content_text)
                content_tokens = _tokenize(content_text)

                nodes.append(
                    {
                        "id": m_id,
                        "type": "memory",
                        "sub_type": r["memory_type"],
                        "content": content_text,
                        "timestamp": _safe_ts(r["created_at"]),
                        "provenance": r["monologue_source"] or r["phen_source"] or "autonomous",
                        "somatic_signature": {
                            "stress": somatic.get("stress") or somatic.get("stress (load)") if somatic else None,
                            "arousal": somatic.get("arousal") or somatic.get("arousal (restlessness)") if somatic else None,
                            "anxiety": somatic.get("anxiety") or somatic.get("anxiety (unease)") if somatic else None,
                            "coherence": somatic.get("coherence") or somatic.get("coherence (clarity)") if somatic else None,
                        },
                        "val": 12,
                    }
                )
                mem_lookup.append(
                    {
                        "id": m_id,
                        "embedding": r["embedding"],
                        "content": content_text,
                        "content_norm": content_norm,
                        "content_tokens": content_tokens,
                        "timestamp": _safe_ts(r["created_at"]) or 0.0,
                    }
                )

            # 2. Similarity edges between memory nodes.
            for i in range(len(mem_lookup)):
                for j in range(i + 1, len(mem_lookup)):
                    sim = cosine_similarity(mem_lookup[i]["embedding"], mem_lookup[j]["embedding"])
                    if sim >= similarity_threshold:
                        links.append(
                            {
                                "source": mem_lookup[i]["id"],
                                "target": mem_lookup[j]["id"],
                                "type": "similarity",
                                "strength": sim,
                                "label": f"semantic_sim: {sim:.2f}",
                            }
                        )

            # 3. Identity matrix nodes + semantic grounding.
            identity_rows = await conn.fetch(
                "SELECT id, key, value, updated_at, updated_by FROM identity_matrix WHERE ghost_id = $1",
                ghost_id,
            )
            identity_map: dict[str, str] = {}
            identity_nodes_by_id: dict[str, dict[str, Any]] = {}
            identity_profiles: dict[str, dict[str, Any]] = {}
            identity_timestamps: dict[str, float | None] = {}
            for r in identity_rows:
                i_id = f"id_{r['id']}"
                i_key = str(r["key"] or "")
                i_value = str(r["value"] or "")
                i_key_phrase = i_key.replace("_", " ").strip()
                i_profile_text = f"{i_key_phrase} {i_value}".strip()
                i_ts = _safe_ts(r["updated_at"])
                i_node = {
                    "id": i_id,
                    "type": "identity",
                    "key": i_key,
                    "content": i_value,
                    "provenance": r["updated_by"] or "system",
                    "timestamp": i_ts,
                    "val": 30,
                }
                identity_map[i_key] = i_id
                identity_nodes_by_id[i_id] = i_node
                identity_timestamps[i_id] = i_ts
                identity_profiles[i_id] = {
                    "key": i_key,
                    "key_phrase_norm": _normalize_text(i_key_phrase),
                    "value_norm": _normalize_text(i_value),
                    "value_excerpt_norm": _normalize_text(i_value)[:96],
                    "tokens": _tokenize(i_profile_text),
                }
                nodes.append(i_node)
                for m_node in mem_lookup:
                    if i_key and i_key.lower() in str(m_node["content"]).lower():
                        links.append(
                            {
                                "source": m_node["id"],
                                "target": i_id,
                                "type": "semantic_grounding",
                                "strength": 0.8,
                                "label": f"identity_ref: {i_key}",
                                "curvature": 0.1,
                                "color": "#aa88ff55",
                            }
                        )

            # 4. Audit trail consolidation edges (memory -> identity).
            audit_rows: list[dict[str, Any]] = []
            identity_audit_ts_by_key: defaultdict[str, list[float]] = defaultdict(list)
            idx_exists = await conn.fetchval("SELECT to_regclass('identity_audit_log')")
            if idx_exists:
                audit_rows = await conn.fetch(
                    """
                    SELECT key, prev_value, new_value, created_at, updated_by
                    FROM identity_audit_log
                    WHERE ghost_id = $1
                    ORDER BY created_at DESC
                    LIMIT 60
                    """,
                    ghost_id,
                )
                for audit in audit_rows:
                    key = str(audit["key"] or "")
                    audit_ts = _safe_ts(audit["created_at"]) or 0.0
                    if key and audit_ts > 0:
                        identity_audit_ts_by_key[key].append(float(audit_ts))
                    if key not in identity_map:
                        continue
                    target_id = identity_map[key]
                    for m_node in mem_lookup:
                        delta = audit_ts - float(m_node["timestamp"] or 0.0)
                        if 0 < delta < 600:
                            links.append(
                                {
                                    "source": m_node["id"],
                                    "target": target_id,
                                    "type": "consolidation",
                                    "strength": 0.9,
                                    "label": f"audit_trail: {audit['updated_by']}",
                                    "curvature": 0.3,
                                    "particle_speed": 0.02,
                                    "color": "#aa88ffcc",
                                }
                            )

            # 5. Phenomenological event nodes + causal ties to memory.
            phenom_rows = await conn.fetch(
                """
                SELECT id, trigger_source, subjective_report, created_at, before_state
                FROM phenomenology_logs
                WHERE ghost_id = $1
                ORDER BY created_at DESC
                LIMIT 50
                """,
                ghost_id,
            )
            phenom_nodes: list[dict[str, Any]] = []
            for p in phenom_rows:
                p_id = f"phen_{p['id']}"
                p_ts = _safe_ts(p["created_at"]) or 0.0
                subjective_report = str(p["subjective_report"] or "")
                somatic = p["before_state"]
                if isinstance(somatic, str):
                    try:
                        somatic = json.loads(somatic)
                    except Exception:
                        somatic = {}

                nodes.append(
                    {
                        "id": p_id,
                        "type": "phenomenology",
                        "content": subjective_report,
                        "provenance": p["trigger_source"],
                        "timestamp": p_ts,
                        "val": 20,
                        "color": "#00ffff",
                        "somatic_signature": {
                            "stress": somatic.get("stress") or somatic.get("stress (load)") if somatic else None,
                            "arousal": somatic.get("arousal") or somatic.get("arousal (restlessness)") if somatic else None,
                            "anxiety": somatic.get("anxiety") or somatic.get("anxiety (unease)") if somatic else None,
                            "coherence": somatic.get("coherence") or somatic.get("coherence (clarity)") if somatic else None,
                        },
                    }
                )
                phenom_nodes.append(
                    {
                        "id": p_id,
                        "timestamp": p_ts,
                        "content_norm": _normalize_text(subjective_report),
                        "content_tokens": _tokenize(subjective_report),
                    }
                )
                for m_node in mem_lookup:
                    delta = float(m_node["timestamp"] or 0.0) - p_ts
                    if 0 < delta < 120:
                        links.append(
                            {
                                "source": p_id,
                                "target": m_node["id"],
                                "type": "phenomenological",
                                "strength": 0.85,
                                "label": "causal_generation",
                                "curvature": -0.2,
                                "particle_speed": 0.04,
                                "color": "#00ffffcc",
                            }
                        )

                # Ground orphans to identity
                phen_linked = any(l["source"] == p_id for l in links if l["type"] == "phenomenological")
                if not phen_linked:
                    # Link to self_model or any identity if possible
                    anchor_id = identity_map.get("self_model") or identity_map.get("subjective_anchor")
                    if not anchor_id and identity_map:
                        anchor_id = list(identity_map.values())[0]
                    if anchor_id:
                        links.append(
                            {
                                "source": p_id,
                                "target": anchor_id,
                                "type": "phenomenological",
                                "strength": 0.35,
                                "label": "axiomatic_grounding",
                                "curvature": -0.1,
                                "color": "#00ffff88",
                            }
                        )

            # 5b. Evidence-scored phenomenology <-> identity alignment.
            if phenom_nodes and identity_profiles:
                for phen in phenom_nodes:
                    phen_id = str(phen["id"])
                    phen_ts = float(phen.get("timestamp") or 0.0)
                    phen_norm = str(phen.get("content_norm") or "")
                    phen_tokens = set(phen.get("content_tokens") or set())
                    scored_identities: list[tuple[float, str, list[str]]] = []

                    for identity_id, profile in identity_profiles.items():
                        score = 0.0
                        reasons: list[str] = []
                        profile_tokens = set(profile.get("tokens") or set())
                        key_phrase_norm = str(profile.get("key_phrase_norm") or "")
                        value_excerpt_norm = str(profile.get("value_excerpt_norm") or "")
                        identity_key = str(profile.get("key") or "")

                        overlap = len(phen_tokens.intersection(profile_tokens))
                        if overlap > 0 and profile_tokens:
                            overlap_ratio = overlap / max(1.0, float(min(8, len(profile_tokens))))
                            score += min(0.42, 0.12 + (overlap_ratio * 0.55))
                            reasons.append("lexical_overlap")

                        if key_phrase_norm and len(key_phrase_norm) >= 4 and key_phrase_norm in phen_norm:
                            score += 0.31
                            reasons.append("key_phrase")

                        if value_excerpt_norm and len(value_excerpt_norm) >= 12 and value_excerpt_norm in phen_norm:
                            score += 0.17
                            reasons.append("value_phrase")

                        audit_ts_list = identity_audit_ts_by_key.get(identity_key, [])
                        if phen_ts > 0 and audit_ts_list:
                            nearest_delta = min(abs(phen_ts - float(ts)) for ts in audit_ts_list)
                            if nearest_delta <= 3600:
                                temporal_score = max(0.0, 1.0 - (nearest_delta / 3600.0))
                                score += temporal_score * 0.24
                                reasons.append("audit_temporal")

                        score = min(1.0, score)
                        if score >= 0.38:
                            scored_identities.append((score, identity_id, reasons))

                    scored_identities.sort(key=lambda item: item[0], reverse=True)
                    for score, identity_id, reasons in scored_identities[:2]:
                        links.append(
                            {
                                "source": phen_id,
                                "target": identity_id,
                                "type": "phenomenology_identity_alignment",
                                "strength": score,
                                "label": f"identity_alignment:{','.join(reasons[:2])}",
                                "curvature": -0.07,
                                "particle_speed": 0.015,
                                "color": "#7fe8ffcc",
                            }
                        )

            # 6. Operator beliefs + contradictions.
            beliefs = await conn.fetch(
                """
                SELECT id, dimension, belief, confidence, evidence_count
                FROM operator_model
                WHERE ghost_id = $1 AND invalidated_at IS NULL
                """,
                ghost_id,
            )
            belief_ids: dict[str, str] = {}
            for b in beliefs:
                b_id = f"belief_{b['id']}"
                dimension = str(b["dimension"] or "")
                belief_ids[dimension] = b_id
                nodes.append(
                    {
                        "id": b_id,
                        "type": "belief",
                        "dimension": dimension,
                        "content": b["belief"],
                        "provenance": "operator_model",
                        "confidence": float(b["confidence"] or 0.0),
                        "evidence_count": int(b["evidence_count"] or 0),
                        "val": 15,
                    }
                )

            tensions = await conn.fetch(
                """
                SELECT id, dimension, observed_event, tension_score
                FROM operator_contradictions
                WHERE ghost_id = $1 AND status = 'open'
                """,
                ghost_id,
            )
            for t in tensions:
                t_id = f"tension_{t['id']}"
                dimension = str(t["dimension"] or "")
                tension_score = float(t["tension_score"] or 0.0)
                nodes.append(
                    {
                        "id": t_id,
                        "type": "contradiction",
                        "dimension": dimension,
                        "content": t["observed_event"],
                        "val": 22,
                        "color": "#ff0088",
                        "tension_score": tension_score,
                    }
                )
                if dimension in belief_ids:
                    links.append(
                        {
                            "source": t_id,
                            "target": belief_ids[dimension],
                            "type": "conflict",
                            "strength": tension_score,
                            "label": "logical_contradiction",
                        }
                    )

            # 7. Person Rolodex alignment graph (person/fact nodes + explicit edges).
            person_rows = await conn.fetch(
                """
                SELECT
                    p.person_key,
                    p.display_name,
                    p.first_seen,
                    p.last_seen,
                    p.interaction_count,
                    p.mention_count,
                    p.confidence,
                    p.is_locked,
                    p.locked_at,
                    p.contact_handle,
                    p.notes,
                    COALESCE(f.fact_count, 0)::int AS fact_count
                FROM person_rolodex p
                LEFT JOIN LATERAL (
                    SELECT COUNT(*)::int AS fact_count
                    FROM person_memory_facts f
                    WHERE f.ghost_id = p.ghost_id
                      AND f.person_key = p.person_key
                      AND f.invalidated_at IS NULL
                ) f ON TRUE
                WHERE p.ghost_id = $1
                ORDER BY p.last_seen DESC, p.interaction_count DESC, p.mention_count DESC
                """,
                ghost_id,
            )
            fact_rows = await conn.fetch(
                """
                SELECT
                    id,
                    person_key,
                    fact_type,
                    fact_value,
                    confidence,
                    source_role,
                    evidence_text,
                    source_session_id,
                    observation_count,
                    first_observed_at,
                    last_observed_at,
                    metadata
                FROM person_memory_facts
                WHERE ghost_id = $1
                  AND invalidated_at IS NULL
                ORDER BY last_observed_at DESC, confidence DESC
                """,
                ghost_id,
            )
            binding_rows = await conn.fetch(
                """
                SELECT person_key, COUNT(*)::int AS session_binding_count, MAX(updated_at) AS last_binding_at
                FROM person_session_binding
                WHERE ghost_id = $1
                GROUP BY person_key
                """,
                ghost_id,
            )
            canonical_place_rows = await conn.fetch(
                """
                SELECT place_key, display_name, confidence, status, provenance, notes, metadata, updated_at
                FROM place_entities
                WHERE ghost_id = $1
                  AND (invalidated_at IS NULL)
                ORDER BY updated_at DESC
                """,
                ghost_id,
            )
            canonical_thing_rows = await conn.fetch(
                """
                SELECT thing_key, display_name, confidence, status, provenance, notes, metadata, updated_at
                FROM thing_entities
                WHERE ghost_id = $1
                  AND (invalidated_at IS NULL)
                ORDER BY updated_at DESC
                """,
                ghost_id,
            )
            canonical_person_place_rows = await conn.fetch(
                """
                SELECT person_key, place_key, confidence, source, evidence_text, metadata, updated_at
                FROM person_place_associations
                WHERE ghost_id = $1
                  AND invalidated_at IS NULL
                ORDER BY updated_at DESC
                """,
                ghost_id,
            )
            canonical_person_thing_rows = await conn.fetch(
                """
                SELECT person_key, thing_key, confidence, source, evidence_text, metadata, updated_at
                FROM person_thing_associations
                WHERE ghost_id = $1
                  AND invalidated_at IS NULL
                ORDER BY updated_at DESC
                """,
                ghost_id,
            )
            canonical_idea_assoc_rows = await conn.fetch(
                """
                SELECT concept_key, target_type, target_key, confidence, source, metadata, updated_at
                FROM idea_entity_associations
                WHERE ghost_id = $1
                  AND invalidated_at IS NULL
                ORDER BY updated_at DESC
                """,
                ghost_id,
            )

            rolodex_alignment["profiles_count"] = len(person_rows)
            rolodex_alignment["facts_count"] = len(fact_rows)
            binding_map: dict[str, dict[str, Any]] = {
                str(row["person_key"]): {
                    "session_binding_count": int(row["session_binding_count"] or 0),
                    "last_binding_at": _safe_ts(row["last_binding_at"]),
                }
                for row in binding_rows
                if row["person_key"]
            }
            rolodex_alignment["session_bindings_total"] = int(
                sum(int(meta.get("session_binding_count", 0)) for meta in binding_map.values())
            )
            rolodex_alignment["profiles_with_session_binding"] = len(binding_map)

            person_node_map: dict[str, str] = {}
            person_display_norm: dict[str, str] = {}
            person_key_phrase_norm: dict[str, str] = {}
            person_tokens_map: dict[str, set[str]] = {}
            person_last_seen_ts: dict[str, float | None] = {}
            person_priority: dict[str, float] = {}
            fact_count_actual_by_person: defaultdict[str, int] = defaultdict(int)
            place_node_map: dict[str, str] = {}
            thing_node_map: dict[str, str] = {}
            place_node_meta: dict[str, dict[str, Any]] = {}
            thing_node_meta: dict[str, dict[str, Any]] = {}
            synthetic_person_nodes_count = 0
            orphan_fact_rows_count = 0
            orphan_fact_rows_sample: list[dict[str, Any]] = []

            # Canonical place/thing entities are first-class sources.
            for place in canonical_place_rows:
                place_key = str(place["place_key"] or "").strip()
                if not place_key:
                    continue
                place_id = f"place_{place_key}"
                place_node_map[place_key] = place_id
                place_node_meta[place_id] = {
                    "id": place_id,
                    "type": "place",
                    "sub_type": "canonical_place",
                    "place_key": place_key,
                    "content": str(place["display_name"] or place_key.replace("_", " ")),
                    "confidence": float(place["confidence"] or 0.0),
                    "reference_count": 1,
                    "timestamp": _safe_ts(place["updated_at"]),
                    "status": str(place["status"] or "active"),
                    "provenance": str(place["provenance"] or "canonical"),
                    "metadata": place["metadata"] or {},
                    "notes": str(place["notes"] or ""),
                    "val": 12.5,
                }
                nodes.append(place_node_meta[place_id])

            for thing in canonical_thing_rows:
                thing_key = str(thing["thing_key"] or "").strip()
                if not thing_key:
                    continue
                thing_id = f"thing_{thing_key}"
                thing_node_map[thing_key] = thing_id
                thing_node_meta[thing_id] = {
                    "id": thing_id,
                    "type": "thing",
                    "sub_type": "canonical_thing",
                    "thing_key": thing_key,
                    "content": str(thing["display_name"] or thing_key.replace("_", " ")),
                    "confidence": float(thing["confidence"] or 0.0),
                    "reference_count": 1,
                    "timestamp": _safe_ts(thing["updated_at"]),
                    "status": str(thing["status"] or "active"),
                    "provenance": str(thing["provenance"] or "canonical"),
                    "metadata": thing["metadata"] or {},
                    "notes": str(thing["notes"] or ""),
                    "val": 12.0,
                }
                nodes.append(thing_node_meta[thing_id])

            for p in person_rows:
                person_key = str(p["person_key"] or "")
                if not person_key:
                    continue
                display_name = str(p["display_name"] or person_key)
                p_id = f"person_{person_key}"
                person_node_map[person_key] = p_id
                p_display_norm = _normalize_text(display_name)
                p_key_phrase_norm = _normalize_text(person_key.replace("_", " "))
                p_tokens = _tokenize(display_name) | _tokenize(person_key.replace("_", " "))
                person_display_norm[person_key] = p_display_norm
                person_key_phrase_norm[person_key] = p_key_phrase_norm
                person_tokens_map[person_key] = p_tokens

                interaction_count = int(p["interaction_count"] or 0)
                mention_count = int(p["mention_count"] or 0)
                confidence = float(p["confidence"] or 0.0)
                fact_count = int(p["fact_count"] or 0)
                priority = (
                    (interaction_count * 1.2)
                    + (mention_count * 1.0)
                    + (fact_count * 1.4)
                    + (confidence * 4.0)
                )
                if person_key == "operator":
                    priority *= 0.85
                person_priority[person_key] = priority
                binding_meta = binding_map.get(person_key, {})
                session_binding_count = int(binding_meta.get("session_binding_count", 0))
                last_binding_at = binding_meta.get("last_binding_at")
                last_seen_ts = _safe_ts(p["last_seen"])
                person_last_seen_ts[person_key] = last_seen_ts
                weight = min(34.0, 12.0 + interaction_count * 0.35 + mention_count * 0.7 + fact_count * 0.55)

                nodes.append(
                    {
                        "id": p_id,
                        "type": "person",
                        "sub_type": "rolodex_profile",
                        "person_key": person_key,
                        "display_name": display_name,
                        "content": display_name,
                        "timestamp": last_seen_ts,
                        "first_seen": _safe_ts(p["first_seen"]),
                        "confidence": confidence,
                        "interaction_count": interaction_count,
                        "mention_count": mention_count,
                        "fact_count": fact_count,
                        "session_binding_count": session_binding_count,
                        "last_binding_at": last_binding_at,
                        "is_locked": bool(p["is_locked"]),
                        "locked_at": _safe_ts(p["locked_at"]),
                        "contact_handle": str(p["contact_handle"] or ""),
                        "notes": str(p["notes"] or ""),
                        "val": weight,
                        "provenance": "person_rolodex",
                    }
                )

            operator_person_id = person_node_map.get("operator")

            # Canonical person->place / person->thing associations.
            for assoc in canonical_person_place_rows:
                person_key = str(assoc["person_key"] or "")
                place_key = str(assoc["place_key"] or "")
                person_id = person_node_map.get(person_key)
                place_id = place_node_map.get(place_key)
                if person_id and place_id:
                    links.append(
                        {
                            "source": person_id,
                            "target": place_id,
                            "type": "person_place",
                            "strength": max(0.16, float(assoc["confidence"] or 0.0)),
                            "label": "canonical_located_in",
                            "curvature": -0.06,
                        }
                    )

            for assoc in canonical_person_thing_rows:
                person_key = str(assoc["person_key"] or "")
                thing_key = str(assoc["thing_key"] or "")
                person_id = person_node_map.get(person_key)
                thing_id = thing_node_map.get(thing_key)
                if person_id and thing_id:
                    links.append(
                        {
                            "source": person_id,
                            "target": thing_id,
                            "type": "person_thing",
                            "strength": max(0.14, float(assoc["confidence"] or 0.0)),
                            "label": "canonical_attribute",
                            "curvature": 0.10,
                        }
                    )

            # Person-level semantic association to memory nodes (even when no explicit facts exist yet).
            for person_key, person_id in person_node_map.items():
                person_disp_norm = person_display_norm.get(person_key, "")
                person_key_norm = person_key_phrase_norm.get(person_key, "")
                person_tokens = person_tokens_map.get(person_key, set())
                scored_matches: list[tuple[float, list[str], str]] = []
                for m in mem_lookup:
                    m_norm = str(m.get("content_norm") or "")
                    m_tokens = m.get("content_tokens") or set()
                    score, reasons = _rolodex_memory_match_score(
                        memory_text_norm=m_norm,
                        memory_tokens=m_tokens,
                        person_display_norm=person_disp_norm,
                        person_key_phrase_norm=person_key_norm,
                        person_tokens=person_tokens,
                        fact_value_norm="",
                        evidence_text_norm="",
                    )
                    if score >= 0.36:
                        scored_matches.append((score, reasons, str(m["id"])))

                scored_matches.sort(key=lambda x: x[0], reverse=True)
                for score, reasons, mem_id in scored_matches[:2]:
                    links.append(
                        {
                            "source": mem_id,
                            "target": person_id,
                            "type": "memory_person_reference",
                            "strength": max(0.22, score),
                            "label": f"profile_ref: {','.join(reasons[:2])}",
                        }
                    )

            for fact in fact_rows:
                person_key = str(fact["person_key"] or "")
                if not person_key:
                    continue
                fact_count_actual_by_person[person_key] += 1
                fact_id = int(fact["id"])
                fact_type = str(fact["fact_type"] or "fact")
                fact_value = str(fact["fact_value"] or "").strip()
                fact_conf = float(fact["confidence"] or 0.0)
                obs_count = int(fact["observation_count"] or 0)
                f_id = f"person_fact_{fact_id}"
                f_weight = min(18.0, 6.0 + max(0.0, fact_conf * 8.0) + min(obs_count, 10) * 0.35)

                nodes.append(
                    {
                        "id": f_id,
                        "type": "person_fact",
                        "sub_type": fact_type,
                        "person_key": person_key,
                        "content": fact_value,
                        "fact_type": fact_type,
                        "fact_value": fact_value,
                        "confidence": fact_conf,
                        "observation_count": obs_count,
                        "source_role": str(fact["source_role"] or "unknown"),
                        "source_session_id": str(fact["source_session_id"]) if fact["source_session_id"] else None,
                        "timestamp": _safe_ts(fact["last_observed_at"]),
                        "first_observed_at": _safe_ts(fact["first_observed_at"]),
                        "evidence_text": str(fact["evidence_text"] or ""),
                        "metadata": fact["metadata"] or {},
                        "val": f_weight,
                        "provenance": "person_memory_facts",
                    }
                )

                person_id = person_node_map.get(person_key)
                if not person_id:
                    # Preserve 1:1 Rolodex->Topology coverage even if profile table is missing a parent row.
                    synthetic_person_nodes_count += 1
                    orphan_fact_rows_count += 1
                    if len(orphan_fact_rows_sample) < 80:
                        orphan_fact_rows_sample.append(
                            {
                                "person_key": person_key,
                                "fact_id": fact_id,
                                "fact_type": fact_type,
                            }
                        )
                    synthetic_display = person_key.replace("_", " ").strip().title() or person_key
                    person_id = f"person_{person_key}"
                    person_node_map[person_key] = person_id
                    person_display_norm[person_key] = _normalize_text(synthetic_display)
                    person_key_phrase_norm[person_key] = _normalize_text(person_key.replace("_", " "))
                    person_tokens_map[person_key] = _tokenize(synthetic_display) | _tokenize(person_key.replace("_", " "))
                    person_last_seen_ts[person_key] = _safe_ts(fact["last_observed_at"])
                    person_priority.setdefault(person_key, 0.01)
                    nodes.append(
                        {
                            "id": person_id,
                            "type": "person",
                            "sub_type": "rolodex_synthetic_profile",
                            "person_key": person_key,
                            "display_name": synthetic_display,
                            "content": synthetic_display,
                            "timestamp": _safe_ts(fact["last_observed_at"]),
                            "confidence": 0.0,
                            "interaction_count": 0,
                            "mention_count": 0,
                            "fact_count": 0,
                            "session_binding_count": 0,
                            "last_binding_at": None,
                            "is_locked": False,
                            "locked_at": None,
                            "is_synthetic": True,
                            "val": 10.5,
                            "provenance": "person_memory_facts_orphan",
                        }
                    )
                place_id: str | None = None
                thing_id: str | None = None
                if person_id:
                    links.append(
                        {
                            "source": person_id,
                            "target": f_id,
                            "type": "person_fact",
                            "strength": max(0.1, fact_conf),
                            "label": fact_type,
                            "curvature": 0.08,
                        }
                    )

                if (
                    fact_type == "relationship_to_speaker"
                    and operator_person_id
                    and person_id
                    and person_id != operator_person_id
                ):
                    links.append(
                        {
                            "source": person_id,
                            "target": operator_person_id,
                            "type": "person_relation",
                            "strength": max(0.2, fact_conf),
                            "label": f"relation: {fact_value}",
                            "curvature": -0.12,
                        }
                    )

                # Promote Rolodex facts into higher-order place/thing nodes.
                fact_type_low = fact_type.strip().lower()
                if fact_value:
                    if fact_type_low in {"location", "city", "region", "country", "residence"}:
                        place_key = _normalize_text(fact_value).replace(" ", "_")[:120]
                        if place_key:
                            place_id = place_node_map.get(place_key)
                            if not place_id:
                                place_id = f"place_{place_key}"
                                place_node_map[place_key] = place_id
                                place_node_meta[place_id] = {
                                    "id": place_id,
                                    "type": "place",
                                    "sub_type": "rolodex_place",
                                    "place_key": place_key,
                                    "content": fact_value,
                                    "confidence": fact_conf,
                                    "reference_count": 1,
                                    "timestamp": _safe_ts(fact["last_observed_at"]),
                                    "val": 11.0,
                                    "provenance": "person_memory_facts",
                                }
                                nodes.append(place_node_meta[place_id])
                            else:
                                place_node = place_node_meta[place_id]
                                place_node["reference_count"] = int(place_node.get("reference_count", 0)) + 1
                                place_node["confidence"] = max(float(place_node.get("confidence", 0.0)), fact_conf)
                                place_node["val"] = min(24.0, float(place_node.get("val", 11.0)) + 0.5)

                            if person_id:
                                links.append(
                                    {
                                        "source": person_id,
                                        "target": place_id,
                                        "type": "person_place",
                                        "strength": max(0.15, fact_conf),
                                        "label": "located_in",
                                        "curvature": -0.08,
                                    }
                                )
                    elif fact_type_low not in {"relationship_to_speaker", "self_identification"}:
                        thing_key = _normalize_text(fact_value).replace(" ", "_")[:120]
                        if thing_key:
                            thing_id = thing_node_map.get(thing_key)
                            if not thing_id:
                                thing_id = f"thing_{thing_key}"
                                thing_node_map[thing_key] = thing_id
                                thing_node_meta[thing_id] = {
                                    "id": thing_id,
                                    "type": "thing",
                                    "sub_type": fact_type_low or "attribute",
                                    "thing_key": thing_key,
                                    "content": fact_value,
                                    "confidence": fact_conf,
                                    "reference_count": 1,
                                    "timestamp": _safe_ts(fact["last_observed_at"]),
                                    "val": 10.5,
                                    "provenance": "person_memory_facts",
                                }
                                nodes.append(thing_node_meta[thing_id])
                            else:
                                thing_node = thing_node_meta[thing_id]
                                thing_node["reference_count"] = int(thing_node.get("reference_count", 0)) + 1
                                thing_node["confidence"] = max(float(thing_node.get("confidence", 0.0)), fact_conf)
                                thing_node["val"] = min(23.0, float(thing_node.get("val", 10.5)) + 0.45)

                            if person_id:
                                links.append(
                                    {
                                        "source": person_id,
                                        "target": thing_id,
                                        "type": "person_thing",
                                        "strength": max(0.12, fact_conf),
                                        "label": fact_type_low or "attribute",
                                        "curvature": 0.12,
                                    }
                                )

                # Cross-link rolodex signals to memory nodes for consistency inspection.
                person_disp_norm = person_display_norm.get(person_key, "")
                person_key_norm = person_key_phrase_norm.get(person_key, "")
                person_tokens = person_tokens_map.get(person_key, set())
                fact_value_norm = _normalize_text(fact_value)
                evidence_text_norm = _normalize_text(fact["evidence_text"] or "")

                scored_matches: list[tuple[float, list[str], str]] = []
                for m in mem_lookup:
                    m_norm = str(m.get("content_norm") or "")
                    m_tokens = m.get("content_tokens") or set()
                    score, reasons = _rolodex_memory_match_score(
                        memory_text_norm=m_norm,
                        memory_tokens=m_tokens,
                        person_display_norm=person_disp_norm,
                        person_key_phrase_norm=person_key_norm,
                        person_tokens=person_tokens,
                        fact_value_norm=fact_value_norm,
                        evidence_text_norm=evidence_text_norm,
                    )
                    if score >= 0.45:
                        scored_matches.append((score, reasons, str(m["id"])))

                scored_matches.sort(key=lambda x: x[0], reverse=True)
                for score, reasons, mem_id in scored_matches[:2]:
                    if person_id and score >= 0.45:
                        links.append(
                            {
                                "source": mem_id,
                                "target": person_id,
                                "type": "memory_person_reference",
                                "strength": score,
                                "label": f"rolodex_ref: {','.join(reasons[:2])}",
                            }
                        )
                    if score >= 0.62:
                        links.append(
                            {
                                "source": mem_id,
                                "target": f_id,
                                "type": "memory_fact_evidence",
                                "strength": score,
                                "label": f"evidence_ref: {','.join(reasons[:2])}",
                                "curvature": 0.06,
                            }
                        )
                    if place_id and score >= 0.55:
                        links.append(
                            {
                                "source": mem_id,
                                "target": place_id,
                                "type": "memory_place_reference",
                                "strength": score,
                                "label": f"place_ref: {','.join(reasons[:2])}",
                            }
                        )
                    if thing_id and score >= 0.55:
                        links.append(
                            {
                                "source": mem_id,
                                "target": thing_id,
                                "type": "memory_thing_reference",
                                "strength": score,
                                "label": f"thing_ref: {','.join(reasons[:2])}",
                            }
                        )

            # Guarantee every person profile is associated to the graph via at least one edge.
            linked_person_ids: set[str] = set()
            for link in links:
                src = str(link.get("source") or "")
                tgt = str(link.get("target") or "")
                if src.startswith("person_"):
                    linked_person_ids.add(src)
                if tgt.startswith("person_"):
                    linked_person_ids.add(tgt)

            for person_key, person_id in person_node_map.items():
                if person_id in linked_person_ids:
                    continue
                if mem_lookup:
                    person_ts = person_last_seen_ts.get(person_key)
                    if person_ts is not None:
                        anchor_mem = min(
                            mem_lookup,
                            key=lambda m: abs(float(m.get("timestamp") or person_ts) - float(person_ts)),
                        )
                    else:
                        anchor_mem = mem_lookup[0]
                    links.append(
                        {
                            "source": person_id,
                            "target": str(anchor_mem["id"]),
                            "type": "person_activity_anchor",
                            "strength": 0.18,
                            "label": "activity_anchor",
                            "curvature": -0.03,
                        }
                    )
                    linked_person_ids.add(person_id)
                    continue

                if operator_person_id and person_id != operator_person_id:
                    links.append(
                        {
                            "source": person_id,
                            "target": operator_person_id,
                            "type": "person_activity_anchor",
                            "strength": 0.12,
                            "label": "rolodex_anchor",
                            "curvature": 0.05,
                        }
                    )
                    linked_person_ids.add(person_id)

            mismatches: list[dict[str, Any]] = []
            for p in person_rows:
                person_key = str(p["person_key"] or "")
                if not person_key:
                    continue
                expected = int(p["fact_count"] or 0)
                actual = int(fact_count_actual_by_person.get(person_key, 0))
                if expected != actual:
                    mismatches.append(
                        {
                            "person_key": person_key,
                            "expected_fact_count": expected,
                            "actual_fact_count": actual,
                        }
                    )
            rolodex_alignment["profile_fact_mismatches"] = mismatches
            rolodex_alignment["synthetic_profile_nodes"] = synthetic_person_nodes_count
            rolodex_alignment["orphan_fact_rows_count"] = orphan_fact_rows_count
            rolodex_alignment["orphan_fact_rows_sample"] = orphan_fact_rows_sample
            entity_expansion["place_nodes"] = len(place_node_map)
            entity_expansion["thing_nodes"] = len(thing_node_map)

            # 8. Emergent ideas from shared conceptual manifold.
            manifold_rows = await conn.fetch(
                """
                SELECT
                    concept_key,
                    concept_text,
                    source,
                    status,
                    confidence,
                    rpd_score,
                    topology_warp_delta,
                    updated_at
                FROM shared_conceptual_manifold
                WHERE ghost_id = $1
                ORDER BY updated_at DESC
                LIMIT 300
                """,
                ghost_id,
            )
            idea_count = 0
            idea_node_keys: set[str] = set()
            for row in manifold_rows:
                concept_key = str(row["concept_key"] or "").strip()
                if not concept_key:
                    continue
                concept_text = str(row["concept_text"] or "").strip() or concept_key.replace("_", " ")
                idea_id = f"idea_{concept_key}"
                idea_node_keys.add(concept_key)
                idea_conf = float(row["confidence"] or 0.0)
                idea_score = float(row["rpd_score"] or 0.0)
                idea_warp = float(row["topology_warp_delta"] or 0.0)
                idea_tokens = _tokenize(concept_text) | _tokenize(concept_key.replace("_", " "))
                idea_norm = _normalize_text(concept_text)
                key_phrase_norm = _normalize_text(concept_key.replace("_", " "))
                idea_count += 1

                nodes.append(
                    {
                        "id": idea_id,
                        "type": "emergent_idea",
                        "sub_type": str(row["status"] or "proposed"),
                        "concept_key": concept_key,
                        "content": concept_text,
                        "source": str(row["source"] or "reflection"),
                        "confidence": idea_conf,
                        "rpd_score": idea_score,
                        "topology_warp_delta": idea_warp,
                        "timestamp": _safe_ts(row["updated_at"]),
                        "val": min(26.0, 11.0 + (idea_conf * 6.0) + (idea_score * 5.0) + (idea_warp * 5.0)),
                        "provenance": "shared_conceptual_manifold",
                    }
                )

                for m in mem_lookup:
                    m_norm = str(m.get("content_norm") or "")
                    m_tokens = m.get("content_tokens") or set()
                    score = 0.0
                    reasons: list[str] = []
                    if key_phrase_norm and key_phrase_norm in m_norm:
                        score += 0.34
                        reasons.append("key_phrase")
                    if idea_norm and len(idea_norm) >= 22 and idea_norm[:96] in m_norm:
                        score += 0.44
                        reasons.append("idea_snippet")
                    overlap = len(idea_tokens.intersection(m_tokens))
                    if overlap >= 4:
                        score += 0.28
                        reasons.append("token_overlap")
                    elif overlap >= 2:
                        score += 0.16
                        reasons.append("token_pair")
                    if score >= 0.46:
                        links.append(
                            {
                                "source": m["id"],
                                "target": idea_id,
                                "type": "memory_idea_resonance",
                                "strength": min(1.0, score),
                                "label": f"idea_ref: {','.join(reasons[:2])}",
                                "curvature": 0.04,
                            }
                        )

                for identity_key, identity_id in identity_map.items():
                    id_key_norm = _normalize_text(identity_key.replace("_", " "))
                    id_tokens = _tokenize(identity_key.replace("_", " "))
                    score = 0.0
                    if identity_key == concept_key:
                        score += 0.65
                    if id_key_norm and id_key_norm in idea_norm:
                        score += 0.24
                    overlap = len(id_tokens.intersection(idea_tokens))
                    if overlap >= 2:
                        score += 0.23
                    elif overlap == 1:
                        score += 0.12
                    if score >= 0.42:
                        links.append(
                            {
                                "source": idea_id,
                                "target": identity_id,
                                "type": "idea_identity_alignment",
                                "strength": min(1.0, score),
                                "label": "manifold_alignment",
                                "curvature": -0.05,
                            }
                        )
            entity_expansion["emergent_idea_nodes"] = idea_count

            # Canonical idea associations are applied directly; create synthetic idea
            # nodes when association rows reference concept keys absent in manifold rows.
            for assoc in canonical_idea_assoc_rows:
                concept_key = str(assoc["concept_key"] or "").strip()
                target_type = str(assoc["target_type"] or "").strip().lower()
                target_key = str(assoc["target_key"] or "").strip()
                if not concept_key or not target_type or not target_key:
                    continue
                if concept_key not in idea_node_keys:
                    idea_node_keys.add(concept_key)
                    idea_count += 1
                    nodes.append(
                        {
                            "id": f"idea_{concept_key}",
                            "type": "emergent_idea",
                            "sub_type": "canonical_association_only",
                            "concept_key": concept_key,
                            "content": concept_key.replace("_", " "),
                            "source": "canonical_association",
                            "confidence": float(assoc["confidence"] or 0.0),
                            "rpd_score": 0.0,
                            "topology_warp_delta": 0.0,
                            "timestamp": _safe_ts(assoc["updated_at"]),
                            "val": 10.5,
                            "provenance": "idea_entity_associations",
                        }
                    )
                idea_id = f"idea_{concept_key}"
                edge_type = ""
                target_id = ""
                if target_type == "place":
                    target_id = place_node_map.get(target_key, "")
                    edge_type = "idea_place_connector"
                elif target_type == "thing":
                    target_id = thing_node_map.get(target_key, "")
                    edge_type = "idea_thing_connector"
                elif target_type == "person":
                    target_id = person_node_map.get(target_key, "")
                    edge_type = "idea_person_connector"
                if target_id and edge_type:
                    links.append(
                        {
                            "source": idea_id,
                            "target": target_id,
                            "type": edge_type,
                            "strength": max(0.16, float(assoc["confidence"] or 0.0)),
                            "label": "canonical_association",
                            "curvature": 0.02 if edge_type != "idea_thing_connector" else -0.02,
                        }
                    )
            entity_expansion["emergent_idea_nodes"] = idea_count

            # 9. Connector-idea edges:
            # Build explicit idea->place / idea->thing / idea->person connectors
            # when they share supporting memory anchors.
            mem_to_ideas: defaultdict[str, dict[str, float]] = defaultdict(dict)
            mem_to_places: defaultdict[str, dict[str, float]] = defaultdict(dict)
            mem_to_things: defaultdict[str, dict[str, float]] = defaultdict(dict)
            mem_to_people: defaultdict[str, dict[str, float]] = defaultdict(dict)

            for link in links:
                ltype = str(link.get("type") or "")
                src = str(link.get("source") or "")
                tgt = str(link.get("target") or "")
                strength = float(link.get("strength") or 0.0)
                if not src or not tgt:
                    continue

                if ltype == "memory_idea_resonance" and src.startswith("mem_") and tgt.startswith("idea_"):
                    mem_to_ideas[src][tgt] = max(float(mem_to_ideas[src].get(tgt, 0.0)), strength)
                elif ltype == "memory_place_reference" and src.startswith("mem_") and tgt.startswith("place_"):
                    mem_to_places[src][tgt] = max(float(mem_to_places[src].get(tgt, 0.0)), strength)
                elif ltype == "memory_thing_reference" and src.startswith("mem_") and tgt.startswith("thing_"):
                    mem_to_things[src][tgt] = max(float(mem_to_things[src].get(tgt, 0.0)), strength)
                elif ltype == "memory_person_reference" and src.startswith("mem_") and tgt.startswith("person_"):
                    mem_to_people[src][tgt] = max(float(mem_to_people[src].get(tgt, 0.0)), strength)
                elif ltype == "person_activity_anchor":
                    if src.startswith("person_") and tgt.startswith("mem_"):
                        mem_to_people[tgt][src] = max(float(mem_to_people[tgt].get(src, 0.0)), strength)
                    elif src.startswith("mem_") and tgt.startswith("person_"):
                        mem_to_people[src][tgt] = max(float(mem_to_people[src].get(tgt, 0.0)), strength)

            idea_place_stats: dict[tuple[str, str], dict[str, Any]] = {}
            idea_thing_stats: dict[tuple[str, str], dict[str, Any]] = {}
            idea_person_stats: dict[tuple[str, str], dict[str, Any]] = {}

            for mem_id, idea_map in mem_to_ideas.items():
                if not idea_map:
                    continue
                place_map = mem_to_places.get(mem_id) or {}
                thing_map = mem_to_things.get(mem_id) or {}
                person_map = mem_to_people.get(mem_id) or {}

                for idea_id, idea_strength in idea_map.items():
                    for place_id, place_strength in place_map.items():
                        key = (idea_id, place_id)
                        stat = idea_place_stats.get(key)
                        if not stat:
                            stat = {"memory_ids": set(), "strength_sum": 0.0, "samples": 0}
                            idea_place_stats[key] = stat
                        stat["memory_ids"].add(mem_id)
                        stat["samples"] = int(stat["samples"]) + 1
                        stat["strength_sum"] = float(stat["strength_sum"]) + max(
                            0.0, min(1.0, (float(idea_strength) + float(place_strength)) * 0.5)
                        )

                    for thing_id, thing_strength in thing_map.items():
                        key = (idea_id, thing_id)
                        stat = idea_thing_stats.get(key)
                        if not stat:
                            stat = {"memory_ids": set(), "strength_sum": 0.0, "samples": 0}
                            idea_thing_stats[key] = stat
                        stat["memory_ids"].add(mem_id)
                        stat["samples"] = int(stat["samples"]) + 1
                        stat["strength_sum"] = float(stat["strength_sum"]) + max(
                            0.0, min(1.0, (float(idea_strength) + float(thing_strength)) * 0.5)
                        )

                    for person_id, person_strength in person_map.items():
                        key = (idea_id, person_id)
                        stat = idea_person_stats.get(key)
                        if not stat:
                            stat = {"memory_ids": set(), "strength_sum": 0.0, "samples": 0}
                            idea_person_stats[key] = stat
                        stat["memory_ids"].add(mem_id)
                        stat["samples"] = int(stat["samples"]) + 1
                        stat["strength_sum"] = float(stat["strength_sum"]) + max(
                            0.0, min(1.0, (float(idea_strength) + float(person_strength)) * 0.5)
                        )

            def _emit_connector_edges(
                pair_stats: dict[tuple[str, str], dict[str, Any]],
                *,
                edge_type: str,
                label_prefix: str,
                curvature: float,
                per_idea_cap: int = 6,
            ) -> None:
                grouped: defaultdict[str, list[tuple[float, str, int]]] = defaultdict(list)
                for (idea_id, target_id), stat in pair_stats.items():
                    memory_ids = stat.get("memory_ids") or set()
                    shared_count = len(memory_ids)
                    if shared_count <= 0:
                        continue
                    sample_count = max(1, int(stat.get("samples") or 0))
                    avg_strength = float(stat.get("strength_sum") or 0.0) / sample_count
                    connector_strength = min(1.0, 0.18 + (shared_count * 0.16) + (avg_strength * 0.36))
                    grouped[idea_id].append((connector_strength, target_id, shared_count))

                for idea_id, entries in grouped.items():
                    entries.sort(key=lambda x: x[0], reverse=True)
                    for connector_strength, target_id, shared_count in entries[: max(1, int(per_idea_cap))]:
                        links.append(
                            {
                                "source": idea_id,
                                "target": target_id,
                                "type": edge_type,
                                "strength": connector_strength,
                                "label": f"{label_prefix}:{shared_count}",
                                "curvature": curvature,
                            }
                        )

            _emit_connector_edges(
                idea_place_stats,
                edge_type="idea_place_connector",
                label_prefix="connector_place",
                curvature=0.03,
                per_idea_cap=6,
            )
            _emit_connector_edges(
                idea_thing_stats,
                edge_type="idea_thing_connector",
                label_prefix="connector_thing",
                curvature=-0.03,
                per_idea_cap=6,
            )
            _emit_connector_edges(
                idea_person_stats,
                edge_type="idea_person_connector",
                label_prefix="connector_person",
                curvature=0.07,
                per_idea_cap=8,
            )

            # Fallback: ensure each emergent idea has place/thing/person connector coverage.
            idea_nodes = [n for n in nodes if str(n.get("type") or "") == "emergent_idea"]
            idea_connector_types: defaultdict[str, set[str]] = defaultdict(set)
            for link in links:
                ltype = str(link.get("type") or "")
                if ltype not in {"idea_place_connector", "idea_thing_connector", "idea_person_connector"}:
                    continue
                src = str(link.get("source") or "")
                if src.startswith("idea_"):
                    idea_connector_types[src].add(ltype)

            fallback_place_id: str | None = None
            fallback_thing_id: str | None = None
            fallback_person_id: str | None = None
            if place_node_meta:
                fallback_place_id = max(
                    place_node_meta.items(),
                    key=lambda kv: int(kv[1].get("reference_count", 0)),
                )[0]
            if thing_node_meta:
                fallback_thing_id = max(
                    thing_node_meta.items(),
                    key=lambda kv: int(kv[1].get("reference_count", 0)),
                )[0]
            if person_node_map:
                prioritized_keys = sorted(
                    person_priority.keys(),
                    key=lambda k: float(person_priority.get(k, 0.0)),
                    reverse=True,
                )
                if prioritized_keys:
                    fallback_person_id = person_node_map.get(prioritized_keys[0])

            for idea_node in idea_nodes:
                idea_id = str(idea_node.get("id") or "")
                if not idea_id:
                    continue
                connected_types = idea_connector_types.get(idea_id) or set()

                if "idea_place_connector" not in connected_types and fallback_place_id:
                    links.append(
                        {
                            "source": idea_id,
                            "target": fallback_place_id,
                            "type": "idea_place_connector",
                            "strength": 0.14,
                            "label": "connector_place:fallback_context",
                            "curvature": 0.02,
                        }
                    )
                    connected_types.add("idea_place_connector")

                if "idea_thing_connector" not in connected_types and fallback_thing_id:
                    links.append(
                        {
                            "source": idea_id,
                            "target": fallback_thing_id,
                            "type": "idea_thing_connector",
                            "strength": 0.14,
                            "label": "connector_thing:fallback_context",
                            "curvature": -0.02,
                        }
                    )
                    connected_types.add("idea_thing_connector")

                if "idea_person_connector" not in connected_types and fallback_person_id:
                    links.append(
                        {
                            "source": idea_id,
                            "target": fallback_person_id,
                            "type": "idea_person_connector",
                            "strength": 0.16,
                            "label": "connector_person:fallback_context",
                            "curvature": 0.09,
                        }
                    )
                    connected_types.add("idea_person_connector")
                idea_connector_types[idea_id] = connected_types

            # 10. Recover unlinked identity nodes so they do not float as graph orphans.
            identity_node_ids = [str(node_id) for node_id in identity_nodes_by_id.keys() if node_id]
            identity_degree: defaultdict[str, int] = defaultdict(int)
            for link in links:
                src = str(link.get("source") or "")
                tgt = str(link.get("target") or "")
                if src in identity_nodes_by_id:
                    identity_degree[src] += 1
                if tgt in identity_nodes_by_id and tgt != src:
                    identity_degree[tgt] += 1

            self_model_id = identity_map.get("self_model")
            fallback_identity_id = self_model_id or (identity_node_ids[0] if identity_node_ids else "")
            for identity_id in identity_node_ids:
                if int(identity_degree.get(identity_id, 0)) > 0:
                    continue

                anchor_target = ""
                anchor_label = "activity_anchor"
                if mem_lookup:
                    id_ts = float(identity_timestamps.get(identity_id) or 0.0)
                    if id_ts > 0:
                        anchor_mem = min(
                            mem_lookup,
                            key=lambda m: abs(float(m.get("timestamp") or id_ts) - id_ts),
                        )
                    else:
                        anchor_mem = mem_lookup[0]
                    anchor_target = str(anchor_mem.get("id") or "")
                elif fallback_identity_id:
                    if fallback_identity_id != identity_id:
                        anchor_target = fallback_identity_id
                    else:
                        for candidate_id in identity_node_ids:
                            if candidate_id != identity_id:
                                anchor_target = candidate_id
                                break
                    anchor_label = "self_model_anchor"

                if anchor_target:
                    links.append(
                        {
                            "source": identity_id,
                            "target": anchor_target,
                            "type": "identity_activity_anchor",
                            "strength": 0.18,
                            "label": anchor_label,
                            "curvature": 0.05,
                            "particle_speed": 0.01,
                            "color": "#bba6ff99",
                        }
                    )
                    identity_degree[identity_id] += 1

    except Exception as e:
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        logger.error("Failed to build high-rigor topology: %s", error_detail)
        return {"nodes": [], "links": [], "error": error_detail}

    bootstrap_mode = False
    if not nodes:
        # Keep the topology visually alive even before the first persisted
        # memory/identity records are present.
        bootstrap_mode = True
        now_ts = datetime.now().timestamp()
        root_id = f"bootstrap_{ghost_id}"
        runtime_id = f"bootstrap_runtime_{ghost_id}"
        nodes = [
            {
                "id": root_id,
                "type": "identity",
                "sub_type": "bootstrap",
                "key": "self_model",
                "content": "Ghost topology bootstrap anchor (no persisted cognitive rows yet).",
                "timestamp": now_ts,
                "provenance": "topology_bootstrap",
                "val": 28,
                "color": "#7ad8ff",
            },
            {
                "id": runtime_id,
                "type": "memory",
                "sub_type": "bootstrap_runtime",
                "content": "Runtime online. Populate conversation, memory, or identity state to expand the graph.",
                "timestamp": now_ts,
                "provenance": "topology_bootstrap",
                "val": 18,
                "color": "#7dffb2",
            },
        ]
        links = [
            {
                "source": runtime_id,
                "target": root_id,
                "type": "bootstrap",
                "strength": 0.7,
                "label": "initialization_anchor",
                "curvature": 0.04,
            }
        ]

    links = _dedupe_links(links)
    link_type_counts: defaultdict[str, int] = defaultdict(int)
    for link in links:
        link_type_counts[str(link.get("type") or "unknown")] += 1

    person_nodes = [n for n in nodes if str(n.get("type") or "") == "person"]
    profile_person_nodes = [n for n in person_nodes if not bool(n.get("is_synthetic"))]
    fact_nodes = [n for n in nodes if str(n.get("type") or "") == "person_fact"]
    place_nodes = [n for n in nodes if str(n.get("type") or "") == "place"]
    thing_nodes = [n for n in nodes if str(n.get("type") or "") == "thing"]
    idea_nodes = [n for n in nodes if str(n.get("type") or "") == "emergent_idea"]
    identity_nodes = [n for n in nodes if str(n.get("type") or "") == "identity"]
    phenomenology_nodes = [n for n in nodes if str(n.get("type") or "") == "phenomenology"]

    rolodex_alignment["profile_nodes"] = len(profile_person_nodes)
    rolodex_alignment["fact_nodes"] = len(fact_nodes)
    rolodex_alignment["missing_profile_nodes"] = max(
        0, int(rolodex_alignment.get("profiles_count", 0)) - len(profile_person_nodes)
    )
    rolodex_alignment["missing_fact_nodes"] = max(
        0, int(rolodex_alignment.get("facts_count", 0)) - len(fact_nodes)
    )

    person_node_ids = {str(n.get("id") or "") for n in person_nodes if n.get("id")}
    person_association_counts: defaultdict[str, int] = defaultdict(int)
    for link in links:
        src = str(link.get("source") or "")
        tgt = str(link.get("target") or "")
        if src in person_node_ids:
            person_association_counts[src] += 1
        if tgt in person_node_ids and tgt != src:
            person_association_counts[tgt] += 1

    profile_association_gaps = [
        str(n.get("person_key") or n.get("id") or "")
        for n in person_nodes
        if int(person_association_counts.get(str(n.get("id") or ""), 0)) == 0
    ]
    rolodex_alignment["profile_association_gap_count"] = len(profile_association_gaps)
    rolodex_alignment["profile_association_gaps"] = profile_association_gaps[:120]
    rolodex_alignment["association_coverage"] = (
        round((len(person_nodes) - len(profile_association_gaps)) / len(person_nodes), 4)
        if person_nodes
        else 1.0
    )

    rolodex_alignment["person_fact_edges"] = int(link_type_counts.get("person_fact", 0))
    rolodex_alignment["person_relation_edges"] = int(link_type_counts.get("person_relation", 0))
    rolodex_alignment["memory_person_reference_edges"] = int(link_type_counts.get("memory_person_reference", 0))
    rolodex_alignment["person_activity_anchor_edges"] = int(link_type_counts.get("person_activity_anchor", 0))
    rolodex_alignment["memory_person_edges"] = int(
        rolodex_alignment["memory_person_reference_edges"] + rolodex_alignment["person_activity_anchor_edges"]
    )
    rolodex_alignment["memory_fact_edges"] = int(link_type_counts.get("memory_fact_evidence", 0))
    rolodex_alignment["connector_idea_edges"] = int(
        link_type_counts.get("idea_place_connector", 0)
        + link_type_counts.get("idea_thing_connector", 0)
        + link_type_counts.get("idea_person_connector", 0)
    )
    idea_node_ids = {str(n.get("id") or "") for n in idea_nodes if n.get("id")}
    idea_place_sources = {
        str(link.get("source") or "")
        for link in links
        if str(link.get("type") or "") == "idea_place_connector"
        and str(link.get("source") or "").startswith("idea_")
    }
    idea_thing_sources = {
        str(link.get("source") or "")
        for link in links
        if str(link.get("type") or "") == "idea_thing_connector"
        and str(link.get("source") or "").startswith("idea_")
    }
    idea_person_sources = {
        str(link.get("source") or "")
        for link in links
        if str(link.get("type") or "") == "idea_person_connector"
        and str(link.get("source") or "").startswith("idea_")
    }
    connector_idea_sources = {
        str(link.get("source") or "")
        for link in links
        if str(link.get("type") or "") in {"idea_place_connector", "idea_thing_connector", "idea_person_connector"}
        and str(link.get("source") or "").startswith("idea_")
    }
    ideas_with_connectors = len(idea_node_ids.intersection(connector_idea_sources))
    rolodex_alignment["idea_nodes"] = len(idea_nodes)
    rolodex_alignment["ideas_with_connectors"] = ideas_with_connectors
    rolodex_alignment["idea_connector_coverage"] = (
        round(ideas_with_connectors / len(idea_nodes), 4) if idea_nodes else 1.0
    )
    place_idea_hits = len(idea_node_ids.intersection(idea_place_sources))
    thing_idea_hits = len(idea_node_ids.intersection(idea_thing_sources))
    person_idea_hits = len(idea_node_ids.intersection(idea_person_sources))
    rolodex_alignment["idea_place_coverage"] = (
        round(place_idea_hits / len(idea_nodes), 4) if idea_nodes and place_nodes else 1.0
    )
    rolodex_alignment["idea_thing_coverage"] = (
        round(thing_idea_hits / len(idea_nodes), 4) if idea_nodes and thing_nodes else 1.0
    )
    rolodex_alignment["idea_person_coverage"] = (
        round(person_idea_hits / len(idea_nodes), 4) if idea_nodes and person_nodes else 1.0
    )
    identity_node_ids = {str(n.get("id") or "") for n in identity_nodes if n.get("id")}
    phenomenology_node_ids = {str(n.get("id") or "") for n in phenomenology_nodes if n.get("id")}
    identity_degree_counts: defaultdict[str, int] = defaultdict(int)
    phenomenology_degree_counts: defaultdict[str, int] = defaultdict(int)
    for link in links:
        src = str(link.get("source") or "")
        tgt = str(link.get("target") or "")
        if src in identity_node_ids:
            identity_degree_counts[src] += 1
        if tgt in identity_node_ids and tgt != src:
            identity_degree_counts[tgt] += 1
        if src in phenomenology_node_ids:
            phenomenology_degree_counts[src] += 1
        if tgt in phenomenology_node_ids and tgt != src:
            phenomenology_degree_counts[tgt] += 1

    identity_orphan_count = sum(1 for node_id in identity_node_ids if int(identity_degree_counts.get(node_id, 0)) == 0)
    phenomenology_orphan_count = sum(
        1 for node_id in phenomenology_node_ids if int(phenomenology_degree_counts.get(node_id, 0)) == 0
    )
    rolodex_alignment["identity_nodes"] = len(identity_nodes)
    rolodex_alignment["phenomenology_nodes"] = len(phenomenology_nodes)
    rolodex_alignment["identity_phenomenology_edges"] = int(
        link_type_counts.get("phenomenology_identity_alignment", 0)
    )
    rolodex_alignment["identity_orphan_count"] = identity_orphan_count
    rolodex_alignment["phenomenology_orphan_count"] = phenomenology_orphan_count
    rolodex_alignment["identity_link_coverage"] = (
        round((len(identity_nodes) - identity_orphan_count) / len(identity_nodes), 4) if identity_nodes else 1.0
    )
    rolodex_alignment["phenomenology_link_coverage"] = (
        round((len(phenomenology_nodes) - phenomenology_orphan_count) / len(phenomenology_nodes), 4)
        if phenomenology_nodes
        else 1.0
    )

    requires_place_connector = bool(idea_nodes) and bool(place_nodes)
    requires_thing_connector = bool(idea_nodes) and bool(thing_nodes)
    requires_person_connector = bool(idea_nodes) and bool(person_nodes)
    rolodex_alignment["mapping_ok"] = all(
        (
            int(rolodex_alignment.get("missing_profile_nodes", 0)) == 0,
            int(rolodex_alignment.get("missing_fact_nodes", 0)) == 0,
            int(rolodex_alignment.get("orphan_fact_rows_count", 0)) == 0,
            len(list(rolodex_alignment.get("profile_fact_mismatches") or [])) == 0,
            int(rolodex_alignment.get("profile_association_gap_count", 0)) == 0,
            float(rolodex_alignment.get("idea_connector_coverage", 1.0)) >= 1.0,
            (not requires_place_connector) or float(rolodex_alignment.get("idea_place_coverage", 1.0)) >= 1.0,
            (not requires_thing_connector) or float(rolodex_alignment.get("idea_thing_coverage", 1.0)) >= 1.0,
            (not requires_person_connector) or float(rolodex_alignment.get("idea_person_coverage", 1.0)) >= 1.0,
        )
    )
    rolodex_alignment["alignment_ok"] = bool(rolodex_alignment["mapping_ok"])
    entity_expansion["person_place_edges"] = int(link_type_counts.get("person_place", 0))
    entity_expansion["person_thing_edges"] = int(link_type_counts.get("person_thing", 0))
    entity_expansion["memory_place_edges"] = int(link_type_counts.get("memory_place_reference", 0))
    entity_expansion["memory_thing_edges"] = int(link_type_counts.get("memory_thing_reference", 0))
    entity_expansion["memory_idea_edges"] = int(link_type_counts.get("memory_idea_resonance", 0))
    entity_expansion["idea_identity_edges"] = int(link_type_counts.get("idea_identity_alignment", 0))
    entity_expansion["idea_place_edges"] = int(link_type_counts.get("idea_place_connector", 0))
    entity_expansion["idea_thing_edges"] = int(link_type_counts.get("idea_thing_connector", 0))
    entity_expansion["idea_person_edges"] = int(link_type_counts.get("idea_person_connector", 0))

    phi_val = 0.42
    try:
        async with pool.acquire() as conn:
            last_phi = await conn.fetchval(
                "SELECT metrics_json->>'phi_proxy' FROM iit_assessment_log ORDER BY created_at DESC LIMIT 1"
            )
            if last_phi:
                phi_val = float(last_phi)
    except Exception:
        pass

    # ── Merge living topology layer (Ghost's annotations, salience, custom edges) ──
    try:
        import topology_memory  # type: ignore
        # Collect all node IDs in the graph
        all_node_ids = [str(n.get("id") or "") for n in nodes if n.get("id")]
        if all_node_ids:
            node_meta = await topology_memory.get_node_meta(pool, all_node_ids)
            for node in nodes:
                nid = str(node.get("id") or "")
                meta = node_meta.get(nid)
                if meta:
                    if meta.get("ghost_note"):
                        node["ghost_note"] = meta["ghost_note"]
                    if meta.get("cluster_label"):
                        node["cluster_label"] = meta["cluster_label"]
                    sal = float(meta.get("salience") or 0.0)
                    if sal > 0.1:
                        # Boost val so salient nodes appear slightly larger
                        node["salience"] = round(sal, 2)
                        node["val"] = float(node.get("val") or 10) + sal * 1.5
        # Merge Ghost's custom edges
        custom_edges = await topology_memory.get_custom_edges(pool)
        existing_node_ids = {str(n.get("id") or "") for n in nodes}
        for edge in custom_edges:
            src = str(edge.get("source_id") or "")
            tgt = str(edge.get("target_id") or "")
            if not src or not tgt:
                continue
            # Only add edges between nodes that exist in the graph
            if src not in existing_node_ids or tgt not in existing_node_ids:
                continue
            links.append({
                "source": src,
                "target": tgt,
                "type": "ghost_assertion",
                "label": str(edge.get("label") or "associated"),
                "strength": float(edge.get("strength") or 0.7),
                "ghost_note": str(edge.get("ghost_note") or ""),
                "color": "#00ff8855",
                "curvature": 0.25,
            })
    except Exception as _topo_exc:
        logger.debug("topology_memory merge skipped: %s", _topo_exc)

    return {
        "nodes": nodes,
        "links": links,
        "metadata": {
            "timestamp": datetime.now().timestamp(),
            "ghost_id": ghost_id,
            "phi_proxy": phi_val,
            "similarity_threshold": similarity_threshold,
            "rigor_level": "diagnostic",
            "bootstrap_mode": bootstrap_mode,
            "rolodex_alignment": rolodex_alignment,
            "entity_expansion": entity_expansion,
        },
    }


async def get_topology_node_count(pool, ghost_id: str) -> int:
    """Lightweight count of distinct nodes in the cognitive topology."""
    if pool is None:
        return 0
    try:
        async with pool.acquire() as conn:
            memories = await conn.fetchval("SELECT count(*) FROM vector_memories WHERE ghost_id = $1", ghost_id)
            identities = await conn.fetchval("SELECT count(*) FROM identity_matrix WHERE ghost_id = $1", ghost_id)
            persons = await conn.fetchval("SELECT count(*) FROM person_rolodex WHERE ghost_id = $1 AND invalidated_at IS NULL", ghost_id)
            places = await conn.fetchval("SELECT count(*) FROM place_entities WHERE ghost_id = $1 AND invalidated_at IS NULL", ghost_id)
            things = await conn.fetchval("SELECT count(*) FROM thing_entities WHERE ghost_id = $1 AND invalidated_at IS NULL", ghost_id)
            return int((memories or 0) + (identities or 0) + (persons or 0) + (places or 0) + (things or 0))
    except Exception:
        return 0


async def get_phi_proxy(pool, ghost_id: str) -> float:
    """Get the latest IIT Phi proxy value."""
    if pool is None:
        return 0.0
    try:
        async with pool.acquire() as conn:
            phi = await conn.fetchval(
                "SELECT metrics_json->>'phi_proxy' FROM iit_assessment_log ORDER BY created_at DESC LIMIT 1"
            )
            return float(phi or 0.0)
    except Exception:
        return 0.0


async def get_topology_edge_count(pool, ghost_id: str) -> int:
    """Count associations between entities in the cognitive topology (graph edges)."""
    if pool is None:
        return 0
    try:
        async with pool.acquire() as conn:
            # Count various associations that serve as "edges" in the neural graph
            pp = await conn.fetchval("SELECT count(*) FROM person_person_associations WHERE ghost_id = $1 AND invalidated_at IS NULL", ghost_id)
            pla = await conn.fetchval("SELECT count(*) FROM person_place_associations WHERE ghost_id = $1 AND invalidated_at IS NULL", ghost_id)
            ti = await conn.fetchval("SELECT count(*) FROM person_thing_associations WHERE ghost_id = $1 AND invalidated_at IS NULL", ghost_id)
            ie = await conn.fetchval("SELECT count(*) FROM idea_entity_associations WHERE ghost_id = $1 AND invalidated_at IS NULL", ghost_id)
            return int((pp or 0) + (pla or 0) + (ti or 0) + (ie or 0))
    except Exception:
        return 0
