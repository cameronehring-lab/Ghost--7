# Placeholder / Mock Audit (2026-03-08)

Scope: runtime backend + frontend user-facing flows.

## Fixed in this pass

| Area | File | What it did before | Real behavior now |
|---|---|---|---|
| Process telemetry | `backend/somatic.py:38` + `backend/somatic.py:218` + `backend/somatic.py:399` | Returned `processes: []` (always empty placeholder) | Returns real top process list (`name`, `cpu`, `mem`) from `psutil` |
| Weather fallback | `backend/ambient_sensors.py:97` + `backend/ambient_sensors.py:204` | Used simulated weather when OpenWeather key missing | Uses real Open‑Meteo no-key weather fallback; simulation only if providers unavailable |
| Push event payload | `backend/main.py:897` + `backend/main.py:927` + `backend/ghost_script.py:233` | Mixed payload shapes (plain strings), frontend expected JSON | Normalized structured JSON payloads (`text`, `timestamp`, optional metadata) end-to-end |
| Stale session summaries | `backend/mind_service.py:354` + `backend/mind_service.py:372` | Closed sessions with static summary text | Generates real summaries (LLM summarization + deterministic fallback) |
| Lucid dream CRP seed | `backend/main.py:1067` | Fell back to synthetic thoughts (`"Initial state"`, etc.) | Uses real monologue/message/identity context; skips CRP with explicit reason when insufficient |
| Consolidation logging | `backend/consciousness.py:1056` | Logged empty `{}` as `before_state` placeholder | Persists actual pre-consolidation identity snapshot and thought count |
| Static asset mount | `backend/main.py:1767` | Created dummy static dir when frontend missing | Fails fast with explicit runtime error |
| Chat stream rendering | `frontend/app.js:792` | Artificial typewriter delay simulation with random waits | Real-time token rendering from SSE stream |
| Coalescence empty-state copy | `frontend/app.js:1281` | Hardcoded `20` interactions in UI | Reads live `coalescence_threshold` from backend health |
| About modal accuracy | `frontend/index.html:437` + `frontend/index.html:441` | Outdated claims (“without human review”, fatigue-only coalescence trigger) | Updated copy to match actual governed behavior |

## Added tests

| Test | File | Coverage |
|---|---|---|
| Session summary fallback | `backend/test_session_summary_fallback.py` | Ensures deterministic fallback summaries are meaningful |
| Push payload normalization | `backend/test_push_payload_normalization.py` | Ensures text/JSON/bytes payloads normalize consistently |

## Runtime verification performed

- `python3 -m compileall -q backend`
- `node --check frontend/app.js`
- `docker exec omega-backend python -m unittest -q test_session_summary_fallback.py test_push_payload_normalization.py`
- Live sanity checks on `/health` and `/somatic` after backend restart

## Remaining intentional simulations (not removed)

| Area | File | Why still present |
|---|---|---|
| Embodiment action cost model | `backend/embodiment_sim.py` | Design-level abstraction for simulated stamina/strain layer; anchored to real telemetry but action cost remains modeled |
| Weather simulation fallback | `backend/ambient_sensors.py:215` | Last-resort fallback when both weather providers are unavailable |
