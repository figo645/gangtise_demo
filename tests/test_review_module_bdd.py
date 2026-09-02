import copy
import json
import unittest
from datetime import date
from pathlib import Path
from unittest import mock
from unittest.mock import patch

import app as app_entry
import src.web.hooks as web_hooks
import src.web.pages as web_pages
from src.domain import ai_services
from src.domain import core_services
from src.domain import market_services
from src.domain.core_services import (
    get_tenant_by_slug,
    normalize_site_config,
    normalize_fund_dashboard_card_refs,
    normalize_fund_dashboard_view,
    build_new_smart_indicator_code,
    resolve_tenant_review_snapshots,
    delete_tenant_review_snapshot,
    sanitize_user_facing_source_text,
)
from src.services import get_tenant_configs


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
        cls._original_is_authenticated = web_hooks.is_authenticated
        cls._original_current_user = web_pages.get_current_authenticated_user
        web_hooks.is_authenticated = lambda: True
        web_pages.get_current_authenticated_user = lambda: {"id": "test-user", "role": "dav"}
        app_entry.app.config.update(TESTING=True)
        cls.client = app_entry.app.test_client()
        cls.tenant_slug = _tenant_slug()

    @classmethod
    def tearDownClass(cls):
        web_hooks.is_authenticated = cls._original_is_authenticated
        web_pages.get_current_authenticated_user = cls._original_current_user

    def test_given_h5_when_page_renders_then_review_surface_exists(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="review-report-feed"', html)
        self.assertIn('id="review-trigger-modal-content"', html)
        self.assertIn('id="review-production-page"', html)
        self.assertIn('id="review-active-jobs-overview-host"', html)
        self.assertIn("function renderReviewExperience()", html)
        self.assertIn("function publishReviewDraft()", html)
        self.assertIn("function syncPublishedReviewStateToH5(tenantSlug, result)", html)

    def test_given_h5_stock_search_when_no_candidate_then_raw_stock_name_is_not_submitted(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("未找到匹配股票，请从候选列表选择", html)
        self.assertIn("/^(?:\\d{5,6})(?:\\.(?:SH|SZ|BJ|HK))?$/i.test(query)", html)

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
        self.assertIn("const isReviewSetupStage = reviewStage === 'intake' || reviewStage === 'optimize_rule';", html)
        self.assertIn("const isReviewFinalPreview = reviewStage === 'preview' || reviewTriggerDraft.previewReady === true;", html)
        self.assertIn("<div class=\"modal-title\" style=\"margin-bottom:${isReviewFinalPreview ? '4px' : '10px'}\">${modalTitle}</div>", html)
        self.assertIn("const hasDavCapabilities = isDavCapableUser(user);", html)
        self.assertIn("${hasDavCapabilities ? `", html)
        self.assertIn("${isReviewSetupStage ? `", html)
        self.assertIn("<div class=\"review-stage-compact-meta\">", html)
        self.assertIn("智能优化规则", html)
        self.assertIn("忽略规则，默认优化", html)
        self.assertIn("输入规则后优化", html)
        self.assertIn("Draft 审核与详细修改", html)
        self.assertIn("id=\"review-draft-review-input\"", html)
        self.assertIn("id=\"review-title-input\"", html)
        self.assertIn("onclick=\"prepareReviewDirectPreview()\"", html)
        self.assertIn("onclick=\"openReviewOptimizeRuleStep()\"", html)
        self.assertIn("onclick=\"publishReviewDraft()\"", html)
        self.assertIn("url.searchParams.set('review', 'compose')", html)
        self.assertIn("function loadActiveReviewJobs()", html)
        self.assertIn("已有复盘草稿正在生成，请勿重复提交", html)
        self.assertIn('oninput="reviewTriggerDraft.reviewTitle = this.value"', html)
        self.assertIn("reviewHostSelector = reviewProductionPage ? '#review-production-page-content' : '#review-trigger-modal-content'", html)
        self.assertIn("reviewTriggerDraft.flowStage = partialAnalysis ? 'structured_review' : 'preview_failed'", html)
        self.assertIn("已保留当前任务的阶段日志和部分返回内容", html)
        self.assertIn("重新生成自选股分析", html)
        self.assertIn("const combinedText = String(watchlistSection.combined_text || '').trim()", html)
        self.assertIn("function renderGangtiseMarkdown(value)", html)
        self.assertIn("const recoverCompressedTable = (rawText) =>", html)
        self.assertIn("review-gangtise-table-wrap", html)
        self.assertIn("const headers = tableCells(line)", html)
        self.assertIn('placeholder="这里是 Gangtise 已返回的分析内容，可继续修改。"', html)
        self.assertIn('id="review-structured-combined-text"', html)
        self.assertIn("reviewStructuredPreview.watchlist_analysis_section.combined_text = structuredCombinedText.value", html)
        self.assertIn("const progressMarkup = failed", html)
        self.assertIn("watchlist_gangtise_sse_streaming')", html)
        self.assertNotIn("id=\"review-skip-ai-processing\"", html)
        self.assertNotIn("function toggleReviewSkipAiProcessing", html)
        self.assertNotIn("不使用大模型处理", html)

    def test_given_h5_dav_review_workspace_when_active_jobs_are_loaded_then_audio_payload_is_not_exposed(self):
        with mock.patch("src.web.api_kol.get_current_authenticated_user", return_value={"role": "dav", "tenant_slug": self.tenant_slug}), mock.patch(
            "src.web.api_kol.list_user_async_jobs",
            return_value=[
                {
                    "job_code": "JOB-REVIEW-VOICE-1",
                    "job_type": "review_voice_transcribe",
                    "tenant_slug": self.tenant_slug,
                    "status": "running",
                    "progress_percent": 45,
                    "summary": "语音处理中",
                    "payload": {"audio_base64": "secret-audio", "filename": "review.webm"},
                }
            ],
        ):
            response = self.client.get(f"/api/review/jobs?tenant_slug={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["jobs"][0]["payload"], {"filename": "review.webm"})

    def test_given_async_review_failure_when_job_is_completed_then_progress_result_is_preserved(self):
        existing_job = {
            "result": {
                "live_log": [{"stage": "watchlist_gangtise_sse_streaming", "text": "已收到部分分析"}],
                "partial_text": "已返回的部分分析",
            }
        }
        with mock.patch("src.domain.core_services.get_user_async_job", return_value=existing_job), mock.patch(
            "src.domain.core_services.update_user_async_job"
        ) as update_job:
            with app_entry.app.app_context():
                core_services._complete_user_async_job(
                    "review-job-1",
                    False,
                    summary="任务执行失败",
                    result={"error_type": "RuntimeError"},
                    error_message="sse_connection_closed",
                )

        saved_result = json.loads(update_job.call_args.kwargs["result_json"])
        self.assertEqual(saved_result["partial_text"], "已返回的部分分析")
        self.assertEqual(saved_result["live_log"][0]["text"], "已收到部分分析")
        self.assertEqual(saved_result["error_type"], "RuntimeError")

    def test_given_cancelled_review_job_when_worker_finishes_then_cancelled_state_is_preserved(self):
        existing_job = {
            "status": "cancelled",
            "result": {"cancel_reason": "user_requested"},
        }
        with mock.patch("src.domain.core_services.get_user_async_job", return_value=existing_job), mock.patch(
            "src.domain.core_services.update_user_async_job"
        ) as update_job:
            with app_entry.app.app_context():
                result = core_services._complete_user_async_job(
                    "review-job-cancelled",
                    True,
                    summary="复盘草稿生成完成",
                    result={"text": "不应写入"},
                )

        self.assertEqual(result["status"], "cancelled")
        update_job.assert_not_called()

    def test_given_cancelled_review_job_when_progress_is_reported_then_no_late_progress_is_written(self):
        existing_job = {"status": "cancelled", "progress_stage": "cancelled"}
        with mock.patch("src.domain.core_services.get_user_async_job", return_value=existing_job), mock.patch(
            "src.domain.core_services.update_user_async_job"
        ) as update_job:
            with app_entry.app.app_context():
                result = core_services.report_user_async_job_progress(
                    "review-job-cancelled",
                    stage="llm_postprocessing",
                    percent=85,
                    summary="晚到的进度",
                )

        self.assertEqual(result["status"], "cancelled")
        update_job.assert_not_called()

    def test_given_dav_owned_active_review_job_when_cancelled_then_endpoint_marks_it_cancelled(self):
        job = {
            "job_code": "review_generate_draft_test_1",
            "job_type": "review_generate_draft",
            "tenant_slug": self.tenant_slug,
            "owner_label": "BDD Tester",
            "status": "running",
            "payload": {"source_text": "原始复盘", "audio_base64": "secret"},
        }
        cancelled = {**job, "status": "cancelled", "progress_stage": "cancelled"}
        with mock.patch(
            "src.web.api_kol.get_current_authenticated_user",
            return_value={"role": "dav", "tenant_slug": self.tenant_slug, "advisor_name": "BDD Tester"},
        ), mock.patch("src.web.api_kol.get_user_async_job", return_value=job), mock.patch(
            "src.web.api_kol.cancel_user_async_job", return_value=cancelled
        ) as cancel_job:
            response = self.client.post(f"/api/review/jobs/{job['job_code']}/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertNotIn("audio_base64", response.get_json()["job"]["payload"])
        cancel_job.assert_called_once_with(job["job_code"])

    def test_given_h5_review_generation_when_rendered_then_stop_action_and_cancel_terminal_state_exist(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('onclick="cancelReviewAsyncJob()">停止生成', html)
        self.assertIn("job.status === 'cancelled'", html)
        self.assertIn('/api/review/jobs/${encodeURIComponent(jobCode)}/cancel', html)

    def test_given_simulated_review_job_when_worker_claims_next_then_it_is_not_excluded_from_execution(self):
        class _FakeCursor:
            def __init__(self):
                self.sql = ""

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, params=None):
                self.sql = sql

            def fetchone(self):
                return None

        class _FakeConnection:
            def __init__(self):
                self.cursor_instance = _FakeCursor()

            def cursor(self, **kwargs):
                return self.cursor_instance

            def rollback(self):
                pass

            def close(self):
                pass

        connection = _FakeConnection()
        with mock.patch("src.domain.core_services.get_app_db_connection", return_value=connection):
            core_services._claim_next_user_async_job()

        self.assertIn("WHERE status = 'pending'", connection.cursor_instance.sql)
        self.assertNotIn("COALESCE(is_simulated", connection.cursor_instance.sql)

    def test_given_large_gangtise_result_when_async_job_completes_then_json_is_not_truncated(self):
        large_answer = "正式复盘内容。" * 2200
        existing_job = {"result": {"partial_text": "已返回的部分分析"}}
        with mock.patch("src.domain.core_services.get_user_async_job", return_value=existing_job), mock.patch(
            "src.domain.core_services.update_user_async_job"
        ) as update_job:
            with app_entry.app.app_context():
                core_services._complete_user_async_job(
                    "review-job-large-result",
                    True,
                    summary="复盘结构化预览完成",
                    result={
                        "watchlist_analysis_section": {
                            "combined_text": large_answer,
                        }
                    },
                )

        saved_result = json.loads(update_job.call_args.kwargs["result_json"])
        self.assertEqual(
            saved_result["watchlist_analysis_section"]["combined_text"],
            large_answer,
        )

    def test_given_h5_review_file_input_when_uploaded_then_real_parser_handoff_exists(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("input.accept = '.pdf,.docx,.xlsx,.xlsm", html)
        self.assertIn("/api/kol/knowledge/file-preview", html)
        self.assertIn("new FormData()", html)
        self.assertIn("文件已解析为文本，可继续编辑后生成 Draft", html)
        self.assertNotIn("系统已从上传文件提炼文案：行业层面保留 AI 算力", html)

    def test_given_new_review_when_opened_on_h5_and_workbench_then_previous_input_is_not_reused(self):
        h5 = self.client.get(f"/h5?tenant={self.tenant_slug}").get_data(as_text=True)
        workbench = self.client.get(f"/kol-workbench?tenant={self.tenant_slug}").get_data(as_text=True)
        for html in (h5, workbench):
            self.assertIn("selectedWatchlist = []", html)
            self.assertIn("fileText = ''", html)
        self.assertIn("Previous content remains available in", h5)
        self.assertIn("every new review starts with an", workbench)

    def test_given_review_without_watchlist_when_preview_is_composed_then_watchlist_analysis_is_skipped(self):
        summary_result = {
            "summary": "仅根据上传材料归纳市场主线和风险边界。",
            "llm_model": {"stage": "user_input_summary", "model_name": "demo-summary"},
        }
        with patch("src.domain.ai_services.summarize_review_user_input_with_llm", return_value=summary_result), patch(
            "src.domain.ai_services.analyze_review_watchlist_with_llm"
        ) as watchlist_mock:
            preview = ai_services.compose_review_structured_preview(
                source_text="上传材料：本期重点观察订单兑现和风险边界。",
                review_period="day",
                source_mode="file",
                selected_watchlist=[],
                speaker_name="财经老王",
                entry_point="test_review_file_without_watchlist",
                tenant_slug=self.tenant_slug,
            )

        watchlist_mock.assert_not_called()
        self.assertEqual(preview["review_summary"], summary_result["summary"])
        self.assertEqual(preview["watchlist_analysis_section"]["items"], [])
        self.assertNotIn("自选股归纳分析", preview["final_text"])

    def test_given_h5_review_preview_when_rendered_then_preview_uses_article_detail_view(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("这是发布前的最终预览。当前阅读态会尽量贴近普通用户和大V最终看到的详情展示。", html)
        self.assertIn("reviewTriggerDraft.flowStage !== 'preview'", html)
        self.assertIn("renderReviewArticleDetailContent(article, { previewMode: true })", html)

    def test_given_h5_when_review_file_or_url_is_processed_then_editor_handoff_logic_exists(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("reviewTriggerDraft.manualHtml = mergePlainTextIntoRichHtml(reviewTriggerDraft.manualHtml || '', reviewTriggerDraft.fileText || '');", html)
        self.assertIn("{ value: 'url', icon: '🔗', label: '网页 URL'", html)
        self.assertIn("async function previewReviewUrl()", html)
        self.assertIn("fetch('/api/kol/knowledge/url-preview'", html)
        self.assertIn("reviewTriggerDraft.manualHtml = mergePlainTextIntoRichHtml(reviewTriggerDraft.manualHtml || '', extractedText);", html)
        self.assertIn("reviewTriggerDraft.sourceMode = 'manual';", html)
        self.assertIn("knowledgeIntakeType = 'manual';", html)
        self.assertIn("knowledgeDraft.bodyHtml = mergePlainTextIntoRichHtml(knowledgeDraft.bodyHtml || '', effectiveBody);", html)

    def test_given_workbench_when_review_file_or_url_is_processed_then_editor_handoff_logic_exists(self):
        response = self.client.get(f"/kol-workbench?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("kwReviewDraft.manualHtml = kwMergePlainTextIntoKnowledgeHtml(kwReviewDraft.manualHtml || '', kwReviewDraft.fileText || '');", html)
        self.assertIn("kwReviewDraft.manualHtml = kwMergePlainTextIntoKnowledgeHtml(kwReviewDraft.manualHtml || '', extractedText);", html)
        self.assertIn("kwReviewDraft.sourceMode = 'manual';", html)
        self.assertIn("kwReviewDraft.flowStage = 'intake';", html)
        self.assertIn("kwKnowledgeIntakeType = 'manual';", html)
        self.assertIn("kwKnowledgeDraft.rawHtml = kwMergePlainTextIntoKnowledgeHtml(kwKnowledgeDraft.rawHtml || '', nextBody);", html)

    def test_given_workbench_review_when_page_renders_then_manual_review_title_field_and_publish_payload_exist(self):
        response = self.client.get(f"/kol-workbench?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="kw-review-title-input"', html)
        self.assertIn("review_title: String(kwReviewDraft.reviewTitle || '').trim()", html)
        self.assertIn("showToast('请先填写复盘主题')", html)

    def test_given_h5_publish_success_when_page_renders_then_publish_no_longer_opens_test_modal(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn("openReviewIngestResultModal('确认发布成功，已写入向量库'", html)

    def test_given_h5_review_when_page_renders_then_optional_watchlist_is_not_preselected(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("kolSelectedWatchlist: []", html)
        self.assertIn("function hasReviewWatchlistAnalysisContent(section)", html)
        self.assertIn("coverTitle: deriveReviewCoverTitle(review)", html)
        self.assertIn("证据链总结", html)
        self.assertNotIn("模型记录", html)
        self.assertIn("syncPublishedReviewStateToH5((user && user.tenant && user.tenant.slug) || '', publishResult);", html)

    def test_given_exact_stock_search_in_review_stage_two_then_candidate_is_added_and_selected(self):
        """A precise name/code lookup must become a checked analysis item without another click."""
        h5 = (PROJECT_ROOT / "templates" / "h5.html").read_text(encoding="utf-8")
        workbench = (PROJECT_ROOT / "templates" / "kol_workbench.html").read_text(encoding="utf-8")

        for html, state_name, add_function in (
            (h5, "reviewWatchlistAddedItems", "addReviewWatchlistCandidate"),
            (workbench, "kwReviewWatchlistAddedItems", "kwAddReviewWatchlistCandidate"),
        ):
            with self.subTest(state_name=state_name):
                self.assertIn(f"let {state_name} = [];", html)
                self.assertIn("const displayItems = [", html)
                self.assertIn("...addedItems.filter", html)
                self.assertIn(f"if (exact) {add_function}(", html)
                self.assertIn("next.add(actualName);", html)
                self.assertIn("type=\"checkbox\" ${selected", html)

    def test_given_h5_review_stage_two_then_candidates_are_read_from_the_current_user_watchlist(self):
        html = (PROJECT_ROOT / "templates" / "h5.html").read_text(encoding="utf-8")
        self.assertIn("getCurrentUserWatchlistItems()", html)
        self.assertIn("这里只显示当前用户在自选股板块中已保存的股票", html)
        self.assertIn("if (!userWatchlistLoaded) return [];", html)
        self.assertNotIn("tenant_lw: ['中芯国际', '腾讯控股', '贵州茅台', '宁德时代', '招商银行', '寒武纪', '比亚迪']", html)

        workbench = (PROJECT_ROOT / "templates" / "kol_workbench.html").read_text(encoding="utf-8")
        self.assertIn("getKwTenantWatchlistItems()", workbench)
        self.assertIn("这里只显示当前大V在自选股板块中已保存的股票", workbench)
        self.assertIn('"watchlist_items": watchlist_items', (PROJECT_ROOT / "src/domain/workbench_services.py").read_text(encoding="utf-8"))

    def test_given_sector_summary_rule_when_refining_then_llm_receives_rule_and_output_is_limited(self):
        captured = {}

        def fake_call(model_config, system_prompt, user_prompt, **kwargs):
            captured["model_config"] = model_config
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return "板块现状：" + ("结构清晰内容。" * 300)

        model = {
            "key": "deepseek-v4-flash",
            "label": "DeepSeek V4 Flash",
            "provider": "volcengine",
            "model_name": "deepseek-v4-flash-ga-260731",
            "purpose": "general",
        }
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services, "call_openai_compatible_llm", side_effect=fake_call
        ):
            result = ai_services.refine_review_sector_summary_with_llm(
                sector_summary="当前自选股集中在科技与消费板块。",
                sector_profiles=[{"sector": "科技", "stock_names": ["中芯国际"]}],
                watchlist_items=["中芯国际", "贵州茅台"],
                rule_text="分成板块现状、代表个股、风险三段，不要写买卖建议。",
                review_period="day",
                entry_point="bdd_sector_rule",
                tenant_slug=self.tenant_slug,
            )

        self.assertLessEqual(len(result["sector_summary"]), 1000)
        self.assertIn("用户规则约束", captured["user_prompt"])
        self.assertIn("不要写买卖建议", captured["user_prompt"])
        self.assertEqual(result["llm_model"]["stage"], "sector_summary_constraint")

    def test_given_gangtise_text_and_constrained_sector_summary_then_both_are_kept_for_publish(self):
        rendered = ai_services._compose_review_watchlist_analysis_text({
            "combined_text": "Gangtise 多股综合分析正文",
            "sector_summary": "按规则生成的板块归纳总结",
        })
        self.assertIn("Gangtise 多股综合分析正文", rendered)
        self.assertIn("板块归纳：按规则生成的板块归纳总结", rendered)

    def test_given_h5_structured_review_then_sector_summary_rule_control_is_rendered(self):
        html = (PROJECT_ROOT / "templates" / "h5.html").read_text(encoding="utf-8")
        self.assertIn('id="review-structured-sector-summary-rule"', html)
        self.assertIn("应用规则并重新生成", html)
        self.assertIn("async function applyReviewSectorSummaryRule()", html)
        self.assertIn("/api/review/refine-sector-summary", html)
        self.assertIn('maxlength="1000"', html)

    def test_given_h5_review_when_page_renders_then_published_articles_use_current_tenant_pages(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("const articles = buildAllPublishedReviewArticles().slice(0, 3);", html)
        self.assertIn("onclick=\"openReviewArticleList()\">查看全部</button>", html)
        self.assertIn("onclick=\"openReviewArticleDetail('${escapeAttr(article.id)}')\"", html)
        self.assertIn("reviewParams.get('review_view')", html)
        self.assertIn("reviewParams.get('review_id')", html)
        self.assertIn("window.history.pushState({}, '', buildReviewRouteUrl('detail', reviewDetailArticleId))", html)
        self.assertIn("const hasReviewRoute = initialParams.get('review') === 'compose'", html)
        self.assertIn("switchTab(hasReviewRoute ? 'review' : getFirstEnabledTab());", html)
        self.assertIn("if (shouldShowReviewPage && !document.getElementById('page-review')?.classList.contains('active'))", html)
        self.assertIn("const tenantSlug = String(activeUserTenant.slug || activeTenant.slug || '').trim().toLowerCase();", html)
        self.assertIn("return matched ? [buildPublishedReviewArticleFromSnapshot(davUser, matched, period)] : [];", html)
        self.assertNotIn("return matched\n      ? buildPublishedReviewArticleFromSnapshot(davUser, matched, period)\n      : buildKolReviewData(davUser, period);", html)
        self.assertNotIn('id="review-article-modal"', html)

    def test_given_review_cards_when_page_renders_then_each_card_has_one_title_and_real_view_meta(self):
        html = (PROJECT_ROOT / "templates" / "h5.html").read_text(encoding="utf-8")

        self.assertIn('${escapeHtml(article.title)}', html)
        self.assertIn('发布日期 ${escapeHtml(article.publishedAt || article.generatedAt || \'日期未提供\')}', html)
        self.assertIn('阅读量 ${escapeHtml(formatReviewViewCount(article.viewCount))}', html)
        self.assertNotIn('${escapeHtml(article.coverTitle)}</div>\n            <div class="review-article-cover-meta">${escapeHtml(article.meta)}', html)
        self.assertNotIn('<div class="review-article-card-title">${escapeHtml(article.title)}</div>', html)

    def test_given_review_snapshot_when_normalized_then_view_count_is_persisted_and_legacy_views_are_supported(self):
        tenant = {"slug": "bdd", "advisor": "测试大V"}
        normalized = core_services.normalize_review_snapshot_item(
            {"id": "bdd-review-1", "title": "唯一主题", "views": "12"},
            tenant,
            index=0,
        )
        self.assertEqual(normalized["view_count"], 12)

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

    def test_given_hermes_tool_plan_when_web_answer_enabled_then_no_embedding_tool_is_injected(self):
        ordered = ai_services.build_hermes_tool_execution_plan(
            {
                "tools": ["watchlist.detail", "evidence.search", "attachment.context"],
            },
            web_answer=True,
        )

        self.assertEqual(ordered[0], "watchlist.detail")
        self.assertNotIn("knowledge.search", ordered)
        self.assertNotIn("evidence.search", ordered)
        self.assertNotIn("web.search", ordered)
        self.assertIn("watchlist.detail", ordered)
        self.assertIn("attachment.context", ordered)

    def test_given_hermes_tool_plan_when_web_answer_disabled_then_only_platform_tools_run(self):
        ordered = ai_services.build_hermes_tool_execution_plan(
            {
                "tools": ["watchlist.detail"],
            },
            web_answer=False,
        )

        self.assertEqual(ordered, ["watchlist.detail"])

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

    def test_given_indicator_chart_question_when_synthesis_text_is_empty_then_artifact_fails_without_data_fallback(self):
        with self.assertRaisesRegex(RuntimeError, "hermes_indicator_artifact_empty_llm_answer"):
            ai_services.build_hermes_indicator_artifact(
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

    def test_given_scope_guard_synthesis_when_built_then_positive_opening_is_added(self):
        with app_entry.app.app_context():
            synthesis = ai_services.build_hermes_scope_synthesis({
                "intent": "out_of_scope_redirect",
                "scope_status": "redirected",
                "guard_message": "Hermes 主要回答个股/自选股、复盘证据链、知识框架、智能指标和平台功能使用相关问题。你可以换成这些方向继续问。",
                "guard_suggestions": ["可以改问个股 / 自选股基本面。"],
                "question_text": "今天天气怎么样？",
            })

        self.assertTrue(synthesis["answer"].startswith(("这个问题", "你这个提问")))
        self.assertIn("Hermes 主要回答", synthesis["answer"])

    def test_given_plain_synthesis_answer_when_positive_tone_is_enforced_then_opening_is_prefixed(self):
        with app_entry.app.app_context():
            answer = ai_services.ensure_hermes_positive_opening(
                "当前优先基于租户知识库和平台工具给你一个结论。",
                question_text="帮我分析腾讯控股的基本面",
                intent="watchlist_fundamental",
                scope_status="allowed",
            )

        self.assertTrue(answer.startswith("这个问题"))
        self.assertIn("当前优先基于租户知识库和平台工具给你一个结论。", answer)

    def test_given_product_help_question_when_router_model_is_missing_then_request_fails(self):
        with app_entry.app.app_context():
            with patch("src.domain.ai_services.get_default_llm_config", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "hermes_intent_router_llm_not_configured"):
                    ai_services.route_hermes_query_intent(
                        "H5 里的智能指标怎么创建和发布？",
                        tenant_slug=self.tenant_slug,
                    )

    def test_given_smart_indicator_question_when_router_model_is_missing_then_request_fails(self):
        with app_entry.app.app_context():
            with patch("src.domain.ai_services.get_default_llm_config", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "hermes_intent_router_llm_not_configured"):
                    ai_services.route_hermes_query_intent(
                        "这个智能指标是按什么公式和提示词计算出来的？",
                        tenant_slug=self.tenant_slug,
                    )

    def test_given_shanghai_index_alias_when_indicator_hub_is_empty_then_registry_alias_still_resolves(self):
        with app_entry.app.app_context():
            with patch("src.domain.ai_services.build_indicator_hub", return_value={"items": []}):
                match = ai_services.find_indicator_reference_from_text(
                    "我需要上证综合指数的分析",
                    tenant_slug=self.tenant_slug,
                )

        self.assertEqual(match["indicator_code"], "source_shanghai_index")
        self.assertEqual(match["indicator_name"], "上证指数")

    def test_given_shanghai_index_question_when_router_model_is_missing_then_request_fails(self):
        with app_entry.app.app_context():
            with patch("src.domain.ai_services.get_default_llm_config", return_value=None), patch(
                "src.domain.ai_services.build_indicator_hub",
                return_value={"items": []},
            ):
                with self.assertRaisesRegex(RuntimeError, "hermes_intent_router_llm_not_configured"):
                    ai_services.route_hermes_query_intent(
                        "我需要上证综合指数的分析",
                        tenant_slug=self.tenant_slug,
                    )

    def test_given_indicator_not_found_in_hub_when_loading_shanghai_index_then_live_gangtise_detail_is_used(self):
        live_detail = {
            "id": "source_shanghai_index",
            "name": "上证指数",
            "value": "3878.4296",
            "numeric_value": 3878.4296,
            "status": "attention",
            "assessment": "上证指数已通过 Gangtise OpenAPI 获取。",
            "provider": "Gangtise OpenAPI",
            "history_series": [
                {"date": "2026-06-01", "value": 3720.11, "status": "attention"},
                {"date": "2026-07-01", "value": 3808.25, "status": "attention"},
                {"date": "2026-08-05", "value": 3878.4296, "status": "attention"},
            ],
            "history_anomalies": [{"date": "2026-07-18", "label": "放量异动"}],
            "history_kline": {
                "candles": [
                    {"date": "2026-08-03", "open": 3842.0, "high": 3870.0, "low": 3828.0, "close": 3855.0},
                    {"date": "2026-08-04", "open": 3855.0, "high": 3886.0, "low": 3849.0, "close": 3878.4296},
                ],
                "ma5": [],
                "ma10": [],
                "ma20": [],
                "anomalies": [{"date": "2026-07-18", "label": "放量异动"}],
            },
            "data_unavailable": False,
        }
        with app_entry.app.app_context():
            with patch("src.domain.ai_services.build_indicator_hub", return_value={"items": []}), patch(
                "src.domain.ai_services.build_live_gangtise_indicator_detail",
                return_value=live_detail,
            ) as live_detail_mock:
                result = ai_services.hermes_tool_indicator_detail(
                    tenant_slug=self.tenant_slug,
                    question_text="我需要上证综合指数的分析",
                )

        self.assertTrue(result["found"])
        self.assertEqual(result["detail"]["id"], "source_shanghai_index")
        self.assertEqual(result["detail"]["code"], "000001.SH")
        self.assertEqual(result["detail"]["indicator_code"], "source_shanghai_index")
        self.assertEqual(result["detail"]["name"], "上证指数")
        self.assertGreater(len(result["detail"]["history_series"]), 0)
        self.assertGreater(len(result["detail"]["history_kline"]["candles"]), 0)
        live_detail_mock.assert_called_once_with("source_shanghai_index")

    def test_given_stock_kline_question_when_router_model_is_missing_then_request_fails(self):
        with app_entry.app.app_context():
            with patch("src.domain.ai_services.get_default_llm_config", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "hermes_intent_router_llm_not_configured"):
                    ai_services.route_hermes_query_intent(
                        "我想看看中国银行这支股票的K线图以及分析",
                        tenant_slug=self.tenant_slug,
                    )

    def test_given_stock_kline_question_when_calling_hermes_api_then_kline_artifact_contains_chart_and_body(self):
        candles = [
            {"date": "2026-08-14", "open": 5.72, "high": 5.80, "low": 5.68, "close": 5.76},
            {"date": "2026-08-15", "open": 5.76, "high": 5.87, "low": 5.73, "close": 5.84},
            {"date": "2026-08-18", "open": 5.84, "high": 5.96, "low": 5.81, "close": 5.90},
        ]
        live_detail = {
            "code": "601988",
            "name": "中国银行",
            "market": "SH",
            "industry": "银行",
            "price": 5.90,
            "change": 0.06,
            "change_pct": 1.03,
            "kline": copy.deepcopy(candles),
            "history_kline": market_services.build_real_indicator_kline_payload(candles),
            "history_series": [{"date": item["date"], "value": item["close"], "status": "good"} for item in candles],
            "fundamental": {"summary": "Gangtise 返回的中国银行真实日线样本。", "metrics": [], "thesis": []},
            "forecast": {"label": "行情判断", "verdict": "继续跟踪", "confidence": "中", "band": "", "drivers": []},
            "data_source": "gangtise_openapi",
            "data_unavailable": False,
        }
        with app_entry.app.app_context(), patch("src.domain.ai_services.get_default_llm_config", return_value={"key": "mock-llm"}), patch(
            "src.domain.ai_services.call_openai_compatible_llm",
            side_effect=[
                '{"intent":"watchlist_fundamental","tools":["watchlist.detail"],"stock_code":"601988","display_mode":"structured","preferred_mode":"kline_chart","reason":"模型路由"}',
                '{"answer":"模型完成中国银行分析","summary":"模型摘要","lead_conclusion":"模型结论","bullets":["模型判断"],"analysis_sections":[{"title":"业务结构拆解","body":"模型对业务结构的分析"},{"title":"财务分析","body":"模型对财务面的分析"},{"title":"行业视角","body":"模型对行业的分析"},{"title":"估值与预期差","body":"模型对估值的分析"}],"next_steps":["模型建议继续验证"],"confidence":"中","citations":[]}',
            ],
        ), patch(
            "src.domain.ai_services.get_watchlist_detail_by_code", return_value=live_detail
        ), patch(
            "src.domain.ai_services.hermes_tool_knowledge_search", return_value={"matches": [], "answer": ""}
        ):
            response = self.client.post(
                "/api/hermes/query",
                json={
                    "tenant_slug": self.tenant_slug,
                    "user_role": "dav",
                    "user_profile_id": "bdd-hermes-dav",
                    "question": "我想看看中国银行这支股票的K线图以及分析",
                    "messages": [{"role": "user", "content": "我想看看中国银行这支股票的K线图以及分析"}],
                    "preferred_mode": "basic",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        artifact = payload["artifacts"][0]
        self.assertEqual(payload["intent"], "watchlist_fundamental")
        self.assertEqual(payload["display_mode"], "structured")
        self.assertEqual(artifact["type"], "watchlist_analysis")
        self.assertEqual(artifact["symbol"]["code"], "601988")
        self.assertEqual(artifact["chart"]["kind"], "kline")
        self.assertGreater(len(artifact["chart"]["points"]), 0)
        self.assertIn("中国银行", artifact["body"])
        self.assertFalse(artifact["body"].startswith("分析方式偏向"))
        self.assertTrue(artifact.get("lead_conclusion"))
        section_titles = [item.get("title") for item in artifact.get("analysis_sections", [])]
        self.assertIn("业务结构拆解", section_titles)
        self.assertIn("财务分析", section_titles)
        self.assertIn("行业视角", section_titles)
        self.assertIn("估值与预期差", section_titles)

    def test_given_stock_typo_alias_when_router_model_is_missing_then_request_fails(self):
        with app_entry.app.app_context():
            with patch("src.domain.ai_services.get_default_llm_config", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "hermes_intent_router_llm_not_configured"):
                    ai_services.route_hermes_query_intent(
                        "帮我分析日久光新这支股票",
                        tenant_slug=self.tenant_slug,
                    )

    def test_given_index_line_chart_question_when_calling_hermes_api_then_line_artifact_is_returned(self):
        live_detail = {
            "id": "source_shanghai_index",
            "name": "上证指数",
            "value": "3878.43",
            "numeric_value": 3878.43,
            "status": "good",
            "assessment": "上证指数真实历史序列已加载。",
            "provider": "Gangtise OpenAPI",
            "history_series": [
                {"date": "2026-06-01", "value": 3720.11, "status": "attention"},
                {"date": "2026-07-01", "value": 3808.25, "status": "attention"},
                {"date": "2026-08-05", "value": 3878.43, "status": "good"},
            ],
            "history_anomalies": [],
            "history_kline": {"candles": [], "ma5": [], "ma10": [], "ma20": [], "anomalies": []},
            "data_unavailable": False,
        }
        with patch("src.domain.ai_services.get_default_llm_config", return_value={"key": "mock-llm"}), patch(
            "src.domain.ai_services.call_openai_compatible_llm",
            side_effect=[
                '{"intent":"smart_indicator_explain","tools":["indicator.detail"],"indicator_code":"source_shanghai_index","display_mode":"structured","preferred_mode":"trend_chart","reason":"模型路由"}',
                '{"answer":"模型完成指数趋势分析","summary":"模型摘要","bullets":[],"citations":[]}',
            ],
        ), patch(
            "src.domain.ai_services.build_indicator_hub", return_value={"items": []}
        ), patch("src.domain.ai_services.build_live_gangtise_indicator_detail", return_value=live_detail), patch(
            "src.domain.ai_services.hermes_tool_knowledge_search", return_value={"matches": [], "answer": ""}
        ):
            response = self.client.post(
                "/api/hermes/query",
                json={
                    "tenant_slug": self.tenant_slug,
                    "user_role": "dav",
                    "user_profile_id": "bdd-hermes-dav",
                    "question": "请展示最近3个月的上证指数的历史数据线图（单纯的线性趋势图）",
                    "messages": [{"role": "user", "content": "请展示最近3个月的上证指数的历史数据线图（单纯的线性趋势图）"}],
                    "preferred_mode": "basic",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        artifact = payload["artifacts"][0]
        self.assertEqual(artifact["type"], "indicator_analysis")
        self.assertEqual(artifact["chart"]["kind"], "trend")
        self.assertGreater(len(artifact["chart"]["series"]), 0)

    def test_given_specific_date_indicator_detail_when_loading_then_target_snapshot_is_attached(self):
        live_detail = {
            "id": "source_shanghai_index",
            "name": "上证指数",
            "value": "3878.4296",
            "numeric_value": 3878.4296,
            "status": "good",
            "assessment": "上证指数已通过 Gangtise OpenAPI 获取。",
            "provider": "Gangtise OpenAPI",
            "unit": "点",
            "history_series": [
                {"date": "2026-08-03", "value": 3855.0, "status": "attention"},
                {"date": "2026-08-04", "value": 3815.12, "status": "attention"},
                {"date": "2026-08-05", "value": 3878.4296, "status": "good"},
            ],
            "history_anomalies": [],
            "history_kline": {
                "candles": [
                    {"date": "2026-08-03", "open": 3842.0, "high": 3870.0, "low": 3828.0, "close": 3855.0},
                    {"date": "2026-08-04", "open": 3855.0, "high": 3858.0, "low": 3801.0, "close": 3815.12},
                    {"date": "2026-08-05", "open": 3815.12, "high": 3884.4, "low": 3815.12, "close": 3878.4296},
                ],
                "ma5": [],
                "ma10": [],
                "ma20": [],
                "anomalies": [],
            },
            "data_unavailable": False,
        }
        with app_entry.app.app_context():
            with patch("src.domain.ai_services.build_indicator_hub", return_value={"items": []}), patch(
                "src.domain.ai_services.build_live_gangtise_indicator_detail",
                return_value=live_detail,
            ):
                result = ai_services.hermes_tool_indicator_detail(
                    tenant_slug=self.tenant_slug,
                    question_text="我需要知道8月5日的上证指数，帮我做一个分析",
                )

        self.assertTrue(result["found"])
        self.assertEqual(result["detail"]["analysis_scope"], "specific_date")
        self.assertEqual(result["detail"]["target_snapshot"]["matched_date"], "2026-08-05")
        self.assertTrue(result["detail"]["target_snapshot"]["matched_exact"])
        self.assertEqual(result["detail"]["target_snapshot"]["close"], 3878.4296)

    def test_given_specific_date_indicator_question_when_detecting_missing_capability_then_no_gap_is_returned(self):
        missing = ai_services.detect_hermes_missing_capability(
            "我需要知道8月5日的上证指数，帮我做一个分析",
            plan={
                "intent": "smart_indicator_explain",
                "display_mode": "structured",
                "scope_status": "allowed",
            },
            tool_outputs={
                "indicator": {
                    "detail": {
                        "name": "上证指数",
                        "id": "source_shanghai_index",
                    }
                }
            },
        )

        self.assertIsNone(missing)

    def test_given_specific_date_indicator_when_building_rule_synthesis_then_answer_uses_that_day(self):
        synthesis = ai_services.build_hermes_indicator_rule_synthesis(
            question_text="我需要知道2026-08-05的上证指数，帮我做一个分析",
            plan={
                "intent": "smart_indicator_explain",
                "scope_status": "allowed",
            },
            detail={
                "name": "上证指数",
                "unit": "点",
                "target_snapshot": {
                    "target_date": "2026-08-05",
                    "matched_date": "2026-08-05",
                    "matched_exact": True,
                    "close": 3878.4296,
                    "prev_close": 3815.12,
                    "change": 63.3096,
                    "change_pct": 1.66,
                    "high": 3884.4,
                    "low": 3815.12,
                    "status": "good",
                },
            },
        )

        self.assertIn("2026-08-05", synthesis["answer"])
        self.assertIn("3878.4296", synthesis["answer"])
        self.assertIn("单日分析", synthesis["summary"])
        self.assertTrue(synthesis["bullets"])

    def test_given_admin_hermes_usage_rows_when_aggregating_then_missing_capabilities_are_visible(self):
        class _FakeCursor:
            def __init__(self, one=None, rows=None):
                self._one = one or {}
                self._rows = rows or []

            def fetchone(self):
                return self._one

            def fetchall(self):
                return self._rows

        class _FakeDb:
            def execute(self, sql, params):
                normalized = " ".join(str(sql).split())
                if "COUNT(*) AS call_count" in normalized and "COUNT(DISTINCT user_profile_id) AS user_count" in normalized:
                    return _FakeCursor(one={"call_count": 2, "user_count": 2})
                if "FROM token_usage_logs" in normalized and "SUM(request_count)" in normalized:
                    return _FakeCursor(one={"total_tokens": 1200, "request_count": 2, "latency_ms": 400})
                if "FROM token_usage_logs" in normalized and "SUM(total_tokens)" in normalized:
                    return _FakeCursor(one={"total_tokens": 220})
                if "FROM hermes_conversation_turns" in normalized and "question_text" in normalized:
                    return _FakeCursor(rows=[
                        {
                            "user_profile_id": "u1",
                            "user_display_name": "用户A",
                            "user_role": "investor",
                            "entry_point": "hermes_chat",
                            "intent": "smart_indicator_explain",
                            "preferred_mode": "basic",
                            "question_text": "我需要知道8月5日的上证指数，帮我做一个分析",
                            "tool_trace_json": "[]",
                            "tags_json": "{\"function_tags\":[\"指标\"],\"missing_capability_tags\":[\"指定日期指数/指标分析\"]}",
                            "memory_summary_json": "{\"compute_used\":1,\"missing_capability\":{\"code\":\"indicator_specific_date_analysis\",\"label\":\"指定日期指数/指标分析\",\"category\":\"数据分析\",\"target_date\":\"2026-08-05\",\"object_name\":\"上证指数\",\"intent\":\"smart_indicator_explain\"}}",
                            "created_at": "2026-08-05 10:00:00",
                        },
                        {
                            "user_profile_id": "u2",
                            "user_display_name": "用户B",
                            "user_role": "investor",
                            "entry_point": "hermes_chat",
                            "intent": "smart_indicator_explain",
                            "preferred_mode": "basic",
                            "question_text": "我需要知道8月5日的上证指数，帮我做一个分析",
                            "tool_trace_json": "[]",
                            "tags_json": "{\"function_tags\":[\"指标\"],\"missing_capability_tags\":[\"指定日期指数/指标分析\"]}",
                            "memory_summary_json": "{\"compute_used\":1,\"missing_capability\":{\"code\":\"indicator_specific_date_analysis\",\"label\":\"指定日期指数/指标分析\",\"category\":\"数据分析\",\"target_date\":\"2026-08-05\",\"object_name\":\"上证指数\",\"intent\":\"smart_indicator_explain\"}}",
                            "created_at": "2026-08-05 11:00:00",
                        },
                    ])
                raise AssertionError(f"Unexpected SQL: {normalized}")

        with patch("src.domain.ai_services.get_db", return_value=_FakeDb()):
            stats = ai_services.build_admin_hermes_usage_stats(self.tenant_slug)

        self.assertEqual(stats["summary"]["missing_capability_turns"], 2)
        self.assertEqual(stats["summary"]["missing_capability_count"], 1)
        self.assertEqual(stats["missing_capabilities"][0]["label"], "指定日期指数/指标分析")
        self.assertEqual(stats["missing_capabilities"][0]["target_date"], "2026-08-05")
        self.assertEqual(stats["missing_capabilities"][0]["user_count"], 2)

    def test_given_missing_token_usage_table_when_aggregating_then_conversation_usage_remains_available(self):
        class _FakeCursor:
            def __init__(self, one=None, rows=None):
                self._one = one or {}
                self._rows = rows or []

            def fetchone(self):
                return self._one

            def fetchall(self):
                return self._rows

        class _FakeDb:
            def execute(self, sql, params):
                normalized = " ".join(str(sql).split())
                if "FROM token_usage_logs" in normalized:
                    raise RuntimeError("relation token_usage_logs does not exist")
                if "COUNT(*) AS call_count" in normalized:
                    return _FakeCursor(one={"call_count": 1, "user_count": 1})
                if "FROM hermes_conversation_turns" in normalized and "question_text" in normalized:
                    return _FakeCursor(rows=[{
                        "user_profile_id": "u1",
                        "user_display_name": "用户A",
                        "user_role": "investor",
                        "entry_point": "hermes_chat",
                        "intent": "general",
                        "preferred_mode": "basic",
                        "question_text": "请分析贵州茅台",
                        "tool_trace_json": "[]",
                        "tags_json": "{}",
                        "memory_summary_json": "{\"latency_ms\": 800}",
                        "created_at": "2026-08-13 10:00:00",
                    }])
                raise AssertionError(f"Unexpected SQL: {normalized}")

        with patch("src.domain.ai_services.get_db", return_value=_FakeDb()):
            stats = ai_services.build_admin_hermes_usage_stats(self.tenant_slug)

        self.assertEqual(stats["summary"]["month_calls"], 1)
        self.assertFalse(stats["summary"]["token_usage_available"])
        self.assertEqual(stats["summary"]["month_tokens"], 0)

    def test_given_specific_date_indicator_question_when_calling_hermes_api_then_single_day_analysis_is_returned(self):
        live_detail = {
            "id": "source_shanghai_index",
            "name": "上证指数",
            "value": "3878.4296",
            "numeric_value": 3878.4296,
            "status": "good",
            "assessment": "上证指数已通过 Gangtise OpenAPI 获取。",
            "provider": "Gangtise OpenAPI",
            "unit": "点",
            "history_series": [
                {"date": "2026-08-03", "value": 3855.0, "status": "attention"},
                {"date": "2026-08-04", "value": 3815.12, "status": "attention"},
                {"date": "2026-08-05", "value": 3878.4296, "status": "good"},
            ],
            "history_anomalies": [],
            "history_kline": {
                "candles": [
                    {"date": "2026-08-03", "open": 3842.0, "high": 3870.0, "low": 3828.0, "close": 3855.0},
                    {"date": "2026-08-04", "open": 3855.0, "high": 3858.0, "low": 3801.0, "close": 3815.12},
                    {"date": "2026-08-05", "open": 3815.12, "high": 3884.4, "low": 3815.12, "close": 3878.4296},
                ],
                "ma5": [],
                "ma10": [],
                "ma20": [],
                "anomalies": [],
            },
            "data_unavailable": False,
        }
        with patch("src.domain.ai_services.get_default_llm_config", return_value={"key": "mock-llm"}), patch(
            "src.domain.ai_services.call_openai_compatible_llm",
            side_effect=[
                '{"intent":"smart_indicator_explain","tools":["indicator.detail"],"indicator_code":"source_shanghai_index","display_mode":"structured","reason":"模型路由"}',
                '{"answer":"模型基于2026-08-05目标日期数据完成分析","summary":"模型摘要","bullets":[],"citations":[]}',
            ],
        ), patch(
            "src.domain.ai_services.build_indicator_hub",
            return_value={"items": []},
        ), patch(
            "src.domain.ai_services.build_live_gangtise_indicator_detail",
            return_value=live_detail,
        ), patch(
            "src.domain.ai_services.hermes_tool_knowledge_search", return_value={"matches": [], "answer": ""}
        ):
            response = self.client.post(
                "/api/hermes/query",
                json={
                    "tenant_slug": self.tenant_slug,
                    "user_role": "dav",
                    "user_profile_id": "bdd-hermes-day-indicator",
                    "question": "我需要知道8月5日的上证指数，帮我做一个分析",
                    "messages": [{"role": "user", "content": "我需要知道8月5日的上证指数，帮我做一个分析"}],
                    "preferred_mode": "basic",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        artifact = payload["artifacts"][0]
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["missing_capability"])
        self.assertEqual(payload["intent"], "smart_indicator_explain")
        self.assertEqual(payload["display_mode"], "structured")
        self.assertIn("2026-08-05", payload["answer"])
        self.assertEqual(artifact["type"], "indicator_analysis")
        self.assertEqual(artifact["target_snapshot"]["matched_date"], "2026-08-05")
        self.assertEqual(artifact["metrics"][0]["label"], "分析日期")
        self.assertIn("2026-08-05", artifact["body"])

    def test_given_store_snapshot_stops_at_aug_4_when_user_asks_aug_5_then_indicator_detail_refreshes_live(self):
        store_detail = {
            "id": "source_shanghai_index",
            "name": "上证指数",
            "value": "3815.12",
            "numeric_value": 3815.12,
            "status": "attention",
            "assessment": "指标湖缓存快照",
            "provider": "Gangtise OpenAPI",
            "unit": "点",
            "history_series": [
                {"date": "2026-08-03", "value": 3855.0, "status": "attention"},
                {"date": "2026-08-04", "value": 3815.12, "status": "attention"},
            ],
            "history_anomalies": [],
            "history_kline": {
                "candles": [
                    {"date": "2026-08-03", "open": 3842.0, "high": 3870.0, "low": 3828.0, "close": 3855.0},
                    {"date": "2026-08-04", "open": 3855.0, "high": 3858.0, "low": 3801.0, "close": 3815.12},
                ],
                "ma5": [],
                "ma10": [],
                "ma20": [],
                "anomalies": [],
            },
            "data_unavailable": False,
        }
        live_detail = {
            "id": "source_shanghai_index",
            "name": "上证指数",
            "value": "3878.4296",
            "numeric_value": 3878.4296,
            "status": "good",
            "assessment": "Gangtise 实时历史已刷新",
            "provider": "Gangtise OpenAPI",
            "unit": "点",
            "history_series": [
                {"date": "2026-08-03", "value": 3855.0, "status": "attention"},
                {"date": "2026-08-04", "value": 3815.12, "status": "attention"},
                {"date": "2026-08-05", "value": 3878.4296, "status": "good"},
            ],
            "history_anomalies": [],
            "history_kline": {
                "candles": [
                    {"date": "2026-08-03", "open": 3842.0, "high": 3870.0, "low": 3828.0, "close": 3855.0},
                    {"date": "2026-08-04", "open": 3855.0, "high": 3858.0, "low": 3801.0, "close": 3815.12},
                    {"date": "2026-08-05", "open": 3815.12, "high": 3884.4, "low": 3815.12, "close": 3878.4296},
                ],
                "ma5": [],
                "ma10": [],
                "ma20": [],
                "anomalies": [],
            },
            "data_unavailable": False,
        }
        with app_entry.app.app_context():
            with patch("src.domain.ai_services.build_indicator_hub", return_value={"items": [store_detail]}), patch(
                "src.domain.ai_services.build_live_gangtise_indicator_detail",
                return_value=live_detail,
            ):
                result = ai_services.hermes_tool_indicator_detail(
                    tenant_slug=self.tenant_slug,
                    question_text="我需要知道8月5日的上证指数，帮我做一个分析",
                )

        self.assertTrue(result["found"])
        self.assertEqual(result["detail"]["target_snapshot"]["matched_date"], "2026-08-05")
        self.assertEqual(result["detail"]["history_series"][-1]["date"], "2026-08-05")
        self.assertEqual(result["detail"]["history_series"][-1]["value"], 3878.4296)

    def test_given_specific_date_indicator_when_llm_is_configured_then_model_answer_wins(self):
        live_detail = {
            "name": "上证指数",
            "unit": "点",
            "analysis_scope": "specific_date",
            "target_snapshot": {
                "target_date": "2026-08-05",
                "matched_date": "2026-08-05",
                "matched_exact": True,
                "close": 3878.4296,
                "prev_close": 3815.12,
                "change": 63.3096,
                "change_pct": 1.66,
                "high": 3884.4,
                "low": 3815.12,
                "status": "good",
            },
        }
        with app_entry.app.app_context(), patch("src.domain.ai_services.get_default_llm_config", return_value={"key": "mock-llm"}), patch(
            "src.domain.ai_services.call_openai_compatible_llm",
            return_value='{"answer":"模型基于目标日期数据完成分析","summary":"模型摘要","bullets":[],"citations":[]}',
        ) as llm_call:
            synthesis, model, mode = ai_services.synthesize_hermes_answer(
                question_text="我需要知道8月5日的上证指数，帮我做一个分析",
                plan={"intent": "smart_indicator_explain", "scope_status": "allowed"},
                tool_outputs={"indicator": {"detail": live_detail}},
                tenant_slug=self.tenant_slug,
                user_role="dav",
            )

        self.assertIsNotNone(model)
        self.assertEqual(mode, "llm_synthesized")
        self.assertEqual(llm_call.call_count, 1)
        self.assertIn("模型基于目标日期数据", synthesis["answer"])

    def test_given_index_openapi_response_when_parsing_smoke_source_then_indicator_detail_uses_real_rows(self):
        with patch(
            "src.domain.market_services._load_watchlist_cache",
            return_value={
                "provider": "AKShare",
                "points": [
                    {"date": "2026-08-04", "open": 3815.12, "high": 3828.0, "low": 3796.5, "close": 3815.12},
                    {"date": "2026-08-05", "open": 3815.12, "high": 3884.4, "low": 3815.12, "close": 3878.4296},
                ],
            },
        ):
            detail = market_services.build_live_gangtise_indicator_detail("source_shanghai_index")

        self.assertFalse(detail["data_unavailable"])
        self.assertEqual(detail["provider"], "AKShare")
        self.assertEqual(detail["history_series"][-1]["date"], "2026-08-05")
        self.assertEqual(detail["history_series"][-1]["value"], 3878.4296)
        self.assertEqual(detail["source_defs"][0]["method"], "Python SDK")

    def test_given_standard_index_alias_when_normalizing_then_all_common_inputs_hit_same_registry(self):
        cases = {
            "上证指数": "source_shanghai_index",
            "000001.SH": "source_shanghai_index",
            "sh000001": "source_shanghai_index",
            "深证成指": "source_shenzhen_index",
            "399001.SZ": "source_shenzhen_index",
            "中证500": "source_zz500",
            "000905.SH": "source_zz500",
            "中证1000": "source_zz1000",
            "000852.SH": "source_zz1000",
            "中证800": "source_zz800",
            "000906.SH": "source_zz800",
            "中证A500": "source_a500",
            "000510.SH": "source_a500",
            "中证2000": "source_zz2000",
            "932000.CSI": "source_zz2000",
            "日经225": "source_nikkei",
        }

        for raw_value, expected_code in cases.items():
            with self.subTest(raw_value=raw_value):
                self.assertEqual(market_services.normalize_watchlist_indicator_code(raw_value), expected_code)

    def test_given_all_broad_indices_when_searching_and_rendering_then_standard_code_and_intraday_are_available(self):
        index_entries = [
            (code, entry)
            for code, entry in market_services.GANGTISE_INDICATOR_REGISTRY.items()
            if entry.get("query_kind") == "index_kline"
        ]
        self.assertEqual(len(index_entries), 11)
        with patch(
            "src.domain.market_services.attach_watchlist_intraday",
            side_effect=lambda detail: {**detail, "intraday_supported": True},
        ):
            for indicator_code, entry in index_entries:
                with self.subTest(indicator_code=indicator_code):
                    self.assertEqual(
                        market_services.normalize_watchlist_indicator_code(entry["indicator_name"]),
                        indicator_code,
                    )
                    self.assertEqual(
                        market_services.normalize_watchlist_indicator_code(entry["security_code"]),
                        indicator_code,
                    )
                    payload = market_services.normalize_watchlist_detail_from_indicator(
                        {
                            "id": indicator_code,
                            "name": entry["indicator_name"],
                            "numeric_value": 100,
                            "history_series": [{"date": "2026-08-07", "value": 100}],
                        },
                        indicator_code,
                    )
                    self.assertEqual(payload["code"], entry["security_code"])
                    self.assertTrue(payload["intraday_supported"])

    def test_given_generic_index_query_when_searching_then_multiple_standard_indices_are_returned(self):
        items = market_services.search_watchlist_candidates("指数", top=20, include_remote=False)
        codes = {str(item.get("code") or "").strip() for item in items}

        self.assertIn("000001.SH", codes)
        self.assertIn("399001.SZ", codes)
        self.assertIn("000300.SH", codes)
        self.assertIn("000905.SH", codes)
        self.assertIn("000852.SH", codes)

    def test_given_indicator_lake_detail_when_converting_watchlist_payload_then_kline_is_exposed(self):
        indicator_detail = {
            "id": "source_shanghai_index",
            "name": "上证指数",
            "category": "数据湖指标",
            "value": "4093.73",
            "numeric_value": 4093.73,
            "history_series": [
                {"date": "2026-08-04", "value": 4080.30},
                {"date": "2026-08-05", "value": 4093.73},
            ],
            "history_kline": {
                "candles": [
                    {"date": "2026-08-04", "open": 4079.79, "high": 4088.10, "low": 4068.20, "close": 4080.30},
                    {"date": "2026-08-05", "open": 4080.30, "high": 4100.10, "low": 4078.50, "close": 4093.73},
                ],
                "ma5": [],
                "ma10": [],
                "ma20": [],
                "anomalies": [],
            },
        }

        payload = market_services.normalize_watchlist_detail_from_indicator(indicator_detail, "上证指数")

        self.assertEqual(payload["code"], "000001.SH")
        self.assertEqual(payload["indicator_code"], "source_shanghai_index")
        self.assertEqual(payload["name"], "上证指数")
        self.assertEqual(payload["standard_code"], "000001.SH")
        self.assertEqual(payload["tencent_symbol"], "sh000001")
        self.assertTrue(payload["kline"])
        self.assertGreater(payload["price"], 0)

    def test_given_persisted_index_lake_when_opening_index_detail_then_shared_series_is_used(self):
        persisted_detail = {
            "id": "source_shanghai_index",
            "name": "上证指数",
            "value": "4093.73",
            "numeric_value": 4093.73,
            "history_series": [
                {"date": "2026-08-07", "value": 4080.30},
                {"date": "2026-08-10", "value": 4093.73},
            ],
            "history_kline": {
                "candles": [
                    {"date": "2026-08-07", "open": 4079.79, "high": 4088.10, "low": 4068.20, "close": 4080.30},
                    {"date": "2026-08-10", "open": 4080.30, "high": 4100.10, "low": 4078.50, "close": 4093.73},
                ],
                "ma5": [], "ma10": [], "ma20": [], "anomalies": [],
            },
            "data_unavailable": False,
        }
        with patch(
            "src.domain.market_services._load_watchlist_cache",
            return_value={
                "provider": "AKShare",
                "points": [
                    {"date": "2026-08-07", "open": 4079.79, "high": 4088.10, "low": 4068.20, "close": 4080.30},
                    {"date": "2026-08-10", "open": 4080.30, "high": 4100.10, "low": 4078.50, "close": 4093.73},
                ],
            },
        ), patch(
            "src.domain.market_services.build_live_gangtise_indicator_detail",
            side_effect=AssertionError("index detail must not request an external provider"),
        ), patch(
            "src.domain.market_services.attach_watchlist_intraday", side_effect=lambda detail: detail,
        ):
            payload = market_services.build_watchlist_indicator_detail("上证指数")

        self.assertEqual(payload["code"], "000001.SH")
        self.assertEqual(payload["kline"][-1]["date"], "2026-08-10")

    def test_given_market_snapshot_missing_when_opening_dashboard_index_then_indicator_lake_is_used(self):
        lake_item = {
            "id": "source_shanghai_index",
            "name": "上证指数",
            "numeric_value": 3867.03,
            "history_series": [
                {"date": "2026-07-22", "value": 3852.11},
                {"date": "2026-07-23", "value": 3867.03},
            ],
            "history_kline": {
                "candles": [
                    {"date": "2026-07-22", "open": 3840.0, "high": 3860.0, "low": 3830.0, "close": 3852.11},
                    {"date": "2026-07-23", "open": 3852.11, "high": 3875.0, "low": 3845.0, "close": 3867.03},
                ],
            },
        }
        with patch("src.domain.market_services.build_market_overview_index_detail", return_value=None), patch(
            "src.domain.market_services.get_indicator_hub_from_store_cached",
            return_value={"lake_items": [lake_item]},
        ), patch("src.domain.market_services.attach_watchlist_intraday", side_effect=lambda detail: detail):
            payload = market_services.build_watchlist_indicator_detail("source_shanghai_index")

        self.assertEqual(payload["name"], "上证指数")
        self.assertEqual(payload["code"], "000001.SH")
        self.assertEqual(payload["kline"][-1]["close"], 3867.03)

    def test_given_market_closed_when_fetching_index_intraday_then_latest_real_trade_date_is_requested(self):
        detail = {
            "code": "000001.SH",
            "market": "CN",
            "standard_code": "000001.SH",
            "kline": [
                {"date": "2026-08-06", "close": 4050.0},
                {"date": "2026-08-07", "close": 4080.3},
            ],
        }
        expected = {"ok": True, "available": True, "points": [{"date": "2026-08-07 15:00:00", "value": 4080.3}]}
        with patch("src.domain.market_services.is_cn_stock_market_open", return_value=False), patch(
            "src.domain.market_services.fetch_gangtise_intraday_series", return_value=expected
        ) as fetch_mock:
            payload = market_services.fetch_watchlist_intraday_series(detail, allow_provider_fetch=True)

        fetch_mock.assert_called_once_with("000001.SH", trade_date="2026-08-07")
        self.assertTrue(payload["available"])
        self.assertEqual(payload["points"][-1]["date"], "2026-08-07 15:00:00")

    def test_given_market_index_intraday_cache_missing_then_akshare_refills_it_before_gangtise(self):
        detail = {
            "id": "source_shanghai_index",
            "indicator_code": "source_shanghai_index",
            "code": "000001.SH",
            "standard_code": "000001.SH",
            "market": "CN",
            "kline": [{"date": "2026-08-10", "close": 3867.03}],
        }
        akshare_result = {
            "ok": True,
            "available": True,
            "points": [{"date": "2026-08-10 09:31:00", "value": 3867.03}],
            "source": "AKShare",
        }
        with patch("src.domain.market_services._load_watchlist_cache", return_value=None), patch(
            "src.domain.market_services._load_gangtise_intraday_snapshot", return_value=None
        ), patch("src.domain.market_services.fetch_akshare_market_index_intraday", return_value=akshare_result) as akshare_fetch, patch(
            "src.domain.market_services._save_watchlist_cache"
        ) as save_cache, patch("src.domain.market_services.fetch_gangtise_intraday_series", side_effect=AssertionError("AKShare should satisfy the index request")):
            payload = market_services.fetch_watchlist_intraday_series(detail, allow_provider_fetch=True)

        akshare_fetch.assert_called_once_with("source_shanghai_index", trade_date="2026-08-10")
        save_cache.assert_called_once_with("market_index_intraday", "source_shanghai_index", akshare_result)
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "AKShare")

    def test_given_gangtise_minute_response_when_fetching_intraday_then_points_are_normalized(self):
        response = {
            "code": "000000",
            "status": True,
            "data": {
                "fieldList": ["securityCode", "securityName", "tradeTime", "open", "high", "low", "close", "volume"],
                "list": [
                    ["600519.SH", "贵州茅台", "2026-08-10 09:31:00", 1688.20, 1689.10, 1687.30, 1688.20, 1000],
                    ["600519.SH", "贵州茅台", "2026-08-10 09:32:00", 1688.20, 1691.10, 1688.00, 1690.10, 1200],
                ],
            },
        }

        points = market_services.normalize_gangtise_minute_points(response)

        self.assertEqual(points, [
            {"date": "2026-08-10 09:31:00", "value": 1688.2},
            {"date": "2026-08-10 09:32:00", "value": 1690.1},
        ])

    def test_given_daily_rows_in_intraday_cache_when_opening_watchlist_then_cache_is_rejected(self):
        cached = {
            "points": [
                {"date": "2026-08-17", "value": 5.72},
                {"date": "2026-08-18", "value": 5.90},
            ],
        }
        with patch("src.domain.market_services._load_watchlist_cache", return_value=cached):
            payload = market_services._load_gangtise_intraday_snapshot("601988.SH", "2026-08-18")

        self.assertIsNone(payload)

    def test_given_minute_response_with_daily_rows_when_fetching_intraday_then_daily_rows_are_not_rendered(self):
        response = {
            "code": "000000",
            "status": True,
            "data": {
                "fieldList": ["securityCode", "tradeTime", "close"],
                "list": [
                    ["601988.SH", "2026-08-17", 5.72],
                    ["601988.SH", "2026-08-18", 5.90],
                ],
            },
        }

        points = market_services.normalize_gangtise_minute_points(response, trade_date="2026-08-18")

        self.assertEqual(points, [])

    def test_given_intraday_request_when_fetching_real_series_then_gangtise_source_is_used(self):
        response = {
            "code": "000000",
            "status": True,
            "data": {
                "fieldList": ["securityCode", "securityName", "tradeTime", "open", "high", "low", "close", "volume"],
                "list": [
                    ["600519.SH", "贵州茅台", "2026-08-10 09:31:00", 1688.20, 1689.10, 1687.30, 1688.20, 1000],
                    ["600519.SH", "贵州茅台", "2026-08-10 09:32:00", 1688.20, 1691.10, 1688.00, 1690.10, 1200],
                ],
            },
        }

        captured_payloads = []

        def fake_post(path, payload, token="", timeout=30):
            captured_payloads.append(payload)
            return 200, response, 123

        with patch("src.domain.market_services._load_watchlist_cache", return_value=None), patch(
            "src.domain.market_services._save_watchlist_cache", return_value=None
        ), patch("src.domain.market_services.post_gangtise_openapi_json", side_effect=fake_post):
            payload = market_services.fetch_gangtise_intraday_series("600519.SH", trade_date="2026-08-10")

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "gangtise_openapi")
        self.assertEqual(payload["points"][-1]["value"], 1690.1)
        self.assertEqual(captured_payloads[0]["securityCode"], "600519.SH")

    def test_given_maotai_detail_when_resolving_intraday_symbol_then_gangtise_standard_code_is_used(self):
        detail = {
            "code": "600519",
            "name": "贵州茅台",
            "market": "SH",
            "standard_code": "600519.SH",
            "tencent_symbol": "sh600519",
        }

        symbol = market_services._resolve_watchlist_intraday_symbol(detail)

        self.assertEqual(symbol, "600519.SH")

    def test_given_intraday_detail_when_attaching_then_real_series_is_kept_without_market_open_gate(self):
        detail = {
            "code": "600519",
            "name": "贵州茅台",
            "market": "SH",
            "standard_code": "600519.SH",
            "tencent_symbol": "sh600519",
        }
        intraday_points = [
            {"date": "09:31", "value": 1688.20},
            {"date": "09:32", "value": 1690.10},
        ]

        with patch("src.domain.market_services.is_cn_stock_market_open", return_value=False), patch(
            "src.domain.market_services.fetch_watchlist_intraday_series",
            return_value={"available": True, "points": intraday_points, "message": "ok", "updated_at": "2026-08-10 09:32:00", "source": "gangtise_openapi"},
        ):
            payload = market_services.attach_watchlist_intraday(detail)

        self.assertTrue(payload["intraday_available"])
        self.assertEqual(payload["intraday_series"], intraday_points)
        self.assertEqual(payload["intraday_source"], "gangtise_openapi")
        self.assertTrue(payload["intraday_supported"])

    def test_given_market_overview_index_when_opening_detail_then_intraday_is_disabled(self):
        detail = {
            "indicator_code": "source_shanghai_index",
            "code": "000001.SH",
            "market": "CN",
            "standard_code": "000001.SH",
            "kline": [{"date": "2026-08-10", "close": 4093.73}],
        }
        with patch("src.domain.market_services.fetch_gangtise_intraday_series") as fetch_mock:
            payload = market_services.attach_watchlist_intraday(detail)

        fetch_mock.assert_not_called()
        self.assertFalse(payload["intraday_supported"])
        self.assertFalse(payload["intraday_available"])
        self.assertEqual(payload["intraday_message"], "market_overview_intraday_disabled")

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
            json={"tenant_slug": self.tenant_slug, "user_role": "dav", "question": "请解释这个智能指标的计算口径"},
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
            json={"tenant_slug": self.tenant_slug, "user_role": "dav", "question": "帮我推荐一个上海周末亲子旅游行程"},
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
        self.assertGreaterEqual(payload["synced_model_count"], 1)
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

    def test_given_existing_llm_registry_when_normalized_then_builtin_gemma4_model_is_appended(self):
        config = normalize_site_config({
            "llm_registry": {
                "default_model_key": "custom-general",
                "models": [
                    {
                        "key": "custom-general",
                        "label": "Custom General",
                        "provider": "openai",
                        "model_name": "custom-model",
                        "base_url": "http://custom/v1",
                        "api_key": "custom-key",
                        "purpose": "general",
                        "enabled": True,
                    }
                ],
            }
        })

        models = config["llm_registry"]["models"]
        self.assertTrue(any(model["key"] == "custom-general" for model in models))
        self.assertTrue(any(model["key"] == "gangtise-gemma4-31b-q4km" for model in models))
        builtin = next(model for model in models if model["key"] == "gangtise-gemma4-31b-q4km")
        self.assertEqual(builtin["model_name"], "gemma4:31b-it-q4_K_M")
        self.assertEqual(builtin["base_url"], "http://8.155.160.194:6031/api")

    def test_given_existing_llm_registry_when_normalized_then_builtin_gemma4_12b_model_is_appended(self):
        config = normalize_site_config({
            "llm_registry": {
                "default_model_key": "custom-general",
                "models": [
                    {
                        "key": "custom-general",
                        "label": "Custom General",
                        "provider": "openai",
                        "model_name": "custom-model",
                        "base_url": "http://custom/v1",
                        "api_key": "custom-key",
                        "purpose": "general",
                        "enabled": True,
                    }
                ],
            }
        })

        models = config["llm_registry"]["models"]
        self.assertTrue(any(model["key"] == "gangtise-gemma4-12b-bf16" for model in models))
        builtin = next(model for model in models if model["key"] == "gangtise-gemma4-12b-bf16")
        self.assertEqual(builtin["model_name"], "gemma4:12b-it-bf16")
        self.assertEqual(builtin["base_url"], "http://8.155.160.194:6031/api")

    def test_given_default_llm_registry_when_normalized_then_deepseek_v4_flash_is_default(self):
        config = core_services.normalize_site_config({})
        registry = config["llm_registry"]
        model = next(item for item in registry["models"] if item["key"] == "volcengine-deepseek-v4-flash")
        self.assertEqual(registry["default_model_key"], "volcengine-deepseek-v4-flash")
        self.assertEqual(model["model_name"], "deepseek-v4-flash-ga-260731")
        self.assertEqual(model["base_url"], "https://ark.cn-beijing.volces.com/api/v3")
        self.assertEqual(model["provider"], "volcengine")

    def test_given_default_site_config_when_normalized_then_all_features_use_admin_default_model(self):
        config = normalize_site_config({})

        registry = config["llm_registry"]
        selected = ai_services.get_default_llm_config(
            site_config=config,
            purpose="general",
            feature_code="review_voice_enhancement",
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected["key"], registry["default_model_key"])
        self.assertEqual(selected["base_url"], "http://8.155.160.194:6031/api")

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
        self.assertIn("/api/review/publish", html)

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
        self.assertIn("published.cards.slice(0, getDashboardCardTarget(layout))", html)
        self.assertIn("if (!rawCard.isEmpty && (rawCard.name || rawCard.value || rawCard.assessment || rawCard.prompt)) return rawCard;", html)
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

    def test_given_2x3_dashboard_with_empty_slots_when_normalized_then_slot_positions_are_preserved(self):
        normalized = normalize_fund_dashboard_card_refs(
            [
                {"indicatorCode": "market_strength"},
                {"indicatorCode": "industry_heat"},
                {},
                {"indicatorCode": "risk_signal"},
                {},
                {"indicatorCode": "new_indicator"},
            ],
            "2x3",
        )

        self.assertEqual(len(normalized), 6)
        self.assertEqual(normalized[0], {"indicatorCode": "market_strength"})
        self.assertEqual(normalized[2], {})
        self.assertEqual(normalized[5], {"indicatorCode": "new_indicator"})

    def test_given_legacy_placeholder_when_normalized_then_it_remains_an_empty_slot(self):
        normalized = normalize_fund_dashboard_card_refs(
            [{"name": "待添加智能指标 1", "value": "--", "isEmpty": False}],
            "2x3",
        )

        self.assertEqual(normalized[0], {})
        self.assertEqual(len(normalized), 6)

    def test_given_two_new_smart_indicators_when_codes_are_created_then_their_identities_differ(self):
        with patch("src.domain.core_services.now_ts_ms", side_effect=["2026-08-13 10:00:00.001", "2026-08-13 10:00:00.002"]):
            first = build_new_smart_indicator_code("laowang")
            second = build_new_smart_indicator_code("laowang")

        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("laowang_smart_"))

    def test_given_five_dashboard_cards_with_legacy_2x2_layout_when_normalized_then_layout_expands_to_2x3(self):
        tenant = {"slug": "laowang", "advisor": "财经老王"}
        cards = [{"indicatorCode": f"indicator_{index}"} for index in range(5)]
        with patch("src.domain.core_services.build_indicator_hub", return_value={"smart_items": [], "lake_items": []}):
            normalized = normalize_fund_dashboard_view({"layout": "2x2", "cards": cards}, tenant)

        self.assertEqual(normalized["layout"], "2x3")
        self.assertEqual(len(normalized["cards"]), 6)

    def test_given_h5_when_page_renders_then_fan_stock_observation_uses_sector_chart(self):
        response = self.client.get(f"/h5?tenant={self.tenant_slug}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="wb-fan-stock-sector-chart"', html)
        self.assertIn("function renderFanStockSectorChart()", html)
        self.assertIn("function openFanStockInsightStock(stockCode)", html)
        self.assertIn("按评论看行业板块分布", html)
        self.assertIn('id="wb-fan-stock-sector-bar"', html)
        self.assertIn("function buildWorkbenchBarChartFallbackMarkup", html)
        self.assertIn('role="img"', html)
        self.assertIn('src="/static/echarts.min.js"', html)
        self.assertIn("if (typeof syncHeaderContext === 'function')", html)
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

    def test_given_unknown_but_valid_stock_code_when_requesting_watchlist_detail_then_no_synthetic_market_data_is_returned(self):
        response = self.client.get("/api/watchlist/601988")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["code"], "601988")
        self.assertEqual(payload["name"], "中国银行")
        self.assertEqual(payload["market"], "SH")
        self.assertEqual(payload.get("kline"), [])
        self.assertTrue(payload.get("data_unavailable"))
        self.assertIsNone(payload.get("price"))
        self.assertTrue(payload.get("fundamental", {}).get("summary"))

    def test_given_gangtise_kline_with_future_trade_date_when_normalizing_then_future_row_is_excluded(self):
        response = {
            "data": {
                "fieldList": ["securityCode", "tradeDate", "open", "high", "low", "close"],
                "list": [
                    ["601988.SH", "2026-08-18", 5.85, 5.96, 5.81, 5.90],
                    ["601988.SH", "2026-08-19", 5.91, 6.02, 5.86, 5.98],
                ],
            },
        }

        points = market_services.normalize_gangtise_kline_points(response, max_trade_date="2026-08-18")

        self.assertEqual([item["date"] for item in points], ["2026-08-18"])

    def test_given_future_end_date_when_fetching_gangtise_kline_then_request_and_rows_are_capped_at_today(self):
        response = {
            "code": "0",
            "status": True,
            "data": {
                "fieldList": ["securityCode", "tradeDate", "open", "high", "low", "close"],
                "list": [
                    ["601988.SH", "2026-08-18", 5.85, 5.96, 5.81, 5.90],
                    ["601988.SH", "2026-08-19", 5.91, 6.02, 5.86, 5.98],
                ],
            },
        }
        with patch("src.domain.market_services._current_cn_market_date", return_value=date(2026, 8, 18)), patch(
            "src.domain.market_services.post_gangtise_openapi_json", return_value=(200, response, 12)
        ):
            result = market_services.fetch_gangtise_market_kline_series(
                "/application/open-quote/kline/daily",
                "601988.SH",
                start_date="2026-08-01",
                end_date="2026-08-19",
            )

        self.assertEqual(result["payload"]["endDate"], "2026-08-18")
        self.assertEqual([item["date"] for item in result["points"]], ["2026-08-18"])

    def test_given_cached_watchlist_with_future_candle_when_loading_then_cache_is_rejected(self):
        with patch("src.domain.market_services._current_cn_market_date", return_value=date(2026, 8, 18)):
            invalid = market_services._watchlist_detail_has_future_kline(
                {"history_kline": {"candles": [{"date": "2026-08-19", "close": 5.98}]}}
            )

        self.assertTrue(invalid)

    def test_given_unavailable_stock_quote_when_building_detail_then_price_and_kline_are_not_simulated(self):
        payload = market_services._build_watchlist_unavailable_detail(
            {"code": "601988", "name": "中国银行", "price": 5.65, "kline": [{"date": "08-19", "close": 6.17}]},
            stock_code="601988",
            stock_name="中国银行",
        )

        self.assertTrue(payload["data_unavailable"])
        self.assertIsNone(payload["price"])
        self.assertEqual(payload["kline"], [])
        self.assertEqual(payload["history_kline"]["candles"], [])

    def test_given_unavailable_watchlist_quote_when_building_market_cards_then_price_is_not_rendered_as_zero(self):
        unavailable_detail = {
            "code": "600519",
            "name": "贵州茅台",
            "market": "SH",
            "industry": "高端白酒",
            "price": None,
            "change": None,
            "change_pct": None,
            "data_unavailable": True,
            "authors": [],
            "fundamental": {"summary": "暂无真实行情", "metrics": [], "thesis": []},
        }
        with app_entry.app.app_context(), patch(
            "src.domain.market_services.gen_watchlist_details", return_value={"600519": unavailable_detail}
        ):
            payload = market_services.gen_market_data()

        maotai = next(item for item in payload if item["code"] == "600519")
        self.assertIsNone(maotai["value"])
        self.assertIsNone(maotai["change"])
        self.assertIsNone(maotai["change_pct"])

    def test_given_empty_user_watchlist_when_building_fundamental_boards_then_no_demo_stock_is_rendered(self):
        boards = market_services.gen_feed_boards_from_watchlist_details({})

        self.assertEqual(boards, [])

    def test_given_unavailable_watchlist_item_when_building_fundamental_boards_then_it_is_excluded(self):
        boards = market_services.gen_feed_boards_from_watchlist_details({
            "600519": {
                "code": "600519",
                "name": "贵州茅台",
                "industry": "高端白酒",
                "price": None,
                "change": None,
                "change_pct": None,
                "data_unavailable": True,
            }
        })

        self.assertEqual(boards, [])

    def test_given_a_user_removes_the_final_watchlist_item_when_listing_then_the_user_watchlist_is_empty(self):
        tenant_slug = self.tenant_slug

        class _Cursor:
            def __init__(self, rows=None, rowcount=0):
                self._rows = rows or []
                self.rowcount = rowcount

            def fetchall(self):
                return self._rows

        class _FakeDb:
            def __init__(self):
                self.rows = [{
                    "id": 1,
                    "tenant_slug": tenant_slug,
                    "user_profile_id": "fan_a",
                    "stock_code": "600519",
                    "stock_name": "贵州茅台",
                    "market": "SH",
                    "industry": "高端白酒",
                    "created_at": "2026-08-19 09:00:00",
                    "updated_at": "2026-08-19 09:00:00",
                }]

            def execute(self, sql, params=()):
                if sql.strip().startswith("DELETE FROM user_watchlist_items"):
                    before = len(self.rows)
                    self.rows = [row for row in self.rows if not (
                        row["tenant_slug"] == params[0] and row["user_profile_id"] == params[1] and row["stock_code"] == params[2]
                    )]
                    return _Cursor(rowcount=before - len(self.rows))
                return _Cursor(rows=list(self.rows))

            def commit(self):
                return None

        db = _FakeDb()
        with patch("src.domain.market_services.get_db", return_value=db):
            deleted = market_services.remove_user_watchlist_item(tenant_slug, "fan_a", "600519")
            items = market_services.list_user_watchlist_items(tenant_slug, "fan_a")

        self.assertTrue(deleted)
        self.assertEqual(items, [])

    def test_given_two_users_when_one_removes_a_stock_then_the_other_users_watchlist_is_unchanged(self):
        tenant_slug = self.tenant_slug

        class _Cursor:
            def __init__(self, rows=None, rowcount=0):
                self._rows = rows or []
                self.rowcount = rowcount

            def fetchall(self):
                return self._rows

        class _FakeDb:
            def __init__(self):
                self.rows = [
                    {"id": 1, "tenant_slug": tenant_slug, "user_profile_id": "fan_a", "stock_code": "600519", "stock_name": "贵州茅台", "market": "SH", "industry": "高端白酒", "created_at": "2026-08-19 09:00:00", "updated_at": "2026-08-19 09:00:00"},
                    {"id": 2, "tenant_slug": tenant_slug, "user_profile_id": "fan_b", "stock_code": "600519", "stock_name": "贵州茅台", "market": "SH", "industry": "高端白酒", "created_at": "2026-08-19 09:00:00", "updated_at": "2026-08-19 09:00:00"},
                ]

            def execute(self, sql, params=()):
                if sql.strip().startswith("DELETE FROM user_watchlist_items"):
                    before = len(self.rows)
                    self.rows = [row for row in self.rows if not (
                        row["tenant_slug"] == params[0] and row["user_profile_id"] == params[1] and row["stock_code"] == params[2]
                    )]
                    return _Cursor(rowcount=before - len(self.rows))
                owner_rows = [row for row in self.rows if row["tenant_slug"] == params[0] and row["user_profile_id"] == params[1]]
                return _Cursor(rows=owner_rows)

            def commit(self):
                return None

        db = _FakeDb()
        live_detail = {"code": "600519", "name": "贵州茅台", "price": 1200, "change": 2, "change_pct": 0.2, "industry": "高端白酒"}
        with patch("src.domain.market_services.get_db", return_value=db), patch(
            "src.domain.market_services.get_watchlist_detail_by_code", return_value=live_detail
        ):
            market_services.remove_user_watchlist_item(tenant_slug, "fan_a", "600519")
            remaining = market_services.list_user_watchlist_items(tenant_slug, "fan_b")

        self.assertEqual([item["code"] for item in remaining], ["600519"])

    def test_given_watchlist_list_request_when_client_supplies_another_user_then_authenticated_owner_is_used(self):
        authenticated_owner = {
            "username": "fan_owner",
            "role": "investor",
            "tenant_slug": self.tenant_slug,
        }
        with patch("src.web.api_core.get_current_authenticated_user", return_value=authenticated_owner), patch(
            "src.web.api_core.list_user_watchlist_items", return_value=[]
        ) as list_items:
            response = self.client.get(
                "/api/watchlist/items?tenant_slug=another_tenant&user_profile_id=another_user"
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        list_items.assert_called_once_with(self.tenant_slug, "fan_owner")

    def test_given_legacy_database_without_watchlist_table_when_loading_then_runtime_schema_guard_creates_it(self):
        class _Cursor:
            def __init__(self, statements):
                self.statements = statements

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, statement):
                self.statements.append(statement)

        class _Connection:
            def __init__(self):
                self.statements = []

            def cursor(self):
                return _Cursor(self.statements)

            def commit(self):
                self.committed = True

        class _Db:
            def __init__(self, connection):
                self._connection = connection

        connection = _Connection()
        with patch.object(market_services, "_user_watchlist_schema_targets", set()):
            market_services._ensure_user_watchlist_items_table(_Db(connection))

        self.assertTrue(connection.committed)
        self.assertEqual(len(connection.statements), 3)
        self.assertIn("CREATE TABLE IF NOT EXISTS user_watchlist_items", connection.statements[0])
        self.assertIn("uq_user_watchlist_items_owner_stock", connection.statements[1])

    def test_given_missing_gangtise_credentials_when_admin_diagnoses_market_data_then_the_reason_is_explicit(self):
        with patch("src.domain.market_services.get_gangtise_openapi_config", return_value={"base_url": "https://openapi.gangtise.com", "access_key": "", "secret_key": "", "long_token": ""}):
            diagnostic = market_services.build_gangtise_market_runtime_diagnostic()

        self.assertFalse(diagnostic["ok"])
        self.assertEqual(diagnostic["status"], "credentials_missing")

    def test_given_local_alias_name_when_requesting_watchlist_detail_then_metadata_is_returned_without_synthetic_quote(self):
        with app_entry.app.app_context():
            payload = market_services.get_watchlist_detail_by_code(stock_code="", stock_name="日久光新")

        self.assertEqual(payload["code"], "003015")
        self.assertEqual(payload["name"], "日久光电")
        self.assertEqual(payload["market"], "SZ")
        self.assertTrue(payload["data_unavailable"])
        self.assertEqual(payload["kline"], [])
        self.assertIsNone(payload.get("price"))

    def test_given_local_alias_name_when_searching_watchlist_then_dropdown_payload_returns_without_remote(self):
        items = market_services.search_watchlist_candidates("日久光新", top=8, include_remote=False)

        self.assertTrue(items)
        self.assertEqual(items[0]["code"], "003015")
        self.assertEqual(items[0]["name"], "日久光电")

    def test_given_common_stock_name_when_searching_watchlist_then_local_candidate_resolves_without_remote(self):
        with patch(
            "src.domain.market_services._search_security_master_candidates",
            return_value=[
                {
                    "code": "601939",
                    "name": "建设银行",
                    "market": "SH",
                    "security_code": "601939.SH",
                    "source": "security_master",
                }
            ],
        ):
            items = market_services.search_watchlist_candidates("建设银行", top=8, include_remote=False)

        self.assertTrue(items)
        self.assertEqual(items[0]["code"], "601939")
        self.assertEqual(items[0]["name"], "建设银行")
        self.assertEqual(items[0]["security_code"], "601939.SH")

    def test_given_security_master_row_when_searching_watchlist_then_database_identity_is_used(self):
        query = mock.Mock()
        query.execute.return_value.fetchall.return_value = [
            {
                "stock_code": "601939",
                "name": "建设银行",
                "market": "SH",
                "security_code": "601939.SH",
                "industry": "银行",
                "security_type": "stock",
                "source": "security_master",
            }
        ]
        with patch("src.domain.market_services.get_db", return_value=query):
            items = market_services._search_security_master_candidates("建设银行")

        self.assertEqual(items[0]["code"], "601939")
        self.assertEqual(items[0]["security_code"], "601939.SH")
        query.execute.assert_called_once()

    def test_given_remote_search_available_when_searching_watchlist_then_gangtise_is_checked_before_master_catalog(self):
        call_order = []

        def remote_candidates(query, top=8):
            call_order.append("gangtise")
            return [{"code": "601939", "name": "建设银行", "market": "SH", "security_code": "601939.SH"}]

        def master_candidates(query, top=8):
            call_order.append("database")
            return [{"code": "601939", "name": "建设银行", "market": "SH", "security_code": "601939.SH"}]

        with patch("src.domain.market_services._search_remote_watchlist_candidates", side_effect=remote_candidates), patch(
            "src.domain.market_services._search_security_master_candidates", side_effect=master_candidates
        ):
            items = market_services.search_watchlist_candidates("建设银行", top=8, include_remote=True)

        self.assertEqual(items[0]["security_code"], "601939.SH")
        self.assertEqual(call_order, ["gangtise"])

    def test_given_direct_watchlist_detail_request_then_catalog_is_not_hydrated_before_gangtise_lookup(self):
        with patch("src.web.api_core.gen_watchlist_details", side_effect=AssertionError("catalog_should_not_be_hydrated")), patch(
            "src.web.api_core.get_watchlist_detail_by_code",
            return_value={
                "code": "601939",
                "name": "建设银行",
                "market": "SH",
                "price": 7.0,
                "change": 0.1,
                "change_pct": 1.45,
                "kline": [{"date": "2026-08-24", "close": 7.0}],
                "authors": [],
                "fundamental": {"summary": "", "metrics": [], "thesis": []},
                "forecast": {},
            },
        ) as detail_lookup:
            response = self.client.get("/api/watchlist/601939")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(detail_lookup.call_args.kwargs["details_map"], {})

    def test_given_empty_shared_quote_cache_when_loading_detail_then_gangtise_fetch_is_retried(self):
        candidate = {"code": "601939", "name": "建设银行", "market": "SH", "security_code": "601939.SH"}
        with patch("src.domain.market_services._load_watchlist_cache", return_value={"data_unavailable": True, "kline": []}), patch(
            "src.domain.market_services._fetch_watchlist_realtime_detail_from_candidate",
            return_value={"code": "601939", "kline": [{"date": "2026-08-23"}, {"date": "2026-08-24"}]},
        ) as fetch_mock:
            payload = market_services._build_watchlist_realtime_detail_from_candidate(candidate)

        self.assertEqual(payload["code"], "601939")
        fetch_mock.assert_called_once_with(candidate, stock_name="")

    def test_given_valid_shared_quote_cache_when_loading_detail_then_gangtise_is_not_called_again(self):
        candidate = {"code": "601939", "name": "建设银行", "market": "SH", "security_code": "601939.SH"}
        cached = {
            "code": "601939",
            "data_unavailable": False,
            "kline": [{"date": "2026-08-23"}, {"date": "2026-08-24"}],
        }
        with patch("src.domain.market_services._load_watchlist_cache", return_value=cached), patch(
            "src.domain.market_services.attach_watchlist_intraday", return_value=cached
        ), patch("src.domain.market_services._fetch_watchlist_realtime_detail_from_candidate") as fetch_mock:
            payload = market_services._build_watchlist_realtime_detail_from_candidate(candidate)

        self.assertEqual(payload, cached)
        fetch_mock.assert_not_called()

    def test_given_stock_name_detail_request_when_local_alias_exists_then_security_code_is_resolved(self):
        with patch(
            "src.domain.market_services.fetch_gangtise_market_kline_series",
            return_value={"ok": False, "points": [], "message": "test_no_market_data"},
        ):
            with app_entry.app.app_context():
                payload = market_services.get_watchlist_detail_by_code(stock_code="601939", stock_name="建设银行")

        self.assertEqual(payload["code"], "601939")
        self.assertEqual(payload["name"], "建设银行")
        self.assertTrue(payload["data_unavailable"])
        self.assertEqual(payload["kline"], [])

    def test_given_watchlist_search_api_when_candidates_exist_then_dropdown_payload_returns(self):
        with patch(
            "src.web.api_core.search_watchlist_candidates",
            return_value=[
                {
                    "code": "003015",
                    "name": "日久光电",
                    "market": "SZ",
                    "security_code": "003015.SZ",
                    "source": "gangtise_openapi",
                }
            ],
        ):
            response = self.client.get("/api/watchlist/search?q=%E6%97%A5%E4%B9%85%E5%85%89%E6%96%B0")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["items"][0]["code"], "003015")
        self.assertEqual(payload["items"][0]["name"], "日久光电")

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

    def test_given_missing_review_title_when_publishing_review_then_reject(self):
        response = self.client.post(
            "/api/review/publish-embed",
            json={
                "tenant_slug": self.tenant_slug,
                "period": "day",
                "text": "这是确认发布后的复盘正文。",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "review_title_required")

    def test_given_valid_publish_text_when_publishing_review_then_publish_without_embedding_job(self):
        snapshot_result = {
            "snapshot": {"id": "review-1", "title": "日复盘：这是确认发布后的复盘正文"},
            "snapshots": [{"id": "review-1", "title": "日复盘：这是确认发布后的复盘正文"}],
            "message_center_state": {"summary": "ok", "threads": [], "broadcasts": []},
        }
        with mock.patch(
            "src.web.api_core.persist_review_publish_snapshot",
            return_value=snapshot_result,
        ) as persist_snapshot, mock.patch(
            "src.web.api_core.create_user_async_job",
            return_value={"job_code": "JOB-REVIEW-PUBLISH-1", "status": "pending"},
        ) as create_job:
            response = self.client.post(
                "/api/review/publish-embed",
                json={
                    "tenant_slug": self.tenant_slug,
                    "period": "day",
                    "review_title": "手动输入的复盘主题",
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
        self.assertFalse(payload["async"])
        self.assertFalse(payload["embedding_generated"])
        self.assertEqual(payload["publish_processing"], "snapshot_only")
        self.assertEqual(payload["snapshot"]["id"], "review-1")
        self.assertEqual(len(payload["snapshots"]), 1)
        persist_snapshot.assert_called_once()
        self.assertEqual(persist_snapshot.call_args.kwargs["review_title"], "手动输入的复盘主题")
        create_job.assert_not_called()

    def test_given_publish_text_when_embedding_queue_unavailable_then_review_is_still_published(self):
        snapshot_result = {
            "snapshot": {"id": "review-2", "title": "日复盘：同步发布"},
            "snapshots": [{"id": "review-2", "title": "日复盘：同步发布"}],
            "message_center_state": {"summary": "ok", "threads": [], "broadcasts": []},
        }
        with mock.patch(
            "src.web.api_core.persist_review_publish_snapshot",
            return_value=snapshot_result,
        ), mock.patch("src.web.api_core.create_user_async_job") as create_job:
            response = self.client.post(
                "/api/review/publish-embed",
                json={
                    "tenant_slug": self.tenant_slug,
                    "period": "day",
                    "review_title": "同步发布主题",
                    "text": "这是确认发布后的复盘正文。",
                    "speaker_name": "BDD Tester",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertFalse(payload["async"])
        self.assertEqual(payload["snapshot"]["id"], "review-2")
        self.assertFalse(payload["embedding_generated"])
        create_job.assert_not_called()

    def test_given_publish_text_when_processing_then_transcription_engine_is_forwarded_without_embedding(self):
        with mock.patch("src.domain.ai_services.build_text_embedding") as build_embedding, mock.patch(
            "src.domain.ai_services._store_review_voice_embedding_record"
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
        self.assertFalse(result["embedding_generated"])
        build_embedding.assert_not_called()
        store_record.assert_not_called()

    def test_given_review_voice_enhancement_when_running_then_gemma4_12b_model_is_used(self):
        config = normalize_site_config({})
        captured = {}

        def _fake_call(model_config, system_prompt, user_prompt, **kwargs):
            captured["model_config"] = model_config
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            captured["kwargs"] = kwargs
            return "整理后的语音正文"

        with mock.patch("src.domain.ai_services.get_site_config", return_value=config), mock.patch(
            "src.domain.ai_services.call_openai_compatible_llm",
            side_effect=_fake_call,
        ):
            result = ai_services.enhance_review_voice_transcript_with_llm(
                "今天先看AI算力和港股互联网两条线。",
                entry_point="bdd_voice",
                speaker_name="BDD Tester",
                tenant_slug=self.tenant_slug,
            )

        self.assertEqual(result["text"], "整理后的语音正文")
        self.assertEqual(captured["model_config"]["key"], "gangtise-gemma4-12b-bf16")
        self.assertEqual(captured["model_config"]["model_name"], "gemma4:12b-it-bf16")
        self.assertEqual(captured["kwargs"]["feature_code"], "review_voice_enhancement")

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

    def test_given_explicit_empty_review_list_when_resolving_then_no_demo_review_is_recreated(self):
        with app_entry.app.app_context():
            tenant = get_tenant_by_slug(self.tenant_slug)
            snapshots = resolve_tenant_review_snapshots(tenant, snapshots=[])
        self.assertEqual(snapshots, [])

    def test_given_published_review_when_deleted_then_snapshot_is_removed(self):
        tenant = {"slug": self.tenant_slug, "advisor": "测试大V", "review_snapshots": [
            {"id": "review-to-delete", "title": "待删除复盘", "content_text": "正文"},
            {"id": "review-to-keep", "title": "保留复盘", "content_text": "正文"},
        ]}
        saved_state = {}
        def get_tenant_side_effect(slug, config=None):
            if config and isinstance(config, dict) and "review_snapshots" in config:
                return {**tenant, "review_snapshots": config["review_snapshots"]}
            return tenant

        with patch("src.domain.core_services.get_tenant_by_slug", side_effect=get_tenant_side_effect), patch(
            "src.domain.core_services._save_tenant_state_field",
            side_effect=lambda slug, field, value: saved_state.update({field: value}) or {"slug": slug, field: value},
        ):
            result = delete_tenant_review_snapshot(self.tenant_slug, "review-to-delete")
        self.assertEqual(result["review_id"], "review-to-delete")
        self.assertEqual([item["id"] for item in result["snapshots"]], ["review-to-keep"])
        self.assertEqual([item["id"] for item in saved_state["review_snapshots"]], ["review-to-keep"])

        tenant["review_snapshots"] = saved_state["review_snapshots"]
        saved_state.clear()
        with patch("src.domain.core_services.get_tenant_by_slug", side_effect=get_tenant_side_effect), patch(
            "src.domain.core_services._save_tenant_state_field",
            side_effect=lambda slug, field, value: saved_state.update({field: value}) or {"slug": slug, field: value},
        ):
            result = delete_tenant_review_snapshot(self.tenant_slug, "review-to-keep")
        self.assertEqual(result["snapshots"], [])
        self.assertEqual(saved_state["review_snapshots"], [])

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
        self.assertEqual(items[0]["content"], "放量确认；量价配合有效，后续看均线支撑。；5日线不破")

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

    def test_given_no_watchlist_when_composing_review_preview_then_summary_still_returns(self):
        summary_result = {
            "summary": "今天先收敛主线判断，再等后续验证节点确认。",
            "llm_model": {"stage": "user_input_summary", "model_name": "demo-summary"},
        }

        with patch("src.domain.ai_services.summarize_review_user_input_with_llm", return_value=summary_result), patch(
            "src.domain.ai_services.analyze_review_watchlist_with_llm"
        ) as watchlist_mock:
            preview = ai_services.compose_review_structured_preview(
                source_text="今天先聚焦市场主线，暂不展开个股归纳。",
                review_period="day",
                source_mode="manual",
                selected_watchlist=[],
                speaker_name="财经老王",
                entry_point="test_review_bdd",
                tenant_slug=self.tenant_slug,
            )

        watchlist_mock.assert_not_called()
        self.assertEqual(preview["review_summary"], summary_result["summary"])
        self.assertEqual(preview["watchlist_analysis_section"]["sector_summary"], "")
        self.assertEqual(preview["watchlist_analysis_section"]["items"], [])
        self.assertIn("【复盘摘要】", preview["final_text"])
        self.assertNotIn("【自选股归纳分析】", preview["final_text"])

    def test_given_skip_summary_when_composing_review_preview_then_only_watchlist_analysis_returns(self):
        watchlist_result = {
            "sector_summary": "半导体板块继续作为核心观察样本。",
            "sector_profiles": [
                {
                    "sector": "半导体",
                    "stock_names": ["中芯国际"],
                    "representative_description": "景气验证优先看订单兑现。",
                }
            ],
            "items": [
                {
                    "stock_name": "中芯国际",
                    "stock_code": "688981",
                    "sector": "半导体",
                    "board_role": "板块代表样本",
                    "analysis_text": "先看订单兑现，再看量价确认。",
                    "evidence": ["K线标注", "成交量放大"],
                }
            ],
            "annotation_evidence": [],
            "workflow_meta": {"status": "ok"},
            "llm_model": {"stage": "watchlist_analysis", "model_name": "demo-watchlist"},
        }

        with patch("src.domain.ai_services.summarize_review_user_input_with_llm") as summary_mock, patch(
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
                include_summary=False,
            )

        summary_mock.assert_not_called()
        self.assertEqual(preview["review_summary"], "")
        self.assertEqual(preview["watchlist_analysis_section"]["sector_summary"], "半导体板块继续作为核心观察样本。")
        self.assertNotIn("【复盘摘要】", preview["final_text"])
        self.assertIn("【自选股归纳分析】", preview["final_text"])

    def test_given_review_text_when_building_evidence_chain_then_knowledge_and_web_matches_are_combined(self):
        knowledge_result = {
            "evidence_items": [
                {
                    "id": "kb-1",
                    "evidence_id": "kb-1",
                    "title": "AI 算力订单跟踪",
                    "summary": "订单兑现与资本开支是当前核心验证点。",
                    "source_label": "知识库",
                    "source_detail": "研究纪要",
                    "score": 0.91,
                }
            ],
            "llm_model": {
                "key": "general-model",
                "label": "General Model",
                "provider": "openai",
                "model_name": "demo-model",
                "purpose": "general",
            },
        }
        web_result = {
            "matches": [
                {
                    "title": "算力产业订单动态",
                    "summary": "公开信息显示订单节奏仍在推进。",
                    "source": "Google News RSS",
                    "published_at": "Tue, 04 Aug 2026 09:00:00 GMT",
                    "link": "https://example.com/news-1",
                }
            ]
        }

        with patch("src.domain.ai_services.build_evidence_chain_response", return_value=knowledge_result), patch(
            "src.domain.ai_services.hermes_tool_web_search",
            return_value=web_result,
        ), patch(
            "src.domain.ai_services.get_default_llm_config",
            return_value=None,
        ):
            result = ai_services.build_review_evidence_chain_section(
                review_text="今天重点看 AI 算力订单兑现，以及资本开支是否继续扩张。",
                tenant_slug=self.tenant_slug,
                review_title="我的新主题",
                entry_point="test_review_bdd",
            )

        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["knowledge_match_count"], 1)
        self.assertEqual(result["web_match_count"], 1)
        self.assertEqual(len(result["items"]), 2)
        self.assertIn("知识库", [item["source_label"] for item in result["items"]])
        self.assertIn("互联网公开信息", [item["source_label"] for item in result["items"]])

    def test_given_review_text_when_no_evidence_matches_then_empty_evidence_chain_is_returned(self):
        with patch("src.domain.ai_services.build_evidence_chain_response", return_value={"evidence_items": []}), patch(
            "src.domain.ai_services.hermes_tool_web_search",
            return_value={"matches": []},
        ), patch(
            "src.domain.ai_services.get_default_llm_config",
            return_value=None,
        ):
            result = ai_services.build_review_evidence_chain_section(
                review_text="今天主要记录自己的盘后判断，没有明确外部证据命中。",
                tenant_slug=self.tenant_slug,
                review_title="我的新主题",
                entry_point="test_review_bdd",
            )

        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["summary"], "暂无匹配的证据链")
        self.assertEqual(result["items"], [])

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
