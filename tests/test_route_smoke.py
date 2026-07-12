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
        cls._original_password_gate = web_hooks.is_password_gate_enabled
        web_hooks.is_password_gate_enabled = lambda: False
        app_entry.app.config.update(TESTING=True)
        cls.client = app_entry.app.test_client()
        cls.tenant_slugs = _tenant_slugs()

    @classmethod
    def tearDownClass(cls):
        web_hooks.is_password_gate_enabled = cls._original_password_gate

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
        self.assertIn("hermes-prompt-chip", html)
        self.assertIn("hermes-prompt-guide", html)
        self.assertIn("hermes-transcript-entry", html)
        self.assertIn("hermes-thinking-stream", html)
        self.assertIn("buildHermesLoadingThoughtTemplates", html)
        self.assertIn("上传文件解析", html)
        self.assertIn("id=\"hermes-internet-toggle\"", html)
        self.assertIn("toggleHermesInternetAnswer()", html)
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
        self.assertIn("摘要和自选股归纳总结审核与详细修改", html)
        self.assertIn("用户复盘", html)
        self.assertIn("自选股归纳总结", html)

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

    def test_workbench_pages_render(self):
        for tenant_slug in self.tenant_slugs:
            with self.subTest(route="/kol-workbench", tenant=tenant_slug):
                response = self.client.get(f"/kol-workbench?tenant={tenant_slug}")
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.content_type)
                self.assertIn("工作台", response.get_data(as_text=True))

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


if __name__ == "__main__":
    unittest.main()
