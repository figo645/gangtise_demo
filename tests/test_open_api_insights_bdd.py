import json
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_entry
import src.web.api_core as api_core
import src.web.hooks as web_hooks
from src.domain import core_services


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADMIN_USER = {"id": "open-api-admin", "username": "admin", "role": "admin"}
DAV_USER = {"id": "open-api-dav", "username": "dav", "role": "dav"}


class _Cursor:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _TokenDb:
    def __init__(self, row):
        self.row = row
        self.calls = []
        self.commit_count = 0

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params or ())))
        return _Cursor(self.row if "SELECT token_id" in sql else None)

    def commit(self):
        self.commit_count += 1


class OpenApiInsightsBddTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._original_is_authenticated = web_hooks.is_authenticated
        cls._original_hook_current_user = web_hooks.get_current_authenticated_user
        web_hooks.is_authenticated = lambda: True
        web_hooks.get_current_authenticated_user = lambda: ADMIN_USER
        app_entry.app.config.update(TESTING=True, SECRET_KEY="open-api-bdd-secret")
        cls.client = app_entry.app.test_client()

    @classmethod
    def tearDownClass(cls):
        web_hooks.is_authenticated = cls._original_is_authenticated
        web_hooks.get_current_authenticated_user = cls._original_hook_current_user

    def test_given_no_bearer_token_when_open_api_is_called_then_it_is_rejected_without_session_login(self):
        response = self.client.post("/api/open/v1/insights", json={"title": "标题", "content_text": "正文"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "open_api_unauthorized")
        self.assertEqual(response.headers.get("WWW-Authenticate"), 'Bearer realm="insight-publish"')

    def test_given_authorized_open_api_when_payload_is_valid_then_raw_insight_is_published_without_llm(self):
        principal = {"token_id": "oat_1", "tenant_slug": "laowang", "token_name": "内容中台"}
        dav = {"dav_id": "tenant_laowang", "tenant_slug": "laowang", "dav_name": "财经老王", "tenant_name": "老王投研"}
        published = {
            "snapshot": {
                "id": "laowang-review-1",
                "title": "市场观察",
                "access_mode": "public",
                "published_date": "2026-09-19",
                "published_at": "2026-09-19 10:00:00",
            }
        }
        with patch.object(api_core, "authenticate_open_api_insight_token", return_value=principal), patch.object(
            api_core, "get_open_api_dav_identity", return_value=dav
        ), patch.object(
            api_core, "persist_review_publish_snapshot", return_value=published
        ) as publish:
            response = self.client.post(
                "/api/open/v1/insights",
                headers={"Authorization": "Bearer gti_live_test"},
                json={"dav_id": "tenant_laowang", "title": "市场观察", "content_text": "未经优化的原文正文", "published_date": "2026-09-19", "external_id": "legacy-note-19", "prompt": "不要使用", "model": "v4"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["data"]["id"], "laowang-review-1")
        self.assertEqual(response.get_json()["data"]["dav_id"], "tenant_laowang")
        kwargs = publish.call_args.kwargs
        self.assertEqual(kwargs["tenant_slug"], "laowang")
        self.assertEqual(kwargs["text"], "未经优化的原文正文")
        self.assertEqual(kwargs["content_html"], "")
        self.assertEqual(kwargs["source_mode"], "open_api")
        self.assertEqual(kwargs["paragraph_mode"], "manual")
        self.assertEqual(kwargs["prompt_tags"], [])
        self.assertEqual(kwargs["access_mode"], "public")
        self.assertEqual(kwargs["published_date"], "2026-09-19")
        self.assertEqual(kwargs["external_id"], "legacy-note-19")
        self.assertEqual(kwargs["dav_id"], "tenant_laowang")
        self.assertFalse(kwargs["notify_followers"])
        self.assertNotIn("prompt", kwargs)
        self.assertNotIn("model", kwargs)

    def test_given_open_api_when_business_date_is_missing_invalid_or_future_then_request_is_rejected(self):
        principal = {"token_id": "oat_1", "tenant_slug": "laowang", "token_name": "内容中台"}
        dav = {"dav_id": "tenant_laowang", "tenant_slug": "laowang", "dav_name": "财经老王", "tenant_name": "老王投研"}
        payload = {"dav_id": "tenant_laowang", "title": "标题", "content_text": "正文"}
        with patch.object(api_core, "authenticate_open_api_insight_token", return_value=principal), patch.object(
            api_core, "get_open_api_dav_identity", return_value=dav
        ), patch.object(api_core, "persist_review_publish_snapshot") as publish:
            missing = self.client.post("/api/open/v1/insights", headers={"Authorization": "Bearer test"}, json=payload)
            malformed = self.client.post("/api/open/v1/insights", headers={"Authorization": "Bearer test"}, json={**payload, "published_date": "2026/09/19"})
            future = self.client.post("/api/open/v1/insights", headers={"Authorization": "Bearer test"}, json={**payload, "published_date": "2999-01-01"})

        self.assertEqual(missing.get_json()["error"], "open_api_published_date_required")
        self.assertEqual(malformed.get_json()["error"], "open_api_published_date_invalid")
        self.assertEqual(future.get_json()["error"], "open_api_published_date_future")
        publish.assert_not_called()

    def test_given_historical_open_api_import_when_notification_is_requested_then_it_is_rejected(self):
        principal = {"token_id": "oat_1", "tenant_slug": "laowang", "token_name": "内容中台"}
        dav = {"dav_id": "tenant_laowang", "tenant_slug": "laowang", "dav_name": "财经老王", "tenant_name": "老王投研"}
        with patch.object(api_core, "authenticate_open_api_insight_token", return_value=principal), patch.object(
            api_core, "get_open_api_dav_identity", return_value=dav
        ), patch.object(api_core, "persist_review_publish_snapshot") as publish:
            response = self.client.post(
                "/api/open/v1/insights", headers={"Authorization": "Bearer test"},
                json={"dav_id": "tenant_laowang", "title": "历史", "content_text": "正文", "published_date": "2026-09-19", "notify_followers": True},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "open_api_historical_insight_notification_forbidden")
        publish.assert_not_called()

    def test_given_authorized_open_api_when_tenant_or_fields_are_invalid_then_publish_is_not_called(self):
        principal = {"token_id": "oat_1", "tenant_slug": "laowang", "token_name": "内容中台"}
        dav = {"dav_id": "tenant_laowang", "tenant_slug": "laowang", "dav_name": "财经老王", "tenant_name": "老王投研"}
        with patch.object(api_core, "authenticate_open_api_insight_token", return_value=principal), patch.object(
            api_core, "get_open_api_dav_identity", return_value=dav
        ), patch.object(
            api_core, "persist_review_publish_snapshot"
        ) as publish:
            mismatch = self.client.post(
                "/api/open/v1/insights",
                headers={"Authorization": "Bearer gti_live_test"},
                json={"dav_id": "tenant_laowang", "tenant_slug": "other", "title": "标题", "content_text": "正文"},
            )
            invalid = self.client.post(
                "/api/open/v1/insights",
                headers={"Authorization": "Bearer gti_live_test"},
                json={"dav_id": "tenant_laowang", "title": "", "content_text": "正文"},
            )
            wrong_dav = self.client.post(
                "/api/open/v1/insights",
                headers={"Authorization": "Bearer gti_live_test"},
                json={"dav_id": "tenant_other", "title": "标题", "content_text": "正文"},
            )

        self.assertEqual(mismatch.status_code, 403)
        self.assertEqual(mismatch.get_json()["error"], "open_api_tenant_scope_forbidden")
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.get_json()["error"], "open_api_insight_title_required")
        self.assertEqual(wrong_dav.status_code, 403)
        self.assertEqual(wrong_dav.get_json()["error"], "open_api_dav_scope_forbidden")
        publish.assert_not_called()

    def test_given_authorized_open_api_when_dav_identity_is_requested_then_only_token_bound_dav_is_returned(self):
        principal = {"token_id": "oat_1", "tenant_slug": "laowang", "token_name": "内容中台"}
        dav = {"dav_id": "tenant_laowang", "tenant_slug": "laowang", "dav_name": "财经老王", "tenant_name": "老王投研"}
        with patch.object(api_core, "authenticate_open_api_insight_token", return_value=principal), patch.object(
            api_core, "get_open_api_dav_identity", return_value=dav
        ) as resolve_dav:
            response = self.client.get("/api/open/v1/davs", headers={"Authorization": "Bearer gti_live_test"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"], [dav])
        resolve_dav.assert_called_once_with("laowang")

    def test_given_admin_when_managing_tokens_then_create_list_reveal_and_revoke_contracts_are_available(self):
        token_info = {
            "token_id": "oat_1", "tenant_slug": "laowang", "token_name": "内容中台",
            "token_prefix": "gti_live_example", "scopes": ["insight.publish"], "status": "active",
            "created_at": "2026-09-19T10:00:00+08:00", "last_used_at": "", "usage_count": 0,
        }
        with patch.object(api_core, "get_current_authenticated_user", return_value=ADMIN_USER), patch.object(
            api_core, "create_open_api_insight_token", return_value={"token": "gti_live_secret", "token_info": token_info}
        ) as create, patch.object(api_core, "list_open_api_tokens", return_value=[token_info]) as list_tokens, patch.object(
            api_core, "reveal_open_api_token", return_value="gti_live_secret"
        ) as reveal, patch.object(api_core, "revoke_open_api_token", return_value="oat_1") as revoke:
            created = self.client.post("/api/admin/open-api/tokens", json={"tenant_slug": "laowang", "token_name": "内容中台"})
            listed = self.client.get("/api/admin/open-api/tokens?tenant_slug=laowang")
            revealed = self.client.post("/api/admin/open-api/tokens/oat_1/reveal")
            revoked = self.client.post("/api/admin/open-api/tokens/oat_1/revoke")

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["token"], "gti_live_secret")
        create.assert_called_once_with("laowang", "内容中台", "admin")
        self.assertEqual(listed.status_code, 200)
        self.assertNotIn("token", listed.get_json()["tokens"][0])
        self.assertNotIn("token_digest", listed.get_json()["tokens"][0])
        list_tokens.assert_called_once_with("laowang")
        self.assertEqual(revealed.get_json()["token"], "gti_live_secret")
        reveal.assert_called_once_with("oat_1")
        self.assertEqual(revoked.get_json()["token_id"], "oat_1")
        revoke.assert_called_once_with("oat_1")

    def test_given_dav_when_admin_token_endpoint_is_called_then_admin_guard_rejects_the_request(self):
        original_current_user = web_hooks.get_current_authenticated_user
        web_hooks.get_current_authenticated_user = lambda: DAV_USER
        try:
            response = self.client.get("/api/admin/open-api/tokens")
        finally:
            web_hooks.get_current_authenticated_user = original_current_user

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "admin_required")

    def test_given_active_token_when_authentication_succeeds_then_usage_is_recorded_and_scope_is_required(self):
        raw_token = "gti_live_test-token"
        row = {
            "token_id": "oat_1", "tenant_slug": "laowang", "token_name": "内容中台",
            "token_digest": core_services._open_api_token_digest(raw_token),
            "scopes_json": json.dumps(["insight.publish"]), "status": "active",
        }
        db = _TokenDb(row)
        with patch.object(core_services, "get_db", return_value=db):
            principal = core_services.authenticate_open_api_insight_token(raw_token)

        self.assertEqual(principal["tenant_slug"], "laowang")
        self.assertEqual(db.commit_count, 1)
        self.assertTrue(any("usage_count = usage_count + 1" in sql for sql, _ in db.calls))
        row["scopes_json"] = json.dumps([])
        with patch.object(core_services, "get_db", return_value=_TokenDb(row)):
            self.assertIsNone(core_services.authenticate_open_api_insight_token(raw_token))

    def test_given_unknown_tenant_when_token_is_issued_then_default_tenant_fallback_is_not_allowed(self):
        with patch.object(core_services, "get_tenant_by_slug", return_value={"slug": "laowang"}):
            with self.assertRaisesRegex(ValueError, "tenant_not_found"):
                core_services.create_open_api_insight_token("not-a-tenant", "错误租户")

    def test_given_open_api_admin_surface_when_checked_then_documentation_and_eye_controls_exist(self):
        migration = (PROJECT_ROOT / "sql/postgres/137_open_api_insight_tokens.sql").read_text(encoding="utf-8")
        admin_html = (PROJECT_ROOT / "templates/admin.html").read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS open_api_tokens", migration)
        self.assertIn("token_digest", migration)
        self.assertIn("token_ciphertext", migration)
        self.assertIn('data-section="open-api"', admin_html)
        self.assertIn("Authorization: Bearer YOUR_TOKEN", admin_html)
        self.assertIn("/api/open/v1/davs", admin_html)
        self.assertIn("dav_id", admin_html)
        self.assertIn("function revealAdminOpenApiToken", admin_html)
        self.assertIn("function revokeAdminOpenApiToken", admin_html)
        self.assertIn("&#128065; 查看", admin_html)
        self.assertIn("/api/admin/open-api/tokens", admin_html)

    def test_given_published_insights_storage_when_checked_then_it_is_independent_and_backfills_legacy_json(self):
        migration = (PROJECT_ROOT / "sql/postgres/138_tenant_published_insights.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS tenant_published_insights", migration)
        self.assertIn("external_id", migration)
        self.assertIn("published_date DATE NOT NULL", migration)
        self.assertIn("jsonb_array_elements", migration)
        self.assertIn("review_snapshots", migration)

    def test_given_domain_storage_migrations_when_checked_then_messages_knowledge_and_config_lock_are_separated(self):
        message_sql = (PROJECT_ROOT / "sql/postgres/139_message_center_domain.sql").read_text(encoding="utf-8")
        knowledge_sql = (PROJECT_ROOT / "sql/postgres/140_knowledge_domain.sql").read_text(encoding="utf-8")
        revision_sql = (PROJECT_ROOT / "sql/postgres/141_app_settings_revision.sql").read_text(encoding="utf-8")
        relation_sql = (PROJECT_ROOT / "sql/postgres/142_domain_foreign_keys.sql").read_text(encoding="utf-8")
        core = (PROJECT_ROOT / "src/domain/core_services.py").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS tenant_message_threads", message_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS tenant_messages", message_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS tenant_broadcasts", message_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS tenant_broadcast_deliveries", message_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS tenant_knowledge_documents", knowledge_sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS revision", revision_sql)
        self.assertIn("_persist_tenant_message_center_state", core)
        self.assertIn("save_tenant_knowledge_document", core)
        self.assertIn("site_config_concurrent_update", core)
        self.assertIn("fk_messages_thread", relation_sql)
        self.assertIn("fk_knowledge_documents_tenant", relation_sql)
