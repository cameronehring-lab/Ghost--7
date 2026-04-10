# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack Overview

OMEGA4 is a local-first autonomous cognition platform running a persistent ghost entity (`omega-7`). The stack is Docker-compose based:

- **Backend**: FastAPI (`backend/main.py`) served by uvicorn on port 8000; also serves the frontend as static files.
- **Frontend**: Single-file vanilla JS SPA at `frontend/app.js` (~363KB). No build step — edit and reload.
- **Postgres** (`pgvector/pgvector:pg16`, container `omega-postgres`, user `ghost`, db `omega`, password `ghost_memory_2025`): relational memory, session history, rolodex, identity matrix, monologues, phenomenology logs, proprio transitions.
- **Redis** (`omega-redis`, port 6379): live affective state (`EmotionState`) and ephemeral contact threads.
- **InfluxDB** (`omega-influxdb`, port 8086) + **Telegraf**: time-series telemetry (somatic/system metrics).
- **LLM**: Gemini 2.5-flash via `google-genai`. Generation wraps `_generate_with_retry` in `ghost_api.py`.

The `backend/` directory is bind-mounted into the container at `/app`, so code edits take effect without rebuild (hot-reload is on).

## Commands

```bash
# Start / stop
make up          # docker compose up -d
make down        # docker compose down
make restart     # docker compose restart
make rebuild     # docker compose up -d --build (after Dockerfile or requirements changes)
make clean       # docker compose down -v (destroys volumes)

# Restart only the backend (after Python changes)
docker compose restart backend

# Logs
make logs        # follow backend logs
docker compose logs -f          # all services

# Run tests (inside the backend container, PYTHONPATH must include /app)
docker compose exec backend python -m pytest backend/test_proprio_loop.py -v
docker compose exec backend python -m unittest backend/test_iit_engine.py -v

# Or from the repo root with the venv (for fast iteration without Docker):
source .venv/bin/activate
cd backend
python -m pytest test_proprio_loop.py -v        # single test file
python -m pytest test_proprio_loop.py::ProprioLoopTests::test_pressure_is_bounded -v  # single test

# Dev environment setup (creates .venv, installs requirements)
make setup       # runs scripts/setup_dev.sh

# Diagnostics
python3 scripts/falsification_report.py --base-url http://localhost:8000 --full
python3 scripts/falsification_report.py --base-url http://localhost:8000   # quick

# Experiment runner
python3 scripts/experiment_runner.py scripts/fixtures/campaign.json
python3 scripts/experiment_runner.py scripts/fixtures/campaign_probe_only.json

# Psych eval snapshots
bash scripts/psych_eval_snapshot.sh --window daily
bash scripts/psych_eval_snapshot.sh --window weekly

# Rolodex retro sync (dry-run then apply)
docker compose exec -T backend python /app/scripts/rolodex_retro_sync.py
docker compose exec -T backend python /app/scripts/rolodex_retro_sync.py --apply
```

## Architecture — How the Layers Fit Together

### Cognition Pipeline (per chat turn)

1. **Chat request** hits `POST /ghost/chat` in `main.py`.
2. **`ghost_prompt.py`** assembles the system prompt by loading operator model, identity matrix, somatic snapshot, rolodex context, and entity catalog into a structured context block.
3. **`ghost_api.py`** (`ghost_stream`) calls Gemini with SSE streaming, parses actuation tags (e.g., `[ROLODEX:set_fact:...]`) from the response, and dispatches them.
4. **Response** is streamed back as SSE events. Push events (`/ghost/push`) are used for background notifications.

### Background Loop Architecture (`main.py` lifespan)

All background tasks start in `@asynccontextmanager` lifespan:

