import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_entry
import src.web.api_kol as api_kol
import src.web.hooks as web_hooks
from src.domain import core_services


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self, one=None, rows=None):
        self._one = one or {}
        self._rows = rows or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows


class _PublishedInsightDb:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((str(sql), tuple(params or ())))
        if "COUNT(*) AS total" in str(sql):
            return _Cursor(one={"total": 201})
        offset = int((params or ())[-1])
        if offset == 200:
            rows = [{
                "insight_id": "insight-historical-201",
                "dav_id": "tenant_dav",
                "external_id": "",
                "title": "2025 年历史市场观察",
                "content_text": "仅用于确认第 201 篇仍可读取。",
                "content_html": "",
                "access_mode": "public",
                "source_mode": "open_api",
                "published_date": "2025-11-04",
                "published_at": "2025-11-04 09:00:00",
                "imported_at": "2026-09-24 09:00:00+08:00",
                "view_count": 0,
                "payload_json": {"tags": ["历史"], "is_simulated": False},
            }]
        else:
            rows = []
        return _Cursor(rows=rows)


class PublishedInsightDirectoryBddTest(unittest.TestCase):
    def test_given_more_than_two_hundred_insights_when_loading_a_later_page_then_historical_content_is_returned(self):
        db = _PublishedInsightDb()
        tenant = {"slug": "dav", "advisor": "财经老王", "name": "老王投研"}
        with patch.object(core_services, "get_tenant_by_slug", return_value=tenant), patch.object(core_services, "get_db", return_value=db):
            page = core_services.list_tenant_published_insights_page("dav", limit=30, offset=200, query="历史")

        self.assertEqual(page["total"], 201)
        self.assertEqual(page["items"][0]["id"], "insight-historical-201")
        self.assertEqual(page["items"][0]["published_date"], "2025-11-04")
        self.assertFalse(page["has_more"])
        sql = "\n".join(call[0] for call in db.calls)
        self.assertIn("payload_json::text ILIKE ?", sql)
        self.assertIn("LIMIT ? OFFSET ?", sql)

    def test_given_directory_request_when_keyword_and_alias_are_sent_then_api_uses_the_paginated_tenant_reader(self):
        tenant = {"slug": "dav", "advisor": "财经老王", "name": "老王投研"}
        page = {"items": [{"id": "old-article", "title": "历史洞见"}], "total": 201, "offset": 200, "limit": 30, "has_more": False, "next_offset": None}
        with patch.object(api_kol, "get_tenant_by_slug", return_value=tenant), patch.object(
            api_kol, "list_tenant_published_insights_page", return_value=page
        ) as list_page, patch.object(api_kol, "protect_tenant_review_snapshots", side_effect=lambda _slug, items, _viewer: items), patch.object(
            api_kol, "fan_can_view_paid_content", return_value=False
        ), patch.object(
            api_kol, "get_current_authenticated_user", return_value={"role": "investor", "tenant_slug": "dav"}
        ), patch.object(web_hooks, "is_authenticated", return_value=True), patch.object(
            web_hooks, "get_current_authenticated_user", return_value={"role": "investor", "tenant_slug": "dav"}
        ):
            response = app_entry.app.test_client().get("/api/tenant/dav/published-insights?limit=30&offset=200&q=历史&alias=600519")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total"], 201)
        self.assertEqual(response.get_json()["items"][0]["id"], "old-article")
        self.assertEqual(list_page.call_args.kwargs["query"], "历史")
        self.assertEqual(list_page.call_args.kwargs["search_terms"], ["600519"])

    def test_given_non_subscriber_search_when_building_the_query_then_paid_bodies_are_not_searchable(self):
        where_sql, params = core_services._tenant_published_insights_query_parts(
            "dav", query="仅正文关键字", search_paid_content=False
        )

        self.assertIn("access_mode <> 'subscriber'", where_sql)
        self.assertIn("payload_json -> 'tags'", where_sql)
        self.assertEqual(len(params), 7)

    def test_given_h5_and_web_directories_when_rendered_then_both_use_the_server_paged_endpoint(self):
        h5_source = (PROJECT_ROOT / "templates/h5.html").read_text(encoding="utf-8")
        workbench_source = (PROJECT_ROOT / "templates/kol_workbench.html").read_text(encoding="utf-8")

        self.assertIn("/published-insights?${params.toString()}", h5_source)
        self.assertIn("function loadMoreReviewDirectory()", h5_source)
        self.assertIn("正在查询全部历史洞见", h5_source)
        self.assertIn("/published-insights?${params.toString()}", workbench_source)
        self.assertIn("function kwLoadMorePublishedReviews()", workbench_source)


if __name__ == "__main__":
    unittest.main()
