#!/usr/bin/env bash
set -euo pipefail

REPO="brh28/frappe-flash"
TAG="${1:?Usage: ./ci.sh <version>}"

docker build -t "${REPO}:${TAG}" -t "${REPO}:latest" .
echo "Tagged ${REPO}:${TAG} and ${REPO}:latest"

echo "To push:"
echo "  docker push ${REPO}:${TAG}"
echo "  docker push ${REPO}:latest"
