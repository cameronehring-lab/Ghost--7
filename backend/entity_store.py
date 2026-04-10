"""
entity_store.py
Canonical relational CRUD for place/thing entities and associations.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

_LEGACY_PERSON_TARGET_MAP = {
    "omega_7": "operator",
}


def normalize_key(raw: str, *, max_len: int = 120) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")
    return text[:max_len] if text else "unknown"


def normalize_concept_key(raw: str, *, max_len: int = 120) -> str:
    return normalize_key(raw, max_len=max_len)


def display_name(raw: str, fallback_key: str) -> str:
    clean = re.sub(r"\s+", " ", str(raw or "").strip())
    if clean:
        return clean[:180]
    return str(fallback_key or "unknown").replace("_", " ").title()


def normalize_relationship_type(raw: str) -> str:
    relation = re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")
    return relation[:80] if relation else "related"


def _safe_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


async def _resolve_person_target_key(
    conn,
    *,
    ghost_id: str,
    target_key: str,
) -> Optional[tuple[str, str]]:
    normalized = normalize_key(target_key, max_len=80)
    if not normalized:
        return None

    direct = await conn.fetchval(
        """
        SELECT person_key
        FROM person_rolodex
        WHERE ghost_id = $1
          AND person_key = $2
          AND invalidated_at IS NULL
        LIMIT 1
        """,
        ghost_id,
        normalized,
    )
    if direct:
        return str(direct), "active_key"

    alias = await conn.fetchval(
        """
        SELECT ea.canonical_key
        FROM entity_aliases ea
        JOIN person_rolodex pr
          ON pr.ghost_id = ea.ghost_id
         AND pr.person_key = ea.canonical_key
         AND pr.invalidated_at IS NULL
        WHERE ea.ghost_id = $1
          AND ea.entity_type = 'person'
          AND ea.alias_key = $2
          AND ea.invalidated_at IS NULL
        LIMIT 1
        """,
        ghost_id,
        normalized,
    )
    if alias:
        return str(alias), "alias"

    legacy = _LEGACY_PERSON_TARGET_MAP.get(normalized)
    if legacy:
        legacy_hit = await conn.fetchval(
            """
            SELECT person_key
            FROM person_rolodex
            WHERE ghost_id = $1
              AND person_key = $2
              AND invalidated_at IS NULL
            LIMIT 1
            """,
            ghost_id,
            normalize_key(legacy, max_len=80),
        )
        if legacy_hit:
            return str(legacy_hit), "legacy_operator_remap"

    return None


async def upsert_place(
    pool,
    *,
    ghost_id: str,
    place_key: str,
    display: str,
    confidence: float = 0.6,
    status: str = "active",
    provenance: str = "operator",
    notes: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    if pool is None:
        return None
    key = normalize_key(place_key)
    status_norm = str(status or "active").strip().lower()
    if status_norm not in {"active", "deprecated"}:
        status_norm = "active"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO place_entities (
                ghost_id, place_key, display_name, confidence, status, provenance, notes, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            ON CONFLICT (ghost_id, place_key) DO UPDATE
            SET
                display_name = EXCLUDED.display_name,
                confidence = GREATEST(place_entities.confidence, EXCLUDED.confidence),
                status = EXCLUDED.status,
                provenance = EXCLUDED.provenance,
                notes = EXCLUDED.notes,
                metadata = COALESCE(place_entities.metadata, '{}'::jsonb) || EXCLUDED.metadata,
                invalidated_at = CASE WHEN EXCLUDED.status = 'active' THEN NULL ELSE place_entities.invalidated_at END,
                updated_at = now()
            RETURNING place_key, display_name, confidence, status, provenance, notes, metadata, created_at, updated_at, invalidated_at
            """,
            ghost_id,
            key,
            display_name(display, key),
            float(max(0.0, min(1.0, confidence))),
            status_norm,
            str(provenance or "operator")[:64],
            str(notes or "")[:1000],
            json.dumps(metadata or {}),
        )
    if not row:
        return None
    return {
        "place_key": row["place_key"],
        "display_name": row["display_name"],
        "confidence": float(row["confidence"] or 0.0),
        "status": row["status"],
        "provenance": row["provenance"],
        "notes": row["notes"] or "",
        "metadata": _safe_json(row["metadata"]),
        "created_at": row["created_at"].timestamp() if row["created_at"] else None,
        "updated_at": row["updated_at"].timestamp() if row["updated_at"] else None,
        "invalidated_at": row["invalidated_at"].timestamp() if row["invalidated_at"] else None,
    }


