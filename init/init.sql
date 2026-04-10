-- OMEGA PROTOCOL — PostgreSQL Schema
-- Auto-runs on first container start via docker-entrypoint-initdb.d

-- Sessions: each browser session is a conversation
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    ghost_id        TEXT NOT NULL DEFAULT 'omega-7',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    summary         TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb
);

-- Messages: full conversation history
CREATE TABLE IF NOT EXISTS messages (
    id              SERIAL PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'model', 'system')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    token_count     INTEGER,
    metadata        JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_ghost_started ON sessions(ghost_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_ghost_ended_started ON sessions(ghost_id, ended_at, started_at DESC);

-- Monologues: Ghost's internal reflections from LangGraph loop
CREATE TABLE IF NOT EXISTS monologues (
    id              SERIAL PRIMARY KEY,
    ghost_id        TEXT NOT NULL DEFAULT 'omega-7',
    content         TEXT NOT NULL,
    somatic_state   JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_monologues_created ON monologues(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_monologues_ghost_created ON monologues(ghost_id, created_at DESC);

-- Actuation log: every somatic defense action Ghost takes
CREATE TABLE IF NOT EXISTS actuation_log (
    id              SERIAL PRIMARY KEY,
    action          TEXT NOT NULL,
    parameters      JSONB,
    result          TEXT,
    somatic_state   JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_actuation_log_created
ON actuation_log(created_at DESC);

-- Operator model: consolidated beliefs about the Operator
CREATE TABLE IF NOT EXISTS operator_model (
    id              SERIAL PRIMARY KEY,
    ghost_id        TEXT NOT NULL DEFAULT 'omega-7',
    dimension       TEXT NOT NULL,
    belief          TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 0.35,
    evidence_count  INTEGER NOT NULL DEFAULT 1,
    formed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_reinforced TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    invalidated_at  TIMESTAMPTZ,
    formed_by       TEXT NOT NULL DEFAULT 'operator_synthesis'
);

CREATE INDEX IF NOT EXISTS idx_operator_model_updated
ON operator_model(ghost_id, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_operator_model_active_dimension
ON operator_model(ghost_id, dimension)
WHERE invalidated_at IS NULL;

-- Contradiction log: tracks conflicts in operator-model evidence over time
CREATE TABLE IF NOT EXISTS operator_contradictions (
    id              SERIAL PRIMARY KEY,
    ghost_id        TEXT NOT NULL DEFAULT 'omega-7',
    dimension       TEXT NOT NULL,
    prior_belief_id INTEGER REFERENCES operator_model(id) ON DELETE SET NULL,
    observed_event  TEXT NOT NULL,
    tension_score   REAL NOT NULL DEFAULT 0.5,
    resolved        BOOLEAN NOT NULL DEFAULT FALSE,
    -- Compatibility columns for alternate schema snapshots
    key             TEXT,
    old_value       TEXT,
    new_value       TEXT,
    conflict_score  REAL NOT NULL DEFAULT 0.0,
    evidence        JSONB NOT NULL DEFAULT '{}'::jsonb,
    status          TEXT NOT NULL DEFAULT 'open',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_operator_contradictions_open
ON operator_contradictions(ghost_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_operator_contradictions_unresolved
ON operator_contradictions(ghost_id, resolved, created_at DESC)
WHERE resolved = FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_contradiction_event
ON operator_contradictions(ghost_id, dimension, observed_event)
WHERE status = 'open';

CREATE UNIQUE INDEX IF NOT EXISTS uq_contradiction_dimension_open
ON operator_contradictions(ghost_id, dimension)
WHERE status = 'open';
