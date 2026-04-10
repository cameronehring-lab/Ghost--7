-- Proprioceptive gate transition log
-- idempotent

CREATE TABLE IF NOT EXISTS proprio_transition_log (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    proprio_pressure REAL NOT NULL,
    cadence_modifier REAL NOT NULL,
    signal_snapshot JSONB NOT NULL DEFAULT '{}',
    contributions JSONB NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT 'threshold_crossing'
);

CREATE INDEX IF NOT EXISTS idx_proprio_transition_created
    ON proprio_transition_log (created_at DESC);

