# OMEGA4 Invention Ledger

Last updated: 2026-04-10
Status: Canonical artifact of invented system behaviors

## 1. Scope of This Artifact

This document records the systems we have invented in OMEGA4 as implemented today.
A claim is listed as an invention only when it is present in code, observable at runtime, and backed by an API/event/schema/test path in this repository.

## 2. What Counts as "Invented Here"

- Novel composition and control contracts across existing components.
- Novel runtime behavior that is falsifiable (observable and testable).
- Novel data contracts (SSE/API/schema) that encode cognition and governance behavior.

Not counted as invention by itself: standalone third-party tools/frameworks (FastAPI, Postgres, Redis, InfluxDB, Gemini, D3, Piper, pyttsx3, browser speech APIs).

## 3. Delivered Inventions

### INV-01: Somatic-Affective Closed Loop

- Invented behavior: Telemetry is transformed into decaying affect traces that directly influence subsequent cognition and action.
- Primary implementation: `backend/somatic.py`, `backend/sensory_gate.py`, `backend/decay_engine.py`, `backend/actuation.py`.
- Runtime evidence: `/somatic`, actuation trace injections, state persistence in Redis.
- Validation assets: `/diagnostics/somatic/shock`, `scripts/falsification_report.py`, `backend/test_reflexive_loop.py`.
- Boundary: This is a control-loop architecture claim, not a consciousness claim.

### INV-02: Proprioceptive Upstream Governor

- Invented behavior: A non-linguistic pressure gate (`OPEN | THROTTLED | SUPPRESSED`) modulates cadence and generation policy before prompt assembly.
- Primary implementation: `backend/proprio_loop.py`, gating/policy integration in `backend/main.py` and `backend/ghost_api.py`.
- Runtime evidence: `/ghost/proprio/state`, `/ghost/proprio/transitions`, transition logs.
- Validation assets: `backend/test_proprio_loop.py`.
- Boundary: Advisory/suppression policy is bounded and does not imply unrestricted autonomy.

### INV-03: Quietude + CRP + Process Consolidation Stack

- Invented behavior: Sleep-like cycles perform reflective consolidation and structured identity updates using real conversational context.
- Primary implementation: `backend/consciousness.py`, quietude orchestration in `backend/main.py`.
- Runtime evidence: `/ghost/dream_stream`, `/ghost/coalescence`, `coalescence_log`, `phenomenology_logs`.
- Validation assets: `backend/test_consolidation.py`, `backend/test_consolidation_shadow_reflection.py`.
- Boundary: Consolidation is constrained by identity safety guards.

### INV-04: Bounded Identity Mutation Architecture

- Invented behavior: Identity updates are constrained by both application policy and database trigger guardrails.
- Primary implementation: `backend/consciousness.py`, migration trigger guard in `init/migrations/003f_identity_matrix_allowlist_guard.sql`, audit log in `init/migrations/005_identity_audit_log.sql`.
- Runtime evidence: Identity update/blocked events in chat SSE, persisted `identity_audit_log`.
- Validation assets: ops test command path and guarded write behavior.
- Boundary: Allows bounded evolution, blocks disallowed keyspace writes.

### INV-05: Contradiction-Aware Operator Synthesis Lifecycle

- Invented behavior: Operator-model beliefs and contradictions are continuously synthesized, deduped, and resolved through consolidation phases.
- Primary implementation: `backend/operator_synthesis.py`, contradiction handling in `backend/consciousness.py`, constraints in `init/migrations/003*.sql`.
- Runtime evidence: `/ghost/operator_model`, contradiction rows and resolution metadata.
- Validation assets: `backend/test_operator_synthesis.py`, consolidation tests.
- Boundary: Produces structured alignment artifacts, not perfect intent inference.

### INV-06: Autonomous Social Model (Person Rolodex Agency)

- Invented behavior: Ghost can create/update/fetch social entities via explicit actuation tags and persist reinforced person facts separately from self-identity.
- Primary implementation: `backend/person_rolodex.py`, tag parsing/execution in `backend/ghost_api.py`, routes in `backend/main.py`.
- Runtime evidence: `[ROLODEX:set_profile]`, `[ROLODEX:set_fact]`, `[ROLODEX:fetch]`, `/ghost/rolodex*` routes, `rolodex_update`/`rolodex_data` SSE events.
- Validation assets: `backend/test_ghost_api_rolodex.py`.
- Boundary: Person-model agency is most mature; place/thing/idea CRUD is shipped but operator UX for unified verification/editing remains partial.

