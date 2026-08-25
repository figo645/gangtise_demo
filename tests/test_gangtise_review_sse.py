import json
import unittest
from unittest.mock import patch

from src.domain import ai_services, market_services


class _FakeSseResponse:
    status = 200

    def __init__(self, lines):
        self._lines = [line.encode("utf-8") for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def __iter__(self):
        return iter(self._lines)


class GangtiseReviewSseTest(unittest.TestCase):
    def test_sse_client_sends_agent_contract_and_merges_snapshots_and_deltas(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _FakeSseResponse(
                [
                    "event: message\n",
                    'data: {"content":"第一段"}\n',
                    "\n",
                    'data: {"content":"第一段第二段"}\n',
                    "\n",
                    'data: {"data":"{\\"content\\":\\"第三段\\"}"}\n',
                    "\n",
                    "data: 纯文本事件\n",
                    "\n",
                    "data: [DONE]\n",
                    "\n",
                ]
            )

        with patch(
            "src.domain.market_services.get_gangtise_openapi_config",
            return_value={"base_url": "https://openapi.gangtise.com"},
        ), patch("src.domain.market_services.urlopen", side_effect=fake_urlopen):
            result = market_services.post_gangtise_openapi_sse(
                "/application/open-ai/ai/chat/sse",
                {"text": "请分析三只股票", "mode": "deep_research"},
                token="test-token",
                timeout=17,
            )

        request = captured["request"]
        self.assertEqual(captured["timeout"], 17)
        self.assertEqual(request.full_url, "https://openapi.gangtise.com/application/open-ai/ai/chat/sse")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.headers["Authorization"], "Bearer test-token")
        self.assertEqual(request.headers["Accept"], "text/event-stream")
        self.assertEqual(json.loads(request.data.decode("utf-8"))["mode"], "deep_research")
        self.assertTrue(result["ok"])
        self.assertEqual(result["events"], 4)
        self.assertEqual(result["text"], "第一段第二段第三段纯文本事件")

    def test_sse_client_flushes_partial_text_to_progress_callback_on_stream_error(self):
        progress = []

        class _FailingResponse(_FakeSseResponse):
            def __iter__(self):
                yield 'data: {"content":"已返回的部分分析"}\n'.encode("utf-8")
                yield b"\n"
                raise RuntimeError("connection_closed")

        def fake_urlopen(request, timeout):
            return _FailingResponse([])

        with patch(
            "src.domain.market_services.get_gangtise_openapi_config",
            return_value={"base_url": "https://openapi.gangtise.com"},
        ), patch("src.domain.market_services.urlopen", side_effect=fake_urlopen):
            result = market_services.post_gangtise_openapi_sse(
                "/application/open-ai/ai/chat/sse",
                {"text": "请分析股票"},
                token="test-token",
                progress_callback=lambda *args: progress.append(args),
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["text"], "已返回的部分分析")
        self.assertEqual(progress[-1][1], "已返回的部分分析")
        self.assertEqual(progress[-1][2], True)

    def test_agent_helper_uses_the_documented_payload(self):
        with patch(
            "src.domain.market_services.post_gangtise_openapi_sse",
            return_value={"ok": True, "text": "组合结论", "duration_ms": 123, "events": 9},
        ) as post_mock:
            result = market_services.call_gangtise_agent_sse(
                "请分析贵州茅台和宁德时代",
                trace_id="review-test",
            )

        path, payload = post_mock.call_args.args[:2]
        self.assertEqual(path, "/application/open-ai/ai/chat/sse")
        self.assertEqual(payload["text"], "请分析贵州茅台和宁德时代")
        self.assertEqual(payload["mode"], "deep_research")
        self.assertEqual(payload["askChatParam"]["iter"], 2)
        self.assertTrue(payload["askChatParam"]["webEnable"])
        self.assertEqual(payload["askChatParam"]["traceId"], "review-test")
        self.assertEqual(result["text"], "组合结论")

    def test_watchlist_review_calls_gangtise_and_does_not_call_local_general_llm(self):
        matched = [
            {"name": "贵州茅台", "code": "600519", "market": "SH", "industry": "白酒", "annotations": []},
            {"name": "宁德时代", "code": "300750", "market": "SZ", "industry": "新能源", "annotations": []},
        ]
        with patch("src.domain.ai_services.gen_watchlist_details", return_value={}), patch(
            "src.domain.ai_services.build_watchlist_annotation_context", return_value=matched
        ), patch(
            "src.domain.ai_services.call_gangtise_agent_sse",
            return_value={
                "text": "两只股票组合层面的综合结论。",
                "provider": "Gangtise Agent助手 SSE",
                "endpoint": "/application/open-ai/ai/chat/sse",
                "duration_ms": 321,
                "events": 7,
            },
        ) as gangtise_mock, patch(
            "src.domain.ai_services.call_openai_compatible_llm",
            side_effect=AssertionError("local general LLM must not be called for watchlist analysis"),
        ):
            result = ai_services.analyze_review_watchlist_with_llm(
                selected_watchlist=["贵州茅台", "宁德时代"],
                review_period="day",
                source_text="大V输入：今天关注消费和新能源的分化。",
                tenant_slug="laowang",
            )

        gangtise_mock.assert_called_once()
        request_text = gangtise_mock.call_args.args[0]
        self.assertIn("贵州茅台（600519.SH）", request_text)
        self.assertIn("宁德时代（300750.SZ）", request_text)
        self.assertIn("大V本次复盘输入", request_text)
        self.assertEqual(result["combined_text"], "两只股票组合层面的综合结论。")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["endpoint"], "/application/open-ai/ai/chat/sse")

    def test_watchlist_review_progress_persists_partial_gangtise_text(self):
        matched = [{"name": "贵州茅台", "code": "600519", "market": "SH", "industry": "白酒", "annotations": []}]
        progress_calls = []

        def fake_progress(job_code, **kwargs):
            progress_calls.append((job_code, kwargs))

        def fake_gangtise(*args, **kwargs):
            callback = kwargs["progress_callback"]
            callback(1, "第一段")
            callback(5, "第一段第二段")
            raise RuntimeError("sse_connection_closed")

        with patch("src.domain.ai_services.gen_watchlist_details", return_value={}), patch(
            "src.domain.ai_services.build_watchlist_annotation_context", return_value=matched
        ), patch("src.domain.ai_services.report_user_async_job_progress", side_effect=fake_progress), patch(
            "src.domain.ai_services.call_gangtise_agent_sse", side_effect=fake_gangtise
        ):
            with self.assertRaises(RuntimeError):
                ai_services.analyze_review_watchlist_with_llm(
                    selected_watchlist=["贵州茅台"],
                    review_period="day",
                    source_text="今天关注消费板块。",
                    tenant_slug="laowang",
                    job_code="review-job-partial",
                )

        streaming_updates = [kwargs for job_code, kwargs in progress_calls if kwargs.get("stage") == "watchlist_gangtise_sse_streaming"]
        self.assertTrue(streaming_updates)
        self.assertEqual(streaming_updates[-1]["extra_result"]["partial_text"], "第一段第二段")

    def test_combined_gangtise_text_is_preserved_in_final_review_text(self):
        with patch(
            "src.domain.ai_services.summarize_review_user_input_with_llm",
            return_value={"summary": "", "llm_model": None},
        ), patch(
            "src.domain.ai_services.analyze_review_watchlist_with_llm",
            return_value={
                "sector_summary": "",
                "sector_profiles": [],
                "items": [],
                "combined_text": "Gangtise 返回的完整多股分析和组合结论。",
                "provider": "Gangtise Agent助手 SSE",
                "endpoint": "/application/open-ai/ai/chat/sse",
                "request_text": "请分析两只股票",
                "annotation_evidence": [],
                "llm_model": {"key": "gangtise_agent_sse"},
            },
        ):
            preview = ai_services.compose_review_structured_preview(
                source_text="大V输入的复盘内容。",
                review_period="day",
                source_mode="manual",
                selected_watchlist=["贵州茅台", "宁德时代"],
                include_summary=False,
            )

        self.assertIn("大V输入的复盘内容。", preview["final_text"])
        self.assertIn("Gangtise 返回的完整多股分析和组合结论。", preview["final_text"])
        self.assertEqual(
            preview["watchlist_analysis_section"]["endpoint"],
            "/application/open-ai/ai/chat/sse",
        )


if __name__ == "__main__":
    unittest.main()
