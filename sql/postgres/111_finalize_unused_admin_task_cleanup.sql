-- Finalize cleanup after an older application process recreated obsolete
-- task-center defaults while migration 110 was being applied.
DELETE FROM admin_task_configs
WHERE task_code IN (
    'indicator_clean_pipeline',
    'indicator_mock_seed',
    'indicator_raw_landing',
    'knowledge_query_batch',
    'knowledge_sync_manual',
    'review_publish_embed'
)
AND NOT EXISTS (
    SELECT 1
    FROM admin_task_runs
    WHERE admin_task_runs.task_code = admin_task_configs.task_code
);
