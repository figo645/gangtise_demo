"""Host-level singleton locks for long-running runtime roles.

PostgreSQL leases prevent duplicate work, but they do not prevent every
duplicate process from loading the full application into memory.  This lock
keeps one worker and one scheduler process per application instance on a host.
"""

import atexit
import os
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - supported deployments are POSIX
    fcntl = None


_lock_handles = {}


def acquire_runtime_role_lock(role):
    """Acquire a non-blocking singleton lock for ``role``.

    ``GANGTISE_RUNTIME_INSTANCE`` allows intentionally co-located staging and
    production processes to use separate lock namespaces.
    """
    if fcntl is None:
        raise RuntimeError("Runtime role locking requires a POSIX host with fcntl")

    instance = os.environ.get("GANGTISE_RUNTIME_INSTANCE", "gangtise-demo").strip() or "gangtise-demo"
    lock_dir = Path(os.environ.get("GANGTISE_RUNTIME_LOCK_DIR", "/tmp"))
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{instance}.{role}.lock"
    handle = lock_path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        print(
            f"{role} singleton already active for instance={instance}; "
            "exiting duplicate process.",
            flush=True,
        )
        return False

    handle.seek(0)
    handle.truncate()
    handle.write(f"pid={os.getpid()} role={role} instance={instance}\n")
    handle.flush()
    _lock_handles[role] = handle
    atexit.register(_release_runtime_role_lock, role)
    return True


def _release_runtime_role_lock(role):
    handle = _lock_handles.pop(role, None)
    if handle is None:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()
