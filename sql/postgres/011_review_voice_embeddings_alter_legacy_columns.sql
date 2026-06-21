-- Backfill columns used by newer application versions on older databases.
ALTER TABLE review_voice_embeddings
ADD COLUMN IF NOT EXISTS vector_namespace TEXT NOT NULL DEFAULT '';

ALTER TABLE review_voice_embeddings
ADD COLUMN IF NOT EXISTS transcription_engine TEXT NOT NULL DEFAULT '';

ALTER TABLE review_voice_embeddings
ADD COLUMN IF NOT EXISTS embedding_engine TEXT NOT NULL DEFAULT '';
