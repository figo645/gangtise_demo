from datetime import date

from src.runtime import *
from src.services import *


def _quiz_user():
    user = get_current_authenticated_user() or {}
    if not user or str(user.get("role") or "").lower() not in {"investor", "dav", "admin"}:
        return None, (jsonify({"ok": False, "error": "auth_required"}), 401)
    return user, None


def _quiz_tenant_for_user(user, requested_tenant=""):
    """Keep quiz attempts and the DAv's quiz statistics in the user's tenant."""
    role = str((user or {}).get("role") or "").strip().lower()
    account_tenant = str((user or {}).get("tenant_slug") or "").strip().lower()
    requested = str(requested_tenant or "").strip().lower()
    if role != "admin" and requested and requested != account_tenant:
        raise ValueError("tenant_scope_forbidden")
    return requested if role == "admin" and requested else account_tenant


@app.route("/api/quiz/daily", methods=["GET"])
def api_quiz_daily():
    user, denied = _quiz_user()
    if denied:
        return denied
    try:
        tenant_slug = _quiz_tenant_for_user(user, request.args.get("tenant"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    try:
        return jsonify({"ok": True, **get_daily_quiz_payload(user, tenant_slug)})
    except Exception:
        app.logger.exception("Failed to load daily quiz")
        return jsonify({"ok": False, "error": "quiz_load_failed"}), 500


@app.route("/api/quiz/daily/start", methods=["POST"])
def api_quiz_start():
    user, denied = _quiz_user()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    try:
        tenant_slug = _quiz_tenant_for_user(user, body.get("tenant_slug"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    quiz_date = str(body.get("quiz_date") or date.today().isoformat())
    try:
        return jsonify({"ok": True, "attempt": start_quiz_attempt(user, tenant_slug, quiz_date)})
    except Exception:
        app.logger.exception("Failed to start daily quiz")
        return jsonify({"ok": False, "error": "quiz_start_failed"}), 500


@app.route("/api/quiz/daily/submit", methods=["POST"])
def api_quiz_submit():
    user, denied = _quiz_user()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    try:
        tenant_slug = _quiz_tenant_for_user(user, body.get("tenant_slug"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    quiz_date = str(body.get("quiz_date") or date.today().isoformat())
    try:
        return jsonify({"ok": True, "result": submit_quiz_attempt(user, tenant_slug, quiz_date, body.get("answers"), body.get("attempt_id"))})
    except Exception:
        app.logger.exception("Failed to submit daily quiz")
        return jsonify({"ok": False, "error": "quiz_submit_failed"}), 500


@app.route("/api/kol/quiz/stats", methods=["GET"])
def api_kol_quiz_stats():
    user, denied = _quiz_user()
    if denied:
        return denied
    role = str(user.get("role") or "").lower()
    if role not in {"dav", "admin"}:
        return jsonify({"ok": False, "error": "dav_required"}), 403
    tenant_slug = str(request.args.get("tenant") or user.get("tenant_slug") or "").strip().lower()
    if role != "admin":
        tenant_slug = str(user.get("tenant_slug") or "").strip().lower()
    try:
        return jsonify({"ok": True, "stats": build_quiz_admin_stats(tenant_slug or None)})
    except Exception:
        app.logger.exception("Failed to load quiz interaction statistics")
        return jsonify({"ok": False, "error": "quiz_stats_failed"}), 500
