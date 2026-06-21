-- Default vector dimension is 1536, matching PGVECTOR_TARGET_DIM in app.py.
ALTER TABLE review_voice_embeddings
ADD COLUMN IF NOT EXISTS embedding_vector vector(1536);

CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_vector
ON review_voice_embeddings
USING ivfflat (embedding_vector vector_cosine_ops);
