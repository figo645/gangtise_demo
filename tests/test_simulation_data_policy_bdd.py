import os
import unittest
from unittest.mock import patch

from src.runtime import PgCompatConnection
import src.domain.core_services as core_services


class SharedDatabaseContentBddTest(unittest.TestCase):
    def test_sql_normalization_never_adds_environment_visibility_predicates(self):
        connection = PgCompatConnection(None)
        sql = connection._normalize_sql(
            "SELECT u.username FROM users u "
            "JOIN hermes_conversation_turns h ON h.user_profile_id = u.username "
            "WHERE u.status = ? ORDER BY h.created_at DESC"
        )

        self.assertIn("WHERE u.status = %s", sql)
        self.assertNotIn("is_simulated", sql)
        self.assertFalse(hasattr(connection, "_hide_simulated_data"))

    def test_sql_normalization_preserves_nested_and_cte_queries(self):
        connection = PgCompatConnection(None)
        nested_sql = connection._normalize_sql(
            "SELECT sm.session_id, (SELECT question_text FROM hermes_conversation_turns t "
            "WHERE t.session_id = sm.session_id LIMIT 1) AS first_question "
            "FROM hermes_session_memory sm WHERE sm.tenant_slug = ?"
        )
        cte_sql = connection._normalize_sql(
            "WITH recent AS (SELECT id FROM knowledge_embeddings WHERE tenant_slug = ?) "
            "SELECT * FROM recent ORDER BY id DESC"
        )

        self.assertIn("WHERE t.session_id = sm.session_id LIMIT 1", nested_sql)
        self.assertIn("WHERE sm.tenant_slug = %s", nested_sql)
        self.assertIn("WHERE tenant_slug = %s", cte_sql)
        self.assertNotIn("is_simulated", nested_sql + cte_sql)

    def test_runtime_environment_does_not_change_shared_policy(self):
        with patch.dict(os.environ, {"GANGTISE_RUNTIME_ENV": "local"}, clear=False):
            local_sql = PgCompatConnection(None)._normalize_sql("SELECT * FROM users")
        with patch.dict(os.environ, {"GANGTISE_RUNTIME_ENV": "production"}, clear=False):
            production_sql = PgCompatConnection(None)._normalize_sql("SELECT * FROM users")

        self.assertEqual(local_sql, production_sql)

    def test_environment_simulation_migration_removes_triggers_and_settings(self):
        migration = (
            core_services.PROJECT_ROOT
            / "sql"
            / "postgres"
            / "043_remove_environment_simulation_processing.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("DROP TRIGGER IF EXISTS", migration)
        self.assertIn("DROP FUNCTION IF EXISTS gangtise_mark_local_simulated_write", migration)
        self.assertIn("simulation_data_visibility", migration)
        self.assertIn("simulation_data_bootstrap_completed", migration)
        self.assertIn("SET DEFAULT 0", migration)


if __name__ == "__main__":
    unittest.main()
