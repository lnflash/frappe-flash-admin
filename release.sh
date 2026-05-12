#!/usr/bin/env bash
set -euo pipefail

BUMP="${1:?Usage: ./release.sh <major|minor|patch>}"

LAST_TAG="$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//')"
if [[ -z "$LAST_TAG" ]]; then
  echo "Error: no existing tags found." >&2
  exit 1
fi

IFS='.' read -r MAJOR MINOR PATCH <<< "$LAST_TAG"

case "$BUMP" in
  major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
  minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
  patch) PATCH=$((PATCH + 1)) ;;
  *) echo "Error: bump must be major, minor, or patch." >&2; exit 1 ;;
esac

NEW_TAG="v${MAJOR}.${MINOR}.${PATCH}"

echo "Last tag: v${LAST_TAG}"
echo "New tag:  ${NEW_TAG}"
read -rp "Proceed? [y/N] " CONFIRM
[[ "$CONFIRM" =~ ^[Yy]$ ]] || exit 0

git tag "$NEW_TAG"
git push origin "$NEW_TAG"

./ci.sh
