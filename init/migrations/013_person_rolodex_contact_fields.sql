-- ==========================================================================
-- OMEGA 4 / Ghost — Person Rolodex Contact Handle
-- File: init/migrations/013_person_rolodex_contact_fields.sql
--
-- Adds contact_handle used for iMessage sender/target resolution.
-- Safe to run multiple times.
-- ==========================================================================

ALTER TABLE person_rolodex
ADD COLUMN IF NOT EXISTS contact_handle TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_person_rolodex_contact_handle
    ON person_rolodex (ghost_id, contact_handle)
    WHERE contact_handle IS NOT NULL;
