#!/usr/bin/env bash
set -euo pipefail

# Create a complete, portable snapshot before removing account-bound runtime
# data. This script is only started by the 5051 release controller.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${DATABASE_RELEASE_TARGET:-}"
DB_NAME="${REMOTE_DB_NAME:-sprint_dashboard}"
DB_USER="${REMOTE_DB_USER:-postgres}"
DB_HOST="${REMOTE_DB_HOST:-}"
DB_PORT="${REMOTE_DB_PORT:-5432}"
DB_PASSWORD="${REMOTE_DB_PASSWORD:-}"
MODE="${USER_DATA_CLEANUP_MODE:-}"
USERNAMES="${USER_DATA_CLEANUP_USERNAMES:-}"
BACKUP_ID="${USER_DATA_BACKUP_ID:-}"
BACKUP_ROOT="${USER_DATA_BACKUP_ROOT:-${ROOT_DIR}/.deploy/user_data_backups}"
RETAIN_COUNT="${USER_DATA_BACKUP_RETAIN_COUNT:-2}"

[[ "$TARGET" =~ ^(local|staging|production)$ ]] || { echo "Invalid cleanup target: ${TARGET}" >&2; exit 2; }
[[ "$MODE" =~ ^(account_runtime_data|all_non_admin_accounts|all_user_business_data)$ ]] || { echo "Invalid cleanup mode: ${MODE}" >&2; exit 2; }
[[ "$BACKUP_ID" =~ ^user_cleanup_${TARGET}_[0-9]{8}_[0-9]{6}_[0-9]{6}$ ]] || { echo "Invalid cleanup backup id: ${BACKUP_ID}" >&2; exit 2; }
[[ -n "$DB_HOST" ]] || { echo "REMOTE_DB_HOST is required." >&2; exit 2; }
[[ "$RETAIN_COUNT" =~ ^[1-9][0-9]*$ ]] || { echo "Invalid backup retention: ${RETAIN_COUNT}" >&2; exit 2; }
for value in DB_NAME DB_USER; do
  [[ "${!value}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || { echo "Invalid PostgreSQL identifier: ${!value}" >&2; exit 2; }
done
if [[ "$MODE" == "account_runtime_data" ]]; then
  [[ -n "$USERNAMES" ]] || { echo "USER_DATA_CLEANUP_USERNAMES is required." >&2; exit 2; }
  [[ ",$USERNAMES," != *,admin,* ]] || { echo "The admin account cannot be included in an account cleanup." >&2; exit 2; }
elif [[ "$MODE" == "all_non_admin_accounts" || "$MODE" == "all_user_business_data" ]]; then
  [[ -z "$USERNAMES" ]] || { echo "USER_DATA_CLEANUP_USERNAMES must be empty for ${MODE}." >&2; exit 2; }
fi
command -v psql >/dev/null 2>&1 || { echo "psql is not installed." >&2; exit 1; }
command -v pg_dump >/dev/null 2>&1 || { echo "pg_dump is not installed." >&2; exit 1; }

export PGPASSWORD="$DB_PASSWORD"
export PGCONNECT_TIMEOUT="${DATABASE_RELEASE_CONNECT_TIMEOUT_SECONDS:-8}"
PSQL=(psql -w -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1)
BACKUP_DIR="${BACKUP_ROOT}/${TARGET}/${BACKUP_ID}"
DUMP_FILE="${BACKUP_DIR}/${BACKUP_ID}.dump"
SQL_FILE="${BACKUP_DIR}/${BACKUP_ID}.sql"
MANIFEST_FILE="${BACKUP_DIR}/manifest.json"

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'; else shasum -a 256 "$1" | awk '{print $1}'; fi
}

cleanup_failed_backup() {
  status=$?
  if [[ ! -f "$MANIFEST_FILE" ]]; then rm -rf "$BACKUP_DIR"; fi
  exit "$status"
}
trap cleanup_failed_backup ERR INT TERM

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
echo "==> [preflight] Checking ${DB_HOST}:${DB_PORT}/${DB_NAME}"
"${PSQL[@]}" -Atqc "SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'users'" | grep -q '^1$' || {
  echo "Required users table is unavailable." >&2
  exit 1
}

echo "==> Exporting complete database backup: ${DUMP_FILE}"
pg_dump -w -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" --format=custom --no-owner --no-acl --file "$DUMP_FILE"
echo "==> Exporting portable SQL backup: ${SQL_FILE}"
pg_dump -w -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" --format=plain --no-owner --no-privileges --no-acl --file "$SQL_FILE"
chmod 600 "$DUMP_FILE" "$SQL_FILE"

DUMP_SHA256="$(sha256_file "$DUMP_FILE")"
SQL_SHA256="$(sha256_file "$SQL_FILE")"
DUMP_BYTES="$(wc -c < "$DUMP_FILE" | tr -d ' ')"
SQL_BYTES="$(wc -c < "$SQL_FILE" | tr -d ' ')"
export BACKUP_ID TARGET MODE USERNAMES DB_NAME DUMP_FILE SQL_FILE DUMP_SHA256 SQL_SHA256 DUMP_BYTES SQL_BYTES MANIFEST_FILE
python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

manifest = {
    "backup_id": os.environ["BACKUP_ID"],
    "target": os.environ["TARGET"],
    "mode": os.environ["MODE"],
    "usernames": [item.strip() for item in os.environ.get("USERNAMES", "").split(",") if item.strip()],
    "database": os.environ["DB_NAME"],
    "created_at": datetime.now(timezone.utc).isoformat(),
    "status": "backup_ready",
    "dump_file": Path(os.environ["DUMP_FILE"]).name,
    "sql_file": Path(os.environ["SQL_FILE"]).name,
    "dump_sha256": os.environ["DUMP_SHA256"],
    "sql_sha256": os.environ["SQL_SHA256"],
    "dump_bytes": int(os.environ["DUMP_BYTES"]),
    "sql_bytes": int(os.environ["SQL_BYTES"]),
}
Path(os.environ["MANIFEST_FILE"]).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
chmod 600 "$MANIFEST_FILE"
echo "==> Complete backup ready: ${BACKUP_ID}"

# All cleanup statements run in one transaction. The all_user_business_data
# mode deliberately retains users and platform configuration while removing
# user-generated content, conversations, messages, analytics, and commerce.
"${PSQL[@]}" -v cleanup_mode="$MODE" -v cleanup_usernames="$USERNAMES" <<'SQL'
BEGIN;
CREATE TEMP TABLE cleanup_users (id BIGINT PRIMARY KEY, username TEXT NOT NULL UNIQUE) ON COMMIT DROP;

SET LOCAL app.cleanup_mode = :'cleanup_mode';
SET LOCAL app.cleanup_usernames = :'cleanup_usernames';

DO $$
DECLARE requested_count INTEGER;
DECLARE selected_count INTEGER;
BEGIN
  IF current_setting('app.cleanup_mode', true) = 'account_runtime_data' THEN
    SELECT count(DISTINCT trim(value)) INTO requested_count
    FROM unnest(string_to_array(current_setting('app.cleanup_usernames', true), ',')) AS value
    WHERE trim(value) <> '';
    INSERT INTO cleanup_users (id, username)
      SELECT id, username FROM users
      WHERE username = ANY(string_to_array(current_setting('app.cleanup_usernames', true), ','));
    SELECT count(*) INTO selected_count FROM cleanup_users;
    IF requested_count = 0 OR selected_count <> requested_count THEN
      RAISE EXCEPTION 'Requested account was not found; requested=% found=%', requested_count, selected_count;
    END IF;
  ELSIF current_setting('app.cleanup_mode', true) = 'all_user_business_data' THEN
    NULL;
  ELSIF current_setting('app.cleanup_mode', true) = 'all_non_admin_accounts' THEN
    INSERT INTO cleanup_users (id, username)
      SELECT id, username FROM users WHERE role <> 'admin';
    SELECT count(*) INTO selected_count FROM cleanup_users;
    IF selected_count = 0 THEN RAISE EXCEPTION 'No non-admin accounts are available for cleanup'; END IF;
  ELSE
    RAISE EXCEPTION 'Unsupported cleanup mode';
  END IF;
  IF EXISTS (SELECT 1 FROM users u JOIN cleanup_users c ON c.id = u.id WHERE u.role = 'admin') THEN
    RAISE EXCEPTION 'Admin accounts cannot be cleaned';
  END IF;
END $$;

DO $$
DECLARE removed INTEGER;
BEGIN
  IF current_setting('app.cleanup_mode', true) = 'all_user_business_data' THEN
    IF to_regclass('public.access_logs') IS NOT NULL THEN DELETE FROM access_logs; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=access_logs rows=%', removed; END IF;
    IF to_regclass('public.user_async_jobs') IS NOT NULL THEN DELETE FROM user_async_jobs; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=user_async_jobs rows=%', removed; END IF;
    IF to_regclass('public.token_usage_logs') IS NOT NULL THEN DELETE FROM token_usage_logs; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=token_usage_logs rows=%', removed; END IF;
    IF to_regclass('public.hermes_conversation_turns') IS NOT NULL THEN DELETE FROM hermes_conversation_turns; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=hermes_conversation_turns rows=%', removed; END IF;
    IF to_regclass('public.hermes_session_memory') IS NOT NULL THEN DELETE FROM hermes_session_memory; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=hermes_session_memory rows=%', removed; END IF;
    IF to_regclass('public.hermes_user_memory') IS NOT NULL THEN DELETE FROM hermes_user_memory; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=hermes_user_memory rows=%', removed; END IF;
    IF to_regclass('public.hermes_user_profiles') IS NOT NULL THEN DELETE FROM hermes_user_profiles; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=hermes_user_profiles rows=%', removed; END IF;
    IF to_regclass('public.hermes_interception_audits') IS NOT NULL THEN DELETE FROM hermes_interception_audits; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=hermes_interception_audits rows=%', removed; END IF;
    IF to_regclass('public.user_watchlist_items') IS NOT NULL THEN DELETE FROM user_watchlist_items; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=user_watchlist_items rows=%', removed; END IF;
    IF to_regclass('public.fan_stock_observation_events') IS NOT NULL THEN DELETE FROM fan_stock_observation_events; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=fan_stock_observation_events rows=%', removed; END IF;
    IF to_regclass('public.watchlist_kline_annotations') IS NOT NULL THEN DELETE FROM watchlist_kline_annotations; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=watchlist_kline_annotations rows=%', removed; END IF;
    IF to_regclass('public.watchlist_comments') IS NOT NULL THEN DELETE FROM watchlist_comments; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=watchlist_comments rows=%', removed; END IF;
    IF to_regclass('public.review_voice_embeddings') IS NOT NULL THEN DELETE FROM review_voice_embeddings; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=review_voice_embeddings rows=%', removed; END IF;
    IF to_regclass('public.tenant_insight_drafts') IS NOT NULL THEN DELETE FROM tenant_insight_drafts; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=tenant_insight_drafts rows=%', removed; END IF;
    IF to_regclass('public.tenant_fan_qr_invite_claims') IS NOT NULL THEN DELETE FROM tenant_fan_qr_invite_claims; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=tenant_fan_qr_invite_claims rows=%', removed; END IF;
    IF to_regclass('public.fan_subscriptions') IS NOT NULL THEN DELETE FROM fan_subscriptions; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=fan_subscriptions rows=%', removed; END IF;
    IF to_regclass('public.fan_payment_orders') IS NOT NULL THEN DELETE FROM fan_payment_orders; GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=fan_payment_orders rows=%', removed; END IF;
    IF to_regclass('public.app_settings') IS NOT NULL THEN
      DELETE FROM app_settings WHERE setting_key LIKE 'h5_profile_settings:%';
      GET DIAGNOSTICS removed = ROW_COUNT;
      RAISE NOTICE 'cleanup_deleted table=app_settings_profile rows=%', removed;
      UPDATE app_settings
      SET setting_value = jsonb_set(
        setting_value::jsonb,
        '{tenants}',
        COALESCE((
          SELECT jsonb_agg(
            tenant || jsonb_build_object(
              'message_center_state', jsonb_build_object(
                'summary', '暂无消息',
                'threads', '[]'::jsonb,
                'broadcasts', '[]'::jsonb
              ),
              'review_snapshots', '[]'::jsonb,
              'insight_drafts', '[]'::jsonb
            )
          )
          FROM jsonb_array_elements(
            CASE
              WHEN jsonb_typeof(setting_value::jsonb -> 'tenants') = 'array'
              THEN setting_value::jsonb -> 'tenants'
              ELSE '[]'::jsonb
            END
          ) AS tenant
        ), '[]'::jsonb), true
      )::text,
      updated_at = CURRENT_TIMESTAMP::text
      WHERE setting_key = 'site_config';
    END IF;
  ELSE
    IF to_regclass('public.user_watchlist_items') IS NOT NULL THEN DELETE FROM user_watchlist_items WHERE user_profile_id IN (SELECT username FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=user_watchlist_items rows=%', removed; END IF;
    IF to_regclass('public.fan_stock_observation_events') IS NOT NULL THEN DELETE FROM fan_stock_observation_events WHERE user_profile_id IN (SELECT username FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=fan_stock_observation_events rows=%', removed; END IF;
    IF to_regclass('public.watchlist_kline_annotations') IS NOT NULL THEN DELETE FROM watchlist_kline_annotations WHERE created_by_user_id IN (SELECT username FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=watchlist_kline_annotations rows=%', removed; END IF;
    IF to_regclass('public.watchlist_comments') IS NOT NULL THEN DELETE FROM watchlist_comments WHERE created_by_user_id IN (SELECT username FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=watchlist_comments rows=%', removed; END IF;
    IF to_regclass('public.hermes_conversation_turns') IS NOT NULL THEN DELETE FROM hermes_conversation_turns WHERE user_profile_id IN (SELECT username FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=hermes_conversation_turns rows=%', removed; END IF;
    IF to_regclass('public.hermes_session_memory') IS NOT NULL THEN DELETE FROM hermes_session_memory WHERE user_profile_id IN (SELECT username FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=hermes_session_memory rows=%', removed; END IF;
    IF to_regclass('public.hermes_user_memory') IS NOT NULL THEN DELETE FROM hermes_user_memory WHERE user_profile_id IN (SELECT username FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=hermes_user_memory rows=%', removed; END IF;
    IF to_regclass('public.hermes_user_profiles') IS NOT NULL THEN DELETE FROM hermes_user_profiles WHERE user_profile_id IN (SELECT username FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=hermes_user_profiles rows=%', removed; END IF;
    IF to_regclass('public.hermes_interception_audits') IS NOT NULL THEN DELETE FROM hermes_interception_audits WHERE user_profile_id IN (SELECT username FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=hermes_interception_audits rows=%', removed; END IF;
    IF to_regclass('public.user_async_jobs') IS NOT NULL THEN DELETE FROM user_async_jobs WHERE owner_label IN (SELECT username FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=user_async_jobs rows=%', removed; END IF;
    IF to_regclass('public.app_settings') IS NOT NULL THEN DELETE FROM app_settings WHERE setting_key IN (SELECT 'h5_profile_settings:' || username FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=app_settings_profile rows=%', removed; END IF;
    IF to_regclass('public.tenant_fan_qr_invite_claims') IS NOT NULL THEN DELETE FROM tenant_fan_qr_invite_claims WHERE user_id IN (SELECT id FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=tenant_fan_qr_invite_claims rows=%', removed; END IF;
    IF to_regclass('public.fan_subscriptions') IS NOT NULL THEN DELETE FROM fan_subscriptions WHERE user_id IN (SELECT id FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=fan_subscriptions rows=%', removed; END IF;
    IF to_regclass('public.fan_payment_orders') IS NOT NULL THEN UPDATE fan_payment_orders SET confirmed_by_user_id = NULL WHERE confirmed_by_user_id IN (SELECT id FROM cleanup_users); DELETE FROM fan_payment_orders WHERE user_id IN (SELECT id FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=fan_payment_orders rows=%', removed; END IF;
    IF to_regclass('public.tenant_subscription_products') IS NOT NULL THEN UPDATE tenant_subscription_products SET created_by_user_id = NULL WHERE created_by_user_id IN (SELECT id FROM cleanup_users); END IF;
    IF to_regclass('public.tenant_fan_qr_invites') IS NOT NULL THEN UPDATE tenant_fan_qr_invites SET created_by_user_id = NULL WHERE created_by_user_id IN (SELECT id FROM cleanup_users); END IF;
    IF current_setting('app.cleanup_mode', true) = 'all_non_admin_accounts' THEN DELETE FROM users WHERE id IN (SELECT id FROM cleanup_users); GET DIAGNOSTICS removed = ROW_COUNT; RAISE NOTICE 'cleanup_deleted table=users rows=%', removed; END IF;
  END IF;
END $$;
COMMIT;
SQL

python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

path = Path(os.environ["MANIFEST_FILE"])
manifest = json.loads(path.read_text(encoding="utf-8"))
manifest["status"] = "cleanup_completed"
manifest["cleanup_completed_at"] = datetime.now(timezone.utc).isoformat()
path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

# Retain only the two newest complete pre-cleanup backups per target.
index=0
while IFS= read -r backup_dir; do
  [[ -n "$backup_dir" ]] || continue
  index=$((index + 1))
  (( index > RETAIN_COUNT )) || continue
  [[ -f "$backup_dir/manifest.json" ]] || continue
  echo "==> Pruning expired user cleanup backup: $(basename "$backup_dir")"
  rm -rf "$backup_dir"
done < <(
  for backup_dir in "${BACKUP_ROOT}/${TARGET}"/user_cleanup_${TARGET}_*/; do
    [[ -d "$backup_dir" ]] && printf '%s\n' "${backup_dir%/}"
  done | sort -r
)
trap - ERR INT TERM
echo "User runtime data cleanup complete. Backup: ${BACKUP_ID}"
