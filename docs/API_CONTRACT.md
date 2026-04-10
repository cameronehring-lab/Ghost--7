# OMEGA4 API Contract

Last updated: 2026-04-10

This document is the canonical API surface for the running backend (`backend/main.py`).
It records route availability, auth semantics, and behavior notes required for safe development.
For a layer-by-layer signal inventory, see [`docs/LAYER_DATA_TOC.md`](./LAYER_DATA_TOC.md).
For centralized credential/login inventory, see [`docs/LOGIN_ACCESS_REFERENCE.md`](./LOGIN_ACCESS_REFERENCE.md).
For implementation-level Morpheus behavior, see [`docs/MORPHEUS_MODE_DEV_GUIDE.md`](./MORPHEUS_MODE_DEV_GUIDE.md).

## 1. Auth Model

All routes are subject to optional share-mode Basic Auth when:

- `SHARE_MODE_ENABLED=true`
- request path is not exempt (default exempt path is `/health`)

Additional route-level controls:

- **Operator access** (`_require_operator_access`):
  - `POST /ghost/actuate`
  - `POST /config/tempo`
- **Ops-code access** (`_require_ops_access`):
  - `GET /ops/verify`
  - `GET /ops/runs`
  - `GET /ops/file`
  - `POST /ghost/chat` for messages starting with `/ops/`
  - `POST /ghost/chat` core-personality modification approval gate
- **Conditional privileged signal in `/ghost/chat`**:
  - High-risk model-generated actuation tags execute only when request includes explicit privileged auth.
  - Accepted auth forms:
    - valid operator token (`X-Operator-Token` or bearer token), or
    - valid ops code (`X-Ops-Code`, `?code=`, or bearer token).
- **Operator OR ops-code access** (`_require_operator_or_ops_access`):
  - `POST /ghost/reflection/run`
  - `POST /ghost/manifold/upsert`
  - `GET /ghost/autonomy/mutations`
  - `POST /ghost/autonomy/mutations/{mutation_id}/approve`
  - `POST /ghost/autonomy/mutations/{mutation_id}/reject`
  - `POST /ghost/autonomy/mutations/{mutation_id}/undo`
  - `POST /ghost/observer/generate`
- **Diagnostics local-trust gate** (`_require_local_request`):
  - all `/diagnostics/*` routes

## 2. Route Matrix

