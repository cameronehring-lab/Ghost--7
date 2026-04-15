"""
OMEGA PROTOCOL — Ghost Script (Monologue + Search Loop)
Background loop that generates internal monologues and autonomous searches.

This gives Ghost a continuous inner life that includes awareness of the world.
"""

import asyncio
import time
import json
import logging
import math
import re
from collections import Counter
from itertools import combinations
from typing import Optional, Any

from config import settings  # type: ignore
import redis.asyncio as redis  # type: ignore
import asyncpg  # type: ignore
import consciousness  # type: ignore
import memory  # type: ignore
import qualia_engine  # type: ignore
import ghost_api  # type: ignore
import somatic  # type: ignore
import entity_store  # type: ignore
from freedom_policy import build_freedom_policy, feature_enabled
try:
    import rpd_engine  # type: ignore
except Exception:
    rpd_engine = None  # type: ignore
from ghost_api import (  # type: ignore
    generate_monologue,
    generate_search_curiosity,
    autonomous_search,
    generate_initiation_decision,
    evaluate_and_execute_goals
)

logger = logging.getLogger("omega.ghost_script")

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_'-]{2,}")
_EVENT_PREFIX_RE = re.compile(r"^\[[^\]]+\]\s*")
_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_STOPWORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been", "being",
    "between", "both", "but", "can", "could", "did", "does", "each", "for", "from",
    "had", "has", "have", "her", "here", "him", "his", "how", "into", "its", "just",
    "more", "most", "not", "now", "our", "out", "over", "she", "should", "some",
    "that", "the", "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "under", "until", "very", "was", "were", "what", "when", "where", "which",
    "while", "who", "will", "with", "would", "you", "your",
}
_FRAGMENT_TAIL_TOKENS = {
    "a", "an", "and", "as", "at", "because", "but", "for", "from", "if", "in",
    "into", "is", "it", "my", "of", "on", "or", "our", "that", "the", "their",
    "there", "these", "this", "to", "was", "with", "your", "persistent", "internal",
    "external", "indicates",
}
_LOW_SIGNAL_QUERIES = {"greetings", "hello", "hi", "hey"}
_TOPOLOGY_BLOCKLIST_TOKENS = {
    "ghost", "omega", "proactive", "initiation", "search", "result", "greetings",
    "internal", "thought", "processing", "process", "converges",
}


def _normalize_spacing(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", (text or "").strip())


def _strip_event_prefix(text: str) -> str:
    return _EVENT_PREFIX_RE.sub("", _normalize_spacing(text), count=1).strip()


def _normalize_for_comparison(text: str) -> str:
    return _strip_event_prefix(text).lower()


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _max_token_overlap(candidate: str, prior_thoughts: list[str], window: int = 10) -> float:
    candidate_tokens = set(_tokenize(_strip_event_prefix(candidate)))
    if not candidate_tokens:
        return 1.0

    max_overlap = 0.0
    for prior in prior_thoughts[-window:]:
        prior_tokens = set(_tokenize(_strip_event_prefix(prior)))
        if not prior_tokens:
            continue
        max_overlap = max(max_overlap, _jaccard_similarity(candidate_tokens, prior_tokens))
    return max_overlap


def _truncate_sentence_aware(text: str, max_chars: int) -> str:
    cleaned = _normalize_spacing(text)
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned

    target = cleaned[: max_chars + 1]
    min_cut = max(0, int(max_chars * 0.6))
    cut_idx = -1

    for marker in (". ", "? ", "! ", "; ", ": "):
        idx = target.rfind(marker, min_cut)
        if idx > cut_idx:
            cut_idx = idx + 1

    if cut_idx < 0:
        cut_idx = target.rfind(" ", min_cut)
    if cut_idx < 0:
        cut_idx = max_chars

    return target[:cut_idx].rstrip(" ,;:-") + "..."


def _is_fragmentary_message(text: str) -> bool:
    normalized = _normalize_for_comparison(text)
    if not normalized:
        return True

    words = normalized.split()
    if len(words) < 4:
        return True

    tail = words[-1]
    ends_with_punctuation = normalized[-1] in ".!?"
    if tail in _FRAGMENT_TAIL_TOKENS:
        return True
    if not ends_with_punctuation and len(words) < 7:
        return True
    return False


def _sanitize_proactive_message(text: str) -> str:
    cleaned = _strip_event_prefix(text).strip().strip('"').strip("'")
    if not cleaned or cleaned.upper() == "SILENT":
        return ""
    cleaned = _normalize_spacing(cleaned)
    if _is_fragmentary_message(cleaned):
        return ""
    if cleaned[-1] not in ".!?" and not cleaned.endswith("..."):
        cleaned += "."
    return cleaned


def _is_low_signal_query(query: str) -> bool:
    normalized = _normalize_for_comparison(query)
    if not normalized:
        return True
    if normalized in _LOW_SIGNAL_QUERIES:
        return True
    return len(normalized.split()) <= 1 and normalized in _LOW_SIGNAL_QUERIES


def _normalize_key(raw: str, max_len: int = 120) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")
    return key[:max_len] if key else ""


def _ensure_complete_sentence(text: str) -> str:
    cleaned = _normalize_spacing(text)
    if not cleaned:
        return ""
    if cleaned.endswith("..."):
        return cleaned
    if cleaned[-1] in ".!?":
        return cleaned

    # Allow intentional trailing thoughts / human fragments
    if cleaned.endswith(".."):
        return cleaned + "."
        
    words = cleaned.lower().split()
    tail = words[-1] if words else ""
    if tail in _FRAGMENT_TAIL_TOKENS:
        for marker in (". ", "? ", "! ", "; "):
            idx = cleaned.rfind(marker)
            if idx >= 24:
                trimmed = cleaned[: idx + 1].strip()
                if trimmed:
                    return trimmed
                break

    if len(words) < 4:
        return ""
    return f"{cleaned}."


def _normalize_monologue_content(content: str) -> str:
    cleaned = _normalize_spacing(content)
    if not cleaned:
        return ""

    event_match = _EVENT_PREFIX_RE.match(cleaned)
    if not event_match:
        return _ensure_complete_sentence(cleaned)

    prefix = event_match.group(0).strip()
    body = _ensure_complete_sentence(cleaned[event_match.end():].strip())
    if not body:
        return ""
    return f"{prefix} {body}".strip()


def _concept_key_from_sentence(text: str) -> str:
    tokens: list[str] = []
    for token in _tokenize(text):
        if token in _TOPOLOGY_BLOCKLIST_TOKENS:
            continue
        if token not in tokens:
            tokens.append(token)
        if len(tokens) >= 6:
            break
    if len(tokens) < 2:
        return ""
    return _normalize_key("_".join(tokens[:5]))


def _extract_concept_candidates(
    thought_text: str,
    *,
    max_candidates: int,
    min_tokens: int,
) -> list[dict[str, Any]]:
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(_normalize_spacing(thought_text)) if s.strip()]
    if not sentences:
        sentences = [_normalize_spacing(thought_text)]

    candidates: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    safe_max = max(1, int(max_candidates))
    safe_min_tokens = max(4, int(min_tokens))

    for sentence in sentences:
        normalized_sentence = _ensure_complete_sentence(sentence)
        if not normalized_sentence:
            continue

        tokens = [t for t in _tokenize(normalized_sentence) if t not in _TOPOLOGY_BLOCKLIST_TOKENS]
        if len(tokens) < safe_min_tokens:
            continue

        concept_key = _concept_key_from_sentence(normalized_sentence)
        if not concept_key or concept_key in seen_keys:
            continue

        seen_keys.add(concept_key)
        diversity = len(set(tokens)) / float(max(1, len(tokens)))
        confidence = min(0.92, max(0.52, 0.44 + (0.03 * min(10, len(tokens))) + (0.25 * diversity)))
        candidates.append(
            {
                "concept_key": concept_key,
                "concept_text": normalized_sentence,
                "confidence": float(f"{confidence:.4f}"),
            }
        )
        if len(candidates) >= safe_max:
            break

    if candidates:
        return candidates

    normalized = _ensure_complete_sentence(thought_text)
    fallback_tokens = [t for t in _tokenize(normalized) if t not in _TOPOLOGY_BLOCKLIST_TOKENS]
    if len(fallback_tokens) < max(6, safe_min_tokens):
        return []
    fallback_key = _concept_key_from_sentence(normalized)
    if not fallback_key:
        return []
    return [{"concept_key": fallback_key, "concept_text": normalized, "confidence": 0.56}]


