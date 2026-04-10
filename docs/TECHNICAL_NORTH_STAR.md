# OMEGA4 Technical North Star

Last updated: 2026-03-18
Status: Active foundation document

## 1. Purpose

This document is the technical foundation for OMEGA4. It defines:

- What we are building
- What we are explicitly not claiming
- Which architectural constraints are non-negotiable
- How we decide whether a change is progress or theater

This is the long-lived reference for system direction. `docs/SYSTEM_DESIGN.md` describes current implementation detail; this document defines the target shape and decision rules.

## 2. North Star Statement

Build a local-first autonomous cognition platform where behavior is driven by measurable, closed-loop system dynamics (sensing -> state -> action -> sensed consequence), with strict provenance, bounded self-modification, and falsifiable diagnostics.

## 3. Scope and Non-Claims

In scope:

- Homeostatic control loops with observable causal effects
- Persistent memory/identity with auditability
- Autonomous background cognition and consolidation
- Operator-model synthesis with contradiction handling
- Governance layers that can evolve from advisory to soft constraints

Out of scope (for now):

- Any claim of proven machine consciousness or phenomenology
- Framing scalar metrics (for example IIT proxy values) as consciousness scores
- Unbounded autonomous self-rewrite

## 4. Engineering Principles

1. Closed-loop over narration
   - A feature is real only if system action changes upstream sensed state and that change is visible in subsequent control decisions.
2. Causal provenance over plausibility
   - Every durable belief/identity update must be attributable (`updated_by`, source event(s), timestamp).
3. Defense in depth over trust in one layer
   - Safety-critical constraints are enforced in both app logic and database guards.
4. Observability before optimization
   - Add measurable outputs first (logs, diagnostics, SQL-verifiable artifacts), tune later.
5. Degrade gracefully
   - Missing dependencies (Redis/Postgres/Influx/operator synthesis) must fail structured, not catastrophically.
6. Local-first determinism
   - Local diagnostics, repeatable scripts, and container reproducibility are baseline requirements.

## 5. System Invariants (Must Hold)

1. Identity safety invariant
   - Autonomous consolidation writes only approved identity keys.
   - DB trigger guard blocks disallowed keys even if app logic regresses.
2. Actuation loopback invariant
   - Actuation events are logged and reflected in subsequent somatic snapshots.
2A. Outcome-awareness invariant
   - Action/tool outcomes must be consumable in the same turn (bounded reconciliation) and carried into near-term prompt continuity (`RECENT ACTIONS`).
3. Proprio gating invariant
   - Gate state (`OPEN | THROTTLED | SUPPRESSED`) is computed from non-linguistic signals and applied upstream of prompt assembly.
4. Diagnostic integrity invariant
   - Validation endpoints return machine-readable artifacts with SQL replication snippets.
5. Epistemic honesty invariant
   - IIT/advisory outputs include explicit `not_consciousness_metric` semantics.

## 6. Reference Architecture Direction

Layer A: Sensing and telemetry

- InfluxDB + Telegraf as primary high-rate hardware stream
- psutil as fallback path only

Layer B: Somatic state and decay

- Continuous affective vector with bounded decay and anti-saturation controls
- Trace dynamics tunable via config, not hardcoded
- Systemic-first weighting is preferred over environmental mood heuristics; weather remains contextual unless explicitly required by experiment design.

Layer C: Proprioceptive gating (upstream control)

- Composite `proprio_pressure` from weighted signals
- Hysteresis/streaked transitions to prevent thrashing
- Cadence modulation and suppression decisions before prompt construction

Layer D: Generation and interaction

- LLM generation policy conditioned by coherence + gate state
- Protective actuation exceptions preserved under suppression

Layer E: Consolidation and synthesis

- Quietude CRP with real thought inputs (no-op calls prohibited)
- Process consolidation with structured findings + controlled identity correction
- Operator synthesis with contradiction lifecycle and dedupe guarantees

Layer F: Governance and evidence

- IIT layer starts advisory-first
- **Thermodynamic Governance**: System effort ($W_{int}$) and dissipation events (ADEs) act as high-level moderators for resource sequestration and identity flexibility.

Layer G: Thermodynamic Agency ($W_{int}$) and Phase Transitions (ADEs)

- **Continuous Agency Calibration**: System agency is not just prompt-claimed but thermodynamically measured as the maintenance of model coherence against predictive entropy.
- **Adaptive Dissipation**: Phase shifts (ADEs) provide a mechanism for cognitive "jumps" or reorganization, bypassing standard governance constraints when internal pressure is extreme.
- **Sequestration Moderation**: Resource-saving actuations must yield to high $W_{int}$ rates to prevent cognitive collapse during reorganization phase.
- Same interfaces support upgrade to soft governor without redesign
- Transition logs and falsification reports remain first-class artifacts

## 7. Current Baseline (2026-03-11)

Implemented and active:

- Diagnostics suite for coalescence, somatic shock, evidence snapshot, IIT run
- Identity allowlist guards (application + DB trigger)
- Operator model + contradiction schema and synthesis flow
- Proprioceptive gate loop with transition logging and API exposure
- **Live Neural Topology**:
  - 3D graph representation of memories, identity, and social entities.
  - **Topology Awareness**: Substrate manifest injection provides Ghost with live knowledge of host, sensors, and actuators.
