-- Published Insights are business content, not tenant configuration.  Keep the
-- legacy JSON intact for rollback compatibility while backfilling it once.
CREATE TABLE IF NOT EXISTS tenant_published_insights (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL,
    insight_id TEXT NOT NULL,
    dav_id TEXT NOT NULL DEFAULT '',
    external_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    content_text TEXT NOT NULL,
    content_html TEXT NOT NULL DEFAULT '',
    access_mode TEXT NOT NULL DEFAULT 'public'
        CHECK (access_mode IN ('public', 'subscriber')),
    source_mode TEXT NOT NULL DEFAULT 'manual',
    published_date DATE NOT NULL,
    published_at TEXT NOT NULL DEFAULT '',
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    view_count BIGINT NOT NULL DEFAULT 0,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (tenant_slug, insight_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_published_insights_external_id
    ON tenant_published_insights(tenant_slug, external_id)
    WHERE external_id <> '';

CREATE INDEX IF NOT EXISTS idx_tenant_published_insights_feed
    ON tenant_published_insights(tenant_slug, published_date DESC, published_at DESC, imported_at DESC, id DESC);

INSERT INTO tenant_published_insights (
    tenant_slug, insight_id, title, content_text, content_html, access_mode,
    source_mode, published_date, published_at, view_count, payload_json
)
SELECT
    tenant->>'slug',
    COALESCE(NULLIF(snapshot->>'id', ''),
        (tenant->>'slug') || '-legacy-insight-' || md5(snapshot::text)),
    COALESCE(NULLIF(snapshot->>'title', ''), '未命名洞见'),
    COALESCE(NULLIF(snapshot->>'content_text', ''), NULLIF(snapshot->>'content', ''),
        NULLIF(snapshot->>'summary', ''), '暂无正文'),
    COALESCE(snapshot->>'content_html', ''),
    CASE WHEN snapshot->>'access_mode' = 'subscriber' THEN 'subscriber' ELSE 'public' END,
    COALESCE(NULLIF(snapshot->>'source_mode', ''), 'manual'),
    CASE
        WHEN COALESCE(snapshot->>'published_at', snapshot->>'time', '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
        THEN substring(COALESCE(snapshot->>'published_at', snapshot->>'time') from '^[0-9]{4}-[0-9]{2}-[0-9]{2}')::date
        ELSE CURRENT_DATE
    END,
    COALESCE(snapshot->>'published_at', snapshot->>'time', ''),
    CASE WHEN COALESCE(snapshot->>'view_count', '') ~ '^\\d+$' THEN (snapshot->>'view_count')::bigint ELSE 0 END,
    snapshot
FROM app_settings settings
CROSS JOIN LATERAL jsonb_array_elements(COALESCE((settings.setting_value::jsonb)->'tenants', '[]'::jsonb)) tenant
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(tenant->'review_snapshots', '[]'::jsonb)) snapshot
WHERE settings.setting_key = 'site_config'
  AND COALESCE(tenant->>'slug', '') <> ''
  AND jsonb_typeof(snapshot) = 'object'
ON CONFLICT (tenant_slug, insight_id) DO NOTHING;
