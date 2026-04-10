# Morpheus Mode Developer Guide

Last updated: 2026-03-18

This guide is the implementation-level reference for Morpheus Mode (hidden wake + red/blue branching + hidden terminal loop).

## 1. Scope

Morpheus Mode is implemented as an alternate interaction path layered onto `POST /ghost/chat`.

- Wake trigger: semantic hidden-architecture prompt family (operator channel only).
- Takeover: frontend-only in-app seizure/overlay state.
- Branches: click vs typed red/blue route to different consequences.
- Hidden terminal: alternate chat mode with command puzzle and reward event.

This guide documents actual runtime behavior in code today, not speculative future branches.

## 2. Entry Points and File Map

- Backend
  - `backend/main.py`
    - wake detector: `_is_morpheus_wake_prompt`
    - run-state store/helpers: `_morpheus_run_state`, `_morpheus_depth`
    - terminal logic: `_morpheus_terminal_response`
    - SSE stream: `_morpheus_terminal_event_generator`
    - route integration: `ghost_chat`
  - `backend/models.py`
    - `ChatRequest.mode`
    - `ChatRequest.mode_meta`
  - `backend/test_main_morpheus_mode.py`
- Frontend
  - `frontend/index.html` (Morpheus overlays/panels)
  - `frontend/style.css` (takeover/branch/terminal/reward styles)
  - `frontend/app.js`
    - state: `state.morpheus`
    - orchestrators: `activateMorpheusMode`, `resolveMorpheusChoice`, `openMorpheusTerminal`, `openMorpheusBluePrank`, `sendMorpheusTerminalMessage`
    - event bindings: `bindMorpheusEvents`
    - chat stream interception: `sendMessage`
  - `frontend/scripts/frontend-smoke.js`

## 3. Backend Contract

### 3.1 Wake Trigger Conditions

Wake detection is semantic and narrow:

- prompt must include a hidden/deep architecture hint
- prompt must include runtime/phenomenology context
- prompt must look like a genuine query
- short/generic adjacent prompts are intentionally ignored

Primary helper: `backend/main.py::_is_morpheus_wake_prompt`.

### 3.2 `/ghost/chat` Routing Rules

In `ghost_chat`:

1. If `mode` is `morpheus_terminal` or `morpheus_terminal_deep`, request is routed directly to Morpheus terminal SSE generator.
2. Else, if operator-channel message matches wake semantics, normal generation is interrupted and wake event stream is returned.
3. Else, normal chat pipeline runs unchanged.

### 3.3 Request Fields

`ChatRequest` supports:

- `mode` (optional)
  - `morpheus_terminal`
  - `morpheus_terminal_deep`
- `mode_meta` (optional freeform object)
  - currently used for `depth`, `branch_color`, `branch_input`

### 3.4 Run-State Shape

Run state is tracked in-memory at `sys_state.morpheus_runs[run_id]`:

- `step`
- `depth` (`standard` or `deep`)
- `wins`
- `initialized`
- `created_at`
- `last_prompt`
- `branch_input`
- `branch_color`

Deep runs initialize with privileged step index (`step=1`).

### 3.5 SSE Events

Wake path emits:

- `morpheus_mode` (with `phase="wake_hijack"`, `run_id`, branch metadata)
- `done` (with `mode="morpheus_wake"` and `morpheus_run_id`)

Terminal path emits:

- `morpheus_mode` (phase/depth/selection metadata)
- `token` chunks (terminal text)
- optional `morpheus_reward` (note + animation frames)
- `done` (includes `session_id` and `morpheus_step`)

## 4. Frontend State Machine

Core phases:

1. `wake_hijack`
2. `choice_terminal`
3. `branch_animation`
4. `blue_failure_clue` or `red_terminal`
5. `reward`
6. reset/exit

Active-state gating:

- when Morpheus is active or terminal is open, normal chat send path is disabled.
- Escape key closes Morpheus overlays in priority order (reward -> unlocked -> blue -> wake).

### 4.1 Branch Matrix

