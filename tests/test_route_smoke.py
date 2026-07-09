import unittest

import app as app_entry
import src.web.hooks as web_hooks
from src.services import get_tenant_configs


def _tenant_slugs():
    try:
        tenants = get_tenant_configs()
    except Exception:
        return ["lisa"]
    slugs = [str(item.get("slug") or "").strip() for item in tenants if str(item.get("slug") or "").strip()]
    return slugs or ["lisa"]


class RouteSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._original_password_gate = web_hooks.is_password_gate_enabled
        web_hooks.is_password_gate_enabled = lambda: False
        app_entry.app.config.update(TESTING=True)
        cls.client = app_entry.app.test_client()
        cls.tenant_slugs = _tenant_slugs()

    @classmethod
    def tearDownClass(cls):
        web_hooks.is_password_gate_enabled = cls._original_password_gate

    def test_h5_pages_render(self):
        for tenant_slug in self.tenant_slugs:
            with self.subTest(route="/h5", tenant=tenant_slug):
                response = self.client.get(f"/h5?tenant={tenant_slug}")
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.content_type)
                self.assertIn("Hermes", response.get_data(as_text=True))

    def test_workbench_pages_render(self):
        for tenant_slug in self.tenant_slugs:
            with self.subTest(route="/kol-workbench", tenant=tenant_slug):
                response = self.client.get(f"/kol-workbench?tenant={tenant_slug}")
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.content_type)
                self.assertIn("工作台", response.get_data(as_text=True))

    def test_tenant_portal_pages_render(self):
        for tenant_slug in self.tenant_slugs:
            with self.subTest(route="/tenant/<tenant_slug>", tenant=tenant_slug):
                response = self.client.get(f"/tenant/{tenant_slug}")
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response.content_type)
                self.assertIn("Dashboard", response.get_data(as_text=True))

    def test_workbench_api_payloads(self):
        for tenant_slug in self.tenant_slugs:
            with self.subTest(route="/api/kol/workbench", tenant=tenant_slug):
                response = self.client.get(f"/api/kol/workbench?tenant={tenant_slug}")
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertIsInstance(payload, dict)
                self.assertIn("fund_dashboard", payload)
                self.assertIn("indicator_hub", payload)

    def test_dashboard_api_payloads(self):
        for tenant_slug in self.tenant_slugs:
            with self.subTest(route="/api/tenant/<tenant_slug>/dashboard", tenant=tenant_slug):
                response = self.client.get(f"/api/tenant/{tenant_slug}/dashboard")
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertTrue(payload["success"])
                self.assertIn("dashboard", payload)
                self.assertIn("fund_dashboard_state", payload)

    def test_smart_indicator_api_payloads(self):
        for tenant_slug in self.tenant_slugs:
            with self.subTest(route="/api/tenant/<tenant_slug>/smart-indicators", tenant=tenant_slug):
                response = self.client.get(f"/api/tenant/{tenant_slug}/smart-indicators")
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                self.assertTrue(payload["success"])
                self.assertIn("smart_indicator_catalog", payload)
                self.assertIn("dashboard", payload)


if __name__ == "__main__":
    unittest.main()
