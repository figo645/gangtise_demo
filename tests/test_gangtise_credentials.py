import json
import unittest
from unittest.mock import patch

import app as app_entry
import src.web.hooks as web_hooks
from src.domain import core_services, market_services


class GangtiseCredentialsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._original_is_authenticated = web_hooks.is_authenticated
        cls._original_current_user = web_hooks.get_current_authenticated_user
        web_hooks.is_authenticated = lambda: True
        web_hooks.get_current_authenticated_user = lambda: {"id": "test-admin", "role": "admin"}
        app_entry.app.config.update(TESTING=True, SECRET_KEY="test-gangtise-credential-encryption-key")
        cls.client = app_entry.app.test_client()

    @classmethod
    def tearDownClass(cls):
        web_hooks.is_authenticated = cls._original_is_authenticated
        web_hooks.get_current_authenticated_user = cls._original_current_user

    def test_given_credentials_when_saved_then_postgres_payload_is_encrypted(self):
        persisted = {}
        safe_status = {"stored_in_postgres": True, "credential_mode": "access_key_secret"}
        with patch.object(core_services, "load_gangtise_openapi_credentials", return_value={}), patch.object(
            core_services, "_save_json_app_setting", side_effect=lambda key, value: persisted.update({"key": key, "value": value})
        ), patch.object(core_services, "get_gangtise_openapi_credentials_status", return_value=safe_status):
            result = core_services.save_gangtise_openapi_credentials_patch(
                {"base_url": "https://openapi.example.test", "access_key": "access-key-value", "secret_key": "secret-key-value"}
            )

        self.assertEqual(result, safe_status)
        self.assertEqual(persisted["key"], core_services.GANGTISE_OPENAPI_CREDENTIAL_SETTING_KEY)
        encoded = json.dumps(persisted["value"], ensure_ascii=False)
        self.assertNotIn("access-key-value", encoded)
        self.assertNotIn("secret-key-value", encoded)
        decrypted = core_services._gangtise_openapi_credential_fernet().decrypt(
            persisted["value"]["ciphertext"].encode("ascii")
        )
        self.assertEqual(json.loads(decrypted.decode("utf-8"))["access_key"], "access-key-value")

    def test_given_existing_credentials_when_blank_patch_then_secrets_are_preserved(self):
        persisted = {}
        existing = {
            "base_url": "https://openapi.gangtise.com",
            "access_key": "existing-access", "secret_key": "existing-secret", "long_token": "",
        }
        with patch.object(core_services, "load_gangtise_openapi_credentials", return_value=existing), patch.object(
            core_services, "_save_json_app_setting", side_effect=lambda key, value: persisted.update({"key": key, "value": value})
        ), patch.object(core_services, "get_gangtise_openapi_credentials_status", return_value={}):
            core_services.save_gangtise_openapi_credentials_patch({"base_url": "https://gateway.example.test"})

        decrypted = core_services._gangtise_openapi_credential_fernet().decrypt(
            persisted["value"]["ciphertext"].encode("ascii")
        )
        saved = json.loads(decrypted.decode("utf-8"))
        self.assertEqual(saved["access_key"], "existing-access")
        self.assertEqual(saved["secret_key"], "existing-secret")
        self.assertEqual(saved["base_url"], "https://gateway.example.test")

    def test_given_environment_credentials_when_postgres_is_empty_then_runtime_ignores_environment(self):
        with patch.object(market_services, "load_gangtise_openapi_credentials", return_value={}), patch.dict(
            "os.environ", {"GANGTISE_ACCESS_KEY": "environment-access", "GANGTISE_SECRET_KEY": "environment-secret"}, clear=False
        ):
            config = market_services.get_gangtise_openapi_config()

        self.assertEqual(config["base_url"], core_services.GANGTISE_OPENAPI_DEFAULT_BASE_URL)
        self.assertEqual(config["access_key"], "")
        self.assertEqual(config["secret_key"], "")
        self.assertEqual(config["long_token"], "")

    def test_given_admin_credential_status_when_requested_then_no_secret_is_returned(self):
        safe_status = {
            "stored_in_postgres": True, "base_url": "https://openapi.gangtise.com", "has_access_key": True,
            "has_secret_key": True, "has_long_token": False, "credential_mode": "access_key_secret", "updated_at": "2026-08-20 12:00:00",
        }
        with patch("src.web.api_core.get_gangtise_openapi_credentials_status", return_value=safe_status):
            response = self.client.get("/api/admin/gangtise-credentials")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertNotIn("access_key", payload["credentials"])
        self.assertNotIn("secret_key", payload["credentials"])
        self.assertNotIn("long_token", payload["credentials"])

    def test_given_admin_credential_save_when_called_then_token_cache_is_invalidated(self):
        safe_status = {"stored_in_postgres": True, "credential_mode": "long_token"}
        with patch("src.web.api_core.save_gangtise_openapi_credentials_patch", return_value=safe_status) as save_patch, patch(
            "src.web.api_core.invalidate_gangtise_openapi_token_cache"
        ) as invalidate_cache:
            response = self.client.post("/api/admin/gangtise-credentials", json={"long_token": "never-return-this"})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("never-return-this", response.get_data(as_text=True))
        save_patch.assert_called_once()
        invalidate_cache.assert_called_once()

    def test_given_unreadable_old_ciphertext_when_admin_saves_new_credentials_then_it_is_replaced(self):
        persisted = {}
        core_services._encrypted_setting_decryption_errors.add(core_services.GANGTISE_OPENAPI_CREDENTIAL_SETTING_KEY)
        try:
            with patch.object(core_services, "load_gangtise_openapi_credentials", return_value={}), patch.object(
                core_services, "_save_json_app_setting", side_effect=lambda key, value: persisted.update({"key": key, "value": value})
            ), patch.object(core_services, "get_gangtise_openapi_credentials_status", return_value={"credential_mode": "access_key_secret"}):
                result = core_services.save_gangtise_openapi_credentials_patch(
                    {"access_key": "replacement-access", "secret_key": "replacement-secret"}
                )
        finally:
            core_services._encrypted_setting_decryption_errors.discard(core_services.GANGTISE_OPENAPI_CREDENTIAL_SETTING_KEY)

        self.assertEqual(result["credential_mode"], "access_key_secret")
        self.assertEqual(persisted["key"], core_services.GANGTISE_OPENAPI_CREDENTIAL_SETTING_KEY)


if __name__ == "__main__":
    unittest.main()
