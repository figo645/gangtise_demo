"""BDD-style regression checks for fan subscriptions and QR acquisition."""

import unittest
from unittest.mock import patch

from src.domain import commerce_services


class FanCommerceBddTest(unittest.TestCase):
    def test_given_paywall_off_when_fan_reads_review_then_access_is_granted(self):
        with patch.object(commerce_services, "load_tenant_commerce_settings", return_value={"paywall_enabled": False, "default_review_access": "subscriber"}), patch.object(commerce_services, "is_feature_enabled", return_value=True):
            self.assertTrue(commerce_services.fan_can_view_paid_content("laowang", {"id": 7, "role": "investor", "tenant_slug": "laowang"}))

    def test_given_paywall_on_and_public_review_when_fan_reads_then_body_is_preserved(self):
        user = {"id": 7, "role": "investor", "tenant_slug": "laowang"}
        snapshot = {"id": "r1", "title": "今日洞见", "summary": "完整摘要", "content_text": "完整正文", "access_mode": "public", "user_input_section": {"display_text": "原始输入"}}
        with patch.object(commerce_services, "load_tenant_commerce_settings", return_value={"paywall_enabled": True, "default_review_access": "subscriber"}), patch.object(commerce_services, "is_feature_enabled", return_value=True), patch.object(commerce_services, "has_tenant_subscription_access", return_value=False):
            visible = commerce_services.protect_tenant_review_snapshots("laowang", [snapshot], user)[0]
        self.assertEqual(visible["access_mode"], "public")
        self.assertEqual(visible["content_text"], "完整正文")
        self.assertNotIn("access_required", visible)

    def test_given_paywall_on_and_subscriber_review_when_fan_has_no_subscription_then_body_is_removed(self):
        user = {"id": 7, "role": "investor", "tenant_slug": "laowang"}
        snapshot = {"id": "r1", "title": "订阅洞见", "summary": "完整摘要", "content_text": "完整正文", "access_mode": "subscriber", "user_input_section": {"display_text": "原始输入"}}
        with patch.object(commerce_services, "load_tenant_commerce_settings", return_value={"paywall_enabled": True, "default_review_access": "subscriber"}), patch.object(commerce_services, "is_feature_enabled", return_value=True), patch.object(commerce_services, "has_tenant_subscription_access", return_value=False):
            protected = commerce_services.protect_tenant_review_snapshots("laowang", [snapshot], user)[0]
        self.assertTrue(protected["access_required"])
        self.assertEqual(protected["content_text"], "")
        self.assertEqual(protected["user_input_section"], {})
        self.assertEqual(protected["summary"], "该洞见内容面向订阅用户开放。")

    def test_given_legacy_global_free_setting_and_subscriber_review_when_fan_reads_then_body_is_still_removed(self):
        user = {"id": 7, "role": "investor", "tenant_slug": "laowang"}
        snapshot = {"id": "r1", "content_text": "订阅正文", "access_mode": "subscriber"}
        with patch.object(commerce_services, "load_tenant_commerce_settings", return_value={"paywall_enabled": True, "default_review_access": "free"}), patch.object(commerce_services, "is_feature_enabled", return_value=True), patch.object(commerce_services, "has_tenant_subscription_access", return_value=False):
            protected = commerce_services.protect_tenant_review_snapshots("laowang", [snapshot], user)[0]
        self.assertTrue(protected["access_required"])
        self.assertEqual(protected["content_text"], "")

    def test_given_active_subscription_when_review_payload_is_built_then_body_is_preserved(self):
        user = {"id": 7, "role": "investor", "tenant_slug": "laowang"}
        snapshot = {"id": "r1", "content_text": "完整正文", "access_mode": "subscriber"}
        with patch.object(commerce_services, "load_tenant_commerce_settings", return_value={"paywall_enabled": True, "default_review_access": "subscriber"}), patch.object(commerce_services, "is_feature_enabled", return_value=True), patch.object(commerce_services, "has_tenant_subscription_access", return_value=True):
            visible = commerce_services.protect_tenant_review_snapshots("laowang", [snapshot], user)[0]
        self.assertEqual(visible["content_text"], "完整正文")
        self.assertNotIn("access_required", visible)

    def test_given_legacy_review_without_access_mode_when_fan_reads_then_it_defaults_to_public(self):
        user = {"id": 7, "role": "investor", "tenant_slug": "laowang"}
        snapshot = {"id": "legacy", "content_text": "历史正文"}
        with patch.object(commerce_services, "load_tenant_commerce_settings", return_value={"paywall_enabled": True, "default_review_access": "subscriber"}), patch.object(commerce_services, "is_feature_enabled", return_value=True), patch.object(commerce_services, "has_tenant_subscription_access", return_value=False):
            visible = commerce_services.protect_tenant_review_snapshots("laowang", [snapshot], user)[0]
        self.assertEqual(visible["access_mode"], "public")
        self.assertEqual(visible["access_label"], "常规笔记")
        self.assertEqual(visible["content_text"], "历史正文")

    def test_given_subscriber_review_when_dav_or_admin_reads_then_body_is_preserved(self):
        snapshot = {"id": "r1", "content_text": "内部正文", "access_mode": "subscriber"}
        for role in ("dav", "admin"):
            with self.subTest(role=role), patch.object(commerce_services, "load_tenant_commerce_settings", return_value={"paywall_enabled": True, "default_review_access": "subscriber"}), patch.object(commerce_services, "is_feature_enabled", return_value=True), patch.object(commerce_services, "has_tenant_subscription_access", return_value=False):
                visible = commerce_services.protect_tenant_review_snapshots("laowang", [snapshot], {"id": 1, "role": role, "tenant_slug": "laowang"})[0]
            self.assertEqual(visible["content_text"], "内部正文")
            self.assertNotIn("access_required", visible)

    def test_given_configured_qr_invite_when_safe_config_is_served_then_fan_cannot_receive_unprotected_review_body(self):
        config = {"tenants": [{"slug": "laowang", "review_snapshots": [{"content_text": "secret", "access_mode": "subscriber"}]}]}
        user = {"id": 7, "role": "investor", "tenant_slug": "laowang"}
        with patch.object(commerce_services, "load_tenant_commerce_settings", return_value={"paywall_enabled": True, "default_review_access": "subscriber"}), patch.object(commerce_services, "is_feature_enabled", return_value=True), patch.object(commerce_services, "has_tenant_subscription_access", return_value=False):
            safe = commerce_services.build_fan_safe_site_config(config, user)
        self.assertEqual(safe["tenants"][0]["review_snapshots"][0]["content_text"], "")
        self.assertEqual(config["tenants"][0]["review_snapshots"][0]["content_text"], "secret")


if __name__ == "__main__":
    unittest.main()
