#!/usr/bin/env python3
"""Read-only local-to-target PostgreSQL release audit.

Schema metadata is compared for every application table. Row-level comparison
is deliberately limited to MDM-managed master data and uses business-key
digests; runtime, user, account and environment configuration data is never
scanned as a release difference. The tool never exports row values, modifies a
database, or creates release packages.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import psycopg2


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.domain.core_services import get_local_app_db_target  # noqa: E402
from src.domain.database_release_services import get_database_release_target  # noqa: E402


MAX_HASH_BYTES = 128 * 1024 * 1024
MAX_GENERATED_ROWS_PER_TABLE = 10000
EXCLUDED_LEDGER_TABLES = {"database_release_packages", "schema_migrations"}
# These tables belong to the release controller itself. They are allowed to
# exist only on the target and must not be treated as application drift.
EXCLUDED_SCHEMA_TABLES = EXCLUDED_LEDGER_TABLES
MDM_MASTER_DATA_TABLES = {
    "security_master",
    "indicator_definitions",
    "indicator_mapping_rules",
    "indicator_source_defs",
    "quiz_questions",
}
MDM_MASTER_DATA_KEYS = {
    "indicator_definitions": "indicator_code",
    "indicator_mapping_rules": "rule_code",
    "indicator_source_defs": "source_code",
    "security_master": "security_code",
    "quiz_questions": "question_code",
}
CONFIGURATION_TABLES = {"admin_task_configs", "app_settings", "tenant_registry", "tenant_subscription_products", "tenant_fan_qr_invites", "open_api_tokens"}
RUNTIME_SETTING_PREFIXES = (
    "watchlist_intraday_cache:",
    "watchlist_detail_cache:",
    "watchlist_search_cache:",
    "h5_profile_settings:",
    "fundamental_news_lake:",
)
# These settings are environment-owned secrets. A database release may not
# copy encrypted values between local, staging, and production because each
# runtime has its own application secret.
PROTECTED_SETTING_KEYS = {
    "gangtise_openapi_credentials:v1",
    "gangtise_openapi_token:v1",
    "llm_api_credentials:v1",
}
RUNTIME_DATA_TABLES = {
    "access_logs",
    "admin_task_runs",
    "fan_stock_observation_events",
    "hermes_conversation_turns",
    "indicator_source_tests",
    "review_voice_embeddings",
    "token_usage_logs",
    "user_async_jobs",
    "users",
    "watchlist_comments",
    "watchlist_kline_annotations",
}
RUNTIME_DATA_TABLES.update({
    "daily_quiz_sets",
    "market_snapshot_payloads",
    "indicator_series",
    "indicator_kline_points",
    "indicator_latest_values",
    "indicator_raw_records",
    "indicator_load_batches",
})
VOLATILE_DATA_COLUMNS = {"created_at", "updated_at", "started_at", "finished_at", "applied_at", "last_tested_at"}
TABLE_RUNTIME_COLUMNS = {
    "admin_task_configs": {
        "last_run_started_at",
        "last_run_finished_at",
        "last_run_status",
        "last_run_message",
        "last_run_duration_ms",
        "last_next_run_at",
        "last_error_at",
        "last_error_message",
    },
}


def _quote_identifier(value):
    return '"' + str(value).replace('"', '""') + '"'


def _connect(target):
    try:
        statement_timeout_ms = int(os.environ.get("DATABASE_RELEASE_SCAN_STATEMENT_TIMEOUT_MS", "120000"))
    except (TypeError, ValueError):
        statement_timeout_ms = 120000
    statement_timeout_ms = max(1000, min(statement_timeout_ms, 600000))
    return psycopg2.connect(
        host=target["host"] if "host" in target else target["db_host"],
        port=target["port"] if "port" in target else target["db_port"],
        dbname=target["dbname"] if "dbname" in target else target["db_name"],
        user=target["user"] if "user" in target else target["db_user"],
        password=target["password"] if "password" in target else target["db_password"],
        connect_timeout=8,
        options=f"-c statement_timeout={statement_timeout_ms} -c lock_timeout=5000 -c application_name=database_release_diff",
    )


def _public_tables(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        return [row[0] for row in cursor.fetchall()]


def _table_schema(connection, table_name):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT column_name, data_type, udt_name, is_nullable, column_default, ordinal_position
               FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = %s
               ORDER BY ordinal_position""",
            (table_name,),
        )
        columns = [list(row) for row in cursor.fetchall()]
        cursor.execute(
            """SELECT conname, contype, pg_get_constraintdef(c.oid, true)
               FROM pg_constraint c
               JOIN pg_class r ON r.oid = c.conrelid
               JOIN pg_namespace n ON n.oid = r.relnamespace
               WHERE n.nspname = 'public' AND r.relname = %s
               ORDER BY conname""",
            (table_name,),
        )
        constraints = [list(row) for row in cursor.fetchall()]
        cursor.execute(
            """SELECT indexname, indexdef FROM pg_indexes
               WHERE schemaname = 'public' AND tablename = %s
               ORDER BY indexname""",
            (table_name,),
        )
        indexes = [list(row) for row in cursor.fetchall()]
    payload = {"columns": columns, "constraints": constraints, "indexes": indexes}
    return {"hash": _digest(payload), **payload}


