#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

export DATABASE_RELEASE_HOST="${DATABASE_RELEASE_HOST:-127.0.0.1}"
export DATABASE_RELEASE_PORT="${DATABASE_RELEASE_PORT:-5051}"
exec "$PYTHON_BIN" "$ROOT_DIR/tools/database_release_web.py"
