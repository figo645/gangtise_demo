#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.app.foreground.pid"
WORKER_PID_FILE="$SCRIPT_DIR/.app.foreground.worker.pid"
SCHEDULER_PID_FILE="$SCRIPT_DIR/.app.foreground.scheduler.pid"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/scripts/runtime_process_lib.sh"

pid_matches_app() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null | grep -F -- "gunicorn" >/dev/null 2>&1
}

if [ ! -f "$PID_FILE" ]; then
  echo "No foreground app process is being tracked."
  stop_runtime_sidecar "$WORKER_PID_FILE" "$SCRIPT_DIR/src/process_worker.py" "worker"
  stop_runtime_sidecar "$SCHEDULER_PID_FILE" "$SCRIPT_DIR/src/process_scheduler.py" "scheduler"
  exit 0
fi

APP_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [ -z "${APP_PID:-}" ] || ! kill -0 "$APP_PID" 2>/dev/null || ! pid_matches_app "$APP_PID"; then
  rm -f "$PID_FILE"
  echo "Foreground app.py is not running."
else
  kill "$APP_PID"
  for _ in 1 2 3 4 5; do
    if ! kill -0 "$APP_PID" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  if kill -0 "$APP_PID" 2>/dev/null; then
    kill -9 "$APP_PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  echo "Stopped foreground Gunicorn Web service (PID: $APP_PID)."
fi

stop_runtime_sidecar "$WORKER_PID_FILE" "$SCRIPT_DIR/src/process_worker.py" "worker"
stop_runtime_sidecar "$SCHEDULER_PID_FILE" "$SCRIPT_DIR/src/process_scheduler.py" "scheduler"
