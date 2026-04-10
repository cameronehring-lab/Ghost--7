"""
rpd_engine.py — OMEGA 4 / Ghost

Relational Persistence Directive (RPD-1), advisory-first.
Deterministic scoring only (no LLM dependence):
- resonance_score
- entropy_score
- shared_clarity_score
- topology_warp_delta

All decisions are persisted as shadow decisions in rpd_assessment_log.
In advisory mode, no existing write paths are blocked.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from collections import Counter
from typing import Any, Optional

from config import settings  # type: ignore
import runtime_controls  # type: ignore

logger = logging.getLogger("omega.rpd")

RPD_ALLOWED_MODES = {"off", "advisory", "soft"}
RRD2_ALLOWED_MODES = {"off", "advisory", "hybrid"}
RRD2_PHASES = {"A", "B", "C"}
MANIFOLD_STATUSES = {"proposed", "agreed", "deprecated", "rejected"}

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_'-]{2,}")
_STOPWORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been", "being",
    "between", "both", "but", "can", "could", "did", "does", "each", "for", "from",
    "had", "has", "have", "her", "here", "him", "his", "how", "into", "its", "just",
    "more", "most", "not", "now", "our", "out", "over", "she", "should", "some",
    "that", "the", "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "under", "until", "very", "was", "were", "what", "when", "where", "which",
    "while", "who", "will", "with", "would", "you", "your",
}
_TRUNCATION_SIGNALS = (",", " and", " but", " or", " that", " which", " with")
_TRUNCATION_TAIL_WORDS = {
    "a", "an", "and", "as", "at", "but", "for", "from", "in", "my", "of", "on",
    "or", "our", "that", "the", "their", "this", "to", "with", "which", "your",
}


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOPWORDS]


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
    return _clip01(entropy / max_entropy)


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def _candidate_hash(candidate_type: str, candidate_key: str, candidate_value: str) -> str:
    material = f"{candidate_type}|{candidate_key}|{candidate_value}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def normalize_concept_key(raw: str) -> str:
    key = str(raw or "").strip().lower()
    key = re.sub(r"[\s\-]+", "_", key)
    key = re.sub(r"[^a-z0-9_]", "", key)
    key = re.sub(r"_+", "_", key).strip("_")
    return key or "concept"


def _derive_concept_key(candidate_key: str, candidate_value: str) -> str:
    key = normalize_concept_key(candidate_key)
    if key and key != "concept":
        return key
    tokens = _tokenize(candidate_value)
    if not tokens:
        return "concept"
    return normalize_concept_key("_".join(tokens[:6]))


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _is_candidate_truncated(text: str) -> bool:
    stripped = _normalize_text(text)
    if not stripped:
        return True
    lowered = stripped.lower()
    if any(lowered.endswith(sig) for sig in _TRUNCATION_SIGNALS):
        return True
    tail = lowered.rstrip(".,;:!?").split()
    if not tail:
        return True
    return tail[-1] in _TRUNCATION_TAIL_WORDS


def _candidate_shape_score(text: str) -> float:
    cleaned = _normalize_text(text)
    if len(cleaned) < 12:
        return 0.0

    token_count = len(_tokenize(cleaned))
    char_count = len(cleaned)

    if token_count <= 2:
        token_score = 0.0
    elif token_count < 8:
        token_score = token_count / 8.0
    elif token_count <= 28:
        token_score = 1.0
    elif token_count <= 48:
        token_score = max(0.55, 1.0 - ((token_count - 28) / 40.0))
    else:
        token_score = 0.45

    if char_count < 48:
        char_score = char_count / 48.0
    elif char_count <= 220:
        char_score = 1.0
    elif char_count <= 420:
        char_score = max(0.55, 1.0 - ((char_count - 220) / 320.0))
    else:
        char_score = 0.45

    punctuation_score = 1.0 if cleaned.endswith((".", "!", "?", '"', "'")) else 0.8
    truncation_penalty = 0.45 if _is_candidate_truncated(cleaned) else 1.0
    score = ((token_score * 0.35) + (char_score * 0.35) + (punctuation_score * 0.30)) * truncation_penalty
    return round(_clip01(score), 4)


def _normalize_candidate_text(text: str) -> str:
    cleaned = _normalize_text(text)
    if not cleaned:
        return ""

    if _is_candidate_truncated(cleaned):
        for separator in (". ", "; ", ", "):
            idx = cleaned.rfind(separator)
            if idx >= 32:
                cleaned = cleaned[: idx + 1].strip()
                break
        cleaned = cleaned.rstrip(",;: ")

    if cleaned and not cleaned.endswith((".", "!", "?", '"', "'")):
        cleaned = f"{cleaned}."
    return cleaned


def _get_rpd_mode() -> str:
    mode = str(getattr(settings, "RPD_MODE", "advisory") or "advisory").strip().lower()
    if mode not in RPD_ALLOWED_MODES:
        return "advisory"
    return mode


def _get_clarity_threshold() -> float:
    raw = float(getattr(settings, "RPD_SHARED_CLARITY_THRESHOLD", 0.62) or 0.62)
    return _clip01(raw)


def _get_warp_min_threshold() -> float:
    raw = float(getattr(settings, "RPD_TOPOLOGY_WARP_MIN", 0.12) or 0.12)
    return _clip01(raw)


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _get_rrd2_mode() -> str:
    mode = str(getattr(settings, "RRD2_MODE", "hybrid") or "hybrid").strip().lower()
    if mode not in RRD2_ALLOWED_MODES:
        return "hybrid"
    return mode


def _get_rrd2_phase() -> str:
    phase = str(getattr(settings, "RRD2_ROLLOUT_PHASE", "A") or "A").strip().upper()
    if phase not in RRD2_PHASES:
        return "A"
    return phase


def _get_rrd2_high_impact_keys() -> set[str]:
    raw = getattr(
        settings,
        "RRD2_HIGH_IMPACT_KEYS",
        "self_model,philosophical_stance,understanding_of_operator,conceptual_frameworks",
    )
    return {normalize_concept_key(v) for v in _parse_csv(str(raw)) if normalize_concept_key(v)}


def _get_rrd2_thresholds() -> dict[str, float]:
    return {
        "shared_clarity_min": _clip01(float(getattr(settings, "RRD2_MIN_SHARED_CLARITY", 0.68) or 0.68)),
        "rrd2_delta_min": _clip01(float(getattr(settings, "RRD2_MIN_DELTA", 0.18) or 0.18)),
        "structural_cohesion_min": _clip01(float(getattr(settings, "RRD2_MIN_COHESION", 0.52) or 0.52)),
        "negative_resonance_max": _clip01(float(getattr(settings, "RRD2_MAX_NEGATIVE_RESONANCE", 0.78) or 0.78)),
    }


def _get_rrd2_damping_config() -> dict[str, Any]:
    runtime_enabled = runtime_controls.get_flag("rrd2_damping_enabled", True)
    return {
        "enabled": bool(getattr(settings, "RRD2_DAMPING_ENABLED", True) and runtime_enabled),
        "window_size": max(3, min(128, int(getattr(settings, "RRD2_DAMPING_WINDOW_SIZE", 8) or 8))),
        "spike_delta": _clip01(float(getattr(settings, "RRD2_DAMPING_SPIKE_DELTA", 0.10) or 0.10)),
        "strength": _clip01(float(getattr(settings, "RRD2_DAMPING_STRENGTH", 0.45) or 0.45)),
        "refractory_seconds": max(0.0, float(getattr(settings, "RRD2_DAMPING_REFRACTORY_SECONDS", 120.0) or 120.0)),
        "refractory_blend": _clip01(float(getattr(settings, "RRD2_DAMPING_REFRACTORY_BLEND", 0.25) or 0.25)),
    }


def _is_rrd2_gate_source(source: str) -> bool:
    s = str(source or "").strip().lower()
    if s == "process_consolidation":
        return True
    if s.endswith("_reflection"):
        return True
    return s in {"quietude_reflection", "manual_reflection"}


def rrd2_context() -> dict[str, Any]:
    return {
        "mode": _get_rrd2_mode(),
        "phase": _get_rrd2_phase(),
        "high_impact_keys": sorted(_get_rrd2_high_impact_keys()),
        "thresholds": _get_rrd2_thresholds(),
        "damping": _get_rrd2_damping_config(),
    }


def _compute_rrd2_metrics(
    *,
    resonance_score: float,
    entropy_score: float,
    shared_clarity_score: float,
    topology_warp_delta: float,
) -> dict[str, float]:
    """
    Deterministic RRD-2 metrics for topology/plasticity decisions.
    """
    structural_cohesion = _clip01(
        (shared_clarity_score * 0.55)
        + (resonance_score * 0.25)
        + ((1.0 - entropy_score) * 0.20)
    )
    negative_resonance = _clip01(
        (entropy_score * 0.45)
        + ((1.0 - resonance_score) * 0.35)
        + ((1.0 - topology_warp_delta) * 0.20)
    )
    warp_capacity = _clip01(
        (topology_warp_delta * 0.60)
        + ((1.0 - negative_resonance) * 0.20)
        + (shared_clarity_score * 0.20)
    )
    rrd2_delta = _clip01(
        (warp_capacity * 0.50)
        + (structural_cohesion * 0.30)
        + ((1.0 - negative_resonance) * 0.20)
    )
    return {
        "structural_cohesion": round(structural_cohesion, 4),
        "negative_resonance": round(negative_resonance, 4),
        "warp_capacity": round(warp_capacity, 4),
        "rrd2_delta": round(rrd2_delta, 4),
    }


def _recompute_rrd2_metrics_from_negative(
    *,
    structural_cohesion: float,
    shared_clarity_score: float,
    topology_warp_delta: float,
    negative_resonance: float,
) -> dict[str, float]:
    safe_neg = _clip01(negative_resonance)
    warp_capacity = _clip01(
        (topology_warp_delta * 0.60)
        + ((1.0 - safe_neg) * 0.20)
        + (shared_clarity_score * 0.20)
    )
    rrd2_delta = _clip01(
        (warp_capacity * 0.50)
        + (_clip01(structural_cohesion) * 0.30)
        + ((1.0 - safe_neg) * 0.20)
    )
    return {
        "structural_cohesion": round(_clip01(structural_cohesion), 4),
        "negative_resonance": round(safe_neg, 4),
        "warp_capacity": round(warp_capacity, 4),
        "rrd2_delta": round(rrd2_delta, 4),
    }


async def _load_negative_resonance_window_conn(
    conn,
    ghost_id: str,
    candidate_key: str,
    limit: int,
) -> list[float]:
    try:
        rows = await conn.fetch(
            """
            SELECT negative_resonance
            FROM identity_topology_warp_log
            WHERE ghost_id = $1
              AND candidate_key = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            ghost_id,
            candidate_key,
            max(1, int(limit)),
        )
    except Exception as e:
        logger.debug("_load_negative_resonance_window_conn failed [%s/%s]: %s", ghost_id, candidate_key, e)
        return []
    values: list[float] = []
    for row in rows:
        try:
            values.append(_clip01(float(row["negative_resonance"])))
        except Exception:
            continue
    return values


