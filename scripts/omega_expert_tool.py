#!/usr/bin/env python3
"""
Repo-local expert guide for OMEGA4.

Purpose:
- expose a stable architecture overview outside chat history
- provide a fast read order for new operators/developers
- map core backend/frontend modules into operational slices
- trace a normal /ghost/chat turn end-to-end

Examples:
  python3 scripts/omega_expert_tool.py
  python3 scripts/omega_expert_tool.py overview
  python3 scripts/omega_expert_tool.py read-order --profile quick
  python3 scripts/omega_expert_tool.py module-map
  python3 scripts/omega_expert_tool.py chat-trace --json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class RefSpec:
    path: str
    needles: tuple[str, ...] = ()
    note: str = ""


def _ref(path: str, *needles: str, note: str = "") -> RefSpec:
    return RefSpec(path=path, needles=tuple(needle for needle in needles if needle), note=note)


def _find_line(path: Path, needles: tuple[str, ...]) -> int | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None

    if not needles:
        return 1 if path.exists() else None

    for needle in needles:
        for idx, line in enumerate(lines, start=1):
            if needle in line:
                return idx
    return 1 if path.exists() else None


def _resolve_ref(spec: RefSpec) -> dict[str, Any]:
    abs_path = ROOT / spec.path
    line = _find_line(abs_path, spec.needles)
    ref = f"{spec.path}:{line}" if line else spec.path
    return {
        "path": spec.path,
        "line": line,
        "ref": ref,
        "note": spec.note,
    }


def _resolve_refs(specs: list[RefSpec]) -> list[dict[str, Any]]:
    return [_resolve_ref(spec) for spec in specs]


def _overview_payload() -> dict[str, Any]:
    refs = _resolve_refs(
        [
            _ref("docs/TECHNICAL_NORTH_STAR.md", "## 2. North Star Statement", note="North-star intent and explicit non-claims."),
            _ref("docs/SYSTEM_DESIGN.md", "## 3. High-Level Architecture", note="Implementation architecture and runtime topology."),
            _ref("backend/main.py", '@app.post("/ghost/chat")', note="Primary operator chat entrypoint."),
            _ref("backend/ghost_api.py", "async def ghost_stream(", note="Turn engine: prompting, tools, follow-up rounds, streaming."),
            _ref("frontend/app.js", "const res = await originalFetch(`${API_BASE}/ghost/chat`", note="Browser send/receive loop for main chat."),
        ]
    )
    return {
        "section": "overview",
        "summary": (
            "OMEGA4 is a self-hosted autonomous-agent runtime for Ghost: chat, persistent memory, "
            "telemetry-driven state, governance controls, world-model tooling, and document authoring."
        ),
        "core_spine": (
            "browser -> /ghost/chat -> session/history/state assembly -> prompt build -> "
            "Gemini/tool rounds -> SSE stream -> persistence"
        ),
        "notes": [
            "This is not a single-purpose app. It is an operator console plus a continuously running agent stack.",
            "The repo explicitly treats IIT as advisory diagnostics, not proof of consciousness.",
            "Most of the themed language wraps concrete subsystems: memory, telemetry, governance, topology, and authoring.",
        ],
        "refs": refs,
    }


def _module_map_payload() -> dict[str, Any]:
    groups = [
        {
            "name": "Runtime And Orchestration",
            "summary": "Bootstraps services, owns the major routes, starts loops, and bridges stream output into SSE.",
            "refs": _resolve_refs(
                [
                    _ref("backend/main.py", '@app.post("/ghost/chat")', note="Route layer, session bootstrap, SSE wrapper."),
                    _ref("backend/config.py", "class Settings(BaseSettings):", note="Runtime contract via env vars."),
                    _ref("docker-compose.yml", "services:", note="Infra topology and backend container wiring."),
                ]
            ),
        },
        {
            "name": "Conversation And Prompting",
            "summary": "Owns turn execution, prompt assembly, model/tool rounds, and transcript persistence.",
            "refs": _resolve_refs(
                [
                    _ref("backend/ghost_api.py", "async def ghost_stream(", note="Turn controller and model/tool loop."),
                    _ref("backend/ghost_prompt.py", "def build_system_prompt(", note="Prompt builder for Ghost's runtime context."),
                    _ref("backend/memory.py", "async def save_message(", note="Transcript persistence."),
                ]
            ),
        },
        {
            "name": "Somatic And Telemetry State",
            "summary": "Transforms telemetry and ambient signals into Ghost's state, gate pressure, and regulation inputs.",
            "refs": _resolve_refs(
                [
                    _ref("backend/somatic.py", note="Somatic snapshot assembly and telemetry collection."),
                    _ref("backend/sensory_gate.py", note="Anomaly and gating support."),
                    _ref("backend/decay_engine.py", note="Affective decay/state persistence."),
                    _ref("backend/proprio_loop.py", note="Proprioceptive gate loop and pressure signals."),
                ]
            ),
        },
        {
            "name": "Memory Graph And Social Model",
            "summary": "Maintains session memory, people/entities, topology views, and world-model state.",
            "refs": _resolve_refs(
                [
                    _ref("backend/person_rolodex.py", note="People/contact memory and social facts."),
                    _ref("backend/neural_topology.py", note="3D graph construction from memory and entities."),
                    _ref("backend/entity_store.py", note="Place/thing/idea entity storage."),
                    _ref("backend/world_model.py", note="Structured world-model backend."),
                ]
            ),
        },
        {
            "name": "Governance And Diagnostics",
            "summary": "Tracks instability, governance policy, diagnostic mirrors, and observer-style reporting.",
            "refs": _resolve_refs(
                [
                    _ref("backend/governance_engine.py", note="Governance decision layer."),
                    _ref("backend/predictive_governor.py", note="Forward-looking instability detection."),
                    _ref("backend/iit_engine.py", note="Advisory IIT assessment layer."),
                    _ref("backend/observer_report.py", note="Observer report generation and artifacts."),
                ]
            ),
        },
        {
            "name": "Knowledge And Authoring",
            "summary": "Handles uploaded documents, Ghost-owned drafts, and TPCV repository content.",
            "refs": _resolve_refs(
                [
                    _ref("backend/document_store.py", note="Document ingestion and retrieval context."),
                    _ref("backend/ghost_authoring.py", note="Ghost-owned document mutation/versioning."),
                    _ref("backend/tpcv_repository.py", note="Research repository storage and summaries."),
                ]
            ),
        },
        {
            "name": "Frontend Operator Console",
            "summary": "Static console UI with chat streaming, telemetry panels, topology modal, and governance surfaces.",
            "refs": _resolve_refs(
                [
                    _ref("frontend/index.html", '<div class="main-layout">', note="UI shell and modal surface layout."),
                    _ref("frontend/app.js", "const res = await originalFetch(`${API_BASE}/ghost/chat`", note="Chat send/receive loop."),
                ]
            ),
        },
    ]
    return {
        "section": "module_map",
        "groups": groups,
    }


def _read_order_payload(profile: str) -> dict[str, Any]:
    if profile == "quick":
        steps = [
            {
                "order": 1,
                "title": "System Design",
                "minutes": 5,
                "focus": "Read runtime topology, high-level architecture, and subsystem sections first.",
                "refs": _resolve_refs(
                    [_ref("docs/SYSTEM_DESIGN.md", "## 3. High-Level Architecture", note="Implementation overview.")]
                ),
            },
            {
                "order": 2,
                "title": "Main Route Spine",
                "minutes": 8,
                "focus": "Read session bootstrap, history loading, /ghost/chat, and the SSE event generator.",
                "refs": _resolve_refs(
                    [
                        _ref("backend/main.py", "async def _prepare_chat_session(", note="Session bootstrap."),
                        _ref("backend/main.py", "async def _load_operator_chat_history(", note="History loading."),
                        _ref("backend/main.py", '@app.post("/ghost/chat")', note="Main route."),
                        _ref("backend/main.py", "async def event_generator():", note="SSE wrapper and final persistence."),
                    ]
                ),
            },
            {
                "order": 3,
                "title": "Turn Engine",
                "minutes": 10,
                "focus": "Read search/tool config, retry wrapper, recent action loading, and ghost_stream().",
                "refs": _resolve_refs(
                    [
                        _ref("backend/ghost_api.py", "async def load_recent_action_memory(", note="Recent-action continuity."),
                        _ref("backend/ghost_api.py", "def _search_config(", note="Search vs tool-call config."),
                        _ref("backend/ghost_api.py", "async def _generate_with_retry(", note="Gemini call wrapper."),
                        _ref("backend/ghost_api.py", "async def ghost_stream(", note="Main turn engine."),
                    ]
                ),
            },
            {
                "order": 4,
                "title": "Prompt Builder",
                "minutes": 4,
                "focus": "Read build_system_prompt() and skim the injected context sections it assembles.",
                "refs": _resolve_refs(
                    [_ref("backend/ghost_prompt.py", "def build_system_prompt(", note="Prompt layout and injected context.")]
                ),
            },
            {
                "order": 5,
                "title": "Frontend Receive Path",
                "minutes": 3,
                "focus": "Read the browser-side /ghost/chat fetch and SSE parser.",
                "refs": _resolve_refs(
                    [_ref("frontend/app.js", "const res = await originalFetch(`${API_BASE}/ghost/chat`", note="Chat stream receive loop.")]
                ),
            },
        ]
        total_minutes = 30
    else:
        steps = [
            {
                "order": 1,
                "title": "Technical Direction",
                "minutes": 6,
                "focus": "Read the North Star and System Design docs to separate engineering claims from repo mythology.",
                "refs": _resolve_refs(
                    [
                        _ref("docs/TECHNICAL_NORTH_STAR.md", "## 2. North Star Statement", note="Intent and non-claims."),
                        _ref("docs/SYSTEM_DESIGN.md", "## 3. High-Level Architecture", note="Concrete subsystem map."),
                    ]
                ),
            },
            {
                "order": 2,
                "title": "Route And Session Bootstrap",
                "minutes": 8,
                "focus": "Follow how the backend accepts a turn, normalizes sessions, and loads history.",
                "refs": _resolve_refs(
                    [
                        _ref("backend/main.py", "async def _prepare_chat_session(", note="Session creation and normalization."),
                        _ref("backend/main.py", "async def _load_operator_chat_history(", note="Session vs thread history."),
                        _ref("backend/main.py", '@app.post("/ghost/chat")', note="Chat route entrypoint."),
                    ]
                ),
            },
            {
                "order": 3,
                "title": "Turn Execution",
                "minutes": 12,
                "focus": "Understand prompting, search/tool config, follow-up rounds, and streamed output generation.",
                "refs": _resolve_refs(
                    [
                        _ref("backend/ghost_api.py", "def _search_config(", note="Search-grounded vs tool-calling mode."),
                        _ref("backend/ghost_api.py", "async def _generate_with_retry(", note="Model invocation and retry behavior."),
                        _ref("backend/ghost_api.py", "async def ghost_stream(", note="Multi-round generation and tool reconciliation."),
                    ]
                ),
            },
            {
                "order": 4,
                "title": "Prompt Composition",
                "minutes": 8,
                "focus": "Study how Ghost's self-model, somatic state, recent actions, memory, and documents become prompt context.",
                "refs": _resolve_refs(
                    [_ref("backend/ghost_prompt.py", "def build_system_prompt(", note="Prompt composition.")]
                ),
            },
            {
                "order": 5,
                "title": "Persistence",
                "minutes": 8,
                "focus": "Read session/message persistence and how durable memory differs from prompt-local context.",
                "refs": _resolve_refs(
                    [
                        _ref("backend/memory.py", "async def create_session(", note="Session creation."),
                        _ref("backend/memory.py", "async def ensure_session(", note="Session existence guard."),
                        _ref("backend/memory.py", "async def save_message(", note="Transcript writes."),
                        _ref("backend/memory.py", "async def load_session_history(", note="History reads."),
                    ]
                ),
            },
            {
                "order": 6,
                "title": "Telemetry And State",
                "minutes": 8,
                "focus": "Read how telemetry becomes somatic state and gate pressure.",
                "refs": _resolve_refs(
                    [
                        _ref("backend/somatic.py", note="Somatic snapshot assembly."),
                        _ref("backend/sensory_gate.py", note="Signal gating support."),
                        _ref("backend/decay_engine.py", note="Affective state persistence."),
                        _ref("backend/proprio_loop.py", note="Gate pressure/control loop."),
                    ]
                ),
            },
            {
                "order": 7,
                "title": "World Model",
                "minutes": 8,
                "focus": "Read the social/entity/topology layer once the core chat path is clear.",
                "refs": _resolve_refs(
                    [
                        _ref("backend/person_rolodex.py", note="Person/social memory."),
                        _ref("backend/neural_topology.py", note="Topology graph builder."),
                        _ref("backend/entity_store.py", note="Entity CRUD/state."),
                        _ref("backend/world_model.py", note="Structured world-model layer."),
                    ]
                ),
            },
            {
                "order": 8,
                "title": "Frontend Console",
                "minutes": 6,
                "focus": "Read the operator console after the backend path is familiar.",
                "refs": _resolve_refs(
                    [
                        _ref("frontend/index.html", '<div class="main-layout">', note="UI shell and panels."),
                        _ref("frontend/app.js", "const res = await originalFetch(`${API_BASE}/ghost/chat`", note="Stream receive/render logic."),
                    ]
                ),
            },
        ]
        total_minutes = sum(step["minutes"] for step in steps)

    return {
        "section": "read_order",
        "profile": profile,
        "total_minutes": total_minutes,
        "steps": steps,
    }


def _chat_trace_payload() -> dict[str, Any]:
    steps = [
        {
            "order": 1,
            "title": "Browser Sends Turn",
            "summary": "The main UI posts message, session_id, channel, and attachments to /ghost/chat.",
            "refs": _resolve_refs(
                [
                    _ref("frontend/app.js", "const res = await originalFetch(`${API_BASE}/ghost/chat`", note="Browser request."),
                    _ref("backend/main.py", '@app.post("/ghost/chat")', note="Backend route."),
                ]
            ),
        },
        {
            "order": 2,
            "title": "Session Bootstrap",
            "summary": "The backend normalizes the session id, creates a session when missing, and chooses session or thread history.",
            "refs": _resolve_refs(
                [
                    _ref("backend/main.py", "async def _prepare_chat_session(", note="Session bootstrap."),
                    _ref("backend/main.py", "async def _load_operator_chat_history(", note="History loader."),
                    _ref("backend/memory.py", "async def create_session(", note="Session create."),
                    _ref("backend/memory.py", "async def ensure_session(", note="Session ensure."),
                ]
            ),
        },
        {
            "order": 3,
            "title": "Parallel Context Load",
            "summary": "main.py loads monologues, recent actions, current somatic state, autonomy architecture, identity, subconscious recall, operator model, documents, and repository context.",
            "refs": _resolve_refs(
                [
                    _ref("backend/main.py", "monologues_task = asyncio.create_task(memory.get_monologue_buffer(limit=40))", note="Monologue load."),
                    _ref("backend/main.py", "recent_actions_task = asyncio.create_task(", note="Recent-action load."),
                    _ref("backend/main.py", "somatic_obj = build_somatic_snapshot", note="Somatic snapshot."),
                    _ref("backend/main.py", "subconscious_task = asyncio.create_task(", note="Identity and vector recall."),
                ]
            ),
        },
        {
            "order": 4,
            "title": "User Message Persistence",
            "summary": "The turn is persisted both as transcript history and as semantic memory before generation continues.",
            "refs": _resolve_refs(
                [
                    _ref("backend/main.py", 'await consciousness.remember(model_user_message, "conversation", memory._pool)', note="Semantic remember."),
                    _ref("backend/main.py", 'await memory.save_message(session_id, "user", persist_user_message)', note="Transcript write."),
                ]
            ),
        },
        {
            "order": 5,
            "title": "Prompt Assembly",
            "summary": "ghost_stream() calls build_system_prompt() with somatic state, recent thoughts, recent actions, architecture context, identity, documents, repository context, and more.",
            "refs": _resolve_refs(
                [
                    _ref("backend/ghost_api.py", "async def ghost_stream(", note="Turn engine entry."),
                    _ref("backend/ghost_api.py", "system_prompt = build_system_prompt(", note="Prompt assembly call."),
                    _ref("backend/ghost_prompt.py", "def build_system_prompt(", note="Prompt builder."),
                ]
            ),
        },
        {
            "order": 6,
            "title": "Model Call Selection",
            "summary": "The backend chooses either search-grounded Gemini generation or tool-calling mode; Gemini cannot combine Google Search and function calling in one request.",
            "refs": _resolve_refs(
                [
                    _ref("backend/ghost_api.py", "def _search_config(", note="Search vs tool-call config."),
                    _ref("backend/ghost_api.py", "async def _generate_with_retry(", note="Model wrapper."),
                    _ref("backend/ghost_api.py", "client.models.generate_content", note="Gemini invocation."),
                ]
            ),
        },
        {
            "order": 7,
            "title": "Multi-Round Reconciliation",
            "summary": "A turn can run multiple internal rounds: detect function calls, execute tools, execute actuation tags, append function responses, and ask Gemini for a same-turn follow-up.",
            "refs": _resolve_refs(
                [
                    _ref("backend/ghost_api.py", "for round_idx in range(max_total_rounds):", note="Bounded multi-round loop."),
                    _ref("backend/ghost_api.py", "types.Part.from_function_response", note="Tool outcome reinjection."),
                    _ref("backend/ghost_api.py", "tags = parse_actuation_tags(round_response_text)", note="Actuation tag handling."),
                    _ref("backend/ghost_api.py", "followup_prompt = _build_unified_followup_prompt(", note="Follow-up prompt."),
                ]
            ),
        },
        {
            "order": 8,
            "title": "SSE Streaming",
            "summary": "ghost_stream() yields text chunks and structured events; main.py wraps them into SSE token/event packets.",
            "refs": _resolve_refs(
                [
                    _ref("backend/ghost_api.py", "for i in range(0, len(words), chunk_size):", note="Chunked text yield."),
                    _ref("backend/ghost_api.py", '"event": "tts_ready"', note="Structured event emit."),
                    _ref("backend/main.py", 'yield {', note="SSE wrapper block in event_generator()."),
                    _ref("backend/main.py", '"event": "token"', note="Token event bridge."),
                ]
            ),
        },
        {
            "order": 9,
            "title": "Final Persistence",
            "summary": "After the stream completes, the backend saves the model reply, updates semantic memory, records operator-synthesis continuity, and emits auto-save.",
            "refs": _resolve_refs(
                [
                    _ref("backend/main.py", 'await memory.save_message(session_id, "model", display_text)', note="Transcript write."),
                    _ref("backend/main.py", 'await consciousness.remember(display_text, "conversation", memory._pool)', note="Semantic remember."),
                    _ref("backend/main.py", "operator_synthesis_loop.record_turn(session_id=session_id)", note="Operator synthesis continuity."),
                    _ref("backend/main.py", '"event": "auto_save"', note="Frontend save indicator event."),
                ]
            ),
        },
        {
            "order": 10,
            "title": "Browser Render",
            "summary": "The browser reads SSE events, appends token text live, handles done/error/tts_ready/morpheus/identity_update branches, and finalizes the rendered message.",
            "refs": _resolve_refs(
                [
                    _ref("frontend/app.js", "while (true) {", note="Chat stream loop."),
                    _ref("frontend/app.js", "if (currentEvent === 'token' && data.text) {", note="Token accumulation."),
                    _ref("frontend/app.js", "} else if (currentEvent === 'done' && data.session_id) {", note="Done handling."),
                    _ref("frontend/app.js", "if (!streamError && !morpheusIntercepted) {", note="Final render path."),
                ]
            ),
        },
    ]
    return {
        "section": "chat_trace",
        "steps": steps,
    }


def _format_refs(refs: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for ref in refs:
        text = f"- {ref['ref']}"
        note = str(ref.get("note") or "").strip()
        if note:
            text += f"  {note}"
        out.append(text)
    return out


def _print_overview(payload: dict[str, Any]) -> None:
    print("OVERVIEW")
    print(payload["summary"])
    print()
    print(f"Core spine: {payload['core_spine']}")
    print()
    print("Notes:")
    for line in payload["notes"]:
        print(f"- {line}")
    print()
    print("Key references:")
    for line in _format_refs(payload["refs"]):
        print(line)


def _print_module_map(payload: dict[str, Any]) -> None:
    print("MODULE MAP")
    for group in payload["groups"]:
        print()
        print(group["name"].upper())
        print(group["summary"])
        for line in _format_refs(group["refs"]):
            print(line)


def _print_read_order(payload: dict[str, Any]) -> None:
    print(f"READ ORDER ({payload['profile'].upper()} // {payload['total_minutes']} min)")
    for step in payload["steps"]:
        print()
        print(f"{step['order']}. {step['title']}  [{step['minutes']}m]")
        print(step["focus"])
        for line in _format_refs(step["refs"]):
            print(line)


def _print_chat_trace(payload: dict[str, Any]) -> None:
    print("CHAT TRACE")
    for step in payload["steps"]:
        print()
        print(f"{step['order']}. {step['title']}")
        print(step["summary"])
        for line in _format_refs(step["refs"]):
            print(line)


def _print_section(command: str, payload: dict[str, Any]) -> None:
    if command == "overview":
        _print_overview(payload)
        return
    if command == "module-map":
        _print_module_map(payload)
        return
    if command == "read-order":
        _print_read_order(payload)
        return
    if command == "chat-trace":
        _print_chat_trace(payload)
        return
    raise ValueError(f"Unknown command: {command}")


def _build_payload(command: str, *, profile: str) -> dict[str, Any]:
    if command == "overview":
        return _overview_payload()
    if command == "module-map":
        return _module_map_payload()
    if command == "read-order":
        return _read_order_payload(profile)
    if command == "chat-trace":
        return _chat_trace_payload()
    if command == "all":
        return {
            "section": "all",
            "overview": _overview_payload(),
            "read_order": _read_order_payload(profile),
            "module_map": _module_map_payload(),
            "chat_trace": _chat_trace_payload(),
        }
    raise ValueError(f"Unknown command: {command}")


def main() -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    parser = argparse.ArgumentParser(
        description="Repo-local expert guide for architecture, read order, module map, and /ghost/chat trace."
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("overview", parents=[common], help="Print high-level repo overview.")
    read_order = subparsers.add_parser("read-order", parents=[common], help="Print recommended file read order.")
    read_order.add_argument("--profile", choices=("quick", "full"), default="quick", help="Reading depth/profile.")
    subparsers.add_parser("module-map", parents=[common], help="Print grouped module map.")
    subparsers.add_parser("chat-trace", parents=[common], help="Trace one /ghost/chat turn end-to-end.")
    all_parser = subparsers.add_parser("all", parents=[common], help="Print all sections.")
    all_parser.add_argument("--profile", choices=("quick", "full"), default="quick", help="Read-order profile for the all view.")

    args = parser.parse_args()
    command = str(args.command or "all")
    profile = str(getattr(args, "profile", "quick") or "quick")
    payload = _build_payload(command, profile=profile)

    if bool(getattr(args, "json", False)):
        print(json.dumps(payload, indent=2))
        return 0

    if command == "all":
        _print_overview(payload["overview"])
        print()
        print()
        _print_read_order(payload["read_order"])
        print()
        print()
        _print_module_map(payload["module_map"])
        print()
        print()
        _print_chat_trace(payload["chat_trace"])
        return 0

    _print_section(command, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
