"""BDD contracts for the product analytics event pipeline."""

from pathlib import Path

from src.domain import analytics_services


ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def fetchone(self):
        return {"id": 42}


class _Db:
    def __init__(self):
        self.calls = []
        self.commits = 0

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Cursor()

    def commit(self):
        self.commits += 1


def test_given_valid_event_when_recorded_then_sensitive_free_structured_fact_is_written():
    db = _Db()
    event_id = analytics_services.record_analytics_event(
        "feature_click",
        "h5.watchlist",
        event_category="interaction",
        surface="h5",
        tenant_slug="laowang",
        user_profile_id="fan-1",
        session_id="session-1",
        anonymous_id="anon-1",
        object_type="stock",
        object_id="600519.SH",
        success=True,
        properties={"action": "open_detail", "question": "should_not_be_sent"},
        path="/h5",
        referrer="/login",
        db=db,
    )

    assert event_id == 42
    sql, params = db.calls[0]
    assert "INSERT INTO analytics_events" in sql
    assert params[0:5] == ("feature_click", "interaction", "h5.watchlist", "h5", "laowang")
    # The event API accepts only structured properties and does not persist the
    # raw user question as a first-class field.
    assert params[-1].find('"action":"open_detail"') >= 0
    assert "should_not_be_sent" not in params[-1]


def test_given_invalid_surface_when_event_recorded_then_surface_is_neutralized():
    db = _Db()
    analytics_services.record_analytics_event(
        "query_submit",
        "h5.search",
        surface="internal-debug",
        path="/h5",
        db=db,
    )

    assert db.calls[0][1][3] == "unknown"


def test_given_oversized_properties_when_event_recorded_then_properties_are_bounded():
    db = _Db()
    analytics_services.record_analytics_event(
        "feature_action",
        "web.review",
        properties={f"payload_{index}": "x" * 500 for index in range(24)},
        path="/web",
        db=db,
    )

    assert db.calls[0][1][-1] == '{"truncated":true}'


def test_given_admin_filter_when_parsed_then_scope_is_bounded_and_parameterized():
    parsed = analytics_services._parse_analytics_filters({
        "days": "9999",
        "surface": "all",
        "tenant_slug": " Laowang ",
        "user_role": "DAV",
    })

    assert parsed["days"] == 365
    assert parsed["surface"] == ""
    assert parsed["tenant_slug"] == "laowang"
    assert parsed["user_role"] == "dav"
    assert "tenant_slug = ?" in parsed["where"]
    assert "laowang" in parsed["params"]


def test_given_product_surfaces_when_templates_load_then_tracker_and_admin_entry_exist():
    for name in ("h5.html", "kol_workbench.html", "tenant_portal.html", "admin.html"):
        source = (ROOT / "templates" / name).read_text(encoding="utf-8")
        assert "/static/js/analytics_tracker.js" in source
    admin = (ROOT / "templates/admin.html").read_text(encoding="utf-8")
    assert 'data-section="event-analytics"' in admin
    assert 'id="section-event-analytics"' in admin
    assert "loadEventAnalytics" in admin


def test_given_database_migration_when_release_runs_then_analytics_schema_is_versioned():
    migration = (ROOT / "sql/postgres/132_analytics_events.sql").read_text(encoding="utf-8")
    runner = (ROOT / "scripts/apply_postgres_updates.sh").read_text(encoding="utf-8")
    bootstrap = (ROOT / "src/domain/core_services.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS analytics_events" in migration
    assert "idx_analytics_events_feature_time" in migration
    assert "131|132" in runner
    assert 'sql_dir / "132_analytics_events.sql"' in bootstrap


def test_given_technical_event_keys_when_reported_then_chinese_labels_are_available():
    assert analytics_services._feature_label("h5.action.open_fundamental") == "H5 · 打开 · 基本面"
    assert analytics_services._feature_label("admin.event_analytics") == "Admin · 埋点分析"
    assert analytics_services._event_label("navigation_click") == "导航切换"


def test_given_unknown_event_key_when_reported_then_code_is_still_human_readable():
    assert analytics_services._feature_label("web.action.refresh_new_module") == "Web · 刷新 · new_module"
    assert analytics_services._event_label("custom_metric_refresh") == "custom · metric · refresh"
