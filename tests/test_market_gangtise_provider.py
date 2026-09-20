from unittest.mock import ANY, patch


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


def test_market_snapshot_source_definition_identifies_the_gangtise_shared_snapshot():
    from src.domain import market_services

    source = market_services.build_akshare_market_snapshot_source_seed_payload("source_shanghai_index")

    assert source["provider"] == "Gangtise OpenAPI"
    assert source["path"] == "gangtise://application/open-quote/index/kline/daily"
    assert source["auth_type"] == "none"
    assert source["response_mapping"]["connector_type"] == "gangtise_market_snapshot"


def test_market_overview_payload_rejects_old_snapshot_versions(monkeypatch):
    from src.domain import market_services

    payload = {"ok": True, "snapshot_version": 7, "source": "Gangtise", "items": [{"value": 1}]}
    monkeypatch.setattr(market_services, "_load_market_snapshot_payload", lambda *args, **kwargs: payload)
    monkeypatch.setattr(market_services, "_load_watchlist_cache", lambda *args, **kwargs: None)

    result = market_services.build_market_overview_payload()

    assert result["items"] == []
    assert result["source"] == "Gangtise OpenAPI"
    assert result["refreshing"] is True


def test_market_sector_payload_rejects_old_snapshot_versions(monkeypatch):
    from src.domain import market_services

    payload = {"ok": True, "snapshot_version": 7, "source": "Gangtise", "items": [{"sector": "银行"}]}
    monkeypatch.setattr(market_services, "_load_market_snapshot_payload", lambda *args, **kwargs: payload)
    monkeypatch.setattr(market_services, "_load_watchlist_cache", lambda *args, **kwargs: None)

    result = market_services.build_market_sector_overview_payload()

    assert result["items"] == []
    assert result["source"] == "Gangtise OpenAPI"
    assert result["refreshing"] is True


def test_market_index_detail_rejects_malformed_gangtise_history(monkeypatch):
    from src.domain import market_services

    monkeypatch.setattr(
        market_services,
        "_load_watchlist_cache",
        lambda *args, **kwargs: {"provider": "Gangtise OpenAPI", "points": [{"close": 1}, {"close": 2}]},
    )

    assert market_services.build_market_overview_index_detail("source_shanghai_index") is None


def test_akshare_sector_sync_returns_only_shenwan_level_one_rows():
    from src.domain import market_services

    class Frame:
        empty = False
        columns = ["指数名称", "指数代码", "最新价", "昨收盘"]

        def iterrows(self):
            for index, sector in enumerate(reversed(market_services.SHENWAN_LEVEL1_INDUSTRIES), start=1):
                yield index, {
                    "指数名称": sector,
                    "指数代码": f"801{index:03d}",
                    "最新价": str(100 + index),
                    "昨收盘": "100",
                }
            yield 99, {"指数名称": "非行业", "指数代码": "000001", "最新价": "100", "昨收盘": "99"}

    class AkShare:
        def index_realtime_sw(self, symbol):
            assert symbol == "一级行业"
            return Frame()

    rows = market_services._fetch_akshare_sector_overview(ak=AkShare())

    assert len(rows) == len(market_services.SHENWAN_LEVEL1_INDUSTRIES)
    assert rows[0]["sector"] == market_services.SHENWAN_LEVEL1_INDUSTRIES[0]
    assert rows[0]["change_pct"] > rows[-1]["change_pct"]
    assert all(row["data_source"] == "AKShare" for row in rows)


def test_akshare_sector_sync_rejects_incomplete_shenwan_level_one_response():
    from src.domain import market_services

    class Frame:
        empty = False
        columns = ["指数名称", "指数代码", "最新价", "昨收盘"]

        def iterrows(self):
            yield 0, {"指数名称": "银行", "指数代码": "801780", "最新价": "102", "昨收盘": "100"}

    class AkShare:
        def index_realtime_sw(self, symbol):
            return Frame()

    assert market_services._fetch_akshare_sector_overview(ak=AkShare()) == []


