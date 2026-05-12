#!/bin/bash
# Restores a bench site from a Frappe SQL backup.
#
# Usage (from repo root):
#   ./dev/restore.sh <backup-file.sql.gz>
#   ./dev/restore.sh ../../flash/dev/erpnext/backups/clean-snapshot.sql.gz

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <backup-file.sql.gz>"
  exit 1
fi

BACKUP_FILE="$(realpath "$1")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")/frappe-bench-v15"
SITE_NAME="flashapp.me.localhost"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Error: backup file not found: $BACKUP_FILE"
  exit 1
fi

cd "$BENCH_DIR"

echo "==> Removing stale locks"
rm -f "sites/$SITE_NAME/locks/"*.lock 2>/dev/null || true

echo "==> Restoring $BACKUP_FILE"
bench --site "$SITE_NAME" restore --db-root-password admin "$BACKUP_FILE"

echo "==> Migrating"
bench --site "$SITE_NAME" migrate || {
  echo "Migration failed, retrying..."
  sleep 5
  bench --site "$SITE_NAME" migrate
}

echo ""
echo "Done."
