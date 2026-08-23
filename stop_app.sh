#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.app.foreground.pid"

pid_matches_app() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null | grep -F -- "$SCRIPT_DIR/app.py" >/dev/null 2>&1
}

if [ ! -f "$PID_FILE" ]; then
  echo "No foreground app process is being tracked."
  exit 0
fi

APP_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
if [ -z "${APP_PID:-}" ] || ! kill -0 "$APP_PID" 2>/dev/null || ! pid_matches_app "$APP_PID"; then
  rm -f "$PID_FILE"
  echo "Foreground app.py is not running."
  exit 0
fi

kill "$APP_PID"
rm -f "$PID_FILE"
echo "Stopped foreground app.py (PID: $APP_PID)."