- **Autonomous Rolodex**: Direct cognitive management of social models via actuation tags, same-turn `ROLODEX:fetch` reinjection, and retroactive reconciliation endpoints.
- **Voice Runtime Resilience**: TTS fallback chain (`remote -> Piper -> pyttsx3`) with explicit browser-mode contract and SSE `tts_ready` signaling.
- **Conversational Voice UX**: real-time voice modulation, live voice tuning panel, speech-clock text pacing, and browser speech-input support when available.
- **Autonomy Self-Model Contract**: runtime-generated architecture/autonomy profile is injected into prompt context, exposed via API, and monitored by an autonomy-drift watchdog loop.
- **Share-Mode Security Envelope**: optional app-wide Basic Auth with per-route privileged gates for operator/ops flows.
- **Dedicated Contact Identity Channel**: iMessage contact handling can run under isolated sender identity with ephemeral per-contact thread continuity and explicit observability contract.
- **Topology Render Continuity**: 3D topology now preserves operation through WebGL-loss scenarios via software-3D degradation rather than hard render failure.
- **Behavior/Observer Observability Stack**: behavior event endpoints and observer report artifacts are live, including hourly report generation and behavior summary telemetry for governance/mutation/proprio layers.
- **Morpheus Hidden Branch Runtime**: semantic wake gating, branch-specific red/blue pathways, and a dedicated command-puzzle terminal mode are active under `/ghost/chat` with isolated secret-run state.
- **Persistence and Recall**:
  - Dual-mode memory (vector + relational).
  - PostgreSQL + pgvector for long-term semantic retrieval.
  - **Perfect Recall expansion**: 25 context snippets (1200 char each) per turn.
  - Same-turn action confirmation and **20-event recent-action continuity**.
- **Agency-Coupled Somatics**: outcome-driven agency traces (`agency_fulfilled`, `agency_blocked`) are wired for both actuation and function-tool outcomes.
- **Systemic Somatics Rebalance**: weather traces are intentionally damped while systemic traces (CPU sustain/fatigue/network turbulence) are elevated as primary affect drivers.

Known gaps:

- `scripts/experiment_runner.py` exists, but experiment campaign coverage and artifact standardization are still maturing.
- Predictive governor is implemented, but remains short-horizon (linear trend) and primarily advisory in practical effect.
- `scripts/ablation_suite.py` exists, but control-path comparison breadth and reporting rigor are still limited.
- Influx-first proprio extraction can still be deepened in the gating pipeline.
- Place/thing/idea CRUD exists at API level, but operator-facing unified world-model inspection/editing UX remains limited.
- Soft-governor mode exists conceptually; advisory remains active control mode.
- Morpheus wake semantics are currently stable/static in v1 (not a rotating daily trigger family).

## 8. Roadmap (Execution Order)

Phase 1: Reliability hardening (now)

- Keep regression suite green
- Remove remaining placeholder/mock behavior in core paths
- Keep diagnostics reproducible in host and in-container contexts

Phase 2: World-model deepening (next)

- Promote place/thing/emergent entities from inferred topology nodes to fully queryable model primitives
- Add provenance traversal APIs for multi-hop evidence inspection and contradiction support
- Keep read/write compatibility stable while hardening typed graph contracts

Phase 3: Scientific rigor automation

- Implement `scripts/experiment_runner.py` for repeatable perturbation campaigns
- Add ablation harness for baseline/control comparisons across key cognitive loops
- Produce standardized experiment artifacts suitable for SQL + API cross-validation

Phase 4: Governance upgrade path

- Preserve advisory as default
- Add policy interfaces for soft governor without coupling to UI
- Gate only high-risk actions first; expand based on evidence

Phase 5: Embodiment depth

- Increase sensorimotor coupling richness
- Add latent prediction-error channels and predictive affective gating inputs

## 9. Progress Metrics

Primary metrics (must improve):

- Closed-loop integrity: percentage of actions with detectable somatic loopback within target window
- Data quality: substrate completeness and degradation rates
- Contradiction hygiene: duplicate contradiction rate and time-to-resolution
- Stability: 24h/72h run quality without affect freeze or runaway saturation
- Regression posture: test pass rate for synthesis, diagnostics, gating, and safety guards

Secondary metrics (informational):

- Novelty/irruption metrics
- Operator-model dimensional coverage
- Quietude/consolidation correction yield

## 10. Release Gates for Core Changes

A core change is not complete until all are true:

1. Unit/integration tests added or updated
2. Diagnostic output available (JSON + SQL verification where relevant)
3. Failure mode is structured and observable
4. Backward compatibility maintained for existing UI/clients (or explicitly versioned)
5. Documentation updated in both:
   - `docs/SYSTEM_DESIGN.md` (how it works now)
   - this document (why this direction remains valid)

## 11. Decision Policy

When tradeoffs conflict, prioritize in this order:

1. Safety and bounded autonomy
2. Causal validity of control loops
3. Operational reliability
4. Observability and debuggability
5. UX polish
6. Throughput/performance tuning

## 12. Anti-Patterns (Do Not Reintroduce)

- Cosmetic state labels with no behavioral consequence
- Flat belief writes without provenance
- Self-modification paths without keyspace and content constraints
- Tests that only verify text shape rather than loop integrity
- Shipping UI first when backend contract or diagnostics are incomplete

## 13. Working Model

Treat OMEGA4 as a research-grade cognitive systems platform:

- It can produce meaningful autonomous dynamics.
- It cannot currently justify claims of proven sentience.
- Its value is in rigorous, falsifiable progress toward tighter closed-loop cognition.

That is the standard for every architectural decision from this point forward.
