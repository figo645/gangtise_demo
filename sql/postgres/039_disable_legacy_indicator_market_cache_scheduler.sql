-- A legacy task created before the explicit Gangtise task names existed.
-- It uses the same real-indicator sync path and could re-enter EDB requests.
-- Keep it available for an intentional admin run, but never schedule it.
UPDATE admin_task_configs
SET schedule_type = 'manual',
    schedule_value = '',
    updated_at = CURRENT_TIMESTAMP::text
WHERE task_code = 'indicator_market_cache_sync'
  AND (schedule_type <> 'manual' OR COALESCE(schedule_value, '') <> '');
