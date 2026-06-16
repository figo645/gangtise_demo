#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.app.pid"

cd "$SCRIPT_DIR"

if [ -f "$PID_FILE" ]; then
  APP_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${APP_PID:-}" ] && kill -0 "$APP_PID" 2>/dev/null; then
    kill "$APP_PID" 2>/dev/null || true
    sleep 1
    if kill -0 "$APP_PID" 2>/dev/null; then
      kill -9 "$APP_PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    echo "Stopped app.py."
    exit 0
  fi
  rm -f "$PID_FILE"
fi

PIDS="$(pgrep -f "$SCRIPT_DIR/app.py" || true)"
if [ -n "$PIDS" ]; then
  kill $PIDS 2>/dev/null || true
  sleep 1
  for pid in $PIDS; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
  echo "Stopped app.py."
  exit 0
fi

echo "app.py is not running."