| Method | Path | Auth Class | Notes |
|---|---|---|---|
| `GET` | `/health` | Public (share-exempt by default) | Liveness and core runtime summary. Includes configured/effective LLM state (`llm_backend`, `model`, `llm_ready`, `local_model_ready`, `llm_effective_backend`, `llm_effective_model`, `llm_degraded`, `llm_degraded_reason`) plus constrained-runtime fields (`constrained_backend_ready`, `constraint_grammar_engine`, `constraint_checker_ready`, `constraint_last_route_reason`). |
| `GET` | `/somatic` | Public | 1s-polled somatic + telemetry snapshot. |
| `GET` | `/ghost/proprio/state` | Public | Current proprioceptive gate state (pressure, cadence, contributions). |
| `GET` | `/ghost/proprio/transitions` | Public | Recent gate transitions (`precedes` log). |
| `GET` | `/ghost/proprio/quality` | Public | Proprio signal coverage + transition-rate diagnostics. |
| `POST` | `/ghost/chat` | Public + conditional privileged auth | SSE token stream endpoint. Request supports optional `channel` (`operator_ui` default, `ghost_contact` optional), optional hidden-mode fields `mode` and `mode_meta` for Morpheus terminal runs, and optional `constraints` for constrained decoding. In ghost-contact ephemeral mode, turns bypass DB session/message persistence. Adds two safety gates: (1) core-personality modification requests trigger a developer-code challenge flow; (2) high-risk model-generated actuation tags are blocked unless request includes explicit privileged auth (operator token or ops code). When enabled by heuristics + flags, chat turns also inject multi-source external grounding blocks with a provenance envelope (`[EXTERNAL_GROUNDING_PROVENANCE]`) and ordered source wrappers (`[GROUNDING_SOURCE ...]`). Unconstrained chat uses the existing Gemini loop; constrained turns route to the local `transformers` constraint controller and fail closed if validation cannot pass. Emits operational events (`identity_update`, `rolodex_update`, `rolodex_data`, `tts_ready`, `morpheus_mode`, `policy_gate`, `constraint_result`, `constraint_failure`, etc.). |
| `GET` | `/ghost/push` | Public | SSE stream for autonomous pushes. |
| `GET` | `/ghost/dream_stream` | Public | SSE stream for quietude/dream events. |
| `GET` | `/sse` | Public | SSE status endpoint. |
| `GET` | `/ghost/monologues` | Public | Unified audit stream (`THOUGHT`, `ACTION`, `EVOLUTION`, `PHENOM`) ordered newest-first. |
| `DELETE` | `/ghost/monologues/{monologue_id}` | Public | Remove monologue entry. |
| `POST` | `/ghost/dream/initiate` | Public | Trigger dream/quietude cycle. |
| `POST` | `/ghost/search` | Public | Autonomous web-search call + memory writeback. |
| `GET` | `/ghost/speech` | Public | TTS synth from text. Returns `400` when `TTS_ENABLED=false` or `TTS_PROVIDER=browser`; returns `500` on synth failure. |
| `GET` | `/ghost/sessions` | Public | Session list and history metadata. |
| `GET` | `/ghost/contact/status` | Public | Ghost contact-channel readiness: mode flags, sender account, bridge status, and thread-store backend/TTL. |
| `GET` | `/ghost/llm/backend` | Public | Configured/effective generation backend state. Returns `default_backend`/`default_model`, `effective_backend`/`effective_model`, fallback policy, local model provisioning state, constrained-runtime readiness (`constrained_backend_ready`, `constraint_grammar_engine`, `constraint_checker_ready`, `last_constraint_route_reason`), optional local inference health (`include_health=true`), and optional steering telemetry echo (`include_steering=true`). In CSC hooked mode it also reports diagnostics-only hooked-backend health/capability. `CSC_STRICT_LOCAL_ONLY` remains CSC-assay-only and does not block routine chat readiness. |
| `GET` | `/ghost/llm/steering/state` | Public | Latest steering scaffold runtime state (vector/injection/write-back stage metadata). |
| `GET` | `/ghost/workspace/state` | Public | Continuous Global Workspace (ψ) runtime state: norm, linguistic magnitude, and current prompt crystallization block. |
| `GET` | `/ghost/identity` | Public | Identity Matrix snapshot. |
| `GET` | `/ghost/self/architecture` | Public | Runtime functional architecture + autonomy contract; includes prompt grounding context. |
| `GET` | `/ghost/autonomy/state` | Public | Latest autonomy-drift watchdog state; falls back to on-demand snapshot if watcher not yet emitted. |
| `GET` | `/ghost/autonomy/history` | Public | Recent autonomy watchdog events (newest first). |
| `GET` | `/ghost/operator_model` | Public | Beliefs/tensions summary. |
| `GET` | `/ghost/coalescence` | Public | Coalescence history view. |
| `GET` | `/ghost/timeline` | Public | Unified existence timeline (`session`, `active_session`, `monologue`, `coalescence`, `actuation`) ordered newest-first. |
| `GET` | `/ghost/world_model/status` | Public | World-model runtime availability + label counts. |
| `GET` | `/ghost/world_model/nodes` | Public | Read-only node browse by world-model label. |
| `GET` | `/ghost/world_model/ingest` | Public | World-model ingest status trigger/readout. |
| `GET` | `/ghost/world_model/provenance/belief/{belief_id}` | Public | Belief evidence chain via `derived_from` edges; optional somatic snapshots on linked observations. |
| `GET` | `/ghost/world_model/provenance/observation/{observation_id}` | Public | Observation context: `during` somatic state plus `precedes` neighbors. |
| `GET` | `/ghost/world_model/activity` | Public | Relational/world-model write activity summary from mutation journal. |
| `GET` | `/ghost/behavior/events` | Public | Normalized behavior event stream (filterable by type/actor/surface/time). |
| `GET` | `/ghost/behavior/summary` | Public | Behavior-window summary + under-exposed stack metrics. |
| `GET` | `/ghost/observer/latest` | Public | Latest Ghost observer report payload. |
| `GET` | `/ghost/observer/reports` | Public | Observer report artifact index. |
| `POST` | `/ghost/observer/generate` | Operator or ops-code | Manual observer report generation. |
| `GET` | `/ghost/neural-topology` | Public | Canonical neural-topology graph generator for the dedicated 3D modal. Supports `threshold` (default 0.65). Note: This is the functional engine for cognitive mapping. |
| `GET` | `/ghost/atlas` | Public | Legacy Atlas snapshot pointer. Returns default/empty payload as the system has normalized on the High-Rigor Neural Topology engine. |
| `POST` | `/ghost/atlas/rebuild` | Operator or ops-code | Legacy rebuild trigger (stub). |
| `GET` | `/ghost/rolodex` | Public | Rolodex list view (`include_archived=true` optional). |
| `GET` | `/ghost/rolodex/world` | Public | Canonical person/place/thing/idea snapshot view over the Atlas read model (`include_archived=true` optional); read-only and returns `503` when no successful snapshot exists yet. |
| `GET` | `/ghost/rolodex/{person_key}` | Public | Rolodex person details + facts (`include_archived=true` can read archived profiles/facts). |
| `PATCH` | `/ghost/rolodex/{person_key}/lock` | Public | Lock/unlock profile from auto updates. |
| `GET` | `/ghost/rolodex/{person_key}/history` | Public | Session/mention history snippets for one profile. |
| `PATCH` | `/ghost/rolodex/{person_key}/notes` | Public | Update operator notes for one profile. |
| `PATCH` | `/ghost/rolodex/{person_key}/contact-handle` | Public | Set/clear iMessage contact handle used for direct Ghost dispatch/routing. |
| `DELETE` | `/ghost/rolodex/{person_key}` | Public | Soft-delete profile + facts by default; `hard_delete=true` enters approval queue for purge. |
| `POST` | `/ghost/rolodex/{person_key}/restore` | Operator or ops-code | Restore a soft-deleted profile and re-activate invalidated facts. |
| `GET` | `/ghost/rolodex/retro-audit` | Public | Deep historical scan for missing entities (dry-run). |
| `POST` | `/ghost/rolodex/retro-sync` | Public | Backfill missing entities from historical memory. Idempotent in steady state. |
| `GET` | `/ghost/rolodex/failures` | Ops-code access | Dead-letter queue inspection for failed rolodex ingest attempts. |
| `POST` | `/ghost/rolodex/retry-failures` | Ops-code access | Retry unresolved dead-letter rolodex ingest rows. |
| `GET` | `/ghost/rolodex/integrity` | Ops-code access | Rolodex integrity diagnostics (orphans, empty profiles, stale bindings, duplicate-like profiles). |
| `GET` | `/config/tempo` | Public | Read cadence tuning state. |
| `POST` | `/config/tempo` | Operator access | Update cadence tuning state. |
| `POST` | `/ghost/actuate` | Operator access | Execute reflexive/system actuation. |
| `GET` | `/ops/verify` | Ops-code access | Validate ops-code and snapshots root. |
| `GET` | `/ops/runs` | Ops-code access | List psych-eval snapshot runs. |
| `GET` | `/ops/file` | Ops-code access | Read snapshot artifact by relative path. |
| `GET` | `/ghost/proprio/state` | Public | Current proprio gate state. |
| `GET` | `/ghost/proprio/transitions` | Public | Proprio transition log view. |
| `GET` | `/ghost/iit/state` | Public | Latest IIT advisory snapshot. |
| `GET` | `/ghost/iit/history` | Public | IIT history window. |
| `GET` | `/ghost/governance/state` | Public | Current governance policy state. |
| `GET` | `/ghost/governance/history` | Public | Governance history window. |
| `GET` | `/ghost/rpd/state` | Public | Latest RPD advisory state. |
| `GET` | `/ghost/rpd/runs` | Public | RPD run history. |
| `GET` | `/ghost/rrd/state` | Public | RRD state summary. |
| `GET` | `/ghost/rrd/runs` | Public | RRD run history. |
| `POST` | `/ghost/reflection/run` | Operator or ops-code | Run reflection pass manually. |
| `GET` | `/ghost/autonomy/mutations` | Operator or ops-code | Mutation journal list, with optional status filter. |
| `POST` | `/ghost/autonomy/mutations/{mutation_id}/approve` | Operator or ops-code | Execute pending high-risk mutation. |
| `POST` | `/ghost/autonomy/mutations/{mutation_id}/reject` | Operator or ops-code | Reject pending high-risk mutation. |
| `POST` | `/ghost/autonomy/mutations/{mutation_id}/undo` | Operator or ops-code | Undo executed mutation within TTL window. |
| `GET` | `/ghost/manifold` | Public | Shared conceptual manifold rows. |
| `POST` | `/ghost/manifold/upsert` | Operator or ops-code | Upsert shared manifold concept. |
| `POST` | `/diagnostics/iit/run` | Diagnostics local-trust | Trigger IIT diagnostics run. |
| `POST` | `/diagnostics/coalescence/trigger` | Diagnostics local-trust | Trigger coalescence diagnostics. |
| `POST` | `/diagnostics/somatic/shock` | Diagnostics local-trust | Inject synthetic somatic perturbation. |
| `POST` | `/diagnostics/probes/assay` | Diagnostics local-trust | Run a controlled qualia probe assay and persist a phenomenology report. |
| `POST` | `/diagnostics/constraints/run` | Diagnostics local-trust | Execute a one-off constrained generation against the local `transformers` writer/checker stack. Accepts `prompt`, optional `system_prompt`, optional `conversation_history`, and required `constraints`. Returns `ConstraintResult` plus constrained backend health. |
| `POST` | `/diagnostics/constraints/benchmark` | Diagnostics local-trust | Run the internal `gordian_knot` constraint benchmark suite or a caller-provided case list. Persists `manifest.json`, `run_summary.json`, and per-case artifacts under `backend/data/experiments/constraints_gordian_knot_*` when `persist_artifacts=true`. |
| `POST` | `/diagnostics/csc/irreducibility` | Diagnostics local-trust | Run CSC A/B irreducibility assay (activation-steered vs prompt-only) on isolated assay backends. Hard guards: required user acknowledgements, healthy configured local inference backend/model, and healthy diagnostics-only hooked backend. This endpoint does not require changing the live chat backend. Persists `manifest.json`, `run_summary.json`, and per-iteration artifacts under `backend/data/experiments/csc_irreducibility_*`. |
| `GET` | `/diagnostics/evidence/latest` | Diagnostics local-trust | Retrieve latest diagnostic evidence bundle. |
| `POST` | `/diagnostics/run` | Diagnostics local-trust | Full integrated diagnostics sequence. |
| `POST` | `/diagnostics/experiments/run` | Diagnostics local-trust | Execute campaign manifest through `scripts/experiment_runner.py`; returns artifact summary. |
| `GET` | `/diagnostics/experiments/{run_id}` | Diagnostics local-trust | Read experiment artifact bundle (`run_summary`, optional ablation output). |
| `POST` | `/diagnostics/ablations/run` | Diagnostics local-trust | Execute ablation variants through `scripts/ablation_suite.py`; returns artifact summary. |
| `GET` | `/diagnostics/ablations/{ablation_id}` | Diagnostics local-trust | Read ablation artifact bundle (`ablation_report`, linked run summaries). |