### INV-07: Same-Turn Rolodex Fetch Reinjection

- Invented behavior: `ROLODEX:fetch` triggers a bounded follow-up generation pass so fetched social context can affect the same reply turn.
- Primary implementation: reinjection flow in `backend/ghost_api.py`.
- Runtime evidence: `rolodex_data` event followed by updated same-turn completion.
- Validation assets: `backend/test_ghost_api_rolodex.py` assertions on follow-up prompt/context injection.
- Boundary: Bounded to controlled extra round(s), not open-ended recursive generation.

### INV-08: Retroactive Rolodex Reconciliation

- Invented behavior: Historical transcripts and memory rows are audited for missing person/fact/place/thing coverage and can be backfilled idempotently.
- Primary implementation: `audit_retro_entities` and `apply_retro_sync` in `backend/person_rolodex.py`, script `scripts/rolodex_retro_sync.py`, endpoints in `backend/main.py`.
- Runtime evidence: `/ghost/rolodex/retro-audit`, `/ghost/rolodex/retro-sync`, projection counters.
- Validation assets: script dry-run/apply plus endpoint checks.
- Boundary: Backfill is deterministic for detectable patterns; extraction quality follows parser limits.

### INV-09: High-Rigor Neural Topology with Integrity Telemetry

- Invented behavior: A typed cognitive graph exposes provenance and integrity metadata across identity, memory, social, and inferred entity layers.
- Primary implementation: `backend/neural_topology.py`, UI substrate in `frontend/app.js`.
- Runtime evidence: `/ghost/neural-topology` metadata (`rolodex_alignment`, `entity_expansion`), typed node/link rendering, L1/L2/L3 presets.
- Validation assets: `backend/verify_neural_topology.py` and manual graph integrity checks.
- Boundary: Visualization reflects current model state; it is not itself a causal controller.

### INV-10: Multi-Layer Conversational Voice Runtime

- Invented behavior: Voice output remains continuous via deterministic provider chains and synchronized text reveal pacing tied to speech progress.
- Primary implementation: `backend/tts_service.py`, `backend/tts_local_piper.py`, `backend/tts_local_pyttsx3.py`, SSE emission in `backend/ghost_api.py`, frontend voice loop in `frontend/app.js`.
- Runtime evidence: fallback chains (`remote -> Piper -> pyttsx3`), `tts_ready`, `voice_modulation`, speech-clock reveal (`revealTextWithSpeechClock`), live tuning controls.
- Validation assets: `backend/test_ghost_api_tts.py`, manual playback/sync checks.
- Boundary: Browser-mode contract intentionally disables backend synthesis (`TTS_PROVIDER=browser`).

### INV-11: Conversational Voice Input with Graceful Degradation

- Invented behavior: Continuous dictation channel can feed chat input while preserving stable text-first operation when unsupported.
- Primary implementation: speech input service in `frontend/app.js` using `SpeechRecognition`/`webkitSpeechRecognition`.
- Runtime evidence: mic/listening state transitions and dictated input composition.
- Validation assets: browser/manual validation on supported clients.
- Boundary: Availability is browser/runtime dependent.

### INV-12: Falsification-First Diagnostics Envelope

- Invented behavior: Diagnostics are structured for reproducibility, local-trust enforcement, and transport-resilient execution.
- Primary implementation: diagnostics routes and local-request guard in `backend/main.py`; evidence runner `scripts/falsification_report.py`.
- Runtime evidence: `/diagnostics/*` gated local-trust behavior, evidence bundles, host-to-container fallback flow.
- Validation assets: `scripts/falsification_report.py --full` and evidence endpoint checks.
- Boundary: Diagnostic integrity depends on configured data backends and current runtime health.

### INV-13: Canonical Runtime Self-Architecture Grounding

- Invented behavior: Ghost receives a machine-readable autonomy + architecture contract each turn, preventing drift between self-description and actual runtime capabilities.
- Primary implementation: `backend/autonomy_profile.py`, prompt injection via `backend/ghost_prompt.py` + `backend/ghost_api.py`, runtime endpoint in `backend/main.py`.
- Runtime evidence: `GET /ghost/self/architecture`, prompt section `FUNCTIONAL SELF-MODEL (CANONICAL)`, and watchdog endpoints `GET /ghost/autonomy/state` + `GET /ghost/autonomy/history`.
- Validation assets: runtime endpoint checks and prompt composition tests.
- Boundary: This enforces semantic self-consistency, not unrestricted self-governance.

