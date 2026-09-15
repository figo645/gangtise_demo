INSERT INTO admin_task_configs (
    task_code, task_name, task_group, task_type, description, task_params_json,
    schedule_type, schedule_value, enabled, timeout_seconds, created_at, updated_at
) VALUES (
    'daily_quiz_set_prepare', '每日问答盲盒题集准备', 'engagement', 'prepare_daily_quiz_set',
    '从数据库题库中稳定随机抽取当天 5 道股市知识题，供 H5 和 Web 粉丝端共享；不调用模型，不使用浏览器本地存储。', '{}',
    'daily', '08:00', 1, 120, CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT
)
ON CONFLICT (task_code) DO NOTHING;