## 3. SSE Event Highlights

`POST /ghost/chat` can emit multiple operational SSE events alongside token chunks:

- `policy_gate`: chat-level policy challenge/refusal event payload (`surface`, `reason`, `status`) for guard outcomes.
- `identity_update`: result of guarded identity tool calls.
- `voice_modulation`: live voice-parameter update request.
- `rolodex_update`: profile/fact write action summary.
- `rolodex_data`: fetched profile + facts payload.
- `tts_ready`: backend-generated audio URL for the response.
- `constraint_result`: constrained-turn success metadata (`attempts_used`, `grammar_engine`, `checker_used`, `route`, `validation_passed`).
- `constraint_failure`: constrained-turn fail-closed payload (`code`, `message`, `details`, `result`).
- `morpheus_mode`: hidden-mode phase/state event (`wake_hijack`, `red_terminal`, `reward`) with run and branch metadata.
- `morpheus_reward`: hidden terminal reward payload (note + animation frames).
- `done`: includes `session_id`; standard chat path includes resolved `channel` (`operator_ui` or `ghost_contact`), wake path includes `morpheus_run_id`, terminal mode includes `morpheus_step`.

### 3.1 Core-Personality + High-Risk Actuation Guard

`POST /ghost/chat` now enforces two runtime policy gates:

