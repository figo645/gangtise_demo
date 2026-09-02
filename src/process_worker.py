"""Dedicated user async-job worker entry point."""

from src.domain.core_services import run_user_async_job_worker_forever, startup_bootstrap


if __name__ == "__main__":
    startup_bootstrap(start_background=False)
    run_user_async_job_worker_forever()
