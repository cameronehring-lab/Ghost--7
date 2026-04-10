# ADR-0002: QUANT scoring for archive capture selection

- Status: Accepted
- Date: 2026-03-21

## Context

Archive searches can return many captures for the same page. We need a fast, repeatable way to decide which snapshot to recover first without pretending the ranking is objective truth.

## Decision

Use a lightweight heuristic called `QUANT` to score candidate captures from 0 to 100:

- `Q` query fit
- `U` uniqueness
- `A` authority
- `N` novelty
- `T` temporal fit

Each component contributes up to 20 points. The breakdown is written into the capture row as `quant_breakdown`, and the total is stored as `quant_score`.

The intended use is prioritization, not epistemic certainty.

## Consequences

### Positive

- Capture selection is more transparent than “pick the latest row.”
- We can debug ranking decisions by inspecting component scores.
- The score can later be tuned without changing the append-only ledger model.

### Tradeoffs

- The weights are heuristic and may need revision after real usage.
- Domain authority is simplified and does not replace source evaluation by a human researcher.
- A high QUANT score means “good recovery candidate,” not “true claim.”
