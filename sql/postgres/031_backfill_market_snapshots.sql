-- Retry the legacy-cache copy for databases where 030 ran before a legacy
-- snapshot existed. Never replace a non-empty dedicated snapshot.
INSERT INTO market_snapshot_payloads (
    snapshot_type, snapshot_key, source, snapshot_version, payload_json, collected_at
)
SELECT
    CASE WHEN setting_key = 'market_overview:standard_indices' THEN 'market_overview' ELSE 'market_sector_overview' END,
    CASE WHEN setting_key = 'market_overview:standard_indices' THEN 'standard_indices' ELSE 'shenwan_level1' END,
    COALESCE(setting_value::jsonb -> 'value' ->> 'source', ''),
    COALESCE((setting_value::jsonb -> 'value' ->> 'snapshot_version')::INTEGER, 1),
    (setting_value::jsonb -> 'value')::TEXT,
    COALESCE(setting_value::jsonb ->> 'cached_at', '')
FROM app_settings
WHERE setting_key IN ('market_overview:standard_indices', 'market_sector_overview:shenwan_level1')
  AND setting_value IS NOT NULL
  AND setting_value <> ''
  AND jsonb_array_length(COALESCE(setting_value::jsonb -> 'value' -> 'items', '[]'::jsonb)) > 0
ON CONFLICT (snapshot_type, snapshot_key) DO UPDATE SET
    source = EXCLUDED.source,
    snapshot_version = EXCLUDED.snapshot_version,
    payload_json = EXCLUDED.payload_json,
    collected_at = EXCLUDED.collected_at,
    updated_at = CURRENT_TIMESTAMP
WHERE jsonb_array_length(COALESCE(market_snapshot_payloads.payload_json::jsonb -> 'items', '[]'::jsonb)) = 0;
