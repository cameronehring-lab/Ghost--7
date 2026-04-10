-- ==========================================================================
-- OMEGA 4 / Ghost — Identity Matrix Allowlist Guard
-- File: init/migrations/003f_identity_matrix_allowlist_guard.sql
--
-- Prevent process_consolidation from writing outside approved keyspace.
-- Safe to run multiple times.
-- Run: psql "$DATABASE_URL" -f init/migrations/003f_identity_matrix_allowlist_guard.sql
-- ==========================================================================

CREATE OR REPLACE FUNCTION enforce_identity_matrix_allowlist()
RETURNS TRIGGER AS $$
DECLARE
    allowed_keys TEXT[] := ARRAY[
        'self_model', 'philosophical_stance', 'communication_preference',
        'communication_style', 'conceptual_frameworks', 'current_interests',
        'learned_preferences', 'unresolved_questions', 'speech_style_constraints',
        'understanding_of_operator', 'latest_dream_synthesis'
    ];
BEGIN
    IF NEW.updated_by = 'process_consolidation'
       AND NOT (NEW.key = ANY(allowed_keys)) THEN
        RAISE EXCEPTION
            'Identity write blocked: key % not in allowlist for process_consolidation',
            NEW.key;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS identity_matrix_allowlist_guard ON identity_matrix;
CREATE TRIGGER identity_matrix_allowlist_guard
    BEFORE INSERT OR UPDATE ON identity_matrix
    FOR EACH ROW EXECUTE FUNCTION enforce_identity_matrix_allowlist();

DO $$
BEGIN
    RAISE NOTICE 'Migration 003f_identity_matrix_allowlist_guard: OK';
END $$;
