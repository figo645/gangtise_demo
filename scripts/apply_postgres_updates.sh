#!/usr/bin/env bash
set -euo pipefail

# Compatibility entrypoint. Database connections, advisory locking, SQL
# execution, checksum validation and schema_migrations writes are performed by
# scripts/run_postgres_migrations.py, not by psql or shell interpolation.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CREDENTIALS_FILE="${POSTGRES_CREDENTIALS_FILE:-${ROOT_DIR}/.gangtise_postgres_credentials}"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/venv/bin/python" "$ROOT_DIR/env/bin/python" python3; do
    if command -v "$candidate" >/dev/null 2>&1 || [[ -x "$candidate" ]]; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

[[ -n "$PYTHON_BIN" ]] || { echo "Python executable not found." >&2; exit 1; }
exec "$PYTHON_BIN" "$ROOT_DIR/scripts/run_postgres_migrations.py" \
  --credentials-file "$CREDENTIALS_FILE" "$@"
