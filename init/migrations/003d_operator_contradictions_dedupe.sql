-- ==========================================================================
-- OMEGA 4 / Ghost — Contradiction Dedupe Guard
-- File: init/migrations/003d_operator_contradictions_dedupe.sql
--
-- Prevents duplicate open contradictions for the same evidence event.
-- Safe to run multiple times (idempotent).
-- Run: psql "$DATABASE_URL" -f init/migrations/003d_operator_contradictions_dedupe.sql
-- ==========================================================================

-- 1) Normalize unresolved state for rows that are clearly open
UPDATE operator_contradictions
SET status = 'open'
WHERE (status IS NULL OR status = '')
  AND COALESCE(resolved, FALSE) = FALSE;

-- 2) Resolve duplicate open contradictions, keeping most recent row open
WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY ghost_id, dimension, observed_event
            ORDER BY created_at DESC, id DESC
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

-- 3) Enforce uniqueness for open contradictions
CREATE UNIQUE INDEX IF NOT EXISTS uq_contradiction_event
    ON operator_contradictions (ghost_id, dimension, observed_event)
    WHERE status = 'open';

-- 4) Verify
DO $$
DECLARE
    dup_count INT;
    open_count INT;
BEGIN
    SELECT COUNT(*) INTO dup_count
    FROM (
        SELECT ghost_id, dimension, observed_event, COUNT(*) AS c
        FROM operator_contradictions
        WHERE status = 'open'
        GROUP BY ghost_id, dimension, observed_event
        HAVING COUNT(*) > 1
    ) d;

    SELECT COUNT(*) INTO open_count
    FROM operator_contradictions
    WHERE status = 'open';

    IF dup_count > 0 THEN
        RAISE EXCEPTION 'Duplicate open contradictions remain: %', dup_count;
    END IF;

    RAISE NOTICE 'Open contradiction rows: %', open_count;
    RAISE NOTICE 'Migration 003d_operator_contradictions_dedupe: OK';
END $$;
