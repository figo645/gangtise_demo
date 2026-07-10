import unittest
from unittest import mock
from unittest.mock import patch

import app as app_entry
import src.web.hooks as web_hooks
from src.domain import ai_services
from src.domain import market_services
from src.domain.core_services import (
    get_tenant_by_slug,
    normalize_fund_dashboard_card_refs,
    normalize_fund_dashboard_view,
    resolve_tenant_review_snapshots,
    sanitize_user_facing_source_text,
)
from src.services import get_tenant_configs


def _tenant_slug():
    try:
        tenants = get_tenant_configs()
    except Exception:
        return "lisa"
    for item in tenants:
        slug = str(item.get("slug") or "").strip()
        if slug:
            return slug
    return "lisa"


class ReviewModuleBddTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._original_password_gate = web_hooks.is_password_gate_enabled
        web_hooks.is_password_gate_enabled = lambda: False
        app_entry.app.config.update(TESTING=True)
        cls.client = app_entry.app.test_client()
        cls.tenant_slug = _tenant_slug()

    @classmethod
    def tearDownClass(cls):
        web_hooks.is_password_gate_enabled = cls._original_password_gate

    def test_given_h5_when_page_renders_then_review_surface_exists(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="review-report-feed"', html)
        self.assertIn('id="review-trigger-modal-content"', html)
        self.assertIn("function renderReviewExperience()", html)
        self.assertIn("function publishReviewDraft()", html)

    def test_given_h5_dav_review_when_page_renders_then_new_review_flow_exists(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("function renderReviewFlowActions()", html)
        self.assertIn("function openReviewOptimizeRuleStep()", html)
        self.assertIn("function setReviewOptimizeRuleMode(mode)", html)
        self.assertIn("async function submitReviewSmartOptimize()", html)
        self.assertIn("draft_generating", html)
        self.assertIn("正在生成 Draft", html)
        self.assertIn("function renderReviewDraftReviewPanel()", html)
        self.assertIn("function confirmReviewDraftToPreview()", html)
        self.assertIn("function prepareReviewDirectPreview()", html)
        self.assertIn("function backToReviewDraftEdit()", html)
        self.assertIn("function buildReviewPreviewArticle()", html)
        self.assertIn("function renderReviewArticleDetailContent(article, options = {})", html)
        self.assertIn("智能优化规则", html)
        self.assertIn("忽略规则，默认优化", html)
        self.assertIn("输入规则后优化", html)
        self.assertIn("Draft 审核与详细修改", html)
        self.assertIn("id=\"review-draft-review-input\"", html)
        self.assertIn("onclick=\"prepareReviewDirectPreview()\"", html)
        self.assertIn("onclick=\"openReviewOptimizeRuleStep()\"", html)
        self.assertIn("onclick=\"publishReviewDraft()\"", html)
        self.assertNotIn("id=\"review-skip-ai-processing\"", html)
        self.assertNotIn("function toggleReviewSkipAiProcessing", html)
        self.assertNotIn("不使用大模型处理", html)

    def test_given_h5_review_preview_when_rendered_then_preview_uses_article_detail_view(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("这是发布前的最终预览。当前阅读态会尽量贴近普通用户和大V最终看到的详情展示。", html)
        self.assertIn("reviewTriggerDraft.flowStage !== 'preview'", html)
        self.assertIn("renderReviewArticleDetailContent(article, { previewMode: true })", html)

    def test_given_h5_review_optimize_when_page_renders_then_llm_config_guard_exists(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("function hasConfiguredGeneralLlm()", html)
        self.assertIn("function getReviewDraftGenerationErrorMessage(error)", html)
        self.assertIn("当前还没有配置可用的大模型。请先到 Admin 的系统专区 · 大模型专区配置一个通用模型。", html)

    def test_given_admin_llm_page_when_rendered_then_sync_button_exists(self):
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("从 staging 同步 LLM 配置到本地", html)
        self.assertIn("async function syncLocalLlmRegistryFromStaging()", html)
        self.assertIn("/api/admin/site-config/sync-llm-registry", html)

    def test_given_sync_request_when_api_called_then_only_llm_registry_is_synced(self):
        local_site_config = {
            "brand": {"name": "Local Brand"},
            "feature_flags": {"community": False},
            "llm_registry": {
                "default_model_key": "local-general",
                "models": [
                    {
                        "key": "local-general",
                        "label": "Local General",
                        "provider": "openai",
                        "model_name": "gpt-local",
                        "base_url": "http://local/v1",
                        "api_key": "local-key",
                        "purpose": "general",
                        "enabled": True,
                    }
                ],
            },
        }
        staging_site_config = {
            "brand": {"name": "Staging Brand"},
            "feature_flags": {"community": True},
            "llm_registry": {
                "default_model_key": "staging-general",
                "models": [
                    {
                        "key": "staging-general",
                        "label": "Staging General",
                        "provider": "openai",
                        "model_name": "gpt-staging",
                        "base_url": "https://staging.example/v1",
                        "api_key": "staging-key",
                        "purpose": "general",
                        "enabled": True,
                    }
                ],
            },
        }
        saved_payloads = []

        def fake_load_site_config_from_db_target(target):
            if (target or {}).get("label") == "local":
                return local_site_config
            if (target or {}).get("label") == "staging":
                return staging_site_config
            raise AssertionError("unexpected target")

        def fake_save_site_config_to_db_target(config, target):
            saved_payloads.append((config, target))
            return config

        with patch("src.domain.core_services.load_site_config_from_db_target", side_effect=fake_load_site_config_from_db_target), patch(
            "src.domain.core_services.save_site_config_to_db_target",
            side_effect=fake_save_site_config_to_db_target,
        ):
            response = self.client.post("/api/admin/site-config/sync-llm-registry", json={})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["synced_model_count"], 1)
        self.assertEqual(payload["default_model_key"], "staging-general")
        self.assertEqual(payload["local_db_target"]["label"], "local")
        self.assertEqual(payload["staging_db_target"]["label"], "staging")
        self.assertEqual(len(saved_payloads), 1)
        saved_config, saved_target = saved_payloads[0]
        self.assertEqual(saved_target["label"], "local")
        self.assertEqual(saved_config["brand"]["name"], "Local Brand")
        self.assertEqual(saved_config["feature_flags"]["community"], False)
        self.assertEqual(saved_config["llm_registry"]["default_model_key"], "staging-general")
        self.assertEqual(saved_config["llm_registry"]["models"][0]["model_name"], "gpt-staging")

    def test_given_community_api_when_called_then_posts_and_events_render(self):
        posts_response = self.client.get("/api/community/posts")
        events_response = self.client.get("/api/community/events")

        self.assertEqual(posts_response.status_code, 200)
        self.assertEqual(events_response.status_code, 200)
        self.assertIsInstance(posts_response.get_json(), list)
        self.assertIsInstance(events_response.get_json(), list)

    def test_given_h5_review_page_when_rendering_then_legacy_dav_studio_block_is_removed(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("function renderDavReviewStudio(user)", html)
        self.assertNotIn("大V复盘供稿台", html)
        self.assertNotIn("先点输入按钮口述，系统自动转成复盘文案。", html)
        self.assertNotIn("上传后自动抽取并转成复盘文案。", html)

    def test_given_workbench_when_page_renders_then_review_studio_assets_exist(self):
        response = self.client.get(f"/kol-workbench?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("review_studio", html)
        self.assertIn("published_reviews", html)
        self.assertIn("/api/review/generate-draft", html)
        self.assertIn("/api/review/compose-draft", html)

    def test_given_workbench_when_page_renders_then_fan_message_block_is_removed(self):
        response = self.client.get(f"/kol-workbench?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn('data-section="messages"', html)
        self.assertNotIn('id="workbench-section-messages"', html)
        self.assertNotIn("kwRenderMessageCenter()", html)
        self.assertNotIn("待回复消息", html)
        self.assertNotIn("未读粉丝会话", html)

    def test_given_workbench_when_page_renders_then_broadcast_block_is_removed(self):
        response = self.client.get(f"/kol-workbench?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn('data-section="broadcast"', html)
        self.assertNotIn('id="workbench-section-broadcast"', html)
        self.assertNotIn("kwRenderBroadcastHistory()", html)

    def test_given_h5_when_smart_indicator_editor_renders_then_formula_builder_assets_exist(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("公式编辑器", html)
        self.assertIn("function insertWorkbenchSmartTagReference(tagCode)", html)
        self.assertIn("function insertWorkbenchSmartOperator(operator)", html)
        self.assertIn("id=\"wb-smart-indicator-formula-tools\"", html)
        self.assertIn("id=\"wb-smart-indicator-formula-hint\"", html)
        self.assertIn("点击指标会直接插入下方公式编辑器", html)
        self.assertIn("正在生成智能指标预览", html)
        self.assertIn("wbSmartIndicatorDraft.isGenerating", html)
        self.assertIn("生成中...", html)
        self.assertIn("function getWorkbenchDirectPreviewCandidate(selectedTagCodes)", html)
        self.assertIn("direct_reference", html)
        self.assertIn("已直接引用指标，无需等待生成", html)
        self.assertIn("这是已有指标的直接引用，不需要等待 LLM 生成", html)
        self.assertIn("function buildWorkbenchSmartDashboardCardRefs(active, layout, slotIndex, nextIndicatorCode)", html)
        self.assertNotIn("当前值为 151.275", html)
        self.assertNotIn('wb-dashboard-summary-card filled" style="margin-top:10px"', html)

    def test_given_h5_when_page_renders_then_on_demand_fundamental_panel_is_removed(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn("按需基本面面板", html)
        self.assertNotIn("面向大V的通用分析设计", html)
        self.assertNotIn("选择分析模块", html)
        self.assertNotIn("发起综合分析", html)

    def test_given_duplicate_dashboard_cards_when_normalized_then_indicator_codes_are_unique(self):
        normalized = normalize_fund_dashboard_card_refs(
            [
                {"indicatorCode": "laowang_cpi"},
                {"indicatorCode": "laowang_cpi"},
                {"indicatorCode": "gold_silver_ratio"},
            ],
            "2x2",
        )

        indicator_codes = [item.get("indicatorCode") for item in normalized if item.get("indicatorCode")]
        self.assertEqual(indicator_codes, list(dict.fromkeys(indicator_codes)))
        self.assertEqual(len(indicator_codes), 2)

    def test_given_h5_when_page_renders_then_fan_stock_observation_uses_sector_chart(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="wb-fan-stock-sector-chart"', html)
        self.assertIn("function renderFanStockSectorChart()", html)
        self.assertIn("function openFanStockInsightStock(stockCode)", html)
        self.assertIn("按板块看访问热度", html)
        self.assertNotIn("投研达人_小陈 · 中际旭创", html)
        self.assertNotIn("价值猎人小林 · 腾讯控股", html)

    def test_given_h5_workbench_when_page_renders_then_message_and_broadcast_blocks_are_removed(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn('id="wb-fan-inbox"', html)
        self.assertNotIn('id="wb-quick-reply"', html)
        self.assertNotIn('id="wb-broadcast-text"', html)
        self.assertNotIn('id="wb-broadcast-history"', html)
        self.assertNotIn("查看全部 ›", html)
        self.assertNotIn("快速回复选中粉丝", html)
        self.assertNotIn("触达 128 位留资用户", html)
        self.assertNotIn(">最近群发<", html)

    def test_given_h5_feed_when_page_renders_then_stock_signal_does_not_expose_internal_function_name(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn("macro_china_cpi_monthly()", html)

    def test_given_internal_source_text_when_sanitized_then_api_and_function_names_are_hidden(self):
        source_text = "上证指数: 实时接口: qt.gtimg.cn/q=sh000001; 历史回退: AKShare stock_zh_index_daily(symbol='sh000001')"

        normalized = sanitize_user_facing_source_text(source_text)

        self.assertEqual(normalized, "上证指数：实时行情数据；历史行情数据：历史数据服务")
        self.assertNotIn("qt.gtimg.cn", normalized)
        self.assertNotIn("stock_zh_index_daily", normalized)
        self.assertNotIn("AKShare", normalized)

    def test_given_watchlist_detail_when_indicator_assessment_contains_internal_sources_then_api_response_is_sanitized(self):
        mock_context = {
            "items": [
                {
                    "id": "credit_pulse",
                    "name": "信贷脉冲",
                    "status": "attention",
                    "assessment": "宏观环境继续观察",
                    "alert": "保持关注",
                    "value": "中性",
                },
                {
                    "id": "source_cpi",
                    "name": "CPI",
                    "status": "attention",
                    "assessment": "月度宏观接口: macro_china_cpi_monthly()",
                    "alert": "保持关注",
                    "value": "2.1%",
                },
                {
                    "id": "source_shanghai_index",
                    "name": "上证指数",
                    "status": "normal",
                    "assessment": "实时接口: qt.gtimg.cn/q=sh000001; 历史回退: AKShare stock_zh_index_daily(symbol='sh000001')",
                    "alert": "保持观察",
                    "value": "3288.4",
                },
            ],
            "by_id": {},
            "warnings": [],
            "attentions": [],
            "anomalies": [],
        }
        mock_context["by_id"] = {item["id"]: item for item in mock_context["items"]}
        mock_context["attentions"] = mock_context["items"][:2]

        with patch("src.domain.market_services.build_watchlist_indicator_context", return_value=mock_context):
            response = self.client.get("/api/watchlist/600519")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        thesis_text = " ".join(payload["fundamental"]["thesis"])
        metrics_text = " ".join(str(item.get("note") or "") for item in payload["fundamental"]["metrics"])

        self.assertNotIn("macro_china_cpi_monthly()", thesis_text)
        self.assertNotIn("qt.gtimg.cn", thesis_text)
        self.assertNotIn("stock_zh_index_daily", thesis_text)
        self.assertNotIn("macro_china_cpi_monthly()", metrics_text)
        self.assertNotIn("qt.gtimg.cn", metrics_text)
        self.assertNotIn("stock_zh_index_daily", metrics_text)
        payload_text = str(payload)
        self.assertNotIn("macro_china_cpi_monthly()", payload_text)
        self.assertNotIn("qt.gtimg.cn", payload_text)
        self.assertNotIn("stock_zh_index_daily", payload_text)
        self.assertNotIn("AKShare", payload_text)
        self.assertIn("CPI：月度宏观数据", thesis_text)

        signal_bundle = market_services.build_watchlist_signal_bundle(
            "600519",
            "贵州茅台",
            "高端白酒",
            mock_context,
        )
        signal_text = str(signal_bundle)
        self.assertIn("上证指数：实时行情数据", signal_text)
        self.assertNotIn("qt.gtimg.cn", signal_text)
        self.assertNotIn("stock_zh_index_daily", signal_text)
        self.assertNotIn("AKShare", signal_text)

    def test_given_empty_source_text_when_generating_review_draft_then_reject(self):
        response = self.client.post(
            "/api/review/generate-draft",
            json={
                "tenant_slug": self.tenant_slug,
                "period": "day",
                "source_mode": "manual",
                "source_text": "   ",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "review_source_text_required")

    def test_given_valid_source_text_when_generating_review_draft_then_queue_async_job(self):
        with mock.patch(
            "src.web.api_kol.create_user_async_job",
            return_value={"job_code": "JOB-REVIEW-DRAFT-1", "status": "pending"},
        ) as create_job:
            response = self.client.post(
                "/api/review/generate-draft",
                json={
                    "tenant_slug": self.tenant_slug,
                    "period": "day",
                    "source_mode": "manual",
                    "source_text": "今天先看 AI 算力和港股互联网两条线。",
                    "prompt_text": "保留风险边界",
                    "prompt_tags": ["风险提示"],
                    "selected_watchlist": ["腾讯控股"],
                    "speaker_name": "BDD Tester",
                    "entry_point": "test_review_bdd",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["async"])
        self.assertEqual(payload["job_code"], "JOB-REVIEW-DRAFT-1")
        create_job.assert_called_once()
        self.assertEqual(create_job.call_args.args[0], "review_generate_draft")
        self.assertEqual(create_job.call_args.kwargs["tenant_slug"], self.tenant_slug)

    def test_given_empty_source_text_when_composing_review_then_reject(self):
        response = self.client.post(
            "/api/review/compose-draft",
            json={
                "tenant_slug": self.tenant_slug,
                "period": "week",
                "source_text": "",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "review_source_text_required")

    def test_given_valid_source_text_when_composing_review_then_queue_async_job(self):
        with mock.patch(
            "src.web.api_kol.create_user_async_job",
            return_value={"job_code": "JOB-REVIEW-COMPOSE-1", "status": "pending"},
        ) as create_job:
            response = self.client.post(
                "/api/review/compose-draft",
                json={
                    "tenant_slug": self.tenant_slug,
                    "period": "week",
                    "source_text": "原始收盘笔记",
                    "prompt_text": "按板块、个股、风险边界展开",
                    "prompt_tags": ["个股跟踪"],
                    "selected_watchlist": ["腾讯控股", "美团-W"],
                    "dashboard_cards": [{"id": "card-1", "title": "北向资金", "summary": "净流入"}],
                    "knowledge_items": [{"id": "k-1", "title": "会议纪要", "summary": "需求修复"}],
                    "speaker_name": "BDD Tester",
                    "entry_point": "test_review_bdd",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["async"])
        self.assertEqual(payload["job_code"], "JOB-REVIEW-COMPOSE-1")
        create_job.assert_called_once()
        self.assertEqual(create_job.call_args.args[0], "review_compose_draft")

    def test_given_empty_publish_text_when_publishing_review_then_reject(self):
        response = self.client.post(
            "/api/review/publish-embed",
            json={
                "tenant_slug": self.tenant_slug,
                "period": "day",
                "text": "",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "publish_text_required")

    def test_given_valid_publish_text_when_publishing_review_then_queue_async_job(self):
        with mock.patch(
            "src.web.api_core.create_user_async_job",
            return_value={"job_code": "JOB-REVIEW-PUBLISH-1", "status": "pending"},
        ) as create_job:
            response = self.client.post(
                "/api/review/publish-embed",
                json={
                    "tenant_slug": self.tenant_slug,
                    "period": "day",
                    "text": "这是确认发布后的复盘正文。",
                    "source_mode": "manual",
                    "paragraph_mode": "ai",
                    "selected_watchlist": ["腾讯控股"],
                    "prompt_tags": ["风险提示"],
                    "speaker_name": "BDD Tester",
                    "entry_point": "test_review_bdd",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["async"])
        self.assertEqual(payload["job_code"], "JOB-REVIEW-PUBLISH-1")
        create_job.assert_called_once()
        self.assertEqual(create_job.call_args.args[0], "review_publish_embed")

    def test_given_publish_text_when_processing_then_transcription_engine_is_forwarded(self):
        with mock.patch("src.domain.ai_services.get_voice_embedding_config", return_value={"engine": "local"}), mock.patch(
            "src.domain.ai_services.build_text_embedding",
            return_value=([0.1, 0.2], "local", "test-embedding-model"),
        ), mock.patch(
            "src.domain.ai_services._store_review_voice_embedding_record",
            return_value={"id": 1, "storage_mode": "jsonb"},
        ) as store_record:
            result = ai_services.process_review_publish_text(
                text="发布后的复盘正文",
                tenant_slug=self.tenant_slug,
                review_period="day",
                entry_point="test_review_bdd",
                speaker_name="BDD Tester",
                transcription_engine="manual",
                transcript_model="manual_input",
            )

        self.assertEqual(result["transcription_engine"], "manual")
        store_record.assert_called_once()
        self.assertEqual(store_record.call_args.kwargs["transcription_engine"], "manual")

    def test_given_sparse_snapshot_when_resolving_then_required_review_fields_are_filled(self):
        with app_entry.app.app_context():
            tenant = get_tenant_by_slug(self.tenant_slug)
            snapshots = resolve_tenant_review_snapshots(
                tenant,
                snapshots=[
                    {
                        "title": "只给了标题",
                        "watchlist": ["腾讯控股"],
                    }
                ],
            )

        self.assertEqual(len(snapshots), 1)
        snapshot = snapshots[0]
        self.assertEqual(snapshot["title"], "只给了标题")
        self.assertEqual(snapshot["watchlist"], ["腾讯控股"])
        self.assertTrue(snapshot["summary"])
        self.assertTrue(snapshot["content_text"])
        self.assertEqual(snapshot["snapshot_type"], "published_review")
        self.assertIn("period_key", snapshot)


if __name__ == "__main__":
    unittest.main()
