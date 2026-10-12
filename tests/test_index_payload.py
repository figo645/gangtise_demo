import json
import re

import app as app_entry
import src.web.pages as pages


def test_index_embeds_only_theme_bootstrap_config(monkeypatch):
    large_private_value = "x" * 1_000_000
    site_config = {
        "brand": {"name": "Test", "short_name": "Test"},
        "default_theme": "dark",
        "default_accent": "green",
        "default_tenant_slug": "test",
        "feature_flags": {"tenant_portal": False},
        "tenants": [{"slug": "test", "name": "Test", "logo_mark": "T"}],
        "review_generation": {"private_prompt": large_private_value},
    }
    monkeypatch.setattr(pages, "get_site_config", lambda: site_config)

    response = app_entry.app.test_client().get("/")
    html = response.get_data(as_text=True)
    match = re.search(r"window\.SITE_CONFIG\s*=\s*(\{.*?\});", html)

    assert response.status_code == 200
    assert match is not None
    assert json.loads(match.group(1)) == {
        "default_accent": "green",
        "default_theme": "dark",
    }
    assert large_private_value not in html
    assert len(response.data) < 250_000
