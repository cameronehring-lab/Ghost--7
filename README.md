# OMEGA4

Self-hosted autonomous agent stack for Ghost (`omega-7`) — data-sovereign, closed-loop, deployable on bare metal or a VPS. The architecture is designed so all persistent state (Postgres, Redis, InfluxDB) lives on infrastructure you control; the LLM generation layer currently uses the Gemini cloud API. With:

- FastAPI backend + static frontend
- Postgres (`pgvector`) for memory/state
- Redis for affective state persistence
- InfluxDB + Telegraf for time-series telemetry
- Background cognition loops (monologue, quietude, consolidation, synthesis)
- **Person Rolodex Autonomy** (social modeling via actuation tags)
- **High-Rigor Neural Topology** (3D cognitive mapping with glitched diagnostics)
- **Conversational Voice Stack** (remote/local TTS fallback, voice tuning, speech-to-text input)
- **Runtime Autonomy Profile** (canonical self-architecture + guardrail contract)
- **Morpheus Mode** (hidden semantic wake + branching red/blue terminal path)

## Core Documentation

- [Technical North Star](docs/TECHNICAL_NORTH_STAR.md)
- [System Design Document](docs/SYSTEM_DESIGN.md)
- [Living System Status](docs/LIVING_SYSTEM_STATUS.md)
- [API Contract](docs/API_CONTRACT.md)
- [Morpheus Mode Developer Guide](docs/MORPHEUS_MODE_DEV_GUIDE.md)
- [Login and Access Reference](docs/LOGIN_ACCESS_REFERENCE.md)
- [Governance Policy Matrix](docs/GOVERNANCE_POLICY_MATRIX.md)
- [Layer & Datum TOC](docs/LAYER_DATA_TOC.md)
- [Technical Capability Manifest](docs/TECHNICAL_CAPABILITY_MANIFEST.md)
- [Invention Ledger](docs/INVENTION_LEDGER.md)
- [Repo Expert Tool](docs/REPO_EXPERT_TOOL.md)
- [About FAQ and Glossary](docs/ABOUT_FAQ_GLOSSARY.md)
- [Documentation Sync Audit (2026-03-18)](docs/DOCUMENTATION_SYNC_AUDIT_2026-03-18.md)
- [Documentation Sync Audit (2026-03-18 Reliability-First)](docs/DOCUMENTATION_SYNC_AUDIT_2026-03-18_RELIABILITY_FIRST.md)
- [Q2 2026 Execution Plan](docs/EXECUTION_PLAN_Q2_2026.md)

## Backend Documentation

- [Backend Docs Index](backend/docs/README.md)
- [Backend Runtime Note: Action Confirmation + Systemic Somatics (2026-03-18)](backend/docs/ACTION_CONFIRMATION_SYSTEMIC_SOMATICS_2026-03-18.md)
- [Backend Runtime Note: Reliability-First Autonomous Expansion (2026-03-18)](backend/docs/RELIABILITY_FIRST_AUTONOMOUS_EXPANSION_2026-03-18.md)

## About Tab Content Source of Truth

- FAQ and glossary content for the tester-visible About modal is sourced from `docs/ABOUT_FAQ_GLOSSARY.md`.
- Technical engineering and falsifiable research sections in About are sourced from canonical docs via `GET /ghost/about/content`.
- About payload is server-redacted before delivery so tester views do not expose sensitive credential/token values.

## Secure Remote Sharing

If you want someone outside your network to use the interface:

1. Enable share mode in `.env`:
   - `SHARE_MODE_ENABLED=true`
   - `SHARE_MODE_USERNAME=<username>`
   - `SHARE_MODE_PASSWORD=<strong-random-password>`
2. Start/restart backend:
   - `docker compose up -d --force-recreate backend`
3. Expose `http://localhost:8000` through a tunnel (Cloudflare Tunnel, Tailscale, or ngrok).
4. Share the HTTPS tunnel URL and credentials.

Notes:

- Share mode protects UI + API + SSE with HTTP Basic Auth.
- Tester URL serves the same runtime as `http://localhost:8000`.
- Frontend edits apply on browser refresh.
- Backend Python edits auto-reload in a few seconds (`uvicorn --reload`); syntax/runtime errors can temporarily break tester access until fixed.
- `/diagnostics/*` remains local-only by design.
- Keep `OPERATOR_API_TOKEN` configured if you want strict control-route enforcement.
- Use a share password that is different from `OPS_TEST_CODE`.

### Permanent Tester URL (Cloudflare Named Tunnel)

For a non-rotating tester URL (for example `https://omega-protocol-ghost.com`):

