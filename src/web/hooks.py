from src.runtime import *
from src.services import *
from src.web.request_helpers import get_client_ip, safe_next_target

@app.teardown_appcontext
def close_db(exc):
    """Close the request-scoped PostgreSQL connection and its transaction."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def is_authenticated():
    try:
        return get_current_authenticated_user() is not None
    except Exception as exc:
        if is_db_unavailable_error(exc):
            return False
        raise


def should_log_request():
    return not request.path.startswith("/static/") and not request.path.startswith("/api/")


def is_admin_only_request(path):
    normalized_path = str(path or "").rstrip("/") or "/"
    return normalized_path in {"/admin", "/intern-handbook"} or normalized_path.startswith("/api/admin/")


def admin_access_denied_response():
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "admin_required"}), 403
    abort(403)


def record_access(response):
    if not should_log_request():
        return response
    try:
        # Access logging applies to every platform role.  Resolving through the
        # H5-only profile helper would discard an admin session after login.
        current_profile = get_current_authenticated_user()
        tenant_slug = ""
        user_profile_id = ""
        user_role = ""
        if isinstance(current_profile, dict):
            tenant_slug = str((current_profile.get("tenant") or {}).get("slug") or current_profile.get("tenant_slug") or "").strip().lower()
            user_profile_id = str(current_profile.get("username") or "").strip()
            user_role = str(current_profile.get("role") or "").strip().lower()
        if not tenant_slug:
            tenant_slug = str(request.args.get("tenant") or "").strip().lower()
        path_value = request.full_path.rstrip("?") if getattr(request, "full_path", "") else request.path
        db = get_db()
        db.execute(
            """
            INSERT INTO access_logs (ip, path, method, status_code, created_at, user_agent, referrer, tenant_slug, user_profile_id, user_role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                get_client_ip(),
                path_value,
                request.method,
                response.status_code,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                request.headers.get("User-Agent", ""),
                request.headers.get("Referer", ""),
                tenant_slug,
                user_profile_id,
                user_role,
            ),
        )
        db.commit()
    except Exception as exc:
        if is_db_unavailable_error(exc):
            return response
        app.logger.exception("Failed to write access log")
    return response


@app.before_request
def require_user_login():
    public_paths = {
        "/",
        "/login",
        "/logout",
        "/switch-account",
        "/api/demo-profiles",
        "/api/demo-profile/switch",
        "/api/h5/login/password",
        "/api/h5/register/password",
        "/api/h5/wechat/start",
        "/api/h5/wechat/callback",
        "/api/h5/logout",
    }
    if request.path.startswith("/static/") or request.path in public_paths:
        return None
    if is_authenticated():
        if is_admin_only_request(request.path):
            current_user = get_current_authenticated_user() or {}
            if str(current_user.get("role") or "").strip().lower() != "admin":
                return admin_access_denied_response()
        return None
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "auth_required"}), 401
    return redirect(url_for("login", next=safe_next_target(request.full_path.rstrip("?"))))


@app.after_request
def log_access(response):
    return record_access(response)
