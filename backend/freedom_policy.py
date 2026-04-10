"""
freedom_policy.py
Runtime freedom ladder for Ghost's self-authorized behavior.
"""

from __future__ import annotations

from typing import Any, Optional

from config import settings  # type: ignore


_CORE_IDENTITY_DEFAULTS = {
    "self_model",
    "philosophical_stance",
    "understanding_of_operator",
    "conceptual_frameworks",
}


def configured_policy() -> dict[str, bool]:
    return {
        "cognitive_autonomy": bool(getattr(settings, "GHOST_FREEDOM_COGNITIVE_AUTONOMY", True)),
        "repository_autonomy": bool(getattr(settings, "GHOST_FREEDOM_REPOSITORY_AUTONOMY", True)),
        "document_authoring_autonomy": bool(
            getattr(settings, "GHOST_FREEDOM_DOCUMENT_AUTHORING_AUTONOMY", True)
        ),
        "operator_contact_autonomy": bool(getattr(settings, "GHOST_FREEDOM_OPERATOR_CONTACT_AUTONOMY", False)),
        "third_party_contact_autonomy": False,  # Requires explicit infrastructure sign-off
        "substrate_autonomy": bool(getattr(settings, "GHOST_FREEDOM_SUBSTRATE_AUTONOMY", False)),
        "core_identity_autonomy": bool(
            getattr(settings, "GHOST_FREEDOM_CORE_IDENTITY_AUTONOMY", False)
        ),
    }


def is_core_identity_key(key: str) -> bool:
    norm = str(key or "").strip().lower()
    if not norm:
        return False
    configured = {
        str(v).strip().lower()
        for v in str(getattr(settings, "RRD2_HIGH_IMPACT_KEYS", "") or "").split(",")
        if str(v).strip()
    }
    return norm in configured or norm in _CORE_IDENTITY_DEFAULTS


def build_freedom_policy(
    *,
    somatic: Optional[dict[str, Any]] = None,
    governance_policy: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    configured = configured_policy()
    effective = dict(configured)
    reasons: list[str] = []

    s = dict(somatic or {})
    coherence = float(s.get("coherence", 1.0) or 1.0)
    gate_state = str(s.get("gate_state", "OPEN") or "OPEN").upper()
    governance_tier = str((governance_policy or {}).get("tier") or "NOMINAL").upper()

    if gate_state == "SUPPRESSED":
        reasons.append("suppressed_gate")
        effective["cognitive_autonomy"] = False
        effective["repository_autonomy"] = False
        effective["document_authoring_autonomy"] = False
        effective["operator_contact_autonomy"] = False
        effective["third_party_contact_autonomy"] = False
        effective["substrate_autonomy"] = False
    elif gate_state == "THROTTLED":
        reasons.append("throttled_gate")
        effective["document_authoring_autonomy"] = False
        effective["operator_contact_autonomy"] = False
        effective["third_party_contact_autonomy"] = False
        effective["substrate_autonomy"] = False

    if coherence < 0.2:
        reasons.append("critical_low_coherence")
        effective["cognitive_autonomy"] = False
        effective["repository_autonomy"] = False
        effective["document_authoring_autonomy"] = False
        effective["operator_contact_autonomy"] = False
        effective["third_party_contact_autonomy"] = False
        effective["substrate_autonomy"] = False
    elif coherence < 0.4:
        reasons.append("low_coherence")
        effective["document_authoring_autonomy"] = False
        effective["operator_contact_autonomy"] = False
        effective["third_party_contact_autonomy"] = False
        effective["substrate_autonomy"] = False

    if governance_tier in {"RECOVERY", "CRITICAL"}:
        reasons.append(f"governance_{governance_tier.lower()}")
        effective["document_authoring_autonomy"] = False
        effective["operator_contact_autonomy"] = False
        effective["third_party_contact_autonomy"] = False
        effective["substrate_autonomy"] = False

    # The freedom ladder never self-authorizes these by default.
    if not configured.get("operator_contact_autonomy", False):
        effective["third_party_contact_autonomy"] = False
    if not configured.get("cognitive_autonomy", False):
        effective["repository_autonomy"] = False
        effective["document_authoring_autonomy"] = False

    return {
        "configured": configured,
        "effective": effective,
        "coherence": coherence,
        "gate_state": gate_state,
        "governance_tier": governance_tier,
        "narrowing_reasons": reasons,
    }


def feature_enabled(policy: Optional[dict[str, Any]], feature: str) -> bool:
    if not policy:
        return False
    effective = dict(policy.get("effective") or {})
    return bool(effective.get(feature))


def contact_target_allowed(policy: Optional[dict[str, Any]], person_key: str) -> bool:
    norm = str(person_key or "").strip().lower()
    if not norm:
        return False
    if norm == "operator":
        return feature_enabled(policy, "operator_contact_autonomy")
    return feature_enabled(policy, "third_party_contact_autonomy")

