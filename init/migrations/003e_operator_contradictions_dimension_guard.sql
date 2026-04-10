-- ==========================================================================
-- OMEGA 4 / Ghost — Open-Contradiction Dimension Guard
-- File: init/migrations/003e_operator_contradictions_dimension_guard.sql
--
-- Ensures at most one OPEN contradiction per (ghost_id, dimension), so
-- repeated synthesis passes merge rather than spam near-duplicate rows.
-- Safe to run multiple times (idempotent).
-- Run: psql "$DATABASE_URL" -f init/migrations/003e_operator_contradictions_dimension_guard.sql
-- ==========================================================================

-- Resolve duplicate OPEN contradictions within each dimension, keep strongest/latest row OPEN
WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY ghost_id, dimension
            ORDER BY tension_score DESC, created_at DESC, id DESC
        ) AS rn
    FROM operator_contradictions
    WHERE status = 'open'
)
UPDATE operator_contradictions oc
SET resolved = TRUE,
    status = 'resolved',
    resolved_at = COALESCE(oc.resolved_at, now())
FROM ranked r
WHERE oc.id = r.id
  AND r.rn > 1;

-- Enforce one OPEN contradiction per dimension
CREATE UNIQUE INDEX IF NOT EXISTS uq_contradiction_dimension_open
    ON operator_contradictions (ghost_id, dimension)
    WHERE status = 'open';

-- Verify
DO $$
DECLARE
    dup_count INT;
BEGIN
    SELECT COUNT(*) INTO dup_count
    FROM (
        SELECT ghost_id, dimension, COUNT(*) AS c
        FROM operator_contradictions
        WHERE status = 'open'
        GROUP BY ghost_id, dimension
        HAVING COUNT(*) > 1
    ) d;

    IF dup_count > 0 THEN
        RAISE EXCEPTION 'Duplicate open contradictions by dimension remain: %', dup_count;
    END IF;

    RAISE NOTICE 'Migration 003e_operator_contradictions_dimension_guard: OK';
END $$;
