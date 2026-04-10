-- ==========================================================================
-- OMEGA 4 / Ghost — RRD-101 Performance Observability
-- File: init/migrations/011_rrd2_perf_observability.sql
-- Adds per-candidate runtime metadata to identity_topology_warp_log.
-- Safe to run multiple times.
-- ==========================================================================

ALTER TABLE identity_topology_warp_log
    ADD COLUMN IF NOT EXISTS eval_ms REAL NOT NULL DEFAULT 0.0;

ALTER TABLE identity_topology_warp_log
    ADD COLUMN IF NOT EXISTS candidate_batch_size INT NOT NULL DEFAULT 0;

ALTER TABLE identity_topology_warp_log
    ADD COLUMN IF NOT EXISTS candidate_batch_index INT NOT NULL DEFAULT 0;

ALTER TABLE identity_topology_warp_log
    ADD COLUMN IF NOT EXISTS queue_depth_snapshot INT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_identity_topology_warp_log_ghost_eval
    ON identity_topology_warp_log (ghost_id, created_at DESC, eval_ms);

DO $$
BEGIN
    RAISE NOTICE 'Migration 011_rrd2_perf_observability applied';
END $$;
