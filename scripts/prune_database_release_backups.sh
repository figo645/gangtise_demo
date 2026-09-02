#!/usr/bin/env bash
set -euo pipefail

# Keep exactly the two newest complete database rollback snapshots. Database
# names carry the timestamp because PostgreSQL does not expose a creation time
# in pg_database. Only the controller-owned backup name family is eligible.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${DATABASE_RELEASE_TARGET:-staging}"
REMOTE_DB_HOST="${REMOTE_DB_HOST:-}"
REMOTE_DB_PORT="${REMOTE_DB_PORT:-5432}"
REMOTE_DB_NAME="${REMOTE_DB_NAME:-sprint_dashboard}"
REMOTE_DB_USER="${REMOTE_DB_USER:-postgres}"
REMOTE_DB_PASSWORD="${REMOTE_DB_PASSWORD:-}"
REMOTE_MAINTENANCE_DB="${REMOTE_MAINTENANCE_DB:-postgres}"
WORK_DIR="${DATABASE_RELEASE_WORK_DIR:-${ROOT_DIR}/.deploy}"
RETAIN_COUNT=2

[[ "$TARGET" == "staging" || "$TARGET" == "production" ]] || { echo "Invalid database release target: ${TARGET}" >&2; exit 2; }
[[ -n "$REMOTE_DB_HOST" && -n "$REMOTE_DB_PASSWORD" ]] || { echo "Database credentials are required for backup retention." >&2; exit 2; }
for value in REMOTE_DB_NAME REMOTE_DB_USER REMOTE_MAINTENANCE_DB; do
  [[ "${!value}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || { echo "Invalid PostgreSQL identifier: ${!value}" >&2; exit 2; }
done
command -v psql >/dev/null 2>&1 || { echo "psql is not installed." >&2; exit 1; }

export PGPASSWORD="$REMOTE_DB_PASSWORD"
ADMIN=(psql -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$REMOTE_MAINTENANCE_DB" -v ON_ERROR_STOP=1)

# Existing legacy backup names use backup_from_*, backup_clear_* and backup_*
# formats. All end with the same sortable timestamp suffix.
backup_pattern="^${REMOTE_DB_NAME}_(backup(_[A-Za-z0-9_]+)?|rollback_from)_[0-9]{8}_[0-9]{6}$"
backup_rows="$("${ADMIN[@]}" -Atqc "SELECT datname FROM pg_database WHERE datname ~ '${backup_pattern}' ORDER BY substring(datname FROM '([0-9]{8}_[0-9]{6})$') DESC, datname DESC")"
backup_count="$(printf '%s\n' "$backup_rows" | sed '/^$/d' | wc -l | tr -d ' ')"
if (( backup_count <= RETAIN_COUNT )); then
  echo "==> Rollback snapshot retention: keeping ${backup_count}/${RETAIN_COUNT} complete snapshot(s)"
  exit 0
fi

index=0
while IFS= read -r backup; do
  [[ -n "$backup" ]] || continue
  index=$((index + 1))
  (( index > RETAIN_COUNT )) || continue
  [[ "$backup" =~ $backup_pattern ]] || { echo "Refusing to prune unexpected database name: ${backup}" >&2; exit 1; }
  echo "==> Pruning expired rollback snapshot: ${backup}"
  "${ADMIN[@]}" -c "DROP DATABASE \"${backup}\" WITH (FORCE);" >/dev/null
  rm -f "${WORK_DIR}/${backup}.manifest"
done <<< "$backup_rows"
echo "==> Rollback snapshot retention complete: retained newest ${RETAIN_COUNT} complete snapshot(s)"
