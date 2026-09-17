"""BDD contracts for report-verified Gangtise market snapshots."""

from pathlib import Path
from unittest.mock import patch
import psycopg2

from src.runtime import app


def test_gangtise_market_snapshot_uses_four_platform_schedule_slots():
    from src.domain import market_services

    task = next(item for item in market_services.DEFAULT_ADMIN_TASKS if item["task_code"] == "market_snapshot_sync")
    assert task["task_name"] == "Gangtise 市场与行业指标同步"
    assert task["schedule_type"] == "daily"
    assert task["schedule_value"] == "09:30,12:00,14:00,15:30"
    migration = (Path(__file__).resolve().parents[1] / "sql/postgres/135_use_gangtise_market_snapshots.sql").read_text(encoding="utf-8")
    assert ".SWI" in migration


def test_gangtise_fixed_overseas_index_reads_the_reported_id_without_searching():
    from src.domain import market_services

    response = {"code": "000000", "status": True, "data": {"dataList": [["2026-09-16", "100"], ["2026-09-17", "101"]]}}
    with patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 1)) as post:
        result = market_services.fetch_gangtise_market_index_history("source_hsi", "2026-09-01", "2026-09-17")
    assert result["ok"] is True
    assert post.call_args.args[0] == "/application/open-alternative/EDB/getData"
    assert post.call_args.args[1]["indicatorIdList"] == ["M00015437"]


def test_gangtise_industry_snapshot_uses_all_static_swi_symbols():
    from src.domain import market_services

    assert len(market_services.GANGTISE_SHENWAN_LEVEL1_CODES) == 31
    assert set(market_services.GANGTISE_SHENWAN_LEVEL1_CODES) == set(market_services.SHENWAN_LEVEL1_INDUSTRIES)
    assert all(code.endswith(".SWI") for code in market_services.GANGTISE_SHENWAN_LEVEL1_CODES.values())


def test_market_catalog_matches_the_reported_nine_daily_kline_and_six_fixed_edb_sources():
    from src.domain import market_services

    entries = [market_services.GANGTISE_INDICATOR_REGISTRY[code] for code in market_services.MARKET_OVERVIEW_INDEX_CODES]
    assert len(entries) == 15
    assert sum(entry.get("query_kind") == "index_kline" for entry in entries) == 9
    fixed_edb = [entry for entry in entries if entry.get("query_kind") == "edb_fixed"]
    assert len(fixed_edb) == 6
    assert all(entry.get("preferred_indicator_id") for entry in fixed_edb)
    assert "source_hscei" not in market_services.MARKET_OVERVIEW_INDEX_CODES
    assert "source_hscci" not in market_services.MARKET_OVERVIEW_INDEX_CODES


def test_stopping_a_market_sync_is_checked_between_each_gangtise_request_boundary():
    from src.domain import market_services

    source = Path(market_services.__file__).read_text(encoding="utf-8")
    market_fetcher = source[source.index("def fetch_gangtise_market_index_history"):source.index("def _fetch_gangtise_sector_overview")]
    sector_fetcher = source[source.index("def _fetch_gangtise_sector_overview"):source.index("def sync_market_snapshot")]
    synchronizer = source[source.index("def sync_market_snapshot"):source.index("def request_market_snapshot_refresh")]
    assert "open-indicator/EDB/search" not in market_fetcher + sector_fetcher + synchronizer
    assert sector_fetcher.count('assert_admin_task_not_stopped("market_snapshot_sync")') >= 1
    assert synchronizer.count('assert_admin_task_not_stopped("market_snapshot_sync")') >= 3


def test_default_task_setup_never_reenables_an_operator_stopped_shared_task():
    from src.domain import core_services

    source = Path(core_services.__file__).read_text(encoding="utf-8")
    start = source.index('item["task_code"] == "market_snapshot_sync"')
    end = source.index('item["task_code"] == "news_title_impact_sync"', start)
    market_update = source[start:end]
    assert "schedule_type = ?" not in market_update
    assert "enabled = ?" not in market_update


def test_gangtise_indicator_mapping_write_retries_once_after_a_severed_postgres_connection():
    from src.domain import core_services

    class BrokenDb:
        def execute(self, *_args, **_kwargs):
            raise psycopg2.InterfaceError("connection already closed")

    class HealthyDb:
        def __init__(self):
            self.executed = False
            self.committed = False

        def execute(self, *_args, **_kwargs):
            self.executed = True

        def commit(self):
            self.committed = True

    healthy = HealthyDb()
    with app.app_context(), patch.object(core_services, "get_db", side_effect=[BrokenDb(), healthy]), patch.object(
        core_services, "reset_request_runtime_state"
    ) as reset:
        saved = core_services._save_json_app_setting("market-mapping-test", {"items": {}})

    assert saved == {"items": {}}
    reset.assert_called_once()
    assert healthy.executed is True
    assert healthy.committed is True