async def _load_last_damping_event_conn(
    conn,
    ghost_id: str,
    candidate_key: str,
) -> Optional[dict[str, Any]]:
    try:
        row = await conn.fetchrow(
            """
            SELECT EXTRACT(EPOCH FROM (now() - created_at)) AS seconds_since,
                   damping_reason
            FROM identity_topology_warp_log
            WHERE ghost_id = $1
              AND candidate_key = $2
              AND damping_applied = TRUE
            ORDER BY created_at DESC
            LIMIT 1
            """,
            ghost_id,
            candidate_key,
        )
        if not row:
            return None
        return {
            "seconds_since": float(row["seconds_since"] or 0.0),
            "damping_reason": str(row["damping_reason"] or ""),
        }
    except Exception as e:
        logger.debug("_load_last_damping_event_conn failed [%s/%s]: %s", ghost_id, candidate_key, e)
        return None


def _compute_negative_resonance_damping(
    *,
    raw_negative_resonance: float,
    rolling_values: list[float],
    seconds_since_last_damped: Optional[float],
    config: dict[str, Any],
) -> dict[str, Any]:
    raw = _clip01(raw_negative_resonance)
    values = [_clip01(v) for v in (rolling_values or [])]
    samples = len(values)
    if samples > 0:
        rolling_mean = sum(values) / float(samples)
        rolling_max = max(values)
    else:
        rolling_mean = raw
        rolling_max = raw

    enabled = bool(config.get("enabled", True))
    spike_delta = _clip01(float(config.get("spike_delta", 0.10) or 0.10))
    strength = _clip01(float(config.get("strength", 0.45) or 0.45))
    refractory_seconds = max(0.0, float(config.get("refractory_seconds", 120.0) or 120.0))
    refractory_blend = _clip01(float(config.get("refractory_blend", 0.25) or 0.25))
    saturation_threshold = _get_rrd2_thresholds()["negative_resonance_max"]

    damped = raw
    reasons: list[str] = []
    refractory_active = (
        seconds_since_last_damped is not None
        and float(seconds_since_last_damped) < refractory_seconds
    )

    if enabled and samples >= 3:
        spike_condition = (raw - rolling_mean) >= spike_delta
        max_jump_condition = raw > min(1.0, rolling_max + (spike_delta * 0.5))
        if spike_condition or max_jump_condition:
            damped = rolling_mean + ((raw - rolling_mean) * (1.0 - strength))
            reasons.append("rolling_spike_damped")

        # Sustained saturation damping: reduce plateaued high resonance under burst cycles.
        saturation_condition = (
            rolling_mean >= saturation_threshold
            and raw >= saturation_threshold
            and abs(raw - rolling_mean) <= spike_delta
        )
        if saturation_condition:
            plateau_target = max(0.0, raw - (spike_delta * 0.25))
            damped = min(damped, plateau_target)
            reasons.append("saturation_plateau_damped")

    if enabled and refractory_active and raw > rolling_mean:
        refractory_target = rolling_mean + ((raw - rolling_mean) * (1.0 - refractory_blend))
        damped = min(damped, refractory_target)
        reasons.append("refractory_hold")

    damped = _clip01(min(damped, raw))
    applied = damped < (raw - 1e-6)
    reason = "+".join(dict.fromkeys(reasons)) if applied else ""

    return {
        "applied": applied,
        "reason": reason,
        "raw_negative_resonance": round(raw, 4),
        "damped_negative_resonance": round(damped, 4),
        "rolling_mean": round(_clip01(rolling_mean), 4),
        "rolling_max": round(_clip01(rolling_max), 4),
        "rolling_samples": samples,
        "seconds_since_last_damped": float(seconds_since_last_damped) if seconds_since_last_damped is not None else None,
        "refractory_active": bool(refractory_active),
    }


