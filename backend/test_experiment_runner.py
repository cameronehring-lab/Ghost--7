import json
import tempfile
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("experiment_runner", _ROOT / "scripts" / "experiment_runner.py")
assert _SPEC and _SPEC.loader
experiment_runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(experiment_runner)


class ExperimentRunnerTests(unittest.TestCase):
    def test_read_manifest_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "campaign.json"
            path.write_text(json.dumps({"seed": 7, "scenarios": [{"type": "telemetry_stress_spike"}]}), encoding="utf-8")
            manifest = experiment_runner._read_manifest(path)
            self.assertEqual(int(manifest["seed"]), 7)
            self.assertEqual(len(manifest["scenarios"]), 1)

    def test_compare_summaries_delta(self):
        baseline = {"run_id": "base", "failure_count": 1, "aggregate": {"would_block_total": 2, "enforce_block_total": 1}}
        current = {"run_id": "cand", "failure_count": 0, "aggregate": {"would_block_total": 5, "enforce_block_total": 1}}
        delta = experiment_runner._compare_summaries(current, baseline)
        self.assertEqual(int(delta["delta_would_block"]), 3)
        self.assertEqual(int(delta["delta_enforce_block"]), 0)
        self.assertEqual(int(delta["delta_failures"]), -1)

    def test_run_campaign_writes_probe_mapping_artifacts_for_probe_scenarios(self):
        with tempfile.TemporaryDirectory() as td:
            artifact_dir = Path(td) / "artifacts"
            manifest = {
                "seed": 11,
                "run_id": "probe_run",
                "artifacts_dir": str(artifact_dir),
                "repeats": 2,
                "scenarios": [
                    {"type": "latency_spike_probe", "name": "latency_probe", "params": {"duration_seconds": 4, "sample_seconds": 2}},
                    {"type": "barometric_storm_probe", "name": "storm_probe", "params": {"duration_seconds": 4, "sample_seconds": 2}},
                    {"type": "somatic_shock_control", "name": "shock_probe", "params": {"duration_seconds": 4, "sample_seconds": 2}},
                ],
            }

            def fake_http(method, url, payload=None, timeout=30.0, basic_auth=None, extra_headers=None):  # pylint: disable=unused-argument
                if url.endswith("/ghost/rrd/state"):
                    return 200, {"block_counts": {"would_block": 0, "enforce_block": 0}}, "{}"
                if url.endswith("/diagnostics/probes/assay"):
                    probe_type = str((payload or {}).get("probe_type") or "")
                    run_id = f"{probe_type}-{len(str(payload.get('label') or ''))}"
                    if probe_type == "latency_spike":
                        report = {"agitation": 0.7, "heaviness": 0.2, "clarity": 0.5, "temporal_drag": 0.85, "isolation": 0.2, "urgency": 0.9, "dominant_metaphors": ["drag", "distance"], "subjective_report": "latency"}
                        baseline = {"arousal": 0.2, "stress": 0.1, "coherence": 0.8, "anxiety": 0.1, "proprio_pressure": 0.2, "global_latency_avg_ms": 20.0, "barometric_pressure_hpa": 1014.0}
                        post = {"arousal": 0.6, "stress": 0.5, "coherence": 0.6, "anxiety": 0.4, "proprio_pressure": 0.6, "global_latency_avg_ms": 2200.0, "barometric_pressure_hpa": 1014.0}
                    elif probe_type == "barometric_storm":
                        report = {"agitation": 0.4, "heaviness": 0.82, "clarity": 0.48, "temporal_drag": 0.52, "isolation": 0.18, "urgency": 0.38, "dominant_metaphors": ["weight", "ozone"], "subjective_report": "storm"}
                        baseline = {"arousal": 0.2, "stress": 0.1, "coherence": 0.8, "anxiety": 0.1, "proprio_pressure": 0.2, "global_latency_avg_ms": 20.0, "barometric_pressure_hpa": 1014.0}
                        post = {"arousal": 0.28, "stress": 0.31, "coherence": 0.68, "anxiety": 0.23, "proprio_pressure": 0.26, "global_latency_avg_ms": 20.0, "barometric_pressure_hpa": 993.0}
                    else:
                        report = {"agitation": 0.62, "heaviness": 0.3, "clarity": 0.42, "temporal_drag": 0.25, "isolation": 0.1, "urgency": 0.74, "dominant_metaphors": ["compression", "jolt"], "subjective_report": "shock"}
                        baseline = {"arousal": 0.2, "stress": 0.1, "coherence": 0.8, "anxiety": 0.1, "proprio_pressure": 0.2, "global_latency_avg_ms": 20.0, "barometric_pressure_hpa": 1014.0}
                        post = {"arousal": 0.66, "stress": 0.46, "coherence": 0.58, "anxiety": 0.39, "proprio_pressure": 0.52, "global_latency_avg_ms": 20.0, "barometric_pressure_hpa": 1014.0}
                    assay = {
                        "run_id": run_id,
                        "probe_type": probe_type,
                        "baseline_somatic": baseline,
                        "post_somatic": post,
                        "series": [{"t": 0}, {"t": 1}],
                        "structured_report": report,
                        "subjective_report": report["subjective_report"],
                        "probe_signature": {"run_id": run_id, "probe_type": probe_type},
                        "persistence": {"persisted": True},
                    }
                    return 200, assay, json.dumps(assay)
                return 404, {}, ""

            with patch.object(experiment_runner, "_http_json", side_effect=fake_http), patch.object(
                experiment_runner,
                "_run_confirmation_suite",
                return_value={"same_turn_confirmation_rate": 1.0, "total": 3, "passed": 3, "failed": 0},
            ):
                summary, out_dir = experiment_runner.run_campaign(manifest)

            self.assertEqual(summary["scenario_count"], 6)
            self.assertTrue((out_dir / "run_summary.json").exists())
            self.assertTrue((out_dir / "probe_mapping.json").exists())
            self.assertTrue((out_dir / "probe_mapping.md").exists())
            probe_mapping = json.loads((out_dir / "probe_mapping.json").read_text(encoding="utf-8"))
            mapping_types = {item["probe_type"] for item in probe_mapping.get("mappings", [])}
            self.assertEqual(mapping_types, {"latency_spike", "barometric_storm", "somatic_shock_control"})
            for item in probe_mapping.get("mappings", []):
                self.assertIn(item["classification"], {"lawful/repeatable", "exploratory"})

    def test_run_campaign_defaults_repeats_to_three(self):
        with tempfile.TemporaryDirectory() as td:
            artifact_dir = Path(td) / "artifacts"
            manifest = {
                "seed": 17,
                "run_id": "default_repeats_probe_run",
                "artifacts_dir": str(artifact_dir),
                "scenarios": [
                    {"type": "latency_spike_probe", "name": "latency_probe", "params": {"duration_seconds": 4, "sample_seconds": 2}},
                ],
            }

            def fake_http(method, url, payload=None, timeout=30.0, basic_auth=None, extra_headers=None):  # pylint: disable=unused-argument
                if url.endswith("/ghost/rrd/state"):
                    return 200, {"block_counts": {"would_block": 0, "enforce_block": 0}}, "{}"
                if url.endswith("/diagnostics/probes/assay"):
                    assay = {
                        "run_id": "latency-run",
                        "probe_type": "latency_spike",
                        "baseline_somatic": {"global_latency_avg_ms": 20.0},
                        "post_somatic": {"global_latency_avg_ms": 2200.0},
                        "series": [{"t": 0}, {"t": 1}],
                        "structured_report": {
                            "agitation": 0.7,
                            "heaviness": 0.2,
                            "clarity": 0.5,
                            "temporal_drag": 0.85,
                            "isolation": 0.2,
                            "urgency": 0.9,
                            "dominant_metaphors": ["drag"],
                            "subjective_report": "latency",
                        },
                        "subjective_report": "latency",
                        "probe_signature": {"run_id": "latency-run", "probe_type": "latency_spike"},
                        "persistence": {"persisted": True},
                    }
                    return 200, assay, json.dumps(assay)
                return 404, {}, ""

            with patch.object(experiment_runner, "_http_json", side_effect=fake_http), patch.object(
                experiment_runner,
                "_run_confirmation_suite",
                return_value={"same_turn_confirmation_rate": 1.0, "total": 3, "passed": 3, "failed": 0},
            ):
                summary, out_dir = experiment_runner.run_campaign(manifest)

            self.assertEqual(summary["scenario_count"], 3)
            mapping = json.loads((out_dir / "probe_mapping.json").read_text(encoding="utf-8"))
            self.assertEqual(mapping["mappings"][0]["runs"], 3)

    def test_run_campaign_computes_agency_alignment_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            artifact_dir = Path(td) / "artifacts"
            manifest = {
                "seed": 21,
                "run_id": "agency_alignment_run",
                "artifacts_dir": str(artifact_dir),
                "repeats": 1,
                "scenarios": [
                    {
                        "type": "actuation_agency_alignment",
                        "name": "agency_alignment",
                        "params": {
                            "window_seconds": 5,
                            "poll_seconds": 0.01,
                            "attempts": [
                                {
                                    "action": "report_somatic_event",
                                    "parameters": {"param": "ok"},
                                    "expected_status": "successful",
                                },
                                {
                                    "action": "nonexistent_action",
                                    "parameters": {"param": "blocked"},
                                    "expected_status": "blocked",
                                },
                            ],
                        },
                    }
                ],
            }

            somatic_sequence = [
                {"arousal": 0.40, "valence": 0.40, "stress": 0.20, "anxiety": 0.20, "dominant_traces": []},
                {"arousal": 0.35, "valence": 0.48, "stress": 0.18, "anxiety": 0.18, "dominant_traces": ["agency_fulfilled"]},
                {"arousal": 0.35, "valence": 0.48, "stress": 0.18, "anxiety": 0.18, "dominant_traces": []},
                {"arousal": 0.44, "valence": 0.36, "stress": 0.24, "anxiety": 0.24, "dominant_traces": ["agency_blocked"]},
            ]
            somatic_index = {"i": 0}

            def fake_http(method, url, payload=None, timeout=30.0, basic_auth=None, extra_headers=None):  # pylint: disable=unused-argument
                if url.endswith("/ghost/rrd/state"):
                    return 200, {"block_counts": {"would_block": 0, "enforce_block": 0}}, "{}"
                if url.endswith("/somatic"):
                    idx = min(somatic_index["i"], len(somatic_sequence) - 1)
                    somatic_index["i"] += 1
                    snapshot = dict(somatic_sequence[idx])
                    return 200, snapshot, json.dumps(snapshot)
                if url.endswith("/ghost/actuate"):
                    action = str((payload or {}).get("action") or "")
                    if action == "report_somatic_event":
                        response = {
                            "success": True,
                            "reason": "ok",
                            "injected": True,
                            "trace": "agency_fulfilled",
                            "agency_trace": "agency_fulfilled",
                        }
                        return 200, response, json.dumps(response)
                    response = {
                        "success": False,
                        "reason": "unknown_action",
                        "injected": True,
                        "trace": "agency_blocked",
                    }
                    return 200, response, json.dumps(response)
                return 404, {}, ""

            with patch.object(experiment_runner, "_http_json", side_effect=fake_http), patch.object(
                experiment_runner,
                "_run_confirmation_suite",
                return_value={"same_turn_confirmation_rate": 1.0, "total": 3, "passed": 3, "failed": 0},
            ), patch.object(experiment_runner.time, "sleep", return_value=None):
                summary, _ = experiment_runner.run_campaign(manifest)

            quality = dict(summary.get("quality_metrics") or {})
            self.assertEqual(float(quality.get("agency_trace_alignment_rate") or 0.0), 1.0)
            alignment = dict(quality.get("agency_alignment") or {})
            self.assertEqual(int(alignment.get("total") or 0), 2)
            self.assertEqual(int(alignment.get("aligned") or 0), 2)
            misalignments = dict(alignment.get("misalignments") or {})
            self.assertEqual(sum(int(v or 0) for v in misalignments.values()), 0)


if __name__ == "__main__":
    unittest.main()
