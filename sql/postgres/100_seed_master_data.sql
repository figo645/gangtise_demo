-- Master data seed entrypoint for Postgres / pgvector environment.
-- Keep this file idempotent.
--
-- Add platform baseline data here when needed, for example:
-- - tenant master rows
-- - default model registry rows if later moved into Postgres tables
-- - knowledge classification dictionaries
-- - workflow preset data
--
-- Current application stores most master config in SQLite `app_settings`,
-- so this seed file is intentionally left as a no-op placeholder.

SELECT 'master_data_seed_ready' AS status;
