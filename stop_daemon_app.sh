#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.app.daemon.pid"

pid_matches_app() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null | grep -F -- "$SCRIPT_DIR/app.py" >/dev/null 2>&1
}

if [ ! -f "$PID_FILE" ]; then
  echo "No daemon app process is being tracked."
  exit 0
fi

APP_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [ -z "${APP_PID:-}" ] || ! kill -0 "$APP_PID" 2>/dev/null || ! pid_matches_app "$APP_PID"; then
  rm -f "$PID_FILE"
  echo "Daemon app.py is not running."
  exit 0
fi

kill "$APP_PID"
for _ in 1 2 3 4 5; do
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    break
  fi
  sleep 1
done

if kill -0 "$APP_PID" 2>/dev/null; then
  kill -9 "$APP_PID"
fi

rm -f "$PID_FILE"
echo "Stopped daemon app.py (PID: $APP_PID)."
