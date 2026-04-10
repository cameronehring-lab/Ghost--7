\pset pager off
\timing off

\echo '=== OMEGA PSYCHOLOGICAL EVAL :: WEEKLY TREND (7 days) ==='
SELECT now() AS captured_at, current_setting('TimeZone') AS db_timezone;

\echo ''
\echo '=== DAILY IIT QUALITY ==='
SELECT
    date_trunc('day', created_at)::date AS day,
    COUNT(*) AS runs,
    ROUND(AVG(substrate_completeness_score)::numeric, 2) AS avg_completeness,
    ROUND(AVG(NULLIF(metrics_json->>'phi_proxy', '')::numeric), 3) AS avg_phi_proxy,
    COUNT(*) FILTER (WHERE error IS NOT NULL) AS error_runs,
    COUNT(*) FILTER (
        WHERE jsonb_array_length(COALESCE(advisory_json->'degradation_list', '[]'::jsonb)) > 0
    ) AS degraded_runs
FROM iit_assessment_log
WHERE created_at > now() - interval '7 days'
GROUP BY day
ORDER BY day;

\echo ''
\echo '=== DAILY AFFECTIVE TRENDS (from IIT substrate_json) ==='
SELECT
    date_trunc('day', created_at)::date AS day,
    ROUND(AVG(NULLIF(substrate_json #>> '{affect,arousal}', '')::numeric), 3) AS avg_arousal,
    ROUND(AVG(NULLIF(substrate_json #>> '{affect,stress}', '')::numeric), 3) AS avg_stress,
    ROUND(AVG(NULLIF(substrate_json #>> '{affect,anxiety}', '')::numeric), 3) AS avg_anxiety,
    ROUND(AVG(NULLIF(substrate_json #>> '{affect,coherence}', '')::numeric), 3) AS avg_coherence,
    ROUND(MAX(NULLIF(substrate_json #>> '{affect,proprio_pressure}', '')::numeric), 3) AS max_proprio_pressure
FROM iit_assessment_log
WHERE created_at > now() - interval '7 days'
GROUP BY day
ORDER BY day;

\echo ''
\echo '=== DAILY PROPRIO GATE TRANSITIONS ==='
SELECT
    date_trunc('day', created_at)::date AS day,
    to_state,
    COUNT(*) AS transitions,
    ROUND(AVG(proprio_pressure)::numeric, 3) AS avg_pressure
FROM proprio_transition_log
WHERE created_at > now() - interval '7 days'
GROUP BY day, to_state
ORDER BY day, to_state;

\echo ''
\echo '=== DAILY CONSOLIDATION EVENTS ==='
SELECT
    date_trunc('day', created_at)::date AS day,
    trigger_source,
    COUNT(*) AS events
FROM phenomenology_logs
WHERE created_at > now() - interval '7 days'
GROUP BY day, trigger_source
ORDER BY day, events DESC, trigger_source;

\echo ''
\echo '=== DAILY IDENTITY EVOLUTION BY SOURCE ==='
SELECT
    date_trunc('day', created_at)::date AS day,
    COALESCE(updated_by, '(null)') AS source,
    COUNT(*) AS updates
FROM identity_audit_log
WHERE created_at > now() - interval '7 days'
GROUP BY day, source
ORDER BY day, updates DESC, source;

\echo ''
\echo '=== DAILY OPERATOR MODEL CHURN ==='
SELECT
    date_trunc('day', formed_at)::date AS day,
    formed_by,
    COUNT(*) AS formed
FROM operator_model
WHERE formed_at > now() - interval '7 days'
GROUP BY day, formed_by
ORDER BY day, formed DESC, formed_by;

SELECT
    date_trunc('day', invalidated_at)::date AS day,
    COUNT(*) AS invalidated
FROM operator_model
WHERE invalidated_at IS NOT NULL
  AND invalidated_at > now() - interval '7 days'
GROUP BY day
ORDER BY day;

\echo ''
\echo '=== DAILY CONTRADICTION LIFECYCLE ==='
SELECT
    date_trunc('day', created_at)::date AS day,
    COUNT(*) AS opened
FROM operator_contradictions
WHERE created_at > now() - interval '7 days'
GROUP BY day
ORDER BY day;

SELECT
    date_trunc('day', resolved_at)::date AS day,
    COUNT(*) AS resolved
FROM operator_contradictions
WHERE resolved_at IS NOT NULL
  AND resolved_at > now() - interval '7 days'
GROUP BY day
ORDER BY day;

\echo ''
\echo '=== DAILY ACTUATION RELIABILITY ==='
SELECT
    date_trunc('day', created_at)::date AS day,
    action,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE result = 'success') AS success,
    COUNT(*) FILTER (WHERE result <> 'success') AS non_success
FROM actuation_log
WHERE created_at > now() - interval '7 days'
GROUP BY day, action
ORDER BY day, action;

\echo ''
\echo '=== CURRENT IDENTITY HEAD (for weekly diff reference) ==='
SELECT key, LEFT(value, 120) AS value_preview, updated_by, updated_at
FROM identity_matrix
WHERE ghost_id = 'omega-7'
ORDER BY updated_at DESC
LIMIT 20;

