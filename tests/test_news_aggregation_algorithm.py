import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from src.domain.core_services import normalize_tenant_config
from src.domain import market_services


class NewsAggregationAlgorithmTest(unittest.TestCase):
    def test_news_impact_annotation_is_explainable(self):
        positive = market_services.annotate_news_impact({
            "title": "半导体公司获批扩产并取得重大订单",
        })
        negative = market_services.annotate_news_impact({
            "title": "医药公司被立案调查并遭行政处罚",
        })
        mixed = market_services.annotate_news_impact({
            "title": "银行回购但同时面临息差下调压力",
        })
        self.assertEqual(positive["impact"], "positive")
        self.assertEqual(positive["impact_label"], "利好")
        self.assertEqual(positive["industry"], "半导体")
        self.assertEqual(negative["impact"], "negative")
        self.assertEqual(negative["impact_label"], "利空")
        self.assertEqual(negative["industry"], "医药生物")
        self.assertEqual(mixed["impact"], "mixed")
        self.assertEqual(mixed["impact_label"], "影响分化")

    def test_news_event_rules_cover_policy_industry_and_negation(self):
        aerospace = market_services.annotate_news_impact({
            "title": "中共中央 国务院 中央军委关于给张陆颁发航天功勋奖章的决定",
            "source_group": "政策要闻",
        })
        auto_policy = market_services.annotate_news_impact({
            "title": "我国提出到2030年进入世界汽车强国行列",
            "source_group": "政策要闻",
        })
        negated = market_services.annotate_news_impact({
            "title": "公司尚未获批扩产项目，市场等待进一步消息",
        })
        self.assertEqual(aerospace["impact"], "positive")
        self.assertEqual(aerospace["impact_label"], "间接利好")
        self.assertEqual(aerospace["industry"], "航天军工")
        self.assertEqual(aerospace["impact_scope"], "industry")
        self.assertEqual(aerospace["impact_directness"], "indirect")
        self.assertEqual(aerospace["impact_strength"], "weak")
        self.assertEqual(auto_policy["impact"], "positive")
        self.assertEqual(auto_policy["impact_label"], "行业利好")
        self.assertEqual(auto_policy["industry"], "汽车")
        self.assertEqual(auto_policy["impact_strength"], "strong")
        self.assertEqual(negated["impact"], "neutral")
        self.assertEqual(negated["impact_evidence"], [])
        self.assertEqual(negated["impact_method"], "event_rules_v2")

    def test_title_classifier_contract_is_compact_and_rejects_fabricated_rows(self):
        items = [{"event_id": "n1", "title": "我国提出进入世界汽车强国行列"}]
        prompt = market_services.build_news_title_classifier_prompt(items)
        self.assertIn('"news_id":"n1"', prompt)
        self.assertNotIn("url", prompt)
        result = market_services._parse_news_title_classifier_result(
            '[{"news_id":"n1","impact":"positive","industry_code":"automotive"},'
            '{"news_id":"fake","impact":"negative","industry_code":"banking"},'
            '{"news_id":"n1","impact":"bad","industry_code":"automotive"}]',
            {"n1"},
        )
        self.assertEqual(result, {"n1": {"impact": "positive", "industry": "汽车", "industry_code": "automotive"}})

    def test_title_classifier_merge_preserves_rules_when_model_has_no_result(self):
        items = [{"event_id": "n1", "title": "医药公司被行政处罚"}, {"event_id": "n2", "title": "普通新闻"}]
        merged = market_services.apply_news_title_classifications(items, {
            "classified": {"n1": {"impact": "negative", "industry": "医药生物", "industry_code": "pharma_biotech"}},
        })
        self.assertEqual(merged[0]["impact_method"], "v4_title_classification_v1")
        self.assertEqual(merged[0]["industry"], "医药生物")
        self.assertEqual(merged[1]["impact_method"], "event_rules_v2")

    def test_news_event_mapping_covers_major_financial_events(self):
        cases = [
            ({"title": "人工智能发展规划发布，算力支持力度加大"}, "positive", "计算机"),
            ({"title": "创新药获得纳入医保资格"}, "positive", "医药生物"),
            ({"title": "上市公司财务造假并被监管立案"}, "negative", "综合/未分类"),
            ({"title": "汽车销量下降，需求疲软"}, "negative", "汽车"),
            ({"title": "铜产品涨价且库存下降"}, "positive", "有色金属"),
        ]
        for item, expected_impact, expected_industry in cases:
            with self.subTest(title=item["title"]):
                annotated = market_services.annotate_news_impact(item)
                self.assertEqual(annotated["impact"], expected_impact)
                self.assertEqual(annotated["industry"], expected_industry)
                self.assertTrue(annotated["impact_event_types"])

    def test_industry_catalog_covers_all_primary_industries(self):
        expected = {
            "农林牧渔", "基础化工", "钢铁", "有色金属", "电子", "家用电器", "食品饮料",
            "纺织服饰", "轻工制造", "医药生物", "公用事业", "交通运输", "房地产", "商贸零售",
            "社会服务", "综合", "建筑材料", "建筑装饰", "电力设备", "国防军工", "计算机",
            "通信", "银行", "非银金融", "汽车", "机械设备", "煤炭", "石油石化", "环保",
            "美容护理", "传媒",
        }
        self.assertEqual(set(market_services.NEWS_INDUSTRY_COVERAGE), expected)
        self.assertEqual(len(market_services.NEWS_INDUSTRY_COVERAGE), 31)

    def test_news_impact_analysis_only_uses_today_and_returns_percentages(self):
        items = [
            {"title": "半导体扩产获批", "published_at": "2026-09-15 09:00:00"},
            {"title": "半导体公司被处罚", "published_at": "2026-09-15 10:00:00"},
            {"title": "昨日半导体扩产获批", "published_at": "2026-09-14 10:00:00"},
        ]
        analysis = market_services.build_news_impact_analysis(items, now=datetime(2026, 9, 15, 12, 0, 0))
        self.assertEqual(analysis["total"], 2)
        self.assertEqual(analysis["counts"]["positive"], 1)
        self.assertEqual(analysis["counts"]["negative"], 1)
        self.assertEqual(len(analysis["industries"]), 1)
        industry = analysis["industries"][0]
        self.assertEqual(industry["total"], 2)
        self.assertEqual(industry["positive_pct"], 50.0)
        self.assertEqual(industry["negative_pct"], 50.0)
        self.assertEqual(sum(industry[f"{key}_pct"] for key in ("positive", "negative", "neutral", "mixed")), 100.0)

    def test_news_impact_analysis_reports_annotation_coverage_for_each_source(self):
        items = [
            {"title": "汽车强国规划发布", "source_code": "gov_cn_policy", "source_name": "中国政府网", "published_at": "2026-09-15 09:00:00"},
            {"title": "公司被行政处罚", "source_code": "cninfo_announcements", "source_name": "巨潮资讯", "published_at": "2026-09-15 10:00:00"},
            {"title": "政策新闻待确认", "source_code": "stats_macro", "source_name": "国家统计局", "published_at": "2026-09-15 11:00:00"},
        ]
        analysis = market_services.build_news_impact_analysis(items, now=datetime(2026, 9, 15, 12, 0, 0))
        coverage = analysis["annotation"]
        self.assertEqual(coverage["input_count"], 3)
        self.assertEqual(coverage["annotated_count"], 3)
        self.assertTrue(coverage["annotation_complete"])
        self.assertEqual(coverage["source_count"], 3)
        self.assertEqual({row["source_code"] for row in coverage["sources"]}, {
            "gov_cn_policy", "cninfo_announcements", "stats_macro",
        })

    def test_news_impact_analysis_provides_today_three_day_and_ten_day_windows(self):
        items = [
            {"title": "今日汽车强国政策", "published_at": "2026-09-15 09:00:00"},
            {"title": "昨日汽车销量下降", "published_at": "2026-09-14 09:00:00"},
            {"title": "前日汽车公司中标", "published_at": "2026-09-12 09:00:00"},
            {"title": "上周汽车公司被行政处罚", "published_at": "2026-09-05 09:00:00"},
        ]
        analysis = market_services.build_news_impact_analysis(items, now=datetime(2026, 9, 15, 12, 0, 0))
        self.assertEqual(analysis["windows"]["today"]["total"], 1)
        self.assertEqual(analysis["windows"]["recent_3d"]["total"], 3)
        self.assertEqual(analysis["windows"]["recent_10d"]["total"], 4)
        self.assertEqual(analysis["total"], analysis["windows"]["today"]["total"])

    def test_normalize_tenant_config_preserves_news_algorithm(self):
        payload = {
            "slug": "laowang",
            "news_aggregation_algorithm": {
                "version": "v9",
                "strategy": "watchlist_sector_first",
                "script_js": "function rankNews(input) { return { score: 1, bucket: 'other', reason: 'ok' }; }",
                "source_prompt": "按行业板块优先",
            },
        }
        normalized = normalize_tenant_config(payload, 0)
        self.assertIn("news_aggregation_algorithm", normalized)
        self.assertEqual(normalized["news_aggregation_algorithm"]["version"], "v9")
        self.assertIn("rankNews", normalized["news_aggregation_algorithm"]["script_js"])

    def test_rank_news_uses_normalized_rule_plan_not_untrusted_script(self):
        custom_script = """
function rankNews(input) {
  const title = String(input.item.title || '');
  if (title.includes('重大利好')) {
    return { score: 200, bucket: 'major_market', reason: '重大消息优先' };
  }
  if (Array.isArray(input.watchlistSectors) && input.watchlistSectors.some(tag => title.includes(tag))) {
    return { score: 10, bucket: 'watchlist_sector', reason: '行业板块命中' };
  }
  return { score: 1, bucket: 'other', reason: '其他公开信息' };
}
""".strip()
        items = [
            {"title": "半导体制造行业消息", "content": "", "summary": "", "published_at": "2026-08-01 10:00:00"},
            {"title": "重大利好公告", "content": "", "summary": "", "published_at": "2026-08-01 09:00:00"},
        ]
        with patch.object(
            market_services,
            "load_tenant_news_aggregation_algorithm",
            return_value={"version": "v9", "strategy": "watchlist_sector_first", "script_js": custom_script, "source_prompt": "行业板块优先"},
        ):
            ranked = market_services._rank_news_for_tenant(
                items,
                tenant={"slug": "laowang", "name": "财经老王研究院"},
                watchlist_details=[{"industry": "半导体制造", "name": "中芯国际"}],
        )
        self.assertGreaterEqual(len(ranked), 2)
        self.assertEqual(ranked[0]["title"], "半导体制造行业消息")
        self.assertEqual(ranked[0]["aggregation_bucket"], "watchlist_sector")
        self.assertEqual(ranked[0]["aggregation_algorithm_version"], "v3")
        self.assertEqual(ranked[1]["aggregation_bucket"], "major_market")

    def test_build_fundamental_news_payload_uses_recent_three_day_source_tabs(self):
        items = []
        for index in range(12):
            items.append({
                "title": f"新闻 {index + 1}",
                "content": "",
                "summary": "",
                "published_at": f"2026-08-01 0{index % 9}:00:00",
                "aggregation_bucket": "watchlist_sector" if index < 7 else "major_market",
                "source_code": ("policy" if index < 3 else "company" if index < 6 else "regulation" if index < 9 else "macro"),
                "source_group": "政策要闻" if index < 3 else "公司公告" if index < 6 else "监管要闻" if index < 9 else "宏观要闻",
                "tag": "综合要闻",
            })
        with patch.object(market_services, "gen_news_feed", return_value=items):
            payload = market_services.build_fundamental_news_payload(tenant={"slug": "laowang"}, watchlist_details={})
        self.assertEqual(len(payload["items"]), 0)
        self.assertEqual(payload["total"], 0)
        self.assertEqual(len(payload["tabs"]), 1)
        self.assertEqual(payload["tabs"][0]["key"], "all")
        self.assertEqual(payload["tabs"][0]["label"], "全部新闻")
        self.assertEqual(payload["tabs"][0]["count"], 0)
        self.assertEqual(payload["selection_mode"], "recent_3d_source_tabs")

    def test_fundamental_homepage_keeps_only_recent_three_day_news(self):
        items = [
            {"title": "昨日较新", "source_code": "policy", "published_at": "2026-09-01 23:59:00"},
            {"title": "今日最早", "source_code": "policy", "published_at": "2026-09-02 09:00:00"},
            {"title": "今日最新", "source_code": "policy", "published_at": "2026-09-02 15:00:00"},
            {"title": "今日中间", "source_code": "macro", "published_at": "2026-09-02 12:00:00"},
            {"title": "今日第二", "source_code": "company", "published_at": "2026-09-02 14:00:00"},
            {"title": "今日第三", "source_code": "regulation", "published_at": "2026-09-02 13:00:00"},
            {"title": "今日第四", "source_code": "industry", "published_at": "2026-09-02 10:00:00"},
        ]
        with patch.object(market_services, "gen_news_feed", return_value=items), patch.object(
            market_services, "datetime"
        ) as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 9, 2, 16, 0, 0)
            datetime_mock.fromisoformat.side_effect = datetime.fromisoformat
            payload = market_services.build_fundamental_news_payload(tenant={"slug": "laowang"}, watchlist_details={})
        self.assertEqual(
            [item["title"] for item in payload["items"]],
            ["今日最新", "今日第二", "今日第三", "今日中间", "今日第四"],
        )
        self.assertEqual(payload["selection_mode"], "recent_3d_source_tabs")

    def test_fundamental_homepage_shows_only_latest_item_per_source(self):
        items = [
            {"title": "政策旧闻", "source_code": "policy", "source_name": "中国政府网", "published_at": "2026-09-02 09:00:00"},
            {"title": "政策最新", "source_code": "policy", "source_name": "中国政府网", "published_at": "2026-09-03 09:00:00"},
            {"title": "宏观最新", "source_code": "macro", "source_name": "国家统计局", "published_at": "2026-09-03 08:00:00"},
        ]
        with patch.object(market_services, "gen_news_feed", return_value=items), patch.object(
            market_services, "datetime"
        ) as datetime_mock:
            datetime_mock.now.return_value = datetime(2026, 9, 3, 12, 0, 0)
            datetime_mock.fromisoformat.side_effect = datetime.fromisoformat
            payload = market_services.build_fundamental_news_payload(tenant={"slug": "laowang"}, watchlist_details={})
        self.assertEqual([item["title"] for item in payload["items"]], ["政策最新", "宏观最新"])
        self.assertEqual(payload["tabs"][0]["count"], 2)
        self.assertEqual(payload["list_tabs"][0]["count"], 3)

    def test_prompt_only_algorithm_generates_executable_script(self):
        algorithm = market_services.normalize_news_aggregation_algorithm_payload({
            "source_prompt": "行业板块优先，个股标的命中加权，再补充最近重大新闻。",
        })
        self.assertIn("function rankNews", algorithm["script_js"])
        self.assertIn("sectorWeight = 120", algorithm["script_js"])
        self.assertIn("symbolWeight = 35", algorithm["script_js"])
        self.assertIn("majorWeight = 80", algorithm["script_js"])
        items = [
            {"title": "重大新闻通报", "content": "市场重大利好", "summary": "", "published_at": "2026-08-01 10:00:00"},
            {"title": "银行板块政策跟踪", "content": "中国银行", "summary": "", "published_at": "2026-08-01 09:00:00"},
        ]
        ranked = market_services._rank_news_for_tenant(
            items,
            tenant={"slug": "laowang"},
            watchlist_details=[{"industry": "银行", "name": "中国银行"}],
            algorithm_payload=algorithm,
        )
        self.assertEqual(ranked[0]["title"], "银行板块政策跟踪")
        self.assertEqual(ranked[0]["aggregation_bucket"], "watchlist_sector")

    def test_fallback_rank_requires_high_impact_event_not_source_category(self):
        macro_item = {
            "title": "国家统计局发布月度数据说明",
            "content": "宏观要闻更新",
            "summary": "",
            "source_group": "宏观要闻",
            "tag": "宏观要闻",
        }
        major_item = {
            "title": "央行宣布降准释放长期资金",
            "content": "重大政策事件",
            "summary": "",
            "source_group": "宏观要闻",
            "tag": "宏观要闻",
        }
        sector_item = {
            "title": "芯片产业链需求回暖",
            "content": "晶圆制造订单改善",
            "summary": "",
        }
        macro_rank = market_services._fallback_news_rank(macro_item, sectors=["半导体制造"], symbols=[])
        major_rank = market_services._fallback_news_rank(major_item, sectors=["半导体制造"], symbols=[])
        sector_rank = market_services._fallback_news_rank(sector_item, sectors=["半导体制造"], symbols=[])
        self.assertEqual(macro_rank["bucket"], "other")
        self.assertEqual(major_rank["bucket"], "major_market")
        self.assertEqual(sector_rank["bucket"], "watchlist_sector")

    def test_news_feed_uses_the_inclusive_five_day_window(self):
        now = datetime(2026, 8, 8, 12, 0, 0)
        items = [
            {"title": "窗口内新闻", "published_at": (now - timedelta(days=5)).isoformat()},
            {"title": "窗口外旧新闻", "published_at": (now - timedelta(days=5, seconds=1)).isoformat()},
            {"title": "窗口内未来校验", "published_at": (now + timedelta(days=5)).isoformat()},
            {"title": "窗口外未来新闻", "published_at": (now + timedelta(days=5, seconds=1)).isoformat()},
        ]
        with patch.object(market_services, "_aggregate_real_news_sources", return_value={"items": items}), patch.object(
            market_services, "datetime"
        ) as datetime_mock:
            datetime_mock.now.return_value = now
            datetime_mock.fromisoformat.side_effect = datetime.fromisoformat
            ranked = market_services.gen_news_feed(tenant={"slug": "laowang"}, watchlist_details=[])

        self.assertEqual({item["title"] for item in ranked}, {"窗口内新闻", "窗口内未来校验"})

    def test_news_feed_refreshes_stale_cache_when_window_has_no_items(self):
        now = datetime(2026, 8, 8, 12, 0, 0)
        stale = [{"title": "旧缓存新闻", "published_at": (now - timedelta(days=10)).isoformat()}]
        fresh = [{"title": "刷新后的新闻", "published_at": (now - timedelta(days=1)).isoformat()}]
        with patch.object(
            market_services,
            "_aggregate_real_news_sources",
            side_effect=[{"items": stale}, {"items": fresh}],
        ) as aggregate_mock, patch.object(market_services, "datetime") as datetime_mock:
            datetime_mock.now.return_value = now
            datetime_mock.fromisoformat.side_effect = datetime.fromisoformat
            ranked = market_services.gen_news_feed(tenant={"slug": "laowang"}, watchlist_details=[])

        self.assertEqual([item["title"] for item in ranked], ["刷新后的新闻"])
        aggregate_mock.assert_any_call(force_refresh=True)

    def test_news_feed_refreshes_empty_cache_instead_of_returning_no_news(self):
        now = datetime(2026, 8, 8, 12, 0, 0)
        fresh = [{"title": "实时来源新闻", "published_at": (now - timedelta(days=1)).isoformat()}]
        with patch.object(
            market_services,
            "_aggregate_real_news_sources",
            side_effect=[{"cached_at": now.isoformat(), "items": []}, {"items": fresh}],
        ) as aggregate_mock, patch.object(market_services, "datetime") as datetime_mock:
            datetime_mock.now.return_value = now
            datetime_mock.fromisoformat.side_effect = datetime.fromisoformat
            ranked = market_services.gen_news_feed(tenant={"slug": "laowang"}, watchlist_details=[])

        self.assertEqual([item["title"] for item in ranked], ["实时来源新闻"])
        aggregate_mock.assert_any_call(force_refresh=True)

    def test_transient_source_failure_is_not_permanently_excluded(self):
        with patch.object(
            market_services,
            "_load_json_app_setting",
            return_value={"excluded_codes": ["gov_cn_policy"]},
        ):
            active = market_services._load_active_news_source_whitelist()
        self.assertIn("gov_cn_policy", {item["code"] for item in active})

        saved = []
        with patch.object(market_services, "_load_json_app_setting", return_value={}), patch.object(
            market_services, "_save_json_app_setting", side_effect=lambda key, value: saved.append(value)
        ):
            market_services._persist_news_source_exclusions([
                {
                    "source": {"code": "gov_cn_policy"},
                    "included": False,
                    "count": 0,
                    "reason": "<urlopen error temporary network failure>",
                }
            ])
        self.assertEqual(saved, [])

    def test_news_lake_refreshes_from_active_sources_when_forced(self):
        source = {"code": "gov_cn_policy", "name": "中国政府网", "category": "政策", "source_group": "政策要闻"}
        source_item = {"event_id": "n1", "title": "来源新闻", "url": "https://example.com/n1", "published_at": "2026-09-15"}
        with patch.object(market_services, "_load_news_lake_cache", return_value=None), patch.object(
            market_services, "_load_active_news_source_whitelist", return_value=[source]
        ), patch.object(
            market_services, "_fetch_news_source", return_value={"source": source, "included": True, "count": 1, "reason": "ok", "items": [source_item]}
        ), patch.object(market_services, "_persist_news_source_exclusions"), patch.object(
            market_services, "_save_json_app_setting"
        ):
            payload = market_services._aggregate_real_news_sources(force_refresh=True)

        self.assertEqual(payload["items"][0]["title"], "来源新闻")
        self.assertEqual(payload["items"][0]["url"], "https://example.com/n1")

    def test_admin_news_source_payload_exposes_governed_runtime_status(self):
        aggregate_payload = {
            "cached_at": "2026-08-08T02:00:00",
            "items": [{"title": "真实事件"}],
            "sources": [
                {
                    "code": "gov_cn_policy",
                    "included": True,
                    "count": 20,
                    "reason": "已达到来源纳入门槛",
                },
            ],
        }
        with patch.object(market_services, "_aggregate_real_news_sources", return_value=aggregate_payload), patch.object(
            market_services, "_load_json_app_setting", return_value={"excluded_codes": ["gov_cn_policy"]}
        ):
            payload = market_services.build_admin_news_source_payload()

        self.assertEqual(payload["min_items"], 5)
        self.assertEqual(payload["total_events"], 1)
        self.assertEqual(payload["active_sources"], len(market_services.NEWS_SOURCE_WHITELIST))
        source = next(item for item in payload["sources"] if item["code"] == "gov_cn_policy")
        self.assertTrue(source["active"])
        self.assertTrue(source["historical_exclusion"])
        self.assertTrue(source["last_fetch_included"])

    def test_homepage_selection_prioritizes_related_news_and_limits_source_concentration(self):
        ranked = [
            {"title": f"宏观新闻 {index}", "aggregation_bucket": "major_market", "source_code": "stats_macro", "source_group": "宏观要闻"}
            for index in range(10)
        ] + [
            {"title": f"半导体新闻 {index}", "aggregation_bucket": "watchlist_sector", "source_code": f"sector_{index}", "source_group": "公司公告"}
            for index in range(3)
        ]
        selected = market_services._select_fundamental_homepage_news(ranked, 10)
        self.assertEqual([item["title"] for item in selected[:3]], ["半导体新闻 0", "半导体新闻 1", "半导体新闻 2"])
        self.assertLessEqual(sum(item["source_code"] == "stats_macro" for item in selected), 3)

    def test_homepage_selection_covers_each_watchlist_sector_before_filling_bank_heavy_news(self):
        ranked = [
            {
                "title": f"银行新闻 {index}",
                "content": "银行 信贷 息差 招商银行",
                "aggregation_bucket": "watchlist_sector",
                "relevance_score": 400 - index,
                "matched_topics": ["银行", "招商银行"],
                "source_code": f"bank_{index}",
                "source_group": "政策要闻",
            }
            for index in range(8)
        ] + [
            {
                "title": "贵州茅台白酒渠道更新",
                "content": "高端白酒 贵州茅台 消费修复",
                "aggregation_bucket": "watchlist_sector",
                "relevance_score": 180,
                "matched_topics": ["高端白酒", "贵州茅台"],
                "source_code": "liquor_source",
                "source_group": "公司公告",
            },
            {
                "title": "半导体晶圆制造订单改善",
                "content": "半导体制造 中芯国际 晶圆 订单",
                "aggregation_bucket": "watchlist_sector",
                "relevance_score": 170,
                "matched_topics": ["半导体制造", "中芯国际"],
                "source_code": "chip_source",
                "source_group": "公司公告",
            },
        ]
        watchlist = [
            {"industry": "银行", "name": "招商银行"},
            {"industry": "高端白酒", "name": "贵州茅台"},
            {"industry": "半导体制造", "name": "中芯国际"},
        ]

        selected = market_services._select_fundamental_homepage_news(ranked, 5, watchlist_details=watchlist)
        titles = [item["title"] for item in selected]

        self.assertIn("贵州茅台白酒渠道更新", titles)
        self.assertIn("半导体晶圆制造订单改善", titles)
        self.assertIn("银行新闻 0", titles)
        self.assertLessEqual(sum(title.startswith("银行新闻") for title in titles), 3)

    def test_prompt_is_decomposed_into_bounded_rule_atoms(self):
        algorithm = market_services.normalize_news_aggregation_algorithm_payload({
            "source_prompt": "先按自选股行业板块聚合，再看社会性重大利好/利空消息。首页只展示 8 条，每个来源最多 2 条，每类最多 3 条。",
            "script_js": "function rankNews(input) { return { score: 9999, bucket: 'major_market' }; }",
        })
        plan = algorithm["rule_plan"]
        self.assertEqual(plan["priority_order"], ["watchlist_sector", "major_market"])
        self.assertEqual(plan["presentation"]["home_limit"], 8)
        self.assertEqual(plan["diversity"]["max_per_source"], 2)
        self.assertEqual(plan["diversity"]["max_per_group"], 3)
        self.assertTrue(plan["filters"]["exclude_unrelated"])
        self.assertNotIn("9999", algorithm["script_js"])
        self.assertGreaterEqual(len(algorithm["rule_atoms"]), 5)


if __name__ == "__main__":
    unittest.main()
