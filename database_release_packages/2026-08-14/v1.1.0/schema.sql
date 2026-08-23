-- v1.1.0 schema delta.
-- Safe to apply repeatedly. It adds platform capabilities without changing or
-- deleting existing user, tenant, knowledge, review, or market records.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE users ADD COLUMN IF NOT EXISTS source_label TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_paid_sample INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS paid_sample_marked_at TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS paid_sample_note TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS labels_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider TEXT NOT NULL DEFAULT 'local';
ALTER TABLE users ADD COLUMN IF NOT EXISTS wechat_openid TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS wechat_unionid TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS wechat_nickname TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS wechat_bound_at TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS compliance_acknowledged_at TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS compliance_version TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS h5_channel_label TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS h5_channel_selected_at TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_completed_at TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_simulated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS simulation_batch_code TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS simulation_label TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_users_tenant_role_paid ON users(tenant_slug, role, is_paid_sample, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_users_tenant_role ON users(tenant_slug, role, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_users_auth_provider ON users(auth_provider);
CREATE INDEX IF NOT EXISTS idx_users_wechat_openid ON users(wechat_openid);
CREATE INDEX IF NOT EXISTS idx_users_wechat_unionid ON users(wechat_unionid);
CREATE INDEX IF NOT EXISTS idx_users_h5_channel_label ON users(h5_channel_label);
CREATE INDEX IF NOT EXISTS idx_users_onboarding_completed_at ON users(onboarding_completed_at);
CREATE INDEX IF NOT EXISTS idx_users_simulation_batch ON users(simulation_batch_code, created_at DESC);

ALTER TABLE access_logs ADD COLUMN IF NOT EXISTS tenant_slug TEXT NOT NULL DEFAULT '';
ALTER TABLE access_logs ADD COLUMN IF NOT EXISTS user_profile_id TEXT NOT NULL DEFAULT '';
ALTER TABLE access_logs ADD COLUMN IF NOT EXISTS user_role TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_access_logs_tenant_created_at ON access_logs(tenant_slug, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_access_logs_tenant_user_role ON access_logs(tenant_slug, user_role, created_at DESC);

CREATE TABLE IF NOT EXISTS hermes_conversation_turns (
    id BIGSERIAL PRIMARY KEY, turn_id TEXT NOT NULL UNIQUE, session_id TEXT NOT NULL,
    tenant_slug TEXT NOT NULL DEFAULT '', user_profile_id TEXT NOT NULL DEFAULT '', user_role TEXT NOT NULL DEFAULT '',
    user_display_name TEXT NOT NULL DEFAULT '', entry_point TEXT NOT NULL DEFAULT '', question_text TEXT NOT NULL DEFAULT '',
    answer_text TEXT NOT NULL DEFAULT '', answer_summary TEXT NOT NULL DEFAULT '', intent TEXT NOT NULL DEFAULT '',
    scope_status TEXT NOT NULL DEFAULT '', display_mode TEXT NOT NULL DEFAULT 'text', preferred_mode TEXT NOT NULL DEFAULT '',
    web_answer INTEGER NOT NULL DEFAULT 0, citations_json TEXT NOT NULL DEFAULT '[]', tool_trace_json TEXT NOT NULL DEFAULT '[]',
    tags_json TEXT NOT NULL DEFAULT '{}', memory_summary_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hermes_turns_tenant_user_created ON hermes_conversation_turns(tenant_slug, user_profile_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hermes_turns_session_created ON hermes_conversation_turns(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hermes_turns_intent_created ON hermes_conversation_turns(intent, created_at DESC);

CREATE TABLE IF NOT EXISTS hermes_session_memory (
    session_id TEXT PRIMARY KEY, tenant_slug TEXT NOT NULL DEFAULT '', user_profile_id TEXT NOT NULL DEFAULT '',
    user_role TEXT NOT NULL DEFAULT '', user_display_name TEXT NOT NULL DEFAULT '', turn_count INTEGER NOT NULL DEFAULT 0,
    recent_topics_json TEXT NOT NULL DEFAULT '[]', recent_symbols_json TEXT NOT NULL DEFAULT '[]', recent_intents_json TEXT NOT NULL DEFAULT '[]',
    working_memory_json TEXT NOT NULL DEFAULT '{}', summary_text TEXT NOT NULL DEFAULT '', last_intent TEXT NOT NULL DEFAULT '',
    last_tags_json TEXT NOT NULL DEFAULT '{}', first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hermes_session_tenant_user ON hermes_session_memory(tenant_slug, user_profile_id, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS hermes_user_memory (
    tenant_slug TEXT NOT NULL DEFAULT '', user_profile_id TEXT NOT NULL DEFAULT '', user_role TEXT NOT NULL DEFAULT '',
    user_display_name TEXT NOT NULL DEFAULT '', total_turns INTEGER NOT NULL DEFAULT 0, last_session_id TEXT NOT NULL DEFAULT '',
    fact_memory_json TEXT NOT NULL DEFAULT '{}', working_memory_json TEXT NOT NULL DEFAULT '{}', recent_topics_json TEXT NOT NULL DEFAULT '[]',
    focus_symbols_json TEXT NOT NULL DEFAULT '[]', last_tags_json TEXT NOT NULL DEFAULT '{}', preferred_response_style TEXT NOT NULL DEFAULT '',
    preferred_intents_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_slug, user_profile_id)
);
CREATE INDEX IF NOT EXISTS idx_hermes_user_memory_updated ON hermes_user_memory(updated_at DESC);

CREATE TABLE IF NOT EXISTS hermes_user_profiles (
    tenant_slug TEXT NOT NULL DEFAULT '', user_profile_id TEXT NOT NULL DEFAULT '', user_role TEXT NOT NULL DEFAULT '',
    user_display_name TEXT NOT NULL DEFAULT '', persona_primary TEXT NOT NULL DEFAULT '', persona_secondary TEXT NOT NULL DEFAULT '',
    interest_topics_json TEXT NOT NULL DEFAULT '[]', focus_symbols_json TEXT NOT NULL DEFAULT '[]', function_tags_json TEXT NOT NULL DEFAULT '[]',
    behavior_tags_json TEXT NOT NULL DEFAULT '[]', style_tags_json TEXT NOT NULL DEFAULT '[]', commercial_tags_json TEXT NOT NULL DEFAULT '[]',
    intent_distribution_json TEXT NOT NULL DEFAULT '{}', research_depth_score INTEGER NOT NULL DEFAULT 0, engagement_score INTEGER NOT NULL DEFAULT 0,
    conversion_signal_score INTEGER NOT NULL DEFAULT 0, total_queries INTEGER NOT NULL DEFAULT 0, last_intent TEXT NOT NULL DEFAULT '',
    last_scope_status TEXT NOT NULL DEFAULT '', last_activity_at TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (tenant_slug, user_profile_id)
);
CREATE INDEX IF NOT EXISTS idx_hermes_user_profiles_activity ON hermes_user_profiles(last_activity_at DESC);

CREATE TABLE IF NOT EXISTS review_voice_embeddings (
    id BIGSERIAL PRIMARY KEY, tenant_slug TEXT NOT NULL DEFAULT '', review_period TEXT NOT NULL DEFAULT '', entry_point TEXT NOT NULL DEFAULT '',
    vector_namespace TEXT NOT NULL DEFAULT '', speaker_name TEXT NOT NULL DEFAULT '', original_filename TEXT NOT NULL DEFAULT '',
    mime_type TEXT NOT NULL DEFAULT '', audio_size_bytes INTEGER NOT NULL DEFAULT 0, transcript_text TEXT NOT NULL, transcript_hash TEXT NOT NULL,
    transcription_engine TEXT NOT NULL DEFAULT '', transcript_model TEXT NOT NULL DEFAULT '', embedding_engine TEXT NOT NULL DEFAULT '',
    embedding_model TEXT NOT NULL DEFAULT '', embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS vector_namespace TEXT NOT NULL DEFAULT '';
ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS transcription_engine TEXT NOT NULL DEFAULT '';
ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS embedding_engine TEXT NOT NULL DEFAULT '';
ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS embedding_vector vector(1536);
CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_tenant_created ON review_voice_embeddings(tenant_slug, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_hash ON review_voice_embeddings(transcript_hash);
CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_namespace ON review_voice_embeddings(vector_namespace, created_at DESC);

CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    id BIGSERIAL PRIMARY KEY, tenant_slug TEXT NOT NULL DEFAULT '', knowledge_id TEXT NOT NULL DEFAULT '', knowledge_type TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '', body_text TEXT NOT NULL DEFAULT '', source_detail TEXT NOT NULL DEFAULT '',
    vector_namespace TEXT NOT NULL DEFAULT '', embedding_engine TEXT NOT NULL DEFAULT '', embedding_model TEXT NOT NULL DEFAULT '',
    embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb, metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE knowledge_embeddings ADD COLUMN IF NOT EXISTS embedding_vector vector(1536);
CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_tenant_created ON knowledge_embeddings(tenant_slug, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_knowledge_id ON knowledge_embeddings(knowledge_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_namespace ON knowledge_embeddings(vector_namespace, created_at DESC);

CREATE TABLE IF NOT EXISTS fan_stock_observation_events (
    id BIGSERIAL PRIMARY KEY, tenant_slug TEXT NOT NULL DEFAULT '', user_profile_id TEXT NOT NULL DEFAULT '', user_role TEXT NOT NULL DEFAULT '',
    stock_code TEXT NOT NULL DEFAULT '', stock_name TEXT NOT NULL DEFAULT '', sector_name TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL DEFAULT 'watchlist_detail_view', entry_point TEXT NOT NULL DEFAULT '', source_detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
ALTER TABLE fan_stock_observation_events ADD COLUMN IF NOT EXISTS is_simulated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE fan_stock_observation_events ADD COLUMN IF NOT EXISTS simulation_batch_code TEXT NOT NULL DEFAULT '';
ALTER TABLE fan_stock_observation_events ADD COLUMN IF NOT EXISTS simulation_label TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_fan_stock_observation_tenant_created ON fan_stock_observation_events(tenant_slug, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fan_stock_observation_stock_created ON fan_stock_observation_events(tenant_slug, stock_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fan_stock_observation_user_created ON fan_stock_observation_events(tenant_slug, user_profile_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fan_stock_observation_simulation_batch ON fan_stock_observation_events(simulation_batch_code, created_at DESC);

CREATE TABLE IF NOT EXISTS watchlist_kline_annotations (
    id BIGSERIAL PRIMARY KEY, tenant_slug TEXT NOT NULL DEFAULT '', stock_code TEXT NOT NULL DEFAULT '', stock_name TEXT NOT NULL DEFAULT '',
    candle_index INTEGER NOT NULL DEFAULT 0, candle_date TEXT NOT NULL DEFAULT '', open_price DOUBLE PRECISION NOT NULL DEFAULT 0,
    high_price DOUBLE PRECISION NOT NULL DEFAULT 0, low_price DOUBLE PRECISION NOT NULL DEFAULT 0, close_price DOUBLE PRECISION NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', trigger TEXT NOT NULL DEFAULT '', created_by_user_id TEXT NOT NULL DEFAULT '',
    created_by_name TEXT NOT NULL DEFAULT '', source_client TEXT NOT NULL DEFAULT 'h5', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_watchlist_kline_annotations_tenant_stock_candle ON watchlist_kline_annotations(tenant_slug, stock_code, candle_index);
CREATE INDEX IF NOT EXISTS idx_watchlist_kline_annotations_tenant_stock_updated ON watchlist_kline_annotations(tenant_slug, stock_code, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_kline_annotations_tenant_updated ON watchlist_kline_annotations(tenant_slug, updated_at DESC);

CREATE TABLE IF NOT EXISTS watchlist_comments (
    id BIGSERIAL PRIMARY KEY, tenant_slug TEXT NOT NULL DEFAULT '', stock_code TEXT NOT NULL DEFAULT '', stock_name TEXT NOT NULL DEFAULT '',
    comment_text TEXT NOT NULL DEFAULT '', label_tags_json TEXT NOT NULL DEFAULT '[]', keyword_tags_json TEXT NOT NULL DEFAULT '[]',
    sentiment_label TEXT NOT NULL DEFAULT '', topic_label TEXT NOT NULL DEFAULT '', comment_summary TEXT NOT NULL DEFAULT '',
    labeling_source TEXT NOT NULL DEFAULT '', labeling_model_key TEXT NOT NULL DEFAULT '', labeling_model_name TEXT NOT NULL DEFAULT '',
    created_by_user_id TEXT NOT NULL DEFAULT '', created_by_name TEXT NOT NULL DEFAULT '', created_by_role TEXT NOT NULL DEFAULT 'investor',
    source_client TEXT NOT NULL DEFAULT 'h5', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS label_tags_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS keyword_tags_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS sentiment_label TEXT NOT NULL DEFAULT '';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS topic_label TEXT NOT NULL DEFAULT '';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS comment_summary TEXT NOT NULL DEFAULT '';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS labeling_source TEXT NOT NULL DEFAULT '';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS labeling_model_key TEXT NOT NULL DEFAULT '';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS labeling_model_name TEXT NOT NULL DEFAULT '';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS is_simulated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS simulation_batch_code TEXT NOT NULL DEFAULT '';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS simulation_label TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_watchlist_comments_tenant_stock_updated ON watchlist_comments(tenant_slug, stock_code, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_comments_tenant_user ON watchlist_comments(tenant_slug, created_by_user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_comments_simulation_batch ON watchlist_comments(simulation_batch_code, created_at DESC);

CREATE TABLE IF NOT EXISTS simulated_data_batches (
    batch_code TEXT PRIMARY KEY, tenant_slug TEXT NOT NULL DEFAULT '', batch_label TEXT NOT NULL DEFAULT '模拟数据',
    created_at TEXT NOT NULL, created_by TEXT NOT NULL DEFAULT 'database_release_web', notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_simulated_data_batches_tenant_created ON simulated_data_batches(tenant_slug, created_at DESC);

CREATE TABLE IF NOT EXISTS market_snapshot_payloads (
    snapshot_type TEXT NOT NULL, snapshot_key TEXT NOT NULL, source TEXT NOT NULL DEFAULT '', snapshot_version INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL DEFAULT '{}', collected_at TEXT NOT NULL DEFAULT '', updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (snapshot_type, snapshot_key)
);
CREATE INDEX IF NOT EXISTS idx_market_snapshot_payloads_updated ON market_snapshot_payloads(snapshot_type, updated_at DESC);
