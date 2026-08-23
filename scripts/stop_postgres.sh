#!/usr/bin/env bash

set -euo pipefail

PG_MAJOR="${PG_MAJOR:-16}"
DB_HOST="${LOCAL_POSTGRES_HOST:-127.0.0.1}"
DB_PORT="${LOCAL_POSTGRES_PORT:-5432}"
STOP_TIMEOUT="${POSTGRES_STOP_TIMEOUT:-30}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this script as root: sudo $0" >&2
  exit 1
fi

if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
  echo "PostgreSQL is already stopped at ${DB_HOST}:${DB_PORT}."
  exit 0
fi

echo "==> Stopping PostgreSQL ${PG_MAJOR}"
if command -v systemctl >/dev/null 2>&1; then
  systemctl stop postgresql
elif command -v pg_ctlcluster >/dev/null 2>&1; then
  pg_ctlcluster "${PG_MAJOR}" main stop
else
  echo "Neither systemctl nor pg_ctlcluster is available." >&2
  exit 1
fi

for ((second = 1; second <= STOP_TIMEOUT; second++)); do
  if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
    echo "PostgreSQL stopped successfully."
    exit 0
  fi
  sleep 1
done

echo "PostgreSQL did not stop within ${STOP_TIMEOUT}s." >&2
systemctl status postgresql --no-pager 2>/dev/null || true
exit 1
