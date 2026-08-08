#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${1:-$ROOT_DIR/gangtise_demo.db}"
OUT_DIR="${2:-$ROOT_DIR/db_backups/sql}"
STAMP="${BACKUP_STAMP:-20260805}"

MASTER_TABLES=(
  app_settings
  users
  indicator_definitions
  indicator_source_defs
  indicator_mapping_rules
)

BUSINESS_TABLES=(
  access_logs
  indicator_source_tests
  indicator_load_batches
  indicator_latest_values
  indicator_series
  indicator_kline_points
  indicator_anomalies
  indicator_raw_records
  indicator_clean_jobs
)

if [[ ! -f "$DB_PATH" ]]; then
  echo "Database file not found: $DB_PATH" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

SCHEMA_FILE="$OUT_DIR/${STAMP}_current_schema.sql"
MASTER_FILE="$OUT_DIR/${STAMP}_master_data.sql"
BUSINESS_FILE="$OUT_DIR/${STAMP}_business_data.sql"

write_header() {
  local target_file="$1"
  local title="$2"
  {
    echo "-- ${title}"
    echo "-- Source database: ${DB_PATH}"
    echo "-- Generated at: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "PRAGMA foreign_keys=OFF;"
    echo "BEGIN TRANSACTION;"
    echo
  } > "$target_file"
}

append_footer() {
  local target_file="$1"
  echo "COMMIT;" >> "$target_file"
}

dump_table_data() {
  local table_name="$1"
  local target_file="$2"
  {
    echo "-- Table: ${table_name}"
    echo "DELETE FROM ${table_name};"
    sqlite3 "$DB_PATH" <<SQL
.mode insert ${table_name}
SELECT * FROM ${table_name};
SQL
    echo
  } >> "$target_file"
}

{
  echo "-- Current schema backup"
  echo "-- Source database: ${DB_PATH}"
  echo "-- Generated at: $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  sqlite3 "$DB_PATH" ".schema" | grep -v "sqlite_sequence" || true
} > "$SCHEMA_FILE"

write_header "$MASTER_FILE" "Master data backup"
for table_name in "${MASTER_TABLES[@]}"; do
  dump_table_data "$table_name" "$MASTER_FILE"
done
append_footer "$MASTER_FILE"

write_header "$BUSINESS_FILE" "Business data backup"
for table_name in "${BUSINESS_TABLES[@]}"; do
  dump_table_data "$table_name" "$BUSINESS_FILE"
done
append_footer "$BUSINESS_FILE"

echo "Schema backup   : $SCHEMA_FILE"
echo "Master data     : $MASTER_FILE"
echo "Business data   : $BUSINESS_FILE"
