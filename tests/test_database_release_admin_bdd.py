import unittest
from unittest.mock import patch

import app as app_entry
import src.web.api_core as api_core
import src.web.hooks as web_hooks
from src.domain import database_release_services


class DatabaseReleaseAdminBddTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._original_is_authenticated = web_hooks.is_authenticated
        cls._original_current_user = web_hooks.get_current_authenticated_user
        web_hooks.is_authenticated = lambda: True
        web_hooks.get_current_authenticated_user = lambda: {"id": "bdd-admin", "role": "admin"}
        app_entry.app.config.update(TESTING=True)
        cls.client = app_entry.app.test_client()

    @classmethod
    def tearDownClass(cls):
        web_hooks.is_authenticated = cls._original_is_authenticated
        web_hooks.get_current_authenticated_user = cls._original_current_user

    def setUp(self):
        with self.client.session_transaction() as current_session:
            current_session.pop(api_core.DATABASE_RELEASE_UNLOCK_SESSION_KEY, None)

    def test_given_production_release_when_confirmation_is_missing_then_the_service_rejects_it(self):
        target = {"name": "production", "db_name": "demo", "db_user": "postgres", "db_host": "127.0.0.1", "db_port": "5432", "db_password": "secret"}
        with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(database_release_services, "list_database_release_packages", return_value=[]):
            with self.assertRaisesRegex(ValueError, "production_confirmation_required"):
                database_release_services.start_database_release("production", confirm_production=False)

    def test_given_allowlisted_release_when_admin_starts_it_then_the_service_creates_one_job(self):
        target = {"name": "staging", "db_name": "demo", "db_user": "postgres", "db_host": "127.0.0.1", "db_port": "5432", "db_password": "secret"}
        package = {"id": "2026-08-13/v1.2.0", "type": "data"}
        with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(database_release_services, "list_database_release_packages", return_value=[package]), patch.object(database_release_services, "_start_job", return_value={"status": "queued", "target": "staging"}) as start_job:
            result = database_release_services.start_database_release("staging", package_id=package["id"])
        self.assertEqual(result["status"], "queued")
        start_job.assert_called_once()

    def test_given_admin_when_loading_database_release_then_the_admin_api_and_page_are_available(self):
        overview = {
            "targets": [{"name": "staging", "label": "Staging", "host": "127.0.0.1", "database": "demo"}],
            "simulation_targets": [{"name": "local", "label": "本地开发库", "host": "127.0.0.1", "database": "demo"}],
            "packages": [],
            "job": {"status": "idle"},
        }
        with patch("src.web.api_core.build_database_release_overview", return_value=overview):
            response = self.client.get("/api/admin/database-release/overview")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(response.get_json()["targets"][0]["name"], "staging")

        page = self.client.get("/admin")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('data-section="database-release"', html)
        self.assertIn('id="section-database-release"', html)
        self.assertIn("loadAdminDatabaseRelease", html)
        self.assertIn('id="admin-database-release-password-modal"', html)
        self.assertIn("confirmAdminDatabaseReleasePassword", html)

    def test_given_admin_when_database_operation_is_locked_then_password_is_required_before_release(self):
        payload = {"target": "staging", "package_id": "", "confirm_production": False}
        with patch("src.web.api_core.start_database_release") as start_release:
            locked_requests = [
                ("post", "/api/admin/database-release", payload),
                ("post", "/api/admin/database-release/rollback", {"target": "staging", "backup_name": "backup"}),
                ("post", "/api/admin/database-release/simulations", {"target": "local", "tenant_slug": "laowang"}),
                ("delete", "/api/admin/database-release/simulations/sim_fans_laowang_1", {"target": "local"}),
            ]
            for method, path, body in locked_requests:
                locked_response = getattr(self.client, method)(path, json=body)
                self.assertEqual(locked_response.status_code, 423)
                self.assertEqual(locked_response.get_json()["error"], "database_release_password_required")
            start_release.assert_not_called()

            invalid_response = self.client.post("/api/admin/database-release/unlock", json={"password": "wrong"})
            self.assertEqual(invalid_response.status_code, 403)
            self.assertEqual(invalid_response.get_json()["error"], "database_release_password_invalid")

            unlock_response = self.client.post("/api/admin/database-release/unlock", json={"password": "536953"})
            self.assertEqual(unlock_response.status_code, 200)
            self.assertTrue(unlock_response.get_json()["operation_unlocked"])

            start_release.return_value = {"status": "queued", "target": "staging"}
            permitted_response = self.client.post("/api/admin/database-release", json=payload)
            self.assertEqual(permitted_response.status_code, 202)
            start_release.assert_called_once_with("staging", package_id="", confirm_production=False)


if __name__ == "__main__":
    unittest.main()
