#!/usr/bin/env python3
"""
Host-level watchdog that probes the local OMEGA stack and restarts Docker when
the app is genuinely stalled.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
_STATE_DIR_OVERRIDE = str(os.getenv("OMEGA4_DOCKER_RECOVERY_STATE_DIR", "") or "").strip()
STATE_DIR = Path(_STATE_DIR_OVERRIDE) if _STATE_DIR_OVERRIDE else Path(tempfile.gettempdir()) / "omega4_docker_recovery"
STATE_PATH = STATE_DIR / "state.json"
PID_PATH = STATE_DIR / "watchdog.pid"
LOG_PATH = STATE_DIR / "watchdog.log"

BASE_URL = "http://127.0.0.1:8000"
HEALTH_URL = f"{BASE_URL}/health"
SOMATIC_URL = f"{BASE_URL}/somatic"
PUSH_URL = f"{BASE_URL}/ghost/push"

DEFAULT_INTERVAL_SECONDS = 20
FAILURE_THRESHOLD = 3
GRACE_SECONDS = 60.0
FULL_RESTART_RATE_LIMIT_SECONDS = 600.0
PUSH_EVENT_TIMEOUT_SECONDS = 12.0

StateDict = dict[str, Any]
ProbeDict = dict[str, Any]
RestartFn = Callable[[str], tuple[bool, str]]


def _load_env_defaults(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_env_defaults(ROOT / ".env")


def _now_label(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(ts or time.time()).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _write_text(path: Path, text: str) -> None:
    _ensure_state_dir()
    path.write_text(text, encoding="utf-8")


def _append_log(message: str) -> None:
    _ensure_state_dir()
    line = f"{_now_label()} {message}".rstrip()
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line)


def _read_pid() -> Optional[int]:
    raw = _read_text(PID_PATH).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _is_pid_alive(pid: Optional[int]) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _stop_pid(pid: Optional[int]) -> bool:
    if not _is_pid_alive(pid):
        return False
    try:
        os.kill(int(pid), signal.SIGTERM)
    except OSError:
        return False
    deadline = time.time() + 6.0
    while time.time() < deadline and _is_pid_alive(pid):
        time.sleep(0.2)
    if _is_pid_alive(pid):
        try:
            os.kill(int(pid), signal.SIGKILL)
        except OSError:
            pass
    return not _is_pid_alive(pid)


def _default_state() -> StateDict:
    return {
        "consecutive_failures": 0,
        "escalate_to_full_stack": False,
        "grace_until": 0.0,
        "last_cycle_at": 0.0,
        "last_cycle_healthy": None,
        "last_cycle_note": "never_ran",
        "last_cycle_detail": "",
        "last_healthy_at": 0.0,
        "last_recovery_action": "",
        "last_recovery_detail": "",
        "last_recovery_at": 0.0,
        "last_backend_restart_at": 0.0,
        "last_full_restart_at": 0.0,
        "last_full_restart_suppressed_at": 0.0,
        "last_probe": {},
    }


def _normalize_state(raw: Optional[StateDict]) -> StateDict:
    state = _default_state()
    if isinstance(raw, dict):
        state.update(raw)
    if not isinstance(state.get("last_probe"), dict):
        state["last_probe"] = {}
    return state


def _read_state() -> StateDict:
    try:
        data = json.loads(_read_text(STATE_PATH) or "{}")
    except json.JSONDecodeError:
        data = {}
    return _normalize_state(data if isinstance(data, dict) else {})


def _write_state(state: StateDict) -> None:
    _ensure_state_dir()
    tmp_path = STATE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(STATE_PATH)


def _http_status(url: str, *, timeout_seconds: float = 10.0) -> tuple[Optional[int], str]:
    req = request.Request(url=url, method="GET")
    try:
        with request.urlopen(req, timeout=max(1.0, float(timeout_seconds))) as resp:
            return int(getattr(resp, "status", 200) or 200), ""
    except error.HTTPError as exc:
        return int(getattr(exc, "code", 500) or 500), f"http_error:{exc.code}"
    except Exception as exc:
        return None, f"request_error:{exc}"


def _probe_push_stream(*, timeout_seconds: float = PUSH_EVENT_TIMEOUT_SECONDS) -> tuple[bool, str]:
    req = request.Request(url=PUSH_URL, method="GET")
    deadline = time.time() + max(1.0, float(timeout_seconds))
    try:
        with request.urlopen(req, timeout=max(1.0, float(timeout_seconds))) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            if status != 200:
                return False, f"http_status:{status}"
            while time.time() < deadline:
                raw_line = resp.readline()
                if raw_line == b"":
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip() or "unknown"
                    return True, f"event:{event_name}"
                if line.startswith("data:"):
                    return True, "data"
            return False, "timeout_waiting_for_event"
    except error.HTTPError as exc:
        return False, f"http_error:{exc.code}"
    except Exception as exc:
        return False, f"request_error:{exc}"


def _probe_cycle() -> ProbeDict:
    checked_at = time.time()
    health_code, health_detail = _http_status(HEALTH_URL, timeout_seconds=10.0)
    somatic_code, somatic_detail = _http_status(SOMATIC_URL, timeout_seconds=10.0)
    push_ok, push_detail = _probe_push_stream(timeout_seconds=PUSH_EVENT_TIMEOUT_SECONDS)
    probe = {
        "checked_at": checked_at,
        "health_code": health_code,
        "health_ok": health_code == 200,
        "health_detail": health_detail,
        "somatic_code": somatic_code,
        "somatic_ok": somatic_code == 200,
        "somatic_detail": somatic_detail,
        "push_ok": bool(push_ok),
        "push_detail": push_detail,
    }
    probe["healthy"] = bool(probe["health_ok"] and probe["somatic_ok"] and probe["push_ok"])
    return probe


def _probe_summary(probe: ProbeDict) -> str:
    health = probe.get("health_code")
    somatic = probe.get("somatic_code")
    push = probe.get("push_detail") or "-"
    return f"health={health} somatic={somatic} push={push}"


def _cooldown_remaining_seconds(state: StateDict, now_ts: float) -> int:
    last_full = float(state.get("last_full_restart_at") or 0.0)
    if last_full <= 0.0:
        return 0
    remaining = FULL_RESTART_RATE_LIMIT_SECONDS - (float(now_ts) - last_full)
    return max(0, int(math.ceil(remaining)))


def _run_compose_restart(target: str) -> tuple[bool, str]:
    cmd = ["docker", "compose", "restart"]
    label = "full_stack"
    if target == "backend":
        cmd.append("backend")
        label = "backend"
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=180.0,
            check=False,
        )
    except Exception as exc:
        return False, f"{label}:request_error:{exc}"
    output = (proc.stdout or proc.stderr or "").strip().replace("\n", " ")
    detail = output[:400] if output else f"{label}:exit={proc.returncode}"
    return proc.returncode == 0, detail


def _run_cycle(
    state: StateDict,
    probe: ProbeDict,
    *,
    now_ts: Optional[float] = None,
    restart_fn: RestartFn = _run_compose_restart,
) -> StateDict:
    now = float(now_ts if now_ts is not None else time.time())
    next_state = _normalize_state(state)
    next_state["last_cycle_at"] = now
    next_state["last_probe"] = probe
    next_state["last_cycle_healthy"] = bool(probe.get("healthy"))

    if bool(probe.get("healthy")):
        next_state["consecutive_failures"] = 0
        next_state["escalate_to_full_stack"] = False
        next_state["grace_until"] = 0.0
        next_state["last_healthy_at"] = now
        next_state["last_cycle_note"] = "healthy"
        next_state["last_cycle_detail"] = _probe_summary(probe)
        return next_state

    next_state["last_cycle_detail"] = _probe_summary(probe)
    grace_until = float(next_state.get("grace_until") or 0.0)
    if grace_until > now:
        next_state["consecutive_failures"] = 0
        next_state["last_cycle_note"] = "grace_window"
        remaining = int(math.ceil(grace_until - now))
        next_state["last_cycle_detail"] = (
            f"{_probe_summary(probe)} grace_remaining={remaining}s"
        )
        return next_state

    failures = int(next_state.get("consecutive_failures") or 0) + 1
    next_state["consecutive_failures"] = failures
    next_state["last_cycle_note"] = "unhealthy"
    if failures < FAILURE_THRESHOLD:
        return next_state

    if not bool(next_state.get("escalate_to_full_stack")):
        ok, detail = restart_fn("backend")
        next_state["last_recovery_action"] = "restart_backend"
        next_state["last_recovery_detail"] = detail
        next_state["last_recovery_at"] = now
        if ok:
            next_state["consecutive_failures"] = 0
            next_state["escalate_to_full_stack"] = True
            next_state["grace_until"] = now + GRACE_SECONDS
            next_state["last_backend_restart_at"] = now
            next_state["last_cycle_note"] = "restart_backend"
            next_state["last_cycle_detail"] = f"{_probe_summary(probe)} action=restart_backend"
        else:
            next_state["consecutive_failures"] = FAILURE_THRESHOLD
            next_state["last_cycle_note"] = "restart_backend_failed"
            next_state["last_cycle_detail"] = f"{_probe_summary(probe)} action=restart_backend_failed"
        return next_state

    cooldown_remaining = _cooldown_remaining_seconds(next_state, now)
    if cooldown_remaining > 0:
        next_state["consecutive_failures"] = FAILURE_THRESHOLD
        next_state["last_full_restart_suppressed_at"] = now
        next_state["last_cycle_note"] = "full_restart_suppressed"
        next_state["last_cycle_detail"] = (
            f"{_probe_summary(probe)} cooldown_remaining={cooldown_remaining}s"
        )
        return next_state

    ok, detail = restart_fn("full")
    next_state["last_recovery_action"] = "restart_all"
    next_state["last_recovery_detail"] = detail
    next_state["last_recovery_at"] = now
    if ok:
        next_state["consecutive_failures"] = 0
        next_state["grace_until"] = now + GRACE_SECONDS
        next_state["last_full_restart_at"] = now
        next_state["last_cycle_note"] = "restart_all"
        next_state["last_cycle_detail"] = f"{_probe_summary(probe)} action=restart_all"
    else:
        next_state["consecutive_failures"] = FAILURE_THRESHOLD
        next_state["last_cycle_note"] = "restart_all_failed"
        next_state["last_cycle_detail"] = f"{_probe_summary(probe)} action=restart_all_failed"
    return next_state


def _status_line(state: StateDict) -> str:
    pid = _read_pid()
    probe = dict(state.get("last_probe") or {})
    last_cycle_at = float(state.get("last_cycle_at") or 0.0)
    grace_until = float(state.get("grace_until") or 0.0)
    now = time.time()
    grace_remaining = max(0, int(math.ceil(grace_until - now))) if grace_until else 0
    full_cooldown = _cooldown_remaining_seconds(state, now)
    return (
        f"pid={pid or ''} "
        f"alive={_is_pid_alive(pid)} "
        f"failures={int(state.get('consecutive_failures') or 0)} "
        f"escalate_to_full_stack={bool(state.get('escalate_to_full_stack'))} "
        f"grace_remaining={grace_remaining} "
        f"full_restart_cooldown={full_cooldown} "
        f"last_cycle_note={state.get('last_cycle_note') or ''} "
        f"last_cycle_at={_now_label(last_cycle_at) if last_cycle_at else ''} "
        f"last_recovery_action={state.get('last_recovery_action') or ''} "
        f"last_recovery_at={_now_label(float(state.get('last_recovery_at') or 0.0)) if state.get('last_recovery_at') else ''} "
        f"health_code={probe.get('health_code')} "
        f"somatic_code={probe.get('somatic_code')} "
        f"push_ok={probe.get('push_ok')} "
        f"push_detail={probe.get('push_detail') or ''}"
    )


def _cmd_status() -> int:
    state = _read_state()
    print(_status_line(state))
    return 0


def _cmd_stop() -> int:
    pid = _read_pid()
    stopped = _stop_pid(pid)
    if stopped or not _is_pid_alive(pid):
        _write_text(PID_PATH, "")
        print("stopped")
        return 0
    print(f"failed_to_stop pid={pid or ''}")
    return 1


def _run_once(*, log_line: bool) -> int:
    state = _read_state()
    probe = _probe_cycle()
    next_state = _run_cycle(state, probe)
    _write_state(next_state)
    line = (
        f"healthy={bool(probe.get('healthy'))} "
        f"note={next_state.get('last_cycle_note')} "
        f"failures={int(next_state.get('consecutive_failures') or 0)} "
        f"summary=\"{next_state.get('last_cycle_detail') or ''}\""
    )
    if log_line:
        _append_log(line)
    else:
        print(line)
    return 0 if bool(probe.get("healthy")) else 1


def _cmd_ensure() -> int:
    return _run_once(log_line=False)


def _cmd_watch(interval_seconds: int) -> int:
    current_pid = _read_pid()
    if _is_pid_alive(current_pid) and current_pid != os.getpid():
        print(f"watchdog already running pid={current_pid}")
        return 0

    _write_text(PID_PATH, str(os.getpid()))
    _append_log(
        f"watch_start interval_seconds={max(5, int(interval_seconds))} state_dir={STATE_DIR}"
    )
    try:
        while True:
            _run_once(log_line=True)
            time.sleep(max(5, int(interval_seconds)))
    finally:
        _write_text(PID_PATH, "")


def main() -> int:
    parser = argparse.ArgumentParser(description="OMEGA4 Docker recovery watchdog")
    parser.add_argument(
        "command",
        nargs="?",
        default="watch",
        choices=["watch", "ensure", "status", "stop"],
        help="Command to run",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help="Watch interval in seconds",
    )
    args = parser.parse_args()

    if args.command == "status":
        return _cmd_status()
    if args.command == "stop":
        return _cmd_stop()
    if args.command == "ensure":
        return _cmd_ensure()
    return _cmd_watch(interval_seconds=int(args.interval_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
