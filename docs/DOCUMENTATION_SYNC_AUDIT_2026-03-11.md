# OMEGA4 Documentation Sync Audit

Last updated: 2026-03-11

This audit records the current documentation baseline and the checks used to keep docs aligned with running code.

## 1. Canonical Document Roles

- `README.md`: operator/deployment workflows and runtime behavior notes.
- `docs/API_CONTRACT.md`: route/auth/SSE contract for `backend/main.py`.
- `docs/SYSTEM_DESIGN.md`: implementation detail and architecture/data-flow behavior.
- `docs/TECHNICAL_CAPABILITY_MANIFEST.md`: capability-level claims.
- `docs/TECHNICAL_NORTH_STAR.md`: strategic direction and active gaps.

## 2. Verification Checks Executed

- Ghost-contact contract parity:
  - Verified code/docs alignment for `POST /ghost/chat` `channel` semantics (`operator_ui` default, `ghost_contact` optional).
  - Verified `GET /ghost/contact/status` response fields against implementation in `backend/main.py`.
  - Verified push payload additions for contact channel (`channel`, `thread_key`, `person_key`, `direction`, `ephemeral`).
  - Verified contact-mode env flags against `backend/config.py` and `.env.example`:
    - `IMESSAGE_SENDER_ACCOUNT`
    - `GHOST_CONTACT_MODE_ENABLED`
    - `GHOST_CONTACT_PERSIST_ENABLED`
    - `GHOST_CONTACT_THREAD_TTL_SECONDS`
- Local Markdown link integrity:
  - Checked `README.md` and all `docs/*.md` local links.
  - Result: all local links resolved.
- Behavior claim spot-checks:
  - `TTS_PROVIDER=browser` -> `/ghost/speech` returns `400`.
  - `/ghost/self/architecture` returns the runtime autonomy/architecture contract and prompt grounding block.
  - `/ghost/autonomy/state` and `/ghost/autonomy/history` expose watchdog state/history.
  - share-mode auth middleware and exempt-path behavior.
  - same-turn Rolodex fetch reinjection + SSE events (`rolodex_data`, `tts_ready`, `voice_modulation`).
  - topology metadata (`rolodex_alignment`, `entity_expansion`) and place/thing/idea node expansion.
  - topology renderer continuity in `frontend/app.js`:
    - WebGL probe + multi-profile retries,
    - context-loss watchdog recovery path,
    - software-3D fallback path when WebGL init fails.
  - timeline monologue drill-down in `frontend/app.js`:
    - preview truncation for timeline scanability,
    - monologue `id` hydration against `/ghost/monologues`,
    - click/keyboard open path into full audit detail modal.
  - `/ghost/monologues` contract parity:
    - verified unified audit stream semantics (`THOUGHT`, `ACTION`, `EVOLUTION`, `PHENOM`) against `memory.get_unified_audit_log`.
  - internal-thought guardrails in `backend/ghost_script.py`:
    - proactive cooldown + dedupe overlap thresholds,
    - low-signal curiosity-query suppression,
    - sentence-aware search-result truncation,
    - real operator idle-time feed into initiation decisions,
    - monologue sentence-completion normalization,
    - autonomous thought-to-topology concept/association projection,
    - novelty-bootstrap promotion path for sparse-manifold coherence seeking.

## 3. Drift Remediation Completed

- Updated `README.md` with dedicated Ghost-contact mode operations:
  - sender isolation behavior,
  - ephemeral defaults and compaction policy,
  - status/observability endpoints and payload contract.
- Updated `docs/API_CONTRACT.md` to include:
  - `/ghost/contact/status`,
  - `/ghost/chat` channel contract,
  - contact push payload fields and routing constraints.
- Updated `docs/SYSTEM_DESIGN.md` to include:
  - Ghost-contact subsystem architecture,
  - non-Postgres ephemeral thread model,
  - configuration knobs and failure behavior.
- Updated `README.md`, `docs/API_CONTRACT.md`, and `docs/SYSTEM_DESIGN.md` with internal-thought quality controls and runtime tuning knobs.
- Updated docs for autonomous topology coherence-drive knobs and behavior (`shared_conceptual_manifold` + `idea_entity_associations` projection path).
- Updated `docs/TECHNICAL_CAPABILITY_MANIFEST.md` with dedicated-contact identity and ephemeral-thread capability claims.
- Updated docs for timeline preview-to-full-thought drill-down behavior and unified audit stream semantics.
- Updated docs for topology renderer continuity behavior (WebGL-first + software-3D fallback + watchdog recovery).

## 4. Ongoing Maintenance Rule

For each backend/frontend contract change:

1. Update `docs/API_CONTRACT.md` (routes/auth/SSE).
2. Update `docs/SYSTEM_DESIGN.md` sections 4-6 and 12 as applicable.
3. Update `README.md` when operator workflow/deployment behavior changes.
4. Update `docs/TECHNICAL_CAPABILITY_MANIFEST.md` when capability claims change.
5. Update `docs/TECHNICAL_NORTH_STAR.md` when priorities, gaps, or roadmap phases change.
6. Bump `Last updated` in each touched document.
