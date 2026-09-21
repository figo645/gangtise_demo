-- Normalize message recipients to account IDs while retaining the legacy
-- profile identifier for display and backwards-compatible API payloads.
ALTER TABLE tenant_message_threads
    ADD COLUMN IF NOT EXISTS user_id BIGINT;

ALTER TABLE tenant_broadcast_deliveries
    ADD COLUMN IF NOT EXISTS user_id BIGINT;

UPDATE tenant_message_threads thread
SET user_id = users.id
FROM users
WHERE thread.user_id IS NULL
  AND lower(users.tenant_slug) = lower(thread.tenant_slug)
  AND users.username = thread.user_profile_id;

UPDATE tenant_broadcast_deliveries delivery
SET user_id = users.id
FROM users
WHERE delivery.user_id IS NULL
  AND lower(users.tenant_slug) = lower(delivery.tenant_slug)
  AND users.username = delivery.user_profile_id;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_message_threads_user') THEN
        ALTER TABLE tenant_message_threads
            ADD CONSTRAINT fk_message_threads_user
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_broadcast_deliveries_user') THEN
        ALTER TABLE tenant_broadcast_deliveries
            ADD CONSTRAINT fk_broadcast_deliveries_user
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_tenant_message_threads_user_id
    ON tenant_message_threads(tenant_slug, user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenant_broadcast_deliveries_user_id
    ON tenant_broadcast_deliveries(tenant_slug, user_id, delivered_at DESC);
