#!/usr/bin/env bash
# ============================================================
# BEACON COMPUTING INITIATIVE
# Component: A440 Quarter Lab v0.1.2 Safe Staged Start
# Developer Seal: CJB-DEV-2026
# Scope: Synthetic research only. No unrelated container changes.
# ============================================================
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="bci-a440-quarter-lab"
QUARTER_SECONDS="${QUARTER_SECONDS:-300}"
cd "$ROOT"

# Execute if and only if source integrity and runtime constraints pass.
if ! [[ "$QUARTER_SECONDS" =~ ^[0-9]+$ ]] || (( QUARTER_SECONDS < 1 )); then
  echo '[BCI][BLOCKED] QUARTER_SECONDS must be a positive integer.' >&2
  exit 1
fi
for executable in docker python3 sha256sum; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    echo "[BCI][BLOCKED] Missing required executable: $executable" >&2
    exit 1
  fi
done
sha256sum -c SHA256SUMS

TEST_STATE="$(mktemp -d "${TMPDIR:-/tmp}/a440-release-test-XXXXXXXX")"
trap 'rm -rf -- "$TEST_STATE"' EXIT
python3 -m py_compile model.py endpoint.py test_lab.py generate_compose.py
A440_STATE_DIR="$TEST_STATE" python3 test_lab.py

docker info >/dev/null
docker compose version
compose() {
  QUARTER_SECONDS="$QUARTER_SECONDS" docker compose \
    -p "$PROJECT" -f compose.yaml -f compose.safe.yaml "$@"
}
compose config -q
[[ "$(compose config --services | wc -l)" -eq 21 ]] || {
  echo '[BCI][BLOCKED] Expected exactly 20 endpoints and one model.' >&2
  exit 1
}

# Never adopt or replace an already-running instance of this research lab.
if [[ -n "$(compose ps -a -q)" ]]; then
  echo '[BCI][BLOCKED] Existing lab instance found; preserving it unchanged.' >&2
  compose ps -a
  exit 1
fi

# Host port must be available before starting a model.
python3 - <<'PY'
import socket
s=socket.socket()
try:
    s.bind(('127.0.0.1',8080))
except OSError as e:
    raise SystemExit(f'[BCI][BLOCKED] TCP 127.0.0.1:8080 is unavailable: {e}')
finally:
    s.close()
PY

echo '[BCI] Building one shared lab image.'
compose build model

for begin in 1 6 11 16; do
  services=()
  for ((i=begin; i<begin+5; i++)); do
    printf -v service 'endpoint-%02d' "$i"
    services+=("$service")
  done
  compose up --no-build --no-deps -d "${services[@]}"
  for service in "${services[@]}"; do
    healthy=0
    for attempt in $(seq 1 20); do
      if compose exec -T "$service" python -c \
        "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)); assert d['ok']" \
        >/dev/null 2>&1; then
        healthy=1
        break
      fi
      sleep 1
    done
    if (( healthy != 1 )); then
      echo "[BCI][BLOCKED] Unhealthy endpoint: $service" >&2
      compose ps -a
      exit 1
    fi
    echo "[BCI][PASS] $service"
  done
done

echo '[BCI] All 20 endpoint services are responsive; starting model.'
compose up --no-build --no-deps -d model

ready=0
for attempt in $(seq 1 90); do
  if compose exec -T model python -c \
      "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8080/ask',timeout=3)); assert d.get('status')=='running' and d.get('required_source_contributions')==20" \
      >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if (( ready != 1 )); then
  echo '[BCI][BLOCKED] Model did not report an initialized baseline.' >&2
  compose logs --tail=80 model
  exit 1
fi
compose exec -T model python -c \
  "import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen('http://127.0.0.1:8080/ask',timeout=5)),indent=2))"
echo '[BCI][PASS] Staged initialization of 20 synthetic endpoints and A440.'
echo '[BCI] Interval: one simulated fiscal quarter every 300 seconds by default.'
echo '[BCI] Developer Seal: CJB-DEV-2026'
