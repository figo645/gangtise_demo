-- Distinguish the two tenant registration paths shown on the public login page.
ALTER TABLE tenant_fan_qr_invites
    ADD COLUMN IF NOT EXISTS registration_type TEXT NOT NULL DEFAULT 'free';

UPDATE tenant_fan_qr_invites
SET registration_type = 'free'
WHERE registration_type IS NULL OR registration_type NOT IN ('free', 'subscriber');

ALTER TABLE tenant_fan_qr_invites
    DROP CONSTRAINT IF EXISTS tenant_fan_qr_invites_registration_type_check;
ALTER TABLE tenant_fan_qr_invites
    ADD CONSTRAINT tenant_fan_qr_invites_registration_type_check
    CHECK (registration_type IN ('free', 'subscriber'));

CREATE INDEX IF NOT EXISTS idx_tenant_fan_qr_invites_registration_type
ON tenant_fan_qr_invites(tenant_slug, registration_type, status, created_at DESC);
