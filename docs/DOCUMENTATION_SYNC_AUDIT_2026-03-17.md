# OMEGA4 Documentation Sync Audit

Last updated: 2026-03-17

This audit records the Morpheus Mode documentation parity pass and cross-checks against implementation.

## 1. Canonical Document Roles

- `README.md`: operator workflow + high-level feature behavior (including hidden-mode boundaries).
- `docs/API_CONTRACT.md`: route/auth/SSE behavior for `backend/main.py`.
- `docs/MORPHEUS_MODE_DEV_GUIDE.md`: implementation-level Morpheus behavior, state machine, and test/runbook guidance.
- `docs/SYSTEM_DESIGN.md`: subsystem architecture, interfaces, test assets, and known limitations.
- `docs/LAYER_DATA_TOC.md`: operator-facing datum inventory and event surface map.
- `docs/ABOUT_FAQ_GLOSSARY.md`: tester-visible FAQ/glossary source of truth.
- `docs/TECHNICAL_CAPABILITY_MANIFEST.md`: capability-level claims.
- `docs/INVENTION_LEDGER.md`: falsifiable invention claims and boundaries.
- `docs/TECHNICAL_NORTH_STAR.md`: strategic baseline and active gaps.

## 2. Verification Checks Executed

- Morpheus route/event contract parity:
  - verified `POST /ghost/chat` accepts `mode` / `mode_meta` in request model.
  - verified wake interception path emits `morpheus_mode` (`phase="wake_hijack"`) then `done` with `morpheus_run_id`.
  - verified hidden terminal path emits `morpheus_mode`, token chunks, optional `morpheus_reward`, and `done` with `morpheus_step`.
- Branch semantics parity:
  - verified frontend differentiates click vs typed red/blue choices and maps typed red to deep mode (`morpheus_terminal_deep`).
  - verified blue branch preserves/loses only secret run state and does not delete persisted chat history in backend stores.
- Runtime containment parity:
  - verified hostile takeover effects are rendered as in-app overlays/windows and do not invoke destructive host/browser APIs.
- Test asset parity:
  - verified backend tests in `backend/test_main_morpheus_mode.py`.
  - verified frontend smoke path includes Morpheus wake -> red terminal -> reward checks in `frontend/scripts/frontend-smoke.js`.

## 3. Drift Remediation Completed

- Updated `CHANGELOG.md` with Morpheus mode additions/changes and documentation parity note.
- Updated `README.md` with Morpheus feature overview and smoke-test scope expansion.
- Updated `docs/API_CONTRACT.md` with Morpheus request/event contract details.
- Added `docs/MORPHEUS_MODE_DEV_GUIDE.md` as the canonical dev-facing implementation/runbook for Morpheus Mode.
- Updated `docs/SYSTEM_DESIGN.md` with Morpheus subsystem architecture, interface notes, tests, and limitations.
- Updated `docs/LAYER_DATA_TOC.md` with Morpheus datum layer and event snapshot section.
- Updated `docs/ABOUT_FAQ_GLOSSARY.md` with Morpheus FAQ + glossary additions.
- Updated research/capability docs (`TECHNICAL_CAPABILITY_MANIFEST`, `INVENTION_LEDGER`, `TECHNICAL_NORTH_STAR`) to include Morpheus runtime status and boundaries.

## 4. Ongoing Maintenance Rule

For each hidden-mode contract change:

1. Update `docs/API_CONTRACT.md` (`/ghost/chat` request/SSE semantics).
2. Update `docs/MORPHEUS_MODE_DEV_GUIDE.md` with state/branch/testing details.
3. Update `docs/SYSTEM_DESIGN.md` section 4 + 6 + 9/12 as applicable.
4. Update `docs/LAYER_DATA_TOC.md` if datum fields/events change.
5. Update `docs/ABOUT_FAQ_GLOSSARY.md` if tester-visible behavior changes.
6. Update `README.md` when operator workflow/smoke behavior changes.
7. Record the pass in a new dated `DOCUMENTATION_SYNC_AUDIT_*.md` artifact.
