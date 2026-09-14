-- Fan commerce: subscription products, auditable orders, entitlements and
-- tenant-scoped QR acquisition links. Payment confirmation is deliberately
-- separate from order creation so pending orders can never unlock content.

CREATE TABLE IF NOT EXISTS tenant_subscription_products (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL,
    product_code TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    billing_period_days INTEGER NOT NULL CHECK (billing_period_days > 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft', 'active', 'archived')),
    created_by_user_id BIGINT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_slug, product_code)
);

CREATE INDEX IF NOT EXISTS idx_tenant_subscription_products_active
ON tenant_subscription_products(tenant_slug, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS fan_payment_orders (
    id BIGSERIAL PRIMARY KEY,
    order_no TEXT NOT NULL UNIQUE,
    tenant_slug TEXT NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    product_id BIGINT NOT NULL REFERENCES tenant_subscription_products(id) ON DELETE RESTRICT,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    currency TEXT NOT NULL DEFAULT 'CNY',
    payment_channel TEXT NOT NULL DEFAULT 'manual_transfer',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'cancelled', 'expired', 'refunded')),
    provider_trade_no TEXT NOT NULL DEFAULT '',
    payment_reference TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    paid_at TEXT NOT NULL DEFAULT '',
    confirmed_by_user_id BIGINT,
    confirmed_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fan_payment_orders_tenant_status
ON fan_payment_orders(tenant_slug, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fan_payment_orders_user_status
ON fan_payment_orders(user_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS fan_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    product_id BIGINT NOT NULL REFERENCES tenant_subscription_products(id) ON DELETE RESTRICT,
    order_id BIGINT NOT NULL UNIQUE REFERENCES fan_payment_orders(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'expired', 'cancelled', 'refunded')),
    starts_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fan_subscriptions_access
ON fan_subscriptions(tenant_slug, user_id, status, expires_at DESC);

CREATE TABLE IF NOT EXISTS tenant_fan_qr_invites (
    id BIGSERIAL PRIMARY KEY,
    invite_token TEXT NOT NULL UNIQUE,
    tenant_slug TEXT NOT NULL,
    source_label TEXT NOT NULL DEFAULT '扫码导入',
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'expired')),
    max_uses INTEGER NOT NULL DEFAULT 0 CHECK (max_uses >= 0),
    used_count INTEGER NOT NULL DEFAULT 0 CHECK (used_count >= 0),
    expires_at TEXT NOT NULL DEFAULT '',
    created_by_user_id BIGINT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tenant_fan_qr_invites_tenant_status
ON tenant_fan_qr_invites(tenant_slug, status, created_at DESC);

CREATE TABLE IF NOT EXISTS tenant_fan_qr_invite_claims (
    id BIGSERIAL PRIMARY KEY,
    invite_id BIGINT NOT NULL REFERENCES tenant_fan_qr_invites(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    tenant_slug TEXT NOT NULL,
    claimed_at TEXT NOT NULL,
    UNIQUE (invite_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_fan_qr_invite_claims_tenant
ON tenant_fan_qr_invite_claims(tenant_slug, claimed_at DESC);