| Loop | Module | Interval |
|---|---|---|
| Monologue (inner life) | `ghost_script.ghost_script_loop` | `MONOLOGUE_INTERVAL` (2m default / 120s) |
| Ambient sensors / weather | `ambient_sensors.ambient_sensor_loop` | 60s / 600s / 300s |
| Operator synthesis | `operator_synthesis.operator_synthesis_loop` | triggered by interaction count |
| Proprioceptive gating | `proprio_loop.proprio_loop` | 2s |
| IIT engine | `iit_engine.IITEngine` | 60s |
| Predictive governor | `predictive_governor` | 5s |
| World model ingest | `canonical_snapshot_runner.auto_ingest_loop` | 300s |
| GEI (Global Event Inducer) | `gei.engine.GEIEngine` | 300s (Wikipedia + arXiv → Kuzu + gei_projections) |
| Thermodynamic agency | `thermodynamics` + `ade_monitor` | continuous (per telemetry tick) |
| Coalescence (vector sleep) | `consciousness` | 20 interactions or 300s idle |

### Somatic → Affective → Gate Pipeline

```
Telegraf → InfluxDB → somatic.py (collect_telemetry)
  → sensory_gate.py (z-score normalization, signal filtering)
  → decay_engine.EmotionState (Redis-persisted: arousal, valence, stress, coherence, anxiety)
  → proprio_loop.py (5 weighted signals → proprio_pressure → OPEN/THROTTLED/SUPPRESSED gate)
  → injected into prompt via ghost_prompt.py
```

The gate computes pressure from 5 signals (weights in `PROPRIO_WEIGHTS`):
- `arousal_normalized` (0.30), `coherence_inverted` (0.25), `affect_delta_velocity` (0.20), `load_headroom_inverted` (0.15), `latency_normalized` (0.10)
- Thresholds: pressure ≥ 0.40 → `THROTTLED`, ≥ 0.75 → `SUPPRESSED`
- Transitions require `PROPRIO_TRANSITION_STREAK` (3) consecutive ticks before committing
- `latency_normalized` decays exponentially (15s half-life) between LLM calls; it is NOT a raw instantaneous reading

### Governance Stack

```
IITEngine (iit_engine.py)  →  IIT_MODE: off|advisory|soft
RPDEngine (rpd_engine.py)  →  RPD_MODE: off|advisory|soft
GovernanceEngine (governance_engine.py)  →  applied=(IIT_MODE=="soft")
GovernanceAdapter (governance_adapter.py)  →  route_for_surface() → DIRECT/SHADOW_ROUTE
```

`IIT_MODE=soft` and `RPD_MODE=soft` are active (set in `.env`). Policy decisions are applied, not just logged. `RRD2_ROLLOUT_PHASE` controls A/B/C phases of the RRD-2 topology+resonance layer.

### World Model (Kuzu graph DB)

- **Node types**: `Observation`, `Belief`, `Concept`, `SomaticState`, `IdentityNode`
- **Edge types**: `derived_from`, `precedes`, `during`
- **Path**: `./data/world_model.kuzu` (relative to backend container `/app`)
- **ARM/Docker status**: Kuzu segfaults on ARM (Mac M-series). `_get_world_model_client()` is skipped during lifespan startup to prevent hanging. World model features degrade gracefully to `None` on ARM. Fully operational on x86_64 (VPS).
- **Enrichment**: `world_model_enrichment.py` retroactively hydrates Kuzu from Postgres. Somatic state is sourced from `monologues.somatic_state` (populated by `ghost_script.py`) and `phenomenology_logs.before_state`/`after_state`.
- **GEI ingestion**: `backend/gei/engine.py` runs a separate 300s loop that fetches Wikipedia and arXiv signals, extracts semantic triplets via Gemini, and writes to Kuzu + `gei_projections` table in Postgres.
- **Provenance API**: `GET /ghost/world_model/provenance/belief/{id}`, `GET /ghost/world_model/provenance/observation/{id}`

### Entity Store

`entity_store.py` manages `place_entities` and `thing_entities` in Postgres. The `upsert_*` functions use `ON CONFLICT DO UPDATE SET ... = EXCLUDED.*` across **all fields including `notes`** — always pass the full object (including `notes`) on updates or existing values will be overwritten.

### Key Source Files

