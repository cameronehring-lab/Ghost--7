# OMEGA4 Quick Reference

**Date**: 2026-04-10 | Full manual: [`docs/OPERATOR_MANUAL.md`](OPERATOR_MANUAL.md)

---

## Start / Stop

```bash
make up                              # start full stack
make down                            # stop
make logs                            # follow backend logs
docker compose restart backend       # apply Python changes
docker compose up -d --build         # after Dockerfile / requirements change
make clean                           # destroy all volumes (data loss)
```

## Health Checks

```bash
curl http://localhost:8000/health                          # stack health
curl "http://localhost:8000/ghost/llm/backend?include_health=true"   # LLM + constrained backend health
curl http://localhost:8000/somatic                         # live affect state
python3 scripts/backend_bootstrap_verify.py               # full bootstrap verify
python3 scripts/falsification_report.py --full            # evidence audit
```

## Gate States

| State | Pressure | Meaning |
|-------|----------|---------|
| `OPEN` | < 0.40 | Normal — full generation, all actuation allowed |
| `THROTTLED` | 0.40–0.74 | Slowed cadence, reduced token budgets |
| `SUPPRESSED` | ≥ 0.75 | Minimal generation, only protective actuation |

## Governance Tiers

| Tier | Meaning |
|------|---------|
| `NOMINAL` | All surfaces operating normally |
| `CAUTION` | Advisory flags raised; watch mode |
| `STABILIZE` | Enforcement tightened; crystallization throttled |
| `RECOVERY` | Freeze active; most surfaces blocked |

## Access Codes

| Gate | Default | Where |
|------|---------|-------|
| Boot overlay | `OMEGA` | Frontend only — not backend security |
| Ops panel | _(set in .env)_ | Click snail logo in header; set `OPS_TEST_CODE` in `.env` |
| Share mode | set in `.env` | `SHARE_MODE_USERNAME` / `SHARE_MODE_PASSWORD` |

## 18 Tools (Quick List)

**Base (7)**: `update_identity` · `modulate_voice` · `perceive_url_images` · `physics_workbench` · `thought_simulation` · `stack_audit` · `recall_session_history`

**TPCV (5)**: `repository_upsert_content` · `repository_query_content` · `repository_link_data_source` · `repository_status_update` · `repository_sync_master_draft`

**Authoring (6)**: `authoring_get_document` · `authoring_upsert_section` · `authoring_clone_section` · `authoring_merge_sections` · `authoring_rewrite_document` · `authoring_restore_version`

**X/Social (3 — research-isolated)**: `x_post` · `x_read` · `x_profile_update`

## Key URLs (local)

| URL | Purpose |
|-----|---------|
| `http://localhost:8000` | Main UI |
| `http://localhost:8000/health` | Stack health JSON |
| `http://localhost:8000/ghost/llm/backend?include_health=true` | LLM backend + constrained runtime health |
| `http://localhost:8000/somatic` | Live affect state |
| `http://localhost:8000/ghost/self/architecture` | Ghost's live autonomy contract |
| `http://localhost:8000/ghost/autonomy/state` | Drift watchdog status |
| `http://localhost:8000/ghost/observer/latest` | Latest observer report |

## Diagnostics (local-only)

```bash
python3 scripts/falsification_report.py --base-url http://localhost:8000 --full
python3 scripts/backend_bootstrap_verify.py --base-url http://localhost:8000
bash scripts/psych_eval_snapshot.sh --window daily
bash scripts/psych_eval_snapshot.sh --window weekly
curl -X POST http://localhost:8000/diagnostics/constraints/run -H "Content-Type: application/json" -d '{"prompt":"Say exactly two words.","constraints":{"exact_word_count":2}}'
curl -X POST http://localhost:8000/diagnostics/constraints/benchmark -H "Content-Type: application/json" -d '{"persist_artifacts":true}'
```

## Docker Recovery Watchdog

```bash
python3 scripts/docker_recovery_watchdog.py watch    # start loop
python3 scripts/docker_recovery_watchdog.py status   # inspect
python3 scripts/docker_recovery_watchdog.py stop     # stop
bash scripts/install_docker_recovery_watchdog.sh install    # LaunchAgent
```

## Rolodex Retro Sync

```bash
docker compose exec -T backend python /app/scripts/rolodex_retro_sync.py           # dry-run
docker compose exec -T backend python /app/scripts/rolodex_retro_sync.py --apply   # apply
```
