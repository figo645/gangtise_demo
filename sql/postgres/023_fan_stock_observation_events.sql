-- Fan stock observation events for KOL workbench analytics.

CREATE TABLE IF NOT EXISTS fan_stock_observation_events (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL DEFAULT '',
    user_profile_id TEXT NOT NULL DEFAULT '',
    user_role TEXT NOT NULL DEFAULT '',
    stock_code TEXT NOT NULL DEFAULT '',
    stock_name TEXT NOT NULL DEFAULT '',
    sector_name TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL DEFAULT 'watchlist_detail_view',
    entry_point TEXT NOT NULL DEFAULT '',
    source_detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fan_stock_observation_tenant_created
ON fan_stock_observation_events(tenant_slug, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_fan_stock_observation_stock_created
ON fan_stock_observation_events(tenant_slug, stock_code, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_fan_stock_observation_user_created
ON fan_stock_observation_events(tenant_slug, user_profile_id, created_at DESC);
