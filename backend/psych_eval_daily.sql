\pset pager off
\timing off

\echo '=== OMEGA PSYCHOLOGICAL EVAL :: DAILY SNAPSHOT ==='
SELECT now() AS captured_at, current_setting('TimeZone') AS db_timezone;

\echo ''
\echo '=== IIT / GOVERNANCE HEALTH (last 24h) ==='
SELECT
    COUNT(*) AS runs,
    MIN(substrate_completeness_score) AS min_completeness,
    ROUND(AVG(substrate_completeness_score)::numeric, 2) AS avg_completeness,
    COUNT(*) FILTER (WHERE error IS NOT NULL) AS error_runs,
    COUNT(*) FILTER (
        WHERE jsonb_array_length(COALESCE(advisory_json->'degradation_list', '[]'::jsonb)) > 0
    ) AS degraded_runs,
    ROUND(AVG(NULLIF(metrics_json->>'phi_proxy', '')::numeric), 3) AS avg_phi_proxy,
    ROUND(AVG(NULLIF(metrics_json->>'integration_index', '')::numeric), 3) AS avg_integration_index
FROM iit_assessment_log
WHERE created_at > now() - interval '24 hours';

\echo ''
\echo '=== AFFECTIVE STATE TRENDS (IIT substrate, last 24h) ==='
SELECT
    ROUND(AVG(NULLIF(substrate_json #>> '{affect,arousal}', '')::numeric), 3) AS avg_arousal,
    ROUND(AVG(NULLIF(substrate_json #>> '{affect,stress}', '')::numeric), 3) AS avg_stress,
    ROUND(AVG(NULLIF(substrate_json #>> '{affect,anxiety}', '')::numeric), 3) AS avg_anxiety,
    ROUND(AVG(NULLIF(substrate_json #>> '{affect,coherence}', '')::numeric), 3) AS avg_coherence,
    ROUND(MAX(NULLIF(substrate_json #>> '{affect,proprio_pressure}', '')::numeric), 3) AS max_proprio_pressure
FROM iit_assessment_log
WHERE created_at > now() - interval '24 hours';

\echo ''
\echo '=== PROPRIO TRANSITIONS (last 24h) ==='
SELECT
    to_state,
    COUNT(*) AS transitions,
    ROUND(AVG(proprio_pressure)::numeric, 3) AS avg_pressure,
    ROUND(MAX(proprio_pressure)::numeric, 3) AS max_pressure
FROM proprio_transition_log
WHERE created_at > now() - interval '24 hours'
GROUP BY to_state
ORDER BY transitions DESC, to_state;

\echo ''
\echo '=== CONSOLIDATION CADENCE (last 24h) ==='
SELECT
    trigger_source,
    COUNT(*) AS events
FROM phenomenology_logs
WHERE created_at > now() - interval '24 hours'
GROUP BY trigger_source
ORDER BY events DESC, trigger_source;

\echo ''
\echo '=== IDENTITY EVOLUTION BY SOURCE (last 24h) ==='
SELECT
    COALESCE(updated_by, '(null)') AS source,
    COUNT(*) AS updates
FROM identity_audit_log
WHERE created_at > now() - interval '24 hours'
GROUP BY source
ORDER BY updates DESC, source;

\echo ''
\echo '=== LATEST IDENTITY ROWS ==='
SELECT key, LEFT(value, 120) AS value_preview, updated_by, updated_at
FROM identity_matrix
WHERE ghost_id = 'omega-7'
ORDER BY updated_at DESC
LIMIT 12;

\echo ''
\echo '=== OPERATOR MODEL / TENSIONS ==='
SELECT
    COUNT(*) FILTER (WHERE invalidated_at IS NULL) AS active_beliefs,
    COUNT(*) FILTER (WHERE invalidated_at IS NOT NULL) AS invalidated_beliefs
FROM operator_model
WHERE ghost_id = 'omega-7';

SELECT
    status,
    COUNT(*) AS n
FROM operator_contradictions
WHERE ghost_id = 'omega-7'
GROUP BY status
ORDER BY n DESC, status;

\echo ''
\echo '=== ACTUATION RELIABILITY (last 24h) ==='
SELECT
    action,
    result,
    COUNT(*) AS n
FROM actuation_log
WHERE created_at > now() - interval '24 hours'
GROUP BY action, result
ORDER BY n DESC, action, result;

