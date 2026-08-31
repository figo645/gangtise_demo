from unittest.mock import patch


def _daily_response():
    return {
        "code": "000000",
        "status": True,
        "data": {
            "fieldList": ["securityCode", "tradeDate", "open", "high", "low", "close"],
            "list": [
                ["000001.SH", "2026-08-07", "3500", "3515", "3490", "3510"],
                ["000001.SH", "2026-08-10", "3512", "3530", "3505", "3520"],
            ],
        },
    }


def test_market_index_rejects_gangtise_provider_calls():
    from src.domain import market_services

    with patch.object(
        market_services,
        "post_gangtise_openapi_json",
        side_effect=AssertionError("market indices must not call Gangtise"),
    ) as post:
        result = market_services.fetch_gangtise_indicator_series(
            "source_shanghai_index",
            start_date="2026-08-01",
            end_date="2026-08-10",
        )

    assert result["ok"] is False
    assert result["message"] == "market_indicator_akshare_only"
    post.assert_not_called()


def test_market_snapshot_source_definition_has_no_external_gangtise_endpoint():
    from src.domain import market_services

    source = market_services.build_akshare_market_snapshot_source_seed_payload("source_shanghai_index")

    assert source["provider"] == "AKShare"
    assert source["path"] == "akshare://market_snapshot"
    assert source["auth_type"] == "none"
    assert source["response_mapping"]["connector_type"] == "akshare_snapshot"


def test_akshare_sector_sync_returns_only_shenwan_level_one_rows():
    from src.domain import market_services

    class Frame:
        empty = False
        columns = ["指数名称", "指数代码", "最新价", "昨收盘"]

        def iterrows(self):
            yield 0, {"指数名称": "银行", "指数代码": "801780", "最新价": "102", "昨收盘": "100"}
            yield 1, {"指数名称": "非行业", "指数代码": "000001", "最新价": "100", "昨收盘": "99"}

    class AkShare:
        def index_realtime_sw(self, symbol):
            assert symbol == "一级行业"
            return Frame()

    rows = market_services._fetch_akshare_sector_overview(ak=AkShare())

    assert len(rows) == 1
    assert rows[0]["sector"] == "银行"
    assert rows[0]["data_source"] == "AKShare"


def test_market_snapshot_task_runs_every_five_minutes():
    from src.domain import market_services

    task = next(item for item in market_services.DEFAULT_ADMIN_TASKS if item["task_code"] == "market_snapshot_sync")

    assert task["schedule_type"] == "interval"
    assert task["schedule_value"] == "300"
    assert task["enabled"] == 1


def test_market_snapshot_task_is_registered_with_admin_task_dispatcher():
    from src.domain import core_services

    task = {"task_type": "sync_market_snapshot", "task_params": {}}
    expected = {"ok": True, "overview_count": 9, "sector_count": 31}
    with patch.object(core_services, "execute_admin_task_by_type", return_value=expected) as execute:
        result = core_services.execute_admin_task(task)

    execute.assert_called_once_with("sync_market_snapshot", force=False)
    assert result == expected


def test_smart_indicator_refresh_task_runs_every_five_minutes_without_llm():
    from src.domain import core_services, market_services

    task = next(item for item in market_services.DEFAULT_ADMIN_TASKS if item["task_code"] == "smart_indicator_refresh")
    assert task["task_type"] == "smart_indicator_refresh"
    assert task["schedule_type"] == "interval"
    assert task["schedule_value"] == "300"
    assert task["enabled"] == 1

    expected = {"tenants": 1, "checked": 2, "refreshed": 1}
    with patch.object(core_services, "refresh_all_tenant_smart_indicator_snapshots", return_value=expected) as refresh, patch.object(
        market_services, "invalidate_indicator_hub_cache"
    ) as invalidate:
        result = core_services.execute_admin_task_by_type("smart_indicator_refresh")

    refresh.assert_called_once_with()
    invalidate.assert_called_once_with()
    assert result == expected


def test_gangtise_edb_tasks_are_manual_by_default_to_control_credits():
    from src.domain import market_services

    tasks = {item["task_code"]: item for item in market_services.DEFAULT_ADMIN_TASKS}

    for task_code in ("indicator_prepare", "indicator_gangtise_openapi_sync"):
        assert tasks[task_code]["schedule_type"] == "manual"
        assert tasks[task_code]["schedule_value"] == ""


def test_legacy_wind_industry_edb_source_is_not_registered_for_sync():
    from src.domain import market_services

    assert "source_industry_index" not in market_services.GANGTISE_INDICATOR_REGISTRY


