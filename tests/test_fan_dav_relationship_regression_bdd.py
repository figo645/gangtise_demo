"""BDD regressions for the persisted fan-to-DAv tenancy contract."""

import copy
import unittest
from unittest.mock import patch

import app as app_entry
from src.domain import core_services, market_services, workbench_services
from src.web import api_core, api_kol, api_quiz, hooks as web_hooks


TENANTS = [
    {"id": "tenant_laowang", "slug": "laowang", "name": "老王研究院", "short_name": "老王", "advisor": "财经老王"},
    {"id": "tenant_duoge", "slug": "duoge", "name": "多哥研究空间", "short_name": "多哥财经", "advisor": "duoge"},
]

USERS = [
    {"id": 1, "username": "财经老王", "role": "dav", "tenant_slug": "laowang", "status": "active"},
    {"id": 2, "username": "duoge", "role": "dav", "tenant_slug": "duoge", "status": "active"},
    {"id": 3, "username": "老王粉丝", "role": "investor", "tenant_slug": "laowang", "advisor_name": "财经老王", "status": "active", "is_paid_sample": True, "source_label": "社群", "labels": [], "created_at": "2026-09-17 10:00:00"},
    {"id": 4, "username": "多哥粉丝", "role": "investor", "tenant_slug": "duoge", "advisor_name": "duoge", "status": "active", "is_paid_sample": False, "source_label": "直播", "labels": [], "created_at": "2026-09-17 10:00:00"},
]


def _tenant(slug):
    normalized = str(slug or "").strip().lower()
    return next((copy.deepcopy(item) for item in TENANTS if item["slug"] == normalized), {})


def _users(role=None, tenant_slug=None):
    return [
        copy.deepcopy(item)
        for item in USERS
        if (not role or item["role"] == role)
        and (not tenant_slug or item["tenant_slug"] == tenant_slug)
    ]


