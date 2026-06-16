#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/app.log"
PID_FILE="$SCRIPT_DIR/.app.pid"
PYTHON_BIN=""

cd "$SCRIPT_DIR"

for candidate in "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/env/bin/python"; do
  if [ -x "$candidate" ]; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "No local virtualenv found in this project directory."
  echo "Expected one of:"
  echo "  $SCRIPT_DIR/.venv/bin/python"
  echo "  $SCRIPT_DIR/venv/bin/python"
  echo "  $SCRIPT_DIR/env/bin/python"
  echo
  echo "Example:"
  echo "  python3 -m venv .venv"
  echo "  source .venv/bin/activate"
  echo "  pip install -r requirements.txt"
  exit 1
fi

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "app.py is already running."
    echo "PID: $OLD_PID"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if pgrep -f "$SCRIPT_DIR/app.py" >/dev/null 2>&1; then
  echo "app.py is already running."
  pgrep -af "$SCRIPT_DIR/app.py"
  exit 0
fi

nohup "$PYTHON_BIN" "$SCRIPT_DIR/app.py" >"$LOG_FILE" 2>&1 &
APP_PID=$!
echo "$APP_PID" >"$PID_FILE"

sleep 1

if kill -0 "$APP_PID" 2>/dev/null; then
  echo "Started app.py successfully."
  echo "PID: $APP_PID"
  echo "Python: $PYTHON_BIN"
  echo "Log: $LOG_FILE"
else
  echo "Failed to start app.py. Check log: $LOG_FILE"
  exit 1
fi
