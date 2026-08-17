import unittest
from unittest.mock import patch

from src.domain import market_services


class ChinaCpiMappingTest(unittest.TestCase):
    def test_china_cpi_uses_verified_nbs_index(self):
        entry = market_services.GANGTISE_INDICATOR_REGISTRY["source_cpi"]

        self.assertEqual(entry["preferred_indicator_id"], "M00000016")
        self.assertEqual(entry["expected_indicator_name"], "CPI:同比指数:当月值")
        self.assertEqual(entry["expected_data_source"], "国家统计局")
        self.assertEqual(entry["valid_value_range"], (50, 200))

    def test_direct_china_cpi_prompt_compiles_without_llm(self):
        with patch.object(market_services, "get_default_llm_config", side_effect=AssertionError("direct projection must not call LLM")):
            result = market_services.generate_smart_indicator_js(
                "CPI智能指标",
                "中国CPI",
                [{"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"}],
                tenant_slug="laowang",
            )

        self.assertEqual(result["generator"], "direct_projection")
        self.assertFalse(result["llm_used"])
        self.assertIn('inputs["source_cpi"]', result["formula_js"])

    def test_us_cpi_candidate_is_rejected_before_requesting_series(self):
        us_candidate = {
            "indicatorId": "M00009835",
            "indicatorName": "CPI:美国:当月值",
            "dataSource": "美国劳工部",
        }
        search_response = {"code": "000000", "status": True, "data": [us_candidate]}

        with patch.object(market_services, "choose_gangtise_indicator_candidate", return_value=us_candidate), patch.object(
            market_services,
            "post_gangtise_openapi_json",
            return_value=(200, search_response, 12),
        ) as request:
            result = market_services.fetch_gangtise_indicator_series("source_cpi", token="test")

        self.assertFalse(result["ok"])
        self.assertIn("主数据校验失败", result["message"])
        self.assertEqual(request.call_count, 1)

    def test_out_of_range_cpi_is_rejected(self):
        china_candidate = {
            "indicatorId": "M00000016",
            "indicatorName": "CPI:同比指数:当月值",
            "dataSource": "国家统计局",
        }
        search_response = {"code": "000000", "status": True, "data": [china_candidate]}
        data_response = {"code": "000000", "status": True, "data": {"dataList": [["2026-06-01", 333.95], ["2026-07-01", 334.1]]}}

        with patch.object(
            market_services,
            "post_gangtise_openapi_json",
            side_effect=[(200, search_response, 12), (200, data_response, 20)],
        ):
            result = market_services.fetch_gangtise_indicator_series("source_cpi", token="test")

        self.assertFalse(result["ok"])
        self.assertEqual(result["points"], [])
        self.assertIn("数值校验失败", result["message"])
