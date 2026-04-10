-- IIT assessment log for advisory/soft governance
-- idempotent creation

CREATE TABLE IF NOT EXISTS iit_assessment_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    mode TEXT NOT NULL,            -- off|advisory|soft at time of run
    backend TEXT NOT NULL,         -- heuristic|pyphi|...
    substrate_completeness_score INT NOT NULL,
    not_consciousness_metric BOOLEAN NOT NULL DEFAULT TRUE,
    substrate_json JSONB NOT NULL,
    metrics_json JSONB NOT NULL,
    maximal_complex_json JSONB,
    advisory_json JSONB,
    compute_ms DOUBLE PRECISION,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_iit_assessment_created
    ON iit_assessment_log (created_at DESC);

