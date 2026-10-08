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
APP_SERVER="${APP_SERVER:-gunicorn}"
PYTHON_BIN="${PYTHON_BIN:-}"
AUTO_START_POSTGRES="${AUTO_START_POSTGRES:-1}"
if [ "$(uname -s)" = "Darwin" ]; then
  GANGTISE_RUNTIME_ENV="${GANGTISE_RUNTIME_ENV:-local}"
else
  GANGTISE_RUNTIME_ENV="${GANGTISE_RUNTIME_ENV:-production}"
fi

# The Admin selector persists the target in .db_runtime.json. Do not try to
# start a local PostgreSQL service when the application is configured for a
# remote staging/production database.
DB_RUNTIME_TARGET="${GANGTISE_DB_TARGET:-}"
if [ -z "$DB_RUNTIME_TARGET" ] && [ -f "$SCRIPT_DIR/.db_runtime.json" ]; then
  DB_RUNTIME_TARGET="$(sed -n 's/.*"target"[[:space:]]*:[[:space:]]*"\([a-z_]*\)".*/\1/p' "$SCRIPT_DIR/.db_runtime.json" | head -n 1)"
  if [ -z "$DB_RUNTIME_TARGET" ] && grep -Eq '"use_staging"[[:space:]]*:[[:space:]]*true' "$SCRIPT_DIR/.db_runtime.json"; then
    DB_RUNTIME_TARGET="staging"
  fi
fi
DB_RUNTIME_TARGET="${DB_RUNTIME_TARGET:-local}"
export GANGTISE_DB_TARGET="$DB_RUNTIME_TARGET"
case "$DB_RUNTIME_TARGET" in
  staging|production)
    AUTO_START_POSTGRES=0
    echo "Application database target: $DB_RUNTIME_TARGET (remote PostgreSQL; local auto-start disabled)."
    ;;
  local)
    echo "Application database target: local PostgreSQL."
    ;;
  *)
    echo "Invalid GANGTISE_DB_TARGET: $DB_RUNTIME_TARGET (expected local, staging, or production)." >&2
    exit 1
    ;;
esac

cd "$SCRIPT_DIR"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/scripts/runtime_process_lib.sh"
APP_SERVER="$(validate_app_server)"
export APP_SERVER

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

ensure_python_dependencies "$SCRIPT_DIR" "$PYTHON_BIN"

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
#
# PID files can be lost after a crash or a manual deployment. Do not start a
# second set of workers in that state: they each maintain their own PostgreSQL
# pool and can exhaust Staging before the port collision becomes apparent.
EXISTING_RUNTIME_PIDS="$(runtime_project_pids "$SCRIPT_DIR" || true)"
if [ -n "$(printf '%s' "$EXISTING_RUNTIME_PIDS" | tr -d '[:space:]')" ]; then
  echo "Existing Gangtise runtime processes found. Stopping them before restart: $EXISTING_RUNTIME_PIDS"
  "$SCRIPT_DIR/stop_daemon_app.sh"
  sleep 1
fi
rm -f "$PID_FILE"

if lsof -nP -iTCP:"$APP_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $APP_PORT is already in use. Stop the existing process before starting the daemon." >&2
  exit 1
fi

# Gunicorn mode keeps queue and scheduler roles outside the Web process.
# Flask mode intentionally uses the legacy single-process lifecycle; starting
# sidecars as well would create duplicate consumers and scheduler loops.
if [[ "$APP_SERVER" == "gunicorn" ]]; then
  start_runtime_sidecar "$SCRIPT_DIR" "$PYTHON_BIN" worker "$WORKER_PID_FILE" "$WORKER_LOG_FILE" "$GANGTISE_RUNTIME_ENV"
  start_runtime_sidecar "$SCRIPT_DIR" "$PYTHON_BIN" scheduler "$SCHEDULER_PID_FILE" "$SCHEDULER_LOG_FILE" "$GANGTISE_RUNTIME_ENV"
fi

nohup env PORT="$APP_PORT" DEBUG=0 APP_SERVER="$APP_SERVER" PYTHONUNBUFFERED=1 GANGTISE_RUNTIME_ENV="$GANGTISE_RUNTIME_ENV" GANGTISE_RUNTIME_ROLE=web "$PYTHON_BIN" "$SCRIPT_DIR/app.py" \
  >"$LOG_FILE" 2>&1 < /dev/null &
APP_PID=$!
echo "$APP_PID" >"$PID_FILE"

EXPECTED_WEB_PROCESS="$SCRIPT_DIR/app.py"
if [[ "$APP_SERVER" == "gunicorn" ]]; then
  EXPECTED_WEB_PROCESS="gunicorn"
fi
if wait_for_runtime_process "$APP_PID" "$EXPECTED_WEB_PROCESS" "${WEB_START_TIMEOUT_SECONDS:-30}"; then
  echo "Started daemon Web service ($APP_SERVER)."
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
