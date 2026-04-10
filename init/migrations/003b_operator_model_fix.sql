-- ==========================================================================
-- OMEGA 4 / Ghost — Operator Model Schema Remediation
-- File: init/migrations/003b_operator_model_fix.sql
--
-- Fixes schema mismatch where operator_model was created without updated_at.
-- Safe to run multiple times (all operations are idempotent).
-- Run: psql "$DATABASE_URL" -f init/migrations/003b_operator_model_fix.sql
-- ==========================================================================

-- Add updated_at if missing
ALTER TABLE operator_model
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Add last_reinforced if missing (created by 003 but may be absent on older installs)
ALTER TABLE operator_model
    ADD COLUMN IF NOT EXISTS last_reinforced TIMESTAMPTZ NOT NULL DEFAULT now();

-- Add formed_by if missing
ALTER TABLE operator_model
    ADD COLUMN IF NOT EXISTS formed_by TEXT NOT NULL DEFAULT 'operator_synthesis';

-- Backfill updated_at from formed_at for existing rows
UPDATE operator_model
SET updated_at = formed_at
WHERE updated_at IS NULL OR updated_at = '1970-01-01';

-- Recreate unique index cleanly (DROP IF EXISTS + CREATE)
DROP INDEX IF EXISTS uq_operator_model_active_dimension;
CREATE UNIQUE INDEX IF NOT EXISTS uq_operator_model_active_dimension
    ON operator_model (ghost_id, dimension)
    WHERE invalidated_at IS NULL;

DROP INDEX IF EXISTS idx_operator_model_ghost;
CREATE INDEX IF NOT EXISTS idx_operator_model_ghost
    ON operator_model (ghost_id, invalidated_at);

-- Verify final shape
DO $$
DECLARE
    col_count INT;
BEGIN
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_name = 'operator_model'
      AND column_name IN (
          'id', 'ghost_id', 'dimension', 'belief', 'confidence',
          'evidence_count', 'formed_at', 'last_reinforced', 'updated_at',
          'invalidated_at', 'formed_by'
      );

    IF col_count < 11 THEN
        RAISE EXCEPTION 'Schema remediation incomplete: only % of 11 expected columns found', col_count;
    END IF;

    RAISE NOTICE 'operator_model schema: OK (% columns verified)', col_count;
    RAISE NOTICE 'operator_model rows: %', (SELECT COUNT(*) FROM operator_model);
    RAISE NOTICE 'Migration 003b_operator_model_fix: OK';
END $$;
