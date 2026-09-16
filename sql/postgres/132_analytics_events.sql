-- Reusable product analytics event fact table.
-- Page request auditing remains in access_logs; this table stores product
-- interactions with a stable event/feature vocabulary.

CREATE TABLE IF NOT EXISTS analytics_events (
    id BIGSERIAL PRIMARY KEY,
    event_name TEXT NOT NULL,
    event_category TEXT NOT NULL DEFAULT 'interaction',
    feature_key TEXT NOT NULL,
    surface TEXT NOT NULL DEFAULT 'unknown',
    tenant_slug TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    user_profile_id TEXT NOT NULL DEFAULT '',
    user_role TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    anonymous_id TEXT NOT NULL DEFAULT '',
    object_type TEXT NOT NULL DEFAULT '',
    object_id TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    referrer TEXT NOT NULL DEFAULT '',
    event_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duration_ms INTEGER,
    success BOOLEAN,
    error_code TEXT NOT NULL DEFAULT '',
    properties_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analytics_events_event_at
    ON analytics_events(event_at DESC);

CREATE INDEX IF NOT EXISTS idx_analytics_events_feature_time
    ON analytics_events(feature_key, event_at DESC);

CREATE INDEX IF NOT EXISTS idx_analytics_events_tenant_time
    ON analytics_events(tenant_slug, event_at DESC);

CREATE INDEX IF NOT EXISTS idx_analytics_events_profile_time
    ON analytics_events(user_profile_id, event_at DESC);

CREATE INDEX IF NOT EXISTS idx_analytics_events_session_time
    ON analytics_events(session_id, event_at, id);

CREATE INDEX IF NOT EXISTS idx_analytics_events_surface_time
    ON analytics_events(surface, event_at DESC);
