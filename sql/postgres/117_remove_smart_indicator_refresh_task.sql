-- The smart-indicator background refresh is retired. Remove the Admin task
-- and its run history; indicator calculation functions remain available to
-- explicit product flows that still need them.
DELETE FROM admin_task_runs
WHERE task_code = 'smart_indicator_refresh';

DELETE FROM admin_task_configs
WHERE task_code = 'smart_indicator_refresh';
