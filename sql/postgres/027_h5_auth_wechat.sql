ALTER TABLE users
ADD COLUMN IF NOT EXISTS auth_provider TEXT NOT NULL DEFAULT 'local';

ALTER TABLE users
ADD COLUMN IF NOT EXISTS wechat_openid TEXT NOT NULL DEFAULT '';

ALTER TABLE users
ADD COLUMN IF NOT EXISTS wechat_unionid TEXT NOT NULL DEFAULT '';

ALTER TABLE users
ADD COLUMN IF NOT EXISTS wechat_nickname TEXT NOT NULL DEFAULT '';

ALTER TABLE users
ADD COLUMN IF NOT EXISTS wechat_bound_at TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_users_auth_provider
ON users(auth_provider);

CREATE INDEX IF NOT EXISTS idx_users_wechat_openid
ON users(wechat_openid);

CREATE INDEX IF NOT EXISTS idx_users_wechat_unionid
ON users(wechat_unionid);
