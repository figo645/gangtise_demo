-- Traceable simulated fan accounts and their watchlist demonstration data.
-- All records created by the release controller share a batch code so they can
-- be reviewed and deleted without touching real tenant activity.

CREATE TABLE IF NOT EXISTS simulated_data_batches (
    batch_code TEXT PRIMARY KEY,
    tenant_slug TEXT NOT NULL DEFAULT '',
    batch_label TEXT NOT NULL DEFAULT '模拟数据',
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'database_release_web',
    notes TEXT NOT NULL DEFAULT ''
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_simulated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS simulation_batch_code TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS simulation_label TEXT NOT NULL DEFAULT '';

ALTER TABLE fan_stock_observation_events ADD COLUMN IF NOT EXISTS is_simulated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE fan_stock_observation_events ADD COLUMN IF NOT EXISTS simulation_batch_code TEXT NOT NULL DEFAULT '';
ALTER TABLE fan_stock_observation_events ADD COLUMN IF NOT EXISTS simulation_label TEXT NOT NULL DEFAULT '';

ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS is_simulated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS simulation_batch_code TEXT NOT NULL DEFAULT '';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS simulation_label TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_simulated_data_batches_tenant_created
ON simulated_data_batches(tenant_slug, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_users_simulation_batch
ON users(simulation_batch_code, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_fan_stock_observation_simulation_batch
ON fan_stock_observation_events(simulation_batch_code, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_watchlist_comments_simulation_batch
ON watchlist_comments(simulation_batch_code, created_at DESC);