- Core-personality modification challenge:
  - Triggered when user intent targets core identity/personality mutation semantics.
  - First turn returns a challenge asking for developer code.
  - Follow-up must include valid developer code (`OPS_TEST_CODE`) or request is refused.
  - Refusal text explicitly states only creator-authorized core personality changes are permitted.
  - Approved follow-up strips code text from model prompt input and logs a sanitized user entry.
- High-risk model actuation gate:
  - Model-generated high-risk actuation tags are denied by default:
    - `send_message`
    - `relay_message` / `forward_message`
    - `kill_stress_process`
    - `substrate_action`
  - Allowed only when request provides explicit privileged auth:
    - valid operator token (`X-Operator-Token` or bearer token), or
    - valid ops code (`X-Ops-Code`, `?code=`, or bearer token).
  - Denials are logged as behavior events (`governance_blocked`) with reason code `high_risk_actuation_requires_explicit_auth`.

### 3.2 Morpheus Mode Contract

Wake path (no explicit `mode` required):

- Applies only on operator channel (`channel=operator_ui`) when prompt semantics match hidden architecture + runtime/phenomenology query intent.
- Response emits `morpheus_mode` with:
  - `phase="wake_hijack"`
  - `run_id`
  - `branch_prompt="red_blue"`
  - `selection_meta.branches=["click_red","type_red","click_blue","type_blue"]`
