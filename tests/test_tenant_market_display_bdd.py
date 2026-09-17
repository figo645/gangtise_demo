"""BDD contracts for Gangtise shared snapshots and DaV 4+10 display choices."""

from unittest.mock import patch

from src.runtime import app


DAV = {"id": "dav-1", "username": "dav-1", "role": "dav", "tenant_slug": "laowang"}


def _status(response):
    return response[1] if isinstance(response, tuple) else response.status_code


def _json(response):
    return response[0].get_json() if isinstance(response, tuple) else response.get_json()


def test_given_shared_gangtise_snapshot_when_tenant_has_published_selection_then_only_4_and_10_are_visible():
    from src.domain import market_services

    overview = {
        "items": [
            {"indicator_code": code, "available": True, "name": code}
            for code in market_services.MARKET_OVERVIEW_INDEX_CODES
        ]
    }
    sectors = {
        "items": [
            {"sector": name, "available": True}
            for name in market_services.SHENWAN_LEVEL1_INDUSTRIES
        ]
    }
    settings = {
        "configured": True,
        "market_overview_codes": list(market_services.MARKET_OVERVIEW_INDEX_CODES[:4]),
        "sector_names": list(market_services.SHENWAN_LEVEL1_INDUSTRIES[:10]),
    }
    with patch("src.domain.core_services.load_tenant_market_display_settings", return_value=settings):
        selected_market = market_services._apply_tenant_market_display_selection(overview, "laowang", "market")
        selected_sectors = market_services._apply_tenant_market_display_selection(sectors, "laowang", "sector")

    assert [item["indicator_code"] for item in selected_market["items"]] == settings["market_overview_codes"]
    assert [item["sector"] for item in selected_sectors["items"]] == settings["sector_names"]
    assert selected_market["display_limit"] == 4
    assert selected_sectors["display_limit"] == 10


def test_given_dav_clears_all_choices_when_published_then_the_snapshot_projection_is_empty():
    from src.domain import market_services

    payload = {"items": [{"indicator_code": "source_shanghai_index", "available": True}]}
    with patch("src.domain.core_services.load_tenant_market_display_settings", return_value={
        "configured": True, "market_overview_codes": [], "sector_names": []
    }):
        selected = market_services._apply_tenant_market_display_selection(payload, "laowang", "market")
    assert selected["items"] == []


def test_given_unconfigured_tenant_when_reading_shared_snapshot_then_platform_recommendation_is_limited_but_not_persisted():
    from src.domain import market_services

    payload = {"items": [{"indicator_code": str(index)} for index in range(9)]}
    with patch("src.domain.core_services.load_tenant_market_display_settings", return_value={
        "configured": False, "market_overview_codes": [], "sector_names": []
    }):
        selected = market_services._apply_tenant_market_display_selection(payload, "new-tenant", "market")
    assert len(selected["items"]) == 4


def test_given_dav_posts_more_than_4_market_or_10_sector_choices_when_saving_then_api_rejects_it():
    from src.web import api_kol

    with app.test_request_context(
        "/api/tenant/laowang/market-display-config", method="POST", json={
            "market_overview_codes": ["x"] * 5, "sector_names": []
        }
    ), patch.object(api_kol, "get_current_authenticated_user", return_value=DAV):
        response = api_kol.api_tenant_market_display_config("laowang")
    assert _status(response) == 400
    assert _json(response)["error"] == "market_overview_limit_exceeded"

    with app.test_request_context(
        "/api/tenant/laowang/market-display-config", method="POST", json={
            "market_overview_codes": [], "sector_names": ["x"] * 11
        }
    ), patch.object(api_kol, "get_current_authenticated_user", return_value=DAV):
        response = api_kol.api_tenant_market_display_config("laowang")
    assert _status(response) == 400
    assert _json(response)["error"] == "hot_industry_limit_exceeded"


def test_given_dav_publishes_selection_when_follower_reads_h5_market_api_then_same_tenant_is_used():
    from src.web import api_core

    current_fan = {"id": "fan-1", "username": "fan-1", "role": "investor", "tenant_slug": "laowang"}
    with app.test_request_context("/api/market-overview?tenant=other"), patch.object(
        api_core, "get_current_authenticated_user", return_value=current_fan
    ), patch.object(api_core, "build_market_overview_payload", return_value={"ok": True, "items": []}) as build:
        response = api_core.api_market_overview()
    assert response.status_code == 200
    build.assert_called_once_with(tenant_slug="laowang")


def test_given_shared_market_task_when_scheduled_then_it_is_gangtise_and_runs_at_four_configured_times():
    from src.domain import market_services

    task = next(item for item in market_services.DEFAULT_ADMIN_TASKS if item["task_code"] == "market_snapshot_sync")
    assert task["task_name"] == "Gangtise 市场与行业指标同步"
    assert task["schedule_type"] == "daily"
    assert task["schedule_value"] == "09:30,12:00,14:00,15:30"
    assert "Gangtise EDB" in task["description"]


def test_given_four_daily_collection_slots_when_reading_between_slots_then_shared_snapshot_does_not_expire_in_six_minutes():
    from src.domain import market_services

    assert market_services.MARKET_SNAPSHOT_CACHE_TTL_SECONDS >= 20 * 60 * 60
    assert market_services.MARKET_SECTOR_OVERVIEW_CACHE_TTL_SECONDS >= 20 * 60 * 60


def test_given_dav_on_h5_or_web_when_configuring_market_display_then_both_surfaces_expose_the_same_fixed_slots():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    h5 = (root / "templates" / "h5.html").read_text(encoding="utf-8")
    web = (root / "templates" / "kol_workbench.html").read_text(encoding="utf-8")
    assert 'id="h5-market-display-config"' in h5
    assert 'data-h5-market-slot="${field}"' in h5
    assert "热门行业席位" in h5
    assert "粉丝端行情版面" in h5
    assert "编辑版面" in h5
    assert 'data-market-display-slot="${field}"' in web
    assert "编辑市场一览席位" in web
    assert "已发布给本租户粉丝" in web
