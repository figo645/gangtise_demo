from src.runtime import *
from src.services import *
from src.web.request_helpers import get_client_ip, safe_next_target

def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def is_authenticated():
    return session.get(AUTH_SESSION_KEY) is True


def is_password_gate_enabled():
    config = get_site_config()
    if g.get("site_config_db_unavailable"):
        app.logger.warning("Database unavailable while checking password gate, temporarily disabling gate")
        return False
    return bool(config.get("password_gate_enabled", True))


def should_log_request():
    return not request.path.startswith("/static/") and not request.path.startswith("/api/")


def record_access(response):
    if not should_log_request():
        return response
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO access_logs (ip, path, method, status_code, created_at, user_agent, referrer)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                get_client_ip(),
                request.path,
                request.method,
                response.status_code,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                request.headers.get("User-Agent", ""),
                request.headers.get("Referer", ""),
            ),
        )
        db.commit()
    except Exception as exc:
        if is_db_unavailable_error(exc):
            return response
        app.logger.exception("Failed to write access log")
    return response


@app.before_request
def require_password_gate():
    if not is_password_gate_enabled():
        return None
    public_paths = {
        "/login",
        "/unlock",
        "/logout",
        "/api/demo-profiles",
        "/api/demo-profile/switch",
        "/api/h5/logout",
    }
    if request.path.startswith("/static/") or request.path in public_paths:
        return None
    if is_authenticated():
        return None
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "auth_required"}), 401
    return redirect(url_for("login", next=safe_next_target(request.full_path.rstrip("?"))))


@app.after_request
def log_access(response):
    return record_access(response)
