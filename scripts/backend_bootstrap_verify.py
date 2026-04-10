#!/usr/bin/env python3
"""
Deterministic backend bootstrap + reliability verification flow.

Failure classes:
- env_missing_dep
- service_unreachable
- policy_block_expected
- regression_failure
"""

from __future__ import annotations

import argparse
import base64
import importlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional
from urllib import error, request


_DEPENDENCY_MODULES = (
    ("fastapi", "fastapi"),
    ("pydantic-settings", "pydantic_settings"),
    ("asyncpg", "asyncpg"),
    ("psutil", "psutil"),
    ("redis", "redis"),
    ("google-genai", "google.genai"),
)

_TARGETED_TESTS = (
    "backend.test_ghost_api_action_confirmation",
    "backend.test_actuation_agency_traces",
    "backend.test_ambient_trace_balance",
    "backend.test_ghost_api_external_context",
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    elapsed_ms: float
    failure_class: str = ""
    status_code: Optional[int] = None


def _auth_from_env() -> tuple[str, str] | None:
    user = str(os.getenv("SHARE_MODE_USERNAME", "") or "").strip()
    password = str(os.getenv("SHARE_MODE_PASSWORD", "") or "").strip()
    if user and password:
        return user, password
    return None


def _http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = 15.0,
    basic_auth: tuple[str, str] | None = None,
    operator_token: str = "",
) -> tuple[int, dict[str, Any], str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(url=url, method=method.upper(), data=data)
    req.add_header("Accept", "application/json")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    if basic_auth:
        encoded = base64.b64encode(f"{basic_auth[0]}:{basic_auth[1]}".encode("utf-8")).decode("utf-8")
        req.add_header("Authorization", f"Basic {encoded}")
    if operator_token:
        req.add_header("X-Operator-Token", operator_token)

    try:
        with request.urlopen(req, timeout=max(1.0, float(timeout_seconds))) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            body = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        status = int(getattr(exc, "code", 500) or 500)
        body = exc.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, {}, f"request_error:{exc}"

    try:
        parsed = json.loads(body) if body.strip() else {}
    except Exception:
        parsed = {}
    return status, parsed, body


def _run_subprocess(cmd: list[str], *, cwd: Path, timeout_seconds: float) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=max(5.0, timeout_seconds),
        check=False,
    )
    return int(proc.returncode or 0), str(proc.stdout or ""), str(proc.stderr or "")


def _check_dependencies() -> CheckResult:
    t0 = time.time()
    missing: list[str] = []
    for label, module_name in _DEPENDENCY_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception:
            missing.append(label)
    elapsed_ms = (time.time() - t0) * 1000.0
    if missing:
        return CheckResult(
            name="dependency_preflight",
            ok=False,
            detail=f"Missing required modules: {', '.join(missing)}",
            elapsed_ms=elapsed_ms,
            failure_class="env_missing_dep",
        )
    return CheckResult(
        name="dependency_preflight",
        ok=True,
        detail="All required Python modules import successfully.",
        elapsed_ms=elapsed_ms,
    )


def _check_health(base_url: str, *, timeout_seconds: float, basic_auth: tuple[str, str] | None) -> CheckResult:
    t0 = time.time()
    status, parsed, body = _http_json(
        "GET",
        f"{base_url.rstrip('/')}/health",
        timeout_seconds=timeout_seconds,
        basic_auth=basic_auth,
    )
    elapsed_ms = (time.time() - t0) * 1000.0
    if status != 200:
        detail = str(parsed or body or "health endpoint failed")
        return CheckResult(
            name="service_preflight",
            ok=False,
            detail=detail[:300],
            elapsed_ms=elapsed_ms,
            failure_class="service_unreachable",
            status_code=status,
        )
    return CheckResult(
        name="service_preflight",
        ok=True,
        detail="Backend health endpoint reachable.",
        elapsed_ms=elapsed_ms,
        status_code=status,
    )


def _check_policy_guard(base_url: str, *, timeout_seconds: float, basic_auth: tuple[str, str] | None) -> CheckResult:
    t0 = time.time()
    status, parsed, body = _http_json(
        "GET",
        f"{base_url.rstrip('/')}/ops/verify",
        timeout_seconds=timeout_seconds,
        basic_auth=basic_auth,
    )
    elapsed_ms = (time.time() - t0) * 1000.0
    if status == 401:
        detail = "policy_block_expected: /ops/verify requires ops code."
        return CheckResult(
            name="policy_guard_preflight",
            ok=True,
            detail=detail,
            elapsed_ms=elapsed_ms,
            status_code=status,
        )
    detail = str(parsed or body or "unexpected response from /ops/verify")
    return CheckResult(
        name="policy_guard_preflight",
        ok=False,
        detail=detail[:300],
        elapsed_ms=elapsed_ms,
        failure_class="regression_failure",
        status_code=status,
    )


