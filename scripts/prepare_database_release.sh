#!/usr/bin/env bash
set -euo pipefail

# Full local-to-remote PostgreSQL release. Uses database TCP connections only.
# The target's users and user-generated records are overlaid after the local
# database is restored, so a code/schema release cannot erase live accounts.

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
USER_DATA_DUMP="${WORK_DIR}/target_user_data_${STAMP}.sql"
USER_DATA_TABLE_LIST="${WORK_DIR}/target_user_data_${STAMP}.tables"
USER_DATA_COUNTS="${WORK_DIR}/target_user_data_${STAMP}.counts"

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
echo "==> Discovering target user data tables"
"${CURRENT_TARGET_QUERY[@]}" <<'SQL' > "$USER_DATA_TABLE_LIST"
WITH RECURSIVE user_tables AS (
  SELECT 'public.users'::text COLLATE "C" AS table_name
  UNION
  SELECT format('%I.%I', child_ns.nspname, child.relname)::text COLLATE "C"
  FROM user_tables parent
  JOIN pg_class parent_rel ON format('%I.%I',
      (SELECT nspname FROM pg_namespace WHERE oid = parent_rel.relnamespace), parent_rel.relname)::text COLLATE "C" = parent.table_name COLLATE "C"
  JOIN pg_constraint con ON con.confrelid = parent_rel.oid AND con.contype = 'f'
  JOIN pg_class child ON child.oid = con.conrelid
  JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
  WHERE child.relnamespace = 'public'::regnamespace
), identity_tables AS (
  SELECT format('%I.%I', table_schema, table_name)::text COLLATE "C" AS table_name
  FROM information_schema.columns
  WHERE table_schema = 'public'
    AND column_name IN ('tenant_slug', 'user_profile_id', 'created_by_user_id', 'user_id', 'created_by')
)
SELECT DISTINCT discovered.table_name COLLATE "C" FROM (
  SELECT table_name FROM user_tables
  UNION ALL SELECT table_name FROM identity_tables
) discovered
JOIN information_schema.tables t ON format('%I.%I', t.table_schema, t.table_name)::text COLLATE "C" = discovered.table_name COLLATE "C"
WHERE t.table_type = 'BASE TABLE' AND t.table_name <> 'app_settings'
ORDER BY discovered.table_name COLLATE "C";
SQL
grep -qx 'public.users' "$USER_DATA_TABLE_LIST" || { echo "Target users table was not discovered." >&2; exit 1; }
echo "==> Target user data tables: $(wc -l < "$USER_DATA_TABLE_LIST" | tr -d ' ')"
while IFS= read -r table_name; do
  count="$(${CURRENT_TARGET_QUERY[@]} -c "SELECT count(*) FROM ${table_name}")"
  printf '%s\t%s\n' "$table_name" "$count"