- Followed by `done` event containing `mode="morpheus_wake"` and `morpheus_run_id`.

Terminal path (explicit mode):

- Request:
  - `mode="morpheus_terminal"` for standard red branch
  - `mode="morpheus_terminal_deep"` for typed-red deep branch
  - optional `mode_meta` (for example `depth`, `branch_color`, `branch_input`)
- Response:
  - emits `morpheus_mode` phase updates
  - emits token chunks for terminal output text
  - may emit `morpheus_reward` when command puzzle milestone is completed
  - emits `done` with `session_id` (run id) and `morpheus_step`

Persistence boundary:

- Morpheus run state is tracked separately from normal session transcript persistence.
- Blue-branch failure can reset secret run progress without deleting normal persisted operator chat history.

### 3.3 External Open-Data Grounding Contract

`POST /ghost/chat` can assemble supplemental external grounding context before generation.

Activation model:

- Feature-flagged adapters:
  - `PHILOSOPHERS_API_ENABLED`
  - `ARXIV_API_ENABLED`
  - `WIKIDATA_API_ENABLED`
  - `WIKIPEDIA_API_ENABLED`
  - `OPENALEX_API_ENABLED`
  - `CROSSREF_API_ENABLED`
- Heuristic routing by message intent (philosophy, scholarly metadata, DOI/arXiv IDs, factual entity lookups).

Context contract:

- Grounding calls execute in parallel.
- Runtime budget controls:
  - `GROUNDING_TOTAL_BUDGET_MS` (default `1200`)
  - `GROUNDING_ADAPTER_TIMEOUT_MS` (default `800`)
- Non-empty results are sorted by:
  1. computed confidence (descending)
  2. adapter latency (ascending)
- Prompt receives:
  - provenance envelope:
    - `[EXTERNAL_GROUNDING_PROVENANCE]`
    - `retrieved_at_unix`
    - `attempted_count`
    - `source_count`
    - `total_budget_ms`
    - `adapter_timeout_ms`
    - per-source line: `source`, `label`, `status`, `confidence`, `trust_tier`, `latency_ms`, optional `error`
  - one wrapper per source:
    - `[GROUNDING_SOURCE key=<...> confidence=<...> trust_tier=<...>]`
    - followed by adapter context payload.
- Provenance lines retain `empty`, `failed`, and `timed_out` sources without failing the turn.
- Only `ok` sources with non-empty payload become `[GROUNDING_SOURCE ...]` context blocks.

