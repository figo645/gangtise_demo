-- Hermes conversation memory, session memory, and user profiling tables.

CREATE TABLE IF NOT EXISTS hermes_conversation_turns (
    id BIGSERIAL PRIMARY KEY,
    turn_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    tenant_slug TEXT NOT NULL DEFAULT '',
    user_profile_id TEXT NOT NULL DEFAULT '',
    user_role TEXT NOT NULL DEFAULT '',
    user_display_name TEXT NOT NULL DEFAULT '',
    entry_point TEXT NOT NULL DEFAULT '',
    question_text TEXT NOT NULL DEFAULT '',
    answer_text TEXT NOT NULL DEFAULT '',
    answer_summary TEXT NOT NULL DEFAULT '',
    intent TEXT NOT NULL DEFAULT '',
    scope_status TEXT NOT NULL DEFAULT '',
    display_mode TEXT NOT NULL DEFAULT 'text',
    preferred_mode TEXT NOT NULL DEFAULT '',
    web_answer INTEGER NOT NULL DEFAULT 0,
    citations_json TEXT NOT NULL DEFAULT '[]',
    tool_trace_json TEXT NOT NULL DEFAULT '[]',
    tags_json TEXT NOT NULL DEFAULT '{}',
    memory_summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hermes_turns_tenant_user_created
ON hermes_conversation_turns(tenant_slug, user_profile_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hermes_turns_session_created
ON hermes_conversation_turns(session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hermes_turns_intent_created
ON hermes_conversation_turns(intent, created_at DESC);

CREATE TABLE IF NOT EXISTS hermes_session_memory (
    session_id TEXT PRIMARY KEY,
    tenant_slug TEXT NOT NULL DEFAULT '',
    user_profile_id TEXT NOT NULL DEFAULT '',
    user_role TEXT NOT NULL DEFAULT '',
    user_display_name TEXT NOT NULL DEFAULT '',
    turn_count INTEGER NOT NULL DEFAULT 0,
    recent_topics_json TEXT NOT NULL DEFAULT '[]',
    recent_symbols_json TEXT NOT NULL DEFAULT '[]',
    recent_intents_json TEXT NOT NULL DEFAULT '[]',
    working_memory_json TEXT NOT NULL DEFAULT '{}',
    summary_text TEXT NOT NULL DEFAULT '',
    last_intent TEXT NOT NULL DEFAULT '',
    last_tags_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hermes_session_tenant_user
ON hermes_session_memory(tenant_slug, user_profile_id, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS hermes_user_memory (
    tenant_slug TEXT NOT NULL DEFAULT '',
    user_profile_id TEXT NOT NULL DEFAULT '',
    user_role TEXT NOT NULL DEFAULT '',
    user_display_name TEXT NOT NULL DEFAULT '',
    total_turns INTEGER NOT NULL DEFAULT 0,
    last_session_id TEXT NOT NULL DEFAULT '',
    fact_memory_json TEXT NOT NULL DEFAULT '{}',
    working_memory_json TEXT NOT NULL DEFAULT '{}',
    recent_topics_json TEXT NOT NULL DEFAULT '[]',
    focus_symbols_json TEXT NOT NULL DEFAULT '[]',
    last_tags_json TEXT NOT NULL DEFAULT '{}',
    preferred_response_style TEXT NOT NULL DEFAULT '',
    preferred_intents_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_slug, user_profile_id)
);

CREATE INDEX IF NOT EXISTS idx_hermes_user_memory_updated
ON hermes_user_memory(updated_at DESC);

CREATE TABLE IF NOT EXISTS hermes_user_profiles (
    tenant_slug TEXT NOT NULL DEFAULT '',
    user_profile_id TEXT NOT NULL DEFAULT '',
    user_role TEXT NOT NULL DEFAULT '',
    user_display_name TEXT NOT NULL DEFAULT '',
    persona_primary TEXT NOT NULL DEFAULT '',
    persona_secondary TEXT NOT NULL DEFAULT '',
    interest_topics_json TEXT NOT NULL DEFAULT '[]',
    focus_symbols_json TEXT NOT NULL DEFAULT '[]',
    function_tags_json TEXT NOT NULL DEFAULT '[]',
    behavior_tags_json TEXT NOT NULL DEFAULT '[]',
    style_tags_json TEXT NOT NULL DEFAULT '[]',
    commercial_tags_json TEXT NOT NULL DEFAULT '[]',
    intent_distribution_json TEXT NOT NULL DEFAULT '{}',
    research_depth_score INTEGER NOT NULL DEFAULT 0,
    engagement_score INTEGER NOT NULL DEFAULT 0,
    conversion_signal_score INTEGER NOT NULL DEFAULT 0,
    total_queries INTEGER NOT NULL DEFAULT 0,
    last_intent TEXT NOT NULL DEFAULT '',
    last_scope_status TEXT NOT NULL DEFAULT '',
    last_activity_at TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant_slug, user_profile_id)
);

CREATE INDEX IF NOT EXISTS idx_hermes_user_profiles_activity
ON hermes_user_profiles(last_activity_at DESC);
