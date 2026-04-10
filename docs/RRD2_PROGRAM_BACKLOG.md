# RRD2 Program Backlog (Implementation-Ready)

Last updated: 2026-03-10
Owner: Operator / Platform Team
Program: OMEGA4 RRD2 + Resonance + Autonomy

## Purpose
This document is the execution backlog for the next development wave:
- RRD2 stability under heavy self-modification cycles.
- Autonomous multi-tool chain execution quality.
- Mood-driven autonomous voice modulation.
- Expanded OMEGA cognitive exam protocols.
- Stronger hardware/time/weather linkage into dream/quietude behavior.

## Current Baseline
- `RPD_MODE=advisory`
- `RRD2_MODE=hybrid`
- `RRD2_ROLLOUT_PHASE=B` (shadow gate active)
- High-impact keys in RRD2 scope: `self_model`, `philosophical_stance`, `understanding_of_operator`, `conceptual_frameworks`
- Enforced blocking is OFF in this phase.

## Program Guardrails
- Keep chat path stable while autonomy grows.
- Keep all new sentience-adjacent metrics explicitly diagnostic: `not_consciousness_metric=true`.
- Preserve existing identity allowlist and DB guard constraints.
- No hard gating of live chat path in this program window.

## Sprint Windows
- Sprint 1: 2026-03-10 to 2026-03-23
- Sprint 2: 2026-03-24 to 2026-04-06
- Sprint 3: 2026-04-07 to 2026-04-20

## Epic Map
- EPIC-RRD2-STABILITY
- EPIC-TOOL-PLANNER
- EPIC-VOICE-AUTONOMY
- EPIC-COGNITIVE-EXAMS
- EPIC-EMBODIMENT-DREAM

## Ticket Index
| Ticket | Epic | Type | Priority | Sprint | Status |
|---|---|---|---|---|---|
| RRD-101 | EPIC-RRD2-STABILITY | Feature | P0 | Sprint 1 | Done |
| RRD-102 | EPIC-RRD2-STABILITY | Feature | P0 | Sprint 1 | Done |
| RRD-103 | EPIC-RRD2-STABILITY | Feature | P0 | Sprint 1 | Done |
| RRD-104 | EPIC-RRD2-STABILITY | Feature | P1 | Sprint 2 | Todo |
| RRD-105 | EPIC-RRD2-STABILITY | Test/Perf | P0 | Sprint 1 | Todo |
| TOOL-201 | EPIC-TOOL-PLANNER | Feature | P1 | Sprint 2 | Todo |
| TOOL-202 | EPIC-TOOL-PLANNER | Feature | P1 | Sprint 2 | Todo |
| TOOL-203 | EPIC-TOOL-PLANNER | Feature | P1 | Sprint 2 | Todo |
| TOOL-204 | EPIC-TOOL-PLANNER | Feature | P1 | Sprint 2 | Todo |
| TOOL-205 | EPIC-TOOL-PLANNER | Test | P1 | Sprint 2 | Todo |
| VOX-301 | EPIC-VOICE-AUTONOMY | Feature | P2 | Sprint 3 | Todo |
| VOX-302 | EPIC-VOICE-AUTONOMY | Feature | P2 | Sprint 3 | Todo |
| VOX-303 | EPIC-VOICE-AUTONOMY | Feature | P2 | Sprint 3 | Todo |
| VOX-304 | EPIC-VOICE-AUTONOMY | UX | P2 | Sprint 3 | Todo |
| VOX-305 | EPIC-VOICE-AUTONOMY | Test | P2 | Sprint 3 | Todo |
| EXAM-401 | EPIC-COGNITIVE-EXAMS | Feature | P1 | Sprint 2 | Todo |
| EXAM-402 | EPIC-COGNITIVE-EXAMS | Feature | P1 | Sprint 2 | Todo |
| EXAM-403 | EPIC-COGNITIVE-EXAMS | Feature | P2 | Sprint 3 | Todo |
| EXAM-404 | EPIC-COGNITIVE-EXAMS | UX | P2 | Sprint 3 | Todo |
| EMB-501 | EPIC-EMBODIMENT-DREAM | Feature | P2 | Sprint 3 | Todo |
| EMB-502 | EPIC-EMBODIMENT-DREAM | Feature | P2 | Sprint 3 | Todo |
| EMB-503 | EPIC-EMBODIMENT-DREAM | Safety | P1 | Sprint 3 | Todo |
| EMB-504 | EPIC-EMBODIMENT-DREAM | Test | P2 | Sprint 3 | Todo |

