"""
person_rolodex.py — OMEGA 4 / Ghost
Persistent per-person memory rolodex.

This module extracts lightweight person signals from user messages and stores:
  - person profile rows (first_seen/last_seen/interaction_count)
  - reinforced person facts (preferences, location, relationship mentions)
  - optional session -> person binding for stable identity across a session
"""

from __future__ import annotations

from collections import defaultdict
import difflib
import json
import logging
import re
import time
from typing import Any, Optional
from uuid import UUID

import entity_store  # type: ignore

logger = logging.getLogger(__name__)

OPERATOR_FALLBACK_KEY = "operator"

_STOPWORD_NAME_TOKENS = {
    "a",
    "an",
    "the",
    "this",
    "that",
    "these",
    "those",
    "my",
    "your",
    "our",
    "their",
    "his",
    "her",
    "its",
    "i",
    "im",
    "i'm",
    "me",
    "you",
    "he",
    "she",
    "we",
    "they",
    "it",
    "someone",
    "anyone",
    "everyone",
    "nobody",
    "none",
    "unknown",
    "testing",
    "ready",
    "curious",
    "ghost",
    "omega",
    "operator",
    "assistant",
    "system",
    "chatgpt",
    "openai",
    "done",
    "okay",
    "ok",
    "thanks",
    "thank",
    "sure",
}

_SELF_ID_NAME_CAPTURE = (
    r"(?P<name>[A-Za-z][A-Za-z'\-]*(?: [A-Za-z][A-Za-z'\-]*){0,2}?)"
    r"(?=(?:\s+(?:and|but)\b)|[.!?\n,;:]|$)"
)
_SELF_ID_PATTERNS = [
    re.compile(rf"\bmy name is {_SELF_ID_NAME_CAPTURE}", re.IGNORECASE),
    re.compile(rf"\bcall me {_SELF_ID_NAME_CAPTURE}", re.IGNORECASE),
    re.compile(rf"\bthis is {_SELF_ID_NAME_CAPTURE}", re.IGNORECASE),
    re.compile(
        r"(?i:\bi am )(?P<name>[A-Z][A-Za-z'\-]*(?: [A-Z][A-Za-z'\-]*){0,2})"
        r"(?=(?:\s+(?:and|but)\b)|[.!?\n,;:]|$)"
    ),
    re.compile(
        r"(?i:\bi[’']m )(?P<name>[A-Z][A-Za-z'\-]*(?: [A-Z][A-Za-z'\-]*){0,2})"
        r"(?=(?:\s+(?:and|but)\b)|[.!?\n,;:]|$)"
    ),
]

_RELATION_PATTERNS = [
    re.compile(
        r"(?i:\bmy (?P<relation>dad|father|mom|mother|wife|husband|son|daughter|brother|sister|friend|partner|boss|coworker|colleague|girlfriend|boyfriend|fiance|fiancee|uncle|aunt|nephew|niece|cousin|grandpa|grandma|grandfather|grandmother|roommate|mentor|student)) (?P<name>[A-Z][A-Za-z'\-]*(?: [A-Z][A-Za-z'\-]*){0,2})",
    ),
]

_SELF_FACT_PATTERNS = [
    ("preference", re.compile(r"\bi (?:really )?(?:like|love|prefer)\s+(?P<value>[^.!?\n]{2,80})", re.IGNORECASE), 0.62),
    (
        "location",
        re.compile(
            r"\bi(?:'m| am) from\s+(?P<value>[^.!?\n]{2,60}?)(?=(?:\s+(?:and|but)\s+i\b)|[.!?\n]|$)",
            re.IGNORECASE,
        ),
        0.70,
    ),
    (
        "location",
        re.compile(
            r"\bi live in\s+(?P<value>[^.!?\n]{2,60}?)(?=(?:\s+(?:and|but)\s+i\b)|[.!?\n]|$)",
            re.IGNORECASE,
        ),
        0.70,
    ),
    ("occupation", re.compile(r"\bi work as\s+(?P<value>[^.!?\n]{2,60})", re.IGNORECASE), 0.64),
    ("occupation", re.compile(r"\bi work at\s+(?P<value>[^.!?\n]{2,60})", re.IGNORECASE), 0.62),
    ("occupation", re.compile(r"\bi am an?\s+(?P<value>[^.!?\n]{2,60})", re.IGNORECASE), 0.58),
    (
        "self_identification",
        re.compile(r"\bi go by\s+(?P<value>[A-Za-z][A-Za-z'\-\s]{1,40})", re.IGNORECASE),
        0.68,
    ),
    (
        "self_identification",
        re.compile(r"\bpeople call me\s+(?P<value>[A-Za-z][A-Za-z'\-\s]{1,40})", re.IGNORECASE),
        0.66,
    ),
    ("age", re.compile(r"\bi(?:'m| am)\s+(?P<value>\d{1,3})\s+years?\s+old\b", re.IGNORECASE), 0.64),
    ("age", re.compile(r"\bi(?:'m| am)\s+(?P<value>\d{1,3})\b", re.IGNORECASE), 0.58),
    (
        "contact_email",
        re.compile(r"\bmy email(?: address)? is\s+(?P<value>[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})", re.IGNORECASE),
        0.74,
    ),
    (
        "contact_phone",
        re.compile(r"\bmy phone(?: number)? is\s+(?P<value>\+?[0-9][0-9\-\s().]{6,20})", re.IGNORECASE),
        0.72,
    ),
]
_PLACE_FACT_TYPES = {"location", "city", "region", "country", "residence"}
_NON_THING_FACT_TYPES = _PLACE_FACT_TYPES | {"relationship_to_speaker", "self_identification"}
_OCCUPATION_REJECT_PREFIXES = {
    "absolute",
    "expert at nothing",
    "mess",
    "idiot",
    "awful",
    "not sure",
    "not good",
    "nothing",
}
_OCCUPATION_REJECT_TOKENS = {
    "mess",
    "nothing",
    "broken",
    "sad",
    "anxious",
    "confused",
    "tired",
}


