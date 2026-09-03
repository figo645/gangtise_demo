import unittest
from unittest.mock import patch

from src.domain import core_services
from src.domain import market_services


class ChinaCpiMappingTest(unittest.TestCase):
    def _assert_arithmetic_case(self, prompt, selected, latest_values, expected):
        with patch.object(
            market_services,
            "get_default_llm_config",
            side_effect=AssertionError("explicit arithmetic must not call LLM"),
        ):
            generated = market_services.generate_smart_indicator_js(
                "组合测试指标", prompt, selected, tenant_slug="laowang"
            )
        self.assertEqual(generated["generator"], "arithmetic_expression")
        self.assertFalse(generated["llm_used"])
        actual = market_services.evaluate_smart_indicator_formula_js(
            generated["formula_js"], selected, latest_values
        )
        self.assertAlmostEqual(actual, expected, places=4)

    def test_structured_formula_token_resolves_ppi_reference(self):
        tag = {
            "tag_code": "indicator:source_ppi",
            "label": "中国PPI同比指数",
            "prompt_aliases": ["PPI"],
            "selected_indicators": [{
                "indicator_code": "source_ppi",
                "indicator_name": "中国PPI同比指数",
            }],
        }
        with patch.object(core_services, "build_tenant_smart_indicator_tag_catalog", return_value=[tag]), patch.object(
            core_services,
            "build_indicator_hub",
            return_value={"items": [{"id": "source_ppi", "name": "中国PPI同比指数"}]},
        ), patch.object(
            market_services,
            "GANGTISE_INDICATOR_REGISTRY",
            {"source_ppi": {"indicator_name": "中国PPI同比指数"}},
        ):
            refs = core_services.resolve_smart_indicator_selected_refs(
                {"slug": "laowang"},
                {
                    "prompt_text": "PPI*2",
                    "formula_tokens": [{
                        "type": "reference",
                        "tagCode": "indicator:source_ppi",
                        "indicatorCode": "source_ppi",
                        "label": "中国PPI同比指数",
                    }, {"type": "operator", "text": "*"}, {"type": "number", "text": "2"}],
                },
            )

        self.assertEqual(refs, [{"indicator_code": "source_ppi", "indicator_name": "中国PPI同比指数"}])

    def test_registered_macro_tag_exposes_ppi_short_alias(self):
        with patch.object(core_services, "build_dashboard_base_indicator_options", return_value=[{
            "indicator_code": "source_ppi",
            "indicator_name": "中国PPI同比",
            "category": "宏观经济",
            "unit": "%",
        }]), patch.object(core_services, "gen_watchlist_details", return_value={}):
            tags = core_services.build_tenant_smart_indicator_tag_catalog({"slug": "laowang"})

        ppi_tag = next(item for item in tags if item.get("tag_code") == "indicator:source_ppi")
        self.assertIn("PPI", ppi_tag.get("prompt_aliases") or [])

    def test_saved_smart_indicator_tags_are_explicit_only(self):
        with patch.object(core_services, "build_dashboard_base_indicator_options", return_value=[
            {
                "indicator_code": "source_cpi",
                "indicator_name": "中国CPI同比指数",
                "source_type": "macro_economic",
            },
            {
                "indicator_code": "laowang_smart_cpi_combo",
                "indicator_name": "中国CPI同比指数组合指标",
                "source_type": "smart",
            },
        ]), patch.object(core_services, "gen_watchlist_details", return_value={}), patch.object(
            core_services, "build_hot_industry_indicator_catalog", return_value=[]
        ):
            tags = core_services.build_tenant_smart_indicator_tag_catalog({"slug": "laowang"})

        tag_map = {item["tag_code"]: item for item in tags}
        self.assertTrue(tag_map["indicator:source_cpi"]["auto_match"])
        self.assertFalse(tag_map["indicator:laowang_smart_cpi_combo"]["auto_match"])

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

    def test_smart_indicator_reads_the_same_sector_snapshot_as_hot_industries(self):
        class Result:
            def __init__(self, rows=None):
                self.rows = rows or []

            def fetchall(self):
                return self.rows

        class Db:
            def __init__(self):
                self.latest_rows = [
                    {
                        "indicator_code": "laowang_smart_mechanical",
                        "latest_value": "2242.01",
                        "latest_status": "normal",
                        "latest_assessment": "已计算",
                        "latest_alert": "",
                        "updated_at": "2026-09-02",
                        "is_simulated": 0,
                        "source_code": "derived_smart_indicator",
                    }
                ]

            def execute(self, query, params=()):
                if "FROM indicator_latest_values" in query:
                    return Result(self.latest_rows)
                return Result()

        definition = {
            "indicator_code": "laowang_smart_mechanical",
            "indicator_name": "申万一级行业指数:机械设备智能指标",
            "tenant_slug": "laowang",
            "category": "大V自定义指标",
            "unit": "",
            "description": "",
            "owner": "财经老王",
            "enabled": 1,
            "status_hint": "normal",
            "assessment_template": "",
            "alert_template": "",
            "prompt_text": "机械设备",
            "formula_js": 'return Number(inputs["source_sector_27"] || 0);',
            "selected_indicators": [
                {"indicator_code": "source_sector_27", "indicator_name": "申万一级行业指数:机械设备"}
            ],
            "source_type": "smart",
            "source_type_label": "智能指标",
            "provider": "DeepSeek-V4-Flash",
            "display_order": 1,
            "updated_at": "2026-09-02",
        }
        with patch.object(market_services, "GANGTISE_INDICATOR_REGISTRY", {}), patch.object(
            market_services, "list_indicator_definitions", return_value=[definition]
        ), patch.object(
            market_services, "list_indicator_source_defs", return_value=[]
        ), patch.object(market_services, "build_macro_economic_payload", return_value={"items": []}), patch.object(
            market_services,
            "build_market_sector_overview_payload",
            return_value={
                "items": [{"sector": "机械设备", "value": 2242.01, "updated_at": "2026-09-02"}],
                "updated_at": "2026-09-02",
            },
        ), patch.object(market_services, "get_db", return_value=Db()):
            hub = market_services.build_indicator_hub_from_store()

        item = hub["smart_items"][0]
        self.assertEqual(item["value"], "2242.01")
        self.assertEqual(item["numeric_value"], 2242.01)
        self.assertFalse(item["data_unavailable"])
        self.assertEqual(item["data_mode"], "real")
        self.assertEqual(item["data_at"], "2026-09-02")

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

    def test_cpi_plus_ppi_resolves_both_macro_sources_and_compiles_deterministically(self):
        resolved = core_services.resolve_smart_indicator_prompt_refs("CPI + PPI", [], {})
        self.assertEqual(
            [item["indicator_code"] for item in resolved],
            ["source_cpi", "source_ppi"],
        )
        with patch.object(market_services, "get_default_llm_config", side_effect=AssertionError("explicit arithmetic must not call LLM")):
            result = market_services.generate_smart_indicator_js(
                "CPI + PPI", "CPI + PPI", resolved, tenant_slug="laowang"
            )
        self.assertEqual(result["generator"], "arithmetic_expression")
        self.assertFalse(result["llm_used"])
        self.assertEqual(
            result["formula_js"],
            'return Number(inputs["source_cpi"] || 0) + Number(inputs["source_ppi"] || 0);',
        )

    def test_market_two_indicator_add_subtract_multiply_divide(self):
        selected = [
            {"indicator_code": "source_shanghai_index", "indicator_name": "上证指数"},
            {"indicator_code": "source_shenzhen_index", "indicator_name": "深证指数"},
        ]
        values = {
            "source_shanghai_index": {"latest_value": "300"},
            "source_shenzhen_index": {"latest_value": "120"},
        }
        cases = [("上证指数 + 深证指数", 420), ("上证指数 - 深证指数", 180), ("上证指数 * 深证指数", 36000), ("上证指数 / 深证指数", 2.5)]
        for prompt, expected in cases:
            with self.subTest(prompt=prompt):
                self._assert_arithmetic_case(prompt, selected, values, expected)

    def test_industry_two_indicator_add_subtract_multiply_divide(self):
        selected = [
            {"indicator_code": "source_sector_15", "indicator_name": "申万一级行业指数:商贸零售"},
            {"indicator_code": "source_sector_27", "indicator_name": "申万一级行业指数:机械设备"},
        ]
        values = {
            "source_sector_15": {"latest_value": "80"},
            "source_sector_27": {"latest_value": "20"},
        }
        cases = [("商贸零售 + 机械设备", 100), ("商贸零售 - 机械设备", 60), ("商贸零售 * 机械设备", 1600), ("商贸零售 / 机械设备", 4)]
        for prompt, expected in cases:
            with self.subTest(prompt=prompt):
                self._assert_arithmetic_case(prompt, selected, values, expected)

    def test_market_three_indicator_add_subtract_multiply_divide(self):
        selected = [
            {"indicator_code": "source_shanghai_index", "indicator_name": "上证指数"},
            {"indicator_code": "source_shenzhen_index", "indicator_name": "深证指数"},
            {"indicator_code": "source_hs300", "indicator_name": "沪深300"},
        ]
        values = {
            "source_shanghai_index": {"latest_value": "300"},
            "source_shenzhen_index": {"latest_value": "120"},
            "source_hs300": {"latest_value": "60"},
        }
        cases = [("上证指数 + 深证指数 + 沪深300", 480), ("上证指数 - 深证指数 - 沪深300", 120), ("上证指数 * 深证指数 * 沪深300", 2160000), ("上证指数 / 深证指数 / 沪深300", 1 / 24)]
        for prompt, expected in cases:
            with self.subTest(prompt=prompt):
                self._assert_arithmetic_case(prompt, selected, values, expected)

    def test_industry_three_indicator_add_subtract_multiply_divide(self):
        selected = [
            {"indicator_code": "source_sector_15", "indicator_name": "申万一级行业指数:商贸零售"},
            {"indicator_code": "source_sector_27", "indicator_name": "申万一级行业指数:机械设备"},
            {"indicator_code": "source_sector_05", "indicator_name": "申万一级行业指数:电子"},
        ]
        values = {
            "source_sector_15": {"latest_value": "80"},
            "source_sector_27": {"latest_value": "20"},
            "source_sector_05": {"latest_value": "10"},
        }
        cases = [("商贸零售 + 机械设备 + 电子", 110), ("商贸零售 - 机械设备 - 电子", 50), ("商贸零售 * 机械设备 * 电子", 16000), ("商贸零售 / 机械设备 / 电子", 0.4)]
        for prompt, expected in cases:
            with self.subTest(prompt=prompt):
                self._assert_arithmetic_case(prompt, selected, values, expected)

    def test_canonical_macro_names_with_suffix_resolve_and_compile(self):
        resolved = core_services.resolve_smart_indicator_prompt_refs(
            "中国CPI同比指数 + 中国PPI同比指数", [], {}
        )
        self.assertEqual(
            [item["indicator_code"] for item in resolved],
            ["source_cpi", "source_ppi"],
        )
        result = market_services.generate_smart_indicator_js(
            "宏观组合", "中国CPI同比指数 + 中国PPI同比指数", resolved, tenant_slug="laowang"
        )
        self.assertEqual(
            result["formula_js"],
            'return Number(inputs["source_cpi"] || 0) + Number(inputs["source_ppi"] || 0);',
        )

    def test_indicator_formula_never_converts_a_missing_source_to_zero(self):
        with self.assertRaisesRegex(ValueError, "smart_indicator_source_unavailable:source_cpi"):
            market_services.evaluate_smart_indicator_formula_js(
                'return Number(inputs["source_cpi"] || 0);',
                [{"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"}],
                {},
            )

    def test_malformed_nested_input_formula_is_rejected_before_evaluation(self):
        with self.assertRaisesRegex(ValueError, "smart_indicator_js_unsafe"):
            market_services.validate_smart_indicator_js(
                'return Number(inputs["source_Number(inputs["source_cpi"] || 0)"] || 0) + Number(inputs["source_ppi"] || 0);',
                [
                    {"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"},
                    {"indicator_code": "source_ppi", "indicator_name": "中国PPI同比"},
                ],
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

    def test_cpi_fuzzy_resolution_excludes_derived_smart_indicator_labels(self):
        tags = [
            {
                "tag_code": "indicator:source_cpi",
                "label": "中国CPI同比指数",
                "auto_match": True,
                "selected_indicators": [{"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"}],
            },
            {
                "tag_code": "indicator:laowang_smart_cpi_combo",
                "label": "中国CPI同比指数组合指标",
                "auto_match": False,
                "selected_indicators": [{"indicator_code": "laowang_smart_cpi_combo", "indicator_name": "中国CPI同比指数组合指标"}],
            },
        ]

        resolved = core_services.resolve_smart_indicator_prompt_refs("中国CPI", tags, {})

        self.assertEqual(
            resolved,
            [{"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"}],
        )

    def test_hot_industry_partial_query_resolves_to_registered_sector_snapshot(self):
        industry_item = {
            "sector_name": "商贸零售",
            "indicator_code": "source_sector_15",
            "indicator_name": "申万一级行业指数:商贸零售",
            "value": 1234.5,
            "numeric_value": 1234.5,
        }
        with patch.object(core_services, "build_hot_industry_indicator_catalog", return_value=[industry_item]):
            resolved = core_services.resolve_smart_indicator_prompt_refs("商贸零", [], {})
        self.assertEqual(
            resolved,
            [{"indicator_code": "source_sector_15", "indicator_name": "申万一级行业指数:商贸零售"}],
        )

    def test_suppressed_auto_matched_tag_is_excluded_from_resolution(self):
        tag = {
            "tag_code": "industry:商贸零售",
            "label": "商贸零售",
            "tag_type": "industry",
            "selected_indicators": [{"indicator_code": "source_sector_15", "indicator_name": "申万一级行业指数:商贸零售"}],
        }
        with patch.object(core_services, "build_tenant_smart_indicator_tag_catalog", return_value=[tag]), patch.object(
            core_services, "build_indicator_hub", return_value={"items": []}
        ):
            resolved = core_services.resolve_smart_indicator_selected_refs(
                {"slug": "laowang"},
                {"prompt_text": "商贸零售", "suppressed_tag_codes": ["industry:商贸零售"]},
            )
        self.assertEqual(resolved, [])

    def test_suppressed_structured_formula_token_is_excluded_from_resolution(self):
        tag = {
            "tag_code": "indicator:source_ppi",
            "label": "中国PPI同比指数",
            "selected_indicators": [{
                "indicator_code": "source_ppi",
                "indicator_name": "中国PPI同比指数",
            }],
        }
        with patch.object(core_services, "build_tenant_smart_indicator_tag_catalog", return_value=[tag]), patch.object(
            core_services,
            "build_indicator_hub",
            return_value={"items": [{"id": "source_ppi", "name": "中国PPI同比指数"}]},
        ), patch.object(
            market_services,
            "GANGTISE_INDICATOR_REGISTRY",
            {"source_ppi": {"indicator_name": "中国PPI同比指数"}},
        ):
            refs = core_services.resolve_smart_indicator_selected_refs(
                {"slug": "laowang"},
                {
                    "prompt_text": "PPI*2",
                    "suppressed_tag_codes": ["indicator:source_ppi"],
                    "formula_tokens": [{
                        "type": "reference",
                        "tagCode": "indicator:source_ppi",
                        "indicatorCode": "source_ppi",
                        "label": "中国PPI同比指数",
                    }, {"type": "operator", "text": "*"}, {"type": "number", "text": "2"}],
                },
            )

        self.assertEqual(refs, [])

    def test_structured_formula_tokens_ignore_stale_selected_tags(self):
        tags = [
            {
                "tag_code": "indicator:source_ppi",
                "label": "中国PPI同比",
                "selected_indicators": [{"indicator_code": "source_ppi", "indicator_name": "中国PPI同比"}],
            },
            {
                "tag_code": "indicator:source_cpi",
                "label": "中国CPI同比指数",
                "selected_indicators": [{"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"}],
            },
            {
                "tag_code": "watchlist:600519",
                "label": "贵州茅台",
                "selected_indicators": [{"indicator_code": "source_shanghai_index", "indicator_name": "上证指数"}],
            },
        ]
        with patch.object(core_services, "build_tenant_smart_indicator_tag_catalog", return_value=tags), patch.object(
            core_services,
            "build_indicator_hub",
            return_value={"items": [
                {"id": "source_ppi", "name": "中国PPI同比"},
                {"id": "source_cpi", "name": "中国CPI同比指数"},
                {"id": "source_shanghai_index", "name": "上证指数"},
            ]},
        ):
            refs = core_services.resolve_smart_indicator_selected_refs(
                {"slug": "laowang"},
                {
                    "prompt_text": "【中国PPI同比】*5+【中国CPI同比指数】",
                    "selected_tag_codes": ["indicator:source_ppi", "indicator:source_cpi", "watchlist:600519"],
                    "formula_tokens": [
                        {"type": "reference", "tagCode": "indicator:source_ppi", "label": "中国PPI同比"},
                        {"type": "operator", "text": "*"},
                        {"type": "number", "text": "5"},
                        {"type": "operator", "text": "+"},
                        {"type": "reference", "tagCode": "indicator:source_cpi", "label": "中国CPI同比指数"},
                    ],
                },
            )

        self.assertEqual(
            refs,
            [
                {"indicator_code": "source_ppi", "indicator_name": "中国PPI同比"},
                {"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"},
            ],
        )

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
