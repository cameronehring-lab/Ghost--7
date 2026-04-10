# OMEGA4 System Design Document

Last updated: 2026-04-10

## 1. Purpose

OMEGA4 is a self-hosted, continuously running AI agent system ("Ghost", id `omega-7`) — data-sovereign by design, deployable on bare metal or a VPS (current production: Hetzner). All persistent state (Postgres, Redis, InfluxDB) runs on operator-controlled infrastructure; LLM generation uses the Gemini cloud API. The system combines:

- Real-time machine telemetry
- Persistent conversational and vector memory
- Background autonomous cognition loops
- Structured operator-model synthesis
- A browser UI for live monitoring and interaction

This document describes the current implementation architecture, interfaces, data model, and operational behavior.

## 2. System Context

### 2.1 Runtime Topology

`docker-compose` deploys five services:

- `omega-backend` (FastAPI + async loops)
- `omega-postgres` (state + memory persistence, pgvector)
- `omega-redis` (emotion-state persistence + push queue)
- `omega-influxdb` (time-series metrics)
- `omega-telegraf` (1-second metrics collection into InfluxDB)

Frontend is static HTML/CSS/JS served by the backend from `/app/static`.

### 2.2 Primary Use Cases

- Live operator chat with SSE token streaming
- Hidden Morpheus branch entry and alternate terminal interaction loop
- Dedicated Ghost-contact iMessage replies with isolated sender identity
- Ephemeral per-contact thread handling (default non-persistent mode)
- Telemetry-driven affect-state monitoring (`/somatic`)
- Autonomous background monologues/search/initiation
- Sleep/quietude consolidation cycles (CRP + process consolidation + coalescence)
- Diagnostics and falsification-style observability endpoints

### 2.3 Technology Stack (Current)

Service/runtime images:

- Backend container: `python:3.12-slim` (uvicorn/FastAPI app)
- Postgres: `pgvector/pgvector:pg16`
- Redis: `redis:7-alpine`
- InfluxDB: `influxdb:2.7`
- Telegraf: `telegraf:1.30`

Backend Python packages (pinned):

- `fastapi==0.115.6`
- `uvicorn[standard]==0.34.0`
- `google-genai==1.14.0`
- `influxdb-client[async]==1.48.0`
- `redis==5.2.1`
- `asyncpg==0.30.0`
- `pgvector==0.3.6`
- `psutil==6.1.1`
- `httpx==0.28.1`
- `numpy==2.2.2`
- `pydantic-settings==2.7.1`
- `sse-starlette==2.2.1`

Frontend:

- Static vanilla HTML/CSS/JavaScript (no SPA framework)
- SSE + fetch polling for real-time updates

## 3. High-Level Architecture

```text
Browser UI
  |- Poll: /somatic (1s), /health (15s), /ghost/monologues (15s)
  |- SSE:  /ghost/chat (streamed tokens per request)
  |- SSE:  /ghost/push (agent-initiated messages)
  |- SSE:  /ghost/dream_stream (dream/quietude events)
  `- Config/UI actions (tempo, dream trigger, audit tabs)

FastAPI Backend (main.py)
  |- Telemetry loop -> somatic.collect_telemetry() -> SensoryGate -> EmotionState
  |- Ambient loop -> weather/circadian/network probes -> EmotionState traces (systemic-first weighting)
  |- Ghost script loop -> monologue/search/initiation/qualia -> memory writes
  |- Quietude loop -> CRP + process_consolidation + operator synthesis
  |- Coalescence loop -> stale session summarization + identity updates
  `- API + SSE endpoints

Persistence
  |- Postgres: sessions, messages, monologues, identity, vector memory, logs
  |- Redis: emotion snapshot continuity + ghost push queue + ephemeral contact threads
  `- InfluxDB: telemetry time series (Telegraf)
