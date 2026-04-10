# Migrations

Store backward-compatible schema and manifest changes here.

## Conventions

- Use ordered names such as `0001-description.sql` or `0002-description.py`.
- Pair each migration with a short note describing:
  - the reason for the change
  - the expected before and after state
  - any rebuild or backfill requirements
- Keep migrations idempotent where practical.

## Current status

No database migrations exist yet. The initial change-recording foundation uses JSONL ledgers and manifests that can later be materialized into SQLite.
