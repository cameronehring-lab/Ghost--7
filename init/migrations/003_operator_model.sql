-- ==========================================================================
-- OMEGA 4 / Ghost — Operator Model Migration
-- File: init/migrations/003_operator_model.sql
-- Run: psql "$DATABASE_URL" -f init/migrations/003_operator_model.sql
-- ==========================================================================

-- Operator belief store
CREATE TABLE IF NOT EXISTS operator_model (
    id              SERIAL PRIMARY KEY,
    ghost_id        TEXT        NOT NULL DEFAULT 'omega-7',
    dimension       TEXT        NOT NULL,
    belief          TEXT        NOT NULL,
    confidence      FLOAT       NOT NULL DEFAULT 0.35,
    evidence_count  INT         NOT NULL DEFAULT 1,
    formed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_reinforced TIMESTAMPTZ NOT NULL DEFAULT now(),
    invalidated_at  TIMESTAMPTZ,
    formed_by       TEXT        NOT NULL DEFAULT 'operator_synthesis'
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_operator_model_active_dimension
    ON operator_model (ghost_id, dimension)
    WHERE invalidated_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_operator_model_ghost
    ON operator_model (ghost_id, invalidated_at);

-- Contradiction / tension log
CREATE TABLE IF NOT EXISTS operator_contradictions (
    id              SERIAL PRIMARY KEY,
    ghost_id        TEXT        NOT NULL DEFAULT 'omega-7',
    dimension       TEXT        NOT NULL,
    prior_belief_id INT         REFERENCES operator_model(id) ON DELETE SET NULL,
    observed_event  TEXT        NOT NULL,
    tension_score   FLOAT       NOT NULL DEFAULT 0.5,
    resolved        BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_operator_contradictions_unresolved
    ON operator_contradictions (ghost_id, resolved)
    WHERE resolved = FALSE;

-- Verify
DO $$
BEGIN
    RAISE NOTICE 'operator_model rows: %',
        (SELECT COUNT(*) FROM operator_model);
    RAISE NOTICE 'operator_contradictions rows: %',
        (SELECT COUNT(*) FROM operator_contradictions);
    RAISE NOTICE 'Migration 003_operator_model: OK';
END $$;
