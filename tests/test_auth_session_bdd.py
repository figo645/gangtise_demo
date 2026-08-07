import unittest

from flask import session

from src.runtime import H5_USER_SESSION_KEY, app, _resolve_session_secret_key
from src.domain.core_services import save_current_demo_profile_id


class AuthSessionBddTest(unittest.TestCase):
    def test_given_a_login_when_session_is_written_then_it_is_permanent_for_twenty_minutes(self):
        with app.test_request_context("/"):
            save_current_demo_profile_id("bdd-user")

            self.assertEqual(session.get(H5_USER_SESSION_KEY), "bdd-user")
            self.assertTrue(session.permanent)
            self.assertEqual(app.permanent_session_lifetime.total_seconds(), 20 * 60)
            self.assertTrue(app.config["SESSION_REFRESH_EACH_REQUEST"])

    def test_given_no_environment_secret_when_runtime_reloads_then_the_fallback_secret_is_stable(self):
        self.assertEqual(_resolve_session_secret_key(), _resolve_session_secret_key())
        self.assertGreaterEqual(len(_resolve_session_secret_key()), 32)
