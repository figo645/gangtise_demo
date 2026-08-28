import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from src.runtime import app
from src.web.pages import h5, login_entry, resolve_login_destination


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AccountNavigationBddTest(unittest.TestCase):
    def test_given_admin_session_when_h5_is_requested_then_h5_is_rendered(self):
        with app.test_request_context("/h5?tenant=laowang"), patch(
            "src.web.pages.get_current_authenticated_user",
            return_value={"username": "admin", "role": "admin", "status": "active"},
        ), patch("src.web.pages.get_site_config", return_value={}), patch(
            "src.web.pages.get_current_demo_profile",
            return_value={"username": "admin", "role": "admin", "tenant": {}},
        ), patch(
            "src.web.pages.get_tenant_by_slug",
            return_value={"id": "tenant-laowang", "slug": "laowang", "name": "财经老王研究院", "advisor": "财经老王"},
        ), patch("src.web.pages.build_indicator_hub", return_value={"smart_items": []}), patch(
            "src.web.pages.build_fundamental_column_payload", return_value={}
        ), patch("src.web.pages.build_indicator_dashboard_seed_cards", return_value=[]), patch(
            "src.web.pages.build_tenant_dashboard_payload", return_value={}
        ), patch("src.web.pages.get_auth_settings", return_value={"quick_select_enabled": False}), patch(
            "src.web.pages.gen_market_data", return_value={}
        ), patch("src.web.pages.build_fundamental_news_payload", return_value={"items": [], "tabs": []}), patch(
            "src.web.pages.gen_feed_boards_from_watchlist_details", return_value=[]
        ):
            response = app.make_response(h5())

        self.assertEqual(response.status_code, 200)
        self.assertIn("CURRENT_DEMO_PROFILE", response.get_data(as_text=True))
        self.assertIn('"role": "admin"', response.get_data(as_text=True))

    def test_given_admin_switching_from_a_role_page_when_login_completes_then_admin_keeps_workbench_destination(self):
        with app.test_request_context("/login"):
            destination = resolve_login_destination({"role": "admin", "tenant_slug": "laowang"}, "/kol-workbench?tenant=laowang")

        self.assertEqual(destination, "/login/entry?next=/kol-workbench?tenant%3Dlaowang")

    def test_given_admin_switching_from_h5_when_login_completes_then_admin_keeps_h5_destination(self):
        with app.test_request_context("/login"):
            destination = resolve_login_destination({"role": "admin", "tenant_slug": "laowang"}, "/h5?tenant=laowang")

        self.assertEqual(destination, "/login/entry?next=/h5?tenant%3Dlaowang")

    def test_given_admin_entry_page_exposes_h5_workbench_and_admin_backend(self):
        with app.test_request_context("/login/entry?next=/h5"):
            with patch("src.web.pages.get_current_authenticated_user", return_value={"username": "admin", "role": "admin", "status": "active", "tenant_slug": "laowang"}):
                response = app.make_response(login_entry())

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("进入 H5", html)
        self.assertIn("进入大V工作台", html)
        self.assertIn("进入 Admin 后台", html)

    def test_given_investor_switching_from_admin_when_login_completes_then_investor_returns_to_h5(self):
        with app.test_request_context("/login"):
            destination = resolve_login_destination({"role": "investor", "tenant_slug": "laowang"}, "/admin?section=users")

        self.assertEqual(destination, "/h5?tenant=laowang")

    def test_given_signed_in_user_when_switching_account_then_session_is_cleared_and_next_page_is_preserved(self):
        client = app.test_client()
        with client.session_transaction() as stored_session:
            stored_session["current_h5_username"] = "admin"

        response = client.get("/switch-account?next=/admin?section=users", follow_redirects=False)
        query = parse_qs(urlsplit(response.headers["Location"]).query)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response.headers["Location"]).path, "/login")
        self.assertEqual(query.get("next"), ["/admin?section=users"])
        with client.session_transaction() as stored_session:
            self.assertNotIn("current_h5_username", stored_session)

    def test_given_dav_when_logging_out_then_all_session_state_is_cleared_and_login_page_is_used(self):
        client = app.test_client()
        with client.session_transaction() as stored_session:
            stored_session["current_h5_username"] = "laowang"
            stored_session["database_release_unlock_until"] = 4102444800
            stored_session["h5_wechat_login_state"] = "state"

        response = client.get("/logout", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        with client.session_transaction() as stored_session:
            self.assertFalse(dict(stored_session))

    def test_given_h5_user_when_logging_out_then_the_api_clears_the_full_shared_session(self):
        client = app.test_client()
        with client.session_transaction() as stored_session:
            stored_session["current_h5_username"] = "laowang"
            stored_session["database_release_unlock_until"] = 4102444800

        response = client.post("/api/h5/logout")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        with client.session_transaction() as stored_session:
            self.assertFalse(dict(stored_session))

    def test_given_admin_credentials_on_h5_when_login_succeeds_then_admin_session_is_kept_and_browser_is_redirected_to_entry_choice(self):
        admin = {"username": "admin", "role": "admin", "status": "active"}
        client = app.test_client()
        with patch("src.web.api_core.get_site_config", return_value={}), patch(
            "src.web.api_core.get_auth_settings", return_value={"password_login_enabled": True}
        ), patch("src.web.api_core.verify_h5_password_login", return_value=admin), patch(
            "src.web.api_core._build_h5_auth_options_payload", return_value={"auth_settings": {}, "profiles": []}
        ):
            response = client.post("/api/h5/login/password", json={"username": "admin", "password": "admin123"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["redirect_to"], "/login/entry?next=/h5")
        self.assertIsNone(response.get_json()["current_profile"])
        with client.session_transaction() as stored_session:
            self.assertEqual(stored_session.get("current_h5_username"), "admin")

    def test_given_admin_and_workbench_pages_when_rendered_then_both_expose_the_same_account_actions(self):
        admin_template = (PROJECT_ROOT / "templates" / "admin.html").read_text(encoding="utf-8")
        workbench_template = (PROJECT_ROOT / "templates" / "kol_workbench.html").read_text(encoding="utf-8")
        shared_css = (PROJECT_ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")

        for template in (admin_template, workbench_template):
            self.assertIn("platform-topbar-actions", template)
            self.assertIn("platform-account-chip", template)
            self.assertIn("/switch-account?next=", template)
            self.assertIn(">切换账号<", template)
            self.assertIn('href="/logout"', template)
            self.assertIn(">退出登录<", template)
        self.assertIn(".platform-account-chip", shared_css)
        self.assertIn(".platform-account-action", shared_css)


if __name__ == "__main__":
    unittest.main()
