-- The legacy Wind industry-index EDB source duplicates the separate H5
-- Shenwan industry snapshot. Disable it without deleting historical records.
-- Both parent tasks are paused because each can invoke the EDB sync path.

UPDATE indicator_definitions
SET enabled = 0,
    updated_at = CURRENT_TIMESTAMP::text
WHERE indicator_code = 'source_industry_index';

UPDATE indicator_source_defs
SET enabled = 0,
    updated_at = CURRENT_TIMESTAMP::text
WHERE indicator_code = 'source_industry_index'
   OR source_code = 'source_industry_index';

UPDATE indicator_mapping_rules
SET enabled = 0,
    updated_at = CURRENT_TIMESTAMP::text
WHERE indicator_code = 'source_industry_index'
   OR source_code = 'source_industry_index';

UPDATE admin_task_configs
SET schedule_type = 'manual',
    schedule_value = '',
    updated_at = CURRENT_TIMESTAMP::text
WHERE task_code IN ('indicator_prepare', 'indicator_gangtise_openapi_sync')
  AND (schedule_type <> 'manual' OR COALESCE(schedule_value, '') <> '');
