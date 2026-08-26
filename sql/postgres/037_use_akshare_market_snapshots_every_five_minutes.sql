-- Market Overview and Hot Industries are AKShare-only PostgreSQL snapshots.
-- H5 reads the persisted snapshot and never calls AKShare or Gangtise.
UPDATE admin_task_configs
SET schedule_type = 'interval',
    schedule_value = '300',
    enabled = 1,
    updated_at = CURRENT_TIMESTAMP::text
WHERE task_code = 'market_snapshot_sync';
