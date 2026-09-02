#!/usr/bin/env bash
set -euo pipefail

# Replace a remote target database with an empty database while retaining the
# previous database under a timestamped rollback name.

TARGET_DB_NAME="${REMOTE_DB_NAME:-sprint_dashboard}"
TARGET_DB_USER="${REMOTE_DB_USER:-postgres}"
TARGET_DB_HOST="${REMOTE_DB_HOST:-}"
TARGET_DB_PORT="${REMOTE_DB_PORT:-5432}"
TARGET_DB_PASSWORD="${REMOTE_DB_PASSWORD:-}"
TARGET_MAINTENANCE_DB="${REMOTE_MAINTENANCE_DB:-postgres}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DB_NAME="${TARGET_DB_NAME}_backup_clear_${STAMP}"

for value in TARGET_DB_NAME TARGET_DB_USER TARGET_MAINTENANCE_DB BACKUP_DB_NAME; do
  if ! [[ "${!value}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "Invalid PostgreSQL identifier: ${!value}" >&2
    exit 2
  fi
done
[[ -n "$TARGET_DB_HOST" ]] || { echo "REMOTE_DB_HOST is required." >&2; exit 2; }
command -v psql >/dev/null 2>&1 || { echo "psql is not installed." >&2; exit 1; }
command -v pg_isready >/dev/null 2>&1 || { echo "pg_isready is not installed." >&2; exit 1; }

export PGCONNECT_TIMEOUT="${DATABASE_RELEASE_CONNECT_TIMEOUT_SECONDS:-8}"
export PGPASSWORD="$TARGET_DB_PASSWORD"
ADMIN=(psql -w -h "$TARGET_DB_HOST" -p "$TARGET_DB_PORT" -U "$TARGET_DB_USER" -d "$TARGET_MAINTENANCE_DB" -v ON_ERROR_STOP=1)

RENAMED=0
EMPTY_CREATED=0
restore_on_error() {
  status=$?
  if [[ "$RENAMED" == "1" ]]; then
    echo "!! Clear failed; attempting to restore the original database name." >&2
    if [[ "$EMPTY_CREATED" == "1" ]]; then
      "${ADMIN[@]}" -c "DROP DATABASE IF EXISTS \"${TARGET_DB_NAME}\";" >/dev/null 2>&1 || true
    fi
    "${ADMIN[@]}" -c "ALTER DATABASE \"${BACKUP_DB_NAME}\" RENAME TO \"${TARGET_DB_NAME}\";" >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap restore_on_error ERR

echo "==> [preflight] Checking ${TARGET_DB_HOST}:${TARGET_DB_PORT}/${TARGET_DB_NAME}"
pg_isready -t "$PGCONNECT_TIMEOUT" -h "$TARGET_DB_HOST" -p "$TARGET_DB_PORT" >/dev/null
"${ADMIN[@]}" -Atqc "SELECT 1 FROM pg_database WHERE datname='${TARGET_DB_NAME}'" | grep -q '^1$' || {
  echo "Target database does not exist: ${TARGET_DB_NAME}" >&2
  exit 1
}
"${ADMIN[@]}" -Atqc "SELECT rolsuper FROM pg_roles WHERE rolname=current_user" | grep -q '^t$' || {
  echo "Target database user must be a PostgreSQL superuser." >&2
  exit 1
}
"${ADMIN[@]}" -Atqc "SELECT 1 FROM pg_available_extensions WHERE name='vector'" | grep -q '^1$' || {
  echo "pgvector is unavailable on the target PostgreSQL server." >&2
  exit 1
}

echo "==> Terminating connections to ${TARGET_DB_NAME}"
"${ADMIN[@]}" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${TARGET_DB_NAME}' AND pid <> pg_backend_pid();" >/dev/null
echo "==> Retaining current database as ${BACKUP_DB_NAME}"
"${ADMIN[@]}" -c "ALTER DATABASE \"${TARGET_DB_NAME}\" RENAME TO \"${BACKUP_DB_NAME}\";"
RENAMED=1
echo "==> Creating empty database ${TARGET_DB_NAME}"
"${ADMIN[@]}" -c "CREATE DATABASE \"${TARGET_DB_NAME}\" OWNER \"${TARGET_DB_USER}\";"
EMPTY_CREATED=1
PGPASSWORD="$TARGET_DB_PASSWORD" psql -w -h "$TARGET_DB_HOST" -p "$TARGET_DB_PORT" -U "$TARGET_DB_USER" -d "$TARGET_DB_NAME" -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null
echo "==> Empty database created: ${TARGET_DB_NAME}"
DATABASE_RELEASE_TARGET="${DATABASE_RELEASE_TARGET:-staging}" REMOTE_DB_HOST="$TARGET_DB_HOST" REMOTE_DB_PORT="$TARGET_DB_PORT" REMOTE_DB_NAME="$TARGET_DB_NAME" REMOTE_DB_USER="$TARGET_DB_USER" REMOTE_DB_PASSWORD="$TARGET_DB_PASSWORD" REMOTE_MAINTENANCE_DB="$TARGET_MAINTENANCE_DB" "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/prune_database_release_backups.sh"
echo "Database clear complete. Rollback database: ${BACKUP_DB_NAME}"
