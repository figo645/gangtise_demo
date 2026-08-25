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

PGHOST="${PGHOST:-${APP_DB_HOST:-127.0.0.1}}"
PGPORT="${PGPORT:-${APP_DB_PORT:-5432}}"
PGDATABASE="${PGDATABASE:-${APP_DB_NAME:-sprint_dashboard}}"
PGUSER="${PGUSER:-${APP_DB_USER:-postgres}}"
PGPASSWORD="${PGPASSWORD:-${APP_DB_PASSWORD:-your_password}}"
export PGPASSWORD

if ! command -v psql >/dev/null 2>&1; then
  echo "psql command not found" >&2
  exit 1
fi

echo "Database: ${PGDATABASE} @ ${PGHOST}:${PGPORT}"
echo "Migration ledger:"
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -AtF '|' -c \
  "SELECT migration_name, migration_scope, applied_at FROM schema_migrations ORDER BY applied_at DESC LIMIT 5"

echo "Market snapshots:"
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -AtF '|' -c \
  "SELECT snapshot_type, snapshot_key, source, jsonb_array_length(COALESCE(payload_json::jsonb -> 'items', '[]'::jsonb)) AS item_count, collected_at FROM market_snapshot_payloads ORDER BY snapshot_type"

TOTAL_ITEMS="$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -Atc \
  "SELECT COALESCE(SUM(jsonb_array_length(COALESCE(payload_json::jsonb -> 'items', '[]'::jsonb))), 0) FROM market_snapshot_payloads WHERE snapshot_type IN ('market_overview', 'market_sector_overview')")"
if [ "${TOTAL_ITEMS:-0}" -le 0 ]; then
  echo "No persisted market snapshot rows. Check market_snapshot_sync.log and run start_daemon_app.sh again." >&2
  exit 2
fi
echo "Persisted market rows: ${TOTAL_ITEMS}"
