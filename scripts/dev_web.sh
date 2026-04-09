#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WEB_DIR="$ROOT_DIR/apps/web"
HOST="${WEB_HOST:-127.0.0.1}"
PORT="${WEB_PORT:-3000}"
BASE_CMD=(npm run --prefix "$WEB_DIR" dev -- --hostname "$HOST" --port "$PORT")
LOG_FILE="${WEB_LOG_FILE:-}"

if [[ -n "$LOG_FILE" ]]; then
  mkdir -p "$(dirname "$LOG_FILE")"
  : >"$LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
fi

if [[ "${ONE_SHOT:-0}" == "1" ]]; then
  LOG_FILE="${LOG_FILE:-/tmp/smarthrbi-dev-web.log}"
  "${BASE_CMD[@]}" >"$LOG_FILE" 2>&1 &
  PID=$!
  trap 'kill "$PID" >/dev/null 2>&1 || true' EXIT

  for _ in $(seq 1 60); do
    if curl -fsS "http://$HOST:$PORT" >/dev/null; then
      echo "[dev-web] Health check passed: http://$HOST:$PORT"
      exit 0
    fi
    sleep 1
  done

  echo "[dev-web] Health check failed. Last logs:"
  tail -n 60 "$LOG_FILE" || true
  exit 1
fi

exec "${BASE_CMD[@]}"
