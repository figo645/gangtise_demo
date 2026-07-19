-- Persisted tenant-scoped comments on watchlist detail pages.

CREATE TABLE IF NOT EXISTS watchlist_comments (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL DEFAULT '',
    stock_code TEXT NOT NULL DEFAULT '',
    stock_name TEXT NOT NULL DEFAULT '',
    comment_text TEXT NOT NULL DEFAULT '',
    label_tags_json TEXT NOT NULL DEFAULT '[]',
    keyword_tags_json TEXT NOT NULL DEFAULT '[]',
    sentiment_label TEXT NOT NULL DEFAULT '',
    topic_label TEXT NOT NULL DEFAULT '',
    comment_summary TEXT NOT NULL DEFAULT '',
    labeling_source TEXT NOT NULL DEFAULT '',
    labeling_model_key TEXT NOT NULL DEFAULT '',
    labeling_model_name TEXT NOT NULL DEFAULT '',
    created_by_user_id TEXT NOT NULL DEFAULT '',
    created_by_name TEXT NOT NULL DEFAULT '',
    created_by_role TEXT NOT NULL DEFAULT 'investor',
    source_client TEXT NOT NULL DEFAULT 'h5',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS label_tags_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS keyword_tags_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS sentiment_label TEXT NOT NULL DEFAULT '';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS topic_label TEXT NOT NULL DEFAULT '';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS comment_summary TEXT NOT NULL DEFAULT '';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS labeling_source TEXT NOT NULL DEFAULT '';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS labeling_model_key TEXT NOT NULL DEFAULT '';
ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS labeling_model_name TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_watchlist_comments_tenant_stock_updated
ON watchlist_comments(tenant_slug, stock_code, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_watchlist_comments_tenant_user
ON watchlist_comments(tenant_slug, created_by_user_id, updated_at DESC);
