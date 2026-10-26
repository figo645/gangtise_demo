import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_entry
import src.web.api_core as api_core
import src.web.api_kol as api_kol
import src.web.hooks as web_hooks
from src.domain import ai_services, core_services, market_services
from src.runtime import app


class StockInsightGridBddTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True)
        cls.original_authenticated = web_hooks.is_authenticated
        cls.original_hook_user = web_hooks.get_current_authenticated_user
        cls.original_api_user = api_kol.get_current_authenticated_user
        cls.user = {"id": "dav-1", "username": "财经老王", "role": "dav", "tenant_slug": "laowang"}
        web_hooks.is_authenticated = lambda: True
        web_hooks.get_current_authenticated_user = lambda: cls.user
        api_kol.get_current_authenticated_user = lambda: cls.user
        cls.client = app.test_client()
        cls.context = app.app_context()
        cls.context.push()

    @classmethod
    def tearDownClass(cls):
        web_hooks.is_authenticated = cls.original_authenticated
        web_hooks.get_current_authenticated_user = cls.original_hook_user
        api_kol.get_current_authenticated_user = cls.original_api_user
        cls.context.pop()

    def test_stock_grid_builds_real_cards_without_automatic_summary(self):
        selected = [{
            "code": "600519",
            "name": "贵州茅台",
            "market": "SH",
            "industry": "白酒",
            "price": 1255.79,
            "change_pct": -0.22,
            "security_code": "600519.SH",
        }]
        with patch.object(market_services, "call_gangtise_stock_summaries") as call:
            result = market_services.build_gangtise_stock_insight_grid(selected)
        call.assert_not_called()
        self.assertEqual(result["cards"][0]["summary"], "")
        self.assertEqual(result["cards"][0]["summary_mode"], "empty")
        self.assertEqual(result["endpoint"], "")

    def test_missing_gangtise_summary_is_not_fabricated(self):
        with patch.object(market_services, "call_gangtise_stock_summaries", return_value={"items": []}), patch.object(market_services, "get_watchlist_detail_by_code", return_value=None):
            result = market_services.build_gangtise_stock_insight_grid([{"code": "600519", "name": "贵州茅台", "security_code": "600519.SH"}])
        self.assertEqual(result["cards"][0]["summary"], "")

    def test_each_card_defaults_to_empty_and_uses_only_manual_reasons(self):
        selected = [
            {"code": "600519", "name": "贵州茅台", "security_code": "600519.SH", "price": 1255.79, "change_pct": 1.2, "summary_mode": "manual", "recommendation_reason": "品牌力稳健，适合继续观察需求修复。"},
            {"code": "601939", "name": "建设银行", "security_code": "601939.SH", "price": 8.12, "change_pct": -0.4, "summary_mode": "empty"},
            {"code": "00700", "name": "腾讯控股", "security_code": "00700.HK", "price": 388.4, "change_pct": 1.46, "summary_mode": "gangtise"},
        ]
        with patch.object(market_services, "call_gangtise_stock_summaries") as call:
            result = market_services.build_gangtise_stock_insight_grid(selected)
        call.assert_not_called()
        self.assertEqual(result["cards"][0]["summary"], "品牌力稳健，适合继续观察需求修复。")
        self.assertEqual(result["cards"][0]["summary_mode"], "manual")
        self.assertEqual(result["cards"][1]["summary"], "")
        self.assertEqual(result["cards"][1]["summary_mode"], "empty")
        self.assertEqual(result["cards"][2]["summary"], "")
        self.assertEqual(result["cards"][2]["summary_mode"], "empty")
        self.assertEqual(result["cards"][2]["price"], 388.4)

    def test_preview_route_accepts_any_canonical_security_not_in_tenant_watchlist(self):
        grid = {"cards": [{"stock_code": "600519", "stock_name": "贵州茅台", "summary": "真实简评"}], "provider": "Gangtise 个股看点摘要", "endpoint": "/application/open-ai/stock-summary/getList"}
        canonical = {"code": "600519", "name": "贵州茅台", "market": "SH", "security_code": "600519.SH", "industry": "白酒"}
        with patch.object(api_kol, "resolve_watchlist_candidate", return_value=canonical), patch.object(api_kol, "build_gangtise_stock_insight_grid", return_value=grid) as build:
            response = self.client.post("/api/review/stock-grid-preview", json={"tenant_slug": "laowang", "selected_watchlist": [canonical]})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        build.assert_called_once()
        self.assertEqual(build.call_args.args[0][0]["summary_mode"], "empty")

    def test_preview_route_preserves_manual_and_empty_summary_modes(self):
        selections = [
            {"code": "600519", "name": "贵州茅台", "market": "SH", "security_code": "600519.SH", "summary_mode": "manual", "recommendation_reason": "观察需求修复。"},
            {"code": "601939", "name": "建设银行", "market": "SH", "security_code": "601939.SH", "summary_mode": "empty"},
        ]
        grid = {"cards": [], "provider": "用户自定义个股简述", "endpoint": ""}
        with patch.object(api_kol, "resolve_watchlist_candidate", side_effect=lambda stock_code="", stock_name="": next(item for item in selections if item["code"] in stock_code)), patch.object(api_kol, "build_gangtise_stock_insight_grid", return_value=grid) as build:
            response = self.client.post("/api/review/stock-grid-preview", json={"tenant_slug": "laowang", "selected_watchlist": selections})
        self.assertEqual(response.status_code, 200)
        passed = build.call_args.args[0]
        self.assertEqual([item["summary_mode"] for item in passed], ["manual", "empty"])
        self.assertEqual(passed[0]["recommendation_reason"], "观察需求修复。")

    def test_preview_route_rejects_unknown_security(self):
        with patch.object(api_kol, "resolve_watchlist_candidate", return_value=None):
            response = self.client.post("/api/review/stock-grid-preview", json={"tenant_slug": "laowang", "selected_watchlist": ["NOT-A-SECURITY"]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "stock_grid_security_not_found")

    def test_preview_route_rejects_more_than_nine(self):
        with patch.object(api_kol, "get_current_authenticated_user", return_value=self.user):
            response = self.client.post("/api/review/stock-grid-preview", json={"tenant_slug": "laowang", "selected_watchlist": [str(index) for index in range(10)]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "stock_grid_max_nine")

    def test_preview_route_exposes_retryable_upstream_failure(self):
        canonical = {"code": "600519", "name": "贵州茅台", "market": "SH", "security_code": "600519.SH"}
        with patch.object(api_kol, "resolve_watchlist_candidate", return_value=canonical), patch.object(
            api_kol,
            "build_gangtise_stock_insight_grid",
            side_effect=RuntimeError("gangtise_stock_summary_failed:http_status=503:upstream unavailable"),
        ):
            response = self.client.post("/api/review/stock-grid-preview", json={"tenant_slug": "laowang", "selected_watchlist": [canonical]})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "stock_grid_upstream_unavailable")
        self.assertTrue(response.get_json()["retryable"])

    def test_snapshot_normalization_keeps_grid_as_optional_insight_content(self):
        tenant = {"slug": "laowang", "advisor": "财经老王"}
        normalized = core_services.normalize_review_snapshot_item({"source_mode": "manual", "title": "今日点评", "content_text": "今日个股点评", "stock_grid_enabled": True, "stock_grid_cards": [{"stock_code": "600519", "summary": "观察需求"}]}, tenant)
        self.assertEqual(normalized["content_kind"], "insight")
        self.assertTrue(normalized["stock_grid_enabled"])
        self.assertEqual(normalized["stock_grid_cards"][0]["stock_code"], "600519")

    def test_grid_draft_without_text_is_rejected_because_it_is_an_insight_addon(self):
        tenant = {"slug": "laowang", "advisor": "财经老王"}
        with self.assertRaisesRegex(ValueError, "insight_draft_content_required"):
            core_services._normalize_insight_draft_item({
                "source_mode": "manual",
                "title": "今日个股点评",
                "content_text": "",
                "metadata": {"stock_grid_enabled": True, "stock_grid_cards": [{"stock_code": "600519", "stock_name": "贵州茅台"}]},
            }, tenant)

    def test_published_directory_row_restores_grid_metadata_from_payload(self):
        tenant = {"slug": "laowang", "advisor": "财经老王"}
        normalized = core_services._published_insight_row_to_snapshot({
            "insight_id": "grid-1",
            "title": "今日个股点评",
            "content_text": "今日个股点评",
            "content_html": "",
            "access_mode": "public",
            "source_mode": "stock_grid",
            "published_date": "2026-10-14",
            "published_at": "2026-10-14 09:00:00",
            "view_count": 0,
            "payload_json": {
                "content_kind": "insight",
                "stock_grid_enabled": True,
                "stock_grid_cards": [{"stock_code": "600519", "stock_name": "贵州茅台", "summary": "观察需求。"}],
            },
        }, tenant)
        self.assertEqual(normalized["content_kind"], "insight")
        self.assertTrue(normalized["stock_grid_enabled"])
        self.assertEqual(normalized["stock_grid_cards"][0]["stock_name"], "贵州茅台")

    def test_publish_contract_returns_one_insight_with_optional_grid_cards(self):
        snapshot = {
            "id": "laowang-review-grid-1",
            "title": "今日个股点评",
            "content_kind": "insight",
            "stock_grid_enabled": True,
            "source_mode": "manual",
            "stock_grid_cards": [{"stock_code": "600519", "stock_name": "贵州茅台", "summary": "观察需求修复。"}],
        }
        with patch.object(
            api_core,
            "persist_review_publish_snapshot",
            return_value={"snapshot": snapshot, "snapshots": [snapshot], "message_center_state": {}},
        ) as persist:
            response = self.client.post(
                "/api/review/publish",
                json={
                    "tenant_slug": "laowang",
                    "review_title": "今日个股点评",
                    "text": "今日个股点评",
                    "source_mode": "manual",
                    "stock_grid_enabled": True,
                    "stock_grid_cards": snapshot["stock_grid_cards"],
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["snapshot"]["content_kind"], "insight")
        self.assertTrue(payload["snapshot"]["stock_grid_enabled"])
        self.assertEqual(payload["snapshots"][0]["stock_grid_cards"][0]["stock_code"], "600519")
        self.assertEqual(persist.call_args.kwargs["source_mode"], "manual")
        self.assertEqual(persist.call_args.kwargs["stock_grid_cards"][0]["stock_code"], "600519")

    def test_normal_source_mode_contract_remains_unchanged(self):
        self.assertEqual(api_kol._validate_review_source_mode("manual"), "manual")
        self.assertEqual(api_kol._validate_review_source_mode("stock_grid"), "manual")

    def test_h5_and_workbench_share_the_same_grid_authoring_contract(self):
        root = Path(__file__).resolve().parents[1]
        h5 = (root / "templates/h5.html").read_text(encoding="utf-8")
        workbench = (root / "templates/kol_workbench.html").read_text(encoding="utf-8")
        for source in (h5, workbench):
            self.assertIn("stockGridEnabled", source)
            if source is workbench:
                self.assertIn("kwRenderStockGridAppendix", source)
            self.assertIn('在这篇洞见末尾加入九宫格股票赏析', source)
            self.assertIn('供稿方式', source)
            self.assertIn("/api/watchlist/search", source)
            self.assertIn("summary_mode", source)
            self.assertIn("recommendation_reason", source)
            self.assertIn("change_pct", source)
            self.assertIn("填写理由", source)
            self.assertIn("已填写", source)
            self.assertNotIn("stock-grid-mode-tag", source)
            self.assertNotIn("stock-grid-mode-tags", source)
            self.assertNotIn("setReviewStockGridSummaryMode", source)
        h5_app = (root / "static/js/h5-app.js").read_text(encoding="utf-8")
        self.assertIn('stockGridEnabled ? renderReviewStockGridSection(article)', h5_app)
        self.assertIn('含九宫格个股赏析', h5_app)
        self.assertIn('function renderReviewWatchlistSelectionPanel()', h5_app)
        self.assertIn('/api/review/stock-grid-preview', h5_app)
        self.assertIn('stock_grid_selection: reviewTriggerDraft.selectedWatchlist || []', h5_app)
        self.assertIn('const draftMetadata = draft.metadata && typeof draft.metadata === \'object\' ? draft.metadata : {};', h5_app)
        self.assertIn('function renderReviewStockGridSection(article)', h5_app)
        self.assertIn('loadReviewDirectoryPage({force: true})', h5_app)
        self.assertIn('stock_grid_enabled: Boolean(reviewTriggerDraft.stockGridEnabled)', h5_app)
        self.assertIn('kwLoadPublishedReviewPage({force: true})', workbench)
        self.assertIn('含九宫格个股赏析', workbench)

    def test_web_workbench_mounts_the_grid_authoring_surface(self):
        response = self.client.get('/kol-workbench?tenant=laowang')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="workbench-section-review"', html)
        self.assertIn('id="kw-review-input-mode-row"', html)
        self.assertIn('在这篇洞见末尾加入九宫格股票赏析', html)
        self.assertIn('function kwRenderReviewInputPanel()', html)
        self.assertIn('function kwRequestStockGridPreview()', html)
        self.assertIn('发布新洞见', html)


if __name__ == "__main__":
    unittest.main()
