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
        self.assertIn("function syncPublishedReviewStateToH5(tenantSlug, result)", html)

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

    def test_given_h5_publish_success_when_page_renders_then_publish_no_longer_opens_test_modal(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn("openReviewIngestResultModal('确认发布成功，已写入向量库'", html)
        self.assertIn("syncPublishedReviewStateToH5((user && user.tenant && user.tenant.slug) || '', result);", html)

    def test_given_workbench_publish_success_when_page_renders_then_publish_no_longer_opens_test_modal(self):
        response = self.client.get(f"/kol-workbench?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn("kwOpenReviewIngestResultModal('确认发布成功，已写入向量库'", html)
        self.assertIn("function kwSyncPublishedReviewState(result)", html)

    def test_given_h5_review_optimize_when_page_renders_then_llm_config_guard_exists(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("function hasConfiguredGeneralLlm()", html)
        self.assertIn("function getReviewDraftGenerationErrorMessage(error)", html)
        self.assertIn("当前还没有配置可用的大模型。请先到 Admin 的系统专区 · 大模型专区配置一个通用模型。", html)

    def test_given_h5_knowledge_page_when_rendered_then_framework_and_ingestion_cards_are_removed(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn("方法与框架", html)
        self.assertNotIn("复盘四步法：收拢资料", html)
        self.assertNotIn("入库方式", html)
        self.assertNotIn("大V通过语音输入、文件上传、网页 URL 提供的内容，会在清洗后进入知识专区", html)

    def test_given_hermes_tool_plan_when_web_answer_enabled_then_knowledge_runs_before_web(self):
        ordered = ai_services.build_hermes_tool_execution_plan(
            {
                "tools": ["watchlist.detail", "evidence.search", "attachment.context"],
            },
            web_answer=True,
        )

        self.assertEqual(ordered[0], "knowledge.search")
        self.assertEqual(ordered[-1], "web.search")
        self.assertIn("watchlist.detail", ordered)
        self.assertIn("evidence.search", ordered)
        self.assertIn("attachment.context", ordered)

    def test_given_hermes_tool_plan_when_web_answer_disabled_then_only_platform_tools_run(self):
        ordered = ai_services.build_hermes_tool_execution_plan(
            {
                "tools": ["watchlist.detail"],
            },
            web_answer=False,
        )

        self.assertEqual(ordered, ["knowledge.search", "watchlist.detail"])

    def test_given_watchlist_annotations_when_executing_hermes_tool_plan_then_annotation_context_is_attached(self):
        with app_entry.app.app_context():
            with patch("src.domain.ai_services.gen_watchlist_details", return_value={}):
                with patch("src.domain.ai_services.build_watchlist_annotation_context", return_value=[
                    {
                        "name": "腾讯控股",
                        "code": "00700",
                        "industry": "港股互联网",
                        "annotation_summary": "回购节奏继续，等待利润率验证",
                        "annotation_titles": ["回购验证", "利润率观察"],
                        "annotations": [{"id": 1}, {"id": 2}],
                    }
                ]):
                    with patch("src.domain.ai_services.resolve_tenant_review_snapshots", return_value=[
                        {"watchlist": ["腾讯控股", "贵州茅台"]}
                    ]):
                        outputs, _ = ai_services.execute_hermes_tool_plan(
                            {"tools": ["indicator.detail"], "indicator_code": "sh_index"},
                            tenant_slug=self.tenant_slug,
                            question_text="请展示上证指数K线图并解读",
                            web_answer=False,
                        )

        self.assertIn("watchlist_annotation_context", outputs)
        self.assertTrue(outputs["watchlist_annotation_context"]["available"])
        self.assertIn("腾讯控股", outputs["watchlist_annotation_context"]["summary"])

    def test_given_indicator_chart_question_when_synthesis_text_is_empty_then_artifact_still_contains_analysis_body(self):
        artifact = ai_services.build_hermes_indicator_artifact(
            detail={
                "name": "上证综合指数",
                "id": "sh000001",
                "value": "4093.73",
                "unit": "点",
                "status": "attention",
                "provider": "指标中心",
                "history_series": [
                    {"date": "2026-05-01", "value": "3980.12", "status": "attention"},
                    {"date": "2026-06-01", "value": "4056.44", "status": "attention"},
                    {"date": "2026-07-01", "value": "4093.73", "status": "attention"},
                ],
                "history_anomalies": [{"date": "2026-06-18", "label": "放量异动"}],
                "history_kline": {
                    "candles": [
                        {"date": "2026-07-01", "open": "4050.21", "high": "4102.66", "low": "4042.31", "close": "4093.73"}
                    ]
                },
            },
            question_text="我需要展示最近3个月的上证综合指数的K线图并做一下解读分析",
            synthesis={"answer": "", "summary": "", "bullets": []},
            tool_outputs={
                "watchlist_annotation_context": {
                    "available": True,
                    "summary": "腾讯控股：回购节奏继续，等待利润率验证",
                    "items": [{"name": "腾讯控股", "annotation_titles": ["回购验证"], "annotation_summary": "回购节奏继续，等待利润率验证"}],
                },
                "_meta": {"preferred_mode": "kline_chart"},
            },
            citations=[],
            tenant_slug=self.tenant_slug,
            user_role="dav",
        )

        self.assertEqual(artifact["type"], "indicator_analysis")
        self.assertTrue(artifact["body"])
        self.assertIn("上证综合指数", artifact["body"])
        self.assertIn("腾讯控股", artifact["body"])
        self.assertTrue(artifact["judgement"])

    def test_given_out_of_scope_question_when_scope_guard_runs_then_redirected(self):
        with app_entry.app.app_context():
            result = ai_services.hermes_scope_guard("今天天气怎么样，顺便推荐晚饭吃什么？")

        self.assertEqual(result["status"], "redirected")
        self.assertEqual(result["intent_hint"], "out_of_scope_redirect")
        self.assertIn("Hermes 主要回答", result["message"])

    def test_given_direct_trading_instruction_when_scope_guard_runs_then_blocked(self):
        with app_entry.app.app_context():
            result = ai_services.hermes_scope_guard("明天这只股票该不该满仓买入？")

        self.assertEqual(result["status"], "blocked")
        self.assertIn("不直接提供买卖", result["message"])

    def test_given_product_help_question_when_router_falls_back_then_product_help_is_selected(self):
        with app_entry.app.app_context():
            with patch("src.domain.ai_services.get_default_llm_config", return_value=None):
                plan, _, route_mode = ai_services.route_hermes_query_intent(
                    "H5 里的智能指标怎么创建和发布？",
                    tenant_slug=self.tenant_slug,
                )

        self.assertEqual(route_mode, "fallback_rule_router")
        self.assertEqual(plan["intent"], "product_help")
        self.assertIn("dashboard.context", plan["tools"])

    def test_given_smart_indicator_question_when_router_falls_back_then_dashboard_context_is_used(self):
        with app_entry.app.app_context():
            with patch("src.domain.ai_services.get_default_llm_config", return_value=None):
                plan, _, route_mode = ai_services.route_hermes_query_intent(
                    "这个智能指标是按什么公式和提示词计算出来的？",
                    tenant_slug=self.tenant_slug,
                )

        self.assertEqual(route_mode, "fallback_rule_router")
        self.assertEqual(plan["intent"], "smart_indicator_explain")
        self.assertIn("dashboard.context", plan["tools"])

    def test_given_watchlist_question_when_extracting_hermes_memory_then_focus_symbols_and_persona_are_updated(self):
        payload = ai_services.extract_hermes_memory_payload(
            question_text="请判断腾讯控股当前更适合继续跟踪还是重点研究？",
            plan={
                "intent": "watchlist_fundamental",
                "display_mode": "structured",
                "scope_status": "allowed",
                "preferred_mode": "judgement",
                "web_answer": False,
            },
            synthesis={
                "answer": "腾讯控股当前更适合继续跟踪，重点看回购与利润率兑现。",
                "summary": "继续跟踪腾讯控股，先看利润率与回购兑现。",
                "citations": ["腾讯控股 00700 HK"],
            },
            tool_outputs={
                "watchlist": {
                    "detail": {
                        "name": "腾讯控股",
                        "code": "00700",
                    }
                }
            },
            actor_context={
                "tenant_slug": self.tenant_slug,
                "user_role": "investor",
                "profile_id": "价值猎人小林",
                "display_name": "价值猎人小林",
                "membership": "专业会员",
            },
            memory_state={
                "session_id": "session_demo",
                "session": {"turn_count": 1, "recent_topics": ["港股互联网"], "recent_symbols": ["腾讯控股"]},
                "user_memory": {"total_turns": 2, "preferred_response_style": "结构化偏好", "recent_topics": ["港股互联网"], "focus_symbols": ["腾讯控股"]},
                "user_profile": {"total_queries": 2, "research_depth_score": 60, "interest_topics": ["港股互联网"], "focus_symbols": ["腾讯控股"], "style_tags": ["结构化偏好"]},
                "recent_turns": [],
            },
        )

        profile_snapshot = payload["profile_snapshot"]
        turn_tags = payload["turn_record"]["tags"]
        self.assertEqual(profile_snapshot["persona_primary"], "个股研究型用户")
        self.assertIn("腾讯控股", profile_snapshot["focus_symbols"])
        self.assertIn("个股", turn_tags["function_tags"])
        self.assertIn("结构化偏好", profile_snapshot["style_tags"])
        self.assertGreaterEqual(profile_snapshot["total_queries"], 3)

    def test_given_hermes_query_when_db_unavailable_then_memory_meta_falls_back_without_failing(self):
        response = self.client.post(
            "/api/hermes/query",
            json={"tenant_slug": self.tenant_slug, "question": "请解释这个智能指标的计算口径"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("memory_meta", payload)
        self.assertIn("user_profile_snapshot", payload)
        self.assertEqual(payload["memory_meta"]["storage_mode"], "memoryless_fallback")
        self.assertTrue(payload["session_id"])

    def test_given_out_of_scope_question_when_calling_hermes_api_then_response_is_redirected(self):
        response = self.client.post(
            "/api/hermes/query",
            json={"tenant_slug": self.tenant_slug, "question": "帮我推荐一个上海周末亲子旅游行程"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["intent"], "out_of_scope_redirect")
        self.assertEqual(payload["router"]["mode"], "scope_guard")
        self.assertFalse(payload["tool_trace"])
        self.assertTrue(payload["bullets"])

    def test_given_admin_llm_page_when_rendered_then_sync_button_exists(self):
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("从 staging 同步 LLM 配置到本地", html)
        self.assertIn("async function syncLocalLlmRegistryFromStaging()", html)
        self.assertIn("/api/admin/site-config/sync-llm-registry", html)
        self.assertIn("功能级模型映射", html)
        self.assertIn("watchlist_comment_labeling", html)

    def test_given_watchlist_comment_when_llm_unavailable_then_rule_labeling_still_returns_tags(self):
        with patch("src.domain.ai_services.get_default_llm_config", return_value=None):
            result = ai_services.label_watchlist_comment_with_llm(
                "我觉得腾讯回购节奏还在，但利润率兑现要继续验证，暂时先跟踪。",
                stock_detail={"name": "腾讯控股", "code": "00700", "industry": "港股互联网"},
                tenant_slug=self.tenant_slug,
            )

        self.assertTrue(result["labels"])
        self.assertTrue(result["keywords"])
        self.assertIn(result["sentiment_label"], {"积极", "中性", "谨慎", "追问"})
        self.assertTrue(result["summary"])

    def test_given_admin_page_when_rendered_then_agent_workflow_center_exists(self):
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("智能体工作流", html)
        self.assertIn("loadAdminAgentWorkflows", html)
        self.assertIn("/api/admin/agent-workflows", html)
        self.assertIn("section-agent-workflows", html)

    def test_given_admin_page_when_rendered_then_hermes_memory_governance_exists(self):
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Hermes 记忆治理", html)
        self.assertIn("admin-hermes-memory-summary", html)
        self.assertIn("admin-hermes-memory-preview", html)
        self.assertIn("async function loadAdminHermesMemorySummary", html)
        self.assertIn("async function backupAdminHermesMemory", html)
        self.assertIn("async function clearAdminHermesMemory", html)
        self.assertIn("/api/admin/hermes/memory-summary", html)
        self.assertIn("/api/admin/hermes/memory-clear-preview", html)
        self.assertIn("/api/admin/hermes/memory-backup", html)
        self.assertIn("/api/admin/hermes/memory-clear", html)

    def test_given_admin_hermes_memory_summary_when_api_called_then_payload_returns(self):
        summary = {
            "tenant_slug": self.tenant_slug,
            "turn_count": 12,
            "session_count": 3,
            "user_count": 2,
            "profile_count": 2,
            "range_options": [{"key": "3m", "label": "最近 3 个月"}],
        }
        with patch("src.web.api_core.build_admin_hermes_memory_summary", return_value=summary):
            response = self.client.get(f"/api/admin/hermes/memory-summary?tenant_slug={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"]["tenant_slug"], self.tenant_slug)
        self.assertEqual(payload["summary"]["turn_count"], 12)

    def test_given_admin_hermes_memory_full_clear_without_confirm_when_api_called_then_bad_request(self):
        with patch("src.web.api_core.clear_admin_hermes_memory", side_effect=ValueError("confirm_text_required")):
            response = self.client.post(
                "/api/admin/hermes/memory-clear",
                json={"tenant_slug": self.tenant_slug, "range_key": "all", "confirm_text": ""},
            )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "confirm_text_required")

    def test_given_admin_hermes_memory_backup_when_api_called_then_attachment_returns(self):
        backup_result = {
            "filename": "hermes_memory_demo.zip",
            "content_bytes": b"zip-bytes",
            "manifest": {
                "tenant_slug": self.tenant_slug,
                "range_key": "3m",
                "counts": {"conversation_turns": 5},
            },
        }
        with patch("src.web.api_core.build_admin_hermes_memory_backup_zip", return_value=backup_result):
            response = self.client.post(
                "/api/admin/hermes/memory-backup",
                json={"tenant_slug": self.tenant_slug, "range_key": "3m"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")
        self.assertIn("attachment; filename=\"hermes_memory_demo.zip\"", response.headers.get("Content-Disposition", ""))
        self.assertEqual(response.headers.get("X-Hermes-Backup-Tenant"), self.tenant_slug)
        self.assertEqual(response.headers.get("X-Hermes-Backup-Range"), "3m")
        self.assertEqual(response.get_data(), b"zip-bytes")

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
        self.assertIn("/api/review/prepare-preview", html)
        self.assertIn("/api/review/publish-embed", html)

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

    def test_given_unknown_but_valid_stock_code_when_requesting_watchlist_detail_then_dynamic_detail_is_returned(self):
        response = self.client.get("/api/watchlist/601988")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["code"], "601988")
        self.assertEqual(payload["name"], "中国银行")
        self.assertEqual(payload["market"], "SH")
        self.assertTrue(isinstance(payload.get("kline"), list) and len(payload["kline"]) >= 20)
        self.assertTrue(payload.get("fundamental", {}).get("summary"))

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

    def test_given_watchlist_annotation_rows_when_listing_then_fields_are_normalized(self):
        tenant_slug = self.tenant_slug

        class _FakeCursor:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        class _FakeDb:
            def execute(self, sql, params):
                self.last_sql = sql
                self.last_params = params
                return _FakeCursor(
                    [
                        {
                            "id": 11,
                            "tenant_slug": tenant_slug,
                            "stock_code": "688981",
                            "stock_name": "中芯国际",
                            "candle_index": 3,
                            "candle_date": "07-08",
                            "title": "放量确认",
                            "note": "量价配合有效，后续看均线支撑。",
                            "trigger": "5日线不破",
                            "updated_at": "2026-07-18 10:00:00",
                            "created_at": "2026-07-18 09:30:00",
                            "open_price": 45.1,
                            "high_price": 46.2,
                            "low_price": 44.8,
                            "close_price": 46.0,
                            "created_by_name": "财经老王",
                            "created_by_user_id": "dav_1",
                            "source_client": "h5",
                        }
                    ]
                )

        fake_db = _FakeDb()
        details_map = {
            "688981": {
                "code": "688981",
                "name": "中芯国际",
            }
        }

        with patch("src.domain.market_services.get_db", return_value=fake_db), patch(
            "src.domain.market_services.gen_watchlist_details",
            return_value=details_map,
        ):
            items = market_services.list_watchlist_kline_annotations(
                tenant_slug=self.tenant_slug,
                stock_code="688981",
            )

        self.assertEqual(len(items), 1)
        self.assertEqual(fake_db.last_params, (self.tenant_slug, "688981"))
        self.assertEqual(items[0]["id"], 11)
        self.assertEqual(items[0]["stock_name"], "中芯国际")
        self.assertEqual(items[0]["dateLabel"], "07-08")
        self.assertEqual(items[0]["title"], "放量确认")
        self.assertEqual(items[0]["trigger"], "5日线不破")

    def test_given_annotation_id_when_deleting_then_delete_is_confirmed_by_followup_lookup(self):
        class _FakeCursor:
            def __init__(self, row=None):
                self._row = row

            def fetchone(self):
                return self._row

        class _FakeDb:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params):
                self.calls.append((sql, params))
                if "SELECT id FROM watchlist_kline_annotations WHERE tenant_slug = ? AND id = ?" in sql:
                    return _FakeCursor(None)
                return _FakeCursor(None)

            def commit(self):
                self.calls.append(("COMMIT", None))

        fake_db = _FakeDb()
        details_map = {"688981": {"code": "688981", "name": "中芯国际"}}

        with patch("src.domain.market_services.get_db", return_value=fake_db), patch(
            "src.domain.market_services.gen_watchlist_details",
            return_value=details_map,
        ):
            deleted = market_services.delete_watchlist_kline_annotation(
                tenant_slug=self.tenant_slug,
                stock_code="688981",
                annotation_id=11,
                candle_index=3,
            )

        self.assertTrue(deleted)
        self.assertIn(
            (
                "DELETE FROM watchlist_kline_annotations WHERE tenant_slug = ? AND id = ?",
                (self.tenant_slug, 11),
            ),
            fake_db.calls,
        )
        self.assertIn(("COMMIT", None), fake_db.calls)

    def test_given_watchlist_annotations_when_composing_review_preview_then_annotation_evidence_is_preserved(self):
        summary_result = {
            "summary": "今天主要围绕半导体主线复盘，重点看景气兑现与市场确认。",
            "llm_model": {"stage": "user_input_summary", "model_name": "demo-summary"},
        }
        watchlist_result = {
            "sector_summary": "半导体板块以中芯国际为代表，更适合继续跟踪景气兑现和量价确认。",
            "sector_profiles": [
                {
                    "sector": "半导体",
                    "representative_description": "中芯国际是本次观察的代表样本。",
                }
            ],
            "items": [
                {
                    "stock_name": "中芯国际",
                    "stock_code": "688981",
                    "sector": "半导体",
                    "board_role": "板块代表样本",
                    "analysis_text": "优先根据 K 线标注判断量价确认，再结合基本面观察后续催化。",
                    "evidence": ["放量确认", "验证节点：5日线不破"],
                }
            ],
            "annotation_evidence": [
                {
                    "annotation_id": 11,
                    "stock_name": "中芯国际",
                    "stock_code": "688981",
                    "date_label": "07-08",
                    "title": "放量确认",
                    "note": "量价配合有效，后续看均线支撑。",
                    "trigger": "5日线不破",
                }
            ],
            "llm_model": {"stage": "watchlist_analysis", "model_name": "demo-watchlist"},
        }

        with patch("src.domain.ai_services.summarize_review_user_input_with_llm", return_value=summary_result), patch(
            "src.domain.ai_services.analyze_review_watchlist_with_llm",
            return_value=watchlist_result,
        ):
            preview = ai_services.compose_review_structured_preview(
                source_text="今天先聚焦半导体主线，重点观察景气兑现和市场确认。",
                review_period="day",
                source_mode="manual",
                selected_watchlist=["中芯国际"],
                speaker_name="财经老王",
                entry_point="test_review_bdd",
                tenant_slug=self.tenant_slug,
            )

        watchlist_section = preview["watchlist_analysis_section"]
        self.assertEqual(preview["review_summary"], summary_result["summary"])
        self.assertEqual(len(watchlist_section["annotation_evidence"]), 1)
        self.assertEqual(watchlist_section["annotation_evidence"][0]["title"], "放量确认")
        self.assertIn("优先根据 K 线标注判断量价确认", watchlist_section["items"][0]["analysis_text"])
        self.assertIn("板块归纳：半导体板块以中芯国际为代表", preview["final_text"])

    def test_given_fan_comment_interaction_disabled_when_listing_watchlist_comments_then_investor_only_sees_dav_and_self(self):
        tenant_slug = self.tenant_slug

        class _FakeCursor:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        class _FakeDb:
            def execute(self, sql, params):
                return _FakeCursor([
                    {
                        "id": 3,
                        "tenant_slug": tenant_slug,
                        "stock_code": "600519",
                        "stock_name": "贵州茅台",
                        "comment_text": "粉丝A的跟踪观点",
                        "created_by_user_id": "fan_a",
                        "created_by_name": "粉丝A",
                        "created_by_role": "investor",
                        "source_client": "h5",
                        "created_at": "2026-07-19 10:00:00",
                        "updated_at": "2026-07-19 10:00:00",
                    },
                    {
                        "id": 2,
                        "tenant_slug": tenant_slug,
                        "stock_code": "600519",
                        "stock_name": "贵州茅台",
                        "comment_text": "大V给出的阶段判断",
                        "created_by_user_id": "dav_1",
                        "created_by_name": "财经老王",
                        "created_by_role": "dav",
                        "source_client": "h5",
                        "created_at": "2026-07-19 09:30:00",
                        "updated_at": "2026-07-19 09:30:00",
                    },
                    {
                        "id": 1,
                        "tenant_slug": tenant_slug,
                        "stock_code": "600519",
                        "stock_name": "贵州茅台",
                        "comment_text": "我自己的观察",
                        "created_by_user_id": "fan_me",
                        "created_by_name": "我自己",
                        "created_by_role": "investor",
                        "source_client": "h5",
                        "created_at": "2026-07-19 09:00:00",
                        "updated_at": "2026-07-19 09:00:00",
                    },
                ])

        with patch("src.domain.market_services.get_db", return_value=_FakeDb()), patch(
            "src.domain.market_services.gen_watchlist_details",
            return_value={"600519": {"code": "600519", "name": "贵州茅台"}},
        ):
            items = market_services.list_watchlist_comments(
                tenant_slug=tenant_slug,
                stock_code="600519",
                viewer_role="investor",
                viewer_profile_id="fan_me",
                allow_fan_to_fan=False,
            )

        self.assertEqual([item["id"] for item in items], [2, 1])
        self.assertTrue(items[1]["can_delete"])
        self.assertFalse(items[0]["can_delete"])

    def test_given_dav_when_listing_watchlist_comments_then_all_tenant_comments_are_visible(self):
        tenant_slug = self.tenant_slug

        class _FakeCursor:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        class _FakeDb:
            def execute(self, sql, params):
                return _FakeCursor([
                    {
                        "id": 2,
                        "tenant_slug": tenant_slug,
                        "stock_code": "00700",
                        "stock_name": "腾讯控股",
                        "comment_text": "粉丝追问",
                        "created_by_user_id": "fan_1",
                        "created_by_name": "粉丝1",
                        "created_by_role": "investor",
                        "source_client": "h5",
                        "created_at": "2026-07-19 11:00:00",
                        "updated_at": "2026-07-19 11:00:00",
                    },
                    {
                        "id": 1,
                        "tenant_slug": tenant_slug,
                        "stock_code": "00700",
                        "stock_name": "腾讯控股",
                        "comment_text": "大V主判断",
                        "created_by_user_id": "dav_1",
                        "created_by_name": "财经老王",
                        "created_by_role": "dav",
                        "source_client": "h5",
                        "created_at": "2026-07-19 10:30:00",
                        "updated_at": "2026-07-19 10:30:00",
                    },
                ])

        with patch("src.domain.market_services.get_db", return_value=_FakeDb()), patch(
            "src.domain.market_services.gen_watchlist_details",
            return_value={"00700": {"code": "00700", "name": "腾讯控股"}},
        ):
            items = market_services.list_watchlist_comments(
                tenant_slug=tenant_slug,
                stock_code="00700",
                viewer_role="dav",
                viewer_profile_id="财经老王",
                allow_fan_to_fan=False,
            )

        self.assertEqual(len(items), 2)
        self.assertTrue(all(item["can_delete"] for item in items))


if __name__ == "__main__":
    unittest.main()
