ALTER TABLE users
ADD COLUMN IF NOT EXISTS compliance_acknowledged_at TEXT NOT NULL DEFAULT '';

ALTER TABLE users
ADD COLUMN IF NOT EXISTS compliance_version TEXT NOT NULL DEFAULT '';

ALTER TABLE users
ADD COLUMN IF NOT EXISTS h5_channel_label TEXT NOT NULL DEFAULT '';

ALTER TABLE users
ADD COLUMN IF NOT EXISTS h5_channel_selected_at TEXT NOT NULL DEFAULT '';

ALTER TABLE users
ADD COLUMN IF NOT EXISTS onboarding_completed_at TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_users_h5_channel_label
ON users(h5_channel_label);

CREATE INDEX IF NOT EXISTS idx_users_onboarding_completed_at
ON users(onboarding_completed_at);
