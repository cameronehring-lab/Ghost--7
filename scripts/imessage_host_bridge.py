#!/usr/bin/env python3
"""
Minimal host-side iMessage bridge.

Run this on macOS host so containerized backend can dispatch iMessage via:
  POST /send {"target":"+12145551212","content":"hello","sender_account":"..."}
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


logger = logging.getLogger("imessage_host_bridge")


def _escape_applescript_string(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _build_imessage_script(target: str, content: str, sender_account: str) -> str:
    target_esc = _escape_applescript_string(target)
    content_esc = _escape_applescript_string(content)
    sender_esc = _escape_applescript_string(sender_account)
    return f'''
tell application "Messages"
    set senderAccount to "{sender_esc}"
    set matchedService to missing value
    repeat with svc in (services whose service type = iMessage)
        if senderAccount is "" then
            set matchedService to svc
            exit repeat
        end if
        set svcId to ""
        try
            set svcId to (id of svc as text)
        end try
        set svcName to ""
        try
            set svcName to (name of svc as text)
        end try
        if (svcId contains senderAccount) or (svcName contains senderAccount) then
            set matchedService to svc
            exit repeat
        end if
    end repeat
    if matchedService is missing value then
        error "sender_identity_unavailable"
    end if
    set targetBuddy to buddy "{target_esc}" of matchedService
    send "{content_esc}" to targetBuddy
end tell
'''.strip()


def _send_imessage(target: str, content: str, sender_account: str) -> dict[str, Any]:
    target_clean = str(target or "").strip()
    content_clean = str(content or "").strip()
    sender_clean = str(sender_account or "").strip()
    if not target_clean:
        return {"success": False, "reason": "missing_target"}
    if not content_clean:
        return {"success": False, "reason": "missing_content"}
    if platform.system() != "Darwin":
        return {"success": False, "reason": "unsupported_platform"}

    script = _build_imessage_script(target_clean, content_clean, sender_clean)
    cmd = ["osascript", "-e", script]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
    except Exception as exc:
        return {"success": False, "reason": "osascript_exception", "error": str(exc)}

    if proc.returncode != 0:
        stderr = str(proc.stderr or "").strip()
        if "sender_identity_unavailable" in stderr:
            return {"success": False, "reason": "sender_identity_unavailable", "error": stderr}
        return {"success": False, "reason": "osascript_failed", "error": stderr or "unknown_error"}

    return {
        "success": True,
        "transport": "imessage",
        "target": target_clean,
        "content_chars": len(content_clean),
    }


class BridgeHandler(BaseHTTPRequestHandler):
    bridge_token = ""

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = str(self.bridge_token or "").strip()
        if not expected:
            return True
        provided = str(self.headers.get("X-Bridge-Token", "") or "").strip()
        return provided == expected

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/health":
            self._write_json(200, {"ok": True, "service": "imessage_host_bridge"})
            return
        self._write_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/send":
            self._write_json(404, {"ok": False, "error": "not_found"})
            return
        if not self._authorized():
            self._write_json(401, {"ok": False, "error": "unauthorized"})
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            self._write_json(400, {"success": False, "reason": "invalid_payload"})
            return

        target = str(payload.get("target") or "").strip()
        content = str(payload.get("content") or "").strip()
        sender_account = str(payload.get("sender_account") or "").strip()
        result = _send_imessage(target, content, sender_account)
        status = 200 if bool(result.get("success")) else 400
        self._write_json(status, result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run host-side iMessage bridge.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    parser.add_argument(
        "--token",
        default=str(os.getenv("IMESSAGE_HOST_BRIDGE_TOKEN", "") or "").strip(),
        help="Optional shared token expected in X-Bridge-Token header.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(levelname)s: %(message)s")
    BridgeHandler.bridge_token = str(args.token or "").strip()
    server = ThreadingHTTPServer((args.host, int(args.port)), BridgeHandler)
    logger.info("iMessage host bridge listening on http://%s:%s", args.host, args.port)
    if BridgeHandler.bridge_token:
        logger.info("Bridge token auth enabled")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
