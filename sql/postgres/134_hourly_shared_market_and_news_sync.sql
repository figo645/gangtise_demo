-- Operational task configuration only. No schema or business data changes.
-- Market/industry snapshots run only during the China market session; news
-- sources refresh hourly throughout the day. Startup catch-up is performed by
-- the PostgreSQL-locked Scheduler, never by Web workers.
UPDATE admin_task_configs
SET task_name = 'Gangtise 市场与行业指标同步',
    task_type = 'sync_market_snapshot',
    schedule_type = 'daily',
    schedule_value = '09:30,12:00,14:00,15:30',
    enabled = 1,
    timeout_seconds = 900,
    description = '每日 09:30、12:00、14:00、15:30 统一从 Gangtise EDB 采集标准市场指数与申万一级行业，写入 PostgreSQL 共享快照供全部租户展示；个股 K 线与分时仅在用户查看标的详情时按需获取。',
    updated_at = CURRENT_TIMESTAMP
WHERE task_code = 'market_snapshot_sync';

UPDATE admin_task_configs
SET task_name = '新闻源采集同步',
    task_type = 'sync_news_sources',
    schedule_type = 'interval',
    schedule_value = '3600',
    enabled = 1,
    timeout_seconds = 300,
    description = '每小时采集全部合格新闻源并写入 PostgreSQL 共享快照；不调用 V4，首页与列表仅读取新闻源数据。',
    updated_at = CURRENT_TIMESTAMP
WHERE task_code = 'news_title_impact_sync';
