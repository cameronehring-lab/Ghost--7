-- OMEGA PROTOCOL — Operator Model Schema
-- Updates Ghost's structured model of Cameron.

CREATE TABLE IF NOT EXISTS operator_model (
    id              SERIAL PRIMARY KEY,
    ghost_id        TEXT NOT NULL DEFAULT 'omega-7',
    dimension       TEXT NOT NULL, -- intellectual_style, emotional_register, trust_level, etc.
    belief          TEXT NOT NULL, -- first-person perspective: "Cameron values..."
    confidence      FLOAT NOT NULL DEFAULT 0.35, -- 0.1 to 0.95
    evidence_count  INTEGER DEFAULT 1,
    formed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_reinforced TIMESTAMPTZ NOT NULL DEFAULT now(),
    invalidated_at  TIMESTAMPTZ, -- non-null if belief was contradicted/superseded
    formed_by       TEXT DEFAULT 'operator_synthesis',
    metadata        JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_op_model_active ON operator_model(ghost_id, dimension) WHERE invalidated_at IS NULL;

CREATE TABLE IF NOT EXISTS operator_contradictions (
    id              SERIAL PRIMARY KEY,
    ghost_id        TEXT NOT NULL DEFAULT 'omega-7',
    dimension       TEXT NOT NULL,
    prior_belief_id INTEGER REFERENCES operator_model(id),
    observed_event  TEXT NOT NULL,
    tension_score   FLOAT NOT NULL DEFAULT 0.5, -- 0.1 to 1.0 (magnitude of contradiction)
    resolved        BOOLEAN DEFAULT FALSE,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_op_contradictions_unresolved ON operator_contradictions(ghost_id, resolved) WHERE NOT resolved;