def normalize_person_key(raw: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", str(raw or "").lower()).strip("_")
    return key[:80] if key else "unknown_person"


def normalize_contact_handle(raw: str) -> str:
    handle = str(raw or "").strip()
    if not handle:
        return ""
    # Email-like iMessage IDs
    if "@" in handle:
        return handle.lower()

    compact = re.sub(r"[^0-9+]", "", handle)
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    if compact.startswith("1") and len(compact) == 11:
        compact = "+" + compact
    if not compact.startswith("+") and len(compact) == 10:
        compact = "+1" + compact
    return compact or handle.lower()


def _coerce_session_uuid(session_id: Optional[str]) -> Optional[str]:
    candidate = str(session_id or "").strip()
    if not candidate:
        return None
    try:
        return str(UUID(candidate))
    except (TypeError, ValueError, AttributeError):
        return None


def _format_display_name(raw: str) -> str:
    tokens = [t for t in re.split(r"\s+", str(raw or "").strip()) if t]
    return " ".join(t[:1].upper() + t[1:].lower() for t in tokens[:3])


def _looks_like_name(candidate: str) -> bool:
    text = re.sub(r"[^\w\s'\-]", "", str(candidate or "")).strip()
    if not text:
        return False
    tokens = [t for t in text.split() if t]
    if not (1 <= len(tokens) <= 3):
        return False
    has_any_upper = any(ch.isupper() for ch in text)
    if len(tokens) > 1 and not has_any_upper:
        return False
    for token in tokens:
        low = token.lower()
        if low in _STOPWORD_NAME_TOKENS:
            return False
        if len(low) < 2:
            return False
        if not re.fullmatch(r"[A-Za-z][A-Za-z'\-]*", token):
            return False
        if len(tokens) > 1 and not token[0].isupper():
            return False
    return True


def _clean_fact_value(value: str, max_len: int = 140) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip(" .,;:!?")
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return cleaned


def _is_valid_occupation_value(value: str) -> bool:
    text = _clean_fact_value(value, max_len=80)
    if not text:
        return False
    low = text.lower()
    if len(low) < 2:
        return False
    if any(low.startswith(prefix) for prefix in _OCCUPATION_REJECT_PREFIXES):
        return False
    tokens = [t for t in re.split(r"\s+", low) if t]
    if not tokens:
        return False
    if len(tokens) <= 2 and any(t in _OCCUPATION_REJECT_TOKENS for t in tokens):
        return False
    if len(tokens) > 7:
        return False
    return True


def _normalize_json_obj(value: Any) -> dict[str, Any]:
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


def _normalize_fact_signature(person_key: str, fact_type: str, fact_value: str, source_role: str) -> tuple[str, str, str, str]:
    return (
        normalize_person_key(person_key),
        re.sub(r"\s+", " ", str(fact_type or "").strip().lower()),
        re.sub(r"\s+", " ", str(fact_value or "").strip().lower()),
        str(source_role or "").strip().lower(),
    )


def _normalize_entity_key(raw: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", str(raw or "").lower())).strip()


def _fact_bucket(fact_type: str) -> str:
    t = str(fact_type or "").strip().lower()
    if t in _PLACE_FACT_TYPES:
        return "place"
    if t in _NON_THING_FACT_TYPES:
        return "none"
    return "thing"


def _init_candidate_profile(person_key: str, display_name: str, confidence: float, source: str, sample: str) -> dict[str, Any]:
    return {
        "person_key": normalize_person_key(person_key),
        "display_name": _format_display_name(display_name) if display_name else "Unknown",
        "interaction_count": 0,
        "mention_count": 0,
        "confidence": float(max(0.0, min(1.0, confidence))),
        "sources": [source] if source else [],
        "sample_evidence": sample[:220] if sample else "",
    }


def _touch_candidate_profile(
    profiles: dict[str, dict[str, Any]],
    *,
    person_key: str,
    display_name: str,
    confidence: float,
    source: str,
    sample: str,
    interaction_inc: int = 0,
    mention_inc: int = 0,
) -> dict[str, Any]:
    key = normalize_person_key(person_key)
    profile = profiles.get(key)
    if not profile:
        profile = _init_candidate_profile(key, display_name, confidence, source, sample)
        profiles[key] = profile
    profile["interaction_count"] = int(profile.get("interaction_count", 0)) + int(max(0, interaction_inc))
    profile["mention_count"] = int(profile.get("mention_count", 0)) + int(max(0, mention_inc))
    profile["confidence"] = max(float(profile.get("confidence", 0.0)), float(max(0.0, min(1.0, confidence))))
    if source and source not in profile["sources"]:
        profile["sources"].append(source)
    if sample and len(sample) > len(str(profile.get("sample_evidence") or "")):
        profile["sample_evidence"] = sample[:220]
    if display_name and profile.get("display_name", "Unknown") == "Unknown":
        profile["display_name"] = _format_display_name(display_name)
    return profile


def _upsert_candidate_fact(
    facts: dict[tuple[str, str, str, str], dict[str, Any]],
    *,
    person_key: str,
    fact_type: str,
    fact_value: str,
    confidence: float,
    source_session_id: Optional[str],
    source_role: str,
    evidence_text: str,
    source: str,
) -> None:
    sig = _normalize_fact_signature(person_key, fact_type, fact_value, source_role)
    entry = facts.get(sig)
    if not entry:
        facts[sig] = {
            "person_key": normalize_person_key(person_key),
            "fact_type": str(fact_type or "").strip(),
            "fact_value": str(fact_value or "").strip(),
            "confidence": float(max(0.0, min(1.0, confidence))),
            "source_session_id": str(source_session_id) if source_session_id else None,
            "source_role": str(source_role or "user").lower(),
            "evidence_text": str(evidence_text or "")[:500],
            "observation_count": 1,
            "sources": [source] if source else [],
        }
        return

    entry["confidence"] = max(float(entry.get("confidence", 0.0)), float(max(0.0, min(1.0, confidence))))
    entry["observation_count"] = int(entry.get("observation_count", 0)) + 1
    if evidence_text and len(evidence_text) > len(str(entry.get("evidence_text") or "")):
        entry["evidence_text"] = str(evidence_text)[:500]
    if not entry.get("source_session_id") and source_session_id:
        entry["source_session_id"] = str(source_session_id)
    if source and source not in entry["sources"]:
        entry["sources"].append(source)


def parse_message_signals(text: str) -> dict[str, Any]:
    """
    Deterministically extract person-memory signals from a user message.
    Returns:
      {
        "speaker_name": str|None,
        "self_facts": [{"fact_type","fact_value","confidence"}],
        "mentions": [{"display_name","person_key","relation","confidence"}],
      }
    """
    content = str(text or "")
    speaker_name: Optional[str] = None

    for pattern in _SELF_ID_PATTERNS:
        match = pattern.search(content)
        if not match:
            continue
        candidate = _clean_fact_value(match.group("name"), max_len=64)
        if _looks_like_name(candidate):
            speaker_name = _format_display_name(candidate)
            break

    mentions: list[dict[str, Any]] = []
    for pattern in _RELATION_PATTERNS:
        for match in pattern.finditer(content):
            relation = str(match.group("relation") or "").lower()
            raw_name = _clean_fact_value(match.group("name"), max_len=64)
            if not _looks_like_name(raw_name):
                continue
            display_name = _format_display_name(raw_name)
            mentions.append(
                {
                    "display_name": display_name,
                    "person_key": normalize_person_key(display_name),
                    "relation": relation,
                    "confidence": 0.66,
                }
            )

    self_facts: list[dict[str, Any]] = []
    seen_facts: set[tuple[str, str]] = set()
    for fact_type, pattern, confidence in _SELF_FACT_PATTERNS:
        for match in pattern.finditer(content):
            raw_val = match.group("value")
            value = _clean_fact_value(raw_val)
            if len(value) < 2:
                continue
            if fact_type == "occupation" and not _is_valid_occupation_value(value):
                continue
            if fact_type == "self_identification":
                if not _looks_like_name(value):
                    continue
                value = _format_display_name(value)
            if fact_type == "contact_phone":
                value = normalize_contact_handle(value)
                if not value:
                    continue
            sig = (fact_type, value.lower())
            if sig in seen_facts:
                continue
            seen_facts.add(sig)
            self_facts.append(
                {
                    "fact_type": fact_type,
                    "fact_value": value,
                    "confidence": float(confidence),
                }
            )

    return {
        "speaker_name": speaker_name,
        "self_facts": self_facts,
        "mentions": mentions,
    }


async def _upsert_person_profile(
    conn,
    ghost_id: str,
    person_key: str,
    display_name: str,
    interaction_inc: int = 0,
    mention_inc: int = 0,
    confidence: float = 0.35,
    metadata: Optional[dict[str, Any]] = None,
    contact_handle: Optional[str] = None,
) -> None:
    normalized_handle = normalize_contact_handle(contact_handle or "")
    await conn.execute(
        """
        INSERT INTO person_rolodex (
            ghost_id, person_key, display_name,
            interaction_count, mention_count, confidence, metadata, contact_handle
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
        ON CONFLICT (ghost_id, person_key) DO UPDATE
        SET
            display_name = EXCLUDED.display_name,
            interaction_count = person_rolodex.interaction_count + EXCLUDED.interaction_count,
            mention_count = person_rolodex.mention_count + EXCLUDED.mention_count,
            confidence = GREATEST(person_rolodex.confidence, EXCLUDED.confidence),
            metadata = COALESCE(person_rolodex.metadata, '{}'::jsonb) || EXCLUDED.metadata,
            contact_handle = COALESCE(EXCLUDED.contact_handle, person_rolodex.contact_handle),
            invalidated_at = NULL,
            last_seen = now(),
            updated_at = now()
        WHERE person_rolodex.is_locked = FALSE
        """,
        ghost_id,
        person_key,
        display_name,
        int(interaction_inc),
        int(mention_inc),
        float(max(0.0, min(1.0, confidence))),
        json.dumps(metadata or {}),
        normalized_handle or None,
    )


async def _upsert_session_binding(
    conn,
    ghost_id: str,
    session_id: str,
    person_key: str,
    confidence: float,
) -> None:
    session_uuid = _coerce_session_uuid(session_id)
    if not session_uuid:
        return
    await conn.execute(
        """
        INSERT INTO person_session_binding (ghost_id, session_id, person_key, confidence)
        VALUES ($1, $2::uuid, $3, $4)
        ON CONFLICT (ghost_id, session_id) DO UPDATE
        SET
            person_key = EXCLUDED.person_key,
            confidence = GREATEST(person_session_binding.confidence, EXCLUDED.confidence),
            updated_at = now()
        """,
        ghost_id,
        session_uuid,
        person_key,
        float(max(0.0, min(1.0, confidence))),
    )


async def _resolve_session_person_key(conn, ghost_id: str, session_id: str) -> Optional[str]:
    session_uuid = _coerce_session_uuid(session_id)
    if not session_uuid:
        return None
    row = await conn.fetchrow(
        """
        SELECT person_key
        FROM person_session_binding
        WHERE ghost_id = $1 AND session_id = $2::uuid
        LIMIT 1
        """,
        ghost_id,
        session_uuid,
    )
    if not row:
        return None
    return str(row["person_key"])


async def _upsert_person_person_assoc(
    conn,
    *,
    ghost_id: str,
    source_person_key: str,
    target_person_key: str,
    relationship_type: str,
    confidence: float = 0.6,
    source: str = "rolodex",
    evidence_text: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    source_key = normalize_person_key(source_person_key)
    target_key = normalize_person_key(target_person_key)
    relation = entity_store.normalize_relationship_type(relationship_type)
    if not source_key or not target_key or source_key == target_key:
        return False
    await conn.execute(
        """
        INSERT INTO person_person_associations (
            ghost_id, source_person_key, target_person_key, relationship_type,
            confidence, source, evidence_text, metadata
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
        ON CONFLICT (ghost_id, source_person_key, target_person_key, relationship_type) DO UPDATE
        SET
            confidence = GREATEST(person_person_associations.confidence, EXCLUDED.confidence),
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
        source_key,
        target_key,
        relation,
        float(max(0.0, min(1.0, confidence))),
        str(source or "rolodex")[:64],
        str(evidence_text or "")[:500],
        json.dumps(metadata or {}),
    )
    return True


async def fetch_person_by_contact_handle(pool, ghost_id: str, contact_handle: str) -> Optional[dict[str, Any]]:
    if pool is None:
        return None
    normalized = normalize_contact_handle(contact_handle)
    if not normalized:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT person_key, display_name, contact_handle, is_locked
            FROM person_rolodex
            WHERE ghost_id = $1
              AND contact_handle = $2
              AND invalidated_at IS NULL
            LIMIT 1
            """,
            ghost_id,
            normalized,
        )
    if not row:
        return None
    return {
        "person_key": str(row["person_key"]),
        "display_name": str(row["display_name"] or ""),
        "contact_handle": str(row["contact_handle"] or ""),
        "is_locked": bool(row["is_locked"]),
    }


async def fetch_contact_handle_for_person(pool, ghost_id: str, person_key: str) -> Optional[str]:
    if pool is None:
        return None
    key = normalize_person_key(person_key)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT contact_handle
            FROM person_rolodex
            WHERE ghost_id = $1
              AND person_key = $2
              AND invalidated_at IS NULL
            LIMIT 1
            """,
            ghost_id,
            key,
        )
    if not row:
        return None
    value = str(row["contact_handle"] or "").strip()
    return value or None


async def count_persons(pool, ghost_id: str) -> int:
    """Count non-invalidated person entries in the rolodex."""
    if pool is None:
        return 0
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT count(*) FROM person_rolodex WHERE ghost_id = $1 AND invalidated_at IS NULL",
            ghost_id,
        )
        return int(val or 0)


async def _person_is_locked(conn, ghost_id: str, person_key: str) -> bool:
    row = await conn.fetchrow(
        """
        SELECT is_locked
        FROM person_rolodex
        WHERE ghost_id = $1 AND person_key = $2 AND invalidated_at IS NULL
        LIMIT 1
        """,
        ghost_id,
        person_key,
    )
    if not row:
        return False
    return bool(row["is_locked"])


async def _upsert_fact(
    conn,
    ghost_id: str,
    person_key: str,
    fact_type: str,
    fact_value: str,
    confidence: float,
    source_session_id: Optional[str],
    source_role: str,
    evidence_text: str,
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    if await _person_is_locked(conn, ghost_id=ghost_id, person_key=person_key):
        return False

    fact_type_norm = str(fact_type or "").strip()[:64]
    fact_value_norm = str(fact_value or "").strip()[:240]
    source_role_norm = str(source_role or "user").strip().lower()
    evidence_norm = str(evidence_text or "")[:500]
    confidence_norm = float(max(0.0, min(1.0, confidence)))
    metadata_json = json.dumps(metadata or {})
    session_uuid = _coerce_session_uuid(source_session_id)

    before = await conn.fetchrow(
        """
        SELECT id, confidence, evidence_text, observation_count
        FROM person_memory_facts
        WHERE ghost_id = $1
          AND person_key = $2
          AND fact_type = $3
          AND fact_value = $4
          AND source_role = $5
        LIMIT 1
        """,
        ghost_id,
        person_key,
        fact_type_norm,
        fact_value_norm,
        source_role_norm,
    )

    row = await conn.fetchrow(
        """
        INSERT INTO person_memory_facts (
            ghost_id, person_key, fact_type, fact_value,
            confidence, source_session_id, source_role, evidence_text, metadata
        )
        VALUES ($1, $2, $3, $4, $5, $6::uuid, $7, $8, $9::jsonb)
        ON CONFLICT (ghost_id, person_key, fact_type, fact_value, source_role) DO UPDATE
        SET
            confidence = GREATEST(person_memory_facts.confidence, EXCLUDED.confidence),
            observation_count = person_memory_facts.observation_count + 1,
            last_observed_at = now(),
            evidence_text = CASE
                WHEN length(person_memory_facts.evidence_text) >= length(EXCLUDED.evidence_text)
                    THEN person_memory_facts.evidence_text
                ELSE EXCLUDED.evidence_text
            END,
            metadata = COALESCE(person_memory_facts.metadata, '{}'::jsonb) || EXCLUDED.metadata
        RETURNING id, confidence, evidence_text, observation_count
        """,
        ghost_id,
        person_key,
        fact_type_norm,
        fact_value_norm,
        confidence_norm,
        session_uuid,
        source_role_norm,
        evidence_norm,
        metadata_json,
    )
    if not row:
        return False

    if before:
        prev_conf = float(before["confidence"] or 0.0)
        new_conf = float(row["confidence"] or 0.0)
        prev_evidence = str(before["evidence_text"] or "")
        new_evidence = str(row["evidence_text"] or "")
        prev_obs = int(before["observation_count"] or 0)
        new_obs = int(row["observation_count"] or 0)
        meaningful = abs(new_conf - prev_conf) > 0.10 or prev_evidence != new_evidence
        if meaningful:
            await conn.execute(
                """
                INSERT INTO rolodex_fact_history (
                    fact_id, ghost_id, person_key, fact_type, fact_value,
                    prev_confidence, new_confidence,
                    prev_evidence, new_evidence,
                    prev_observation_count, new_observation_count,
                    change_source
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7,
                    $8, $9,
                    $10, $11,
                    $12
                )
                """,
                int(row["id"]),
                ghost_id,
                person_key,
                fact_type_norm,
                fact_value_norm,
                prev_conf,
                new_conf,
                prev_evidence[:500],
                new_evidence[:500],
                prev_obs,
                new_obs,
                str((metadata or {}).get("source") or "unknown")[:80],
            )
    return True


async def _record_ingest_failure(
    pool,
    *,
    ghost_id: str,
    session_id: Optional[str],
    role: str,
    message_text: str,
    error_text: str,
    source: str,
) -> None:
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO rolodex_ingest_failures (
                    ghost_id,
                    session_id,
                    role,
                    source,
                    message_text,
                    error_text
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                ghost_id,
                str(session_id or "")[:120],
                str(role or "unknown")[:32].lower(),
                str(source or "unknown")[:64].lower(),
                str(message_text or "")[:4000],
                str(error_text or "")[:1000],
            )
    except Exception as exc:
        logger.error("Rolodex ingest failure queue write failed: %s", exc)


async def _promote_fact_entity(
    conn,
    *,
    ghost_id: str,
    person_key: str,
    fact_type: str,
    fact_value: str,
    confidence: float,
    evidence_text: str,
    source: str,
) -> None:
    bucket = _fact_bucket(fact_type)
    if bucket not in {"place", "thing"}:
        return

    key_norm = entity_store.normalize_key(fact_value)
    display = entity_store.display_name(fact_value, key_norm)
    confidence_norm = float(max(0.0, min(1.0, confidence)))
    person_norm = normalize_person_key(person_key)
    meta = json.dumps({"source": source, "fact_type": fact_type})

    if bucket == "place":
        await conn.execute(
            """
            INSERT INTO place_entities (
                ghost_id, place_key, display_name, confidence, status, provenance, notes, metadata
            )
            VALUES ($1, $2, $3, $4, 'active', 'chat_extraction', '', $5::jsonb)
            ON CONFLICT (ghost_id, place_key) DO UPDATE
            SET
                display_name = EXCLUDED.display_name,
                confidence = GREATEST(place_entities.confidence, EXCLUDED.confidence),
                status = 'active',
                provenance = EXCLUDED.provenance,
                metadata = COALESCE(place_entities.metadata, '{}'::jsonb) || EXCLUDED.metadata,
                invalidated_at = NULL,
                updated_at = now()
            """,
            ghost_id,
            key_norm,
            display,
            confidence_norm,
            meta,
        )
        await conn.execute(
            """
            INSERT INTO person_place_associations (
                ghost_id, person_key, place_key, confidence, source, evidence_text, metadata
            )
            VALUES ($1, $2, $3, $4, 'chat_extraction', $5, $6::jsonb)
            ON CONFLICT (ghost_id, person_key, place_key) DO UPDATE
            SET
                confidence = GREATEST(person_place_associations.confidence, EXCLUDED.confidence),
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
            person_norm,
            key_norm,
            confidence_norm,
            str(evidence_text or "")[:500],
            meta,
        )
        return

    await conn.execute(
        """
        INSERT INTO thing_entities (
            ghost_id, thing_key, display_name, confidence, status, provenance, notes, metadata
        )
        VALUES ($1, $2, $3, $4, 'active', 'chat_extraction', '', $5::jsonb)
        ON CONFLICT (ghost_id, thing_key) DO UPDATE
        SET
            display_name = EXCLUDED.display_name,
            confidence = GREATEST(thing_entities.confidence, EXCLUDED.confidence),
            status = 'active',
            provenance = EXCLUDED.provenance,
            metadata = COALESCE(thing_entities.metadata, '{}'::jsonb) || EXCLUDED.metadata,
            invalidated_at = NULL,
            updated_at = now()
        """,
        ghost_id,
        key_norm,
        display,
        confidence_norm,
        meta,
    )
    await conn.execute(
        """
        INSERT INTO person_thing_associations (
            ghost_id, person_key, thing_key, confidence, source, evidence_text, metadata
        )
        VALUES ($1, $2, $3, $4, 'chat_extraction', $5, $6::jsonb)
        ON CONFLICT (ghost_id, person_key, thing_key) DO UPDATE
        SET
            confidence = GREATEST(person_thing_associations.confidence, EXCLUDED.confidence),
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
        person_norm,
        key_norm,
        confidence_norm,
        str(evidence_text or "")[:500],
        meta,
    )


async def ingest_message(
    pool,
    message_text: str,
    session_id: Optional[str],
    role: str = "user",
    ghost_id: str = "omega-7",
    record_failure: bool = True,
) -> dict[str, Any]:
    """
    Ingest one message into the person rolodex.
    Non-user roles are ignored by design in this phase.
    """
    if pool is None:
        return {"ingested": False, "reason": "pool_unavailable"}
    if str(role).lower() != "user":
        return {"ingested": False, "reason": "role_not_supported"}

    text = str(message_text or "").strip()
    if not text:
        return {"ingested": False, "reason": "empty_text"}

    parsed = parse_message_signals(text)
    speaker_name = parsed.get("speaker_name")
    facts = parsed.get("self_facts") or []
    mentions = parsed.get("mentions") or []

    summary: dict[str, Any] = {
        "ingested": True,
        "speaker_key": None,
        "facts_upserted": 0,
        "mentions_upserted": 0,
    }

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                speaker_key: Optional[str] = None
                display_name: str = "Operator"

                if speaker_name:
                    display_name = str(speaker_name)
                    speaker_key = normalize_person_key(display_name)
                    if session_id:
                        await _upsert_session_binding(
                            conn,
                            ghost_id,
                            str(session_id),
                            speaker_key,
                            confidence=0.94,
                        )
                    saved = await _upsert_fact(
                        conn,
                        ghost_id=ghost_id,
                        person_key=speaker_key,
                        fact_type="self_identification",
                        fact_value=display_name,
                        confidence=0.94,
                        source_session_id=session_id,
                        source_role=role,
                        evidence_text=text,
                        metadata={"source": "self_intro"},
                    )
                    if saved:
                        summary["facts_upserted"] += 1
                elif session_id:
                    speaker_key = await _resolve_session_person_key(conn, ghost_id, str(session_id))

                if not speaker_key:
                    speaker_key = OPERATOR_FALLBACK_KEY
                    display_name = "Operator"
                    if session_id:
                        await _upsert_session_binding(conn, ghost_id, str(session_id), speaker_key, confidence=0.40)

                await _upsert_person_profile(
                    conn,
                    ghost_id=ghost_id,
                    person_key=speaker_key,
                    display_name=display_name,
                    interaction_inc=1,
                    mention_inc=0,
                    confidence=0.50 if speaker_key == OPERATOR_FALLBACK_KEY else 0.88,
                    metadata={"source": "chat_user_message"},
                )
                summary["speaker_key"] = speaker_key

                for fact in facts:
                    fact_type = str(fact["fact_type"])
                    fact_value = str(fact["fact_value"])
                    fact_conf = float(fact.get("confidence", 0.55))
                    saved = await _upsert_fact(
                        conn,
                        ghost_id=ghost_id,
                        person_key=speaker_key,
                        fact_type=fact_type,
                        fact_value=fact_value,
                        confidence=fact_conf,
                        source_session_id=session_id,
                        source_role=role,
                        evidence_text=text,
                        metadata={"source": "self_fact"},
                    )
                    if saved:
                        summary["facts_upserted"] += 1
                        await _promote_fact_entity(
                            conn,
                            ghost_id=ghost_id,
                            person_key=speaker_key,
                            fact_type=fact_type,
                            fact_value=fact_value,
                            confidence=fact_conf,
                            evidence_text=text,
                            source="chat_user_message",
                        )

                for mention in mentions:
                    mention_key = str(mention["person_key"])
                    mention_name = str(mention["display_name"])
                    relation = str(mention["relation"])

                    await _upsert_person_profile(
                        conn,
                        ghost_id=ghost_id,
                        person_key=mention_key,
                        display_name=mention_name,
                        interaction_inc=0,
                        mention_inc=1,
                        confidence=float(mention.get("confidence", 0.6)),
                        metadata={"source": "relationship_mention"},
                    )
                    saved = await _upsert_fact(
                        conn,
                        ghost_id=ghost_id,
                        person_key=mention_key,
                        fact_type="relationship_to_speaker",
                        fact_value=relation,
                        confidence=0.66,
                        source_session_id=session_id,
                        source_role=role,
                        evidence_text=text,
                        metadata={"source": "relationship_mention", "speaker_key": speaker_key},
                    )
                    if saved:
                        summary["facts_upserted"] += 1
                        summary["mentions_upserted"] += 1
                        await _upsert_person_person_assoc(
                            conn,
                            ghost_id=ghost_id,
                            source_person_key=speaker_key,
                            target_person_key=mention_key,
                            relationship_type=relation,
                            confidence=0.66,
                            source="relationship_mention",
                            evidence_text=text,
                            metadata={"speaker_key": speaker_key},
                        )

        return summary
    except Exception as e:
        logger.error("Person rolodex ingest failed: %s", e)
        if record_failure:
            await _record_ingest_failure(
                pool,
                ghost_id=ghost_id,
                session_id=session_id,
                role=role,
                message_text=text,
                error_text=str(e),
                source="ingest_message",
            )
        return {"ingested": False, "reason": "ingest_exception", "error": str(e)}


async def ingest_ghost_response(
    pool,
    *,
    message_text: str,
    session_id: Optional[str],
    ghost_id: str = "omega-7",
    record_failure: bool = True,
) -> dict[str, Any]:
    """
    Parse Ghost-authored response text for social facts.
    Uses lower confidence and does not mutate session bindings.
    """
    if pool is None:
        return {"ingested": False, "reason": "pool_unavailable"}

    text = str(message_text or "").strip()
    if not text:
        return {"ingested": False, "reason": "empty_text"}

    parsed = parse_message_signals(text)
    facts = parsed.get("self_facts") or []
    mentions = parsed.get("mentions") or []
    summary: dict[str, Any] = {
        "ingested": True,
        "speaker_key": OPERATOR_FALLBACK_KEY,
        "facts_upserted": 0,
        "mentions_upserted": 0,
    }

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                speaker_key = OPERATOR_FALLBACK_KEY
                if session_id:
                    resolved = await _resolve_session_person_key(conn, ghost_id, str(session_id))
                    if resolved:
                        speaker_key = resolved

                summary["speaker_key"] = speaker_key
                await _upsert_person_profile(
                    conn,
                    ghost_id=ghost_id,
                    person_key=speaker_key,
                    display_name="Operator",
                    interaction_inc=0,
                    mention_inc=0,
                    confidence=0.55,
                    metadata={"source": "ghost_response_extract"},
                )

                for fact in facts:
                    fact_type = str(fact.get("fact_type") or "").strip()
                    fact_value = str(fact.get("fact_value") or "").strip()
                    if not fact_type or not fact_value:
                        continue
                    fact_conf = min(0.60, max(0.50, float(fact.get("confidence") or 0.55)))
                    saved = await _upsert_fact(
                        conn,
                        ghost_id=ghost_id,
                        person_key=speaker_key,
                        fact_type=fact_type,
                        fact_value=fact_value,
                        confidence=fact_conf,
                        source_session_id=None,
                        source_role="ghost",
                        evidence_text=text,
                        metadata={"source": "ghost_response_extract"},
                    )
                    if not saved:
                        continue
                    summary["facts_upserted"] += 1
                    await _promote_fact_entity(
                        conn,
                        ghost_id=ghost_id,
                        person_key=speaker_key,
                        fact_type=fact_type,
                        fact_value=fact_value,
                        confidence=fact_conf,
                        evidence_text=text,
                        source="ghost_response_extract",
                    )

                for mention in mentions:
                    mention_name = str(mention.get("display_name") or "").strip()
                    mention_rel = str(mention.get("relation") or "").strip()
                    if not mention_name or not mention_rel:
                        continue
                    mention_key = normalize_person_key(str(mention.get("person_key") or mention_name))
                    mention_conf = min(0.60, max(0.50, float(mention.get("confidence") or 0.55)))
                    await _upsert_person_profile(
                        conn,
                        ghost_id=ghost_id,
                        person_key=mention_key,
                        display_name=mention_name,
                        mention_inc=1,
                        confidence=mention_conf,
                        metadata={"source": "ghost_response_extract"},
                    )
                    saved = await _upsert_fact(
                        conn,
                        ghost_id=ghost_id,
                        person_key=mention_key,
                        fact_type="relationship_to_speaker",
                        fact_value=mention_rel,
                        confidence=mention_conf,
                        source_session_id=None,
                        source_role="ghost",
                        evidence_text=text,
                        metadata={"source": "ghost_response_extract", "speaker_key": speaker_key},
                    )
                    if saved:
                        summary["mentions_upserted"] += 1
                        summary["facts_upserted"] += 1
                        await _upsert_person_person_assoc(
                            conn,
                            ghost_id=ghost_id,
                            source_person_key=speaker_key,
                            target_person_key=mention_key,
                            relationship_type=mention_rel,
                            confidence=mention_conf,
                            source="ghost_response_extract",
                            evidence_text=text,
                            metadata={"speaker_key": speaker_key},
                        )
        return summary
    except Exception as e:
        logger.error("Ghost response rolodex ingest failed: %s", e)
        if record_failure:
            await _record_ingest_failure(
                pool,
                ghost_id=ghost_id,
                session_id=session_id,
                role="ghost",
                message_text=text,
                error_text=str(e),
                source="ingest_ghost_response",
            )
        return {"ingested": False, "reason": "ingest_exception", "error": str(e)}


async def audit_retro_entities(
    pool,
    ghost_id: str = "omega-7",
    max_messages: int = 0,
    max_memory_rows: int = 1500,
) -> dict[str, Any]:
    """
    Deep-scan historical memory to find entities known by Ghost but missing from Rolodex.
    Scans:
      - user messages (authoritative for social facts)
      - vector memories (supporting cross-check)
    """
    if pool is None:
        return {"ok": False, "error": "pool_unavailable"}

    msg_cap = max(0, int(max_messages))
    mem_cap = max(0, int(max_memory_rows))

    async with pool.acquire() as conn:
        if msg_cap > 0:
            message_rows = await conn.fetch(
                """
                SELECT m.id, m.session_id::text AS session_id, m.content, m.created_at
                FROM messages m
                JOIN sessions s ON s.id = m.session_id
                WHERE s.ghost_id = $1
                  AND m.role = 'user'
                ORDER BY m.created_at ASC
                LIMIT $2
                """,
                ghost_id,
                msg_cap,
            )
        else:
            message_rows = await conn.fetch(
                """
                SELECT m.id, m.session_id::text AS session_id, m.content, m.created_at
                FROM messages m
                JOIN sessions s ON s.id = m.session_id
                WHERE s.ghost_id = $1
                  AND m.role = 'user'
                ORDER BY m.created_at ASC
                """,
                ghost_id,
            )

        existing_profile_rows = await conn.fetch(
            """
            SELECT person_key, display_name, is_locked
            FROM person_rolodex
            WHERE ghost_id = $1
              AND invalidated_at IS NULL
            """,
            ghost_id,
        )
        existing_fact_rows = await conn.fetch(
            """
            SELECT person_key, fact_type, fact_value, source_role
            FROM person_memory_facts
            WHERE ghost_id = $1
              AND invalidated_at IS NULL
            """,
            ghost_id,
        )
        binding_rows = await conn.fetch(
            """
            SELECT session_id::text AS session_id, person_key
            FROM person_session_binding
            WHERE ghost_id = $1
            """,
            ghost_id,
        )
        if mem_cap > 0:
            vector_rows = await conn.fetch(
                """
                SELECT id, content
                FROM vector_memories
                WHERE ghost_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                ghost_id,
                mem_cap,
            )
        else:
            vector_rows = []

    existing_profiles = {
        str(r["person_key"]): {
            "display_name": str(r["display_name"] or ""),
            "is_locked": bool(r["is_locked"]),
        }
        for r in existing_profile_rows
        if r["person_key"]
    }
    existing_fact_signatures = {
        _normalize_fact_signature(
            str(r["person_key"] or ""),
            str(r["fact_type"] or ""),
            str(r["fact_value"] or ""),
            str(r["source_role"] or ""),
        )
        for r in existing_fact_rows
    }
    existing_place_keys = {
        _normalize_entity_key(str(r["fact_value"] or ""))
        for r in existing_fact_rows
        if str(r["fact_type"] or "").strip().lower() in _PLACE_FACT_TYPES and str(r["fact_value"] or "").strip()
    }
    existing_thing_keys = {
        _normalize_entity_key(str(r["fact_value"] or ""))
        for r in existing_fact_rows
        if _fact_bucket(str(r["fact_type"] or "")) == "thing" and str(r["fact_value"] or "").strip()
    }

    session_key_map: dict[str, str] = {
        str(r["session_id"]): normalize_person_key(str(r["person_key"]))
        for r in binding_rows
        if r["session_id"] and r["person_key"]
    }

    candidate_profiles: dict[str, dict[str, Any]] = {}
    candidate_facts: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    candidate_place_counts: defaultdict[str, int] = defaultdict(int)
    candidate_thing_counts: defaultdict[str, int] = defaultdict(int)

    for row in message_rows:
        text = str(row["content"] or "").strip()
        if not text:
            continue
        session_id = str(row["session_id"]) if row["session_id"] else None
        parsed = parse_message_signals(text)
        speaker_name = parsed.get("speaker_name")

        if speaker_name:
            speaker_key = normalize_person_key(str(speaker_name))
            speaker_display = _format_display_name(str(speaker_name))
            if session_id:
                session_key_map[session_id] = speaker_key
            speaker_conf = 0.88
            speaker_source = "self_identification"
        elif session_id and session_id in session_key_map:
            speaker_key = session_key_map[session_id]
            speaker_display = existing_profiles.get(speaker_key, {}).get(
                "display_name",
                candidate_profiles.get(speaker_key, {}).get("display_name", "Operator"),
            )
            speaker_conf = 0.62
            speaker_source = "session_binding"
        else:
            speaker_key = OPERATOR_FALLBACK_KEY
            speaker_display = existing_profiles.get(OPERATOR_FALLBACK_KEY, {}).get("display_name", "Operator")
            speaker_conf = 0.50
            speaker_source = "operator_fallback"
            if session_id:
                session_key_map.setdefault(session_id, speaker_key)

        _touch_candidate_profile(
            candidate_profiles,
            person_key=speaker_key,
            display_name=speaker_display,
            confidence=speaker_conf,
            source=speaker_source,
            sample=text,
            interaction_inc=1,
        )

        for fact in parsed.get("self_facts") or []:
            fact_type = str(fact.get("fact_type") or "").strip()
            fact_value = _clean_fact_value(str(fact.get("fact_value") or ""))
            if not fact_type or not fact_value:
                continue
            conf = float(fact.get("confidence") or 0.55)
            _upsert_candidate_fact(
                candidate_facts,
                person_key=speaker_key,
                fact_type=fact_type,
                fact_value=fact_value,
                confidence=conf,
                source_session_id=session_id,
                source_role="user",
                evidence_text=text,
                source="self_fact",
            )
            bucket = _fact_bucket(fact_type)
            normalized_value = _normalize_entity_key(fact_value)
            if bucket == "place" and normalized_value:
                candidate_place_counts[normalized_value] += 1
            elif bucket == "thing" and normalized_value:
                candidate_thing_counts[normalized_value] += 1

        for mention in parsed.get("mentions") or []:
            mention_key = normalize_person_key(str(mention.get("person_key") or ""))
            mention_name = _format_display_name(str(mention.get("display_name") or mention_key))
            relation = _clean_fact_value(str(mention.get("relation") or ""))
            if not mention_key or not relation:
                continue

            _touch_candidate_profile(
                candidate_profiles,
                person_key=mention_key,
                display_name=mention_name,
                confidence=float(mention.get("confidence") or 0.66),
                source="relationship_mention",
                sample=text,
                mention_inc=1,
            )
            _upsert_candidate_fact(
                candidate_facts,
                person_key=mention_key,
                fact_type="relationship_to_speaker",
                fact_value=relation,
                confidence=float(mention.get("confidence") or 0.66),
                source_session_id=session_id,
                source_role="user",
                evidence_text=text,
                source="relationship_mention",
            )

    missing_profiles = [
        {
            "person_key": key,
            "display_name": profile.get("display_name") or "Unknown",
            "interaction_count": int(profile.get("interaction_count", 0)),
            "mention_count": int(profile.get("mention_count", 0)),
            "confidence": float(profile.get("confidence", 0.5)),
            "sources": list(profile.get("sources") or []),
            "sample_evidence": str(profile.get("sample_evidence") or ""),
        }
        for key, profile in candidate_profiles.items()
        if key not in existing_profiles
    ]
    missing_profiles.sort(
        key=lambda p: (
            int(p.get("interaction_count", 0)) + int(p.get("mention_count", 0)),
            float(p.get("confidence", 0.0)),
        ),
        reverse=True,
    )

    locked_in_db = {k for k, v in existing_profiles.items() if v.get("is_locked")}

    missing_facts = []
    for sig, fact in candidate_facts.items():
        if sig in existing_fact_signatures:
            continue
        if fact.get("person_key") in locked_in_db:
            continue
        missing_facts.append(
            {
                "person_key": fact["person_key"],
                "fact_type": fact["fact_type"],
                "fact_value": fact["fact_value"],
                "confidence": float(fact["confidence"]),
                "observation_count": int(fact["observation_count"]),
                "source_session_id": fact["source_session_id"],
                "source_role": fact["source_role"],
                "evidence_text": fact["evidence_text"],
                "sources": list(fact.get("sources") or []),
            }
        )
    missing_facts.sort(
        key=lambda f: (
            int(f.get("observation_count", 0)),
            float(f.get("confidence", 0.0)),
        ),
        reverse=True,
    )

    missing_place_counts: defaultdict[str, int] = defaultdict(int)
    missing_thing_counts: defaultdict[str, int] = defaultdict(int)
    for fact in missing_facts:
        bucket = _fact_bucket(str(fact.get("fact_type") or ""))
        normalized_value = _normalize_entity_key(str(fact.get("fact_value") or ""))
        if not normalized_value:
            continue
        if bucket == "place":
            missing_place_counts[normalized_value] += int(fact.get("observation_count", 1))
        elif bucket == "thing":
            missing_thing_counts[normalized_value] += int(fact.get("observation_count", 1))

    # Supporting memory-only scan from vector store for blind spots.
    memory_only_people: defaultdict[str, int] = defaultdict(int)
    memory_only_places: defaultdict[str, int] = defaultdict(int)
    memory_only_things: defaultdict[str, int] = defaultdict(int)
    candidate_people_keys = set(candidate_profiles.keys())
    candidate_place_keys = set(candidate_place_counts.keys())
    candidate_thing_keys = set(candidate_thing_counts.keys())

    for row in vector_rows:
        content = str(row["content"] or "").strip()
        if not content:
            continue
        parsed = parse_message_signals(content)
        speaker_name = parsed.get("speaker_name")
        if speaker_name:
            speaker_key = normalize_person_key(str(speaker_name))
            if speaker_key not in candidate_people_keys:
                memory_only_people[speaker_key] += 1
        for mention in parsed.get("mentions") or []:
            mention_key = normalize_person_key(str(mention.get("person_key") or ""))
            if mention_key and mention_key not in candidate_people_keys:
                memory_only_people[mention_key] += 1
        for fact in parsed.get("self_facts") or []:
            bucket = _fact_bucket(str(fact.get("fact_type") or ""))
            normalized_value = _normalize_entity_key(str(fact.get("fact_value") or ""))
            if not normalized_value:
                continue
            if bucket == "place" and normalized_value not in candidate_place_keys:
                memory_only_places[normalized_value] += 1
            elif bucket == "thing" and normalized_value not in candidate_thing_keys:
                memory_only_things[normalized_value] += 1

    projected_people = set(existing_profiles.keys()) | set(candidate_profiles.keys())
    projected_places = set(existing_place_keys) | set(candidate_place_counts.keys())
    projected_things = set(existing_thing_keys) | set(candidate_thing_counts.keys())

    return {
        "ok": True,
        "scan": {
            "message_rows_scanned": len(message_rows),
            "vector_rows_scanned": len(vector_rows),
            "max_messages": msg_cap,
            "max_memory_rows": mem_cap,
        },
        "current": {
            "profiles": len(existing_profiles),
            "facts": len(existing_fact_signatures),
            "places": len(existing_place_keys),
            "things": len(existing_thing_keys),
        },
        "candidates": {
            "profiles": len(candidate_profiles),
            "facts": len(candidate_facts),
            "places": len(candidate_place_counts),
            "things": len(candidate_thing_counts),
        },
        "missing": {
            "profiles_count": len(missing_profiles),
            "facts_count": len(missing_facts),
            "places_count": len(missing_place_counts),
            "things_count": len(missing_thing_counts),
            "profiles": missing_profiles[:80],
            "facts": missing_facts[:200],
            "places": [
                {"place_key": k, "observations": int(v)}
                for k, v in sorted(missing_place_counts.items(), key=lambda x: x[1], reverse=True)[:120]
            ],
            "things": [
                {"thing_key": k, "observations": int(v)}
                for k, v in sorted(missing_thing_counts.items(), key=lambda x: x[1], reverse=True)[:160]
            ],
        },
        "memory_only_candidates": {
            "people": [
                {"person_key": k, "observations": int(v)}
                for k, v in sorted(memory_only_people.items(), key=lambda x: x[1], reverse=True)[:80]
            ],
            "places": [
                {"place_key": k, "observations": int(v)}
                for k, v in sorted(memory_only_places.items(), key=lambda x: x[1], reverse=True)[:120]
            ],
            "things": [
                {"thing_key": k, "observations": int(v)}
                for k, v in sorted(memory_only_things.items(), key=lambda x: x[1], reverse=True)[:160]
            ],
        },
        "topology_projection": {
            "people_nodes_current": len(existing_profiles),
            "people_nodes_projected": len(projected_people),
            "place_nodes_current": len(existing_place_keys),
            "place_nodes_projected": len(projected_places),
            "thing_nodes_current": len(existing_thing_keys),
            "thing_nodes_projected": len(projected_things),
        },
    }


async def apply_retro_sync(pool, ghost_id: str = "omega-7", max_messages: int = 0) -> dict[str, Any]:
    """
    Insert only missing profile/fact entities discovered by audit_retro_entities.
    Safe for repeated runs: only currently-missing entities are inserted each invocation.
    """
    if pool is None:
        return {"ok": False, "error": "pool_unavailable"}

    audit_before = await audit_retro_entities(pool, ghost_id=ghost_id, max_messages=max_messages)
    if not audit_before.get("ok"):
        return {"ok": False, "error": "audit_failed", "audit": audit_before}

    missing_profiles = list((audit_before.get("missing") or {}).get("profiles") or [])
    missing_facts = list((audit_before.get("missing") or {}).get("facts") or [])

    profiles_inserted = 0
    facts_inserted = 0
    facts_skipped_locked = 0

    async with pool.acquire() as conn:
        async with conn.transaction():
            for profile in missing_profiles:
                await _upsert_person_profile(
                    conn,
                    ghost_id=ghost_id,
                    person_key=str(profile.get("person_key") or ""),
                    display_name=str(profile.get("display_name") or "Unknown"),
                    interaction_inc=int(profile.get("interaction_count") or 0),
                    mention_inc=int(profile.get("mention_count") or 0),
                    confidence=float(profile.get("confidence") or 0.5),
                    metadata={"source": "retro_sync", "retroactive": True, "sources": profile.get("sources") or []},
                )
                profiles_inserted += 1

            for fact in missing_facts:
                saved = await _upsert_fact(
                    conn,
                    ghost_id=ghost_id,
                    person_key=str(fact.get("person_key") or ""),
                    fact_type=str(fact.get("fact_type") or ""),
                    fact_value=str(fact.get("fact_value") or ""),
                    confidence=float(fact.get("confidence") or 0.5),
                    source_session_id=str(fact.get("source_session_id") or "") or None,
                    source_role=str(fact.get("source_role") or "user"),
                    evidence_text=str(fact.get("evidence_text") or "")[:500],
                    metadata={"source": "retro_sync", "retroactive": True, "sources": fact.get("sources") or []},
                )
                if saved:
                    facts_inserted += 1
                    await _promote_fact_entity(
                        conn,
                        ghost_id=ghost_id,
                        person_key=str(fact.get("person_key") or ""),
                        fact_type=str(fact.get("fact_type") or ""),
                        fact_value=str(fact.get("fact_value") or ""),
                        confidence=float(fact.get("confidence") or 0.5),
                        evidence_text=str(fact.get("evidence_text") or "")[:500],
                        source="retro_sync",
                    )
                else:
                    facts_skipped_locked += 1

    audit_after = await audit_retro_entities(pool, ghost_id=ghost_id, max_messages=max_messages)
    return {
        "ok": True,
        "applied": {
            "profiles_inserted": profiles_inserted,
            "facts_inserted": facts_inserted,
            "facts_skipped_locked": facts_skipped_locked,
        },
        "audit_before": audit_before,
        "audit_after": audit_after,
    }


async def fetch_rolodex(
    pool,
    ghost_id: str,
    limit: int = 50,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    if pool is None:
        return []
    cap = max(1, min(int(limit), 200))
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                p.person_key,
                p.display_name,
                p.contact_handle,
                p.first_seen,
                p.last_seen,
                p.interaction_count,
                p.mention_count,
                p.confidence,
                p.is_locked,
                p.locked_at,
                p.invalidated_at,
                p.notes,
                p.metadata,
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
              AND ($3 OR p.invalidated_at IS NULL)
            ORDER BY p.last_seen DESC, p.interaction_count DESC, p.mention_count DESC
            LIMIT $2
            """,
            ghost_id,
            cap,
            bool(include_archived),
        )

    return [
        {
            "person_key": r["person_key"],
            "display_name": r["display_name"],
            "contact_handle": r["contact_handle"] or "",
            "first_seen": r["first_seen"].timestamp() if r["first_seen"] else None,
            "last_seen": r["last_seen"].timestamp() if r["last_seen"] else None,
            "interaction_count": int(r["interaction_count"] or 0),
            "mention_count": int(r["mention_count"] or 0),
            "confidence": float(r["confidence"] or 0.0),
            "is_locked": bool(r["is_locked"]),
            "locked_at": r["locked_at"].timestamp() if r["locked_at"] else None,
            "invalidated_at": r["invalidated_at"].timestamp() if r["invalidated_at"] else None,
            "notes": r["notes"] or "",
            "metadata": _normalize_json_obj(r["metadata"]),
            "fact_count": int(r["fact_count"] or 0),
        }
        for r in rows
    ]


async def fetch_rolodex_with_associations(
    pool,
    ghost_id: str,
    limit: int = 50,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    entries = await fetch_rolodex(
        pool,
        ghost_id=ghost_id,
        limit=limit,
        include_archived=include_archived,
    )
    if pool is None or not entries:
        return entries

    associations = await entity_store.list_associations(pool, ghost_id=ghost_id, limit=max(300, int(limit) * 12))
    people_counts: defaultdict[str, int] = defaultdict(int)
    place_counts: defaultdict[str, int] = defaultdict(int)
    thing_counts: defaultdict[str, int] = defaultdict(int)
    idea_counts: defaultdict[str, int] = defaultdict(int)

    for row in list((associations or {}).get("person_person") or []):
        source_key = normalize_person_key(str(row.get("source_person_key") or ""))
        target_key = normalize_person_key(str(row.get("target_person_key") or ""))
        if source_key:
            people_counts[source_key] += 1
        if target_key:
            people_counts[target_key] += 1
    for row in list((associations or {}).get("person_place") or []):
        key = normalize_person_key(str(row.get("person_key") or ""))
        if key:
            place_counts[key] += 1
    for row in list((associations or {}).get("person_thing") or []):
        key = normalize_person_key(str(row.get("person_key") or ""))
        if key:
            thing_counts[key] += 1
    for row in list((associations or {}).get("idea_links") or []):
        if str(row.get("target_type") or "").strip().lower() != "person":
            continue
        key = normalize_person_key(str(row.get("target_key") or ""))
        if key:
            idea_counts[key] += 1

    enriched: list[dict[str, Any]] = []
    for row in entries:
        key = normalize_person_key(str(row.get("person_key") or ""))
        copy = dict(row)
        copy["association_counts"] = {
            "people": int(people_counts.get(key, 0)),
            "places": int(place_counts.get(key, 0)),
            "things": int(thing_counts.get(key, 0)),
            "ideas": int(idea_counts.get(key, 0)),
        }
        enriched.append(copy)
    return enriched


async def fetch_person_details(
    pool,
    ghost_id: str,
    person_key: str,
    fact_limit: int = 80,
    include_archived: bool = False,
) -> Optional[dict[str, Any]]:
    if pool is None:
        return None
    key = normalize_person_key(person_key)
    cap = max(1, min(int(fact_limit), 200))

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                person_key, display_name, first_seen, last_seen,
                interaction_count, mention_count, confidence, contact_handle,
                is_locked, locked_at, invalidated_at, notes, metadata
            FROM person_rolodex
            WHERE ghost_id = $1
              AND person_key = $2
              AND ($3 OR invalidated_at IS NULL)
            LIMIT 1
            """,
            ghost_id,
            key,
            bool(include_archived),
        )
        if not row:
            return None

        fact_rows = await conn.fetch(
            """
            SELECT
                fact_type, fact_value, confidence, source_session_id, source_role,
                evidence_text, first_observed_at, last_observed_at, observation_count,
                invalidated_at, metadata
            FROM person_memory_facts
            WHERE ghost_id = $1
              AND person_key = $2
              AND ($3 OR invalidated_at IS NULL)
            ORDER BY confidence DESC, observation_count DESC, last_observed_at DESC
            LIMIT $4
            """,
            ghost_id,
            key,
            bool(include_archived),
            cap,
        )

    return {
        "person_key": row["person_key"],
        "display_name": row["display_name"],
        "contact_handle": row["contact_handle"] or "",
        "first_seen": row["first_seen"].timestamp() if row["first_seen"] else None,
        "last_seen": row["last_seen"].timestamp() if row["last_seen"] else None,
        "interaction_count": int(row["interaction_count"] or 0),
        "mention_count": int(row["mention_count"] or 0),
        "confidence": float(row["confidence"] or 0.0),
        "is_locked": bool(row["is_locked"]),
        "locked_at": row["locked_at"].timestamp() if row["locked_at"] else None,
        "invalidated_at": row["invalidated_at"].timestamp() if row["invalidated_at"] else None,
        "notes": row["notes"] or "",
        "metadata": _normalize_json_obj(row["metadata"]),
        "facts": [
            {
                "fact_type": f["fact_type"],
                "fact_value": f["fact_value"],
                "confidence": float(f["confidence"] or 0.0),
                "source_role": f["source_role"],
                "evidence_text": f["evidence_text"],
                "first_observed_at": f["first_observed_at"].timestamp() if f["first_observed_at"] else None,
                "last_observed_at": f["last_observed_at"].timestamp() if f["last_observed_at"] else None,
                "observation_count": int(f["observation_count"] or 0),
                "invalidated_at": f["invalidated_at"].timestamp() if f["invalidated_at"] else None,
            }
            for f in fact_rows
        ],
    }


async def fetch_person_history(pool, ghost_id: str, person_key: str, limit: int = 50) -> dict[str, Any]:
    """Fetch session history and mention snippets for an individual."""
    if pool is None:
        return {"sessions": [], "mentions": []}
    key = normalize_person_key(person_key)
    async with pool.acquire() as conn:
        # 1. Sessions where they were the speaker
        session_rows = await conn.fetch(
            """
            SELECT s.id, s.started_at, s.ended_at, s.summary, pb.confidence
            FROM sessions s
            JOIN person_session_binding pb ON s.id = pb.session_id::text
            WHERE pb.ghost_id = $1 AND pb.person_key = $2
            ORDER BY s.started_at DESC
            LIMIT $3
            """,
            ghost_id,
            key,
            limit,
        )
        sessions = [
            {
                "session_id": str(row["id"]),
                "started_at": row["started_at"].timestamp() if row["started_at"] else None,
                "ended_at": row["ended_at"].timestamp() if row["ended_at"] else None,
                "summary": row["summary"] or "no summary",
                "binding_confidence": float(row["confidence"] or 0.0),
            }
            for row in session_rows
        ]

        # 2. Mentions in vector memory (top matches)
        # We search specifically for the display_name or key in content
        # For now, we use a simple ILIKE or we could use the fact evidence
        mention_rows = await conn.fetch(
            """
            SELECT content, created_at, memory_type
            FROM vector_memories
            WHERE ghost_id = $1
              AND (content ILIKE $2 OR content ILIKE $3)
            ORDER BY created_at DESC
            LIMIT $4
            """,
            ghost_id,
            f"%{key}%",
            f"%{person_key}%",
            limit,
        )
        mentions = [
            {
                "content": row["content"],
                "timestamp": row["created_at"].timestamp() if row["created_at"] else None,
                "type": row["memory_type"],
            }
            for row in mention_rows
        ]

    return {"sessions": sessions, "mentions": mentions}


async def ingest_bound_message(
    pool,
    *,
    message_text: str,
    person_key: str,
    session_id: Optional[str],
    ghost_id: str = "omega-7",
    source: str = "imessage",
) -> dict[str, Any]:
    """
    Ingest an externally sourced user message that is already bound to person_key.
    """
    if pool is None:
        return {"ingested": False, "reason": "pool_unavailable"}

    text = str(message_text or "").strip()
    key = normalize_person_key(person_key)
    if not text:
        return {"ingested": False, "reason": "empty_text"}
    if not key or key == "unknown_person":
        return {"ingested": False, "reason": "invalid_person_key"}

    parsed = parse_message_signals(text)
    facts = parsed.get("self_facts") or []
    mentions = parsed.get("mentions") or []
    summary: dict[str, Any] = {
        "ingested": True,
        "speaker_key": key,
        "facts_upserted": 0,
        "mentions_upserted": 0,
    }

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                speaker_row = await conn.fetchrow(
                    """
                    SELECT display_name
                    FROM person_rolodex
                    WHERE ghost_id = $1 AND person_key = $2 AND invalidated_at IS NULL
                    LIMIT 1
                    """,
                    ghost_id,
                    key,
                )
                if not speaker_row:
                    return {"ingested": False, "reason": "person_not_found", "speaker_key": key}

                display_name = str(speaker_row["display_name"] or key.replace("_", " ").title())
                await _upsert_person_profile(
                    conn,
                    ghost_id=ghost_id,
                    person_key=key,
                    display_name=display_name,
                    interaction_inc=1,
                    confidence=0.90,
                    metadata={"source": source, "bound_ingest": True},
                )

                if session_id:
                    await _upsert_session_binding(
                        conn,
                        ghost_id,
                        str(session_id),
                        key,
                        confidence=0.96,
                    )

                for fact in facts:
                    fact_type = str(fact.get("fact_type") or "").strip()[:64]
                    fact_value = str(fact.get("fact_value") or "").strip()[:240]
                    fact_conf = float(fact.get("confidence") or 0.58)
                    if await _upsert_fact(
                        conn,
                        ghost_id=ghost_id,
                        person_key=key,
                        fact_type=fact_type,
                        fact_value=fact_value,
                        confidence=fact_conf,
                        source_session_id=session_id,
                        source_role="user",
                        evidence_text=text,
                        metadata={"source": source, "bound_ingest": True},
                    ):
                        summary["facts_upserted"] += 1
                        await _promote_fact_entity(
                            conn,
                            ghost_id=ghost_id,
                            person_key=key,
                            fact_type=fact_type,
                            fact_value=fact_value,
                            confidence=fact_conf,
                            evidence_text=text,
                            source=source,
                        )

                for mention in mentions:
                    mention_name = str(mention.get("display_name") or "").strip()
                    if not mention_name:
                        continue
                    mention_key = normalize_person_key(mention.get("person_key") or mention_name)
                    await _upsert_person_profile(
                        conn,
                        ghost_id=ghost_id,
                        person_key=mention_key,
                        display_name=mention_name,
                        mention_inc=1,
                        confidence=float(mention.get("confidence") or 0.55),
                        metadata={"source": source, "mentioned_by": key},
                    )
                    rel = str(mention.get("relation") or "").strip()
                    if rel:
                        if await _upsert_fact(
                            conn,
                            ghost_id=ghost_id,
                            person_key=mention_key,
                            fact_type="relationship_to_speaker",
                            fact_value=f"{rel}:{display_name}",
                            confidence=float(mention.get("confidence") or 0.55),
                            source_session_id=session_id,
                            source_role="user",
                            evidence_text=text,
                            metadata={"source": source, "speaker_key": key},
                        ):
                            summary["mentions_upserted"] += 1
                            await _upsert_person_person_assoc(
                                conn,
                                ghost_id=ghost_id,
                                source_person_key=key,
                                target_person_key=mention_key,
                                relationship_type=rel,
                                confidence=float(mention.get("confidence") or 0.55),
                                source=source,
                                evidence_text=text,
                                metadata={"speaker_key": key},
                            )

    except Exception as exc:
        logger.error("Bound rolodex ingest failed: %s", exc)
        await _record_ingest_failure(
            pool,
            ghost_id=ghost_id,
            session_id=session_id,
            role="user",
            message_text=text,
            error_text=str(exc),
            source="ingest_bound_message",
        )
        return {"ingested": False, "reason": f"exception:{exc}"}

    return summary


async def reconcile_fact_entities(
    pool,
    *,
    ghost_id: str,
    limit: int = 2000,
    person_key: Optional[str] = None,
) -> dict[str, Any]:
    """
    Ensure place/thing entities and person associations exist for active Rolodex facts.
    Only promotes missing entity/association edges to avoid churn.
    """
    if pool is None:
        return {"ok": False, "reason": "pool_unavailable"}

    cap = max(1, min(int(limit or 0), 10000))
    person_norm = normalize_person_key(person_key) if person_key else ""

    promoted_places = 0
    promoted_things = 0
    promoted_person_relations = 0
    skipped_existing = 0
    examined = 0
    scanned_rows = 0

    async with pool.acquire() as conn:
        if person_norm:
            fact_rows = await conn.fetch(
                """
                SELECT person_key, fact_type, fact_value, confidence, evidence_text, metadata
                FROM person_memory_facts
                WHERE ghost_id = $1
                  AND person_key = $2
                  AND invalidated_at IS NULL
                ORDER BY last_observed_at DESC
                LIMIT $3
                """,
                ghost_id,
                person_norm,
                cap,
            )
        else:
            fact_rows = await conn.fetch(
                """
                SELECT person_key, fact_type, fact_value, confidence, evidence_text, metadata
                FROM person_memory_facts
                WHERE ghost_id = $1
                  AND invalidated_at IS NULL
                ORDER BY last_observed_at DESC
                LIMIT $2
                """,
                ghost_id,
                cap,
            )

        locked_person_rows = await conn.fetch(
            """
            SELECT person_key
            FROM person_rolodex
            WHERE ghost_id = $1
              AND is_locked = TRUE
              AND invalidated_at IS NULL
            """,
            ghost_id,
        )
        locked_person_keys: set[str] = {
            normalize_person_key(str(r["person_key"])) for r in locked_person_rows if r["person_key"]
        }

        place_rows = await conn.fetch(
            """
            SELECT place_key
            FROM place_entities
            WHERE ghost_id = $1
              AND invalidated_at IS NULL
            """,
            ghost_id,
        )
        thing_rows = await conn.fetch(
            """
            SELECT thing_key
            FROM thing_entities
            WHERE ghost_id = $1
              AND invalidated_at IS NULL
            """,
            ghost_id,
        )
        if person_norm:
            ppr_rows = await conn.fetch(
                """
                SELECT source_person_key, target_person_key, relationship_type
                FROM person_person_associations
                WHERE ghost_id = $1
                  AND invalidated_at IS NULL
                  AND (source_person_key = $2 OR target_person_key = $2)
                """,
                ghost_id,
                person_norm,
            )
            pp_rows = await conn.fetch(
                """
                SELECT person_key, place_key
                FROM person_place_associations
                WHERE ghost_id = $1
                  AND person_key = $2
                  AND invalidated_at IS NULL
                """,
                ghost_id,
                person_norm,
            )
            pt_rows = await conn.fetch(
                """
                SELECT person_key, thing_key
                FROM person_thing_associations
                WHERE ghost_id = $1
                  AND person_key = $2
                  AND invalidated_at IS NULL
                """,
                ghost_id,
                person_norm,
            )
        else:
            ppr_rows = await conn.fetch(
                """
                SELECT source_person_key, target_person_key, relationship_type
                FROM person_person_associations
                WHERE ghost_id = $1
                  AND invalidated_at IS NULL
                """,
                ghost_id,
            )
            pp_rows = await conn.fetch(
                """
                SELECT person_key, place_key
                FROM person_place_associations
                WHERE ghost_id = $1
                  AND invalidated_at IS NULL
                """,
                ghost_id,
            )
            pt_rows = await conn.fetch(
                """
                SELECT person_key, thing_key
                FROM person_thing_associations
                WHERE ghost_id = $1
                  AND invalidated_at IS NULL
                """,
                ghost_id,
            )

        place_keys = {str(r["place_key"] or "") for r in place_rows if r["place_key"]}
        thing_keys = {str(r["thing_key"] or "") for r in thing_rows if r["thing_key"]}
        person_person_triples = {
            (
                normalize_person_key(str(r["source_person_key"] or "")),
                normalize_person_key(str(r["target_person_key"] or "")),
                entity_store.normalize_relationship_type(str(r["relationship_type"] or "")),
            )
            for r in ppr_rows
            if r["source_person_key"] and r["target_person_key"] and r["relationship_type"]
        }
        person_place_pairs = {
            (normalize_person_key(str(r["person_key"] or "")), str(r["place_key"] or ""))
            for r in pp_rows
            if r["person_key"] and r["place_key"]
        }
        person_thing_pairs = {
            (normalize_person_key(str(r["person_key"] or "")), str(r["thing_key"] or ""))
            for r in pt_rows
            if r["person_key"] and r["thing_key"]
        }

        seen: set[tuple[str, str, str]] = set()
        for row in fact_rows:
            scanned_rows += 1
            f_type = str(row["fact_type"] or "").strip().lower()
            metadata = _normalize_json_obj(row.get("metadata"))
            if f_type == "relationship_to_speaker":
                speaker_key = normalize_person_key(str(metadata.get("speaker_key") or ""))
                relation_value = str(row["fact_value"] or "").strip()
                relation = relation_value.split(":", 1)[0].strip().lower()
                person = normalize_person_key(str(row["person_key"] or ""))
                if speaker_key and person and relation and person not in locked_person_keys:
                    relation_sig = (speaker_key, person, entity_store.normalize_relationship_type(relation))
                    if relation_sig in person_person_triples:
                        skipped_existing += 1
                    else:
                        await _upsert_person_person_assoc(
                            conn,
                            ghost_id=ghost_id,
                            source_person_key=speaker_key,
                            target_person_key=person,
                            relationship_type=relation,
                            confidence=float(row["confidence"] or 0.6),
                            source="rolodex_reconcile",
                            evidence_text=str(row["evidence_text"] or ""),
                            metadata={"speaker_key": speaker_key, "reconciled_from_fact": True},
                        )
                        promoted_person_relations += 1
                        person_person_triples.add(relation_sig)
                continue
            bucket = _fact_bucket(f_type)
            if bucket not in {"place", "thing"}:
                continue
            person = normalize_person_key(str(row["person_key"] or ""))
            value = str(row["fact_value"] or "").strip()
            if not person or not value:
                continue
            if person in locked_person_keys:
                skipped_existing += 1
                continue
            entity_key = entity_store.normalize_key(value)
            if not entity_key or entity_key == "unknown":
                continue
            sig = (person, bucket, entity_key)
            if sig in seen:
                continue
            seen.add(sig)
            examined += 1

            if bucket == "place":
                if entity_key in place_keys and (person, entity_key) in person_place_pairs:
                    skipped_existing += 1
                    continue
                await _promote_fact_entity(
                    conn,
                    ghost_id=ghost_id,
                    person_key=person,
                    fact_type=f_type,
                    fact_value=value,
                    confidence=float(row["confidence"] or 0.6),
                    evidence_text=str(row["evidence_text"] or ""),
                    source="rolodex_reconcile",
                )
                promoted_places += 1
                place_keys.add(entity_key)
                person_place_pairs.add((person, entity_key))
                continue

            if entity_key in thing_keys and (person, entity_key) in person_thing_pairs:
                skipped_existing += 1
                continue
            await _promote_fact_entity(
                conn,
                ghost_id=ghost_id,
                person_key=person,
                fact_type=f_type,
                fact_value=value,
                confidence=float(row["confidence"] or 0.6),
                evidence_text=str(row["evidence_text"] or ""),
                source="rolodex_reconcile",
            )
            promoted_things += 1
            thing_keys.add(entity_key)
            person_thing_pairs.add((person, entity_key))

    return {
        "ok": True,
        "ghost_id": ghost_id,
        "person_key": person_norm or None,
        "scanned_rows": scanned_rows,
        "examined_candidates": examined,
        "promoted_places": promoted_places,
        "promoted_things": promoted_things,
        "promoted_person_relations": promoted_person_relations,
        "skipped_existing": skipped_existing,
    }


async def merge_people(
    pool,
    *,
    ghost_id: str,
    source_person_key: str,
    target_person_key: str,
    reason: str = "",
    keep_source_active: bool = False,
) -> dict[str, Any]:
    """
    Merge source profile into target profile and rewire relational associations.
    Source profile is archived by default.
    """
    if pool is None:
        return {"ok": False, "reason": "pool_unavailable"}

    source_key = normalize_person_key(source_person_key)
    target_key = normalize_person_key(target_person_key)
    if not source_key or not target_key:
        return {"ok": False, "reason": "invalid_keys"}
    if source_key == target_key:
        return {
            "ok": True,
            "status": "noop_same_key",
            "source_person_key": source_key,
            "target_person_key": target_key,
        }

    reason_text = str(reason or "").strip()[:240]

    promoted: dict[str, Any] = {"ok": False, "reason": "not_run"}
    target_updated: dict[str, Any] = {}
    facts_tag = "UPDATE 0"
    bindings_tag = "UPDATE 0"
    person_person_out_tag = "UPDATE 0"
    person_person_in_tag = "UPDATE 0"
    place_assoc_tag = "UPDATE 0"
    thing_assoc_tag = "UPDATE 0"
    idea_assoc_tag = "UPDATE 0"
    source_update_tag = "UPDATE 0"
    target_had_contact = False
    source_had_contact = False
    contact_transfer_conflict = False
    contact_transfer_applied = False

    async with pool.acquire() as conn:
        async with conn.transaction():
            source = await conn.fetchrow(
                """
                SELECT person_key, display_name, interaction_count, mention_count, confidence,
                       contact_handle, is_locked, first_seen, last_seen, notes, metadata
                FROM person_rolodex
                WHERE ghost_id = $1
                  AND person_key = $2
                  AND invalidated_at IS NULL
                LIMIT 1
                """,
                ghost_id,
                source_key,
            )
            if not source:
                return {
                    "ok": False,
                    "reason": "source_not_found",
                    "source_person_key": source_key,
                    "target_person_key": target_key,
                }
            source_had_contact = bool(str(source["contact_handle"] or "").strip())

            target = await conn.fetchrow(
                """
                SELECT person_key, display_name, interaction_count, mention_count, confidence,
                       contact_handle, is_locked, first_seen, last_seen, notes, metadata
                FROM person_rolodex
                WHERE ghost_id = $1
                  AND person_key = $2
                LIMIT 1
                """,
                ghost_id,
                target_key,
            )
            if not target:
                await _upsert_person_profile(
                    conn,
                    ghost_id=ghost_id,
                    person_key=target_key,
                    display_name=str(source["display_name"] or target_key.replace("_", " ").title()),
                    confidence=float(source["confidence"] or 0.5),
                    metadata={"source": "merge_seed", "merged_from": [source_key]},
                    contact_handle=str(source["contact_handle"] or ""),
                )
                target = await conn.fetchrow(
                    """
                    SELECT person_key, display_name, interaction_count, mention_count, confidence,
                           contact_handle, is_locked, first_seen, last_seen, notes, metadata
                    FROM person_rolodex
                    WHERE ghost_id = $1
                      AND person_key = $2
                    LIMIT 1
                    """,
                    ghost_id,
                    target_key,
                )
            if not target:
                return {"ok": False, "reason": "target_seed_failed"}

            source_meta = _normalize_json_obj(source["metadata"])
            target_meta = _normalize_json_obj(target["metadata"])
            merged_from = list(target_meta.get("merged_from") or [])
            if source_key not in merged_from:
                merged_from.append(source_key)
            merged_metadata = dict(target_meta)
            merged_metadata["merged_from"] = merged_from
            if reason_text:
                merged_metadata["merge_reason"] = reason_text
            merged_metadata["last_merge_at"] = time.time()
            source_notes = str(source["notes"] or "").strip()
            target_notes = str(target["notes"] or "").strip()
            merged_notes = target_notes
            if source_notes:
                target_notes_norm = re.sub(r"\s+", " ", target_notes.lower()).strip()
                source_notes_norm = re.sub(r"\s+", " ", source_notes.lower()).strip()
                if source_notes_norm and source_notes_norm not in target_notes_norm:
                    merged_notes = f"{target_notes}\n\n{source_notes}".strip() if target_notes else source_notes
            target_display_name = str(target["display_name"] or "").strip()
            if not target_display_name or target_display_name.lower() in {"unknown", target_key.replace("_", " ")}:
                target_display_name = str(source["display_name"] or target_key.replace("_", " ").title())

            facts_tag = await conn.execute(
                """
                INSERT INTO person_memory_facts (
                    ghost_id, person_key, fact_type, fact_value, confidence,
                    source_session_id, source_role, evidence_text, metadata,
                    observation_count, first_observed_at, last_observed_at
                )
                SELECT
                    ghost_id, $3, fact_type, fact_value, confidence,
                    source_session_id, source_role, evidence_text, COALESCE(metadata, '{}'::jsonb),
                    observation_count, first_observed_at, last_observed_at
                FROM person_memory_facts
                WHERE ghost_id = $1
                  AND person_key = $2
                  AND invalidated_at IS NULL
                ON CONFLICT (ghost_id, person_key, fact_type, fact_value, source_role) DO UPDATE
                SET
                    confidence = GREATEST(person_memory_facts.confidence, EXCLUDED.confidence),
                    observation_count = person_memory_facts.observation_count + EXCLUDED.observation_count,
                    first_observed_at = LEAST(person_memory_facts.first_observed_at, EXCLUDED.first_observed_at),
                    last_observed_at = GREATEST(person_memory_facts.last_observed_at, EXCLUDED.last_observed_at),
                    evidence_text = CASE
                        WHEN length(person_memory_facts.evidence_text) >= length(EXCLUDED.evidence_text)
                        THEN person_memory_facts.evidence_text
                        ELSE EXCLUDED.evidence_text
                    END,
                    metadata = COALESCE(person_memory_facts.metadata, '{}'::jsonb) || EXCLUDED.metadata
                """,
                ghost_id,
                source_key,
                target_key,
            )
            if not keep_source_active:
                await conn.execute(
                    """
                    UPDATE person_memory_facts
                    SET invalidated_at = now(), last_observed_at = now()
                    WHERE ghost_id = $1
                      AND person_key = $2
                      AND invalidated_at IS NULL
                    """,
                    ghost_id,
                    source_key,
                )

            bindings_tag = await conn.execute(
                """
                INSERT INTO person_session_binding (ghost_id, session_id, person_key, confidence)
                SELECT ghost_id, session_id, $3, confidence
                FROM person_session_binding
                WHERE ghost_id = $1
                  AND person_key = $2
                ON CONFLICT (ghost_id, session_id) DO UPDATE
                SET
                    person_key = EXCLUDED.person_key,
                    confidence = GREATEST(person_session_binding.confidence, EXCLUDED.confidence),
                    updated_at = now()
                """,
                ghost_id,
                source_key,
                target_key,
            )
            await conn.execute(
                """
                DELETE FROM person_session_binding
                WHERE ghost_id = $1
                  AND person_key = $2
                """,
                ghost_id,
                source_key,
            )

            place_assoc_tag = await conn.execute(
                """
                INSERT INTO person_place_associations (
                    ghost_id, person_key, place_key, confidence, source, evidence_text, metadata
                )
                SELECT
                    ghost_id, $3, place_key, confidence, source, evidence_text, COALESCE(metadata, '{}'::jsonb)
                FROM person_place_associations
                WHERE ghost_id = $1
                  AND person_key = $2
                  AND invalidated_at IS NULL
                ON CONFLICT (ghost_id, person_key, place_key) DO UPDATE
                SET
                    confidence = GREATEST(person_place_associations.confidence, EXCLUDED.confidence),
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
                source_key,
                target_key,
            )
            person_person_out_tag = await conn.execute(
                """
                INSERT INTO person_person_associations (
                    ghost_id, source_person_key, target_person_key, relationship_type,
                    confidence, source, evidence_text, metadata
                )
                SELECT
                    ghost_id, $3, target_person_key, relationship_type,
                    confidence, source, evidence_text, COALESCE(metadata, '{}'::jsonb)
                FROM person_person_associations
                WHERE ghost_id = $1
                  AND source_person_key = $2
                  AND invalidated_at IS NULL
                ON CONFLICT (ghost_id, source_person_key, target_person_key, relationship_type) DO UPDATE
                SET
                    confidence = GREATEST(person_person_associations.confidence, EXCLUDED.confidence),
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
                source_key,
                target_key,
            )
            person_person_in_tag = await conn.execute(
                """
                INSERT INTO person_person_associations (
                    ghost_id, source_person_key, target_person_key, relationship_type,
                    confidence, source, evidence_text, metadata
                )
                SELECT
                    ghost_id, source_person_key, $3, relationship_type,
                    confidence, source, evidence_text, COALESCE(metadata, '{}'::jsonb)
                FROM person_person_associations
                WHERE ghost_id = $1
                  AND target_person_key = $2
                  AND invalidated_at IS NULL
                ON CONFLICT (ghost_id, source_person_key, target_person_key, relationship_type) DO UPDATE
                SET
                    confidence = GREATEST(person_person_associations.confidence, EXCLUDED.confidence),
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
                source_key,
                target_key,
            )
            thing_assoc_tag = await conn.execute(
                """
                INSERT INTO person_thing_associations (
                    ghost_id, person_key, thing_key, confidence, source, evidence_text, metadata
                )
                SELECT
                    ghost_id, $3, thing_key, confidence, source, evidence_text, COALESCE(metadata, '{}'::jsonb)
                FROM person_thing_associations
                WHERE ghost_id = $1
                  AND person_key = $2
                  AND invalidated_at IS NULL
                ON CONFLICT (ghost_id, person_key, thing_key) DO UPDATE
                SET
                    confidence = GREATEST(person_thing_associations.confidence, EXCLUDED.confidence),
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
                source_key,
                target_key,
            )
            idea_assoc_tag = await conn.execute(
                """
                INSERT INTO idea_entity_associations (
                    ghost_id, concept_key, target_type, target_key, confidence, source, metadata
                )
                SELECT
                    ghost_id, concept_key, target_type, $3, confidence, source, COALESCE(metadata, '{}'::jsonb)
                FROM idea_entity_associations
                WHERE ghost_id = $1
                  AND target_type = 'person'
                  AND target_key = $2
                  AND invalidated_at IS NULL
                ON CONFLICT (ghost_id, concept_key, target_type, target_key) DO UPDATE
                SET
                    confidence = GREATEST(idea_entity_associations.confidence, EXCLUDED.confidence),
                    source = EXCLUDED.source,
                    metadata = COALESCE(idea_entity_associations.metadata, '{}'::jsonb) || EXCLUDED.metadata,
                    invalidated_at = NULL,
                    updated_at = now()
                """,
                ghost_id,
                source_key,
                target_key,
            )

            if not keep_source_active:
                await conn.execute(
                    """
                    UPDATE person_person_associations
                    SET invalidated_at = now(), updated_at = now()
                    WHERE ghost_id = $1
                      AND (source_person_key = $2 OR target_person_key = $2)
                      AND invalidated_at IS NULL
                    """,
                    ghost_id,
                    source_key,
                )
                await conn.execute(
                    """
                    UPDATE person_place_associations
                    SET invalidated_at = now(), updated_at = now()
                    WHERE ghost_id = $1
                      AND person_key = $2
                      AND invalidated_at IS NULL
                    """,
                    ghost_id,
                    source_key,
                )
                await conn.execute(
                    """
                    UPDATE person_thing_associations
                    SET invalidated_at = now(), updated_at = now()
                    WHERE ghost_id = $1
                      AND person_key = $2
                      AND invalidated_at IS NULL
                    """,
                    ghost_id,
                    source_key,
                )
                await conn.execute(
                    """
                    UPDATE idea_entity_associations
                    SET invalidated_at = now(), updated_at = now()
                    WHERE ghost_id = $1
                      AND target_type = 'person'
                      AND target_key = $2
                      AND invalidated_at IS NULL
                    """,
                    ghost_id,
                    source_key,
                )

            source_contact = str(source["contact_handle"] or "").strip()
            target_contact = str(target["contact_handle"] or "").strip()
            target_had_contact = bool(target_contact)
            contact_for_target = target_contact
            if source_contact and not target_contact:
                conflict = await conn.fetchrow(
                    """
                    SELECT person_key
                    FROM person_rolodex
                    WHERE ghost_id = $1
                      AND contact_handle = $2
                      AND person_key NOT IN ($3, $4)
                    LIMIT 1
                    """,
                    ghost_id,
                    source_contact,
                    source_key,
                    target_key,
                )
                if conflict:
                    contact_transfer_conflict = True
                else:
                    contact_for_target = source_contact
                    contact_transfer_applied = True
                    if not keep_source_active:
                        await conn.execute(
                            """
                            UPDATE person_rolodex
                            SET contact_handle = NULL, updated_at = now()
                            WHERE ghost_id = $1
                              AND person_key = $2
                            """,
                            ghost_id,
                            source_key,
                        )
            source_first_seen = source["first_seen"]
            source_last_seen = source["last_seen"]
            target_row_updated = await conn.fetchrow(
                """
                UPDATE person_rolodex
                SET
                    display_name = COALESCE(NULLIF($3, ''), display_name),
                    interaction_count = COALESCE(interaction_count, 0) + $4,
                    mention_count = COALESCE(mention_count, 0) + $5,
                    confidence = GREATEST(COALESCE(confidence, 0.0), $6),
                    metadata = COALESCE(metadata, '{}'::jsonb) || $7::jsonb,
                    contact_handle = COALESCE(NULLIF(contact_handle, ''), NULLIF($8, '')),
                    is_locked = COALESCE(is_locked, FALSE) OR $9,
                    locked_at = CASE
                        WHEN (COALESCE(is_locked, FALSE) OR $9) THEN COALESCE(locked_at, now())
                        ELSE NULL
                    END,
                    first_seen = CASE
                        WHEN first_seen IS NULL THEN $10::timestamptz
                        WHEN $10::timestamptz IS NULL THEN first_seen
                        ELSE LEAST(first_seen, $10::timestamptz)
                    END,
                    last_seen = CASE
                        WHEN last_seen IS NULL THEN $11::timestamptz
                        WHEN $11::timestamptz IS NULL THEN last_seen
                        ELSE GREATEST(last_seen, $11::timestamptz)
                    END,
                    notes = COALESCE(NULLIF($12, ''), notes),
                    invalidated_at = NULL,
                    updated_at = now()
                WHERE ghost_id = $1
                  AND person_key = $2
                RETURNING person_key, display_name, interaction_count, mention_count, confidence, contact_handle, is_locked, notes
                """,
                ghost_id,
                target_key,
                target_display_name,
                int(source["interaction_count"] or 0),
                int(source["mention_count"] or 0),
                float(source["confidence"] or 0.0),
                json.dumps(merged_metadata),
                contact_for_target,
                bool(source["is_locked"]),
                source_first_seen,
                source_last_seen,
                merged_notes,
            )
            target_updated = dict(target_row_updated or {})

            source_meta = dict(source_meta)
            source_meta["merged_into"] = target_key
            source_meta["merged_at"] = time.time()
            if reason_text:
                source_meta["merge_reason"] = reason_text
            if keep_source_active:
                source_update_tag = await conn.execute(
                    """
                    UPDATE person_rolodex
                    SET metadata = COALESCE(metadata, '{}'::jsonb) || $3::jsonb,
                        updated_at = now()
                    WHERE ghost_id = $1
                      AND person_key = $2
                    """,
                    ghost_id,
                    source_key,
                    json.dumps(source_meta),
                )
            else:
                source_update_tag = await conn.execute(
                    """
                    UPDATE person_rolodex
                    SET invalidated_at = now(),
                        metadata = COALESCE(metadata, '{}'::jsonb) || $3::jsonb,
                        updated_at = now()
                    WHERE ghost_id = $1
                      AND person_key = $2
                    """,
                    ghost_id,
                    source_key,
                    json.dumps(source_meta),
                )

    promoted = await reconcile_fact_entities(
        pool,
        ghost_id=ghost_id,
        person_key=target_key,
        limit=4000,
    )

    return {
        "ok": True,
        "source_person_key": source_key,
        "target_person_key": target_key,
        "target_profile": {
            "person_key": str(target_updated.get("person_key") or target_key),
            "display_name": str(target_updated.get("display_name") or ""),
            "interaction_count": int(target_updated.get("interaction_count") or 0),
            "mention_count": int(target_updated.get("mention_count") or 0),
            "confidence": float(target_updated.get("confidence") or 0.0),
            "contact_handle": str(target_updated.get("contact_handle") or ""),
            "is_locked": bool(target_updated.get("is_locked")),
        },
        "merged_counts": {
            "facts": _command_rowcount(facts_tag),
            "session_bindings": _command_rowcount(bindings_tag),
            "person_person_outgoing": _command_rowcount(person_person_out_tag),
            "person_person_incoming": _command_rowcount(person_person_in_tag),
            "person_place": _command_rowcount(place_assoc_tag),
            "person_thing": _command_rowcount(thing_assoc_tag),
            "idea_person_links": _command_rowcount(idea_assoc_tag),
        },
        "source_archived": (not keep_source_active) and _command_rowcount(source_update_tag) > 0,
        "reason": reason_text,
        "reconcile": promoted,
        "contact_transfer": {
            "source_had_contact": bool(source_had_contact),
            "target_had_contact": bool(target_had_contact),
            "applied": bool(contact_transfer_applied),
            "skipped_due_conflict": bool(contact_transfer_conflict),
        },
    }


async def update_person_notes(pool, ghost_id: str, person_key: str, notes: str) -> bool:
    """Update manual operator notes for a person."""
    if pool is None:
        return False
    key = normalize_person_key(person_key)
    async with pool.acquire() as conn:
        res = await conn.execute(
            """
            UPDATE person_rolodex
            SET notes = $3, updated_at = now()
            WHERE ghost_id = $1 AND person_key = $2 AND invalidated_at IS NULL
            """,
            ghost_id,
            key,
            str(notes or "").strip(),
        )
        return res == "UPDATE 1"


async def update_person_contact_handle(
    pool,
    ghost_id: str,
    person_key: str,
    contact_handle: Optional[str],
) -> Optional[dict[str, Any]]:
    if pool is None:
        return None
    key = normalize_person_key(person_key)
    normalized = normalize_contact_handle(contact_handle or "")
    async with pool.acquire() as conn:
        if normalized:
            conflict_row = await conn.fetchrow(
                """
                SELECT person_key
                FROM person_rolodex
                WHERE ghost_id = $1
                  AND contact_handle = $2
                  AND person_key <> $3
                  AND invalidated_at IS NULL
                LIMIT 1
                """,
                ghost_id,
                normalized,
                key,
            )
            if conflict_row:
                raise ValueError("contact_handle_conflict")
        row = await conn.fetchrow(
            """
            UPDATE person_rolodex
            SET
                contact_handle = $3,
                updated_at = now()
            WHERE ghost_id = $1
              AND person_key = $2
              AND invalidated_at IS NULL
            RETURNING person_key, display_name, contact_handle, updated_at
            """,
            ghost_id,
            key,
            normalized or None,
        )
    if not row:
        return None
    return {
        "person_key": str(row["person_key"]),
        "display_name": str(row["display_name"] or ""),
        "contact_handle": str(row["contact_handle"] or ""),
        "updated_at": row["updated_at"].timestamp() if row["updated_at"] else None,
    }


async def set_person_lock(pool, ghost_id: str, person_key: str, locked: bool) -> Optional[dict[str, Any]]:
    if pool is None:
        return None
    key = normalize_person_key(person_key)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE person_rolodex
            SET
                is_locked = $3,
                locked_at = CASE
                    WHEN $3 THEN COALESCE(locked_at, now())
                    ELSE NULL
                END,
                updated_at = now()
            WHERE ghost_id = $1
              AND person_key = $2
              AND invalidated_at IS NULL
            RETURNING person_key, display_name, is_locked, locked_at, updated_at
            """,
            ghost_id,
            key,
            bool(locked),
        )
    if not row:
        return None
    return {
        "person_key": row["person_key"],
        "display_name": row["display_name"],
        "is_locked": bool(row["is_locked"]),
        "locked_at": row["locked_at"].timestamp() if row["locked_at"] else None,
        "updated_at": row["updated_at"].timestamp() if row["updated_at"] else None,
    }


def _command_rowcount(tag: str) -> int:
    try:
        return int(str(tag).split()[-1])
    except Exception:
        return 0


async def delete_person(pool, ghost_id: str, person_key: str) -> Optional[dict[str, Any]]:
    if pool is None:
        return None
    key = normalize_person_key(person_key)
    async with pool.acquire() as conn:
        async with conn.transaction():
            deleted_profile = await conn.fetchrow(
                """
                UPDATE person_rolodex
                SET invalidated_at = now(), updated_at = now()
                WHERE ghost_id = $1
                  AND person_key = $2
                  AND invalidated_at IS NULL
                RETURNING person_key, display_name
                """,
                ghost_id,
                key,
            )
            if not deleted_profile:
                return None

            facts_tag = await conn.execute(
                """
                UPDATE person_memory_facts
                SET invalidated_at = now(), last_observed_at = now()
                WHERE ghost_id = $1
                  AND person_key = $2
                  AND invalidated_at IS NULL
                """,
                ghost_id,
                key,
            )
            binding_tag = await conn.execute(
                """
                DELETE FROM person_session_binding
                WHERE ghost_id = $1
                  AND person_key = $2
                """,
                ghost_id,
                key,
            )
    return {
        "person_key": deleted_profile["person_key"],
        "display_name": deleted_profile["display_name"],
        "facts_soft_deleted": _command_rowcount(facts_tag),
        "bindings_deleted": _command_rowcount(binding_tag),
        "mode": "soft_delete",
    }


async def purge_person(pool, ghost_id: str, person_key: str) -> Optional[dict[str, Any]]:
    if pool is None:
        return None
    key = normalize_person_key(person_key)
    async with pool.acquire() as conn:
        async with conn.transaction():
            deleted_profile = await conn.fetchrow(
                """
                DELETE FROM person_rolodex
                WHERE ghost_id = $1
                  AND person_key = $2
                RETURNING person_key, display_name
                """,
                ghost_id,
                key,
            )
            if not deleted_profile:
                return None

            facts_tag = await conn.execute(
                """
                DELETE FROM person_memory_facts
                WHERE ghost_id = $1
                  AND person_key = $2
                """,
                ghost_id,
                key,
            )
            binding_tag = await conn.execute(
                """
                DELETE FROM person_session_binding
                WHERE ghost_id = $1
                  AND person_key = $2
                """,
                ghost_id,
                key,
            )
    return {
        "person_key": deleted_profile["person_key"],
        "display_name": deleted_profile["display_name"],
        "facts_deleted": _command_rowcount(facts_tag),
        "bindings_deleted": _command_rowcount(binding_tag),
        "mode": "purge",
    }


async def restore_person(pool, ghost_id: str, person_key: str) -> Optional[dict[str, Any]]:
    if pool is None:
        return None
    key = normalize_person_key(person_key)
    async with pool.acquire() as conn:
        async with conn.transaction():
            restored_profile = await conn.fetchrow(
                """
                UPDATE person_rolodex
                SET invalidated_at = NULL, updated_at = now(), last_seen = now()
                WHERE ghost_id = $1
                  AND person_key = $2
                  AND invalidated_at IS NOT NULL
                RETURNING person_key, display_name
                """,
                ghost_id,
                key,
            )
            if not restored_profile:
                return None
            facts_tag = await conn.execute(
                """
                UPDATE person_memory_facts
                SET invalidated_at = NULL, last_observed_at = now()
                WHERE ghost_id = $1
                  AND person_key = $2
                  AND invalidated_at IS NOT NULL
                """,
                ghost_id,
                key,
            )
    return {
        "person_key": str(restored_profile["person_key"]),
        "display_name": str(restored_profile["display_name"] or ""),
        "facts_restored": _command_rowcount(facts_tag),
        "mode": "restore",
    }


async def list_ingest_failures(
    pool,
    *,
    ghost_id: str,
    limit: int = 100,
    unresolved_only: bool = True,
) -> list[dict[str, Any]]:
    if pool is None:
        return []
    cap = max(1, min(int(limit), 500))
    async with pool.acquire() as conn:
        if unresolved_only:
            rows = await conn.fetch(
                """
                SELECT id, ghost_id, session_id, role, source, message_text, error_text,
                       retry_count, created_at, last_retry_at, resolved_at
                FROM rolodex_ingest_failures
                WHERE ghost_id = $1
                  AND resolved_at IS NULL
                ORDER BY created_at DESC
                LIMIT $2
                """,
                ghost_id,
                cap,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, ghost_id, session_id, role, source, message_text, error_text,
                       retry_count, created_at, last_retry_at, resolved_at
                FROM rolodex_ingest_failures
                WHERE ghost_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                ghost_id,
                cap,
            )
    return [
        {
            "id": int(r["id"]),
            "ghost_id": str(r["ghost_id"] or ""),
            "session_id": str(r["session_id"] or ""),
            "role": str(r["role"] or ""),
            "source": str(r["source"] or ""),
            "message_text": str(r["message_text"] or ""),
            "error_text": str(r["error_text"] or ""),
            "retry_count": int(r["retry_count"] or 0),
            "created_at": r["created_at"].timestamp() if r["created_at"] else None,
            "last_retry_at": r["last_retry_at"].timestamp() if r["last_retry_at"] else None,
            "resolved_at": r["resolved_at"].timestamp() if r["resolved_at"] else None,
        }
        for r in rows
    ]


async def retry_ingest_failures(
    pool,
    *,
    ghost_id: str,
    limit: int = 25,
) -> dict[str, Any]:
    if pool is None:
        return {"ok": False, "error": "pool_unavailable"}

    rows = await list_ingest_failures(pool, ghost_id=ghost_id, limit=limit, unresolved_only=True)
    retried = 0
    recovered = 0
    still_failed = 0
    details: list[dict[str, Any]] = []

    for row in rows:
        retried += 1
        failure_id = int(row.get("id") or 0)
        role = str(row.get("role") or "user").lower()
        session_id = str(row.get("session_id") or "").strip() or None
        text = str(row.get("message_text") or "")
        try:
            if role == "ghost":
                result = await ingest_ghost_response(
                    pool,
                    message_text=text,
                    session_id=session_id,
                    ghost_id=ghost_id,
                    record_failure=False,
                )
            else:
                result = await ingest_message(
                    pool,
                    message_text=text,
                    session_id=session_id,
                    role=role or "user",
                    ghost_id=ghost_id,
                    record_failure=False,
                )
        except Exception as exc:
            result = {"ingested": False, "reason": f"retry_exception:{exc}"}

        ok = bool(result.get("ingested"))
        if ok:
            recovered += 1
        else:
            still_failed += 1
        details.append(
            {
                "id": failure_id,
                "ok": ok,
                "reason": str(result.get("reason") or ""),
            }
        )

        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE rolodex_ingest_failures
                SET
                    retry_count = retry_count + 1,
                    last_retry_at = now(),
                    error_text = CASE
                        WHEN $2 THEN error_text
                        ELSE LEFT($3, 1000)
                    END,
                    resolved_at = CASE
                        WHEN $2 THEN now()
                        ELSE resolved_at
                    END
                WHERE id = $1
                """,
                failure_id,
                ok,
                str(result.get("reason") or "retry_failed"),
            )

    return {
        "ok": True,
        "retried": retried,
        "recovered": recovered,
        "still_failed": still_failed,
        "details": details,
    }


def _normalized_name_for_dup(display_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(display_name or "").lower())


async def integrity_check(pool, *, ghost_id: str, include_samples: bool = True) -> dict[str, Any]:
    if pool is None:
        return {"ok": False, "error": "pool_unavailable"}

    async with pool.acquire() as conn:
        orphaned = await conn.fetch(
            """
            SELECT f.person_key, f.fact_type, f.fact_value, f.last_observed_at
            FROM person_memory_facts f
            LEFT JOIN person_rolodex p
              ON p.ghost_id = f.ghost_id
             AND p.person_key = f.person_key
             AND p.invalidated_at IS NULL
            WHERE f.ghost_id = $1
              AND f.invalidated_at IS NULL
              AND p.person_key IS NULL
            ORDER BY f.last_observed_at DESC
            LIMIT 120
            """,
            ghost_id,
        )
        empty_profiles = await conn.fetch(
            """
            SELECT p.person_key, p.display_name, p.last_seen
            FROM person_rolodex p
            LEFT JOIN person_memory_facts f
              ON f.ghost_id = p.ghost_id
             AND f.person_key = p.person_key
             AND f.invalidated_at IS NULL
            WHERE p.ghost_id = $1
              AND p.invalidated_at IS NULL
            GROUP BY p.person_key, p.display_name, p.last_seen
            HAVING COUNT(f.id) = 0
            ORDER BY p.last_seen DESC
            LIMIT 120
            """,
            ghost_id,
        )
        stale_bindings = await conn.fetch(
            """
            SELECT b.session_id::text AS session_id, b.person_key, s.ended_at
            FROM person_session_binding b
            JOIN sessions s ON s.id = b.session_id::text
            JOIN person_rolodex p
              ON p.ghost_id = b.ghost_id
             AND p.person_key = b.person_key
             AND p.invalidated_at IS NULL
            WHERE b.ghost_id = $1
              AND s.ended_at IS NOT NULL
              AND s.ended_at <= (now() - interval '7 days')
            ORDER BY s.ended_at DESC
            LIMIT 200
            """,
            ghost_id,
        )
        profile_rows = await conn.fetch(
            """
            SELECT person_key, display_name
            FROM person_rolodex
            WHERE ghost_id = $1
              AND invalidated_at IS NULL
            ORDER BY last_seen DESC
            LIMIT 400
            """,
            ghost_id,
        )

    duplicates: list[dict[str, Any]] = []
    entries = [
        (str(r["person_key"] or ""), str(r["display_name"] or ""))
        for r in profile_rows
        if r["person_key"]
    ]
    for i in range(len(entries)):
        key_a, name_a = entries[i]
        norm_a = _normalized_name_for_dup(name_a)
        if not norm_a:
            continue
        for j in range(i + 1, len(entries)):
            key_b, name_b = entries[j]
            if key_a == key_b:
                continue
            norm_b = _normalized_name_for_dup(name_b)
            if not norm_b:
                continue
            ratio = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
            if ratio < 0.90:
                continue
            duplicates.append(
                {
                    "person_key_a": key_a,
                    "display_name_a": name_a,
                    "person_key_b": key_b,
                    "display_name_b": name_b,
                    "similarity": float(f"{ratio:.3f}"),
                }
            )
            if len(duplicates) >= 80:
                break
        if len(duplicates) >= 80:
            break

    return {
        "ok": True,
        "ghost_id": ghost_id,
        "checked_at": time.time(),
        "counts": {
            "orphaned_facts": len(orphaned),
            "empty_profiles": len(empty_profiles),
            "stale_bindings": len(stale_bindings),
            "duplicate_profiles": len(duplicates),
        },
        "samples": {
            "orphaned_facts": (
                [
                    {
                        "person_key": str(r["person_key"] or ""),
                        "fact_type": str(r["fact_type"] or ""),
                        "fact_value": str(r["fact_value"] or ""),
                        "last_observed_at": r["last_observed_at"].timestamp() if r["last_observed_at"] else None,
                    }
                    for r in orphaned[:30]
                ]
                if include_samples
                else []
            ),
            "empty_profiles": (
                [
                    {
                        "person_key": str(r["person_key"] or ""),
                        "display_name": str(r["display_name"] or ""),
                        "last_seen": r["last_seen"].timestamp() if r["last_seen"] else None,
                    }
                    for r in empty_profiles[:30]
                ]
                if include_samples
                else []
            ),
            "stale_bindings": (
                [
                    {
                        "session_id": str(r["session_id"] or ""),
                        "person_key": str(r["person_key"] or ""),
                        "ended_at": r["ended_at"].timestamp() if r["ended_at"] else None,
                    }
                    for r in stale_bindings[:40]
                ]
                if include_samples
                else []
            ),
            "duplicate_profiles": duplicates[:40] if include_samples else [],
        },
    }