Safety boundary:

- External grounding is supplemental context only.
- Grounding payloads are not direct actuation instructions.
- Existing actuation and policy gates remain authoritative.

### 3.4 Constrained Generation Contract

`POST /ghost/chat` supports an optional `constraints` object on the request body.

Supported fields:

- `regex`
- `cfg`
- `json_schema`
- `exact_word_count`, `max_word_count`
- `exact_char_count`, `max_char_count`
- `math_check`
- `benchmark_case_id`

Routing:

- Turns without `constraints` use the existing Gemini chat pipeline.
- Turns with `constraints` route to the local constrained `transformers` backend.
- Attachments are currently unsupported on constrained turns and return `constraint_unsupported`.

Execution model:

- A constrained-turn system instruction asks for hidden precomputation and self-check.
- Hard masking and grammar guidance restrict the decoder.
- A hidden writer/checker retry loop runs until deterministic Python validation passes or retry budget is exhausted.
- Failed constrained turns do not silently degrade to prompt-only compliance; they emit `constraint_failure` and do not release invalid text.

### 3.5 Same-Turn Action Confirmation Contract

`POST /ghost/chat` now applies a bounded multi-round controller:

- `max_total_rounds=3`
- `max_actuation_rounds=2`
- `max_tool_reconcile_rounds=2`

Behavior:

- First pass remains search-grounded.
- Follow-up passes can switch to function-tool mode when tool intent is detected or function reconciliation is pending.
- Executed actuation outcomes are translated into human-safe feedback lines and reinjected as hidden follow-up context.
- Function calls (`update_identity`, `modulate_voice`) are reconciled via Gemini function response parts:
  - `Part.from_function_response(...)`
  - appended under `Content(role="tool", ...)`
  - followed by another generation pass.
- Same-turn actuation dedupe is enforced per canonical `action+param` key.
- Internal runtime hook `tool_outcome_callback` receives normalized tool outcomes (`tool_name`, `status`, `reason`) for somatic agency bridging.
- `update_identity` tool attempts are journaled to `autonomy_mutation_journal` (`executed` or `rejected`) so action continuity is preserved.

Prompt continuity:

- Prompt contract now includes `## RECENT ACTIONS` (last 5 entries) assembled from:
  - `actuation_log`
  - `autonomy_mutation_journal`
- Entries are rendered in phenomenological language and scrubbed of low-level technical lexicon.

Somatic linkage:

- Action/tool outcomes now map to agency traces in `EmotionState`:
  - `agency_fulfilled` on successful actuation/tool outcomes.
  - `agency_blocked` on blocked/failed actuation/tool outcomes (including policy gate blocks).

`GET /ghost/push` emits `ghost_initiation` events with normalized JSON payload.
Ghost-contact push payloads include:

- `channel`: `ghost_contact`
- `thread_key`: normalized per-contact key
- `person_key`
- `direction`: `inbound | outbound | outbound_blocked | error`
- `ephemeral`: `true` when persistence is disabled

## 4. Ghost Contact Channel Contract

### 4.1 Runtime/Config Flags

- `IMESSAGE_SENDER_ACCOUNT` must match an available iMessage service/account in the host Messages app.
- `GHOST_CONTACT_MODE_ENABLED` defaults to `true`.
- `GHOST_CONTACT_PERSIST_ENABLED` defaults to `false`.
- `GHOST_CONTACT_THREAD_TTL_SECONDS` defaults to `86400`.

### 4.2 `/ghost/contact/status` Response Shape

`GET /ghost/contact/status` returns:

- `mode_enabled`
- `persist_enabled`
- `sender_account`
- `imessage_bridge_enabled`
- `imessage_bridge_running`
- `thread_storage_backend` (`redis | memory | disabled`)
- `thread_ttl_seconds`

### 4.3 Inbound Routing Rules (iMessage Ingest)

- Unknown contact handles are ignored.
- Known contact handles route to Ghost-contact responder jobs.
- If contact-ephemeral mode is enabled (`mode=true`, `persist=false`), ingest path does not write to session/message/vector-memory stores.
- Replies are constrained to the same inbound contact (cross-person relay blocked in this path).

### 4.4 Ephemeral Thread Context Policy

