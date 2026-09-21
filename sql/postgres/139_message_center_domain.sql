-- Message Center is durable business activity, not tenant configuration.
CREATE TABLE IF NOT EXISTS tenant_message_threads (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    thread_type TEXT NOT NULL DEFAULT 'fan_interaction',
    name TEXT NOT NULL DEFAULT '',
    user_profile_id TEXT NOT NULL DEFAULT '',
    user_name TEXT NOT NULL DEFAULT '',
    user_avatar TEXT NOT NULL DEFAULT '',
    tier TEXT NOT NULL DEFAULT '粉丝',
    status TEXT NOT NULL DEFAULT '待处理',
    last_msg TEXT NOT NULL DEFAULT '',
    kol_unread INTEGER NOT NULL DEFAULT 0,
    user_unread INTEGER NOT NULL DEFAULT 0,
    last_sender TEXT NOT NULL DEFAULT '',
    last_message_type TEXT NOT NULL DEFAULT 'text',
    vip_only BOOLEAN NOT NULL DEFAULT FALSE,
    is_simulated BOOLEAN NOT NULL DEFAULT FALSE,
    simulation_label TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (tenant_slug, thread_id)
);

CREATE TABLE IF NOT EXISTS tenant_messages (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    message_key TEXT NOT NULL,
    sender TEXT NOT NULL DEFAULT 'user',
    content TEXT NOT NULL DEFAULT '',
    message_time TEXT NOT NULL DEFAULT '',
    message_type TEXT NOT NULL DEFAULT 'text',
    broadcast_kind TEXT NOT NULL DEFAULT '',
    visual_theme TEXT NOT NULL DEFAULT '',
    insight_id TEXT NOT NULL DEFAULT '',
    price INTEGER NOT NULL DEFAULT 0,
    preview TEXT NOT NULL DEFAULT '',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_slug, thread_id, message_key)
);

CREATE TABLE IF NOT EXISTS tenant_broadcasts (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL,
    broadcast_id TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    broadcast_time TEXT NOT NULL DEFAULT '',
    reach INTEGER NOT NULL DEFAULT 0,
    open_rate INTEGER NOT NULL DEFAULT 0,
    target TEXT NOT NULL DEFAULT 'all',
    broadcast_type TEXT NOT NULL DEFAULT 'broadcast',
    broadcast_kind TEXT NOT NULL DEFAULT '',
    visual_theme TEXT NOT NULL DEFAULT '',
    insight_id TEXT NOT NULL DEFAULT '',
    is_simulated BOOLEAN NOT NULL DEFAULT FALSE,
    simulation_label TEXT NOT NULL DEFAULT '',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_slug, broadcast_id)
);

