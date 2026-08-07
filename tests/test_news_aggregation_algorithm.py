import unittest
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
