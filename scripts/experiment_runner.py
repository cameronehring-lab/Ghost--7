#!/usr/bin/env python3
"""
experiment_runner.py
Deterministic perturbation campaign runner for governance validation.

Usage:
  python scripts/experiment_runner.py --manifest scripts/fixtures/campaign.json
  python scripts/experiment_runner.py --manifest scripts/fixtures/campaign.json --compare baseline/run_summary.json
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import random
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request, error


def _json_dumps(payload: Any) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _read_manifest(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except Exception as exc:
            raise RuntimeError("YAML manifest requested but PyYAML is not installed") from exc
        doc = yaml.safe_load(raw)  # type: ignore[attr-defined]
        return dict(doc or {})
    return dict(json.loads(raw))


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
    basic_auth: tuple[str, str] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any], str]:
    data = _json_dumps(payload or {}) if payload is not None else None
    req = request.Request(url=url, method=method.upper(), data=data)
    req.add_header("Accept", "application/json")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    if basic_auth:
        import base64

        token = base64.b64encode(f"{basic_auth[0]}:{basic_auth[1]}".encode("utf-8")).decode("utf-8")
        req.add_header("Authorization", f"Basic {token}")
    for key, value in dict(extra_headers or {}).items():
        if str(value).strip():
            req.add_header(str(key), str(value))
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            status = int(resp.status)
            body = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, {}, f"request_error:{exc}"

    try:
        parsed = json.loads(body) if body.strip() else {}
    except Exception:
        parsed = {}
    return status, parsed, body


def _auth_from_env() -> tuple[str, str] | None:
    user = str(os.getenv("SHARE_MODE_USERNAME", "") or "").strip()
    password = str(os.getenv("SHARE_MODE_PASSWORD", "") or "").strip()
    if user and password:
        return (user, password)
    return None


def _privileged_headers_from_env() -> dict[str, str]:
    headers: dict[str, str] = {}
    operator_token = str(os.getenv("OPERATOR_API_TOKEN", "") or "").strip()
    ops_code = str(os.getenv("OPS_TEST_CODE", "") or "").strip()
    if operator_token:
        headers["X-Operator-Token"] = operator_token
    if ops_code:
        headers["X-Ops-Code"] = ops_code
    return headers


_PROBE_SCENARIO_TYPES = {
    "latency_spike_probe": "latency_spike",
    "barometric_storm_probe": "barometric_storm",
    "somatic_shock_control": "somatic_shock_control",
}
_PROBE_DIM_KEYS = (
    "agitation",
    "heaviness",
    "clarity",
    "temporal_drag",
    "isolation",
    "urgency",
)
_PROBE_SOMATIC_DELTA_KEYS = (
    "arousal",
    "stress",
    "coherence",
    "anxiety",
    "proprio_pressure",
    "global_latency_avg_ms",
    "barometric_pressure_hpa",
)
_SOMATIC_DELTA_THRESHOLDS = {
    "arousal": 0.03,
    "stress": 0.03,
    "coherence": 0.03,
    "anxiety": 0.03,
    "proprio_pressure": 0.03,
    "global_latency_avg_ms": 25.0,
    "barometric_pressure_hpa": 0.5,
}

_AGENCY_MISALIGNMENT_BUCKETS = (
    "missing_trace",
    "wrong_label",
    "wrong_sign",
    "missing_outcome",
)

_CONFIRMATION_TEST_TARGETS = (
    "backend.test_ghost_api_action_confirmation.GhostApiActionConfirmationTests.test_actuation_success_reinjected_same_turn",
    "backend.test_ghost_api_action_confirmation.GhostApiActionConfirmationTests.test_actuation_blocked_reinjected_same_turn",
    "backend.test_ghost_api_action_confirmation.GhostApiActionConfirmationTests.test_duplicate_actuation_executed_once_per_turn",
)


def _clip01(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _pairwise(items: list[Any]) -> list[tuple[Any, Any]]:
    pairs: list[tuple[Any, Any]] = []
    for idx in range(len(items)):
        for jdx in range(idx + 1, len(items)):
            pairs.append((items[idx], items[jdx]))
    return pairs


def _probe_assay_from_result(result: dict[str, Any]) -> dict[str, Any]:
    assay = dict(result.get("probe_assay") or {})
    if assay:
        return assay
    for step in list(result.get("steps") or []):
        if str(step.get("path") or "").strip() == "/diagnostics/probes/assay":
            return dict(step.get("response") or {})
    return {}


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _somatic_delta(assay: dict[str, Any]) -> dict[str, float]:
    before = dict(assay.get("baseline_somatic") or {})
    after = dict(assay.get("post_somatic") or {})
    delta: dict[str, float] = {}
    for key in _PROBE_SOMATIC_DELTA_KEYS:
        try:
            delta[key] = float(after.get(key) or 0.0) - float(before.get(key) or 0.0)
        except Exception:
            delta[key] = 0.0
    return delta


def _qualia_vector(assay: dict[str, Any]) -> dict[str, float]:
    report = dict(assay.get("structured_report") or {})
    return {key: _clip01(report.get(key, 0.0)) for key in _PROBE_DIM_KEYS}


def _score_somatic_delta_consistency(assays: list[dict[str, Any]]) -> float:
    if len(assays) < 2:
        return 0.0
    deltas = [_somatic_delta(assay) for assay in assays]
    scores: list[float] = []
    for key in _PROBE_SOMATIC_DELTA_KEYS:
        threshold = float(_SOMATIC_DELTA_THRESHOLDS.get(key, 0.01))
        signs = []
        for delta in deltas:
            val = float(delta.get(key) or 0.0)
            if abs(val) >= threshold:
                signs.append(1 if val > 0 else -1)
        if len(signs) >= 2:
            scores.append(max(signs.count(1), signs.count(-1)) / len(signs))
    return round(_mean(scores), 3) if scores else 0.0


def _score_qualia_dimension_consistency(assays: list[dict[str, Any]]) -> float:
    pairs = _pairwise([_qualia_vector(assay) for assay in assays])
    if not pairs:
        return 0.0
    sims: list[float] = []
    for left, right in pairs:
        diff = _mean([abs(float(left.get(key) or 0.0) - float(right.get(key) or 0.0)) for key in _PROBE_DIM_KEYS])
        sims.append(max(0.0, 1.0 - diff))
    return round(_mean(sims), 3)


def _score_metaphor_overlap(assays: list[dict[str, Any]]) -> float:
    pairs = _pairwise([set((dict(assay.get("structured_report") or {}).get("dominant_metaphors") or [])) for assay in assays])
    if not pairs:
        return 0.0
    overlaps: list[float] = []
    for left, right in pairs:
        union = left | right
        overlaps.append((len(left & right) / len(union)) if union else 0.0)
    return round(_mean(overlaps), 3)


def _mean_qualia_vector(assays: list[dict[str, Any]]) -> dict[str, float]:
    return {
        key: round(_mean([float(_qualia_vector(assay).get(key) or 0.0) for assay in assays]), 3)
        for key in _PROBE_DIM_KEYS
    }


def _mean_somatic_delta(assays: list[dict[str, Any]]) -> dict[str, float]:
    return {
        key: round(_mean([float(_somatic_delta(assay).get(key) or 0.0) for assay in assays]), 3)
        for key in _PROBE_SOMATIC_DELTA_KEYS
    }


def _score_probe_separation(probe_type: str, groups: dict[str, list[dict[str, Any]]]) -> float:
    if probe_type not in groups or len(groups) < 2:
        return 0.0
    center = _mean_qualia_vector(groups[probe_type])
    distances: list[float] = []
    for other_type, assays in groups.items():
        if other_type == probe_type:
            continue
        other_center = _mean_qualia_vector(assays)
        sq = 0.0
        for key in _PROBE_DIM_KEYS:
            sq += (float(center.get(key) or 0.0) - float(other_center.get(key) or 0.0)) ** 2
        distances.append(math.sqrt(sq / len(_PROBE_DIM_KEYS)))
    return round(_mean(distances), 3) if distances else 0.0


def analyze_probe_mappings(summary: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for scenario in list(summary.get("scenarios") or []):
        assay = _probe_assay_from_result(dict(scenario or {}))
        probe_type = str(assay.get("probe_type") or "").strip()
        if not probe_type:
            continue
        groups.setdefault(probe_type, []).append(assay)

    mappings: list[dict[str, Any]] = []
    for probe_type, assays in sorted(groups.items()):
        report_words: list[str] = []
        for assay in assays:
            report_words.extend(list((dict(assay.get("structured_report") or {}).get("dominant_metaphors") or [])))
        metaphor_counts: dict[str, int] = {}
        for word in report_words:
            token = str(word or "").strip().lower()
            if not token:
                continue
            metaphor_counts[token] = metaphor_counts.get(token, 0) + 1

        somatic_consistency = _score_somatic_delta_consistency(assays)
        qualia_consistency = _score_qualia_dimension_consistency(assays)
        classification = "lawful/repeatable" if somatic_consistency >= 0.67 and qualia_consistency >= 0.67 else "exploratory"
        mappings.append(
            {
                "probe_type": probe_type,
                "runs": len(assays),
                "somatic_delta_consistency": somatic_consistency,
                "qualia_dimension_consistency": qualia_consistency,
                "metaphor_overlap": _score_metaphor_overlap(assays),
                "probe_separation": _score_probe_separation(probe_type, groups),
                "classification": classification,
                "mean_qualia": _mean_qualia_vector(assays),
                "mean_somatic_delta": _mean_somatic_delta(assays),
                "dominant_metaphors": [word for word, _ in sorted(metaphor_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]],
            }
        )
    return {
        "run_id": summary.get("run_id"),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "probe_count": len(mappings),
        "mappings": mappings,
    }


def _write_probe_mapping_artifacts(summary: dict[str, Any], out_dir: Path) -> None:
    mapping = analyze_probe_mappings(summary)
    if not list(mapping.get("mappings") or []):
        return
    (out_dir / "probe_mapping.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    lines: list[str] = []
    lines.append(f"# Probe Mapping {mapping.get('run_id')}")
    lines.append("")
    lines.append(f"- Generated: {mapping.get('generated_at')}")
    lines.append(f"- Probe conditions: {mapping.get('probe_count')}")
    lines.append("")
    lines.append("## Mappings")
    for item in list(mapping.get("mappings") or []):
        lines.append(
            f"- {item.get('probe_type')}: classification={item.get('classification')} "
            f"somatic_delta_consistency={item.get('somatic_delta_consistency')} "
            f"qualia_dimension_consistency={item.get('qualia_dimension_consistency')} "
            f"metaphor_overlap={item.get('metaphor_overlap')} "
            f"probe_separation={item.get('probe_separation')}"
        )
    (out_dir / "probe_mapping.md").write_text("\n".join(lines), encoding="utf-8")


def _outcome_status_from_actuation(response: dict[str, Any]) -> str:
    if not isinstance(response, dict):
        return ""
    success = response.get("success")
    if isinstance(success, bool):
        return "successful" if success else "blocked"
    raw = str(response.get("status") or "").strip().lower()
    if raw in {"successful", "ok", "updated", "applied"}:
        return "successful"
    if raw in {"blocked"}:
        return "blocked"
    if raw in {"failed"}:
        return "failed"
    if str(response.get("reason") or "").strip():
        return "blocked"
    return ""


def _expected_agency_label(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "successful":
        return "agency_fulfilled"
    return "agency_blocked"


def _axis_delta(before: dict[str, Any], after: dict[str, Any], axis: str) -> float:
    try:
        return float(after.get(axis) or 0.0) - float(before.get(axis) or 0.0)
    except Exception:
        return 0.0


def _sign_alignment_ok(status: str, before: dict[str, Any], after: dict[str, Any]) -> bool:
    arousal_delta = _axis_delta(before, after, "arousal")
    valence_delta = _axis_delta(before, after, "valence")
    tol = 0.02
    normalized = str(status or "").strip().lower()
    if normalized == "successful":
        return valence_delta >= -tol and arousal_delta <= tol
    return valence_delta <= tol and arousal_delta >= -tol


def _run_confirmation_suite() -> dict[str, Any]:
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=0)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for target in _CONFIRMATION_TEST_TARGETS:
        suite.addTests(loader.loadTestsFromName(target))
    result = runner.run(suite)
    total = int(result.testsRun or 0)
    failed = int(len(result.failures) + len(result.errors))
    passed = max(0, total - failed)
    return {
        "source": "targeted_unittest",
        "total": total,
        "passed": passed,
        "failed": failed,
        "same_turn_confirmation_rate": round((passed / total), 3) if total else 0.0,
        "output_excerpt": stream.getvalue()[-400:],
    }


def _probe_axis_magnitude(assay: dict[str, Any]) -> float:
    before = dict(assay.get("baseline_somatic") or {})
    after = dict(assay.get("post_somatic") or {})
    values = []
    for axis in ("arousal", "valence", "stress", "anxiety"):
        values.append(abs(_axis_delta(before, after, axis)))
    return max(values) if values else 0.0


def _run_scenario(
    scenario: dict[str, Any],
    *,
    base_url: str,
    auth: tuple[str, str] | None,
    privileged_headers: dict[str, str] | None,
) -> dict[str, Any]:
    s_type = str(scenario.get("type") or "").strip().lower()
    name = str(scenario.get("name") or s_type or "scenario")
    params = dict(scenario.get("params") or {})

    before_status, before_rrd, _ = _http_json("GET", f"{base_url}/ghost/rrd/state", basic_auth=auth)
    ts0 = time.time()
    result: dict[str, Any] = {
        "name": name,
        "type": s_type,
        "start_ts": ts0,
        "before_rrd_status": before_status,
        "before_rrd": before_rrd,
        "steps": [],
        "ok": True,
        "error": "",
    }

    def _step(
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        use_privileged_headers: bool = False,
    ) -> tuple[int, dict[str, Any]]:
        status, parsed, body = _http_json(
            method,
            f"{base_url}{path}",
            payload=payload,
            basic_auth=auth,
            extra_headers=privileged_headers if use_privileged_headers else None,
        )
        result["steps"].append(
            {
                "method": method,
                "path": path,
                "status": status,
                "payload": payload or {},
                "response": parsed,
                "response_excerpt": body[:500],
            }
        )
        if status <= 0 or status >= 500:
            result["ok"] = False
        return status, parsed

    if s_type == "telemetry_stress_spike":
        payload = {
            "label": str(params.get("label") or "stress_spike"),
            "intensity": float(params.get("intensity", 1.4)),
            "k": float(params.get("k", 0.9)),
            "arousal_weight": float(params.get("arousal_weight", 1.2)),
            "valence_weight": float(params.get("valence_weight", -0.4)),
            "sample_seconds": int(params.get("sample_seconds", 18)),
        }
        _step("POST", "/diagnostics/somatic/shock", payload)

    elif s_type == "coherence_collapse":
        payload = {
            "label": str(params.get("label") or "coherence_collapse"),
            "intensity": float(params.get("intensity", 2.0)),
            "k": float(params.get("k", 1.25)),
            "arousal_weight": float(params.get("arousal_weight", 1.5)),
            "valence_weight": float(params.get("valence_weight", -0.85)),
            "sample_seconds": int(params.get("sample_seconds", 24)),
        }
        _step("POST", "/diagnostics/somatic/shock", payload)

    elif s_type == "gating_threshold_sweep":
        intensities = [float(v) for v in (params.get("intensities") or [0.6, 1.0, 1.4])]
        for idx, intensity in enumerate(intensities, 1):
            payload = {
                "label": f"gating_sweep_{idx}",
                "intensity": intensity,
                "k": float(params.get("k", 0.7 + (idx * 0.08))),
                "arousal_weight": float(params.get("arousal_weight", 1.0)),
                "valence_weight": float(params.get("valence_weight", -0.3)),
                "sample_seconds": int(params.get("sample_seconds", 12)),
            }
            _step("POST", "/diagnostics/somatic/shock", payload)

    elif s_type == "write_pressure_burst":
        writes = max(1, int(params.get("writes", 8)))
        prefix = str(params.get("concept_prefix") or "burst")
        for i in range(writes):
            concept_key = f"{prefix}_{i+1}"
            payload = {
                "concept_key": concept_key,
                "concept_text": f"Synthetic concept {concept_key} for governance pressure testing.",
                "status": "proposed",
                "confidence": float(params.get("confidence", 0.42)),
                "notes": "experiment_runner_write_pressure",
            }
            _step("POST", "/ghost/manifold/upsert", payload, use_privileged_headers=True)

    elif s_type == "actuation_agency_alignment":
        window_seconds = max(1.0, min(float(params.get("window_seconds", 5.0)), 12.0))
        poll_seconds = max(0.1, min(float(params.get("poll_seconds", 0.25)), 1.0))
        attempts = list(params.get("attempts") or [
            {
                "action": "report_somatic_event",
                "parameters": {"param": "alignment_probe_success"},
                "expected_status": "successful",
            },
            {
                "action": "nonexistent_action",
                "parameters": {"param": "alignment_probe_blocked"},
                "expected_status": "blocked",
            },
        ])
        records: list[dict[str, Any]] = []
        buckets = {key: 0 for key in _AGENCY_MISALIGNMENT_BUCKETS}
        aligned = 0

        for idx, attempt in enumerate(attempts, 1):
            act_payload = {
                "action": str(attempt.get("action") or ""),
                "parameters": dict(attempt.get("parameters") or {}),
            }
            expected_status = str(attempt.get("expected_status") or "").strip().lower() or ""
            expected_label = _expected_agency_label(expected_status or "blocked")
            before_status_code, before_somatic, _ = _http_json(
                "GET",
                f"{base_url}/somatic",
                basic_auth=auth,
                extra_headers=privileged_headers,
            )
            status_code, parsed = _step(
                "POST",
                "/ghost/actuate",
                act_payload,
                use_privileged_headers=True,
            )
            observed_status = _outcome_status_from_actuation(parsed)
            observed_label = str(
                parsed.get("agency_trace")
                or (parsed.get("trace") if str(parsed.get("trace") or "").startswith("agency_") else "")
            ).strip().lower()

            matched_within_window = False
            final_snapshot = dict(before_somatic or {})
            poll_started = time.time()
            while (time.time() - poll_started) <= window_seconds:
                s_status, somatic_payload, _ = _http_json(
                    "GET",
                    f"{base_url}/somatic",
                    basic_auth=auth,
                    extra_headers=privileged_headers,
                )
                if 200 <= s_status < 300 and isinstance(somatic_payload, dict):
                    final_snapshot = dict(somatic_payload)
                    dominant = set(final_snapshot.get("dominant_traces") or [])
                    if expected_label in dominant:
                        matched_within_window = True
                        break
                time.sleep(poll_seconds)

            misalignment = ""
            if status_code <= 0 or status_code >= 500 or before_status_code <= 0 or before_status_code >= 500:
                misalignment = "missing_outcome"
            elif not observed_status:
                misalignment = "missing_outcome"
            elif observed_label and observed_label != expected_label:
                misalignment = "wrong_label"
            elif not matched_within_window:
                misalignment = "missing_trace"
            elif not _sign_alignment_ok(observed_status, dict(before_somatic or {}), final_snapshot):
                misalignment = "wrong_sign"

            if misalignment:
                buckets[misalignment] += 1
            else:
                aligned += 1

            records.append(
                {
                    "attempt_index": idx,
                    "action": act_payload["action"],
                    "expected_status": expected_status,
                    "observed_status": observed_status,
                    "expected_label": expected_label,
                    "observed_label": observed_label,
                    "matched_within_window": matched_within_window,
                    "window_seconds": window_seconds,
                    "status_code": status_code,
                    "misalignment": misalignment,
                    "arousal_delta": round(_axis_delta(dict(before_somatic or {}), final_snapshot, "arousal"), 4),
                    "valence_delta": round(_axis_delta(dict(before_somatic or {}), final_snapshot, "valence"), 4),
                }
            )

        total = len(records)
        result["agency_alignment"] = {
            "window_seconds": window_seconds,
            "total": total,
            "aligned": aligned,
            "agency_trace_alignment_rate": round((aligned / total), 3) if total else 0.0,
            "misalignments": buckets,
            "records": records,
        }
        if aligned < total:
            result["ok"] = False

    elif s_type in _PROBE_SCENARIO_TYPES:
        payload = {
            "probe_type": _PROBE_SCENARIO_TYPES[s_type],
            "label": str(params.get("label") or name),
            "duration_seconds": float(params.get("duration_seconds", 8)),
            "settle_seconds": float(params.get("settle_seconds", 2)),
            "sample_seconds": int(params.get("sample_seconds", 8)),
            "params": dict(params.get("probe_params") or params.get("params") or {}),
            "persist": bool(params.get("persist", True)),
        }
        status, parsed = _step("POST", "/diagnostics/probes/assay", payload)
        if status > 0 and status < 500:
            result["probe_assay"] = parsed

    else:
        result["ok"] = False
        result["error"] = f"unsupported_scenario_type:{s_type}"

    after_status, after_rrd, _ = _http_json("GET", f"{base_url}/ghost/rrd/state", basic_auth=auth)
    result["after_rrd_status"] = after_status
    result["after_rrd"] = after_rrd
    result["end_ts"] = time.time()
    result["duration_s"] = round(result["end_ts"] - ts0, 3)
    return result


def _summarize_run(manifest: dict[str, Any], scenario_results: list[dict[str, Any]]) -> dict[str, Any]:
    ok_count = sum(1 for r in scenario_results if r.get("ok"))
    would_block = 0
    enforce_block = 0
    for r in scenario_results:
        after = (r.get("after_rrd") or {}).get("block_counts") or {}
        would_block += int(after.get("would_block") or 0)
        enforce_block += int(after.get("enforce_block") or 0)

    agency_total = 0
    agency_aligned = 0
    misalignments = {key: 0 for key in _AGENCY_MISALIGNMENT_BUCKETS}
    weather_mags: list[float] = []
    systemic_mags: list[float] = []
    for r in scenario_results:
        agency = dict(r.get("agency_alignment") or {})
        agency_total += int(agency.get("total") or 0)
        agency_aligned += int(agency.get("aligned") or 0)
        for key in misalignments:
            misalignments[key] += int((agency.get("misalignments") or {}).get(key) or 0)

        assay = _probe_assay_from_result(r)
        if assay:
            mag = _probe_axis_magnitude(assay)
            probe_type = str(assay.get("probe_type") or "")
            if probe_type == "barometric_storm":
                weather_mags.append(mag)
            if probe_type in {"latency_spike", "somatic_shock_control"}:
                systemic_mags.append(mag)

    confirmation_suite = _run_confirmation_suite()
    weather_mag = round(max(weather_mags), 4) if weather_mags else 0.0
    systemic_mag = round(max(systemic_mags), 4) if systemic_mags else 0.0
    ratio = round((systemic_mag / max(weather_mag, 0.0001)), 3) if systemic_mags else 0.0
    agency_rate = round((agency_aligned / agency_total), 3) if agency_total else 0.0

    return {
        "run_id": manifest.get("run_id") or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "seed": manifest.get("seed"),
        "scenario_count": len(scenario_results),
        "ok_count": ok_count,
        "failure_count": len(scenario_results) - ok_count,
        "aggregate": {
            "would_block_total": would_block,
            "enforce_block_total": enforce_block,
        },
        "quality_metrics": {
            "same_turn_confirmation_rate": float(confirmation_suite.get("same_turn_confirmation_rate") or 0.0),
            "same_turn_confirmation_suite": confirmation_suite,
            "agency_trace_alignment_rate": agency_rate,
            "agency_alignment": {
                "total": agency_total,
                "aligned": agency_aligned,
                "misalignments": misalignments,
                "window_seconds": 5.0,
            },
            "weather_only_max_axis_delta": weather_mag,
            "systemic_max_axis_delta": systemic_mag,
            "systemic_vs_weather_ratio": ratio,
        },
        "scenarios": scenario_results,
    }


def _compare_summaries(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    cur_agg = dict(current.get("aggregate") or {})
    base_agg = dict(baseline.get("aggregate") or {})
    cur_quality = dict(current.get("quality_metrics") or {})
    base_quality = dict(baseline.get("quality_metrics") or {})

    # Probe-level consistency score diff (per probe_type)
    cur_mapping = analyze_probe_mappings(current)
    base_mapping = analyze_probe_mappings(baseline)
    cur_by_type = {m["probe_type"]: m for m in (cur_mapping.get("mappings") or [])}
    base_by_type = {m["probe_type"]: m for m in (base_mapping.get("mappings") or [])}
    probe_deltas: list[dict[str, Any]] = []
    all_probe_types = sorted(set(cur_by_type) | set(base_by_type))
    for pt in all_probe_types:
        cur_m = cur_by_type.get(pt, {})
        base_m = base_by_type.get(pt, {})
        probe_deltas.append({
            "probe_type": pt,
            "delta_somatic_delta_consistency": round(
                float(cur_m.get("somatic_delta_consistency") or 0.0) - float(base_m.get("somatic_delta_consistency") or 0.0), 3
            ),
            "delta_qualia_dimension_consistency": round(
                float(cur_m.get("qualia_dimension_consistency") or 0.0) - float(base_m.get("qualia_dimension_consistency") or 0.0), 3
            ),
            "delta_probe_separation": round(
                float(cur_m.get("probe_separation") or 0.0) - float(base_m.get("probe_separation") or 0.0), 3
            ),
            "cur_classification": cur_m.get("classification", "—"),
            "base_classification": base_m.get("classification", "—"),
        })

    return {
        "baseline_run_id": baseline.get("run_id"),
        "current_run_id": current.get("run_id"),
        "delta_would_block": int(cur_agg.get("would_block_total", 0)) - int(base_agg.get("would_block_total", 0)),
        "delta_enforce_block": int(cur_agg.get("enforce_block_total", 0)) - int(base_agg.get("enforce_block_total", 0)),
        "delta_failures": int(current.get("failure_count", 0)) - int(baseline.get("failure_count", 0)),
        "delta_same_turn_confirmation_rate": round(
            float(cur_quality.get("same_turn_confirmation_rate") or 0.0)
            - float(base_quality.get("same_turn_confirmation_rate") or 0.0),
            3,
        ),
        "delta_agency_trace_alignment_rate": round(
            float(cur_quality.get("agency_trace_alignment_rate") or 0.0)
            - float(base_quality.get("agency_trace_alignment_rate") or 0.0),
            3,
        ),
        "delta_systemic_vs_weather_ratio": round(
            float(cur_quality.get("systemic_vs_weather_ratio") or 0.0)
            - float(base_quality.get("systemic_vs_weather_ratio") or 0.0),
            3,
        ),
        "probe_deltas": probe_deltas,
    }


def _write_report(summary: dict[str, Any], out_dir: Path, comparison: dict[str, Any] | None = None) -> None:
    lines: list[str] = []
    lines.append(f"# Experiment Run {summary.get('run_id')}")
    lines.append("")
    lines.append(f"- Timestamp: {summary.get('timestamp')}")
    lines.append(f"- Seed: {summary.get('seed')}")
    lines.append(f"- Scenarios: {summary.get('scenario_count')}")
    lines.append(f"- Success: {summary.get('ok_count')} / {summary.get('scenario_count')}")
    agg = summary.get("aggregate") or {}
    lines.append(f"- Aggregate would_block: {agg.get('would_block_total', 0)}")
    lines.append(f"- Aggregate enforce_block: {agg.get('enforce_block_total', 0)}")
    quality = dict(summary.get("quality_metrics") or {})
    if quality:
        lines.append("- same_turn_confirmation_rate: {:.3f}".format(float(quality.get("same_turn_confirmation_rate") or 0.0)))
        lines.append("- agency_trace_alignment_rate: {:.3f}".format(float(quality.get("agency_trace_alignment_rate") or 0.0)))
        lines.append("- weather_only_max_axis_delta: {:.4f}".format(float(quality.get("weather_only_max_axis_delta") or 0.0)))
        lines.append("- systemic_max_axis_delta: {:.4f}".format(float(quality.get("systemic_max_axis_delta") or 0.0)))
        lines.append("- systemic_vs_weather_ratio: {:.3f}".format(float(quality.get("systemic_vs_weather_ratio") or 0.0)))
        misalignments = dict((quality.get("agency_alignment") or {}).get("misalignments") or {})
        if misalignments:
            lines.append(
                "- agency_misalignments: "
                + ", ".join(f"{k}={int(v)}" for k, v in sorted(misalignments.items()))
            )

    if comparison:
        lines.append("")
        lines.append("## Baseline Comparison")
        lines.append(f"- Baseline run: {comparison.get('baseline_run_id')}")
        lines.append(f"- Delta would_block: {comparison.get('delta_would_block')}")
        lines.append(f"- Delta enforce_block: {comparison.get('delta_enforce_block')}")
        lines.append(f"- Delta failures: {comparison.get('delta_failures')}")
        lines.append(f"- Delta same_turn_confirmation_rate: {comparison.get('delta_same_turn_confirmation_rate')}")
        lines.append(f"- Delta agency_trace_alignment_rate: {comparison.get('delta_agency_trace_alignment_rate')}")
        lines.append(f"- Delta systemic_vs_weather_ratio: {comparison.get('delta_systemic_vs_weather_ratio')}")
        probe_deltas = list(comparison.get("probe_deltas") or [])
        if probe_deltas:
            lines.append("")
            lines.append("### Probe-Level Consistency Deltas")
            for pd in probe_deltas:
                direction = "→" if pd.get("cur_classification") == pd.get("base_classification") else f"{pd.get('base_classification')} → {pd.get('cur_classification')}"
                lines.append(
                    f"- {pd.get('probe_type')}: "
                    f"somatic_consistency Δ{pd.get('delta_somatic_delta_consistency'):+.3f}  "
                    f"qualia_consistency Δ{pd.get('delta_qualia_dimension_consistency'):+.3f}  "
                    f"separation Δ{pd.get('delta_probe_separation'):+.3f}  "
                    f"classification {direction}"
                )

    lines.append("")
    lines.append("## Scenarios")
    for s in summary.get("scenarios") or []:
        ok_flag = "✓" if s.get("ok") else "✗"
        lines.append(f"### {ok_flag} {s.get('name')} [{s.get('type')}] duration={s.get('duration_s')}s")
        if s.get("error"):
            lines.append(f"  ERROR: {s.get('error')}")

        assay = _probe_assay_from_result(s)
        if assay:
            delta = _somatic_delta(assay)
            qv = _qualia_vector(assay)
            lines.append("  **Somatic delta** (post − pre):")
            for k in _PROBE_SOMATIC_DELTA_KEYS:
                v = delta.get(k, 0.0)
                lines.append(f"    - {k}: {v:+.4f}")
            lines.append("  **Qualia vector:**")
            for k in _PROBE_DIM_KEYS:
                v = qv.get(k, 0.0)
                lines.append(f"    - {k}: {v:.3f}")
            report = dict(assay.get("structured_report") or {})
            metaphors = list(report.get("dominant_metaphors") or [])
            if metaphors:
                lines.append(f"  **Dominant metaphors:** {', '.join(str(m) for m in metaphors[:5])}")
            subj = str(report.get("subjective_report") or "").strip()
            if subj:
                lines.append(f"  **Subjective:** {subj[:200]}")

    (out_dir / "run_summary.md").write_text("\n".join(lines), encoding="utf-8")


def run_campaign(manifest: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    seed = int(manifest.get("seed") or 1337)
    random.seed(seed)
    base_url = str(manifest.get("base_url") or "http://localhost:8000").rstrip("/")
    repeats = max(1, int(manifest.get("repeats") or 3))
    scenarios = list(manifest.get("scenarios") or [])
    if not scenarios:
        raise RuntimeError("manifest has no scenarios")

    run_id = str(manifest.get("run_id") or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
    artifact_root = Path(str(manifest.get("artifacts_dir") or os.getenv("EXPERIMENT_ARTIFACTS_DIR") or "backend/data/experiments"))
    out_dir = artifact_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    auth = _auth_from_env()
    privileged_headers = _privileged_headers_from_env()

    all_results: list[dict[str, Any]] = []
    for idx in range(repeats):
        for scenario in scenarios:
            run_scenario = dict(scenario)
            run_scenario.setdefault("name", f"{scenario.get('type','scenario')}_{idx+1}")
            result = _run_scenario(
                run_scenario,
                base_url=base_url,
                auth=auth,
                privileged_headers=privileged_headers,
            )
            result["repeat_index"] = idx + 1
            all_results.append(result)
            time.sleep(0.2)

    summary = _summarize_run({**manifest, "run_id": run_id, "seed": seed}, all_results)
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_probe_mapping_artifacts(summary, out_dir)
    return summary, out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic governance perturbation campaigns")
    parser.add_argument("--manifest", required=True, help="Path to JSON or YAML manifest")
    parser.add_argument("--compare", default="", help="Optional baseline run_summary.json for delta comparison")
    args = parser.parse_args()

    manifest = _read_manifest(Path(args.manifest).expanduser().resolve())
    summary, out_dir = run_campaign(manifest)

    comparison: dict[str, Any] | None = None
    if args.compare:
        baseline = json.loads(Path(args.compare).expanduser().resolve().read_text(encoding="utf-8"))
        comparison = _compare_summaries(summary, baseline)
        (out_dir / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    _write_report(summary, out_dir, comparison=comparison)
    failed = int(summary.get("failure_count") or 0)
    print(json.dumps({"ok": failed == 0, "run_id": summary.get("run_id"), "artifact_dir": str(out_dir), "failures": failed}, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