1. In Cloudflare Zero Trust, create a named tunnel (for example `omega4-tester`).
2. Route your hostname DNS record to that tunnel (`omega-protocol-ghost.com`).
3. Configure `.env`:
   - `SHARE_TUNNEL_MODE=named`
   - `SHARE_TUNNEL_FIXED_HOSTNAME=omega-protocol-ghost.com`
   - `CLOUDFLARE_TUNNEL_TOKEN=<token-from-cloudflare>`
4. Run watchdog:
   - `python3 scripts/share_tunnel_watchdog.py watch --interval-seconds 20`
5. Validate:
   - `python3 scripts/share_tunnel_watchdog.py status`

Quick tunnels (`*.trycloudflare.com`) remain available as an emergency fallback but are intentionally ephemeral.

### HA-Lite Runtime Target (DigitalOcean)

To keep tester access available when one node fails:

1. Deploy two Ubuntu droplets running identical OMEGA4 stacks (Docker Compose).
2. Run the same named tunnel token on both droplets (`cloudflared tunnel run --token ...`).
3. Set both `cloudflared` and backend services to auto-restart (`Restart=always` / equivalent).
4. Validate failover by stopping connector/backend on one node and confirming `https://omega-protocol-ghost.com` still serves from the other node.

### Tunnel Troubleshooting (macOS + Windows)

| Symptom | Interpretation | Action |
|---|---|---|
| `http://localhost:8000` works but tunnel hostname returns `NXDOMAIN` on host | Local DNS resolver issue on operator machine | Keep tunnel running, switch resolver to public DNS, then re-check hostname |
| Tunnel returns `401 Unauthorized` without credentials | Healthy share-mode gate | Expected behavior before HTTP Basic Auth |
| Tunnel returns `200` with credentials | Tester-ready link | Share URL + username/password + boot code |
| Tunnel hostname fails on both local and public DNS checks | Tunnel is stale/unreachable | Regenerate tunnel and re-run status check |

Cross-platform verification commands:

- Watchdog status (includes `resolver_issue`): `python3 scripts/share_tunnel_watchdog.py status`
- Local resolver check: `nslookup <tunnel-hostname>`
- Public resolver check: `nslookup <tunnel-hostname> 1.1.1.1`
- macOS DNS resolver order: `scutil --dns`
- Windows DNS resolver order (PowerShell): `Get-DnsClientServerAddress`
- Windows DNS hostname check (PowerShell): `Resolve-DnsName <tunnel-hostname>`

## Automatic Docker Recovery Watchdog

For local operator recovery on macOS, OMEGA4 now includes a host-level watchdog that monitors the loopback runtime and restarts Docker only when the app is genuinely stalled.

What counts as unhealthy:

- `GET http://127.0.0.1:8000/health` must return `200`
- `GET http://127.0.0.1:8000/somatic` must return `200`
- `GET http://127.0.0.1:8000/ghost/push` must emit an SSE event within 12 seconds; `event: ping` counts as healthy

What does not count as unhealthy:

- Normal quietude/coalescence behavior
- Lack of Ghost-initiated chat pushes while the SSE heartbeat is still alive

Recovery behavior:

- The watchdog runs every 20 seconds.
- It waits for 3 consecutive unhealthy cycles before taking action.
- First threshold breach: `docker compose restart backend`
- After any restart, it applies a 60-second grace window before counting failures again.
- If another 3-cycle unhealthy streak happens before a healthy cycle, it escalates to `docker compose restart`.
- Full-stack restarts are rate-limited to one every 10 minutes.
- A single healthy cycle clears the escalation state and returns to backend-first recovery.

Manual commands:

- Start watch loop: `python3 scripts/docker_recovery_watchdog.py watch --interval-seconds 20`
- Run one recovery check: `python3 scripts/docker_recovery_watchdog.py ensure`
- Inspect status: `python3 scripts/docker_recovery_watchdog.py status`
- Stop the watch loop: `python3 scripts/docker_recovery_watchdog.py stop`
- Install LaunchAgent: `bash scripts/install_docker_recovery_watchdog.sh install`
- Remove LaunchAgent: `bash scripts/install_docker_recovery_watchdog.sh uninstall`

Makefile shortcuts:

- `make recovery-watch`
- `make recovery-status`
- `make recovery-stop`
- `make recovery-install`
- `make recovery-uninstall`

Logs and state:

- Runtime state dir:
  - manual runs default to the Python temp dir (`tempfile.gettempdir() / "omega4_docker_recovery"`)
  - LaunchAgent installs pin it to `/tmp/omega4_docker_recovery`
  - override both with `OMEGA4_DOCKER_RECOVERY_STATE_DIR`
