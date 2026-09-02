#!/usr/bin/env bash
set -euo pipefail

# Full local-to-remote PostgreSQL release. Uses database TCP connections only.
# No SSH, no remote shell, and no server filesystem dependency.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORK_DIR="${DATABASE_RELEASE_WORK_DIR:-${ROOT_DIR}/.deploy}"
DUMP_FILE="${WORK_DIR}/sprint_dashboard_${STAMP}.dump"
MANIFEST_FILE="${WORK_DIR}/sprint_dashboard_${STAMP}.manifest"

LOCAL_HOST="${LOCAL_PGHOST:-${LOCAL_POSTGRES_HOST:-127.0.0.1}}"
LOCAL_PORT="${LOCAL_PGPORT:-${LOCAL_POSTGRES_PORT:-5432}}"
LOCAL_DB="${LOCAL_PGDATABASE:-${LOCAL_POSTGRES_DB:-sprint_dashboard}}"
LOCAL_USER="${LOCAL_PGUSER:-${LOCAL_POSTGRES_USER:-postgres}}"
LOCAL_PASSWORD="${LOCAL_PGPASSWORD:-${LOCAL_POSTGRES_PASSWORD:-your_password}}"
TARGET="${DATABASE_RELEASE_TARGET:-staging}"
REMOTE_DB_HOST="${REMOTE_DB_HOST:-129.211.65.53}"
REMOTE_DB_PORT="${REMOTE_DB_PORT:-5432}"
REMOTE_DB_NAME="${REMOTE_DB_NAME:-sprint_dashboard}"
REMOTE_DB_USER="${REMOTE_DB_USER:-postgres}"
REMOTE_DB_PASSWORD="${REMOTE_DB_PASSWORD:-${REMOTE_POSTGRES_PASSWORD:-your_password}}"
REMOTE_MAINTENANCE_DB="${REMOTE_MAINTENANCE_DB:-postgres}"
CONNECT_TIMEOUT_SECONDS="${DATABASE_RELEASE_CONNECT_TIMEOUT_SECONDS:-8}"
PROTECTED_APP_SETTING_KEYS="'gangtise_openapi_credentials:v1','gangtise_openapi_token:v1','llm_api_credentials:v1','auth_credentials:wechat:v1'"

[[ "${1:-}" != "--help" && "${1:-}" != "-h" ]] || { echo "Usage: $0"; exit 0; }
[[ "$TARGET" == staging || "$TARGET" == production ]] || { echo "Invalid target: $TARGET" >&2; exit 2; }
for command in pg_dump pg_restore psql pg_isready; do command -v "$command" >/dev/null 2>&1 || { echo "Missing command: $command" >&2; exit 1; }; done
export PGCONNECT_TIMEOUT="$CONNECT_TIMEOUT_SECONDS"
echo "==> [preflight] Checking local PostgreSQL ${LOCAL_HOST}:${LOCAL_PORT} (timeout ${CONNECT_TIMEOUT_SECONDS}s)"
pg_isready -t "$CONNECT_TIMEOUT_SECONDS" -h "$LOCAL_HOST" -p "$LOCAL_PORT" >/dev/null || { echo "Local PostgreSQL is unavailable." >&2; exit 1; }
echo "==> [preflight] Local PostgreSQL connection is available"
echo "==> [preflight] Checking ${TARGET} PostgreSQL ${REMOTE_DB_HOST}:${REMOTE_DB_PORT} (timeout ${CONNECT_TIMEOUT_SECONDS}s)"
pg_isready -t "$CONNECT_TIMEOUT_SECONDS" -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" >/dev/null || { echo "${TARGET} PostgreSQL is unavailable at ${REMOTE_DB_HOST}:${REMOTE_DB_PORT}." >&2; exit 1; }
echo "==> [preflight] ${TARGET} PostgreSQL connection is available"

