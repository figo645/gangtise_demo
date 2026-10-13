"""BDD coverage for the real-K-line forecast projection."""

from datetime import date, timedelta
from unittest.mock import patch

from app import app
from src.domain.core_services import build_default_forecast_workflow_graph, build_watchlist_kline_forecast
from src.domain.watchlist_analysis_services import build_watchlist_kline_analysis


def _real_candles(count=90):
    start = date(2026, 1, 2)
    rows = []
    close = 100.0
    for index in range(count):
        close += 0.3 if index % 6 else -0.12
        current = start + timedelta(days=index)
        rows.append({
            "date": current.isoformat(),
            "open": round(close - 0.2, 2),
            "high": round(close + 0.7, 2),
            "low": round(close - 0.8, 2),
            "close": round(close, 2),
            "volume": 1000 + index * 10,
        })
    return rows


def test_given_real_daily_kline_when_forecast_runs_then_it_returns_20_to_60_day_statistical_projection():
    candles = _real_candles()
    result = build_watchlist_kline_forecast(
        candles,
        analysis=build_watchlist_kline_analysis(candles),
        graph=build_default_forecast_workflow_graph(),
    )

    assert result["available"] is True
    assert result["summary"]["sample_size"] == 90
    assert len(result["history"]) == 90
    assert len(result["points"]) == 60
    assert all(point["lower"] < point["value"] < point["upper"] for point in result["points"])
    assert result["history"][-1]["close"] == candles[-1]["close"]
    assert "真实历史日 K" in result["disclaimer"]


def test_given_insufficient_real_kline_when_forecast_runs_then_it_is_explicitly_unavailable():
    result = build_watchlist_kline_forecast(_real_candles(29))

    assert result == {
        "available": False,
        "reason": "insufficient_real_kline_history",
        "message": "至少需要 30 个真实交易日 K 线后才能生成预测区间。",
    }


def test_given_watchlist_analysis_surface_when_rendered_then_forecast_chart_uses_payload_and_hover_markers():
    source = open("templates/h5.html", encoding="utf-8").read()
    shared_source = open("static/js/h5-app.js", encoding="utf-8").read()

    assert "function renderWatchlistForecastChart(forecast)" in source
    assert "历史关键点" in source
    assert "setWatchlistForecastHorizon(20)" not in source  # buttons are generated from the shared horizon list
    assert "data.kline_forecast || {}" in source
    assert "预测中轴" in source
    assert "未来预测K线" in source
    assert "未来趋势预测" in source
    assert "统计区间" in source
    assert "5. 基于历史数据的未来预测" in source
    assert 'data-kline-forecast-panel="true"' in source
    assert 'data-watchlist-active-section="${escapeAttr(visibleSection)}"' in source
    assert "const overviewKlineSeries = analysisSeries.slice(-90);" in source
    assert "日K线（近90个交易日）" in source
    assert "function renderWatchlistForecastChart(forecast)" in shared_source
    assert "function renderWatchlistKlineAnalysis(analysis, forecast)" in shared_source
    assert "data.kline_forecast || {}" in shared_source
    assert "5. 基于历史数据的未来预测" in shared_source
    assert "未来预测K线" in shared_source
    assert "未来趋势预测" in shared_source
    assert "统计区间" in shared_source
    assert "const overviewKlineSeries = analysisSeries.slice(-90);" in shared_source
    assert "日K线（近90个交易日）" in shared_source


def test_given_h5_and_web_shells_when_rendered_then_both_load_forecast_capable_shared_script():
    user = {"username": "forecast-test", "role": "admin", "status": "active", "tenant_slug": "laowang"}
    with patch("src.web.hooks.get_current_authenticated_user", return_value=user), patch(
        "src.web.pages.get_current_authenticated_user", return_value=user
    ), patch(
        "src.web.api_core.get_site_config", return_value={"feature_flags": {"stock_forecast": True}}
    ):
        client = app.test_client()
        h5 = client.get("/h5?tenant=laowang")
        web = client.get("/web?tenant=laowang")

    assert h5.status_code == 200
    assert web.status_code == 200
    for response in (h5, web):
        html = response.get_data(as_text=True)
        if '/static/js/h5-app.js' in html:
            assert '/static/js/h5-app.js?v=20261013-2' in html
            assert 'data.kline_forecast || {}' not in html
        else:
            assert 'function renderWatchlistForecastChart(forecast)' in html
    shared_source = open("static/js/h5-app.js", encoding="utf-8").read()
    assert "function renderWatchlistForecastChart(forecast)" in shared_source
    assert "5. 基于历史数据的未来预测" in shared_source


def test_given_enabled_forecast_when_opening_stock_detail_then_real_kline_projection_is_returned():
    candles = _real_candles()
    detail = {
        "code": "600000",
        "name": "测试标的",
        "market": "SH",
        "asset_type": "stock",
        "kline": candles,
        "history_kline": {"candles": candles},
    }
    with patch("src.web.hooks.get_current_authenticated_user", return_value={"username": "forecast-test", "role": "admin", "status": "active"}), patch(
        "src.web.api_core.get_site_config", return_value={"feature_flags": {"stock_forecast": True}}
    ), patch("src.web.api_core.get_watchlist_detail_by_code", return_value=detail):
        response = app.test_client().get("/api/watchlist/600000")

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["kline_forecast"]["available"] is True
    assert len(payload["kline_forecast"]["points"]) == 60
    assert all({"open", "high", "low", "close"}.issubset(point) for point in payload["kline_forecast"]["points"])
    assert len({point["close"] for point in payload["kline_forecast"]["points"][:20]}) > 1


def test_given_legacy_disabled_flag_when_opening_stock_detail_then_forecast_failure_is_visible_and_diagnosable():
    candles = _real_candles()
    detail = {
        "code": "600000",
        "name": "测试标的",
        "market": "SH",
        "asset_type": "stock",
        "kline": candles,
        "history_kline": {"candles": candles},
    }
    with patch("src.web.hooks.get_current_authenticated_user", return_value={"username": "forecast-test", "role": "admin", "status": "active"}), patch(
        "src.web.api_core.get_site_config", return_value={"feature_flags": {"stock_forecast": False}}
    ), patch("src.web.api_core.get_watchlist_detail_by_code", return_value=detail):
        response = app.test_client().get("/api/watchlist/600000")

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["kline_forecast"] == {
        "available": False,
        "reason": "stock_forecast_disabled",
        "message": "预测模型未启用，请在 Admin 功能开关中启用股票 K 线预测。",
    }


def test_given_gangtise_minute_contract_when_building_request_then_unsupported_security_name_is_not_sent():
    from src.domain.market_services import fetch_gangtise_intraday_series

    captured = []

    def fake_post(path, payload, token="", timeout=30):
        captured.append(payload)
        return 200, {
            "code": "000000",
            "status": True,
            "data": {
                "fieldList": ["securityCode", "tradeTime", "close"],
                "list": [["600519.SH", "2026-08-10 09:31:00", 1688.2], ["600519.SH", "2026-08-10 09:32:00", 1690.1]],
            },
        }, 1

    with patch("src.domain.market_services._load_watchlist_cache", return_value=None), patch(
        "src.domain.market_services._save_watchlist_cache", return_value=None
    ), patch("src.domain.market_services.post_gangtise_openapi_json", side_effect=fake_post):
        result = fetch_gangtise_intraday_series("600519.SH", trade_date="2026-08-10")

    assert result["available"] is True
    assert "securityName" not in captured[0]["fieldList"]
