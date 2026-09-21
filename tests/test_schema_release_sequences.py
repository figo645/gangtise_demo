from unittest.mock import patch

from tools import audit_database_release_diff as schema_diff


def test_final_schema_equivalence_does_not_fail_for_target_only_master_data_ledger_history():
    report = {
        "generated_at": "2026-09-17 12:33:01",
        "local": {"label": "source"},
        "target": {"label": "target"},
        "summary": {},
        "schema": {"local_only_tables": [], "target_only_tables": [], "different_tables": []},
        "schema_migration_difference": {
            "local_only": [],
            "target_only": ["113_fan_commerce_and_qr_import.sql"],
            "checksum_mismatch": [],
            "strict_schema": {"local_only": [], "target_only": [], "checksum_mismatch": []},
            "non_structural": {
                "local_only": [],
                "target_only": ["113_fan_commerce_and_qr_import.sql"],
                "checksum_mismatch": [],
            },
        },
    }
    with patch.object(schema_diff, "audit_schema_only", return_value=report):
        result = schema_diff.verify_schema_equivalence({"name": "local"}, {"name": "production"})
    assert result["ok"] is True
    assert result["differences"] == []
    assert result["non_structural_migration_ledger_difference"]["target_only"] == [
        "113_fan_commerce_and_qr_import.sql"
    ]


def test_final_schema_equivalence_rejects_missing_or_conflicting_schema_migrations():
    report = {
        "generated_at": "2026-09-17 12:33:01",
        "local": {}, "target": {}, "summary": {},
        "schema": {"local_only_tables": [], "target_only_tables": [], "different_tables": []},
        "schema_migration_difference": {
            "local_only": ["132_analytics_events.sql"], "target_only": [], "checksum_mismatch": ["131_review.sql"],
            "strict_schema": {"local_only": ["132_analytics_events.sql"], "target_only": [], "checksum_mismatch": ["131_review.sql"]},
            "non_structural": {"local_only": [], "target_only": [], "checksum_mismatch": []},
        },
    }
    with patch.object(schema_diff, "audit_schema_only", return_value=report):
        result = schema_diff.verify_schema_equivalence({"name": "local"}, {"name": "production"})
    assert result["ok"] is False
    assert result["differences"] == ["132_analytics_events.sql", "131_review.sql"]


def test_migration_history_classification_keeps_target_only_records_as_observations():
    differences = schema_diff._migration_differences(
        {
            "132_analytics_events.sql": {"scope": "schema", "checksum": "source-132"},
            "119_replace_news_source.sql": {"scope": "master_data", "checksum": "source-119"},
        },
        {
            "113_fan_commerce.sql": {"scope": "master_data", "checksum": "target-113"},
            "132_analytics_events.sql": {"scope": "schema", "checksum": "source-132"},
            "119_replace_news_source.sql": {"scope": "master_data", "checksum": "target-119"},
        },
    )
    assert differences["strict_schema"] == {
        "local_only": [], "target_only": [], "checksum_mismatch": [],
    }
    assert differences["non_structural"] == {
        "local_only": [],
        "target_only": ["113_fan_commerce.sql"],
        "checksum_mismatch": ["119_replace_news_source.sql"],
    }


def _serial_column(name="id"):
    return {
        "name": name,
        "type": "bigint",
        "not_null": True,
        "default": "nextval('analytics_events_id_seq'::regclass)",
        "identity": "",
        "serial_sequence": "public.analytics_events_id_seq",
    }


def test_new_table_serial_column_creates_sequence_before_table_and_owns_it():
    local_connection, target_connection = object(), object()
    report = {"schema": {"different_tables": []}}
    with patch.object(schema_diff, "_public_tables", side_effect=lambda connection: ["analytics_events"] if connection is local_connection else []), patch.object(
        schema_diff, "_column_specs", return_value=[_serial_column()]
    ), patch.object(schema_diff, "_table_constraints", return_value={}), patch.object(
        schema_diff, "_table_indexes", return_value={}
    ):
        generated = schema_diff._schema_incremental_sql(local_connection, target_connection, report, schema_only=True)

    sql = generated["sql"]
    assert sql.index('CREATE SEQUENCE IF NOT EXISTS public."analytics_events_id_seq";') < sql.index('CREATE TABLE IF NOT EXISTS "analytics_events"')
    assert 'ALTER SEQUENCE public."analytics_events_id_seq" OWNED BY "analytics_events"."id";' in sql
    assert not generated["blockers"]


