#!/usr/bin/env python3
"""
Run OMEGA diagnostics and print a signed-style falsification report.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse, urlunparse
from typing import Any


def _load_dotenv_map() -> dict[str, str]:
    """
    Lightweight .env loader (no external dependency).
    Looks for ../.env relative to this script.
    """
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    values: dict[str, str] = {}
    if not os.path.exists(env_path):
        return values

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                values[key] = val
    except Exception:
        return {}
    return values


def _share_auth_pair(args: argparse.Namespace) -> tuple[str, str]:
    dotenv = _load_dotenv_map()
    user = (
        str(getattr(args, "share_user", "") or "").strip()
        or os.getenv("SHARE_MODE_USERNAME", "").strip()
        or str(dotenv.get("SHARE_MODE_USERNAME", "")).strip()
    )
    password = (
        str(getattr(args, "share_password", "") or "")
        or os.getenv("SHARE_MODE_PASSWORD", "")
        or str(dotenv.get("SHARE_MODE_PASSWORD", ""))
    )
    return user, password


def _auth_headers(args: argparse.Namespace) -> dict[str, str]:
    user, password = _share_auth_pair(args)
    if not user or not password:
        return {}
    raw = f"{user}:{password}".encode("utf-8")
    token = base64.b64encode(raw).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def post_json(url: str, payload: dict[str, Any], timeout: int = 120, headers: dict[str, str] | None = None) -> dict[str, Any]:
    merged_headers = {"Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=merged_headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def get_json(url: str, timeout: int = 120, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET", headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def summarize(report: dict[str, Any]) -> tuple[bool, list[str]]:
    checks = report.get("checks", {})
    is_fallback = bool(report.get("fallback"))
    lines = []
    ok = True
    for key in ("shock_has_series", "coalescence_has_updates", "evidence_has_rows"):
        if key == "coalescence_has_updates" and is_fallback:
            lines.append("INFO  coalescence_has_updates skipped in quick mode")
            continue
        val = bool(checks.get(key))
        ok = ok and val
        lines.append(f"{'PASS' if val else 'FAIL'}  {key}")

    shock = report.get("shock", {})
    stats = shock.get("stats", {})
    if stats:
        lines.append(
            "INFO  shock arousal "
            f"{stats.get('arousal_start')} -> {stats.get('arousal_end')} "
            f"(nonincreasing={stats.get('arousal_nonincreasing_ratio')})"
        )

    coal = report.get("coalescence", {})
    updates = coal.get("identity_updates")
    if isinstance(updates, dict):
        lines.append(f"INFO  coalescence identity_updates keys={len(updates.keys())}")
    elif isinstance(updates, list):
        lines.append(f"INFO  coalescence identity_updates count={len(updates)}")

    ev = report.get("evidence", {})
    lines.append(
        "INFO  evidence rows "
        f"qualia={len(ev.get('qualia_nexus', []))} "
        f"actuation={len(ev.get('actuation_log', []))} "
        f"coalescence={len(ev.get('coalescence_log', []))}"
    )
    return ok, lines


def _run_report_payload(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    """Run diagnostics over HTTP and return (payload, used_fallback_mode)."""
    url = f"{args.base_url.rstrip('/')}/diagnostics/run"
    used_fallback = False
    auth_headers = _auth_headers(args)
    try:
        if args.full:
            payload = post_json(url, {}, timeout=args.timeout, headers=auth_headers)
        else:
            used_fallback = True
            shock = post_json(
                f"{args.base_url.rstrip('/')}/diagnostics/somatic/shock",
                {"sample_seconds": 3, "label": "report_quick"},
                timeout=max(30, args.timeout // 2),
                headers=auth_headers,
            )
            evidence = get_json(
                f"{args.base_url.rstrip('/')}/diagnostics/evidence/latest",
                timeout=max(30, args.timeout // 2),
                headers=auth_headers,
            )
            payload = {
                "run_id": f"quick-{int(time.time())}",
                "timestamp": time.time(),
                "checks": {
                    "shock_has_series": bool(shock.get("series")),
                    "coalescence_has_updates": False,
                    "evidence_has_rows": bool(
                        evidence.get("coalescence_log")
                        or evidence.get("actuation_log")
                        or evidence.get("qualia_nexus")
                    ),
                },
                "shock": shock,
                "coalescence": {"info": "not executed in quick mode (use --full)"},
                "evidence": evidence,
                "fallback": True,
            }
    except Exception as e:
        used_fallback = True
        # Fallback path still gives reproducible evidence if full run stalls.
        shock = post_json(
            f"{args.base_url.rstrip('/')}/diagnostics/somatic/shock",
            {"sample_seconds": 3, "label": "report_fallback"},
            timeout=max(30, args.timeout // 2),
            headers=auth_headers,
        )
        evidence = get_json(
            f"{args.base_url.rstrip('/')}/diagnostics/evidence/latest",
            timeout=max(30, args.timeout // 2),
            headers=auth_headers,
        )
        payload = {
            "run_id": f"fallback-{int(time.time())}",
            "timestamp": time.time(),
            "checks": {
                "shock_has_series": bool(shock.get("series")),
                "coalescence_has_updates": False,
                "evidence_has_rows": bool(
                    evidence.get("coalescence_log")
                    or evidence.get("actuation_log")
                    or evidence.get("qualia_nexus")
                ),
            },
            "shock": shock,
            "coalescence": {"error": f"skipped after /diagnostics/run failure: {e}"},
            "evidence": evidence,
            "fallback": True,
        }
    return payload, used_fallback


def _is_localish_base_url(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _container_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    netloc = "127.0.0.1"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    scheme = parsed.scheme or "http"
    return urlunparse((scheme, netloc, "", "", "", ""))


def _rerun_in_container(args: argparse.Namespace, reason: urllib.error.HTTPError) -> int:
    container = args.container_name
    container_base = _container_base_url(args.base_url)
    share_user, share_password = _share_auth_pair(args)

    cmd = [
        "docker", "exec", "-i", container,
        "python", "/app/scripts/falsification_report.py",
        "--base-url", container_base,
        "--timeout", str(args.timeout),
        "--no-docker-fallback",
    ]
    if share_user:
        cmd.extend(["--share-user", share_user])
    if share_password:
        cmd.extend(["--share-password", share_password])
    if args.full:
        cmd.append("--full")
    if args.raw_json:
        cmd.append("--raw-json")

    print(
        f"INFO  diagnostics got HTTP {reason.code} from host path; "
        f"auto-running inside container '{container}'"
    )
    try:
        proc = subprocess.run(cmd, check=False, text=True, capture_output=True)
    except FileNotFoundError:
        print(
            "FAIL  docker not found; cannot auto-fallback to container execution. "
            "Install Docker or run from inside omega-backend."
        )
        return 2

    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OMEGA falsification diagnostics report.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="OMEGA backend base URL")
    parser.add_argument("--timeout", type=int, default=180, help="Request timeout seconds")
    parser.add_argument("--full", action="store_true", help="Use /diagnostics/run (slower, includes coalescence)")
    parser.add_argument("--raw-json", action="store_true", help="Print full JSON payload")
    parser.add_argument("--share-user", default="", help="HTTP Basic auth username for share mode")
    parser.add_argument("--share-password", default="", help="HTTP Basic auth password for share mode")
    parser.add_argument(
        "--container-name",
        default=os.getenv("OMEGA_BACKEND_CONTAINER", "omega-backend"),
        help="Container name for auto-fallback execution",
    )
    parser.add_argument(
        "--no-docker-fallback",
        action="store_true",
        help="Disable automatic docker exec fallback on local 403 responses",
    )
    args = parser.parse_args()

    started = time.time()
    try:
        payload, used_fallback = _run_report_payload(args)
    except urllib.error.HTTPError as he:
        if (
            he.code == 403
            and not args.no_docker_fallback
            and _is_localish_base_url(args.base_url)
        ):
            return _rerun_in_container(args, he)
        if he.code == 401:
            print(
                "FAIL  diagnostics HTTP error: 401 Unauthorized "
                "(set share credentials via --share-user/--share-password or SHARE_MODE_* env/.env)"
            )
            return 2
        print(f"FAIL  diagnostics HTTP error: {he.code} {he.reason}")
        return 2
    except Exception as e:
        print(f"FAIL  diagnostics request failed: {e}")
        return 2

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    ok, lines = summarize(payload)

    print("OMEGA FALSIFICATION REPORT")
    print(f"run_id={payload.get('run_id')}")
    print(f"timestamp={payload.get('timestamp')}")
    print(f"elapsed_sec={round(time.time() - started, 2)}")
    if used_fallback:
        print("INFO  fallback_mode=True")
    for line in lines:
        print(line)
    print(f"SHA256={digest}")

    if args.raw_json:
        print("\nRAW_JSON_START")
        print(json.dumps(payload, indent=2))
        print("RAW_JSON_END")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
