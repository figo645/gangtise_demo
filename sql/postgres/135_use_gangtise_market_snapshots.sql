-- Operational task configuration only. No schema or business data changes.
UPDATE admin_task_configs
SET task_name = 'Gangtise 市场与行业指标同步',
    task_type = 'sync_market_snapshot',
    schedule_type = 'daily',
    schedule_value = '09:30,12:00,14:00,15:30',
    enabled = 1,
    timeout_seconds = 900,
    description = '每日 09:30、12:00、14:00、15:30 仅采集各大V已发布的标准市场指数与申万一级行业面板指标去重并集：A股及 .SWI 使用日K，海外指数使用固定 EDB ID；个股 K 线与分时仅按需获取，写入 PostgreSQL 共享快照供全部租户展示。',
    updated_at = CURRENT_TIMESTAMP
WHERE task_code = 'market_snapshot_sync';