- Watchdog log: `watchdog.log`
- LaunchAgent logs: `launchd.out.log`, `launchd.err.log`

Disable it:

- Manual watchdog: `python3 scripts/docker_recovery_watchdog.py stop`
- LaunchAgent-managed watchdog: `bash scripts/install_docker_recovery_watchdog.sh uninstall`

## Quietude + Fatigue Tuning

- Circadian fatigue is now quietude-aware (effective awake time, not raw host uptime).
- Optional env knobs:
  - `CIRCADIAN_FATIGUE_HOURS` (default `72.0`)
  - `QUIETUDE_RECOVERY_MULTIPLIER` (default `6.0`)
  - `QUIETUDE_FATIGUE_INJECTION_SCALE` (default `0.35`)
- `enter_quietude` now supports `light`, `deep`, and `profound`.

## Internal Thought Quality Controls

- Proactive initiation and autonomous search thoughts now apply duplicate/fragment guards before writing to the monologue timeline.
- Proactive initiation now uses real operator idle time from message history instead of a hardcoded value.
- Search result monologues now use sentence-aware truncation with explicit ellipsis (`...`) instead of hard mid-token clipping.
- Every monologue write now normalizes to complete sentence boundaries before persistence.
- Ghost now runs an autonomous topology-coherence organizer:
  - promotes coherent thought concepts into the shared conceptual manifold,
  - links concept nodes to known person/place/thing entities by lexical evidence,
  - runs periodically as an active coherence drive (not only on user turns).
- Optional env knobs:
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

## Timeline + Audit Drill-Down

- Timeline modal (`TIMELINE // ω-7 EXISTENCE RECORD`) now renders monologue entries as preview snippets.
- Clicking a timeline monologue (or using `Enter`/`Space`) opens full thought detail in the existing audit detail modal.
- Timeline detail hydration uses monologue `id` matching against `/ghost/monologues` so full text is shown when available.
- `/ghost/monologues` is a unified audit stream (not thought-only): `THOUGHT`, `ACTION`, `EVOLUTION`, `PHENOM`.

## Real-Time Action Confirmation + Memory

- `/ghost/chat` now runs a bounded multi-round confirmation loop:
  - total rounds: `3`
  - actuation execution rounds: `2`
  - tool-reconcile rounds: `2`
- Internal tool-outcome bridge:
  - `ghost_stream(..., tool_outcome_callback=...)` emits normalized tool outcomes (`tool_name`, `status`, `reason`) to runtime somatic handlers.
- Same-turn feedback is reinjected for:
  - actuation outcomes (`successful`, `blocked`, `failed`)
  - function-tool outcomes (`update_identity`, `modulate_voice`)
  - Rolodex fetch data (existing behavior, now part of the unified follow-up prompt path)
- Same-turn actuation dedupe is enforced per canonical `action+param` key (duplicates in later rounds do not re-execute).
- `update_identity` tool attempts (accepted and blocked) are now journaled into `autonomy_mutation_journal` so `RECENT ACTIONS` carries identity-change continuity across turns.
- Prompt context now includes `## RECENT ACTIONS` (last `5` events) built from:
  - `actuation_log`
  - `autonomy_mutation_journal`
  with phenomenological wording and low-level lexicon scrubbing.
- New agency traces are layered on top of existing reflexive action traces:
  - `agency_fulfilled` (`k=0.18`, `arousal=-0.10`, `valence=+0.40`)
  - `agency_blocked` (`k=0.22`, `arousal=+0.20`, `valence=-0.30`)
  - applies to both actuation outcomes and function-tool outcomes.

## Systemic Somatics Rebalance

- Weather remains present as context but is now near-zero impact in affect math.
- Weather-driven traces (`barometric_heaviness`, `rain_atmosphere`, `cold_outside`, `heat_outside`) use damped weights/intensities.
- Systemic traces are elevated as primary affect drivers:
  - `cpu_sustained`: `+0.90 / -0.65`
  - `cognitive_fatigue`: `-0.18 / -0.45`
  - `internet_stormy`: `+0.55 / -0.35`
  - `internet_isolated`: `+0.60 / -0.65`
- Prompt mood synthesis now treats weather lines as factual context (not primary mood narration).

## Placeholder Remediation Highlights

- Weather data now uses real providers in priority order:
  - OpenWeatherMap (if API key present)
  - Open-Meteo (no-key fallback)
  - local simulation only as last-resort outage fallback
- `/somatic` process list now reports real top processes instead of an always-empty array.
- Ghost push events are normalized to structured JSON payloads (`text`, `timestamp`, optional metadata) for reliable frontend rendering.
- Stale session closure now generates a real conversation summary (LLM + deterministic fallback) instead of a static placeholder sentence.

