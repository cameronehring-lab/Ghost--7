-- ==========================================================================
-- OMEGA 4 / Ghost — RRD-102 Negative Resonance Damping
-- File: init/migrations/012_rrd2_negative_resonance_damping.sql
-- Adds damping audit fields and key-time index for rolling window/refractory logic.
-- Safe to run multiple times.
-- ==========================================================================

ALTER TABLE identity_topology_warp_log
    ADD COLUMN IF NOT EXISTS damping_applied BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE identity_topology_warp_log
    ADD COLUMN IF NOT EXISTS damping_reason TEXT NOT NULL DEFAULT '';

ALTER TABLE identity_topology_warp_log
    ADD COLUMN IF NOT EXISTS damping_meta_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_identity_topology_warp_log_ghost_key_created
    ON identity_topology_warp_log (ghost_id, candidate_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_identity_topology_warp_log_ghost_key_damped
    ON identity_topology_warp_log (ghost_id, candidate_key, damping_applied, created_at DESC);

DO $$
BEGIN
    RAISE NOTICE 'Migration 012_rrd2_negative_resonance_damping applied';
END $$;
