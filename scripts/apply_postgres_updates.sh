#!/usr/bin/env bash
set -euo pipefail

# Applies immutable numbered SQL migrations and records every execution in
# schema_migrations. Safe to re-run: applied files are skipped after checksum
# verification; changing an applied file fails fast instead of silently drifting.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SQL_DIR="${ROOT_DIR}/sql/postgres"

PGHOST="${PGHOST:-${APP_DB_HOST:-127.0.0.1}}"
PGPORT="${PGPORT:-${APP_DB_PORT:-5432}}"
PGDATABASE="${PGDATABASE:-${APP_DB_NAME:-sprint_dashboard}}"
PGUSER="${PGUSER:-${APP_DB_USER:-postgres}}"
PGPASSWORD="${PGPASSWORD:-${APP_DB_PASSWORD:-your_password}}"
INCLUDE_MASTER_DATA=1

usage() {
  cat <<'EOF'
Usage: ./scripts/apply_postgres_updates.sh [--schema-only]

Environment: PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
Default mode applies schema and master-data migrations. --schema-only skips
100+ master-data files. Use a new numbered SQL file for every database change.
EOF
}

if [[ "${1:-}" == "--schema-only" ]]; then
  INCLUDE_MASTER_DATA=0
elif [[ -n "${1:-}" ]]; then
  usage >&2
  exit 2
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql command not found. Install the PostgreSQL client first." >&2
  exit 1
fi
if [[ ! -d "$SQL_DIR" ]]; then
  echo "SQL directory not found: $SQL_DIR" >&2
  exit 1
fi

export PGPASSWORD
PSQL=(psql --host "$PGHOST" --port "$PGPORT" --username "$PGUSER" --dbname "$PGDATABASE" --set ON_ERROR_STOP=1 --no-psqlrc)

checksum() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

sql_literal() {
  printf "%s" "$1" | sed "s/'/''/g"
}

"${PSQL[@]}" --command "
CREATE TABLE IF NOT EXISTS schema_migrations (
  migration_name TEXT PRIMARY KEY,
  migration_scope TEXT NOT NULL CHECK (migration_scope IN ('schema', 'master_data')),
  checksum_sha256 TEXT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  execution_ms INTEGER NOT NULL DEFAULT 0
);"

FILES=()
while IFS= read -r file; do
  FILES+=("$file")
done < <(find "$SQL_DIR" -maxdepth 1 -type f -name '[0-9][0-9][0-9]_*.sql' -print | sort)
if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "No numbered SQL migrations found in $SQL_DIR" >&2
  exit 1
fi

applied=0
skipped=0
for file in "${FILES[@]}"; do
  name="$(basename "$file")"
  version="${name%%_*}"
  [[ "$version" == "000" ]] && continue
  case "$version" in
    0??)
      scope="schema"
      ;;
    *)
      scope="master_data"
      [[ "$INCLUDE_MASTER_DATA" -eq 0 ]] && continue
      ;;
  esac
  digest="$(checksum "$file")"
  row="$("${PSQL[@]}" --tuples-only --no-align --field-separator '|' --command "SELECT checksum_sha256 FROM schema_migrations WHERE migration_name = '$(sql_literal "$name")';")"
  recorded="${row//$'\n'/}"
  if [[ -n "$recorded" ]]; then
    if [[ "$recorded" != "$digest" ]]; then
      echo "Checksum mismatch for $name. Do not edit an applied migration; add a new numbered file." >&2
      exit 1
    fi
    echo "SKIP  $name (already applied)"
    skipped=$((skipped + 1))
    continue
  fi

  started="$(date +%s)"
  wrapper="$(mktemp)"
  trap 'rm -f "$wrapper"' EXIT
  {
    echo 'BEGIN;'
    echo "SET LOCAL lock_timeout = '10s';"
    echo "SET LOCAL statement_timeout = '120s';"
    printf "\\i '%s'\n" "$file"
    printf "INSERT INTO schema_migrations (migration_name, migration_scope, checksum_sha256, execution_ms) VALUES ('%s', '%s', '%s', 0);\n" "$(sql_literal "$name")" "$scope" "$digest"
    echo 'COMMIT;'
  } > "$wrapper"
  echo "APPLY $name"
  "${PSQL[@]}" --file "$wrapper"
  rm -f "$wrapper"
  trap - EXIT
  elapsed=$(( $(date +%s) - started ))
  "${PSQL[@]}" --command "UPDATE schema_migrations SET execution_ms = ${elapsed} * 1000 WHERE migration_name = '$(sql_literal "$name")';" >/dev/null
  applied=$((applied + 1))
done

echo "Postgres updates completed: applied=${applied}, skipped=${skipped}, database=${PGDATABASE}, host=${PGHOST}:${PGPORT}"
echo "Audit: SELECT migration_name, migration_scope, applied_at, execution_ms FROM schema_migrations ORDER BY applied_at;"
