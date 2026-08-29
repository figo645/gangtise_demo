import unittest
from pathlib import Path
from unittest.mock import patch

from src.domain.market_services import build_admin_channel_payload, build_admin_funnel_payload
from src.domain.workbench_services import (
    build_admin_commission_payload,
    build_admin_kol_analytics_payload,
    build_admin_revenue_analytics_payload,
    build_tenant_business_analytics,
)


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

    def test_given_tenant_paid_users_when_commission_builds_then_amounts_use_persisted_inputs(self):
        tenants = [{"slug": "demo", "name": "示例租户", "advisor": "示例投顾", "tier": "种子投顾"}]
        users = [{"id": 1, "role": "investor", "is_paid_sample": True}]
        ops_stats = {"monthly_revenue": 500, "vip_subscribers": 1, "registration_price": 500}
        with patch("src.domain.workbench_services.get_tenant_configs", return_value=tenants), patch(
            "src.domain.workbench_services.list_users", return_value=users
        ), patch("src.domain.workbench_services.build_tenant_ops_stats", return_value=ops_stats):
            payload = build_admin_commission_payload()

        self.assertEqual(payload["pending_total"], 0)
        self.assertEqual(payload["settled_total"], 0)
        self.assertEqual(payload["rows"][0]["revenue"], 500)
        self.assertEqual(payload["rows"][0]["payable"], 0)
        self.assertEqual(payload["rows"][0]["source"], "付费用户标注 × 注册单价")

    def test_given_channel_labeled_users_when_channel_payload_builds_then_no_demo_metrics_are_used(self):
        users = [
            {
                "role": "investor", "status": "active", "source_label": "微信社群",
                "created_at": "2026-08-03 10:00:00", "is_paid_sample": True,
                "tenant_slug": "demo",
            },
            {
                "role": "investor", "status": "active", "source_label": "微信社群",
                "created_at": "2026-07-03 10:00:00", "is_paid_sample": False,
                "tenant_slug": "demo",
            },
        ]
        with patch("src.domain.market_services.list_users", return_value=users), patch(
            "src.domain.market_services.load_tenant_fan_ops_settings", return_value={"registration_price": 500}
        ):
            payload = build_admin_channel_payload()

        self.assertEqual(payload["total_users"], 2)
        self.assertEqual(payload["new_users_month"], 1)
        self.assertEqual(payload["paid_users"], 1)
        self.assertEqual(payload["revenue"], 500)
        self.assertFalse(payload["cac_available"])
        self.assertFalse(payload["roi_available"])

    def test_given_persisted_users_and_access_events_when_funnel_builds_then_stages_are_real(self):
        class FakeResult:
            def fetchone(self):
                return {"count": 7}

        class FakeDb:
            def execute(self, *_args):
                return FakeResult()

        users = [
            {
                "role": "investor", "status": "active", "tenant_slug": "demo",
                "source_label": "微信社群", "onboarding_completed_at": "2026-08-02 10:00:00",
                "is_paid_sample": True, "labels": ["付费用户", "高频用户"],
                "paid_sample_marked_at": "2026-08-03 10:00:00", "created_at": "2026-08-01 10:00:00",
            },
            {
                "role": "investor", "status": "active", "tenant_slug": "demo",
                "source_label": "微信社群", "onboarding_completed_at": "",
                "is_paid_sample": False, "labels": [], "created_at": "2026-08-04 10:00:00",
            },
        ]
        tenants = [{"slug": "demo", "name": "示例租户", "advisor": "示例投顾"}]
        with patch("src.domain.market_services.list_users", return_value=users), patch(
            "src.domain.market_services.get_tenant_configs", return_value=tenants
        ), patch("src.domain.market_services.load_tenant_fan_ops_settings", return_value={"registration_price": 299}), patch(
            "src.domain.market_services.get_db", return_value=FakeDb()
        ):
            payload = build_admin_funnel_payload()

        self.assertEqual([item["count"] for item in payload["funnel"]], [7, 2, 1, 1, 1])
        self.assertEqual(payload["channels"]["rows"][0]["users"], 2)
        self.assertEqual(payload["monthly"][-1]["revenue"], 299)
        self.assertEqual(payload["kols"][0]["gmv"], 299)
        self.assertEqual(payload["segments"][0]["count"], 1)
        self.assertEqual(payload["heatmap"][0]["values"][3], 50.0)

    def test_given_selected_kol_when_funnel_builds_then_all_user_metrics_use_that_tenant(self):
        users = [
            {"role": "investor", "status": "active", "tenant_slug": "demo", "source_label": "公众号",
             "onboarding_completed_at": "2026-08-02 10:00:00", "is_paid_sample": True,
             "labels": ["付费用户"], "paid_sample_marked_at": "2026-08-03 10:00:00",
             "created_at": "2026-08-01 10:00:00"},
            {"role": "investor", "status": "active", "tenant_slug": "other", "source_label": "直播",
             "onboarding_completed_at": "2026-08-02 10:00:00", "is_paid_sample": True,
             "labels": ["付费用户"], "paid_sample_marked_at": "2026-08-03 10:00:00",
             "created_at": "2026-08-01 10:00:00"},
        ]

        class FakeResult:
            def fetchone(self):
                return {"count": 1}

        class FakeDb:
            def execute(self, sql, params):
                self.sql = sql
                self.params = params
                return FakeResult()

        tenants = [
            {"slug": "demo", "name": "示例租户", "advisor": "示例投顾"},
            {"slug": "other", "name": "其他租户", "advisor": "其他投顾"},
        ]
        with patch("src.domain.market_services.list_users", side_effect=lambda role=None, tenant_slug=None: [
            user for user in users
            if not tenant_slug or user["tenant_slug"] == tenant_slug
        ]), patch(
            "src.domain.market_services.get_tenant_configs", return_value=tenants
        ), patch("src.domain.market_services.load_tenant_fan_ops_settings", return_value={"registration_price": 299}), patch(
            "src.domain.market_services.get_db", return_value=FakeDb()
        ):
            payload = build_admin_funnel_payload("demo")

        self.assertEqual([item["count"] for item in payload["funnel"]], [1, 1, 1, 1, 0])
        self.assertEqual(payload["kol_filter"], "demo")
        self.assertEqual(payload["kols"], [{"name": "示例投顾", "gmv": 299, "commission": 0}])
        self.assertEqual({item["slug"] for item in payload["kol_options"]}, {"demo", "other"})

    def test_given_persisted_paid_users_when_admin_revenue_builds_then_price_and_paid_marker_drive_metrics(self):
        from datetime import datetime

        month = datetime.now().strftime("%Y-%m")
        tenants = [{"slug": "demo", "name": "示例租户"}]
        users = [
            {"role": "investor", "tenant_slug": "demo", "is_paid_sample": True,
             "paid_sample_marked_at": f"{month}-02 10:00:00", "created_at": f"{month}-01 10:00:00"},
            {"role": "investor", "tenant_slug": "demo", "is_paid_sample": False,
             "created_at": f"{month}-03 10:00:00"},
        ]
        with patch("src.domain.workbench_services.list_users", return_value=users), patch(
            "src.domain.workbench_services.get_tenant_configs", return_value=tenants
        ), patch("src.domain.workbench_services.load_tenant_fan_ops_settings", return_value={"registration_price": 299}):
            payload = build_admin_revenue_analytics_payload()

        self.assertEqual(payload["mrr"], 299)
        self.assertEqual(payload["arr"], 3588)
        self.assertEqual(payload["paid_users"], 1)
        self.assertEqual(payload["monthly"][-1], {"month": month, "revenue": 299, "users": 1})
        self.assertEqual(payload["channel_revenue"][0]["revenue"], 299)
        self.assertEqual(payload["active_tenants"], 1)
        self.assertEqual(payload["average_price"], 299)
        self.assertEqual(payload["tenant_revenue"][0]["paid_users"], 1)
        self.assertEqual(payload["tenant_revenue"][0]["revenue"], 299)

    def test_given_selected_kol_when_revenue_and_collaboration_build_then_only_that_kol_is_included(self):
        tenants = [
            {"slug": "demo", "name": "示例租户", "advisor": "示例投顾", "tier": "种子投顾", "commission_rate": 15},
            {"slug": "other", "name": "其他租户", "advisor": "其他投顾", "tier": "成长投顾", "commission_rate": 20},
        ]
        users = [
            {"role": "investor", "tenant_slug": "demo", "is_paid_sample": True, "created_at": "2026-08-01 10:00:00"},
            {"role": "investor", "tenant_slug": "other", "is_paid_sample": True, "created_at": "2026-08-01 10:00:00"},
        ]
        with patch("src.domain.workbench_services.get_tenant_configs", return_value=tenants), patch(
            "src.domain.workbench_services.list_users", side_effect=lambda role=None, tenant_slug=None: [
                user for user in users if not tenant_slug or user["tenant_slug"] == tenant_slug
            ]
        ), patch("src.domain.workbench_services.load_tenant_fan_ops_settings", return_value={"registration_price": 299}):
            revenue = build_admin_revenue_analytics_payload("demo")
            collaboration = build_admin_kol_analytics_payload("demo")

        self.assertEqual(revenue["kol_filter"], "demo")
        self.assertEqual([item["tenant_slug"] for item in revenue["tenant_revenue"]], ["demo"])
        self.assertEqual(collaboration["kol_filter"], "demo")
        self.assertEqual([item["name"] for item in collaboration["rows"]], ["示例投顾"])

    def test_given_real_tenant_and_fans_when_admin_kol_builds_then_no_static_kol_rows_are_added(self):
        tenants = [{"slug": "demo", "name": "示例租户", "advisor": "示例投顾", "tier": "种子投顾", "commission_rate": 15}]
        users = [
            {"role": "investor", "tenant_slug": "demo", "is_paid_sample": True},
            {"role": "investor", "tenant_slug": "demo", "is_paid_sample": False},
        ]
        with patch("src.domain.workbench_services.get_tenant_configs", return_value=tenants), patch(
            "src.domain.workbench_services.list_users", return_value=users
        ), patch("src.domain.workbench_services.load_tenant_fan_ops_settings", return_value={"registration_price": 500}):
            payload = build_admin_kol_analytics_payload()

        self.assertEqual(payload["total_kols"], 1)
        self.assertEqual(payload["rows"], [{
            "name": "示例投顾", "platform": "示例租户", "fans": 2, "gmv": 500,
            "commission": 75.0, "rate": 15.0, "tier": "种子投顾", "trend": "--",
        }])
        self.assertEqual(payload["tier_counts"], {"种子投顾": 1})

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

    def test_given_admin_analytics_when_funnel_or_channel_opens_then_real_admin_endpoints_are_used(self):
        charts = (PROJECT_ROOT / "static" / "js" / "charts.js").read_text(encoding="utf-8")
        self.assertIn("/api/admin/funnel-analytics", charts)
        self.assertIn("/api/admin/channels", charts)
        self.assertNotIn("const CHANNEL_DATA =", charts)
        self.assertNotIn("const CHANNEL_MONTHLY =", charts)

    def test_given_admin_funnel_when_opened_then_kol_scope_control_is_visible(self):
        template = (PROJECT_ROOT / "templates" / "admin.html").read_text(encoding="utf-8")
        charts = (PROJECT_ROOT / "static" / "js" / "charts.js").read_text(encoding="utf-8")
        self.assertIn('id="admin-analytics-kol-input"', template)
        self.assertIn('list="admin-analytics-kol-options"', template)
        self.assertIn('id="admin-analytics-kol-options"', template)
        self.assertIn('id="admin-analytics-kol-list"', template)
        self.assertIn('id="admin-analytics-scope"', template)
        self.assertIn("placeholder=\"输入大V名称筛选，留空为全部\"", template)
        self.assertIn("/api/admin/channels${query}", charts)
        self.assertIn("/api/admin/kol-analytics${query}", charts)
        self.assertIn("/api/admin/revenue-analytics${query}", charts)
        self.assertIn("tenant_slug=${encodeURIComponent(adminFunnelKolSlug)}", charts)
        self.assertIn("function applyAdminAnalyticsKolFilter", charts)
        self.assertIn("function selectAdminAnalyticsKol", charts)
        self.assertIn("function updateAdminAnalyticsScope", charts)
        self.assertIn("document.querySelector('.admin-funnel-kol-picker')", charts)

    def test_given_admin_sidebar_when_data_analysis_is_rendered_then_it_is_an_independent_category(self):
        template = (PROJECT_ROOT / "templates" / "admin.html").read_text(encoding="utf-8")
        start = template.index('data-nav-group="data-analysis"')
        end = template.index('data-nav-group="system"', start)
        group = template[start:end]
        self.assertIn('id="nav-funnel"', group)
        self.assertIn('id="nav-channel"', group)
        self.assertIn('id="nav-kol"', group)
        self.assertIn('id="nav-revenue"', group)
        channels_start = template.index('data-nav-group="channels"')
        self.assertLess(channels_start, start)
        indicator_start = template.index('data-nav-group="indicator"')
        self.assertLess(indicator_start, start)
        indicator_end = template.index('data-nav-group="data-analysis"', indicator_start)
        indicator_group = template[indicator_start:indicator_end]
        self.assertIn('data-section="indicator-overview"', indicator_group)
        self.assertNotIn('id="nav-funnel"', indicator_group)
        self.assertNotIn('data-nav-group="analytics"', template)
