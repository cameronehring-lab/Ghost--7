# OMEGA4 Backend Runtime Note
## Reliability-First Autonomous Expansion (2026-03-18)

This note captures backend/runtime contract changes added in the reliability-first expansion pass.

## 1. Canonical Bootstrap + Verification Flow

- Script: `scripts/backend_bootstrap_verify.py`
- Purpose: deterministic startup/verification gate for dependency, service, policy, and regression checks.
- Normalized failure classes:
  - `env_missing_dep`
  - `service_unreachable`
  - `policy_block_expected`
  - `regression_failure`

## 2. External Grounding Budget Hardening

- New config knobs:
  - `GROUNDING_TOTAL_BUDGET_MS=1200` (default)
  - `GROUNDING_ADAPTER_TIMEOUT_MS=800` (default)
- `ghost_api._external_reference_context(...)` now:
  - enforces per-adapter timeout and global parallel budget,
  - preserves per-source statuses in provenance (`ok|empty|failed|timed_out`),
  - keeps non-success sources provenance-only,
  - emits source wrappers only for `ok` + non-empty payloads.

## 3. Experiment Metrics and Agency Alignment

- `scripts/experiment_runner.py` now emits `quality_metrics` in `run_summary.json`:
  - `same_turn_confirmation_rate`
  - `agency_trace_alignment_rate`
  - `weather_only_max_axis_delta`
  - `systemic_max_axis_delta`
  - `systemic_vs_weather_ratio`
- New scenario type: `actuation_agency_alignment`
  - deterministic `5s` outcome-to-trace matching window,
  - misalignment buckets:
    - `missing_trace`
    - `wrong_label`
    - `wrong_sign`
    - `missing_outcome`

## 4. Regression Coverage Additions

- `backend/test_ghost_api_external_context.py`:
  - verifies provenance status handling for `ok|empty|timed_out`.
- `backend/test_ambient_trace_balance.py`:
  - asserts weather/systemic magnitude thresholds,
  - asserts `decay_engine` and `ambient_sensors` weight contracts.
- `backend/test_experiment_runner.py`:
  - validates agency alignment metric aggregation and quality metric wiring.
