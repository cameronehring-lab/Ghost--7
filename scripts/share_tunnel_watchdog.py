#!/usr/bin/env python3
"""
Keep Cloudflare tunnel alive for tester access and continuously refresh
LOGIN_HANDOFF.local.md with the current shared URL + status.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
HANDOFF_PATH = ROOT / "docs" / "LOGIN_HANDOFF.local.md"

STATE_DIR = Path(tempfile.gettempdir()) / "omega4_share_tunnel"
LOG_PATH = STATE_DIR / "cloudflared.log"
PID_PATH = STATE_DIR / "cloudflared.pid"
URL_PATH = STATE_DIR / "current_url.txt"
WATCHDOG_PID_PATH = STATE_DIR / "watchdog.pid"
PUBLIC_DNS_SERVERS = ("1.1.1.1", "8.8.8.8")
ORIGIN_HEALTH_URL = "http://localhost:8000/health"
DEFAULT_CLOUDFLARED_BIN_CANDIDATES = (
    "/opt/homebrew/bin/cloudflared",
    "/usr/local/bin/cloudflared",
    "/usr/bin/cloudflared",
)


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


def _resolve_cloudflared_bin() -> str:
    env_bin = os.getenv("CLOUDFLARED_BIN", "").strip()
    if env_bin:
        return env_bin
    found = shutil.which("cloudflared")
    if found:
        return found
    for candidate in DEFAULT_CLOUDFLARED_BIN_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return "cloudflared"


_mode_raw = os.getenv("SHARE_TUNNEL_MODE", "quick").strip().lower()
SHARE_TUNNEL_MODE = _mode_raw if _mode_raw in {"quick", "named"} else "quick"
SHARE_TUNNEL_FIXED_HOSTNAME_RAW = os.getenv("SHARE_TUNNEL_FIXED_HOSTNAME", "").strip()
CLOUDFLARE_TUNNEL_TOKEN = os.getenv("CLOUDFLARE_TUNNEL_TOKEN", "").strip()
CLOUDFLARED_BIN = _resolve_cloudflared_bin()

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
HANDOFF_URL_LINE_RE = re.compile(r"^- Shared tunnel URL: `[^`]+`$", re.MULTILINE)
HANDOFF_STATUS_LINE_RE = re.compile(r"^- Tunnel status at `[^`]+`:.*$", re.MULTILINE)
HANDOFF_STEP_LINE_RE = re.compile(
    r"^1\. Open `https://[^`]+` if you are remote, or `http://localhost:8000` if you are on the host machine\.$",
    re.MULTILINE,
)

QUICK_CLOUDFLARED_CMD = [
    CLOUDFLARED_BIN,
    "tunnel",
    "--protocol",
    "http2",
    "--url",
    "http://localhost:8000",
]
NAMED_CLOUDFLARED_CMD = [
    CLOUDFLARED_BIN,
    "tunnel",
    "run",
    "--url",
    "http://localhost:8000",
]
ResolverIssue = Literal["healthy", "local_dns_mismatch", "unreachable"]


def _now_label() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _is_named_mode() -> bool:
    return SHARE_TUNNEL_MODE == "named"


def _normalize_hostname(host_or_url: str) -> str:
    raw = (host_or_url or "").strip()
    if not raw:
        return ""
    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        return (urlparse(candidate).hostname or "").strip().lower()
    except ValueError:
        return ""


def _fixed_tunnel_hostname() -> str:
    return _normalize_hostname(SHARE_TUNNEL_FIXED_HOSTNAME_RAW)


def _fixed_tunnel_url() -> str:
    host = _fixed_tunnel_hostname()
    if not host:
        return ""
    return f"https://{host}"


def _cloudflared_cmd() -> list[str]:
    if _is_named_mode():
        return list(NAMED_CLOUDFLARED_CMD)
    return list(QUICK_CLOUDFLARED_CMD)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_pid(path: Path) -> Optional[int]:
    raw = _read_text(path).strip()
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


def _run_curl_head(url: str) -> Optional[int]:
    proc = subprocess.run(
        ["curl", "-sS", "--max-time", "10", "-o", "/dev/null", "-w", "%{http_code}", url],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    raw = proc.stdout.strip()
    if raw.isdigit() and raw != "000":
        return int(raw)
    return None


def _local_status() -> Optional[int]:
    return _run_curl_head("http://localhost:8000")


def _origin_status() -> Optional[int]:
    return _run_curl_head(ORIGIN_HEALTH_URL)


def _extract_latest_url_from_log() -> Optional[str]:
    if _is_named_mode():
        fixed_url = _fixed_tunnel_url()
        return fixed_url or None
    content = _read_text(LOG_PATH)
    matches = URL_RE.findall(content)
    if not matches:
        return None
    return matches[-1]


def _wait_for_tunnel_url(timeout_seconds: int = 60) -> Optional[str]:
    if _is_named_mode():
        fixed_url = _fixed_tunnel_url()
        return fixed_url or None
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        url = _extract_latest_url_from_log()
        if url:
            return url
        time.sleep(1)
    return None


def _extract_hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").strip()
    except ValueError:
        return ""


def _local_dns_resolves(hostname: str) -> bool:
    if not hostname:
        return False
    try:
        socket.getaddrinfo(hostname, None)
        return True
    except socket.gaierror:
        return False
    except OSError:
        return False


def _nslookup_resolves(hostname: str, dns_server: str) -> bool:
    if not hostname or not dns_server:
        return False
    try:
        proc = subprocess.run(
            ["nslookup", hostname, dns_server],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    output = f"{proc.stdout}\n{proc.stderr}".lower()
    failure_markers = (
        "nxdomain",
        "non-existent domain",
        "can't find",
        "timed out",
        "server failed",
    )
    if any(marker in output for marker in failure_markers):
        return False

    return proc.returncode == 0 and (
        "address:" in output or "addresses:" in output or "has address" in output
    )


def _public_dns_resolves(hostname: str) -> bool:
    return any(_nslookup_resolves(hostname, server) for server in PUBLIC_DNS_SERVERS)


def _classify_tunnel_health(url: Optional[str], status_code: Optional[int]) -> ResolverIssue:
    if url and status_code is not None and status_code < 500:
        return "healthy"
    if not url:
        return "unreachable"

    hostname = _extract_hostname(url)
    if not hostname:
        return "unreachable"

    if not _local_dns_resolves(hostname) and _public_dns_resolves(hostname):
        return "local_dns_mismatch"

    return "unreachable"


def _kill_pid_windows(pid: int) -> None:
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return


def _stop_cloudflared() -> None:
    pid = _read_pid(PID_PATH)
    if _is_pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        deadline = time.time() + 6
        while time.time() < deadline and _is_pid_alive(pid):
            time.sleep(0.2)
        if _is_pid_alive(pid):
            if sys.platform == "win32":
                _kill_pid_windows(int(pid))
            else:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
    _write_text(PID_PATH, "")


def _named_mode_config_error() -> Optional[str]:
    if _is_named_mode():
        if not _fixed_tunnel_hostname():
            return "SHARE_TUNNEL_FIXED_HOSTNAME is required when SHARE_TUNNEL_MODE=named."
        if not CLOUDFLARE_TUNNEL_TOKEN:
            return "CLOUDFLARE_TUNNEL_TOKEN is required when SHARE_TUNNEL_MODE=named."
    if not (Path(CLOUDFLARED_BIN).exists() or shutil.which(CLOUDFLARED_BIN)):
        return f"cloudflared executable not found: {CLOUDFLARED_BIN}"
    return None


def _start_cloudflared() -> int:
    config_error = _named_mode_config_error()
    if config_error:
        raise RuntimeError(config_error)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    # Reset log so URL extraction always reflects the active process, not stale runs.
    _write_text(LOG_PATH, "")
    child_env = os.environ.copy()
    if _is_named_mode():
        child_env["TUNNEL_TOKEN"] = CLOUDFLARE_TUNNEL_TOKEN
    with LOG_PATH.open("a", encoding="utf-8") as log:
        proc = subprocess.Popen(
            _cloudflared_cmd(),
            stdout=log,
            stderr=log,
            cwd=str(ROOT),
            start_new_session=True,
            env=child_env,
        )
    _write_text(PID_PATH, str(proc.pid))
    return proc.pid


def _start_cloudflared_safe() -> bool:
    try:
        _start_cloudflared()
        return True
    except RuntimeError as exc:
        prev = _read_text(LOG_PATH)
        marker = f"{_now_label()} ERROR: {exc}\n"
        _write_text(LOG_PATH, f"{prev}{marker}")
        return False


def _update_handoff(url: str, status_code: Optional[int], resolver_issue: ResolverIssue) -> None:
    content = _read_text(HANDOFF_PATH)
    if not content:
        return

    timestamp = _now_label()
    if resolver_issue == "healthy":
        if status_code == 401:
            status_text = "reachable and returning `401 Unauthorized`, which is expected before HTTP Basic Auth."
        else:
            status_text = f"reachable via {'named' if _is_named_mode() else 'quick'} tunnel and returning `{status_code}`."
    elif resolver_issue == "local_dns_mismatch":
        status_text = (
            "reachable from public DNS, but this host cannot resolve the tunnel hostname. "
            "This is a local DNS resolver issue, not tunnel downtime."
        )
    elif status_code is None:
        status_text = "not reachable yet from this host (DNS/connectivity failure)."
    else:
        status_text = f"reachable and returning `{status_code}` (expected is `401 Unauthorized`)."

    new_url_line = f"- Shared tunnel URL: `{url}`"
    new_status_line = f"- Tunnel status at `{timestamp}`: {status_text}"
    new_step_line = (
        f"1. Open `{url}` if you are remote, or `http://localhost:8000` if you are on the host machine."
    )

    if HANDOFF_URL_LINE_RE.search(content):
        content = HANDOFF_URL_LINE_RE.sub(new_url_line, content)
    else:
        content += f"\n{new_url_line}\n"

    if HANDOFF_STATUS_LINE_RE.search(content):
        content = HANDOFF_STATUS_LINE_RE.sub(new_status_line, content)
    else:
        content += f"\n{new_status_line}\n"

    if HANDOFF_STEP_LINE_RE.search(content):
        content = HANDOFF_STEP_LINE_RE.sub(new_step_line, content)

    _write_text(HANDOFF_PATH, content)


def _ensure_once(
    restart_on_unhealthy: bool = True,
) -> tuple[Optional[str], Optional[int], bool, ResolverIssue]:
    restarted = False
    pid = _read_pid(PID_PATH)
    if not _is_pid_alive(pid):
        _stop_cloudflared()
        if _start_cloudflared_safe():
            restarted = True

    url = _wait_for_tunnel_url(timeout_seconds=75)
    status_code = _run_curl_head(url) if url else None
    resolver_issue = _classify_tunnel_health(url, status_code)

    if restart_on_unhealthy and resolver_issue == "unreachable":
        _stop_cloudflared()
        if _start_cloudflared_safe():
            restarted = True
        url = _wait_for_tunnel_url(timeout_seconds=75)
        status_code = _run_curl_head(url) if url else None
        resolver_issue = _classify_tunnel_health(url, status_code)

    if url:
        _write_text(URL_PATH, url + "\n")
        _update_handoff(url, status_code, resolver_issue)

    return (url, status_code, restarted, resolver_issue)


def _cmd_status() -> int:
    pid = _read_pid(PID_PATH)
    alive = _is_pid_alive(pid)
    url = _fixed_tunnel_url() if _is_named_mode() else ""
    if not url:
        url = _read_text(URL_PATH).strip() or _extract_latest_url_from_log() or ""
    status_code = _run_curl_head(url) if url else None
    resolver_issue = _classify_tunnel_health(url or None, status_code)
    origin_status = _origin_status()
    connector_health = "healthy" if alive else "down"
    origin_health = "healthy" if origin_status == 200 else "unhealthy"
    config_error = _named_mode_config_error()
    print(
        f"pid={pid or ''} alive={alive} url={url or ''} status={status_code} resolver_issue={resolver_issue} "
        f"tunnel_mode={SHARE_TUNNEL_MODE} connector_health={connector_health} origin_status={origin_status} "
        f"origin_health={origin_health} config_error={'none' if not config_error else config_error}"
    )
    return 0


def _cmd_ensure() -> int:
    if _local_status() != 401:
        print("warning: localhost:8000 is not returning expected 401 share-auth gate")
    config_error = _named_mode_config_error()
    if config_error:
        print(f"warning: {config_error}")
    url, status_code, restarted, resolver_issue = _ensure_once(restart_on_unhealthy=True)
    origin_status = _origin_status()
    connector_alive = _is_pid_alive(_read_pid(PID_PATH))
    print(
        f"restarted={restarted} url={url or ''} status={status_code} resolver_issue={resolver_issue} "
        f"tunnel_mode={SHARE_TUNNEL_MODE} connector_health={'healthy' if connector_alive else 'down'} "
        f"origin_status={origin_status}"
    )
    return 0 if resolver_issue == "healthy" and connector_alive and origin_status == 200 else 1


def _cmd_stop() -> int:
    _stop_cloudflared()
    _write_text(URL_PATH, "")
    print("stopped")
    return 0


def _cmd_watch(interval_seconds: int) -> int:
    current_watchdog_pid = _read_pid(WATCHDOG_PID_PATH)
    if _is_pid_alive(current_watchdog_pid) and current_watchdog_pid != os.getpid():
        print(f"watchdog already running pid={current_watchdog_pid}")
        return 0

    _write_text(WATCHDOG_PID_PATH, str(os.getpid()))
    failures = 0
    try:
        while True:
            url, status_code, _, resolver_issue = _ensure_once(restart_on_unhealthy=False)
            if resolver_issue in {"healthy", "local_dns_mismatch"}:
                failures = 0
            else:
                failures += 1

            if failures >= 3:
                _stop_cloudflared()
                if _start_cloudflared_safe():
                    failures = 0
                    url = _wait_for_tunnel_url(timeout_seconds=75)
                    status_code = _run_curl_head(url) if url else None
                    resolver_issue = _classify_tunnel_health(url, status_code)
                    if url:
                        _write_text(URL_PATH, url + "\n")
                        _update_handoff(url, status_code, resolver_issue)

            print(
                f"{_now_label()} url={url or ''} status={status_code} "
                f"resolver_issue={resolver_issue} failures={failures}"
            )
            time.sleep(max(5, interval_seconds))
    finally:
        _write_text(WATCHDOG_PID_PATH, "")


def main() -> int:
    parser = argparse.ArgumentParser(description="OMEGA4 share tunnel watchdog")
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
        default=20,
        help="Watch interval",
    )
    args = parser.parse_args()

    if args.command == "status":
        return _cmd_status()
    if args.command == "ensure":
        return _cmd_ensure()
    if args.command == "stop":
        return _cmd_stop()
    return _cmd_watch(interval_seconds=int(args.interval_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
