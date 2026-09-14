import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src.domain import ai_services, market_services
from src.runtime import app


V4_MODEL = {
    "key": "volcengine-deepseek-v4-flash",
    "label": "DeepSeek-V4-Flash正式版",
    "provider": "volcengine",
    "model_name": "deepseek-v4-flash-ga-260731",
    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "test-key",
    "purpose": "general",
    "enabled": True,
}


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _DigestDb:
    _connection = None

    def __init__(self, comments, annotations):
        self.comments = comments
        self.annotations = annotations

    def execute(self, sql, _params):
        return _Rows(self.comments if "watchlist_comments" in sql else self.annotations)


class _FixedDateTime(datetime):
    """Keep relative task-range assertions independent of the test run date."""

    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 9, 20, 12, 0, 0)
        return value.replace(tzinfo=tz) if tz else value


class HermesTaskBddTest(unittest.TestCase):
    def test_given_task_mode_ui_when_rendered_then_it_only_describes_the_user_facing_interaction_capability(self):
        template = (Path(__file__).parents[1] / "templates" / "h5.html").read_text(encoding="utf-8")
        task_note_start = template.index("const taskNote = hermesAssistantMode === 'task'")
        task_note_end = template.index("if (hermesSelectedSkill", task_note_start)
        task_note = template[task_note_start:task_note_end]

        self.assertIn("用户评论与个股 K 线标注", task_note)
        self.assertIn("今日、昨日、本周、本月、今年或所有", task_note)
        self.assertNotIn("gangtise", task_note.lower())
        self.assertIn("assistant_mode: hermesAssistantMode", template)
        self.assertIn("function isHermesInteractionSummaryEntry(entry)", template)
        self.assertIn("将互动归纳加入洞见草稿", template)
        self.assertIn("function buildHermesInteractionInsightDraftTitle(question)", template)
        self.assertIn("hermes_interaction_task", template)
        self.assertIn("intent: (turn || {}).intent || ''", template)
        self.assertIn("intent: data.intent || ''", template)

        draft_action_start = template.index("async function openInsightDraftFromHermes(entryId)")
        draft_action_end = template.index("function buildHermesInteractionInsightDraftTitle(question)", draft_action_start)
        draft_action = template[draft_action_start:draft_action_end]
        self.assertIn("/insight-drafts`,", draft_action)
        self.assertIn("已加入洞见草稿", draft_action)
        self.assertNotIn("switchTab('review')", draft_action)
        self.assertNotIn("reviewProductionPage = true", draft_action)

    def test_given_today_interactions_when_digest_is_built_then_only_tenant_rows_for_the_day_are_returned(self):
        db = _DigestDb(
            [
                {"id": 1, "tenant_slug": "laowang", "stock_code": "600519.SH", "stock_name": "贵州茅台", "comment_text": "关注估值和业绩兑现", "created_by_name": "粉丝甲", "created_by_role": "investor", "created_at": "2026-09-14 09:30:00", "label_tags_json": "[\"基本面\"]"},
                {"id": 2, "tenant_slug": "laowang", "stock_code": "600519.SH", "stock_name": "贵州茅台", "comment_text": "昨天评论", "created_at": "2026-09-13 09:30:00", "label_tags_json": "[]"},
            ],
            [
                {"id": 3, "tenant_slug": "laowang", "stock_code": "600519.SH", "stock_name": "贵州茅台", "note": "突破后观察成交量", "candle_date": "2026-09-14", "created_by_name": "财经老王", "updated_at": "2026-09-14 14:00:00"},
                {"id": 4, "tenant_slug": "laowang", "stock_code": "000001.SH", "stock_name": "上证指数", "note": "当天K线标注也应纳入", "candle_date": "2026-09-14", "created_by_name": "财经老王", "updated_at": "2026-09-13 14:00:00"},
            ],
        )
        with patch.object(market_services, "get_db", return_value=db), patch.object(
            market_services, "gen_watchlist_details", side_effect=AssertionError("task digest must not enrich market data")
        ):
            digest = market_services.build_today_user_interaction_digest("laowang", target_date="2026-09-14")

        self.assertEqual(digest["comment_count"], 1)
        self.assertEqual(digest["annotation_count"], 2)
        self.assertEqual(digest["comments"][0]["content"], "关注估值和业绩兑现")
        self.assertEqual(digest["annotations"][0]["content"], "突破后观察成交量")
        self.assertEqual(digest["stocks"], [
            {"stock_code": "600519.SH", "stock_name": "贵州茅台"},
            {"stock_code": "000001.SH", "stock_name": "上证指数"},
        ])

    def test_given_relative_ranges_when_digest_is_built_then_yesterday_week_and_all_filter_correctly(self):
        db = _DigestDb(
            [
                {"id": 1, "tenant_slug": "laowang", "stock_code": "600519.SH", "stock_name": "贵州茅台", "comment_text": "今日评论", "created_at": "2026-09-20 09:30:00", "label_tags_json": "[]"},
                {"id": 2, "tenant_slug": "laowang", "stock_code": "000001.SH", "stock_name": "上证指数", "comment_text": "昨日评论", "created_at": "2026-09-19 09:30:00", "label_tags_json": "[]"},
                {"id": 3, "tenant_slug": "laowang", "stock_code": "300750.SZ", "stock_name": "宁德时代", "comment_text": "本周早些时候评论", "created_at": "2026-09-15 09:30:00", "label_tags_json": "[]"},
                {"id": 4, "tenant_slug": "laowang", "stock_code": "00700.HK", "stock_name": "腾讯控股", "comment_text": "上月评论", "created_at": "2026-08-31 09:30:00", "label_tags_json": "[]"},
            ],
            [
                {"id": 11, "tenant_slug": "laowang", "stock_code": "600519.SH", "stock_name": "贵州茅台", "note": "昨日K线", "candle_date": "2026-09-19", "updated_at": "2026-09-19 15:00:00"},
                {"id": 12, "tenant_slug": "laowang", "stock_code": "000001.SH", "stock_name": "上证指数", "note": "旧K线昨日修订", "candle_date": "2026-08-01", "updated_at": "2026-09-19 16:00:00"},
                {"id": 13, "tenant_slug": "laowang", "stock_code": "300750.SZ", "stock_name": "宁德时代", "note": "本周K线", "candle_date": "2026-09-15", "updated_at": "2026-09-15 15:00:00"},
                {"id": 14, "tenant_slug": "laowang", "stock_code": "00700.HK", "stock_name": "腾讯控股", "note": "历史K线", "candle_date": "2026-08-31", "updated_at": "2026-08-31 15:00:00"},
            ],
        )
        with patch.object(market_services, "datetime", _FixedDateTime), patch.object(market_services, "get_db", return_value=db):
            yesterday = market_services.build_today_user_interaction_digest("laowang", range_key="yesterday")
            week = market_services.build_today_user_interaction_digest("laowang", range_key="week")
            all_history = market_services.build_today_user_interaction_digest("laowang", range_key="all")

        self.assertEqual(yesterday["range_label"], "昨日")
        self.assertEqual([item["content"] for item in yesterday["comments"]], ["昨日评论"])
        self.assertEqual([item["content"] for item in yesterday["annotations"]], ["昨日K线", "旧K线昨日修订"])
        self.assertEqual(week["comment_count"], 3)
        self.assertEqual(week["annotation_count"], 3)
        self.assertEqual(all_history["range_label"], "所有历史")
        self.assertEqual(all_history["comment_count"], 4)
        self.assertEqual(all_history["annotation_count"], 4)

    def test_given_task_data_when_synthesizing_then_deepseek_v4_is_used_without_gangtise(self):
        site_config = {"llm_registry": {"models": [V4_MODEL], "default_model_key": "volcengine-deepseek-v4-flash"}}
        digest = {"date": "2026-09-14", "comment_count": 0, "annotation_count": 0, "comments": [], "annotations": [], "stocks": []}
        response = '{"answer":"今日暂无可总结的用户评论和K线标注。","summary":"暂无互动","lead_conclusion":"暂无数据","bullets":[],"analysis_sections":[],"next_steps":[],"confidence":"高","citations":["本地互动数据"]}'
        with patch.object(ai_services, "get_site_config", return_value=site_config), patch.object(
            ai_services, "get_tenant_by_slug", return_value={"name": "财经老王"}
        ), patch.object(ai_services, "call_openai_compatible_llm", return_value=response) as llm_call:
            synthesis, model, mode = ai_services.build_hermes_today_user_interaction_synthesis(
                "总结今天互动", digest, tenant_slug="laowang"
            )

        self.assertEqual(model["model_name"], "deepseek-v4-flash-ga-260731")
        self.assertEqual(mode, "task_llm_synthesis")
        self.assertIn("暂无", synthesis["answer"])
        self.assertEqual(llm_call.call_args.kwargs["feature_code"], "hermes_today_user_interaction_task")
        self.assertEqual(llm_call.call_args.kwargs["entry_point"], "hermes_task")
        self.assertEqual(llm_call.call_args.args[0]["key"], "volcengine-deepseek-v4-flash")
        self.assertIn("互动统计摘要", llm_call.call_args.args[2])
        self.assertIn("K线标注是独立的盘面记录", llm_call.call_args.args[1])

    def test_given_many_fan_comments_when_rollup_is_built_then_fan_signals_and_kline_records_are_separated(self):
        rollup = ai_services.build_hermes_user_interaction_rollup({
            "comments": [
                {"author": "粉丝甲", "author_role": "investor", "stock_code": "600519.SH", "stock_name": "贵州茅台", "labels": ["基本面", "估值"]},
                {"author": "粉丝乙", "author_role": "investor", "stock_code": "600519.SH", "stock_name": "贵州茅台", "labels": ["基本面"]},
                {"author": "财经老王", "author_role": "dav", "stock_code": "300750.SZ", "stock_name": "宁德时代", "labels": ["观点"]},
            ],
            "annotations": [
                {"stock_code": "600519.SH", "stock_name": "贵州茅台", "content": "观察量能"},
                {"stock_code": "300750.SZ", "stock_name": "宁德时代", "content": "观察支撑"},
            ],
        })

        self.assertEqual(rollup["fan_comment_count"], 2)
        self.assertEqual(rollup["non_fan_comment_count"], 1)
        self.assertEqual(rollup["known_fan_author_count"], 2)
        self.assertEqual(rollup["comment_label_counts"][0], {"label": "基本面", "count": 2})
        self.assertEqual(rollup["top_stocks"][0]["stock_name"], "贵州茅台")
        self.assertEqual(rollup["top_stocks"][0]["fan_comment_count"], 2)
        self.assertEqual(rollup["top_stocks"][0]["annotation_count"], 1)

    def test_given_dav_task_request_when_running_then_it_bypasses_router_and_gangtise_and_writes_memory(self):
        config = {
            "feature_flags": {"hermes": True},
            "role_capabilities": {"dav": ["hermes", "dav"]},
            "hermes_settings": {},
            "llm_registry": {"models": [V4_MODEL], "default_model_key": "volcengine-deepseek-v4-flash"},
        }
        digest = {"date": "2026-09-14", "comment_count": 1, "annotation_count": 1, "comments": [{"content": "关注风险", "stock_name": "贵州茅台"}], "annotations": [{"content": "观察支撑", "stock_name": "贵州茅台"}], "stocks": [{"stock_name": "贵州茅台", "stock_code": "600519.SH"}]}
        intent_json = '{"supported":true,"time_range":"week","reason":"用户要求归纳本周互动"}'
        llm_json = '{"answer":"粉丝主要关注风险，建议优先回应贵州茅台的支撑位与业绩验证。","summary":"关注风险","lead_conclusion":"先回应风险问题","bullets":["贵州茅台"],"analysis_sections":[],"next_steps":["发布回应"],"confidence":"中","citations":["本地数据"]}'
        persisted = []
        with app.test_request_context("/api/hermes/query", method="POST"):
            with patch.object(ai_services, "get_site_config", return_value=config), patch.object(
                ai_services, "is_hermes_available_for_role", return_value=True
            ), patch.object(ai_services, "get_current_authenticated_user", return_value=None), patch.object(
                ai_services, "load_hermes_memory_state", return_value={"available": True, "storage_mode": "db", "session_id": "task-session", "session": {}, "user_memory": {}, "user_profile": {}, "recent_turns": [], "context_text": ""}
            ), patch.object(ai_services, "build_today_user_interaction_digest", return_value=digest) as digest_call, patch.object(
                ai_services, "call_openai_compatible_llm", side_effect=[intent_json, llm_json]
            ) as llm_call, patch.object(
                ai_services, "route_hermes_query_intent", side_effect=AssertionError("task mode must not use consultation router")
            ), patch.object(
                ai_services, "execute_hermes_tool_plan", side_effect=AssertionError("task mode must not dispatch Gangtise tools")
            ), patch.object(
                ai_services, "gen_watchlist_details", side_effect=AssertionError("task mode must not load market details")
            ), patch.object(
                ai_services, "record_hermes_interception_audit", return_value="audit-task"
            ), patch.object(
                ai_services, "update_hermes_interception_audit_tool_status"
            ), patch.object(
                ai_services, "persist_hermes_turn_and_memory", side_effect=lambda **kwargs: persisted.append(kwargs) or {"storage_mode": "db", "turn_id": "turn-task"}
            ), patch.object(
                ai_services, "persist_hermes_user_profile", return_value={"storage_mode": "db", "profile_snapshot": {}}
            ), patch.object(ai_services, "get_tenant_by_slug", return_value={"name": "财经老王"}):
                result = ai_services.build_hermes_query_response({
                    "tenant_slug": "laowang", "user_role": "dav", "user_profile_id": "财经老王", "user_name": "财经老王",
                    "assistant_mode": "task", "session_id": "task-session", "question": "请做本周互动总结", "messages": [{"role": "user", "content": "请做本周互动总结"}],
                })

        self.assertTrue(result["ok"])
        self.assertEqual(result["assistant_mode"], "task")
        self.assertEqual(result["intent"], "today_user_interaction_task")
        self.assertEqual(result["answer_engine"]["model"]["model_name"], "deepseek-v4-flash-ga-260731")
        self.assertFalse(result["source_policy"]["gangtise_api_enabled"])
        self.assertEqual(result["tool_trace"][0]["tool"], "local.today_user_interactions")
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0]["session_id"], result["session_id"])
        self.assertEqual(digest_call.call_args.kwargs["range_key"], "week")
        self.assertEqual(llm_call.call_count, 2)
        self.assertEqual(llm_call.call_args_list[0].kwargs["feature_code"], "hermes_today_user_interaction_task_intent")
        self.assertEqual(llm_call.call_args_list[1].kwargs["feature_code"], "hermes_today_user_interaction_task")

    def test_given_unsupported_task_prompt_when_running_then_it_explains_the_only_capability_without_reading_data(self):
        config = {
            "feature_flags": {"hermes": True},
            "role_capabilities": {"dav": ["hermes", "dav"]},
            "hermes_settings": {},
            "llm_registry": {"models": [V4_MODEL], "default_model_key": "volcengine-deepseek-v4-flash"},
        }
        unsupported_intent = '{"supported":false,"time_range":"today","reason":"当前任务不属于互动归纳"}'
        with app.test_request_context("/api/hermes/query", method="POST"):
            with patch.object(ai_services, "get_site_config", return_value=config), patch.object(
                ai_services, "is_hermes_available_for_role", return_value=True
            ), patch.object(ai_services, "get_current_authenticated_user", return_value=None), patch.object(
                ai_services, "load_hermes_memory_state", return_value={"available": True, "storage_mode": "db", "session_id": "task-session", "session": {}, "user_memory": {}, "user_profile": {}, "recent_turns": [], "context_text": ""}
            ), patch.object(ai_services, "build_today_user_interaction_digest", side_effect=AssertionError("unsupported task must not read interactions")), patch.object(
                ai_services, "call_openai_compatible_llm", return_value=unsupported_intent
            ) as llm_call, patch.object(
                ai_services, "record_hermes_interception_audit", return_value="audit-task"
            ), patch.object(
                ai_services, "update_hermes_interception_audit_tool_status"
            ), patch.object(
                ai_services, "persist_hermes_turn_and_memory", return_value={"storage_mode": "db", "turn_id": "turn-task"}
            ), patch.object(
                ai_services, "persist_hermes_user_profile", return_value={"storage_mode": "db", "profile_snapshot": {}}
            ):
                result = ai_services.build_hermes_query_response({
                    "tenant_slug": "laowang", "user_role": "dav", "user_profile_id": "财经老王", "user_name": "财经老王",
                    "assistant_mode": "task", "session_id": "task-session", "question": "帮我生成一份个股深度报告",
                })

        self.assertTrue(result["ok"])
        self.assertEqual(result["intent"], "capability_unavailable")
        self.assertIn("任务模式当前仅提供一项能力", result["answer"])
        self.assertIn("用户评论和个股 K 线标注", result["answer"])
        self.assertEqual(llm_call.call_count, 1)

    def test_given_investor_task_request_when_running_then_access_is_denied(self):
        with patch.object(ai_services, "get_site_config", return_value={"feature_flags": {"hermes": True}}), patch.object(
            ai_services, "is_hermes_available_for_role", return_value=True
        ):
            with self.assertRaisesRegex(ValueError, "hermes_task_dav_only"):
                ai_services.build_hermes_query_response({
                    "tenant_slug": "laowang", "user_role": "investor", "assistant_mode": "task", "question": "总结今天互动"
                })
