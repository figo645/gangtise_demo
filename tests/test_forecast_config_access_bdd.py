"""API acceptance for prediction workflow access in the DAV workbench."""

from contextlib import ExitStack
from pathlib import Path
import unittest
from unittest.mock import patch

from app import app
from src.domain.core_services import build_default_forecast_workflow_graph


class ForecastConfigAccessBDD(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.user = {"username": "forecast-dav", "role": "dav", "tenant_slug": "laowang"}
        for module in ("src.web.hooks", "src.web.api_core"):
            self.stack.enter_context(patch(
                f"{module}.get_current_authenticated_user", side_effect=lambda: self.user,
            ))
        self.stack.enter_context(patch("src.domain.core_services.get_site_config", return_value={}))
        self.enabled = self.stack.enter_context(patch("src.web.api_core.is_feature_enabled", return_value=True))
        self.graph = build_default_forecast_workflow_graph()
        self.load = self.stack.enter_context(patch("src.web.api_core.load_forecast_workflow_graph", return_value=self.graph))
        self.save = self.stack.enter_context(patch("src.web.api_core.save_forecast_workflow_graph", side_effect=lambda graph: graph))
        self.client = app.test_client()

    def test_dav_can_load_prediction_workflow(self):
        response = self.client.get("/api/kol/forecast-config")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertIn("graph", response.get_json()["workflow_meta"])

    def test_dav_can_save_prediction_workflow(self):
        response = self.client.post("/api/kol/forecast-config", json={"graph": self.graph})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.save.assert_called_once()

    def test_dav_can_restore_recommended_workflow(self):
        response = self.client.post("/api/kol/forecast-config", json={"reset_default": True})
        self.assertEqual(response.status_code, 200)
        self.save.assert_called_once_with(self.graph)

    def test_investor_cannot_read_or_write_prediction_configuration(self):
        self.user["role"] = "investor"
        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(self.client, method)("/api/kol/forecast-config")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.get_json()["error"], "dav_required")
        self.load.assert_not_called()
        self.save.assert_not_called()

    def test_anonymous_access_requires_login(self):
        self.user = None
        for method in ("get", "post"):
            response = getattr(self.client, method)("/api/kol/forecast-config")
            self.assertEqual(response.status_code, 401)
        self.save.assert_not_called()

    def test_dav_still_cannot_access_admin_endpoints(self):
        for path in ("/api/admin/forecast-config", "/api/admin/site-config"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.get_json()["error"], "admin_required")

    def test_admin_can_use_both_configuration_endpoints(self):
        self.user["role"] = "admin"
        for path in ("/api/admin/forecast-config", "/api/kol/forecast-config"):
            for method in ("get", "post"):
                with self.subTest(path=path, method=method):
                    response = getattr(self.client, method)(path)
                    self.assertEqual(response.status_code, 200)

    def test_feature_switch_still_blocks_read_and_write(self):
        self.enabled.return_value = False
        for method in ("get", "post"):
            response = getattr(self.client, method)("/api/kol/forecast-config")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.get_json()["error"], "stock_forecast_disabled")
        self.save.assert_not_called()

    def test_workbench_uses_dav_endpoint_for_load_save_and_reset(self):
        source = (Path(__file__).resolve().parents[1] / "templates/kol_workbench.html").read_text(encoding="utf-8")
        self.assertEqual(source.count("fetch('/api/kol/forecast-config'"), 3)
        self.assertNotIn("fetch('/api/admin/forecast-config'", source)
