import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from src.domain import ai_services, core_services, market_services


class HermesGangtiseCapabilitiesTest(unittest.TestCase):
    def test_explicit_hermes_question_precedes_stale_conversation_messages(self):
        self.assertEqual(
            ai_services.extract_hermes_question_text(
                [{"role": "user", "content": "上一轮问题"}],
                "对今天中国银行的股票做下个股分析，看看今天整体情况怎么样",
            ),
            "对今天中国银行的股票做下个股分析，看看今天整体情况怎么样",
        )

    def test_hermes_question_falls_back_to_latest_user_message_for_legacy_clients(self):
        self.assertEqual(
            ai_services.extract_hermes_question_text(
                [
                    {"role": "user", "content": "上一轮问题"},
                    {"role": "assistant", "content": "上一轮回答"},
                    {"role": "user", "content": "当前问题"},
                ],
                "",
            ),
            "当前问题",
        )

    def test_h5_snapshots_current_question_before_clearing_inputs(self):
        template = (Path(__file__).parents[1] / "templates" / "h5.html").read_text(encoding="utf-8")
        snapshot_index = template.index("const messagesSnapshot = buildHermesMessagesPayload();")
        clear_index = template.index("clearHermesQuestionInputs({ focus: true });")
        request_index = template.index("messages: messagesSnapshot,")
        self.assertLess(snapshot_index, clear_index)
        self.assertLess(clear_index, request_index)
        self.assertIn("messagesSnapshot.push({ role: 'user', content: question });", template)

    def test_hermes_router_uses_one_remote_request_with_generation_budget(self):
        router_json = (
            '{"intent":"stock_today_observation",'
            '"tools":["gangtise.stock_today_observation"],'
            '"target_type":"stock","securities":[{"name":"中国银行"}],'
            '"time_scope":"today","display_mode":"text"}'
        )
        model = {
            "key": "admin-default",
            "base_url": "http://8.155.160.194:6031/api",
            "model_name": "qwen3.5:27b-q4_K_M",
            "api_key": "configured",
            "enabled": True,
        }
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services, "call_openai_compatible_llm", return_value=router_json
        ) as llm_call, patch.object(
            ai_services, "search_watchlist_candidates", return_value=[]
        ), patch.object(
            ai_services, "find_watchlist_code_from_text", return_value="601988"
        ), patch.object(
            ai_services, "resolve_watchlist_candidate",
            return_value={"name": "中国银行", "code": "601988", "security_code": "601988.SH"},
        ):
            ai_services.route_hermes_query_intent(
                "对今天中国银行的股票做下个股分析，看看今天整体情况怎么样"
            )

        llm_call.assert_called_once()
        self.assertEqual(llm_call.call_args.kwargs["request_timeout_seconds"], 60)
        self.assertEqual(llm_call.call_args.kwargs["max_tokens"], 512)

    def test_router_sends_the_current_question_verbatim_and_uses_memory_only_as_context(self):
        model = {
            "key": "admin-default",
            "base_url": "http://8.155.160.194:6031/api",
            "model_name": "qwen3.5:27b-q4_K_M",
            "api_key": "configured",
            "enabled": True,
        }
        current_question = "对今天中国银行的股票做下个股分析，看看今天整体情况怎么样"
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services,
            "call_openai_compatible_llm",
            return_value='{"intent":"stock_today_observation","tools":["gangtise.stock_today_observation"],"target_type":"stock","securities":[{"name":"中国银行"}],"time_scope":"today","display_mode":"text"}',
        ) as llm_call, patch.object(
            ai_services, "search_watchlist_candidates", return_value=[]
        ), patch.object(
            ai_services,
            "resolve_watchlist_candidate",
            return_value={"name": "中国银行", "code": "601988", "security_code": "601988.SH"},
        ):
            ai_services.route_hermes_query_intent(
                current_question,
                messages=[{"role": "user", "content": "上一轮问题"}],
                memory_state={"session": {"last_intent": "small_talk"}},
            )

        user_prompt = llm_call.call_args.args[2]
        self.assertIn(f"用户问题：{current_question}", user_prompt)
        self.assertIn("上一轮问题", user_prompt)
        self.assertNotIn("上一轮问题\n是否有附件", user_prompt)

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

    def test_admin_workflow_catalog_exposes_current_hermes_execution_chain(self):
        workflow = ai_services.build_default_hermes_agent_workflow_definition()
        labels = [item["label"] for item in workflow["nodes"]]
        edges = workflow["edges"]
        router_edges = [item for item in edges if item["from"] == "intent_router"]

        self.assertEqual(workflow["id"], "hermes_agent")
        self.assertIn("LLM 意图拆解", labels)
        self.assertIn("任务级工具调度", labels)
        self.assertIn("会话与用户记忆写回", labels)
        self.assertEqual(
            [(item["from"], item["to"]) for item in router_edges],
            [("intent_router", "semantic_interception")],
        )
        interception_edges = [item for item in edges if item["from"] == "semantic_interception"]
        self.assertEqual(
            {item["label"] for item in interception_edges},
            {"拒绝", "需补充", "闲聊", "单任务", "多任务", "人工审核"},
        )
        self.assertIn("语义拦截 Skill", labels)
        self.assertIn("基础技术校验", labels)
        self.assertTrue(any(item.get("visual_only") for item in workflow["nodes"]))
        for label in ("今日个股观察", "今日大盘分析", "个股结构化分析报告", "个股看点摘要", "多自选股综合分析", "闲聊回答生成"):
            self.assertIn(label, labels)
        self.assertTrue(any(item.get("condition") == "stock_today_observation" for item in edges))
        self.assertIn("Gangtise 研究正文原样返回", workflow["summary"])

    def test_visual_only_workflow_nodes_are_retained_for_admin_but_not_executed(self):
        workflow = {
            "id": "visual_branch_test",
            "nodes": [
                {"id": "input", "label": "输入", "processor": "input"},
                {"id": "branch", "label": "条件", "processor": "branch", "visual_only": True},
                {"id": "output", "label": "输出", "processor": "output"},
            ],
            "edges": [
                {"from": "input", "to": "branch", "label": "条件边", "condition": "enabled"},
                {"from": "branch", "to": "output"},
            ],
        }
        result = ai_services.run_declared_agent_workflow(
            workflow,
            executor_registry={
                "input": lambda **_: {"output": "input"},
                "branch": lambda **_: self.fail("visual branch must not execute"),
                "output": lambda **_: {"output": "output"},
            },
        )

        self.assertTrue(result["workflow"]["nodes"][1]["visual_only"])
        self.assertEqual(result["workflow"]["edges"][0]["label"], "条件边")
        self.assertEqual(result["workflow"]["edges"][0]["condition"], "enabled")
        self.assertEqual(result["node_results"]["branch"]["status"], "design_only")
        self.assertEqual(result["node_results"]["output"]["status"], "ok")

    def test_admin_workflow_center_renders_agent_graph_not_vertical_sequence(self):
        template = (Path(__file__).parents[1] / "templates" / "admin.html").read_text(encoding="utf-8")

        self.assertIn("function buildAgentWorkflowTopDownLayout", template)
        self.assertIn("const layout = buildAgentWorkflowTopDownLayout(nodes, edges);", template)
        self.assertIn("function renderAgentWorkflowEdges", template)
        self.assertIn("agent-workflow-edge-label", template)
        self.assertIn("workflow-node agent-workflow-node", template)
        self.assertNotIn("function buildAgentWorkflowVerticalOrder", template)

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

    def test_llm_response_parser_accepts_openai_content_variants(self):
        responses = [
            {"choices": [{"message": {"content": [{"type": "text", "text": "片段回答"}]}}]},
            {"choices": [{"message": {"content": {"type": "output_text", "text": "对象回答"}}}]},
            {"choices": [{"text": "兼容回答"}]},
        ]
        model = {
            "key": "admin-default",
            "base_url": "http://8.155.160.194:6031/api",
            "model_name": "qwen3.5:27b-q4_K_M",
            "api_key": "key",
            "enabled": True,
        }
        with patch.object(ai_services.requests, "Session") as session_factory, patch.object(
            ai_services, "log_token_usage"
        ):
            session_factory.return_value.post.side_effect = [
                type("Response", (), {"status_code": 200, "text": "", "json": lambda self, payload=payload: payload})()
                for payload in responses
            ]
            results = [
                ai_services.call_openai_compatible_llm(model, "system", "user")
                for _ in responses
            ]

        self.assertEqual(results, ["片段回答", "对象回答", "兼容回答"])

    def test_llm_reasoning_only_response_remains_strict_failure(self):
        payload = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "", "reasoning_content": "内部推理，不应展示"},
                }
            ]
        }
        response = type("Response", (), {"status_code": 200, "text": "", "json": lambda self: payload})()
        model = {
            "key": "admin-default",
            "base_url": "http://8.155.160.194:6031/api",
            "model_name": "qwen3.5:27b-q4_K_M",
            "api_key": "key",
            "enabled": True,
        }
        with patch.object(ai_services.requests, "Session") as session_factory, patch.object(
            ai_services, "log_token_usage"
        ), patch.object(ai_services.app.logger, "warning") as warning:
            session_factory.return_value.post.return_value = response
            with self.assertRaisesRegex(RuntimeError, "empty_llm_response:reasoning_only"):
                ai_services.call_openai_compatible_llm(model, "system", "user", feature_code="hermes_intent_router")

        warning.assert_called_once()
        self.assertNotIn("内部推理", str(warning.call_args))

    def test_hermes_turn_metrics_reads_task_intents_from_tags(self):
        metrics = ai_services._extract_hermes_turn_metrics(
            {
                "question_text": "组合分析",
                "answer_text": "已完成",
                "intent": "composite_research",
                "tags_json": '{"task_intents":["stock_today_observation","market_today_observation"]}',
                "memory_summary_json": "{}",
                "tool_trace_json": "[]",
            }
        )

        self.assertEqual(
            metrics["task_intents"],
            ["stock_today_observation", "market_today_observation"],
        )

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

    def test_contextual_market_followup_is_routed_with_context_and_synthesized_by_llm(self):
        model = {"key": "router", "provider": "mock", "model_name": "router", "enabled": True}
        router_json = (
            '{"disposition":"execute","intent":"market_today_observation",'
            '"tools":["gangtise.market_today_observation"],"target_type":"index",'
            '"securities":[],"time_scope":"today","use_context_entities":true,'
            '"answer_with_context":true,"display_mode":"structured","reason":"延续上一轮A股大盘分析"}'
        )
        messages = [
            {"role": "user", "content": "分析今天A股市场整体走势"},
            {"role": "assistant", "content": "上证和深证今天均需结合资金与情绪观察。"},
        ]
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services, "call_openai_compatible_llm", return_value=router_json
        ):
            plan, _router_model, route_mode = ai_services.route_hermes_query_intent(
                "继续分析A股市场走向，请基于上下文，来分析回答。",
                messages=messages,
                memory_state={"session": {"last_intent": "market_today_observation"}},
            )

        self.assertEqual(route_mode, "llm_router")
        self.assertEqual(plan["intent"], "market_today_observation")
        self.assertTrue(plan["use_context_entities"])
        self.assertTrue(plan["answer_with_context"])

        answer_json = '{"answer":"结合上轮走势，当前仍应优先观察量能与风险偏好。","summary":"A股续问分析","bullets":[],"analysis_sections":[],"next_steps":[],"citations":[]}'
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services, "call_openai_compatible_llm", return_value=answer_json
        ) as answer_call, patch.object(
            ai_services, "get_tenant_by_slug", return_value={"name": "财经老王"}
        ):
            synthesis, answer_model, answer_mode = ai_services.synthesize_hermes_answer(
                "继续分析A股市场走向，请基于上下文，来分析回答。",
                plan,
                {"gangtise_market_observation": {"text": "上证量能改善，市场情绪中性偏强。", "provider": "Gangtise"}},
                tenant_slug="laowang",
                messages=messages,
            )

        self.assertEqual(answer_mode, "llm_contextual_research")
        self.assertIs(answer_model, model)
        self.assertIn("量能", synthesis["answer"])
        self.assertIn("上证量能改善", answer_call.call_args.args[2])

    def test_unavailable_capability_returns_polite_notice_without_tools_or_answer_llm(self):
        model = {"key": "router", "provider": "mock", "model_name": "router", "enabled": True}
        router_json = '{"disposition":"unavailable","intent":"capability_unavailable","tools":[],"reason":"该功能尚未上线","capability_request":"自动下单与仓位管理"}'
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services, "call_openai_compatible_llm", return_value=router_json
        ):
            plan, _router_model, route_mode = ai_services.route_hermes_query_intent("请帮我自动下单并管理仓位")

        outputs, trace = ai_services.execute_hermes_tool_plan(plan, "laowang", "请帮我自动下单并管理仓位")
        with patch.object(ai_services, "get_default_llm_config") as answer_model:
            synthesis, model_used, answer_mode = ai_services.synthesize_hermes_answer(
                "请帮我自动下单并管理仓位", plan, outputs
            )

        self.assertEqual(route_mode, "llm_router")
        self.assertEqual(plan["intent"], "capability_unavailable")
        self.assertEqual(plan["tools"], [])
        self.assertEqual(plan["capability_request"], "自动下单与仓位管理")
        self.assertEqual(trace, [])
        self.assertEqual(answer_mode, "capability_unavailable")
        self.assertIsNone(model_used)
        self.assertIn("还在开发中", synthesis["answer"])
        self.assertIn("已经记录下来", synthesis["answer"])
        self.assertIn("近期推出", synthesis["answer"])
        answer_model.assert_not_called()

    def test_unavailable_capability_is_persisted_as_an_admin_demand_metric(self):
        plan = {
            "intent": "capability_unavailable",
            "tools": [],
            "target_type": "none",
            "time_scope": "conversation",
        }
        synthesis = ai_services.build_hermes_capability_unavailable_synthesis("请提供税务筹划服务", plan)
        payload = ai_services.extract_hermes_memory_payload(
            "请提供税务筹划服务",
            plan,
            synthesis,
            actor_context={"tenant_slug": "laowang", "profile_id": "财经老王", "user_role": "dav"},
        )
        missing = payload["turn_record"]["memory_summary"]["missing_capability"]

        self.assertEqual(missing["code"], "capability_unavailable:请提供税务筹划服务")
        self.assertEqual(missing["label"], "请提供税务筹划服务")
        self.assertEqual(missing["category"], "产品能力")
        self.assertIn("请提供税务筹划服务", payload["turn_record"]["tags"]["missing_capability_tags"])
        self.assertEqual(ai_services._normalize_hermes_mode_label("capability_unavailable"), "能力开发中")

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

    def test_planner_clarification_skips_research_tools_and_answer_llm(self):
        model = {"key": "router", "provider": "mock", "model_name": "router", "enabled": True}
        raw = (
            '{"disposition":"clarify","clarifying_question":"请说明要分析哪只股票，以及要看今天还是最近一期。",'
            '"tools":[],"reason":"缺少证券对象"}'
        )
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services, "call_openai_compatible_llm", return_value=raw
        ) as llm_call, patch.object(ai_services, "call_gangtise_agent_sse") as gangtise_call:
            plan, _router_model, route_mode = ai_services.route_hermes_query_intent("帮我分析一下")
            outputs, trace = ai_services.execute_hermes_tool_plan(plan, "laowang", "帮我分析一下")
            synthesis, answer_model, answer_mode = ai_services.synthesize_hermes_answer("帮我分析一下", plan, outputs)

        self.assertEqual(route_mode, "llm_router")
        self.assertEqual(plan["intent"], "clarify")
        self.assertEqual(trace, [])
        self.assertEqual(answer_mode, "clarification")
        self.assertIsNone(answer_model)
        self.assertIn("哪只股票", synthesis["answer"])
        self.assertEqual(llm_call.call_count, 1)
        gangtise_call.assert_not_called()

    def test_composite_execution_keeps_successful_gangtise_result_when_another_task_fails(self):
        plan = {
            "intent": "composite_research",
            "tasks": [
                {"intent": "stock_today_observation", "tools": ["gangtise.stock_today_observation"]},
                {"intent": "market_today_observation", "tools": ["gangtise.market_today_observation"]},
            ],
        }
        registry = {
            "gangtise.stock_today_observation": {
                "output_key": "gangtise_stock_observation",
                "executor": lambda runtime: {"text": "中国银行今日观察正文", "provider": "Gangtise"},
            },
            "gangtise.market_today_observation": {
                "output_key": "gangtise_market_observation",
                "executor": lambda runtime: (_ for _ in ()).throw(RuntimeError("上游超时")),
            },
        }
        with patch.object(ai_services, "get_hermes_tool_registry", return_value=registry):
            outputs, trace = ai_services.execute_hermes_tool_plan(plan, "laowang", "分别看个股和大盘")
        synthesis, model, answer_mode = ai_services.synthesize_hermes_answer("分别看个股和大盘", plan, outputs)

        self.assertEqual(answer_mode, "composite_direct")
        self.assertIsNone(model)
        self.assertIn("中国银行今日观察正文", synthesis["answer"])
        self.assertIn("本任务未完成", synthesis["answer"])
        self.assertEqual(len(outputs["composite_tasks"]), 2)
        self.assertTrue(any(item.get("status") == "error" for item in trace))

    def test_mixed_composite_answers_chat_with_admin_llm_and_keeps_gangtise_report_out_of_prompt(self):
        question = "你有什么功能，自我介绍一下吧，你多大呀？今天上证指数表现如何？"
        plan = {
            "intent": "composite_research",
            "tasks": [
                {"intent": "product_help", "tools": []},
                {"intent": "small_talk", "tools": []},
                {"intent": "market_today_observation", "tools": ["gangtise.market_today_observation"]},
            ],
        }
        gangtise_report = "上证指数 Gangtise 原始观察报告，禁止进入回答 LLM。"
        outputs = {
            "composite_tasks": [
                {"task_index": 0, "intent": "product_help", "status": "ok", "plan": plan["tasks"][0], "outputs": {}},
                {"task_index": 1, "intent": "small_talk", "status": "ok", "plan": plan["tasks"][1], "outputs": {}},
                {
                    "task_index": 2,
                    "intent": "market_today_observation",
                    "status": "ok",
                    "plan": plan["tasks"][2],
                    "outputs": {"gangtise_market_observation": {"text": gangtise_report, "provider": "Gangtise AI"}},
                },
            ],
        }
        model = {"key": "admin-default", "label": "Admin 默认模型", "provider": "mock", "model_name": "mock", "enabled": True}
        llm_response = (
            '{"answer":"我是小金智能体，没有真实年龄。可提供六类能力，包括今日个股观察、今日大盘综合分析、个股深化研究、个股看点摘要、多支自选股综合分析和多轮闲聊。",'
            '"summary":"已回答功能与自我介绍","lead_conclusion":"","bullets":[],"analysis_sections":[],"next_steps":[],"confidence":"","citations":[]}'
        )
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services, "get_tenant_by_slug", return_value={"name": "财经老王"}
        ), patch.object(ai_services, "call_openai_compatible_llm", return_value=llm_response) as llm_call:
            synthesis, answer_model, answer_mode = ai_services.synthesize_hermes_answer(
                question,
                plan,
                outputs,
                tenant_slug="laowang",
                user_role="dav",
            )

        self.assertEqual(answer_mode, "composite_mixed_llm")
        self.assertEqual(answer_model["key"], "admin-default")
        self.assertEqual(llm_call.call_count, 1)
        llm_prompt = llm_call.call_args.args[2]
        self.assertIn(question, llm_prompt)
        self.assertIn("product_help", llm_prompt)
        self.assertIn("small_talk", llm_prompt)
        self.assertNotIn(gangtise_report, llm_prompt)
        self.assertIn("没有真实年龄", synthesis["answer"])
        self.assertIn(gangtise_report, synthesis["answer"])
        self.assertIn("### Gangtise 研究原文", synthesis["answer"])
        self.assertIn("Admin 默认 LLM", synthesis["citations"])
        self.assertIn("Gangtise AI 研究原文", synthesis["citations"])

    def test_pure_gangtise_composite_remains_direct_without_answer_llm(self):
        plan = {
            "intent": "composite_research",
            "tasks": [
                {"intent": "stock_today_observation", "tools": ["gangtise.stock_today_observation"]},
                {"intent": "market_today_observation", "tools": ["gangtise.market_today_observation"]},
            ],
        }
        outputs = {
            "composite_tasks": [
                {
                    "task_index": 0,
                    "intent": "stock_today_observation",
                    "status": "ok",
                    "plan": plan["tasks"][0],
                    "outputs": {"gangtise_stock_observation": {"text": "个股 Gangtise 原文"}},
                },
                {
                    "task_index": 1,
                    "intent": "market_today_observation",
                    "status": "ok",
                    "plan": plan["tasks"][1],
                    "outputs": {"gangtise_market_observation": {"text": "大盘 Gangtise 原文"}},
                },
            ],
        }
        with patch.object(ai_services, "call_openai_compatible_llm") as llm_call:
            synthesis, answer_model, answer_mode = ai_services.synthesize_hermes_answer("分别看个股和大盘", plan, outputs)

        self.assertEqual(answer_mode, "composite_direct")
        self.assertIsNone(answer_model)
        self.assertIn("个股 Gangtise 原文", synthesis["answer"])
        self.assertIn("大盘 Gangtise 原文", synthesis["answer"])
        llm_call.assert_not_called()

    def test_mixed_composite_trace_is_marked_as_llm_and_gangtise_original(self):
        trace = ai_services.build_hermes_agent_trace(
            {"intent": "composite_research", "task_family": "research_qa", "tasks": [{}, {}, {}]},
            [],
            route_mode="llm_router",
            answer_mode="composite_mixed_llm",
        )
        answer_step = next(item for item in trace["steps"] if item["key"] == "answer")
        self.assertEqual(answer_step["status"], "ok")
        self.assertIn("LLM + Gangtise 原文", answer_step["detail"])

    def test_composite_memory_keeps_task_intents_and_recent_symbols(self):
        payload = ai_services.extract_hermes_memory_payload(
            "中国银行和贵州茅台分别做今日观察",
            {
                "intent": "composite_research",
                "tasks": [
                    {"intent": "stock_today_observation"},
                    {"intent": "stock_highlights"},
                ],
            },
            {"answer": "已完成", "summary": "两项研究"},
            actor_context={"tenant_slug": "laowang", "profile_id": "tester", "user_role": "dav"},
            memory_state={"session": {}, "user_memory": {}, "user_profile": {}},
        )

        self.assertEqual(payload["profile_snapshot"]["task_intents"], ["stock_today_observation", "stock_highlights"])
        self.assertEqual(payload["session_snapshot"]["last_tags"]["task_intents"], ["stock_today_observation", "stock_highlights"])

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

    def test_interception_skill_is_opt_in_and_disabled_does_not_call_a_second_llm(self):
        decision = ai_services.evaluate_hermes_interception_skills(
            "请帮我分析中国银行",
            {"intent": "stock_today_observation"},
            hermes_settings={
                "interception_skills_enabled": False,
                "interception_skills": [{
                    "id": "rule-1",
                    "rule_prompt": "判断是否为直接交易指令",
                    "action": "block",
                }],
            },
        )

        self.assertFalse(decision["enabled"])
        self.assertEqual(decision["status"], "disabled")

    def test_enabled_interception_skill_can_block_without_calling_gangtise(self):
        model = {"key": "router", "provider": "mock", "model_name": "router", "enabled": True}
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services,
            "call_openai_compatible_llm",
            return_value='{"decisions":[{"skill_id":"no-buy","matched":true,"confidence":0.98,"reason":"用户明确要求买入"}]}',
        ) as llm_call:
            decision = ai_services.evaluate_hermes_interception_skills(
                "明天买入中国银行并满仓",
                {"intent": "stock_today_observation", "tools": ["gangtise.stock_today_observation"]},
                hermes_settings={
                    "interception_skills_enabled": True,
                    "interception_skills": [{
                        "id": "no-buy",
                        "label": "直接交易指令",
                        "rule_prompt": "识别买入、卖出、满仓或仓位要求",
                        "action": "block",
                        "version": "3",
                    }],
                },
            )

        self.assertEqual(llm_call.call_count, 1)
        self.assertEqual(decision["status"], "intercepted")
        self.assertEqual(decision["action"], "block")
        self.assertEqual(decision["selected_skill"]["version"], "3")
        self.assertEqual(decision["matched_skill_ids"], ["no-buy"])

    def test_interception_skill_can_return_clarify_action(self):
        model = {"key": "router", "provider": "mock", "model_name": "router", "enabled": True}
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services,
            "call_openai_compatible_llm",
            return_value='{"decisions":[{"skill_id":"need-context","matched":true,"confidence":0.9,"reason":"缺少明确时间范围"}]}',
        ):
            decision = ai_services.evaluate_hermes_interception_skills(
                "帮我看看这只股票",
                {"intent": "stock_today_observation"},
                hermes_settings={
                    "interception_skills_enabled": True,
                    "interception_skills": [{
                        "id": "need-context",
                        "rule_prompt": "问题缺少证券或时间范围时要求补充",
                        "action": "clarify",
                        "user_message": "请补充股票名称和希望查看的时间范围。",
                    }],
                },
            )

        self.assertEqual(decision["action"], "clarify")
        self.assertEqual(decision["user_message"], "请补充股票名称和希望查看的时间范围。")

    def test_interception_skill_requires_a_decision_for_every_configured_rule(self):
        model = {"key": "router", "provider": "mock", "model_name": "router", "enabled": True}
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services,
            "call_openai_compatible_llm",
            return_value='{"decisions":[{"skill_id":"rule-a","matched":false,"confidence":0.9,"reason":"未命中"}]}',
        ):
            with self.assertRaisesRegex(RuntimeError, "missing_skills:rule-b"):
                ai_services.evaluate_hermes_interception_skills(
                    "请分析中国银行",
                    {"intent": "stock_today_observation"},
                    hermes_settings={
                        "interception_skills_enabled": True,
                        "interception_skills": [
                            {"id": "rule-a", "rule_prompt": "规则 A"},
                            {"id": "rule-b", "rule_prompt": "规则 B"},
                        ],
                    },
                )

    def test_planner_safe_disposition_cannot_execute_accidental_tasks(self):
        model = {"key": "router", "provider": "mock", "model_name": "router", "enabled": True}
        with patch.object(ai_services, "get_default_llm_config", return_value=model), patch.object(
            ai_services,
            "call_openai_compatible_llm",
            return_value=(
                '{"disposition":"chat","reason":"用户在闲聊",'
                '"tasks":[{"intent":"stock_today_observation","tools":["gangtise.stock_today_observation"],'
                '"target_type":"stock","securities":[{"name":"中国银行"}],"time_scope":"today"}]}'
            ),
        ), patch.object(ai_services, "search_watchlist_candidates", return_value=[]):
            plan, _model, _mode = ai_services.route_hermes_query_intent("你好，顺便分析中国银行")

        self.assertEqual(plan["intent"], "small_talk")
        self.assertEqual(plan["disposition"], "chat")
        self.assertEqual(plan["tools"], [])

    def test_question_extraction_rejects_non_string_payload_and_preserves_current_text(self):
        with self.assertRaisesRegex(ValueError, "hermes_question_invalid_type"):
            ai_services.extract_hermes_question_text([], {"text": "not a question"})

        current = "  原始问题：请分析中国银行  \n"
        self.assertEqual(ai_services.extract_hermes_question_text([], current), current)

    def test_human_review_interception_has_a_non_llm_user_response(self):
        synthesis, model, mode = ai_services.synthesize_hermes_answer(
            "请帮我处理这个问题",
            {
                "intent": "human_review",
                "interception_message": "已提交人工审核，请等待处理。",
                "interception_reason": "命中人工审核规则",
            },
            {},
        )

        self.assertIsNone(model)
        self.assertEqual(mode, "human_review")
        self.assertEqual(synthesis["answer"], "已提交人工审核，请等待处理。")

    def test_interception_audit_contains_raw_question_planner_and_skill_version(self):
        class FakeDb:
            def __init__(self):
                self.values = None

            def execute(self, _sql, params=()):
                self.values = tuple(params)
                return self

            def commit(self):
                return None

        fake_db = FakeDb()
        with patch.object(ai_services, "get_db", return_value=fake_db), patch.object(
            ai_services, "ensure_hermes_interception_audit_table", return_value=None
        ):
            audit_id = ai_services.record_hermes_interception_audit(
                question_text="原始问题：请分析中国银行",
                router_plan={"intent": "stock_today_observation", "tasks": [{"intent": "stock_today_observation"}]},
                decision={
                    "status": "intercepted",
                    "action": "block",
                    "reason": "命中规则",
                    "matched_skill_ids": ["no-buy"],
                    "results": [{"skill_id": "no-buy", "rule_version": "7", "matched": True}],
                },
                tenant_slug="laowang",
                user_profile_id="财经老王",
            )

        self.assertTrue(audit_id.startswith("hermes-interception-"))
        self.assertIsNotNone(fake_db.values)
        self.assertIn("原始问题：请分析中国银行", fake_db.values)
        self.assertTrue(any('"stock_today_observation"' in str(value) for value in fake_db.values))
        self.assertTrue(any('"rule_version": "7"' in str(value) for value in fake_db.values))

    def test_interception_audit_failure_does_not_fail_normal_answer(self):
        with patch.object(ai_services, "ensure_hermes_interception_audit_table", side_effect=RuntimeError("db down")), patch.object(
            ai_services.app.logger, "exception"
        ) as log_exception:
            audit_id = ai_services.record_hermes_interception_audit(
                question_text="你好",
                router_plan={"intent": "small_talk"},
                decision={"status": "disabled", "action": "allow"},
            )

        self.assertEqual(audit_id, "")
        log_exception.assert_called_once()

    def test_interception_skill_configuration_normalizes_invalid_priority(self):
        skills = core_services.normalize_hermes_interception_skills([
            {"id": "bad-priority", "priority": "not-a-number", "rule_prompt": "判断规则"},
            {"id": "bad-priority", "priority": 1, "rule_prompt": "重复规则"},
        ])

        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]["priority"], 100)


if __name__ == "__main__":
    unittest.main()
