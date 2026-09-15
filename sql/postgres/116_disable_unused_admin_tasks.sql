-- Keep maintenance tasks available for explicit Admin runs, but prevent
-- background execution of retired or currently hidden capabilities.
UPDATE admin_task_configs
SET schedule_type = 'manual',
    schedule_value = '',
    enabled = 0,
    updated_at = CURRENT_TIMESTAMP::text
WHERE task_code IN (
    'indicator_prepare',
    'indicator_gangtise_openapi_sync',
    'smart_indicator_refresh'
);

-- The only globally scheduled data tasks are the AKShare market snapshot and
-- the shared news title classifier. Do not overwrite an Admin-customized
-- news schedule here; only migrate the original 15-minute default.
UPDATE admin_task_configs
SET schedule_type = 'daily',
    schedule_value = '10:15,14:15',
    enabled = 1,
    updated_at = CURRENT_TIMESTAMP::text
WHERE task_code = 'news_title_impact_sync'
  AND task_type = 'sync_news_title_classifications'
  AND schedule_type = 'interval'
  AND schedule_value = '900';
