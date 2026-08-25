#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CREDENTIALS_FILE="${POSTGRES_CREDENTIALS_FILE:-${ROOT_DIR}/.gangtise_postgres_credentials}"
if [ -f "$CREDENTIALS_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$CREDENTIALS_FILE"
  set +a
fi

DB_NAME="${APP_DB_NAME:-${POSTGRES_DB:-sprint_dashboard}}"
DB_HOST="${LOCAL_POSTGRES_HOST:-${APP_DB_HOST:-127.0.0.1}}"
DB_PORT="${LOCAL_POSTGRES_PORT:-${APP_DB_PORT:-5432}}"
DB_USER="${APP_DB_USER:-gangtise_app}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root: sudo $0" >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql not found. Install PostgreSQL first." >&2
  exit 1
fi

if ! command -v runuser >/dev/null 2>&1; then
  echo "runuser not found. This script expects a local Linux PostgreSQL installation." >&2
  exit 1
fi

if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
  echo "PostgreSQL is not ready at ${DB_HOST}:${DB_PORT}. Run start_postgres.sh first." >&2
  exit 1
fi

if ! runuser -u postgres -- psql -d "$DB_NAME" -Atqc \
  "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'" \
  2>/dev/null | grep -q '^1$'; then
  echo "pgvector is not installed for this PostgreSQL instance." >&2
  echo "Run install_postgres_pgvector.sh first, then run this script again." >&2
  exit 1
fi

runuser -u postgres -- psql --set ON_ERROR_STOP=1 -d "$DB_NAME" \
  -c 'CREATE EXTENSION IF NOT EXISTS vector;'

VECTOR_VERSION="$(runuser -u postgres -- psql -d "$DB_NAME" -Atqc \
  "SELECT extversion FROM pg_extension WHERE extname = 'vector'" | tr -d '[:space:]')"

echo "pgvector ${VECTOR_VERSION:-unknown} is enabled in ${DB_NAME}."