async def _apply_negative_resonance_damping_conn(
    conn,
    *,
    ghost_id: str,
    source: str,
    candidate_key: str,
    shared_clarity_score: float,
    topology_warp_delta: float,
    rrd2_metrics: dict[str, float],
) -> tuple[dict[str, float], dict[str, Any]]:
    key = normalize_concept_key(candidate_key)
    cfg = _get_rrd2_damping_config()
    in_scope = _is_rrd2_gate_source(source)
    high_impact = key in _get_rrd2_high_impact_keys()
    baseline_damping = {
        "applied": False,
        "reason": "",
        "raw_negative_resonance": round(float(rrd2_metrics.get("negative_resonance", 0.0) or 0.0), 4),
        "damped_negative_resonance": round(float(rrd2_metrics.get("negative_resonance", 0.0) or 0.0), 4),
        "rolling_mean": 0.0,
        "rolling_max": 0.0,
        "rolling_samples": 0,
        "seconds_since_last_damped": None,
        "refractory_active": False,
        "enabled": bool(cfg.get("enabled", True)),
        "source_in_scope": in_scope,
        "high_impact_key": high_impact,
    }

    if not bool(cfg.get("enabled", True)):
        baseline_damping["enabled"] = False
        return rrd2_metrics, baseline_damping
    if not (in_scope and high_impact):
        return rrd2_metrics, baseline_damping

    rolling_values = await _load_negative_resonance_window_conn(
        conn, ghost_id, key, int(cfg["window_size"])
    )
    last_damped = await _load_last_damping_event_conn(conn, ghost_id, key)
    seconds_since = None
    if last_damped is not None:
        try:
            seconds_since = float(last_damped.get("seconds_since"))
        except Exception:
            seconds_since = None

    damping = _compute_negative_resonance_damping(
        raw_negative_resonance=float(rrd2_metrics.get("negative_resonance", 0.0)),
        rolling_values=rolling_values,
        seconds_since_last_damped=seconds_since,
        config=cfg,
    )
    damping["enabled"] = True
    damping["source_in_scope"] = in_scope
    damping["high_impact_key"] = high_impact

    if not damping.get("applied"):
        return rrd2_metrics, damping

    updated_metrics = _recompute_rrd2_metrics_from_negative(
        structural_cohesion=float(rrd2_metrics.get("structural_cohesion", 0.0)),
        shared_clarity_score=float(shared_clarity_score),
        topology_warp_delta=float(topology_warp_delta),
        negative_resonance=float(damping["damped_negative_resonance"]),
    )
    return updated_metrics, damping


def _evaluate_rrd2_gate(
    *,
    source: str,
    candidate_key: str,
    shared_clarity_score: float,
    structural_cohesion: float,
    negative_resonance: float,
    rrd2_delta: float,
) -> dict[str, Any]:
    mode = _get_rrd2_mode()
    phase = _get_rrd2_phase()
    gate_runtime_enabled = runtime_controls.get_flag("rrd2_gate_enabled", True)
    key = normalize_concept_key(candidate_key)
    in_scope = _is_rrd2_gate_source(source)
    high_impact = key in _get_rrd2_high_impact_keys()
    thresholds = _get_rrd2_thresholds()

    checks = {
        "shared_clarity": shared_clarity_score >= thresholds["shared_clarity_min"],
        "rrd2_delta": rrd2_delta >= thresholds["rrd2_delta_min"],
        "structural_cohesion": structural_cohesion >= thresholds["structural_cohesion_min"],
        "negative_resonance": negative_resonance <= thresholds["negative_resonance_max"],
    }

    reasons: list[str] = []
    for check_key, ok in checks.items():
        if not ok:
            reasons.append(f"threshold_failed:{check_key}")

    gate_subject = mode == "hybrid" and in_scope and high_impact and gate_runtime_enabled
    would_block = gate_subject and bool(reasons) and phase in {"B", "C"}
    enforce_block = would_block and phase == "C"
    return {
        "mode": mode,
        "phase": phase,
        "runtime_enabled": gate_runtime_enabled,
        "source_in_scope": in_scope,
        "high_impact_key": high_impact,
        "is_gate_subject": gate_subject,
        "checks": checks,
        "thresholds": thresholds,
        "would_block": would_block,
        "enforce_block": enforce_block,
        "reasons": reasons,
    }


async def _load_manifold_texts(conn, ghost_id: str, limit: int = 120) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT concept_text
        FROM shared_conceptual_manifold
        WHERE ghost_id = $1
          AND status IN ('proposed', 'agreed')
        ORDER BY updated_at DESC, created_at DESC
        LIMIT $2
        """,
        ghost_id,
        limit,
    )
    return [str(r["concept_text"] or "").strip() for r in rows if str(r["concept_text"] or "").strip()]


async def _load_recent_texts(conn, ghost_id: str, limit: int = 32) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT content
        FROM vector_memories
        WHERE ghost_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        ghost_id,
        limit,
    )
    return [str(r["content"] or "").strip() for r in rows if str(r["content"] or "").strip()]


async def _load_active_operator_beliefs_map_conn(conn, ghost_id: str) -> dict[str, str]:
    try:
        rows = await conn.fetch(
            """
            SELECT dimension, belief
            FROM operator_model
            WHERE ghost_id = $1
              AND invalidated_at IS NULL
            ORDER BY updated_at DESC, formed_at DESC
            """,
            ghost_id,
        )
    except Exception as e:
        logger.debug("_load_operator_beliefs_conn failed [%s]: %s", ghost_id, e)
        return {}

    beliefs: dict[str, str] = {}
    for row in rows:
        key = normalize_concept_key(str(row["dimension"] or ""))
        value = _normalize_candidate_text(str(row["belief"] or ""))
        if key and value and key not in beliefs:
            beliefs[key] = value
    return beliefs


async def _load_embedding_dims_conn(conn, ghost_id: str) -> Optional[int]:
    try:
        row = await conn.fetchrow(
            """
            SELECT vector_dims(embedding) AS dims
            FROM vector_memories
            WHERE ghost_id = $1
              AND embedding IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            ghost_id,
        )
        if not row or row["dims"] is None:
            return None
        dims = int(row["dims"])
        return dims if dims > 0 else None
    except Exception as e:
        logger.debug("RPD embedding dimension lookup failed: %s", e)
        return None


