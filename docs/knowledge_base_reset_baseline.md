# Knowledge Base Reset Baseline

This branch is an intentionally empty knowledge-base baseline.

## Preserved

- Knowledge-base domain code, APIs, workflow definitions, and database schema.
- Knowledge-base design documentation for the next implementation.
- Non-knowledge application data and product configuration.

## Removed from the clean main branch

- Historical knowledge source files and generated knowledge reports.
- Tracked SQLite and PostgreSQL backup files that could carry old knowledge rows.
- Historical data-bearing release packages under `database_release_packages/`.
- The tracked `gangtise_demo.db` runtime database.
- Existing rows in `knowledge_embeddings` and `review_voice_embeddings`.
- Tenant `knowledge_hub_config.items` and review `knowledge_attachments`.

## Reset migration

`sql/postgres/108_reset_knowledge_base.sql` is an immutable, transactional reset
for an existing PostgreSQL database. It clears knowledge data while preserving
the schema, users, market data, model configuration, and other product state.

The archive branch `archive/knowledge-base-before-reset-20260830` retains the
pre-reset repository state and all local uncommitted work that existed before
the reset.
