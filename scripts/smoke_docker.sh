#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "[smoke-docker] Docker is not installed"
  exit 1
fi

API_BASE_URL="${DOCKER_API_BASE_URL:-http://127.0.0.1:8000}"
WEB_BASE_URL="${DOCKER_WEB_BASE_URL:-http://127.0.0.1:3000}"

cleanup() {
  if [[ "${KEEP_DOCKER_STACK:-0}" != "1" ]]; then
    docker compose down --remove-orphans >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

docker compose up -d --build

wait_http_ok() {
  local target="$1"
  local max_tries="$2"
  for _ in $(seq 1 "$max_tries"); do
    if curl -fsS "$target" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

if ! wait_http_ok "${API_BASE_URL}/healthz" 90; then
  echo "[smoke-docker] API health check failed"
  docker compose ps
  docker compose logs api --tail=200 || true
  exit 1
fi

if ! wait_http_ok "${WEB_BASE_URL}" 120; then
  echo "[smoke-docker] Web health check failed"
  docker compose ps
  docker compose logs web --tail=200 || true
  exit 1
fi

.venv/bin/python tests/smoke/run_smoke_flow.py \
  --api-base-url "$API_BASE_URL" \
  --web-base-url "$WEB_BASE_URL"

echo "[smoke-docker] Completed"