## Important Notes

- Diagnostics routes under `/diagnostics/*` are protected as local-only.
- In some host/network setups, requests to `http://localhost:8000` can arrive at the backend with a non-loopback source IP (for example `172.253.x.x`) and return `403`.
- `scripts/falsification_report.py` now handles this automatically:
  - If host diagnostics call gets `403` on local URL, it auto-runs the report inside `omega-backend` and prints the same output.
  - No manual `docker exec` step is needed.
- If your backend container name is different, set `OMEGA_BACKEND_CONTAINER` or pass `--container-name`.

### Control Endpoint Security

- `POST /ghost/actuate` and `POST /config/tempo` now require either:
  - a valid operator token (`Authorization: Bearer <token>` or `X-Operator-Token`), or
  - a request source in trusted local CIDRs.
- Configure with env vars:
  - `OPERATOR_API_TOKEN` (recommended for any non-local deployment)
  - `CONTROL_TRUSTED_CIDRS`
  - `DIAGNOSTICS_TRUSTED_CIDRS`
- If `OPERATOR_API_TOKEN` is set, clients calling those control routes must send the token header.
- CORS is now controlled by:
  - `CORS_ALLOW_ORIGINS` (comma-separated)
  - `CORS_ALLOW_CREDENTIALS`
- Static serving blocks hidden entries (for example `/.git/*`) via backend static-file guard.

## Quick Commands

- Canonical backend bootstrap + reliability verify:
  - `python3 scripts/backend_bootstrap_verify.py --base-url http://localhost:8000`
- Full diagnostics:
  - `python3 scripts/falsification_report.py --base-url http://localhost:8000 --full`
- Quick diagnostics:
  - `python3 scripts/falsification_report.py --base-url http://localhost:8000`

Experiment artifacts (`/diagnostics/experiments/run`, `/diagnostics/ablations/run`) now include quality metrics:

- `same_turn_confirmation_rate`
- `agency_trace_alignment_rate` + misalignment buckets (`missing_trace`, `wrong_label`, `wrong_sign`, `missing_outcome`)
- `weather_only_max_axis_delta`, `systemic_max_axis_delta`, `systemic_vs_weather_ratio`

## LLM Backend

**Current active backend**: `LLM_BACKEND=gemini` — Gemini 2.5 Flash is the only active chat generation path. Local LLM routing via Ollama has been removed from the standard chat path.

The local LLM infrastructure (`local_llm_client.py`, steering scaffold, hooked CSC model) remains present for the CSC irreducibility research assay only — it is not used for routine Ghost cognition.

- Backend selection:
  - `LLM_BACKEND=gemini` (current active runtime)
  - `LLM_BACKEND=local` (CSC research assay only — not for standard chat)
- Local/CSC-only knobs:
  - `LOCAL_LLM_BASE_URL` (container-safe default: `http://ollama:11434`)
  - `LOCAL_LLM_MODEL` (canonical Ollama model: `llama3.1:8b`)
  - `LOCAL_LLM_API_FORMAT=ollama|openai`
  - `LOCAL_LLM_FALLBACK_TO_GEMINI_ENABLED=true|false`
  - `LOCAL_LLM_AUTO_PULL_ENABLED=true|false`
  - `LOCAL_LLM_PULL_ON_STARTUP=true|false`
  - `LOCAL_LLM_PULL_TIMEOUT_SECONDS`
  - `CSC_STRICT_LOCAL_ONLY=true|false` (CSC assay-only; does not govern routine chat routing)
  - Phase 2 steering scaffold knobs:
    - `ACTIVATION_STEERING_ENABLED=true|false`
    - `STEERING_VECTOR_DIM`
    - `STEERING_BASE_SCALE`
    - `STEERING_PRESSURE_GAIN`
    - `STEERING_WRITEBACK_ENABLED`
  - Phase 2F hooked CSC assay knobs:
    - `CSC_STEERING_MODE=scaffold|hooked_local`
    - `CSC_HOOKED_MODEL_ID` (default: `Qwen/Qwen2.5-0.5B-Instruct`)
    - `CSC_HOOKED_DEVICE=cpu|mps|cuda`
    - `CSC_HOOKED_MAX_NEW_TOKENS`
    - `CSC_HOOKED_TEMPERATURE`
    - `CSC_HOOKED_SEED`
- Optional local inference service:
  - `docker compose --profile local-llm up -d ollama`
