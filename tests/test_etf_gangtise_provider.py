from unittest.mock import patch


def test_etf_batch_daily_kline_uses_gangtise_security_contract():
    from src.domain import market_services

    response = {
        "code": "000000",
        "status": True,
        "data": {
            "fieldList": ["securityCode", "securityName", "tradeDate", "open", "high", "low", "close", "volume"],
            "list": [
                ["510300.SH", "沪深300ETF华泰柏瑞", "2026-10-07", "1.00", "1.02", "0.99", "1.00", "10000"],
                ["510300.SH", "沪深300ETF华泰柏瑞", "2026-10-08", "1.10", "1.12", "1.08", "1.10", "12000"],
                ["510500.SH", "中证500ETF南方", "2026-10-07", "2.00", "2.02", "1.99", "2.00", "20000"],
                ["510500.SH", "中证500ETF南方", "2026-10-08", "2.10", "2.12", "2.08", "2.10", "22000"],
            ],
        },
    }
    with patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 5)) as post:
        result = market_services.fetch_gangtise_etf_kline_series(
            ["510300.SH", "510500.SH"],
            start_date="2026-10-01",
            end_date="2026-10-08",
        )

    assert post.call_args.args[0] == market_services.GANGTISE_SECURITY_KLINE_DAILY_PATH
    assert post.call_args.args[1]["securityList"] == ["510300.SH", "510500.SH"]
    assert post.call_args.args[1]["Limit"] == 500
    assert "limit" not in post.call_args.args[1]
    assert post.call_args.args[1]["fieldList"][-1] == "volume"
    assert "securityName" not in post.call_args.args[1]["fieldList"]
    assert result["510300.SH"]["provider"] == "Gangtise OpenAPI"
    assert result["510300.SH"]["points"][-1]["close"] == 1.1
    assert result["510300.SH"]["points"][-1]["volume"] == 12000
    assert result["510500.SH"]["points"][-1]["close"] == 2.1


def test_etf_batch_retries_a_code_with_only_one_returned_day():
    from src.domain import market_services

    batch_response = {
        "code": "000000",
        "status": True,
        "data": {
            "fieldList": ["securityCode", "securityName", "tradeDate", "open", "high", "low", "close", "volume"],
            "list": [["510500.SH", "中证500ETF南方", "2026-10-08", "2.10", "2.12", "2.08", "2.10", "22000"]],
        },
    }
    single_response = {
        "code": "000000",
        "status": True,
        "data": {
            "fieldList": ["securityCode", "securityName", "tradeDate", "open", "high", "low", "close", "volume"],
            "list": [
                ["510500.SH", "中证500ETF南方", "2026-10-07", "2.00", "2.02", "1.99", "2.00", "20000"],
                ["510500.SH", "中证500ETF南方", "2026-10-08", "2.10", "2.12", "2.08", "2.10", "22000"],
            ],
        },
    }
    with patch.object(
        market_services,
        "post_gangtise_openapi_json",
        side_effect=[(200, batch_response, 5), (200, single_response, 6)],
    ) as post:
        result = market_services.fetch_gangtise_etf_kline_series(
            ["510500.SH"], start_date="2026-10-01", end_date="2026-10-08"
        )

    assert post.call_count == 2
    assert len(result["510500.SH"]["points"]) == 2
    assert result["510500.SH"]["ok"] is True


def test_etf_overview_does_not_fall_back_to_akshare():
    from src.domain import market_services

    with patch.object(market_services, "fetch_gangtise_etf_kline_series", return_value={}), \
        patch.object(market_services, "fetch_akshare_stock_kline_series", side_effect=AssertionError("AKShare fallback is forbidden for ETF")):
        with market_services._etf_overview_cache_lock:
            market_services._etf_overview_cache["payload"] = None
            market_services._etf_overview_cache["expires_at"] = 0
        payload = market_services.build_etf_overview_payload()

    assert payload["data_source"] == "Gangtise OpenAPI ETF 日线"
    assert all(item["available"] is False for item in payload["items"])


def test_etf_detail_returns_gangtise_history_for_the_existing_detail_page():
    from src.domain import market_services

    points = [
        {"date": "2026-10-07", "open": 2.0, "high": 2.02, "low": 1.99, "close": 2.0, "volume": 20000},
        {"date": "2026-10-08", "open": 2.1, "high": 2.12, "low": 2.08, "close": 2.1, "volume": 22000},
    ]
    with patch.object(market_services, "fetch_gangtise_etf_kline_series", return_value={
        "510500.SH": {"provider": "Gangtise OpenAPI", "points": points},
    }):
        payload = market_services.build_etf_detail_payload("510500.SH")

    assert payload["ok"] is True
    assert payload["asset_type"] == "etf"
    assert payload["data_source"] == "Gangtise OpenAPI"
    assert payload["price"] == 2.1
    assert payload["change_pct"] == 5.0
    assert len(payload["kline"]) == 2
    assert payload["history_kline"]["candles"][-1]["close"] == 2.1


def test_etf_overview_keeps_latest_price_when_gangtise_returns_only_one_day():
    from src.domain import market_services

    with patch.object(
        market_services,
        "fetch_gangtise_etf_kline_series",
        return_value={
            "510500.SH": {
                "provider": "Gangtise OpenAPI",
                "points": [{"date": "2026-10-08", "close": 2.1, "volume": 0}],
            }
        },
    ), patch.object(market_services, "fetch_gangtise_market_kline_series", return_value={"points": []}):
        with market_services._etf_overview_cache_lock:
            market_services._etf_overview_cache["payload"] = None
            market_services._etf_overview_cache["expires_at"] = 0
        payload = market_services.build_etf_overview_payload()

    item = next(item for item in payload["items"] if item["security_code"] == "510500.SH")
    assert item["available"] is True
    assert item["change_available"] is False
    assert item["price"] == 2.1
    assert item["change_pct"] is None
