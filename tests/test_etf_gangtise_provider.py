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
    assert post.call_args.args[1]["fieldList"][-1] == "volume"
    assert result["510300.SH"]["provider"] == "Gangtise OpenAPI"
    assert result["510300.SH"]["points"][-1]["close"] == 1.1
    assert result["510300.SH"]["points"][-1]["volume"] == 12000
    assert result["510500.SH"]["points"][-1]["close"] == 2.1


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
