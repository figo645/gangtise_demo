-- Operational task configuration only. No schema or business data changes.
UPDATE admin_task_configs
SET task_name = 'Gangtise 市场与行业指标同步',
    task_type = 'sync_market_snapshot',
    schedule_type = 'daily',
    schedule_value = '09:30,12:00,14:00,15:30',
    enabled = 1,
    timeout_seconds = 900,
    description = '每日 09:30、12:00、14:00、15:30 统一从 Gangtise EDB 采集标准市场指数与申万一级行业，写入 PostgreSQL 共享快照供全部租户展示；大V手动执行复用同一平台任务与运行记录。',
    updated_at = CURRENT_TIMESTAMP
WHERE task_code = 'market_snapshot_sync';