export PGPASSWORD="$LOCAL_PASSWORD"
echo "==> [preflight] Verifying local pgvector extension"
psql -w -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" -Atqc "SELECT 1 FROM pg_extension WHERE extname='vector'" | grep -q '^1$' || { echo "Local pgvector is not enabled." >&2; exit 1; }
echo "==> [preflight] Local pgvector extension is enabled"
mkdir -p "$WORK_DIR"
echo "==> Exporting complete local database: ${LOCAL_DB}"
pg_dump -w -h "$LOCAL_HOST" -p "$LOCAL_PORT" -U "$LOCAL_USER" -d "$LOCAL_DB" --format=custom --no-owner --no-acl --file "$DUMP_FILE"
LOCAL_SHA256="$(shasum -a 256 "$DUMP_FILE" | awk '{print $1}')"
LOCAL_SIZE="$(wc -c < "$DUMP_FILE" | tr -d ' ')"
echo "==> Export complete: ${LOCAL_SIZE} bytes · SHA256 ${LOCAL_SHA256}"

if [[ "${CONFIRM_DATABASE_REPLACE:-}" != YES ]]; then
  printf 'Replace %s database %s with the complete local database? [y/N] ' "$TARGET" "$REMOTE_DB_NAME"
  read -r answer
  [[ "$answer" == y || "$answer" == Y ]] || { echo "Cancelled."; exit 0; }
fi

