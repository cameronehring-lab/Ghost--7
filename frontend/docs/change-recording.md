# Change Recording Guide

This project uses two Git-tracked work areas with different responsibilities:

- `/Users/cehring/OMEGA4/frontend`
  Tooling repo for the skill, scripts, schema migrations, and UI.
- `/Users/cehring/Downloads/uap-research-workspace`
  Research repo for journals, ledgers, manifests, and generated exports.

## Commit prefixes

Use short, atomic commit subjects with one of these prefixes:

- `tool:` feature or behavior changes
- `schema:` database, manifest, or export format changes
- `docs:` changelog, ADR, process, or workflow docs
- `fix:` bug fixes
- `test:` verification-only work

## Tool repo workflow

1. Start the session with `scripts/new-dev-session "summary"`.
2. Make code or documentation changes.
3. Update `CHANGELOG.md` for user-visible changes.
4. Add or update an ADR when architecture or methodology changes.
5. Run any relevant checks before committing.

## Research repo workflow

1. Start a run with `scripts/new-research-run --reason "..." --mode recover`.
2. Save or link artifacts locally, then hash them with `scripts/hash-artifact`.
3. Append rows to the relevant JSONL ledgers.
4. Summarize the work in `journal/research-log.md` and `journal/recovery-log.md`.
5. Regenerate `exports/timeline.md` and `exports/evidence-log.md` with `scripts/build-exports`.
6. Validate with `scripts/validate-ledger`.

For Wayback-based recovery, use `scripts/recover-wayback URL --debug` to run the full loop in one step:

- query CDX
- rank captures with QUANT
- save the chosen artifact locally
- append source, capture, artifact, event, and run records
- refresh exports

Add `--plain` for log-friendly output or `--json` if you want a machine-readable final summary.

## Append-only rule

Interpretive rows in the research ledgers should be superseded, not rewritten.

- Preserve the original row.
- Append a new row with a fresh `record_id`.
- Set `supersedes_record_id` to the earlier row.
- Record the reason in the row and summarize material changes in the research journal.

## Large artifacts

Large recovered media stays out of Git history.

- Use the on-disk artifact directories in the research workspace.
- Track provenance, hashes, and local paths in Git-tracked JSONL ledgers.
- Keep only small fixtures in Git if they are needed for tests.

## QUANT scoring

Wayback captures are ranked with a simple quantitative heuristic called `QUANT`:

- `Q` query fit: how closely the archived capture matches the requested URL
- `U` uniqueness: whether the digest is new to the local workspace
- `A` authority: how trustworthy the source domain is for primary evidence
- `N` novelty: whether this exact replay URL has already been recorded
- `T` temporal fit: closeness to a target date when provided, otherwise recency among available captures

The score is stored with each capture row as `quant_score` plus a `quant_breakdown` object.
