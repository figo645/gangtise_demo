-- Persist every tenant insight draft as an independent record.
-- Legacy drafts embedded in site_config are copied once during migration.

CREATE TABLE IF NOT EXISTS tenant_insight_drafts (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL,
    draft_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    content_text TEXT NOT NULL,
    source_mode TEXT NOT NULL DEFAULT 'manual',
    access_mode TEXT NOT NULL DEFAULT 'public' CHECK (access_mode IN ('public', 'subscriber')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_slug, draft_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_insight_drafts_updated
ON tenant_insight_drafts(tenant_slug, updated_at DESC);

INSERT INTO tenant_insight_drafts (
    tenant_slug, draft_id, title, content_text, source_mode, access_mode, created_at, updated_at
)
SELECT
    tenant->>'slug',
    draft->>'id',
    COALESCE(draft->>'title', '未命名洞见草稿'),
    draft->>'content_text',
    COALESCE(draft->>'source_mode', 'manual'),
    CASE WHEN draft->>'access_mode' = 'subscriber' THEN 'subscriber' ELSE 'public' END,
    COALESCE(draft->>'created_at', CURRENT_TIMESTAMP::text),
    COALESCE(draft->>'updated_at', CURRENT_TIMESTAMP::text)
FROM app_settings settings
CROSS JOIN LATERAL jsonb_array_elements((settings.setting_value::jsonb)->'tenants') tenant
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(tenant->'insight_drafts', '[]'::jsonb)) draft
WHERE settings.setting_key = 'site_config'
  AND COALESCE(tenant->>'slug', '') <> ''
  AND COALESCE(draft->>'id', '') <> ''
  AND COALESCE(draft->>'content_text', '') <> ''
ON CONFLICT (tenant_slug, draft_id) DO NOTHING;