export PGPASSWORD="$REMOTE_DB_PASSWORD"
ADMIN=(psql -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$REMOTE_MAINTENANCE_DB" -v ON_ERROR_STOP=1)
echo "==> [preflight] Verifying ${TARGET} database privileges and pgvector"
"${ADMIN[@]}" -Atqc "SELECT rolsuper FROM pg_roles WHERE rolname=current_user" | grep -q '^t$' || { echo "Remote user must be superuser for full database replacement." >&2; exit 1; }
echo "==> [preflight] ${TARGET} superuser privilege verified"
"${ADMIN[@]}" -Atqc "SELECT 1 FROM pg_available_extensions WHERE name='vector'" | grep -q '^1$' || { echo "pgvector unavailable on ${TARGET}." >&2; exit 1; }
echo "==> [preflight] ${TARGET} pgvector extension is available"

TEMP_DB="${REMOTE_DB_NAME}_pre_release_${STAMP}"
BACKUP_DB="${REMOTE_DB_NAME}_backup_${STAMP}"
CURRENT_TARGET_QUERY=(psql -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$REMOTE_DB_NAME" -Atq)
TEMP_TARGET_EXEC=(psql -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$TEMP_DB" -v ON_ERROR_STOP=1)
preserve_target_environment_credentials() {
  local count
  count="$("${CURRENT_TARGET_QUERY[@]}" "SELECT count(*) FROM app_settings WHERE setting_key IN (${PROTECTED_APP_SETTING_KEYS})")"
  if [[ "${count:-0}" -eq 0 ]]; then
    echo "==> No target environment credential records to preserve"
    return
  fi
  echo "==> Preserving ${count} target environment credential record(s)"
  "${CURRENT_TARGET_QUERY[@]}" "SELECT format('INSERT INTO app_settings (setting_key, setting_value, updated_at) VALUES (%L, %L, %L) ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at;', setting_key, setting_value, updated_at) FROM app_settings WHERE setting_key IN (${PROTECTED_APP_SETTING_KEYS}) ORDER BY setting_key" | "${TEMP_TARGET_EXEC[@]}"
}
echo "==> Restoring ${LOCAL_SIZE} bytes into temporary ${TARGET} database"
echo "==> Creating temporary database: ${TEMP_DB}"
"${ADMIN[@]}" -c "CREATE DATABASE \"${TEMP_DB}\" OWNER \"${REMOTE_DB_USER}\";"
echo "==> Temporary database created: ${TEMP_DB}"
cleanup_temp() { "${ADMIN[@]}" -c "DROP DATABASE IF EXISTS \"${TEMP_DB}\" WITH (FORCE);" >/dev/null 2>&1 || true; }
cancel_release() { echo "==> Release cancelled before completion; cleaning temporary ${TARGET} database"; cleanup_temp; exit 130; }
trap cleanup_temp ERR
trap cancel_release INT TERM
PGPASSWORD="$REMOTE_DB_PASSWORD" pg_restore -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$TEMP_DB" --format=custom --no-owner --no-acl --exit-on-error "$DUMP_FILE"
echo "==> Restore completed: ${TEMP_DB}"
preserve_target_environment_credentials
echo "==> Applying schema updates to temporary database"
PGHOST="$REMOTE_DB_HOST" PGPORT="$REMOTE_DB_PORT" PGDATABASE="$TEMP_DB" PGUSER="$REMOTE_DB_USER" PGPASSWORD="$REMOTE_DB_PASSWORD" "$ROOT_DIR/scripts/apply_postgres_updates.sh"
echo "==> Schema updates completed"

echo "==> Validating temporary database structure and market master data"
VALIDATE=(psql -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$TEMP_DB" -Atqc)
VECTOR_OK="$(${VALIDATE[@]} "SELECT count(*) FROM pg_extension WHERE extname='vector'")"
TABLE_COUNT="$(${VALIDATE[@]} "SELECT count(*) FROM pg_tables WHERE schemaname='public'")"
MIGRATION_COUNT="$(${VALIDATE[@]} "SELECT count(*) FROM schema_migrations")"
SNAPSHOT_ITEMS="$(${VALIDATE[@]} "SELECT COALESCE(SUM(jsonb_array_length(COALESCE(payload_json::jsonb->'items','[]'::jsonb))),0) FROM market_snapshot_payloads WHERE snapshot_type IN ('market_overview','market_sector_overview')")"
SECTOR_COUNT="$(${VALIDATE[@]} "SELECT COALESCE(jsonb_array_length(setting_value::jsonb->'items'),0) FROM app_settings WHERE setting_key='master_data:market_sector_catalog:shenwan_level1'")"
INDEX_COUNT="$(${VALIDATE[@]} "SELECT COALESCE(jsonb_array_length(setting_value::jsonb->'items'),0) FROM app_settings WHERE setting_key='master_data:market_index_catalog:standard'")"
[[ "$VECTOR_OK" == 1 && "$TABLE_COUNT" -gt 0 && "$MIGRATION_COUNT" -gt 0 && "$SNAPSHOT_ITEMS" -gt 0 && "$SECTOR_COUNT" -gt 0 && "$INDEX_COUNT" -gt 0 ]] || { echo "Validation failed: vector=$VECTOR_OK tables=$TABLE_COUNT migrations=$MIGRATION_COUNT market_rows=$SNAPSHOT_ITEMS sectors=$SECTOR_COUNT indices=$INDEX_COUNT" >&2; exit 1; }
echo "Validated: tables=$TABLE_COUNT migrations=$MIGRATION_COUNT market_rows=$SNAPSHOT_ITEMS sectors=$SECTOR_COUNT indices=$INDEX_COUNT"

echo "==> Switching ${TARGET} database"
"${ADMIN[@]}" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${REMOTE_DB_NAME}' AND pid <> pg_backend_pid();" >/dev/null
echo "==> Existing ${TARGET} database connections terminated"
"${ADMIN[@]}" -c "ALTER DATABASE \"${REMOTE_DB_NAME}\" RENAME TO \"${BACKUP_DB}\";"
echo "==> Current database retained for rollback: ${BACKUP_DB}"
"${ADMIN[@]}" -c "ALTER DATABASE \"${TEMP_DB}\" RENAME TO \"${REMOTE_DB_NAME}\";"
echo "==> Temporary database promoted as ${REMOTE_DB_NAME}"
DATABASE_RELEASE_TARGET="$TARGET" REMOTE_DB_HOST="$REMOTE_DB_HOST" REMOTE_DB_PORT="$REMOTE_DB_PORT" REMOTE_DB_NAME="$REMOTE_DB_NAME" REMOTE_DB_USER="$REMOTE_DB_USER" REMOTE_DB_PASSWORD="$REMOTE_DB_PASSWORD" REMOTE_MAINTENANCE_DB="$REMOTE_MAINTENANCE_DB" DATABASE_RELEASE_WORK_DIR="$WORK_DIR" "$ROOT_DIR/scripts/prune_database_release_backups.sh"
trap - ERR INT TERM
cat > "$MANIFEST_FILE" <<EOF
target=${TARGET}
completed_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
local_database=${LOCAL_DB}
remote_database=${REMOTE_DB_NAME}
rollback_database=${BACKUP_DB}
dump_sha256=${LOCAL_SHA256}
dump_bytes=${LOCAL_SIZE}
EOF
rm -f "$DUMP_FILE"
echo "==> Local export file removed after successful release"
echo "Database preparation complete. Rollback database: ${BACKUP_DB}"