def _table_data_digest(connection, table_name, ignore_volatile_columns=False):
    quoted_table = _quote_identifier(table_name)
    relation = f"public.{quoted_table}"
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT count(*), pg_total_relation_size(%s::regclass) FROM {quoted_table}", (relation,))
        row_count, relation_size = cursor.fetchone()
        if int(relation_size or 0) > MAX_HASH_BYTES:
            return {"row_count": int(row_count or 0), "bytes": int(relation_size or 0), "hash": "", "status": "skipped_large_table"}
        cursor.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = %s
               ORDER BY ordinal_position""",
            (table_name,),
        )
        ignored = [name for (name,) in cursor.fetchall() if ignore_volatile_columns and name in VOLATILE_DATA_COLUMNS]
        ignored_sql = ", ".join("'" + name + "'" for name in ignored)
        payload = f"to_jsonb(t) - ARRAY[{ignored_sql}]" if ignored else "to_jsonb(t)"
        # JSONB text gives a canonical key order. Ordering values makes the
        # digest independent of physical row order without exposing row data.
        cursor.execute(f"SELECT ({payload})::text FROM {quoted_table} AS t ORDER BY ({payload})::text")
        digest = hashlib.sha256()
        while True:
            rows = cursor.fetchmany(1000)
            if not rows:
                break
            for item in rows:
                digest.update(str(item[0]).encode("utf-8"))
                digest.update(b"\n")
    return {"row_count": int(row_count or 0), "bytes": int(relation_size or 0), "hash": digest.hexdigest(), "status": "hashed", "ignored_columns": ignored}


def _stable_master_rows(connection, table_name):
    """Return business-key to stable row digest without persisting row values."""
    key_column = MDM_MASTER_DATA_KEYS[table_name]
    quoted_table = _quote_identifier(table_name)
    quoted_key = _quote_identifier(key_column)
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = %s
               ORDER BY ordinal_position""",
            (table_name,),
        )
        ignored_columns = VOLATILE_DATA_COLUMNS | TABLE_RUNTIME_COLUMNS.get(table_name, set())
        ignored = [name for (name,) in cursor.fetchall() if name in ignored_columns]
        ignored_sql = ", ".join("'" + name + "'" for name in ignored)
        payload = f"to_jsonb(t) - ARRAY[{ignored_sql}]" if ignored else "to_jsonb(t)"
        cursor.execute(f"SELECT {quoted_key}::text, ({payload})::text FROM {quoted_table} AS t ORDER BY {quoted_key}::text")
        rows = {}
        for key, payload_text in cursor.fetchall():
            normalized_key = str(key or "")
            rows[normalized_key] = hashlib.sha256(str(payload_text).encode("utf-8")).hexdigest()
    return rows


def _stable_master_difference(connection, target_connection, table_name):
    local_rows = _stable_master_rows(connection, table_name)
    target_rows = _stable_master_rows(target_connection, table_name)
    local_keys, target_keys = set(local_rows), set(target_rows)
    changed = sorted(key for key in local_keys & target_keys if local_rows[key] != target_rows[key])
    return {
        "local_only": sorted(local_keys - target_keys),
        "target_only": sorted(target_keys - local_keys),
        "changed_shared": changed,
    }


