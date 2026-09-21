-- Knowledge documents are the source of truth; vector rows are only indexes.
CREATE TABLE IF NOT EXISTS tenant_knowledge_documents (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL,
    document_id TEXT NOT NULL,
    document_type TEXT NOT NULL DEFAULT 'manual',
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    content_text TEXT NOT NULL DEFAULT '',
    content_html TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    source_detail TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    document_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (tenant_slug, document_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_knowledge_documents_updated
    ON tenant_knowledge_documents(tenant_slug, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenant_knowledge_documents_type
    ON tenant_knowledge_documents(tenant_slug, document_type, updated_at DESC);

INSERT INTO tenant_knowledge_documents (
    tenant_slug, document_id, document_type, title, summary, content_text,
    content_html, source, source_detail, status, document_json
)
SELECT tenant->>'slug', item->>'id', COALESCE(item->>'type', 'manual'),
       COALESCE(item->>'title', ''), COALESCE(item->>'summary', ''),
       COALESCE(item->>'body', item->>'raw_input', ''), COALESCE(item->>'raw_html', ''),
       COALESCE(item->>'source', ''), COALESCE(item->>'source_detail', ''),
       COALESCE(item->>'status', ''), item
FROM app_settings settings
CROSS JOIN LATERAL jsonb_array_elements(COALESCE((settings.setting_value::jsonb)->'tenants', '[]'::jsonb)) tenant
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(tenant->'knowledge_hub_config'->'items', '[]'::jsonb)) item
WHERE settings.setting_key = 'site_config'
  AND COALESCE(tenant->>'slug', '') <> '' AND COALESCE(item->>'id', '') <> ''
ON CONFLICT (tenant_slug, document_id) DO NOTHING;
