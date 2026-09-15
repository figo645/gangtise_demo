-- Replace the temporary direct-search task with shared source collection plus
-- V4 title classification. The schedule remains two fixed runs per day.
UPDATE admin_task_configs
SET task_name = '新闻源采集与 V4 标题标注',
    task_type = 'sync_news_title_classifications',
    description = '每天两次采集全部合格新闻源记录，按批调用 V4 仅依据标题标注利好/利空/中性和行业；原始新闻链接与结果写入 PostgreSQL，供所有用户共享。',
    schedule_type = 'daily',
    schedule_value = '10:15,14:15',
    enabled = 1,
    updated_at = CURRENT_TIMESTAMP::text
WHERE task_code = 'news_title_impact_sync';
