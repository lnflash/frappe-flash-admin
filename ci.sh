#!/usr/bin/env bash
set -euo pipefail

REPO="brh28/frappe-flash"
TAG="${1:?Usage: ./ci.sh <version>}"

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --push \
  -t "${REPO}:${TAG}" \
  .
echo "Built and pushed ${REPO}:${TAG} (amd64, arm64)"

docker buildx imagetools create -t "${REPO}:latest" "${REPO}:${TAG}"
echo "Tagged ${REPO}:latest from ${REPO}:${TAG}"