done < "$USER_DATA_TABLE_LIST" > "$USER_DATA_COUNTS"
echo "==> Exporting target users and user-generated records"
USER_TABLE_ARGS=()
while IFS= read -r table_name; do USER_TABLE_ARGS+=(--table="$table_name"); done < "$USER_DATA_TABLE_LIST"
pg_dump -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$REMOTE_DB_NAME" --data-only --column-inserts --disable-triggers --no-owner --no-acl "${USER_TABLE_ARGS[@]}" --file "$USER_DATA_DUMP"
USER_DATA_SHA256="$(shasum -a 256 "$USER_DATA_DUMP" | awk '{print $1}')"
echo "==> Target user data export complete: $(wc -c < "$USER_DATA_DUMP" | tr -d ' ') bytes · SHA256 ${USER_DATA_SHA256}"
preserve_target_environment_credentials() {
  local count
  count="$("${CURRENT_TARGET_QUERY[@]}" -c "SELECT count(*) FROM app_settings WHERE setting_key IN (${PROTECTED_APP_SETTING_KEYS})")"
  if [[ "${count:-0}" -eq 0 ]]; then
    echo "==> No target environment credential records to preserve"
    return
  fi
  echo "==> Preserving ${count} target environment credential record(s)"
  "${CURRENT_TARGET_QUERY[@]}" -c "SELECT format('INSERT INTO app_settings (setting_key, setting_value, updated_at) VALUES (%L, %L, %L) ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at;', setting_key, setting_value, updated_at) FROM app_settings WHERE setting_key IN (${PROTECTED_APP_SETTING_KEYS}) ORDER BY setting_key" | "${TEMP_TARGET_EXEC[@]}"
}
echo "==> Restoring ${LOCAL_SIZE} bytes into temporary ${TARGET} database"
echo "==> Creating temporary database: ${TEMP_DB}"
"${ADMIN[@]}" -c "CREATE DATABASE \"${TEMP_DB}\" OWNER \"${REMOTE_DB_USER}\";"
echo "==> Temporary database created: ${TEMP_DB}"
cleanup_temp() { "${ADMIN[@]}" -c "DROP DATABASE IF EXISTS \"${TEMP_DB}\" WITH (FORCE);" >/dev/null 2>&1 || true; }
cancel_release() { echo "==> Release cancelled before completion; cleaning temporary ${TARGET} database"; cleanup_temp; exit 130; }
trap cleanup_temp EXIT
trap cancel_release INT TERM
PGPASSWORD="$REMOTE_DB_PASSWORD" pg_restore -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$TEMP_DB" --format=custom --no-owner --no-acl --exit-on-error "$DUMP_FILE"
echo "==> Restore completed: ${TEMP_DB}"
echo "==> Overlaying target users and user-generated records"
TRUNCATE_SQL="TRUNCATE TABLE $(paste -sd, "$USER_DATA_TABLE_LIST") CASCADE;"
"${TEMP_TARGET_EXEC[@]}" -c "$TRUNCATE_SQL"
"${TEMP_TARGET_EXEC[@]}" < "$USER_DATA_DUMP"
while IFS=$'\t' read -r table_name expected_count; do
  actual_count="$(${TEMP_TARGET_EXEC[@]} -Atqc "SELECT count(*) FROM ${table_name}")"
  [[ "$actual_count" == "$expected_count" ]] || { echo "User data validation failed for ${table_name}: expected=${expected_count} actual=${actual_count}" >&2; exit 1; }
done < "$USER_DATA_COUNTS"
"${TEMP_TARGET_EXEC[@]}" <<'SQL'
DO $$
DECLARE item record; next_value bigint;
BEGIN
  FOR item IN
    SELECT n.nspname AS schema_name, c.relname AS table_name,
           a.attname AS column_name, pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname) AS sequence_name
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    WHERE n.nspname = 'public' AND c.relkind = 'r'
      AND a.attname = 'id' AND pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname) IS NOT NULL
  LOOP
    EXECUTE format('SELECT COALESCE(max(%I), 0) + 1 FROM %I.%I', item.column_name, item.schema_name, item.table_name) INTO next_value;
    EXECUTE format('SELECT setval(%L, %s, false)', item.sequence_name, next_value);
  END LOOP;
END $$;
SQL
echo "==> Target user data overlay and sequence repair validated"
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
trap - EXIT INT TERM
cat > "$MANIFEST_FILE" <<EOF
target=${TARGET}
completed_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
local_database=${LOCAL_DB}
remote_database=${REMOTE_DB_NAME}
rollback_database=${BACKUP_DB}
dump_sha256=${LOCAL_SHA256}
dump_bytes=${LOCAL_SIZE}
EOF
rm -f "$DUMP_FILE" "$USER_DATA_DUMP" "$USER_DATA_TABLE_LIST" "$USER_DATA_COUNTS"
echo "==> Local export file removed after successful release"
echo "Database preparation complete. Rollback database: ${BACKUP_DB}"
