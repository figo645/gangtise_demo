import os
import unittest
from unittest.mock import patch

import app as app_entry
import src.web.hooks as web_hooks
from src.services import get_tenant_configs


def _tenant_slugs():
    try:
        tenants = get_tenant_configs()
    except Exception:
        return ["lisa"]
    slugs = [str(item.get("slug") or "").strip() for item in tenants if str(item.get("slug") or "").strip()]
    return slugs or ["lisa"]


class RouteSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._original_is_authenticated = web_hooks.is_authenticated
        web_hooks.is_authenticated = lambda: True
        app_entry.app.config.update(TESTING=True)
        cls.client = app_entry.app.test_client()
        cls.tenant_slugs = _tenant_slugs()

    @classmethod
    def tearDownClass(cls):
        web_hooks.is_authenticated = cls._original_is_authenticated

    def test_h5_pages_render(self):
        for tenant_slug in self.tenant_slugs:
            with self.subTest(route="/h5", tenant=tenant_slug):
                response = self.client.get(f"/h5?tenant={tenant_slug}")
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.content_type)
                self.assertIn("Hermes", response.get_data(as_text=True))

    def test_h5_market_has_overview_and_watchlist_tabs(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slugs[0]}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="market-overview-tab"', html)
        self.assertIn('id="market-sector-tab"', html)
        self.assertIn('id="market-watchlist-tab"', html)
        self.assertIn('id="market-overview-list"', html)
        self.assertIn('id="market-sector-list"', html)
        self.assertIn("switchMarketView('overview')", html)
        self.assertIn("switchMarketView('sectors')", html)
        self.assertIn("switchMarketView('watchlist')", html)
        self.assertLess(html.index('id="market-watchlist-tab"'), html.index('id="market-sector-tab"'))
        self.assertLess(html.index('id="market-sector-tab"'), html.index('id="market-overview-tab"'))
        self.assertIn("renderColumn('涨幅', gains", html)
        self.assertIn("renderColumn('跌幅', losses", html)
        self.assertIn("candleLabel: `${data.name || '标的'} 日K线`", html)
        self.assertIn("data.annotation_key || data.indicator_code || data.code", html)

    def test_h5_core_market_index_cards_use_the_unified_market_detail(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slugs[0]}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("STANDARD_MARKET_INDEX_INDICATOR_CODES", html)
        self.assertIn("openWatchlistDetail(indicatorCode, 'overview');", html)
        self.assertIn("'source_shanghai_index'", html)
        self.assertIn("'source_shenzhen_index'", html)

    def test_dav_profile_does_not_offer_account_switching(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slugs[0]}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("const canSwitch = role === 'admin';", html)
        self.assertNotIn("const canSwitch = role === 'dav' || role === 'admin';", html)

    def test_dav_profile_hides_account_overview(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slugs[0]}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("el('profile-overview-card').style.display = user.role === 'dav' ? 'none' : ''", html)

    def test_h5_market_research_guide_is_only_rendered_for_dav_users(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slugs[0]}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="market-dav-research-guide"', html)
        self.assertIn('function renderMarketDavResearchGuide(user)', html)
        self.assertIn("guide.style.display = user && user.role === 'dav' ? '' : 'none';", html)
        self.assertIn('大V研究节奏', html)
        self.assertIn('在日 K 线上记录关键判断', html)
        self.assertNotIn('建议使用路径', html)

    def test_market_overview_returns_standard_index_rows_without_fake_values(self):
        from src.domain import market_services

        expected_names = ("上证指数", "深证指数", "恒生指数", "国企指数", "红筹指数", "道琼斯", "纳斯达克", "标普500", "日经225")
        registered_names = tuple(market_services.GANGTISE_INDICATOR_REGISTRY[code]["indicator_name"] for code in market_services.MARKET_OVERVIEW_INDEX_CODES)
        self.assertEqual(registered_names, expected_names)

        rows = [
            {"indicator_code": code, "name": code, "code": "000001.SH", "available": False, "message": "暂无真实行情数据"}
            for code in market_services.MARKET_OVERVIEW_INDEX_CODES
        ]
        with patch("src.web.api_core.build_market_overview_payload", return_value={"ok": True, "items": rows, "source": "AKShare"}):
            response = self.client.get("/api/market-overview")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload["items"]), 9)
        self.assertTrue(all("available" in item for item in payload["items"]))
        self.assertTrue(all(item["available"] is False or item.get("price") is not None for item in payload["items"]))

    def test_market_overview_reads_persisted_snapshot_without_provider_call(self):
        from src.domain import market_services
        snapshot = {"ok": True, "snapshot_version": 3, "source": "AKShare", "items": [{"indicator_code": "source_shanghai_index", "name": "上证指数", "price": 3500.2, "available": True}]}
        with patch.object(market_services, "_load_watchlist_cache", return_value=snapshot), patch.object(market_services, "_load_akshare", side_effect=AssertionError("H5 must not call AkShare")):
            payload = market_services.build_market_overview_payload()

        self.assertEqual(payload, snapshot)

    def test_market_overview_does_not_use_the_legacy_gangtise_indicator_lake(self):
        from src.domain import market_services

        with patch.dict(os.environ, {"MARKET_DEMO_DATA_ENABLED": "0"}), patch.object(market_services, "load_real_indicator_series_map", side_effect=AssertionError("legacy Gangtise lake must not be read")), patch.object(
            market_services, "_load_watchlist_cache", return_value=None
        ):
            payload = market_services.build_market_overview_payload()

        self.assertEqual(payload["source"], "AKShare")
        self.assertEqual(payload["items"], [])

    def test_fundamental_boards_use_the_same_industry_names_as_hot_industries(self):
        from src.domain import market_services

        boards = market_services.gen_feed_boards_from_watchlist_details({
            "600519": {"code": "600519", "name": "贵州茅台", "industry": "高端白酒"},
            "300750": {"code": "300750", "name": "宁德时代", "industry": "动力电池"},
            "688981": {"code": "688981", "name": "中芯国际", "industry": "半导体制造"},
            "00700": {"code": "00700", "name": "腾讯控股", "industry": "港股互联网"},
        })

        self.assertEqual([board["name"] for board in boards], ["食品饮料", "电力设备", "电子", "传媒"])

    def test_watchlist_cards_use_the_same_industry_names_as_hot_industries(self):
        from src.domain import market_services

        signal_bundle = {
            "board_alert_level": "normal",
            "board_alert_text": "当前无明显预警",
            "board_summary": "当前无明显预警",
            "anomaly_text": "",
            "related_indicator_ids": [],
            "related_indicator_names": [],
            "metrics": [],
            "thesis": [],
        }
        with patch.object(market_services, "build_watchlist_indicator_context", return_value={}), patch.object(
            market_services, "build_watchlist_signal_bundle", return_value=signal_bundle
        ):
            details = market_services._enrich_watchlist_details({
                "600519": {"code": "600519", "name": "贵州茅台", "industry": "高端白酒", "focus": "高端白酒"},
                "300750": {"code": "300750", "name": "宁德时代", "industry": "动力电池", "focus": "动力电池"},
                "688981": {"code": "688981", "name": "中芯国际", "industry": "半导体制造", "focus": "半导体制造"},
            })

        self.assertEqual(details["600519"]["industry"], "食品饮料")
        self.assertEqual(details["300750"]["focus"], "电力设备")
        self.assertEqual(details["688981"]["industry"], "电子")

    def test_market_snapshot_collects_akshare_index_and_industry_data(self):
        from src.domain import market_services

        def index_series(code, start_date, end_date, ak, global_symbols):
            return {"ok": True, "provider": "AKShare", "points": [{"date": "2026-08-09", "open": 99, "high": 101, "low": 98, "close": 100}, {"date": "2026-08-10", "open": 100, "high": 102, "low": 99, "close": 101}], "message": ""}

        sector_rows = [{"sector": name, "code": f"THS-{name}", "value": 100, "change": 1, "change_pct": 1, "updated_at": "2026-08-10", "data_source": "AKShare 同花顺行业汇总"} for name in market_services.SHENWAN_LEVEL1_INDUSTRIES]

        with patch.object(market_services, "_load_akshare", return_value=object()), patch.object(market_services, "_akshare_global_index_symbols", return_value={}), patch.object(market_services, "fetch_gangtise_market_index_history", side_effect=AssertionError("market snapshots must use only AKShare")) as gangtise_fetch, patch.object(market_services, "fetch_akshare_market_index_history", side_effect=index_series) as index_fetch, patch.object(market_services, "fetch_gangtise_intraday_series", side_effect=AssertionError("market snapshots must use only AKShare")) as gangtise_intraday, patch.object(market_services, "fetch_akshare_market_index_intraday", return_value={"available": True, "points": [{"date": "2026-08-10 09:31:00", "value": 100.0}]}) as intraday_fetch, patch.object(market_services, "_fetch_akshare_sector_overview", return_value=sector_rows) as sector_fetch, patch.object(market_services, "_save_watchlist_cache") as save_cache:
            result = market_services.sync_market_snapshot(force=True)

        self.assertEqual(gangtise_fetch.call_count, 0)
        self.assertEqual(index_fetch.call_count, 9)
        self.assertEqual(gangtise_intraday.call_count, 0)
        self.assertEqual(intraday_fetch.call_count, 9)
        self.assertEqual(sector_fetch.call_count, 1)
        self.assertEqual(result["overview_count"], 9)
        self.assertEqual(result["sector_count"], len(market_services.SHENWAN_LEVEL1_INDUSTRIES))
        self.assertEqual(result["intraday_count"], 9)
        self.assertEqual(save_cache.call_count, 20)

    def test_market_snapshot_keeps_last_akshare_index_when_sync_fails(self):
        from src.domain import market_services

        previous = {
            "ok": True, "snapshot_version": 5, "source": "AKShare",
            "items": [{
                "indicator_code": "source_hsi", "name": "恒生指数", "code": "HSI",
                "market": "HK", "price": 24500.0, "change": 120.0,
                "change_pct": 0.49, "updated_at": "2026-08-08", "available": True,
                "data_source": "AKShare",
            }],
        }
        unavailable = {"ok": False, "points": [], "message": "upstream_unavailable", "provider": "AKShare"}
        with patch.object(market_services, "_load_akshare", return_value=object()), patch.object(
            market_services, "_akshare_global_index_symbols", return_value={}
        ), patch.object(market_services, "_load_watchlist_cache", side_effect=[previous, None]), patch.object(
            market_services, "fetch_akshare_market_index_history", return_value=unavailable
        ), patch.object(market_services, "_fetch_akshare_sector_overview", return_value=[]), patch.object(
            market_services, "_save_watchlist_cache"
        ) as save_cache:
            result = market_services.sync_market_snapshot(force=True)

        overview_payload = next(call.args[2] for call in save_cache.call_args_list if call.args[:2] == ("market_overview", "standard_indices"))
        hsi = next(item for item in overview_payload["items"] if item["indicator_code"] == "source_hsi")
        self.assertTrue(result["overview_count"])
        self.assertTrue(hsi["available"])
        self.assertTrue(hsi["stale"])
        self.assertEqual(hsi["price"], 24500.0)

    def test_market_sector_sync_continues_when_akshare_is_unavailable(self):
        from src.domain import market_services

        sector_rows = [{"sector": name, "code": f"THS-{name}", "value": 100, "change": 1, "change_pct": 1, "updated_at": "2026-08-10", "data_source": "AKShare 同花顺行业汇总"} for name in market_services.SHENWAN_LEVEL1_INDUSTRIES]
        with patch.object(market_services, "_load_akshare", side_effect=RuntimeError("AKShare unavailable")), patch.object(
            market_services, "_fetch_akshare_sector_overview", return_value=sector_rows
        ) as sector_fetch, patch.object(market_services, "_save_watchlist_cache"):
            result = market_services.sync_market_snapshot(force=True)

        self.assertEqual(result["overview_count"], 0)
        self.assertEqual(result["sector_count"], len(market_services.SHENWAN_LEVEL1_INDUSTRIES))
        self.assertEqual(sector_fetch.call_count, 1)

    def test_market_sector_uses_akshare_industry_summary(self):
        from src.domain import market_services

        fallback_rows = [{"sector": "食品饮料", "code": "BK0477", "value": 9100.0, "change": 20.0, "change_pct": 0.22, "updated_at": "2026-08-10 10:00:00", "data_source": "AKShare 行业板块"}]
        with patch.object(market_services, "_load_akshare", return_value=object()), patch.object(
            market_services, "_akshare_global_index_symbols", return_value={}
        ), patch.object(market_services, "fetch_akshare_market_index_history", return_value={"ok": False, "points": [], "message": "unavailable"}), patch.object(
            market_services, "_fetch_akshare_sector_overview", return_value=fallback_rows
        ), patch.object(
            market_services, "_save_watchlist_cache"
        ) as save_cache:
            result = market_services.sync_market_snapshot(force=True)

        self.assertEqual(result["sector_count"], 1)
        sector_payload = next(call.args[2] for call in save_cache.call_args_list if call.args[:2] == ("market_sector_overview", "shenwan_level1"))
        self.assertEqual(sector_payload["source"], "AKShare")
        self.assertEqual(sector_payload["snapshot_version"], 5)

    def test_h5_does_not_expose_market_snapshot_refresh_to_frontend_users(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slugs[0]}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn('onclick="refreshMarketSnapshot()"', html)
        self.assertIn('后台 AKShare 采集后入库', html)

    def test_akshare_index_snapshot_uses_real_daily_values(self):
        from src.domain import market_services

        result = {"provider": "AKShare", "points": [{"date": "2026-08-07", "open": 3500.0, "high": 3515.0, "low": 3490.0, "close": 3510.0}, {"date": "2026-08-10", "open": 3512.0, "high": 3530.0, "low": 3505.0, "close": 3520.0}]}
        shanghai = market_services._build_market_index_snapshot_item("source_shanghai_index", result)
        shenzhen = market_services._build_market_index_snapshot_item("source_shenzhen_index", result)

        self.assertEqual(shanghai["data_source"], "AKShare")
        self.assertEqual(shanghai["price"], 3520.0)
        self.assertEqual(shenzhen["code"], "399001.SZ")

    def test_market_index_detail_reads_the_persisted_akshare_snapshot(self):
        from src.domain import market_services

        history = {"provider": "AKShare", "points": [{"date": "2026-08-07", "open": 3500.0, "high": 3515.0, "low": 3490.0, "close": 3510.0}, {"date": "2026-08-10", "open": 3512.0, "high": 3530.0, "low": 3505.0, "close": 3520.0}]}
        with patch.object(market_services, "_load_watchlist_cache", return_value=history), patch.object(market_services, "build_live_gangtise_indicator_detail", side_effect=AssertionError("detail must not fall back to Gangtise")):
            detail = market_services.build_watchlist_indicator_detail("source_shanghai_index")

        self.assertEqual(detail["data_source"], "AKShare")
        self.assertEqual(detail["price"], 3520.0)

    def test_market_sector_reads_persisted_snapshot_without_provider_call(self):
        from src.domain import market_services
        snapshot = {"ok": True, "snapshot_version": 5, "source": "AKShare", "items": [{"sector": "银行", "value": 1020, "change_pct": 2.0}]}
        with patch.object(market_services, "_load_watchlist_cache", return_value=snapshot), patch.object(market_services, "_load_akshare", side_effect=AssertionError("H5 must not call AkShare")):
            payload = market_services.build_market_sector_overview_payload()

        self.assertEqual(payload, snapshot)

    def test_market_sector_rejects_legacy_gangtise_snapshot(self):
        from src.domain import market_services

        legacy_snapshot = {
            "ok": True,
            "source": "Gangtise OpenAPI EDB",
            "items": [{"sector": "食品饮料", "value": 1888.0, "change_pct": 1.25}],
        }
        with patch.object(market_services, "_load_watchlist_cache", return_value=legacy_snapshot), patch.object(
            market_services, "_save_watchlist_cache"
        ) as save_cache:
            payload = market_services.build_market_sector_overview_payload()

        self.assertNotEqual(payload["items"], legacy_snapshot["items"])
        self.assertEqual(payload["items"], [])
        self.assertTrue(payload["refreshing"])
        save_cache.assert_not_called()

    def test_market_sector_rejects_legacy_non_gangtise_snapshot(self):
        from src.domain import market_services

        legacy_snapshot = {
            "ok": True,
            "source": "AKShare",
            "items": [{"sector": "食品饮料", "value": 1888.0, "change_pct": 1.25}],
        }
        with patch.dict(os.environ, {"MARKET_DEMO_DATA_ENABLED": "0"}), patch.object(market_services, "_load_watchlist_cache", return_value=legacy_snapshot), patch.object(
            market_services, "_save_watchlist_cache"
        ) as save_cache:
            payload = market_services.build_market_sector_overview_payload()

        self.assertEqual(payload["items"], [])
        save_cache.assert_not_called()

    def test_market_sector_keeps_the_last_real_snapshot_when_refresh_is_stale(self):
        from src.domain import market_services

        snapshot = {"ok": True, "snapshot_version": 5, "source": "AKShare", "items": [{"sector": "银行", "value": 1020, "change_pct": 2.0}]}
        with patch.object(market_services, "_load_watchlist_cache", side_effect=[None, snapshot]):
            payload = market_services.build_market_sector_overview_payload()

        self.assertEqual(payload["items"], snapshot["items"])
        self.assertTrue(payload["stale"])

    def test_market_payloads_do_not_create_fake_values_when_snapshot_is_missing(self):
        from src.domain import market_services

        # A presentation flag must never turn fabricated market values back on.
        with patch.dict(os.environ, {"MARKET_DEMO_DATA_ENABLED": "1"}), patch.object(market_services, "_load_watchlist_cache", return_value=None):
            overview = market_services.build_market_overview_payload()
            sectors = market_services.build_market_sector_overview_payload(force_refresh=True)

        self.assertEqual(overview["items"], [])
        self.assertEqual(sectors["items"], [])

    def test_market_sectors_returns_real_rows_only(self):
        rows = [
            {"ok": True, "sector": "电子", "code": "S02000001", "value": 100.0, "change": 1.0, "change_pct": 1.0},
            {"ok": False, "sector": "银行", "message": "真实行业指标数据不足"},
        ]
        with patch("src.web.api_core.build_market_sector_overview_payload", return_value={"ok": True, "items": rows[:1], "total": 1, "catalog_size": 31}):
            response = self.client.get("/api/market-sectors")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["items"][0]["sector"], "电子")
        self.assertEqual(payload["total"], 1)

    def test_market_sector_uses_api_test_edb_search_and_get_data_contract(self):
        from src.domain import market_services

        responses = [
            (200, {"code": "000000", "status": True, "data": []}, 1),
            (200, {"code": "000000", "status": True, "data": [{"indicatorId": "S02002067", "indicatorName": "Wind行业指数:化工:当日值"}]}, 1),
            (200, {"code": "000000", "status": True, "data": {"fieldList": ["date", "S02002067"], "dataList": [["2026-08-09", "100"], ["2026-08-10", "102"]]}}, 1),
        ]
        with patch.object(market_services, "post_gangtise_openapi_json", side_effect=responses):
            result = market_services._fetch_gangtise_sector_index("化工", "2026-06-01", "2026-08-10")

        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], "S02002067")
        self.assertEqual(result["change_pct"], 2.0)

    def test_market_sector_batch_uses_one_catalog_search_and_one_get_data_call(self):
        from src.domain import market_services

        catalog = [
            {"indicatorId": "S-CHEM", "indicatorName": "Wind行业指数:化工:当日值"},
            {"indicatorId": "S-BANK", "indicatorName": "Wind行业指数:银行:当日值"},
        ]
        data = {
            "code": "000000", "status": True,
            "data": {
                "fieldList": ["date", "S-CHEM", "S-BANK"],
                "dataList": [["2026-08-09", "100", "200"], ["2026-08-10", "102", "198"]],
            },
        }
        with patch.object(market_services, "_load_watchlist_cache", return_value=None), patch.object(
            market_services, "post_gangtise_openapi_json", side_effect=[(200, {"code": "000000", "status": True, "data": catalog}, 2), (200, data, 3)]
        ) as post, patch.object(market_services, "_save_watchlist_cache"):
            rows, errors = market_services._fetch_gangtise_sector_overview("2026-08-01", "2026-08-10")

        self.assertEqual(post.call_count, 2)
        self.assertEqual({row["sector"] for row in rows}, {"基础化工", "银行"})
        self.assertEqual(next(row for row in rows if row["sector"] == "基础化工")["change_pct"], 2.0)
        self.assertTrue(errors)

    def test_h5_hermes_composer_is_compact(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slugs[0]}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('placeholder="问 Hermes..."', html)
        self.assertIn('class="hermes-lobster-toolbar"', html)
        self.assertIn('id="hermes-composer-submit"', html)
        self.assertIn("hermes-prompt-chip", html)
        self.assertIn("hermes-prompt-guide", html)
        self.assertIn("hermes-transcript-entry", html)
        self.assertIn("hermes-thinking-stream", html)
        self.assertIn("buildHermesLoadingThoughtTemplates", html)
        self.assertIn("上传文件解析", html)
        self.assertIn("id=\"hermes-internet-toggle\"", html)
        self.assertIn("handleHermesComposerSubmit()", html)
        self.assertIn("toggleHermesVoiceCapture()", html)
        self.assertIn("toggleHermesInternetAnswer()", html)
        self.assertIn("closeH5ModalById('watchlist-detail-modal')", html)
        self.assertIn('class="modal-close-btn"', html)
        self.assertIn("互联网补充开关已移到输入框外侧", html)
        self.assertIn("这个智能指标是按什么口径算出来的？", html)
        self.assertIn("ensureHermesSessionId()", html)
        self.assertNotIn("hermes-chat-bubble", html)
        self.assertNotIn("默认按全部知识库做文字回答，也可以点 + 指定知识或上传文件。", html)
        self.assertNotIn("指定知识条目", html)
        self.assertNotIn("Hermes 扩展能力", html)
        self.assertIn("function dedupeHermesTextItems(items)", html)
        self.assertIn("overflow-wrap:anywhere;", html)
        self.assertIn(".hermes-transcript-entry.assistant .hermes-transcript-text,", html)
        self.assertIn("justify-items:stretch;", html)
        self.assertIn("function saveHermesAnswerAsKnowledge(entryId)", html)
        self.assertIn("function buildHermesKnowledgePayload(entry, artifact)", html)
        self.assertIn("加入知识源", html)
        self.assertNotIn("加入上下文", html)
        self.assertIn("function requestReviewStructuredPreview()", html)
        self.assertIn("function confirmStructuredReviewToPreview()", html)
        self.assertIn("Draft 审核与详细修改", html)
        self.assertIn("用户复盘", html)
        self.assertIn("自选股归纳总结", html)
        self.assertIn("系统标签", html)
        self.assertIn("openAccountSettingsModal()", html)
        self.assertIn("openProfileNotificationCenter()", html)
        self.assertIn("openHelpCenterModal()", html)
        self.assertIn("id=\"account-settings-modal\"", html)
        self.assertIn("id=\"help-center-modal\"", html)

    def test_h5_watchlist_comment_assets_render(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slugs[0]}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("submitWatchlistComment(", html)
        self.assertIn("deleteWatchlistComment(", html)
        self.assertIn("activeSection === 'comments'", html)
        self.assertIn('id="watchlist-stock-suggestion-list"', html)
        self.assertIn("function handleWatchlistStockCodeInput(value)", html)
        self.assertIn("function selectWatchlistSuggestionByIndex(index)", html)

    def test_hermes_query_accepts_web_answer_flag(self):
        response = self.client.post(
            "/api/hermes/query",
            json={"question": "最近这个方向怎么看？", "web_answer": True, "user_role": "dav"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["web_answer"])
        self.assertIn("agent_trace", payload)
        self.assertTrue(payload["agent_trace"]["steps"])
        self.assertIn("workflow_meta", payload)
        self.assertEqual(payload["workflow_meta"]["id"], "hermes_agent")
        self.assertIn("memory_meta", payload)
        self.assertIn("user_profile_snapshot", payload)
        workflow_node_ids = [item["id"] for item in payload["workflow_meta"]["graph"]["nodes"]]
        self.assertIn("scope_guard", workflow_node_ids)
        self.assertIn("session_load", workflow_node_ids)
        self.assertIn("memory_read", workflow_node_ids)
        self.assertIn("memory_extract", workflow_node_ids)
        self.assertIn("user_profile_update", workflow_node_ids)

    def test_admin_site_config_renders_hermes_controls(self):
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="hermes-dav-access-enabled"', html)
        self.assertIn('id="hermes-investor-access-enabled"', html)
        self.assertIn('id="save-hermes-settings"', html)
        self.assertIn("function saveHermesSettings", html)
        self.assertIn('id="hermes-internet-answer-enabled"', html)
        self.assertIn('id="hermes-thinking-process-enabled"', html)
        self.assertIn('id="hermes-answer-save-to-knowledge-enabled"', html)
        self.assertIn('id="hermes-default-response-style"', html)
        self.assertIn('id="hermes-chart-types-enabled"', html)
        self.assertIn('id="hermes-intent-tree"', html)
        self.assertIn('id="hermes-route-priority"', html)
        self.assertIn('id="hermes-template-tree"', html)
        self.assertIn('id="admin-hermes-missing-capability-tbody"', html)
        self.assertIn('id="feature-watchlist_fan_comment_interaction"', html)
        self.assertIn('id="llm-feature-model-mapping"', html)
        self.assertIn("function updateAdminLlmFeatureModel", html)
        self.assertIn("功能级模型映射", html)
        self.assertIn('data-section="settings-llm-features"', html)
        self.assertIn("百科结构", html)
        self.assertIn("百科词条", html)
        self.assertIn("词条结构概览", html)
        self.assertIn("refreshAdminKnowledgeIntelligence(", html)
        self.assertIn('id="admin-knowledge-assets-summary"', html)
        self.assertIn('data-section="knowledge-overview"', html)
        self.assertIn('data-section="knowledge-intake"', html)
        self.assertIn('data-section="knowledge-encyclopedia"', html)
        self.assertIn('data-section="knowledge-entries"', html)
        self.assertIn('data-section="knowledge-graph"', html)
        self.assertIn("配置子菜单", html)
        self.assertIn("主题与外观", html)
        self.assertIn("登录与访问策略", html)
        self.assertIn("知识输入源", html)
        self.assertIn("证据链配置", html)
        self.assertIn("复盘生成配置", html)
        self.assertIn("功能级模型映射", html)
        self.assertIn('data-settings-panel="knowledge-source"', html)
        self.assertIn('data-settings-panel="llm-feature-map"', html)
        self.assertIn("openAdminSettingsSubmenu('knowledge-source')", html)

    def test_workbench_pages_render(self):
        for tenant_slug in self.tenant_slugs:
            with self.subTest(route="/kol-workbench", tenant=tenant_slug):
                response = self.client.get(f"/kol-workbench?tenant={tenant_slug}")
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.content_type)
                html = response.get_data(as_text=True)
                self.assertIn("工作台", html)
                self.assertIn("知识专区", html)
                self.assertIn("知识总览", html)
                self.assertIn("知识治理", html)
                self.assertIn("百科结构", html)
                self.assertIn("百科词条", html)
                self.assertIn("知识图谱", html)
                self.assertIn("词条列表", html)
                self.assertIn("id=\"kw-kg-legend\"", html)
                self.assertIn("loadWorkbenchKnowledgeMap(", html)
                self.assertIn("loadWorkbenchKnowledgeAssets(", html)
                self.assertIn('class="kw-review-modal-close-pill"', html)
                self.assertIn("评论标注总览", html)
                self.assertIn("kw-watchlist-comment-analytics", html)
                self.assertIn("renderWorkbenchWatchlistCommentAnalytics()", html)

    def test_tenant_portal_pages_render(self):
        for tenant_slug in self.tenant_slugs:
            with self.subTest(route="/tenant/<tenant_slug>", tenant=tenant_slug):
                response = self.client.get(f"/tenant/{tenant_slug}")
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.content_type)
                self.assertIn("Dashboard", response.get_data(as_text=True))

    def test_workbench_api_payloads(self):
        for tenant_slug in self.tenant_slugs:
            with self.subTest(route="/api/kol/workbench", tenant=tenant_slug):
                response = self.client.get(f"/api/kol/workbench?tenant={tenant_slug}")
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertIsInstance(payload, dict)
                self.assertIn("fund_dashboard", payload)
                self.assertIn("indicator_hub", payload)

    def test_workbench_knowledge_assets_api_payloads(self):
        tenant_slug = self.tenant_slugs[0]
        response = self.client.get(f"/api/kol/knowledge-assets?tenant={tenant_slug}")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("assets", payload)
        self.assertIn("summary", payload["assets"])
        self.assertIn("entries", payload["assets"])
        self.assertIn("workflow_meta", payload)
        self.assertEqual(payload["workflow_meta"]["id"], "knowledge_asset_agent")

    def test_dashboard_api_payloads(self):
        for tenant_slug in self.tenant_slugs:
            with self.subTest(route="/api/tenant/<tenant_slug>/dashboard", tenant=tenant_slug):
                response = self.client.get(f"/api/tenant/{tenant_slug}/dashboard")
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertTrue(payload["success"])
                self.assertIn("dashboard", payload)
                self.assertIn("fund_dashboard_state", payload)
                self.assertIn("fan_stock_observation", payload["dashboard"])

    def test_smart_indicator_api_payloads(self):
        for tenant_slug in self.tenant_slugs:
            with self.subTest(route="/api/tenant/<tenant_slug>/smart-indicators", tenant=tenant_slug):
                response = self.client.get(f"/api/tenant/{tenant_slug}/smart-indicators")
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertTrue(payload["success"])
                self.assertIn("smart_indicator_catalog", payload)
                self.assertIn("dashboard", payload)

    def test_fan_stock_observation_api_payloads(self):
        tenant_slug = self.tenant_slugs[0]
        response = self.client.get(f"/api/tenant/{tenant_slug}/fan-stock-observation")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("fan_stock_observation", payload)
        self.assertIn("totals", payload["fan_stock_observation"])

    def test_watchlist_comment_analytics_api_payloads(self):
        tenant_slug = self.tenant_slugs[0]
        response = self.client.get(f"/api/tenant/{tenant_slug}/watchlist-comment-analytics")

        self.assertIn(response.status_code, {200, 503})
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        if response.status_code == 200:
            self.assertTrue(payload["ok"])
            self.assertIn("analytics", payload)
            self.assertIn("summary", payload["analytics"])
            self.assertIn("keyword_cloud", payload["analytics"])
        else:
            self.assertFalse(payload["ok"])
            self.assertIn("error", payload)

    def test_fan_stock_observation_tracking_endpoint_accepts_watchlist_event(self):
        tenant_slug = self.tenant_slugs[0]
        response = self.client.post(
            f"/api/tenant/{tenant_slug}/fan-stock-observation",
            json={
                "stock_code": "00700",
                "event_type": "watchlist_detail_view",
                "user_role": "investor",
                "user_profile_id": "route_smoke_investor",
                "entry_point": "watchlist_detail",
                "source_detail": "overview",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("recorded", payload)
        self.assertIn("fan_stock_observation", payload)

    def test_admin_agent_workflows_api_payloads(self):
        response = self.client.get("/api/admin/agent-workflows")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("center", payload)
        workflows = payload["center"]["workflows"]
        workflow_ids = {item["id"] for item in workflows}
        self.assertIn("hermes_agent", workflow_ids)
        self.assertIn("smart_indicator_agent", workflow_ids)
        self.assertIn("review_voice_enhancement", workflow_ids)
        self.assertIn("review_watchlist_analysis", workflow_ids)
        self.assertIn("knowledge_query_agent", workflow_ids)
        self.assertIn("evidence_chain_agent", workflow_ids)
        self.assertIn("knowledge_processing_agent", workflow_ids)
        self.assertIn("knowledge_graph_agent", workflow_ids)
        self.assertIn("knowledge_asset_agent", workflow_ids)

    def test_admin_knowledge_assets_api_payloads(self):
        response = self.client.get("/api/admin/knowledge-assets")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("assets", payload)
        self.assertIn("summary", payload["assets"])
        self.assertIn("entries", payload["assets"])
        self.assertIn("workflow_meta", payload)
        self.assertEqual(payload["workflow_meta"]["id"], "knowledge_asset_agent")

    def test_review_prepare_preview_endpoint_queues_job(self):
        response = self.client.post(
            "/api/review/prepare-preview",
            json={
                "tenant_slug": self.tenant_slugs[0],
                "period": "day",
                "source_mode": "manual",
                "source_text": "今天用户自己输入的复盘内容，重点聚焦科技主线和风险边界。",
                "selected_watchlist": ["中芯国际", "腾讯控股"],
                "speaker_name": "测试大V",
                "entry_point": "test_review_preview",
            },
        )

        self.assertIn(response.status_code, {200, 503})
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        if response.status_code == 200:
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["async"])
            self.assertIn("job_code", payload)

    def test_review_prepare_preview_endpoint_allows_empty_watchlist(self):
        response = self.client.post(
            "/api/review/prepare-preview",
            json={
                "tenant_slug": self.tenant_slugs[0],
                "period": "day",
                "source_mode": "manual",
                "source_text": "今天用户自己输入的复盘内容，先只生成摘要。",
                "selected_watchlist": [],
                "speaker_name": "测试大V",
                "entry_point": "test_review_preview_no_watchlist",
            },
        )

        self.assertIn(response.status_code, {200, 503})
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        if response.status_code == 200:
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["async"])
            self.assertIn("job_code", payload)
        else:
            self.assertFalse(payload["ok"])
            self.assertIn("error", payload)

    def test_knowledge_query_api_returns_workflow_meta(self):
        response = self.client.post(
            "/api/kol/knowledge/query",
            json={"tenant_slug": self.tenant_slugs[0], "query": "测试知识问题", "submit_to_model": False},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("workflow_meta", payload)
        self.assertEqual(payload["workflow_meta"]["id"], "knowledge_query_agent")

    def test_evidence_chain_api_returns_workflow_meta(self):
        response = self.client.post(
            "/api/evidence-chain/query",
            json={"tenant_slug": self.tenant_slugs[0], "query": "测试证据问题", "submit_to_model": False},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("workflow_meta", payload)
        self.assertEqual(payload["workflow_meta"]["id"], "evidence_chain_agent")

    def test_knowledge_graph_api_returns_graph_payload(self):
        tenant_slug = self.tenant_slugs[0]
        response = self.client.get(f"/api/kol/knowledge-graph?tenant={tenant_slug}")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("graph", payload)
        self.assertIn("nodes", payload["graph"])
        self.assertEqual(payload["graph"].get("default_depth"), 3)
        kinds = {node.get("kind") for node in payload["graph"].get("nodes", [])}
        self.assertIn("root", kinds)
        self.assertTrue(kinds.intersection({"topic", "entity", "method", "claim", "signal"}))
        self.assertFalse(kinds.intersection({"voice", "file", "url", "manual"}))
        self.assertIn("workflow_meta", payload)
        self.assertEqual(payload["workflow_meta"]["id"], "knowledge_graph_agent")

    def test_admin_knowledge_graph_api_returns_graph_payload(self):
        response = self.client.get("/api/admin/knowledge-graph")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("graph", payload)
        self.assertIn("nodes", payload["graph"])
        self.assertEqual(payload["graph"].get("default_depth"), 3)
        kinds = {node.get("kind") for node in payload["graph"].get("nodes", [])}
        self.assertIn("root", kinds)
        self.assertFalse(kinds.intersection({"voice", "file", "url", "manual"}))
        self.assertIn("workflow_meta", payload)
        self.assertEqual(payload["workflow_meta"]["id"], "knowledge_graph_agent")

    def test_h5_help_center_api_returns_articles(self):
        response = self.client.get("/api/h5/help-center?role=dav")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("help_center", payload)
        self.assertIn("articles", payload["help_center"])
        self.assertTrue(payload["help_center"]["articles"])
        self.assertEqual(payload["help_center"]["role"], "dav")

    def test_admin_page_contains_hermes_memory_governance_controls(self):
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Hermes 记忆治理", html)
        self.assertIn("id=\"admin-hermes-memory-tenant\"", html)
        self.assertIn("id=\"admin-hermes-memory-backup-range\"", html)
        self.assertIn("id=\"admin-hermes-memory-clear-range\"", html)
        self.assertIn("loadAdminHermesMemorySummary", html)
        self.assertIn("previewAdminHermesMemoryClear", html)
        self.assertIn("backupAdminHermesMemory", html)
        self.assertIn("clearAdminHermesMemory", html)
        self.assertIn("/api/admin/hermes/memory-summary", html)
        self.assertIn("/api/admin/hermes/memory-backup", html)
        self.assertIn("/api/admin/hermes/memory-clear", html)
        self.assertIn("Hermes 缺失能力需求", html)

    def test_admin_page_contains_knowledge_center_graph(self):
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("知识图谱中心", html)
        self.assertIn("settings-knowledge-graph", html)
        self.assertIn("id=\"admin-kg-board\"", html)
        self.assertIn("id=\"admin-kg-legend\"", html)
        self.assertIn("loadAdminKnowledgeMap(", html)
        self.assertIn("/api/admin/knowledge-graph", html)


if __name__ == "__main__":
    unittest.main()
