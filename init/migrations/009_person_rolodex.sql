-- ==========================================================================
-- OMEGA 4 / Ghost — Person Rolodex
-- File: init/migrations/009_person_rolodex.sql
--
-- Adds persistent per-person memory tables:
--   - person_rolodex
--   - person_memory_facts
--   - person_session_binding
--
-- Safe to run multiple times (idempotent).
-- Run: psql "$DATABASE_URL" -f init/migrations/009_person_rolodex.sql
-- ==========================================================================

CREATE TABLE IF NOT EXISTS person_rolodex (
    id SERIAL PRIMARY KEY,
    ghost_id TEXT NOT NULL DEFAULT 'omega-7',
    person_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    interaction_count INTEGER NOT NULL DEFAULT 0,
    mention_count INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0.35,
    notes TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ghost_id, person_key)
);

CREATE TABLE IF NOT EXISTS person_memory_facts (
    id SERIAL PRIMARY KEY,
    ghost_id TEXT NOT NULL DEFAULT 'omega-7',
    person_key TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    source_session_id UUID,
    source_role TEXT NOT NULL DEFAULT 'user',
    evidence_text TEXT NOT NULL DEFAULT '',
    first_observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    observation_count INTEGER NOT NULL DEFAULT 1,
    invalidated_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}',
    UNIQUE (ghost_id, person_key, fact_type, fact_value, source_role)
);

CREATE TABLE IF NOT EXISTS person_session_binding (
    id SERIAL PRIMARY KEY,
    ghost_id TEXT NOT NULL DEFAULT 'omega-7',
    session_id UUID NOT NULL,
    person_key TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ghost_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_person_rolodex_ghost_last_seen
    ON person_rolodex (ghost_id, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_person_memory_facts_lookup
    ON person_memory_facts (ghost_id, person_key, last_observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_person_memory_facts_active
    ON person_memory_facts (ghost_id, person_key)
    WHERE invalidated_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_person_session_binding_lookup
    ON person_session_binding (ghost_id, session_id);

DO $$
BEGIN
    RAISE NOTICE 'person_rolodex rows: %', (SELECT COUNT(*) FROM person_rolodex);
    RAISE NOTICE 'person_memory_facts rows: %', (SELECT COUNT(*) FROM person_memory_facts);
    RAISE NOTICE 'Migration 009_person_rolodex: OK';
END $$;