def _ledger(connection, target_name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.database_release_packages')")
        if not cursor.fetchone()[0]:
            return []
        cursor.execute(
            """SELECT release_version, package_type, title, checksum_sha256, status, applied_at
               FROM database_release_packages
               WHERE target_environment = %s
               ORDER BY applied_at, release_version""",
            (target_name,),
        )
        return [
            {"version": row[0], "type": row[1], "title": row[2], "checksum": row[3], "status": row[4], "applied_at": str(row[5])}
            for row in cursor.fetchall()
        ]


def _migration_ledger(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.schema_migrations')")
        if not cursor.fetchone()[0]:
            return {}
        cursor.execute(
            "SELECT migration_name, migration_scope, checksum_sha256 "
            "FROM schema_migrations ORDER BY migration_name"
        )
        return {
            str(name): {"scope": str(scope), "checksum": str(checksum)}
            for name, scope, checksum in cursor.fetchall()
        }


def _migration_differences(local_migrations, target_migrations):
    """Separate release-blocking schema history from non-structural history.

    A schema-only release flows from local to target. Target-only migrations
    are historical facts about the target, not proof of structural drift: the
    table/column/index comparison is authoritative for that. Master-data
    migration ledgers are deliberately never auto-repaired by this workflow.
    """
    local_names, target_names = set(local_migrations), set(target_migrations)
    local_only = sorted(local_names - target_names)
    target_only = sorted(target_names - local_names)
    checksum_mismatch = sorted(
        name for name in local_names & target_names
        if local_migrations[name]["checksum"] != target_migrations[name]["checksum"]
    )
    strict = {
        "local_only": [name for name in local_only if local_migrations[name]["scope"] == "schema"],
        # A target-only structural migration is reported for governance, but
        # cannot block an additive local-to-target release when metadata is equal.
        "target_only": [],
        "checksum_mismatch": [
            name for name in checksum_mismatch
            if local_migrations[name]["scope"] == "schema" or target_migrations[name]["scope"] == "schema"
        ],
    }
    strict_names = set(strict["local_only"]) | set(strict["checksum_mismatch"])
    observed = {
        "local_only": [name for name in local_only if name not in strict_names],
        "target_only": target_only,
        "checksum_mismatch": [name for name in checksum_mismatch if name not in strict_names],
    }
    return {
        "local_only": local_only,
        "target_only": target_only,
        "checksum_mismatch": checksum_mismatch,
        "strict_schema": strict,
        "non_structural": observed,
    }


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _safe_target(target):
    return {"label": target.get("label") or target.get("name"), "host": target.get("host") or target.get("db_host"), "port": target.get("port") or target.get("db_port"), "database": target.get("dbname") or target.get("db_name")}


def _column_specs(connection, table_name):
    quoted_table = _quote_identifier(table_name)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull,
                       pg_get_expr(d.adbin, d.adrelid), a.attidentity,
                       pg_get_serial_sequence(format('%%I.%%I', n.nspname, c.relname), a.attname)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                WHERE n.nspname = 'public' AND c.relname = %s
                  AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY a.attnum""",
            (table_name,),
        )
        return [
            {
                "name": row[0], "type": row[1], "not_null": bool(row[2]),
                "default": row[3] or "", "identity": row[4] or "",
                "serial_sequence": row[5] or "",
            }
            for row in cursor.fetchall()
        ]


def _column_definition(spec, allow_not_null=True):
    parts = [_quote_identifier(spec["name"]), spec["type"]]
    if spec.get("identity"):
        parts.append("GENERATED " + ("ALWAYS" if spec["identity"] == "a" else "BY DEFAULT") + " AS IDENTITY")
    elif spec.get("default"):
        parts.append("DEFAULT " + spec["default"])
    if allow_not_null and spec.get("not_null"):
        parts.append("NOT NULL")
    return " ".join(parts)


def _serial_sequence_identifier(spec):
    """Return a safely qualified public serial sequence name, if applicable."""
    raw_name = str(spec.get("serial_sequence") or "").strip()
    if not raw_name:
        return ""
    normalized = raw_name.replace('"', "")
    parts = normalized.split(".")
    if len(parts) != 2 or parts[0] != "public" or not parts[1]:
        return ""
    return "public." + _quote_identifier(parts[1])


def _append_serial_sequence_statements(statements, actions, table_name, specs):
    """Create sequences before a table or column references ``nextval``."""
    bindings = []
    for spec in specs:
        sequence_identifier = _serial_sequence_identifier(spec)
        if not sequence_identifier:
            continue
        statements.append("CREATE SEQUENCE IF NOT EXISTS " + sequence_identifier + ";")
        actions.append({"table": table_name, "column": spec["name"], "sequence": sequence_identifier, "action": "create_sequence"})
        bindings.append((sequence_identifier, spec["name"]))
    return bindings


def _append_serial_sequence_ownership(statements, actions, table_name, bindings):
    for sequence_identifier, column_name in bindings:
        statements.append(
            "ALTER SEQUENCE " + sequence_identifier + " OWNED BY "
            + _quote_identifier(table_name) + "." + _quote_identifier(column_name) + ";"
        )
        actions.append({"table": table_name, "column": column_name, "sequence": sequence_identifier, "action": "own_sequence"})


def _primary_key_columns(connection, table_name):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT a.attname
               FROM pg_constraint c
               JOIN unnest(c.conkey) WITH ORDINALITY AS key(attnum, ord) ON true
               JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = key.attnum
               JOIN pg_class r ON r.oid = c.conrelid
               JOIN pg_namespace n ON n.oid = r.relnamespace
               WHERE n.nspname = 'public' AND r.relname = %s AND c.contype = 'p'
               ORDER BY key.ord""",
            (table_name,),
        )
        return [row[0] for row in cursor.fetchall()]


def _table_constraints(connection, table_name):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT conname, pg_get_constraintdef(c.oid, true)
               FROM pg_constraint c
               JOIN pg_class r ON r.oid = c.conrelid
               JOIN pg_namespace n ON n.oid = r.relnamespace
               WHERE n.nspname = 'public' AND r.relname = %s
               ORDER BY conname""",
            (table_name,),
        )
        return {str(name): str(definition) for name, definition in cursor.fetchall()}


def _table_indexes(connection, table_name):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT indexname, indexdef FROM pg_indexes
               WHERE schemaname = 'public' AND tablename = %s
               ORDER BY indexname""",
            (table_name,),
        )
        return {str(name): str(definition) for name, definition in cursor.fetchall()}


