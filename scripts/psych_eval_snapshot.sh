#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

WINDOW="daily"
BASE_URL="${BASE_URL:-http://localhost:8000}"
OUT_ROOT="${OUT_ROOT:-$REPO_ROOT/backend/data/psych_eval}"
GHOST_ID="${GHOST_ID:-omega-7}"

usage() {
  cat <<'USAGE'
Usage:
  psych_eval_snapshot.sh [--window daily|weekly] [--base-url URL] [--out-root PATH]

Examples:
  scripts/psych_eval_snapshot.sh
  scripts/psych_eval_snapshot.sh --window weekly
  scripts/psych_eval_snapshot.sh --base-url http://localhost:8000 --out-root /tmp/omega-snaps
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --window)
      WINDOW="${2:-}"
      shift 2
      ;;
    --base-url)
      BASE_URL="${2:-}"
      shift 2
      ;;
    --out-root)
      OUT_ROOT="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ "$WINDOW" != "daily" && "$WINDOW" != "weekly" ]]; then
  echo "Invalid --window '$WINDOW' (expected daily or weekly)" >&2
  exit 2
fi

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd docker
require_cmd curl

json_pretty() {
  if command -v jq >/dev/null 2>&1; then
    jq .
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m json.tool
  else
    cat
  fi
}

cd "$REPO_ROOT"

DATE_TAG="$(date +%F)"
TS_TAG="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$OUT_ROOT/$WINDOW/$DATE_TAG/$TS_TAG"
mkdir -p "$RUN_DIR"

errors=0

capture_endpoint() {
  local endpoint="$1"
  local out_file="$2"
  local tmp_file
  tmp_file="$(mktemp)"
  if curl -fsS --max-time 20 "$BASE_URL$endpoint" >"$tmp_file"; then
    json_pretty <"$tmp_file" >"$out_file" || cat "$tmp_file" >"$out_file"
  else
    errors=$((errors + 1))
    printf '{"error":"request_failed","endpoint":"%s","captured_at":"%s"}\n' \
      "$endpoint" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$out_file"
  fi
  rm -f "$tmp_file"
}

run_sql_file() {
  local sql_file="$1"
  local out_file="$2"
  if [[ ! -f "$sql_file" ]]; then
    echo "SQL file not found: $sql_file" >&2
    errors=$((errors + 1))
    return 1
  fi
  if ! docker compose exec -T postgres psql -U ghost -d omega -v ON_ERROR_STOP=1 <"$sql_file" >"$out_file"; then
    errors=$((errors + 1))
    return 1
  fi
  return 0
}

echo "[psych-eval] capturing API snapshots to $RUN_DIR"
capture_endpoint "/health" "$RUN_DIR/api_health.json"
capture_endpoint "/somatic" "$RUN_DIR/api_somatic.json"
capture_endpoint "/ghost/iit/state" "$RUN_DIR/api_iit_state.json"
capture_endpoint "/ghost/proprio/transitions?limit=20" "$RUN_DIR/api_proprio_transitions.json"
capture_endpoint "/ghost/operator_model" "$RUN_DIR/api_operator_model.json"
capture_endpoint "/ghost/identity" "$RUN_DIR/api_identity.json"

echo "[psych-eval] running SQL reports"
run_sql_file "$REPO_ROOT/backend/daily_snapshot.sql" "$RUN_DIR/sql_daily_snapshot.txt" || true

if [[ "$WINDOW" == "daily" ]]; then
  run_sql_file "$REPO_ROOT/backend/psych_eval_daily.sql" "$RUN_DIR/sql_psych_eval_daily.txt" || true
else
  run_sql_file "$REPO_ROOT/backend/psych_eval_weekly.sql" "$RUN_DIR/sql_psych_eval_weekly.txt" || true
fi

SUMMARY_FILE="$RUN_DIR/summary.txt"
{
  echo "OMEGA4 Psychological Evaluation Snapshot"
  echo "run_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "window=$WINDOW"
  echo "base_url=$BASE_URL"
  echo "ghost_id=$GHOST_ID"
  echo "run_dir=$RUN_DIR"
  echo "errors=$errors"
  echo
  if command -v jq >/dev/null 2>&1; then
    if [[ -f "$RUN_DIR/api_somatic.json" ]]; then
      echo "[somatic]"
      jq -r '"arousal=\(.arousal) stress=\(.stress) anxiety=\(.anxiety) coherence=\(.coherence) gate=\(.gate_state) fatigue=\(.fatigue_index) dream_pressure=\(.dream_pressure)"' \
        "$RUN_DIR/api_somatic.json" 2>/dev/null || true
      echo
    fi
    if [[ -f "$RUN_DIR/api_iit_state.json" ]]; then
      echo "[iit]"
      jq -r '"mode=\(.mode) backend=\(.backend) completeness=\(.substrate_completeness_score) degradation=\(.advisory.degradation_list // [])"' \
        "$RUN_DIR/api_iit_state.json" 2>/dev/null || true
      echo
    fi
  fi
  echo "Artifacts:"
  find "$RUN_DIR" -maxdepth 1 -type f -print | sed "s|$RUN_DIR/|  - |"
} >"$SUMMARY_FILE"

echo "[psych-eval] complete: $SUMMARY_FILE"
if [[ "$errors" -gt 0 ]]; then
  echo "[psych-eval] completed with $errors error(s)" >&2
  exit 1
fi
