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


def test_market_index_uses_reported_gangtise_daily_quote_path():
    from src.domain import market_services

    with patch.object(
        market_services,
        "post_gangtise_openapi_json",
        return_value=(200, _daily_response(), 5),
    ) as post:
        result = market_services.fetch_gangtise_indicator_series(
            "source_shanghai_index",
            start_date="2026-08-01",
            end_date="2026-08-10",
        )

    assert result["ok"] is True
    assert result["source_meta"]["path"] == "/application/open-quote/kline/daily"
    assert post.call_args.args[0] == "/application/open-quote/kline/daily"
    assert post.call_args.args[1]["securityList"] == ["000001.SH"]


def test_market_index_history_supports_verified_edb_indices_without_akshare():
    from src.domain import market_services

    expected = {"ok": True, "points": [
        {"date": "2026-08-07", "close": 25800.00},
        {"date": "2026-08-10", "close": 26009.46},
    ]}
    with patch.object(market_services, "fetch_gangtise_indicator_series", return_value=expected) as fetch:
        result = market_services.fetch_gangtise_market_index_history(
            "source_hsi", "2026-08-01", "2026-08-10"
        )

    assert result["ok"] is True
    assert result["provider"] == "Gangtise OpenAPI"
    fetch.assert_called_once_with("source_hsi", start_date="2026-08-01", end_date="2026-08-10", token="")


def test_shenwan_sector_sync_uses_all_verified_swi_codes():
    from src.domain import market_services

    calls = []

    def fake_fetch(path, security_code, **kwargs):
        calls.append((path, security_code, kwargs))
        return {
            "ok": True,
            "points": [
                {"date": "2026-08-07", "close": 100},
                {"date": "2026-08-10", "close": 102},
            ],
            "duration_ms": 3,
        }

    with patch.object(market_services, "fetch_gangtise_market_kline_series", side_effect=fake_fetch):
        rows, errors = market_services._fetch_gangtise_sector_overview("2026-08-01", "2026-08-10")

    assert errors == []
    assert len(rows) == 31
    assert len(calls) == 31
    assert {code for _, code, _ in calls} == set(market_services.GANGTISE_SHENWAN_LEVEL1_CODES.values())
    assert all(path == "/application/open-quote/kline/daily" for path, _, _ in calls)
    assert all(row["data_source"] == "Gangtise OpenAPI" for row in rows)


def test_market_snapshot_does_not_call_akshare_and_persists_gangtise_source():
    from src.domain import market_services

    index_result = {
        "ok": True,
        "provider": "Gangtise OpenAPI",
        "points": [
            {"date": "2026-08-07", "open": 100, "high": 101, "low": 99, "close": 100},
            {"date": "2026-08-10", "open": 101, "high": 102, "low": 100, "close": 101},
        ],
    }
    sector_rows = [{
        "sector": "银行", "code": "801780.SWI", "value": 102, "change": 2,
        "change_pct": 2, "updated_at": "2026-08-10", "data_source": "Gangtise OpenAPI",
    }]
    with patch.object(market_services, "fetch_gangtise_market_index_history", return_value=index_result) as index_fetch, \
        patch.object(market_services, "_fetch_gangtise_sector_overview", return_value=(sector_rows, [])), \
        patch.object(market_services, "_load_market_snapshot_payload", return_value=None), \
        patch.object(market_services, "_load_watchlist_cache", return_value=None), \
        patch.object(market_services, "_save_watchlist_cache"), \
        patch.object(market_services, "_save_market_snapshot_payload") as save_snapshot, \
        patch.object(market_services, "_load_akshare", side_effect=AssertionError("AKShare must not be used")):
        result = market_services.sync_market_snapshot(force=True)

    assert index_fetch.call_count == len(market_services.MARKET_OVERVIEW_INDEX_CODES)
    assert result["overview_count"] == len(market_services.MARKET_OVERVIEW_INDEX_CODES)
    assert result["sector_count"] == 1
    overview = next(call.args[2] for call in save_snapshot.call_args_list if call.args[:2] == ("market_overview", "standard_indices"))
    sectors = next(call.args[2] for call in save_snapshot.call_args_list if call.args[:2] == ("market_sector_overview", "shenwan_level1"))
    assert overview["source"] == "Gangtise OpenAPI"
    assert overview["snapshot_version"] == 6
    assert sectors["source"] == "Gangtise OpenAPI"


def test_market_payload_rejects_old_akshare_snapshot():
    from src.domain import market_services

    old_snapshot = {
        "ok": True,
        "snapshot_version": 5,
        "source": "AKShare",
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
