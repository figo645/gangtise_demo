from unittest.mock import Mock, patch

import pandas as pd

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
