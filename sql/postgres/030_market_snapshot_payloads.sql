-- Dedicated persisted snapshots for the H5 Market Overview and Hot Industries
-- views. Payloads remain intact so schema changes do not discard valid quotes.
CREATE TABLE IF NOT EXISTS market_snapshot_payloads (
    snapshot_type TEXT NOT NULL,
    snapshot_key TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    snapshot_version INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL DEFAULT '{}',
    collected_at TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (snapshot_type, snapshot_key)
);

CREATE INDEX IF NOT EXISTS idx_market_snapshot_payloads_updated
    ON market_snapshot_payloads (snapshot_type, updated_at DESC);

-- One-time, non-destructive migration of the legacy app_settings cache. It
-- only copies valid JSON snapshots and never deletes the legacy source.
INSERT INTO market_snapshot_payloads (
    snapshot_type, snapshot_key, source, snapshot_version, payload_json, collected_at
)
SELECT
    CASE
        WHEN setting_key = 'market_overview:standard_indices' THEN 'market_overview'
        WHEN setting_key = 'market_sector_overview:shenwan_level1' THEN 'market_sector_overview'
    END,
    CASE
        WHEN setting_key = 'market_overview:standard_indices' THEN 'standard_indices'
        WHEN setting_key = 'market_sector_overview:shenwan_level1' THEN 'shenwan_level1'
    END,
    COALESCE(setting_value::jsonb -> 'value' ->> 'source', ''),
    COALESCE((setting_value::jsonb -> 'value' ->> 'snapshot_version')::INTEGER, 1),
    (setting_value::jsonb -> 'value')::TEXT,
    COALESCE(setting_value::jsonb ->> 'cached_at', '')
FROM app_settings
WHERE setting_key IN (
    'market_overview:standard_indices',
    'market_sector_overview:shenwan_level1'
)
  AND setting_value IS NOT NULL
  AND setting_value <> ''
ON CONFLICT (snapshot_type, snapshot_key) DO NOTHING;