def _constraint_release_phase(definition):
    """Return the DDL phase required for an additive table constraint."""
    normalized = str(definition or "").lstrip().upper()
    if normalized.startswith("PRIMARY KEY") or normalized.startswith("UNIQUE"):
        return "key"
    if normalized.startswith("FOREIGN KEY"):
        return "foreign_key"
    return "other"


def _tenant_registry_reference_repair_statement(table_name, definition):
    """Return the narrowly-scoped parent-row repair needed before a tenant FK.

    Older deployments can contain valid tenant-scoped records created before
    ``tenant_registry`` became the canonical aggregate root.  Adding the FK
    must not delete or rewrite those records.  This statement only creates a
    missing registry parent for a canonical, non-empty tenant slug.  Invalid
    historic values remain a hard failure rather than being silently changed.
    """
    normalized = re.sub(r'\s+', ' ', str(definition or '')).strip().lower()
    expected = "foreign key (tenant_slug) references tenant_registry(tenant_slug) on delete restrict"
    if normalized != expected:
        return ""
    child = _quote_identifier(table_name)
    return (
        "DO $$ BEGIN "
        f"IF EXISTS (SELECT 1 FROM {child} "
        "WHERE tenant_slug IS NULL OR btrim(tenant_slug) = '' "
        "OR tenant_slug <> lower(btrim(tenant_slug))) THEN "
        f"RAISE EXCEPTION 'tenant_registry_reference_invalid:{table_name}'; END IF; "
        "INSERT INTO tenant_registry (tenant_slug, tenant_name, created_at, updated_at) "
        f"SELECT DISTINCT child.tenant_slug, child.tenant_slug, CURRENT_TIMESTAMP::text, CURRENT_TIMESTAMP::text FROM {child} child "
        "LEFT JOIN tenant_registry registry ON registry.tenant_slug = child.tenant_slug "
        "WHERE registry.tenant_slug IS NULL "
        "ON CONFLICT (tenant_slug) DO NOTHING; "
        "END $$;"
    )


