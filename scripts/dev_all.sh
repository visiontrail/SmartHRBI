#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

bash scripts/ensure_postgres.sh

bash scripts/dev_api.sh &
API_PID=$!

bash scripts/dev_web.sh &
WEB_PID=$!

cleanup() {
  kill "$API_PID" "$WEB_PID" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

EXIT_STATUS=0
while true; do
  if ! kill -0 "$API_PID" >/dev/null 2>&1; then
    wait "$API_PID" || EXIT_STATUS=$?
    break
  fi
  if ! kill -0 "$WEB_PID" >/dev/null 2>&1; then
    wait "$WEB_PID" || EXIT_STATUS=$?
    break
  fi
  sleep 1
done

exit "$EXIT_STATUS"
