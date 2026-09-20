from unittest.mock import Mock, patch

import pandas as pd

import app as app_entry
from src.domain import market_services


def test_stock_daily_uses_sina_backed_akshare_for_a_share():
    frame = pd.DataFrame([
        {"日期": "2026-09-01", "开盘": 10, "最高": 11, "最低": 9, "收盘": 10.5},
        {"日期": "2026-09-02", "开盘": 10.5, "最高": 12, "最低": 10, "收盘": 11.5},
    ])
    ak = Mock()
    ak.stock_zh_a_daily.return_value = frame

    result = market_services.fetch_akshare_stock_kline_series(
        "600519.SH", "2026-09-01", "2026-09-02", ak=ak
    )

    assert result["ok"] is True
    assert result["provider"] == "Sina"
    assert result["points"][-1]["close"] == 11.5
    ak.stock_zh_a_daily.assert_called_once()


def test_on_demand_unseeded_a_share_detail_fetches_its_canonical_sina_series():
    """A direct watchlist view must fetch a normal A-share absent from demo seeds."""
    candidate = {
        "code": "601818",
        "name": "光大银行",
        "market": "SH",
        "security_code": "601818.SH",
        "industry": "银行",
    }
    daily_result = {
        "ok": True,
        "provider": "Sina",
        "points": [
            {"date": "2026-09-16", "open": 3.1, "high": 3.2, "low": 3.0, "close": 3.12},
            {"date": "2026-09-17", "open": 3.12, "high": 3.25, "low": 3.1, "close": 3.2},
        ],
    }
    with app_entry.app.app_context():
        with patch.object(market_services, "_resolve_watchlist_candidate", return_value=candidate), patch.object(
            market_services, "fetch_akshare_stock_kline_series", return_value=daily_result
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
    assert fetch_daily.call_args.kwargs["security_code"] == "601818.SH"


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


def test_watchlist_intraday_never_calls_gangtise():
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
        "source": "Sina",
        "updated_at": "2026-09-02 09:31:00",
    }
    with patch.object(market_services, "_load_watchlist_cache", return_value=None), patch.object(
        market_services, "fetch_akshare_stock_intraday_series", return_value=expected
    ) as fetch_akshare, patch.object(
        market_services, "fetch_gangtise_intraday_series", side_effect=AssertionError("K-line must not call Gangtise")
    ):
        result = market_services.fetch_watchlist_intraday_series(detail)

    fetch_akshare.assert_called_once_with("600519.SH", trade_date="2026-09-02")
    assert result["source"] == "Sina"


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