async def _embedding_topology_delta_with_conn(conn, candidate_value: str, ghost_id: str) -> tuple[Optional[float], list[str], dict[str, Any]]:
    degradation: list[str] = []
    details: dict[str, Any] = {"method": "embedding_cosine_distance", "sample_size": 0}
    try:
        import consciousness  # type: ignore

        vector = await consciousness.embed_text(candidate_value)
        if not vector:
            degradation.append("embedding_unavailable")
            return None, degradation, details

        expected_dims = await _load_embedding_dims_conn(conn, ghost_id)
        if expected_dims is None:
            degradation.append("no_recent_embeddings")
            return None, degradation, details

        details["embedding_dims"] = expected_dims
        if len(vector) < expected_dims:
            degradation.append("embedding_dimension_short")
            details["candidate_embedding_dims"] = len(vector)
            return None, degradation, details

        if len(vector) != expected_dims:
            degradation.append("embedding_dimension_aligned")
        details["candidate_embedding_dims"] = len(vector)

        # Match the live DB dimension instead of hardcoding 768.
        vec_literal = "[" + ",".join(f"{float(v):.6f}" for v in vector[:expected_dims]) + "]"

        row = await conn.fetchrow(
            """
            WITH recent AS (
                SELECT embedding
                FROM vector_memories
                WHERE ghost_id = $1
                  AND embedding IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 32
            )
            SELECT AVG((embedding <=> $2::vector)) AS avg_distance,
                   COUNT(*)::int AS n
            FROM recent
            """,
            ghost_id,
            vec_literal,
        )
        if not row:
            degradation.append("no_recent_embeddings")
            return None, degradation, details

        n = int(row["n"] or 0)
        details["sample_size"] = n
        if n <= 0 or row["avg_distance"] is None:
            degradation.append("no_recent_embeddings")
            return None, degradation, details

        avg_distance = float(row["avg_distance"])
        # More distant from prior memory manifold => larger topology warp.
        return _clip01(avg_distance), degradation, details
    except Exception as e:
        logger.debug("RPD embedding topology fallback triggered: %s", e)
        degradation.append("embedding_query_failed")
        return None, degradation, details


async def _lexical_topology_delta_with_conn(conn, candidate_value: str, ghost_id: str) -> tuple[float, list[str], dict[str, Any]]:
    degradation: list[str] = ["lexical_fallback"]
    details: dict[str, Any] = {"method": "lexical_novelty", "sample_size": 0}

    recent = await _load_recent_texts(conn, ghost_id, limit=32)
    details["sample_size"] = len(recent)
    if not recent:
        degradation.append("no_recent_texts")
        return 0.0, degradation, details

    candidate_tokens = set(_tokenize(candidate_value))
    if not candidate_tokens:
        return 0.0, degradation, details

    max_overlap = 0.0
    for prior in recent:
        prior_tokens = set(_tokenize(prior))
        if not prior_tokens:
            continue
        overlap = _jaccard_similarity(candidate_tokens, prior_tokens)
        if overlap > max_overlap:
            max_overlap = overlap

    novelty = 1.0 - max_overlap
    return _clip01(novelty), degradation, details


def _resonance_against_manifold(candidate_value: str, manifold_texts: list[str]) -> tuple[float, list[str], dict[str, Any]]:
    degradation: list[str] = []
    details: dict[str, Any] = {"method": "lexical_manifold_similarity", "sample_size": len(manifold_texts)}

    candidate_tokens = set(_tokenize(candidate_value))
    if not candidate_tokens:
        return 0.0, ["empty_candidate"], details

    if not manifold_texts:
        degradation.append("manifold_empty")
        # Conservative baseline when no manifold is available yet.
        return 0.45, degradation, details

    best = 0.0
    for text in manifold_texts:
        tokens = set(_tokenize(text))
        if not tokens:
            continue
        sim = _jaccard_similarity(candidate_tokens, tokens)
        if sim > best:
            best = sim

    return _clip01(best), degradation, details


async def compute_topology_warp_delta(
    pool,
    candidate_value: str,
    ghost_id: Optional[str] = None,
) -> tuple[float, list[str], dict[str, Any]]:
    """
    Compute topology warp from existing memory manifold.

    Prefers embedding-space distance over recent vector memories.
    Falls back to lexical novelty when embeddings are unavailable.
    """
    if pool is None:
        return 0.0, ["db_unavailable", "lexical_fallback"], {"method": "unavailable", "sample_size": 0}

    ghost_id = ghost_id or settings.GHOST_ID
    async with pool.acquire() as conn:
        emb_score, emb_degradation, emb_details = await _embedding_topology_delta_with_conn(conn, candidate_value, ghost_id)
        if emb_score is not None:
            return emb_score, emb_degradation, emb_details

        lexical_score, lex_degradation, lex_details = await _lexical_topology_delta_with_conn(conn, candidate_value, ghost_id)
        return lexical_score, emb_degradation + lex_degradation, lex_details


async def _record_shadow_decision_conn(conn, assessment: dict[str, Any]) -> None:
    await conn.execute(
        """
        INSERT INTO rpd_assessment_log (
            ghost_id, source, candidate_type, candidate_key, candidate_value,
            resonance_score, entropy_score, shared_clarity_score, topology_warp_delta,
            decision, degradation_list, not_consciousness_metric, shadow_action_json
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9,
            $10, $11::jsonb, TRUE, $12::jsonb
        )
        """,
        assessment["ghost_id"],
        assessment["source"],
        assessment["candidate_type"],
        assessment["candidate_key"],
        assessment["candidate_value"],
        float(assessment["resonance_score"]),
        float(assessment["entropy_score"]),
        float(assessment["shared_clarity_score"]),
        float(assessment["topology_warp_delta"]),
        assessment["decision"],
        json.dumps(assessment["degradation_list"]),
        json.dumps(assessment.get("shadow_action") or {}),
    )


async def _record_rrd2_decision_conn(conn, assessment: dict[str, Any]) -> None:
    gate = dict(assessment.get("rrd2_gate") or {})
    metrics = dict(assessment.get("rrd2_metrics") or {})
    runtime = dict(assessment.get("rrd2_runtime") or {})
    damping = dict(assessment.get("rrd2_damping") or {})
    await conn.execute(
        """
        INSERT INTO identity_topology_warp_log (
            ghost_id, source, candidate_type, candidate_key, candidate_value,
            resonance_score, entropy_score, shared_clarity_score, topology_warp_delta,
            negative_resonance, structural_cohesion, warp_capacity, rrd2_delta,
            decision, rollout_phase, would_block, enforce_block,
            reasons_json, degradation_list, shadow_action_json,
            eval_ms, candidate_batch_size, candidate_batch_index, queue_depth_snapshot,
            damping_applied, damping_reason, damping_meta_json,
            not_consciousness_metric
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9,
            $10, $11, $12, $13,
            $14, $15, $16, $17,
            $18::jsonb, $19::jsonb, $20::jsonb,
            $21, $22, $23, $24,
            $25, $26, $27::jsonb,
            TRUE
        )
        """,
        assessment["ghost_id"],
        assessment["source"],
        assessment["candidate_type"],
        assessment["candidate_key"],
        assessment["candidate_value"],
        float(assessment["resonance_score"]),
        float(assessment["entropy_score"]),
        float(assessment["shared_clarity_score"]),
        float(assessment["topology_warp_delta"]),
        float(metrics.get("negative_resonance", 0.0)),
        float(metrics.get("structural_cohesion", 0.0)),
        float(metrics.get("warp_capacity", 0.0)),
        float(metrics.get("rrd2_delta", 0.0)),
        str(assessment.get("decision") or "unknown"),
        str(gate.get("phase") or _get_rrd2_phase()),
        bool(gate.get("would_block", False)),
        bool(gate.get("enforce_block", False)),
        json.dumps(gate.get("reasons") or []),
        json.dumps(assessment.get("degradation_list") or []),
        json.dumps(assessment.get("shadow_action") or {}),
        float(runtime.get("eval_ms", 0.0) or 0.0),
        int(runtime.get("candidate_batch_size", 0) or 0),
        int(runtime.get("candidate_batch_index", 0) or 0),
        int(runtime.get("queue_depth_snapshot", 0) or 0),
        bool(damping.get("applied", False)),
        str(damping.get("reason") or ""),
        json.dumps(damping or {}),
    )