def _schema_incremental_sql(local_connection, target_connection, report, schema_only=False):
    """Build only additive, idempotent DDL and report unsafe schema changes."""
    local_tables = [name for name in _public_tables(local_connection) if name not in EXCLUDED_SCHEMA_TABLES]
    target_tables = [name for name in _public_tables(target_connection) if name not in EXCLUDED_SCHEMA_TABLES]
    local_set, target_set = set(local_tables), set(target_tables)
    # A foreign key may point at another table that is also new in this
    # release. Emit all tables before any constraint, then indexes last.
    # Alphabetical table iteration alone is not a dependency order.
    foundation_statements, key_constraint_statements = [], []
    foreign_key_repair_statements, foreign_key_statements = [], []
    other_constraint_statements, index_statements = [], []
    blockers, actions = [], []

    def append_constraint(table_name, name, definition):
        statement = (
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = "
            + "'" + name.replace("'", "''") + "' AND conrelid = 'public."
            + table_name.replace('"', '""').replace("'", "''") + "'::regclass) THEN ALTER TABLE " + _quote_identifier(table_name)
            + " ADD CONSTRAINT " + _quote_identifier(name) + " " + definition + "; END IF; END $$;"
        )
        phase = _constraint_release_phase(definition)
        if phase == "key":
            key_constraint_statements.append(statement)
        elif phase == "foreign_key":
            repair_statement = _tenant_registry_reference_repair_statement(table_name, definition)
            if repair_statement:
                foreign_key_repair_statements.append(repair_statement)
                actions.append({
                    "table": table_name,
                    "parent_table": "tenant_registry",
                    "action": "reconcile_missing_tenant_registry_references",
                })
            foreign_key_statements.append(statement)
        else:
            other_constraint_statements.append(statement)
        actions.append({"table": table_name, "constraint": name, "action": "add_constraint"})

    for table_name in sorted(local_set - target_set):
        specs = _column_specs(local_connection, table_name)
        if not specs:
            blockers.append({"table": table_name, "reason": "source_table_has_no_columns"})
            continue
        unmanaged_sequences = [
            spec["name"] for spec in specs
            if "nextval(" in str(spec.get("default") or "") and not _serial_sequence_identifier(spec)
        ]
        if unmanaged_sequences:
            blockers.append({"table": table_name, "columns": unmanaged_sequences, "reason": "unmanaged_sequence_default"})
            continue
        sequence_bindings = _append_serial_sequence_statements(foundation_statements, actions, table_name, specs)
        foundation_statements.append(
            "CREATE TABLE IF NOT EXISTS " + _quote_identifier(table_name) + " (\n    "
            + ",\n    ".join(_column_definition(spec) for spec in specs) + "\n);"
        )
        actions.append({"table": table_name, "action": "create_table"})
        _append_serial_sequence_ownership(foundation_statements, actions, table_name, sequence_bindings)
        for name, definition in _table_constraints(local_connection, table_name).items():
            append_constraint(table_name, name, definition)
        for name, definition in _table_indexes(local_connection, table_name).items():
            index_sql = re.sub(r"^CREATE( UNIQUE)? INDEX ", r"CREATE\1 INDEX IF NOT EXISTS ", definition, count=1)
            index_statements.append(index_sql.rstrip(";") + ";")
            actions.append({"table": table_name, "index": name, "action": "add_index"})
    changed_tables = set(report["schema"].get("different_tables") or [])
    for table_name in sorted((local_set & target_set) & changed_tables):
        local_specs = {item["name"]: item for item in _column_specs(local_connection, table_name)}
        target_specs = {item["name"]: item for item in _column_specs(target_connection, table_name)}
        # A schema-only release must never inspect business rows. Be
        # conservative for a new NOT NULL column without a default: the
        # target may contain rows, and a data backfill is outside this path.
        target_rows = 0 if schema_only else _table_data_digest(target_connection, table_name).get("row_count", 0)
        for name in sorted(set(local_specs) - set(target_specs)):
            spec = local_specs[name]
            if "nextval(" in str(spec.get("default") or ""):
                # Adding a serial default to an existing table may invoke
                # nextval for existing rows. That is a data rewrite and is
                # intentionally outside the zero-business-data-write path.
                blockers.append({"table": table_name, "column": name, "reason": "sequence_default_on_existing_table"})
                continue
            if spec["not_null"] and not spec["default"] and not spec["identity"] and (schema_only or target_rows):
                blockers.append({"table": table_name, "column": name, "reason": "non_null_column_without_default"})
                continue
            foundation_statements.append(
                "ALTER TABLE " + _quote_identifier(table_name) + " ADD COLUMN IF NOT EXISTS "
                + _column_definition(spec) + ";"
            )
            actions.append({"table": table_name, "column": name, "action": "add_column"})
        for name in sorted(set(local_specs) & set(target_specs)):
            local_spec, target_spec = local_specs[name], target_specs[name]
            if (local_spec["type"], local_spec["not_null"], local_spec["default"], local_spec["identity"]) != (target_spec["type"], target_spec["not_null"], target_spec["default"], target_spec["identity"]):
                blockers.append({"table": table_name, "column": name, "reason": "existing_column_definition_differs"})
        local_constraints = _table_constraints(local_connection, table_name)
        target_constraints = _table_constraints(target_connection, table_name)
        for name in sorted(set(local_constraints) - set(target_constraints)):
            append_constraint(table_name, name, local_constraints[name])
        for name in sorted(set(local_constraints) & set(target_constraints)):
            if local_constraints[name] != target_constraints[name]:
                blockers.append({"table": table_name, "constraint": name, "reason": "existing_constraint_definition_differs"})
        local_indexes = _table_indexes(local_connection, table_name)
        target_indexes = _table_indexes(target_connection, table_name)
        for name in sorted(set(local_indexes) - set(target_indexes)):
            index_sql = re.sub(r"^CREATE( UNIQUE)? INDEX ", r"CREATE\1 INDEX IF NOT EXISTS ", local_indexes[name], count=1)
            index_statements.append(index_sql.rstrip(";") + ";")
            actions.append({"table": table_name, "index": name, "action": "add_index"})
        for name in sorted(set(local_indexes) & set(target_indexes)):
            if local_indexes[name] != target_indexes[name]:
                blockers.append({"table": table_name, "index": name, "reason": "existing_index_definition_differs"})
    for table_name in sorted(target_set - local_set):
        blockers.append({"table": table_name, "reason": "target_only_table_not_deleted"})
    statements = (
        foundation_statements
        + key_constraint_statements
        + foreign_key_repair_statements
        + foreign_key_statements
        + other_constraint_statements
        + index_statements
    )
    return {"sql": "\n\n".join(statements), "actions": actions, "blockers": blockers}