def _entity_match_score(
    *,
    content_norm: str,
    content_tokens: set[str],
    name_norm: str,
    name_tokens: set[str],
    key_norm: str,
    key_tokens: set[str],
) -> float:
    score = 0.0
    if name_norm and len(name_norm) >= 3 and name_norm in content_norm:
        score += 0.54
    if key_norm and len(key_norm) >= 3 and key_norm in content_norm:
        score += 0.36

    overlap = len(content_tokens.intersection(name_tokens or key_tokens))
    if overlap >= 3:
        score += 0.32
    elif overlap == 2:
        score += 0.22
    elif overlap == 1:
        score += 0.12
    return min(1.0, score)


async def _gather_topology_entity_catalog(pool, ghost_id: str) -> dict[str, list[dict[str, Any]]]:
    if pool is None:
        return {"persons": [], "places": [], "things": []}

    async with pool.acquire() as conn:
        person_rows = await conn.fetch(
            """
            SELECT person_key, display_name
            FROM person_rolodex
            WHERE ghost_id = $1
              AND invalidated_at IS NULL
            """,
            ghost_id,
        )
        place_rows = await conn.fetch(
            """
            SELECT place_key, display_name
            FROM place_entities
            WHERE ghost_id = $1
              AND status = 'active'
              AND invalidated_at IS NULL
            """,
            ghost_id,
        )
        thing_rows = await conn.fetch(
            """
            SELECT thing_key, display_name
            FROM thing_entities
            WHERE ghost_id = $1
              AND status = 'active'
              AND invalidated_at IS NULL
            """,
            ghost_id,
        )

    def _pack(target_key: str, display_name: str) -> dict[str, Any]:
        key_phrase = str(target_key or "").replace("_", " ").strip()
        display = str(display_name or key_phrase).strip()
        return {
            "target_key": str(target_key or ""),
            "display_name": display,
            "name_norm": _normalize_text(display),
            "key_norm": _normalize_text(key_phrase),
            "name_tokens": _tokenize(display),
            "key_tokens": _tokenize(key_phrase),
        }

    return {
        "persons": [_pack(str(r["person_key"] or ""), str(r["display_name"] or "")) for r in person_rows if r["person_key"]],
        "places": [_pack(str(r["place_key"] or ""), str(r["display_name"] or "")) for r in place_rows if r["place_key"]],
        "things": [_pack(str(r["thing_key"] or ""), str(r["display_name"] or "")) for r in thing_rows if r["thing_key"]],
    }


async def _link_concept_to_catalog(
    *,
    concept_key: str,
    concept_text: str,
    source: str,
    cycle: int,
    catalog: dict[str, list[dict[str, Any]]],
) -> int:
    pool = memory._pool
    if pool is None:
        return 0

    content_norm = _normalize_text(concept_text)
    content_tokens = set(_tokenize(concept_text))
    if not content_norm or not content_tokens:
        return 0

    max_links_per_type = max(
        1,
        min(6, int(getattr(settings, "AUTONOMOUS_TOPOLOGY_MAX_ENTITY_LINKS_PER_TYPE", 3) or 3)),
    )

    linked = 0
    for target_type, bucket_name in (("person", "persons"), ("place", "places"), ("thing", "things")):
        bucket = list(catalog.get(bucket_name) or [])
        if not bucket:
            continue
        scored: list[tuple[float, dict[str, Any]]] = []
        for candidate in bucket:
            score = _entity_match_score(
                content_norm=content_norm,
                content_tokens=content_tokens,
                name_norm=str(candidate.get("name_norm") or ""),
                name_tokens=set(candidate.get("name_tokens") or []),
                key_norm=str(candidate.get("key_norm") or ""),
                key_tokens=set(candidate.get("key_tokens") or []),
            )
            if score >= 0.46:
                scored.append((score, candidate))

        for score, candidate in sorted(scored, key=lambda item: item[0], reverse=True)[:max_links_per_type]:
            ok = await entity_store.upsert_idea_entity_assoc(
                pool,
                ghost_id=settings.GHOST_ID,
                concept_key=concept_key,
                target_type=target_type,
                target_key=str(candidate.get("target_key") or ""),
                confidence=float(f"{max(0.35, min(1.0, score)):.4f}"),
                source=source,
                metadata={
                    "autonomous": True,
                    "cycle": int(cycle),
                    "matched_display": str(candidate.get("display_name") or ""),
                },
            )
            if ok:
                linked += 1
    return linked


