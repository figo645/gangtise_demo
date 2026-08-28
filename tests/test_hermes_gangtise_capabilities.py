import unittest
from contextlib import ExitStack
from unittest.mock import patch

from src.domain import ai_services, core_services, market_services


class HermesGangtiseCapabilitiesTest(unittest.TestCase):
    def test_admin_uses_the_dav_hermes_permission_gate_without_becoming_dav(self):
        site_config = {
            "feature_flags": {"hermes": True},
            "hermes_settings": {
                "dav_access_enabled": True,
                "investor_access_enabled": False,
            },
        }

        self.assertTrue(core_services.is_hermes_available_for_role("dav", site_config))
        self.assertTrue(core_services.is_hermes_available_for_role("admin", site_config))
        self.assertFalse(core_services.is_hermes_available_for_role("investor", site_config))

    def test_role_capabilities_keep_admin_identity_independent_from_dav(self):
        site_config = {
            "feature_flags": {"hermes": True},
            "hermes_settings": {"dav_access_enabled": True, "investor_access_enabled": False},
            "role_capabilities": {
                "admin": ["admin", "h5", "dav", "hermes", "workbench"],
                "dav": ["h5", "dav", "hermes", "workbench"],
            },
        }

        self.assertTrue(core_services.has_role_capability("admin", "admin", site_config))
        self.assertTrue(core_services.has_role_capability("admin", "dav", site_config))
        self.assertTrue(core_services.has_role_capability("dav", "dav", site_config))
        self.assertFalse(core_services.has_role_capability("dav", "admin", site_config))
        self.assertTrue(core_services.is_hermes_available_for_role("admin", site_config))
        self.assertTrue(core_services.is_hermes_available_for_role("dav", site_config))

    def test_custom_role_can_receive_h5_and_hermes_without_code_changes(self):
        site_config = {
            "feature_flags": {"hermes": True},
            "hermes_settings": {"dav_access_enabled": True, "investor_access_enabled": False},
            "role_capabilities": {"researcher": ["h5", "hermes"]},
        }

        self.assertTrue(core_services.has_role_capability("researcher", "h5", site_config))
        self.assertTrue(core_services.is_hermes_available_for_role("researcher", site_config))

    def test_stock_summary_helper_uses_batch_contract_and_preserves_items(self):
        response = {
            "code": "000000",
            "status": True,
            "data": {"list": [{"securityCode": "601988.SH", "summary": "息差企稳"}]},
        }
        with patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 18)) as post_mock:
            result = market_services.call_gangtise_stock_summaries(["601988.sh", "601988.SH"])

        self.assertEqual(post_mock.call_args.args[0], "/application/open-ai/stock-summary/getList")
        self.assertEqual(post_mock.call_args.args[1], {"securityList": ["601988.SH"]})
        self.assertEqual(result["items"][0]["summary"], "息差企稳")

    def test_one_pager_helper_uses_single_security_code_contract(self):
        response = {"code": "000000", "status": True, "data": {"content": "# 深度报告", "date": "2026-08-28"}}
        with patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 24)) as post_mock:
            result = market_services.call_gangtise_stock_one_pager("600519.sh")

        self.assertEqual(post_mock.call_args.args[0], "/application/open-ai/agent/one-pager")
        self.assertEqual(post_mock.call_args.args[1], {"securityCode": "600519.SH"})
        self.assertEqual(result["data"]["content"], "# 深度报告")
        self.assertEqual(result["data"]["date"], "2026-08-28")

    def test_direct_gangtise_result_does_not_call_local_llm(self):
        plan = {"intent": "stock_today_observation"}
        outputs = {"gangtise_stock_observation": {"text": "# 今日行情\n中国银行上涨", "provider": "Gangtise Agent助手 SSE"}}
        with patch.object(ai_services, "get_default_llm_config") as llm_config:
            result, model, mode = ai_services.synthesize_hermes_answer("今天中国银行", plan, outputs)

        llm_config.assert_not_called()
        self.assertIsNone(model)
        self.assertEqual(mode, "gangtise_direct")
        self.assertIn("中国银行", result["answer"])

    def test_hermes_rejects_loopback_admin_default(self):
        local_default_model = {
            "key": "old-local-default",
            "base_url": "http://127.0.0.1:10900/api",
            "model_name": "old-local-default",
            "enabled": True,
        }
        remote_default_model = {
            "key": "configured-remote-default",
            "base_url": "https://llm.example.com/v1",
            "model_name": "remote-model",
            "enabled": True,
            "purpose": "general",
        }
        site_config = {"llm_registry": {"models": [local_default_model, remote_default_model]}}
        with patch.object(ai_services, "get_default_llm_config", return_value=local_default_model):
            with self.assertRaisesRegex(RuntimeError, "llm_loopback_url_not_allowed"):
                ai_services.get_hermes_llm_config("hermes_intent_router", site_config=site_config)

    def test_all_features_ignore_stale_feature_binding_and_use_admin_default(self):
        config = {
            "llm_registry": {
                "default_model_key": "admin-default",
                "feature_model_keys": {"hermes_intent_router": "old-local-model", "review_draft_generation": "other-model"},
                "models": [
                    {
                        "key": "admin-default",
                        "base_url": "http://8.155.160.194:6031/api",
                        "model_name": "qwen3.5:27b-q4_K_M",
                        "enabled": True,
                        "purpose": "general",
                    },
                    {
                        "key": "old-local-model",
                        "base_url": "http://127.0.0.1:10900/api",
                        "model_name": "old-local",
                        "enabled": True,
                        "purpose": "general",
                    },
                    {
                        "key": "other-model",
                        "base_url": "https://other.example/v1",
                        "model_name": "other",
                        "enabled": True,
                        "purpose": "general",
                    },
                ],
            }
        }

        for feature_code in ("hermes_intent_router", "review_draft_generation", "embedding_api"):
            with self.subTest(feature_code=feature_code):
                selected = ai_services.get_default_llm_config(site_config=config, feature_code=feature_code)
                self.assertEqual(selected["key"], "admin-default")
                self.assertEqual(selected["base_url"], "http://8.155.160.194:6031/api")

    def test_llm_network_boundary_rejects_loopback_before_http(self):
        with patch.object(ai_services.requests, "Session") as session_factory:
            with self.assertRaisesRegex(RuntimeError, "llm_loopback_url_not_allowed"):
                ai_services.call_openai_compatible_llm(
                    {
                        "key": "old-local",
                        "base_url": "http://127.0.0.1:10900/api",
                        "model_name": "old-local",
                        "api_key": "key",
                        "enabled": True,
                    },
                    "system",
                    "user",
                )
            session_factory.assert_not_called()

    def test_llm_network_boundary_does_not_use_environment_proxy_or_redirect(self):
        response = type("Response", (), {"status_code": 200, "text": "", "json": lambda self: {"choices": [{"message": {"content": "OK"}}]}})()
        with patch.object(ai_services.requests, "Session") as session_factory, patch.object(ai_services, "log_token_usage"):
            session_factory.return_value.post.return_value = response
            result = ai_services.call_openai_compatible_llm(
                {
                    "key": "admin-default",
                    "base_url": "http://8.155.160.194:6031/api",
                    "model_name": "qwen3.5:27b-q4_K_M",
                    "api_key": "key",
                    "enabled": True,
                },
                "system",
                "user",
            )
        self.assertEqual(result, "OK")
        self.assertFalse(session_factory.return_value.trust_env)
        session_factory.return_value.post.assert_called_once()
        self.assertFalse(session_factory.return_value.post.call_args.kwargs["allow_redirects"])

    def test_hermes_ignores_feature_binding_and_uses_admin_default(self):
        admin_default_model = {
            "key": "configured-admin-default",
            "base_url": "https://llm.example.com/v1",
            "model_name": "remote-model",
            "enabled": True,
        }
        with patch.object(
            ai_services,
            "get_default_llm_config",
            return_value=admin_default_model,
        ) as get_config:
            result = ai_services.get_hermes_llm_config("hermes_intent_router")

        self.assertEqual(result["key"], "configured-admin-default")
        get_config.assert_called_once_with(site_config=None, purpose="general", feature_code="")

    def test_hermes_does_not_replace_loopback_admin_default(self):
        loopback_default = {
            "key": "old-local-default",
            "base_url": "http://127.0.0.1:10900/api",
            "model_name": "old-local-model",
            "enabled": True,
        }
        site_config = {
            "llm_registry": {
                "default_model_key": "old-local-default",
                "models": [
                    loopback_default,
                    {
                        "key": "configured-remote-model",
                        "base_url": "http://8.155.160.194:6031/api",
                        "model_name": "qwen3.5:27b-q4_K_M",
                        "enabled": True,
                        "purpose": "general",
                    },
                ],
            }
        }
        with patch.object(ai_services, "get_default_llm_config", return_value=loopback_default):
            with self.assertRaisesRegex(RuntimeError, "llm_loopback_url_not_allowed"):
                ai_services.get_hermes_llm_config("hermes_intent_router", site_config=site_config)

    def test_hermes_keeps_valid_remote_admin_default(self):
        admin_default_model = {
            "key": "configured-remote-default",
            "base_url": "https://llm.example.com/v1",
            "model_name": "remote-model",
            "enabled": True,
        }
        with patch.object(ai_services, "get_default_llm_config", return_value=admin_default_model) as get_config:
            result = ai_services.get_hermes_llm_config("hermes_intent_router")

        self.assertIs(result, admin_default_model)
        get_config.assert_called_once_with(site_config=None, purpose="general", feature_code="")

    def test_hermes_rejects_loopback_model_when_only_old_local_model_remains(self):
        loopback_model = {
            "key": "local-model",
            "base_url": "http://localhost:10900/api",
            "model_name": "local-model",
            "enabled": True,
        }
        site_config = {"llm_registry": {"models": [loopback_model]}}
        with patch.object(ai_services, "get_default_llm_config", return_value=loopback_model):
            with self.assertRaisesRegex(RuntimeError, "llm_loopback_url_not_allowed"):
                ai_services.get_hermes_llm_config("hermes_intent_router", site_config=site_config)

    def test_one_pager_accepts_content_directly_in_data_list(self):
        result = ai_services.build_hermes_gangtise_direct_synthesis(
            {"intent": "stock_one_pager"},
            {"gangtise_one_pager": {"data": [{"content": "# 贵州茅台深化研究"}]}},
        )

        self.assertEqual(result["answer"], "# 贵州茅台深化研究")

    def test_one_pager_empty_payload_reports_no_report_without_fallback(self):
        outputs = {
            "gangtise_one_pager": {
                "data": {"reportList": []},
                "http_status": 200,
                "response": {"code": "000000", "status": True},
            }
        }
        with patch.object(ai_services, "get_default_llm_config") as llm_config:
            with self.assertRaisesRegex(RuntimeError, "gangtise_one_pager_no_report:http_status=200"):
                ai_services.synthesize_hermes_answer("对贵州茅台做一次深化研究", {"intent": "stock_one_pager"}, outputs)

        llm_config.assert_not_called()

    def test_one_pager_unrecognized_payload_reports_shape_without_fallback(self):
        with self.assertRaisesRegex(RuntimeError, "gangtise_one_pager_response_unrecognized:.*data_keys=payload"):
            ai_services.build_hermes_gangtise_direct_synthesis(
                {"intent": "stock_one_pager"},
                {
                    "gangtise_one_pager": {
                        "data": {"payload": {"opaque": True}},
                        "http_status": 200,
                        "response": {"code": "000000", "status": True},
                    }
                },
            )

    def test_stock_today_observation_resolves_stock_and_calls_deep_research_sse(self):
        candidate = {"name": "中国银行", "code": "601988", "security_code": "601988.SH"}
        upstream = {
            "text": "## 中国银行\n昨日收盘表现稳定。",
            "provider": "Gangtise Agent助手 SSE",
            "endpoint": "/application/open-ai/ai/chat/sse",
            "duration_ms": 42,
        }
        with patch.object(ai_services, "resolve_watchlist_candidate", return_value=candidate) as resolve_mock, patch.object(
            ai_services, "call_gangtise_agent_sse", return_value=upstream
        ) as agent_mock:
            result = ai_services.hermes_tool_gangtise_stock_today_observation(
                "", "请帮我分析中国银行昨天的个股表现"
            )

        resolve_mock.assert_called_once_with(stock_code="", stock_name="请帮我分析中国银行昨天的个股表现")
        self.assertIn("昨天", agent_mock.call_args.args[0])
        self.assertEqual(agent_mock.call_args.kwargs["mode"], "deep_research")
        self.assertEqual(result["candidate"]["security_code"], "601988.SH")
        self.assertEqual(result["endpoint"], "/application/open-ai/ai/chat/sse")

    def test_market_observation_splits_shanghai_and_shenzhen_into_two_single_index_calls(self):
        upstream = [
            {"text": "上证报告", "provider": "Gangtise Agent助手 SSE", "endpoint": "/application/open-ai/ai/chat/sse", "duration_ms": 21},
            {"text": "深证报告", "provider": "Gangtise Agent助手 SSE", "endpoint": "/application/open-ai/ai/chat/sse", "duration_ms": 34},
        ]
        with patch.object(ai_services, "call_gangtise_agent_sse", side_effect=upstream) as agent_mock:
            result = ai_services.hermes_tool_gangtise_market_today_observation(
                "分析下今天大盘的整体走势，上证和深证指数表现如何"
            )

        self.assertEqual(agent_mock.call_count, 2)
        self.assertEqual(result["index_targets"], ["上证综合指数", "深证成份指数"])
        self.assertEqual(result["duration_ms"], 55)
        self.assertIn("## 上证综合指数", result["text"])
        self.assertIn("## 深证成份指数", result["text"])
        self.assertEqual(
            [item["request_text"] for item in result["requests"]],
            [
                "给我一份今天上证综合指数的分析观察报告，包含指数表现、板块资金和市场情绪展望。",
                "给我一份今天深证成份指数的分析观察报告，包含指数表现、板块资金和市场情绪展望。",
            ],
        )

    def test_market_observation_accepts_router_index_entities_without_stock_resolution(self):
        plan = ai_services.validate_hermes_intent_plan({
            "intent": "market_today_observation",
            "tools": ["gangtise.market_today_observation"],
            "target_type": "index",
            "securities": [{"name": "上证综合指数"}, {"name": "深证成份指数"}],
            "time_scope": "today",
        }, question_text="分析今天上证和深证指数表现")

        self.assertEqual(plan["securities"], [])

    def test_multi_stock_hermes_reuses_the_review_gangtise_request_builder(self):
        candidates = [
            {"name": "中国银行", "code": "601988", "security_code": "601988.SH"},
            {"name": "建设银行", "code": "601939", "security_code": "601939.SH"},
        ]
        upstream = {
            "text": "Gangtise 多股分析",
            "provider": "Gangtise Agent助手 SSE",
            "endpoint": "/application/open-ai/ai/chat/sse",
            "duration_ms": 42,
        }
        with patch.object(
            ai_services,
            "build_gangtise_multi_stock_review_request",
            return_value="请进行日复盘，分析以下自选股：中国银行（601988.SH）、建设银行（601939.SH）。",
        ) as request_builder, patch.object(
            ai_services,
            "call_gangtise_agent_sse",
            return_value=upstream,
        ) as agent_mock:
            result = ai_services.hermes_tool_gangtise_multi_watchlist_analysis(
                "", "请做详细综合分析", securities=candidates
            )

        request_builder.assert_called_once_with(
            ["中国银行（601988.SH）", "建设银行（601939.SH）"],
            review_period="day",
        )
        self.assertEqual(agent_mock.call_args.args[0], request_builder.return_value)
        self.assertEqual(agent_mock.call_args.kwargs["mode"], "deep_research")
        self.assertEqual(result["text"], "Gangtise 多股分析")

    def test_router_name_mapping_overrides_cross_market_model_code(self):
        candidates = {
            "601988": {"name": "中国银行", "code": "601988", "security_code": "601988.SH", "market": "SH"},
        }
        with patch.object(ai_services, "find_watchlist_code_from_text", return_value="601988"), patch.object(
            ai_services, "search_watchlist_candidates", side_effect=lambda query, top=1, include_remote=False: [candidates[query]]
        ):
            plan = ai_services.validate_hermes_intent_plan({
                "intent": "stock_today_observation",
                "tools": ["gangtise.stock_today_observation"],
                "target_type": "stock",
                "securities": [{"name": "中国银行", "code": "03988", "security_code": "03988.HK"}],
                "time_scope": "today",
            })

        self.assertEqual(plan["securities"][0]["security_code"], "601988.SH")

    def test_six_scenarios_have_single_dispatch_and_direct_research_output(self):
        model = {"key": "router", "provider": "mock", "model_name": "router", "enabled": True}
        candidate_map = {
            "中国银行": {"name": "中国银行", "code": "601988", "security_code": "601988.SH", "market": "SH"},
            "建设银行": {"name": "建设银行", "code": "601939", "security_code": "601939.SH", "market": "SH"},
            "招商银行": {"name": "招商银行", "code": "600036", "security_code": "600036.SH", "market": "SH"},
        }
        candidate_map.update({item["code"]: item for item in list(candidate_map.values())})
        scenarios = [
            (
                "对今天中国银行的股票做下个股分析，看看今天整体情况怎么样",
                '{"intent":"stock_today_observation","tools":["gangtise.stock_today_observation"],"target_type":"stock","securities":[{"name":"中国银行"}],"time_scope":"today","display_mode":"text"}',
                "stock_today_observation",
                [{"name": "中国银行"}],
                "个股今日报告",
            ),
            (
                "分析下今天大盘的整体走势，上证和深证指数表现如何",
                '{"intent":"market_today_observation","tools":["gangtise.market_today_observation"],"target_type":"index","securities":[],"time_scope":"today","display_mode":"text"}',
                "market_today_observation",
                [],
                "大盘今日报告",
            ),
            (
                "对中国银行做一下深入研究",
                '{"intent":"stock_one_pager","tools":["gangtise.stock_one_pager"],"target_type":"stock","securities":[{"name":"中国银行"}],"time_scope":"latest","display_mode":"text"}',
                "stock_one_pager",
                [{"name": "中国银行"}],
                "最近一期深化研究",
            ),
            (
                "中国银行、建设银行、招商银行，帮我简单介绍分析下",
                '{"intent":"stock_highlights","tools":["gangtise.stock_highlights"],"target_type":"multi_stock","securities":[{"name":"中国银行"},{"name":"建设银行"},{"name":"招商银行"}],"time_scope":"latest","display_mode":"text"}',
                "stock_highlights",
                [{"name": "中国银行"}, {"name": "建设银行"}, {"name": "招商银行"}],
                "银行看点",
            ),
            (
                "中国银行、建设银行、招商银行，做详细的综合分析",
                '{"intent":"multi_watchlist_analysis","tools":["gangtise.multi_watchlist_analysis"],"target_type":"multi_stock","securities":[{"name":"中国银行"},{"name":"建设银行"},{"name":"招商银行"}],"time_scope":"today","display_mode":"text"}',
                "multi_watchlist_analysis",
                [{"name": "中国银行"}, {"name": "建设银行"}, {"name": "招商银行"}],
                "组合综合结论",
            ),
        ]
        for question, raw, intent, _raw_securities, expected_text in scenarios:
            with self.subTest(intent=intent), patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
                ai_services, "call_openai_compatible_llm", return_value=raw
            ), patch.object(
                ai_services, "search_watchlist_candidates",
                side_effect=lambda query, top=1, include_remote=False: [candidate_map[query]] if query in candidate_map else [],
            ), patch.object(ai_services, "find_watchlist_code_from_text", side_effect=lambda value: candidate_map.get(value, {}).get("code", "")):
                plan, _model, route_mode = ai_services.route_hermes_query_intent(question)

            upstream = {
                "text": expected_text,
                "provider": "Gangtise Agent助手 SSE",
                "endpoint": "/application/open-ai/ai/chat/sse",
            }
            with ExitStack() as stack:
                if intent in {"stock_today_observation", "market_today_observation", "multi_watchlist_analysis"}:
                    upstream_call = stack.enter_context(
                        patch.object(ai_services, "call_gangtise_agent_sse", return_value=upstream)
                    )
                elif intent == "stock_one_pager":
                    upstream_call = stack.enter_context(
                        patch.object(ai_services, "call_gangtise_stock_one_pager", return_value={"data": {"markdown": expected_text}})
                    )
                else:
                    upstream_call = stack.enter_context(
                        patch.object(ai_services, "call_gangtise_stock_summaries", return_value={"items": [
                            {"securityName": "中国银行", "summary": "息差观察"},
                            {"securityName": "建设银行", "summary": "资产质量"},
                            {"securityName": "招商银行", "summary": "零售业务"},
                        ]})
                    )
                annotation_context = stack.enter_context(patch.object(
                    ai_services,
                    "resolve_hermes_watchlist_annotation_context",
                    return_value={"available": False},
                ))
                outputs, trace = ai_services.execute_hermes_tool_plan(plan, "laowang", question)
                local_llm = stack.enter_context(patch.object(ai_services, "get_default_llm_config"))
                result, answer_model, answer_mode = ai_services.synthesize_hermes_answer(question, plan, outputs)

            self.assertEqual(route_mode, "llm_router")
            self.assertEqual(len(trace), 1)
            if intent == "market_today_observation":
                self.assertEqual(upstream_call.call_count, 2)
                self.assertEqual(
                    [call.args[0] for call in upstream_call.call_args_list],
                    [
                        "给我一份今天上证综合指数的分析观察报告，包含指数表现、板块资金和市场情绪展望。",
                        "给我一份今天深证成份指数的分析观察报告，包含指数表现、板块资金和市场情绪展望。",
                    ],
                )
            else:
                upstream_call.assert_called_once()
            annotation_context.assert_not_called()
            local_llm.assert_not_called()
            self.assertEqual(answer_mode, "gangtise_direct")
            self.assertIsNone(answer_model)
            self.assertIn("息差观察" if intent == "stock_highlights" else expected_text, result["answer"])
            if intent in {"stock_today_observation", "market_today_observation", "multi_watchlist_analysis"}:
                self.assertEqual(upstream_call.call_args.kwargs["mode"], "deep_research")

        chat_raw = '{"intent":"small_talk","tools":[],"target_type":"none","securities":[],"time_scope":"conversation","display_mode":"text"}'
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services, "call_openai_compatible_llm", side_effect=[chat_raw, '{"answer":"先从风险承受能力开始。","summary":"选股先定框架","bullets":[],"analysis_sections":[],"next_steps":[],"citations":[]}']
        ) as llm_call, patch.object(ai_services, "call_gangtise_agent_sse") as gangtise_call, patch.object(
            ai_services, "resolve_hermes_watchlist_annotation_context", return_value={"available": False}
        ), patch.object(
            ai_services, "build_hermes_synthesis_prompt", return_value=("system", "user")
        ):
            plan, _model, _route_mode = ai_services.route_hermes_query_intent("我该怎么选股呢？")
            outputs, trace = ai_services.execute_hermes_tool_plan(plan, "laowang", "我该怎么选股呢？")
            result, _answer_model, answer_mode = ai_services.synthesize_hermes_answer("我该怎么选股呢？", plan, outputs)
        self.assertEqual(plan["intent"], "small_talk")
        self.assertEqual(plan["tools"], [])
        self.assertEqual(trace, [])
        self.assertEqual(answer_mode, "llm_synthesized")
        self.assertIn("风险承受能力", result["answer"])
        self.assertEqual(llm_call.call_count, 2)
        gangtise_call.assert_not_called()

    def test_stock_highlights_render_each_upstream_item_without_model_rewrite(self):
        plan = {"intent": "stock_highlights"}
        outputs = {
            "gangtise_stock_highlights": {
                "items": [{"securityName": "中国银行", "date": "2026-08-25", "summary": "净息差率先企稳"}],
            },
        }
        result = ai_services.build_hermes_gangtise_direct_synthesis(plan, outputs)

        self.assertIn("### 中国银行（2026-08-25）", result["answer"])
        self.assertIn("净息差率先企稳", result["answer"])

    def test_router_prompt_lists_all_gangtise_capabilities(self):
        prompt = ai_services.build_hermes_intent_router_prompt(
            "那再看一下它今天的风险",
            messages=[{"role": "user", "content": "上一轮看中国银行"}],
            memory_context_text="重点关注对象：中国银行 / 601988",
            memory_state={"session": {"recent_symbols": ["601988"], "last_intent": "stock_today_observation"}},
        )
        for value in (
            "stock_today_observation",
            "market_today_observation",
            "stock_one_pager",
            "stock_highlights",
            "multi_watchlist_analysis",
        ):
            self.assertIn(value, prompt)
        self.assertIn("/application/open-ai/ai/chat/sse", prompt)
        self.assertIn("/application/open-ai/agent/one-pager", prompt)
        self.assertIn("6000", prompt)
        self.assertIn("研究结果原样展示", prompt)
        self.assertIn("上一轮看中国银行", prompt)
        self.assertIn("601988", prompt)
        self.assertIn("帮我简单介绍分析下", prompt)
        self.assertIn("做详细的综合分析", prompt)
        self.assertIn("投资有什么建议", prompt)

    def test_stock_highlights_accepts_multiple_confirmed_securities(self):
        candidates = {
            "601988": {"name": "中国银行", "code": "601988", "security_code": "601988.SH", "market": "CN"},
            "601939": {"name": "建设银行", "code": "601939", "security_code": "601939.SH", "market": "CN"},
            "600036": {"name": "招商银行", "code": "600036", "security_code": "600036.SH", "market": "CN"},
        }
        with patch.object(ai_services, "resolve_watchlist_candidate", side_effect=lambda stock_code="", stock_name="": candidates.get(stock_code)):
            plan = ai_services.validate_hermes_intent_plan({
                "intent": "stock_highlights",
                "tools": ["gangtise.stock_highlights"],
                "target_type": "multi_stock",
                "securities": [{"code": "601988"}, {"code": "601939"}, {"code": "600036"}],
            })

        self.assertEqual(plan["target_type"], "multi_stock")
        self.assertEqual([item["security_code"] for item in plan["securities"]], ["601988.SH", "601939.SH", "600036.SH"])

    def test_general_investment_question_is_allowed_for_llm_chat(self):
        scope = ai_services.hermes_scope_guard("我该怎么选股呢？")
        self.assertEqual(scope["status"], "soft_allowed")
        self.assertEqual(scope["intent_hint"], "small_talk")

    def test_router_scenario_contracts_dispatch_to_expected_capabilities(self):
        model = {"key": "router", "provider": "mock", "model_name": "router", "enabled": True}
        candidates = {
            "中国银行": {"name": "中国银行", "code": "601988", "security_code": "601988.SH", "market": "CN"},
            "建设银行": {"name": "建设银行", "code": "601939", "security_code": "601939.SH", "market": "CN"},
            "招商银行": {"name": "招商银行", "code": "600036", "security_code": "600036.SH", "market": "CN"},
        }
        scenarios = [
            (
                "对今天中国银行的股票做下个股分析，看看今天整体情况怎么样",
                '{"intent":"stock_today_observation","tools":["gangtise.stock_today_observation"],"target_type":"stock","securities":[{"name":"中国银行"}],"time_scope":"today","display_mode":"text"}',
                "stock_today_observation",
                "stock",
            ),
            (
                "分析下今天大盘的整体走势，上证和深证指数表现如何",
                '{"intent":"market_today_observation","tools":["gangtise.market_today_observation"],"target_type":"index","securities":[],"time_scope":"today","display_mode":"text"}',
                "market_today_observation",
                "index",
            ),
            (
                "对中国银行做一下深入研究",
                '{"intent":"stock_one_pager","tools":["gangtise.stock_one_pager"],"target_type":"stock","securities":[{"name":"中国银行"}],"time_scope":"latest","display_mode":"text"}',
                "stock_one_pager",
                "stock",
            ),
            (
                "我这里有3支股票，中国银行，建设银行，招商银行，帮我简单介绍分析下",
                '{"intent":"stock_highlights","tools":["gangtise.stock_highlights"],"target_type":"multi_stock","securities":[{"name":"中国银行"},{"name":"建设银行"},{"name":"招商银行"}],"time_scope":"latest","display_mode":"text"}',
                "stock_highlights",
                "multi_stock",
            ),
            (
                "我这里有3支股票，中国银行，建设银行，招商银行。我需要对于这三支股票做一下详细的综合分析",
                '{"intent":"multi_watchlist_analysis","tools":["gangtise.multi_watchlist_analysis"],"target_type":"multi_stock","securities":[{"name":"中国银行"},{"name":"建设银行"},{"name":"招商银行"}],"time_scope":"today","display_mode":"text"}',
                "multi_watchlist_analysis",
                "multi_stock",
            ),
            (
                "我该怎么选股呢？",
                '{"intent":"small_talk","tools":[],"target_type":"none","securities":[],"time_scope":"conversation","display_mode":"text"}',
                "small_talk",
                "none",
            ),
        ]
        for question, raw, expected_intent, expected_target in scenarios:
            with self.subTest(question=question), patch.object(
                ai_services, "get_default_llm_config", return_value=model
            ), patch.object(ai_services, "call_openai_compatible_llm", return_value=raw), patch.object(
                ai_services, "search_watchlist_candidates", return_value=[]
            ), patch.object(
                ai_services,
                "resolve_watchlist_candidate",
                side_effect=lambda stock_code="", stock_name="": candidates.get(stock_name) or candidates.get(stock_code),
            ):
                plan, _router_model, route_mode = ai_services.route_hermes_query_intent(question)

            self.assertEqual(route_mode, "llm_router")
            self.assertEqual(plan["intent"], expected_intent)
            self.assertEqual(plan["target_type"], expected_target)

    def test_redirect_hint_does_not_bypass_llm_router(self):
        model = {"key": "router", "provider": "mock", "model_name": "router", "enabled": True}
        raw = '{"intent":"small_talk","tools":[],"target_type":"none","securities":[],"display_mode":"text","reason":"模型判断"}'
        scope = {"status": "redirected", "reason": "仅作为范围提示", "message": "", "suggestions": []}
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services, "call_openai_compatible_llm", return_value=raw
        ) as llm_call:
            _plan, _model, route_mode = ai_services.route_hermes_query_intent(
                "这个问题需要模型判断", scope_result=scope
            )

        self.assertEqual(route_mode, "llm_router")
        llm_call.assert_called_once()

    def test_intent_tool_mismatch_is_rejected_by_server(self):
        with self.assertRaisesRegex(RuntimeError, "hermes_intent_tool_mismatch:stock_today_observation"):
            ai_services.validate_hermes_intent_plan({
                "intent": "stock_today_observation",
                "tools": ["gangtise.market_today_observation"],
                "target_type": "stock",
                "securities": [{"code": "601988"}],
            })

    def test_multi_turn_router_inherits_and_confirms_previous_stock(self):
        model = {"key": "router", "provider": "mock", "model_name": "router", "enabled": True}
        candidates = {
            "601988": {"name": "中国银行", "code": "601988", "security_code": "601988.SH", "market": "CN"},
            "600519": {"name": "贵州茅台", "code": "600519", "security_code": "600519.SH", "market": "CN"},
        }

        def resolve(stock_code="", stock_name=""):
            return candidates.get(stock_code) or candidates.get(stock_name)

        raw = '{"intent":"stock_today_observation","tools":["gangtise.stock_today_observation"],"target_type":"stock","securities":[],"use_context_entities":true,"display_mode":"text","reason":"承接上一轮标的"}'
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services, "call_openai_compatible_llm", return_value=raw
        ), patch.object(ai_services, "resolve_watchlist_candidate", side_effect=resolve):
            plan, _router_model, mode = ai_services.route_hermes_query_intent(
                "那再看一下它今天的风险",
                memory_state={"session": {"recent_symbols": ["601988"]}, "user_memory": {"focus_symbols": []}},
            )

        self.assertEqual(mode, "llm_router")
        self.assertEqual(plan["securities"][0]["security_code"], "601988.SH")
        self.assertEqual(plan["stock_code"], "601988")

    def test_one_pager_index_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "hermes_target_type_mismatch:stock_one_pager"):
            ai_services.validate_hermes_intent_plan({
                "intent": "stock_one_pager",
                "tools": ["gangtise.stock_one_pager"],
                "target_type": "index",
                "securities": [],
            })

    def test_stock_highlights_over_6000_is_rejected_before_entity_lookup(self):
        with self.assertRaisesRegex(RuntimeError, "hermes_stock_highlights_limit_exceeded:6000"):
            ai_services.validate_hermes_intent_plan({
                "intent": "stock_highlights",
                "tools": ["gangtise.stock_highlights"],
                "target_type": "stock",
                "securities": [{"code": str(index)} for index in range(6001)],
            })

    def test_multi_stock_requires_two_confirmed_securities(self):
        with self.assertRaisesRegex(RuntimeError, "hermes_multi_stock_at_least_two_required"):
            ai_services.validate_hermes_intent_plan({
                "intent": "multi_watchlist_analysis",
                "tools": ["gangtise.multi_watchlist_analysis"],
                "target_type": "multi_stock",
                "securities": [{"code": "601988"}],
            })


if __name__ == "__main__":
    unittest.main()