def test_akshare_sector_sync_accepts_pandas_style_ambiguous_columns_index():
    """A valid provider frame must not fail only because Index has no truth value."""
    from src.domain import market_services

    class AmbiguousColumns(list):
        def __bool__(self):
            raise ValueError("The truth value of a Index is ambiguous")

    class Frame:
        empty = False
        columns = AmbiguousColumns(["指数名称", "指数代码", "最新价", "昨收盘"])

        def iterrows(self):
            for index, sector in enumerate(market_services.SHENWAN_LEVEL1_INDUSTRIES, start=1):
                yield index, {
                    "指数名称": sector,
                    "指数代码": f"801{index:03d}",
                    "最新价": str(100 + index),
                    "昨收盘": "100",
                }

    class AkShare:
        def index_realtime_sw(self, symbol):
            assert symbol == "一级行业"
            return Frame()

    rows = market_services._fetch_akshare_sector_overview(ak=AkShare())

    assert len(rows) == len(market_services.SHENWAN_LEVEL1_INDUSTRIES)
    assert {row["sector"] for row in rows} == set(market_services.SHENWAN_LEVEL1_INDUSTRIES)


def test_market_snapshot_task_runs_at_the_four_published_slots():
    from src.domain import market_services

    task = next(item for item in market_services.DEFAULT_ADMIN_TASKS if item["task_code"] == "market_snapshot_sync")

    assert task["schedule_type"] == "daily"
    assert task["schedule_value"] == "09:30,12:00,14:00,15:30"
    assert task["enabled"] == 1


def test_market_snapshot_task_is_registered_with_admin_task_dispatcher():
    from src.domain import core_services

    task = {"task_type": "sync_market_snapshot", "task_params": {}}
    expected = {"ok": True, "overview_count": 9, "sector_count": 31}
    with patch.object(core_services, "execute_admin_task_by_type", return_value=expected) as execute:
        result = core_services.execute_admin_task(task)

    execute.assert_called_once_with("sync_market_snapshot", force=False)
    assert result == expected


def test_smart_indicator_refresh_task_is_removed_from_admin_schedule():
    from src.domain import market_services

    assert not any(item["task_code"] == "smart_indicator_refresh" for item in market_services.DEFAULT_ADMIN_TASKS)


def test_news_source_task_runs_hourly_without_model_dispatch():
    from src.domain import core_services, market_services

    task = next(item for item in market_services.DEFAULT_ADMIN_TASKS if item["task_code"] == "news_title_impact_sync")
    assert task["schedule_type"] == "interval"
    assert task["schedule_value"] == "3600"

    assert task["task_type"] == "sync_news_sources"
    expected = {"method": "news_source_fetch_v1", "input_count": 120, "source_count": 4}
    with patch.object(market_services, "sync_news_sources", return_value=expected) as sync:
        result = core_services.execute_admin_task_by_type("sync_news_sources", force=True)

    sync.assert_called_once_with(force=True)
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


def test_market_snapshot_uses_report_verified_gangtise_contracts():
    from src.domain import market_services

    index_result = {
        "ok": True,
        "provider": "Gangtise OpenAPI",
        "points": [
            {"date": "2026-08-07", "open": 100, "high": 101, "low": 99, "close": 100},
            {"date": "2026-08-10", "open": 101, "high": 102, "low": 100, "close": 101},
        ],
    }
    selected_market = ["source_shanghai_index", "source_hsi"]
    selected_sectors = ["电子", "银行"]
    sector_rows = [{"sector": sector, "code": market_services.GANGTISE_SHENWAN_LEVEL1_CODES[sector], "value": 102, "change": 2, "change_pct": 2, "updated_at": "2026-08-10", "data_source": "Gangtise OpenAPI"} for sector in selected_sectors]
    with patch.object(market_services, "fetch_gangtise_market_index_history", return_value=index_result) as index_fetch, \
        patch.object(market_services, "_fetch_gangtise_sector_overview", return_value=(sector_rows, [])) as sector_fetch, \
        patch.object(market_services, "_resolve_shared_market_snapshot_selection", return_value={"market_codes": selected_market, "sector_names": selected_sectors}), \
        patch.object(market_services, "_save_watchlist_cache"), \
        patch.object(market_services, "_save_market_snapshot_payload") as save_snapshot:
        result = market_services.sync_market_snapshot(force=True)

    assert [call.args[0] for call in index_fetch.call_args_list] == selected_market
    assert result["overview_count"] == len(selected_market)
    assert result["sector_count"] == len(selected_sectors)
    assert result["selected_market_codes"] == selected_market
    assert result["selected_sector_names"] == selected_sectors
    sector_fetch.assert_called_once_with(ANY, ANY, selected_sectors)
    overview = next(call.args[2] for call in save_snapshot.call_args_list if call.args[:2] == ("market_overview", "standard_indices"))
    assert overview["source"] == "Gangtise OpenAPI"
    assert overview["snapshot_version"] == 10
    assert overview["selection_scope"] == "tenant_union"
    assert any(call.args[:2] == ("market_sector_overview", "shenwan_level1") for call in save_snapshot.call_args_list)


