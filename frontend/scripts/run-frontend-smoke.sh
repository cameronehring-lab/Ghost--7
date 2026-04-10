#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PW_TMP=$(mktemp -d)
cleanup() {
  rm -rf "$PW_TMP"
}
trap cleanup EXIT

npm --prefix "$PW_TMP" install playwright@1.58.2 --silent

NODE_PATH="$PW_TMP/node_modules" node "$SCRIPT_DIR/frontend-smoke.js" "$@"
