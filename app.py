import os
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
from src.domain.core_services import startup_bootstrap
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
    startup_bootstrap()
    app.run(**server_options)
