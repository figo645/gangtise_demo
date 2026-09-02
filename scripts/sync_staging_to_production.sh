#!/usr/bin/env bash
set -euo pipefail

# Rebuild Production from Staging through a validated temporary database.
# Production is renamed only after the restored snapshot passes validation.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORK_DIR="${DATABASE_RELEASE_WORK_DIR:-${ROOT_DIR}/.deploy}"
DUMP_FILE="${WORK_DIR}/staging_to_production_${STAMP}.dump"

SOURCE_HOST="${STAGING_DB_HOST:-}"
SOURCE_PORT="${STAGING_DB_PORT:-5432}"
SOURCE_DB="${STAGING_DB_NAME:-sprint_dashboard}"
SOURCE_USER="${STAGING_DB_USER:-postgres}"
SOURCE_PASSWORD="${STAGING_DB_PASSWORD:-}"
TARGET_HOST="${REMOTE_DB_HOST:-}"
TARGET_PORT="${REMOTE_DB_PORT:-5432}"
TARGET_DB="${REMOTE_DB_NAME:-sprint_dashboard}"
TARGET_USER="${REMOTE_DB_USER:-postgres}"
TARGET_PASSWORD="${REMOTE_DB_PASSWORD:-}"
TARGET_MAINTENANCE_DB="${REMOTE_MAINTENANCE_DB:-postgres}"
CONNECT_TIMEOUT_SECONDS="${DATABASE_RELEASE_CONNECT_TIMEOUT_SECONDS:-8}"
PROTECTED_APP_SETTING_KEYS="'gangtise_openapi_credentials:v1','gangtise_openapi_token:v1','llm_api_credentials:v1','auth_credentials:wechat:v1'"

[[ "${CONFIRM_STAGING_TO_PRODUCTION_SYNC:-}" == "YES" ]] || { echo "Staging-to-Production confirmation is required." >&2; exit 2; }
[[ -n "$SOURCE_HOST" && -n "$TARGET_HOST" ]] || { echo "Staging and Production database hosts must be configured." >&2; exit 2; }
[[ "${DATABASE_RELEASE_TARGET:-}" == "production" ]] || { echo "This operation only permits Production as its target." >&2; exit 2; }
[[ "$SOURCE_HOST:$SOURCE_PORT/$SOURCE_DB" != "$TARGET_HOST:$TARGET_PORT/$TARGET_DB" ]] || { echo "Staging and Production must be different databases." >&2; exit 2; }
for command in pg_dump pg_restore psql pg_isready; do
  command -v "$command" >/dev/null 2>&1 || { echo "Missing command: $command" >&2; exit 1; }
done

export PGCONNECT_TIMEOUT="$CONNECT_TIMEOUT_SECONDS"
echo "==> [preflight] Checking Staging PostgreSQL ${SOURCE_HOST}:${SOURCE_PORT} (timeout ${CONNECT_TIMEOUT_SECONDS}s)"
pg_isready -t "$CONNECT_TIMEOUT_SECONDS" -h "$SOURCE_HOST" -p "$SOURCE_PORT" >/dev/null || { echo "Staging PostgreSQL is unavailable." >&2; exit 1; }
echo "==> [preflight] Staging PostgreSQL connection is available"
echo "==> [preflight] Checking Production PostgreSQL ${TARGET_HOST}:${TARGET_PORT} (timeout ${CONNECT_TIMEOUT_SECONDS}s)"
pg_isready -t "$CONNECT_TIMEOUT_SECONDS" -h "$TARGET_HOST" -p "$TARGET_PORT" >/dev/null || { echo "Production PostgreSQL is unavailable." >&2; exit 1; }
echo "==> [preflight] Production PostgreSQL connection is available"

