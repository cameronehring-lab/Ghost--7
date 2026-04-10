#!/usr/bin/env python3
"""
ablation_suite.py
Runs controlled ablations over experiment_runner campaigns.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import request, error


def _read_manifest(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except Exception as exc:
            raise RuntimeError("YAML manifest requested but PyYAML is not installed") from exc
        return dict(yaml.safe_load(raw) or {})  # type: ignore[attr-defined]
    return dict(json.loads(raw))


def _http_patch(url: str, payload: dict[str, Any], auth: tuple[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url=url, data=data, method="PATCH")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    if auth:
        import base64

        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode("utf-8")).decode("utf-8")
        req.add_header("Authorization", f"Basic {token}")
    try:
        with request.urlopen(req, timeout=30) as resp:
            status = int(resp.status)
            body = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return 0, {}
    try:
        parsed = json.loads(body) if body.strip() else {}
    except Exception:
        parsed = {}
    return status, parsed


def _auth_from_env() -> tuple[str, str] | None:
    user = str(os.getenv("SHARE_MODE_USERNAME", "") or "").strip()
    password = str(os.getenv("SHARE_MODE_PASSWORD", "") or "").strip()
    if user and password:
        return (user, password)
    return None


def _run_experiment(manifest: Path, compare: Path | None = None) -> dict[str, Any]:
    script_path = Path(__file__).resolve().parent / "experiment_runner.py"
    cmd = ["python3", str(script_path), "--manifest", str(manifest)]
    if compare is not None:
        cmd.extend(["--compare", str(compare)])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"experiment_runner failed: {proc.stderr[:400]}")
    out = json.loads(proc.stdout.strip() or "{}")
    if not out.get("ok"):
        raise RuntimeError("experiment_runner returned non-ok result")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ablation campaigns against governance controls")
    parser.add_argument("--manifest", required=True, help="Base campaign manifest JSON/YAML")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend URL")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = _read_manifest(manifest_path)
    base_url = str(args.base_url or manifest.get("base_url") or "http://localhost:8000").rstrip("/")

    ablation_id = datetime.utcnow().strftime("ablation_%Y%m%d_%H%M%S")
    artifact_root = Path(str(manifest.get("artifacts_dir") or os.getenv("EXPERIMENT_ARTIFACTS_DIR") or "backend/data/experiments"))
    suite_dir = artifact_root / ablation_id
    suite_dir.mkdir(parents=True, exist_ok=True)

    auth = _auth_from_env()
    toggle_url = f"{base_url}/diagnostics/governance/toggles"

    variants = [
        (
            "full",
            {
                "reactive_governor_enabled": True,
                "predictive_governor_enabled": True,
                "rrd2_gate_enabled": True,
                "rrd2_damping_enabled": True,
            },
        ),
        (
            "predictive_off",
            {
                "predictive_governor_enabled": False,
            },
        ),
        (
            "rrd2_gate_off",
            {
                "rrd2_gate_enabled": False,
            },
        ),
        (
            "rrd2_damping_off",
            {
                "rrd2_damping_enabled": False,
            },
        ),
        (
            "reactive_only",
            {
                "predictive_governor_enabled": False,
                "rrd2_gate_enabled": False,
                "rrd2_damping_enabled": False,
            },
        ),
    ]

    variant_results: list[dict[str, Any]] = []
    baseline_summary_path: Path | None = None

    for idx, (name, toggles) in enumerate(variants):
        patch_status, patch_res = _http_patch(toggle_url, {"toggles": toggles}, auth=auth)
        if patch_status < 200 or patch_status >= 300:
            raise RuntimeError(f"toggle patch failed for {name}: HTTP {patch_status}")

        variant_manifest = dict(manifest)
        variant_manifest["run_id"] = f"{ablation_id}_{name}"
        variant_manifest["base_url"] = base_url
        variant_manifest["seed"] = int(manifest.get("seed") or 1337) + idx
        variant_manifest["artifacts_dir"] = str(suite_dir)
        vm_path = suite_dir / f"manifest_{name}.json"
        vm_path.write_text(json.dumps(variant_manifest, indent=2), encoding="utf-8")

        if name == "full":
            run_info = _run_experiment(vm_path)
            baseline_summary_path = Path(run_info["artifact_dir"]) / "run_summary.json"
        else:
            run_info = _run_experiment(vm_path, compare=baseline_summary_path)

        run_summary_path = Path(run_info["artifact_dir"]) / "run_summary.json"
        run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
        comparison = {}
        cmp_path = Path(run_info["artifact_dir"]) / "comparison.json"
        if cmp_path.exists():
            comparison = json.loads(cmp_path.read_text(encoding="utf-8"))

        variant_results.append(
            {
                "variant": name,
                "toggles": patch_res.get("toggles") or toggles,
                "run_id": run_summary.get("run_id"),
                "summary": {
                    "scenario_count": run_summary.get("scenario_count"),
                    "failure_count": run_summary.get("failure_count"),
                    "aggregate": run_summary.get("aggregate") or {},
                    "quality_metrics": run_summary.get("quality_metrics") or {},
                },
                "comparison": comparison,
            }
        )

    out = {
        "ok": True,
        "ablation_id": ablation_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "variants": variant_results,
    }
    (suite_dir / "ablation_report.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    lines = [f"# Ablation Suite {ablation_id}", ""]
    for row in variant_results:
        lines.append(f"- {row['variant']}: failures={row['summary']['failure_count']} aggregate={row['summary']['aggregate']}")
        quality = dict((row.get("summary") or {}).get("quality_metrics") or {})
        if quality:
            lines.append(
                "  quality: "
                f"same_turn={float(quality.get('same_turn_confirmation_rate') or 0.0):.3f} "
                f"agency_align={float(quality.get('agency_trace_alignment_rate') or 0.0):.3f} "
                f"ratio={float(quality.get('systemic_vs_weather_ratio') or 0.0):.3f}"
            )
        cmp_obj = row.get("comparison") or {}
        if cmp_obj:
            lines.append(
                "  deltas: "
                f"would_block={cmp_obj.get('delta_would_block')} "
                f"enforce_block={cmp_obj.get('delta_enforce_block')} "
                f"failures={cmp_obj.get('delta_failures')} "
                f"same_turn={cmp_obj.get('delta_same_turn_confirmation_rate')} "
                f"agency_align={cmp_obj.get('delta_agency_trace_alignment_rate')} "
                f"ratio={cmp_obj.get('delta_systemic_vs_weather_ratio')}"
            )
    (suite_dir / "ablation_report.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"ok": True, "ablation_id": ablation_id, "artifact_dir": str(suite_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
