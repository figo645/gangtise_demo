"""Dedicated PostgreSQL-leased admin task scheduler entry point."""

from src.runtime import app
from src.domain.core_services import run_scheduler_forever, startup_bootstrap


if __name__ == "__main__":
    startup_bootstrap(start_background=False)
    run_scheduler_forever()
