-- ==========================================================================
-- OMEGA 4 / Ghost — RRD-2 Topology + Resonance Layer
-- File: init/migrations/010_rrd2_topology.sql
-- Safe to run multiple times (idempotent where supported)
-- ==========================================================================

CREATE TABLE IF NOT EXISTS identity_topology_state (
    id BIGSERIAL PRIMARY KEY,
    ghost_id TEXT NOT NULL DEFAULT 'omega-7',
    identity_key TEXT NOT NULL,
    stability REAL NOT NULL DEFAULT 0.5,
    plasticity REAL NOT NULL DEFAULT 0.5,
    friction_load REAL NOT NULL DEFAULT 0.0,
    resonance_alignment REAL NOT NULL DEFAULT 0.5,
    last_rrd2_delta REAL NOT NULL DEFAULT 0.0,
    last_decision TEXT NOT NULL DEFAULT 'advisory',
    last_source TEXT NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ghost_id, identity_key)
);

CREATE INDEX IF NOT EXISTS idx_identity_topology_state_ghost_updated
ON identity_topology_state (ghost_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS identity_topology_warp_log (
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
    negative_resonance REAL NOT NULL DEFAULT 0.0,
    structural_cohesion REAL NOT NULL DEFAULT 0.0,
    warp_capacity REAL NOT NULL DEFAULT 0.0,
    rrd2_delta REAL NOT NULL DEFAULT 0.0,
    decision TEXT NOT NULL,
    rollout_phase TEXT NOT NULL DEFAULT 'A',
    would_block BOOLEAN NOT NULL DEFAULT FALSE,
    enforce_block BOOLEAN NOT NULL DEFAULT FALSE,
    reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    degradation_list JSONB NOT NULL DEFAULT '[]'::jsonb,
    shadow_action_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    not_consciousness_metric BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_identity_topology_warp_log_ghost_created
ON identity_topology_warp_log (ghost_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_identity_topology_warp_log_ghost_decision
ON identity_topology_warp_log (ghost_id, decision, created_at DESC);

CREATE TABLE IF NOT EXISTS affect_resonance_log (
    id BIGSERIAL PRIMARY KEY,
    ghost_id TEXT NOT NULL DEFAULT 'omega-7',
    event_source TEXT NOT NULL,
    resonance_axes JSONB NOT NULL DEFAULT '{}'::jsonb,
    resonance_signature JSONB NOT NULL DEFAULT '{}'::jsonb,
    somatic_excerpt JSONB NOT NULL DEFAULT '{}'::jsonb,
    not_consciousness_metric BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_affect_resonance_log_ghost_created
ON affect_resonance_log (ghost_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_affect_resonance_log_ghost_source
ON affect_resonance_log (ghost_id, event_source, created_at DESC);

DO $$
BEGIN
    RAISE NOTICE 'Migration 010_rrd2_topology applied';
END $$;
