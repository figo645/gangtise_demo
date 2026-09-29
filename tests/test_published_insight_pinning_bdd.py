import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_entry
import src.web.api_kol as api_kol
import src.web.hooks as web_hooks
from src.domain import core_services


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _PinDb:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((str(sql), tuple(params or ())))
        if str(sql).lstrip().upper().startswith("UPDATE"):
            pinned = bool((params or (False,))[0])
            return _Cursor(row={
                "insight_id": "insight-1",
                "dav_id": "dav-1",
                "external_id": "",
                "title": "市场观察",
                "content_text": "正文",
                "content_html": "",
                "access_mode": "public",
                "source_mode": "manual",
                "published_date": "2025-11-01",
                "published_at": "2025-11-01 09:00:00",
                "imported_at": "2026-09-29 09:00:00+08:00",
                "view_count": 0,
                "is_pinned": pinned,
                "pinned_at": "2026-09-29 09:00:00+08:00" if pinned else None,
                "payload_json": {},
            })
        return _Cursor(rows=[])

    def commit(self):
        pass


class PublishedInsightPinningBddTest(unittest.TestCase):
    def test_new_migration_defaults_new_insights_to_unpinned_and_indexes_editorial_order(self):
        sql = (PROJECT_ROOT / "sql/postgres/146_tenant_published_insight_pinning.sql").read_text(encoding="utf-8")
        self.assertIn("is_pinned BOOLEAN NOT NULL DEFAULT FALSE", sql)
        self.assertIn("pinned_at TIMESTAMPTZ", sql)
        self.assertIn("is_pinned DESC", sql)

    def test_pin_service_changes_only_explicit_pin_state_and_keeps_published_date(self):
        db = _PinDb()
        tenant = {"slug": "dav", "advisor": "财经老王"}
        with patch.object(core_services, "get_tenant_by_slug", return_value=tenant), patch.object(core_services, "get_db", return_value=db), patch.object(
            core_services, "list_tenant_published_insights", return_value=[]
        ):
            result = core_services.set_tenant_published_insight_pin("dav", "insight-1", True)

        self.assertTrue(result["pinned"])
        self.assertEqual(result["snapshot"]["published_date"], "2025-11-01")
        self.assertIn("SET is_pinned = ?", db.calls[0][0])
        self.assertIn("published_date", db.calls[0][0])

    def test_pin_endpoint_requires_dav_and_has_one_shared_h5_web_route(self):
        client = app_entry.app.test_client()
        with patch.object(api_kol, "get_current_authenticated_user", return_value={"role": "investor", "tenant_slug": "dav"}), patch.object(
            web_hooks, "is_authenticated", return_value=True
        ), patch.object(web_hooks, "get_current_authenticated_user", return_value={"role": "investor", "tenant_slug": "dav"}):
            denied = client.post("/api/tenant/dav/reviews/insight-1/pin", json={"pinned": True})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.get_json()["error"], "dav_required")

        h5 = (PROJECT_ROOT / "templates/h5.html").read_text(encoding="utf-8")
        web = (PROJECT_ROOT / "templates/kol_workbench.html").read_text(encoding="utf-8")
        self.assertIn("/reviews/${encodeURIComponent(reviewId)}/pin", h5)
        self.assertIn("/reviews/${encodeURIComponent(normalizedReviewId)}/pin", web)
        self.assertIn("togglePublishedReviewPin", h5)
        self.assertIn("kwTogglePublishedReviewPin", web)


if __name__ == "__main__":
    unittest.main()
