#!/usr/bin/env bash
# Build cognitrix-api and cognitrix-web, push both to Docker Hub.
# Usage:
#   ./scripts/docker_publish.sh                        # uses defaults
#   ./scripts/docker_publish.sh colingg 1.2.0          # custom user + version
#   DOCKER_USER=colingg TAG=1.2.0 ./scripts/docker_publish.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# ── config ──────────────────────────────────────────────────────────────────
DOCKER_USER="${1:-${DOCKER_USER:-colingg}}"
TAG="${2:-${TAG:-latest}}"
PLATFORM="${PLATFORM:-linux/amd64}"

API_IMAGE="${DOCKER_USER}/cognitrix-api:${TAG}"
WEB_IMAGE="${DOCKER_USER}/cognitrix-web:${TAG}"
# ────────────────────────────────────────────────────────────────────────────

echo "[publish] platform=${PLATFORM}  tag=${TAG}"
echo "[publish] api → ${API_IMAGE}"
echo "[publish] web → ${WEB_IMAGE}"
echo ""

# Verify docker is available and logged in
if ! command -v docker &>/dev/null; then
  echo "[publish] ERROR: docker not found" >&2
  exit 1
fi

if ! docker-credential-desktop list 2>/dev/null | grep -q "index.docker.io"; then
  echo "[publish] ERROR: not logged in to Docker Hub — run: docker login" >&2
  exit 1
fi

# Build API
echo "[publish] building API image..."
docker buildx build \
  --platform "${PLATFORM}" \
  --file apps/api/Dockerfile \
  --tag "${API_IMAGE}" \
  --load \
  .

# Build Web
echo "[publish] building Web image..."
docker buildx build \
  --platform "${PLATFORM}" \
  --file apps/web/Dockerfile \
  --tag "${WEB_IMAGE}" \
  --load \
  .

# Push
echo "[publish] pushing ${API_IMAGE}..."
docker push "${API_IMAGE}"

echo "[publish] pushing ${WEB_IMAGE}..."
docker push "${WEB_IMAGE}"

echo ""
echo "[publish] done."
echo "  docker pull ${API_IMAGE}"
echo "  docker pull ${WEB_IMAGE}"
