"""BDD contracts for the Gangtise noon/night finance broadcast workflow."""

import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from src.domain import market_services


RECORDED_GANGTISE_RESPONSE = {
    "code": "000000",
    "status": True,
    "data": {
        "list": [
            {"reportTypeName": "早报", "closeReading": "早间市场摘要。"},
            {"reportTypeName": "午报", "closeReading": "午间市场摘要。政策、行业与公司动态。"},
            {"reportTypeName": "晚报", "closeReading": "晚间市场摘要。海外市场与明日观察。"},
        ]
    },
}


class DailyFinanceBroadcastBDDTest(unittest.TestCase):
    def test_given_beijing_time_when_slot_is_resolved_then_manual_runs_use_expected_report(self):
        noon, noon_date, _ = market_services._daily_finance_broadcast_slot(
            datetime(2026, 9, 16, 12, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        )
        night, night_date, _ = market_services._daily_finance_broadcast_slot(
            datetime(2026, 9, 16, 19, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        )
        early, early_date, _ = market_services._daily_finance_broadcast_slot(
            datetime(2026, 9, 16, 1, 24, tzinfo=ZoneInfo("Asia/Shanghai"))
        )
        self.assertEqual((noon, noon_date), ("noon", "2026-09-16"))
        self.assertEqual((night, night_date), ("night", "2026-09-16"))
        self.assertEqual((early, early_date), ("night", "2026-09-15"))

    def test_given_recorded_success_json_when_fetching_noon_then_matching_text_is_returned(self):
        with patch.object(
            market_services,
            "post_gangtise_openapi_json",
            return_value=(200, RECORDED_GANGTISE_RESPONSE, 42),
        ) as post:
            result = market_services.fetch_gangtise_daily_finance_broadcast("noon", "2026-09-16")
        post.assert_called_once_with(
            "/application/open-ai/hot-topic/getList",
            {"startDate": "2026-09-16", "endDate": "2026-09-16", "withCloseReading": True},
            timeout=90,
        )
        self.assertEqual(result["report_kind"], "noon")
        self.assertIn("午间市场摘要", result["text"])
        self.assertEqual(result["selected_record"]["reportTypeName"], "午报")
        self.assertEqual(result["endpoint"], "/application/open-ai/hot-topic/getList")

    def test_given_gangtise_english_report_types_when_fetching_night_then_evening_briefing_is_selected(self):
        response = {
            "code": "000000",
            "status": True,
            "data": {"list": [
                {"reportTypeName": "morningbriefing", "content": "早间内容"},
                {"reportTypeName": "noonbriefing", "content": "午间内容"},
                {"reportTypeName": "eveningbriefing", "content": "晚间内容：海外市场与明日观察"},
                {"reportTypeName": "afternoonflash", "content": "下午快讯"},
            ]},
        }
        with patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 10)):
            result = market_services.fetch_gangtise_daily_finance_broadcast("night", "2026-09-15")
        self.assertEqual(result["selected_record"]["reportTypeName"], "eveningbriefing")
        self.assertIn("晚间内容", result["text"])

    def test_given_night_has_no_readable_text_when_fetching_then_noon_is_used_as_provider_fallback(self):
        response = {
            "code": "000000",
            "status": True,
            "data": {"list": [
                {"reportTypeName": "eveningbriefing", "title": "晚间摘要"},
                {"reportTypeName": "noonbriefing", "content": "可用的午间播报内容"},
            ]},
        }
        with patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 10)):
            result = market_services.fetch_gangtise_daily_finance_broadcast("night", "2026-09-15")
        self.assertEqual(result["requested_report_kind"], "night")
        self.assertEqual(result["selected_report_kind"], "noon")
        self.assertIn("可用的午间播报内容", result["text"])
        self.assertEqual(market_services._format_daily_broadcast_markdown(result["text"], "noon", "2026-09-15").splitlines()[0], "# 午间财经播报")

    def test_given_topic_digest_is_in_title_when_fetching_then_title_is_used_as_readable_fallback(self):
        response = {
            "code": "000000",
            "status": True,
            "data": {"list": [
                {"title": "英伟达 Rubin 液冷价值量跃升、人形机器人产能供不应求 eveningbriefing"},
            ]},
        }
        with patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 10)):
            result = market_services.fetch_gangtise_daily_finance_broadcast("night", "2026-09-15")
        self.assertEqual(result["selected_report_kind"], "night")
        self.assertEqual(result["text_source"], "topic_title_fallback")
        self.assertIn("液冷价值量跃升", result["text"])

    def test_given_actual_gangtise_topic_shape_when_fetching_then_nested_close_reading_content_is_extracted(self):
        response = {
            "code": "000000",
            "msg": "操作成功",
            "status": True,
            "data": {"total": 4, "list": [
                {"id": "1103", "category": "morningBriefing", "title": "早报主题", "topics": [{
                    "topicId": "1", "topicTitle": "早间主题", "closeReading": [{"title": "早间解读", "content": "早间正文"}],
                }]},
                {"id": "1104", "category": "noonBriefing", "title": "午报主题", "topics": [{
                    "topicId": "2", "topicTitle": "午间主题", "closeReading": [{"title": "午间解读", "content": "午间正文"}],
                }]},
                {"id": "1105", "category": "eveningBriefing", "title": "晚报主题", "topics": [{
                    "topicId": "3", "topicTitle": "晚间主题", "closeReading": [{"title": "晚间解读", "content": "晚间正文"}],
                }]},
            ]},
        }
        with patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 10)):
            result = market_services.fetch_gangtise_daily_finance_broadcast("night", "2026-09-15")
        self.assertEqual(result["selected_report_kind"], "night")
        self.assertEqual(result["text_source"], "close_reading_or_content")
        self.assertIn("晚间解读", result["text"])
        self.assertIn("晚间正文", result["text"])

    def test_given_noon_missing_when_fetching_then_morning_is_used_as_provider_fallback(self):
        response = {"code": "000000", "status": True, "data": {"list": [{"reportTypeName": "早报", "closeReading": "只有早报"}]}}
        with patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 10)):
            result = market_services.fetch_gangtise_daily_finance_broadcast("noon", "2026-09-16")
        self.assertEqual(result["selected_report_kind"], "morning")
        self.assertIn("只有早报", result["text"])

    def test_given_broadcast_text_when_formatted_then_article_is_readable_and_traceable(self):
        formatted = market_services._format_daily_broadcast_markdown(
            "一、政策观察\n\n汽车行业出现新变化。\n2、公司动态\n重点公司公告。",
            "night",
            "2026-09-16",
        )
        self.assertTrue(formatted.startswith("# 晚间财经播报\n\n> 2026-09-16"))
        self.assertIn("## 今日播报", formatted)
        self.assertIn("由 Gangtise 热点日报接口提供", formatted)
        self.assertIn("仅用于信息整理与研究参考", formatted)
        self.assertNotIn("{\"", formatted)

    def test_given_malformed_provider_payload_when_fetching_then_no_partial_publication_is_possible(self):
        response = {"code": "000000", "status": True, "data": {"list": [{"reportTypeName": "晚报"}]}}
        with patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 10)):
            with self.assertRaisesRegex(RuntimeError, "gangtise_daily_broadcast_empty"):
                market_services.fetch_gangtise_daily_finance_broadcast("night", "2026-09-16")


if __name__ == "__main__":
    unittest.main()
