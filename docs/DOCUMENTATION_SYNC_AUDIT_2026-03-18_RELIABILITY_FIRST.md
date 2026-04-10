# Documentation Sync Audit (2026-03-18, Reliability-First Expansion)

This artifact records the documentation parity pass for the reliability-first autonomous expansion implementation completed on 2026-03-18.

## 1. Scope

- Canonical bootstrap/verify flow added.
- External grounding fanout hardened with global/per-adapter budgets.
- Experiment artifacts extended with explicit action/agency continuity metrics.
- Somatic weighting regression gates expanded for `decay_engine.py` + `ambient_sensors.py`.

## 2. Contract Deltas

### 2.1 Grounding Budget + Provenance

- New runtime env knobs:
  - `GROUNDING_TOTAL_BUDGET_MS` (default `1200`)
  - `GROUNDING_ADAPTER_TIMEOUT_MS` (default `800`)
- Prompt provenance envelope now includes:
  - `attempted_count`
  - `source_count`
  - `total_budget_ms`
  - `adapter_timeout_ms`
  - per-source `status` (`ok`, `empty`, `failed`, `timed_out`) and optional `error`
- Only `ok` + non-empty adapter outputs emit `[GROUNDING_SOURCE ...]` blocks.

### 2.2 Reliability Metric Definitions

- `same_turn_confirmation_rate`
  - Source: targeted confirmation unit suite in `scripts/experiment_runner.py`
  - Formula: `passed / total`
- `agency_trace_alignment_rate`
  - Source: `actuation_agency_alignment` scenario
  - Window: `5` seconds (default)
  - Formula: `aligned / total`
  - Misalignment buckets:
    - `missing_trace`
    - `wrong_label`
    - `wrong_sign`
    - `missing_outcome`
- Weather/systemic balance:
  - `weather_only_max_axis_delta`
  - `systemic_max_axis_delta`
  - `systemic_vs_weather_ratio`

### 2.3 Canonical Bootstrap Verifier

- New script: `scripts/backend_bootstrap_verify.py`
- Canonical failure classes:
  - `env_missing_dep`
  - `service_unreachable`
  - `policy_block_expected`
  - `regression_failure`

## 3. Acceptance Threshold Snapshot

- `same_turn_confirmation_rate >= 0.95`
- `agency_trace_alignment_rate >= 0.95`
- weather-only per-axis delta `<= 0.08`
- systemic stress magnitude `>= 3x` weather-only magnitude
- duplicate same-turn actuation execution `= 0`

## 4. Updated Canonical Docs

- `README.md`
- `docs/API_CONTRACT.md`
- `docs/SYSTEM_DESIGN.md`
- `docs/LAYER_DATA_TOC.md`
- `CHANGELOG.md`
- `.env.example`

## 5. Validation Surface Updates

- Added/updated tests:
  - `backend/test_ghost_api_external_context.py`
  - `backend/test_ambient_trace_balance.py`
  - `backend/test_experiment_runner.py`
- Updated runtime/ops scripts:
  - `scripts/backend_bootstrap_verify.py`
  - `scripts/experiment_runner.py`
  - `scripts/fixtures/campaign.json`