class FanDavRelationshipRegressionBddTest(unittest.TestCase):
    def setUp(self):
        app_entry.app.config.update(TESTING=True)
        self.client = app_entry.app.test_client()
        self.authenticated = patch.object(web_hooks, "is_authenticated", return_value=True)
        self.authenticated.start()

    def tearDown(self):
        self.authenticated.stop()

    def test_given_new_dav_when_provisioned_then_a_dedicated_tenant_is_created(self):
        config = {"tenants": [copy.deepcopy(TENANTS[0])], "default_tenant_slug": "laowang"}
        saved_config = {}

        def find_tenant(slug, site_config=None):
            for tenant in (site_config or config).get("tenants", []):
                if tenant["slug"] == slug:
                    return tenant
            return {}

        def save_config(saved):
            saved_config.update(copy.deepcopy(saved))
            return saved

        with patch.object(core_services, "get_site_config", return_value=config), patch.object(
            core_services, "get_tenant_configs", side_effect=lambda source=None: copy.deepcopy((source or config)["tenants"])
        ), patch.object(core_services, "save_site_config", side_effect=save_config), patch.object(
            core_services, "get_tenant_by_slug", side_effect=find_tenant
        ):
            slug = core_services.provision_dav_tenant("duoge")

        self.assertNotEqual(slug, "laowang")
        created = next(item for item in saved_config["tenants"] if item["slug"] == slug)
        self.assertEqual(created["advisor"], "duoge")

    def test_given_fan_assignment_when_normalized_then_tenant_and_advisor_are_canonical(self):
        with app_entry.app.app_context(), patch.object(core_services, "get_tenant_by_slug", side_effect=_tenant), patch.object(
            core_services, "get_site_config", return_value={"role_capabilities": {"investor": ["h5"]}}
        ):
            payload = core_services.normalize_user_payload(
                {"username": "新粉丝", "password": "Abc123456", "phone": "13800000000", "role": "investor", "tenant_slug": "duoge", "advisor_name": "伪造名称"},
                context={"scope": "admin", "tenant_slug": "", "advisor_name": "", "allowed_roles": ["investor", "dav", "admin"]},
            )
            created_payload = {**payload, "advisor_name": "伪造名称"}
            # Creation owns the final attribution rather than trusting a browser value.
            with patch.object(core_services, "get_user_by_username", return_value=None), patch.object(
                core_services, "get_db"
            ) as db:
                db.return_value.execute.return_value = None
                core_services.create_user(created_payload)

        inserted_values = db.return_value.execute.call_args[0][1]
        self.assertEqual(inserted_values[3], "duoge")
        self.assertEqual(inserted_values[4], "duoge")

    def test_given_two_davs_when_statistics_build_then_each_tenant_only_counts_its_fans(self):
        with patch.object(workbench_services, "list_users", side_effect=_users), patch.object(
            workbench_services, "build_watchlist_comment_analytics", return_value={"summary": {}}
        ), patch.object(workbench_services, "load_tenant_fan_ops_settings", return_value={"registration_price": 100}), patch.object(
            workbench_services, "build_tenant_view_analytics", return_value={"total_views": 0, "active_viewers": 0, "distribution": [], "trend_7d": []}
        ):
            stats = workbench_services.build_tenant_ops_stats(tenant=_tenant("duoge"))

        with patch.object(market_services, "list_users", side_effect=_users), patch.object(
            market_services, "load_tenant_fan_ops_settings", return_value={"registration_price": 100}
        ), patch.object(market_services, "build_admin_kol_options", return_value=[]):
            channels = market_services.build_admin_channel_payload("duoge")

        self.assertEqual(stats["total_followers"], 1)
        self.assertEqual(stats["vip_subscribers"], 0)
        self.assertEqual(channels["total_users"], 1)
        self.assertEqual(channels["rows"][0]["name"], "直播")

    def test_given_dav_when_requesting_other_tenant_fan_statistics_then_access_is_denied(self):
        with patch.object(api_core, "get_current_authenticated_user", return_value=USERS[1]), patch.object(
            api_core, "get_tenant_by_slug", side_effect=_tenant
        ):
            response = self.client.get("/api/kol/business-analytics?tenant=laowang")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "tenant_scope_forbidden")

    def test_given_dav_when_requesting_own_fan_statistics_then_only_own_tenant_is_used(self):
        with patch.object(api_core, "get_current_authenticated_user", return_value=USERS[1]), patch.object(
            api_core, "get_tenant_by_slug", side_effect=_tenant
        ), patch.object(api_core, "list_users", side_effect=_users), patch.object(
            api_core, "build_tenant_ops_stats", return_value={"total_followers": 1}
        ), patch.object(api_core, "build_tenant_business_analytics", return_value={"estimated_revenue": 0}):
            response = self.client.get("/api/kol/business-analytics?tenant=duoge")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["stats"]["total_followers"], 1)

    def test_given_dav_when_requesting_other_tenant_comment_analytics_then_access_is_denied(self):
        with patch.object(api_core, "get_current_authenticated_user", return_value=USERS[1]):
            response = self.client.get("/api/tenant/laowang/watchlist-comment-analytics")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "tenant_scope_forbidden")

    def test_given_fan_observation_event_when_saved_then_investor_cannot_read_tenant_aggregate(self):
        with patch.object(api_kol, "get_current_authenticated_user", return_value=USERS[2]), patch.object(
            api_kol, "get_tenant_by_slug", side_effect=_tenant
        ), patch.object(api_kol, "record_fan_stock_observation_event", return_value={"id": 1}), patch.object(
            api_kol, "build_fan_stock_observation_payload"
        ) as aggregate:
            response = self.client.post("/api/tenant/laowang/fan-stock-observation", json={"stock_code": "600519", "event_type": "watchlist_add"})

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertTrue(response.get_json()["recorded"])
        self.assertNotIn("fan_stock_observation", response.get_json())
        aggregate.assert_not_called()

    def test_given_fan_when_starting_a_quiz_for_another_dav_then_the_attempt_is_denied(self):
        with patch.object(api_quiz, "get_current_authenticated_user", return_value=USERS[2]):
            response = self.client.post("/api/quiz/daily/start", json={"tenant_slug": "duoge"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "tenant_scope_forbidden")

    def test_given_broadcast_when_dispatched_then_only_that_dav_and_its_fans_receive_it(self):
        captured = {}
        state = {"summary": {}, "threads": [], "broadcasts": []}

        def save_threads(_slug, _state, threads):
            captured["threads"] = threads
            return {}, state

        with patch.object(core_services, "get_tenant_by_slug", side_effect=_tenant), patch.object(
            core_services, "resolve_tenant_message_center_state", return_value=state
        ), patch.object(core_services, "list_users", side_effect=_users), patch.object(
            core_services, "save_tenant_message_threads", side_effect=save_threads
        ):
            core_services.push_broadcast_to_fan_threads("duoge", {"content": "午间播报", "type": "agent_broadcast"})

        recipients = {item["user_profile_id"] for item in captured["threads"]}
        self.assertEqual(recipients, {"duoge", "多哥粉丝"})


if __name__ == "__main__":
    unittest.main()
