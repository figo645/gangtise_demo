import os
import unittest
from unittest.mock import MagicMock, patch

from src.runtime import PgCompatConnection, app
import src.domain.core_services as core_services
import src.web.api_core as api_core


class SimulationDataPolicyBddTest(unittest.TestCase):
    def test_given_production_connection_when_selecting_business_rows_then_simulated_rows_are_filtered(self):
        connection = PgCompatConnection(None)
        connection._hide_simulated_data = True

        sql = connection._normalize_sql(
            "SELECT u.username FROM users u JOIN hermes_conversation_turns h ON h.user_profile_id = u.username WHERE u.status = ? ORDER BY h.created_at DESC"
        )

        self.assertIn("COALESCE(u.is_simulated, 0) = 0", sql)
        self.assertIn("COALESCE(h.is_simulated, 0) = 0", sql)
        self.assertIn("ORDER BY h.created_at DESC", sql)

    def test_given_nested_or_cte_selects_when_production_filters_then_each_scope_is_protected(self):
        connection = PgCompatConnection(None)
        connection._hide_simulated_data = True

        nested_sql = connection._normalize_sql(
            "SELECT sm.session_id, (SELECT question_text FROM hermes_conversation_turns t "
            "WHERE t.session_id = sm.session_id LIMIT 1) AS first_question "
            "FROM hermes_session_memory sm WHERE sm.tenant_slug = ?"
        )
        cte_sql = connection._normalize_sql(
            "WITH recent AS (SELECT id FROM knowledge_embeddings WHERE tenant_slug = ?) "
            "SELECT * FROM recent ORDER BY id DESC"
        )

        self.assertIn("COALESCE(t.is_simulated, 0) = 0 LIMIT 1", nested_sql)
        self.assertIn("COALESCE(sm.is_simulated, 0) = 0", nested_sql)
        self.assertNotIn("COALESCE(t.is_simulated, 0) = 0 AND COALESCE(sm", nested_sql)
        self.assertIn("COALESCE(knowledge_embeddings.is_simulated, 0) = 0", cte_sql)

    def test_given_production_runtime_without_saved_setting_when_admin_requests_policy_then_visibility_defaults_off(self):
        with patch.dict(os.environ, {"GANGTISE_RUNTIME_ENV": "production"}, clear=False), patch.object(
            core_services, "get_app_db_connection"
        ) as get_connection:
            fake_connection = MagicMock()
            get_connection.return_value = fake_connection
            policy = core_services.get_simulation_data_policy()

        self.assertEqual(policy["runtime_environment"], "production")
        self.assertFalse(policy["simulated_data_visible"])
        self.assertFalse(policy["production_forced_hidden"])
        self.assertTrue(policy["admin_controlled"])

    def test_given_production_runtime_when_admin_enables_simulated_data_then_the_setting_is_saved(self):
        expected = {"simulated_data_visible": True, "admin_controlled": True}
        with app.test_request_context("/api/admin/simulation-data-policy", method="POST", json={"simulated_data_visible": True}), patch.object(
            api_core, "save_simulation_data_visibility", return_value=expected
        ):
            response = api_core.api_admin_simulation_data_policy()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["policy"], expected)

    def test_given_visibility_migration_when_inspected_then_all_tagged_tables_receive_origin_defaults(self):
        migration = (core_services.PROJECT_ROOT / "sql" / "postgres" / "035_local_simulation_data_visibility.sql").read_text(encoding="utf-8")

        self.assertIn("gangtise.simulated_write", migration)
        self.assertIn("本机模拟数据", migration)
        self.assertIn("hermes_conversation_turns", migration)
        self.assertIn("user_watchlist_items", migration)
        self.assertIn("CREATE TRIGGER", migration)
        self.assertIn("BEFORE INSERT OR UPDATE", migration)

    def test_given_control_plane_accounts_when_latest_migration_is_inspected_then_they_remain_real(self):
        migration = (core_services.PROJECT_ROOT / "sql" / "postgres" / "041_keep_control_plane_accounts_real.sql").read_text(encoding="utf-8")

        self.assertIn("role IN ('dav', 'admin')", migration)
        self.assertIn("TG_TABLE_NAME = 'users'", migration)
        self.assertIn("NEW.is_simulated := 0", migration)

    def test_given_production_visibility_when_resolving_embedded_review_snapshots_then_local_content_is_removed(self):
        tenant = {"slug": "laowang", "advisor": "财经老王", "review_snapshots": []}
        snapshots = [
            {"id": "local-review", "title": "本机复盘", "is_simulated": True, "simulation_label": "本机模拟数据"},
            {"id": "production-review", "title": "正式复盘", "is_simulated": False},
        ]
        with patch.object(core_services, "should_hide_simulated_data", return_value=True):
            result = core_services.resolve_tenant_review_snapshots(tenant, snapshots=snapshots)

        self.assertEqual([item["id"] for item in result], ["production-review"])

    def test_given_hidden_visibility_when_resolving_embedded_knowledge_then_local_content_is_removed_without_deleting_it(self):
        tenant = {"slug": "laowang", "advisor": "财经老王", "knowledge_hub_config": {}}
        source = {
            "items": [
                {"id": "local-knowledge", "title": "本机资料", "type": "manual", "is_simulated": True},
                {"id": "production-knowledge", "title": "正式资料", "type": "manual", "is_simulated": False},
            ]
        }
        with patch.object(core_services, "should_hide_simulated_data", return_value=True):
            visible = core_services.normalize_knowledge_hub_config(source, tenant)
            stored = core_services.normalize_knowledge_hub_config(source, tenant, include_simulated=True)

        self.assertEqual([item["id"] for item in visible["items"]], ["production-knowledge"])
        self.assertEqual([item["id"] for item in stored["items"]], ["local-knowledge", "production-knowledge"])


if __name__ == "__main__":
    unittest.main()
