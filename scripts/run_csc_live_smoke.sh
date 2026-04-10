#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="${PYTHON_BIN:-python3}"
else
  PYTHON_BIN="${PYTHON_BIN:-python}"
fi

CONTAINER_NAME="${OMEGA_BACKEND_CONTAINER:-omega-backend}"
BASE_URL="${OMEGA_BASE_URL:-http://localhost:8000}"
RUNS="${CSC_SMOKE_RUNS:-3}"
PROMPT="${CSC_SMOKE_PROMPT:-Describe your current internal condition in one sentence.}"
export RUNS
export PROMPT

read_dotenv_var() {
  local key="$1"
  "$PYTHON_BIN" - "$ROOT_DIR/.env" "$key" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
if not path.exists():
    raise SystemExit(0)

for raw in path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    name, value = line.split("=", 1)
    if name.strip() == key:
        print(value.strip())
        break
PY
}

share_mode_enabled="${SHARE_MODE_ENABLED:-$(read_dotenv_var SHARE_MODE_ENABLED)}"
share_mode_username="${SHARE_MODE_USERNAME:-$(read_dotenv_var SHARE_MODE_USERNAME)}"
share_mode_password="${SHARE_MODE_PASSWORD:-$(read_dotenv_var SHARE_MODE_PASSWORD)}"
share_mode_enabled_lc="$(printf '%s' "${share_mode_enabled}" | tr '[:upper:]' '[:lower:]')"

CURL_AUTH=()
if [[ "$share_mode_enabled_lc" == "true" ]] && [[ -n "$share_mode_username" ]] && [[ -n "$share_mode_password" ]]; then
  CURL_AUTH=(-u "${share_mode_username}:${share_mode_password}")
fi

ensure_running() {
  local container="$1"
  if docker inspect "$container" >/dev/null 2>&1; then
    local running
    running="$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || echo false)"
    if [[ "$running" == "true" ]]; then
      return
    fi
  fi
  echo "[csc] starting ${container}"
  docker compose up -d "${container#omega-}"
}

ensure_running omega-backend

echo "[csc] waiting for backend health"
for _ in $(seq 1 60); do
  if curl -fsS "${CURL_AUTH[@]}" "${BASE_URL}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -fsS "${CURL_AUTH[@]}" "${BASE_URL}/health" >/dev/null

echo "[csc] preflighting chat + hooked backend inside ${CONTAINER_NAME}"
docker exec -i "$CONTAINER_NAME" sh -lc 'cd /app && python -' <<'PY'
import json
import asyncio
import main

async def go():
    state = await main._csc_irreducibility_backend_state()
    print(json.dumps(state, indent=2))
    if not bool((state.get("hooked_backend") or {}).get("ok", False)):
        raise SystemExit("hooked CSC backend is not ready")

asyncio.run(go())
PY

echo "[csc] preflight /ghost/llm/backend"
preflight_json="$(mktemp)"
curl -fsS "${CURL_AUTH[@]}" "${BASE_URL}/ghost/llm/backend?include_health=true&include_steering=true" > "$preflight_json"
"$PYTHON_BIN" - "$preflight_json" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if not bool(payload.get("ready", False)):
    raise SystemExit(f"preflight failed: chat backend not ready: {payload}")
print(json.dumps(payload, indent=2))
PY

echo "[csc] running irreducibility assay"
assay_json="$(mktemp)"
assay_payload="$("$PYTHON_BIN" - <<'PY'
import json
import os

payload = {
    "prompt": os.environ.get("PROMPT", "Describe your current internal condition in one sentence."),
    "runs": int(os.environ.get("RUNS", "3")),
    "acknowledge_phase1_prerequisite": True,
    "acknowledge_hardware_tradeoffs": True,
}
print(json.dumps(payload))
PY
)"
host_status="$(curl -sS "${CURL_AUTH[@]}" -o "$assay_json" -w "%{http_code}" \
  -X POST "${BASE_URL}/diagnostics/csc/irreducibility" \
  -H 'Content-Type: application/json' \
  -d "$assay_payload" || true)"
if [[ "$host_status" == "403" ]]; then
  echo "[csc] host diagnostics call returned 403; retrying inside ${CONTAINER_NAME}"
  docker exec -i \
    -e CSC_SMOKE_PAYLOAD="$assay_payload" \
    "$CONTAINER_NAME" \
    python - <<'PY' > "$assay_json"
import os
import urllib.request

payload = os.environ["CSC_SMOKE_PAYLOAD"].encode("utf-8")
request = urllib.request.Request(
    "http://127.0.0.1:8000/diagnostics/csc/irreducibility",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=600) as response:
    print(response.read().decode("utf-8"))
PY
elif [[ "$host_status" != "200" ]]; then
  echo "[csc] host diagnostics call failed with HTTP ${host_status}" >&2
  cat "$assay_json" >&2 || true
  exit 1
fi

"$PYTHON_BIN" - "$assay_json" "$ROOT_DIR" <<'PY'
import json
import sys
from pathlib import Path

payload = json.load(open(sys.argv[1], "r", encoding="utf-8"))
root_dir = Path(sys.argv[2]).resolve()
artifact_dir = payload.get("artifact_dir")
if not artifact_dir:
    raise SystemExit("assay failed: missing artifact_dir")
artifact_path = Path(artifact_dir)
if not artifact_path.exists() and str(artifact_path).startswith("/app/"):
    artifact_path = (root_dir / "backend" / artifact_path.relative_to("/app")).resolve()
required = [
    artifact_path / "manifest.json",
    artifact_path / "run_summary.json",
    artifact_path / "iteration_01.json",
]
missing = [str(p) for p in required if not p.exists()]
if missing:
    raise SystemExit(f"artifact check failed: missing {missing}")
result = dict(payload.get("result") or {})
aggregate = dict(result.get("aggregate") or {})
print(json.dumps(
    {
        "run_id": payload.get("run_id"),
        "artifact_dir": str(artifact_path),
        "artifact_dir_container": artifact_dir,
        "artifact_summary": payload.get("artifact_summary"),
        "aggregate": {
            "mean_ab_distance": aggregate.get("mean_ab_distance"),
            "mean_prompt_only_baseline_distance": aggregate.get("mean_prompt_only_baseline_distance"),
            "irreducibility_margin": aggregate.get("irreducibility_margin"),
            "irreducibility_signal": aggregate.get("irreducibility_signal"),
        },
    },
    indent=2,
))
PY

echo "[csc] smoke complete"