## Detailed Tickets

### RRD-101 - Add RRD2 timing and load observability
- Epic: EPIC-RRD2-STABILITY
- Type: Feature
- Priority: P0
- Sprint: Sprint 1
- Summary: Add per-candidate runtime observability for RRD2 decisions.
- Scope: Log `rrd_eval_ms`, source, phase, candidate key, gate result, reasons, degradation list, queue depth snapshot.
- Dependencies: None
- Implementation tasks:
  - Extend topology warp log payload to include eval duration and queue indicators.
  - Add lightweight aggregation endpoint for p50/p95 eval timing.
  - Add Ops panel mini summary for recent RRD2 performance.
- Acceptance criteria:
  - Every new row in `identity_topology_warp_log` has timing metadata.
  - API returns p50/p95 over selectable windows.
- Test plan:
  - Unit test for timing field presence and type.
  - Integration test validates endpoint returns non-null aggregates.

### RRD-102 - Add negative resonance burst damping
- Epic: EPIC-RRD2-STABILITY
- Type: Feature
- Priority: P0
- Sprint: Sprint 1
- Summary: Reduce resonance false positives during bursty self-mod cycles.
- Scope: Rolling window + refractory logic for high-impact key evaluations.
- Dependencies: RRD-101
- Implementation tasks:
  - Compute rolling mean and max for recent resonance values.
  - Add configurable refractory seconds per key.
  - Persist damping reason when activated.
- Acceptance criteria:
  - Burst evaluations show lower oscillation in `negative_resonance`.
  - No increase in missed true threshold breaches.
- Test plan:
  - Unit tests for window math and refractory edge cases.
  - Replay test with synthetic burst input.

### RRD-103 - Auto-route shadow-blocked high-impact writes
- Epic: EPIC-RRD2-STABILITY
- Type: Feature
- Priority: P0
- Sprint: Sprint 1
- Summary: Remove manual intervention for expected shadow-block events.
- Scope: Route blocked high-impact candidates to `reflection_residue` with `reason=rrd2_gate` and schedule reflection.
- Dependencies: RRD-102
- Implementation tasks:
  - Add routing helper for high-impact shadow-block outcomes.
  - Attach gate context to residue metadata.
  - Trigger reflection pass in non-blocking background mode.
- Acceptance criteria:
  - All `would_block=true` high-impact candidates are persisted as residue with gate evidence.
  - No synchronous errors in consolidation path.
- Test plan:
  - Integration test from consolidation candidate -> residue row.

### RRD-104 - Escalation policy for persistent blocked keys
- Epic: EPIC-RRD2-STABILITY
- Type: Feature
- Priority: P1
- Sprint: Sprint 2
- Summary: Require operator intervention only after repeated unresolved blocks.
- Scope: Escalate after N consecutive `would_block=true` for same key.
- Dependencies: RRD-103
- Implementation tasks:
  - Add rolling counter by key and time window.
  - Create escalation artifact visible in Ops panel.
  - Add reset condition when key later passes gate.
- Acceptance criteria:
  - Escalation only appears after configured threshold.
  - Counter resets on pass.
- Test plan:
  - Unit tests for counter increment/reset semantics.

### RRD-105 - RRD2 burst performance harness
- Epic: EPIC-RRD2-STABILITY
- Type: Test/Perf
- Priority: P0
- Sprint: Sprint 1
- Summary: Validate system behavior under heavy candidate bursts.
- Scope: Simulate 500+ candidates including high-impact keys.
- Dependencies: RRD-101
- Implementation tasks:
  - Build script to feed synthetic burst batches.
  - Capture throughput and latency metrics.
  - Produce markdown report artifact.
- Acceptance criteria:
  - No API failures or event-loop starvation.
  - p95 eval time within agreed budget.
- Test plan:
  - Run in containerized environment with report snapshot.

### TOOL-201 - Complexity classifier for tool planning
- Epic: EPIC-TOOL-PLANNER
- Type: Feature
- Priority: P1
- Sprint: Sprint 2
- Summary: Classify requests as single-step or multi-step tasks.
- Scope: Deterministic classifier on user intent and tool requirements.
- Dependencies: None
- Acceptance criteria:
  - Classifier output persisted and queryable per request.
