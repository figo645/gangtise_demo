-- Core seed entrypoint for application tables migrated from SQLite.
-- In the current migration strategy, real app data is imported by the
-- SQLite -> Postgres migration script instead of being hard-coded here.
-- Keep this file as a stable extension point for future pure-Postgres installs.

SELECT 'app_core_seed_ready' AS status;
