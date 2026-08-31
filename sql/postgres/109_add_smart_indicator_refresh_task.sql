-- Recalculate persisted tenant smart indicators after upstream snapshots change.
-- The application reuses stored formulas and does not invoke an LLM here.
INSERT INTO admin_task_configs (
    task_code, task_name, task_group, task_type, description, task_params_json,
    schedule_type, schedule_value, enabled, timeout_seconds, created_at, updated_at
)
VALUES (
    'smart_indicator_refresh',
    '智能指标定时刷新',
    'indicator',
    'smart_indicator_refresh',
    '每 5 分钟检查底层指标快照，仅对数据已更新的租户智能指标复用已保存公式重算；不重新调用 LLM。',
    '{}',
    'interval',
    '300',
    1,
    900,
    CURRENT_TIMESTAMP::text,
    CURRENT_TIMESTAMP::text
)
ON CONFLICT (task_code) DO UPDATE SET
    task_name = EXCLUDED.task_name,
    task_group = EXCLUDED.task_group,
    task_type = EXCLUDED.task_type,
    description = EXCLUDED.description,
    schedule_type = EXCLUDED.schedule_type,
    schedule_value = EXCLUDED.schedule_value,
    enabled = EXCLUDED.enabled,
    timeout_seconds = EXCLUDED.timeout_seconds,
    updated_at = CURRENT_TIMESTAMP::text;