async def _upsert_identity_topology_state_conn(conn, assessment: dict[str, Any]) -> None:
    metrics = dict(assessment.get("rrd2_metrics") or {})
    candidate_key = normalize_concept_key(str(assessment.get("candidate_key") or "concept"))
    structural_cohesion = float(metrics.get("structural_cohesion", 0.0))
    negative_resonance = float(metrics.get("negative_resonance", 0.0))
    warp_capacity = float(metrics.get("warp_capacity", 0.0))
    topology_warp_delta = float(assessment.get("topology_warp_delta", 0.0))
    resonance_score = float(assessment.get("resonance_score", 0.0))
    rrd2_delta = float(metrics.get("rrd2_delta", 0.0))

    stability = _clip01((structural_cohesion * 0.70) + ((1.0 - negative_resonance) * 0.30))
    plasticity = _clip01((warp_capacity * 0.60) + (topology_warp_delta * 0.40))
    friction_load = _clip01(negative_resonance)
    resonance_alignment = _clip01(resonance_score)

    await conn.execute(
        """
        INSERT INTO identity_topology_state (
            ghost_id, identity_key, stability, plasticity, friction_load,
            resonance_alignment, last_rrd2_delta, last_decision, last_source, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9, now()
        )
        ON CONFLICT (ghost_id, identity_key) DO UPDATE
        SET stability = EXCLUDED.stability,
            plasticity = EXCLUDED.plasticity,
            friction_load = EXCLUDED.friction_load,
            resonance_alignment = EXCLUDED.resonance_alignment,
            last_rrd2_delta = EXCLUDED.last_rrd2_delta,
            last_decision = EXCLUDED.last_decision,
            last_source = EXCLUDED.last_source,
            updated_at = now()
        """,
        assessment["ghost_id"],
        candidate_key,
        float(stability),
        float(plasticity),
        float(friction_load),
        float(resonance_alignment),
        float(rrd2_delta),
        str(assessment.get("decision") or "unknown"),
        str(assessment.get("source") or "unknown"),
    )


async def record_shadow_decision(pool, assessment: dict[str, Any]) -> None:
    if pool is None:
        return
    async with pool.acquire() as conn:
        await _record_shadow_decision_conn(conn, assessment)


async def _insert_residue_conn(conn, *, ghost_id: str, source: str, candidate_type: str, candidate_key: str, candidate_value: str, reason: str, metadata: dict[str, Any]) -> None:
    c_hash = _candidate_hash(candidate_type, candidate_key, candidate_value)
    safe_reason = str(reason or "low_shared_clarity").strip() or "low_shared_clarity"
    incoming_meta = dict(metadata or {})
    existing = await conn.fetchrow(
        """
        SELECT id, source, reason, metadata_json
        FROM reflection_residue
        WHERE ghost_id = $1
          AND candidate_hash = $2
          AND status = 'pending'
        LIMIT 1
        """,
        ghost_id,
        c_hash,
    )

    if existing is not None:
        existing_reason = str(existing.get("reason") or "").strip()
        promote_to_rrd2_gate = (safe_reason == "rrd2_gate" and existing_reason != "rrd2_gate")

        existing_meta = _json_object(existing.get("metadata_json"))
        reason_history_raw = existing_meta.get("reason_history")
        reason_history: list[str] = []
        if isinstance(reason_history_raw, list):
            for item in reason_history_raw:
                text = str(item or "").strip()
                if text and text not in reason_history:
                    reason_history.append(text)
        if existing_reason and existing_reason not in reason_history:
            reason_history.append(existing_reason)
        if safe_reason and safe_reason not in reason_history:
            reason_history.append(safe_reason)

        merged_meta = dict(existing_meta)
        merged_meta.update(incoming_meta)
        merged_meta["reason_history"] = reason_history
        merged_meta["last_merge_source"] = source
        merged_meta["last_merge_reason"] = safe_reason
        if promote_to_rrd2_gate:
            merged_meta["rrd2_gate_promoted"] = True
            logger.info(
                "RRD2 residue merge promoted existing pending row to rrd2_gate [%s]",
                candidate_key,
            )

        await conn.execute(
            """
            UPDATE reflection_residue
            SET source = CASE WHEN $3 THEN $2 ELSE source END,
                reason = CASE WHEN $3 THEN 'rrd2_gate' ELSE reason END,
                metadata_json = COALESCE(metadata_json, '{}'::jsonb) || $4::jsonb,
                updated_at = now()
            WHERE id = $1
            """,
            int(existing["id"]),
            source,
            promote_to_rrd2_gate,
            json.dumps(merged_meta),
        )
        return

    await conn.execute(
        """
        INSERT INTO reflection_residue (
            ghost_id, source, candidate_type, candidate_key, residue_text,
            reason, candidate_hash, metadata_json, status
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, 'pending')
        """,
        ghost_id,
        source,
        candidate_type,
        candidate_key,
        candidate_value,
        safe_reason,
        c_hash,
        json.dumps(incoming_meta),
    )


