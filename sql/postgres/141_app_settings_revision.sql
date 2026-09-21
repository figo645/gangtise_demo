-- Prevent last-write-wins corruption when two admin/workbench requests update
-- the remaining small configuration document concurrently.
ALTER TABLE app_settings
    ADD COLUMN IF NOT EXISTS revision BIGINT NOT NULL DEFAULT 1;

UPDATE app_settings SET revision = 1 WHERE revision IS NULL OR revision < 1;
