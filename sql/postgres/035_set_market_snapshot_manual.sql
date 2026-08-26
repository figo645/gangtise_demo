-- Pause external market collection for this release. The task remains enabled
-- for an administrator to run manually from the task center. This migration is
-- recorded once, so a later Admin change to an interval is not overwritten.
UPDATE admin_task_configs
SET schedule_type = 'manual',
    schedule_value = '',
    updated_at = CURRENT_TIMESTAMP::text
WHERE task_code = 'market_snapshot_sync'
  AND (schedule_type <> 'manual' OR COALESCE(schedule_value, '') <> '');
