"""Dedicated PostgreSQL-leased admin task scheduler entry point."""

from src.runtime_role_lock import acquire_runtime_role_lock


if __name__ == "__main__":
    if not acquire_runtime_role_lock("scheduler"):
        raise SystemExit(0)
    from src.domain.core_services import run_scheduler_forever, startup_bootstrap

    startup_bootstrap(start_background=False)
    run_scheduler_forever()
