#!/usr/bin/env bash
set -euo pipefail

# Swap a retained full-release backup database back into service over direct PostgreSQL TCP.
BACKUP_DB="${1:-}"
TARGET="${DATABASE_RELEASE_TARGET:-staging}"
REMOTE_DB_HOST="${REMOTE_DB_HOST:-129.211.65.53}"
REMOTE_DB_PORT="${REMOTE_DB_PORT:-5432}"
REMOTE_DB_NAME="${REMOTE_DB_NAME:-sprint_dashboard}"
REMOTE_DB_USER="${REMOTE_DB_USER:-postgres}"
REMOTE_DB_PASSWORD="${REMOTE_DB_PASSWORD:-${REMOTE_POSTGRES_PASSWORD:-your_password}}"

[[ "$BACKUP_DB" =~ ^${REMOTE_DB_NAME}_backup_([0-9]{8}_[0-9]{6}|clear_[0-9]{8}_[0-9]{6})$ ]] || { echo "Invalid rollback database name." >&2; exit 2; }
export PGPASSWORD="$REMOTE_DB_PASSWORD"
PSQL=(psql -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d postgres -v ON_ERROR_STOP=1)
echo "==> [preflight] Checking ${TARGET} rollback database connection"
"${PSQL[@]}" -Atqc "SELECT 1" >/dev/null
echo "==> [preflight] ${TARGET} rollback database connection is available"
"${PSQL[@]}" -Atqc "SELECT rolsuper FROM pg_roles WHERE rolname=current_user" | grep -q '^t$' || { echo "Remote user must be superuser." >&2; exit 1; }
echo "==> [preflight] Rollback privilege verified"
"${PSQL[@]}" -Atqc "SELECT 1 FROM pg_database WHERE datname='${BACKUP_DB}'" | grep -q '^1$' || { echo "Rollback database does not exist." >&2; exit 1; }
echo "==> [preflight] Rollback source database exists"

STAMP="$(date +%Y%m%d_%H%M%S)"
CURRENT_BACKUP="${REMOTE_DB_NAME}_rollback_from_${STAMP}"
echo "==> Rolling ${TARGET} back to ${BACKUP_DB}"
"${PSQL[@]}" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('${REMOTE_DB_NAME}','${BACKUP_DB}') AND pid <> pg_backend_pid();" >/dev/null
echo "==> Existing target connections terminated"
"${PSQL[@]}" -c "ALTER DATABASE \"${REMOTE_DB_NAME}\" RENAME TO \"${CURRENT_BACKUP}\";"
echo "==> Current database retained: ${CURRENT_BACKUP}"
"${PSQL[@]}" -c "ALTER DATABASE \"${BACKUP_DB}\" RENAME TO \"${REMOTE_DB_NAME}\";"
echo "==> Rollback database promoted as ${REMOTE_DB_NAME}"
echo "Rollback completed. Current database retained as: ${CURRENT_BACKUP}"
