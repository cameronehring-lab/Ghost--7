#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.omega4.docker-recovery-watchdog"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LAUNCHCTL_BIN="${LAUNCHCTL_BIN:-$(command -v launchctl || true)}"
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${PLIST_DIR}/${LABEL}.plist"
STATE_DIR="$("${PYTHON_BIN}" - <<'PY'
import os
state_dir = os.getenv("OMEGA4_DOCKER_RECOVERY_STATE_DIR", "").strip()
print(state_dir or "/tmp/omega4_docker_recovery")
PY
)"
STDOUT_LOG="${STATE_DIR}/launchd.out.log"
STDERR_LOG="${STATE_DIR}/launchd.err.log"
WATCHDOG_SCRIPT="${ROOT_DIR}/scripts/docker_recovery_watchdog.py"

ensure_prereqs() {
  command -v "${PYTHON_BIN}" >/dev/null 2>&1 || {
    echo "python interpreter not found: ${PYTHON_BIN}" >&2
    exit 1
  }
  [[ -f "${WATCHDOG_SCRIPT}" ]] || {
    echo "watchdog script not found: ${WATCHDOG_SCRIPT}" >&2
    exit 1
  }
}

render_plist() {
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>${WATCHDOG_SCRIPT}</string>
    <string>watch</string>
    <string>--interval-seconds</string>
    <string>20</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OMEGA4_DOCKER_RECOVERY_STATE_DIR</key>
    <string>${STATE_DIR}</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${STDOUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${STDERR_LOG}</string>
</dict>
</plist>
EOF
}

install_agent() {
  ensure_prereqs
  mkdir -p "${PLIST_DIR}" "${STATE_DIR}"
  render_plist > "${PLIST_PATH}"
  if [[ -n "${LAUNCHCTL_BIN}" ]]; then
    "${LAUNCHCTL_BIN}" bootout "gui/${UID}" "${PLIST_PATH}" >/dev/null 2>&1 || true
    "${LAUNCHCTL_BIN}" bootstrap "gui/${UID}" "${PLIST_PATH}"
    "${LAUNCHCTL_BIN}" enable "gui/${UID}/${LABEL}" >/dev/null 2>&1 || true
    "${LAUNCHCTL_BIN}" kickstart -k "gui/${UID}/${LABEL}" >/dev/null 2>&1 || true
  fi
  echo "installed label=${LABEL} plist=${PLIST_PATH}"
}

uninstall_agent() {
  if [[ -n "${LAUNCHCTL_BIN}" ]]; then
    "${LAUNCHCTL_BIN}" bootout "gui/${UID}" "${PLIST_PATH}" >/dev/null 2>&1 || true
    "${LAUNCHCTL_BIN}" disable "gui/${UID}/${LABEL}" >/dev/null 2>&1 || true
  fi
  rm -f "${PLIST_PATH}"
  echo "uninstalled label=${LABEL} plist=${PLIST_PATH}"
}

status_agent() {
  local installed="false"
  local loaded="false"
  if [[ -f "${PLIST_PATH}" ]]; then
    installed="true"
  fi
  if [[ -n "${LAUNCHCTL_BIN}" ]] && "${LAUNCHCTL_BIN}" print "gui/${UID}/${LABEL}" >/dev/null 2>&1; then
    loaded="true"
  fi
  echo "installed=${installed} loaded=${loaded} label=${LABEL} plist=${PLIST_PATH} state_dir=${STATE_DIR}"
}

main() {
  local command="${1:-status}"
  case "${command}" in
    install)
      install_agent
      ;;
    uninstall)
      uninstall_agent
      ;;
    status)
      status_agent
      ;;
    *)
      echo "usage: $0 {install|uninstall|status}" >&2
      exit 1
      ;;
  esac
}

main "${1:-status}"
