-- Open the existing forecast workflow for current deployments. This only
-- changes the feature flag; it does not alter schema or business records.
UPDATE app_settings
SET setting_value = jsonb_set(
    setting_value::jsonb,
    '{feature_flags,stock_forecast}',
    'true'::jsonb,
    true
),
updated_at = CURRENT_TIMESTAMP::text
WHERE setting_key = 'site_config'
  AND setting_value IS NOT NULL
  AND jsonb_typeof(setting_value::jsonb) = 'object';
