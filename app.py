import os
import sys
import tempfile
from pathlib import Path


def _ensure_tempdir():
    candidates = (
        os.environ.get("TMPDIR"),
        "/private/tmp",
        "/tmp",
        "/var/tmp",
    )
    for candidate in candidates:
        if not candidate:
            continue
        try:
            Path(candidate).mkdir(parents=True, exist_ok=True)
            if os.access(candidate, os.W_OK | os.X_OK):
                os.environ["TMPDIR"] = candidate
                os.environ.setdefault("TEMP", candidate)
                os.environ.setdefault("TMP", candidate)
                tempfile.tempdir = candidate
                return candidate
        except Exception:
            continue
    return None


_ensure_tempdir()

from src.runtime import app
from src.domain.core_services import close_app_db_pool, startup_bootstrap
import src.app_setup  # noqa: F401


def _is_enabled(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def get_server_runtime_options():
    """Keep the integrated release controller stable during local debugging.

    Database release jobs continuously update `.deploy` state and log files.
    Werkzeug's file reloader can restart the only web process while the Admin
    POST is still open, which surfaces in the browser as `Failed to fetch`.
    Developers can explicitly opt back into reload with FLASK_USE_RELOADER=1.
    """
    return {
        "host": os.environ.get("HOST", "0.0.0.0"),
        "port": int(os.environ.get("PORT", "5001")),
        "debug": _is_enabled(os.environ.get("DEBUG", "1")),
        "use_reloader": _is_enabled(os.environ.get("FLASK_USE_RELOADER"), default=False),
    }


if __name__ == "__main__":
    server_options = get_server_runtime_options()
    server_mode = str(os.environ.get("APP_SERVER", "gunicorn")).strip().lower()
    if server_mode in {"gunicorn", "prod", "production"}:
        if not os.path.exists(os.path.join(os.path.dirname(sys.executable), "gunicorn")):
            try:
                import gunicorn  # noqa: F401
            except Exception as exc:
                raise SystemExit(
                    "Gunicorn is required for startup. Install requirements.txt before serving traffic, "
                    "or explicitly set APP_SERVER=flask for development only."
                ) from exc
        # Bootstrap is run before exec so it happens once, while the Gunicorn
        # workers begin with no inherited PostgreSQL sockets. Running the
        # module through this interpreter prevents a global Gunicorn binary
        # from silently using a different Python environment.
        startup_bootstrap(start_background=False)
        close_app_db_pool()
        workers = max(1, int(os.environ.get("WEB_WORKERS", "3")))
        threads = max(1, int(os.environ.get("WEB_THREADS", "4")))
        bind = f"{server_options['host']}:{server_options['port']}"
        gunicorn_args = [
            sys.executable,
            "-m", "gunicorn",
            "--bind", bind,
            "--workers", str(workers),
            "--threads", str(threads),
            "--worker-class", "gthread",
            "--timeout", os.environ.get("WEB_TIMEOUT_SECONDS", "180"),
            "--graceful-timeout", os.environ.get("WEB_GRACEFUL_TIMEOUT_SECONDS", "30"),
            "--keep-alive", os.environ.get("WEB_KEEPALIVE_SECONDS", "5"),
            "--max-requests", os.environ.get("WEB_MAX_REQUESTS", "1000"),
            "--max-requests-jitter", os.environ.get("WEB_MAX_REQUESTS_JITTER", "100"),
            "--access-logfile", "-",
            "--error-logfile", "-",
            "wsgi:app",
        ]
        os.execv(sys.executable, gunicorn_args)
    startup_bootstrap(start_background=True)
    app.run(**server_options)