export PGPASSWORD="$SOURCE_PASSWORD"
SOURCE_QUERY=(psql -w -h "$SOURCE_HOST" -p "$SOURCE_PORT" -U "$SOURCE_USER" -d "$SOURCE_DB" -Atqc)
echo "==> [preflight] Verifying Staging pgvector"
"${SOURCE_QUERY[@]}" "SELECT 1 FROM pg_extension WHERE extname='vector'" | grep -q '^1$' || { echo "Staging pgvector is not enabled." >&2; exit 1; }
SOURCE_TABLE_COUNT="$("${SOURCE_QUERY[@]}" "SELECT count(*) FROM pg_tables WHERE schemaname='public'")"
SOURCE_MIGRATION_COUNT="$("${SOURCE_QUERY[@]}" "SELECT count(*) FROM schema_migrations")"
[[ "$SOURCE_TABLE_COUNT" -gt 0 && "$SOURCE_MIGRATION_COUNT" -gt 0 ]] || { echo "Staging validation baseline is incomplete." >&2; exit 1; }
echo "==> [preflight] Staging validation baseline: tables=${SOURCE_TABLE_COUNT} migrations=${SOURCE_MIGRATION_COUNT}"

mkdir -p "$WORK_DIR"
echo "==> Exporting complete Staging database: ${SOURCE_DB}"
pg_dump -w -h "$SOURCE_HOST" -p "$SOURCE_PORT" -U "$SOURCE_USER" -d "$SOURCE_DB" --format=custom --no-owner --no-acl --file "$DUMP_FILE"
SOURCE_SHA256="$(shasum -a 256 "$DUMP_FILE" | awk '{print $1}')"
SOURCE_SIZE="$(wc -c < "$DUMP_FILE" | tr -d ' ')"
echo "==> Export complete: ${SOURCE_SIZE} bytes · SHA256 ${SOURCE_SHA256}"

export PGPASSWORD="$TARGET_PASSWORD"
ADMIN=(psql -w -h "$TARGET_HOST" -p "$TARGET_PORT" -U "$TARGET_USER" -d "$TARGET_MAINTENANCE_DB" -v ON_ERROR_STOP=1)
echo "==> [preflight] Verifying Production database privileges and pgvector"
"${ADMIN[@]}" -Atqc "SELECT rolsuper FROM pg_roles WHERE rolname=current_user" | grep -q '^t$' || { echo "Production user must be superuser for database replacement." >&2; exit 1; }
"${ADMIN[@]}" -Atqc "SELECT 1 FROM pg_available_extensions WHERE name='vector'" | grep -q '^1$' || { echo "pgvector is unavailable on Production." >&2; exit 1; }
"${ADMIN[@]}" -Atqc "SELECT 1 FROM pg_database WHERE datname='${TARGET_DB}'" | grep -q '^1$' || { echo "Current Production database does not exist." >&2; exit 1; }
echo "==> [preflight] Production replacement privileges verified"

TEMP_DB="${TARGET_DB}_pre_staging_sync_${STAMP}"
BACKUP_DB="${TARGET_DB}_backup_from_staging_${STAMP}"
CURRENT_TARGET_QUERY=(psql -w -h "$TARGET_HOST" -p "$TARGET_PORT" -U "$TARGET_USER" -d "$TARGET_DB" -Atq)
TEMP_TARGET_EXEC=(psql -w -h "$TARGET_HOST" -p "$TARGET_PORT" -U "$TARGET_USER" -d "$TEMP_DB" -v ON_ERROR_STOP=1)
preserve_target_environment_credentials() {
  local count
  count="$("${CURRENT_TARGET_QUERY[@]}" "SELECT count(*) FROM app_settings WHERE setting_key IN (${PROTECTED_APP_SETTING_KEYS})")"
  if [[ "${count:-0}" -eq 0 ]]; then
    echo "==> No Production environment credential records to preserve"
    return
  fi
  echo "==> Preserving ${count} Production environment credential record(s)"
  "${CURRENT_TARGET_QUERY[@]}" "SELECT format('INSERT INTO app_settings (setting_key, setting_value, updated_at) VALUES (%L, %L, %L) ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at;', setting_key, setting_value, updated_at) FROM app_settings WHERE setting_key IN (${PROTECTED_APP_SETTING_KEYS}) ORDER BY setting_key" | "${TEMP_TARGET_EXEC[@]}"
}
cleanup_temp() {
  "${ADMIN[@]}" -c "DROP DATABASE IF EXISTS \"${TEMP_DB}\" WITH (FORCE);" >/dev/null 2>&1 || true
  rm -f "$DUMP_FILE"
}
cancel_sync() {
  echo "==> Staging-to-Production sync cancelled before final switch; cleaning temporary Production database"
  cleanup_temp
  exit 130
}
trap cleanup_temp ERR
trap cancel_sync INT TERM