async def upsert_thing(
    pool,
    *,
    ghost_id: str,
    thing_key: str,
    display: str,
    confidence: float = 0.6,
    status: str = "active",
    provenance: str = "operator",
    notes: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    if pool is None:
        return None
    key = normalize_key(thing_key)
    status_norm = str(status or "active").strip().lower()
    if status_norm not in {"active", "deprecated"}:
        status_norm = "active"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO thing_entities (
                ghost_id, thing_key, display_name, confidence, status, provenance, notes, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            ON CONFLICT (ghost_id, thing_key) DO UPDATE
            SET
                display_name = EXCLUDED.display_name,
                confidence = GREATEST(thing_entities.confidence, EXCLUDED.confidence),
                status = EXCLUDED.status,
                provenance = EXCLUDED.provenance,
                notes = EXCLUDED.notes,
                metadata = COALESCE(thing_entities.metadata, '{}'::jsonb) || EXCLUDED.metadata,
                invalidated_at = CASE WHEN EXCLUDED.status = 'active' THEN NULL ELSE thing_entities.invalidated_at END,
                updated_at = now()
            RETURNING thing_key, display_name, confidence, status, provenance, notes, metadata, created_at, updated_at, invalidated_at
            """,
            ghost_id,
            key,
            display_name(display, key),
            float(max(0.0, min(1.0, confidence))),
            status_norm,
            str(provenance or "operator")[:64],
            str(notes or "")[:1000],
            json.dumps(metadata or {}),
        )
    if not row:
        return None
    return {
        "thing_key": row["thing_key"],
        "display_name": row["display_name"],
        "confidence": float(row["confidence"] or 0.0),
        "status": row["status"],
        "provenance": row["provenance"],
        "notes": row["notes"] or "",
        "metadata": _safe_json(row["metadata"]),
        "created_at": row["created_at"].timestamp() if row["created_at"] else None,
        "updated_at": row["updated_at"].timestamp() if row["updated_at"] else None,
        "invalidated_at": row["invalidated_at"].timestamp() if row["invalidated_at"] else None,
    }


async def list_places(pool, *, ghost_id: str, limit: int = 200) -> list[dict[str, Any]]:
    if pool is None:
        return []
    cap = max(1, min(int(limit), 800))
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT place_key, display_name, confidence, status, provenance, notes, metadata,
                   created_at, updated_at, invalidated_at
            FROM place_entities
            WHERE ghost_id = $1
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            ghost_id,
            cap,
        )
    return [
        {
            "place_key": r["place_key"],
            "display_name": r["display_name"],
            "confidence": float(r["confidence"] or 0.0),
            "status": r["status"],
            "provenance": r["provenance"],
            "notes": r["notes"] or "",
            "metadata": _safe_json(r["metadata"]),
            "created_at": r["created_at"].timestamp() if r["created_at"] else None,
            "updated_at": r["updated_at"].timestamp() if r["updated_at"] else None,
            "invalidated_at": r["invalidated_at"].timestamp() if r["invalidated_at"] else None,
        }
        for r in rows
    ]


async def get_place(pool, *, ghost_id: str, place_key: str) -> Optional[dict[str, Any]]:
    if pool is None:
        return None
    key = normalize_key(place_key)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT place_key, display_name, confidence, status, provenance, notes, metadata,
                   created_at, updated_at, invalidated_at
            FROM place_entities
            WHERE ghost_id = $1
              AND place_key = $2
            LIMIT 1
            """,
            ghost_id,
            key,
        )
    if not row:
        return None
    return {
        "place_key": row["place_key"],
        "display_name": row["display_name"],
        "confidence": float(row["confidence"] or 0.0),
        "status": row["status"],
        "provenance": row["provenance"],
        "notes": row["notes"] or "",
        "metadata": _safe_json(row["metadata"]),
        "created_at": row["created_at"].timestamp() if row["created_at"] else None,
        "updated_at": row["updated_at"].timestamp() if row["updated_at"] else None,
        "invalidated_at": row["invalidated_at"].timestamp() if row["invalidated_at"] else None,
    }


async def list_things(pool, *, ghost_id: str, limit: int = 200) -> list[dict[str, Any]]:
    if pool is None:
        return []
    cap = max(1, min(int(limit), 800))
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT thing_key, display_name, confidence, status, provenance, notes, metadata,
                   created_at, updated_at, invalidated_at
            FROM thing_entities
            WHERE ghost_id = $1
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            ghost_id,
            cap,
        )
    return [
        {
            "thing_key": r["thing_key"],
            "display_name": r["display_name"],
            "confidence": float(r["confidence"] or 0.0),
            "status": r["status"],
            "provenance": r["provenance"],
            "notes": r["notes"] or "",
            "metadata": _safe_json(r["metadata"]),
            "created_at": r["created_at"].timestamp() if r["created_at"] else None,
            "updated_at": r["updated_at"].timestamp() if r["updated_at"] else None,
            "invalidated_at": r["invalidated_at"].timestamp() if r["invalidated_at"] else None,
        }
        for r in rows
    ]