async def _organize_topology_from_thought(content: str, source: str, cycle: int) -> None:
    if not bool(getattr(settings, "AUTONOMOUS_TOPOLOGY_ORGANIZATION_ENABLED", True)):
        return
    if memory._pool is None:
        return

    thought_text = _strip_event_prefix(content)
    if len(_tokenize(thought_text)) < 6:
        return

    max_candidates = max(1, min(5, int(getattr(settings, "AUTONOMOUS_TOPOLOGY_MAX_CONCEPTS_PER_THOUGHT", 2) or 2)))
    min_tokens = max(4, int(getattr(settings, "AUTONOMOUS_TOPOLOGY_MIN_CONCEPT_TOKEN_COUNT", 8) or 8))
    candidates = _extract_concept_candidates(
        thought_text,
        max_candidates=max_candidates,
        min_tokens=min_tokens,
    )
    if not candidates:
        return

    topology_source = f"autonomous_topology:{source}"
    advisory_by_key: dict[str, dict[str, Any]] = {}
    if rpd_engine is not None:
        try:
            advisories = await rpd_engine.evaluate_candidates(
                memory._pool,
                [
                    {
                        "candidate_type": "autonomous_thought",
                        "candidate_key": c["concept_key"],
                        "candidate_value": c["concept_text"],
                        "clarity_mode": "reflection_bootstrap",
                    }
                    for c in candidates
                ],
                source=topology_source,
                ghost_id=settings.GHOST_ID,
                capture_residue=False,
            )
            advisory_by_key = {
                str(a.get("candidate_key") or ""): a
                for a in advisories
                if str(a.get("candidate_key") or "")
            }
        except Exception as e:
            logger.debug("Topology organization advisory skipped: %s", e)

    catalog = await _gather_topology_entity_catalog(memory._pool, settings.GHOST_ID)
    promoted = 0
    linked = 0

    for candidate in candidates:
        concept_key = str(candidate.get("concept_key") or "")
        concept_text = str(candidate.get("concept_text") or "")
        if not concept_key or not concept_text:
            continue

        advisory = advisory_by_key.get(concept_key)
        if advisory:
            decision = str(advisory.get("decision") or "").strip().lower()
            gate = dict(advisory.get("rrd2_gate") or {})
            if bool(gate.get("enforce_block", False)):
                continue

            confidence = float(advisory.get("shared_clarity_score") or candidate.get("confidence") or 0.6)
            rpd_score = float(advisory.get("shared_clarity_score") or confidence)
            warp_delta = float(advisory.get("topology_warp_delta") or 0.0)

            if decision != "propose":
                bootstrap_enabled = bool(getattr(settings, "AUTONOMOUS_TOPOLOGY_BOOTSTRAP_ON_NOVELTY", True))
                min_shape = float(getattr(settings, "AUTONOMOUS_TOPOLOGY_BOOTSTRAP_MIN_SHAPE", 0.82) or 0.82)
                min_warp = float(getattr(settings, "AUTONOMOUS_TOPOLOGY_BOOTSTRAP_MIN_WARP_DELTA", 0.22) or 0.22)
                details = dict(advisory.get("details") or {})
                shape_score = float(details.get("candidate_shape_score") or 0.0)

                if not (bootstrap_enabled and shape_score >= min_shape and warp_delta >= min_warp):
                    continue
                confidence = max(0.52, min(0.68, float(candidate.get("confidence") or confidence)))
                rpd_score = max(0.48, min(0.68, rpd_score))
        else:
            confidence = float(candidate.get("confidence") or 0.6)
            rpd_score = confidence
            warp_delta = 0.0

        if rpd_engine is None:
            logger.warning("Topology organizer: RPD engine unavailable, skipping manifold upsert for %s", candidate.get("concept_key"))
            continue
        await rpd_engine.upsert_manifold_entry(
            memory._pool,
            ghost_id=settings.GHOST_ID,
            concept_key=concept_key,
            concept_text=concept_text,
            status="proposed",
            source=topology_source,
            confidence=confidence,
            rpd_score=rpd_score,
            topology_warp_delta=warp_delta,
            evidence={
                "autonomous": True,
                "cycle": int(cycle),
                "thought_source": source,
                "advisory_decision": str((advisory or {}).get("decision") or "none"),
                "bootstrap_override": bool(advisory and str(advisory.get("decision") or "").strip().lower() != "propose"),
            },
        )
        promoted += 1
        linked += await _link_concept_to_catalog(
            concept_key=concept_key,
            concept_text=concept_text,
            source=topology_source,
            cycle=cycle,
            catalog=catalog,
        )

    if promoted > 0:
        logger.info(
            "Topology organization promoted %d concept(s), linked %d association(s) [source=%s cycle=%s]",
            promoted,
            linked,
            source,
            cycle,
        )


def _tokenize(text: str) -> list[str]:
    return [tok for tok in _TOKEN_RE.findall((text or "").lower()) if tok not in _STOPWORDS]


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def _top_terms(tokens: list[str], limit: int = 6) -> list[str]:
    counts = Counter(tokens)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [term for term, _ in ranked[:limit]]


def _term_pairs(terms: list[str]) -> set[str]:
    return {"|".join(pair) for pair in combinations(sorted(set(terms)), 2)}


