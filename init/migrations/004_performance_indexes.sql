-- ==========================================================================
-- OMEGA PROTOCOL — Migration 004: Performance Indexes
-- Adds missing hot-path indexes for existing deployments.
-- Safe to run multiple times.
--
-- Run:
--   psql "$DATABASE_URL" -f init/migrations/004_performance_indexes.sql
-- ==========================================================================

-- Session/message hot paths
CREATE INDEX IF NOT EXISTS idx_messages_created
    ON messages(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sessions_ghost_started
    ON sessions(ghost_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_sessions_ghost_ended_started
    ON sessions(ghost_id, ended_at, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_monologues_ghost_created
    ON monologues(ghost_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_qualia_nexus_created
    ON qualia_nexus(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_actuation_log_created
    ON actuation_log(created_at DESC);

-- Optional table from vector-memory migration.
DO $$
BEGIN
    IF to_regclass('public.vector_memories') IS NOT NULL THEN
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_vector_memories_ghost_created
                 ON vector_memories(ghost_id, created_at DESC)';
    END IF;
END $$;

