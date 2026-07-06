#!/usr/bin/env bash
set -euo pipefail

# Local fallback only — the publish-image GitHub workflow is the normal path
# (builds on v* tag push). Requires a PAT with packages:write for ghcr login.
REPO="ghcr.io/lnflash/frappe-flash"

TAG="$(git describe --tags --exact-match HEAD 2>/dev/null)" || {
  echo "Error: HEAD is not tagged. Tag the commit first (e.g. git tag v1.2.0)." >&2
  exit 1
}

docker buildx build \
  --no-cache \
  --platform linux/amd64,linux/arm64 \
  --push \
  -t "${REPO}:${TAG}" \
  .
echo "Built and pushed ${REPO}:${TAG} (amd64, arm64)"

docker buildx imagetools create -t "${REPO}:latest" "${REPO}:${TAG}"
echo "Tagged ${REPO}:latest from ${REPO}:${TAG}"