CREATE TABLE IF NOT EXISTS tenant_broadcast_deliveries (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL,
    broadcast_id TEXT NOT NULL,
    user_profile_id TEXT NOT NULL,
    thread_id TEXT NOT NULL DEFAULT '',
    delivery_status TEXT NOT NULL DEFAULT 'delivered',
    delivered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_slug, broadcast_id, user_profile_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_message_threads_updated
    ON tenant_message_threads(tenant_slug, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenant_messages_thread_time
    ON tenant_messages(tenant_slug, thread_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenant_broadcasts_time
    ON tenant_broadcasts(tenant_slug, broadcast_time DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenant_broadcast_deliveries_profile
    ON tenant_broadcast_deliveries(tenant_slug, user_profile_id, delivered_at DESC);

INSERT INTO tenant_message_threads (
    tenant_slug, thread_id, thread_type, name, user_profile_id, user_name,
    user_avatar, tier, status, last_msg, kol_unread, user_unread,
    last_sender, last_message_type, vip_only, is_simulated, simulation_label,
    created_at, updated_at, metadata_json
)
SELECT tenant->>'slug', thread->>'id', COALESCE(thread->>'type', 'fan_interaction'),
       COALESCE(thread->>'name', ''), COALESCE(thread->>'user_profile_id', ''),
       COALESCE(thread->>'user_name', ''), COALESCE(thread->>'user_avatar', ''),
       COALESCE(thread->>'tier', '粉丝'), COALESCE(thread->>'status', '待处理'),
       COALESCE(thread->>'last_msg', thread->>'content', ''),
       COALESCE(NULLIF(thread->>'kol_unread', '')::integer, 0),
       COALESCE(NULLIF(thread->>'user_unread', '')::integer, 0),
       COALESCE(thread->>'last_sender', ''), COALESCE(thread->>'last_message_type', 'text'),
       CASE WHEN lower(COALESCE(thread->>'vip_only', '')) IN ('1', 'true', 't', 'yes') THEN true ELSE false END,
       CASE WHEN lower(COALESCE(thread->>'is_simulated', '')) IN ('1', 'true', 't', 'yes') THEN true ELSE false END,
       COALESCE(thread->>'simulation_label', ''),
       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, thread
FROM app_settings settings
CROSS JOIN LATERAL jsonb_array_elements(COALESCE((settings.setting_value::jsonb)->'tenants', '[]'::jsonb)) tenant
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(tenant->'message_center_state'->'threads', '[]'::jsonb)) thread
WHERE settings.setting_key = 'site_config' AND COALESCE(tenant->>'slug', '') <> ''
  AND COALESCE(thread->>'id', '') <> ''
ON CONFLICT (tenant_slug, thread_id) DO NOTHING;

INSERT INTO tenant_messages (
    tenant_slug, thread_id, message_key, sender, content, message_time,
    message_type, broadcast_kind, visual_theme, insight_id, price, preview, metadata_json
)
SELECT tenant->>'slug', thread->>'id', COALESCE(message->>'id', (row_number() OVER ())::text),
       COALESCE(message->>'sender', 'user'), COALESCE(message->>'content', ''),
       COALESCE(message->>'time', ''), COALESCE(message->>'type', 'text'),
       COALESCE(message->>'broadcast_kind', ''), COALESCE(message->>'visual_theme', ''),
       COALESCE(message->>'insight_id', ''), COALESCE(NULLIF(message->>'price', '')::integer, 0),
       COALESCE(message->>'preview', ''), message
FROM app_settings settings
CROSS JOIN LATERAL jsonb_array_elements(COALESCE((settings.setting_value::jsonb)->'tenants', '[]'::jsonb)) tenant
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(tenant->'message_center_state'->'threads', '[]'::jsonb)) thread
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(thread->'messages', '[]'::jsonb)) message
WHERE settings.setting_key = 'site_config' AND COALESCE(thread->>'id', '') <> ''
ON CONFLICT (tenant_slug, thread_id, message_key) DO NOTHING;

INSERT INTO tenant_broadcasts (
    tenant_slug, broadcast_id, content, broadcast_time, reach, open_rate, target,
    broadcast_type, broadcast_kind, visual_theme, insight_id, is_simulated, simulation_label, metadata_json
)
SELECT tenant->>'slug', COALESCE(broadcast->>'id', md5(broadcast::text)),
       COALESCE(broadcast->>'content', ''), COALESCE(broadcast->>'time', ''),
       COALESCE(NULLIF(broadcast->>'reach', '')::integer, 0),
       COALESCE(NULLIF(broadcast->>'open_rate', '')::integer, 0),
       COALESCE(broadcast->>'target', 'all'), COALESCE(broadcast->>'type', 'broadcast'),
       COALESCE(broadcast->>'broadcast_kind', ''), COALESCE(broadcast->>'visual_theme', ''),
       COALESCE(broadcast->>'insight_id', ''),
       CASE WHEN lower(COALESCE(broadcast->>'is_simulated', '')) IN ('1', 'true', 't', 'yes') THEN true ELSE false END,
       COALESCE(broadcast->>'simulation_label', ''), broadcast
FROM app_settings settings
CROSS JOIN LATERAL jsonb_array_elements(COALESCE((settings.setting_value::jsonb)->'tenants', '[]'::jsonb)) tenant
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(tenant->'message_center_state'->'broadcasts', '[]'::jsonb)) broadcast
WHERE settings.setting_key = 'site_config' AND COALESCE(tenant->>'slug', '') <> ''
ON CONFLICT (tenant_slug, broadcast_id) DO NOTHING;
