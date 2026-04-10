"""
governance_adapter.py
Unified governance surface routing and rollout semantics.
"""

from __future__ import annotations

import time
from typing import Any

from config import settings  # type: ignore


ALLOW = "allow"
SHADOW_ROUTE = "shadow-route"
ENFORCE_BLOCK = "enforce-block"

_DEFAULT_SURFACES = {
    "generation",
    "actuation",
    "messaging",
    "identity_corrections",
    "manifold_writes",
    "rolodex_writes",
    "entity_writes",
}

_SURFACE_ALIASES = {
    "identity": "identity_corrections",
    "identity_correction": "identity_corrections",
    "message": "messaging",
    "messages": "messaging",
    "manifold": "manifold_writes",
    "rolodex": "rolodex_writes",
    "entity": "entity_writes",
    "entities": "entity_writes",
}


def _csv(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _norm_surface(surface: str) -> str:
    key = str(surface or "").strip().lower()
    return _SURFACE_ALIASES.get(key, key)


def configured_surfaces() -> set[str]:
    raw = getattr(settings, "GOVERNANCE_ENFORCEMENT_SURFACES", "")
    vals = {_norm_surface(v) for v in _csv(str(raw))}
    vals.discard("")
    return vals or set(_DEFAULT_SURFACES)


def in_scope(surface: str) -> bool:
    return _norm_surface(surface) in configured_surfaces()


def soft_mode_active(governance_policy: dict[str, Any] | None) -> bool:
    if str(getattr(settings, "IIT_MODE", "advisory") or "advisory").strip().lower() == "soft":
        return True
    return bool((governance_policy or {}).get("applied", False))


def should_apply_surface_policy(surface: str, governance_policy: dict[str, Any] | None) -> bool:
    if not in_scope(surface):
        return False
    return soft_mode_active(governance_policy)


def route_for_surface(
    surface: str,
    *,
    governance_policy: dict[str, Any] | None = None,
    rrd2_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_surface = _norm_surface(surface)
    scoped = in_scope(normalized_surface)
    soft_active = soft_mode_active(governance_policy)

    phase = str((rrd2_gate or {}).get("phase") or getattr(settings, "RRD2_ROLLOUT_PHASE", "A") or "A").strip().upper()
    would_block = bool((rrd2_gate or {}).get("would_block", False))
    enforce_block = bool((rrd2_gate or {}).get("enforce_block", False))

    route = ALLOW
    reasons: list[str] = []

    freeze_until = float((governance_policy or {}).get("freeze_until") or 0.0)
    if freeze_until and time.time() < freeze_until:
        route = ENFORCE_BLOCK if soft_active else SHADOW_ROUTE
        reasons.append("governance_freeze_active")
        return {
            "surface": normalized_surface,
            "route": route,
            "phase": phase,
            "soft_active": soft_active,
            "scoped": scoped,
            "reasons": reasons,
        }

    if not scoped:
        reasons.append("surface_not_in_scope")
        return {
            "surface": normalized_surface,
            "route": route,
            "phase": phase,
            "soft_active": soft_active,
            "scoped": scoped,
            "reasons": reasons,
        }

    if would_block and phase in {"B", "C"}:
        route = SHADOW_ROUTE
        reasons.append("rrd2_would_block")

    if enforce_block and phase == "C":
        route = ENFORCE_BLOCK if soft_active else SHADOW_ROUTE
        reasons.append("rrd2_enforce_block")
        if not soft_active:
            reasons.append("soft_mode_inactive_downgraded_to_shadow")

    if soft_active:
        reasons.append("soft_mode_active")
    else:
        reasons.append("soft_mode_inactive")

    return {
        "surface": normalized_surface,
        "route": route,
        "phase": phase,
        "soft_active": soft_active,
        "scoped": scoped,
        "reasons": reasons,
    }


def actuation_filter(
    tags: list[dict[str, Any]],
    *,
    governance_policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not should_apply_surface_policy("actuation", governance_policy):
        return list(tags)

    act_policy = dict((governance_policy or {}).get("actuation") or {})
    allowlist = [str(v).strip().lower() for v in (act_policy.get("allowlist") or []) if str(v).strip()]
    denylist = [str(v).strip().lower() for v in (act_policy.get("denylist") or []) if str(v).strip()]

    if not allowlist:
        allowlist = ["*"]

    out: list[dict[str, Any]] = []
    wildcard = "*" in allowlist
    for tag in tags:
        action = str(tag.get("action") or "").strip().lower()
        if not action:
            continue
        if action in denylist:
            continue
        if wildcard or action in allowlist:
            out.append(tag)
    return out


def generation_overrides(governance_policy: dict[str, Any] | None) -> dict[str, Any]:
    if not should_apply_surface_policy("generation", governance_policy):
        return {}
    return dict((governance_policy or {}).get("generation") or {})
