# OMEGA4 Workspace Setup (Codex/Desktop)

This folder is currently the active Codex workspace root:

- `/Users/cehring/OMEGA4/frontend`

To edit the full OMEGA4 project (backend + frontend + docs) in one view:

1. Open `/Users/cehring/OMEGA4/frontend/OMEGA4.code-workspace`.
2. Use the `OMEGA4` folder in that workspace for backend/docs/scripts edits.
3. Run tasks from `Terminal: Run Task`:
   - `OMEGA4: setup dev env`
   - `OMEGA4: docker up`
   - `OMEGA4: backend logs`
   - `OMEGA4: healthcheck`
   - `OMEGA4: docker down`

Notes:

- The tasks run from project root (`/Users/cehring/OMEGA4`) automatically.
- Current Codex file-write permissions are scoped to this workspace root unless expanded.

-## Frontend Smoke Test

- Run `frontend/scripts/run-frontend-smoke.sh` from the repo root to batch-install Playwright, authenticate with the `.env` share credentials, and exercise the major modals and toggles.
- Add `--mobile` to simulate the iPhone 13 viewport or `--url=` if you host on a different port (the script still loads credentials and boot code from `.env` by default).
