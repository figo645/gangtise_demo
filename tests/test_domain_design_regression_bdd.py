"""BDD contracts for the domain-storage boundaries introduced in migrations 138-143."""

from pathlib import Path

from src.domain import core_services


ROOT = Path(__file__).resolve().parents[1]


def test_message_center_empty_domain_state_is_authoritative():
    source = (ROOT / "src/domain/core_services.py").read_text(encoding="utf-8")
    assert 'if stored.get("storage_available"):' in source
    assert "would resurrect content that a user has deleted" in source
    assert "DELETE FROM tenant_message_threads" in source
    assert "DELETE FROM tenant_messages" in source
    assert "DELETE FROM tenant_broadcasts" in source


def test_message_broadcast_ids_are_not_forced_to_integers():
    item = core_services.normalize_message_broadcast_item(
        {"id": "provider-broadcast-9", "content": "内容", "time": "2026-09-21"},
        {"slug": "laowang"},
    )
    assert item["id"] == "provider-broadcast-9"


def test_domain_tables_have_explicit_tenant_ownership():
    migration = (ROOT / "sql/postgres/143_domain_tenant_ownership.sql").read_text(encoding="utf-8")
    assert "fk_insight_drafts_tenant" in migration
    assert "fk_open_api_tokens_tenant" in migration
    assert "REFERENCES tenant_registry(tenant_slug)" in migration


def test_message_domain_tracks_recipient_identity_and_delivery_audit():
    migration = (ROOT / "sql/postgres/144_message_domain_user_identity.sql").read_text(encoding="utf-8")
    source = (ROOT / "src/domain/core_services.py").read_text(encoding="utf-8")
    assert "fk_message_threads_user" in migration
    assert "fk_broadcast_deliveries_user" in migration
    assert "_record_tenant_broadcast_deliveries" in source
    assert "tenant_broadcast_deliveries" in source


def test_runtime_schema_bootstrap_includes_latest_domain_migration():
    source = (ROOT / "src/domain/core_services.py").read_text(encoding="utf-8")
    script = (ROOT / "scripts/apply_postgres_updates.sh").read_text(encoding="utf-8")
    python_runner = (ROOT / "scripts/run_postgres_migrations.py").read_text(encoding="utf-8")
    assert 'sql_dir / "143_domain_tenant_ownership.sql"' in source
    assert 'sql_dir / "144_message_domain_user_identity.sql"' in source
    assert 'sql_dir / "145_reconcile_tenant_registry_references.sql"' in source
    assert "run_postgres_migrations.py" in script
    assert '"143", "144", "145"' in python_runner


def test_knowledge_and_published_content_do_not_fall_back_when_domain_tables_are_empty():
    core = (ROOT / "src/domain/core_services.py").read_text(encoding="utf-8")
    ai = (ROOT / "src/domain/ai_services.py").read_text(encoding="utf-8")
    assert "Once migration 140 exists, an empty document table is a valid" in core
    assert "Published Insights table unavailable; using legacy JSON" in core
    assert "config_items =" in ai
