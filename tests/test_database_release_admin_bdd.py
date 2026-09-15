import unittest
from unittest.mock import patch

import app as app_entry
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

    def test_main_application_no_longer_exposes_database_release_control_plane(self):
        for path in (
            "/api/admin/database-release/overview",
            "/api/admin/database-release",
            "/api/admin/database-release/rollback",
            "/api/admin/database-release/simulations",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_service_accepts_only_full_release_package_marker(self):
        target = {"name": "staging", "db_name": "demo", "db_user": "postgres", "db_host": "127.0.0.1", "db_port": "5432", "db_password": "secret"}
        with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(
            database_release_services, "_start_job", return_value={"status": "queued", "target": "staging"}
        ) as start_job:
            result = database_release_services.start_database_release("staging", package_id="__full__")
        self.assertEqual(result["status"], "queued")
        self.assertEqual(start_job.call_args.args[1], [str(database_release_services.PREPARE_SCRIPT)])
        self.assertEqual(start_job.call_args.args[2], "full_release")

    def test_service_rejects_historical_incremental_package_execution(self):
        with self.assertRaisesRegex(ValueError, "database_release_incremental_disabled"):
            database_release_services.start_database_release("staging", package_id="database_release_packages/v1/data")

    def test_service_requires_explicit_production_to_staging_confirmation(self):
        with self.assertRaisesRegex(ValueError, "production_to_staging_confirmation_required"):
            database_release_services.start_production_to_staging_sync(confirm=False)

    def test_service_starts_guarded_production_to_staging_job(self):
        production = {"name": "production", "db_name": "prod", "db_user": "postgres", "db_host": "prod-db", "db_port": "5432", "db_password": "prod-secret"}
        staging = {"name": "staging", "db_name": "stage", "db_user": "postgres", "db_host": "stage-db", "db_port": "5432", "db_password": "stage-secret"}
        with patch.object(database_release_services, "get_database_release_target", side_effect=[production, staging]), patch.object(
            database_release_services, "_start_job", return_value={"status": "queued", "target": "staging"}
        ) as start_job:
            result = database_release_services.start_production_to_staging_sync(confirm=True)
        self.assertEqual(result["target"], "staging")
        self.assertEqual(start_job.call_args.args[1], [str(database_release_services.PRODUCTION_TO_STAGING_SCRIPT)])
        self.assertEqual(start_job.call_args.args[2], "production_to_staging")
        self.assertEqual(start_job.call_args.kwargs["extra_env"]["PRODUCTION_DB_HOST"], "prod-db")
        self.assertEqual(start_job.call_args.kwargs["extra_env"]["CONFIRM_PRODUCTION_TO_STAGING_SYNC"], "YES")

    def test_service_requires_explicit_staging_to_production_confirmation(self):
        with self.assertRaisesRegex(ValueError, "staging_to_production_confirmation_required"):
            database_release_services.start_staging_to_production_sync(confirm=False)

    def test_service_starts_guarded_staging_to_production_job(self):
        staging = {"name": "staging", "db_name": "stage", "db_user": "postgres", "db_host": "stage-db", "db_port": "5432", "db_password": "stage-secret"}
        production = {"name": "production", "db_name": "prod", "db_user": "postgres", "db_host": "prod-db", "db_port": "5432", "db_password": "prod-secret"}
        with patch.object(database_release_services, "get_database_release_target", side_effect=[staging, production]), patch.object(
            database_release_services, "_start_job", return_value={"status": "queued", "target": "production"}
        ) as start_job:
            result = database_release_services.start_staging_to_production_sync(confirm=True)
        self.assertEqual(result["target"], "production")
        self.assertEqual(start_job.call_args.args[1], [str(database_release_services.STAGING_TO_PRODUCTION_SCRIPT)])
        self.assertEqual(start_job.call_args.args[2], "staging_to_production")
        self.assertEqual(start_job.call_args.kwargs["extra_env"]["STAGING_DB_HOST"], "stage-db")
        self.assertEqual(start_job.call_args.kwargs["extra_env"]["CONFIRM_STAGING_TO_PRODUCTION_SYNC"], "YES")

    def test_service_starts_all_user_business_cleanup_without_deleting_accounts(self):
        target = {"name": "staging", "db_name": "demo", "db_user": "postgres", "db_host": "stage-db", "db_port": "5432", "db_password": "secret"}
        with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(
            database_release_services, "_start_job", return_value={"status": "queued", "target": "staging"}
        ) as start_job:
            result = database_release_services.start_user_data_cleanup(
                "staging",
                "all_user_business_data",
                usernames=[],
                confirmation="CLEAR ALL USER BUSINESS DATA",
            )
        self.assertEqual(result["status"], "queued")
        self.assertEqual(start_job.call_args.args[1], [str(database_release_services.USER_DATA_CLEANUP_SCRIPT)])
        self.assertEqual(start_job.call_args.args[2], "user_data_cleanup")
        self.assertEqual(start_job.call_args.kwargs["extra_env"]["USER_DATA_CLEANUP_MODE"], "all_user_business_data")
        self.assertEqual(start_job.call_args.kwargs["extra_env"]["USER_DATA_CLEANUP_USERNAMES"], "")

    def test_service_rejects_all_user_business_cleanup_without_confirmation(self):
        target = {"name": "staging", "db_name": "demo", "db_user": "postgres", "db_host": "stage-db", "db_port": "5432", "db_password": "secret"}
        with patch.object(database_release_services, "get_database_release_target", return_value=target):
            with self.assertRaisesRegex(ValueError, "user_data_cleanup_confirmation_required"):
                database_release_services.start_user_data_cleanup(
                    "staging", "all_user_business_data", usernames=[], confirmation="CLEAR ALL NON-ADMIN ACCOUNTS"
                )


if __name__ == "__main__":
    unittest.main()
