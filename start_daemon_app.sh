#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.app.daemon.pid"
LOG_FILE="$SCRIPT_DIR/app.daemon.log"
APP_PORT="${PORT:-5001}"
PYTHON_BIN="${PYTHON_BIN:-}"
AUTO_START_POSTGRES="${AUTO_START_POSTGRES:-1}"

cd "$SCRIPT_DIR"

CREDENTIALS_FILE="${POSTGRES_CREDENTIALS_FILE:-/root/gangtise_postgres_credentials}"
if [ -f "$CREDENTIALS_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$CREDENTIALS_FILE"
  set +a
fi

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

if [[ "$AUTO_START_POSTGRES" != "0" && "$AUTO_START_POSTGRES" != "false" && "$AUTO_START_POSTGRES" != "no" ]]; then
  DB_HOST="${LOCAL_POSTGRES_HOST:-${APP_DB_HOST:-127.0.0.1}}"
  DB_PORT="${LOCAL_POSTGRES_PORT:-${APP_DB_PORT:-5432}}"
  if command -v pg_isready >/dev/null 2>&1 && pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
    echo "PostgreSQL is already ready at ${DB_HOST}:${DB_PORT}."
  elif [[ "$DB_HOST" == "127.0.0.1" || "$DB_HOST" == "localhost" || "$DB_HOST" == "::1" ]] && [ "$(id -u)" -eq 0 ] && [ -x "$SCRIPT_DIR/scripts/start_postgres.sh" ]; then
    echo "PostgreSQL is not ready. Starting it automatically..."
    "$SCRIPT_DIR/scripts/start_postgres.sh"
  else
    echo "PostgreSQL is unavailable at ${DB_HOST}:${DB_PORT}." >&2
    echo "Run ./scripts/start_postgres.sh as root, or set AUTO_START_POSTGRES=0 if PostgreSQL is managed externally." >&2
    exit 1
  fi
else
  echo "PostgreSQL auto-start check skipped (AUTO_START_POSTGRES=$AUTO_START_POSTGRES)."
fi

# Database releases, migrations, master data and market snapshots are managed
# exclusively by the release controller on port 5051. Application startup only
# verifies that PostgreSQL is reachable (and may start a local service).

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
