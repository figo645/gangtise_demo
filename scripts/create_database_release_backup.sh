#!/usr/bin/env bash
set -euo pipefail

# Create a complete logical snapshot before an in-place Production delta.
# Full replacement flows retain the previous database through a name swap;
# incremental SQL needs this explicit snapshot to offer the same rollback path.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${DATABASE_RELEASE_TARGET:-staging}"
REMOTE_DB_HOST="${REMOTE_DB_HOST:-}"
REMOTE_DB_PORT="${REMOTE_DB_PORT:-5432}"
REMOTE_DB_NAME="${REMOTE_DB_NAME:-sprint_dashboard}"
REMOTE_DB_USER="${REMOTE_DB_USER:-postgres}"
REMOTE_DB_PASSWORD="${REMOTE_DB_PASSWORD:-}"
REMOTE_MAINTENANCE_DB="${REMOTE_MAINTENANCE_DB:-postgres}"
CONNECT_TIMEOUT_SECONDS="${DATABASE_RELEASE_CONNECT_TIMEOUT_SECONDS:-8}"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORK_DIR="${DATABASE_RELEASE_WORK_DIR:-${ROOT_DIR}/.deploy}"
DUMP_FILE="${WORK_DIR}/${REMOTE_DB_NAME}_backup_${STAMP}.dump"
BACKUP_DB="${REMOTE_DB_NAME}_backup_${STAMP}"

[[ "$TARGET" == "production" ]] || { echo "==> Full rollback snapshot is only required for Production incremental releases"; exit 0; }
[[ -n "$REMOTE_DB_HOST" && -n "$REMOTE_DB_PASSWORD" ]] || { echo "Production database credentials are required for the rollback snapshot." >&2; exit 2; }
for command in pg_dump pg_restore psql pg_isready; do
  command -v "$command" >/dev/null 2>&1 || { echo "Missing command: $command" >&2; exit 1; }
done
for value in REMOTE_DB_NAME REMOTE_DB_USER REMOTE_MAINTENANCE_DB BACKUP_DB; do
  [[ "${!value}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || { echo "Invalid PostgreSQL identifier: ${!value}" >&2; exit 2; }
done

export PGCONNECT_TIMEOUT="$CONNECT_TIMEOUT_SECONDS"
export PGPASSWORD="$REMOTE_DB_PASSWORD"
ADMIN=(psql -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$REMOTE_MAINTENANCE_DB" -v ON_ERROR_STOP=1)
SOURCE=(psql -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$REMOTE_DB_NAME" -Atqc)

echo "==> [preflight] Creating complete Production rollback snapshot"
pg_isready -t "$CONNECT_TIMEOUT_SECONDS" -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" >/dev/null || { echo "Production PostgreSQL is unavailable." >&2; exit 1; }
"${ADMIN[@]}" -Atqc "SELECT rolsuper FROM pg_roles WHERE rolname=current_user" | grep -q '^t$' || { echo "Production user must be superuser for rollback snapshots." >&2; exit 1; }
"${ADMIN[@]}" -Atqc "SELECT 1 FROM pg_database WHERE datname='${REMOTE_DB_NAME}'" | grep -q '^1$' || { echo "Production database does not exist." >&2; exit 1; }
"${ADMIN[@]}" -Atqc "SELECT 1 FROM pg_available_extensions WHERE name='vector'" | grep -q '^1$' || { echo "pgvector is unavailable on Production." >&2; exit 1; }
"${ADMIN[@]}" -Atqc "SELECT 1 FROM pg_database WHERE datname='${BACKUP_DB}'" | grep -q '^1$' && { echo "Rollback snapshot name already exists: ${BACKUP_DB}" >&2; exit 1; }

mkdir -p "$WORK_DIR"
SOURCE_TABLE_COUNT="$("${SOURCE[@]}" "SELECT count(*) FROM pg_tables WHERE schemaname='public'")"
SOURCE_MIGRATION_COUNT="$("${SOURCE[@]}" "SELECT count(*) FROM schema_migrations")"
echo "==> Exporting current Production database for rollback: ${REMOTE_DB_NAME}"
pg_dump -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$REMOTE_DB_NAME" --format=custom --no-owner --no-acl --file "$DUMP_FILE"
SNAPSHOT_SHA256="$(shasum -a 256 "$DUMP_FILE" | awk '{print $1}')"
SNAPSHOT_SIZE="$(wc -c < "$DUMP_FILE" | tr -d ' ')"

cleanup_incomplete_snapshot() {
  "${ADMIN[@]}" -c "DROP DATABASE IF EXISTS \"${BACKUP_DB}\" WITH (FORCE);" >/dev/null 2>&1 || true
  rm -f "$DUMP_FILE"
}
trap cleanup_incomplete_snapshot ERR INT TERM

echo "==> Restoring rollback snapshot into ${BACKUP_DB}"
"${ADMIN[@]}" -c "CREATE DATABASE \"${BACKUP_DB}\" OWNER \"${REMOTE_DB_USER}\";"
pg_restore -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$BACKUP_DB" --format=custom --no-owner --no-acl --exit-on-error "$DUMP_FILE"
BACKUP=(psql -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$BACKUP_DB" -Atqc)
BACKUP_VECTOR_OK="$("${BACKUP[@]}" "SELECT count(*) FROM pg_extension WHERE extname='vector'")"
BACKUP_TABLE_COUNT="$("${BACKUP[@]}" "SELECT count(*) FROM pg_tables WHERE schemaname='public'")"
BACKUP_MIGRATION_COUNT="$("${BACKUP[@]}" "SELECT count(*) FROM schema_migrations")"
[[ "$BACKUP_VECTOR_OK" == "1" && "$BACKUP_TABLE_COUNT" == "$SOURCE_TABLE_COUNT" && "$BACKUP_MIGRATION_COUNT" == "$SOURCE_MIGRATION_COUNT" ]] || {
  echo "Rollback snapshot validation failed: source_tables=${SOURCE_TABLE_COUNT} backup_tables=${BACKUP_TABLE_COUNT} source_migrations=${SOURCE_MIGRATION_COUNT} backup_migrations=${BACKUP_MIGRATION_COUNT} backup_vector=${BACKUP_VECTOR_OK}" >&2
  exit 1
}

cat > "${WORK_DIR}/${BACKUP_DB}.manifest" <<EOF
target=production
created_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
backup_database=${BACKUP_DB}
source_database=${REMOTE_DB_NAME}
dump_sha256=${SNAPSHOT_SHA256}
dump_bytes=${SNAPSHOT_SIZE}
EOF
rm -f "$DUMP_FILE"
trap - ERR INT TERM
echo "==> Complete Production rollback snapshot ready: ${BACKUP_DB}"
"${ROOT_DIR}/scripts/prune_database_release_backups.sh"
