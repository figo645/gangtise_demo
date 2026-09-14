-- Establish canonical tenant and user references without breaking legacy text
-- fields. Existing *_slug and *_profile_id columns remain compatibility fields
-- until all readers have migrated to the new identifiers.

CREATE TABLE IF NOT EXISTS tenant_registry (
    tenant_slug TEXT PRIMARY KEY,
    tenant_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Runtime code validates these columns; schema changes remain migration-only.
ALTER TABLE knowledge_embeddings
    ADD COLUMN IF NOT EXISTS is_simulated INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS simulation_label TEXT NOT NULL DEFAULT '';
ALTER TABLE review_voice_embeddings
    ADD COLUMN IF NOT EXISTS is_simulated INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS simulation_label TEXT NOT NULL DEFAULT '';

INSERT INTO tenant_registry (tenant_slug, tenant_name, created_at, updated_at)
SELECT DISTINCT
    lower(trim(tenant->>'slug')),
    COALESCE(tenant->>'name', tenant->>'advisor', tenant->>'slug', ''),
    CURRENT_TIMESTAMP::text,
    CURRENT_TIMESTAMP::text
FROM app_settings settings
CROSS JOIN LATERAL jsonb_array_elements(
    CASE
        WHEN jsonb_typeof(settings.setting_value::jsonb->'tenants') = 'array'
        THEN settings.setting_value::jsonb->'tenants'
        ELSE '[]'::jsonb
    END
) tenant
WHERE settings.setting_key = 'site_config'
  AND lower(trim(COALESCE(tenant->>'slug', ''))) <> ''
ON CONFLICT (tenant_slug) DO UPDATE SET
    tenant_name = CASE
        WHEN EXCLUDED.tenant_name <> '' THEN EXCLUDED.tenant_name
        ELSE tenant_registry.tenant_name
    END,
    updated_at = CURRENT_TIMESTAMP::text;

-- Preserve rows created before site_config contained a tenant catalog.
INSERT INTO tenant_registry (tenant_slug, tenant_name, created_at, updated_at)
SELECT DISTINCT lower(trim(tenant_slug)), '', CURRENT_TIMESTAMP::text, CURRENT_TIMESTAMP::text
FROM users
WHERE trim(COALESCE(tenant_slug, '')) <> ''
ON CONFLICT (tenant_slug) DO NOTHING;

ALTER TABLE user_watchlist_items
    ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE watchlist_comments
    ADD COLUMN IF NOT EXISTS created_by_user_pk BIGINT;
ALTER TABLE watchlist_kline_annotations
    ADD COLUMN IF NOT EXISTS created_by_user_pk BIGINT;
ALTER TABLE fan_stock_observation_events
    ADD COLUMN IF NOT EXISTS user_id BIGINT;

UPDATE user_watchlist_items item
SET user_id = users.id
FROM users
WHERE item.user_id IS NULL
  AND lower(users.tenant_slug) = lower(item.tenant_slug)
  AND users.username = item.user_profile_id;

UPDATE watchlist_comments item
SET created_by_user_pk = users.id
FROM users
WHERE item.created_by_user_pk IS NULL
  AND lower(users.tenant_slug) = lower(item.tenant_slug)
  AND users.username = item.created_by_user_id;

UPDATE watchlist_kline_annotations item
SET created_by_user_pk = users.id
FROM users
WHERE item.created_by_user_pk IS NULL
  AND lower(users.tenant_slug) = lower(item.tenant_slug)
  AND users.username = item.created_by_user_id;

UPDATE fan_stock_observation_events item
SET user_id = users.id
FROM users
WHERE item.user_id IS NULL
  AND lower(users.tenant_slug) = lower(item.tenant_slug)
  AND users.username = item.user_profile_id;

CREATE INDEX IF NOT EXISTS idx_user_watchlist_items_user_id
ON user_watchlist_items(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_comments_created_by_user_pk
ON watchlist_comments(created_by_user_pk, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_annotations_created_by_user_pk
ON watchlist_kline_annotations(created_by_user_pk, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_fan_stock_observation_user_id
ON fan_stock_observation_events(user_id, created_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_watchlist_items_user') THEN
        ALTER TABLE user_watchlist_items
            ADD CONSTRAINT fk_user_watchlist_items_user
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_watchlist_comments_created_by_user') THEN
        ALTER TABLE watchlist_comments
            ADD CONSTRAINT fk_watchlist_comments_created_by_user
            FOREIGN KEY (created_by_user_pk) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_watchlist_annotations_created_by_user') THEN
        ALTER TABLE watchlist_kline_annotations
            ADD CONSTRAINT fk_watchlist_annotations_created_by_user
            FOREIGN KEY (created_by_user_pk) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_fan_stock_observation_user') THEN
        ALTER TABLE fan_stock_observation_events
            ADD CONSTRAINT fk_fan_stock_observation_user
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE OR REPLACE VIEW data_integrity_relation_audit AS
SELECT 'user_watchlist_items' AS table_name, COUNT(*)::bigint AS total_rows,
       COUNT(*) FILTER (WHERE user_id IS NULL)::bigint AS unresolved_rows
FROM user_watchlist_items
UNION ALL
SELECT 'watchlist_comments', COUNT(*)::bigint,
       COUNT(*) FILTER (WHERE created_by_user_pk IS NULL)::bigint
FROM watchlist_comments
UNION ALL
SELECT 'watchlist_kline_annotations', COUNT(*)::bigint,
       COUNT(*) FILTER (WHERE created_by_user_pk IS NULL)::bigint
FROM watchlist_kline_annotations
UNION ALL
SELECT 'fan_stock_observation_events', COUNT(*)::bigint,
       COUNT(*) FILTER (WHERE user_id IS NULL)::bigint
FROM fan_stock_observation_events;
