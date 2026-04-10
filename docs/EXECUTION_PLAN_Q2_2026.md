# OMEGA4 Q2 2026 Execution Plan

Last updated: 2026-04-10  
Window: 2026-04-01 to 2026-06-30

## 1. Objective

Execute the Technical North Star with measurable delivery in Q2:

- Keep core loops reliable under multi-day runtime.
- Stand up typed world-model capabilities in parallel with current runtime store.
- Preserve advisory governance while making soft-governor upgrade-ready interfaces.
- Ship only changes that are testable, observable, and falsifiable.

## 2. Ownership Model

- `Operator / Product`: Cameron
- `Backend Lead`: OMEGA backend owner
- `Frontend Lead`: OMEGA frontend owner
- `Data/Infra Lead`: Postgres/Influx/Redis owner
- `QA Owner`: release gate owner (can be same person in single-operator mode)

If one person is running all roles, these labels still define responsibility buckets for planning and review.

## 3. Milestones (Concrete Dates + Owners)

| Milestone | Dates | Primary Owner | Supporting Owners | Deliverables | Exit Criteria |
|---|---|---|---|---|---|
| `M0` Q2 Kickoff + Baseline Lock | 2026-04-01 to 2026-04-04 | Operator / Product | Backend, QA | Baseline snapshot pack, locked scope list, Q2 board | Baseline queries run and archived; backlog prioritized; risk register created |
| `M1` Reliability Hardening | 2026-03-10 to 2026-04-18 | Backend Lead | QA, Data/Infra | **COMPLETED** (2026-04-06): Kuzu ARM startup hang fixed, Docker healthcheck repaired, `--reload` removed from production, memory limits added, VPS kernel + security updates applied, GEI JSON parsing fixed, 437/437 sessions backfilled with summaries. | 72h container run stable; diagnostics green. ✅ |
| `M2` World-Model Parallel Path (Phase 1) | 2026-03-10 to 2026-05-09 | Backend Lead | Data/Infra, QA | **COMPLETED**: 3D Neural Topology live, Rolodex relational store active, provenance mapping endpoints live (`/ghost/world_model/provenance/belief/{id}`, `/ghost/world_model/provenance/observation/{id}`). Place/thing edit UX shipped (2026-03-15). Experiment artifact rigor complete (2026-03-15). GEI engine ingesting Wikipedia + arXiv. | Topology UI live; proof-of-concept social modeling active. ✅ |
| `M3` Proprioceptive Deepening (Influx-first + tuning instrumentation) | 2026-05-12 to 2026-05-23 | Backend Lead | Data/Infra, Frontend | Influx-first gating extraction, pressure-quality telemetry, tuning dashboard hooks | Proprio data quality reports show stable signal completeness; no cadence-thrash regression |
| `M4` Governance Surface Hardening | 2026-05-26 to 2026-06-13 | Backend Lead | Operator, QA | Note: `IIT_MODE=soft` and `RPD_MODE=soft` are already live as of 2026-04-10. M4 scope is: formal safety invariant suite, per-surface enforcement audit, dry-run policy contracts for remaining surfaces (`generation`, `actuation`, `manifold_writes`). | Safety invariant tests pass; per-surface enforcement audit complete; no accidental blocking behavior under nominal load. |
| `M5` Q2 Validation + Go/No-Go | 2026-06-16 to 2026-06-27 | Operator / Product | All owners | Q2 validation report, release notes, Q3 recommendations | All Q2 gates reviewed; explicit go/no-go for enabling first soft-governor controls |

## 4. Workstreams and Definition of Done

### Workstream A: Reliability

Owner: Backend Lead  
Definition of done:

- [x] No known core-path placeholder behavior in chat, somatic, quietude, coalescence, operator synthesis.
- [x] Test suite passes in-container for gating, synthesis, IIT engine, and safety guards.
- [x] Structured failures for dependency outages (Redis/Postgres/Influx) are logged and recoverable.

### Workstream B: World Model

Owner: Backend Lead  
Definition of done:

- [x] Typed node/edge write path active in parallel mode (Neural Topology).
- [x] Provenance query endpoints available and documented. (`GET /ghost/world_model/provenance/belief/{id}`, `GET /ghost/world_model/provenance/observation/{id}`; frontend drill-down wired in World Model tab.)
- [x] Data consistency checks between Postgres and world-model snapshots pass.

