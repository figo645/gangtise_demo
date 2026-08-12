#!/usr/bin/env bash
set -euo pipefail

# Mac-side release entrypoint. It synchronizes the local PostgreSQL database
# into a validated remote staging database, then atomically swaps databases.
# The remote host must already have PostgreSQL/pgvector and this repository.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORK_DIR="${DEPLOY_WORK_DIR:-${ROOT_DIR}/.deploy}"
DUMP_FILE="${WORK_DIR}/sprint_dashboard_${STAMP}.dump"

LOCAL_CREDENTIALS_FILE="${LOCAL_POSTGRES_CREDENTIALS_FILE:-${HOME}/.gangtise_postgres_credentials}"
if [[ -f "$LOCAL_CREDENTIALS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$LOCAL_CREDENTIALS_FILE"
  set +a
fi

LOCAL_HOST="${LOCAL_PGHOST:-${LOCAL_POSTGRES_HOST:-127.0.0.1}}"
LOCAL_PORT="${LOCAL_PGPORT:-${LOCAL_POSTGRES_PORT:-5432}}"
LOCAL_DB="${LOCAL_PGDATABASE:-${LOCAL_POSTGRES_DB:-sprint_dashboard}}"
LOCAL_USER="${LOCAL_PGUSER:-${LOCAL_POSTGRES_USER:-gangtise_app}}"
LOCAL_PASSWORD="${LOCAL_PGPASSWORD:-${LOCAL_POSTGRES_PASSWORD:-}}"

PROD_SSH_TARGET="${PROD_SSH_TARGET:-}"
PROD_APP_DIR="${PROD_APP_DIR:-/opt/devsource/gangtise_demo}"
PROD_DB_NAME="${PROD_DB_NAME:-sprint_dashboard}"
PROD_DB_USER="${PROD_DB_USER:-gangtise_app}"
PROD_DB_HOST="${PROD_DB_HOST:-127.0.0.1}"
PROD_DB_PORT="${PROD_DB_PORT:-5432}"
PROD_BRANCH="${PROD_BRANCH:-$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)}"
PROD_CREDENTIALS_FILE="${PROD_CREDENTIALS_FILE:-/root/gangtise_postgres_credentials}"

usage() {
  cat <<'EOF'
Usage:
  PROD_SSH_TARGET=root@server ./scripts/deploy_sync_production.sh

Required:
  PROD_SSH_TARGET       SSH target, for example root@1.2.3.4

Before running:
  Commit and push the code branch that the server must pull. This command
  synchronizes the local PostgreSQL database; it does not migrate SQLite.

Useful overrides:
  LOCAL_PGHOST LOCAL_PGPORT LOCAL_PGDATABASE LOCAL_PGUSER LOCAL_PGPASSWORD
  LOCAL_POSTGRES_CREDENTIALS_FILE  defaults to ~/.gangtise_postgres_credentials
  PROD_APP_DIR PROD_DB_NAME PROD_DB_USER PROD_DB_HOST PROD_DB_PORT PROD_BRANCH
  PROD_CREDENTIALS_FILE=...       remote credentials file
  CONFIRM_PRODUCTION_SYNC=YES     skip the interactive confirmation
  KEEP_LOCAL_DUMP=1                keep the local pg_dump file
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then usage; exit 0; fi
if [[ -z "$PROD_SSH_TARGET" ]]; then
  echo "PROD_SSH_TARGET is required. Use --help for an example." >&2
  exit 2
fi
if [[ -z "$PROD_BRANCH" ]]; then
  echo "Could not determine the local git branch; set PROD_BRANCH explicitly." >&2
  exit 2
fi
for command in pg_dump pg_restore psql pg_isready ssh scp; do
  command -v "$command" >/dev/null 2>&1 || { echo "Required command not found: $command" >&2; exit 1; }
done

if ! pg_isready -h "$LOCAL_HOST" -p "$LOCAL_PORT" >/dev/null 2>&1; then
  echo "Local PostgreSQL is not ready at ${LOCAL_HOST}:${LOCAL_PORT}." >&2
  exit 1
fi
export PGPASSWORD="$LOCAL_PASSWORD"
if ! psql -w -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" -Atqc \
  "SELECT 1 FROM pg_extension WHERE extname = 'vector'" | grep -q '^1$'; then
  echo "Local database ${LOCAL_DB} does not have pgvector enabled." >&2
  exit 1
fi

mkdir -p "$WORK_DIR"
echo "==> Dumping local PostgreSQL ${LOCAL_DB} (${LOCAL_HOST}:${LOCAL_PORT})"
pg_dump -w -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" \
  --format=custom --no-owner --no-acl --file "$DUMP_FILE"
unset PGPASSWORD

if [[ "${CONFIRM_PRODUCTION_SYNC:-}" != "YES" ]]; then
  printf 'This will replace the production database after validation. Continue? [y/N] '
  read -r answer
  [[ "$answer" == "y" || "$answer" == "Y" ]] || { echo "Cancelled."; exit 0; }
fi

echo "==> Uploading dump to ${PROD_SSH_TARGET}"
scp "$DUMP_FILE" "${PROD_SSH_TARGET}:/tmp/$(basename "$DUMP_FILE")"

echo "==> Pulling code and restoring validated production database"
ssh "$PROD_SSH_TARGET" bash -s -- \
  "$PROD_APP_DIR" "$PROD_BRANCH" "$PROD_DB_NAME" "$PROD_DB_USER" \
  "$PROD_DB_HOST" "$PROD_DB_PORT" "$PROD_CREDENTIALS_FILE" \
  "/tmp/$(basename "$DUMP_FILE")" "$STAMP" <<'REMOTE_SCRIPT'
set -euo pipefail

APP_DIR="$1"
BRANCH="$2"
DB_NAME="$3"
DB_USER="$4"
DB_HOST="$5"
DB_PORT="$6"
CREDENTIALS_FILE="$7"
DUMP_FILE="$8"
STAMP="$9"
STAGING_DB="${DB_NAME}_import_${STAMP}"
BACKUP_DB="${DB_NAME}_backup_${STAMP}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Production deployment must connect as root so PostgreSQL can create, validate, and switch databases." >&2
  exit 1
fi
ADMIN=(runuser -u postgres --)
command -v psql >/dev/null 2>&1 || { echo "psql is not installed on production" >&2; exit 1; }
command -v pg_restore >/dev/null 2>&1 || { echo "pg_restore is not installed on production" >&2; exit 1; }
[[ -d "$APP_DIR/.git" ]] || { echo "Git repository not found: $APP_DIR" >&2; exit 1; }

if [[ -f "$CREDENTIALS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$CREDENTIALS_FILE"
  set +a
fi
APP_PASSWORD="${APP_DB_PASSWORD:-${POSTGRES_PASSWORD:-}}"
[[ -n "$APP_PASSWORD" ]] || { echo "Production database password is missing from ${CREDENTIALS_FILE}" >&2; exit 1; }
export PGPASSWORD="$APP_PASSWORD"

PG=(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER")
# The OS postgres account uses the local Unix socket, avoiding a dependency on
# a separately configured password for the PostgreSQL superuser.
ADMIN_PG=("${ADMIN[@]}" psql -p "$DB_PORT" -U postgres)
admin_sql() { "${ADMIN_PG[@]}" -v ON_ERROR_STOP=1 "$@"; }

"${ADMIN[@]}" pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null
if ! admin_sql -d postgres -Atqc "SELECT 1 FROM pg_available_extensions WHERE name='vector'" | grep -q '^1$'; then
  echo "pgvector is not installed on production PostgreSQL" >&2
  exit 1
fi

git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
if admin_sql -d postgres -Atqc "SELECT 1 FROM pg_database WHERE datname='${STAGING_DB}'" | grep -q '^1$'; then
  admin_sql -d postgres -c "DROP DATABASE \"${STAGING_DB}\" WITH (FORCE);" >/dev/null
fi
admin_sql -d postgres -c "CREATE DATABASE \"${STAGING_DB}\" OWNER \"${DB_USER}\";"
admin_sql -d "$STAGING_DB" -c 'CREATE EXTENSION IF NOT EXISTS vector;' >/dev/null

echo "==> Restoring into ${STAGING_DB}"
"${ADMIN[@]}" pg_restore -p "$DB_PORT" -U postgres -d "$STAGING_DB" \
  --format=custom --no-owner --no-acl --exit-on-error "$DUMP_FILE"
admin_sql -d "$STAGING_DB" -c "GRANT USAGE ON SCHEMA public TO \"${DB_USER}\"; GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO \"${DB_USER}\"; GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO \"${DB_USER}\";"

PGHOST="$DB_HOST" PGPORT="$DB_PORT" PGDATABASE="$STAGING_DB" PGUSER="$DB_USER" PGPASSWORD="$APP_PASSWORD" \
  "$APP_DIR/scripts/apply_postgres_updates.sh"

VECTOR_OK="$(admin_sql -d "$STAGING_DB" -Atqc "SELECT count(*) FROM pg_extension WHERE extname='vector'")"
SNAPSHOT_ITEMS="$(admin_sql -d "$STAGING_DB" -Atqc "SELECT COALESCE(SUM(jsonb_array_length(COALESCE(payload_json::jsonb->'items','[]'::jsonb))),0) FROM market_snapshot_payloads WHERE snapshot_type IN ('market_overview','market_sector_overview')")"
SECTOR_COUNT="$(admin_sql -d "$STAGING_DB" -Atqc "SELECT jsonb_array_length(setting_value::jsonb->'items') FROM app_settings WHERE setting_key='master_data:market_sector_catalog:shenwan_level1'")"
INDEX_COUNT="$(admin_sql -d "$STAGING_DB" -Atqc "SELECT jsonb_array_length(setting_value::jsonb->'items') FROM app_settings WHERE setting_key='master_data:market_index_catalog:standard'")"
[[ "$VECTOR_OK" == "1" && "$SNAPSHOT_ITEMS" -gt 0 && "$SECTOR_COUNT" -gt 0 && "$INDEX_COUNT" -gt 0 ]] || {
  echo "Validation failed: vector=${VECTOR_OK}, snapshots=${SNAPSHOT_ITEMS}, sectors=${SECTOR_COUNT}, indices=${INDEX_COUNT}" >&2
  exit 1
}
echo "Validated: vector=${VECTOR_OK}, snapshots=${SNAPSHOT_ITEMS}, sectors=${SECTOR_COUNT}, indices=${INDEX_COUNT}"

echo "==> Switching databases"
"$APP_DIR/stop_daemon_app.sh" >/dev/null 2>&1 || true
admin_sql -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB_NAME}' AND pid <> pg_backend_pid();" >/dev/null
if admin_sql -d postgres -Atqc "SELECT 1 FROM pg_database WHERE datname='${BACKUP_DB}'" | grep -q '^1$'; then
  admin_sql -d postgres -c "DROP DATABASE \"${BACKUP_DB}\" WITH (FORCE);" >/dev/null
fi
admin_sql -d postgres -c "ALTER DATABASE \"${DB_NAME}\" RENAME TO \"${BACKUP_DB}\";"
admin_sql -d postgres -c "ALTER DATABASE \"${STAGING_DB}\" RENAME TO \"${DB_NAME}\";"
rm -f "$DUMP_FILE"
AUTO_START_POSTGRES=0 AUTO_DB_UPDATE=1 AUTO_MARKET_SNAPSHOT_SYNC=1 "$APP_DIR/start_daemon_app.sh"
"$APP_DIR/scripts/check_market_data.sh"
echo "Production database switched to ${DB_NAME}. Rollback database: ${BACKUP_DB}"
REMOTE_SCRIPT

if [[ "${KEEP_LOCAL_DUMP:-0}" != "1" ]]; then rm -f "$DUMP_FILE"; fi
echo "Deployment completed. Production code branch: ${PROD_BRANCH}"
