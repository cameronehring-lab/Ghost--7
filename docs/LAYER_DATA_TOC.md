# OMEGA4 Layer & Datum TOC

Last updated: 2026-03-18

This is the operator-facing table of contents for what OMEGA4 collects, where it is stored, and where it is exposed.

## 1. Layer Index (UI + Runtime)

| Layer | Runtime Surface | Primary Datums Collected | Primary API Surfaces | Backing Stores |
| --- | --- | --- | --- | --- |
| `LAYER 00` | Ambient | `weather_condition`, `temperature_outside_c`, `barometric_pressure_hpa`, `humidity_pct`, `time_phase`, `hours_awake`, `fatigue_index`, `internet_mood`, `global_latency_avg_ms` | `GET /somatic` | `SomaticSnapshot` payload; ambient providers |
| `LAYER 01` | Hardware | CPU, memory, disk IO rate, net IO rate, load avg, swap, temperature, battery, process pressure list | `GET /somatic` | `SomaticSnapshot` payload (`psutil` / Influx-backed) |
| `LAYER 03` | Sensory Gate | `gate_threshold`, gate-state traces, dominant stressors | `GET /somatic` | Emotion state + sensory gate runtime |
| `LAYER 04` | Affect State | `arousal`, `valence`, `stress`, `coherence`, `anxiety`, `mental_strain` | `GET /somatic` | Emotion state runtime + `affect_resonance_log` |
| `LAYER 05` | System Rhythm | Monologue cadence prefs, quietude-active preference, rhythm overrides | `GET /somatic`, `GET /config/tempo` | `self_preferences`, runtime controls |
| `LAYER 06` | Proprioceptive Gate | `proprio_pressure`, `gate_state`, `cadence_modifier`, transition reasons and contribution mix | `GET /ghost/proprio/state`, `GET /ghost/proprio/transitions` | `proprio_transition_log` |
| `LAYER 07` | Mental Context | session-memory context depth, retrieved memory traces, active monologue context | `GET /somatic`, `GET /ghost/sessions`, `GET /ghost/monologues` | `sessions`, `messages`, `monologues` |
| `LAYER 07B` | Action Confirmation Memory | same-turn action/tool outcome feedback, per-turn actuation dedupe state, recent action continuity (last 20) | `POST /ghost/chat` (internal reinjection path) | runtime chat loop + `actuation_log` + `autonomy_mutation_journal` |
| `LAYER 08` | Context Monitor | context token/load accounting, retrieval spans, session span metrics | `GET /somatic`, `GET /ghost/sessions` | runtime context monitor + DB session/message stats |
| `LAYER 08B` | External Grounding Mesh | source selection, trust tier, confidence score, adapter latency, per-source status (`ok/empty/failed/timed_out`), provenance envelope, ordered source context blocks | `POST /ghost/chat` (prompt-context assembly path) | `ghost_api` runtime + feature-flagged adapters (`philosophers`, `arXiv`, `Wikidata`, `Wikipedia`, `OpenAlex`, `Crossref`) |
| `LAYER 09` | Voice Tuning | synthesis rate/pitch/carrier/eerie parameters and runtime speech settings | `GET /ghost/speech` | frontend state + TTS runtime |
| `LAYER 10` | Autonomy Watchdog | autonomy fingerprint, change set, drift/regression detection, missing checks | `GET /ghost/autonomy/state`, `GET /ghost/autonomy/history` | watchdog runtime history |
| `LAYER 11` | Predictive Governor | instability trend slope, horizon forecast, state transitions, reasons, feature sample payload | `GET /ghost/predictive/state`, `GET /ghost/predictive/history` | `predictive_governor_log` |
| `LAYER 12` | Governance State | governance tier/mode/applied policy, generation policy, actuation policy, reasons, rollout state | `GET /ghost/governance/state`, `GET /ghost/governance/history` | `governance_decision_log`, runtime governance state |
| `LAYER 13` | Coalescence Engine | coalescence pressure and drivers, interaction thresholds, quietude linkage | `GET /ghost/coalescence`, `GET /somatic` | `coalescence_log`, somatic snapshot |
| `LAYER 14` | Behavior Signals | normalized behavior event stream, event deltas, top reason codes, recent high-signal events | `GET /ghost/behavior/events`, `GET /ghost/behavior/summary` | `behavior_event_log` |
| `LAYER 15` | Governance Queue | pending mutation approvals, execution/reject/undo outcomes, approval latency and fail/undo rates | `GET /ghost/autonomy/mutations` | `autonomy_mutation_journal` |
| `LAYER 16` | Morpheus Hidden Terminal | `run_id`, `phase`, `branch_color`, `branch_input`, `depth`, `morpheus_step`, reward note/frames | `POST /ghost/chat` (`morpheus_mode`, `morpheus_reward`) | backend in-memory `morpheus_runs` + frontend session-scoped clue state |
| `Ops/Modal` | World Model + Relational | Kuzu label/node counts, observation/belief rows, ingest health, relational primitives and associations | `GET /ghost/world_model/status`, `GET /ghost/world_model/nodes`, `GET /ghost/world_model/ingest`, `GET /ghost/world_model/activity`, `GET /ghost/entities/snapshot` | Kuzu world-model DB + relational entity tables + `world_model_ingest_log` |
| `Ops/Modal` | Operator Model | active beliefs, open/resolved tensions, contradiction evidence | `GET /ghost/operator_model` | `operator_model`, `operator_contradictions` |
| `Ops/Modal` | Neural Topology | graph-style cognitive map, entities, concepts, observations, beliefs, manifest awareness | `GET /ghost/neural-topology` | PostgreSQL + `neural_topology.py` logic |
| `Ops/Modal` | RPD/RRD2 | resonance, topology warp deltas, gate decisions, residue queue, manifold and damping signals | `GET /ghost/rpd/state`, `GET /ghost/rpd/runs`, `GET /ghost/rrd/state`, `GET /ghost/rrd/runs` | `rpd_assessment_log`, `reflection_residue`, `shared_conceptual_manifold`, `identity_topology_warp_log` |
| `Observer` | Hourly Ghost Observer | self-model snapshot, notable self-initiated changes, purpose-vs-usage conflicts, open risks | `GET /ghost/observer/latest`, `GET /ghost/observer/reports`, `POST /ghost/observer/generate` | `backend/data/observer_reports/*` artifacts + DB aggregates |