def audit_schema_only(local_target, remote_target):
    """Compare only PostgreSQL schema metadata, never business table rows."""
    with _connect(local_target) as local_connection, _connect(remote_target) as remote_connection:
        local_tables = _public_tables(local_connection)
        remote_tables = _public_tables(remote_connection)
        local_set, remote_set = set(local_tables), set(remote_tables)
        common_tables = sorted(local_set & remote_set)
        schema_differences = []
        table_details = {}
        for table_name in common_tables:
            local_schema = _table_schema(local_connection, table_name)
            remote_schema = _table_schema(remote_connection, table_name)
            schema_same = table_name in EXCLUDED_SCHEMA_TABLES or local_schema["hash"] == remote_schema["hash"]
            if not schema_same:
                schema_differences.append(table_name)
            table_details[table_name] = {
                "schema_same": schema_same,
                "local": {"hash": local_schema["hash"]},
                "target": {"hash": remote_schema["hash"]},
            }
        schema_local_set = local_set - EXCLUDED_SCHEMA_TABLES
        schema_remote_set = remote_set - EXCLUDED_SCHEMA_TABLES
        local_only = sorted(schema_local_set - schema_remote_set)
        target_only = sorted(schema_remote_set - schema_local_set)
        local_migrations = _migration_ledger(local_connection)
        target_migrations = _migration_ledger(remote_connection)
        migration_difference = _migration_differences(local_migrations, target_migrations)
        difference_count = len(local_only) + len(target_only) + len(schema_differences)
        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "read_only_schema_only",
            "local": _safe_target(local_target),
            "target": _safe_target(remote_target),
            "summary": {
                "local_table_count": len(local_tables),
                "target_table_count": len(remote_tables),
                "local_only_tables": len(local_only),
                "target_only_tables": len(target_only),
                "schema_difference_tables": len(schema_differences),
                "data_difference_tables": 0,
                "hash_skipped_tables": 0,
                "release_master_data_difference_tables": 0,
                "raw_master_data_difference_tables": 0,
                "runtime_data_difference_tables": 0,
                "manual_business_data_difference_tables": 0,
                "migration_local_only": len(migration_difference["local_only"]),
                "migration_target_only": len(migration_difference["target_only"]),
                "migration_checksum_mismatch": len(migration_difference["checksum_mismatch"]),
            },
            "schema": {"local_only_tables": local_only, "target_only_tables": target_only, "different_tables": schema_differences},
            "data": {
                "different_tables": [],
                "hash_skipped_tables": [],
                "release_master_data_candidates": [],
                "raw_master_data_difference_tables": [],
                "master_data_stable_differences": {},
                "runtime_data_difference_tables": [],
                "manual_business_data_candidates": [],
            },
            "tables": table_details,
            "schema_migration_difference": migration_difference,
            "safe_release_delta": {
                "schema": schema_differences,
                "master_data": [],
                "business_data": [],
                "total": difference_count,
                "note": "Schema-only mode does not read or write business data. Target-only objects are retained.",
            },
            "local_release_ledger": _ledger(local_connection, "local"),
            "target_release_ledger": _ledger(remote_connection, remote_target.get("name") or ""),
        }


def build_schema_only_delta(local_target, target):
    """Generate an additive schema delta without reading any business rows."""
    report = audit_schema_only(local_target, target)
    with _connect(local_target) as local_connection, _connect(target) as target_connection:
        schema = _schema_incremental_sql(local_connection, target_connection, report, schema_only=True)
    return {"report": report, "schema": schema}


def verify_schema_equivalence(local_target, remote_target):
    """Return a final schema verdict without reading any business rows."""
    report = audit_schema_only(local_target, remote_target)
    schema = report.get("schema") or {}
    migrations = report.get("schema_migration_difference") or {}
    strict_migrations = migrations.get("strict_schema") or migrations
    non_structural_migrations = migrations.get("non_structural") or {}
    differences = (
        list(schema.get("local_only_tables") or [])
        + list(schema.get("target_only_tables") or [])
        + list(schema.get("different_tables") or [])
        + list(strict_migrations.get("local_only") or [])
        + list(strict_migrations.get("target_only") or [])
        + list(strict_migrations.get("checksum_mismatch") or [])
    )
    return {
        "ok": not differences,
        "mode": "final_schema_equivalence",
        "checked_at": report.get("generated_at"),
        "source": report.get("local"),
        "target": report.get("target"),
        "summary": report.get("summary"),
        "schema": schema,
        "schema_migration_difference": migrations,
        "non_structural_migration_ledger_difference": non_structural_migrations,
        "differences": differences,
        "note": "只阻断表、字段、索引、约束与结构迁移 checksum；历史主数据账本仅提示，不读取业务表行内容。",
    }


def _data_rows(connection, table_name, columns, key_columns, include_values=False):
    quoted_table = _quote_identifier(table_name)
    select_columns = ", ".join(_quote_identifier(column) for column in columns)
    key_select = ", ".join(_quote_identifier(column) + "::text" for column in key_columns)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {select_columns}, to_jsonb(t)::text, ARRAY[{key_select}] FROM {quoted_table} AS t")
        rows = {}
        for raw in cursor.fetchall():
            values, payload, key = raw[:len(columns)], raw[len(columns)], raw[len(columns) + 1]
            normalized_key = json.dumps(list(key or []), ensure_ascii=False, separators=(",", ":"))
            rows[normalized_key] = {"hash": hashlib.sha256(str(payload).encode("utf-8")).hexdigest(), "values": values if include_values else None}
    return rows


