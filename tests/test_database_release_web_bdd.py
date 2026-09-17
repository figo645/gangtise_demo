import unittest
import inspect
from unittest.mock import patch

import psycopg2
import src.domain.database_release_services as database_release_services
import tools.database_release_web as database_release_web
import tools.audit_database_release_diff as database_release_diff


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
        self.assertEqual(payload["mode"], "full_and_schema_safe_release")
        self.assertNotIn("packages", payload)

    def test_overview_schema_summary_is_read_only_and_target_resilient(self):
        summary = {
            "mode": "read_only_schema_only",
            "source": {"label": "本地开发库", "host": "127.0.0.1", "database": "sprint_dashboard"},
            "targets": [
                {"target": "staging", "label": "Staging", "available": True, "summary": {"structural_difference_count": 3}},
                {"target": "production", "label": "Production", "available": False, "error": "目标环境暂不可用：too many clients", "summary": {}},
            ],
        }
        with patch.object(database_release_web, "get_database_release_schema_summary", return_value=summary) as get_summary:
            response = self.client.get("/api/overview/schema-summary")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["summary"]["mode"], "read_only_schema_only")
        self.assertEqual(payload["summary"]["targets"][1]["available"], False)
        self.assertIn("too many clients", payload["summary"]["targets"][1]["error"])
        get_summary.assert_called_once_with()

    def test_schema_summary_uses_schema_only_audit_and_isolates_target_failure(self):
        local_target = {"db_host": "127.0.0.1", "db_name": "sprint_dashboard"}
        targets = {
            "staging": {"name": "staging", "db_host": "staging.example", "db_name": "sprint_dashboard"},
            "production": {"name": "production", "db_host": "production.example", "db_name": "sprint_dashboard"},
        }
        report = {
            "generated_at": "2026-09-17 12:00:00",
            "summary": {
                "local_table_count": 40, "target_table_count": 38,
                "local_only_tables": 1, "target_only_tables": 2, "schema_difference_tables": 3,
                "migration_local_only": 4, "migration_target_only": 5, "migration_checksum_mismatch": 6,
            },
            "schema_migration_difference": {"local_only": ["a"], "target_only": ["b"], "checksum_mismatch": ["c"]},
        }
        with patch("src.domain.core_services.get_local_app_db_target", return_value=local_target), \
             patch.object(database_release_services, "get_database_release_target", side_effect=lambda name: targets[name]), \
             patch.object(database_release_diff, "audit_schema_only", side_effect=[report, psycopg2.OperationalError("too many clients")]) as audit:
            result = database_release_services.get_database_release_schema_summary()
        self.assertEqual(result["mode"], "read_only_schema_only")
        self.assertEqual(result["targets"][0]["summary"]["structural_difference_count"], 21)
        self.assertTrue(result["targets"][0]["available"])
        self.assertFalse(result["targets"][1]["available"])
        self.assertIn("too many clients", result["targets"][1]["error"])
        self.assertEqual(audit.call_count, 2)

    def test_console_keeps_statistics_in_overview_and_monitoring_in_full_release(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="overview-dashboard"', html)
        self.assertIn("本地与目标环境结构差异", html)
        self.assertIn("/api/overview/schema-summary", html)
        self.assertIn("consolePages.overview=[document.getElementById('stats'),document.getElementById('overview-dashboard')]", html)
        self.assertIn("consolePages['full-release']=[document.querySelector('.release-actions-grid'),monitor]", html)
        self.assertIn("consolePages.operations=[document.querySelector('.rollback-panel')]", html)
        self.assertNotIn("consolePages.overview=[document.querySelector('.release-actions-grid'),monitor", html)
        self.assertIn("<h2>任务进度</h2>", html)
        self.assertIn("<h2>迁移日志</h2>", html)

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

    def test_generic_diff_endpoints_are_not_exposed(self):
        for path in ("/api/diff/scan", "/api/diff/review", "/api/diff/generate", "/api/diff/release"):
            with self.subTest(path=path):
                response = self.client.post(path) if path != "/api/diff/scan" else self.client.get(path)
                self.assertEqual(response.status_code, 404)

    def test_schema_only_scan_is_exposed_as_a_separate_read_only_path(self):
        with patch.object(
            database_release_web,
            "scan_database_release_schema",
            return_value={"target": "production", "mode": "read_only_schema_only", "summary": {"data_difference_tables": 0}},
        ) as scan:
            response = self.client.get("/api/schema-diff/scan?target=production")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["scan"]["mode"], "read_only_schema_only")
        scan.assert_called_once_with("production")

    def test_final_schema_equivalence_is_exposed_as_a_read_only_workflow_step(self):
        verification = {"ok": True, "mode": "final_schema_equivalence", "differences": []}
        with patch.object(database_release_web, "verify_database_release_schema", return_value=verification) as verify:
            response = self.client.get("/api/schema-diff/verify?target=production")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["verification"]["ok"])
        verify.assert_called_once_with("production")

    def test_schema_inventory_exposes_data_ownership_in_chinese(self):
        with patch.object(
            database_release_web,
            "get_database_table_inventory",
            return_value={
                "target": "staging",
                "counts": {"配置数据": 1, "用户生成数据": 2},
                "rows": [{"table_name": "users", "category_label": "用户账户数据", "status": "两边都有"}],
            },
        ) as inventory:
            response = self.client.get("/api/schema-inventory?target=staging")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["inventory"]["rows"][0]["category_label"], "用户账户数据")
        inventory.assert_called_once_with("staging")

    def test_schema_only_generation_and_release_keep_a_separate_contract(self):
        csrf = self._csrf_token()
        with patch.object(
            database_release_web,
            "generate_database_release_schema",
            return_value={
                "target": "staging",
                "mode": "schema_only",
                "report_path": ".deploy/schema-diff.json",
                "diff_fingerprint": "schema-fingerprint",
                "generated_packages": [{"id": "database_release_packages/2026-09-17/v1.0.1"}],
                "blockers": [],
            },
        ) as generate:
            response = self.client.post(
                "/api/schema-diff/generate",
                json={"target": "staging"},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 201)
        generate.assert_called_once_with("staging")

        response = self.client.post(
            "/api/schema-diff/release",
            json={"target": "staging"},
            headers={"X-Data-Import-CSRF-Token": csrf},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "database_release_schema_review_confirmation_required")

        with patch.object(
            database_release_web,
            "start_database_release_delta",
            return_value={"id": "schema_1", "status": "queued", "target": "staging"},
        ) as start_delta:
            response = self.client.post(
                "/api/schema-diff/release",
                json={
                    "target": "staging",
                    "report_path": ".deploy/schema-diff.json",
                    "diff_fingerprint": "schema-fingerprint",
                    "package_ids": ["database_release_packages/2026-09-17/v1.0.1"],
                    "review_confirmed": True,
                },
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 202)
        start_delta.assert_called_once_with(
            "staging", ".deploy/schema-diff.json", "schema-fingerprint",
            ["database_release_packages/2026-09-17/v1.0.1"],
            confirm_production=False, schema_only=True,
        )

    def test_local_migration_ledger_repair_requires_confirmation_and_never_targets_production(self):
        csrf = self._csrf_token()
        response = self.client.post(
            "/api/local-migration-ledger/repair",
            json={"confirm": False},
            headers={"X-Data-Import-CSRF-Token": csrf},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "database_release_local_migration_repair_confirmation_required")
        with patch.object(
            database_release_web,
            "start_local_migration_ledger_repair",
            return_value={"id": "local_migrations_1", "status": "queued", "target": "local"},
        ) as repair:
            response = self.client.post(
                "/api/local-migration-ledger/repair",
                json={"confirm": True},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.get_json()["job"]["target"], "local")
        repair.assert_called_once_with()

    def test_local_migration_repair_uses_the_canonical_local_updater(self):
        source = inspect.getsource(database_release_services.start_local_migration_ledger_repair)
        self.assertIn('get_database_release_target("local")', source)
        self.assertIn("POSTGRES_UPDATES_SCRIPT", source)
        self.assertIn('"local_migration_repair"', source)
        updater = (database_release_web.ROOT / "scripts" / "apply_postgres_updates.sh").read_text(encoding="utf-8")
        self.assertIn("113|114|115|122|123|124|125|126|127|128|129|131|132", updater)

    def test_migration_ledger_reconciliation_requires_review_and_has_a_separate_contract(self):
        csrf = self._csrf_token()
        plan = {
            "target": "staging", "mode": "migration_ledger_reconciliation",
            "report_path": ".deploy/ledger-plan.json", "fingerprint": "ledger-fingerprint",
            "target_insertions": [{"migration_name": "131_review.sql"}], "local_insertions": [], "blockers": [],
        }
        with patch.object(
            database_release_web, "generate_database_release_migration_ledger_reconciliation", return_value=plan,
        ) as generate:
            response = self.client.post(
                "/api/schema-migration-ledger/generate", json={"target": "staging"},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["plan"]["mode"], "migration_ledger_reconciliation")
        generate.assert_called_once_with("staging")

        response = self.client.post(
            "/api/schema-migration-ledger/apply", json={"target": "staging"},
            headers={"X-Data-Import-CSRF-Token": csrf},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "database_release_migration_ledger_review_confirmation_required")

        with patch.object(
            database_release_web, "apply_database_release_migration_ledger_reconciliation",
            return_value={"target": "staging", "target_inserted": 1, "local_inserted": 0, "verification": {"ok": True}},
        ) as apply:
            response = self.client.post(
                "/api/schema-migration-ledger/apply",
                json={"target": "staging", "report_path": ".deploy/ledger-plan.json", "fingerprint": "ledger-fingerprint", "review_confirmed": True},
                headers={"X-Data-Import-CSRF-Token": csrf},
            )
        self.assertEqual(response.status_code, 200)
        apply.assert_called_once_with("staging", ".deploy/ledger-plan.json", "ledger-fingerprint", confirm_production=False)

    def test_schema_upgrade_console_and_final_runner_have_safety_guards(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("生产结构安全升级", html)
        self.assertIn("表结构与分层", html)
        self.assertIn("console-sidebar", html)
        self.assertIn("schema-inventory", html)
        self.assertIn("function copyReleaseTargets(targetId)", html)
        self.assertIn("const selected=target.value", html)
        self.assertIn("target.value=selected", html)
        self.assertIn("目标环境已变更，请重新比较并生成结构包", html)
        self.assertIn("正在读取 '+targetLabel+' 的结构元数据", html)
        self.assertIn("/api/schema-diff/scan", html)
        self.assertIn("/api/schema-diff/generate", html)
        self.assertIn("/api/schema-diff/release", html)
        self.assertIn("/api/schema-diff/verify", html)
        self.assertIn('id="schemaDiffReview"', html)
        self.assertIn("差异审核", html)
        self.assertIn("与表结构与数据分层的交叉核对", html)
        self.assertIn("schemaDiffReviewConfirmed", html)
        self.assertIn("review_confirmed:true", html)
        self.assertIn("确认审核后应用", html)
        self.assertIn("无需应用结构包，全部步骤已核验通过。", html)
        self.assertIn("没有新增结构包，但迁移账本尚未等价", html)
        self.assertIn("无需用户确认", html)
        self.assertIn("无需应用", html)
        self.assertIn("生成迁移账本对齐计划", html)
        self.assertIn("迁移账本对齐计划", html)
        self.assertIn("需人工核验的非结构迁移", html)
        self.assertIn("/api/schema-migration-ledger/generate", html)
        self.assertIn("/api/schema-migration-ledger/apply", html)
        self.assertIn("function hasBlockingMigrationLedgerDrift()", html)
        self.assertIn("const strict=migration.strict_schema||migration", html)
        self.assertIn("存在需要处理的结构迁移账本差异", html)
        self.assertIn("仅向 schema_migrations 插入缺失账本记录", inspect.getsource(database_release_services._build_migration_ledger_reconciliation))
        ledger_writer = inspect.getsource(database_release_services._insert_migration_ledger_baseline_rows)
        self.assertIn("ON CONFLICT (migration_name) DO NOTHING", ledger_writer)
        self.assertNotIn("DELETE FROM", ledger_writer)
        self.assertNotIn("UPDATE schema_migrations", ledger_writer)
        reconciliation = inspect.getsource(database_release_services._build_migration_ledger_reconciliation)
        self.assertIn('row["migration_scope"] == "schema"', reconciliation)
        self.assertIn("non_schema_migration_ledger_requires_manual_verification", reconciliation)
        script = (database_release_web.ROOT / "scripts" / "apply_database_release_package.sh").read_text(encoding="utf-8")
        self.assertIn("Refusing non-additive SQL in schema release package", script)
        self.assertIn("pg_advisory_xact_lock", script)

        for name in ("prepare_database_release.sh", "sync_production_to_staging.sh", "sync_staging_to_production.sh"):
            flow = (database_release_web.ROOT / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn("verify_database_schema.py", flow)
            self.assertIn("Final schema equivalence verification passed", flow)

    def test_schema_only_audit_never_calls_business_row_digest(self):
        source = inspect.getsource(database_release_diff.audit_schema_only)
        self.assertNotIn("_table_data_digest", source)
        self.assertIn('"mode": "read_only_schema_only"', source)

    def test_final_schema_verification_only_blocks_structural_migration_history(self):
        source = inspect.getsource(database_release_diff.verify_schema_equivalence)
        self.assertIn('strict_migrations = migrations.get("strict_schema") or migrations', source)
        self.assertIn('"non_structural_migration_ledger_difference"', source)
        self.assertIn("历史主数据账本仅提示", source)
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("历史主数据迁移账本观察项", html)
        self.assertIn("不代表表结构漂移", html)

    def test_schema_generator_blocks_unresolved_existing_definition_drift(self):
        source = inspect.getsource(database_release_diff._schema_incremental_sql)
        self.assertIn("existing_constraint_definition_differs", source)
        self.assertIn("existing_index_definition_differs", source)
        self.assertIn("schema_only or target_rows", source)

    def test_schema_generator_creates_all_tables_before_cross_table_foreign_keys(self):
        """A table-name sort is not a safe order for a new-table foreign key."""
        local_connection, target_connection = object(), object()
        columns = [{
            "name": "id", "type": "bigint", "not_null": True,
            "default": "", "identity": "", "serial_sequence": "",
        }]
        constraints = {
            "daily_quiz_sets": {
                "daily_quiz_sets_question_id_fkey": "FOREIGN KEY (id) REFERENCES quiz_questions(id)",
            },
            "quiz_questions": {
                "quiz_questions_pkey": "PRIMARY KEY (id)",
            },
        }
        with patch.object(
            database_release_diff,
            "_public_tables",
            side_effect=lambda connection: ["daily_quiz_sets", "quiz_questions"] if connection is local_connection else [],
        ), patch.object(database_release_diff, "_column_specs", return_value=columns), patch.object(
            database_release_diff, "_table_constraints", side_effect=lambda _connection, table_name: constraints[table_name],
        ), patch.object(database_release_diff, "_table_indexes", return_value={}):
            plan = database_release_diff._schema_incremental_sql(
                local_connection, target_connection, {"schema": {"different_tables": []}}, schema_only=True,
            )
        sql_text = plan["sql"]
        self.assertLess(
            sql_text.index('CREATE TABLE IF NOT EXISTS "quiz_questions"'),
            sql_text.index("FOREIGN KEY (id) REFERENCES quiz_questions(id)"),
        )
        self.assertLess(
            sql_text.index("PRIMARY KEY (id)"),
            sql_text.index("FOREIGN KEY (id) REFERENCES quiz_questions(id)"),
        )

    def test_schema_release_ui_defers_strict_equivalence_until_after_a_package_is_applied(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("预期新增表会在最终核验前显示为差异", html)
        self.assertIn("最终严格等价核验会在应用完成后执行", html)
        self.assertIn("本次 SQL 事务已回滚，未部分写入", html)
        self.assertIn("item.stage==='error'", html)
        self.assertIn("transactionCommitted", html)

    def test_schema_release_submission_ui_is_scoped_to_the_current_plan_and_target(self):
        """A previous Production job must never mark an unsubmitted plan as submitted."""
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("schemaDiffSubmittedJobId='',schemaDiffSubmittedTarget=''", html)
        self.assertIn("function resetSchemaDiffSubmissionState()", html)
        self.assertIn("const isCurrentSubmission=Boolean(schemaDiffPlan&&schemaDiffSubmittedJobId&&job.id===schemaDiffSubmittedJobId&&job.target===schemaDiffSubmittedTarget&&job.target===schemaDiffPlan.target)", html)
        self.assertIn("if(!isSchemaRelease||!isCurrentSubmission)return", html)
        self.assertIn("if(!job.id)throw new Error('database_release_job_id_missing')", html)
        self.assertLess(
            html.index("if(!job.id)throw new Error('database_release_job_id_missing')"),
            html.index("button.textContent='已提交'"),
        )

    def test_schema_release_target_change_clears_submission_visual_state(self):
        html = self.client.get("/").get_data(as_text=True)
        handler = html[html.index("document.getElementById('schemaDiffTarget').addEventListener('change'"):]
        handler = handler[:handler.index("const consolePages=")]
        self.assertIn("resetSchemaDiffSubmissionState()", handler)
        self.assertIn("button.textContent='确认审核后应用'", html)

    def test_schema_release_revalidates_the_generated_ddl_before_starting(self):
        source = inspect.getsource(database_release_services.start_database_release_delta)
        self.assertIn("build_schema_only_delta", source)
        self.assertIn("database_release_schema_plan_blocked", source)
        self.assertIn("database_release_schema_package_stale", source)
        self.assertIn("package_path.read_bytes()", source)

    def test_schema_release_includes_only_proven_schema_migration_ledger_rows(self):
        source = inspect.getsource(database_release_services.generate_database_release_schema)
        self.assertIn("_schema_migration_ledger_baseline_sql", source)
        self.assertIn("schema_migration_ledger_baseline", source)
        baseline = inspect.getsource(database_release_services._schema_migration_ledger_baseline_sql)
        self.assertIn('row["migration_scope"] != "schema"', baseline)
        self.assertIn("ON CONFLICT (migration_name) DO NOTHING", baseline)
        self.assertIn("non_schema_migration_ledger_requires_manual_verification", baseline)
        package_script = (database_release_web.ROOT / "scripts" / "apply_database_release_package.sh").read_text(encoding="utf-8")
        self.assertIn("Schema package SQL transaction committed", package_script)
        self.assertIn("Final schema equivalence verification", package_script)

    def test_console_exposes_scan_busy_feedback(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="schemaDiffScan"', html)
        self.assertIn('id="refresh"', html)
        self.assertIn('onclick="refreshStatus(this)"', html)
        self.assertIn("正在读取 '+targetLabel+' 的结构元数据", html)
        self.assertIn("button.classList.add('is-loading')", html)
        self.assertIn("button.textContent='正在比较...'", html)
        self.assertIn("button.textContent='刷新中...'", html)
        self.assertIn("button.textContent='已刷新'", html)
        self.assertIn("button.textContent='刷新失败'", html)
        self.assertIn("button.is-pressed:not(:disabled)", html)
        self.assertIn("document.addEventListener('pointerdown'", html)
        self.assertIn("event.key==='Enter'||event.key===' '", html)
        self.assertIn("button.textContent='正在发布...'", html)
        self.assertIn("Production 发布中...", html)
        self.assertIn("button.setAttribute('aria-busy','true')", html)
        self.assertIn(">比较并生成结构包</button>", html)
        self.assertNotIn("差异迁移", html)
        self.assertNotIn("/api/diff/", html)
        self.assertIn("button:not(:disabled):active", html)
        self.assertIn("button:focus-visible", html)
        self.assertNotIn('onclick="reviewDiff()', html)
        self.assertNotIn('onclick="generateDiff()', html)
        self.assertNotIn("function reviewDiff", html)
        self.assertNotIn("function generateDiff", html)
        self.assertIn("data-rollback-target", html)
        self.assertNotIn("onclick=\"requestRollback(\\'", html)


if __name__ == "__main__":
    unittest.main()
