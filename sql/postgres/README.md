Postgres / pgvector DDL is split by purpose:

- `000_create_database.sql`: create the project database and ensure the login role exists
- `001_enable_pgvector.sql`: enable pgvector extension
- `002_app_core_tables.sql`: create all application core tables migrated from SQLite
- `004_schema_migrations.sql`: immutable database migration execution ledger
- `010_review_voice_embeddings.sql`: create review voice embedding table and indexes
- `011_review_voice_embeddings_alter_legacy_columns.sql`: legacy column backfill alters
- `012_review_voice_embeddings_pgvector.sql`: review voice pgvector column and vector index
- `020_knowledge_embeddings.sql`: create knowledge embedding table and indexes
- `021_knowledge_embeddings_pgvector.sql`: knowledge pgvector column
- `101_seed_app_core.sql`: app core seed entrypoint
- `100_seed_master_data.sql`: master data seed entrypoint
- `102_seed_market_sector_catalog.sql`: canonical Shenwan level-one industry master data
- `103_seed_market_index_catalog.sql`: Market Overview standard-index master data

Notes:

- Current SQL uses `vector(1536)`, matching the default `PGVECTOR_TARGET_DIM` in `app.py`.
- If you later change `PGVECTOR_TARGET_DIM`, these SQL files should be updated together.
- New or existing database update command (schema plus master data):
  ```bash
  PGHOST=127.0.0.1 PGPORT=5432 PGDATABASE=sprint_dashboard PGUSER=postgres PGPASSWORD='***' \
    ./scripts/apply_postgres_updates.sh
  ```
- Schema-only update command:
  ```bash
  ./scripts/apply_postgres_updates.sh --schema-only
  ```
- One-shot bootstrap for a new database (creates database and then calls the same incremental updater):
  [scripts/init_postgres_vector_db.sh](/Users/xuchenfei/PycharmProjects/gangtise_demo/scripts/init_postgres_vector_db.sh)
- Daemon deployment default: [`start_daemon_app.sh`](/Users/xuchenfei/PycharmProjects/gangtise_demo/start_daemon_app.sh) checks and automatically starts local PostgreSQL, then runs the same updater before restarting the application. Set `AUTO_START_POSTGRES=0` when PostgreSQL is managed externally; set `AUTO_DB_UPDATE=0` only for an emergency application-only restart.
- The daemon also starts a non-blocking real-market snapshot refresh. Existing snapshots remain visible during refresh; set `AUTO_MARKET_SNAPSHOT_SYNC=0` only to skip that refresh.
- Remote diagnosis command: [`scripts/check_market_data.sh`](/Users/xuchenfei/PycharmProjects/gangtise_demo/scripts/check_market_data.sh). It reports migration status, snapshot source and item counts, and exits with code `2` when no market snapshot is persisted.

## Change Control

- Add a new immutable numbered `.sql` file for every schema or master-data change. Do not edit an already applied file.
- `001`-`099` are schema migrations. `100` and above are master-data migrations.
- The updater records filename, SHA-256 checksum, scope, execution time and applied time in `schema_migrations`.
- If an applied file is modified, the updater stops with a checksum mismatch. Create the next numbered migration instead.
- Audit all changes with:
  ```sql
  SELECT migration_name, migration_scope, checksum_sha256, applied_at, execution_ms
  FROM schema_migrations
  ORDER BY applied_at, migration_name;
  ```
- SQLite historical data migration script:
  [scripts/migrate_sqlite_to_postgres.py](/Users/xuchenfei/PycharmProjects/gangtise_demo/scripts/migrate_sqlite_to_postgres.py)