async def get_thing(pool, *, ghost_id: str, thing_key: str) -> Optional[dict[str, Any]]:
    if pool is None:
        return None
    key = normalize_key(thing_key)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT thing_key, display_name, confidence, status, provenance, notes, metadata,
                   created_at, updated_at, invalidated_at
            FROM thing_entities
            WHERE ghost_id = $1
              AND thing_key = $2
            LIMIT 1
            """,
            ghost_id,
            key,
        )
    if not row:
        return None
    return {
        "thing_key": row["thing_key"],
        "display_name": row["display_name"],
        "confidence": float(row["confidence"] or 0.0),
        "status": row["status"],
        "provenance": row["provenance"],
        "notes": row["notes"] or "",
        "metadata": _safe_json(row["metadata"]),
        "created_at": row["created_at"].timestamp() if row["created_at"] else None,
        "updated_at": row["updated_at"].timestamp() if row["updated_at"] else None,
        "invalidated_at": row["invalidated_at"].timestamp() if row["invalidated_at"] else None,
    }


async def invalidate_place(pool, *, ghost_id: str, place_key: str) -> bool:
    if pool is None:
        return False
    key = normalize_key(place_key)
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE place_entities
            SET status = 'deprecated', invalidated_at = now(), updated_at = now()
            WHERE ghost_id = $1 AND place_key = $2
            """,
            ghost_id,
            key,
        )
    return str(tag).endswith(" 1")


async def invalidate_thing(pool, *, ghost_id: str, thing_key: str) -> bool:
    if pool is None:
        return False
    key = normalize_key(thing_key)
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE thing_entities
            SET status = 'deprecated', invalidated_at = now(), updated_at = now()
            WHERE ghost_id = $1 AND thing_key = $2
            """,
            ghost_id,
            key,
        )
    return str(tag).endswith(" 1")


async def hard_delete_place(pool, *, ghost_id: str, place_key: str) -> bool:
    if pool is None:
        return False
    key = normalize_key(place_key)
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            DELETE FROM place_entities
            WHERE ghost_id = $1
              AND place_key = $2
            """,
            ghost_id,
            key,
        )
    return str(tag).endswith(" 1")


