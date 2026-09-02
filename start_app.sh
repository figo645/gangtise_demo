#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CREDENTIALS_FILE="${POSTGRES_CREDENTIALS_FILE:-$SCRIPT_DIR/.gangtise_postgres_credentials}"
if [ -f "$CREDENTIALS_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$CREDENTIALS_FILE"
  set +a
fi

GANGTISE_CREDENTIALS_FILE="${GANGTISE_OPENAPI_CREDENTIALS_FILE:-$SCRIPT_DIR/.gangtise_openapi_credentials}"
if [ -f "$GANGTISE_CREDENTIALS_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$GANGTISE_CREDENTIALS_FILE"
  set +a
fi

PID_FILE="$SCRIPT_DIR/.app.foreground.pid"
WORKER_PID_FILE="$SCRIPT_DIR/.app.foreground.worker.pid"
SCHEDULER_PID_FILE="$SCRIPT_DIR/.app.foreground.scheduler.pid"
WORKER_LOG_FILE="$SCRIPT_DIR/app.foreground.worker.log"
SCHEDULER_LOG_FILE="$SCRIPT_DIR/app.foreground.scheduler.log"
APP_PORT="${PORT:-5001}"
PYTHON_BIN="${PYTHON_BIN:-}"
if [ "$(uname -s)" = "Darwin" ]; then
  GANGTISE_RUNTIME_ENV="${GANGTISE_RUNTIME_ENV:-local}"
else
  GANGTISE_RUNTIME_ENV="${GANGTISE_RUNTIME_ENV:-production}"
fi

cd "$SCRIPT_DIR"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/scripts/runtime_process_lib.sh"

pid_matches_app() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null | grep -F -- "gunicorn" >/dev/null 2>&1
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

ensure_python_dependencies "$SCRIPT_DIR" "$PYTHON_BIN"

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null && pid_matches_app "$OLD_PID"; then
    echo "Foreground app.py is already running (PID: $OLD_PID)."
    exit 1
  fi
  rm -f "$PID_FILE"
fi

if lsof -nP -iTCP:"$APP_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $APP_PORT is already in use. Stop the existing process before starting the foreground app." >&2
  exit 1
fi

start_runtime_sidecar "$SCRIPT_DIR" "$PYTHON_BIN" worker "$WORKER_PID_FILE" "$WORKER_LOG_FILE" "$GANGTISE_RUNTIME_ENV"
start_runtime_sidecar "$SCRIPT_DIR" "$PYTHON_BIN" scheduler "$SCHEDULER_PID_FILE" "$SCHEDULER_LOG_FILE" "$GANGTISE_RUNTIME_ENV"

APP_PID=""
cleanup_runtime() {
  if [ -n "$APP_PID" ] && kill -0 "$APP_PID" 2>/dev/null; then
    kill "$APP_PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  stop_runtime_sidecar "$WORKER_PID_FILE" "$SCRIPT_DIR/src/process_worker.py" "worker"
  stop_runtime_sidecar "$SCHEDULER_PID_FILE" "$SCRIPT_DIR/src/process_scheduler.py" "scheduler"
}
trap cleanup_runtime EXIT INT TERM

echo "Starting the Gunicorn Web service in the foreground on port $APP_PORT."
env PORT="$APP_PORT" DEBUG=0 APP_SERVER=gunicorn PYTHONUNBUFFERED=1 GANGTISE_RUNTIME_ENV="$GANGTISE_RUNTIME_ENV" "$PYTHON_BIN" "$SCRIPT_DIR/app.py" &
APP_PID=$!
echo "$APP_PID" >"$PID_FILE"

if ! wait_for_runtime_process "$APP_PID" "gunicorn" "${WEB_START_TIMEOUT_SECONDS:-30}"; then
  echo "Foreground Gunicorn Web service failed to start." >&2
  exit 1
fi

echo "Gunicorn master PID: $APP_PID"
echo "Press Ctrl+C to stop it, or run ./stop_app.sh from another terminal."
wait "$APP_PID"
