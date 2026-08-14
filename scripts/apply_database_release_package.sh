#!/usr/bin/env bash
set -euo pipefail

# Apply one locally stored immutable package through direct PostgreSQL TCP.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGES_DIR="${DATABASE_RELEASE_PACKAGES_DIR:-${ROOT_DIR}/database_release_packages}"
PACKAGE_DIR="${1:-}"
TARGET="${DATABASE_RELEASE_TARGET:-staging}"
REMOTE_DB_HOST="${REMOTE_DB_HOST:-129.211.65.53}"
REMOTE_DB_PORT="${REMOTE_DB_PORT:-5432}"
REMOTE_DB_NAME="${REMOTE_DB_NAME:-sprint_dashboard}"
REMOTE_DB_USER="${REMOTE_DB_USER:-postgres}"
REMOTE_DB_PASSWORD="${REMOTE_DB_PASSWORD:-${REMOTE_POSTGRES_PASSWORD:-your_password}}"
CONNECT_TIMEOUT_SECONDS="${DATABASE_RELEASE_CONNECT_TIMEOUT_SECONDS:-8}"

[[ -n "$PACKAGE_DIR" ]] || { echo "Usage: $0 database_release_packages/YYYY-MM-DD/vX.Y.Z" >&2; exit 2; }
[[ "$PACKAGE_DIR" = /* ]] || PACKAGE_DIR="$ROOT_DIR/$PACKAGE_DIR"
[[ "$PACKAGE_DIR" == "$PACKAGES_DIR"/* && -f "$PACKAGE_DIR/release.env" ]] || { echo "Invalid package." >&2; exit 2; }
# shellcheck disable=SC1090
. "$PACKAGE_DIR/release.env"
[[ "${RELEASE_VERSION:-}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Invalid RELEASE_VERSION." >&2; exit 2; }
[[ "${PACKAGE_TYPE:-}" == schema || "${PACKAGE_TYPE:-}" == master_data || "${PACKAGE_TYPE:-}" == data ]] || { echo "Invalid PACKAGE_TYPE." >&2; exit 2; }
SQL_FILE="$PACKAGE_DIR/$PACKAGE_TYPE.sql"
[[ -f "$SQL_FILE" ]] || { echo "Missing SQL payload." >&2; exit 2; }

export PGPASSWORD="$REMOTE_DB_PASSWORD"
export PGCONNECT_TIMEOUT="$CONNECT_TIMEOUT_SECONDS"
PSQL=(psql -w -h "$REMOTE_DB_HOST" -p "$REMOTE_DB_PORT" -U "$REMOTE_DB_USER" -d "$REMOTE_DB_NAME" -v ON_ERROR_STOP=1)
echo "==> [preflight] Checking ${TARGET} database connection for ${RELEASE_VERSION} (timeout ${CONNECT_TIMEOUT_SECONDS}s)"
"${PSQL[@]}" -Atqc "SELECT 1" >/dev/null
echo "==> [preflight] ${TARGET} database connection is available"
checksum="$(shasum -a 256 "$SQL_FILE" | awk '{print $1}')"
echo "==> Calculated package checksum: ${checksum}"
sql_literal() { printf "%s" "$1" | sed "s/'/''/g"; }
version_sql="$(sql_literal "$RELEASE_VERSION")"
target_sql="$(sql_literal "$TARGET")"
title_sql="$(sql_literal "${TITLE:-}")"
"${PSQL[@]}" -c "CREATE TABLE IF NOT EXISTS database_release_packages (release_version TEXT NOT NULL,target_environment TEXT NOT NULL,package_type TEXT NOT NULL CHECK (package_type IN ('schema','master_data','data')),title TEXT NOT NULL DEFAULT '',checksum_sha256 TEXT NOT NULL,status TEXT NOT NULL CHECK (status IN ('succeeded','failed')),applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,execution_ms INTEGER NOT NULL DEFAULT 0,PRIMARY KEY (release_version,target_environment)); ALTER TABLE database_release_packages DROP CONSTRAINT IF EXISTS database_release_packages_package_type_check; ALTER TABLE database_release_packages ADD CONSTRAINT database_release_packages_package_type_check CHECK (package_type IN ('schema','master_data','data'));" >/dev/null
echo "==> Release ledger is ready"
recorded="$(${PSQL[@]} -Atqc "SELECT checksum_sha256 FROM database_release_packages WHERE release_version='${version_sql}' AND target_environment='${target_sql}' AND status='succeeded'")"
if [[ -n "$recorded" ]]; then
  [[ "$recorded" == "$checksum" ]] || { echo "Released package checksum changed." >&2; exit 1; }
  echo "SKIP ${RELEASE_VERSION}"
  exit 0
fi
started="$(date +%s)"
wrapper="$(mktemp)"
trap 'rm -f "$wrapper"' EXIT
{
  echo 'BEGIN;'
  echo "SET LOCAL lock_timeout = '10s';"
  echo "SET LOCAL statement_timeout = '120s';"
  printf "\\i '%s'\n" "$SQL_FILE"
  printf "INSERT INTO database_release_packages (release_version,target_environment,package_type,title,checksum_sha256,status) VALUES ('%s','%s','%s','%s','%s','succeeded');\n" "$version_sql" "$target_sql" "$PACKAGE_TYPE" "$title_sql" "$checksum"
  echo 'COMMIT;'
} > "$wrapper"
echo "==> Starting transactional SQL execution: ${RELEASE_VERSION} (${PACKAGE_TYPE})"
"${PSQL[@]}" -f "$wrapper"
echo "==> Transaction committed: ${RELEASE_VERSION}"
elapsed=$(( $(date +%s) - started ))
"${PSQL[@]}" -c "UPDATE database_release_packages SET execution_ms=${elapsed}*1000 WHERE release_version='${version_sql}' AND target_environment='${target_sql}';" >/dev/null
echo "==> Release ledger updated: ${elapsed} seconds"
echo "APPLIED ${RELEASE_VERSION} to ${TARGET} (${PACKAGE_TYPE})"
