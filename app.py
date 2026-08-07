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


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5001"))
    debug = os.environ.get("DEBUG", "1").lower() in {"1", "true", "yes", "y"}
    startup_bootstrap()
    app.run(host=host, port=port, debug=debug)
