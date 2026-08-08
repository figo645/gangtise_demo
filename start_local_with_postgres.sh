#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DB_HOST="${LOCAL_POSTGRES_HOST:-127.0.0.1}"
DB_PORT="${LOCAL_POSTGRES_PORT:-5432}"
APP_PORT="${PORT:-5001}"
START_TIMEOUT="${POSTGRES_START_TIMEOUT:-30}"

export LOCAL_POSTGRES_HOST="$DB_HOST"
export LOCAL_POSTGRES_PORT="$DB_PORT"
export PORT="$APP_PORT"

is_postgres_ready() {
  if command -v pg_isready >/dev/null 2>&1; then
    pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1
    return $?
  fi
  if command -v nc >/dev/null 2>&1; then
    nc -z "$DB_HOST" "$DB_PORT" >/dev/null 2>&1
    return $?
  fi
  echo "Neither pg_isready nor nc is installed; cannot check PostgreSQL readiness." >&2
  return 2
}

start_postgres() {
  echo "PostgreSQL is not accepting connections at $DB_HOST:$DB_PORT. Trying to start it..."

  if command -v brew >/dev/null 2>&1; then
    local formula=""
    formula="$(brew list --formula 2>/dev/null | awk '/^postgresql(@[0-9]+)?$/ { print; exit }')"
    if [ -n "$formula" ]; then
      brew services start "$formula" >/dev/null
      return 0
    fi
  fi

  if command -v systemctl >/dev/null 2>&1; then
    if systemctl start postgresql >/dev/null 2>&1; then
      return 0
    fi
    if command -v sudo >/dev/null 2>&1 && sudo systemctl start postgresql >/dev/null 2>&1; then
      return 0
    fi
  fi

  if command -v pg_ctl >/dev/null 2>&1; then
    local data_dir=""
    for candidate in \
      "${PGDATA:-}" \
      "$HOME/.local/var/postgres" \
      "/opt/homebrew/var/postgresql@18" \
      "/opt/homebrew/var/postgresql@17" \
      "/opt/homebrew/var/postgresql@16" \
      "/opt/homebrew/var/postgres" \
      "/usr/local/var/postgresql@16" \
      "/usr/local/var/postgres"; do
      if [ -n "$candidate" ] && [ -f "$candidate/PG_VERSION" ]; then
        data_dir="$candidate"
        break
      fi
    done
    if [ -n "$data_dir" ]; then
      pg_ctl -D "$data_dir" -l "$data_dir/server.log" start >/dev/null
      return 0
    fi
  fi

  echo "Unable to start PostgreSQL automatically." >&2
  echo "Start PostgreSQL manually, then rerun this script." >&2
  return 1
}

if ! is_postgres_ready; then
  start_postgres
fi

for ((second = 1; second <= START_TIMEOUT; second++)); do
  if is_postgres_ready; then
    echo "PostgreSQL is ready at $DB_HOST:$DB_PORT."
    break
  fi
  if [ "$second" -eq "$START_TIMEOUT" ]; then
    echo "PostgreSQL did not become ready within ${START_TIMEOUT}s." >&2
    exit 1
  fi
  sleep 1
done

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  for candidate in \
    "$SCRIPT_DIR/.venv/bin/python" \
    "$SCRIPT_DIR/venv/bin/python" \
    "$SCRIPT_DIR/env/bin/python"; do
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

echo "Starting app.py on port $APP_PORT..."
exec "$PYTHON_BIN" app.py
