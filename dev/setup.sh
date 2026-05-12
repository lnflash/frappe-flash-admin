#!/bin/bash
# Bootstraps a local frappe bench for developing admin_panel.
#
# Prerequisites:
#   - bench CLI installed (pip install frappe-bench)
#   - Docker running with: docker compose up -d (from this repo root)
#
# Usage (from repo root):
#   ./dev/setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
BENCH_DIR="$(dirname "$REPO_DIR")/frappe-bench-v15"
SITE_NAME="flashapp.me.localhost"

echo "==> Initialising bench at $BENCH_DIR"
bench init \
  --frappe-branch version-15 \
  --skip-redis-config-generation \
  "$BENCH_DIR"

cd "$BENCH_DIR"

echo "==> Updating Procfile (remove local redis, fix port)"
sed -i '/^redis_/d' Procfile
sed -i 's/bench serve  *--port [0-9]*/bench serve --port 8000/' Procfile

echo "==> Getting ERPNext v15"
bench get-app erpnext --branch version-15

echo "==> Linking admin_panel from repo"
ln -sf "$REPO_DIR/admin_panel" apps/admin_panel
printf "\nadmin_panel\n" >> sites/apps.txt
"$BENCH_DIR/env/bin/pip" install -e "$REPO_DIR" --quiet

echo "==> Configuring bench"
bench set-config -g db_host "127.0.0.1"
bench set-config -gp db_port 3307
bench set-config -g redis_cache "redis://127.0.0.1:6379/1"
bench set-config -g redis_queue "redis://127.0.0.1:6379/2"
bench set-config -g redis_socketio "redis://127.0.0.1:6379/2"
bench set-config -g flash_admin_api_url "http://localhost:4002/admin/graphql"
bench set-config -g admin_api_key "not-so-secret"
bench set-config -gp developer_mode 1

echo "==> Creating site $SITE_NAME"
bench new-site "$SITE_NAME" \
  --db-root-username root \
  --db-root-password admin \
  --admin-password admin \
  --install-app erpnext \
  --install-app admin_panel \
  --mariadb-user-host-login-scope='%'

echo ""
echo "Done. Start the bench with: cd $BENCH_DIR && bench start"
