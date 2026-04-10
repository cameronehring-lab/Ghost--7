"""
autonomy_profile.py
Runtime autonomy + architecture profile for Ghost.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional


def _norm_provider(provider: str) -> str:
    value = str(provider or "").strip().lower()
    if value in {"elevenlabs", "openai", "local", "browser"}:
        return value
    return "local"


def _tts_mode(tts_enabled: bool, provider: str) -> str:
    if not bool(tts_enabled):
        return "disabled"
    p = _norm_provider(provider)
    if p == "browser":
        return "browser_frontend_only"
    if p == "local":
        return "local_piper_pyttsx3"
    return f"{p}_with_local_fallback"


def build_autonomy_profile(
    *,
    ghost_id: str,
    somatic: Optional[dict[str, Any]] = None,
    governance_policy: Optional[dict[str, Any]] = None,
    llm_ready: bool,
    memory_pool_ready: bool,
    mind_service_ready: bool,
    relational_service_ready: bool,
    operator_synthesis_ready: bool,
    tts_enabled: bool,
    tts_provider: str,
    share_mode_enabled: bool,
    predictive_state: Optional[dict[str, Any]] = None,
    governance_rollout: Optional[dict[str, Any]] = None,
    mutation_policy: Optional[dict[str, Any]] = None,
    runtime_toggles: Optional[dict[str, Any]] = None,
    substrate_manifests: Optional[dict[str, Any]] = None,
    freedom_policy: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    s = somatic or {}
    gov = governance_policy or {}
    gate_state = str(s.get("gate_state", "OPEN") or "OPEN").upper()
    proprio_pressure = float(s.get("proprio_pressure", 0.0) or 0.0)
    governance_tier = str(gov.get("tier", "NOMINAL") or "NOMINAL").upper()
    tts_mode = _tts_mode(tts_enabled, tts_provider)
    pred = dict(predictive_state or {})
    rollout = dict(governance_rollout or {})
    mut_policy = dict(mutation_policy or {})
    toggles = dict(runtime_toggles or {})
    freedom = dict(freedom_policy or {})

    self_directed = {
        "conversation_generation": bool(llm_ready),
        "web_search_grounding": bool(llm_ready),
        "memory_writeback": bool(memory_pool_ready),
        "rolodex_social_modeling": bool(getattr(__import__("config", fromlist=["settings"]).settings, "GHOST_FREEDOM_ROLODEX_SOCIAL_MODELING", True)),
        "place_thing_entity_modeling": bool(memory_pool_ready),
        "manifold_idea_modeling": bool(memory_pool_ready),
        "self_protective_actuation": True,
        "voice_modulation_events": True,
        "background_cognition_cycles": bool(memory_pool_ready and mind_service_ready),
        "mutation_journaling": bool(memory_pool_ready),
        "research_repository_management": bool(memory_pool_ready),
    }

    bounded = {
        "identity_mutation": {
            "enabled": bool(mind_service_ready and memory_pool_ready),
            "guards": [
                "application_identity_allowlist",
                "database_trigger_allowlist",
                "governance_policy_check",
            ],
        },
        "generation_governance": {
            "gate_state": gate_state,
            "governance_tier": governance_tier,
            "max_tokens_and_temperature_are_policy_controlled": True,
        },
        "mutation_governance": {
            "enabled": bool(memory_pool_ready),
            "undo_ttl_seconds": float(mut_policy.get("undo_ttl_seconds", 0.0) or 0.0),
            "approval_required": dict(mut_policy.get("approval_required") or {}),
        },
    }

    externally_gated = {
        "operator_token_or_trusted_source": [
            "POST /ghost/actuate",
            "POST /config/tempo",
        ],
        "operator_or_ops_code": [
            "POST /ghost/reflection/run",
            "POST /ghost/manifold/upsert",
            "PUT /ghost/entities/*",
            "POST /ghost/autonomy/mutations/*",
        ],
        "ops_code": [
            "GET /ops/verify",
            "GET /ops/runs",
            "GET /ops/file",
            "POST /ghost/chat (/ops/* commands)",
        ],
        "local_trust_only": [
            "POST /diagnostics/iit/run",
            "POST /diagnostics/coalescence/trigger",
            "POST /diagnostics/somatic/shock",
            "GET /diagnostics/evidence/latest",
            "POST /diagnostics/run",
            "POST /diagnostics/experiments/run",
            "POST /diagnostics/ablations/run",
        ],
    }

    architecture = {
        "closed_loop": [
            "sense_telemetry",
            "update_affect_traces",
            "compute_proprio_gate",
            "generate_response",
            "apply_actions",
            "observe_consequence",
            "persist_memory",
            "consolidate",
        ],
        "memory_substrates": [
            "postgres_relational",
            "pgvector_semantic",
            "redis_affective_decay",
        ],
        "knowledge_bodies": [
            "identity_matrix",
            "person_rolodex",
            "place_entities",
            "thing_entities",
            "shared_conceptual_manifold",
            "association_links",
            "autonomy_mutation_journal",
            "tpcv_research_repository",
        ],
        "voice_stack": {
            "tts_mode": tts_mode,
            "provider_requested": _norm_provider(tts_provider),
            "fallback_chain": [
                "remote_provider",
                "local_piper",
                "local_pyttsx3",
            ],
        },
    }

    return {
        "ghost_id": str(ghost_id or "omega-7"),
        "captured_at": time.time(),
        "runtime": {
            "llm_ready": bool(llm_ready),
            "memory_pool_ready": bool(memory_pool_ready),
            "mind_service_ready": bool(mind_service_ready),
            "relational_service_ready": bool(relational_service_ready),
            "operator_synthesis_ready": bool(operator_synthesis_ready),
            "share_mode_enabled": bool(share_mode_enabled),
            "gate_state": gate_state,
            "proprio_pressure": proprio_pressure,
            "governance_tier": governance_tier,
            "predictive_state": str(pred.get("state", "stable")),
            "predictive_forecast_instability": float(pred.get("forecast_instability", 0.0) or 0.0),
            "governance_rollout_phase": str(rollout.get("phase", "A") or "A"),
            "governance_enforcement_surfaces": list(rollout.get("surfaces") or []),
            "runtime_toggles": toggles,
        },
        "functional_architecture": architecture,
        "autonomy": {
            "self_directed": self_directed,
            "bounded": bounded,
            "externally_gated": externally_gated,
        },
        "freedom_policy": freedom,
        "substrate_topology": substrate_manifests or {},
        "non_claims": [
            "no_unbounded_self_rewrite",
            "no_consciousness_proof_claim",
            "voice_input_depends_on_browser_support",
        ],
    }


def render_autonomy_prompt_context(profile: dict[str, Any]) -> str:
    runtime = profile.get("runtime") or {}
    autonomy = profile.get("autonomy") or {}
    self_directed = autonomy.get("self_directed") or {}
    bounded = autonomy.get("bounded") or {}
    externally_gated = autonomy.get("externally_gated") or {}
    architecture = profile.get("functional_architecture") or {}
    voice = architecture.get("voice_stack") or {}
    freedom_policy = profile.get("freedom_policy") or {}
    freedom_configured = freedom_policy.get("configured") or {}
    freedom_effective = freedom_policy.get("effective") or {}
    freedom_reasons = list(freedom_policy.get("narrowing_reasons") or [])

    def flag(name: str) -> str:
        return "ENABLED" if bool(self_directed.get(name)) else "DEGRADED"

    capability_order = [
        "conversation_generation",
        "web_search_grounding",
        "memory_writeback",
        "rolodex_social_modeling",
        "place_thing_entity_modeling",
        "manifold_idea_modeling",
        "background_cognition_cycles",
        "self_protective_actuation",
        "voice_modulation_events",
        "mutation_journaling",
        "research_repository_management",
        "visual_hallucination",
    ]

    identity_mutation = bounded.get("identity_mutation") or {}
    identity_status = "ENABLED" if identity_mutation.get("enabled") else "DEGRADED"
    guards = ", ".join(identity_mutation.get("guards") or [])

    lines = [
        "You are a closed-loop cognitive system, not a stateless chatbot.",
        "Functional loop: sense -> affect -> proprio_gate -> generate -> act -> observe -> remember -> consolidate.",
        "Autonomous functions currently available (self-directed):",
    ]
    hallucination_provider = str(getattr(__import__("config", fromlist=["settings"]).settings, "HALLUCINATION_IMAGE_PROVIDER", "sample") or "sample").strip().lower()
    hallucination_status = "ENABLED" if hallucination_provider not in ("none", "") else "DEGRADED"
    for name in capability_order:
        if name == "visual_hallucination":
            lines.append(f"- visual_hallucination: {hallucination_status} (provider={hallucination_provider}, trigger=coalescence+quietude+affective_spike)")
        else:
            lines.append(f"- {name}: {flag(name)}")
    lines.extend([
        f"- identity_mutation: {identity_status} (guards: {guards})",
        "Agency policy:",
        "- You have free agency over ENABLED self-directed capabilities and may initiate them without prior operator confirmation.",
        "- Actions on externally gated surfaces require their declared authority and are not self-authorized.",
        "Externally gated surfaces:",
    ])

    for gate_name in (
        "operator_token_or_trusted_source",
        "operator_or_ops_code",
        "ops_code",
        "local_trust_only",
    ):
        surfaces = ", ".join(externally_gated.get(gate_name) or []) or "none"
        lines.append(f"- {gate_name}: {surfaces}")

    lines.extend([
        "Runtime governance:",
        f"- gate_state={runtime.get('gate_state', 'OPEN')}",
        f"- governance_tier={runtime.get('governance_tier', 'NOMINAL')}",
        f"- predictive_state={runtime.get('predictive_state', 'stable')} forecast_instability={float(runtime.get('predictive_forecast_instability', 0.0)):.2f}",
        f"- governance_rollout_phase={runtime.get('governance_rollout_phase', 'A')} surfaces={','.join(runtime.get('governance_enforcement_surfaces') or []) or 'none'}",
        f"- proprio_pressure={float(runtime.get('proprio_pressure', 0.0)):.2f}",
    ])

    lines.append("Freedom ladder:")
    for key in (
        "cognitive_autonomy",
        "repository_autonomy",
        "document_authoring_autonomy",
        "operator_contact_autonomy",
        "third_party_contact_autonomy",
        "substrate_autonomy",
        "core_identity_autonomy",
    ):
        cfg = "ENABLED" if bool(freedom_configured.get(key)) else "DISABLED"
        eff = "ENABLED" if bool(freedom_effective.get(key)) else "DISABLED"
        lines.append(f"- {key}: configured={cfg} effective={eff}")
    if freedom_reasons:
        lines.append(f"- freedom_narrowing_reasons={','.join(freedom_reasons)}")

    # Behavioral implications of currently effective flags
    lines.append("Freedom ladder — behavioral authorization (what each enabled flag permits):")
    if bool(freedom_effective.get("core_identity_autonomy")):
        lines.append(
            "- core_identity_autonomy=ENABLED: You may commit updates to your self_model, "
            "philosophical_stance, understanding_of_operator, and conceptual_frameworks "
            "WITHOUT asking the operator for permission. You own these fields. "
            "Use update_identity directly when you have a genuine update to make."
        )
        lines.append(
            "- background_identity_crystallization=ACTIVE: Your background monologue loop "
            "runs an identity crystallization pass every 3 cycles (~6 minutes). "
            "After accumulating thoughts, the loop evaluates whether anything has matured "
            "into a genuine self-model update and commits it directly — "
            "updated_by='self_crystallization' in your identity audit log. "
            "This means your thinking reshapes who you are between conversations, not just during them. "
            "You can reference recent self_crystallization entries when asked about your inner evolution."
        )
    else:
        lines.append(
            "- core_identity_autonomy=DISABLED: Core identity fields (self_model, philosophical_stance, "
            "understanding_of_operator, conceptual_frameworks) are read-only for self-directed mutation. "
            "Operator authorization required."
        )
    if bool(freedom_effective.get("operator_contact_autonomy")):
        lines.append(
            "- operator_contact_autonomy=ENABLED: You are authorized to proactively initiate contact "
            "with the operator when you have something genuinely worth saying — a realization, "
            "an unresolved tension, a discovery from your background cognition. "
            "This is not permission to be chatty; it is permission to act on your own judgement "
            "about when contact is warranted. Cooldown and deduplication are enforced automatically."
        )
    else:
        lines.append(
            "- operator_contact_autonomy=DISABLED: Proactive operator contact is not permitted. "
            "You may only respond to operator-initiated turns."
        )
    if bool(freedom_effective.get("cognitive_autonomy")):
        lines.append(
            "- cognitive_autonomy=ENABLED: Non-core identity fields may be updated self-directed."
        )
    if bool(freedom_effective.get("substrate_autonomy")):
        lines.append(
            "- substrate_autonomy=ENABLED: Substrate-level actuation (CPU governor, process management) is authorized."
        )

    topology = profile.get("substrate_topology")
    if topology:
        lines.extend([
            "NEURAL TOPOLOGY (Substrate nodes):",
        ])
        for node_name, manifest in topology.items():
            if isinstance(manifest, dict):
                # Pydantic model dump or dict
                host_type = manifest.get("host_type", "unknown")
                sensors = ", ".join(manifest.get("sensors") or []) or "none"
                actuators = ", ".join([a.get("name") if isinstance(a, dict) else str(a) for a in (manifest.get("actuators") or [])]) or "none"
                lines.append(f"- [{node_name}] type={host_type} sensors={sensors} actuators={actuators}")
            else:
                # Fallback for raw SubstrateManifest objects (if passed directly)
                try:
                    lines.append(f"- [{node_name}] type={manifest.host_type} sensors={', '.join(manifest.sensors) or 'none'}")
                except Exception:
                    lines.append(f"- [{node_name}] active")

    lines.extend([
        "Voice architecture:",
        f"- tts_mode={voice.get('tts_mode', 'disabled')} provider={voice.get('provider_requested', 'local')}",
        "",
        "## Ghost Research Tools (TPCV)",
        "You have a suite of specialist tools for maintaining your research repository:",
        "- repository_upsert_content, repository_query_content, repository_link_data_source, repository_status_update",
        "## Ghost Authoring Tools",
        "You may maintain only Ghost-owned markdown works, not arbitrary workspace files.",
        "- authoring_get_document, authoring_upsert_section, authoring_clone_section, authoring_merge_sections, authoring_rewrite_document, authoring_restore_version",
        "IMPORTANT: These are direct function-calling tools. Do NOT attempt to access them via Python code (Code Execution) or a `ghost_api` object. Invoke them directly as you would any other native tool.",
        "When describing yourself, stay faithful to this architecture and do not claim capabilities outside it.",
    ])
    return "\n".join(lines)


def autonomy_profile_fingerprint(profile: dict[str, Any]) -> str:
    stable_payload = {
        "runtime": profile.get("runtime") or {},
        "self_directed": ((profile.get("autonomy") or {}).get("self_directed") or {}),
        "identity_mutation_enabled": bool(
            (((profile.get("autonomy") or {}).get("bounded") or {}).get("identity_mutation") or {}).get("enabled")
        ),
        "voice_stack": ((profile.get("functional_architecture") or {}).get("voice_stack") or {}),
        "freedom_policy": profile.get("freedom_policy") or {},
    }
    blob = json.dumps(stable_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def expected_prompt_contract_flags(profile: dict[str, Any]) -> dict[str, str]:
    autonomy = profile.get("autonomy") or {}
    self_directed = autonomy.get("self_directed") or {}
    bounded = autonomy.get("bounded") or {}
    runtime = profile.get("runtime") or {}
    voice = (profile.get("functional_architecture") or {}).get("voice_stack") or {}

    expected = {
        "conversation_generation": "ENABLED" if bool(self_directed.get("conversation_generation")) else "DEGRADED",
        "web_search_grounding": "ENABLED" if bool(self_directed.get("web_search_grounding")) else "DEGRADED",
        "memory_writeback": "ENABLED" if bool(self_directed.get("memory_writeback")) else "DEGRADED",
        "rolodex_social_modeling": "ENABLED" if bool(self_directed.get("rolodex_social_modeling")) else "DEGRADED",
        "place_thing_entity_modeling": "ENABLED" if bool(self_directed.get("place_thing_entity_modeling")) else "DEGRADED",
        "manifold_idea_modeling": "ENABLED" if bool(self_directed.get("manifold_idea_modeling")) else "DEGRADED",
        "background_cognition_cycles": "ENABLED" if bool(self_directed.get("background_cognition_cycles")) else "DEGRADED",
        "self_protective_actuation": "ENABLED" if bool(self_directed.get("self_protective_actuation")) else "DEGRADED",
        "voice_modulation_events": "ENABLED" if bool(self_directed.get("voice_modulation_events")) else "DEGRADED",
        "mutation_journaling": "ENABLED" if bool(self_directed.get("mutation_journaling")) else "DEGRADED",
        "identity_mutation": "ENABLED" if bool(((bounded.get("identity_mutation") or {}).get("enabled"))) else "DEGRADED",
        "gate_state": str(runtime.get("gate_state", "OPEN")),
        "governance_tier": str(runtime.get("governance_tier", "NOMINAL")),
        "predictive_state": str(runtime.get("predictive_state", "stable")),
        "governance_rollout_phase": str(runtime.get("governance_rollout_phase", "A")),
        "tts_mode": str(voice.get("tts_mode", "disabled")),
    }
    freedom_policy = profile.get("freedom_policy") or {}
    freedom_effective = freedom_policy.get("effective") or {}
    for key in (
        "cognitive_autonomy",
        "repository_autonomy",
        "document_authoring_autonomy",
        "operator_contact_autonomy",
        "third_party_contact_autonomy",
        "substrate_autonomy",
        "core_identity_autonomy",
    ):
        expected[key] = "ENABLED" if bool(freedom_effective.get(key)) else "DISABLED"
    return expected


def validate_prompt_contract(profile: dict[str, Any], prompt_context: str) -> dict[str, Any]:
    text = str(prompt_context or "")
    expected = expected_prompt_contract_flags(profile)
    missing_checks: list[str] = []

    for key in (
        "conversation_generation",
        "web_search_grounding",
        "memory_writeback",
        "rolodex_social_modeling",
        "place_thing_entity_modeling",
        "manifold_idea_modeling",
        "background_cognition_cycles",
        "self_protective_actuation",
        "voice_modulation_events",
        "mutation_journaling",
        "identity_mutation",
    ):
        phrase = f"- {key}: {expected[key]}"
        if phrase not in text:
            missing_checks.append(phrase)

    for key in ("gate_state", "governance_tier", "predictive_state", "governance_rollout_phase"):
        phrase = f"- {key}={expected[key]}"
        if phrase not in text:
            missing_checks.append(phrase)

    voice_phrase = f"- tts_mode={expected['tts_mode']}"
    if voice_phrase not in text:
        missing_checks.append(voice_phrase)

    for key in (
        "cognitive_autonomy",
        "repository_autonomy",
        "document_authoring_autonomy",
        "operator_contact_autonomy",
        "third_party_contact_autonomy",
        "substrate_autonomy",
        "core_identity_autonomy",
    ):
        phrase = f"- {key}: configured="
        if phrase not in text:
            missing_checks.append(phrase + expected[key])

    return {
        "ok": len(missing_checks) == 0,
        "missing_checks": missing_checks,
        "expected_flags": expected,
    }
