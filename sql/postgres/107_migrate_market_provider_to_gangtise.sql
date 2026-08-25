-- Switch the persisted Market Overview and Hot Industries catalog metadata to
-- the verified Gangtise contracts. Quote snapshots are rebuilt by the
-- market_snapshot_sync task and are intentionally not fabricated here.

UPDATE app_settings
SET setting_value = jsonb_set(
        jsonb_set(
            jsonb_set(
                setting_value::jsonb,
                '{quote_provider}',
                to_jsonb('Gangtise OpenAPI'::TEXT),
                true
            ),
            '{quote_endpoint}',
            to_jsonb('/application/open-quote/kline/daily'::TEXT),
            true
        ),
        '{items}',
        (
            SELECT COALESCE(
                jsonb_agg(
                    CASE
                        WHEN RIGHT(COALESCE(item->>'code', ''), 4) = '.SWI' THEN item
                        ELSE jsonb_set(item, '{code}', to_jsonb((item->>'code') || '.SWI'), true)
                    END
                ),
                '[]'::jsonb
            )
            FROM jsonb_array_elements(setting_value::jsonb->'items') AS item
        ),
        true
    )::TEXT,
    updated_at = CURRENT_TIMESTAMP::TEXT
WHERE setting_key = 'master_data:market_sector_catalog:shenwan_level1'
  AND setting_value IS NOT NULL
  AND setting_value <> '';


UPDATE app_settings
SET setting_value = jsonb_set(
        jsonb_set(
            setting_value::jsonb,
            '{quote_provider}',
            to_jsonb('Gangtise OpenAPI'::TEXT),
            true
        ),
        '{quote_endpoint}',
        to_jsonb('/application/open-quote/kline/daily'::TEXT),
        true
    )::TEXT,
    updated_at = CURRENT_TIMESTAMP::TEXT
WHERE setting_key = 'master_data:market_index_catalog:standard'
  AND setting_value IS NOT NULL
  AND setting_value <> '';
