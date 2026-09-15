import unittest
from unittest.mock import patch

import tools.database_release_web as database_release_web


class DatabaseReleaseWebBddTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database_release_web.app.config.update(TESTING=True)
        cls.client = database_release_web.app.test_client()

    def _csrf_token(self):
        response = self.client.get("/api/csrf")
        self.assertEqual(response.status_code, 200)
        return response.get_json()["csrf_token"]

    def test_console_exposes_only_full_migration_mode(self):
        response = self.client.get("/api/overview")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["mode"], "full_and_diff_migration")
        self.assertNotIn("packages", payload)

    def test_console_shows_production_to_staging_full_sync_action(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("生产 → Staging 全量同步", html)
        self.assertIn("/api/production-to-staging-sync", html)
        self.assertIn("Staging → Production 全量发布", html)
        self.assertIn("/api/staging-to-production-sync", html)
        self.assertIn("onclick=\"startStagingToProduction(this)\"", html)
        self.assertIn('class="release-actions-grid"', html)
        self.assertLess(html.index("全量迁移"), html.index("生产 → Staging 全量同步"))
        self.assertLess(html.index("生产 → Staging 全量同步"), html.index("Staging → Production 全量发布"))
        self.assertIn("class=\"rollback-table\"", html)
        self.assertIn("备份数据库", html)

    def test_full_release_script_normalizes_recursive_user_table_collation(self):
        script = (database_release_web.ROOT / "scripts" / "prepare_database_release.sh").read_text(encoding="utf-8")
        self.assertIn("'public.users'::text COLLATE \"C\"", script)
        self.assertIn("format('%I.%I', child_ns.nspname, child.relname)::text COLLATE \"C\"", script)
        self.assertIn("format('%I.%I', table_schema, table_name)::text COLLATE \"C\"", script)
        self.assertIn('SELECT DISTINCT discovered.table_name COLLATE "C"', script)
        self.assertIn('ORDER BY discovered.table_name COLLATE "C"', script)
        self.assertIn('${CURRENT_TARGET_QUERY[@]} -c "SELECT count(*) FROM ${table_name}"', script)
        self.assertIn('${TEMP_TARGET_EXEC[@]} -Atqc "SELECT count(*) FROM ${table_name}"', script)
        self.assertIn('trap cleanup_temp EXIT', script)
        self.assertIn('trap - EXIT INT TERM', script)

    def test_release_requires_csrf(self):
        response = self.client.post("/api/release", json={"target": "staging"})
        self.assertEqual(response.status_code, 403)

    def test_release_passes_full_migration_contract_to_service(self):
        csrf = self._csrf_token()
        with patch.object(
            database_release_web,
            "start_database_release",
            return_value={"id": "full_1", "status": "queued", "target": "staging"},
        ) as start_release:
            response = self.client.post(
                "/api/release",
                json={"target": "staging", "package_id": "__full__"},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 202)
        start_release.assert_called_once_with("staging", package_id="__full__", confirm_production=False)

    def test_production_release_requires_explicit_confirmation(self):
        csrf = self._csrf_token()
        with patch.object(
            database_release_web,
            "start_database_release",
            side_effect=ValueError("production_confirmation_required"),
        ):
            response = self.client.post(
                "/api/release",
                json={"target": "production", "package_id": "__full__", "confirm_production": False},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "production_confirmation_required")

    def test_incremental_and_simulation_endpoints_are_not_exposed(self):
        for path in ("/api/packages", "/api/incremental", "/api/simulations"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_production_to_staging_sync_requires_csrf_and_explicit_confirmation(self):
        response = self.client.post("/api/production-to-staging-sync", json={"confirm": True})
        self.assertEqual(response.status_code, 403)
        csrf = self._csrf_token()
        with patch.object(
            database_release_web,
            "start_production_to_staging_sync",
            return_value={"id": "prod_stage_1", "status": "queued", "target": "staging"},
        ) as start_sync:
            response = self.client.post(
                "/api/production-to-staging-sync",
                json={"confirm": True},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 202)
        start_sync.assert_called_once_with(confirm=True)

    def test_staging_to_production_sync_requires_csrf_and_explicit_confirmation(self):
        response = self.client.post("/api/staging-to-production-sync", json={"confirm": True})
        self.assertEqual(response.status_code, 403)
        csrf = self._csrf_token()
        with patch.object(
            database_release_web,
            "start_staging_to_production_sync",
            return_value={"id": "stage_prod_1", "status": "queued", "target": "production"},
        ) as start_sync:
            response = self.client.post(
                "/api/staging-to-production-sync",
                json={"confirm": True},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 202)
        start_sync.assert_called_once_with(confirm=True)

        with patch.object(
            database_release_web,
            "start_staging_to_production_sync",
            side_effect=ValueError("staging_to_production_confirmation_required"),
        ) as start_sync:
            response = self.client.post(
                "/api/staging-to-production-sync",
                json={"confirm": False},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 400)
        start_sync.assert_called_once_with(confirm=False)

    def test_user_business_cleanup_requires_csrf(self):
        response = self.client.post(
            "/api/user-data/cleanup",
            json={"target": "staging", "confirmation": "CLEAR ALL USER BUSINESS DATA"},
        )
        self.assertEqual(response.status_code, 403)

    def test_user_business_cleanup_requires_fixed_mode_and_confirmation(self):
        csrf = self._csrf_token()
        with patch.object(database_release_web, "start_user_data_cleanup") as start_cleanup:
            response = self.client.post(
                "/api/user-data/cleanup",
                json={"target": "staging", "mode": "all_non_admin_accounts", "confirmation": "DELETE ALL NON-ADMIN ACCOUNTS"},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 400)
        start_cleanup.assert_not_called()

        with patch.object(
            database_release_web,
            "start_user_data_cleanup",
            side_effect=ValueError("user_data_cleanup_confirmation_required"),
        ) as start_cleanup:
            response = self.client.post(
                "/api/user-data/cleanup",
                json={"target": "staging", "confirmation": "wrong"},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 400)
        start_cleanup.assert_called_once_with(
            "staging",
            "all_user_business_data",
            usernames=[],
            confirmation="wrong",
            confirm_production=False,
        )

    def test_user_business_cleanup_starts_backup_first_job(self):
        csrf = self._csrf_token()
        with patch.object(
            database_release_web,
            "start_user_data_cleanup",
            return_value={"id": "cleanup_1", "status": "queued", "target": "staging"},
        ) as start_cleanup:
            response = self.client.post(
                "/api/user-data/cleanup",
                json={"target": "staging", "confirmation": "CLEAR ALL USER BUSINESS DATA"},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 202)
        start_cleanup.assert_called_once_with(
            "staging",
            "all_user_business_data",
            usernames=[],
            confirmation="CLEAR ALL USER BUSINESS DATA",
            confirm_production=False,
        )

    def test_user_business_cleanup_console_and_script_preserve_accounts(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("清除全部用户业务数据", html)
        self.assertIn("CLEAR ALL USER BUSINESS DATA", html)
        self.assertIn("/api/user-data/backups", html)
        script = (database_release_web.ROOT / "scripts" / "cleanup_user_runtime_data.sh").read_text(encoding="utf-8")
        self.assertIn("all_user_business_data", script)
        self.assertIn("DELETE FROM access_logs", script)
        self.assertIn("DELETE FROM tenant_insight_drafts", script)
        self.assertIn("DELETE FROM users WHERE id IN (SELECT id FROM cleanup_users)", script)
        self.assertIn("setting_key LIKE 'h5_profile_settings:%'", script)

    def test_diff_scan_is_read_only_and_exposed_on_5051(self):
        with patch.object(
            database_release_web,
            "scan_database_release_delta",
            return_value={"target": "staging", "summary": {"data_difference_tables": 2}},
        ) as scan:
            response = self.client.get("/api/diff/scan?target=staging")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["scan"]["target"], "staging")
        scan.assert_called_once_with("staging")

    def test_diff_scan_returns_a_readable_error_when_audit_fails(self):
        with patch.object(
            database_release_web,
            "scan_database_release_delta",
            side_effect=RuntimeError("database_release_scan_failed: statement timeout"),
        ):
            response = self.client.get("/api/diff/scan?target=staging")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"ok": False, "error": "database_release_scan_failed: statement timeout"})

    def test_console_exposes_scan_busy_feedback(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="diffScan"', html)
        self.assertIn('id="refresh"', html)
        self.assertIn('onclick="refreshStatus(this)"', html)
        self.assertIn("正在连接目标数据库并计算差异摘要，请稍候...", html)
        self.assertIn("button.classList.add('is-loading')", html)
        self.assertIn("button.textContent='正在准备...'", html)
        self.assertIn("button.textContent='刷新中...'", html)
        self.assertIn("button.textContent='已刷新'", html)
        self.assertIn("button.textContent='刷新失败'", html)
        self.assertIn("button.is-pressed:not(:disabled)", html)
        self.assertIn("document.addEventListener('pointerdown'", html)
        self.assertIn("event.key==='Enter'||event.key===' '", html)
        self.assertIn("button.textContent='正在发布...'", html)
        self.assertIn("Production 发布中...", html)
        self.assertIn("button.setAttribute('aria-busy','true')", html)
        self.assertIn(">扫描并准备差异</button>", html)
        self.assertNotIn(">生成预览</button>", html)
        self.assertNotIn(">生成差异计划</button>", html)
        self.assertIn("diffRequest('/api/diff/generate',diffPayload())", html)
        self.assertIn("button.textContent='扫描并准备差异'", html)
        self.assertIn("button:not(:disabled):active", html)
        self.assertIn("button:focus-visible", html)
        self.assertNotIn('onclick="reviewDiff()', html)
        self.assertNotIn('onclick="generateDiff()', html)
        self.assertNotIn("function reviewDiff", html)
        self.assertNotIn("function generateDiff", html)
        self.assertIn("data-rollback-target", html)
        self.assertNotIn("onclick=\"requestRollback(\\'", html)

    def test_diff_generation_and_release_require_csrf_and_reviewed_plan(self):
        csrf = self._csrf_token()
        with patch.object(
            database_release_web,
            "generate_database_release_delta",
            return_value={
                "target": "staging",
                "report_path": ".deploy/diff.json",
                "diff_fingerprint": "fingerprint",
                "generated_packages": [{"id": "database_release_packages/2026-09-15/v1.0.0"}],
                "blockers": [],
            },
        ) as generate:
            response = self.client.post(
                "/api/diff/generate",
                json={"target": "staging", "include_schema": True, "include_master_data": True},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 201)
        generate.assert_called_once_with("staging", include_schema=True, include_master_data=True, include_runtime_data=False)

        with patch.object(
            database_release_web,
            "start_database_release_delta",
            return_value={"id": "delta_1", "status": "queued", "target": "staging"},
        ) as start_delta:
            response = self.client.post(
                "/api/diff/release",
                json={
                    "target": "staging",
                    "report_path": ".deploy/diff.json",
                    "diff_fingerprint": "fingerprint",
                    "package_ids": ["database_release_packages/2026-09-15/v1.0.0"],
                },
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 202)
        start_delta.assert_called_once_with(
            "staging", ".deploy/diff.json", "fingerprint", ["database_release_packages/2026-09-15/v1.0.0"], confirm_production=False,
        )


if __name__ == "__main__":
    unittest.main()
