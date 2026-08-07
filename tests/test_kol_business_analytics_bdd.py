import unittest
from pathlib import Path

from src.domain.workbench_services import build_tenant_business_analytics


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class KolBusinessAnalyticsBddTest(unittest.TestCase):
    def setUp(self):
        self.users = [
            {
                "status": "active",
                "is_paid_sample": True,
                "created_at": "2026-07-10 10:00:00",
                "paid_sample_marked_at": "2026-07-12 10:00:00",
                "labels": ["付费用户", "高频用户"],
                "source_label": "公众号",
            },
            {
                "status": "active",
                "is_paid_sample": False,
                "created_at": "2026-08-02 10:00:00",
                "labels": ["高价值用户"],
                "source_label": "直播",
            },
            {
                "status": "active",
                "is_paid_sample": True,
                "created_at": "2026-08-03 10:00:00",
                "paid_sample_marked_at": "2026-08-04 10:00:00",
                "labels": ["付费用户"],
                "source_label": "公众号",
            },
        ]

    def test_given_tenant_users_when_analytics_builds_then_all_chart_datasets_are_populated(self):
        analytics = build_tenant_business_analytics(self.users, {"registration_price": 100})

        self.assertEqual(analytics["estimated_revenue"], 200)
        self.assertEqual(len(analytics["funnel"]), 4)
        self.assertTrue(all(item["count"] >= 0 for item in analytics["funnel"]))
        self.assertEqual(len(analytics["source_rows"]), 2)
        self.assertTrue(all("conversion_rate" in item for item in analytics["source_rows"]))
        self.assertEqual(len(analytics["monthly_series"]), 6)
        self.assertTrue(any(item["revenue"] > 0 for item in analytics["monthly_series"]))
        self.assertEqual(sum(item["count"] for item in analytics["segments"]), len(self.users))

    def test_given_workbench_when_data_analysis_renders_then_all_four_views_have_chart_targets(self):
        template = (PROJECT_ROOT / "templates" / "kol_workbench.html").read_text(encoding="utf-8")
        required_targets = [
            "kw-biz-funnel-chart",
            "kw-biz-source-pie",
            "kw-biz-revenue-trend",
            "kw-biz-label-pie",
            "kw-biz-channel-users",
            "kw-biz-channel-revenue",
            "kw-biz-monthly-revenue",
            "kw-biz-monthly-growth",
            "kw-biz-revenue-source-bar",
            "kw-biz-segment-pie",
            "kw-biz-label-bar",
        ]
        for target in required_targets:
            self.assertIn(f'id="{target}"', template)
        for section in ("funnel", "channel", "revenue", "segment"):
            self.assertIn(f'id="kw-biz-section-{section}"', template)
            self.assertIn(f'id="kw-biz-nav-{section}"', template)
        self.assertIn("renderKwBizDashboardCharts(section)", template)
        self.assertIn("window.GangtiseEcharts.render", template)
        self.assertIn("kw-biz-chart-empty", template)
        self.assertIn("暂无可展示的数据", template)

    def test_given_offline_or_restricted_network_when_workbench_loads_then_echarts_is_served_locally(self):
        template = (PROJECT_ROOT / "templates" / "kol_workbench.html").read_text(encoding="utf-8")
        asset = PROJECT_ROOT / "static" / "echarts.min.js"

        self.assertIn('<script src="/static/echarts.min.js"></script>', template)
        self.assertNotIn("cdn.jsdelivr.net/npm/echarts", template)
        self.assertTrue(asset.exists())
        self.assertGreater(asset.stat().st_size, 500_000)

    def test_given_chart_is_prepared_in_a_hidden_tab_when_the_tab_opens_then_helper_resizes_it(self):
        helper = (PROJECT_ROOT / "static" / "js" / "echarts_helpers.js").read_text(encoding="utf-8")
        template = (PROJECT_ROOT / "templates" / "kol_workbench.html").read_text(encoding="utf-8")

        self.assertIn("function getChartSize(container)", helper)
        self.assertIn("width: size.width, height: size.height", helper)
        self.assertIn("function resizeAll()", helper)
        self.assertIn("window.GangtiseEcharts.resizeAll()", template)

    def test_given_dynamic_dashboard_rerender_when_chart_ids_are_reused_then_detached_instances_are_released(self):
        helper = (PROJECT_ROOT / "static" / "js" / "echarts_helpers.js").read_text(encoding="utf-8")
        template = (PROJECT_ROOT / "templates" / "kol_workbench.html").read_text(encoding="utf-8")

        self.assertIn("current.getDom() === container", helper)
        self.assertIn("Dynamic pages can replace a chart node", helper)
        self.assertIn("kw-biz-funnel-chart', 'kw-biz-source-pie'", template)
        self.assertIn("window.GangtiseEcharts.dispose(chartId)", template)
