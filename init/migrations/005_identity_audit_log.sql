-- OMEGA PROTOCOL: Identity Audit Trail
-- Tracks every modification to Ghost's Identity Matrix

CREATE TABLE IF NOT EXISTS identity_audit_log (
    id              SERIAL PRIMARY KEY,
    ghost_id        TEXT NOT NULL DEFAULT 'omega-7',
    key             TEXT NOT NULL,
    prev_value      TEXT,
    new_value       TEXT NOT NULL,
    updated_by      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_identity_audit_log_key_created 
ON identity_audit_log(ghost_id, key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_identity_audit_log_created
ON identity_audit_log(created_at DESC);
