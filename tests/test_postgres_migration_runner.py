from pathlib import Path
import json

from scripts import run_postgres_migrations as runner


ROOT = Path(__file__).resolve().parents[1]


def test_runner_is_the_only_sql_execution_engine_for_the_compatibility_command():
    wrapper = (ROOT / "scripts" / "apply_postgres_updates.sh").read_text(encoding="utf-8")
    assert "run_postgres_migrations.py" in wrapper
    assert "command -v psql" not in wrapper
    assert "PSQL=(" not in wrapper


def test_schema_only_classification_matches_historic_schema_migrations():
    assert runner._migration_scope("002_app_core_tables.sql") == "schema"
    assert runner._migration_scope("132_analytics_events.sql") == "schema"
    assert runner._migration_scope("145_reconcile_tenant_registry_references.sql") == "schema"
    assert runner._migration_scope("100_seed_master_data.sql") == "master_data"
    assert runner._migration_scope("106_security_master_seed.sql") == "master_data"


def test_runner_uses_postgres_lock_transaction_and_checksum_ledger():
    source = (ROOT / "scripts" / "run_postgres_migrations.py").read_text(encoding="utf-8")
    assert "pg_try_advisory_lock" in source
    assert "connection.rollback()" in source
    assert "connection.commit()" in source
    assert "hashlib.sha256" in source
    assert "INSERT INTO schema_migrations" in source


def test_current_release_manifest_includes_the_domain_and_open_api_migrations():
    manifest = json.loads((ROOT / "jenkinsfiles/database/release-manifest.json").read_text(encoding="utf-8"))
    migrations = {item["name"] for item in manifest["migrations"]}
    assert manifest["release_version"] == "v1.1.29"
    assert migrations == {
        "137_open_api_insight_tokens.sql",
        "138_tenant_published_insights.sql",
        "139_message_center_domain.sql",
        "140_knowledge_domain.sql",
        "141_app_settings_revision.sql",
        "142_domain_foreign_keys.sql",
        "143_domain_tenant_ownership.sql",
        "144_message_domain_user_identity.sql",
        "145_reconcile_tenant_registry_references.sql",
    }
    assert runner._load_release_manifest(
        ROOT / "jenkinsfiles/database/release-manifest.json",
        ROOT / "sql/postgres",
        schema_only=True,
    )["release_version"] == "v1.1.29"
    ordered_names = [item["name"] for item in manifest["migrations"]]
    assert ordered_names.index("145_reconcile_tenant_registry_references.sql") < ordered_names.index("142_domain_foreign_keys.sql")
    assert ordered_names.index("145_reconcile_tenant_registry_references.sql") < ordered_names.index("143_domain_tenant_ownership.sql")


def test_release_manifest_restricts_execution_to_the_declared_migrations():
    source = (ROOT / "scripts" / "run_postgres_migrations.py").read_text(encoding="utf-8")
    assert "paths_by_name = {path.name: path for path in files}" in source
    assert "files = [paths_by_name[item[\"name\"]] for item in release_manifest[\"migrations\"]]" in source
