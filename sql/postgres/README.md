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
- Real market data needs Gangtise OpenAPI credentials on every deployed runtime. Copy [`.gangtise_openapi.env.example`](/Users/xuchenfei/PycharmProjects/gangtise_demo/.gangtise_openapi.env.example) to `/root/gangtise_openapi_credentials` (permissions `600`), populate `GANGTISE_ACCESS_KEY` and `GANGTISE_SECRET_KEY`, then restart `./start_daemon_app.sh`. Override the path with `GANGTISE_OPENAPI_CREDENTIALS_FILE`. Docker deployment reads the same protected file and passes only the required environment variables into the container.
- The daemon also starts a non-blocking real-market snapshot refresh. Existing snapshots remain visible during refresh; set `AUTO_MARKET_SNAPSHOT_SYNC=0` only to skip that refresh.
- Remote diagnosis command: [`scripts/check_market_data.sh`](/Users/xuchenfei/PycharmProjects/gangtise_demo/scripts/check_market_data.sh). It reports migration status, snapshot source and item counts, and exits with code `2` when no market snapshot is persisted.
- Mac-to-production one-shot release: [`scripts/deploy_sync_production.sh`](/Users/xuchenfei/PycharmProjects/gangtise_demo/scripts/deploy_sync_production.sh). It creates a custom-format PostgreSQL dump, uploads it over SSH, pulls the selected Git branch, restores into a temporary database, applies the existing incremental migrations, validates pgvector plus market master data and snapshots, then switches databases and starts the daemon. The previous production database is retained as a timestamped rollback database.
  Example: `PROD_SSH_TARGET=root@your-server PROD_APP_DIR=/opt/devsource/gangtise_demo CONFIRM_PRODUCTION_SYNC=YES ./scripts/deploy_sync_production.sh`.
- Full database pre-release preparation: [`scripts/prepare_database_release.sh`](/Users/xuchenfei/PycharmProjects/gangtise_demo/scripts/prepare_database_release.sh). This is the database-only release gate for staging and production: it exports the complete local PostgreSQL database, restores all schemas, tables, sequences, functions and rows into a remote temporary database, applies any new numbered migrations, validates the result, then switches the target database while retaining a rollback database. It does not pull code or start Python.
  Example for staging: `DATABASE_RELEASE_TARGET=staging REMOTE_SSH_TARGET=root@129.211.65.53 REMOTE_APP_DIR=/opt/devsource/gangtise_demo CONFIRM_DATABASE_REPLACE=YES ./scripts/prepare_database_release.sh`.
  `pg_dump` synchronizes the database contents, not cluster-level roles, passwords, `pg_hba.conf`, listen addresses or operating-system services. Those must be provisioned separately and the target application role must already exist.
- Database release is managed from the main application's Admin > 数据库发布 module. Copy [`.database_release.env.example`](/Users/xuchenfei/PycharmProjects/gangtise_demo/.database_release.env.example) to `.database_release.env`, configure the staging and production targets, then open the main Admin page and select “数据库发布”. The module permits only one concurrent database replacement and requires an explicit production confirmation.
- Staging defaults to direct PostgreSQL connection `129.211.65.53:5432`; production defaults to `47.105.48.193:5432`. Both use database `sprint_dashboard` and user `postgres` unless overridden. No SSH is used by the database release flow.
- Incremental packages are fixed under [`database_release_packages`](/Users/xuchenfei/PycharmProjects/gangtise_demo/database_release_packages): `YYYY-MM-DD/vX.Y.Z/release.env` plus either `master_data.sql` or `data.sql`. Select a package in the local Web controller to apply only that package; leave the selection at `全量数据库预发布` to replace the target with the complete local database. Each package is recorded by version, target environment, type and SHA-256 in `database_release_packages`.

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
- SQLite import is legacy-only and disabled by default. It can be explicitly enabled with `IMPORT_LEGACY_SQLITE=1`, but must not be used for routine production deployment because it truncates selected tables before import.
