-- Persist each user's watchlist independently from market data and comments.

CREATE TABLE IF NOT EXISTS user_watchlist_items (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL DEFAULT '',
    user_profile_id TEXT NOT NULL DEFAULT '',
    stock_code TEXT NOT NULL DEFAULT '',
    stock_name TEXT NOT NULL DEFAULT '',
    market TEXT NOT NULL DEFAULT '',
    industry TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_watchlist_items_owner_stock
ON user_watchlist_items(tenant_slug, user_profile_id, stock_code);

CREATE INDEX IF NOT EXISTS idx_user_watchlist_items_owner_updated
ON user_watchlist_items(tenant_slug, user_profile_id, updated_at DESC, id DESC);
