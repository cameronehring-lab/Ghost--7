-- ==========================================================================
-- OMEGA 4 / Ghost — Operator Contradictions Schema Remediation
-- File: init/migrations/003c_operator_contradictions_fix.sql
--
-- Reconciles legacy schema (dimension/observed_event/resolved) with
-- runtime/bootstrap schema (key/new_value/status/resolved_at).
-- Safe to run multiple times (idempotent).
-- Run: psql "$DATABASE_URL" -f init/migrations/003c_operator_contradictions_fix.sql
-- ==========================================================================

-- Legacy columns expected by operator_synthesis + consolidation
ALTER TABLE operator_contradictions
    ADD COLUMN IF NOT EXISTS dimension TEXT;
ALTER TABLE operator_contradictions
    ADD COLUMN IF NOT EXISTS prior_belief_id INT;
ALTER TABLE operator_contradictions
    ADD COLUMN IF NOT EXISTS observed_event TEXT;
ALTER TABLE operator_contradictions
    ADD COLUMN IF NOT EXISTS tension_score DOUBLE PRECISION NOT NULL DEFAULT 0.5;
ALTER TABLE operator_contradictions
    ADD COLUMN IF NOT EXISTS resolved BOOLEAN NOT NULL DEFAULT FALSE;

-- Runtime/bootstrap compatibility columns used by main/init schema
ALTER TABLE operator_contradictions
    ADD COLUMN IF NOT EXISTS key TEXT;
ALTER TABLE operator_contradictions
    ADD COLUMN IF NOT EXISTS old_value TEXT;
ALTER TABLE operator_contradictions
    ADD COLUMN IF NOT EXISTS new_value TEXT;
ALTER TABLE operator_contradictions
    ADD COLUMN IF NOT EXISTS conflict_score REAL NOT NULL DEFAULT 0.0;
ALTER TABLE operator_contradictions
    ADD COLUMN IF NOT EXISTS evidence JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE operator_contradictions
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'open';
ALTER TABLE operator_contradictions
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;

-- Ensure timestamp baseline exists for old schemas
ALTER TABLE operator_contradictions
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Backfill mappings between old and new compatibility fields
UPDATE operator_contradictions
SET status = CASE WHEN resolved THEN 'resolved' ELSE 'open' END
WHERE status IS NULL OR status = '';

UPDATE operator_contradictions
SET resolved = CASE WHEN status = 'resolved' THEN TRUE ELSE FALSE END
WHERE resolved IS NULL;

UPDATE operator_contradictions
SET resolved_at = COALESCE(resolved_at, created_at, now())
WHERE (status = 'resolved' OR resolved = TRUE) AND resolved_at IS NULL;

UPDATE operator_contradictions
SET dimension = COALESCE(NULLIF(dimension, ''), key, 'unknown')
WHERE dimension IS NULL OR dimension = '';

UPDATE operator_contradictions
SET key = COALESCE(NULLIF(key, ''), dimension)
WHERE key IS NULL OR key = '';

UPDATE operator_contradictions
SET observed_event = COALESCE(observed_event, new_value, old_value, 'unspecified contradiction')
WHERE observed_event IS NULL OR observed_event = '';

UPDATE operator_contradictions
SET tension_score = conflict_score
WHERE tension_score IS NULL AND conflict_score IS NOT NULL;

UPDATE operator_contradictions
SET conflict_score = tension_score::REAL
WHERE (conflict_score IS NULL OR conflict_score = 0.0) AND tension_score IS NOT NULL;

-- Keep indexes aligned with both query styles
DROP INDEX IF EXISTS idx_operator_contradictions_open;
CREATE INDEX IF NOT EXISTS idx_operator_contradictions_open
    ON operator_contradictions (ghost_id, status, created_at DESC);

DROP INDEX IF EXISTS idx_operator_contradictions_unresolved;
CREATE INDEX IF NOT EXISTS idx_operator_contradictions_unresolved
    ON operator_contradictions (ghost_id, resolved, created_at DESC)
    WHERE resolved = FALSE;

-- Verify final shape
DO $$
DECLARE
    col_count INT;
BEGIN
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_name = 'operator_contradictions'
      AND column_name IN (
          'id', 'ghost_id', 'dimension', 'prior_belief_id', 'observed_event',
          'tension_score', 'resolved', 'status', 'created_at', 'resolved_at',
          'key', 'old_value', 'new_value', 'conflict_score', 'evidence'
      );

    IF col_count < 15 THEN
        RAISE EXCEPTION 'Schema remediation incomplete: only % of 15 expected columns found', col_count;
    END IF;

    RAISE NOTICE 'operator_contradictions schema: OK (% columns verified)', col_count;
    RAISE NOTICE 'open tensions: %',
        (SELECT COUNT(*) FROM operator_contradictions WHERE resolved = FALSE);
    RAISE NOTICE 'Migration 003c_operator_contradictions_fix: OK';
END $$;
