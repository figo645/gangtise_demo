-- Shared Gangtise noon/night finance broadcast.
-- One scheduler run fetches the report once and fans it out per tenant.
INSERT INTO admin_task_configs (
    task_code, task_name, task_group, task_type, description, task_params_json,
    schedule_type, schedule_value, enabled, timeout_seconds, created_at, updated_at
) VALUES (
    'daily_finance_broadcast', '每日午间与晚间财经播报', 'engagement', 'sync_daily_finance_broadcast',
    '每天 12:30 和 19:00 从 Gangtise 热点日报接口获取午报或晚报，生成智能体播报洞见并推送给当前租户全部粉丝；凌晨至 08:00 手动执行归属前一天晚报。', '{}',
    'daily', '12:30,19:00', 1, 300, CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT
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
    updated_at = CURRENT_TIMESTAMP::TEXT;
