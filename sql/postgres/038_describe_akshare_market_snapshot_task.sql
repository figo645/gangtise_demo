-- Keep the persisted task-center description aligned with the AKShare-only
-- implementation. Existing task records are not overwritten by defaults.
UPDATE admin_task_configs
SET task_name = '市场与热门行业快照同步',
    description = '每 5 分钟从 AKShare 采集标准指数与申万一级行业行情，写入 PostgreSQL 快照供 H5 展示；前台不直接访问外部行情源。',
    schedule_type = 'interval',
    schedule_value = '300',
    enabled = 1,
    updated_at = CURRENT_TIMESTAMP::text
WHERE task_code = 'market_snapshot_sync';
