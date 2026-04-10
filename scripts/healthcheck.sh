#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
BASE_URL="${BASE_URL:-http://localhost:8000}"

get_env_value() {
  local key="$1"
  if [[ ! -f "$ENV_FILE" ]]; then
    return 1
  fi
  local line
  line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    return 1
  fi
  local val="${line#*=}"
  val="${val%\"}"
  val="${val#\"}"
  val="${val%\'}"
  val="${val#\'}"
  printf "%s" "$val"
}

SHARE_ENABLED="$(get_env_value "SHARE_MODE_ENABLED" || true)"
SHARE_USER="$(get_env_value "SHARE_MODE_USERNAME" || true)"
SHARE_PASS="$(get_env_value "SHARE_MODE_PASSWORD" || true)"
SHARE_ENABLED_LC="$(printf "%s" "$SHARE_ENABLED" | tr '[:upper:]' '[:lower:]')"

declare -a AUTH_ARGS=()
if [[ "$SHARE_ENABLED_LC" == "true" && -n "$SHARE_USER" && -n "$SHARE_PASS" ]]; then
  AUTH_ARGS=(-u "${SHARE_USER}:${SHARE_PASS}")
fi

check_endpoint() {
  local path="$1"
  local expected="${2:-200}"
  local code
  code="$(curl -sS "${AUTH_ARGS[@]}" -o /dev/null -w "%{http_code}" "${BASE_URL}${path}")"
  if [[ "$code" == "$expected" ]]; then
    echo "PASS ${path} -> ${code}"
  else
    echo "FAIL ${path} -> ${code} (expected ${expected})"
    return 1
  fi
}

echo "OMEGA healthcheck against ${BASE_URL}"
check_endpoint "/health" "200"
check_endpoint "/ghost/self/architecture" "200"
check_endpoint "/ghost/autonomy/state" "200"

echo "PASS all core health checks"
