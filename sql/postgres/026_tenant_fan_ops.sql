-- Tenant fan ops extensions: pricing, paid sample labels, and tenant/user aware access logs.

ALTER TABLE users ADD COLUMN IF NOT EXISTS source_label TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_paid_sample INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS paid_sample_marked_at TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS paid_sample_note TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_users_tenant_role_paid
ON users(tenant_slug, role, is_paid_sample, created_at DESC);

ALTER TABLE access_logs ADD COLUMN IF NOT EXISTS tenant_slug TEXT NOT NULL DEFAULT '';
ALTER TABLE access_logs ADD COLUMN IF NOT EXISTS user_profile_id TEXT NOT NULL DEFAULT '';
ALTER TABLE access_logs ADD COLUMN IF NOT EXISTS user_role TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_access_logs_tenant_created_at
ON access_logs(tenant_slug, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_access_logs_tenant_user_role
ON access_logs(tenant_slug, user_role, created_at DESC);
