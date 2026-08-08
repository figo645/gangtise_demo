-- Persisted K-line annotations created by KOL users on watchlist detail pages.

CREATE TABLE IF NOT EXISTS watchlist_kline_annotations (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL DEFAULT '',
    stock_code TEXT NOT NULL DEFAULT '',
    stock_name TEXT NOT NULL DEFAULT '',
    candle_index INTEGER NOT NULL DEFAULT 0,
    candle_date TEXT NOT NULL DEFAULT '',
    open_price DOUBLE PRECISION NOT NULL DEFAULT 0,
    high_price DOUBLE PRECISION NOT NULL DEFAULT 0,
    low_price DOUBLE PRECISION NOT NULL DEFAULT 0,
    close_price DOUBLE PRECISION NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    trigger TEXT NOT NULL DEFAULT '',
    created_by_user_id TEXT NOT NULL DEFAULT '',
    created_by_name TEXT NOT NULL DEFAULT '',
    source_client TEXT NOT NULL DEFAULT 'h5',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_watchlist_kline_annotations_tenant_stock_candle
ON watchlist_kline_annotations(tenant_slug, stock_code, candle_index);

CREATE INDEX IF NOT EXISTS idx_watchlist_kline_annotations_tenant_stock_updated
ON watchlist_kline_annotations(tenant_slug, stock_code, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_watchlist_kline_annotations_tenant_updated
ON watchlist_kline_annotations(tenant_slug, updated_at DESC);
