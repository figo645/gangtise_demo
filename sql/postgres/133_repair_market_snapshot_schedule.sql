-- This is operational configuration, not a schema or business-data change.
-- The market dashboard must never continue serving a two-week-old snapshot
-- because an older deployment left its shared collection task disabled.
UPDATE admin_task_configs
SET task_name = 'AKShare 市场与行业指标同步',
    task_type = 'sync_market_snapshot',
    schedule_type = 'interval',
    schedule_value = '300',
    enabled = 1,
    timeout_seconds = 900,
    description = '每 5 分钟统一从 AKShare 采集热门行业涨跌 Top10、市场一览涨跌 Top10 与我的所有自选股涨跌 Top10 所需行情，写入 PostgreSQL 快照供 H5 展示；前台不直接访问外部行情源。',
    updated_at = CURRENT_TIMESTAMP
WHERE task_code = 'market_snapshot_sync';
