-- Make the single AKShare market/industry indicator collector explicit in
-- Admin without creating a second data acquisition path.
UPDATE admin_task_configs
SET task_name = 'AKShare 市场与行业指标同步',
    description = '每 5 分钟统一从 AKShare 采集市场一览与热门行业指标，写入 PostgreSQL 快照供 H5 展示；前台不直接访问外部行情源。',
    updated_at = CURRENT_TIMESTAMP::text
WHERE task_code = 'market_snapshot_sync'
  AND task_type = 'sync_market_snapshot';