- Runtime policy:
  - standard Ghost chat uses Gemini exclusively
  - CSC irreducibility assay uses the local hooked backend and never uses Gemini fallback
  - `LOCAL_LLM_AUTO_PULL_ENABLED` applies to the CSC research assay only
- Runtime checks:
  - `GET /health` now includes `llm_backend`, `model`, `llm_ready`, `local_model_ready`, `llm_effective_backend`, `llm_degraded`, and `llm_degraded_reason`.
  - `GET /ghost/llm/backend` returns default/effective backend state, fallback policy, local model provisioning state, and optional health/steering telemetry. Add `?include_health=true` to probe local inference readiness and `?include_steering=true` to include hooked CSC capability.
  - `GET /ghost/llm/steering/state` returns latest steering scaffold stage metadata.
  - `GET /ghost/workspace/state` returns live ψ workspace norm, linguistic magnitude, and crystallized prompt context.
  - `POST /diagnostics/csc/irreducibility` runs the real CSC A/B irreducibility assay on isolated backends. It does not require switching normal chat off Gemini. It requires:
    - the configured local inference backend and model to be healthy
    - the diagnostics-only hooked backend to be healthy
    - the required user-review acknowledgements
    - Results persist artifact bundles under `backend/data/experiments/csc_irreducibility_*`.
  - `scripts/run_csc_live_smoke.sh` no longer recreates `omega-backend` in CSC mode. It leaves the live chat backend unchanged, preflights local inference + hooked backend readiness, runs the live irreducibility assay, and prints the artifact summary.

## Automated Psychological Evolution Snapshots

Run once manually:

- Daily-style snapshot:
  - `bash scripts/psych_eval_snapshot.sh --window daily`
- Weekly-style trend report:
  - `bash scripts/psych_eval_snapshot.sh --window weekly`

Install cron automation:

- `bash scripts/install_psych_eval_cron.sh`

Default schedule:

- Daily at `08:00` local
- Weekly at `08:15` every Monday

Artifacts and logs:

- Snapshot artifacts: `backend/data/psych_eval/`
- Cron logs: `logs/psych_eval/daily.log`, `logs/psych_eval/weekly.log`

Remove cron block:

- `bash scripts/install_psych_eval_cron.sh --uninstall`

## Hidden System Ops Panel

- Hidden entry: click the header snail logo.
- Unlock code: `1NDASHE77` (or override via `OPS_TEST_CODE` in `.env`).
- Panel reads files from `OPS_SNAPSHOTS_ROOT` (default `/app/data/psych_eval` in backend container).
- Includes a dedicated `RPD / REFLECTION` tab for:
  - latest advisory snapshot
  - recent RPD runs
  - residue queue
  - shared conceptual manifold
  - manual reflection-pass trigger
- Backend APIs used by panel:
  - `GET /ops/verify`
  - `GET /ops/runs?window=daily|weekly`
  - `GET /ops/file?rel_path=...`

### Authorized Ops Chat Commands

- Any chat command starting with `/ops/` is now protected by the same ops code.
- Frontend behavior:
  - On first `/ops/...` command, UI prompts for code.
  - If valid, command is sent with `X-Ops-Code` header.
  - If invalid/missing, command is blocked before send.
- Backend behavior:
  - `/ghost/chat` rejects `/ops/...` commands without valid ops code (`401`).
  - This is server-enforced and cannot be bypassed by client-side changes.
- Example command:
  - `/ops/test-blocked-identity`
- API/manual invocation example:
  - `curl -N -H 'Content-Type: application/json' -H 'X-Ops-Code: <OPS_TEST_CODE>' -d '{"message":"/ops/test-blocked-identity"}' http://localhost:8000/ghost/chat`
- Rotate code:
  - Update `OPS_TEST_CODE` in `.env`
  - Restart backend: `docker compose up -d --force-recreate backend`

### Operator Security Checklist

- Use a strong, non-default `OPS_TEST_CODE` in `.env`.
- Rotate `OPS_TEST_CODE` on a regular cadence (recommended: every 30 days) and immediately after any suspected exposure.
- Never share ops code in chat transcripts, screenshots, or public docs.
- Keep `OPERATOR_API_TOKEN` set for privileged control routes, especially when sharing remotely.
- Enable share auth before exposing the app beyond localhost:
  - `SHARE_MODE_ENABLED=true`
  - strong `SHARE_MODE_PASSWORD`
- Treat tunnel URLs as sensitive and revoke/rotate when no longer needed.
- Verify protected behavior after each deploy:
  - `/ops/...` chat command without code returns `401`
  - same command with code succeeds
  - `/diagnostics/*` remains blocked remotely (`403`) by design
