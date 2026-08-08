-- Reusable Jira-style labels for tenant users. The paid-user label remains
-- synchronized with the existing paid sample field for revenue compatibility.

ALTER TABLE users ADD COLUMN IF NOT EXISTS labels_json TEXT NOT NULL DEFAULT '[]';

CREATE INDEX IF NOT EXISTS idx_users_tenant_role
ON users(tenant_slug, role, created_at DESC);
