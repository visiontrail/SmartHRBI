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

# Verify docker is available and reachable.
if ! command -v docker &>/dev/null; then
  echo "[publish] ERROR: docker not found" >&2
  exit 1
fi

if ! docker info &>/dev/null; then
  echo "[publish] ERROR: docker daemon is not reachable" >&2
  exit 1
fi

docker_credential_helper_has_docker_hub() {
  local helper_bin="docker-credential-$1"
  local server

  command -v "$helper_bin" &>/dev/null || return 1

  for server in \
    "https://index.docker.io/v1/" \
    "index.docker.io" \
    "registry-1.docker.io" \
    "docker.io"; do
    if printf '%s' "$server" | "$helper_bin" get &>/dev/null; then
      return 0
    fi
  done

  return 1
}

docker_hub_credentials_configured() {
  local config_file="${DOCKER_CONFIG:-$HOME/.docker}/config.json"
  local helper_output helper_status helper

  [[ -r "$config_file" ]] || return 1

  if command -v python3 &>/dev/null; then
    if helper_output="$(
      python3 - "$config_file" <<'PY'
import json
import sys

servers = (
    "https://index.docker.io/v1/",
    "index.docker.io",
    "registry-1.docker.io",
    "docker.io",
)

try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        config = json.load(fh)
except Exception:
    sys.exit(1)

auths = config.get("auths") or {}
for server in servers:
    entry = auths.get(server) or {}
    if entry.get("auth") or entry.get("identitytoken"):
        sys.exit(0)

helpers = set()
cred_helpers = config.get("credHelpers") or {}
for server in servers:
    helper = cred_helpers.get(server)
    if helper:
        helpers.add(helper)

creds_store = config.get("credsStore")
if creds_store:
    helpers.add(creds_store)

if helpers:
    print("\n".join(sorted(helpers)))
    sys.exit(2)

sys.exit(1)
PY
    )"; then
      return 0
    else
      helper_status=$?
      if [[ "$helper_status" -eq 2 ]]; then
        while IFS= read -r helper; do
          [[ -n "$helper" ]] || continue
          if docker_credential_helper_has_docker_hub "$helper"; then
            return 0
          fi
        done <<<"$helper_output"
      fi
    fi
  fi

  # Fallback for machines without python3: direct auth entries are enough.
  if grep -Eq '"(https://index\.docker\.io/v1/|index\.docker\.io|registry-1\.docker\.io|docker\.io)"' "$config_file" &&
    grep -Eq '"(auth|identitytoken)"[[:space:]]*:' "$config_file"; then
    return 0
  fi

  return 1
}

if ! docker_hub_credentials_configured; then
  echo "[publish] warning: could not verify Docker Hub credentials from Docker config; continuing and docker push will authenticate." >&2
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