def test_existing_table_serial_default_is_blocked_from_zero_business_data_write_release():
    local_connection, target_connection = object(), object()
    report = {"schema": {"different_tables": ["existing_events"]}}
    with patch.object(schema_diff, "_public_tables", return_value=["existing_events"]), patch.object(
        schema_diff, "_column_specs", side_effect=lambda connection, _table: [_serial_column()] if connection is local_connection else []
    ), patch.object(schema_diff, "_table_constraints", return_value={}), patch.object(
        schema_diff, "_table_indexes", return_value={}):
        generated = schema_diff._schema_incremental_sql(local_connection, target_connection, report, schema_only=True)

    assert generated["sql"] == ""
    assert generated["blockers"] == [
        {"table": "existing_events", "column": "id", "reason": "sequence_default_on_existing_table"}
    ]


def test_existing_tenant_scoped_records_reconcile_registry_before_foreign_key():
    local_connection, target_connection = object(), object()
    report = {"schema": {"different_tables": ["open_api_tokens"]}}
    columns = [{"name": "tenant_slug", "type": "text", "not_null": True, "default": "", "identity": "", "serial_sequence": ""}]
    with patch.object(schema_diff, "_public_tables", return_value=["open_api_tokens"]), patch.object(
        schema_diff, "_column_specs", return_value=columns
    ), patch.object(
        schema_diff,
        "_table_constraints",
        side_effect=lambda connection, _table: {
            "fk_open_api_tokens_tenant": "FOREIGN KEY (tenant_slug) REFERENCES tenant_registry(tenant_slug) ON DELETE RESTRICT"
        } if connection is local_connection else {},
    ), patch.object(schema_diff, "_table_indexes", return_value={}):
        generated = schema_diff._schema_incremental_sql(local_connection, target_connection, report, schema_only=True)

    sql = generated["sql"]
    assert sql.index("INSERT INTO tenant_registry") < sql.index("ADD CONSTRAINT \"fk_open_api_tokens_tenant\"")
    assert "tenant_registry_reference_invalid:open_api_tokens" in sql
    assert generated["actions"] == [
        {"table": "open_api_tokens", "parent_table": "tenant_registry", "action": "reconcile_missing_tenant_registry_references"},
        {"table": "open_api_tokens", "constraint": "fk_open_api_tokens_tenant", "action": "add_constraint"},
    ]


class _MogrifyCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def mogrify(self, _statement, _values):
        return b"('600519.SH', 'Moutai')"


class _MogrifyConnection:
    def cursor(self):
        return _MogrifyCursor()


def test_mdm_data_package_uses_business_key_and_never_copies_serial_id():
    specs = [
        {"name": "id", "serial_sequence": "public.security_master_id_seq", "identity": ""},
        {"name": "security_code", "serial_sequence": "", "identity": ""},
        {"name": "name", "serial_sequence": "", "identity": ""},
    ]
    local_rows = {"[\"600519.SH\"]": {"hash": "local", "values": ("600519.SH", "Moutai")}}
    with patch.object(schema_diff, "_column_specs", return_value=specs), patch.object(
        schema_diff, "_primary_key_columns", side_effect=AssertionError("MDM data must not use surrogate primary keys")
    ), patch.object(
        schema_diff, "_data_rows", side_effect=[local_rows, {}]
    ):
        generated = schema_diff._data_incremental_sql(_MogrifyConnection(), object(), ["security_master"])

    assert 'INSERT INTO "security_master" ("security_code", "name")' in generated["sql"]
    assert 'ON CONFLICT ("security_code") DO UPDATE SET "name" = EXCLUDED."name"' in generated["sql"]
    assert '"id"' not in generated["sql"]