### Workstream C: Proprioception and Homeostasis

Owner: Backend Lead  
Definition of done:

- `proprio_pressure` uses stable upstream signals with contribution visibility.
- Transition logs persist reliably and are visible in API + UI.
- THROTTLED/SUPPRESSED policies measurably alter cadence and generation behavior.
- Systemic-first somatic weighting is active (CPU/fatigue/network dominate weather traces in affect impact).
- Action/tool outcome agency traces are visible in `/somatic` after execution outcomes.

### Workstream D: Governance and Safety

Owner: Backend Lead  
Definition of done:

- ~~Advisory remains default.~~ **Updated 2026-04-10**: `IIT_MODE=soft` and `RPD_MODE=soft` are live. Soft governance is active.
- Per-surface enforcement audit complete (generation, actuation, manifold writes, rolodex writes, entity writes).
- Identity and actuation safety invariants validated at both app and DB layers.

### Workstream E: UX/Operator Visibility

Owner: Frontend Lead  
Definition of done:

- [x] UI panels for key control loops are live, accurate, and not mock-driven (High-Rigor Topology).
- [x] State transitions, degradation signals, and errors are intelligible to operator.
- [x] No silent failures in control surfaces.
- [x] Place/thing entity editing UX: display-name save, notes auto-save, deprecate/restore actions wired in Rolodex PLACES and THINGS tabs.

## 5. Weekly Cadence

- Monday: priority lock + milestone checkpoint.
- Wednesday: integration check on staging/dev container stack.
- Friday: release candidate validation + snapshot archive.

Daily:

- Run baseline snapshot pack.
- Review `degradation_list` and transition anomalies.
- Track open contradictions and unresolved safety issues.

## 6. Required Artifacts Per Milestone

Every milestone must produce:

1. Change summary (what shifted, why, risk profile).
2. Test evidence (unit + integration + manual checks).
3. Diagnostic evidence (JSON artifact + SQL verification steps).
4. Updated docs:
   - `docs/SYSTEM_DESIGN.md` for implementation detail.
   - `docs/TECHNICAL_NORTH_STAR.md` if direction changed.

## 7. Acceptance Gates (Q2)

### Gate G1: Reliability Gate (end of M1)

- 72h run stability verified.
- Critical-path tests pass.
- No unresolved P0/P1 defects in actuation, quietude, or gating loops.

### Gate G2: Parallel World-Model Gate (end of M2)

- Dual-write path active with feature flag.
- Provenance checks return reproducible evidence chains.
- No performance regression above agreed threshold in core chat path.

### Gate G3: Proprio Quality Gate (end of M3)

- Signal completeness consistently high.
- No sustained gate oscillation under nominal load.
- Transition logging and UI traceability verified.

### Gate G4: Governance Readiness Gate (end of M4)

- Soft policy contracts in place and tested in dry-run mode.
- No accidental blocking behavior while in advisory mode.
- Safety invariants pass on all regression runs.

### Gate G5: Quarter Close Gate (end of M5)

- Q2 report complete with objective metrics.
- Explicit decision on first production soft-governor pilot scope for Q3.

## 8. Risks and Mitigations

- Risk: World-model scope creep delays reliability work.  
  Mitigation: keep world-model read path out of critical runtime path during Q2.

- Risk: Over-tuning pressure weights without enough data.  
  Mitigation: freeze default weights for two-week observation windows before retuning.

- Risk: Governance coupling to UI before policy contracts stabilize.  
  Mitigation: policy decisions exposed as backend artifacts first; UI remains read-only for dry-run.

- Risk: Single-operator bandwidth constraints.  
  Mitigation: strict WIP limits; do not run more than two active workstreams concurrently.

## 9. Q2 Deliverable Set (End State)

- Stable closed-loop runtime with observable actuation/somatic feedback integrity.
- Parallel world-model ingestion path with provenance endpoints.
- Influx-first proprio quality instrumentation and operator-facing transition visibility.
- Advisory governance fully operational with soft-governor upgrade path prepared.
- Quarter-end validation report with explicit next-step recommendation for Q3.