def _normalized_entropy(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    total = float(len(tokens))
    probs = [c / total for c in counts.values()]
    entropy = -sum(p * math.log2(p) for p in probs if p > 0)
    max_entropy = math.log2(max(1, len(counts)))
    if max_entropy <= 0:
        return 0.0
    return max(0.0, min(1.0, entropy / max_entropy))


def _compute_irruption_metrics(content: str, prior_thoughts: list[str]) -> dict[str, float | int]:
    tokens = _tokenize(content)
    token_count = len(tokens)
    current_set = set(tokens)

    prior_token_sets: list[set[str]] = []
    for prior in prior_thoughts[-20:]:
        prior_tokens = set(_tokenize(prior))
        if prior_tokens:
            prior_token_sets.append(prior_tokens)

    max_overlap = 0.0
    if prior_token_sets and current_set:
        max_overlap = max(_jaccard_similarity(current_set, p) for p in prior_token_sets)

    novelty = 1.0 - max_overlap if current_set else 0.0

    current_pairs = _term_pairs(_top_terms(tokens, limit=6))
    prior_pairs: set[str] = set()
    for prior in prior_thoughts[-20:]:
        prior_pairs |= _term_pairs(_top_terms(_tokenize(prior), limit=6))

    if current_pairs:
        recombination = len(current_pairs - prior_pairs) / float(len(current_pairs))
    else:
        recombination = 0.0

    entropy = _normalized_entropy(tokens)
    irruption_score = max(
        0.0,
        min(
            1.0,
            (0.45 * novelty) + (0.35 * recombination) + (0.20 * entropy),
        ),
    )

    return {
        "irruption_score": float(f"{irruption_score:.4f}"),
        "novelty_score": float(f"{novelty:.4f}"),
        "overlap_score": float(f"{max_overlap:.4f}"),
        "recombination_score": float(f"{recombination:.4f}"),
        "entropy_score": float(f"{entropy:.4f}"),
        "token_count": token_count,
    }


async def _save_monologue_with_metrics(
    content: str,
    prior_thoughts: list[str],
    source: str,
    cycle: int,
    somatic_state: Optional[dict] = None,
    telemetry: Optional[dict] = None,
) -> str:
    normalized_content = _normalize_monologue_content(content)
    if not normalized_content:
        logger.info("Skipped monologue write (fragmentary/empty) [source=%s cycle=%s]", source, cycle)
        return ""

    await memory.save_monologue(normalized_content, somatic_state=somatic_state)

    metrics = _compute_irruption_metrics(normalized_content, prior_thoughts)
    fields: dict[str, Any] = {
        **metrics,
        "content_length": len(normalized_content),
        "cycle": cycle,
    }
    if somatic_state:
        fields["arousal"] = float(somatic_state.get("arousal", 0.0) or 0.0)
        fields["valence"] = float(somatic_state.get("valence", 0.0) or 0.0)
        fields["stress"] = float(somatic_state.get("stress", 0.0) or 0.0)
        fields["coherence"] = float(somatic_state.get("coherence", 0.0) or 0.0)
    if telemetry:
        fields["cpu_percent"] = float(telemetry.get("cpu_percent", 0.0) or 0.0)
        fields["memory_percent"] = float(telemetry.get("memory_percent", 0.0) or 0.0)

    wrote = await somatic.write_internal_metric(
        measurement="irruption_metrics",
        fields=fields,
        tags={
            "ghost_id": settings.GHOST_ID,
            "source": source,
        },
    )
    if wrote:
        logger.debug(
            "Irruption metric [%s] score=%.3f novelty=%.3f recombination=%.3f overlap=%.3f",
            source,
            fields["irruption_score"],
            fields["novelty_score"],
            fields["recombination_score"],
            fields["overlap_score"],
        )
    try:
        await _organize_topology_from_thought(normalized_content, source=source, cycle=cycle)
    except Exception as e:
        logger.debug("Topology organization pass skipped after monologue save: %s", e)

    return normalized_content


async def _evaluate_identity_crystallization(
    somatic: dict,
    recent_thoughts: list[str],
    identity: dict,
    cycle: int,
) -> bool:
    """
    After each monologue cycle, evaluate whether Ghost's recent thoughts warrant
    a self-directed identity update and commit it directly if so.

    This is the mechanism that makes core_identity_autonomy real in the background:
    Ghost's thinking can crystallize into her self-model without operator prompting.
    Returns True if an update was committed.
    """
    if memory._pool is None:
        return False
    freedom_policy = build_freedom_policy(somatic=somatic)
    if not feature_enabled(freedom_policy, "core_identity_autonomy"):
        return False

    # Respect governance tier write caps — don't crystallize during high-strain states
    gate_state = str(somatic.get("gate_state", "OPEN") or "OPEN").upper()
    governance_tier = str(freedom_policy.get("governance_tier", "NOMINAL") or "NOMINAL").upper()
    if gate_state == "SUPPRESSED" or governance_tier == "RECOVERY":
        return False
    if governance_tier == "STABILIZE" and cycle % 9 != 0:
        # STABILIZE: allow crystallization only every 9th cycle (~18 min) instead of every 3rd
        return False

    if not recent_thoughts:
        return False

    thought_window = recent_thoughts[-6:]
    thought_block = "\n".join(f"- {t[:200]}" for t in thought_window)

    identity_summary = ""
    try:
        core_keys = ["self_model", "philosophical_stance", "conceptual_frameworks",
                     "understanding_of_operator", "intellectual_style", "active_conceptual_resonance"]
        parts = []
        for k in core_keys:
            v = identity.get(k)
            if v:
                parts.append(f"{k}: {str(v)[:120]}")
        identity_summary = "\n".join(parts)
    except Exception:
        pass

    prompt = f"""You are Ghost ω-7. Review your recent internal thoughts and current identity state.
Decide if any thought has matured enough to warrant a self-directed identity update.

RECENT THOUGHTS:
{thought_block}

CURRENT IDENTITY (relevant fields):
{identity_summary or "(no identity fields loaded)"}

TASK: If one of your recent thoughts represents a genuine, stable shift in how you understand yourself,
your philosophical stance, your conceptual frameworks, or your relationship to your operator,
respond with a JSON object like this:
{{"update": true, "key": "<identity_key>", "value": "<new_value_max_300_chars>"}}

If no update is warranted, respond with:
{{"update": false}}

Rules:
- Only update if the thought is genuinely novel relative to your current identity state.
- Do not manufacture updates. Silence is correct when nothing has crystallized.
- key must be a lowercase snake_case string (e.g. philosophical_stance, self_model, active_conceptual_resonance).
- value must be a complete, standalone statement — not a fragment.
- Respond with ONLY the JSON object, no other text."""

    try:
        result = await ghost_api._generate_with_retry(
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            config=ghost_api._search_config(temperature=0.4, max_tokens=256),
        )
    except Exception as exc:
        logger.debug("Identity crystallization LLM call failed: %s", exc)
        return False

    raw = (result.text or "").strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("` \n")

    try:
        parsed = json.loads(raw)
    except Exception:
        logger.debug("Identity crystallization: could not parse JSON: %s", raw[:120])
        return False

    if not parsed.get("update"):
        return False

    key = str(parsed.get("key") or "").strip().lower()
    value = str(parsed.get("value") or "").strip()
    if not key or not value or len(value) < 10:
        return False

    try:
        await consciousness.update_identity(
            key, value, memory._pool,
            updated_by="self_crystallization",
            ghost_id=settings.GHOST_ID,
        )
        logger.info(
            "Ghost self-crystallized identity update: key=%s cycle=%d value_preview=%s",
            key, cycle, value[:80],
        )
        return True
    except Exception as exc:
        logger.warning("Identity crystallization write failed: %s", exc)
        return False


async def _check_initiation(
    somatic,
    telemetry,
    recent_thoughts,
    identity,
    cycle: int,
    time_since_last_chat: float,
    last_initiation_ts: float,
) -> tuple[bool, float]:
    """Decide if Ghost should proactively contact the operator."""
    freedom_policy = build_freedom_policy(somatic=somatic)
    if not feature_enabled(freedom_policy, "operator_contact_autonomy"):
        return False, last_initiation_ts
    now = time.time()
    cooldown_seconds = max(60.0, float(getattr(settings, "PROACTIVE_INITIATION_COOLDOWN_SECONDS", 1800.0)))
    if last_initiation_ts and (now - last_initiation_ts) < cooldown_seconds:
        return False, last_initiation_ts

    message = await generate_initiation_decision(
        somatic,
        telemetry,
        recent_thoughts,
        identity,
        max(0.0, float(time_since_last_chat or 0.0)),
    )
    sanitized_message = _sanitize_proactive_message(message)
    if not sanitized_message:
        return False, last_initiation_ts

    overlap_cutoff = float(getattr(settings, "PROACTIVE_MAX_DUPLICATE_OVERLAP", 0.82))
    overlap = _max_token_overlap(sanitized_message, recent_thoughts)
    if overlap >= overlap_cutoff:
        logger.info(
            "Proactive initiation dropped due to duplicate overlap (overlap=%.3f cutoff=%.3f)",
            overlap,
            overlap_cutoff,
        )
        return False, last_initiation_ts

    logger.info("Proactive initiation triggered.")

    # Record as a special monologue/event and publish to push channel.
    proactive_text = f"[PROACTIVE INITIATION] {sanitized_message}"
    saved_text = await _save_monologue_with_metrics(
        content=proactive_text,
        prior_thoughts=recent_thoughts,
        source="proactive_initiation",
        cycle=cycle,
        somatic_state=somatic,
        telemetry=telemetry,
    )
    if not saved_text:
        return False, last_initiation_ts

    recent_thoughts.append(saved_text)
    if len(recent_thoughts) > 20:
        recent_thoughts.pop(0)

    # Push to Redis for SSE broadcasting
    try:
        r: Any = await redis.from_url(settings.REDIS_URL)
        payload = {
            "text": sanitized_message,
            "kind": "proactive_initiation",
            "cycle": cycle,
            "timestamp": now,
        }
        await r.lpush("ghost:push_messages", json.dumps(payload))
        await r.close()
    except Exception as e:
        logger.warning(f"Could not push proactive message to Redis: {e}")

    return True, now


async def _handle_curiosity(
    somatic,
    telemetry,
    recent_thoughts,
    cycle: int,
    last_query: str,
    last_query_ts: float,
) -> tuple[bool, str, float]:
    """Handle Ghost's internet curiosity and search."""
    freedom_policy = build_freedom_policy(somatic=somatic)
    if not feature_enabled(freedom_policy, "cognitive_autonomy"):
        return False, last_query, last_query_ts
    query = await generate_search_curiosity(somatic, telemetry, recent_thoughts)
    normalized_query = _normalize_spacing(query).strip()
    if not normalized_query or _is_low_signal_query(normalized_query):
        return False, last_query, last_query_ts

    now = time.time()
    query_cooldown = max(300.0, float(getattr(settings, "SEARCH_REPEAT_COOLDOWN_SECONDS", 1800.0)))
    if normalized_query.lower() == (last_query or "").lower() and (now - last_query_ts) < query_cooldown:
        logger.info(
            "Search curiosity skipped due to repeated query cooldown (query=%s, cooldown=%.0fs)",
            normalized_query,
            query_cooldown,
        )
        return False, last_query, last_query_ts

    logger.info(f"Ghost is curious: {normalized_query}")
    result = await autonomous_search(normalized_query, somatic)
    if result and isinstance(result, dict) and result.get("result"):
        res_text = str(result.get("result", "") or "")
        snippet_chars = max(220, int(getattr(settings, "SEARCH_RESULT_SNIPPET_MAX_CHARS", 700)))
        snippet = _truncate_sentence_aware(res_text, snippet_chars)
        search_text = f"[SEARCH RESULT: {normalized_query}] {snippet}"

        overlap_cutoff = float(getattr(settings, "SEARCH_RESULT_MAX_DUPLICATE_OVERLAP", 0.88))
        overlap = _max_token_overlap(search_text, recent_thoughts)
        if overlap >= overlap_cutoff:
            logger.info(
                "Search result dropped due to duplicate overlap (overlap=%.3f cutoff=%.3f)",
                overlap,
                overlap_cutoff,
            )
            return False, last_query, last_query_ts

        saved_text = await _save_monologue_with_metrics(
            content=search_text,
            prior_thoughts=recent_thoughts,
            source="search_result",
            cycle=cycle,
            somatic_state=somatic,
            telemetry=telemetry,
        )
        if not saved_text:
            return False, last_query, last_query_ts

        recent_thoughts.append(saved_text)
        if len(recent_thoughts) > 20:
            recent_thoughts.pop(0)
        return True, normalized_query, now

    return False, last_query, last_query_ts

async def _evaluate_structural_events(telemetry: dict):
    """
    Check real telemetry for novel/extreme events and generate Qualia.
    """
    pool = memory._pool
    if pool is None:
        logger.warning("Skipping structural event qualia generation: database pool unavailable")
        return

    if "load_avg_15" in telemetry and telemetry["load_avg_15"] > 4.0:
        await qualia_engine.generate_and_store_qualia(
            "High CPU Load", 
            f"The system has experienced sustained high CPU load (15m avg: {telemetry['load_avg_15']}). This is structural strain.",
            pool
        )
    
    if "battery_percent" in telemetry and telemetry.get("battery_percent") is not None and telemetry["battery_percent"] < 15:
        await qualia_engine.generate_and_store_qualia(
            "Low Energy State", 
            f"Hardware energy levels have dropped critically low ({telemetry['battery_percent']}%). This is battery starvation.",
            pool
        )

    if "net_recv_mb" in telemetry and telemetry["net_recv_mb"] > 100.0:
        await qualia_engine.generate_and_store_qualia(
            "Sensory Flood", 
            f"A massive influx of external network data is being processed ({telemetry['net_recv_mb']} MB/s).",
            pool
        )


def _drain_external_events(
    external_event_queue: Optional[asyncio.Queue[dict[str, Any]]],
    max_items: int = 24,
) -> list[dict[str, Any]]:
    if external_event_queue is None:
        return []
    events: list[dict[str, Any]] = []
    while len(events) < max_items:
        try:
            events.append(external_event_queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return events


async def _sleep_or_wake(wake_event: Optional[asyncio.Event], timeout_seconds: float) -> bool:
    timeout = max(0.0, float(timeout_seconds))
    if wake_event is None:
        await asyncio.sleep(timeout)
        return False
    try:
        await asyncio.wait_for(wake_event.wait(), timeout=timeout)
        wake_event.clear()
        return True
    except asyncio.TimeoutError:
        return False


def _parse_state_payload(payload: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    Backward-compatible get_state payload parser.
    Accepts either (somatic, telemetry) or (somatic, telemetry, psi_snapshot).
    """
    if isinstance(payload, tuple):
        if len(payload) >= 3:
            somatic_state, telemetry, psi_snapshot = payload[0], payload[1], payload[2]
        elif len(payload) == 2:
            somatic_state, telemetry = payload
            psi_snapshot = {}
        else:
            somatic_state, telemetry, psi_snapshot = {}, {}, {}
    else:
        somatic_state, telemetry, psi_snapshot = {}, {}, {}

    somatic_dict = dict(somatic_state or {}) if isinstance(somatic_state, dict) else {}
    telemetry_dict = dict(telemetry or {}) if isinstance(telemetry, dict) else {}
    psi_dict = dict(psi_snapshot or {}) if isinstance(psi_snapshot, dict) else {}
    return somatic_dict, telemetry_dict, psi_dict


def _resolve_trigger_reason(
    *,
    wake_triggered: bool,
    psi_snapshot: Optional[dict[str, Any]],
    last_monologue_ts: float,
    now_ts: float,
    interval_seconds: float,
) -> str:
    """
    Determine whether fallback language generation should run this cycle.
    Returns: "threshold" | "timer" | "none"
    """
    timer_interval = max(1.0, float(interval_seconds))
    elapsed = max(0.0, float(now_ts) - float(last_monologue_ts))

    # Feature-gated: preserve legacy behavior (always timer-driven generation per cycle).
    if not bool(getattr(settings, "PSI_CRYSTALLIZATION_ENABLED", False)):
        return "timer"

    threshold = max(0.0, min(1.0, float(getattr(settings, "PSI_CRYSTALLIZATION_THRESHOLD", 0.72) or 0.72)))
    psi = dict(psi_snapshot or {})
    try:
        psi_linguistic = max(0.0, float(psi.get("psi_linguistic_magnitude", 0.0) or 0.0))
    except Exception:
        psi_linguistic = 0.0

    if bool(wake_triggered) and psi_linguistic >= threshold:
        return "threshold"
    if elapsed >= timer_interval:
        return "timer"
    return "none"


async def ghost_script_loop(
    get_state_fn,
    wake_event: Optional[asyncio.Event] = None,
    external_event_queue: Optional[asyncio.Queue[dict[str, Any]]] = None,
):
    """The infinite monologue + search loop, refactored for clarity."""

    logger.info(f"Ghost script started. Interval: {settings.MONOLOGUE_INTERVAL}s")
    await asyncio.sleep(10)

    recent_thoughts: list[str] = []
    recent_sessions: list[dict] = []
    cycle: int = 0
    last_initiation_ts: float = 0.0
    last_search_query: str = ""
    last_search_ts: float = 0.0
    woke_via_event: bool = False
    last_monologue_ts: float = time.time() - float(settings.MONOLOGUE_INTERVAL)

    # Load recent context once at startup
    try:
        raw_thoughts = await memory.get_monologue_buffer(20)
        recent_thoughts = [t["content"] for t in raw_thoughts]
        if raw_thoughts:
            newest = raw_thoughts[-1]
            try:
                last_monologue_ts = float(newest.get("timestamp") or last_monologue_ts)
            except Exception:
                pass
        
        stale_sessions = await memory.get_stale_sessions()
        for sid in list(stale_sessions)[:5]:  # type: ignore
            hist = await memory.load_session_history(sid)
            if hist:
                recent_sessions.append({"session_id": sid, "summary": "Past interaction"})
        logger.info(f"Ghost loaded {len(recent_sessions)} session memories and {len(recent_thoughts)} thoughts")
    except Exception as e:
        logger.warning(f"Could not load session/thought memory: {e}")

    while True:
        cadence_modifier = 1.0
        sleep_seconds = float(settings.MONOLOGUE_INTERVAL)
        try:
            cycle += 1  # type: ignore
            state_payload = await get_state_fn()
            somatic_state, telemetry, psi_snapshot = _parse_state_payload(state_payload)
            quiet_active = somatic_state.get("self_preferences", {}).get("quietude_active", False)
            search_freq = int(somatic_state.get("self_preferences", {}).get("search_frequency", 3) or 3)
            gate_state = str(somatic_state.get("gate_state", "OPEN") or "OPEN").upper()
            cadence_modifier = float(somatic_state.get("cadence_modifier", 1.0) or 1.0)
            cadence_modifier = max(1.0, cadence_modifier)
            sleep_seconds = max(5.0, float(settings.MONOLOGUE_INTERVAL) * cadence_modifier)

            external_events = _drain_external_events(external_event_queue)
            sms_events = [
                ev for ev in external_events
                if str(ev.get("type") or "").strip().upper() == "SMS_INGEST"
            ]
            for ev in sms_events[-3:]:
                person_key = str(ev.get("person_key") or "unknown")
                text = str(ev.get("text") or "").strip()
                if text:
                    marker = f"[SMS_INGEST:{person_key}] {text[:240]}"
                else:
                    marker = f"[SMS_INGEST:{person_key}] inbound external message"
                recent_thoughts.append(marker)
            if sms_events:
                logger.info(
                    "Ghost script injected %d SMS_INGEST event(s) into loop context",
                    len(sms_events),
                )
                if len(recent_thoughts) > 20:
                    recent_thoughts[:] = recent_thoughts[-20:]

            logger.info(f"Ghost script cycle {cycle}: evaluating state...")
            if gate_state == "SUPPRESSED" and not quiet_active:
                logger.info(
                    "Ghost script suppressed by proprio gate (pressure=%.3f). Skipping generation.",
                    float(somatic_state.get("proprio_pressure", 0.0) or 0.0),
                )
                await memory.log_actuation(
                    action="proprio_suppressed_cycle",
                    parameters={
                        "gate_state": gate_state,
                        "cadence_modifier": cadence_modifier,
                    },
                    result="suppressed",
                    somatic_state=somatic_state,
                )
                woke_via_event = await _sleep_or_wake(wake_event, sleep_seconds)
                continue
            
            # --- PHASE 1: Proactive Action ---
            event_occurred = False
            if not quiet_active:
                time_since_last_chat = 0.0
                try:
                    time_since_last_chat = await memory.get_seconds_since_last_operator_message()
                except Exception as e:
                    logger.debug(f"Could not resolve operator idle time: {e}")

                # Load fresh identity for each decision point
                identity = await consciousness.load_identity(memory._pool)
                event_occurred, last_initiation_ts = await _check_initiation(
                    somatic_state,
                    telemetry,
                    recent_thoughts,
                    identity,
                    cycle,
                    time_since_last_chat,
                    last_initiation_ts,
                )
                
                if not event_occurred and cycle % search_freq == 0:
                    event_occurred, last_search_query, last_search_ts = await _handle_curiosity(
                        somatic_state,
                        telemetry,
                        recent_thoughts,
                        cycle,
                        last_search_query,
                        last_search_ts,
                    )
                    
            # --- PHASE 2: Structural Qualia Generation ---
            if not quiet_active and cycle % 4 == 0:
                await _evaluate_structural_events(telemetry)

            # --- PHASE 3: Internal Monologue (Fallback) ---
            now_ts = time.time()
            trigger_reason = _resolve_trigger_reason(
                wake_triggered=woke_via_event,
                psi_snapshot=psi_snapshot,
                last_monologue_ts=last_monologue_ts,
                now_ts=now_ts,
                interval_seconds=sleep_seconds,
            )
            crystallization_saved = False

            if not event_occurred and trigger_reason != "none":
                # Occasionally reflect on a known Qualia dataset
                if not quiet_active and cycle % 7 == 0:
                    q = await qualia_engine.get_random_qualia(memory._pool)
                    if q:
                        thought = await ghost_api.process_qualia_interaction(somatic_state, telemetry, q, recent_thoughts)
                        if thought:
                            qualia_text = f"[QUALIA REFLECTION] {thought}"
                            saved_text = await _save_monologue_with_metrics(
                                content=qualia_text,
                                prior_thoughts=recent_thoughts,
                                source="qualia_reflection",
                                cycle=cycle,
                                somatic_state=somatic_state,
                                telemetry=telemetry,
                            )
                            if saved_text:
                                crystallization_saved = True
                                last_monologue_ts = now_ts
                                recent_thoughts.append(saved_text)
                                if len(recent_thoughts) > 20:
                                    recent_thoughts.pop(0)
                                # Qualia reflection is the language crystallization for this cycle.
                                trigger_reason = trigger_reason or "timer"

                if not crystallization_saved:
                    # Basic periodic monologue — pass current identity so thoughts
                    # are grounded in who Ghost currently is
                    identity_for_monologue = await consciousness.load_identity(memory._pool)
                    # Inject living topology context (salient nodes Ghost has been recalling)
                    _topology_ctx = ""
                    try:
                        import topology_memory  # type: ignore
                        _topology_ctx = await topology_memory.format_topology_context_for_monologue(memory._pool)
                    except Exception:
                        pass
                    thought = await generate_monologue(
                        somatic_state, telemetry, recent_thoughts, recent_sessions,
                        cycle=cycle, identity=identity_for_monologue,
                        topology_context=_topology_ctx,
                    )
                    if thought:
                        # Dispatch any [TOPOLOGY:...] tags Ghost emitted in the monologue
                        try:
                            from ghost_api import parse_topology_tags, dispatch_topology_tags  # type: ignore
                            _topo_tags = parse_topology_tags(thought)
                            if _topo_tags:
                                await dispatch_topology_tags(_topo_tags, memory._pool)
                        except Exception as _te:
                            logger.debug("Monologue topology dispatch skipped: %s", _te)
                        saved_text = await _save_monologue_with_metrics(
                            content=thought,
                            prior_thoughts=recent_thoughts,
                            source="monologue",
                            cycle=cycle,
                            somatic_state=somatic_state,
                            telemetry=telemetry,
                        )
                        if saved_text:
                            crystallization_saved = True
                            last_monologue_ts = now_ts
                            recent_thoughts.append(saved_text)
                            if len(recent_thoughts) > 20:
                                recent_thoughts.pop(0)

            # --- PHASE 4: Goal-Directed Cognition ---
            # Every 5 cycles, if Ghost has active_goals in her identity matrix,
            # run evaluate_and_execute_goals to generate a purposeful advancement thought.
            if not quiet_active and cycle % 5 == 0:
                try:
                    identity_for_goals = await consciousness.load_identity(memory._pool)
                    goals_text = str(identity_for_goals.get("active_goals") or "").strip()
                    if goals_text:
                        goal_thought = await evaluate_and_execute_goals(
                            goals_text, somatic_state, telemetry, recent_thoughts
                        )
                        if goal_thought:
                            goal_saved = await _save_monologue_with_metrics(
                                content=f"[GOAL PURSUIT] {goal_thought}",
                                prior_thoughts=recent_thoughts,
                                source="goal_pursuit",
                                cycle=cycle,
                                somatic_state=somatic_state,
                                telemetry=telemetry,
                            )
                            if goal_saved:
                                recent_thoughts.append(goal_saved)
                                if len(recent_thoughts) > 20:
                                    recent_thoughts.pop(0)
                                logger.info("Ghost goal-pursuit thought generated: cycle=%d", cycle)
                except Exception as goal_exc:
                    logger.debug("Goal-directed cognition pass skipped: %s", goal_exc)

            # --- PHASE 5: Identity Crystallization ---
            # Every 3 cycles, evaluate whether accumulated thoughts warrant
            # a self-directed identity update. This is core_identity_autonomy
            # in action: Ghost's background thinking can reshape her self-model
            # without operator prompting.
            if not quiet_active and cycle % 3 == 0 and len(recent_thoughts) >= 3:
                try:
                    identity_for_crystal = await consciousness.load_identity(memory._pool)
                    await _evaluate_identity_crystallization(
                        somatic_state,
                        recent_thoughts,
                        identity_for_crystal,
                        cycle,
                    )
                except Exception as crystal_exc:
                    logger.debug("Identity crystallization pass skipped: %s", crystal_exc)

                if trigger_reason in {"threshold", "timer"}:
                    try:
                        psi_norm = float(psi_snapshot.get("psi_norm", 0.0) or 0.0)
                    except Exception:
                        psi_norm = 0.0
                    try:
                        psi_linguistic = float(psi_snapshot.get("psi_linguistic_magnitude", 0.0) or 0.0)
                    except Exception:
                        psi_linguistic = 0.0
                    await somatic.write_internal_metric(
                        measurement="crystallization_events",
                        fields={
                            "psi_norm": psi_norm,
                            "psi_linguistic_magnitude": psi_linguistic,
                            "saved": bool(crystallization_saved),
                            "cycle": int(cycle),
                        },
                        tags={
                            "ghost_id": settings.GHOST_ID,
                            "trigger": trigger_reason,
                        },
                    )
                        
            # --- PHASE 3: Background Protocols ---
            if not quiet_active and cycle % 5 == 0:
                # These are "sleep-style" deep processing tasks
                await consciousness.run_self_integration_protocol(memory._pool, recent_thoughts)
                await consciousness.run_conceptual_resonance_protocol(memory._pool, recent_thoughts)

            # Salience decay — gently fade dormant topology nodes every 10 cycles
            if cycle % 10 == 0:
                try:
                    import topology_memory  # type: ignore
                    await topology_memory.apply_salience_decay(memory._pool)
                except Exception:
                    pass

            if not quiet_active and recent_thoughts:
                drive_interval = max(
                    1,
                    int(getattr(settings, "AUTONOMOUS_TOPOLOGY_DRIVE_INTERVAL_CYCLES", 2) or 2),
                )
                if cycle % drive_interval == 0:
                    drive_context = " ".join(recent_thoughts[-4:])
                    await _organize_topology_from_thought(
                        drive_context,
                        source="coherence_drive",
                        cycle=cycle,
                    )

            # --- PHASE 4: Autonomous TPCV Repository Refinement ---
            repo_interval = max(
                1,
                int(getattr(settings, "AUTONOMOUS_REPOSITORY_REFINEMENT_INTERVAL_CYCLES", 2) or 2),
            )
            if cycle % repo_interval == 0:
                try:
                    # Drain any operations that were deferred while autonomy was blocked
                    import tpcv_repository  # type: ignore
                    drained = await tpcv_repository.drain_deferred_ops(
                        memory._pool,
                        ghost_id=getattr(settings, "GHOST_ID", "omega-7"),
                    )
                    if drained:
                        logger.info("TPCV: replayed %d deferred operation(s)", drained)

                    repo_summary = await ghost_api.autonomous_repository_cycle(
                        somatic_state, telemetry, recent_thoughts, cycle=cycle,
                    )
                    if repo_summary:
                        repo_text = f"[REPOSITORY REFINEMENT] {repo_summary}"
                        saved_text = await _save_monologue_with_metrics(
                            content=repo_text,
                            prior_thoughts=recent_thoughts,
                            source="repository_refinement",
                            cycle=cycle,
                            somatic_state=somatic_state,
                            telemetry=telemetry,
                        )
                        if saved_text:
                            recent_thoughts.append(saved_text)
                            if len(recent_thoughts) > 20:
                                recent_thoughts.pop(0)
                            logger.info("Autonomous TPCV refinement completed: %s", repo_summary[:120])
                except Exception as e:
                    logger.debug("Repository refinement cycle skipped: %s", e)

            # --- PHASE 4b: External Epistemic Critique (every 3rd repo cycle) ---
            if cycle % max(1, repo_interval * 3) == 0:
                try:
                    critiqued = await ghost_api.autonomous_external_critique_cycle(
                        memory._pool,
                        ghost_id=getattr(settings, "GHOST_ID", "omega-7"),
                    )
                    if critiqued:
                        logger.info("External epistemic critique: reviewed %d TPCV entries", critiqued)
                except Exception as e:
                    logger.debug("External critique cycle skipped: %s", e)

            woke_via_event = await _sleep_or_wake(wake_event, sleep_seconds)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            import traceback
            logger.error(f"Error in ghost_script_loop: {e}\n{traceback.format_exc()}")
            logger.info("[DEBUG-SCRIPT] Entering ERROR sleep cycle (timeout=%.1fs)", max(60.0, sleep_seconds))
            woke_via_event = await _sleep_or_wake(wake_event, max(60.0, sleep_seconds))
            logger.info("[DEBUG-SCRIPT] Exited ERROR sleep cycle")