def test_market_snapshot_refreshes_industry_snapshot_on_every_run():
    from src.domain import market_services

    index_result = {
        "ok": True,
        "provider": "Gangtise OpenAPI",
        "points": [
            {"date": "2026-08-07", "close": 100},
            {"date": "2026-08-10", "close": 101},
        ],
    }
    with patch.object(market_services, "fetch_gangtise_market_index_history", return_value=index_result), \
        patch.object(market_services, "_fetch_gangtise_sector_overview", return_value=([], ["empty"])) as sector_fetch, \
        patch.object(market_services, "_resolve_shared_market_snapshot_selection", return_value={"market_codes": ["source_shanghai_index"], "sector_names": ["电子"]}), \
        patch.object(market_services, "_save_watchlist_cache"), \
        patch.object(market_services, "_save_market_snapshot_payload"):
        result = market_services.sync_market_snapshot(force=False)

    assert result["sector_count"] == 0
    sector_fetch.assert_called_once()


def test_market_snapshot_selection_uses_the_deduplicated_dav_union_and_keeps_empty_selection_empty():
    from src.domain import core_services, market_services

    tenants = [{"slug": "laowang"}, {"slug": "duoge"}, {"slug": "empty"}]
    settings = {
        "laowang": {"configured": True, "market_overview_codes": ["source_shanghai_index", "source_hsi"], "sector_names": ["电子", "银行"]},
        "duoge": {"configured": True, "market_overview_codes": ["source_hsi", "source_dji"], "sector_names": ["银行", "计算机"]},
        "empty": {"configured": True, "market_overview_codes": [], "sector_names": []},
    }
    with patch.object(core_services, "get_tenant_configs", return_value=tenants), patch.object(
        core_services, "load_tenant_market_display_settings", side_effect=lambda slug: settings[slug]
    ):
        selection = market_services._resolve_shared_market_snapshot_selection()

    assert selection == {
        "market_codes": ["source_shanghai_index", "source_hsi", "source_dji"],
        "sector_names": ["电子", "银行", "计算机"],
    }


def test_market_snapshot_selection_does_not_call_defaults_when_every_dav_published_an_empty_panel():
    from src.domain import core_services, market_services

    with patch.object(core_services, "get_tenant_configs", return_value=[{"slug": "empty"}]), patch.object(
        core_services, "load_tenant_market_display_settings", return_value={"configured": True, "market_overview_codes": [], "sector_names": []}
    ):
        selection = market_services._resolve_shared_market_snapshot_selection()

    assert selection == {"market_codes": [], "sector_names": []}


def test_empty_dav_sector_selection_makes_no_gangtise_sector_request():
    from src.domain import market_services

    with patch.object(market_services, "fetch_gangtise_market_kline_series") as fetch:
        items, errors = market_services._fetch_gangtise_sector_overview("2026-09-01", "2026-09-18", [])

    assert items == []
    assert errors == []
    fetch.assert_not_called()


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
    assert overview["source"] == "Gangtise OpenAPI"
    assert sectors["items"] == []
    assert sectors["source"] == "Gangtise OpenAPI"


def test_page_watchlist_catalog_never_fetches_a_provider_when_cache_is_missing(monkeypatch):
    from src.domain import market_services

    monkeypatch.setattr(market_services, "_load_watchlist_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(market_services, "_enrich_watchlist_details", lambda details: details)
    monkeypatch.setattr(
        market_services,
        "_fetch_watchlist_realtime_detail_from_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("page composition must not fetch quotes")),
    )

    details = market_services.gen_watchlist_details()

    assert details
    assert all(item.get("data_unavailable") for item in details.values())