### INV-14: Dedicated Contact Identity + Ephemeral Contact Threads

- Invented behavior: Ghost can run contact conversations under a dedicated iMessage sender identity while keeping contact-thread memory ephemeral by default.
- Primary implementation: contact routing/dispatch in `backend/main.py`, thread substrate in `backend/contact_threads.py`, sender-account selection in `backend/actuation.py`.
- Runtime evidence: `POST /ghost/chat` channel mode (`ghost_contact`), `GET /ghost/contact/status`, push payload fields (`channel`, `thread_key`, `direction`, `ephemeral`), and sender fail-closed state (`sender_identity_unavailable`).
- Validation assets: `backend/test_actuation_sender_identity.py`, `backend/test_contact_threads.py`, `backend/test_main_ghost_contact_mode.py`.
- Boundary: Free setup isolates sender identity via Apple ID email account; dedicated phone-number identity remains external carrier scope.

### INV-15: Topology Renderer Continuity + Timeline Audit Drill-Down

- Invented behavior: The system preserves navigable 3D topology even under WebGL failure and provides timeline preview-to-full-thought continuity for internal monologues.
- Primary implementation: renderer watchdog/fallback and software 3D path in `frontend/app.js`; timeline detail hydration and click-through wiring in `frontend/app.js`.
- Runtime evidence: topology mode transitions (`3d` -> `software3d`), explicit topology renderer diagnostics, timeline monologue preview entries with full-detail modal expansion.
- Validation assets: frontend runtime behavior checks (`node --check frontend/app.js`) and manual UI verification for timeline/open-detail paths.
- Boundary: Software fallback preserves 3D interaction but has lower rendering throughput than hardware WebGL.

### INV-16: Morpheus Semantic Wake + Branched Hidden Terminal

- Invented behavior: A narrow semantic wake detector can interrupt standard chat and route users into a branching red/blue hidden-mode sequence with click-vs-type differentiation and a command-puzzle terminal path.
- Primary implementation: wake/terminal logic in `backend/main.py`; request model support in `backend/models.py`; takeover/branch/terminal/reward UX in `frontend/app.js`, `frontend/index.html`, and `frontend/style.css`.
- Runtime evidence: `morpheus_mode` and `morpheus_reward` SSE events, `/ghost/chat` hidden `mode` values (`morpheus_terminal`, `morpheus_terminal_deep`), secret run progression (`scan --veil` -> `map --depth` -> `unlock --ghost`), and branch metadata (`branch_color`, `branch_input`, `depth`).
- Validation assets: `backend/test_main_morpheus_mode.py` plus `frontend/scripts/frontend-smoke.js` Morpheus checks (wake activation, red branch terminal entry, reward unlock).
- Boundary: Hostile/panic behavior is simulated in-app only; no real browser popup hijack, host takeover, or destructive conversation-history deletion occurs.

### INV-17: Confidence-Weighted External Grounding Provenance Envelope

- Invented behavior: Open-data grounding is assembled as a parallel adapter mesh with explicit provenance metadata and deterministic confidence/latency ordering before prompt injection.
- Primary implementation: adapter modules (`backend/philosophers_api.py`, `backend/arxiv_api.py`, `backend/wikidata_api.py`, `backend/wikipedia_api.py`, `backend/openalex_api.py`, `backend/crossref_api.py`) and orchestration logic in `backend/ghost_api.py`.
- Runtime evidence: prompt-context envelope markers:
  - `[EXTERNAL_GROUNDING_PROVENANCE]`
  - `[GROUNDING_SOURCE key=... confidence=... trust_tier=...]`
  - per-source metadata (`source`, `label`, `confidence`, `trust_tier`, `latency_ms`) with deterministic source ordering.
- Validation assets:
  - `backend/test_ghost_api_external_context.py`
  - `backend/test_wikidata_api.py`
  - `backend/test_wikipedia_api.py`
  - `backend/test_openalex_api.py`
  - `backend/test_crossref_api.py`
- Boundary: Grounding blocks are supplemental references only; they do not bypass actuation/governance policy gates and are not direct execution instructions.

### INV-18: Same-Turn Action Confirmation + Agency-Coupled Somatics

