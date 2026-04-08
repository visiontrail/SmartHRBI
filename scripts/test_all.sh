#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

bash scripts/lint.sh
RUN_WEB_TESTS=1 bash scripts/test.sh
bash scripts/build.sh
bash scripts/smoke_local.sh

if command -v docker >/dev/null 2>&1; then
  if [[ "${RUN_DOCKER_SMOKE:-1}" == "1" ]]; then
    bash scripts/smoke_docker.sh
  else
    echo "[test-all] Docker smoke skipped by RUN_DOCKER_SMOKE=0"
  fi
else
  echo "[test-all] Docker not installed, skipped smoke-docker"
fi

echo "[test-all] Completed"