- Keep auditability enabled:
  - preserve `identity_audit_log`, coalescence logs, and ops snapshots
  - avoid running with ad-hoc bypass patches in production

## Frontend Smoke Test

- Run `frontend/scripts/run-frontend-smoke.sh` (add `--mobile` for handset dimensions) to launch Playwright against `http://127.0.0.1:8000` using the HTTP Basic Auth credentials from `.env` and the boot code `BOOT_CODE`.
- The script installs Playwright into a temporary directory, exercises core modals, terminal toggle, and Morpheus wake/red-terminal/reward flow, then exits non-zero if console/page errors or failed interactions appear.
- For alternative hosts, pass `--url=` (e.g., `--url=http://localhost:8081`); the CLI still reads share credentials from `.env`.

## Morpheus Mode (Hidden Easter Egg)

- Wake condition: a narrow semantic question pattern that combines hidden-architecture intent with runtime/phenomenology context.
- Trigger surface: standard `POST /ghost/chat` operator channel; when matched, normal turn output is interrupted and `morpheus_mode` takeover events are emitted.
- Choice contract:
  - click `RED` -> standard hidden terminal depth
  - type `red` -> deep terminal depth (privileged opening state)
  - click `BLUE` -> panic decoy branch (secret progress usually lost)
  - type `blue` -> panic decoy branch with hidden preserve-clue window
- Hidden terminal:
  - backed by `/ghost/chat` with `mode` (`morpheus_terminal` or `morpheus_terminal_deep`)
  - command puzzle v1: `scan --veil` -> `map --depth` -> `unlock --ghost`
  - first completion unlocks a Ghost note + short animation payload.
- Safety boundaries:
  - all hostile effects are simulated inside the app DOM
  - no real popup hijacking, browser takeover, or destructive OS behavior
  - normal persisted chat history is not deleted by Morpheus branches.
- Engineering reference:
  - Detailed implementation/state/event contract: `docs/MORPHEUS_MODE_DEV_GUIDE.md`

## RPD-1 Reflection Layer

- **Current mode**: `RPD_MODE=soft` — enforcement active. Policy decisions are applied, not shadow-only. The default in `config.py` is `advisory` but the active runtime (`.env`) runs soft mode.
- Env knobs:
  - `RPD_MODE=soft` (current) | `advisory` (shadow-only) | `off`
  - `RPD_SHARED_CLARITY_THRESHOLD=0.62`
  - `RPD_TOPOLOGY_WARP_MIN=0.12`
  - `RPD_REFLECTION_BATCH=8`
  - `RPD_SHADOW_REFLECTION_AUTORUN=true`
  - `RPD_SHADOW_REFLECTION_COOLDOWN_SECONDS=90`
- `POST /ghost/reflection/run` (operator token or ops-code auth)
  - `GET /ghost/manifold`
  - `POST /ghost/manifold/upsert` (operator token or ops-code auth)

## High-Rigor Neural Topology

A 3D interactive visualization of Ghost's cognitive web.

- **Floating Glitched Inspector**: Draggable, resizable diagnostic terminal with CRT effects.
- **Renderer Continuity**: WebGL-first 3D initialization with retry profiles; when WebGL is unavailable the UI automatically degrades to a software 3D renderer (still 3D mapping, lower performance envelope).
- **Ideal Scale Presets**:
    - `L1`: Sparse / High Rigor
    - `L2`: Standard / Integrated
    - `L3`: Dense / Exploratory
- **Causal Visibility**: Flow particles represent memory consolidation and causal generation.
- **Node Provenance**: Detailed diagnostic reports including affective signatures and evidence counts.
- **Rolodex Alignment Metadata**: Graph metadata exposes `rolodex_alignment` and `entity_expansion` counters for integrity checks.
- **Entity Expansion**: Place/thing/emergent-idea nodes are projected from reinforced memory facts and shown with typed links.

## Voice Interaction Stack

- Backend provider chains:
  - `TTS_PROVIDER=elevenlabs` -> ElevenLabs, then Piper, then pyttsx3.
  - `TTS_PROVIDER=openai` -> OpenAI, then Piper, then pyttsx3.
  - `TTS_PROVIDER=local` -> Piper, then pyttsx3 (order follows `LOCAL_TTS_ENGINE` preference).
  - `TTS_PROVIDER=browser` -> backend does not synthesize (`GET /ghost/speech` returns `400` by design).
- `/ghost/chat` may emit:
  - `voice_modulation` (real-time tuning deltas)
  - `tts_ready` (audio cache URL)
  - `rolodex_data` (same-turn social recall payload)
