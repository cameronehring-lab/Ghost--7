# ADR-0001: Dual-repo change recording with append-only research ledgers

- Status: Accepted
- Date: 2026-03-21

## Context

The project needs to evolve in two directions at the same time:

- Tooling development for the skill, capture scripts, exports, and validation.
- Ongoing research collection with changing interpretations, recovered media, and timeline updates.

Those concerns have different storage pressures. Code benefits from a normal Git repository. Research artifacts can become large, and research conclusions may need careful correction without erasing prior states.

## Decision

Use two Git-tracked projects:

- `/Users/cehring/OMEGA4/frontend` for code, scripts, migrations, and documentation.
- `/Users/cehring/Downloads/uap-research-workspace` for journals, manifests, append-only JSONL ledgers, and generated exports.

Track large media outside normal Git history. Persist provenance in Git-tracked metadata:

- source and archive URLs
- retrieval timestamps
- SHA-256 hashes
- local storage paths
- linked entities and events

Treat SQLite as an operational cache that can be rebuilt from ledgers plus migrations.

## Consequences

### Positive

- Tool history stays readable and lightweight.
- Research interpretation changes remain auditable.
- Rebuilding and verification become straightforward.
- Large media can grow without bloating Git history.

### Tradeoffs

- Two repos require clear workflow discipline.
- Ledger validation is now part of the normal process.
- Some convenience is sacrificed in exchange for provenance and auditability.
