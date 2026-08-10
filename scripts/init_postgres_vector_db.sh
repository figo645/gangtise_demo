#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SQL_DIR="${ROOT_DIR}/sql/postgres"

PGHOST="${PGHOST:-${VECTOR_DB_HOST:-${IP:-129.211.65.53}}}"
PGPORT="${PGPORT:-${VECTOR_DB_PORT:-5432}}"
PGDATABASE="${PGDATABASE:-postgres}"
TARGET_DB="${TARGET_DB:-${POSTGRES_DB:-sprint_dashboard}}"
PGUSER="${PGUSER:-${POSTGRES_USER:-postgres}}"
PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-your_password}}"

export PGPASSWORD

if ! command -v psql >/dev/null 2>&1; then
  echo "psql command not found. Please install PostgreSQL client first." >&2
  exit 1
fi

run_sql() {
  local db_name="$1"
  local sql_file="$2"
  echo "==> Running ${sql_file##*/} on database ${db_name}"
  psql \
    --host "$PGHOST" \
    --port "$PGPORT" \
    --username "$PGUSER" \
    --dbname "$db_name" \
    --set ON_ERROR_STOP=1 \
    --file "$sql_file"
}

echo "==> Target host: $PGHOST:$PGPORT"
echo "==> Bootstrap database: $PGDATABASE"
echo "==> Target database: $TARGET_DB"
echo "==> Login user: $PGUSER"

run_sql "$PGDATABASE" "${SQL_DIR}/000_create_database.sql"
echo "==> Applying versioned schema and master-data migrations"
PGHOST="$PGHOST" \
PGPORT="$PGPORT" \
PGDATABASE="$TARGET_DB" \
PGUSER="$PGUSER" \
PGPASSWORD="$PGPASSWORD" \
  "${ROOT_DIR}/scripts/apply_postgres_updates.sh"

if [ -f "${ROOT_DIR}/gangtise_demo.db" ]; then
  echo "==> Migrating existing SQLite data into Postgres"
  APP_DB_HOST="$PGHOST" \
  APP_DB_PORT="$PGPORT" \
  APP_DB_NAME="$TARGET_DB" \
  APP_DB_USER="$PGUSER" \
  APP_DB_PASSWORD="$PGPASSWORD" \
  GANGTISE_DEMO_DB="${ROOT_DIR}/gangtise_demo.db" \
  python3 "${ROOT_DIR}/scripts/migrate_sqlite_to_postgres.py"
fi

echo "==> Postgres application database initialization completed successfully."
