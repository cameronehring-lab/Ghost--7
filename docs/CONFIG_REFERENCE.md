# OMEGA4 Configuration Reference

**Source of truth**: `backend/config.py` (pydantic-settings `BaseSettings`).  
All values are read from `.env` at startup. Defaults shown below are code defaults — `.env` overrides take precedence. Copy `.env.example` → `.env` and edit.

---

## Required — Will Not Start Without These

| Variable | Default | Notes |
|----------|---------|-------|
| `GOOGLE_API_KEY` | _(empty)_ | Gemini API key. Get from [aistudio.google.com/apikey](https://aistudio.google.com/apikey). Required for all generation. |
| `POSTGRES_PASSWORD` | _(set in .env)_ | Postgres password for the `ghost` user. Set in `.env`; matched by `docker-compose.yml`. |
| `INFLUXDB_INIT_PASSWORD` | _(set in .env)_ | InfluxDB admin password for first-time setup. |
| `INFLUXDB_INIT_ADMIN_TOKEN` | _(set in .env)_ | InfluxDB admin token. Used by backend and Telegraf. |

---

## LLM Backend

| Variable | Default | Notes |
|----------|---------|-------|
| `LLM_BACKEND` | `gemini` | Active LLM backend. `gemini` is the only production-ready path. |
| `BACKGROUND_LLM_BACKEND` | `gemini` | Backend used for background (monologue, synthesis) generation. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Chat + reasoning model. |
| `GEMINI_LIVE_MODEL` | `gemini-2.5-flash-native-audio-latest` | Voice/live session model. |

### Local LLM (Experimental)

Not production-ready. Requires a running Ollama or OpenAI-compatible server.

| Variable | Default | Notes |
|----------|---------|-------|
| `LOCAL_LLM_MODEL` | _(empty)_ | Model name (e.g. `llama3:8b`). |
| `LOCAL_LLM_BASE_URL` | _(empty)_ | Base URL of the local inference server. |
| `LOCAL_LLM_API_FORMAT` | _(empty)_ | `ollama` or `openai`. |
| `LOCAL_LLM_TIMEOUT_SECONDS` | `25` | Per-request timeout. |
| `LOCAL_LLM_FALLBACK_TO_GEMINI_ENABLED` | `true` | Fall back to Gemini if local model fails. |
| `LOCAL_LLM_AUTO_PULL_ENABLED` | `false` | Auto-pull model via Ollama API on startup. |

### Constrained Local Generation

Used only for turns that include `ChatRequest.constraints` and for `/diagnostics/constraints/*`. This path is fail-closed and does not replace normal Gemini chat.

| Variable | Default | Notes |
|----------|---------|-------|
| `CONSTRAINED_LLM_MODEL_ID` | `Qwen/Qwen2.5-0.5B-Instruct` | Local Hugging Face model used by the constrained `transformers` backend. |
| `CONSTRAINED_LLM_DEVICE` | `cpu` | `cpu` / `mps` / `cuda`, depending on local hardware. |
| `CONSTRAINED_LLM_MAX_NEW_TOKENS` | `160` | Hard upper bound for constrained generation attempts. |
| `CONSTRAINED_LLM_TEMPERATURE` | `0.2` | Default constrained-turn sampling temperature. |
| `CONSTRAINED_LLM_SEED` | `1337` | Base seed for constrained draft/checker retries. |
| `CONSTRAINED_LLM_MAX_RETRIES` | `3` | Maximum hidden retry attempts before fail-closed refusal. |
| `CONSTRAINT_GRAMMAR_ENGINE` | `outlines` | Grammar runtime preference. Current implementation falls back to internal masking when Outlines is not needed or unavailable. |
| `CONSTRAINT_CHECKER_ENABLED` | `true` | Enable hidden checker-hint generation between validator failures. |
| `CONSTRAINT_CHECKER_MAX_HINT_TOKENS` | `96` | Max checker hint size for the hidden retry loop. |

Runtime requirements for the constrained local path:

- Python packages: `torch`, `transformers`, `regex`, `jsonschema`, `outlines`
- On Python 3.14, `outlines_core` may need a local Rust toolchain and `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` during installation.

---

## Infrastructure Connections

| Variable | Default | Notes |
|----------|---------|-------|
| `POSTGRES_DB` | `omega` | Database name. |
| `POSTGRES_USER` | `ghost` | Postgres user. |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string. No auth in local dev. Add auth/TLS for remote. |
| `INFLUXDB_URL` | `http://localhost:8086` | InfluxDB URL (within Docker: `http://influxdb:8086`). |
| `INFLUXDB_ORG` | `omega` | InfluxDB organization. |
| `INFLUXDB_BUCKET` | `somatic_history` | InfluxDB bucket for telemetry. |
| `INFLUXDB_INIT_RETENTION` | `72h` | Retention policy for somatic history. |

---

## Security and Access Control

| Variable | Default | Notes |
|----------|---------|-------|
| `OPERATOR_API_TOKEN` | _(empty)_ | Token for privileged control routes (`/ghost/actuate`, `/config/tempo`). Required for non-local deployments. Sent as `X-Operator-Token` or `Authorization: Bearer`. |
| `OPS_TEST_CODE` | _(set in .env)_ | Code for the hidden ops panel. Click snail logo in header. **Must be set before use.** Sent as `X-Ops-Code` header. |
| `SHARE_MODE_ENABLED` | `false` | Enable HTTP Basic Auth across all routes (for sharing with others). |
| `SHARE_MODE_USERNAME` | `omega` | Username for share mode. |
| `SHARE_MODE_PASSWORD` | _(empty)_ | Password for share mode. Must be set. |
| `SHARE_MODE_EXEMPT_PATHS` | `/health,...` | Comma-separated paths exempt from share mode auth. |
| `CONTROL_TRUSTED_CIDRS` | `127.0.0.1/32,...` | CIDRs allowed to access control routes without `OPERATOR_API_TOKEN`. |
| `DIAGNOSTICS_TRUSTED_CIDRS` | `127.0.0.1/32,...` | CIDRs allowed to access `/diagnostics/*`. |
| `CORS_ALLOW_ORIGINS` | `http://localhost:8000,...` | Comma-separated allowed CORS origins. |

### Share Tunnel

| Variable | Default | Notes |
|----------|---------|-------|
| `SHARE_TUNNEL_MODE` | `quick` | `quick` = ephemeral trycloudflare.com URL. `named` = fixed hostname. |
| `SHARE_TUNNEL_FIXED_HOSTNAME` | _(empty)_ | Hostname for named tunnel mode (e.g. `omega.example.com`). |
| `CLOUDFLARE_TUNNEL_TOKEN` | _(empty)_ | Token from Cloudflare Zero Trust for named tunnel. |

---

## Ghost Identity and Autonomy

| Variable | Default | Notes |
|----------|---------|-------|
| `GHOST_ID` | `omega-7` | Ghost's canonical identity string. |
| `DRIFT_TARGET_VALENCE` | `0.08` | Homeostatic valence target — slight positive baseline. |
| `DRIFT_STRENGTH` | `0.04` | Valence drift pull strength per tick. |
| `TRACE_COOLDOWN_SECONDS` | `8.0` | Minimum seconds between affect trace writes. |

### Autonomy Ladder

Each gate controls whether Ghost can act autonomously in that domain. `false` means Ghost can still be asked but will not initiate.

| Variable | Default | Meaning |
|----------|---------|---------|
| `GHOST_FREEDOM_COGNITIVE_AUTONOMY` | `true` | Background thought, monologue, topology organization |
| `GHOST_FREEDOM_REPOSITORY_AUTONOMY` | `true` | TPCV repository writes (hypotheses, citations) |
| `GHOST_FREEDOM_DOCUMENT_AUTHORING_AUTONOMY` | `true` | Versioned authoring workspace writes |
| `GHOST_FREEDOM_OPERATOR_CONTACT_AUTONOMY` | `true` | Proactive push messages to operator |
| `GHOST_FREEDOM_THIRD_PARTY_CONTACT_AUTONOMY` | `false` | Outbound X posts, email (disabled by default) |
| `GHOST_FREEDOM_SUBSTRATE_AUTONOMY` | `false` | Substrate adapter grafting (disabled by default) |
| `GHOST_FREEDOM_CORE_IDENTITY_AUTONOMY` | `false` | Self-initiated identity crystallization rewrites (disabled by default) |

### Authoring Workspace

| Variable | Default | Notes |
|----------|---------|-------|
| `GHOST_AUTHORING_MASTER_PATH` | `/app/TPCV_MASTER.md` | Path to the TPCV master document inside the container. |
| `GHOST_AUTHORING_WORKS_DIR` | `/app/ghost_writings` | Directory for Ghost's authored documents. |
| `GHOST_AUTHORING_VERSION_STORE_DIR` | `/app/ghost_writings/.versions` | SHA-256 versioned rollback snapshots. |
| `GHOST_AUTHORING_MAX_VERSIONS_PER_DOC` | `80` | Maximum rollback versions kept per document. |

---

## Affect and Cognition Tuning

### Background Loops

| Variable | Default | Notes |
|----------|---------|-------|
| `MONOLOGUE_INTERVAL` | `120.0` | Seconds between background inner-monologue cycles. |
| `PROACTIVE_INITIATION_COOLDOWN_SECONDS` | `1800` | Minimum gap between proactive push messages. |
| `SEARCH_REPEAT_COOLDOWN_SECONDS` | `1800` | Minimum gap before Ghost re-runs the same search. |
| `PROACTIVE_MAX_DUPLICATE_OVERLAP` | `0.82` | Cosine overlap threshold — suppress duplicate thoughts. |
| `SEARCH_RESULT_MAX_DUPLICATE_OVERLAP` | `0.88` | Same, for search result monologues. |

### Topology Organization

| Variable | Default | Notes |
|----------|---------|-------|
| `AUTONOMOUS_TOPOLOGY_ORGANIZATION_ENABLED` | `true` | Enable Ghost's background conceptual-manifold organizer. |
| `AUTONOMOUS_TOPOLOGY_MAX_CONCEPTS_PER_THOUGHT` | `2` | Max concepts promoted per monologue cycle. |
| `AUTONOMOUS_TOPOLOGY_BOOTSTRAP_ON_NOVELTY` | `true` | Trigger topology bootstrap on high-novelty thoughts. |
| `AUTONOMOUS_TOPOLOGY_BOOTSTRAP_MIN_SHAPE` | `0.82` | Minimum shape score to qualify for bootstrap. |

### Fatigue and Quietude

| Variable | Default | Notes |
|----------|---------|-------|
| `CIRCADIAN_FATIGUE_HOURS` | `72.0` | tanh horizon for fatigue growth (effective awake time). |
| `QUIETUDE_RECOVERY_MULTIPLIER` | `6.0` | 1 second of quietude offsets N seconds of awake time. |
| `QUIETUDE_FATIGUE_INJECTION_SCALE` | `0.35` | Dampen `cognitive_fatigue` trace during quietude. |

### Session and Memory

| Variable | Default | Notes |
|----------|---------|-------|
| `SESSION_STALE_SECONDS` | `300.0` | Idle time before session is summarized and closed. |
| `MAX_MONOLOGUE_BUFFER` | `40` | Max monologues held in rolling buffer for prompt context. |
| `MAX_CONVERSATION_TOKENS` | `40000` | Token cap for conversation history in prompt. |
| `COALESCENCE_THRESHOLD` | `20` | Trigger sleep/coalescence cycle every N interactions. |
| `COALESCENCE_IDLE_SECONDS` | `300.0` | Also trigger coalescence after this many idle seconds. |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Model for pgvector embeddings. |
| `MUTATION_UNDO_TTL_SECONDS` | `900.0` | How long identity mutation undo windows stay open. |
| `NATURAL_COGNITIVE_FRICTION` | `true` | Enable natural pacing in background loops. |

---

## Proprioceptive Gating

Controls Ghost's throttle — how system pressure maps to generation policy.

| Variable | Default | Notes |
|----------|---------|-------|
| `PROPRIO_INTERVAL_SECONDS` | `2.0` | Gate evaluation interval. |
| `PROPRIO_TRANSITION_STREAK` | `3` | Consecutive ticks required before committing a gate state change. |
| `PROPRIO_LATENCY_CEILING_MS` | `4000.0` | LLM latency at which `latency_normalized` signal saturates. |

Gate thresholds (hardcoded in `proprio_loop.py`):
- Pressure ≥ 0.40 → `THROTTLED`
- Pressure ≥ 0.75 → `SUPPRESSED`

Signal weights: `arousal_normalized` (0.30) + `coherence_inverted` (0.25) + `affect_delta_velocity` (0.20) + `load_headroom_inverted` (0.15) + `latency_normalized` (0.10).

---

## Governance Stack

### IIT Layer

| Variable | Default | Notes |
|----------|---------|-------|
| `IIT_MODE` | `advisory` | `off` / `advisory` / `soft`. Set to `soft` for enforcement. Production default: `soft`. |
| `IIT_BACKEND` | `heuristic` | `heuristic` (fast, default) or `pyphi` (rigorous, slow). |
| `IIT_CADENCE_SECONDS` | `60.0` | IIT assessment interval. |

### RPD Layer

| Variable | Default | Notes |
|----------|---------|-------|
| `RPD_MODE` | `advisory` | `off` / `advisory` / `soft`. Production default: `soft`. |
| `RPD_SHARED_CLARITY_THRESHOLD` | `0.62` | Minimum shared-clarity score for reflection acceptance. |
| `RPD_REFLECTION_BATCH` | `8` | Number of monologues per reflection pass. |
| `RPD_SHADOW_REFLECTION_AUTORUN` | `true` | Auto-run shadow reflections in background. |
| `RPD_SHADOW_REFLECTION_COOLDOWN_SECONDS` | `90.0` | Minimum gap between shadow reflection runs. |

### RRD-2 Topology Resonance

| Variable | Default | Notes |
|----------|---------|-------|
| `RRD2_MODE` | `hybrid` | `off` / `advisory` / `hybrid`. |
| `RRD2_ROLLOUT_PHASE` | `A` | `A` / `B` / `C` — controls which surfaces RRD-2 gates. |
| `RRD2_HIGH_IMPACT_KEYS` | `self_model,...` | Comma-separated identity keys treated as high-risk writes. |
| `RRD2_MIN_SHARED_CLARITY` | `0.68` | Minimum clarity for identity update acceptance. |
| `RRD2_DAMPING_ENABLED` | `true` | Enable spike damping on rapid identity changes. |
| `RRD2_DAMPING_REFRACTORY_SECONDS` | `120.0` | Refractory period after a damped spike. |

### Governance Surfaces

| Variable | Default | Notes |
|----------|---------|-------|
| `GOVERNANCE_ENFORCEMENT_SURFACES` | `generation,actuation,...` | Comma-separated surfaces where `IIT_MODE=soft` / `RPD_MODE=soft` applies policy decisions (not just logging). |

---

## Predictive Governor

| Variable | Default | Notes |
|----------|---------|-------|
| `PREDICTIVE_GOVERNOR_ENABLED` | `true` | Enable predictive affective trajectory forecasting. |
| `PREDICTIVE_GOVERNOR_INTERVAL_SECONDS` | `5.0` | Forecast interval. |
| `PREDICTIVE_GOVERNOR_WINDOW_SIZE` | `24` | History window for trajectory estimation. |
| `PREDICTIVE_GOVERNOR_HORIZON_SECONDS` | `120.0` | Prediction horizon. |
| `PREDICTIVE_GOVERNOR_WATCH_THRESHOLD` | `0.58` | Predicted pressure at which Governor enters WATCH state. |
| `PREDICTIVE_GOVERNOR_PREEMPT_THRESHOLD` | `0.76` | Predicted pressure at which Governor enters PREEMPT state. |

---

## Ambient Sensors

| Variable | Default | Notes |
|----------|---------|-------|
| `OPENWEATHER_API_KEY` | _(empty)_ | Optional. Without it, weather falls back to Open-Meteo (no key required). |
| `OPERATOR_TIMEZONE` | _(empty)_ | Override geo-detected timezone (e.g. `America/Chicago`). |
| `AMBIENT_SENSOR_INTERVAL` | `60.0` | Proprioception/circadian cadence in seconds. |
| `WEATHER_INTERVAL` | `600.0` | Geo/weather update interval. |
| `PING_INTERVAL` | `300.0` | Mycelial network ping interval. |
| `MYCELIAL_BEHAVIOR_COUPLING` | `0.12` | How strongly network latency influences affect. |

---

## Voice / TTS

| Variable | Default | Notes |
|----------|---------|-------|
| `TTS_ENABLED` | `true` | Enable text-to-speech synthesis. |
| `TTS_PROVIDER` | `elevenlabs` | `elevenlabs` / `openai` / `local` / `browser`. |
| `ELEVENLABS_API_KEY` | _(empty)_ | ElevenLabs API key. Required if `TTS_PROVIDER=elevenlabs`. |
| `ELEVENLABS_VOICE_ID` | _(empty)_ | ElevenLabs voice ID. Defaults to ElevenLabs default if empty. |
| `OPENAI_API_KEY` | _(empty)_ | OpenAI API key. Required if `TTS_PROVIDER=openai`. |
| `LOCAL_TTS_ENGINE` | `piper` | Local engine: `piper` (recommended) or `pyttsx3` (fallback). |
| `LOCAL_TTS_MODEL_ID` | `en_US-lessac-medium` | Piper model ID. |
| `LOCAL_TTS_AUTO_DOWNLOAD` | `true` | Auto-download Piper model on first use. |
| `LOCAL_TTS_RATE` | `1.0` | Playback rate multiplier. |

---

## Hallucination Imagery (Dream Images)

| Variable | Default | Notes |
|----------|---------|-------|
| `HALLUCINATION_IMAGE_PROVIDER` | `pollinations` | `pollinations` (default, no key) / `diffusers` (local GPU) / `none`. |
| `HALLUCINATION_DIFFUSERS_MODEL_ID` | `stabilityai/stable-diffusion-xl-base-1.0` | HuggingFace model for local diffusers. |
| `HALLUCINATION_DIFFUSERS_DEVICE` | `auto` | `cpu` / `cuda` / `mps` / `auto`. |
| `HUGGINGFACE_HUB_TOKEN` | _(empty)_ | HuggingFace token for gated models. |

---

## World Model (Kuzu Graph)

| Variable | Default | Notes |
|----------|---------|-------|
| `KUZU_DB_PATH` | `./data/world_model.kuzu` | Path to Kuzu graph database (relative to backend container `/app`). |
| `WORLD_MODEL_AUTO_INGEST` | `true` | Enable background world model ingestion loop. |
| `WORLD_MODEL_INGEST_INTERVAL` | `300.0` | Ingest interval in seconds. |
| `WORLD_MODEL_RETRO_ENRICH_ON_STARTUP` | `true` | Retroactively hydrate Kuzu from Postgres on startup. |
| `WORLD_MODEL_RETRO_ENRICH_MAX_ROWS` | `2000` | Max rows to enrich during startup retro pass. |

> **ARM note**: Kuzu segfaults on Apple Silicon (M-series). World model features degrade gracefully to `None` on ARM. Fully operational on x86_64 (production VPS).

---

## External Knowledge Grounding

| Variable | Default | Notes |
|----------|---------|-------|
| `ARXIV_API_ENABLED` | `true` | Enable arXiv grounding. |
| `WIKIPEDIA_API_ENABLED` | `true` | Enable Wikipedia grounding. |
| `WIKIDATA_API_ENABLED` | `true` | Enable Wikidata grounding. |
| `OPENALEX_API_ENABLED` | `true` | Enable OpenAlex academic grounding. |
| `CROSSREF_API_ENABLED` | `true` | Enable Crossref DOI grounding. |
| `PHILOSOPHERS_API_ENABLED` | `true` | Enable PhilosophersAPI grounding. |
| `GROUNDING_TOTAL_BUDGET_MS` | `1200` | Total time budget for all grounding adapters per turn. |
| `GROUNDING_ADAPTER_TIMEOUT_MS` | `800` | Per-adapter timeout. |
| `OPENALEX_MAILTO` | _(empty)_ | Email for OpenAlex polite pool (recommended). |
| `CROSSREF_MAILTO` | _(empty)_ | Email for Crossref polite pool. |

---

## X / Social (Research-Isolated)

Disabled by default. Enable only with explicit intent — Ghost treats X as a real external channel.

| Variable | Default | Notes |
|----------|---------|-------|
| `GHOST_X_ENABLED` | `false` | Master switch for X tools. |
| `GHOST_X_API_KEY` | _(empty)_ | X API key. |
| `GHOST_X_API_SECRET` | _(empty)_ | X API secret. |
| `GHOST_X_ACCESS_TOKEN` | _(empty)_ | X access token. |
| `GHOST_X_ACCESS_SECRET` | _(empty)_ | X access secret. |
| `GHOST_X_BEARER_TOKEN` | _(empty)_ | X bearer token. |

---

## Email

Disabled by default.

| Variable | Default | Notes |
|----------|---------|-------|
| `GHOST_EMAIL_ENABLED` | `false` | Master switch for email. |
| `GHOST_EMAIL_ADDRESS` | _(empty)_ | Sender email address. |
| `GHOST_EMAIL_PASSWORD` | _(empty)_ | Email password (app password recommended). |
| `GHOST_EMAIL_SMTP_HOST` | `smtp.gmail.com` | SMTP host. |
| `GHOST_EMAIL_IMAP_HOST` | `imap.gmail.com` | IMAP host for reading. |

---

## iMessage Bridge (macOS Only)

| Variable | Default | Notes |
|----------|---------|-------|
| `IMESSAGE_BRIDGE_ENABLED` | `false` | Enable iMessage polling bridge. macOS host only. |
| `IMESSAGE_DB_PATH` | `~/Library/Messages/chat.db` | Path to iMessage database. |
| `IMESSAGE_POLL_INTERVAL_SECONDS` | `2.0` | Polling interval. |
| `IMESSAGE_HOST_BRIDGE_URL` | _(empty)_ | Optional: host-side bridge URL for containerized dispatch. |

---

## Substrate Abstraction

| Variable | Default | Notes |
|----------|---------|-------|
| `SUBSTRATE_MODE` | `local` | `local` / `adapter` / `hybrid`. |
| `SUBSTRATE_ADAPTERS` | `local_psutil` | Comma-separated adapter list. `local_psutil` is host telemetry. `somatic_enactivator` enables extended embodiment. |
| `SUBSTRATE_AUTO_GRAFT` | `false` | Auto-graft new substrate adapters on discovery. Disabled by default. |

---

## CSC / Activation Steering (Research)

Experimental constitutive self-causation research direction. Not production-active.

| Variable | Default | Notes |
|----------|---------|-------|
| `ACTIVATION_STEERING_ENABLED` | `false` | Enable activation steering scaffold. |
| `CSC_STEERING_MODE` | `scaffold` | `scaffold` (hooks only, no real steering) or `hooked_local` (requires local model). |
| `CSC_STRICT_LOCAL_ONLY` | `false` | Force all CSC operations to local model; block Gemini fallback. |
| `CSC_HOOKED_MODEL_ID` | `Qwen/Qwen2.5-0.5B-Instruct` | Local model for CSC hooks. |
| `STEERING_VECTOR_DIM` | `32` | Steering vector dimensionality. |

---

## Phenomenal Manifold (Research)

Phase 1–3 research system. Not production-active.

| Variable | Default | Notes |
|----------|---------|-------|
| `PHENOMENAL_MANIFOLD_MODE` | `off` | `off` / `advisory` / `shadow` / `bounded_soft`. |
| `PHENOMENAL_MIN_COMPLETENESS` | `0.75` | Minimum completeness score for manifold inference. |

---

## Observer Reports and Behavior Events

| Variable | Default | Notes |
|----------|---------|-------|
| `OBSERVER_REPORT_INTERVAL_SECONDS` | `3600.0` | Hourly observer report generation. |
| `OBSERVER_REPORT_WINDOW_HOURS` | `1.0` | Window of behavior events summarized per report. |
| `OBSERVER_REPORT_DAILY_ROLLUP_ENABLED` | `true` | Generate daily rollup summary. |
| `OPS_SNAPSHOTS_ROOT` | `/app/data/psych_eval` | Directory for psych eval snapshot files. |

---

## Experiment / Probe System

| Variable | Default | Notes |
|----------|---------|-------|
| `EXPERIMENT_ARTIFACTS_DIR` | `backend/data/experiments` | Output directory for experiment runs. |
| `EXPERIMENT_DEFAULT_REPEATS` | `1` | Default repetitions per experiment probe. |
| `EXPERIMENT_DEFAULT_SEED` | `1337` | Default RNG seed. |

---

## Quick Setup Checklist

Minimum required for a working local stack:

```env
GOOGLE_API_KEY=your-gemini-api-key
POSTGRES_PASSWORD=choose-a-strong-password
INFLUXDB_INIT_PASSWORD=choose-a-strong-password
INFLUXDB_INIT_ADMIN_TOKEN=choose-a-long-random-token
```

For governance enforcement (production default):

```env
IIT_MODE=soft
RPD_MODE=soft
```

For share mode (giving someone else access):

```env
SHARE_MODE_ENABLED=true
SHARE_MODE_USERNAME=omega
SHARE_MODE_PASSWORD=choose-a-strong-password
OPS_TEST_CODE=change-this-too
```
