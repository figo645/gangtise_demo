-- Current table definition for tenant knowledge embeddings.
CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL DEFAULT '',
    knowledge_id TEXT NOT NULL DEFAULT '',
    knowledge_type TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    body_text TEXT NOT NULL DEFAULT '',
    source_detail TEXT NOT NULL DEFAULT '',
    vector_namespace TEXT NOT NULL DEFAULT '',
    embedding_engine TEXT NOT NULL DEFAULT '',
    embedding_model TEXT NOT NULL DEFAULT '',
    embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_tenant_created
ON knowledge_embeddings(tenant_slug, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_knowledge_id
ON knowledge_embeddings(knowledge_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_namespace
ON knowledge_embeddings(vector_namespace, created_at DESC);