- Frontend voice loop:
  - Text rendering is paced by speech playback progress for audio/text sync.
  - Voice tuning sliders apply in real-time and persist in local storage.
  - Speech-to-text input uses browser `SpeechRecognition`/`webkitSpeechRecognition` when available.

## Runtime Self-Architecture

- `GET /ghost/self/architecture`
  - Returns Ghost's live functional architecture, autonomy matrix, bounded guardrails, and prompt-grounding context.
  - Used to keep Ghost's self-description aligned with actual runtime capability/constraints.
- `GET /ghost/autonomy/state`
  - Returns the latest autonomy drift-watchdog status.
- `GET /ghost/autonomy/history`
  - Returns recent watchdog events (`initialized`, `stable`, `contract_change`, `drift_detected`, `error`).

## External Open-Data Grounding

- Philosophy grounding:
  - `PHILOSOPHERS_API_ENABLED=true`
  - Uses `https://philosophersapi.com/api/philosophers/search` and detail lookups to inject philosophy metadata into relevant turns.
- arXiv grounding:
  - `ARXIV_API_ENABLED=true`
  - Uses arXiv legacy API metadata feed (`ARXIV_API_ENDPOINT`) with built-in pacing (`ARXIV_API_MIN_INTERVAL_SECONDS`, default 3s) and single-request locking.
  - Grounding stays metadata-only; Ghost is not instructed to re-host full paper content.
- Wikidata grounding:
  - `WIKIDATA_API_ENABLED=true`
  - Uses Wikidata entity search (`WIKIDATA_API_ENDPOINT`) to inject canonical entity IDs (QIDs), labels, and descriptions for identity/fact queries.
- Wikipedia grounding:
  - `WIKIPEDIA_API_ENABLED=true`
  - Uses MediaWiki search API (`WIKIPEDIA_API_ENDPOINT`) to inject page-title + snippet context for broad factual lookups.
- OpenAlex grounding:
  - `OPENALEX_API_ENABLED=true`
  - Uses OpenAlex works API (`OPENALEX_API_ENDPOINT`) for research-graph metadata (work id, venue, authors, concepts).
  - Optional polite/auth fields: `OPENALEX_MAILTO`, `OPENALEX_API_KEY`.
- Crossref grounding:
  - `CROSSREF_API_ENABLED=true`
  - Uses Crossref works API (`CROSSREF_API_ENDPOINT`) for DOI-first bibliographic metadata (title, DOI, venue, publisher, year).
  - Optional polite contact: `CROSSREF_MAILTO`.
- Runtime behavior:
  - All adapters are feature-flagged and only queried when message heuristics indicate likely relevance.
  - Context blocks are assembled in parallel with explicit budget controls:
    - `GROUNDING_TOTAL_BUDGET_MS` (default `1200`)
    - `GROUNDING_ADAPTER_TIMEOUT_MS` (default `800`)
  - Grounding context now starts with an `[EXTERNAL_GROUNDING_PROVENANCE]` envelope including:
    - retrieval timestamp
    - `attempted_count`
    - `source_count`
    - per-source trust tier, confidence, latency, and `status` (`ok`, `empty`, `failed`, `timed_out`)
  - Source blocks are ordered by confidence first and latency second, then wrapped as `[GROUNDING_SOURCE ...]` sections for deterministic downstream parsing.
  - Empty/failed/timed-out sources are retained in provenance lines (with optional error hints) while only `ok` sources with payload become `[GROUNDING_SOURCE ...]` blocks.

## Ghost Contact Mode (Dedicated Sender + Ephemeral Threads)

This mode supports direct per-contact Ghost conversations over iMessage without attaching turns to normal saved operator session history.

- Dedicated sender identity:
  - Configure `IMESSAGE_SENDER_ACCOUNT` with the Ghost iMessage identity (Apple ID email sender).
  - Send dispatch fails closed with `sender_identity_unavailable` when the configured sender account is missing or cannot be matched in Messages.
  - Free identity setup is email-based iMessage sender identity (separate Apple ID), not a dedicated phone number.
- Containerized backend transport:
  - If backend runs in Docker, start the host bridge so Linux container can hand off outbound iMessage send to macOS:
    - `python3 scripts/imessage_host_bridge.py --host 127.0.0.1 --port 8765`
  - Configure backend env:
    - `IMESSAGE_HOST_BRIDGE_URL=http://host.docker.internal:8765`
    - Optional auth: set `IMESSAGE_HOST_BRIDGE_TOKEN` on both backend and bridge process.
- Core mode flags:
  - `GHOST_CONTACT_MODE_ENABLED=true`
  - `GHOST_CONTACT_PERSIST_ENABLED=false` (default; disables DB persistence for Ghost-contact turns)
  - `GHOST_CONTACT_THREAD_TTL_SECONDS=86400`