def _data_incremental_sql(local_connection, target_connection, table_names):
    statements, details, blockers = [], [], []
    for table_name in sorted(set(table_names or [])):
        specs = _column_specs(local_connection, table_name)
        columns = [item["name"] for item in specs]
        if table_name in MDM_MASTER_DATA_TABLES:
            # MDM releases use the immutable business identifier, never the
            # environment-specific surrogate id. This preserves target-side
            # foreign-key references while still allowing an audited Upsert.
            key_columns = [MDM_MASTER_DATA_KEYS[table_name]]
            if key_columns[0] not in columns:
                blockers.append({"table": table_name, "reason": "missing_mdm_business_key", "key": key_columns[0]})
                continue
            columns = [
                item["name"] for item in specs
                if item["name"] in key_columns or not (item.get("serial_sequence") or item.get("identity"))
            ]
        else:
            key_columns = _primary_key_columns(local_connection, table_name)
        if not key_columns:
            blockers.append({"table": table_name, "reason": "missing_primary_key"})
            continue
        local_rows = _data_rows(local_connection, table_name, columns, key_columns, include_values=True)
        target_rows = _data_rows(target_connection, table_name, columns, key_columns, include_values=False)
        if table_name == "app_settings":
            local_rows = {
                key: row for key, row in local_rows.items()
                if json.loads(key)[0] not in PROTECTED_SETTING_KEYS
            }
            target_rows = {
                key: row for key, row in target_rows.items()
                if json.loads(key)[0] not in PROTECTED_SETTING_KEYS
            }
        if len(local_rows) > MAX_GENERATED_ROWS_PER_TABLE:
            blockers.append({"table": table_name, "reason": "row_limit_exceeded", "limit": MAX_GENERATED_ROWS_PER_TABLE})
            continue
        changed_keys = sorted(key for key, row in local_rows.items() if key not in target_rows or target_rows[key]["hash"] != row["hash"])
        if not changed_keys:
            continue
        quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
        quoted_keys = ", ".join(_quote_identifier(column) for column in key_columns)
        update_columns = [column for column in columns if column not in key_columns]
        updates = ", ".join(_quote_identifier(column) + " = EXCLUDED." + _quote_identifier(column) for column in update_columns)
        with local_connection.cursor() as cursor:
            for key in changed_keys:
                values_sql = cursor.mogrify("(" + ", ".join(["%s"] * len(columns)) + ")", local_rows[key]["values"]).decode("utf-8")
                conflict = "DO UPDATE SET " + updates if updates else "DO NOTHING"
                statements.append(
                    "INSERT INTO " + _quote_identifier(table_name) + " (" + quoted_columns + ") VALUES " + values_sql
                    + " ON CONFLICT (" + quoted_keys + ") " + conflict + ";"
                )
        details.append({"table": table_name, "upsert_rows": len(changed_keys), "target_only_rows_retained": max(0, len(target_rows) - len(local_rows))})
    return {"sql": "\n\n".join(statements), "details": details, "blockers": blockers}


def build_incremental_delta(local_target, target, include_schema=True, include_master_data=True, include_runtime_data=False):
    """Generate reviewable additive SQL from a fresh local-to-target audit.

    The result does not execute SQL. Target-only rows and destructive schema
    changes are retained and returned as blockers for human review.
    """
    report = audit(local_target, target)
    result = {"report": report, "schema": {"sql": "", "actions": [], "blockers": []}, "master_data": {"sql": "", "details": [], "blockers": []}, "runtime_data": {"sql": "", "details": [], "blockers": []}}
    with _connect(local_target) as local_connection, _connect(target) as target_connection:
        schema_changed = bool(
            report["schema"].get("local_only_tables")
            or report["schema"].get("target_only_tables")
            or report["schema"].get("different_tables")
        )
        if include_schema and schema_changed:
            result["schema"] = _schema_incremental_sql(local_connection, target_connection, report)
        master_tables = report["safe_release_delta"]["master_data"]
        if include_master_data and master_tables:
            result["master_data"] = _data_incremental_sql(
                local_connection, target_connection, master_tables,
            )
        runtime_tables = report["data"]["manual_business_data_candidates"]
        if include_runtime_data and runtime_tables:
            result["runtime_data"] = _data_incremental_sql(
                local_connection, target_connection, runtime_tables,
            )
        if include_runtime_data and report["data"]["runtime_data_difference_tables"]:
            result["runtime_data"]["blockers"].extend(
                {
                    "table": table_name,
                    "reason": "target_user_runtime_data_is_protected",
                }
                for table_name in report["data"]["runtime_data_difference_tables"]
            )
    return result