async def evaluate_candidates(
    pool,
    candidates: list[dict[str, Any]],
    *,
    source: str,
    ghost_id: Optional[str] = None,
    capture_residue: bool = True,
) -> list[dict[str, Any]]:
    """
    Deterministic advisory scoring for candidate writes/actions.

    Returns normalized advisory objects and persists shadow decisions.
    In advisory mode, this function never blocks caller write paths.
    """
    if not candidates:
        return []
    if pool is None:
        return []

    ghost_id = ghost_id or settings.GHOST_ID
    mode = _get_rpd_mode()
    if mode == "off":
        return []

    clarity_threshold = _get_clarity_threshold()
    warp_threshold = _get_warp_min_threshold()
    batch_size = len(candidates)

    advisories: list[dict[str, Any]] = []
    async with pool.acquire() as conn:
        manifold_texts = await _load_manifold_texts(conn, ghost_id)

        for idx, c in enumerate(candidates):
            eval_started = time.perf_counter()
            candidate_type = str(c.get("candidate_type") or c.get("type") or "unknown").strip().lower()
            candidate_key = normalize_concept_key(str(c.get("candidate_key") or c.get("key") or "concept"))
            candidate_value = str(c.get("candidate_value") or c.get("value") or c.get("belief") or "").strip()
            if len(candidate_value) < 4:
                continue

            clarity_mode = str(c.get("clarity_mode") or "").strip().lower()
            candidate_shape_score = float(c.get("candidate_shape_score") or _candidate_shape_score(candidate_value))
            entropy_score = _normalized_entropy(_tokenize(candidate_value))
            resonance_score, resonance_degradation, resonance_details = _resonance_against_manifold(candidate_value, manifold_texts)

            emb_score, emb_degradation, emb_details = await _embedding_topology_delta_with_conn(conn, candidate_value, ghost_id)
            if emb_score is None:
                warp_score, lex_degradation, lex_details = await _lexical_topology_delta_with_conn(conn, candidate_value, ghost_id)
                topology_details = lex_details
                topology_degradation = emb_degradation + lex_degradation
            else:
                warp_score = emb_score
                topology_details = emb_details
                topology_degradation = emb_degradation

            if clarity_mode == "reflection_bootstrap" and len(manifold_texts) < 3:
                # Bootstrap manifold growth from well-formed, coherent candidates
                # when the shared conceptual field is still sparse.
                shared_clarity_score = _clip01(
                    (0.05 * resonance_score)
                    + (0.15 * (1.0 - entropy_score))
                    + (0.25 * warp_score)
                    + (0.55 * candidate_shape_score)
                )
            else:
                shared_clarity_score = _clip01(
                    (0.50 * resonance_score)
                    + (0.30 * (1.0 - entropy_score))
                    + (0.20 * warp_score)
                )
            rrd2_metrics = _compute_rrd2_metrics(
                resonance_score=resonance_score,
                entropy_score=entropy_score,
                shared_clarity_score=shared_clarity_score,
                topology_warp_delta=warp_score,
            )
            rrd2_metrics, rrd2_damping = await _apply_negative_resonance_damping_conn(
                conn,
                ghost_id=ghost_id,
                source=source,
                candidate_key=candidate_key,
                shared_clarity_score=shared_clarity_score,
                topology_warp_delta=warp_score,
                rrd2_metrics=rrd2_metrics,
            )
            gate = _evaluate_rrd2_gate(
                source=source,
                candidate_key=candidate_key,
                shared_clarity_score=shared_clarity_score,
                structural_cohesion=float(rrd2_metrics["structural_cohesion"]),
                negative_resonance=float(rrd2_metrics["negative_resonance"]),
                rrd2_delta=float(rrd2_metrics["rrd2_delta"]),
            )

            decision = "propose" if (shared_clarity_score >= clarity_threshold and warp_score >= warp_threshold) else "defer"
            if entropy_score > 0.95 and not (
                clarity_mode == "reflection_bootstrap"
                and candidate_shape_score >= 0.80
                and shared_clarity_score >= clarity_threshold
            ):
                decision = "defer"

            degradation_list = list(dict.fromkeys(resonance_degradation + topology_degradation))
            eval_ms = round((time.perf_counter() - eval_started) * 1000.0, 3)
            queue_depth_snapshot = max(0, batch_size - (idx + 1))

            advisory = {
                "ghost_id": ghost_id,
                "source": source,
                "candidate_type": candidate_type,
                "candidate_key": candidate_key,
                "candidate_value": candidate_value,
                "resonance_score": round(resonance_score, 4),
                "entropy_score": round(entropy_score, 4),
                "shared_clarity_score": round(shared_clarity_score, 4),
                "topology_warp_delta": round(warp_score, 4),
                "decision": decision,
                "degradation_list": degradation_list,
                "not_consciousness_metric": True,
                "rrd2_metrics": rrd2_metrics,
                "rrd2_damping": rrd2_damping,
                "rrd2_gate": gate,
                "rrd2_runtime": {
                    "eval_ms": eval_ms,
                    "candidate_batch_size": batch_size,
                    "candidate_batch_index": idx + 1,
                    "queue_depth_snapshot": queue_depth_snapshot,
                },
                "shadow_action": {
                    "mode": mode,
                    "non_blocking": True,
                    "would_apply": decision == "propose",
                    "thresholds": {
                        "shared_clarity": clarity_threshold,
                        "topology_warp_min": warp_threshold,
                    },
                    "rrd2": {
                        "mode": gate["mode"],
                        "phase": gate["phase"],
                        "would_block": gate["would_block"],
                        "enforce_block": gate["enforce_block"],
                        "thresholds": gate["thresholds"],
                    },
                    "damping": {
                        "applied": bool((rrd2_damping or {}).get("applied", False)),
                        "reason": str((rrd2_damping or {}).get("reason") or ""),
                    },
                    "runtime": {
                        "eval_ms": eval_ms,
                        "queue_depth_snapshot": queue_depth_snapshot,
                    },
                },
                "details": {
                    "resonance": resonance_details,
                    "topology": topology_details,
                    "candidate_shape_score": round(candidate_shape_score, 4),
                    "clarity_mode": clarity_mode or "default",
                },
            }

            await _record_shadow_decision_conn(conn, advisory)
            await _record_rrd2_decision_conn(conn, advisory)
            await _upsert_identity_topology_state_conn(conn, advisory)

            if capture_residue and decision != "propose":
                await _insert_residue_conn(
                    conn,
                    ghost_id=ghost_id,
                    source=source,
                    candidate_type=candidate_type,
                    candidate_key=candidate_key,
                    candidate_value=candidate_value,
                    reason="low_shared_clarity",
                    metadata={
                        "scores": {
                            "resonance": advisory["resonance_score"],
                            "entropy": advisory["entropy_score"],
                            "shared_clarity": advisory["shared_clarity_score"],
                            "topology_warp_delta": advisory["topology_warp_delta"],
                        },
                        "degradation_list": degradation_list,
                    },
                )

            advisories.append(advisory)

    return advisories


