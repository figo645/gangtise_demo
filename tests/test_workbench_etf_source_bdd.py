"""API scenarios for the DAV's complete ETF data-source catalog."""

from unittest.mock import patch

import pytest

from app import app


@pytest.fixture
def etf_source_client():
    user = {"username": "etf-dav", "role": "dav", "tenant_slug": "laowang"}
    payload = {
        "ok": True,
        "data_source": "Gangtise OpenAPI ETF 日线",
        "items": [
            {"security_code": "510300.SH", "available": True, "price": 1.1},
            {"security_code": "510500.SH", "available": False, "price": None},
        ],
    }
    with patch("src.web.hooks.get_current_authenticated_user", side_effect=lambda: user), patch(
        "src.web.api_kol.get_current_authenticated_user", side_effect=lambda: user
    ), patch("src.domain.core_services.get_site_config", return_value={}), patch(
        "src.web.api_kol.build_etf_overview_payload", return_value=payload
    ) as provider:
        yield app.test_client(), user, provider


def test_dav_reads_complete_catalog_without_fan_display_filter(etf_source_client):
    client, _, provider = etf_source_client
    response = client.get("/api/tenant/laowang/etf-data-source")
    assert response.status_code == 200
    assert len(response.get_json()["items"]) == 2
    assert response.get_json()["items"][1]["price"] is None
    provider.assert_called_once_with()


@pytest.mark.parametrize("role,tenant,error", [
    ("investor", "laowang", "dav_required"),
    ("dav", "another-dav", "tenant_scope_forbidden"),
])
def test_unauthorized_read_does_not_call_provider(etf_source_client, role, tenant, error):
    client, user, provider = etf_source_client
    user["role"] = role
    response = client.get(f"/api/tenant/{tenant}/etf-data-source")
    assert response.status_code == 403
    assert response.get_json()["error"] == error
    provider.assert_not_called()


def test_admin_can_read_catalog(etf_source_client):
    client, user, provider = etf_source_client
    user["role"] = "admin"
    response = client.get("/api/tenant/another-dav/etf-data-source")
    assert response.status_code == 200
    provider.assert_called_once_with()


def test_provider_failure_returns_retryable_error(etf_source_client):
    client, _, provider = etf_source_client
    provider.side_effect = RuntimeError("provider unavailable")
    response = client.get("/api/tenant/laowang/etf-data-source")
    assert response.status_code == 502
    assert response.get_json() == {"ok": False, "error": "etf_data_source_failed"}
