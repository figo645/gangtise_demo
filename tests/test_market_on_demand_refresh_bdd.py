"""BDD checks for cache-aside market and industry snapshot refreshes."""

from datetime import datetime, timedelta
from unittest.mock import patch

from src.domain import market_services


def _snapshot(updated_at):
    return {
        "ok": True,
        "snapshot_version": 10,
        "source": "Gangtise OpenAPI",
        "updated_at": updated_at,
        "items": [{"indicator_code": "source_shanghai_index", "name": "上证指数", "available": True}],
    }


def test_given_open_market_and_stale_shared_snapshot_when_read_then_one_refresh_is_queued_without_hiding_data():
    stale = _snapshot((datetime.now() - timedelta(minutes=6)).strftime("%Y-%m-%d %H:%M:%S"))
    with patch.object(market_services, "is_cn_stock_market_open", return_value=True), patch.object(
        market_services, "request_market_snapshot_refresh", return_value={"queued": True, "started": True}
    ) as refresh:
        result = market_services._apply_market_snapshot_on_demand_refresh(stale)

    refresh.assert_called_once()
    assert result["items"] == stale["items"]
    assert result["refreshing"] is True
    assert result["stale"] is True
    assert result["refresh_reason"] == "on_demand_stale"
    assert result["refresh_after_ms"] == 3000


def test_given_open_market_and_fresh_shared_snapshot_when_read_then_no_provider_refresh_is_queued():
    fresh = _snapshot(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    with patch.object(market_services, "is_cn_stock_market_open", return_value=True), patch.object(
        market_services, "request_market_snapshot_refresh"
    ) as refresh:
        result = market_services._apply_market_snapshot_on_demand_refresh(fresh)

    refresh.assert_not_called()
    assert result["freshness"]["needs_refresh"] is False
    assert result.get("refreshing") is not True


def test_given_closed_market_and_old_snapshot_when_read_then_no_unnecessary_refresh_is_queued():
    old = _snapshot((datetime.now() - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S"))
    with patch.object(market_services, "is_cn_stock_market_open", return_value=False), patch.object(
        market_services, "request_market_snapshot_refresh"
    ) as refresh:
        result = market_services._apply_market_snapshot_on_demand_refresh(old)

    refresh.assert_not_called()
    assert result["freshness"]["needs_refresh"] is False


def test_given_stale_market_snapshot_when_building_h5_payload_then_read_is_non_blocking_and_queues_refresh():
    stale = _snapshot((datetime.now() - timedelta(minutes=6)).strftime("%Y-%m-%d %H:%M:%S"))
    with patch.object(market_services, "_load_market_snapshot_payload", return_value=stale), patch.object(
        market_services, "is_cn_stock_market_open", return_value=True
    ), patch.object(
        market_services, "request_market_snapshot_refresh", return_value={"queued": True, "started": True}
    ) as refresh:
        payload = market_services.build_market_overview_payload()

    refresh.assert_called_once()
    assert payload["items"] == stale["items"]
    assert payload["refreshing"] is True


def test_given_missing_sector_snapshot_when_building_h5_payload_then_no_provider_call_happens_in_the_read_path():
    with patch.object(market_services, "_load_market_snapshot_payload", return_value=None), patch.object(
        market_services, "_load_watchlist_cache", return_value=None
    ), patch.object(
        market_services, "request_market_snapshot_refresh", return_value={"queued": True, "started": True}
    ) as refresh:
        payload = market_services.build_market_sector_overview_payload()

    refresh.assert_called_once()
    assert payload["items"] == []
    assert payload["refreshing"] is True
    assert payload["refresh_reason"] == "cache_missing"


def test_given_prior_close_and_today_minute_quote_when_building_market_snapshot_then_today_quote_drives_change():
    daily = {
        "ok": True,
        "points": [
            {"date": "2026-09-16", "close": 3800.0},
            {"date": "2026-09-17", "close": 3810.0},
        ],
    }
    minute = {
        "available": True,
        "points": [{"date": "2026-09-18 10:37:00", "value": 3875.60}],
    }
    with patch.object(market_services, "is_cn_stock_market_open", return_value=True), patch.object(
        market_services, "_current_cn_market_date", return_value=datetime(2026, 9, 18).date()
    ), patch.object(market_services, "fetch_gangtise_intraday_series", return_value=minute):
        result = market_services._with_gangtise_intraday_market_quote(daily, "000001.SH")
        item = market_services._build_market_index_snapshot_item("source_shanghai_index", result)

    assert result["quote_mode"] == "intraday_minute"
    assert result["realtime"] is True
    assert item["updated_at"] == "2026-09-18 10:37:00"
    assert item["price"] == 3875.60
    assert item["change"] == 65.60
    assert item["change_pct"] == 1.72


def test_given_unavailable_minute_quote_when_building_market_snapshot_then_prior_close_is_explicitly_marked_non_realtime():
    daily = {
        "ok": True,
        "points": [
            {"date": "2026-09-16", "close": 3800.0},
            {"date": "2026-09-17", "close": 3810.0},
        ],
    }
    with patch.object(market_services, "is_cn_stock_market_open", return_value=True), patch.object(
        market_services, "fetch_gangtise_intraday_series", return_value={"available": False, "message": "unsupported"}
    ):
        result = market_services._with_gangtise_intraday_market_quote(daily, "000001.SH")
        item = market_services._build_market_index_snapshot_item("source_shanghai_index", result)

    assert result["quote_mode"] == "daily_close_fallback"
    assert item["realtime"] is False
    assert item["intraday_message"] == "unsupported"


def test_given_h5_gets_queued_refresh_when_rendering_then_it_performs_only_one_delayed_recheck():
    source = (market_services.PROJECT_ROOT / "templates" / "h5.html").read_text(encoding="utf-8")
    assert "feedMarketOnDemandRetryPending" in source
    assert "refresh_after_ms" in source
    assert "loadFeedMarketEconomy();" in source