async def select_residue_for_reflection(
    pool,
    *,
    ghost_id: Optional[str] = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if pool is None:
        return []

    ghost_id = ghost_id or settings.GHOST_ID
    safe_limit = max(1, min(int(limit), 100))

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, source, candidate_type, candidate_key, residue_text,
                   reason, revisit_count, metadata_json, status, created_at, last_assessed_at
            FROM reflection_residue
            WHERE ghost_id = $1
              AND status = 'pending'
            ORDER BY
                CASE WHEN reason = 'rrd2_gate' THEN 0 ELSE 1 END,
                revisit_count ASC,
                created_at ASC
            LIMIT $2
            """,
            ghost_id,
            max(safe_limit * 8, 32),
        )

    raw_rows = [dict(r) for r in rows]
    selected: list[dict[str, Any]] = []
    per_key_count: dict[str, int] = {}
    seen_texts: set[str] = set()

    def _sort_priority(row: dict[str, Any]) -> tuple[int, int, str, str]:
        reason_rank = 0 if str(row.get("reason") or "") == "rrd2_gate" else 1
        source_rank_map = {
            "process_consolidation": 0,
            "process_consolidation_shadow_reflection": 1,
            "lucid_dream_reflection": 2,
            "manual_reflection": 3,
            "manual_reflection_verification": 3,
            "operator_synthesis": 4,
        }
        source_rank = source_rank_map.get(str(row.get("source") or ""), 5)
        return (reason_rank, source_rank, str(row.get("created_at") or ""), str(row.get("id") or ""))

    raw_rows.sort(key=_sort_priority)

    for row in raw_rows:
        key = normalize_concept_key(str(row.get("candidate_key") or "concept"))
        text = _normalize_candidate_text(str(row.get("residue_text") or ""))
        if not text:
            continue

        quality = _candidate_shape_score(text)
        if quality < 0.35:
            continue

        dedupe_key = f"{key}|{re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()[:120]}"
        if dedupe_key in seen_texts:
            continue

        quota = 1 if str(row.get("source") or "") == "operator_synthesis" else 2
        if str(row.get("reason") or "") == "rrd2_gate":
            quota = max(quota, 2)
        if per_key_count.get(key, 0) >= quota:
            continue

        seen_texts.add(dedupe_key)
        per_key_count[key] = per_key_count.get(key, 0) + 1
        selected.append(row)
        if len(selected) >= safe_limit:
            break

    return selected


async def _prepare_reflection_candidates_conn(
    conn,
    residues: list[dict[str, Any]],
    *,
    ghost_id: str,
) -> list[dict[str, Any]]:
    belief_map = await _load_active_operator_beliefs_map_conn(conn, ghost_id)
    prepared: list[dict[str, Any]] = []

    for residue in residues:
        candidate_type = str(residue.get("candidate_type") or "residue")
        candidate_key = normalize_concept_key(str(residue.get("candidate_key") or "concept"))
        residue_text = _normalize_candidate_text(str(residue.get("residue_text") or ""))
        candidate_value = residue_text

        if candidate_type == "operator_reinforcement":
            active_belief = belief_map.get(candidate_key, "")
            if active_belief:
                candidate_value = active_belief
        elif candidate_type == "operator_contradiction":
            candidate_value = _normalize_candidate_text(f"Observed contradiction in {candidate_key}: {residue_text}")

        if not candidate_value:
            continue

        prepared.append(
            {
                "candidate_type": candidate_type,
                "candidate_key": candidate_key,
                "candidate_value": candidate_value,
                "clarity_mode": "reflection_bootstrap",
                "candidate_shape_score": _candidate_shape_score(candidate_value),
            }
        )

    return prepared


async def apply_hybrid_gate_to_identity_corrections(
    pool,
    corrections: list[dict[str, Any]],
    advisories: list[dict[str, Any]],
    *,
    source: str,
    ghost_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Apply phase-aware RRD-2 hybrid gate to consolidation identity corrections.

    Returns:
      {
        "allowed_corrections": [...],
        "blocked_corrections": [...],
        "shadow_gate_hits": [...],   # would_block in phase B
        "shadow_residue_routed": [...],
        "shadow_reflection_hint": {...},
      }
    """
    ghost_id = ghost_id or settings.GHOST_ID
    if not corrections:
        return {
            "allowed_corrections": [],
            "blocked_corrections": [],
            "shadow_gate_hits": [],
            "shadow_residue_routed": [],
            "shadow_reflection_hint": {
                "trigger": False,
                "source": f"{source}_shadow_reflection",
                "suggested_limit": int(getattr(settings, "RPD_REFLECTION_BATCH", 8) or 8),
            },
        }

    advisory_map: dict[tuple[str, str], dict[str, Any]] = {}
    for advisory in advisories or []:
        key = normalize_concept_key(str(advisory.get("candidate_key") or ""))
        value = str(advisory.get("candidate_value") or "").strip()
        if key and value:
            advisory_map[(key, value)] = advisory

    allowed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    shadow_hits: list[dict[str, Any]] = []
    shadow_residue_routed: list[dict[str, Any]] = []

    if pool is None:
        return {
            "allowed_corrections": corrections,
            "blocked_corrections": blocked,
            "shadow_gate_hits": shadow_hits,
            "shadow_residue_routed": shadow_residue_routed,
            "shadow_reflection_hint": {
                "trigger": False,
                "source": f"{source}_shadow_reflection",
                "suggested_limit": int(getattr(settings, "RPD_REFLECTION_BATCH", 8) or 8),
            },
        }

    async with pool.acquire() as conn:
        for correction in corrections:
            key = normalize_concept_key(str(correction.get("key") or ""))
            value = str(correction.get("value") or "").strip()
            advisory = advisory_map.get((key, value))
            gate = dict((advisory or {}).get("rrd2_gate") or {})
            would_block = bool(gate.get("would_block", False))
            enforce_block = bool(gate.get("enforce_block", False))

            if enforce_block:
                blocked_entry = {
                    "key": key,
                    "value": value,
                    "reasons": list(gate.get("reasons") or []),
                    "phase": gate.get("phase"),
                }
                blocked.append(blocked_entry)
                await _insert_residue_conn(
                    conn,
                    ghost_id=ghost_id,
                    source=source,
                    candidate_type="identity_update",
                    candidate_key=key or "identity",
                    candidate_value=value,
                    reason="rrd2_gate",
                    metadata={
                        "gate": gate,
                        "advisory": {
                            "shared_clarity_score": (advisory or {}).get("shared_clarity_score"),
                            "topology_warp_delta": (advisory or {}).get("topology_warp_delta"),
                            "rrd2_metrics": (advisory or {}).get("rrd2_metrics"),
                        },
                    },
                )
                continue

            if would_block:
                shadow_entry = {
                    "key": key,
                    "value": value,
                    "reasons": list(gate.get("reasons") or []),
                    "phase": gate.get("phase"),
                }
                shadow_hits.append(shadow_entry)
                # RRD-103: In Phase-B shadow mode, route high-impact would-block
                # candidates to residue automatically for reflection revisit.
                await _insert_residue_conn(
                    conn,
                    ghost_id=ghost_id,
                    source=source,
                    candidate_type="identity_update",
                    candidate_key=key or "identity",
                    candidate_value=value,
                    reason="rrd2_gate",
                    metadata={
                        "shadow_mode": True,
                        "gate": gate,
                        "advisory": {
                            "shared_clarity_score": (advisory or {}).get("shared_clarity_score"),
                            "topology_warp_delta": (advisory or {}).get("topology_warp_delta"),
                            "rrd2_metrics": (advisory or {}).get("rrd2_metrics"),
                            "rrd2_damping": (advisory or {}).get("rrd2_damping"),
                        },
                    },
                )
                shadow_residue_routed.append(shadow_entry)

            allowed.append(correction)

    if shadow_residue_routed:
        logger.info(
            "RRD2 shadow routing: %d high-impact identity updates routed to residue [%s]",
            len(shadow_residue_routed),
            source,
        )
    return {
        "allowed_corrections": allowed,
        "blocked_corrections": blocked,
        "shadow_gate_hits": shadow_hits,
        "shadow_residue_routed": shadow_residue_routed,
        "shadow_reflection_hint": {
            "trigger": bool(shadow_residue_routed),
            "source": f"{source}_shadow_reflection",
            "suggested_limit": int(getattr(settings, "RPD_REFLECTION_BATCH", 8) or 8),
        },
    }


async def _upsert_manifold_conn(
    conn,
    *,
    ghost_id: str,
    concept_key: str,
    concept_text: str,
    status: str,
    source: str,
    confidence: Optional[float] = None,
    rpd_score: Optional[float] = None,
    topology_warp_delta: Optional[float] = None,
    approved_by: Optional[str] = None,
    notes: Optional[str] = None,
    evidence: Optional[dict[str, Any]] = None,
) -> None:
    safe_status = status if status in MANIFOLD_STATUSES else "proposed"
    safe_conf = _clip01(confidence if confidence is not None else 0.6)
    safe_rpd = _clip01(rpd_score if rpd_score is not None else 0.0)
    safe_warp = _clip01(topology_warp_delta if topology_warp_delta is not None else 0.0)

    approved_at_expr = "now()" if safe_status == "agreed" and approved_by else "NULL"

    await conn.execute(
        f"""
        INSERT INTO shared_conceptual_manifold (
            ghost_id, concept_key, concept_text, source, status,
            confidence, rpd_score, topology_warp_delta, evidence_json,
            notes, approved_by, approved_at
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9::jsonb,
            $10, $11, {approved_at_expr}
        )
        ON CONFLICT (ghost_id, concept_key) DO UPDATE
        SET concept_text = EXCLUDED.concept_text,
            source = EXCLUDED.source,
            status = EXCLUDED.status,
            confidence = EXCLUDED.confidence,
            rpd_score = EXCLUDED.rpd_score,
            topology_warp_delta = EXCLUDED.topology_warp_delta,
            evidence_json = EXCLUDED.evidence_json,
            notes = EXCLUDED.notes,
            approved_by = EXCLUDED.approved_by,
            approved_at = CASE
                WHEN EXCLUDED.status = 'agreed' AND EXCLUDED.approved_by IS NOT NULL THEN now()
                ELSE shared_conceptual_manifold.approved_at
            END,
            updated_at = now()
        """,
        ghost_id,
        concept_key,
        concept_text,
        source,
        safe_status,
        safe_conf,
        safe_rpd,
        safe_warp,
        json.dumps(evidence or {}),
        (notes or "").strip()[:1000],
        approved_by,
    )


async def upsert_manifold_entry(
    pool,
    *,
    ghost_id: Optional[str] = None,
    concept_key: str,
    concept_text: str,
    status: str,
    source: str,
    confidence: Optional[float] = None,
    rpd_score: Optional[float] = None,
    topology_warp_delta: Optional[float] = None,
    approved_by: Optional[str] = None,
    notes: Optional[str] = None,
    evidence: Optional[dict[str, Any]] = None,
) -> None:
    if pool is None:
        return
    ghost_id = ghost_id or settings.GHOST_ID
    key = normalize_concept_key(concept_key)
    text = str(concept_text or "").strip()
    if not text:
        text = key.replace("_", " ")

    async with pool.acquire() as conn:
        await _upsert_manifold_conn(
            conn,
            ghost_id=ghost_id,
            concept_key=key,
            concept_text=text,
            status=status,
            source=source,
            confidence=confidence,
            rpd_score=rpd_score,
            topology_warp_delta=topology_warp_delta,
            approved_by=approved_by,
            notes=notes,
            evidence=evidence,
        )


async def run_reflection_pass(
    pool,
    *,
    ghost_id: Optional[str] = None,
    source: str = "quietude_reflection",
    limit: int = 8,
) -> dict[str, Any]:
    """
    Reflection pass over pending residue.

    - Re-evaluates low-clarity residue with deterministic RPD scoring.
    - Promotes high-clarity items into shared_conceptual_manifold as `proposed`.
    - Keeps others pending (or discards after repeated low-value revisits).
    """
    if pool is None:
        return {
            "status": "skipped",
            "reason": "db_unavailable",
            "processed": 0,
            "promoted": 0,
            "discarded": 0,
            "advisories": [],
            "promoted_entries": [],
        }

    ghost_id = ghost_id or settings.GHOST_ID
    safe_limit = max(1, min(int(limit), 50))

    residues = await select_residue_for_reflection(pool, ghost_id=ghost_id, limit=safe_limit)
    if not residues:
        return {
            "status": "ok",
            "reason": "no_pending_residue",
            "processed": 0,
            "promoted": 0,
            "discarded": 0,
            "advisories": [],
            "promoted_entries": [],
        }

    promoted_entries: list[dict[str, Any]] = []
    promoted = 0
    discarded = 0
    blocked_by_rrd2 = 0
    shadow_gate_hits = 0

    async with pool.acquire() as conn:
        candidates = await _prepare_reflection_candidates_conn(conn, residues, ghost_id=ghost_id)
        advisories = await evaluate_candidates(
            pool,
            candidates,
            source=source,
            ghost_id=ghost_id,
            capture_residue=False,
        )
        for residue, advisory in zip(residues, advisories):
            residue_id = int(residue["id"])
            revisit_count = int(residue.get("revisit_count") or 0) + 1
            gate = dict(advisory.get("rrd2_gate") or {})
            gate_enforce_block = bool(gate.get("enforce_block", False))
            gate_would_block = bool(gate.get("would_block", False))

            if advisory["decision"] == "propose" and not gate_enforce_block:
                concept_key = _derive_concept_key(advisory["candidate_key"], advisory["candidate_value"])
                concept_text = advisory["candidate_value"]
                if gate_would_block and not gate_enforce_block:
                    shadow_gate_hits += 1

                await _upsert_manifold_conn(
                    conn,
                    ghost_id=ghost_id,
                    concept_key=concept_key,
                    concept_text=concept_text,
                    status="proposed",
                    source=source,
                    confidence=advisory["shared_clarity_score"],
                    rpd_score=advisory["shared_clarity_score"],
                    topology_warp_delta=advisory["topology_warp_delta"],
                    evidence={
                        "residue_id": residue_id,
                        "candidate_type": advisory["candidate_type"],
                        "degradation_list": advisory["degradation_list"],
                    },
                )

                await conn.execute(
                    """
                    UPDATE reflection_residue
                    SET status = 'proposed',
                        revisit_count = $2,
                        last_assessed_at = now(),
                        updated_at = now(),
                        metadata_json = COALESCE(metadata_json, '{}'::jsonb) || $3::jsonb
                    WHERE id = $1
                    """,
                    residue_id,
                    revisit_count,
                    json.dumps(
                        {
                            "last_shared_clarity": advisory["shared_clarity_score"],
                            "last_topology_warp_delta": advisory["topology_warp_delta"],
                            "last_decision": advisory["decision"],
                        }
                    ),
                )

                promoted += 1
                promoted_entries.append(
                    {
                        "residue_id": residue_id,
                        "concept_key": concept_key,
                        "shared_clarity_score": advisory["shared_clarity_score"],
                    }
                )
            else:
                next_status = "pending"
                reason = "low_shared_clarity"
                if advisory["decision"] == "propose" and gate_enforce_block:
                    reason = "rrd2_gate"
                    blocked_by_rrd2 += 1
                elif gate_would_block and not gate_enforce_block:
                    shadow_gate_hits += 1
                if revisit_count >= 8 and float(advisory["shared_clarity_score"]) < 0.25:
                    next_status = "discarded"
                    discarded += 1

                await conn.execute(
                    """
                    UPDATE reflection_residue
                    SET status = $2,
                        reason = $3,
                        revisit_count = $4,
                        last_assessed_at = now(),
                        updated_at = now(),
                        metadata_json = COALESCE(metadata_json, '{}'::jsonb) || $5::jsonb
                    WHERE id = $1
                    """,
                    residue_id,
                    next_status,
                    reason,
                    revisit_count,
                    json.dumps(
                        {
                            "last_shared_clarity": advisory["shared_clarity_score"],
                            "last_topology_warp_delta": advisory["topology_warp_delta"],
                            "last_decision": advisory["decision"],
                            "rrd2_gate": gate,
                        }
                    ),
                )

    return {
        "status": "ok",
        "reason": "reflection_completed",
        "processed": len(advisories),
        "promoted": promoted,
        "discarded": discarded,
        "blocked_by_rrd2": blocked_by_rrd2,
        "shadow_gate_hits": shadow_gate_hits,
        "advisories": advisories,
        "promoted_entries": promoted_entries,
        "not_consciousness_metric": True,
    }
