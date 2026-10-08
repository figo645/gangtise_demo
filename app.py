import os
import subprocess
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


def start_direct_runtime_sidecars():
    """Start one Worker and Scheduler for a direct ``python3 app.py`` run.

    The daemon script sets ``GANGTISE_RUNTIME_ROLE=web`` and starts these
    roles itself, so this path is deliberately inactive for managed startup.
    The role locks in each sidecar make a second manual launch harmless.
    """
    if os.environ.get("GANGTISE_RUNTIME_ROLE"):
        return []
    if _is_enabled(os.environ.get("GANGTISE_DISABLE_AUTO_SIDECARS"), default=False):
        return []
    project_root = Path(__file__).resolve().parent
    runtime_env = os.environ.copy()
    runtime_env.update({
        "PYTHONPATH": os.pathsep.join(filter(None, [str(project_root), runtime_env.get("PYTHONPATH", "")])),
        "PYTHONUNBUFFERED": "1",
        "DEBUG": "0",
        "GANGTISE_RUNTIME_ENV": runtime_env.get("GANGTISE_RUNTIME_ENV", "local"),
    })
    started = []
    for role in ("worker", "scheduler"):
        entry = project_root / "src" / f"process_{role}.py"
        log_path = project_root / f"app.{role}.log"
        with log_path.open("a", encoding="utf-8") as log_handle:
            child_env = dict(runtime_env)
            child_env["GANGTISE_RUNTIME_ROLE"] = role
            process = subprocess.Popen(
                [sys.executable, str(entry)],
                cwd=str(project_root),
                env=child_env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        started.append({"role": role, "pid": process.pid})
        print(f"Started direct {role} sidecar (PID: {process.pid}).", flush=True)
    return started


if __name__ == "__main__":
    server_options = get_server_runtime_options()
    # ``python3 app.py`` is also used directly. Keep Gunicorn as its default
    # server, but make this entry point self-contained for queued user jobs.
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
        start_direct_runtime_sidecars()
        os.environ["GANGTISE_RUNTIME_ROLE"] = "web"
        startup_bootstrap(start_background=False)
        close_app_db_pool()
        # Every worker imports the complete research domain and keeps sizeable
        # in-process caches. Use one threaded worker by default on 16 GB hosts;
        # increase it only after measuring production RSS and latency.
        workers = max(1, int(os.environ.get("WEB_WORKERS", "1")))
        threads = max(1, int(os.environ.get("WEB_THREADS", "8")))
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
        # Share immutable imports copy-on-write rather than loading them in
        # every worker independently.
        if _is_enabled(os.environ.get("WEB_PRELOAD"), default=True):
            gunicorn_args.insert(-1, "--preload")
        os.execv(sys.executable, gunicorn_args)
    # The legacy single-process mode remains available for local and low
    # traffic deployments. Its background loops live in this process, so the
    # shell launcher must not start dedicated sidecars in the same mode.
    startup_bootstrap(start_background=True)
    server_options["threaded"] = _is_enabled(
        os.environ.get("FLASK_THREADED"), default=True
    )
    app.run(**server_options)