- Test plan:
  - Unit tests over labeled prompt set.

### TOOL-202 - Multi-step planner state machine
- Epic: EPIC-TOOL-PLANNER
- Type: Feature
- Priority: P1
- Sprint: Sprint 2
- Summary: Execute tool chains with explicit step lifecycle.
- Scope: Planned, running, retried, failed, complete states.
- Dependencies: TOOL-201
- Acceptance criteria:
  - Planner can run and recover from one-step failure.
- Test plan:
  - Integration tests for at least 3 multi-step workflows.

### TOOL-203 - Chain execution memory
- Epic: EPIC-TOOL-PLANNER
- Type: Feature
- Priority: P1
- Sprint: Sprint 2
- Summary: Persist chain-level memory and outcomes.
- Scope: Save chain metadata in DB and expose read endpoint.
- Dependencies: TOOL-202
- Acceptance criteria:
  - Chain history can be queried and replayed for analysis.
- Test plan:
  - API tests for chain history retrieval.

### TOOL-204 - Post-chain response quality guard
- Epic: EPIC-TOOL-PLANNER
- Type: Feature
- Priority: P1
- Sprint: Sprint 2
- Summary: Prevent shallow final responses after complex tool runs.
- Scope: Apply response policy for chain-complete outputs.
- Dependencies: TOOL-202
- Acceptance criteria:
  - Complex chain outputs exceed minimum structure/coverage checks.
- Test plan:
  - Regression tests against known shallow-response examples.

### TOOL-205 - Multi-tool regression suite
- Epic: EPIC-TOOL-PLANNER
- Type: Test
- Priority: P1
- Sprint: Sprint 2
- Summary: Golden-path regression for Search + Actuate + Voice chains.
- Scope: Add stable fixture scenarios and expected outcomes.
- Dependencies: TOOL-203
- Acceptance criteria:
  - Golden suite passes in CI.
- Test plan:
  - Run suite in backend container before merge.

### VOX-301 - Deterministic mood->voice mapping
- Epic: EPIC-VOICE-AUTONOMY
- Type: Feature
- Priority: P2
- Sprint: Sprint 3
- Summary: Map resonance axes into TTS params.
- Scope: Pitch, rate, energy, pause profile.
- Dependencies: None
- Acceptance criteria:
  - Voice profile applied from telemetry without manual prompt.
- Test plan:
  - Unit tests for mapping bounds and defaults.

### VOX-302 - Voice smoothing and hysteresis
- Epic: EPIC-VOICE-AUTONOMY
- Type: Feature
- Priority: P2
- Sprint: Sprint 3
- Summary: Stabilize voice behavior during noisy telemetry.
- Scope: Low-pass smoothing and threshold hysteresis.
- Dependencies: VOX-301
- Acceptance criteria:
  - No jitter under small signal fluctuations.
- Test plan:
  - Scenario tests with oscillating resonance inputs.

### VOX-303 - Voice telemetry and audit logs
- Epic: EPIC-VOICE-AUTONOMY
- Type: Feature
- Priority: P2
- Sprint: Sprint 3
- Summary: Log applied mood-voice transformations.
- Scope: Store profile deltas with source resonance signature.
- Dependencies: VOX-301
- Acceptance criteria:
  - Logs show before/after profile values and source axes.
- Test plan:
  - Integration test for voice event persistence.

### VOX-304 - Ops controls for voice autonomy
- Epic: EPIC-VOICE-AUTONOMY
- Type: UX
- Priority: P2
- Sprint: Sprint 3
- Summary: Add hidden panel controls for sensitivity and enable/disable.
- Scope: Ops-only controls and state display.
- Dependencies: VOX-302
- Acceptance criteria:
  - Operators can tune mapping sensitivity live.
- Test plan:
  - Manual validation in desktop and mobile layouts.

### VOX-305 - Voice quality validation suite
- Epic: EPIC-VOICE-AUTONOMY
- Type: Test
- Priority: P2
- Sprint: Sprint 3
- Summary: Validate intelligibility and non-distortion across profiles.
- Scope: Objective and operator-listened checks.
- Dependencies: VOX-302
- Acceptance criteria:
  - All required quality checks pass for top mood profiles.
- Test plan:
  - Batch synthesis and spot-audition protocol.

