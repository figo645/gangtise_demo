-- Default vector dimension is 1536, matching PGVECTOR_TARGET_DIM in app.py.
ALTER TABLE knowledge_embeddings
ADD COLUMN IF NOT EXISTS embedding_vector vector(1536);
