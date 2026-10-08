from unittest.mock import Mock, patch

import pandas as pd

import app as app_entry
from src.domain import market_services


def test_stock_daily_contract_uses_gangtise_security_kline_for_a_share():
    response = {
        "code": "000000",
        "status": True,
        "data": {
            "fieldList": ["securityCode", "tradeDate", "open", "high", "low", "close"],
            "list": [
                ["600519.SH", "2026-09-01", 10, 11, 9, 10.5],
                ["600519.SH", "2026-09-02", 10.5, 12, 10, 11.5],
            ],
        },
    }
    with patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 1)):
        result = market_services.fetch_gangtise_market_kline_series(
            market_services.GANGTISE_SECURITY_KLINE_DAILY_PATH,
            "600519.SH", start_date="2026-09-01", end_date="2026-09-02", limit=90,
        )

    assert result["ok"] is True
    assert result["response"] == response
    assert result["points"][-1]["close"] == 11.5
    assert result["path"] == market_services.GANGTISE_SECURITY_KLINE_DAILY_PATH


def test_on_demand_unseeded_a_share_detail_fetches_its_canonical_gangtise_series():
    """A direct watchlist view must fetch a normal A-share from Gangtise."""
    candidate = {
        "code": "601818",
        "name": "光大银行",
        "market": "SH",
        "security_code": "601818.SH",
        "industry": "银行",
    }
    daily_result = {
        "ok": True,
        "provider": "Gangtise OpenAPI",
        "path": market_services.GANGTISE_SECURITY_KLINE_DAILY_PATH,
        "points": [
            {"date": "2026-09-16", "open": 3.1, "high": 3.2, "low": 3.0, "close": 3.12},
            {"date": "2026-09-17", "open": 3.12, "high": 3.25, "low": 3.1, "close": 3.2},
        ],
    }
    with app_entry.app.app_context():
        with patch.object(market_services, "_resolve_watchlist_candidate", return_value=candidate), patch.object(
            market_services, "fetch_gangtise_market_kline_series", return_value=daily_result
        ) as fetch_daily, patch.object(market_services, "attach_watchlist_intraday", side_effect=lambda detail: detail), patch.object(
            market_services, "_save_watchlist_cache"
        ):
            detail = market_services.get_watchlist_detail_by_code(
                stock_code="601818",
                stock_name="光大银行",
                details_map={},
                allow_provider_fetch=True,
            )

    assert detail["code"] == "601818"
    assert detail["name"] == "光大银行"
    assert detail["market"] == "SH"
    assert detail["data_unavailable"] is False
    assert len(detail["kline"]) == 2
    assert fetch_daily.call_args.args[0] == market_services.GANGTISE_SECURITY_KLINE_DAILY_PATH
    assert fetch_daily.call_args.kwargs["security_code"] == "601818.SH"


def test_watchlist_detail_keeps_up_to_ninety_daily_points_for_analysis():
    candidate = {
        "code": "600519",
        "name": "贵州茅台",
        "market": "SH",
        "security_code": "600519.SH",
        "industry": "食品饮料",
    }
    points = [
        {"date": f"2026-01-{index:02d}", "open": 100 + index, "high": 101 + index, "low": 99 + index, "close": 100 + index}
        for index in range(1, 101)
    ]
    with patch.object(
        market_services, "fetch_gangtise_market_kline_series", return_value={"ok": True, "provider": "Gangtise OpenAPI", "points": points}
    ), patch.object(market_services, "attach_watchlist_intraday", side_effect=lambda detail: detail), patch.object(
        market_services, "_save_watchlist_cache"
    ):
        detail = market_services._fetch_watchlist_realtime_detail_from_candidate(candidate)

    assert len(detail["kline"]) == 20
    assert len(detail["history_kline"]["candles"]) == 90
    assert len(detail["history_series"]) == 90
    assert detail["history_window"] == 90


def test_stock_minute_uses_sina_backed_akshare_for_a_share():
    frame = pd.DataFrame([
        {"day": "2026-09-02 09:31:00", "close": 320.1},
        {"day": "2026-09-02 09:32:00", "close": 321.2},
    ])
    ak = Mock()
    ak.stock_zh_a_minute.return_value = frame

    result = market_services.fetch_akshare_stock_intraday_series(
        "600519.SH", "2026-09-02", ak=ak
    )

    assert result["available"] is True
    assert result["source"] == "Sina"
    assert result["points"][-1]["value"] == 321.2
    ak.stock_zh_a_minute.assert_called_once()


def test_hong_kong_minute_does_not_call_eastmoney_endpoint():
    ak = Mock()
    result = market_services.fetch_akshare_stock_intraday_series("00700.HK", "2026-09-02", ak=ak)

    assert result["available"] is False
    assert result["source"] == "Sina"
    ak.stock_hk_hist_min_em.assert_not_called()


def test_watchlist_intraday_uses_gangtise_not_akshare():
    detail = {
        "code": "600519",
        "market": "SH",
        "standard_code": "600519.SH",
        "kline": [{"date": "2026-09-01"}, {"date": "2026-09-02"}],
    }
    expected = {
        "ok": True,
        "available": True,
        "points": [{"date": "2026-09-02 09:31:00", "value": 10.2}],
        "source": "gangtise_openapi",
        "updated_at": "2026-09-02 09:31:00",
    }
    with patch.object(market_services, "is_cn_stock_market_open", return_value=False), patch.object(
        market_services, "_load_watchlist_cache", return_value=None
    ), patch.object(
        market_services, "fetch_gangtise_intraday_series", return_value=expected
    ) as fetch_gangtise, patch.object(
        market_services, "fetch_akshare_stock_intraday_series", side_effect=AssertionError("Stock K-line must not call AKShare")
    ):
        result = market_services.fetch_watchlist_intraday_series(detail)

    fetch_gangtise.assert_called_once_with("600519.SH", trade_date="2026-09-02")
    assert result["source"] == "gangtise_openapi"