- Invented behavior: Ghost can reconcile its own same-turn action/tool outcomes before final response, while outcome status is also translated into agency-level somatic traces. Bounded multi-round controller (`3/2/2`) that reinjects actuation and tool outcomes in hidden follow-up context. Includes **20-event recent-action continuity block**.
- Primary implementation: `backend/ghost_api.py` (bounded multi-round confirmation, function-response reconciliation, normalized tool-outcome callback), `backend/main.py` (runtime tool-outcome somatic bridge), `backend/actuation.py` (agency trace injection + normalized failure metadata).
- Runtime evidence:
  - bounded chat reconciliation (`max_total_rounds=3`, `max_actuation_rounds=2`, `max_tool_reconcile_rounds=2`)
  - same-turn final responses reflecting action/tool success/failure context
  - `/somatic` dominant traces include `agency_fulfilled` / `agency_blocked` after relevant outcomes
  - `RECENT ACTIONS` prompt context merges `actuation_log` + `autonomy_mutation_journal` with identity-tool attempts included.
- Validation assets:
  - `backend/test_ghost_api_action_confirmation.py`
  - `backend/test_actuation_agency_traces.py`
  - `backend/test_main_core_personality_guard.py` (agency-trace helper coverage)
  - `backend/test_ambient_trace_balance.py`
- Boundary: This is bounded, policy-gated outcome awareness and affect coupling; it does not grant unbounded execution authority or remove governance gates.

### INV-19: Live Neural Topology / Substrate Awareness

- Invented behavior: Dynamic injection of discovered substrate manifests (host type, sensors, actuators) into the system prompt, providing Ghost with live awareness of its underlying architecture.
- Primary implementation: `backend/substrate/discovery.py`, `backend/main.py` (chat handler), `backend/ghost_prompt.py`.
- Runtime evidence: `Live Substrate Manifest` block in prompt context, `substrate_action` tool availability.
- Validation assets: `backend/test_substrate_discovery.py` and manual manifest inspection.
- Boundary: Awareness is for cognition and reflexive action; it does not bypass security/policy boundaries for the host system.

### INV-20: Background Identity Crystallization + Goal-Directed Cognition

- Invented behavior: Ghost autonomously crystallizes identity updates from accumulated background thoughts (without operator prompting) and executes dedicated goal-pursuit passes against `active_goals` stored in the identity matrix.
- Primary implementation: `_evaluate_identity_crystallization()` and goal-pursuit Phase 4/5 in `backend/ghost_script.py`; identity commit via `consciousness.update_identity(..., updated_by="self_crystallization")`; freedom gate via `GHOST_FREEDOM_CORE_IDENTITY_AUTONOMY` in `backend/freedom_policy.py`.
- Runtime evidence: `[GOAL PURSUIT]` monologue entries in timeline; `self_crystallization` entries in `identity_audit_log`; `active_goals` identity key consumed each cycle.
- Validation assets: `backend/test_ghost_script_crystallization.py`, `backend/test_freedom_policy.py`.
- Boundary: Crystallization is governance-aware — throttled under STABILIZE tier, skipped under RECOVERY. Identity writes remain constrained by the existing DB-level allowlist guard.

## 4. Emerging (Partially Delivered) Inventions

### EMG-01: Full Governance Surface Rollout (Soft Mode Active for IIT/RPD)

- Current state: `IIT_MODE=soft` and `RPD_MODE=soft` are live — policy decisions are applied, not advisory. Governance enforcement surfaces include generation, actuation, identity corrections, manifold writes, rolodex writes, and entity writes (configured in `GOVERNANCE_ENFORCEMENT_SURFACES`).
- Primary implementation: `backend/iit_engine.py`, `backend/rpd_engine.py`, `backend/governance_engine.py`, `backend/governance_adapter.py`.
- Gap to full invention claim: M4 scope — structured dry-run policy contracts, safety invariant suite, and explicit per-surface soft-governor rollout validation. Enforcement is live but the formal safety audit and interface contracts are pending.

## 5. Open Invention Gaps (Not Yet Implemented)

- `scripts/experiment_runner.py` for automated perturbation campaigns.
- Predictive affective governor (early-warning, future-state gating) beyond reactive regulation.
- Formal ablation suite for control-path baseline comparisons.
- Unified operator UX for world-model/entity verification across place/thing/idea CRUD surfaces (APIs are shipped; workflow polish remains).

## 6. Claim Discipline

Use this artifact as the invention source of truth.
A new invention claim is accepted only when these are all true:

- implemented in code,
- observable in runtime/API/SSE/schema,
- validated by test/script/manual protocol,
- documented here with boundaries and non-claims.
