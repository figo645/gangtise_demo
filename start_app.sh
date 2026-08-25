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
APP_PORT="${PORT:-5001}"
PYTHON_BIN="${PYTHON_BIN:-}"

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

echo "$$" >"$PID_FILE"

echo "Starting app.py in the foreground on port $APP_PORT."
echo "Press Ctrl+C to stop it, or run ./stop_app.sh from another terminal."

exec env PORT="$APP_PORT" PYTHONUNBUFFERED=1 "$PYTHON_BIN" "$SCRIPT_DIR/app.py"
