import unittest

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
            json={"question": "最近这个方向怎么看？", "web_answer": True},
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