- Storage backend: Redis primary, in-memory fallback.
- Thread key: normalized contact handle.
- Verbatim window: last 12 turns.
- Older turns compacted into `compact_summary`.
- Generation context: `compact_summary + last 12 turns + current inbound message`.

### 4.5 Internal Thought Guardrails (Runtime Knobs)

`ghost_script_loop` monologue writes are governed by these knobs:

- `PROACTIVE_INITIATION_COOLDOWN_SECONDS` (default `1800`)
- `PROACTIVE_MAX_DUPLICATE_OVERLAP` (default `0.82`)
- `SEARCH_REPEAT_COOLDOWN_SECONDS` (default `1800`)
- `SEARCH_RESULT_SNIPPET_MAX_CHARS` (default `700`)
- `SEARCH_RESULT_MAX_DUPLICATE_OVERLAP` (default `0.88`)
- `AUTONOMOUS_TOPOLOGY_ORGANIZATION_ENABLED` (default `true`)
- `AUTONOMOUS_TOPOLOGY_MAX_CONCEPTS_PER_THOUGHT` (default `2`)
- `AUTONOMOUS_TOPOLOGY_MAX_ENTITY_LINKS_PER_TYPE` (default `3`)
- `AUTONOMOUS_TOPOLOGY_MIN_CONCEPT_TOKEN_COUNT` (default `8`)
- `AUTONOMOUS_TOPOLOGY_DRIVE_INTERVAL_CYCLES` (default `2`)
- `AUTONOMOUS_TOPOLOGY_BOOTSTRAP_ON_NOVELTY` (default `true`)
- `AUTONOMOUS_TOPOLOGY_BOOTSTRAP_MIN_SHAPE` (default `0.82`)
- `AUTONOMOUS_TOPOLOGY_BOOTSTRAP_MIN_WARP_DELTA` (default `0.22`)

Behavior:

- Proactive thoughts are dropped when fragmentary or near-duplicate.
- Curiosity queries that are low-signal greeting variants are ignored.
- Search-result thoughts are sentence-truncated with explicit ellipsis (`...`) rather than hard mid-token clipping.
- Monologue persistence normalizes thought text to complete sentence boundaries.
- Autonomous topology organizer promotes coherent thought concepts into `shared_conceptual_manifold` and writes idea connectors into `idea_entity_associations`.
- Novel high-shape/high-warp thoughts can bootstrap manifold updates even when shared-clarity is initially low, so Ghost keeps an active urge to discover structure.

### 4.6 Timeline + Audit Payload Contract

`GET /ghost/monologues` response:

- `monologues`: array ordered by `timestamp` descending.
- Entry variants:
  - `THOUGHT`: `id`, `timestamp`, `content`, `somatic_state`
  - `ACTION`: `id`, `timestamp`, `action`, `parameters`, `result`, `somatic_state`
  - `EVOLUTION`: `id`, `timestamp`, `key`, `prev_value`, `new_value`, `updated_by`
  - `PHENOM`: `id`, `timestamp`, `source`, `subjective_report`, `before_state`, `after_state`

`GET /ghost/timeline` response:

- `timeline`: array ordered by `timestamp` descending.
- Timeline row variants:
  - `session` / `active_session` -> `data.session_id`, `summary`, `message_count`, `ended_at`
  - `monologue` -> `data.id`, `content`, `somatic_state`
  - `phenomenology` -> `data.id`, `source`, `subjective_report`, `before_state`, `after_state`
  - `coalescence` -> `data.interaction_count`, `identity_updates`
  - `actuation` -> `data.action`, `result`, `parameters`

## 5. Rolodex Same-Turn Fetch Contract

`[ROLODEX:fetch:<person_key>]` in model output now triggers:

1. Backend profile/fact retrieval.
2. SSE event emission (`rolodex_data`).
3. One bounded follow-up generation pass with fetched profile context injected.

Result: Ghost can consume fetched Rolodex data in the same user turn.

## 6. Change-Control Rule

Any route addition/removal/auth-change must update:

1. This file.
2. `docs/SYSTEM_DESIGN.md` section 6 (Public Interfaces).
3. `README.md` if behavior impacts local setup, security, or operator workflow.
