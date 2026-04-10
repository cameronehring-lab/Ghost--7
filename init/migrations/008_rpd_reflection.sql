-- ==========================================================================
-- OMEGA 4 / Ghost — RPD-1 Reflection Integration (Advisory-First)
-- File: init/migrations/008_rpd_reflection.sql
-- Safe to run multiple times (idempotent where supported)
-- ===========================================================================

CREATE TABLE IF NOT EXISTS rpd_assessment_log (
    id BIGSERIAL PRIMARY KEY,
    ghost_id TEXT NOT NULL DEFAULT 'omega-7',
    source TEXT NOT NULL,
    candidate_type TEXT NOT NULL,
    candidate_key TEXT NOT NULL,
    candidate_value TEXT NOT NULL,
    resonance_score REAL NOT NULL,
    entropy_score REAL NOT NULL,
    shared_clarity_score REAL NOT NULL,
    topology_warp_delta REAL NOT NULL,
    decision TEXT NOT NULL,
    degradation_list JSONB NOT NULL DEFAULT '[]'::jsonb,
    not_consciousness_metric BOOLEAN NOT NULL DEFAULT TRUE,
    shadow_action_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rpd_assessment_ghost_created
ON rpd_assessment_log (ghost_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rpd_assessment_ghost_source
ON rpd_assessment_log (ghost_id, source, created_at DESC);

CREATE TABLE IF NOT EXISTS reflection_residue (
    id BIGSERIAL PRIMARY KEY,
    ghost_id TEXT NOT NULL DEFAULT 'omega-7',
    source TEXT NOT NULL,
    candidate_type TEXT NOT NULL,
    candidate_key TEXT NOT NULL,
    residue_text TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT 'low_shared_clarity',
    candidate_hash TEXT NOT NULL,
    revisit_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_assessed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_reflection_residue_ghost_status
ON reflection_residue (ghost_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_reflection_residue_ghost_created
ON reflection_residue (ghost_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_reflection_residue_pending_hash
ON reflection_residue (ghost_id, candidate_hash, status)
WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS shared_conceptual_manifold (
    id BIGSERIAL PRIMARY KEY,
    ghost_id TEXT NOT NULL DEFAULT 'omega-7',
    concept_key TEXT NOT NULL,
    concept_text TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'reflection',
    status TEXT NOT NULL DEFAULT 'proposed',
    confidence REAL NOT NULL DEFAULT 0.6,
    rpd_score REAL NOT NULL DEFAULT 0.0,
    topology_warp_delta REAL NOT NULL DEFAULT 0.0,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ghost_id, concept_key)
);

CREATE INDEX IF NOT EXISTS idx_shared_manifold_ghost_status
ON shared_conceptual_manifold (ghost_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_shared_manifold_ghost_created
ON shared_conceptual_manifold (ghost_id, created_at DESC);

DO $$
BEGIN
    RAISE NOTICE 'Migration 008_rpd_reflection applied';
END $$;
