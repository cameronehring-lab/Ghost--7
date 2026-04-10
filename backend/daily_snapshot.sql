-- OMEGA PROTOCOL - Day 0 Baseline Snapshot
-- Objective: Record the state of Ghost ω-7's relational model as the 7-day observation window begins.

\echo '=== IDENTITY MATRIX (Core Self-Model) ==='
SELECT key, left(value, 80) as value_preview, updated_by, updated_at 
FROM identity_matrix 
ORDER BY updated_at DESC;

\echo '\n=== OPERATOR MODEL (Active Beliefs about Cameron) ==='
SELECT dimension, belief, confidence, evidence_count, formed_at 
FROM operator_model 
WHERE invalidated_at IS NULL 
ORDER BY confidence DESC;

\echo '\n=== OPEN TENSIONS (Unresolved Contradictions) ==='
SELECT dimension, observed_event, tension_score, created_at 
FROM operator_contradictions 
WHERE status = 'open' 
ORDER BY tension_score DESC;

\echo '\n=== SESSION SUMMARY (Last 5 Sessions) ==='
SELECT id, started_at, ended_at, left(summary, 60) as summary 
FROM sessions 
ORDER BY started_at DESC 
LIMIT 5;

\echo '\n=== SYSTEM STATE (Recent Evolution Events) ==='
SELECT trigger_source, left(subjective_report, 100) as event 
FROM phenomenology_logs 
ORDER BY created_at DESC 
LIMIT 10;
