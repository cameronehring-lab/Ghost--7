#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SNAPSHOT_SCRIPT="$REPO_ROOT/scripts/psych_eval_snapshot.sh"
LOG_DIR="$REPO_ROOT/logs/psych_eval"

DAILY_CRON="${DAILY_CRON:-0 8 * * *}"
WEEKLY_CRON="${WEEKLY_CRON:-15 8 * * 1}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
UNINSTALL="0"

usage() {
  cat <<'USAGE'
Usage:
  install_psych_eval_cron.sh [--daily-cron "<expr>"] [--weekly-cron "<expr>"] [--base-url URL] [--uninstall]

Defaults:
  daily  = "0 8 * * *"    (08:00 local time every day)
  weekly = "15 8 * * 1"   (08:15 local time every Monday)

Examples:
  scripts/install_psych_eval_cron.sh
  scripts/install_psych_eval_cron.sh --daily-cron "30 7 * * *"
  scripts/install_psych_eval_cron.sh --uninstall
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --daily-cron)
      DAILY_CRON="${2:-}"
      shift 2
      ;;
    --weekly-cron)
      WEEKLY_CRON="${2:-}"
      shift 2
      ;;
    --base-url)
      BASE_URL="${2:-}"
      shift 2
      ;;
    --uninstall)
      UNINSTALL="1"
      shift
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

if ! command -v crontab >/dev/null 2>&1; then
  echo "crontab command not found" >&2
  exit 1
fi

if [[ ! -x "$SNAPSHOT_SCRIPT" ]]; then
  chmod +x "$SNAPSHOT_SCRIPT"
fi
mkdir -p "$LOG_DIR"

BEGIN_MARK="# >>> OMEGA4 psych-eval >>>"
END_MARK="# <<< OMEGA4 psych-eval <<<"

existing="$(crontab -l 2>/dev/null || true)"
cleaned="$(
  printf "%s\n" "$existing" | awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
    $0 == b { skip=1; next }
    $0 == e { skip=0; next }
    !skip { print }
  '
)"

if [[ "$UNINSTALL" == "1" ]]; then
  printf "%s\n" "$cleaned" | crontab -
  echo "Removed OMEGA4 psych-eval cron block."
  exit 0
fi

daily_cmd="$DAILY_CRON cd $REPO_ROOT && $SNAPSHOT_SCRIPT --window daily --base-url $BASE_URL >> $LOG_DIR/daily.log 2>&1"
weekly_cmd="$WEEKLY_CRON cd $REPO_ROOT && $SNAPSHOT_SCRIPT --window weekly --base-url $BASE_URL >> $LOG_DIR/weekly.log 2>&1"

{
  if [[ -n "$cleaned" ]]; then
    printf "%s\n" "$cleaned"
  fi
  echo "$BEGIN_MARK"
  echo "$daily_cmd"
  echo "$weekly_cmd"
  echo "$END_MARK"
} | crontab -

echo "Installed OMEGA4 psych-eval cron jobs:"
echo "  daily : $DAILY_CRON"
echo "  weekly: $WEEKLY_CRON"
echo "Logs:"
echo "  $LOG_DIR/daily.log"
echo "  $LOG_DIR/weekly.log"