def audit(local_target, remote_target):
    with _connect(local_target) as local_connection, _connect(remote_target) as remote_connection:
        local_tables = _public_tables(local_connection)
        remote_tables = _public_tables(remote_connection)
        local_set, remote_set = set(local_tables), set(remote_tables)
        common_tables = sorted(local_set & remote_set)
        schema_differences, data_differences = [], []
        raw_master_data_differences, release_master_differences = [], []
        excluded_from_mdm_comparison = []
        master_data_details = {}
        table_details = {}
        for table_name in common_tables:
            local_schema = _table_schema(local_connection, table_name)
            remote_schema = _table_schema(remote_connection, table_name)
            schema_same = (
                table_name in EXCLUDED_SCHEMA_TABLES
                or local_schema["hash"] == remote_schema["hash"]
            )
            if not schema_same:
                schema_differences.append(table_name)
            if table_name in MDM_MASTER_DATA_TABLES:
                stable_difference = _stable_master_difference(local_connection, remote_connection, table_name)
                master_data_details[table_name] = stable_difference
                data_same = not any(stable_difference.values())
                if not data_same:
                    data_differences.append(table_name)
                    raw_master_data_differences.append(table_name)
                    release_master_differences.append(table_name)
                local_data = {"status": "mdm_business_key_compared"}
                remote_data = {"status": "mdm_business_key_compared"}
            else:
                excluded_from_mdm_comparison.append(table_name)
                local_data = {"status": "not_compared_non_mdm"}
                remote_data = {"status": "not_compared_non_mdm"}
            table_details[table_name] = {
                "schema_same": schema_same,
                "local": local_data,
                "target": remote_data,
            }
        schema_local_set = local_set - EXCLUDED_SCHEMA_TABLES
        schema_remote_set = remote_set - EXCLUDED_SCHEMA_TABLES
        local_only = sorted(schema_local_set - schema_remote_set)
        target_only = sorted(schema_remote_set - schema_local_set)
        local_migrations = _migration_ledger(local_connection)
        target_migrations = _migration_ledger(remote_connection)
        migration_difference = {
            "local_only": sorted(set(local_migrations) - set(target_migrations)),
            "target_only": sorted(set(target_migrations) - set(local_migrations)),
            "checksum_mismatch": sorted(name for name in set(local_migrations) & set(target_migrations) if local_migrations[name] != target_migrations[name]),
        }
        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "read_only",
            "local": _safe_target(local_target),
            "target": _safe_target(remote_target),
            "summary": {
                "local_table_count": len(local_tables),
                "target_table_count": len(remote_tables),
                "local_only_tables": len(local_only),
                "target_only_tables": len(target_only),
                "schema_difference_tables": len(schema_differences),
                "data_difference_tables": len(data_differences),
                "hash_skipped_tables": 0,
                "release_master_data_difference_tables": len(release_master_differences),
                "raw_master_data_difference_tables": len(raw_master_data_differences),
                "runtime_data_difference_tables": 0,
                "manual_business_data_difference_tables": 0,
                "mdm_managed_table_count": len(set(common_tables) & MDM_MASTER_DATA_TABLES),
                "mdm_excluded_table_count": len(excluded_from_mdm_comparison),
                "migration_local_only": len(migration_difference["local_only"]),
                "migration_target_only": len(migration_difference["target_only"]),
                "migration_checksum_mismatch": len(migration_difference["checksum_mismatch"]),
            },
            "schema": {"local_only_tables": local_only, "target_only_tables": target_only, "different_tables": schema_differences},
            "data": {
                "different_tables": data_differences,
                "hash_skipped_tables": [],
                "release_master_data_candidates": release_master_differences,
                "raw_master_data_difference_tables": raw_master_data_differences,
                "master_data_stable_differences": master_data_details,
                "runtime_data_difference_tables": [],
                "manual_business_data_candidates": [],
                "excluded_from_mdm_comparison_tables": excluded_from_mdm_comparison,
            },
            "tables": table_details,
            "schema_migration_difference": migration_difference,
            "safe_release_delta": {
                "schema": schema_differences,
                "master_data": release_master_differences,
                "business_data": [],
                "total": len(schema_differences) + len(release_master_differences),
                "note": "Only schema differences and MDM-managed master-data differences may be turned into release packages. Runtime, user, account and configuration data is intentionally excluded.",
            },
            "local_release_ledger": _ledger(local_connection, "local"),
            "target_release_ledger": _ledger(remote_connection, remote_target.get("name") or ""),
        }


def main():
    parser = argparse.ArgumentParser(description="Read-only local-to-target database release audit")
    parser.add_argument("--target", choices=("staging", "production"), default="staging")
    parser.add_argument("--schema-only", action="store_true", help="Compare PostgreSQL metadata only; never read business table rows")
    parser.add_argument("--fail-on-diff", action="store_true", help="Exit with status 1 when schema or migration metadata differs")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    local_target = get_local_app_db_target()
    target = get_database_release_target(args.target)
    if not target:
        raise SystemExit(f"Target unavailable: {args.target}")
    report = verify_schema_equivalence(local_target, target) if args.fail_on_diff else (audit_schema_only(local_target, target) if args.schema_only else audit(local_target, target))
    output = Path(args.output) if args.output else ROOT / ".deploy" / f"database_diff_local_to_{args.target}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "summary": report["summary"]}, ensure_ascii=False))
    if args.fail_on_diff and not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
