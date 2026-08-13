import unittest
from unittest.mock import patch

from flask import Response, session

from src.runtime import app
from src.domain import core_services
from src.web import hooks


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
            return_value={"username": "admin", "role": "admin"},
        ) as create_user_mock:
            result = core_services.ensure_default_users()
        self.assertEqual(result["created"], [{"username": "admin", "role": "admin"}])
        self.assertEqual(result["skipped"], [])
        create_user_mock.assert_called_once_with(next(item for item in core_services.DEFAULT_USERS if item["role"] == "admin"))

    def test_default_admin_uses_the_documented_credentials(self):
        default_admin = next(item for item in core_services.DEFAULT_USERS if item["role"] == "admin")
        self.assertEqual(default_admin["username"], "admin")
        self.assertEqual(default_admin["password"], "admin123")

    def test_access_logging_does_not_clear_an_admin_login_session(self):
        admin = {"username": "admin", "role": "admin", "status": "active", "tenant_slug": "laowang"}
        with app.test_request_context("/login"):
            core_services.save_current_demo_profile_id("admin")
            with patch.object(hooks, "get_current_authenticated_user", return_value=admin), patch.object(hooks, "get_db"):
                hooks.record_access(Response(status=302))
            self.assertEqual(session.get("current_h5_username"), "admin")


if __name__ == "__main__":
    unittest.main()
