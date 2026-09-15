-- QR registration is now an available account-acquisition capability.
-- Admin can still turn it off later through the feature switch.
UPDATE app_settings
SET setting_value = jsonb_set(
    setting_value::jsonb,
    '{feature_flags,fan_qr_import}',
    'true'::jsonb,
    true
),
updated_at = CURRENT_TIMESTAMP::text
WHERE setting_key = 'site_config'
  AND setting_value IS NOT NULL
  AND jsonb_typeof(setting_value::jsonb) = 'object';