def test_disabled_sources_do_not_authenticate_or_call_gangtise():
    from src.domain import market_services

    definition = {"indicator_code": "source_cpi", "enabled": False}
    source = {
        "indicator_code": "source_cpi",
        "source_code": "source_cpi",
        "enabled": False,
        "provider": "Gangtise OpenAPI",
        "auth_type": "gangtise_openapi",
    }
    with patch.object(market_services, "get_db"), \
        patch.object(market_services, "list_indicator_definitions", return_value=[definition]), \
        patch.object(market_services, "list_indicator_source_defs", return_value=[source]), \
        patch.object(market_services, "obtain_gangtise_openapi_token", side_effect=AssertionError("must not authenticate")), \
        patch.object(market_services, "fetch_gangtise_indicator_series", side_effect=AssertionError("must not fetch")):
        result = market_services.sync_real_indicator_history_from_market_cache()

    assert result["synced"] is True
    assert result["eligible"] == 0
    assert result["skipped_disabled"] == 1


def test_market_snapshot_uses_akshare_and_never_calls_gangtise():
    from src.domain import market_services

    index_result = {
        "ok": True,
        "provider": "AKShare",
        "points": [
            {"date": "2026-08-07", "open": 100, "high": 101, "low": 99, "close": 100},
            {"date": "2026-08-10", "open": 101, "high": 102, "low": 100, "close": 101},
        ],
    }
    sector_rows = [{
        "sector": "银行", "code": "801780.SWI", "value": 102, "change": 2,
        "change_pct": 2, "updated_at": "2026-08-10", "data_source": "AKShare",
    }]
    with patch.object(market_services, "fetch_akshare_market_index_history", return_value=index_result) as index_fetch, \
        patch.object(market_services, "_fetch_akshare_sector_overview", return_value=sector_rows), \
        patch.object(market_services, "_load_market_snapshot_payload", return_value=None), \
        patch.object(market_services, "_load_watchlist_cache", return_value=None), \
        patch.object(market_services, "_save_watchlist_cache"), \
        patch.object(market_services, "_save_market_snapshot_payload") as save_snapshot, \
        patch.object(market_services, "_load_akshare", return_value=object()):
        result = market_services.sync_market_snapshot(force=True)

    assert not hasattr(market_services, "_fetch_gangtise_sector_overview")
    assert not hasattr(market_services, "_load_gangtise_sector_catalog")
    assert index_fetch.call_count == len(market_services.MARKET_OVERVIEW_INDEX_CODES)
    assert result["overview_count"] == len(market_services.MARKET_OVERVIEW_INDEX_CODES)
    assert result["sector_count"] == 1
    overview = next(call.args[2] for call in save_snapshot.call_args_list if call.args[:2] == ("market_overview", "standard_indices"))
    sectors = next(call.args[2] for call in save_snapshot.call_args_list if call.args[:2] == ("market_sector_overview", "shenwan_level1"))
    assert overview["source"] == "AKShare"
    assert overview["snapshot_version"] == 7
    assert sectors["source"] == "AKShare"


def test_market_snapshot_refreshes_industry_snapshot_on_every_run():
    from src.domain import market_services

    index_result = {
        "ok": True,
        "provider": "AKShare",
        "points": [
            {"date": "2026-08-07", "close": 100},
            {"date": "2026-08-10", "close": 101},
        ],
    }
    with patch.object(market_services, "fetch_akshare_market_index_history", return_value=index_result), \
        patch.object(market_services, "_load_market_snapshot_payload", return_value=None), \
        patch.object(market_services, "_load_watchlist_cache", return_value=None), \
        patch.object(market_services, "_load_akshare", return_value=object()), \
        patch.object(market_services, "_fetch_akshare_sector_overview", return_value=[{"sector": "银行", "value": 102}]) as sector_fetch, \
        patch.object(market_services, "_save_watchlist_cache"), \
        patch.object(market_services, "_save_market_snapshot_payload"):
        result = market_services.sync_market_snapshot(force=False)

    assert result["sector_count"] == 1
    sector_fetch.assert_called_once()


def test_market_payload_rejects_old_gangtise_snapshot():
    from src.domain import market_services

    old_snapshot = {
        "ok": True,
        "snapshot_version": 6,
        "source": "Gangtise OpenAPI",
        "items": [{"indicator_code": "source_shanghai_index", "available": True}],
    }
    with patch.object(market_services, "_load_market_snapshot_payload", return_value=old_snapshot), \
        patch.object(market_services, "_load_watchlist_cache", return_value=None):
        overview = market_services.build_market_overview_payload()
        sectors = market_services.build_market_sector_overview_payload()

    assert overview["items"] == []
    assert overview["source"] == "AKShare"
    assert sectors["items"] == []
    assert sectors["source"] == "AKShare"
