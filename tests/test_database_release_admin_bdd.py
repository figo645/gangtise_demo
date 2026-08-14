import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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

    def test_given_remaining_incremental_packages_when_admin_starts_release_then_the_service_uses_the_ordered_batch_runner(self):
        target = {"name": "staging", "db_name": "demo", "db_user": "postgres", "db_host": "127.0.0.1", "db_port": "5432", "db_password": "secret"}
        packages = [
            {"id": "database_release_packages/2026-08-14/v1.1.1", "date": "2026-08-14", "version": "v1.1.1", "type": "master_data"},
            {"id": "database_release_packages/2026-08-14/v1.1.0", "date": "2026-08-14", "version": "v1.1.0", "type": "schema"},
        ]
        with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(database_release_services, "list_database_release_packages", return_value=packages), patch.object(database_release_services, "_start_job", return_value={"status": "queued", "target": "staging"}) as start_job:
            database_release_services.start_database_release("staging", package_id="__pending__")
        command = start_job.call_args.args[1]
        plan = start_job.call_args.kwargs["package_plan"]
        self.assertEqual(command[0], str(database_release_services.PACKAGE_BATCH_SCRIPT))
        self.assertEqual([item["version"] for item in plan], ["v1.1.0", "v1.1.1"])

    def test_given_incremental_runner_log_when_a_package_starts_or_finishes_then_job_progress_is_updated(self):
        with patch.object(database_release_services, "_set_job") as set_job:
            database_release_services._update_release_progress_from_log("==> [2/4] 开始增量包：database_release_packages/2026-08-14/v1.1.1")
            database_release_services._update_release_progress_from_log("==> [2/4] 增量包完成")
        self.assertEqual(set_job.call_count, 2)
        self.assertEqual(set_job.call_args_list[0].kwargs["progress"]["completed_steps"], 1)
        self.assertEqual(set_job.call_args_list[1].kwargs["progress"]["completed_steps"], 2)
        self.assertEqual(set_job.call_args_list[1].kwargs["progress"]["total_steps"], 4)

    def test_given_incremental_schema_package_when_listing_release_packages_then_it_is_available_to_admin(self):
        packages = database_release_services.list_database_release_packages()
        schema_package = next((item for item in packages if item["id"] == "database_release_packages/2026-08-14/v1.1.0"), None)
        self.assertIsNotNone(schema_package)
        self.assertEqual(schema_package["type"], "schema")
        self.assertTrue((Path(database_release_services.ROOT) / schema_package["id"] / "schema.sql").exists())

    def test_given_no_release_history_when_reading_log_then_admin_sees_an_explicit_empty_state(self):
        original_state_file = database_release_services.RELEASE_STATE_FILE
        original_loaded = database_release_services._release_job_loaded
        original_job = dict(database_release_services._release_job)
        with TemporaryDirectory() as temp_dir:
            try:
                database_release_services.RELEASE_STATE_FILE = Path(temp_dir) / "last_job.json"
                database_release_services._release_job_loaded = False
                database_release_services._release_job.clear()
                database_release_services._release_job.update({"status": "idle", "id": "", "target": "", "operation": "", "log": "", "started_at": "", "finished_at": "", "returncode": None})
                self.assertIn("暂无发布或回滚任务日志", database_release_services.get_database_release_log())
            finally:
                database_release_services.RELEASE_STATE_FILE = original_state_file
                database_release_services._release_job_loaded = original_loaded
                database_release_services._release_job.clear()
                database_release_services._release_job.update(original_job)

    def test_given_queued_release_when_controller_restarts_then_last_log_and_interrupted_status_remain_visible(self):
        original_state_file = database_release_services.RELEASE_STATE_FILE
        original_loaded = database_release_services._release_job_loaded
        original_job = dict(database_release_services._release_job)
        with TemporaryDirectory() as temp_dir:
            try:
                state_file = Path(temp_dir) / "last_job.json"
                log_file = Path(temp_dir) / "admin_release_20260814.log"
                log_file.write_text("[controller] 任务已排队：release 20260814\n", encoding="utf-8")
                state_file.write_text('{"status":"running","id":"20260814","target":"production","operation":"release","log":"' + str(log_file) + '","started_at":"2026-08-14 10:00:00","finished_at":"","returncode":null}', encoding="utf-8")
                database_release_services.RELEASE_STATE_FILE = state_file
                database_release_services._release_job_loaded = False
                database_release_services._release_job.clear()
                database_release_services._release_job.update({"status": "idle", "id": "", "target": "", "operation": "", "log": "", "started_at": "", "finished_at": "", "returncode": None})
                job = database_release_services.get_database_release_job()
                self.assertEqual(job["status"], "failed")
                self.assertEqual(job["returncode"], -1)
                self.assertIn("控制器在任务执行期间重启", database_release_services.get_database_release_log())
            finally:
                database_release_services.RELEASE_STATE_FILE = original_state_file
                database_release_services._release_job_loaded = original_loaded
                database_release_services._release_job.clear()
                database_release_services._release_job.update(original_job)

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
        self.assertIn('id="admin-database-release-staging"', html)
        self.assertIn('id="admin-database-release-production"', html)
        self.assertIn("await loadAdminDatabaseReleaseLog();", html)
        self.assertIn("全部剩余增量（推荐，已执行自动跳过）", html)
        self.assertIn("实时进度", html)
        self.assertIn("创建数据库发布任务", html)
        self.assertIn('id="admin-database-release-password-modal"', html)
        self.assertIn("confirmAdminDatabaseReleasePassword", html)

    def test_given_admin_first_load_when_non_visible_analytics_are_slow_then_shell_renders_without_waiting_for_them(self):
        with patch("src.web.pages.get_access_summary", side_effect=AssertionError("access must be lazy")), patch(
            "src.web.pages.build_indicator_hub", side_effect=AssertionError("indicator must be lazy")
        ), patch("src.web.pages.build_admin_task_center_payload", side_effect=AssertionError("tasks must be lazy")), patch(
            "src.web.pages.build_admin_token_usage_payload", side_effect=AssertionError("token usage must be lazy")
        ):
            response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("window.ADMIN_INDICATOR_HUB", html)
        self.assertIn("refreshAdminIndicatorHub(false).catch", html)
        self.assertIn("if (name === 'users')", html)

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

    def test_given_admin_when_release_start_fails_then_api_returns_a_machine_readable_failure_for_the_log_panel(self):
        with self.client.session_transaction() as current_session:
            current_session[api_core.DATABASE_RELEASE_UNLOCK_SESSION_KEY] = 4102444800
        with patch("src.web.api_core.start_database_release", side_effect=ValueError("database_release_target_invalid")):
            response = self.client.post("/api/admin/database-release", json={"target": "invalid", "package_id": "", "confirm_production": False})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "database_release_target_invalid")


if __name__ == "__main__":
    unittest.main()
