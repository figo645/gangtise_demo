-- Allow each tenant user to keep an independent annotation on the same candle.
ALTER TABLE watchlist_kline_annotations
    ADD COLUMN IF NOT EXISTS created_by_role TEXT NOT NULL DEFAULT 'investor';

DROP INDEX IF EXISTS uq_watchlist_kline_annotations_tenant_stock_candle;

CREATE UNIQUE INDEX IF NOT EXISTS uq_watchlist_kline_annotations_tenant_stock_candle_user
ON watchlist_kline_annotations(tenant_slug, stock_code, candle_index, created_by_user_id);

CREATE INDEX IF NOT EXISTS idx_watchlist_kline_annotations_tenant_role_updated
ON watchlist_kline_annotations(tenant_slug, created_by_role, updated_at DESC);