def test_open_market_intraday_points_append_a_provisional_current_day_candle():
    detail = {
        "price": 10.2,
        "change": 0.2,
        "change_pct": 2.0,
        "kline": [
            {"date": "2026-09-18", "open": 9.8, "high": 10.1, "low": 9.7, "close": 10.0},
            {"date": "2026-09-19", "open": 10.0, "high": 10.3, "low": 9.9, "close": 10.2},
        ],
        "history_kline": {"candles": [
            {"date": "2026-09-18", "open": 9.8, "high": 10.1, "low": 9.7, "close": 10.0},
            {"date": "2026-09-19", "open": 10.0, "high": 10.3, "low": 9.9, "close": 10.2},
        ]},
    }
    points = [
        {"date": "2026-09-20 09:31:00", "value": 10.3},
        {"date": "2026-09-20 09:32:00", "value": 10.5},
        {"date": "2026-09-20 09:33:00", "value": 10.4},
    ]
    with patch.object(market_services, "is_cn_stock_market_open", return_value=True), patch.object(
        market_services, "_current_cn_market_date", return_value=__import__("datetime").date(2026, 9, 20)
    ):
        result = market_services._merge_watchlist_intraday_candle(detail, points)

    candle = result["kline"][-1]
    assert candle == {
        "date": "2026-09-20", "open": 10.3, "high": 10.5, "low": 10.3, "close": 10.4, "provisional": True,
    }
    assert result["price"] == 10.4
    assert result["change_pct"] == 1.96
    assert result["kline_contains_intraday"] is True


def test_closed_market_does_not_synthesize_a_daily_candle_from_minutes():
    detail = {"kline": [{"date": "2026-09-19", "close": 10.2}]}
    with patch.object(market_services, "is_cn_stock_market_open", return_value=False):
        result = market_services._merge_watchlist_intraday_candle(
            detail, [{"date": "2026-09-20 09:31:00", "value": 10.3}]
        )
    assert result["kline"] == [{"date": "2026-09-19", "close": 10.2}]


def test_attach_intraday_exposes_the_current_day_candle_on_watchlist_detail():
    detail = {
        "code": "600519", "market": "SH", "standard_code": "600519.SH",
        "kline": [
            {"date": "2026-09-18", "open": 9.8, "high": 10.1, "low": 9.7, "close": 10.0},
            {"date": "2026-09-19", "open": 10.0, "high": 10.3, "low": 9.9, "close": 10.2},
        ],
    }
    intraday = {
        "available": True, "source": "Sina", "updated_at": "2026-09-20 09:33:00", "message": "",
        "points": [
            {"date": "2026-09-20 09:31:00", "value": 10.3},
            {"date": "2026-09-20 09:33:00", "value": 10.4},
        ],
    }
    with patch.object(market_services, "fetch_watchlist_intraday_series", return_value=intraday), patch.object(
        market_services, "is_cn_stock_market_open", return_value=True
    ), patch.object(market_services, "_current_cn_market_date", return_value=__import__("datetime").date(2026, 9, 20)), patch.object(
        market_services, "_resolve_watchlist_intraday_trade_date", return_value=""
    ):
        result = market_services.attach_watchlist_intraday(detail)

    assert result["intraday_available"] is True
    assert result["kline"][-1]["date"] == "2026-09-20"
    assert result["kline"][-1]["close"] == 10.4
    assert result["kline_contains_intraday"] is True


def test_old_gangtise_watchlist_cache_is_not_usable():
    cached = {
        "data_source": "gangtise_openapi",
        "kline": [{"date": "2026-09-01"}, {"date": "2026-09-02"}],
    }
    assert market_services._watchlist_detail_cache_is_usable(cached) is False


def test_old_eastmoney_cache_marked_as_akshare_is_not_usable():
    cached = {
        "data_source": "AKShare",
        "kline": [{"date": "2026-09-01"}, {"date": "2026-09-02"}],
    }
    assert market_services._watchlist_detail_cache_is_usable(cached) is False


def test_watchlist_analysis_history_cache_requires_ninety_points_window():
    cached = {
        "data_source": "Gangtise OpenAPI",
        "kline": [{"date": "2026-09-01"}, {"date": "2026-09-02"}],
        "history_kline": {"candles": [{"date": "2026-09-02"}], "history_window": 60},
        "history_window": 60,
    }

    assert market_services._watchlist_detail_cache_is_usable(cached) is False


def test_hong_kong_construction_bank_uses_name_based_bank_industry_fallback():
    detail = market_services._build_watchlist_unavailable_detail(
        stock_code="00939",
        stock_name="建设银行",
    )

    assert detail["market"] == "HK"
    assert detail["industry"] == "银行"
    assert detail["focus"] == "银行"


def test_remote_security_industry_is_preserved_for_watchlist_classification():
    candidate = market_services._normalize_watchlist_security_candidate({
        "gtsCode": "00939.HK",
        "gtsName": "建设银行",
        "market": "HK",
        "industry": "银行",
    })

    assert candidate["industry"] == "银行"
    assert market_services.resolve_watchlist_industry(
        stock_code=candidate["code"],
        stock_name=candidate["name"],
        industry=candidate["industry"],
    ) == "银行"
