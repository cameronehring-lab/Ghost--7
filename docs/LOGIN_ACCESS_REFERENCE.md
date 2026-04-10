# OMEGA4 Login and Access Reference

Last updated: 2026-03-18

This is the canonical credential inventory for local and remote OMEGA4 operation.
Use it as the single place to check what login/access values exist, where they are configured, and how they are used.

## 1. Human Login and Access Gates

| Surface | Credential | Default / Current Behavior | Where Configured | How It Is Sent | Notes |
|---|---|---|---|---|---|
| Boot overlay UI gate | Boot code | `OMEGA` (hardcoded) | [`frontend/app.js`](../frontend/app.js) (`bindBootLoginEvents`) | Local UI input only | UI-only gate. Not backend security. |
| Share mode (whole app) | `SHARE_MODE_USERNAME`, `SHARE_MODE_PASSWORD` | Username default `omega`; password must be set | `.env` / `.env.example` | HTTP Basic Auth (`Authorization: Basic ...`) | Applies to UI + API + SSE when `SHARE_MODE_ENABLED=true`; exempt paths via `SHARE_MODE_EXEMPT_PATHS` (default `/health`). |
| Hidden ops panel + ops routes | `OPS_TEST_CODE` | _(set in `.env`)_ | `.env` / `backend/config.py` | `X-Ops-Code` header (preferred); `Authorization: Bearer ...`; `?code=` query fallback | Required for `/ops/*` endpoints, `/ghost/chat` messages starting with `/ops/`, core-personality modification approval in chat, and explicit authorization for high-risk model actuations. |
| Operator control auth | `OPERATOR_API_TOKEN` | Empty by default (disabled unless set) | `.env` / `backend/config.py` | `X-Operator-Token` header or `Authorization: Bearer ...` | Governs `_require_operator_access` routes. If unset, trusted-local-source fallback is used. |

## 2. Backend Route Auth Classes (Login-Relevant)

Source of truth: [`docs/API_CONTRACT.md`](./API_CONTRACT.md)

- `share_mode_auth` middleware:
  - Enables HTTP Basic Auth across almost all routes when `SHARE_MODE_ENABLED=true`.
- `_require_operator_access`:
  - Requires `OPERATOR_API_TOKEN` when set.
  - If token is unset, allows trusted local CIDRs and same-origin local browser conditions.
- `_require_ops_access`:
  - Requires valid `OPS_TEST_CODE`.
- `_require_operator_or_ops_access`:
  - Accepts either operator token path or ops-code path.

## 3. Infrastructure Service Login Credentials

These are not UI logins, but they are runtime credentials and should be tracked with the same rigor.

| Service | Credential Fields | Local Dev Defaults (from `.env.example`) | Notes |
|---|---|---|---|
| PostgreSQL | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `ghost` / `<set in .env>` / `omega` | Used by backend `POSTGRES_URL` connection construction in compose/env. |
| InfluxDB | `INFLUXDB_INIT_USERNAME`, `INFLUXDB_INIT_PASSWORD`, `INFLUXDB_INIT_ADMIN_TOKEN` | `omega` / `<set in .env>` / `<set in .env>` | Setup/bootstrap credentials. Rotate for any non-local deployment. |
| Redis | `REDIS_URL` | `redis://redis:6379/0` | Local dev default has no password. Add auth/TLS if exposed outside local network. |

## 4. External Provider API Credentials

| Integration | Credential Fields |
|---|---|
| Gemini | `GOOGLE_API_KEY` |
| OpenWeather | `OPENWEATHER_API_KEY` |
| ElevenLabs | `ELEVENLABS_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |

## 5. Credential Storage Policy

- Store real secrets in local `.env` only.
- Do not commit live secrets to git.
- Treat `.env.example` values as local-development placeholders/defaults only.
- Rotate at minimum:
  - `OPS_TEST_CODE` every 30 days.
  - `SHARE_MODE_PASSWORD` when sharing scope changes.
  - `OPERATOR_API_TOKEN` after any exposure event.

## 6. Quick Header Reference

- Share mode:
  - `Authorization: Basic <base64(username:password)>`
- Operator token:
  - `X-Operator-Token: <token>`
  - or `Authorization: Bearer <token>`
- Ops code:
  - `X-Ops-Code: <code>`
  - or `Authorization: Bearer <code>`
  - or `?code=<code>` (fallback)
