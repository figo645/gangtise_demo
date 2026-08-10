-- Immutable migration execution ledger. Do not update applied migration files;
-- add a new numbered migration instead so every database change is traceable.
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_name TEXT PRIMARY KEY,
    migration_scope TEXT NOT NULL CHECK (migration_scope IN ('schema', 'master_data')),
    checksum_sha256 TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    execution_ms INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at
    ON schema_migrations (applied_at DESC);
