#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.app.daemon.pid"
LOG_FILE="$SCRIPT_DIR/app.daemon.log"
DB_UPDATE_LOG="$SCRIPT_DIR/db.update.log"
MARKET_SYNC_LOG="$SCRIPT_DIR/market_snapshot_sync.log"
APP_PORT="${PORT:-5001}"
PYTHON_BIN="${PYTHON_BIN:-}"
AUTO_DB_UPDATE="${AUTO_DB_UPDATE:-1}"
AUTO_MARKET_SNAPSHOT_SYNC="${AUTO_MARKET_SNAPSHOT_SYNC:-1}"

cd "$SCRIPT_DIR"

pid_matches_app() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null | grep -F -- "$SCRIPT_DIR/app.py" >/dev/null 2>&1
}

if [ -z "$PYTHON_BIN" ]; then
  for candidate in "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/env/bin/python"; do
    if [ -x "$candidate" ]; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && [ ! -x "$PYTHON_BIN" ]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

# Apply immutable, idempotent migrations before replacing a healthy daemon.
# A failed migration leaves an existing service running instead of starting on
# a partially upgraded schema or losing availability during deployment.
if [[ "$AUTO_DB_UPDATE" != "0" && "$AUTO_DB_UPDATE" != "false" && "$AUTO_DB_UPDATE" != "no" ]]; then
  echo "Checking PostgreSQL schema and master-data updates..."
  if ! "$SCRIPT_DIR/scripts/apply_postgres_updates.sh" >>"$DB_UPDATE_LOG" 2>&1; then
    echo "Database update failed. Existing daemon was not stopped." >&2
    echo "Check: $DB_UPDATE_LOG" >&2
    tail -40 "$DB_UPDATE_LOG" >&2 || true
    exit 1
  fi
  echo "Database schema and master data are up to date. Audit: schema_migrations"
else
  echo "Database auto-update skipped (AUTO_DB_UPDATE=$AUTO_DB_UPDATE)."
fi

# Existing snapshots are already available immediately after migration. Refresh
# market data in a separate process so a slow external quote source never
# delays the daemon restart. The helper uses a PostgreSQL advisory lock.
if [[ "$AUTO_MARKET_SNAPSHOT_SYNC" != "0" && "$AUTO_MARKET_SNAPSHOT_SYNC" != "false" && "$AUTO_MARKET_SNAPSHOT_SYNC" != "no" ]]; then
  nohup env PYTHONUNBUFFERED=1 "$PYTHON_BIN" "$SCRIPT_DIR/scripts/sync_market_snapshots.py" \
    >>"$MARKET_SYNC_LOG" 2>&1 < /dev/null &
  echo "Started background market snapshot refresh. Log: $MARKET_SYNC_LOG"
fi

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null && pid_matches_app "$OLD_PID"; then
    echo "Existing daemon app.py found (PID: $OLD_PID). Restarting it."
    "$SCRIPT_DIR/stop_daemon_app.sh"
    sleep 1
  else
    rm -f "$PID_FILE"
  fi
fi

if lsof -nP -iTCP:"$APP_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $APP_PORT is already in use. Stop the existing process before starting the daemon." >&2
  exit 1
fi

# Disable Flask's reloader so this PID represents the actual daemon process.
nohup env PORT="$APP_PORT" DEBUG=0 PYTHONUNBUFFERED=1 "$PYTHON_BIN" "$SCRIPT_DIR/app.py" \
  >"$LOG_FILE" 2>&1 < /dev/null &
APP_PID=$!
echo "$APP_PID" >"$PID_FILE"

sleep 1
if kill -0 "$APP_PID" 2>/dev/null; then
  echo "Started daemon app.py."
  echo "PID: $APP_PID"
  echo "Port: $APP_PORT"
  echo "Log: $LOG_FILE"
  exit 0
fi

rm -f "$PID_FILE"
echo "Daemon app.py failed to start. Check log: $LOG_FILE" >&2
exit 1
