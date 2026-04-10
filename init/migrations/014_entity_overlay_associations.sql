-- File: init/migrations/014_entity_overlay_associations.sql
-- Run: psql "$DATABASE_URL" -f init/migrations/014_entity_overlay_associations.sql

CREATE TABLE IF NOT EXISTS entity_overlay_associations (
    id BIGSERIAL PRIMARY KEY,
    ghost_id TEXT NOT NULL DEFAULT 'omega-7',
    overlay_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    target_entity_type TEXT NOT NULL,
    target_key TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    source TEXT NOT NULL DEFAULT 'atlas_rebuild',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    invalidated_at TIMESTAMPTZ,
    UNIQUE (ghost_id, overlay_type, source_ref, target_entity_type, target_key)
);

CREATE INDEX IF NOT EXISTS idx_entity_overlay_assoc_ghost_updated
ON entity_overlay_associations (ghost_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_entity_overlay_assoc_source
ON entity_overlay_associations (ghost_id, overlay_type, source_ref);

CREATE INDEX IF NOT EXISTS idx_entity_overlay_assoc_target
ON entity_overlay_associations (ghost_id, target_entity_type, target_key);
