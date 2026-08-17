import unittest
from unittest.mock import patch

from src.domain import database_release_services
from tools import database_release_web


class DatabaseReleaseWebBddTest(unittest.TestCase):
    def setUp(self):
        database_release_web.app.config.update(TESTING=True, SECRET_KEY="database-release-web-bdd")
        self.client = database_release_web.app.test_client()
        database_release_web._unlock_failures.clear()

    @staticmethod
    def _target(name, host):
        return {
            "name": name,
            "db_name": "sprint_dashboard",
            "db_user": "postgres",
            "db_host": host,
            "db_port": "5432",
            "db_password": f"{name}-secret",
        }

    def _csrf_token(self):
        self.client.get("/")
        with self.client.session_transaction() as current_session:
            return current_session["data_import_csrf_token"]

    def test_given_distinct_production_and_staging_when_sync_starts_then_only_staging_is_the_target(self):
        production = self._target("production", "production.example")
        staging = self._target("staging", "staging.example")
        with patch.object(
            database_release_services,
            "get_database_release_target",
            side_effect=lambda name: production if name == "production" else staging,
        ), patch.object(
            database_release_services,
            "_start_job",
            return_value={"status": "queued", "target": "staging"},
        ) as start_job:
            result = database_release_services.start_production_to_staging_sync()

        self.assertEqual(result["target"], "staging")
        self.assertEqual(start_job.call_args.args[0], staging)
        self.assertEqual(start_job.call_args.args[1], [str(database_release_services.PRODUCTION_TO_STAGING_SCRIPT)])
        self.assertEqual(start_job.call_args.args[2], "production_to_staging")
        private_env = start_job.call_args.kwargs["extra_env"]
        self.assertEqual(private_env["PRODUCTION_DB_HOST"], "production.example")
        self.assertEqual(private_env["CONFIRM_PRODUCTION_TO_STAGING_SYNC"], "YES")

    def test_given_the_same_database_for_production_and_staging_when_sync_starts_then_the_service_rejects_it(self):
        shared = self._target("production", "shared.example")
        staging = {**shared, "name": "staging"}
        with patch.object(
            database_release_services,
            "get_database_release_target",
            side_effect=lambda name: shared if name == "production" else staging,
        ):
            with self.assertRaisesRegex(ValueError, "production_and_staging_must_differ"):
                database_release_services.start_production_to_staging_sync()

    def test_given_locked_5051_console_when_production_to_staging_is_requested_then_operation_password_is_required(self):
        csrf = self._csrf_token()
        response = self.client.post(
            "/api/production-to-staging-sync",
            json={},
            headers={"X-Data-Import-CSRF-Token": csrf},
        )
        self.assertEqual(response.status_code, 423)
        self.assertEqual(response.get_json()["error"], "operation_password_required")

    def test_given_unlocked_5051_console_when_production_to_staging_is_requested_then_a_background_job_is_created(self):
        csrf = self._csrf_token()
        with patch.object(database_release_web, "_operation_password", return_value="536953"):
            unlock = self.client.post(
                "/api/unlock",
                json={"password": "536953"},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(unlock.status_code, 200)
        with patch.object(
            database_release_web,
            "start_production_to_staging_sync",
            return_value={"id": "sync_1", "status": "queued", "target": "staging"},
        ) as start_sync:
            response = self.client.post(
                "/api/production-to-staging-sync",
                json={},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()["job"]["target"], "staging")
        start_sync.assert_called_once_with()

    def test_given_5051_console_page_when_rendered_then_it_explains_the_fixed_direction_and_confirmation(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('/static/vendor/bootstrap.min.css', html)
        self.assertIn('实时执行进度', html)
        self.assertIn('ops-rollback-item', html)
        self.assertIn('list-group-item', html)
        self.assertIn('releasePlanHint', html)
        self.assertIn('loadReleasePlan()', html)
        self.assertIn('扫描本地差异', html)
        self.assertIn('生成待推送增量', html)
        self.assertIn('/api/delta-review', html)
        self.assertIn('/api/generate-delta', html)
        self.assertIn('/api/package-review', html)
        self.assertIn('/api/reviewed-release', html)
        self.assertIn('增量审核清单', html)
        self.assertIn("Production 覆盖 Staging", html)
        self.assertIn("一键导入 Production 到 Staging", html)
        self.assertIn("/api/production-to-staging-sync", html)
        self.assertIn("Production 只读", html)
        css_response = self.client.get("/static/vendor/bootstrap.min.css")
        js_response = self.client.get("/static/vendor/bootstrap.bundle.min.js")
        try:
            self.assertEqual(css_response.status_code, 200)
            self.assertEqual(js_response.status_code, 200)
        finally:
            css_response.close()
            js_response.close()

    def test_given_a_target_environment_when_5051_loads_increment_plan_then_it_returns_three_type_summary(self):
        plan = {
            "target": "staging",
            "packages": [],
            "summary": {
                "pending_total": 3,
                "applied_total": 1,
                "checksum_mismatch_total": 0,
                "by_type": {
                    "schema": {"pending": 1, "applied": 0, "checksum_mismatch": 0},
                    "master_data": {"pending": 1, "applied": 0, "checksum_mismatch": 0},
                    "data": {"pending": 1, "applied": 1, "checksum_mismatch": 0},
                },
            },
        }
        with patch.object(database_release_web, "get_database_release_package_plan", return_value=plan) as get_plan:
            response = self.client.get("/api/release-plan?target=staging")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["summary"]["by_type"]["schema"]["pending"], 1)
        get_plan.assert_called_once_with("staging")

    def test_given_target_environment_when_5051_scans_local_delta_then_the_safe_categories_are_returned_without_unlocking(self):
        scan = {
            "target": "staging",
            "report_path": ".deploy/database_diff.json",
            "summary": {"schema_difference_tables": 1, "data_difference_tables": 2},
            "safe_release_delta": {"schema": ["users"], "master_data": [], "business_data": [], "total": 1},
            "excluded_runtime_tables": ["access_logs"],
        }
        with patch.object(database_release_web, "scan_database_release_delta", return_value=scan) as scan_delta:
            response = self.client.get("/api/diff-scan?target=staging")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["safe_release_delta"]["total"], 1)
        scan_delta.assert_called_once_with("staging")

    def test_given_selected_delta_categories_when_5051_builds_a_visual_review_then_it_only_reads_the_requested_scope(self):
        review = {
            "target": "staging",
            "generated_at": "2026-08-17 21:00:00",
            "safe_release_delta": {"schema": ["users"], "master_data": [], "business_data": [], "total": 1},
            "summary": {"schema_difference_tables": 1},
            "sections": [{"type": "schema", "risk_level": "low", "changes": [{"table": "users", "action": "add_column"}], "blockers": [], "sql_preview": "ALTER TABLE users ADD COLUMN demo text;"}],
            "blockers": [],
            "can_generate": True,
            "requires_manual_review": False,
        }
        with patch.object(database_release_web, "review_database_release_delta", return_value=review) as build_review:
            response = self.client.get("/api/delta-review?target=staging&include_schema=true&include_master_data=false&include_runtime_data=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["sections"][0]["risk_level"], "low")
        build_review.assert_called_once_with("staging", include_schema=True, include_master_data=False, include_runtime_data=True)

    def test_given_locked_5051_console_when_importing_reviewed_packages_then_the_operation_password_is_required(self):
        csrf = self._csrf_token()
        response = self.client.post(
            "/api/reviewed-release",
            json={"target": "staging", "package_ids": ["database_release_packages/2026-08-17/v1.1.3"]},
            headers={"X-Data-Import-CSRF-Token": csrf},
        )
        self.assertEqual(response.status_code, 423)

    def test_given_unlocked_5051_console_when_importing_reviewed_packages_then_only_the_reviewed_package_ids_are_started(self):
        csrf = self._csrf_token()
        with patch.object(database_release_web, "_operation_password", return_value="536953"):
            self.client.post("/api/unlock", json={"password": "536953"}, headers={"X-Data-Import-CSRF-Token": csrf})
        package_ids = ["database_release_packages/2026-08-17/v1.1.3"]
        with patch.object(database_release_web, "start_database_release_packages", return_value={"id": "reviewed_1", "status": "queued", "target": "staging"}) as start_reviewed:
            response = self.client.post(
                "/api/reviewed-release",
                json={"target": "staging", "package_ids": package_ids},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 202)
        start_reviewed.assert_called_once_with("staging", package_ids=package_ids, confirm_production=False)

    def test_given_locked_5051_console_when_generating_delta_then_the_operation_password_is_required(self):
        csrf = self._csrf_token()
        response = self.client.post(
            "/api/generate-delta",
            json={"target": "staging", "include_schema": True, "include_master_data": True},
            headers={"X-Data-Import-CSRF-Token": csrf},
        )
        self.assertEqual(response.status_code, 423)
        self.assertEqual(response.get_json()["error"], "operation_password_required")

    def test_given_unlocked_5051_console_when_generating_delta_then_a_new_package_plan_is_returned_but_not_applied(self):
        csrf = self._csrf_token()
        with patch.object(database_release_web, "_operation_password", return_value="536953"):
            self.client.post("/api/unlock", json={"password": "536953"}, headers={"X-Data-Import-CSRF-Token": csrf})
        result = {
            "target": "staging",
            "report_path": ".deploy/database_diff.json",
            "generated_packages": [{"id": "database_release_packages/2026-08-17/v1.1.3", "version": "v1.1.3", "type": "master_data"}],
            "blockers": [],
            "safe_release_delta": {"schema": [], "master_data": ["indicator_definitions"], "business_data": [], "total": 1},
            "details": {"schema": [], "master_data": [{"table": "indicator_definitions", "upsert_rows": 1}], "runtime_data": []},
        }
        with patch.object(database_release_web, "generate_database_release_delta", return_value=result) as generate_delta:
            response = self.client.post(
                "/api/generate-delta",
                json={"target": "staging", "include_schema": True, "include_master_data": True, "include_runtime_data": False},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["generated_packages"][0]["version"], "v1.1.3")
        generate_delta.assert_called_once_with("staging", include_schema=True, include_master_data=True, include_runtime_data=False)

    def test_given_sync_shell_script_when_inspected_then_it_uses_a_temp_database_validation_and_cleanup_before_switching(self):
        content = database_release_services.PRODUCTION_TO_STAGING_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("CONFIRM_PRODUCTION_TO_STAGING_SYNC", content)
        self.assertIn("TEMP_DB", content)
        self.assertIn("Validating Production and Staging temporary database equivalence", content)
        self.assertIn("trap cleanup_temp ERR", content)
        self.assertIn("==> Switching Staging database", content)

    def test_given_target_specific_generated_package_when_the_runner_executes_then_the_target_marker_is_verified_and_bound_to_the_checksum(self):
        content = database_release_services.PACKAGE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"${DELTA_TARGET:-}"', content)
        self.assertIn("Package target does not match release target.", content)
        self.assertIn("DELTA_TARGET=%s", content)
