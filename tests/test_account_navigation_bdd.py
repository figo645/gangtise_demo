import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from src.runtime import app
from src.web.pages import resolve_login_destination


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AccountNavigationBddTest(unittest.TestCase):
    def test_given_admin_switching_from_a_role_page_when_login_completes_then_admin_returns_to_admin(self):
        with app.test_request_context("/login"):
            destination = resolve_login_destination({"role": "admin", "tenant_slug": "laowang"}, "/kol-workbench?tenant=laowang")

        self.assertEqual(destination, "/admin")

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