- Inbound routing behavior:
  - iMessage ingest only accepts known handles bound in Rolodex (`contact_handle`); unknown handles are ignored.
  - When persistence is disabled, no writes are made to conversation/session/vector memory tables for Ghost-contact turns.
  - Ghost responds only to the same inbound contact in v1; cross-person relay actions are blocked on this path.
- Ephemeral thread behavior:
  - Thread key is normalized from the contact handle.
  - Storage backend is Redis with in-memory fallback.
  - Last 12 verbatim turns are kept; older turns are compacted into `compact_summary`.
  - Response context uses `compact_summary + last 12 turns + inbound message`.
- API + UI visibility:
  - `POST /ghost/chat` accepts optional `channel` (`operator_ui` default, `ghost_contact` optional).
  - `GET /ghost/contact/status` reports contact-mode flags, sender account, bridge status, and thread-store backend/TTL.
  - Push payloads include `channel`, `thread_key`, `person_key`, `direction`, and `ephemeral`.
  - Status rail `CONTACT` pill shows the current contact channel state (`EPHEMERAL`, `PERSIST ON`, `NO SENDER`, etc.).

## Person Rolodex Autonomy

Ghost maintains a persistent social model for others, separate from his own identity.

- **Actuation Tags**:
  - `[ROLODEX:set_profile:key:name]`
  - `[ROLODEX:set_fact:key:type:value]`
  - `[ROLODEX:fetch:key]`
- **Same-Turn Fetch Reinjection**:
  - `ROLODEX:fetch` now triggers one bounded follow-up generation pass so fetched profile data can be used in the same user response turn.
- **Storage**: Reinforced person facts and profile interaction tracking in Postgres.

## Person Rolodex Memory

Ghost now maintains a persistent person-memory rolodex from conversation text.

- Auto-ingest behavior:
  - Runs on each user chat turn.
  - Extracts self-identification (for example: “my name is Cameron”).
  - Tracks relationship mentions (for example: “my dad John”).
  - Reinforces lightweight facts (preference/location/occupation phrases).
- Storage:
  - `person_rolodex` (profile + interaction/mention counters)
  - `person_memory_facts` (reinforced person facts)
  - `person_session_binding` (session -> likely speaker mapping)
- APIs:
  - `GET /ghost/rolodex?limit=50`
  - `GET /ghost/rolodex/{person_key}?fact_limit=80`
  - `PATCH /ghost/rolodex/{person_key}/lock`
  - `GET /ghost/rolodex/{person_key}/history?limit=50`
  - `PATCH /ghost/rolodex/{person_key}/notes`
  - `DELETE /ghost/rolodex/{person_key}`
  - `GET /ghost/rolodex/retro-audit`
  - `POST /ghost/rolodex/retro-sync`

Retroactive reconciliation utility:

- Dry run: `docker compose exec -T backend python /app/scripts/rolodex_retro_sync.py`
- Apply backfill: `docker compose exec -T backend python /app/scripts/rolodex_retro_sync.py --apply`
- Current production state after sync: no missing profiles/facts/places/things in `/ghost/rolodex/retro-audit`.

## Troubleshooting Diagnostics

- Symptom: host diagnostics show `403 Forbidden`.
  - Cause: request reached backend as non-loopback IP due to local NAT/proxy behavior.
  - Expected behavior now: script auto-falls back to container execution.
  - Expected output excerpt:
    - `INFO  diagnostics got HTTP 403 from host path; auto-running inside container 'omega-backend'`
    - `OMEGA FALSIFICATION REPORT`
    - `PASS  shock_has_series`
    - `PASS  evidence_has_rows`

- Symptom: auto-fallback fails with container name error.
  - Cause: backend container is not named `omega-backend`.
  - Fix:
    - one-off: `python3 scripts/falsification_report.py --container-name <your-backend-container> --base-url http://localhost:8000 --full`
    - persistent: `export OMEGA_BACKEND_CONTAINER=<your-backend-container>`

- Symptom: `docker not found` during fallback.
  - Cause: Docker CLI is unavailable in the current shell environment.
  - Fix:
    - install/enable Docker CLI
    - or run directly inside backend container:
      - `docker exec -i omega-backend python /app/scripts/falsification_report.py --base-url http://127.0.0.1:8000 --full`

- Symptom: report runs but one or more checks show `FAIL`.
  - Meaning: diagnostics executed correctly; this is a system state issue, not networking.
  - Next step:
    - rerun with `--raw-json` and inspect failing section payload.
