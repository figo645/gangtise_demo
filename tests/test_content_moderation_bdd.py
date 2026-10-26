import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from src.domain import content_moderation_services
from src.runtime import app


class _Cursor:
    def __init__(self, rows=None, rowcount=0):
        self.rows = list(rows or [])
        self.rowcount = rowcount

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _ModerationDb:
    def __init__(self):
        self.rules = [{"id": 1, "keyword": "稳赚", "category": "收益承诺", "risk_level": "high"}]
        self.audit_insert = None
        self.committed = False

    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).split()).lower()
        if normalized.startswith("select id, keyword, category, risk_level from content_moderation_keywords"):
            return _Cursor(self.rules)
        if normalized.startswith("insert into content_moderation_audits"):
            self.audit_insert = tuple(params)
            return _Cursor([], 1)
        raise AssertionError(f"unexpected SQL: {sql}")

    def commit(self):
        self.committed = True


def test_content_submission_records_alert_without_persisting_plaintext():
    fake_db = _ModerationDb()
    content = "这不是稳赚承诺，只是风险提示。"
    with app.app_context(), patch("src.domain.core_services.get_db", return_value=fake_db):
        result = content_moderation_services.inspect_and_record_content(
            content,
            "insight",
            tenant_slug="laowang",
            entity_id="insight-1",
            actor_user_id="dav-1",
            actor_name="财经老王",
        )

    assert result["result"] == "alert"
    assert result["risk_level"] == "high"
    assert result["matches"][0]["keyword"] == "稳赚"
    assert result["content_sha256"] == hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert content not in json.dumps(fake_db.audit_insert, ensure_ascii=False)
    assert fake_db.audit_insert[8] == result["content_sha256"]
    assert fake_db.committed is True


def test_content_submission_without_match_records_clear_result():
    fake_db = _ModerationDb()
    with app.app_context(), patch("src.domain.core_services.get_db", return_value=fake_db):
        result = content_moderation_services.inspect_and_record_content("观察成交量变化。", "comment")

    assert result["result"] == "clear"
    assert result["risk_level"] == "none"
    assert json.loads(fake_db.audit_insert[7]) == []


def test_admin_content_moderation_api_is_role_protected_and_exposes_report():
    admin = {"id": "admin-1", "username": "admin", "role": "admin"}
    report = {"summary": {"total": 3, "alerts": 1, "high_risk": 1}, "distribution": [], "trend": [], "logs": []}
    with patch("src.web.hooks.is_authenticated", return_value=True), \
        patch("src.web.hooks.get_current_authenticated_user", return_value=admin), \
        patch("src.web.api_core.get_current_authenticated_user", return_value=admin), \
        patch("src.web.api_core.get_content_moderation_audit_report", return_value=report), \
        patch("src.web.api_core.list_content_moderation_keywords", return_value=[]):
        response = app.test_client().get("/api/admin/content-moderation")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "report": report, "keywords": []}

    with patch("src.web.hooks.is_authenticated", return_value=True), \
        patch("src.web.hooks.get_current_authenticated_user", return_value={"role": "dav"}), \
        patch("src.web.api_core.get_current_authenticated_user", return_value={"role": "dav"}):
        denied = app.test_client().get("/api/admin/content-moderation")
    assert denied.status_code == 403
    assert denied.get_json()["error"] == "admin_required"


def test_admin_keyword_api_supports_create_and_delete():
    admin = {"id": "admin-1", "username": "admin", "role": "admin"}
    saved = {"id": 9, "keyword": "内幕消息", "category": "内幕信息", "risk_level": "high", "enabled": True}
    with patch("src.web.hooks.is_authenticated", return_value=True), \
        patch("src.web.hooks.get_current_authenticated_user", return_value=admin), \
        patch("src.web.api_core.get_current_authenticated_user", return_value=admin), \
        patch("src.web.api_core.save_content_moderation_keyword", return_value=saved) as save:
        response = app.test_client().post(
            "/api/admin/content-moderation/keywords",
            json={"keyword": "内幕消息", "category": "内幕信息", "risk_level": "high"},
        )
    assert response.status_code == 200
    assert response.get_json()["keyword"] == saved
    assert save.call_args.kwargs["actor"] == "admin"

    with patch("src.web.hooks.is_authenticated", return_value=True), \
        patch("src.web.hooks.get_current_authenticated_user", return_value=admin), \
        patch("src.web.api_core.get_current_authenticated_user", return_value=admin), \
        patch("src.web.api_core.delete_content_moderation_keyword", return_value=9) as delete:
        response = app.test_client().delete("/api/admin/content-moderation/keywords/9")
    assert response.status_code == 200
    delete.assert_called_once_with(9)


def test_admin_page_contains_keyword_management_and_audit_surfaces():
    html = (Path(__file__).resolve().parents[1] / "templates/admin.html").read_text(encoding="utf-8")
    assert 'data-section="content-moderation"' in html
    assert 'id="moderation-keyword-rows"' in html
    assert 'id="moderation-trend"' in html
    assert 'id="moderation-log-rows"' in html
    assert "/api/admin/content-moderation" in html
