import unittest
from unittest.mock import patch

from src.domain import core_services


class EnsureDefaultUsersTest(unittest.TestCase):
    def test_seed_defaults_when_user_table_empty(self):
        created_users = [{"username": item["username"]} for item in core_services.DEFAULT_USERS]
        with patch.object(core_services, "list_users", return_value=[]), patch.object(
            core_services,
            "create_user",
            side_effect=created_users,
        ) as create_user_mock:
            result = core_services.ensure_default_users()
        self.assertEqual(len(result["created"]), len(core_services.DEFAULT_USERS))
        self.assertEqual(result["skipped"], [])
        self.assertEqual(create_user_mock.call_count, len(core_services.DEFAULT_USERS))

    def test_skip_seed_when_users_exist(self):
        with patch.object(core_services, "list_users", return_value=[{"username": "existing"}]), patch.object(
            core_services,
            "create_user",
        ) as create_user_mock:
            result = core_services.ensure_default_users()
        self.assertEqual(result, {"created": [], "skipped": []})
        create_user_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