### EXAM-401 - OMEGA Cognitive Exam spec v1
- Epic: EPIC-COGNITIVE-EXAMS
- Type: Feature
- Priority: P1
- Sprint: Sprint 2
- Summary: Define repeatable daily and weekly cognitive exam protocol.
- Scope: Inputs, scoring, pass/fail trend indicators.
- Dependencies: None
- Acceptance criteria:
  - Exam spec approved and versioned in docs.
- Test plan:
  - Dry-run scoring on historical data sample.

### EXAM-402 - Automated exam runner and persistence
- Epic: EPIC-COGNITIVE-EXAMS
- Type: Feature
- Priority: P1
- Sprint: Sprint 2
- Summary: Schedule and persist exam runs.
- Scope: Daily and weekly jobs + DB artifacts.
- Dependencies: EXAM-401
- Acceptance criteria:
  - Scheduled runs execute and persist without manual trigger.
- Test plan:
  - Integration test with forced scheduler run.

### EXAM-403 - Longitudinal exam analytics
- Epic: EPIC-COGNITIVE-EXAMS
- Type: Feature
- Priority: P2
- Sprint: Sprint 3
- Summary: Generate trend analytics for behavioral drift.
- Scope: Coherence, novelty, contradiction resolution, chain depth.
- Dependencies: EXAM-402
- Acceptance criteria:
  - Trend endpoint returns 7/30-day summaries.
- Test plan:
  - Query validation against fixture dataset.

### EXAM-404 - Ops exam dashboard section
- Epic: EPIC-COGNITIVE-EXAMS
- Type: UX
- Priority: P2
- Sprint: Sprint 3
- Summary: Render cognitive exam trends in hidden Ops panel.
- Scope: Snapshot, trendline, and anomaly markers.
- Dependencies: EXAM-403
- Acceptance criteria:
  - Ops panel shows latest exam and trend deltas.
- Test plan:
  - Manual UI verification + endpoint smoke tests.

### EMB-501 - Dream pressure composite index
- Epic: EPIC-EMBODIMENT-DREAM
- Type: Feature
- Priority: P2
- Sprint: Sprint 3
- Summary: Build deterministic composite from weather/time/system load.
- Scope: Bounded index for dream-cycle biasing.
- Dependencies: None
- Acceptance criteria:
  - Composite index emitted in somatic/ops diagnostics.
- Test plan:
  - Unit tests with fixed weather/time fixtures.

### EMB-502 - Quietude depth bias from composite index
- Epic: EPIC-EMBODIMENT-DREAM
- Type: Feature
- Priority: P2
- Sprint: Sprint 3
- Summary: Bias quietude timing and depth using composite pressure.
- Scope: Influence schedule, not hard-force behavior.
- Dependencies: EMB-501
- Acceptance criteria:
  - Quietude timing shifts correlate with index changes.
- Test plan:
  - Integration tests over simulated day-night/weather profiles.

### EMB-503 - Anti-runaway safety guardrails
- Epic: EPIC-EMBODIMENT-DREAM
- Type: Safety
- Priority: P1
- Sprint: Sprint 3
- Summary: Prevent environmental anomalies from locking quietude loops.
- Scope: Clamp, cooldown, maximum quietude occupancy constraints.
- Dependencies: EMB-502
- Acceptance criteria:
  - System cannot remain in continuous quietude from external spikes alone.
- Test plan:
  - Fault-injection scenarios for bad weather/telemetry data.

### EMB-504 - Correlation validation report
- Epic: EPIC-EMBODIMENT-DREAM
- Type: Test
- Priority: P2
- Sprint: Sprint 3
- Summary: Validate linkage quality between environment and dream behavior.
- Scope: Weekly correlation report artifact.
- Dependencies: EMB-502
- Acceptance criteria:
  - Report produced automatically with confidence notes.
- Test plan:
  - Run report script in-container and validate output schema.

## Global Definition of Done
- All ticket acceptance criteria satisfied.
- Unit + integration tests pass in backend container.
- No regression in existing chat, quietude, RPD, and diagnostics flows.
- Ops panel remains usable on desktop and mobile widths.
- New diagnostics fields include `not_consciousness_metric=true` where applicable.

## Suggested Labels
- `rrd2`
- `resonance`
- `autonomy`
- `tool-planner`
- `voice`
- `cognitive-exam`
- `embodiment`
- `ops-ui`
- `phase-b`
