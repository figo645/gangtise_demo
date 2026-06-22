ALTER TABLE admin_task_configs
ADD COLUMN IF NOT EXISTS task_params_json TEXT NOT NULL DEFAULT '{}';
