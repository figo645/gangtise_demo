import unittest
import os
import shlex
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import app as app_entry
import src.web.api_core as api_core
import src.web.hooks as web_hooks
from src.domain import core_services
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

    def test_given_clear_confirmation_when_admin_starts_clear_then_the_allowlisted_clear_script_is_queued(self):
        target = {"name": "staging", "db_name": "demo", "db_user": "postgres", "db_host": "127.0.0.1", "db_port": "5432", "db_password": "secret"}
        with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(database_release_services, "_start_job", return_value={"status": "queued", "target": "staging"}) as start_job:
            result = database_release_services.start_database_clear("staging", confirmation="CLEAR STAGING")
        self.assertEqual(result["status"], "queued")
        self.assertEqual(start_job.call_args.args[1], [str(database_release_services.CLEAR_DATABASE_SCRIPT)])
        self.assertEqual(start_job.call_args.args[2], "clear_database")

    def test_given_clear_confirmation_when_production_confirmation_is_missing_then_clear_is_rejected(self):
        target = {"name": "production", "db_name": "demo", "db_user": "postgres", "db_host": "127.0.0.1", "db_port": "5432", "db_password": "secret"}
        with patch.object(database_release_services, "get_database_release_target", return_value=target):
            with self.assertRaisesRegex(ValueError, "production_confirmation_required"):
                database_release_services.start_database_clear("production", confirmation="CLEAR PRODUCTION")

    def test_given_debug_server_when_database_release_controller_is_integrated_then_reloader_is_off_by_default(self):
        with patch.dict(os.environ, {"DEBUG": "1"}, clear=True):
            options = app_entry.get_server_runtime_options()
        self.assertTrue(options["debug"])
        self.assertFalse(options["use_reloader"])

        with patch.dict(os.environ, {"DEBUG": "1"}, clear=True):
            self.assertFalse(core_services.is_werkzeug_reloader_parent())

        with patch.dict(os.environ, {"DEBUG": "1", "FLASK_USE_RELOADER": "1"}, clear=True):
            options = app_entry.get_server_runtime_options()
        self.assertTrue(options["use_reloader"])

        with patch.dict(os.environ, {"DEBUG": "1", "FLASK_USE_RELOADER": "1"}, clear=True):
            self.assertTrue(core_services.is_werkzeug_reloader_parent())

        with patch.dict(
            os.environ,
            {"DEBUG": "1", "FLASK_USE_RELOADER": "1", "WERKZEUG_RUN_MAIN": "true"},
            clear=True,
        ):
            self.assertFalse(core_services.is_werkzeug_reloader_parent())

    def test_given_allowlisted_release_when_admin_starts_it_then_the_service_creates_one_job(self):
        target = {"name": "staging", "db_name": "demo", "db_user": "postgres", "db_host": "127.0.0.1", "db_port": "5432", "db_password": "secret"}
        package = {"id": "2026-08-13/v1.2.0", "type": "data"}
        plan = {"summary": {"checksum_mismatch_total": 0, "baseline_verification_required": False}, "packages": [{**package, "status": "pending"}]}
        with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(database_release_services, "list_database_release_packages", return_value=[package]), patch.object(database_release_services, "get_database_release_package_plan", return_value=plan), patch.object(database_release_services, "_start_job", return_value={"status": "queued", "target": "staging"}) as start_job:
            result = database_release_services.start_database_release("staging", package_id=package["id"])
        self.assertEqual(result["status"], "queued")
        start_job.assert_called_once()

    def test_given_reviewed_pending_packages_when_starting_a_reviewed_release_then_only_that_exact_ordered_set_is_executed(self):
        target = {"name": "staging", "db_name": "demo", "db_user": "postgres", "db_host": "127.0.0.1", "db_port": "5432", "db_password": "secret"}
        packages = [
            {"id": "database_release_packages/2026-08-17/v1.1.4", "date": "2026-08-17", "version": "v1.1.4", "type": "schema"},
            {"id": "database_release_packages/2026-08-17/v1.1.5", "date": "2026-08-17", "version": "v1.1.5", "type": "data"},
            {"id": "database_release_packages/2026-08-17/v1.1.6", "date": "2026-08-17", "version": "v1.1.6", "type": "data"},
        ]
        plan = {"packages": [{**item, "status": "pending"} for item in packages]}
        requested = [packages[2]["id"], packages[0]["id"]]
        with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(database_release_services, "list_database_release_packages", return_value=packages), patch.object(database_release_services, "get_database_release_package_plan", return_value=plan), patch.object(database_release_services, "_start_job", return_value={"status": "queued", "target": "staging"}) as start_job:
            result = database_release_services.start_database_release_packages("staging", requested)
        self.assertEqual(result["status"], "queued")
        self.assertEqual(start_job.call_args.args[1][0], str(database_release_services.PACKAGE_BATCH_SCRIPT))
        self.assertEqual(start_job.call_args.kwargs["package_plan"], [plan["packages"][0], plan["packages"][2]])

    def test_given_runtime_data_review_when_rendering_review_metadata_then_it_is_marked_high_risk_and_requires_human_confirmation(self):
        review = database_release_services._database_release_review_section(
            "data", {"sql": "INSERT INTO users (id) VALUES (1);", "details": [{"table": "users", "upsert_rows": 1}], "blockers": []},
        )
        self.assertEqual(review["risk_level"], "high")
        self.assertEqual(review["statement_count"], 1)
        self.assertEqual(review["changes"][0]["table"], "users")

    def test_given_target_without_a_release_ledger_when_building_a_plan_then_historical_packages_are_unverified_not_pending(self):
        package = {"id": "database_release_packages/2026-08-14/v1.1.0", "date": "2026-08-14", "version": "v1.1.0", "type": "schema"}
        with patch.object(database_release_services, "_database_release_package_checksum", return_value="checksum"):
            plan = database_release_services._build_database_release_package_plan(
                {"name": "staging"}, [package], {}, ledger_initialized=False,
            )
        self.assertEqual(plan["packages"][0]["status"], "unverified")
        self.assertEqual(plan["summary"]["pending_total"], 0)
        self.assertTrue(plan["summary"]["baseline_verification_required"])

    def test_given_target_specific_delta_when_the_target_ledger_is_empty_then_only_that_new_delta_is_pending(self):
        package = {"id": "database_release_packages/2026-08-17/v1.1.3", "date": "2026-08-17", "version": "v1.1.3", "type": "master_data", "delta_target": "staging"}
        with patch.object(database_release_services, "_database_release_package_checksum", return_value="checksum"):
            plan = database_release_services._build_database_release_package_plan(
                {"name": "staging"}, [package], {}, ledger_initialized=False,
            )
        self.assertEqual(plan["packages"][0]["status"], "pending")
        self.assertEqual(plan["summary"]["pending_total"], 1)
        self.assertFalse(plan["summary"]["baseline_verification_required"])

    def test_given_only_target_specific_delta_in_the_ledger_when_rebuilding_the_plan_then_unrecorded_historical_packages_stay_unverified(self):
        historical = {"id": "database_release_packages/2026-08-14/v1.1.0", "date": "2026-08-14", "version": "v1.1.0", "type": "schema", "delta_target": ""}
        delta = {"id": "database_release_packages/2026-08-17/v1.1.3", "date": "2026-08-17", "version": "v1.1.3", "type": "data", "delta_target": "staging"}
        with patch.object(database_release_services, "_database_release_package_checksum", side_effect=lambda item: item["version"]):
            plan = database_release_services._build_database_release_package_plan(
                {"name": "staging"}, [historical, delta], {"v1.1.3": "v1.1.3"}, ledger_initialized=True,
            )
        statuses = {item["version"]: item["status"] for item in plan["packages"]}
        self.assertEqual(statuses["v1.1.0"], "unverified")
        self.assertEqual(statuses["v1.1.3"], "applied")
        self.assertEqual(plan["summary"]["pending_total"], 0)

    def test_given_generated_package_title_with_spaces_when_the_runner_sources_release_env_then_the_title_remains_one_value(self):
        original_packages_dir = database_release_services.PACKAGES_DIR
        with TemporaryDirectory(dir=database_release_services.ROOT) as temp_dir:
            try:
                database_release_services.PACKAGES_DIR = Path(temp_dir) / "packages"
                package = database_release_services._write_generated_database_release_package(
                    "data", "v9.9.9", "本地到 staging 业务运行数据增量", "SELECT 1;", "staging",
                )
                env_path = database_release_services.ROOT / package["id"] / "release.env"
                result = subprocess.run(
                    ["bash", "-c", f"source {shlex.quote(str(env_path))}; printf '%s' \"$TITLE\""],
                    check=True, capture_output=True, text=True,
                )
                self.assertEqual(result.stdout, "本地到 staging 业务运行数据增量")
                self.assertIn("TITLE='", env_path.read_text(encoding="utf-8"))
            finally:
                database_release_services.PACKAGES_DIR = original_packages_dir

    def test_given_only_archived_historical_packages_when_admin_starts_remaining_incrementals_then_the_service_reports_no_pending_delta(self):
        target = {"name": "staging", "db_name": "demo", "db_user": "postgres", "db_host": "127.0.0.1", "db_port": "5432", "db_password": "secret"}
        package = {"id": "database_release_packages/2026-08-14/v1.1.0", "date": "2026-08-14", "version": "v1.1.0", "type": "schema"}
        plan = {"summary": {"checksum_mismatch_total": 0, "baseline_verification_required": True}, "packages": [{**package, "status": "unverified"}]}
        with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(database_release_services, "list_database_release_packages", return_value=[package]), patch.object(database_release_services, "get_database_release_package_plan", return_value=plan):
            with self.assertRaisesRegex(ValueError, "database_release_no_pending_packages"):
                database_release_services.start_database_release("staging", package_id="__pending__")

    def test_given_remaining_incremental_packages_when_admin_starts_release_then_the_service_uses_the_ordered_batch_runner(self):
        target = {"name": "staging", "db_name": "demo", "db_user": "postgres", "db_host": "127.0.0.1", "db_port": "5432", "db_password": "secret"}
        packages = [
            {"id": "database_release_packages/2026-08-14/v1.1.1", "date": "2026-08-14", "version": "v1.1.1", "type": "master_data"},
            {"id": "database_release_packages/2026-08-14/v1.1.0", "date": "2026-08-14", "version": "v1.1.0", "type": "schema"},
        ]
        release_plan = {"summary": {"checksum_mismatch_total": 0}, "packages": [{**item, "status": "pending"} for item in packages]}
        with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(database_release_services, "list_database_release_packages", return_value=packages), patch.object(database_release_services, "get_database_release_package_plan", return_value=release_plan), patch.object(database_release_services, "_start_job", return_value={"status": "queued", "target": "staging"}) as start_job:
            database_release_services.start_database_release("staging", package_id="__pending__")
        command = start_job.call_args.args[1]
        plan = start_job.call_args.kwargs["package_plan"]
        self.assertEqual(command[0], str(database_release_services.PACKAGE_BATCH_SCRIPT))
        self.assertEqual([item["version"] for item in plan], ["v1.1.0", "v1.1.1"])

    def test_given_production_pending_incrementals_when_admin_starts_release_then_the_direct_incremental_path_remains_available(self):
        target = {"name": "production", "db_name": "demo", "db_user": "postgres", "db_host": "127.0.0.1", "db_port": "5432", "db_password": "secret"}
        packages = [
            {"id": "database_release_packages/2026-08-17/v1.1.3", "date": "2026-08-17", "version": "v1.1.3", "type": "master_data"},
        ]
        release_plan = {"summary": {"checksum_mismatch_total": 0}, "packages": [{**item, "status": "pending"} for item in packages]}
        with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(database_release_services, "list_database_release_packages", return_value=packages), patch.object(database_release_services, "get_database_release_package_plan", return_value=release_plan), patch.object(database_release_services, "_start_job", return_value={"status": "queued", "target": "production"}) as start_job:
            database_release_services.start_database_release("production", package_id="__pending__", confirm_production=True)
        self.assertEqual(start_job.call_args.args[1][0], str(database_release_services.PACKAGE_BATCH_SCRIPT))
        self.assertEqual(start_job.call_args.kwargs["package_plan"][0]["id"], packages[0]["id"])

    def test_given_target_release_ledger_when_building_increment_plan_then_schema_master_data_and_business_data_are_classified(self):
        target = {"name": "staging"}
        packages = database_release_services.list_database_release_packages()
        schema_package = next(item for item in packages if item["type"] == "schema")
        master_package = next(item for item in packages if item["type"] == "master_data")
        data_package = next(item for item in packages if item["type"] == "data")
        plan = database_release_services._build_database_release_package_plan(
            target,
            [schema_package, master_package, data_package],
            {schema_package["version"]: database_release_services._database_release_package_checksum(schema_package)},
        )
        status_by_type = {item["type"]: item["status"] for item in plan["packages"]}
        self.assertEqual(status_by_type["schema"], "applied")
        self.assertEqual(status_by_type["master_data"], "pending")
        self.assertEqual(status_by_type["data"], "pending")
        self.assertEqual(plan["summary"]["by_type"]["schema"]["applied"], 1)
        self.assertEqual(plan["summary"]["by_type"]["master_data"]["pending"], 1)
        self.assertEqual(plan["summary"]["by_type"]["data"]["pending"], 1)

    def test_given_package_checksum_changed_after_target_release_when_building_increment_plan_then_it_is_blocked(self):
        package = next(item for item in database_release_services.list_database_release_packages() if item["type"] == "schema")
        plan = database_release_services._build_database_release_package_plan(
            {"name": "staging"}, [package], {package["version"]: "different-checksum"}
        )
        self.assertEqual(plan["packages"][0]["status"], "checksum_mismatch")
        self.assertEqual(plan["summary"]["checksum_mismatch_total"], 1)

    def test_given_checksum_mismatch_when_starting_remaining_incrementals_then_the_service_requires_a_new_package_version(self):
        target = {"name": "staging", "db_name": "demo", "db_user": "postgres", "db_host": "127.0.0.1", "db_port": "5432", "db_password": "secret"}
        package = {"id": "database_release_packages/2026-08-14/v1.1.0", "date": "2026-08-14", "version": "v1.1.0", "type": "schema"}
        with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(database_release_services, "list_database_release_packages", return_value=[package]), patch.object(database_release_services, "get_database_release_package_plan", return_value={"summary": {"checksum_mismatch_total": 1}, "packages": [{**package, "status": "checksum_mismatch"}]}):
            with self.assertRaisesRegex(ValueError, "database_release_package_checksum_mismatch"):
                database_release_services.start_database_release("staging", package_id="__pending__")

    def test_given_incremental_runner_log_when_a_package_starts_or_finishes_then_job_progress_is_updated(self):
        with patch.object(database_release_services, "_set_job") as set_job:
            database_release_services._update_release_progress_from_log("==> [2/4] 开始增量包：database_release_packages/2026-08-14/v1.1.1")
            database_release_services._update_release_progress_from_log("==> [2/4] 增量包完成")
        self.assertEqual(set_job.call_count, 2)
        self.assertEqual(set_job.call_args_list[0].kwargs["progress"]["completed_steps"], 1)
        self.assertEqual(set_job.call_args_list[1].kwargs["progress"]["completed_steps"], 2)
        self.assertEqual(set_job.call_args_list[1].kwargs["progress"]["total_steps"], 4)

    def test_given_clear_runner_log_when_database_is_switched_then_cancellation_is_disabled(self):
        with patch.object(database_release_services, "_record_release_event"), patch.object(database_release_services, "_set_job") as set_job:
            database_release_services._update_release_progress_from_log("==> Terminating connections to sprint_dashboard")
        self.assertFalse(set_job.call_args.kwargs["cancellable"])
        self.assertEqual(set_job.call_args.kwargs["progress"]["state"], "switching")

    def test_given_release_stage_output_when_worker_reports_each_step_then_durable_timeline_events_are_available(self):
        original_state_file = database_release_services.RELEASE_STATE_FILE
        original_loaded = database_release_services._release_job_loaded
        original_job = dict(database_release_services._release_job)
        with TemporaryDirectory() as temp_dir:
            try:
                database_release_services.RELEASE_STATE_FILE = Path(temp_dir) / "last_job.json"
                database_release_services._release_job_loaded = True
                database_release_services._release_job.clear()
                database_release_services._release_job.update({
                    "status": "running", "id": "release_progress", "target": "staging", "operation": "release",
                    "log": "", "started_at": "2026-08-14 12:00:00", "finished_at": "", "returncode": None,
                    "pid": 4242, "package_plan": [], "progress": {}, "events": [], "cancel_requested": False,
                    "cancel_requested_at": "", "cancellable": True,
                })
                database_release_services._update_release_progress_from_log("==> [preflight] Checking staging PostgreSQL 127.0.0.1:5432 (timeout 8s)")
                database_release_services._update_release_progress_from_log("==> Export complete: 2048 bytes · SHA256 abc123")
                database_release_services._update_release_progress_from_log("Validated: tables=12 migrations=3 market_rows=4 sectors=2 indices=2")
                job = database_release_services.get_database_release_job()
                self.assertEqual(job["progress"]["state"], "validating")
                self.assertEqual(len(job["events"]), 3)
                self.assertEqual(job["events"][0]["stage"], "stage")
                self.assertIn("Export complete", job["events"][1]["detail"])
                self.assertEqual(job["events"][2]["status"], "succeeded")
                self.assertTrue(database_release_services.RELEASE_STATE_FILE.exists())
            finally:
                database_release_services.RELEASE_STATE_FILE = original_state_file
                database_release_services._release_job_loaded = original_loaded
                database_release_services._release_job.clear()
                database_release_services._release_job.update(original_job)

    def test_given_running_release_when_admin_cancels_then_the_release_process_group_is_terminated_and_job_enters_cancelling(self):
        original_state_file = database_release_services.RELEASE_STATE_FILE
        original_loaded = database_release_services._release_job_loaded
        original_job = dict(database_release_services._release_job)
        with TemporaryDirectory() as temp_dir:
            try:
                log_file = Path(temp_dir) / "release.log"
                database_release_services.RELEASE_STATE_FILE = Path(temp_dir) / "last_job.json"
                database_release_services._release_job_loaded = True
                database_release_services._release_job.clear()
                database_release_services._release_job.update({
                    "status": "running", "id": "release_1", "target": "production", "operation": "release",
                    "log": str(log_file), "started_at": "2026-08-14 12:00:00", "finished_at": "", "returncode": None,
                    "pid": 4242, "package_plan": [], "progress": {"state": "running_step"},
                    "cancel_requested": False, "cancel_requested_at": "", "cancellable": True,
                })
                with patch.object(database_release_services, "_terminate_release_process_group") as terminate:
                    job = database_release_services.cancel_database_release("release_1")
                self.assertEqual(job["status"], "cancelling")
                self.assertTrue(job["cancel_requested"])
                terminate.assert_called_once_with(4242)
                self.assertIn("管理员请求取消任务", log_file.read_text(encoding="utf-8"))
            finally:
                database_release_services.RELEASE_STATE_FILE = original_state_file
                database_release_services._release_job_loaded = original_loaded
                database_release_services._release_job.clear()
                database_release_services._release_job.update(original_job)

    def test_given_full_release_in_switching_phase_when_admin_cancels_then_the_service_rejects_the_unsafe_request(self):
        original_loaded = database_release_services._release_job_loaded
        original_job = dict(database_release_services._release_job)
        try:
            database_release_services._release_job_loaded = True
            database_release_services._release_job.clear()
            database_release_services._release_job.update({
                "status": "running", "id": "release_switch", "target": "production", "operation": "release",
                "log": "", "started_at": "", "finished_at": "", "returncode": None, "pid": 4242,
                "package_plan": [], "progress": {"state": "switching"}, "cancel_requested": False,
                "cancel_requested_at": "", "cancellable": False,
            })
            with self.assertRaisesRegex(ValueError, "database_release_job_not_cancellable"):
                database_release_services.cancel_database_release("release_switch")
        finally:
            database_release_services._release_job_loaded = original_loaded
            database_release_services._release_job.clear()
            database_release_services._release_job.update(original_job)

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

    def test_given_admin_when_loading_database_release_then_only_the_compatibility_api_remains_available(self):
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
        self.assertNotIn('data-section="database-release"', html)
        self.assertNotIn('id="section-database-release"', html)
        self.assertNotIn('id="admin-database-release-password-modal"', html)

    def test_given_application_database_auth_is_unavailable_when_database_release_api_is_called_then_the_release_password_gate_remains_reachable(self):
        original_is_authenticated = web_hooks.is_authenticated
        try:
            web_hooks.is_authenticated = lambda: False
            response = self.client.post("/api/admin/database-release/unlock", json={"password": "wrong"})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.get_json()["error"], "database_release_password_invalid")
        finally:
            web_hooks.is_authenticated = original_is_authenticated

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
                ("post", "/api/admin/database-release/cancel", {"job_id": "release_1"}),
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

    def test_given_unlocked_admin_when_cancelling_release_then_cancel_api_returns_the_updated_job(self):
        with self.client.session_transaction() as current_session:
            current_session[api_core.DATABASE_RELEASE_UNLOCK_SESSION_KEY] = 4102444800
        expected = {"status": "cancelling", "id": "release_1"}
        with patch("src.web.api_core.cancel_database_release", return_value=expected) as cancel_release:
            response = self.client.post("/api/admin/database-release/cancel", json={"job_id": "release_1"})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()["job"], expected)
        cancel_release.assert_called_once_with("release_1")

    def test_given_admin_when_release_start_fails_then_api_returns_a_machine_readable_failure_for_the_log_panel(self):
        with self.client.session_transaction() as current_session:
            current_session[api_core.DATABASE_RELEASE_UNLOCK_SESSION_KEY] = 4102444800
        with patch("src.web.api_core.start_database_release", side_effect=ValueError("database_release_target_invalid")):
            response = self.client.post("/api/admin/database-release", json={"target": "invalid", "package_id": "", "confirm_production": False})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "database_release_target_invalid")

    def test_given_release_job_is_already_running_when_start_is_retried_then_api_returns_conflict(self):
        with self.client.session_transaction() as current_session:
            current_session[api_core.DATABASE_RELEASE_UNLOCK_SESSION_KEY] = 4102444800
        with patch("src.web.api_core.start_database_release", side_effect=ValueError("database_release_job_running")):
            response = self.client.post(
                "/api/admin/database-release",
                json={"target": "staging", "package_id": "", "confirm_production": False},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"], "database_release_job_running")

    def test_given_unexpected_task_creation_error_when_admin_starts_release_then_the_api_returns_json_instead_of_dropping_the_request(self):
        with self.client.session_transaction() as current_session:
            current_session[api_core.DATABASE_RELEASE_UNLOCK_SESSION_KEY] = 4102444800
        with patch("src.web.api_core.start_database_release", side_effect=OSError("state file unavailable")):
            response = self.client.post("/api/admin/database-release", json={"target": "staging", "package_id": "", "confirm_production": False})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["error"], "database_release_task_create_failed")
        self.assertIn("state file unavailable", response.get_json()["detail"])


if __name__ == "__main__":
    unittest.main()
