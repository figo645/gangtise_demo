-- Canonical security master used to resolve stock names and codes.
-- Market quotes and K-lines are still fetched from Gangtise; this table only
-- stores instrument identity and searchable metadata.

CREATE TABLE IF NOT EXISTS security_master (
    id BIGSERIAL PRIMARY KEY,
    security_code TEXT NOT NULL UNIQUE,
    stock_code TEXT NOT NULL,
    name TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT '',
    industry TEXT NOT NULL DEFAULT '',
    security_type TEXT NOT NULL DEFAULT 'stock',
    search_aliases TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'gangtise_openapi',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_security_master_market_code
ON security_master(market, stock_code);

CREATE INDEX IF NOT EXISTS idx_security_master_name
ON security_master(name);

CREATE INDEX IF NOT EXISTS idx_security_master_active_name
ON security_master(is_active, name);
