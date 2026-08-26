import unittest
from unittest.mock import patch

from src.domain import ai_services, market_services


class HermesGangtiseCapabilitiesTest(unittest.TestCase):
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

    def test_one_pager_helper_uses_single_security_list_contract(self):
        response = {"code": "000000", "status": True, "data": {"markdown": "# 深度报告"}}
        with patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 24)) as post_mock:
            result = market_services.call_gangtise_stock_one_pager("600519.sh")

        self.assertEqual(post_mock.call_args.args[0], "/application/open-ai/agent/one-pager")
        self.assertEqual(post_mock.call_args.args[1], {"securityList": ["600519.SH"]})
        self.assertEqual(result["data"]["markdown"], "# 深度报告")

    def test_direct_gangtise_result_does_not_call_local_llm(self):
        plan = {"intent": "stock_today_observation"}
        outputs = {"gangtise_stock_observation": {"text": "# 今日行情\n中国银行上涨", "provider": "Gangtise Agent助手 SSE"}}
        with patch.object(ai_services, "get_default_llm_config") as llm_config:
            result, model, mode = ai_services.synthesize_hermes_answer("今天中国银行", plan, outputs)

        llm_config.assert_not_called()
        self.assertIsNone(model)
        self.assertEqual(mode, "gangtise_direct")
        self.assertIn("中国银行", result["answer"])

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
        prompt = ai_services.build_hermes_intent_router_prompt("今天中国银行的观察报告")
        for value in (
            "stock_today_observation",
            "market_today_observation",
            "stock_one_pager",
            "stock_highlights",
            "multi_watchlist_analysis",
        ):
            self.assertIn(value, prompt)


if __name__ == "__main__":
    unittest.main()
