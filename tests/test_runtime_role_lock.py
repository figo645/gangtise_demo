import os
import subprocess
import sys
import time


ROOT = os.path.dirname(os.path.dirname(__file__))


def test_duplicate_role_process_exits_without_loading_application(tmp_path):
    env = os.environ.copy()
    env["GANGTISE_RUNTIME_LOCK_DIR"] = str(tmp_path)
    env["GANGTISE_RUNTIME_INSTANCE"] = "bdd"
    code = (
        "from src.runtime_role_lock import acquire_runtime_role_lock; "
        "assert acquire_runtime_role_lock('scheduler'); input()"
    )
    first = subprocess.Popen(
        [sys.executable, "-c", code], cwd=ROOT, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        lock_path = tmp_path / "bdd.scheduler.lock"
        for _ in range(50):
            if lock_path.exists() and "pid=" in lock_path.read_text(encoding="utf-8"):
                break
            time.sleep(0.01)
        else:
            raise AssertionError("first process did not acquire the role lock")
        second = subprocess.run(
            [sys.executable, "-c", "from src.runtime_role_lock import acquire_runtime_role_lock; print(acquire_runtime_role_lock('scheduler'))"],
            cwd=ROOT, env=env, capture_output=True, text=True, check=False,
        )
        assert second.returncode == 0
        assert "False" in second.stdout
        assert "singleton already active" in second.stdout
    finally:
        first.terminate()
        first.wait(timeout=5)


def test_web_worker_default_is_memory_conservative():
    source = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    assert 'os.environ.get("WEB_WORKERS", "2")' in source
