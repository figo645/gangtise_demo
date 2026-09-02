#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.app.daemon.pid"
LOG_FILE="$SCRIPT_DIR/app.daemon.log"
WORKER_PID_FILE="$SCRIPT_DIR/.app.daemon.worker.pid"
SCHEDULER_PID_FILE="$SCRIPT_DIR/.app.daemon.scheduler.pid"
WORKER_LOG_FILE="$SCRIPT_DIR/app.worker.log"
SCHEDULER_LOG_FILE="$SCRIPT_DIR/app.scheduler.log"
APP_PORT="${PORT:-5001}"
PYTHON_BIN="${PYTHON_BIN:-}"
AUTO_START_POSTGRES="${AUTO_START_POSTGRES:-1}"
if [ "$(uname -s)" = "Darwin" ]; then
  GANGTISE_RUNTIME_ENV="${GANGTISE_RUNTIME_ENV:-local}"
else
  GANGTISE_RUNTIME_ENV="${GANGTISE_RUNTIME_ENV:-production}"
fi

cd "$SCRIPT_DIR"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/scripts/runtime_process_lib.sh"

CREDENTIALS_FILE="${POSTGRES_CREDENTIALS_FILE:-$SCRIPT_DIR/.gangtise_postgres_credentials}"
if [ -f "$CREDENTIALS_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$CREDENTIALS_FILE"
  set +a
fi

# Transitional compatibility path: keep the previously working production
# Gangtise credential file beside the deployed application while credentials
# are migrated to PostgreSQL through the Admin console. The path remains
# overrideable for existing deployments.
GANGTISE_CREDENTIALS_FILE="${GANGTISE_OPENAPI_CREDENTIALS_FILE:-$SCRIPT_DIR/.gangtise_openapi_credentials}"
if [ -f "$GANGTISE_CREDENTIALS_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$GANGTISE_CREDENTIALS_FILE"
  set +a
fi

PYTHON_BIN="$(resolve_python_bin "$SCRIPT_DIR")"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && [ ! -x "$PYTHON_BIN" ]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

# API credentials are encrypted with Fernet. Fail before serving traffic if
# the selected production interpreter has not received the declared package.
if ! "$PYTHON_BIN" -c 'from cryptography.fernet import Fernet' >/dev/null 2>&1; then
  echo "Required dependency cryptography is missing from ${PYTHON_BIN}. Run: ${PYTHON_BIN} -m pip install -r ${SCRIPT_DIR}/requirements.txt" >&2
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

# Database releases are managed by the Admin database-release module. Application
# startup only verifies that PostgreSQL is reachable (and may start a local service).

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null && runtime_pid_matches "$OLD_PID" "gunicorn"; then
    echo "Existing daemon Web process found (PID: $OLD_PID). Restarting it."
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

# Web workers intentionally do not host background loops. Start durable queue
# and scheduler roles before the Gunicorn master so request traffic has its
# supporting services from the first successful health probe.
start_runtime_sidecar "$SCRIPT_DIR" "$PYTHON_BIN" worker "$WORKER_PID_FILE" "$WORKER_LOG_FILE" "$GANGTISE_RUNTIME_ENV"
start_runtime_sidecar "$SCRIPT_DIR" "$PYTHON_BIN" scheduler "$SCHEDULER_PID_FILE" "$SCHEDULER_LOG_FILE" "$GANGTISE_RUNTIME_ENV"

nohup env PORT="$APP_PORT" DEBUG=0 APP_SERVER=gunicorn PYTHONUNBUFFERED=1 GANGTISE_RUNTIME_ENV="$GANGTISE_RUNTIME_ENV" "$PYTHON_BIN" "$SCRIPT_DIR/app.py" \
  >"$LOG_FILE" 2>&1 < /dev/null &
APP_PID=$!
echo "$APP_PID" >"$PID_FILE"

if wait_for_runtime_process "$APP_PID" "gunicorn" "${WEB_START_TIMEOUT_SECONDS:-30}"; then
  echo "Started daemon Web service (Gunicorn)."
  echo "PID: $APP_PID"
  echo "Port: $APP_PORT"
  echo "Log: $LOG_FILE"
  exit 0
fi

rm -f "$PID_FILE"
if kill -0 "$APP_PID" 2>/dev/null; then
  kill "$APP_PID" 2>/dev/null || true
fi
stop_runtime_sidecar "$WORKER_PID_FILE" "$SCRIPT_DIR/src/process_worker.py" "worker"
stop_runtime_sidecar "$SCHEDULER_PID_FILE" "$SCRIPT_DIR/src/process_scheduler.py" "scheduler"
echo "Daemon Web service failed to start. Check log: $LOG_FILE" >&2
exit 1