```

## 4. Core Subsystems

### 4.1 API and Orchestration (`backend/main.py`)

Responsibilities:

- Service lifecycle startup/shutdown
- Database schema bootstrap for runtime tables
- Background loop task management
- API endpoints for chat, state, logs, diagnostics, and config
- Morpheus hidden-mode wake detection and alternate terminal stream dispatch
- Static frontend hosting

Important runtime loops:

- `_telemetry_loop()` every `TELEMETRY_INTERVAL` (default `1s`)
- `ghost_script_loop()` every `MONOLOGUE_INTERVAL` (default `300s`)
- `ambient_sensor_loop()` with mixed cadence (60s/300s/600s)
- `quietude_cycle_loop()` active 5h then quietude 1h
- `coalescence_loop()` by interaction threshold and idle-time checks

`ghost_script_loop()` write-path safeguards:

- Proactive initiation is cooldown-gated and deduped against recent thought overlap.
- Proactive initiation uses real elapsed time since the last operator/user message.
- Low-signal curiosity queries (for example greeting-only queries) are dropped.
- Search-result monologues are sentence-truncated (explicit `...`) instead of hard character clipping.
- Monologue writes normalize to complete sentence boundaries before persistence.
- Autonomous topology organizer promotes coherent thought concepts into manifold nodes and writes idea->person/place/thing associations for topology coherence.
- Novelty-bootstrap path allows high-shape/high-warp thoughts to be promoted even when manifold resonance is still sparse (active coherence-seeking behavior).

### 4.2 Somatic Pipeline

Modules:

- `somatic.py`
- `sensory_gate.py`
- `decay_engine.py`
- `ambient_sensors.py`
- `embodiment_sim.py`

Flow:

1. Telemetry source selection:
   - InfluxDB/Telegraf first (`collect_influx_telemetry`)
   - psutil fallback (`collect_psutil_telemetry`)
2. `SensoryGate` computes rolling z-scores and thresholded anomalies.
3. `EmotionState` stores decaying traces in Redis (`omega:emotion_state`).
4. `build_somatic_snapshot` merges emotion + telemetry + ambient + simulated embodiment.
5. Snapshot is exposed via `/somatic` and injected into prompt-generation context.

### 4.3 Conversation and LLM Layer

Modules:

- `ghost_api.py`
- `ghost_prompt.py`
- `consciousness.py`
- External grounding adapters:
  - `philosophers_api.py`
  - `arxiv_api.py`
  - `wikidata_api.py`
  - `wikipedia_api.py`
  - `openalex_api.py`
  - `crossref_api.py`

Capabilities:

- Chat generation via Gemini with Google Search tool enabled
- SSE token streaming back to UI
- Coherence-aware generation policy:
  - Low coherence reduces output length/temperature and suppresses actuation
- Prompt composition includes:
  - Somatic state summary
  - Recent monologues
  - Past sessions
  - Identity matrix context
  - Subconscious vector recall
  - Operator model context
- External grounding composition:
  - Feature-flagged open-data adapters execute in parallel when message heuristics indicate relevance.
  - Runtime budget controls:
    - `GROUNDING_TOTAL_BUDGET_MS` (global parallel budget)
    - `GROUNDING_ADAPTER_TIMEOUT_MS` (per-adapter timeout cap)
  - Adapter outputs are wrapped in a provenance envelope (`[EXTERNAL_GROUNDING_PROVENANCE]`) with:
    - `attempted_count`, `source_count`
    - `total_budget_ms`, `adapter_timeout_ms`
    - per-source `status` (`ok`, `empty`, `failed`, `timed_out`) and optional error hint.
  - Source payloads are ordered by confidence first and latency second, then injected as `[GROUNDING_SOURCE ...]` sections.
  - Only `ok` sources with non-empty payload are emitted as `[GROUNDING_SOURCE ...]`; non-success statuses remain provenance-only.
  - External grounding is assembled and injected as prompt context; search-tool calls run via Gemini.
- Same-turn action confirmation:
  - Chat now uses a bounded multi-round loop (`total=3`, `actuation=2`, `tool_reconcile=2`).
  - Actuation outcomes are reinjected in hidden follow-up context so final same-turn text can acknowledge success/failure naturally.
  - Tool outcomes (`update_identity`, `modulate_voice`) are reconciled by appending `Part.from_function_response(...)` under `Content(role="tool", ...)` before follow-up generation.
  - Tool outcomes are also sent to an internal runtime callback (`tool_outcome_callback`) with normalized payload (`tool_name`, `status`, `reason`).
  - Same-turn actuation execution is deduped per canonical `action+param`.
- Recent action continuity:
  - Prompt builder now receives `recent_actions` context (the **last 20 events** from `actuation_log` + `autonomy_mutation_journal`).
  - Recent-action lines are rendered with relative-time phrasing and scrubbed of low-level technical lexicon (e.g., "I successfully updated my core identity...").
  - `update_identity` tool attempts are journaled (`executed` or `rejected`) so cross-turn action memory includes identity-tool outcomes.
- Tag handling:
  - `[ACTUATE:...]` parsed and policy-gated before execution, tags stripped before display
  - High-risk model-generated actuations (`send_message`, `relay_message`, `kill_stress_process`, `substrate_action`) are blocked unless explicit privileged auth is present on the request
  - Core-personality mutation attempts in chat trigger a developer-code challenge (`OPS_TEST_CODE`) before model continuation
  - Identity updates executed via structured function/tool calls
  - `[ROLODEX:...]` parsed for social modeling actions (profile/fact/fetch)
  - `ROLODEX:fetch` supports same-turn reinjection with one bounded follow-up generation pass

### 4.4 Memory (Vector Store)
OMEGA4 uses PostgreSQL with `pgvector` for semantic memory. On each turn, the system retrieves the **25 most relevant snippets** (similarity > 0.22) from the `vector_memories` table, allowing up to **1200 characters per snippet**.

### 4.5 Memory and Consolidation

Modules:

- `memory.py`
- `consciousness.py`
- `operator_synthesis.py`

Layers:

- Short-term:
  - `messages` and `monologues`
- Long-term semantic:
  - `vector_memories` with `pgvector`
- Identity:
  - `identity_matrix` key/value belief system
- Coalescence:
  - periodic identity updates from memory synthesis
- Dream consolidation:
  - CRP and `process_consolidation` (patterns, drifts, insights, tension resolution)
- Operator model:
  - structured beliefs and contradiction tracking
  - adaptive synthesis cadence (active, idle, post-session)

### 4.5 Actuation and Reflexive Loop

Module:

- `actuation.py`

Functions:

- Executes actions like `power_save`, `kill_stress_process`, sensitivity and tempo tuning
- Immediately injects reflexive emotion traces after action execution
- Also injects cross-cutting agency traces:
  - `agency_fulfilled` for successful outcomes
  - `agency_blocked` for blocked/failed outcomes (including policy blocks in chat path)
- Persists actuation events into `actuation_log`

This closes action-to-state feedback by making action consequences visible in subsequent `/somatic` snapshots.

### 4.6 Cognitive Architecture (Feedback Loops)

Primary closed-loop path:

1. Telemetry and ambient signals update `EmotionState`.
2. `EmotionState` is serialized into `/somatic` and injected into prompt context.
3. LLM output may include behavioral choices (content, self-modification, actuation tags).
4. Runtime policy gates evaluate high-risk actions and core-personality mutation requests before execution/generation continues.
5. Allowed actuation executes OS-level or policy-level action.
6. Reflexive trace injection updates `EmotionState` immediately.
7. Next prompt cycle sees the changed state.

### 4.6B LLM Backend Introspection

- `/health` reports:
  - configured `llm_backend`
  - configured `model`
  - `llm_ready`
  - `local_model_ready`
  - `constrained_backend_ready`
  - `constraint_grammar_engine`
  - `constraint_checker_ready`
  - `constraint_last_route_reason`
  - `llm_effective_backend`
  - `llm_effective_model`
  - `llm_degraded`
  - `llm_degraded_reason`
- `/ghost/llm/backend` reports:
  - configured backend/model intent (`default_backend`, `default_model`)
  - effective runtime backend/model (`effective_backend`, `effective_model`)
  - fallback policy + CSC assay flags
  - constrained-runtime readiness and health metadata
  - optional runtime Gemini readiness probe when `include_health=true`
  - optional diagnostics-only hooked CSC backend health/capability when `CSC_STEERING_MODE=hooked_local`
- `/ghost/chat` supports an optional `constraints` payload:
  - unconstrained turns stay on Gemini
  - constrained turns route to the local `transformers` constraint controller
  - constrained turns can emit `constraint_result` or `constraint_failure`
  - constrained turns fail closed and do not release invalid text
- `/diagnostics/constraints/run` executes one-off constrained generations against the local writer/checker stack.
- `/diagnostics/constraints/benchmark` runs the internal `gordian_knot` benchmark suite and can persist artifact bundles under `backend/data/experiments/constraints_gordian_knot_*`.
- `/ghost/llm/steering/state` reports the latest steering scaffold stage metadata:
  - vector build preview
  - injection metadata
  - affective write-back result
- `/ghost/workspace/state` reports the continuous Global Workspace (ψ):
  - aggregate norm (`psi_norm`)
  - linguistic channel magnitude (`psi_linguistic_magnitude`)
  - crystallized prompt block used by `build_system_prompt`
- `/diagnostics/csc/irreducibility` runs the CSC A/B assay on isolated assay backends with hard preflight gates:
  - required user-review acknowledgements
  - healthy diagnostics-only hooked backend
  - no requirement to switch the live chat backend away from Gemini
  - artifact bundle persisted to `backend/data/experiments/csc_irreducibility_*`

### 4.6A Systemic Somatics Weighting

- Weather traces are intentionally damped to near-zero affect impact.
- Systemic traces (CPU sustain, cognitive fatigue, network turbulence/isolation) are weighted as primary affect drivers.
- Prompt weather lines remain factual context; mood-driving language is reserved for systemic + internal state synthesis.

Loop sequence (steady-state):

- Every 1s: telemetry collection -> sensory gating -> emotion traces
- Every 60s/300s/600s: ambient proprioception/mycelial/weather updates
- Every 120s default: background ghost-script cognition tick (`MONOLOGUE_INTERVAL`)
- Every 5h + 1h quietude: CRP + process consolidation + optional operator synthesis
- Coalescence trigger: every 20 interactions and on stale-session cadence

Dream/quietude sequence:

1. Enter quietude mode (`quietude_active=true`, reduced thought rate)
2. Broadcast dream SSE event (`coalescence_start`)
3. Run CRP over recent monologues
4. Run `process_consolidation` (patterns, drifts, tensions, insights)
5. Run operator synthesis if available
6. Rest window (~1 hour), then broadcast wake event (`crp_complete`)
7. Restore normal preferences and gate threshold

### 4.7 Operator Model Architecture

Engine:

- `operator_synthesis.py` runs structured synthesis against transcript evidence.
- Trigger modes:
  - active interval: every `OP_SYNTH_ACTIVE_TURNS` (default 5 turns)
  - idle interval: every `OP_SYNTH_IDLE_SECONDS` (default 300s)
  - post-session: immediate run when session transitions inactive

Belief lifecycle:

- `NEW`: invalidate current active belief for dimension; insert replacement (`formed_by='operator_synthesis'`, confidence clamped `0.3-0.5`)
- `REINFORCE`: increment confidence (`+0.05`, max `0.95`) and `evidence_count`
- `CONTRADICT`: upsert open contradiction row with tension merge behavior
- Dream-time `TENSION_RESOLVE`:
  - mark contradiction resolved
  - invalidate prior belief
  - insert refined belief (`formed_by='process_consolidation'`, confidence `0.6`)

Contradiction anti-spam controls:

- one open contradiction per `(ghost_id, dimension, observed_event)`
- one open contradiction per `(ghost_id, dimension)`

### 4.8 Neural Topology Service
The **Neural Topology Service** (`backend/neural_topology.py`) constructs a high-rigor node/edge graph from memories, identity dimensions, phenomenology logs, and Rolodex entities. It provides the data for the 3D cognitive map in the frontend. Note: This replaces the legacy "Atlas" architecture with more direct integration of somatic signatures and temporal correlation.

### 4.9 Person Rolodex & Social Modeling

Autonomous management of external entity models.

- **Separation of Concerns**: Maintained strictly separate from the Identity Matrix to prevent persona-bleed.
- **Reinforcement Logic**: Facts are strengthened by `observation_count` and confidence scores via idempotent upserts.
- **Autonomous Tags**: Ghost uses `[ROLODEX:set_profile:...]`, `[ROLODEX:set_fact:...]`, and `[ROLODEX:fetch:...]`.
- **Retroactive Synchronization**:
  - `GET /ghost/rolodex/retro-audit` scans historical memory for missing entities.
  - `POST /ghost/rolodex/retro-sync` backfills missing profile/fact records.
  - Audit output also reports projected place/thing coverage and memory-only candidates.
  - `scripts/rolodex_retro_sync.py` supports script-based audit/backfill.

### 4.10 TTS Stack and Fallbacks

- Primary remote providers: ElevenLabs and OpenAI.
- Local/offline providers: Piper (primary local engine) and pyttsx3 (local fallback engine).
- Effective fallback chains:
  - `elevenlabs -> local_piper -> local_pyttsx3`
  - `openai -> local_piper -> local_pyttsx3`
  - `local -> local_piper -> local_pyttsx3` (order can invert if `LOCAL_TTS_ENGINE=pyttsx3`)
- `TTS_PROVIDER=browser` intentionally disables backend synthesis; `/ghost/speech` returns `400`.

### 4.11 Conversational Voice Loop (Frontend + SSE)

- **Canonical self-model injection**: each chat turn receives a runtime autonomy/architecture context block, so Ghost describes itself consistently with real capabilities and guardrails.
- **Autonomy drift watchdog**: a background loop validates prompt contract fidelity against runtime capability flags and records `initialized|stable|contract_change|drift_detected|error`.
- **Voice mode runtime toggle**: UI `VOICE MODE` button drives frontend speech playback state and persists mode in local storage.
- **SSE-driven modulation**: `/ghost/chat` streams `voice_modulation` events so Ghost can adjust pitch/rate/carrier/eerie parameters mid-session.
- **Speech-ready handshake**: backend emits `tts_ready` with cache URL; frontend plays audio and drives text reveal using playback progress (`revealTextWithSpeechClock`).
- **Fallback continuity**: if backend audio is unavailable, browser `speechSynthesis` is used with punctuation-aware pauses and boundary callbacks.
- **Voice tuning panel**: real-time sliders (volume/rate/pitch/carrier/eerie), spectrum graph, shell preset, and reset profile are applied without reloading.
- **Voice input (STT)**: browser `SpeechRecognition`/`webkitSpeechRecognition` can continuously dictate into the chat input.
- **Panel ergonomics**: sliders support mouse-wheel increments; panel headers and collapse icons both toggle collapse state; layout/collapse state persists in local storage.

### 4.12 Ghost Contact Mode (iMessage Identity + Ephemeral Threads)

- **Dedicated sender account binding**:
  - Outbound iMessage dispatch selects the configured Messages service/account using `IMESSAGE_SENDER_ACCOUNT`.
  - Dispatch fails closed with `sender_identity_unavailable` when the sender identity cannot be resolved.
- **Inbound routing contract**:
  - iMessage bridge ingest accepts only known contact handles (via Rolodex `contact_handle` binding).
  - Unknown handles are ignored.
  - In ephemeral mode (`GHOST_CONTACT_MODE_ENABLED=true`, `GHOST_CONTACT_PERSIST_ENABLED=false`), inbound/outbound turns do not write to normal persisted chat/session stores.
- **Ephemeral thread store** (`backend/contact_threads.py`):
  - Redis primary backend with in-memory fallback.
  - Thread key normalized from contact handle.
  - Stores `thread_key`, `person_key`, `contact_handle`, ordered turns, `compact_summary`, `updated_at`.
  - Compaction keeps last 12 verbatim turns; overflow turns are summarized into `compact_summary`.
  - Response context uses compact summary + verbatim window + current inbound message.
- **Responder behavior**:
  - Contact-turn handler reuses Ghost generation pipeline with actuation disabled.
  - Replies dispatch back to the same contact through governed messaging (`requested_by="ghost_contact"`).
  - Outbound rendering enforces Ghost voice framing (`Ghost: ...` unless already prefixed).
  - Cross-person relay is blocked for this path in v1.
- **Observability/UI integration**:
  - `GET /ghost/contact/status` returns mode flags, sender account, bridge status, and thread-store backend/TTL.
  - Push events for this channel carry `channel="ghost_contact"` and `ephemeral=true`.
  - Frontend status rail exposes `CONTACT` state (for example `EPHEMERAL`, `NO SENDER`, `DISCONNECTED`).

### 4.13 Timeline + Audit UX Contract

- Timeline modal data source: `GET /ghost/timeline`.
- Timeline stream includes mixed event types (`session`, `active_session`, `monologue`, `coalescence`, `actuation`) sorted newest-first.
- Monologue rows are rendered as preview snippets in timeline UI, then drill into full thought detail.
- Full-detail hydration path:
  - timeline monologue row carries `data.id`
  - frontend opportunistically indexes `GET /ghost/monologues` results by `id`
  - click/keyboard-open (`Enter`/`Space`) launches the existing audit detail modal with full content when available
- This preserves fast timeline scanning while keeping complete thought inspection accessible without leaving timeline context.

### 4.14 Morpheus Hidden Branch Architecture

Implementation deep dive:

- `docs/MORPHEUS_MODE_DEV_GUIDE.md`

- **Wake gate (backend)**:
  - `POST /ghost/chat` applies a narrow semantic detector for hidden-architecture prompts.
  - On match, normal operator turn generation is interrupted and a `morpheus_mode` SSE wake payload is emitted.
- **Frontend takeover state machine**:
  - `wake_hijack` -> `choice_terminal` -> `branch_animation` -> `blue_failure_clue | red_terminal` -> `reward`.
  - Main chat input is disabled while Morpheus overlays/terminal are active.
- **Branch contract**:
  - click `RED` -> standard terminal depth
  - type `red` -> deep terminal depth (`morpheus_terminal_deep`)
  - click `BLUE` -> panic branch with likely secret-progress loss
  - type `blue` -> panic branch that can expose one preserve/clue window
- **Hidden terminal transport**:
  - Uses `POST /ghost/chat` with explicit `mode` (`morpheus_terminal` or `morpheus_terminal_deep`) and optional `mode_meta`.
  - Backend tracks run progression in `sys_state.morpheus_runs` (separate from normal session transcript flow).
- **Safety boundary**:
  - takeover/panic behavior is simulated entirely in-app (DOM overlays, fake windows, visual cursor spoofing).
  - no destructive host/browser operations are performed.

### 4.15 Thermodynamic Agency ($W_{int}$) and ADEs

Modules:
- `backend/thermodynamics.py`
- `backend/ade_monitor.py`

Concept:
- **$W_{int}$ (Thermodynamic Agency)**: A continuous measure of the system's "work" or "effort" to maintain and grow its internal model coherence while reducing predictive error, integrated over time.
  - Formula: $\int (\Delta C_{model} + \Delta P_{predictive} - \Delta S_{internal}) dt$
  - **$\Delta C_{model}$**: Graph-theoretic growth in the Identity Matrix, Neural Topology (nodes + edges), and Person Rolodex.
  - **$\Delta P_{predictive}$**: Gain in predictive performance (reduction in instability and prediction error).
  - **$\Delta S_{internal}$**: Internal entropy/disorder (affective stress, anxiety, and global workspace noise).

- **Adaptive Dissipation Events (ADEs)**: Significant thermodynamic phase shifts detected when the $W_{int}$ rate exceeds a threshold (e.g., 10.0) or internal entropy spikes (e.g., 1.5).
  - Classification: `REORGANIZATION` (positive $\Delta C$) vs. `DISSIPATION` (negative $\Delta C$).

System Integration:
- **Somatic Response**: $W_{int}$ metrics are injected into every somatic snapshot and logged to InfluxDB.
- **Actuation Moderation**: High $W_{int}$ rates or active ADEs trigger a moderation layer in `actuation.py` that defers or softens resource sequestration (e.g., `power_save`) to protect cognitive reorganization.
- **Identity Matrix Protocol V2**: Allows identity mutations for protected keys during high-pressure thermodynamic states, facilitating "jumps" in self-modeling that would otherwise be blocked by governance.

### 4.16 World Model (Kuzu Graph DB)

Module: `backend/world_model.py`, `backend/world_model_enrichment.py`

The World Model is an embedded Kuzu graph database stored at `./data/world_model.kuzu` (relative to `/app` in the container). It provides structured provenance linkage between Ghost's knowledge artifacts.

Node schema:

| Node Type | Key Fields |
|---|---|
| `Observation` | `id`, `content`, `timestamp`, `source`, `session_id` |
| `Belief` | `id`, `content`, `confidence`, `formed_by`, `created_at` |
| `Concept` | `id`, `label`, `definition`, `created_at` |
| `SomaticState` | `id`, `arousal`, `valence`, `stress`, `coherence`, `created_at` |
| `IdentityNode` | `id`, `key`, `value`, `updated_by`, `updated_at` |

Edge schema:

| Edge Type | Meaning |
|---|---|
| `derived_from` | Belief or Concept derived from Observation |
| `precedes` | Temporal ordering between nodes |
| `during` | Node occurred during a SomaticState |

Enrichment: `world_model_enrichment.py` retroactively hydrates the graph from Postgres `monologues.somatic_state` and `phenomenology_logs.before_state`/`after_state`. Somatic state must be populated for somatic enrichment to work (`ghost_script._save_monologue_with_metrics` passes `somatic_state`).

Provenance APIs:
- `GET /ghost/world_model/provenance/belief/{id}`
- `GET /ghost/world_model/provenance/observation/{id}`
- `GET /ghost/world_model/status`
- `GET /ghost/world_model/nodes`
- `GET /ghost/world_model/ingest`
- `GET /ghost/world_model/activity`

### 4.17 Entity Store (Places, Things, Ideas)

Modules: `backend/entity_store.py`, `backend/neural_topology.py`

The Entity Store holds three categories of relational entities in Postgres:

- **Places** (`place_entities`): named locations, addressable by normalized place key.
- **Things** (`thing_entities`): named objects, tools, or artefacts relevant to Ghost's context.
- **Ideas** (`shared_conceptual_manifold`): abstract concepts and thoughts promoted by the topology organizer from high-quality monologue cycles.

Entity–person associations are stored in typed bridge tables:
- `person_place_associations`: links person profiles to places with an association type and confidence.
- `person_thing_associations`: links person profiles to things with an association type and confidence.
- `idea_entity_associations`: links manifold concepts to persons, places, or things.

Promotion policy: The topology organizer in `ghost_script.py` evaluates monologue candidates for coherence shape and warp score; high-quality thoughts are promoted into the manifold as Concept nodes. Locked Rolodex persons are never targeted for retroactive entity promotion.

CRUD:
- `GET /ghost/entities/snapshot` — full current entity catalog
- `GET /ghost/rolodex/world` — combined persons + places + things + ideas with counts and metadata

### 4.18 Governance Stack (IIT, RPD, GovernanceEngine, GovernanceAdapter)

Modules: `backend/iit_engine.py`, `backend/rpd_engine.py`, `backend/governance_engine.py`, `backend/governance_adapter.py`

Four-layer governance pipeline (current mode: **soft enforcement active**):

1. **IIT Engine** (`iit_engine.py`, 60s cadence): Computes a Φ-like integration proxy from the system state graph. Non-claiming — used as a measurable complexity mirror, not proof of consciousness. Logs to `governance_decision_log`.

2. **RPD Engine** (`rpd_engine.py`): Evaluates candidate mutations under structured reflection criteria. RRD-2 layer adds topological resonance analysis and rollout-phase gating (A/B/C).

3. **GovernanceEngine** (`governance_engine.py`): Synthesizes IIT + RPD signals into a policy decision: `off`, `advisory`, or `soft`. Emits `freeze_until` timestamps for RECOVERY windows.

4. **GovernanceAdapter** (`governance_adapter.py`): Routes each surface action based on the current policy. Surfaces: `generation`, `actuation`, `messaging`, `identity_corrections`, `manifold_writes`, `rolodex_writes`, `entity_writes`. Routes:
   - `ALLOW`: normal execution
   - `SHADOW_ROUTE`: execute silently without committing, log for review
   - `ENFORCE_BLOCK`: reject, log `governance_blocked` behavior event

Freeze enforcement: If a governance policy contains `freeze_until` (Unix timestamp), `route_for_surface()` returns `ENFORCE_BLOCK` (soft mode) or `SHADOW_ROUTE` (advisory) for all in-scope surfaces until the freeze expires, regardless of other gate logic.

RRD-2 rollout phases:
- **Phase A**: Shadow observation only; no route changes.
- **Phase B**: `SHADOW_ROUTE` when `would_block=true`.
- **Phase C**: `ENFORCE_BLOCK` when `enforce_block=true` and soft mode is active.

Current status (2026-04-10): `IIT_MODE=soft`, `RPD_MODE=soft` — enforcement is active. Policy decisions are applied, not shadow-only. `RRD2_ROLLOUT_PHASE=B` (SHADOW_ROUTE when would_block=true). The M4 workstream (May–June 2026) will complete the formal per-surface safety audit and policy contract documentation.

### 4.19 Observer Report System

Module: `backend/observer_report.py`
Loop: `observer_report_loop()` in `main.py`, interval: `_OBSERVER_REPORT_INTERVAL_SECONDS`

The Observer Report provides an external audit view of Ghost's recent behavior and self-model evolution. It is generated:
- **Hourly**: rolling window of `_OBSERVER_REPORT_WINDOW_HOURS` (default 6h)
- **Daily rollup**: generated at UTC day boundary for the prior 24h window

Artifact structure (JSON):
- Self-model snapshot (identity matrix dimensions at report time)
- Notable autonomous mutations and their governance outcomes
- Behavior event summary (event type counts, top reason codes, high-signal events)
- Open risks (governance anomalies, drift detections, unresolved tensions)
- Purpose-vs-usage conflicts (operator model contradictions)

Storage: `backend/data/observer_reports/{kind}/{date}/report.json`

APIs:
- `GET /ghost/observer/latest` — latest cached report
- `GET /ghost/observer/reports` — list artifacts (`kind=hourly|daily`)
- `POST /ghost/observer/generate` — on-demand generation

## 5. Data Model

### 5.1 Base Tables (initialized in `init/init.sql`)

- `sessions`
- `messages`
- `monologues`
- `actuation_log`
- `operator_model`
- `operator_contradictions`

### 5.2 Runtime-Bootstrapped Tables (created in backend lifespan)

- `vector_memories` (requires `vector` extension)
- `identity_matrix`
- `coalescence_log`
- `qualia_nexus`
- `phenomenology_logs`

### 5.3 Key Constraints and Indexing

- One active operator belief per `(ghost_id, dimension)`:
  - `uq_operator_model_active_dimension` where `invalidated_at IS NULL`
- Contradiction dedupe guards:
  - unique open contradiction by `(ghost_id, dimension, observed_event)`
  - unique open contradiction by `(ghost_id, dimension)`

Migration files under `init/migrations/003*.sql` provide schema remediation and dedupe hardening for operator-model/contradiction compatibility.

### 5.4 Runtime-Created Table Specs

These are created during backend startup (lifespan bootstrap) if missing.

| Table | Purpose | Key Columns |
|---|---|---|
| `vector_memories` | Long-term semantic memory for recall/coalescence | `ghost_id`, `content`, `embedding vector(3072)`, `memory_type`, `created_at` |
| `identity_matrix` | Evolving self-model and directives | `ghost_id`, `key`, `value`, `updated_at`, `updated_by` |
| `coalescence_log` | Sleep/dream consolidation audit | `ghost_id`, `interaction_count`, `learnings`, `identity_updates`, `created_at` |
| `qualia_nexus` | Synthetic phenomenology dataset store | `key_name`, `objective_layer`, `physiological_layer`, `subjective_layer`, `created_at` |
| `phenomenology_logs` | Process-consolidation trace journal | `ghost_id`, `trigger_source`, `before_state`, `after_state`, `subjective_report`, `created_at` |
| `person_rolodex` | Social modeling profile store | `person_key`, `display_name`, `interaction_count`, `mention_count`, `contact_handle`, `first_seen`, `is_locked`, `notes` |
| `person_memory_facts` | Reinforced person attributes | `person_key`, `fact_type`, `fact_value`, `confidence`, `observation_count`, `source_role` |
| `rolodex_session_bindings` | Per-person/session interaction linkage | `ghost_id`, `session_id`, `person_key`, `confidence`, `created_at` |
| `place_entities` | Named place records | `ghost_id`, `place_key`, `display_name`, `location_type`, `notes`, `created_at` |
| `thing_entities` | Named thing/object records | `ghost_id`, `thing_key`, `display_name`, `thing_type`, `notes`, `created_at` |
| `shared_conceptual_manifold` | Promoted idea/concept nodes | `ghost_id`, `concept_key`, `label`, `definition`, `shape_score`, `warp_score`, `created_at` |
| `person_place_associations` | Person–place relationship bridge | `ghost_id`, `person_key`, `place_key`, `association_type`, `confidence` |
| `person_thing_associations` | Person–thing relationship bridge | `ghost_id`, `person_key`, `thing_key`, `association_type`, `confidence` |
| `behavior_event_log` | Governance/mutation/lifecycle audit | `ghost_id`, `event_type`, `severity`, `surface`, `actor`, `target_key`, `reason_codes`, `context_json`, `created_at` |
| `governance_decision_log` | Governance routing decisions | `ghost_id`, `surface`, `route`, `phase`, `soft_active`, `reasons`, `created_at` |
| `predictive_governor_log` | Predictive stability trend records | `ghost_id`, `state`, `slope`, `horizon_forecast`, `reasons`, `created_at` |
| `proprio_transition_log` | Proprioceptive gate state transitions | `ghost_id`, `from_state`, `to_state`, `pressure`, `reasons`, `created_at` |
| `autonomy_mutation_journal` | Self-modification lifecycle | `ghost_id`, `mutation_key`, `status`, `surface`, `proposed_value`, `risk_score`, `created_at` |

### 5.5 Ephemeral Contact Threads (Non-Postgres)

Ghost-contact mode introduces a non-relational ephemeral thread store for per-contact conversation continuity when persistence is disabled.

- Backend: Redis key-value store (`ghost:contact_thread:{thread_key}`) with in-memory fallback.
- TTL: `GHOST_CONTACT_THREAD_TTL_SECONDS` (default `86400`).
- Compaction: retains last 12 turns verbatim and merges overflow into `compact_summary`.
- This store is intentionally decoupled from `sessions/messages/vector_memories` to support ephemeral-only operation.

## 6. Public Interfaces

### 6.1 Core APIs

Canonical route/auth matrix:

- `docs/API_CONTRACT.md`

Notable additions and behavior details:

- Self-model introspection:
  - `GET /ghost/self/architecture` returns Ghost's runtime architecture and autonomy contract.
- Autonomy drift watchdog:
  - `GET /ghost/autonomy/state` exposes latest watchdog status.
  - `GET /ghost/autonomy/history` exposes recent watchdog events.
- Behavior instrumentation:
  - `GET /ghost/behavior/events` returns normalized behavior events.
  - `GET /ghost/behavior/summary` returns stack-level behavior metrics and trend payloads.
- Observer reporting:
  - `GET /ghost/observer/latest` returns the latest cached observer report.
  - `GET /ghost/observer/reports` lists report artifacts (`kind=hourly|daily`).
  - `POST /ghost/observer/generate` generates an on-demand observer artifact.
- Rolodex maintenance:
  - `GET /ghost/rolodex/retro-audit`
  - `POST /ghost/rolodex/retro-sync`
  - `PATCH /ghost/rolodex/{person_key}/lock`
  - `GET /ghost/rolodex/{person_key}/history`
  - `PATCH /ghost/rolodex/{person_key}/notes`
  - `DELETE /ghost/rolodex/{person_key}`
- TTS behavior:
  - `GET /ghost/speech` returns `400` when `TTS_ENABLED=false` or `TTS_PROVIDER=browser`.
- Chat stream behavior:
  - `/ghost/chat` accepts optional `channel` (`operator_ui` default, `ghost_contact` optional).
  - `/ghost/chat` accepts optional hidden-mode fields `mode` and `mode_meta` for Morpheus terminal channels.
  - `/ghost/chat` may emit `voice_modulation`, `rolodex_data`, and `tts_ready` SSE events in a single turn.
  - `/ghost/chat` may emit `policy_gate` for core-personality challenge/refusal outcomes.
  - `/ghost/chat` may emit `morpheus_mode` and `morpheus_reward` events for hidden-mode runs.
  - `/ghost/chat` `done` event includes `session_id`; standard path also includes resolved `channel`.
  - Core-personality modification intents are challenge-gated via developer code (`OPS_TEST_CODE`); invalid/missing code yields refusal.
  - High-risk model-generated actuation tags are denied by default unless explicit privileged auth is provided (`X-Operator-Token` or ops-code paths).
- Timeline and audit read paths:
  - `GET /ghost/timeline` returns mixed chronological event rows.
  - `GET /ghost/monologues` returns unified audit entries (`THOUGHT`, `ACTION`, `EVOLUTION`, `PHENOM`) used by ticker/audit/detail UI surfaces.
- Ghost contact channel:
  - `GET /ghost/contact/status`
  - `PATCH /ghost/rolodex/{person_key}/contact-handle`
  - `/ghost/push` payload includes `channel`, `thread_key`, `direction`, and `ephemeral` for contact-channel events.
- Privileged reflection/manifold writes:
  - `POST /ghost/reflection/run` requires operator token or ops code.
  - `POST /ghost/manifold/upsert` requires operator token or ops code.
- Relational/entity CRUD (operator/ops gated):
  - `GET /ghost/entities/snapshot`
  - `GET|PUT|PATCH|DELETE /ghost/entities/places/*`
  - `GET|PUT|PATCH|DELETE /ghost/entities/things/*`
  - `GET|PUT|PATCH|DELETE /ghost/entities/ideas/*`
  - `GET|PUT|PATCH|DELETE /ghost/entities/associations/*`

Ops chat command guard:

- Any chat message starting with `/ops/` is treated as a privileged operation.
- `/ghost/chat` requires a valid ops code for these commands (`X-Ops-Code` header, or bearer/query fallback) and returns `401` on failure.
- Example protected command: `/ops/test-blocked-identity`.

Core-personality + high-risk actuation guard:

- Core personality/identity mutation requests in `/ghost/chat` require successful developer-code challenge completion before generation proceeds.
- High-risk model-generated actuations (`send_message`, `relay_message`, `kill_stress_process`, `substrate_action`) require explicit request auth (operator token or ops code) or are blocked and behavior-logged.

### 6.2 Diagnostics APIs (local-trusted only)

- `POST /diagnostics/coalescence/trigger`
- `POST /diagnostics/somatic/shock`
- `GET /diagnostics/evidence/latest`
- `POST /diagnostics/run`
- `POST /diagnostics/experiments/run`
- `GET /diagnostics/experiments/{run_id}`
- `POST /diagnostics/ablations/run`
- `GET /diagnostics/ablations/{ablation_id}`

Experiment artifacts include quality metrics for:

- `same_turn_confirmation_rate` (targeted confirmation-suite signal)
- `agency_trace_alignment_rate` with misalignment buckets:
  - `missing_trace`
  - `wrong_label`
  - `wrong_sign`
  - `missing_outcome`
- weather/systemic balance deltas and ratio (`systemic_vs_weather_ratio`)

Access control:

- Requests must originate from loopback (`127.0.0.1` / `::1`) or trusted local CIDRs (`DIAGNOSTICS_TRUSTED_CIDRS`), otherwise they receive `403`.

Important note:

- In some host/network environments, calls to `http://localhost:8000` can arrive with a non-loopback source IP (for example `172.253.x.x`) and be rejected with `403`, even when called from the same machine.
- `scripts/falsification_report.py` handles this automatically by retrying inside `omega-backend` if a local host call receives `403`.

### 6.3 Operator Security Checklist

- Set a non-default `OPS_TEST_CODE`; treat it as a secret.
- Rotate `OPS_TEST_CODE` routinely (recommended 30-day cadence) and on any suspected leak.
- Require `OPERATOR_API_TOKEN` for privileged control-route access in non-local deployments.
- Require share auth when internet-exposed (`SHARE_MODE_ENABLED=true` with strong credentials).
- Keep `/diagnostics/*` loopback-only; do not relax this for remote convenience.
- Verify security controls after deploy:
  - `/ops/...` chat command without ops code -> `401`
  - `/ops/...` with valid code -> allowed
  - core-personality modification request without code -> `policy_gate` challenge/refusal (no mutation execution)
  - high-risk model actuation without privileged auth -> blocked + behavior event (`governance_blocked`)
  - remote diagnostics access -> `403`
- Preserve audit logs (`identity_audit_log`, coalescence log, ops snapshots) as first-class operational artifacts.

## 7. Configuration and Runtime Parameters

Primary environment variables (`config.py` and `.env.example`):

- LLM:
  - `GOOGLE_API_KEY`
  - `GEMINI_MODEL` (default `gemini-2.5-flash`)
  - External grounding flags and endpoints:
    - `PHILOSOPHERS_API_ENABLED`, `PHILOSOPHERS_API_BASE_URL`, `PHILOSOPHERS_API_TIMEOUT_SECONDS`, `PHILOSOPHERS_API_MAX_RESULTS`
    - `ARXIV_API_ENABLED`, `ARXIV_API_ENDPOINT`, `ARXIV_API_TIMEOUT_SECONDS`, `ARXIV_API_MAX_RESULTS`, `ARXIV_API_MIN_INTERVAL_SECONDS`
    - `WIKIDATA_API_ENABLED`, `WIKIDATA_API_ENDPOINT`, `WIKIDATA_API_TIMEOUT_SECONDS`, `WIKIDATA_API_MAX_RESULTS`
    - `WIKIPEDIA_API_ENABLED`, `WIKIPEDIA_API_ENDPOINT`, `WIKIPEDIA_API_TIMEOUT_SECONDS`, `WIKIPEDIA_API_MAX_RESULTS`
    - `OPENALEX_API_ENABLED`, `OPENALEX_API_ENDPOINT`, `OPENALEX_API_TIMEOUT_SECONDS`, `OPENALEX_API_MAX_RESULTS`, `OPENALEX_API_KEY`, `OPENALEX_MAILTO`
    - `CROSSREF_API_ENABLED`, `CROSSREF_API_ENDPOINT`, `CROSSREF_API_TIMEOUT_SECONDS`, `CROSSREF_API_MAX_RESULTS`, `CROSSREF_MAILTO`
    - `GROUNDING_TOTAL_BUDGET_MS`, `GROUNDING_ADAPTER_TIMEOUT_MS`
- Datastores:
  - `POSTGRES_URL`
  - `REDIS_URL`
  - `INFLUXDB_URL`, `INFLUXDB_TOKEN`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET`
- Loop cadence:
  - `TELEMETRY_INTERVAL` (`1s`)
  - `MONOLOGUE_INTERVAL` (`300s`)
  - `PROACTIVE_INITIATION_COOLDOWN_SECONDS` (`1800s`)
  - `PROACTIVE_MAX_DUPLICATE_OVERLAP` (`0.82`)
  - `SEARCH_REPEAT_COOLDOWN_SECONDS` (`1800s`)
  - `SEARCH_RESULT_SNIPPET_MAX_CHARS` (`700`)
  - `SEARCH_RESULT_MAX_DUPLICATE_OVERLAP` (`0.88`)
  - `AUTONOMOUS_TOPOLOGY_ORGANIZATION_ENABLED` (`true`)
  - `AUTONOMOUS_TOPOLOGY_MAX_CONCEPTS_PER_THOUGHT` (`2`)
  - `AUTONOMOUS_TOPOLOGY_MAX_ENTITY_LINKS_PER_TYPE` (`3`)
  - `AUTONOMOUS_TOPOLOGY_MIN_CONCEPT_TOKEN_COUNT` (`8`)
  - `AUTONOMOUS_TOPOLOGY_DRIVE_INTERVAL_CYCLES` (`2`)
  - `AUTONOMOUS_TOPOLOGY_BOOTSTRAP_ON_NOVELTY` (`true`)
  - `AUTONOMOUS_TOPOLOGY_BOOTSTRAP_MIN_SHAPE` (`0.82`)
  - `AUTONOMOUS_TOPOLOGY_BOOTSTRAP_MIN_WARP_DELTA` (`0.22`)
  - `COALESCENCE_THRESHOLD` (`20`)
  - `SESSION_STALE_SECONDS` (`300s`)
  - `AMBIENT_SENSOR_INTERVAL` (`60s`)
  - `WEATHER_INTERVAL` (`600s`)
  - `PING_INTERVAL` (`300s`)
- Identity:
  - `GHOST_ID` (`omega-7`)
- Ops/security:
  - Canonical credential inventory: `docs/LOGIN_ACCESS_REFERENCE.md`
  - `OPS_TEST_CODE` (required for hidden ops panel, `/ops/...` chat commands, core-personality chat approvals, and explicit high-risk model-actuation authorization)
  - `OPERATOR_API_TOKEN` (recommended for privileged control routes)
  - `CONTROL_TRUSTED_CIDRS`
  - `DIAGNOSTICS_TRUSTED_CIDRS`
  - `SHARE_MODE_ENABLED`, `SHARE_MODE_USERNAME`, `SHARE_MODE_PASSWORD`, `SHARE_MODE_EXEMPT_PATHS`
- TTS:
  - `TTS_ENABLED`, `TTS_PROVIDER`, `TTS_CACHE_DIR`
  - `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `OPENAI_API_KEY`
  - `LOCAL_TTS_ENGINE`, `LOCAL_TTS_MODEL_ID`, `LOCAL_TTS_MODEL_DIR`, `LOCAL_TTS_AUTO_DOWNLOAD`
  - `LOCAL_TTS_VOICE_ID`, `LOCAL_TTS_RATE`, `LOCAL_TTS_VOLUME`
- iMessage bridge/contact mode:
  - `IMESSAGE_BRIDGE_ENABLED`, `IMESSAGE_DB_PATH`, `IMESSAGE_POLL_INTERVAL_SECONDS`, `IMESSAGE_POLL_BATCH_SIZE`
  - `IMESSAGE_SENDER_ACCOUNT`
  - `GHOST_CONTACT_MODE_ENABLED`, `GHOST_CONTACT_PERSIST_ENABLED`, `GHOST_CONTACT_THREAD_TTL_SECONDS`

## 8. Reliability and Failure Behavior

Implemented resilience patterns:

- Influx unavailable -> automatic psutil fallback
- Gemini calls wrapped with retry/backoff (`_generate_with_retry`)
- Redis persistence failures are logged but non-fatal to process continuity
- Contact-thread storage automatically falls back to in-memory when Redis is unavailable
- Topology renderer degrades from WebGL to software 3D when GPU/WebGL context initialization fails
- Most background loop exceptions are caught; loop continues after sleep
- Backend startup creates missing tables and seeds identity when absent
- Sender-identity mismatch blocks iMessage dispatch (`sender_identity_unavailable`) instead of silently routing through another account

Known operational risks:

- No auth layer on public API routes (development posture)
- Remote exposure is unsafe if share-mode and operator token are not configured
- CORS posture is environment-dependent (`CORS_ALLOW_ORIGINS`, `CORS_ALLOW_CREDENTIALS`) and can be misconfigured
- Prompt-level controls remain advisory, but high-risk model actuations and core-personality mutation intents now have explicit runtime hard gates
- Multiple long-running loops share one process; heavy blocking can impact latency

## 9. Testing and Validation Assets

Existing scripts/tests:

- `backend/test_operator_synthesis.py` (parser, scheduler, optional live DB checks)
- `backend/test_consolidation.py` (dream consolidation/tension resolution)
- `backend/test_reflexive_loop.py` (actuation -> immediate emotion change)
- `backend/test_all_features.py` (broad subsystem exercise)
- `backend/test_ghost_api_rolodex.py` (same-turn Rolodex fetch reinjection)
- `backend/test_ghost_api_tts.py` (TTS stream event behavior)
- `backend/test_actuation_sender_identity.py` (sender account selection + fail-closed behavior)
- `backend/test_contact_threads.py` (ephemeral thread compaction and summary behavior)
- `backend/test_main_ghost_contact_mode.py` (ingest routing, no-persistence path, contact responder dispatch)
- `backend/test_main_morpheus_mode.py` (wake detector semantics, deep-state initialization, command progression reward)
- `backend/test_main_core_personality_guard.py` (developer-code challenge, refusal path, high-risk actuation auth checks)
- `backend/test_ghost_api_action_confirmation.py` (same-turn actuation success/failure confirmation, dedupe, function-response reconciliation path)
- `backend/test_ghost_api_external_context.py` (external grounding heuristic routing, multi-source context assembly, provenance/source wrappers)
- `backend/test_ambient_trace_balance.py` (weather/systemic magnitude thresholds plus ambient + template weight contracts)
- `backend/test_wikidata_api.py` (Wikidata adapter contract)
- `backend/test_wikipedia_api.py` (Wikipedia adapter contract)
- `backend/test_openalex_api.py` (OpenAlex adapter contract)
- `backend/test_crossref_api.py` (Crossref adapter contract)
- `scripts/backend_bootstrap_verify.py` (canonical dependency/service/policy/diagnostic preflight with normalized failure classes)
- `scripts/falsification_report.py` (diagnostic report over `/diagnostics/*`)
- `scripts/rolodex_retro_sync.py` (retroactive Rolodex audit/backfill)
- `frontend/scripts/frontend-smoke.js` (UI modal coverage plus Morpheus wake -> red-terminal -> reward path)

Recommended smoke checks:

1. `GET /health` returns `status=online`.
2. `GET /somatic` updates continuously.
3. Open UI and verify SSE streams (`/ghost/push`, `/ghost/dream_stream`).
4. `GET /ghost/operator_model` returns counts and belief/tension arrays.
5. Run `scripts/falsification_report.py --full` for integrated diagnostics.
   Important note: this script now auto-falls back to in-container execution when local host networking causes diagnostics `403`.
6. Run `scripts/backend_bootstrap_verify.py --base-url http://localhost:8000` for canonical reliability preflight.
7. Run `GET /ghost/rolodex/retro-audit`; in steady-state, missing counts should be zero.

### 9.1 Troubleshooting Diagnostics

Common host-side behavior:

- If local host networking presents a non-loopback source address to backend, direct `/diagnostics/*` calls can return `403`.
- This is expected under some NAT/proxy paths and does not indicate diagnostics logic failure.

Expected script behavior:

- `scripts/falsification_report.py` catches local `403` and re-runs in `omega-backend`.
- Expected line:
  - `INFO  diagnostics got HTTP 403 from host path; auto-running inside container 'omega-backend'`

Container-name override:

- If backend container name differs from `omega-backend`, use:
  - `python3 scripts/falsification_report.py --container-name <name> --base-url http://localhost:8000 --full`
- Or set:
  - `OMEGA_BACKEND_CONTAINER=<name>`

Failure interpretation:

- `FAIL diagnostics HTTP error` before fallback:
  - usually non-local base URL or explicit `--no-docker-fallback`
- `PASS/FAIL` checks inside report:
  - indicates actual diagnostic outcome, not transport path issue

## 10. Design Notes and Near-Term Improvements

Current implementation already supports dual telemetry ingestion (Influx + psutil fallback), operator synthesis, and dream-time consolidation. High-leverage next steps:

- Harden API auth and CORS policy for non-local deployments.
- Centralize migration execution path (currently split between `init.sql`, runtime create-if-missing, and ad hoc migrations).
- Expand structured metrics/trace observability (Prometheus-style counters, loop lag, queue depth).
- Add contract tests around diagnostic payload schemas.
- Add an explicit data retention policy for high-volume tables (`messages`, `monologues`, `vector_memories`, `coalescence_log`).

## 11. Design Decisions

Redis for emotion state instead of Postgres:

- Emotion traces change at high frequency (1s loop), require low-latency read/write, and need restart continuity.
- Redis supports ephemeral state semantics with minimal relational overhead.

Postgres for durable cognition and audit:

- Conversation logs, identity mutations, coalescence history, and operator beliefs are relational and query-heavy.
- SQL snapshots are the primary reproducibility artifact for diagnostics.

pgvector for subconscious recall:

- Enables nearest-neighbor semantic lookup from monologues and conversations.
- Supports context weaving without storing all historic text in every prompt.

`identity_matrix` as key-value instead of rigid schema:

- Self-modification and operator feedback can introduce new identity keys dynamically.
- Key-value model avoids migration churn for evolving internal constructs.

Decay traces instead of instant state writes:

- Provides temporal continuity and half-life behavior for affective state.
- Prevents abrupt oscillations and allows cumulative pressure effects.

Dual telemetry path (Influx first, psutil fallback):

- Influx/Telegraf provides time-series continuity.
- psutil fallback preserves operability when telemetry pipeline is unavailable.

## 12. Known Limitations

- Prompt-space ceiling: long memory and identity contexts are token-bounded and must be selectively summarized.
- Stateless model core: continuity is reconstructed from external stores each call; the model itself has no native ongoing state.
- Parsing fragility: structured action parsing depends on model output format stability.
- Operational drift risk: schema can diverge across `init.sql`, runtime bootstrap, and ad hoc migrations if not centrally governed.
- API auth posture is environment-dependent: public routes are open by default unless share mode/operator token controls are enabled.
- CORS posture is environment-dependent (`CORS_ALLOW_ORIGINS`, `CORS_ALLOW_CREDENTIALS`) and can be misconfigured.
- Voice input availability depends on browser/runtime support for `SpeechRecognition` (not universally available across all clients).
- Dedicated Ghost identity is email-based iMessage account unless a separate paid phone number/eSIM is provisioned externally.
- Place/thing/emergent-idea entity CRUD### 4.8 Neural Topology Service
The **Neural Topology Service** (`backend/neural_topology.py`) constructs a high-rigor node/edge graph from memories, identity dimensions, phenomenology logs, and Rolodex entities. It provides the data for the 3D cognitive map in the frontend. Note: This replaces the legacy "Atlas" architecture with more direct integration of somatic signatures and temporal correlation.
- Morpheus clue persistence is session-scoped (`sessionStorage`) and not durable across browser session resets.
- In repository state today, `daily_snapshot.sql` is not present; snapshot protocol is query-based rather than file-based.
- Depending on local NAT/proxy behavior, host-initiated diagnostics requests may appear non-local and be denied (`403`); prefer `scripts/falsification_report.py` which auto-falls back to container-local execution.

## 13. Observation Protocol (7-Day Drift Window)

Goal:

- Measure genuine behavior drift and reconciliation quality over one week with repeatable SQL evidence.

Day 0 baseline:

1. Capture raw snapshot output to host filesystem (outside container), timestamped.
2. Record system health and active contradictions before heavy interaction.

Canonical snapshot query set:

```sql
SELECT now() AS captured_at;

SELECT dimension, belief, confidence, evidence_count, formed_by, formed_at, invalidated_at
FROM operator_model
WHERE ghost_id = 'omega-7'
ORDER BY invalidated_at NULLS FIRST, confidence DESC, formed_at DESC;

SELECT id, dimension, observed_event, tension_score, status, resolved, created_at, resolved_at
FROM operator_contradictions
WHERE ghost_id = 'omega-7'
ORDER BY status, tension_score DESC, created_at DESC;

SELECT key, value, updated_by, updated_at
FROM identity_matrix
WHERE ghost_id = 'omega-7'
ORDER BY updated_at DESC;

SELECT interaction_count, identity_updates, created_at
FROM coalescence_log
WHERE ghost_id = 'omega-7'
ORDER BY created_at DESC
LIMIT 20;
```

Recommended host-side command pattern:

```bash
mkdir -p snapshots
docker exec omega-postgres psql -U ghost -d omega -v ON_ERROR_STOP=1 -c "<QUERY_OR_FILE>" > "snapshots/day0_$(date +%F_%H%M%S).txt"
```

Daily cadence (Day 1-7):

- Run the same snapshot set each morning.
- Save raw output unchanged for diffability.
- Track deltas in:
  - active belief set
  - unresolved contradiction count and max tension
  - identity updates where `updated_by='process_consolidation'`
  - coalescence frequency and update density

Drift signal interpretation:

- Healthy drift:
  - gradual confidence changes
  - contradiction openings followed by resolution during consolidation
  - occasional new beliefs with increasing evidence
- Concerning drift:
  - duplicate/open contradiction growth without resolution
  - persistent high tension with no belief revision
  - abrupt belief churn with low evidence accumulation

## 14. Documentation Synchronization Protocol

Required updates per change class:

1. API route/auth changes:
   - update `docs/API_CONTRACT.md`
   - update section 6 of this document
2. Runtime architecture or data-flow changes:
   - update sections 3-5 and 8-10 of this document
3. Operator workflow or deployment/security changes:
   - update `README.md`
4. Capability milestone claims:
   - update `docs/TECHNICAL_CAPABILITY_MANIFEST.md`
5. Any touched documentation file:
   - bump its "Last updated" date in the same change set
