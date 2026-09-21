-- Complete tenant ownership for independent content and integration domains.
-- Existing rows are preserved; deletion of a tenant is blocked while domain
-- records still belong to it.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_insight_drafts_tenant'
    ) THEN
        ALTER TABLE tenant_insight_drafts
            ADD CONSTRAINT fk_insight_drafts_tenant
            FOREIGN KEY (tenant_slug)
            REFERENCES tenant_registry(tenant_slug)
            ON DELETE RESTRICT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_open_api_tokens_tenant'
    ) THEN
        ALTER TABLE open_api_tokens
            ADD CONSTRAINT fk_open_api_tokens_tenant
            FOREIGN KEY (tenant_slug)
            REFERENCES tenant_registry(tenant_slug)
            ON DELETE RESTRICT;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_tenant_insight_drafts_tenant_id
    ON tenant_insight_drafts(tenant_slug, draft_id);

CREATE INDEX IF NOT EXISTS idx_open_api_tokens_tenant_id
    ON open_api_tokens(tenant_slug, token_id);
