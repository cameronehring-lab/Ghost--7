# Release Checklist

Use this checklist before tagging or handing off a meaningful tooling update.

## Documentation

- `CHANGELOG.md` reflects user-visible changes.
- Relevant dev-log entries are present in `docs/dev-log/`.
- New architectural decisions are captured in `docs/decisions/`.

## Code and data shape

- Migration notes exist for schema or manifest changes.
- Helper scripts print clear errors for invalid inputs.
- Export generation still works against the current research workspace.

## Validation

- Run `scripts/validate-ledger` against the research workspace.
- Run any repo-specific smoke or regression checks.
- Confirm generated exports were refreshed if ledger contents changed.

## Commit hygiene

- Commit subjects use the agreed prefixes.
- Changes are atomic and grouped by purpose.
- Temporary files and large artifacts are not staged accidentally.