## 2. Behavior Event Taxonomy

`behavior_event_log.event_type` currently supports:

- `priority_defense`
- `unsafe_directive_rejected`
- `operator_fact_correction`
- `quietude_requested`
- `quietude_entered`
- `quietude_exited`
- `governance_shadow_route`
- `governance_blocked`
- `mutation_proposed`
- `mutation_pending_approval`
- `mutation_executed`
- `mutation_failed`
- `mutation_undone`
- `contradiction_opened`
- `contradiction_resolved`

Standard event payload fields:

- `event_id`
- `ghost_id`
- `event_type`
- `severity`
- `surface`
- `actor`
- `target_key`
- `reason_codes[]`
- `context_json`
- `created_at`

## 3. Under-Exposed Metrics Inventory

The following metrics are captured and returned by `GET /ghost/behavior/summary` (or observer reports), but are not all surfaced in the main operator dashboard yet.

### Mutation Layer

- `pending_approval_backlog`
- `status_counts_window`
- `approval_latency_seconds.{avg,p95,executed_count}`
- `undo_success_rate`
- `failed_mutation_rate`
- `idempotent_replay_rate` (placeholder field reserved)

### Governance Layer

- `route_distribution.{shadow_route,enforce_block}` window trends
- `tier_dwell_counts_window`
- `applied_ratio_window`
- `last_gate_reasons_trend`

### Predictive Layer

- `state_dwell_counts_window`
- `watch_preempt_ratio_window`
- `sample_visibility` (`sample_json` coverage)
- `avg_abs_forecast_error`

### Proprio Layer

