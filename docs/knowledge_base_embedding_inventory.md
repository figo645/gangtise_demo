# Knowledge Base Embedding Inventory

This inventory records every current embedding-related event and storage path.
It is an implementation inventory, not knowledge content. The clean `main`
branch keeps these capabilities available for the next knowledge-base design,
but contains no historical knowledge records.

## Write Events

- `src/domain/ai_services.py:build_text_embedding`: shared embedding entry point.
- `src/domain/ai_services.py:_build_text_embedding_with_api`: remote embedding provider path.
- `src/domain/ai_services.py:_build_text_embedding_locally`: local embedding provider path.
- `src/domain/ai_services.py:save_manual_knowledge_entry`: manual text ingestion; creates a knowledge embedding record.
- `src/domain/ai_services.py:_store_knowledge_embedding_record`: persists knowledge chunks and vectors.
- `src/domain/ai_services.py:process_review_voice_upload`: voice review ingestion; transcribes and stores review voice vectors.
- `src/domain/ai_services.py:_store_review_voice_embedding_record`: persists voice transcript vectors.

## Read and Retrieval Events

- `src/domain/ai_services.py:fetch_live_knowledge_hub`: merges tenant knowledge configuration with database records.
- `src/domain/ai_services.py:list_admin_knowledge_items`: admin knowledge listing.
- `src/domain/ai_services.py:search_knowledge_embeddings`: vector similarity retrieval.
- `src/domain/ai_services.py:build_knowledge_query_response`: knowledge query orchestration.
- `src/domain/ai_services.py:hermes_tool_knowledge_search`: Hermes knowledge-search tool.
- `src/domain/market_services.py:knowledge_query_batch`: batch knowledge query task.
- `/api/kol/knowledge/query`, `/api/kol/knowledge/manual`, and `/api/kol/knowledge/ingest`: knowledge APIs that reach these paths.

## Storage and Initialization

- `knowledge_embeddings`: text knowledge chunks and their vector fields.
- `review_voice_embeddings`: review voice transcripts and their vector fields.
- `app_settings.site_config.tenants[].knowledge_hub_config.items`: tenant-level knowledge asset metadata.
- `app_settings.site_config.tenants[].review_snapshots[].knowledge_attachments`: review-to-knowledge references.
- `sql/postgres/001_enable_pgvector.sql`: pgvector extension.
- `sql/postgres/010_review_voice_embeddings.sql`, `011_review_voice_embeddings_alter_legacy_columns.sql`, and `012_review_voice_embeddings_pgvector.sql`: voice vector schema.
- `sql/postgres/020_knowledge_embeddings.sql` and `021_knowledge_embeddings_pgvector.sql`: text vector schema.

## Reset Status

`sql/postgres/108_reset_knowledge_base.sql` clears the two embedding tables,
tenant knowledge items, and review knowledge attachments. It does not drop the
schema or disable the code paths. The local database was verified after the
reset with zero rows in both embedding tables and zero tenant knowledge items.

Historical source files, database snapshots, data-bearing release packages,
and old knowledge-bearing reports were removed from `main` and remain in
`archive/knowledge-base-before-reset-20260830`.