def _run_targeted_tests(repo_root: Path, *, timeout_seconds: float) -> CheckResult:
    t0 = time.time()
    cmd = [sys.executable, "-m", "unittest", "-q", *_TARGETED_TESTS]
    code, stdout, stderr = _run_subprocess(cmd, cwd=repo_root, timeout_seconds=timeout_seconds)
    elapsed_ms = (time.time() - t0) * 1000.0
    if code != 0:
        detail = (stderr.strip() or stdout.strip() or f"targeted tests failed with exit code {code}")[:600]
        failure_class = "env_missing_dep" if "ModuleNotFoundError" in detail else "regression_failure"
        return CheckResult(
            name="targeted_regression_gate",
            ok=False,
            detail=detail,
            elapsed_ms=elapsed_ms,
            failure_class=failure_class,
        )
    return CheckResult(
        name="targeted_regression_gate",
        ok=True,
        detail="Targeted backend regression suites passed.",
        elapsed_ms=elapsed_ms,
    )


def _run_diagnostics(repo_root: Path, *, base_url: str, timeout_seconds: float) -> CheckResult:
    t0 = time.time()
    cmd = [sys.executable, "scripts/falsification_report.py", "--base-url", base_url, "--full"]
    code, stdout, stderr = _run_subprocess(cmd, cwd=repo_root, timeout_seconds=timeout_seconds)
    elapsed_ms = (time.time() - t0) * 1000.0
    if code != 0:
        detail = (stderr.strip() or stdout.strip() or f"falsification report failed with exit code {code}")[:600]
        failure_class = "service_unreachable" if "ConnectionError" in detail or "request_error" in detail else "regression_failure"
        return CheckResult(
            name="system_diagnostics_gate",
            ok=False,
            detail=detail,
            elapsed_ms=elapsed_ms,
            failure_class=failure_class,
        )
    return CheckResult(
        name="system_diagnostics_gate",
        ok=True,
        detail="Full falsification diagnostics passed.",
        elapsed_ms=elapsed_ms,
    )


def _start_services(repo_root: Path, *, timeout_seconds: float) -> CheckResult:
    t0 = time.time()
    cmd = ["docker", "compose", "up", "-d", "postgres", "redis", "influxdb", "backend"]
    try:
        code, stdout, stderr = _run_subprocess(cmd, cwd=repo_root, timeout_seconds=timeout_seconds)
    except Exception as exc:
        elapsed_ms = (time.time() - t0) * 1000.0
        return CheckResult(
            name="docker_compose_bootstrap",
            ok=False,
            detail=str(exc)[:300],
            elapsed_ms=elapsed_ms,
            failure_class="service_unreachable",
        )
    elapsed_ms = (time.time() - t0) * 1000.0
    if code != 0:
        detail = (stderr.strip() or stdout.strip() or "docker compose up failed")[:500]
        return CheckResult(
            name="docker_compose_bootstrap",
            ok=False,
            detail=detail,
            elapsed_ms=elapsed_ms,
            failure_class="service_unreachable",
        )
    return CheckResult(
        name="docker_compose_bootstrap",
        ok=True,
        detail="Requested docker compose services are up.",
        elapsed_ms=elapsed_ms,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonical backend bootstrap + verification flow")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--timeout-seconds", type=float, default=120.0, help="Per-step timeout budget")
    parser.add_argument("--start-services", action="store_true", help="Start docker services before checks")
    parser.add_argument("--skip-tests", action="store_true", help="Skip targeted regression unit tests")
    parser.add_argument("--skip-diagnostics", action="store_true", help="Skip falsification diagnostics gate")
    parser.add_argument("--json-out", default="", help="Optional path to write JSON summary")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    basic_auth = _auth_from_env()

    checks: list[CheckResult] = []
    if args.start_services:
        checks.append(_start_services(repo_root, timeout_seconds=args.timeout_seconds))
    checks.append(_check_dependencies())
    checks.append(_check_health(args.base_url, timeout_seconds=args.timeout_seconds, basic_auth=basic_auth))
    checks.append(_check_policy_guard(args.base_url, timeout_seconds=args.timeout_seconds, basic_auth=basic_auth))
    if not args.skip_tests:
        checks.append(_run_targeted_tests(repo_root, timeout_seconds=args.timeout_seconds))
    if not args.skip_diagnostics:
        checks.append(_run_diagnostics(repo_root, base_url=args.base_url, timeout_seconds=args.timeout_seconds))

    ok = all(check.ok for check in checks)
    failed = [check for check in checks if not check.ok]
    output = {
        "ok": ok,
        "generated_at_unix": time.time(),
        "base_url": args.base_url.rstrip("/"),
        "checks": [asdict(c) for c in checks],
        "failure_classes": sorted({c.failure_class for c in failed if c.failure_class}),
    }
    payload = json.dumps(output, indent=2)
    print(payload)
    if args.json_out:
        out_path = Path(args.json_out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
