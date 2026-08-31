import unittest
from unittest.mock import patch

from src.domain import core_services
from src.domain import market_services


class ChinaCpiMappingTest(unittest.TestCase):
    def test_registered_market_index_snapshot_is_a_smart_indicator_input(self):
        class Result:
            def fetchall(self):
                return []

        class Db:
            def execute(self, query, params=()):
                self.query = query
                return Result()

        with patch.object(core_services, "get_db", return_value=Db()), patch.object(
            market_services,
            "build_market_overview_index_detail",
            side_effect=lambda code: {
                "numeric_value": 3986.30,
                "value": 3986.30,
                "status": "normal",
                "updated_at": "2026-08-31",
            } if code == "source_shanghai_index" else None,
        ):
            latest_map = core_services.build_smart_indicator_latest_value_map(
                [{"indicator_code": "source_shanghai_index", "indicator_name": "上证指数"}]
            )

        self.assertEqual(latest_map["source_shanghai_index"]["latest_value"], "3986.3")

    def test_dashboard_card_for_registered_market_index_keeps_value_and_source(self):
        card = core_services.build_fund_dashboard_card_from_indicator(
            {
                "indicator_code": "source_shanghai_index",
                "indicator_name": "上证指数",
                "category": "数据湖指标",
                "value": 3986.30,
                "numeric_value": 3986.30,
                "selected_indicators": [
                    {"indicator_code": "source_shanghai_index", "indicator_name": "上证指数"}
                ],
                "data_status": "available",
                "data_at": "2026-08-31",
            }
        )

        self.assertEqual(card["indicatorCode"], "source_shanghai_index")
        self.assertEqual(card["value"], "3986.30")
        self.assertEqual(card["selectedIndicators"][0]["indicator_code"], "source_shanghai_index")

    def test_legacy_name_only_dashboard_card_is_rehydrated_from_registered_index(self):
        with patch.object(core_services, "build_indicator_hub", return_value={"smart_items": [], "lake_items": []}), patch.object(
            core_services,
            "build_dashboard_base_indicator_options",
            return_value=[
                {
                    "indicator_code": "source_shanghai_index",
                    "indicator_name": "上证指数",
                    "category": "大盘指数",
                    "value": 3986.30,
                    "numeric_value": 3986.30,
                    "source_type": "market_index",
                    "source_type_label": "大盘指数",
                    "selected_indicators": [
                        {"indicator_code": "source_shanghai_index", "indicator_name": "上证指数"}
                    ],
                    "prompt_text": "上证指数",
                    "updated_at": "2026-08-31",
                    "data_at": "2026-08-31",
                    "data_status": "available",
                }
            ],
        ):
            dashboard = core_services.normalize_fund_dashboard_view(
                {"layout": "2x2", "cards": [{"name": "上证指数"}]},
                {"slug": "laowang"},
            )

        card = dashboard["cards"][0]
        self.assertEqual(card["indicatorCode"], "source_shanghai_index")
        self.assertEqual(card["value"], "3986.30")
        self.assertEqual(card["selectedIndicators"][0]["indicator_name"], "上证指数")
        self.assertEqual(card["prompt"], "上证指数")

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

    def test_cpi_divided_by_two_compiles_to_the_explicit_arithmetic_formula(self):
        with patch.object(market_services, "get_default_llm_config", side_effect=AssertionError("explicit arithmetic must not call LLM")):
            result = market_services.generate_smart_indicator_js(
                "CPI折算指标",
                "CPI/2",
                [{"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"}],
                tenant_slug="laowang",
            )

        self.assertEqual(result["generator"], "arithmetic_expression")
        self.assertFalse(result["llm_used"])
        self.assertEqual(result["formula_js"], 'return Number(inputs["source_cpi"] || 0)/2;')

    def test_indicator_formula_never_converts_a_missing_source_to_zero(self):
        with self.assertRaisesRegex(ValueError, "smart_indicator_source_unavailable:source_cpi"):
            market_services.evaluate_smart_indicator_formula_js(
                'return Number(inputs["source_cpi"] || 0);',
                [{"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"}],
                {},
            )

    def test_indicator_formula_preserves_a_real_zero_source_value(self):
        result = market_services.evaluate_smart_indicator_formula_js(
            'return Number(inputs["source_cpi"] || 0);',
            [{"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"}],
            {"source_cpi": {"latest_value": "0"}},
        )

        self.assertEqual(result, 0.0)

    def test_cpi_divided_by_two_uses_the_real_source_value(self):
        formula = market_services.generate_smart_indicator_js(
            "CPI折算指标",
            "CPI/2",
            [{"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"}],
            tenant_slug="laowang",
        )["formula_js"]

        result = market_services.evaluate_smart_indicator_formula_js(
            formula,
            [{"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"}],
            {"source_cpi": {"latest_value": "123.4"}},
        )

        self.assertEqual(result, 61.7)

    def test_shanghai_index_alias_compiles_without_llm(self):
        with patch.object(market_services, "get_default_llm_config", side_effect=AssertionError("direct projection must not call LLM")):
            result = market_services.generate_smart_indicator_js(
                "上证指数智能指标",
                "上证综合指数",
                [{"indicator_code": "source_shanghai_index", "indicator_name": "上证指数"}],
                tenant_slug="laowang",
            )

        self.assertEqual(result["generator"], "direct_projection")
        self.assertFalse(result["llm_used"])
        self.assertIn('inputs["source_shanghai_index"]', result["formula_js"])

    def test_standard_entities_resolve_without_a_browser_tag_catalog(self):
        cases = {
            "CPI": ["source_cpi"],
            "上证综合指数": ["source_shanghai_index"],
            "市场一览": ["source_shanghai_index", "source_shenzhen_index"],
        }

        for prompt, expected_codes in cases.items():
            with self.subTest(prompt=prompt):
                resolved = core_services.resolve_smart_indicator_prompt_refs(prompt, [], {})
                self.assertEqual([item["indicator_code"] for item in resolved], expected_codes)

    def test_standard_market_and_macro_tags_remain_available_without_latest_values(self):
        with patch.object(core_services, "build_dashboard_base_indicator_options", return_value=[]), patch.object(
            core_services,
            "gen_watchlist_details",
            return_value={},
        ):
            tags = core_services.build_tenant_smart_indicator_tag_catalog({"slug": "laowang"})

        tag_map = {item["tag_code"]: item for item in tags}
        self.assertIn("indicator:source_cpi", tag_map)
        self.assertIn("indicator:source_shanghai_index", tag_map)
        self.assertEqual(
            [item["indicator_code"] for item in tag_map["market:overview"]["selected_indicators"]],
            ["source_shanghai_index", "source_shenzhen_index"],
        )

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
