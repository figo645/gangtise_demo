import unittest
from unittest.mock import patch

from src.domain import ai_services
from src.runtime import app


class StrictLlmExecutionBddTest(unittest.TestCase):
    MODEL = {
        "key": "bdd-model",
        "label": "BDD 模型",
        "provider": "mock",
        "base_url": "http://mock.invalid",
        "api_key": "bdd-key",
        "model_name": "bdd-model",
        "purpose": "general",
        "enabled": True,
    }

    def test_given_hermes_model_when_routing_and_synthesizing_then_llm_is_called_for_both_steps(self):
        responses = [
            '{"intent":"small_talk","tools":[],"stock_code":"","display_mode":"text","reason":"模型路由"}',
            '{"answer":"模型回答","summary":"模型摘要","bullets":[],"citations":[]}',
        ]
        with app.app_context(), patch.object(
            ai_services, "get_default_llm_config", return_value=self.MODEL
        ), patch.object(
            ai_services, "call_openai_compatible_llm", side_effect=responses
        ) as llm_call:
            plan, router_model, route_mode = ai_services.route_hermes_query_intent(
                "你好", tenant_slug="bdd"
            )
            synthesis, answer_model, answer_mode = ai_services.synthesize_hermes_answer(
                "你好", plan, {}, tenant_slug="bdd"
            )

        self.assertEqual(llm_call.call_count, 2)
        self.assertEqual(route_mode, "llm_router")
        self.assertEqual(answer_mode, "llm_synthesized")
        self.assertEqual(router_model["key"], self.MODEL["key"])
        self.assertEqual(answer_model["key"], self.MODEL["key"])
        self.assertEqual(synthesis["answer"], "模型回答")

    def test_given_hermes_model_missing_then_router_fails_without_rule_plan(self):
        with app.app_context(), patch.object(ai_services, "get_default_llm_config", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "hermes_intent_router_llm_not_configured"):
                ai_services.route_hermes_query_intent("你好", tenant_slug="bdd")

    def test_given_hermes_model_returns_invalid_json_then_router_fails(self):
        with app.app_context(), patch.object(
            ai_services, "get_default_llm_config", return_value=self.MODEL
        ), patch.object(ai_services, "call_openai_compatible_llm", return_value="not-json"):
            with self.assertRaisesRegex(RuntimeError, "invalid_llm_json_response"):
                ai_services.route_hermes_query_intent("你好", tenant_slug="bdd")

    def test_given_small_talk_router_returns_knowledge_tool_then_tools_are_cleared(self):
        with app.app_context(), patch.object(
            ai_services, "get_default_llm_config", return_value=self.MODEL
        ), patch.object(
            ai_services,
            "call_openai_compatible_llm",
            return_value='{"intent":"small_talk","tools":["knowledge.search"],"stock_code":"","display_mode":"text","reason":"模型路由"}',
        ):
            plan, _model, _mode = ai_services.route_hermes_query_intent("你好", tenant_slug="bdd")

        self.assertEqual(plan["intent"], "small_talk")
        self.assertEqual(plan["tools"], [])

    def test_given_hermes_answer_call_fails_then_no_rule_answer_is_returned(self):
        plan = {"intent": "small_talk", "tools": [], "scope_status": "allowed"}
        with app.app_context(), patch.object(
            ai_services, "get_default_llm_config", return_value=self.MODEL
        ), patch.object(
            ai_services,
            "call_openai_compatible_llm",
            side_effect=RuntimeError("provider_timeout"),
        ):
            with self.assertRaisesRegex(RuntimeError, "provider_timeout"):
                ai_services.synthesize_hermes_answer("你好", plan, {}, tenant_slug="bdd")

    def test_given_review_generation_paths_when_model_is_available_then_each_path_calls_llm(self):
        functions = [
            lambda: ai_services.generate_review_draft_with_llm(
                source_text="市场今天出现明显分化。", tenant_slug="bdd"
            ),
            lambda: ai_services.polish_review_input_with_llm(
                source_text="市场今天出现明显分化。", tenant_slug="bdd"
            ),
            lambda: ai_services.compose_review_draft_with_llm(
                source_text="市场今天出现明显分化。", tenant_slug="bdd"
            ),
        ]
        for generate in functions:
            with self.subTest(generate=generate), app.app_context(), patch.object(
                ai_services, "get_default_llm_config", return_value=self.MODEL
            ), patch.object(
                ai_services, "call_openai_compatible_llm", return_value="模型生成的复盘内容"
            ) as llm_call:
                result = generate()

            self.assertEqual(llm_call.call_count, 1)
            self.assertEqual(result["text"], "模型生成的复盘内容")

    def test_given_review_model_missing_then_generation_fails_without_original_text_fallback(self):
        with app.app_context(), patch.object(ai_services, "get_default_llm_config", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "review_draft_llm_not_configured"):
                ai_services.generate_review_draft_with_llm(
                    source_text="原始复盘内容", tenant_slug="bdd"
                )

    def test_given_review_model_call_fails_then_generation_propagates_error(self):
        with app.app_context(), patch.object(ai_services, "get_default_llm_config", return_value=self.MODEL), patch.object(
            ai_services,
            "call_openai_compatible_llm",
            side_effect=RuntimeError("review_provider_down"),
        ):
            with self.assertRaisesRegex(RuntimeError, "review_provider_down"):
                ai_services.polish_review_input_with_llm(
                    source_text="原始复盘内容", tenant_slug="bdd"
                )

    def test_given_review_evidence_matches_when_publishing_then_filter_answer_and_summary_all_call_llm(self):
        responses = [
            '{"relevant_ids":["k1"],"reason":"与复盘相关"}',
            "证据链回答",
            "证据链总结",
        ]
        with app.app_context(), patch.object(
            ai_services, "get_default_llm_config", return_value=self.MODEL
        ), patch.object(
            ai_services, "call_openai_compatible_llm", side_effect=responses
        ) as llm_call, patch.object(
            ai_services,
            "search_evidence_chain",
            return_value={
                "query": "市场复盘",
                "answer": "检索结果",
                "evidence_items": [
                    {
                        "id": "k1",
                        "title": "知识证据",
                        "summary": "证据摘要",
                        "body": "证据正文",
                        "source_type": "knowledge",
                        "source_label": "知识库",
                        "score": 0.9,
                    }
                ],
                "matches": [],
                "source_types": ["knowledge"],
            },
        ), patch.object(ai_services, "hermes_tool_web_search", return_value={"matches": []}), patch.object(
            ai_services, "get_tenant_by_slug", return_value={"name": "BDD 租户"}
        ), patch.object(
            ai_services,
            "get_evidence_chain_config",
            return_value={
                "filter_prompt_system": "过滤",
                "filter_prompt_user_template": "问题：{query}\n候选：{candidate_blocks}",
                "filter_timeout_seconds": 1,
                "answer_timeout_seconds": 1,
            },
        ):
            result = ai_services.build_review_evidence_chain_section(
                review_text="市场复盘：银行板块出现分化。",
                review_title="日复盘",
                tenant_slug="bdd",
            )

        self.assertEqual(llm_call.call_count, 3)
        self.assertEqual(llm_call.call_args_list[1].args[0]["base_url"], self.MODEL["base_url"])
        self.assertEqual(result["summary"], "证据链总结")
        self.assertEqual(result["llm_model"]["key"], self.MODEL["key"])


if __name__ == "__main__":
    unittest.main()