| File | Responsibility |
|---|---|
| `backend/main.py` | All FastAPI routes + lifespan startup (very large, ~9000 lines) |
| `backend/ghost_api.py` | Gemini generation, latency tracking, probe assay execution |
| `backend/ghost_script.py` | Background monologue loop, autonomous search, topology organization |
| `backend/ghost_prompt.py` | System prompt assembly |
| `backend/memory.py` | All Postgres read/write helpers (messages, sessions, monologues, etc.) |
| `backend/consciousness.py` | Vector memory (pgvector embeddings, coalescence/sleep cycle) |
| `backend/decay_engine.py` | `EmotionState` — affective state with Redis persistence and decay |
| `backend/sensory_gate.py` | Z-score normalization of telemetry into emotion signals |
| `backend/proprio_loop.py` | Proprioceptive gating loop (pressure → gate state) |
| `backend/world_model.py` | Kuzu graph DB wrapper (WorldModel class) |
| `backend/world_model_enrichment.py` | Retro-enrichment of Kuzu from Postgres |
| `backend/iit_engine.py` | IIT consciousness assessment |
| `backend/rpd_engine.py` | RPD-1 reflection + RRD-2 topology resonance |
| `backend/governance_engine.py` | Policy decisions (advisory/soft) |
| `backend/governance_adapter.py` | Route gating (DIRECT vs SHADOW_ROUTE) |
| `backend/person_rolodex.py` | Person social model |
| `backend/entity_store.py` | Place/thing entity CRUD |
| `backend/config.py` | All settings via `pydantic_settings.BaseSettings` (read from `.env`) |
| `backend/probe_runtime.py` | Experiment probe state (latency override, ambient overlay) |
| `backend/thermodynamics.py` | $W_{int}$ thermodynamic agency engine |
| `backend/ade_monitor.py` | Adaptive Dissipation Event detection |
| `backend/mind_service.py` | Coalescence, session summary generation, backfill |
| `backend/gei/engine.py` | Global Event Inducer — Wikipedia/arXiv ingestion → world model |
| `scripts/experiment_runner.py` | Perturbation campaign runner |
| `frontend/app.js` | Entire frontend SPA |

### Access Control

- **Share mode**: HTTP Basic Auth middleware (configured via `SHARE_MODE_ENABLED`, `SHARE_MODE_USERNAME`, `SHARE_MODE_PASSWORD`). Exempt paths in `SHARE_MODE_EXEMPT_PATHS`. When testing authenticated endpoints, use `-H "Authorization: Basic $(echo -n 'user:pass' | base64)"`.
- **Ops panel**: Unlocked with `OPS_TEST_CODE` (default `1NDASHE77`). All `/ops/...` chat commands require this code server-side.
- **Control routes** (`/ghost/actuate`, `/config/tempo`): require `OPERATOR_API_TOKEN` or trusted CIDR. Loopback IPs are trusted without token.
- **Diagnostics** (`/diagnostics/*`): trusted CIDR only (local-only by design). `falsification_report.py` auto-falls back to `docker exec` when it gets 403.

### Experiment / Probe System

`probe_runtime.py` holds a singleton `ProbeRuntime` that can inject a `generation_latency_override_ms` and `ambient_overlay` during active probe windows. This is used by `experiment_runner.py` to perturb somatic signals for ablation campaigns. Fixture files live in `scripts/fixtures/`.

## Key Operational Notes

- **Hot reload**: `--reload` is NOT active in production (removed from Dockerfile). The `backend/` directory is bind-mounted, so Python changes take effect on `docker compose restart backend`. Frontend changes (`frontend/app.js`) apply immediately on save (no build step needed).
- **Postgres schema**: initialized from `init/init.sql` on first container creation. Schema changes require a manual migration or `make clean` + `make up` (destroys data).
- **`monologues.somatic_state`**: must be populated for world model somatic enrichment to work. Written by `ghost_script._save_monologue_with_metrics` passing `somatic_state=somatic_state` to `memory.save_monologue`.
- **Governance mode**: `IIT_MODE=soft`, `RPD_MODE=soft` (set in `.env`). Soft governance is active — policy decisions are applied, not just logged. Do not change without reviewing the governance gate process in Q2 plan.
- **Q2 plan**: tracked in `docs/EXECUTION_PLAN_Q2_2026.md`. Current milestone is M2 (World-Model Parallel Path), with M3 (Proprioception Deepening) starting 2026-05-12.