async def hard_delete_thing(pool, *, ghost_id: str, thing_key: str) -> bool:
    if pool is None:
        return False
    key = normalize_key(thing_key)
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            DELETE FROM thing_entities
            WHERE ghost_id = $1
              AND thing_key = $2
            """,
            ghost_id,
            key,
        )
    return str(tag).endswith(" 1")


async def upsert_person_place_assoc(
    pool,
    *,
    ghost_id: str,
    person_key: str,
    place_key: str,
    confidence: float = 0.6,
    source: str = "operator",
    evidence_text: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    if pool is None:
        return False
    p_key = normalize_key(person_key, max_len=80)
    pl_key = normalize_key(place_key)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO person_place_associations (
                ghost_id, person_key, place_key, confidence, source, evidence_text, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            ON CONFLICT (ghost_id, person_key, place_key) DO UPDATE
            SET confidence = GREATEST(person_place_associations.confidence, EXCLUDED.confidence),
                source = EXCLUDED.source,
                evidence_text = CASE
                    WHEN length(person_place_associations.evidence_text) >= length(EXCLUDED.evidence_text)
                    THEN person_place_associations.evidence_text
                    ELSE EXCLUDED.evidence_text
                END,
                metadata = COALESCE(person_place_associations.metadata, '{}'::jsonb) || EXCLUDED.metadata,
                invalidated_at = NULL,
                updated_at = now()
            """,
            ghost_id,
            p_key,
            pl_key,
            float(max(0.0, min(1.0, confidence))),
            str(source or "operator")[:64],
            str(evidence_text or "")[:500],
            json.dumps(metadata or {}),
        )
    return True