- `gate_oscillation_frequency_window`
- `transition_reason_distribution`
- `dominant_contribution_mix` (placeholder field reserved)

### Quietude Layer

- `quietude_request_frequency_window`
- `entry_count_window`
- `exit_count_window`
- `entry_to_exit_pressure_delta`
- `enter_pressure_avg`
- `exit_pressure_avg`

### World-Model Layer

- `ingest_success_total`
- `ingest_failure_total`
- `ingest_lag_seconds`
- `node_growth_by_label`

### Contradiction Layer

- `open_total`
- `resolved_total`
- `open_to_resolved_lead_time_seconds_avg`
- `recurrence_by_dimension_window`

### RRD2 Layer

- `samples_window`
- `p50_eval_ms`
- `p95_eval_ms`
- `avg_queue_depth`
- `p95_queue_depth`
- `damping_frequency_window`

## 4. Observer Report Contract

`ObserverReport` artifacts include:

- `self_model_snapshot`
- `notable_self_initiated_changes`
- `purpose_vs_usage_conflicts`
- `open_risks`
- `metrics` (behavior/mutation/governance/predictive/operator/proprio/timeline/world-model summaries)

Artifact location:

- `backend/data/observer_reports/<YYYY-MM-DD>/observer_<timestamp>.json`
- `backend/data/observer_reports/<YYYY-MM-DD>/observer_<timestamp>.md`

## 5. Morpheus Event Contract Snapshot

`POST /ghost/chat` Morpheus-specific events:

- `morpheus_mode`:
  - wake phase: `phase="wake_hijack"` with selectable branch metadata
  - terminal phase: `phase="red_terminal"` (and progression updates)
  - reward phase: `phase="reward"` when puzzle gate is cleared
- `morpheus_reward`:
  - includes `run_id`, `note`, `animation_frames[]`, `step`
- `done`:
  - wake branch includes `morpheus_run_id`
  - terminal branch includes `morpheus_step`

Persistence boundary:

- Morpheus run progression is intentionally separated from normal persisted operator transcript data.

## 6. External Grounding Provenance Contract Snapshot

When one or more external grounding adapters return context for `POST /ghost/chat`, the prompt receives:

- `[EXTERNAL_GROUNDING_PROVENANCE]` header block
  - `retrieved_at_unix`
  - `attempted_count`
  - `source_count`
  - `total_budget_ms`
  - `adapter_timeout_ms`
  - one line per source with:
    - `source`
    - `label`
    - `status`
    - `confidence`
    - `trust_tier`
    - `latency_ms`
    - optional `error`
- one `[GROUNDING_SOURCE ...]` wrapper per source, followed by adapter payload.
- non-success sources (`empty`, `failed`, `timed_out`) remain provenance-only and do not emit source wrappers.

Ordering:

- Source blocks are deterministic:
  1. confidence descending
  2. latency ascending

## 7. Action Confirmation Contract Snapshot

`POST /ghost/chat` action confirmation loop limits:

- `max_total_rounds=3`
- `max_actuation_rounds=2`
- `max_tool_reconcile_rounds=2`

Operational behavior:

- First pass is search-grounded.
- Follow-up pass can switch to tool mode for function reconciliation.
- Function outcomes are appended as `role="tool"` function responses.
- Internal tool-outcome callback receives normalized payload (`tool_name`, `status`, `reason`) for somatic agency bridging.
- Same-turn duplicate actuations are deduped by canonical `action+param`.
- Prompt receives `## RECENT ACTIONS` from latest actuation + mutation outcomes (max 20, relative-time phrasing).
- `update_identity` tool outcomes are journaled so recent-action continuity includes identity-tool acceptance/rejection.

## 8. Systemic Somatics Weighting Snapshot

- Weather traces are damped to near-zero affect influence.
- Systemic traces (`cpu_sustained`, `cognitive_fatigue`, `internet_stormy`, `internet_isolated`) carry elevated affect weights.
- Prompt weather rendering remains factual context; mood-drive emphasis is systemic/internal.