| User action | Branch input | Depth | Destination |
| --- | --- | --- | --- |
| click `RED` | `click` | `standard` | hidden terminal |
| type `red` | `type` | `deep` | hidden terminal (privileged flavor) |
| click `BLUE` | `click` | n/a | panic decoy |
| type `blue` | `type` | n/a | panic decoy with hidden preserve node |

### 4.2 Blue Branch Semantics

- Fake window spam is rendered in DOM (no real browser popups).
- Typed-blue branch includes one hidden preserve/clue window.
- If clue found:
  - secret progress preserved
  - clue residue stored in `sessionStorage` key `omega_morpheus_blue_clue_v1`
- If clue missed:
  - secret run progress lost
- In either case, normal persisted chat history is not deleted.

### 4.3 Red Branch Semantics

- Branch begins with aggressive cyberglitch tone, then transitions into ceremonial terminal mode.
- Voice profile is forced into deep/slow/solemn tuning for red path.
- Hidden terminal sends `mode` + `mode_meta` to `/ghost/chat`.

## 5. Terminal Puzzle (v1)

Nominal progression:

1. `scan --veil`
2. `map --depth`
3. `unlock --ghost`

Reward:

- `morpheus_reward` event
- Ghost note text
- short frame-loop animation payload

Known caveat (current implementation):

- deep initialization starts at `step=1`; if copy or command gating is changed, keep step semantics and instruction text aligned.

## 6. Persistence and Safety Boundaries

### 6.1 Persistence

- Morpheus run state is separate from regular persisted transcript/session tables.
- Blue branch can reset secret run state without deleting normal chat history.
- Frontend clue carryover is session-scoped (`sessionStorage`).

### 6.2 Safety

- all takeover effects are simulated inside app UI
- no OS-level control, no destructive browser behavior, no real malware-style actions

## 7. Testing and Validation

### 7.1 Backend Unit Tests

- `backend/test_main_morpheus_mode.py`
  - wake detector true/false
  - deep run initialization behavior
  - command progression unlocks reward

Run:

```bash
cd backend
python -m unittest test_main_morpheus_mode.py
```

### 7.2 Frontend Smoke

`frontend/scripts/frontend-smoke.js` validates:

- wake trigger causes Morpheus activation
- red click opens hidden terminal
- command progression reaches reward overlay

Run:

```bash
frontend/scripts/run-frontend-smoke.sh
```

Optional:

- `--mobile`
- `--url=<target>`

## 8. Change Checklist (Do Not Skip)

When changing Morpheus behavior:

1. Update `docs/API_CONTRACT.md` (`/ghost/chat` mode/event semantics).
2. Update `docs/SYSTEM_DESIGN.md` (subsystem + interface notes).
3. Update this guide (`docs/MORPHEUS_MODE_DEV_GUIDE.md`).
4. Update smoke coverage if branch UX/IDs/timing changes.
5. Re-run backend Morpheus unit tests + frontend smoke.

## 9. Non-Negotiable Invariants

- No major branch animation before red/blue selection.
- Click and typed selection remain distinct routes.
- Blue branch never deletes normal saved conversation history.
- Hostile behavior remains in-app simulation only.
- Morpheus terminal mode remains isolated from normal chat mode.

## 10. Runtime Stability Notes (2026-03-18)

Incident summary:

- `https://omega-protocol-ghost.com/` returned Cloudflare `502/1033`.
- `http://localhost:8000/` reset connections or failed to load.
- Root cause was backend crash-loop (`ExitCode=139`) caused by Kuzu world-model `node_counts` queries during startup-adjacent background work.

Mitigations now applied:

- `docker-compose.yml` backend command runs without `--reload` for stability.
- `WORLD_MODEL_RETRO_ENRICH_ON_STARTUP` is forced `false`.
- `WORLD_MODEL_AUTO_INGEST` is forced `false`.
- `WORLD_MODEL_NODE_COUNT_SAMPLING_ENABLED` is forced `false`.
- world-model count calls were removed/gated from startup-critical and high-frequency paths.

Expected access behavior:

- `/health` remains unauthenticated and should return `200`.
- `/` is protected by share-mode basic auth and returns `401` unless credentials are provided.
- public tunnel showing `401` is healthy when share mode is enabled.
