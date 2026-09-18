-- Operational metadata only. No schema or business-data changes.
-- Market and .SWI panels use today's last valid minute quote during the
-- A-share session, with the prior daily close as the comparison baseline.
UPDATE admin_task_configs
SET description = '每日 09:30、12:00、14:00、15:30 执行共享兜底同步；盘中页面读取发现快照超过 5 分钟或行情仍停留在上一交易日时，仅排队一次按需共享刷新。A股指数与申万一级行业（.SWI）优先采用分钟线最新点，日K仅作为前收与分钟线不可用时的明确降级数据。',
    updated_at = CURRENT_TIMESTAMP
WHERE task_code = 'market_snapshot_sync';