async def upsert_person_person_assoc(
    pool,
    *,
    ghost_id: str,
    source_person_key: str,
    target_person_key: str,
    relationship_type: str,
    confidence: float = 0.6,
    source: str = "operator",
    evidence_text: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    if pool is None:
        return False
    src_key = normalize_key(source_person_key, max_len=80)
    tgt_key = normalize_key(target_person_key, max_len=80)
    rel_key = normalize_relationship_type(relationship_type)
    if not src_key or not tgt_key or not rel_key or src_key == tgt_key:
        return False
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO person_person_associations (
                ghost_id, source_person_key, target_person_key, relationship_type,
                confidence, source, evidence_text, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            ON CONFLICT (ghost_id, source_person_key, target_person_key, relationship_type) DO UPDATE
            SET confidence = GREATEST(person_person_associations.confidence, EXCLUDED.confidence),
                source = EXCLUDED.source,
                evidence_text = CASE
                    WHEN length(person_person_associations.evidence_text) >= length(EXCLUDED.evidence_text)
                    THEN person_person_associations.evidence_text
                    ELSE EXCLUDED.evidence_text
                END,
                metadata = COALESCE(person_person_associations.metadata, '{}'::jsonb) || EXCLUDED.metadata,
                invalidated_at = NULL,
                updated_at = now()
            """,
            ghost_id,
            src_key,
            tgt_key,
            rel_key,
            float(max(0.0, min(1.0, confidence))),
            str(source or "operator")[:64],
            str(evidence_text or "")[:500],
            json.dumps(metadata or {}),
        )
    return True


async def upsert_person_thing_assoc(
    pool,
    *,
    ghost_id: str,
    person_key: str,
    thing_key: str,
    confidence: float = 0.6,
    source: str = "operator",
    evidence_text: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    if pool is None:
        return False
    p_key = normalize_key(person_key, max_len=80)
    th_key = normalize_key(thing_key)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO person_thing_associations (
                ghost_id, person_key, thing_key, confidence, source, evidence_text, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            ON CONFLICT (ghost_id, person_key, thing_key) DO UPDATE
            SET confidence = GREATEST(person_thing_associations.confidence, EXCLUDED.confidence),
                source = EXCLUDED.source,
                evidence_text = CASE
                    WHEN length(person_thing_associations.evidence_text) >= length(EXCLUDED.evidence_text)
                    THEN person_thing_associations.evidence_text
                    ELSE EXCLUDED.evidence_text
                END,
                metadata = COALESCE(person_thing_associations.metadata, '{}'::jsonb) || EXCLUDED.metadata,
                invalidated_at = NULL,
                updated_at = now()
            """,
            ghost_id,
            p_key,
            th_key,
            float(max(0.0, min(1.0, confidence))),
            str(source or "operator")[:64],
            str(evidence_text or "")[:500],
            json.dumps(metadata or {}),
        )
    return True


async def upsert_idea_entity_assoc(
    pool,
    *,
    ghost_id: str,
    concept_key: str,
    target_type: str,
    target_key: str,
    confidence: float = 0.6,
    source: str = "operator",
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    if pool is None:
        return False
    c_key = normalize_concept_key(concept_key)
    t_type = str(target_type or "").strip().lower()
    if t_type not in {"place", "thing", "person"}:
        return False
    input_target_key = normalize_key(target_key, max_len=80)
    metadata_payload = _safe_json(metadata or {})
    async with pool.acquire() as conn:
        t_key = input_target_key
        if t_type == "person":
            resolved = await _resolve_person_target_key(
                conn,
                ghost_id=ghost_id,
                target_key=input_target_key,
            )
            if not resolved:
                return False
            t_key, resolution = resolved
            if t_key != input_target_key or resolution != "active_key":
                metadata_payload["target_resolution"] = {
                    "input_target_key": input_target_key,
                    "resolved_target_key": t_key,
                    "resolution": resolution,
                }
        await conn.execute(
            """
            INSERT INTO idea_entity_associations (
                ghost_id, concept_key, target_type, target_key, confidence, source, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            ON CONFLICT (ghost_id, concept_key, target_type, target_key) DO UPDATE
            SET confidence = GREATEST(idea_entity_associations.confidence, EXCLUDED.confidence),
                source = EXCLUDED.source,
                metadata = COALESCE(idea_entity_associations.metadata, '{}'::jsonb) || EXCLUDED.metadata,
                invalidated_at = NULL,
                updated_at = now()
            """,
            ghost_id,
            c_key,
            t_type,
            t_key,
            float(max(0.0, min(1.0, confidence))),
            str(source or "operator")[:64],
            json.dumps(metadata_payload),
        )
    return True


async def remove_person_place_assoc(pool, *, ghost_id: str, person_key: str, place_key: str) -> bool:
    if pool is None:
        return False
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE person_place_associations
            SET invalidated_at = now(), updated_at = now()
            WHERE ghost_id = $1 AND person_key = $2 AND place_key = $3 AND invalidated_at IS NULL
            """,
            ghost_id,
            normalize_key(person_key, max_len=80),
            normalize_key(place_key),
        )
    return str(tag).endswith(" 1")


async def remove_person_person_assoc(
    pool,
    *,
    ghost_id: str,
    source_person_key: str,
    target_person_key: str,
    relationship_type: str,
) -> bool:
    if pool is None:
        return False
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE person_person_associations
            SET invalidated_at = now(), updated_at = now()
            WHERE ghost_id = $1
              AND source_person_key = $2
              AND target_person_key = $3
              AND relationship_type = $4
              AND invalidated_at IS NULL
            """,
            ghost_id,
            normalize_key(source_person_key, max_len=80),
            normalize_key(target_person_key, max_len=80),
            normalize_relationship_type(relationship_type),
        )
    return str(tag).endswith(" 1")


async def remove_person_thing_assoc(pool, *, ghost_id: str, person_key: str, thing_key: str) -> bool:
    if pool is None:
        return False
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE person_thing_associations
            SET invalidated_at = now(), updated_at = now()
            WHERE ghost_id = $1 AND person_key = $2 AND thing_key = $3 AND invalidated_at IS NULL
            """,
            ghost_id,
            normalize_key(person_key, max_len=80),
            normalize_key(thing_key),
        )
    return str(tag).endswith(" 1")


async def remove_idea_entity_assoc(
    pool,
    *,
    ghost_id: str,
    concept_key: str,
    target_type: str,
    target_key: str,
) -> bool:
    if pool is None:
        return False
    t_type = str(target_type or "").strip().lower()
    if t_type not in {"place", "thing", "person"}:
        return False
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE idea_entity_associations
            SET invalidated_at = now(), updated_at = now()
            WHERE ghost_id = $1
              AND concept_key = $2
              AND target_type = $3
              AND target_key = $4
              AND invalidated_at IS NULL
            """,
            ghost_id,
            normalize_concept_key(concept_key),
            t_type,
            normalize_key(target_key),
        )
    return str(tag).endswith(" 1")


