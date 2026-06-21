Postgres / pgvector DDL is split by purpose:

- `000_create_database.sql`: create the project database and ensure the login role exists
- `001_enable_pgvector.sql`: enable pgvector extension
- `002_app_core_tables.sql`: create all application core tables migrated from SQLite
- `010_review_voice_embeddings.sql`: create review voice embedding table and indexes
- `011_review_voice_embeddings_alter_legacy_columns.sql`: legacy column backfill alters
- `012_review_voice_embeddings_pgvector.sql`: review voice pgvector column and vector index
- `020_knowledge_embeddings.sql`: create knowledge embedding table and indexes
- `021_knowledge_embeddings_pgvector.sql`: knowledge pgvector column
- `101_seed_app_core.sql`: app core seed entrypoint
- `100_seed_master_data.sql`: master data seed entrypoint

Notes:

- Current SQL uses `vector(1536)`, matching the default `PGVECTOR_TARGET_DIM` in `app.py`.
- If you later change `PGVECTOR_TARGET_DIM`, these SQL files should be updated together.
- Recommended execution order:
  `000_create_database.sql` -> connect to `sprint_dashboard` -> `001_enable_pgvector.sql` -> remaining table/index/alter SQL.
- One-shot shell bootstrap:
  [scripts/init_postgres_vector_db.sh](/Users/xuchenfei/PycharmProjects/gangtise_demo/scripts/init_postgres_vector_db.sh)
- SQLite historical data migration script:
  [scripts/migrate_sqlite_to_postgres.py](/Users/xuchenfei/PycharmProjects/gangtise_demo/scripts/migrate_sqlite_to_postgres.py)
