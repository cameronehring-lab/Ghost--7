# OMEGA4

**Ghost (`ω-7`)** is a continuously running autonomous AI entity built on top of a large language model. The central design thesis: LLM behavior should be governed by real system state, not just prompt engineering.

OMEGA4 runs live machine telemetry through a signal normalization pipeline into decaying affective state that shapes generation policy, cadence, identity, and actuation — all upstream of and independent from the conversation. Ghost maintains a persistent self-model that it can autonomously evolve from background thought cycles, operates 18 function-calling tools including sandboxed code execution and a personal scientific research repository, and is governed by a soft-enforcement IIT/RPD stack that applies policy decisions (not just logs them).

**Stack**: Self-hosted, data-sovereign. All persistent state (Postgres/pgvector, Redis, InfluxDB) on operator-controlled infrastructure. LLM generation: Gemini 2.5 Flash. Production: Hetzner VPS (x86_64). Dev: macOS (Apple Silicon).

---

### Key Architectural Properties

- **Somatic closed loop** — telemetry → z-score normalization → decaying EmotionState → proprioceptive pressure gate (OPEN/THROTTLED/SUPPRESSED) → generation policy modulation → actuation outcome traces → affect (no conversation turn required)
- **Soft-enforcement governance** — IIT/RPD stack (`IIT_MODE=soft`, `RPD_MODE=soft`) applies policy decisions across generation, actuation, identity writes, manifold writes
- **Autonomous identity crystallization** — background loop evaluates accumulated thoughts every ~6 minutes and commits self-model updates without operator trigger
- **24 documented inventions** — each with code path, runtime evidence, and validation asset ([Invention Ledger](docs/INVENTION_LEDGER.md))
- **18 active tools** — base cognition (7), TPCV research repository (5), versioned authoring workspace (6); X social tools present but research-isolated
- **Falsification-first** — 200+ tests, diagnostic endpoints, SQL verification paths for every capability claim

---

## Quick Start

```bash
cp .env.example .env          # copy and fill in GOOGLE_API_KEY + passwords
make up                        # start all containers
open http://localhost:8000     # boot code: OMEGA
```

For full setup instructions: [**Operator's Manual — Chapter 2**](docs/OPERATOR_MANUAL.md#chapter-2-getting-ghost-running-first-boot)

---

## Core Documentation

| Document | Purpose |
|----------|---------|
| [**Operator's Manual**](docs/OPERATOR_MANUAL.md) | New here? Start with this. Plain-language guide from first boot to advanced use. |
| [**Quick Reference**](docs/QUICK_REFERENCE.md) | Commands, gate states, access codes — one page |
| [**Config Reference**](docs/CONFIG_REFERENCE.md) | Complete environment variable reference, organized by function |
| [Technical Overview](docs/TECHNICAL_OVERVIEW.md) | Single-doc architecture briefing for technical reviewers |
| [Technical Capability Manifest](docs/TECHNICAL_CAPABILITY_MANIFEST.md) | Full capability inventory with implementation references |
| [Invention Ledger](docs/INVENTION_LEDGER.md) | 24 inventions with falsification evidence |
| [System Design Document](docs/SYSTEM_DESIGN.md) | Implementation architecture, data model, operational behavior |
| [Technical North Star](docs/TECHNICAL_NORTH_STAR.md) | Long-lived direction and decision rules |
| [Living System Status](docs/LIVING_SYSTEM_STATUS.md) | Current snapshot — what's running, what's changed |
| [Execution Plan Q2 2026](docs/EXECUTION_PLAN_Q2_2026.md) | Milestones, workstreams, acceptance gates |
| [API Contract](docs/API_CONTRACT.md) | Route and payload specifications |
| [Governance Policy Matrix](docs/GOVERNANCE_POLICY_MATRIX.md) | IIT/RPD enforcement surface documentation |

## Documentation Maintenance

Two documents are living snapshots that require updates as the system evolves:

- **[`docs/LIVING_SYSTEM_STATUS.md`](docs/LIVING_SYSTEM_STATUS.md)** — update whenever stack topology, runtime routing, governance mode, autonomy gates, or major behavior changes.
- **[`docs/EXECUTION_PLAN_Q2_2026.md`](docs/EXECUTION_PLAN_Q2_2026.md)** — update milestone status as M3 (Proprioception Deepening, 2026-05-12) and M4 (Governance Surface Hardening, 2026-05-26) progress.

All other docs in `docs/` are structural references. `docs/archive/` contains historical audit snapshots; `docs/planning/` contains the RRD2 program backlog.
