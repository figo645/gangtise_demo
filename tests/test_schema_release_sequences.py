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