echo "==> Restoring ${SOURCE_SIZE} bytes into temporary Production database"
echo "==> Creating temporary database: ${TEMP_DB}"
"${ADMIN[@]}" -c "CREATE DATABASE \"${TEMP_DB}\" OWNER \"${TARGET_USER}\";"
echo "==> Temporary database created: ${TEMP_DB}"
PGPASSWORD="$TARGET_PASSWORD" pg_restore -w -h "$TARGET_HOST" -p "$TARGET_PORT" -U "$TARGET_USER" -d "$TEMP_DB" --format=custom --no-owner --no-acl --exit-on-error "$DUMP_FILE"
echo "==> Restore completed: ${TEMP_DB}"
preserve_target_environment_credentials

echo "==> Validating Staging and Production temporary database equivalence"
TARGET_QUERY=(psql -w -h "$TARGET_HOST" -p "$TARGET_PORT" -U "$TARGET_USER" -d "$TEMP_DB" -Atqc)
TARGET_VECTOR_OK="$("${TARGET_QUERY[@]}" "SELECT count(*) FROM pg_extension WHERE extname='vector'")"
TARGET_TABLE_COUNT="$("${TARGET_QUERY[@]}" "SELECT count(*) FROM pg_tables WHERE schemaname='public'")"
TARGET_MIGRATION_COUNT="$("${TARGET_QUERY[@]}" "SELECT count(*) FROM schema_migrations")"
[[ "$TARGET_VECTOR_OK" == 1 && "$TARGET_TABLE_COUNT" == "$SOURCE_TABLE_COUNT" && "$TARGET_MIGRATION_COUNT" == "$SOURCE_MIGRATION_COUNT" ]] || {
  echo "Validation failed: source_tables=${SOURCE_TABLE_COUNT} production_tables=${TARGET_TABLE_COUNT} source_migrations=${SOURCE_MIGRATION_COUNT} production_migrations=${TARGET_MIGRATION_COUNT} production_vector=${TARGET_VECTOR_OK}" >&2
  exit 1
}
echo "Validated: source_tables=${SOURCE_TABLE_COUNT} production_tables=${TARGET_TABLE_COUNT} source_migrations=${SOURCE_MIGRATION_COUNT} production_vector=${TARGET_VECTOR_OK}"

echo "==> Switching Production database"
"${ADMIN[@]}" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${TARGET_DB}' AND pid <> pg_backend_pid();" >/dev/null
echo "==> Existing Production database connections terminated"
"${ADMIN[@]}" -c "BEGIN; ALTER DATABASE \"${TARGET_DB}\" RENAME TO \"${BACKUP_DB}\"; ALTER DATABASE \"${TEMP_DB}\" RENAME TO \"${TARGET_DB}\"; COMMIT;"
echo "==> Current Production database retained for rollback: ${BACKUP_DB}"
echo "==> Staging snapshot promoted as Production database"
DATABASE_RELEASE_TARGET=production REMOTE_DB_HOST="$TARGET_HOST" REMOTE_DB_PORT="$TARGET_PORT" REMOTE_DB_NAME="$TARGET_DB" REMOTE_DB_USER="$TARGET_USER" REMOTE_DB_PASSWORD="$TARGET_PASSWORD" REMOTE_MAINTENANCE_DB="$TARGET_MAINTENANCE_DB" DATABASE_RELEASE_WORK_DIR="$WORK_DIR" "$ROOT_DIR/scripts/prune_database_release_backups.sh"
trap - ERR INT TERM
rm -f "$DUMP_FILE"
echo "==> Temporary Staging export file removed"
echo "Staging-to-Production sync complete. Rollback database: ${BACKUP_DB}"
