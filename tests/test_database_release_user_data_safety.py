from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_APPLY_SCRIPT = ROOT / "scripts" / "apply_database_release_package.sh"
FULL_RELEASE_SCRIPT = ROOT / "scripts" / "prepare_database_release.sh"


PROTECTED_TABLES = {
    "users",
    "tenant_published_insights",
    "tenant_insight_drafts",
    "tenant_message_threads",
    "tenant_messages",
    "tenant_broadcasts",
    "tenant_broadcast_deliveries",
    "tenant_knowledge_documents",
    "user_watchlist_items",
    "watchlist_comments",
    "watchlist_kline_annotations",
    "hermes_conversation_turns",
    "hermes_session_memory",
    "hermes_user_memory",
    "hermes_user_profiles",
    "fan_subscriptions",
    "fan_payment_orders",
    "analytics_events",
    "access_logs",
}


def test_schema_release_boundary_has_no_business_data_write_path():
    script = SCHEMA_APPLY_SCRIPT.read_text(encoding="utf-8")
    for table in PROTECTED_TABLES:
        assert table in script, f"schema release guard missing protected table: {table}"
    assert "Refusing schema release SQL that writes protected user or content data" in script
    assert "INSERT INTO schema_migrations" not in script


def test_full_release_explicitly_preserves_published_insights_and_content():
    script = FULL_RELEASE_SCRIPT.read_text(encoding="utf-8")
    for table in (
        "tenant_published_insights",
        "tenant_insight_drafts",
        "tenant_message_threads",
        "tenant_messages",
        "tenant_broadcasts",
        "tenant_broadcast_deliveries",
        "tenant_knowledge_documents",
    ):
        assert f"public.{table}" in script


def test_recent_schema_package_is_ddl_only():
    package = ROOT / "database_release_packages" / "2026-09-29" / "v1.1.29" / "schema.sql"
    sql = package.read_text(encoding="utf-8")
    assert "ALTER TABLE" in sql
    assert "INSERT INTO tenant_published_insights" not in sql
    assert "DELETE FROM tenant_published_insights" not in sql
    assert "TRUNCATE" not in sql.upper()
