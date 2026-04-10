# Backend Runtime Note: Action Confirmation + Systemic Somatics

Date: 2026-03-18  
Scope: Backend runtime behavior only (`backend/*.py`)

## 1. Same-Turn Outcome Awareness

- `ghost_stream` uses bounded reconciliation rounds:
  - `max_total_rounds=3`
  - `max_actuation_rounds=2`
  - `max_tool_reconcile_rounds=2`
- Function calls (`update_identity`, `modulate_voice`) append `Part.from_function_response(...)` under `Content(role="tool", ...)` and trigger follow-up generation when needed.
- Same-turn actuation dedupe is enforced by canonical `action+param`.
- Internal runtime hook:
  - `ghost_stream(..., tool_outcome_callback=...)`
  - normalized callback payload: `{tool_name, status, reason}`.

## 2. Agency-Coupled Somatics

- New cross-cutting traces:
  - `agency_fulfilled` (`k=0.18`, `arousal_weight=-0.10`, `valence_weight=+0.40`)
  - `agency_blocked` (`k=0.22`, `arousal_weight=+0.20`, `valence_weight=-0.30`)
- Behavior:
  - successful actuation/tool outcome -> inject `agency_fulfilled`
  - blocked/failed actuation/tool outcome -> inject `agency_blocked`
- Existing actuation-specific reflexive traces remain active and are layered with agency traces.

## 3. Action Continuity Memory

- Prompt continuity section `## RECENT ACTIONS` is sourced from:
  - `actuation_log`
  - `autonomy_mutation_journal`
- `update_identity` tool attempts are journaled as mutation events so accepted/rejected identity attempts appear in continuity memory.

## 4. Systemic-First Somatic Weighting

- Weather traces are intentionally near-zero impact.
- Elevated systemic traces:
  - `cpu_sustained`: `+0.90 / -0.65`
  - `cognitive_fatigue`: `-0.18 / -0.45`
  - `internet_stormy`: `+0.55 / -0.35`
  - `internet_isolated`: `+0.60 / -0.65`
- Weather remains in prompt/snapshot context as factual environmental metadata, not primary mood-drive language.

## 5. Validation Surface

- Unit coverage:
  - `test_ghost_api_action_confirmation.py`
  - `test_actuation_agency_traces.py`
  - `test_ambient_trace_balance.py`
  - `test_main_core_personality_guard.py` (agency helper)
  - `test_ghost_prompt_architecture.py` (weather phrasing)