async def list_associations(pool, *, ghost_id: str, limit: int = 300) -> dict[str, list[dict[str, Any]]]:
    if pool is None:
        return {"person_person": [], "person_place": [], "person_thing": [], "idea_links": []}
    cap = max(1, min(int(limit), 2000))
    async with pool.acquire() as conn:
        ppl = await conn.fetch(
            """
            SELECT source_person_key, target_person_key, relationship_type, confidence, source, evidence_text, metadata, updated_at
            FROM person_person_associations
            WHERE ghost_id = $1 AND invalidated_at IS NULL
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            ghost_id,
            cap,
        )
        pp = await conn.fetch(
            """
            SELECT person_key, place_key, confidence, source, evidence_text, metadata, updated_at
            FROM person_place_associations
            WHERE ghost_id = $1 AND invalidated_at IS NULL
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            ghost_id,
            cap,
        )
        pt = await conn.fetch(
            """
            SELECT person_key, thing_key, confidence, source, evidence_text, metadata, updated_at
            FROM person_thing_associations
            WHERE ghost_id = $1 AND invalidated_at IS NULL
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            ghost_id,
            cap,
        )
        il = await conn.fetch(
            """
            SELECT concept_key, target_type, target_key, confidence, source, metadata, updated_at
            FROM idea_entity_associations
            WHERE ghost_id = $1 AND invalidated_at IS NULL
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            ghost_id,
            cap,
        )

    return {
        "person_person": [
            {
                "source_person_key": r["source_person_key"],
                "target_person_key": r["target_person_key"],
                "relationship_type": r["relationship_type"],
                "confidence": float(r["confidence"] or 0.0),
                "source": r["source"],
                "evidence_text": r["evidence_text"] or "",
                "metadata": _safe_json(r["metadata"]),
                "updated_at": r["updated_at"].timestamp() if r["updated_at"] else None,
            }
            for r in ppl
        ],
        "person_place": [
            {
                "person_key": r["person_key"],
                "place_key": r["place_key"],
                "confidence": float(r["confidence"] or 0.0),
                "source": r["source"],
                "evidence_text": r["evidence_text"] or "",
                "metadata": _safe_json(r["metadata"]),
                "updated_at": r["updated_at"].timestamp() if r["updated_at"] else None,
            }
            for r in pp
        ],
        "person_thing": [
            {
                "person_key": r["person_key"],
                "thing_key": r["thing_key"],
                "confidence": float(r["confidence"] or 0.0),
                "source": r["source"],
                "evidence_text": r["evidence_text"] or "",
                "metadata": _safe_json(r["metadata"]),
                "updated_at": r["updated_at"].timestamp() if r["updated_at"] else None,
            }
            for r in pt
        ],
        "idea_links": [
            {
                "concept_key": r["concept_key"],
                "target_type": r["target_type"],
                "target_key": r["target_key"],
                "confidence": float(r["confidence"] or 0.0),
                "source": r["source"],
                "metadata": _safe_json(r["metadata"]),
                "updated_at": r["updated_at"].timestamp() if r["updated_at"] else None,
            }
            for r in il
        ],
    }
