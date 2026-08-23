import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from src.domain.core_services import normalize_tenant_config
from src.domain import market_services


class NewsAggregationAlgorithmTest(unittest.TestCase):
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

    def test_build_fundamental_news_payload_limits_to_ten_and_groups_tabs(self):
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
        self.assertEqual(len(payload["items"]), 10)
        self.assertEqual(payload["total"], 10)
        self.assertGreaterEqual(len(payload["tabs"]), 3)
        self.assertEqual(payload["tabs"][0]["key"], "summary")
        self.assertEqual(payload["tabs"][0]["count"], 10)
        self.assertEqual(payload["tabs"][1]["key"], "all")
        self.assertEqual(payload["tabs"][1]["count"], len(items))

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

    def test_news_feed_uses_the_inclusive_three_day_window(self):
        now = datetime(2026, 8, 8, 12, 0, 0)
        items = [
            {"title": "窗口内新闻", "published_at": (now - timedelta(days=3)).isoformat()},
            {"title": "窗口外旧新闻", "published_at": (now - timedelta(days=3, seconds=1)).isoformat()},
            {"title": "窗口内未来校验", "published_at": (now + timedelta(days=3)).isoformat()},
            {"title": "窗口外未来新闻", "published_at": (now + timedelta(days=3, seconds=1)).isoformat()},
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

    def test_news_lake_preserves_previous_real_cache_when_refresh_fails(self):
        stale_cache = {
            "cached_at": "2026-08-01T10:00:00",
            "items": [{"title": "旧的真实新闻", "published_at": "2026-08-01T09:00:00"}],
            "indicators": [{"indicator_code": "news_event_count", "value": 1}],
            "sources": [{"code": "gov_cn_policy", "included": True, "count": 12, "reason": "已达到来源纳入门槛"}],
        }
        with patch.object(market_services, "_load_json_app_setting", return_value=stale_cache), patch.object(
            market_services,
            "_load_active_news_source_whitelist",
            return_value=[{"code": "gov_cn_policy", "url": "http://example.invalid", "name": "政策要闻", "category": "政策", "source_group": "政策要闻", "validated_item_count": 12}],
        ), patch.object(
            market_services,
            "_fetch_news_source",
            return_value={
                "source": {"code": "gov_cn_policy", "name": "政策要闻", "category": "政策"},
                "included": False,
                "count": 0,
                "reason": "<urlopen error [Errno 8] nodename nor servname provided, or not known>",
                "items": [],
            },
        ), patch.object(
            market_services, "_persist_news_source_exclusions"
        ) as persist_mock, patch.object(market_services, "_save_json_app_setting") as save_mock:
            payload = market_services._aggregate_real_news_sources(force_refresh=True)

        self.assertEqual(payload["items"][0]["title"], "旧的真实新闻")
        persist_mock.assert_called_once()
        save_mock.assert_not_called()

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
