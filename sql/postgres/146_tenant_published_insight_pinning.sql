-- Pinning is an explicit editorial action. New insights remain unpinned.
ALTER TABLE tenant_published_insights
    ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE tenant_published_insights
    ADD COLUMN IF NOT EXISTS pinned_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_tenant_published_insights_editorial_feed
    ON tenant_published_insights(
        tenant_slug,
        is_pinned DESC,
        pinned_at DESC,
        published_date DESC,
        published_at DESC,
        imported_at DESC,
        id DESC
    );
