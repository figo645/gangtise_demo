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

    def test_registered_macro_snapshot_replaces_a_legacy_unavailable_dashboard_card(self):
        cpi_option = {
            "indicator_code": "source_cpi",
            "indicator_name": "中国CPI同比指数",
            "category": "宏观经济",
            "value": 0.5,
            "numeric_value": 0.5,
            "unit": "%",
            "source_type": "macro_economic",
            "source_type_label": "宏观经济指标",
            "provider": "AKShare",
            "source_defs": [{"provider": "AKShare", "path": "akshare://macro_economic"}],
            "algorithm_detail": "由后台 AKShare 公开宏观数据采集后入库，供宏观经济页面与智能指标统一读取。",
            "interpretation": "已读取 中国CPI同比指数 AKShare 宏观快照。数据来源：国家统计局/东方财富。",
            "selected_indicators": [{"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"}],
            "prompt_text": "中国CPI同比指数",
            "updated_at": "2026-07",
            "data_at": "2026-07",
            "data_status": "available",
            "data_status_label": "已读取宏观快照",
        }
        with patch.object(core_services, "build_indicator_hub", return_value={"smart_items": [], "lake_items": []}), patch.object(
            core_services,
            "build_dashboard_base_indicator_options",
            return_value=[cpi_option],
        ):
            dashboard = core_services.normalize_fund_dashboard_view(
                {"layout": "2x2", "cards": [{"indicatorCode": "source_cpi", "value": "--"}]},
                {"slug": "laowang"},
            )

        card = dashboard["cards"][0]
        self.assertEqual(card["name"], "中国CPI同比指数")
        self.assertEqual(card["value"], "0.50")
        self.assertEqual(card["dataAt"], "2026-07")
        self.assertEqual(card["algorithmDetail"], cpi_option["algorithm_detail"])
        self.assertEqual(card["interpretation"], cpi_option["interpretation"])
        self.assertEqual(card["provider"], "AKShare")
        self.assertEqual(card["sourceType"], "macro_economic")

    def test_china_cpi_uses_verified_nbs_index(self):
        entry = market_services.GANGTISE_INDICATOR_REGISTRY["source_cpi"]

        self.assertEqual(entry["category"], "宏观经济")
        self.assertEqual(entry["query_kind"], "macro_latest")
        self.assertEqual(entry["macro_key"], "cpi_yoy")
        self.assertEqual(entry["unit"], "%")

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

    def test_cpi_alias_keeps_the_registered_display_name_after_resolution(self):
        selected = market_services.normalize_selected_indicator_refs(
            [{"indicator_code": "source_cpi", "indicator_name": "CPI"}]
        )

        self.assertEqual(selected, [{"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"}])

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

    def test_macro_catalog_uses_registered_public_adapters(self):
        self.assertEqual(
            set(market_services.MACRO_ECONOMIC_INDICATOR_CODES),
            set(market_services.AKSHARE_MACRO_CATALOG),
        )
        self.assertEqual(
            market_services.AKSHARE_MACRO_CATALOG["source_cpi"]["function"],
            "macro_china_cpi",
        )
        self.assertEqual(
            market_services.AKSHARE_MACRO_CATALOG["source_fixed_asset_investment_yoy"]["value_columns"],
            ("自年初累计",),
        )

    def test_unavailable_macro_indicators_are_kept_registered_but_hidden(self):
        self.assertNotIn("source_urban_unemployment", market_services.MACRO_ECONOMIC_VISIBLE_CODES)
        self.assertNotIn("source_real_estate_investment_yoy", market_services.MACRO_ECONOMIC_VISIBLE_CODES)
        self.assertIn("source_urban_unemployment", market_services.MACRO_ECONOMIC_INDICATOR_CODES)
        self.assertIn("source_real_estate_investment_yoy", market_services.MACRO_ECONOMIC_INDICATOR_CODES)

    def test_hidden_macro_indicators_are_not_dashboard_options(self):
        with patch.object(core_services, "build_indicator_hub", return_value={"items": []}), patch.object(
            market_services,
            "build_macro_economic_payload",
            return_value={
                "items": [
                    {"indicator_code": "source_urban_unemployment", "value": 5.3},
                    {"indicator_code": "source_real_estate_investment_yoy", "value": -10.0},
                ]
            },
        ):
            options = core_services.build_dashboard_base_indicator_options({"slug": "laowang"})
        self.assertEqual(options, [])

    def test_macro_frame_is_normalized_to_latest_period_and_value(self):
        class Frame:
            empty = False
            columns = ["月份", "全国-同比增长"]

            def iterrows(self):
                return iter([(0, {"月份": "2026年07月", "全国-同比增长": "0.5"})])

        result = market_services._build_macro_points(Frame(), "全国-同比增长")
        self.assertEqual(result, [{"date": "2026-07", "value": 0.5}])

    def test_fixed_asset_cumulative_growth_is_derived_from_cumulative_amounts(self):
        class Frame:
            empty = False
            columns = ["月份", "自年初累计"]

            def iterrows(self):
                return iter([
                    (0, {"月份": "2025年07月", "自年初累计": "100"}),
                    (1, {"月份": "2026年07月", "自年初累计": "108"}),
                ])

        result = market_services._build_macro_points(Frame(), "自年初累计", "cumulative_yoy")
        self.assertEqual(result[-1], {"date": "2026-07", "value": 8.0})

    def test_macro_fetch_uses_akshare_and_returns_real_points(self):
        class Frame:
            empty = False
            columns = ["月份", "制造业-指数"]

            def iterrows(self):
                return iter([(0, {"月份": "2026年07月", "制造业-指数": "49.4"})])

        class Ak:
            def macro_china_pmi(self):
                return Frame()

        result = market_services.fetch_akshare_macro_indicator_series("source_manufacturing_pmi", ak=Ak())
        self.assertTrue(result["ok"])
        self.assertEqual(result["points"][-1]["value"], 49.4)

    def test_macro_snapshot_payload_reads_postgres_snapshot_without_provider_call(self):
        snapshot = {"ok": True, "snapshot_version": 1, "source": "AKShare", "items": [{"indicator_code": "source_cpi", "value": 0.5, "available": True}]}
        with patch.object(market_services, "_load_market_snapshot_payload", return_value=snapshot), patch.object(
            market_services, "_load_akshare", side_effect=AssertionError("H5 must not call AKShare")
        ):
            self.assertEqual(market_services.build_macro_economic_payload(), snapshot)
