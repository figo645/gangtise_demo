-- Tenant-scoped bearer tokens for the public Insight publishing API.
-- The raw token is never stored directly: token_digest is used for request
-- authentication and token_ciphertext exists only for an Admin-authorized
-- reveal action using the application's encryption key.

CREATE TABLE IF NOT EXISTS open_api_tokens (
    id BIGSERIAL PRIMARY KEY,
    token_id TEXT NOT NULL UNIQUE,
    tenant_slug TEXT NOT NULL,
    token_name TEXT NOT NULL,
    token_prefix TEXT NOT NULL,
    token_digest TEXT NOT NULL UNIQUE,
    token_ciphertext TEXT NOT NULL,
    scopes_json JSONB NOT NULL DEFAULT '["insight.publish"]'::jsonb,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
    created_by_username TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    usage_count BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_open_api_tokens_tenant_status
    ON open_api_tokens(tenant_slug, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_open_api_tokens_digest
    ON open_api_tokens(token_digest);
