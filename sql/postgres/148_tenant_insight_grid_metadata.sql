-- Persist structured metadata for the stock Insight grid without mixing it
-- into article text or tenant configuration.
ALTER TABLE tenant_insight_drafts
    ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_tenant_insight_drafts_source_mode
    ON tenant_insight_drafts(tenant_slug, source_mode, updated_at DESC);
