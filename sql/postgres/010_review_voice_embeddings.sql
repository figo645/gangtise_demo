-- Current table definition for voice-to-text review embeddings.
CREATE TABLE IF NOT EXISTS review_voice_embeddings (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL DEFAULT '',
    review_period TEXT NOT NULL DEFAULT '',
    entry_point TEXT NOT NULL DEFAULT '',
    vector_namespace TEXT NOT NULL DEFAULT '',
    speaker_name TEXT NOT NULL DEFAULT '',
    original_filename TEXT NOT NULL DEFAULT '',
    mime_type TEXT NOT NULL DEFAULT '',
    audio_size_bytes INTEGER NOT NULL DEFAULT 0,
    transcript_text TEXT NOT NULL,
    transcript_hash TEXT NOT NULL,
    transcription_engine TEXT NOT NULL DEFAULT '',
    transcript_model TEXT NOT NULL DEFAULT '',
    embedding_engine TEXT NOT NULL DEFAULT '',
    embedding_model TEXT NOT NULL DEFAULT '',
    embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_tenant_created
ON review_voice_embeddings(tenant_slug, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_hash
ON review_voice_embeddings(transcript_hash);

CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_namespace
ON review_voice_embeddings(vector_namespace, created_at DESC);
