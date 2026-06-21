#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SQL_DIR="${ROOT_DIR}/sql/postgres"

PGHOST="${PGHOST:-${VECTOR_DB_HOST:-${IP:-129.211.65.53}}}"
PGPORT="${PGPORT:-${VECTOR_DB_PORT:-5432}}"
PGDATABASE="${PGDATABASE:-postgres}"
TARGET_DB="${TARGET_DB:-${POSTGRES_DB:-sprint_dashboard}}"
PGUSER="${PGUSER:-${POSTGRES_USER:-postgres}}"
PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-your_password}}"

export PGPASSWORD

if ! command -v psql >/dev/null 2>&1; then
  echo "psql command not found. Please install PostgreSQL client first." >&2
  exit 1
fi

run_sql() {
  local db_name="$1"
  local sql_file="$2"
  echo "==> Running ${sql_file##*/} on database ${db_name}"
  psql \
    --host "$PGHOST" \
    --port "$PGPORT" \
    --username "$PGUSER" \
    --dbname "$db_name" \
    --set ON_ERROR_STOP=1 \
    --file "$sql_file"
}

echo "==> Target host: $PGHOST:$PGPORT"
echo "==> Bootstrap database: $PGDATABASE"
echo "==> Target database: $TARGET_DB"
echo "==> Login user: $PGUSER"

run_sql "$PGDATABASE" "${SQL_DIR}/000_create_database.sql"
run_sql "$TARGET_DB" "${SQL_DIR}/001_enable_pgvector.sql"
run_sql "$TARGET_DB" "${SQL_DIR}/010_review_voice_embeddings.sql"
run_sql "$TARGET_DB" "${SQL_DIR}/011_review_voice_embeddings_alter_legacy_columns.sql"
run_sql "$TARGET_DB" "${SQL_DIR}/012_review_voice_embeddings_pgvector.sql"
run_sql "$TARGET_DB" "${SQL_DIR}/020_knowledge_embeddings.sql"
run_sql "$TARGET_DB" "${SQL_DIR}/021_knowledge_embeddings_pgvector.sql"
run_sql "$TARGET_DB" "${SQL_DIR}/100_seed_master_data.sql"

echo "==> Postgres / pgvector initialization completed successfully."
