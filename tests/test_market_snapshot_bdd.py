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


def test_gangtise_index_contract_preserves_the_reference_market_values():
    """BDD: source rows must become the exact cards shown to users.

    2026-09-18 was the latest trading date before the 2026-09-20 test date.
    These accepted values are deliberately hard assertions, rather than an
    availability-only check, so a stock endpoint or an incorrectly selected
    row cannot silently publish misleading market data.
    """
    from src.domain import market_services

    shanghai_response = {
        "code": "000000",
        "status": True,
        "data": {
            "fieldList": ["securityCode", "securityName", "tradeDate", "open", "high", "low", "close", "volume"],
            "list": [
                ["000001.SH", "上证指数", "2026-09-17", "3890.12", "3910.00", "3885.00", "3899.62", "100"],
                ["000001.SH", "上证指数", "2026-09-18", "3901.00", "3920.00", "3898.00", "3911.87", "100"],
            ],
        },
    }
    electronic_response = {
        "code": "000000",
        "status": True,
        "data": {
            "fieldList": ["securityCode", "securityName", "tradeDate", "open", "high", "low", "close", "volume"],
            "list": [
                ["801080.SWI", "电子", "2026-09-17", "8600.00", "8700.00", "8590.00", "8678.99", "100"],
                ["801080.SWI", "电子", "2026-09-18", "8700.00", "9000.00", "8690.00", "8935.03", "100"],
            ],
        },
    }

    def source_response(path, payload, **_kwargs):
        assert path == market_services.GANGTISE_INDEX_KLINE_DAILY_PATH
        security_code = payload["securityList"][0]
        assert payload["endDate"] == "2026-09-20"
        return 200, {"000001.SH": shanghai_response, "801080.SWI": electronic_response}[security_code], 8

    with patch.object(market_services, "post_gangtise_openapi_json", side_effect=source_response) as post, patch.object(
        market_services, "is_cn_stock_market_open", return_value=False
    ):
        shanghai_series = market_services.fetch_gangtise_market_index_history(
            "source_shanghai_index", "2026-09-01", "2026-09-20"
        )
        shanghai_card = market_services._build_market_index_snapshot_item("source_shanghai_index", shanghai_series)
        sectors, errors = market_services._fetch_gangtise_sector_overview(
            "2026-09-01", "2026-09-20", ["电子"]
        )

    assert post.call_count == 2
    assert shanghai_series["source_meta"]["path"] == market_services.GANGTISE_INDEX_KLINE_DAILY_PATH
    assert shanghai_card["price"] == 3911.87
    assert shanghai_card["updated_at"] == "2026-09-18"
    assert errors == []
    assert sectors == [
        {
            "sector": "电子",
            "code": "801080.SWI",
            "security_code": "801080.SWI",
            "indicator_name": "申万一级行业指数:电子",
            "value": 8935.03,
            "change": 256.04,
            "change_pct": 2.95,
            "updated_at": "2026-09-18",
            "available": True,
            "data_source": "Gangtise OpenAPI",
            "quote_mode": "daily_close",
            "realtime": False,
            "intraday_message": "",
            "source_meta": {
                "type": "index_kline",
                "path": market_services.GANGTISE_INDEX_KLINE_DAILY_PATH,
                "securityCode": "801080.SWI",
            },
        }
    ]


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


def test_closed_market_keeps_the_last_successful_market_and_industry_snapshots_visible():
    from src.domain import market_services

    overview = {
        "ok": True, "snapshot_version": 10, "source": "Gangtise OpenAPI", "updated_at": "2026-09-18 10:37:30",
        "items": [{"indicator_code": "source_shanghai_index", "name": "上证指数", "price": 3875.6, "available": True}],
    }
    sectors = {
        "ok": True, "snapshot_version": 10, "source": "Gangtise OpenAPI", "updated_at": "2026-09-18 10:37:30",
        "items": [{"sector": "电子", "value": 1234.5, "change_pct": 1.2, "available": True}],
    }
    with patch.object(market_services, "_load_market_snapshot_payload", side_effect=[None, overview, None, sectors]), patch.object(
        market_services, "_load_watchlist_cache", return_value=None
    ), patch.object(market_services, "is_cn_stock_market_open", return_value=False):
        market_payload = market_services.build_market_overview_payload()
        sector_payload = market_services.build_market_sector_overview_payload()

    assert market_payload["items"] == overview["items"]
    assert sector_payload["items"] == sectors["items"]
    assert market_payload["historical"] is True
    assert sector_payload["historical"] is True
    assert "非交易时段" in market_payload["message"]


def test_deployed_v8_market_snapshots_remain_readable_after_the_v10_upgrade():
    """A production v8 payload has the same reader-facing item schema as v10."""
    from src.domain import market_services

    overview = {
        "ok": True, "snapshot_version": 8, "source": "Gangtise OpenAPI", "updated_at": "2026-09-18 10:37:30",
        "items": [{"indicator_code": "source_shanghai_index", "name": "上证指数", "price": 3875.6, "available": True}],
    }
    sectors = {
        "ok": True, "snapshot_version": 8, "source": "Gangtise OpenAPI", "updated_at": "2026-09-18 10:37:30",
        "items": [{"sector": "电子", "value": 1234.5, "change_pct": 1.2, "available": True}],
    }
    with patch.object(market_services, "_load_market_snapshot_payload", side_effect=[overview, sectors]), patch.object(
        market_services, "_load_watchlist_cache", return_value=None
    ), patch.object(market_services, "is_cn_stock_market_open", return_value=False):
        market_payload = market_services.build_market_overview_payload()
        sector_payload = market_services.build_market_sector_overview_payload()

    assert market_payload["items"] == overview["items"]
    assert sector_payload["items"] == sectors["items"]
    assert market_payload["snapshot_version"] == 8
    assert sector_payload["snapshot_version"] == 8


def test_open_market_hides_an_expired_snapshot_before_the_refresh_completes():
    from src.domain import market_services

    snapshot = {
        "ok": True, "snapshot_version": 10, "source": "Gangtise OpenAPI", "updated_at": "2026-09-18 10:37:30",
        "items": [{"indicator_code": "source_shanghai_index", "name": "上证指数", "price": 3875.6, "available": True}],
    }
    with patch.object(market_services, "_load_market_snapshot_payload", side_effect=[None, snapshot]), patch.object(
        market_services, "_load_watchlist_cache", return_value=None
    ), patch.object(market_services, "is_cn_stock_market_open", return_value=True), patch.object(
        market_services, "request_market_snapshot_refresh", return_value={"queued": False}
    ):
        payload = market_services.build_market_overview_payload()

    assert payload["items"] == []
    assert payload["stale"] is True
    assert "超过一个交易日" in payload["message"]


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
