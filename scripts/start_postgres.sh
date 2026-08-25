#!/usr/bin/env bash

set -euo pipefail

PG_MAJOR="${PG_MAJOR:-16}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CREDENTIALS_FILE="${POSTGRES_CREDENTIALS_FILE:-${ROOT_DIR}/.gangtise_postgres_credentials}"
if [ -f "$CREDENTIALS_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$CREDENTIALS_FILE"
  set +a
fi
DB_NAME="${APP_DB_NAME:-sprint_dashboard}"
DB_HOST="${LOCAL_POSTGRES_HOST:-127.0.0.1}"
DB_PORT="${LOCAL_POSTGRES_PORT:-5432}"
START_TIMEOUT="${POSTGRES_START_TIMEOUT:-30}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root: sudo $0" >&2
  exit 1
fi

if ! command -v pg_isready >/dev/null 2>&1; then
  echo "pg_isready not found. Install PostgreSQL first." >&2
  exit 1
fi

if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
  echo "==> Starting PostgreSQL ${PG_MAJOR}"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl start postgresql
  elif command -v pg_ctlcluster >/dev/null 2>&1; then
    pg_ctlcluster "${PG_MAJOR}" main start
  else
    echo "Neither systemctl nor pg_ctlcluster is available." >&2
    exit 1
  fi
fi

for ((second = 1; second <= START_TIMEOUT; second++)); do
  if pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
    echo "PostgreSQL is ready at ${DB_HOST}:${DB_PORT}."
    break
  fi
  if [ "$second" -eq "$START_TIMEOUT" ]; then
    echo "PostgreSQL did not become ready within ${START_TIMEOUT}s." >&2
    systemctl status postgresql --no-pager 2>/dev/null || true
    exit 1
  fi
  sleep 1
done

ENABLE_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/enable_pgvector.sh"
if [ -x "$ENABLE_SCRIPT" ]; then
  "$ENABLE_SCRIPT"
else
  echo "Warning: ${ENABLE_SCRIPT} is missing; pgvector was not checked." >&2
fi
