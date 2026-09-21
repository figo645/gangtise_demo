-- Enforce ownership boundaries for the newly separated business domains.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_published_insights_tenant') THEN
        ALTER TABLE tenant_published_insights
            ADD CONSTRAINT fk_published_insights_tenant
            FOREIGN KEY (tenant_slug) REFERENCES tenant_registry(tenant_slug) ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_message_threads_tenant') THEN
        ALTER TABLE tenant_message_threads
            ADD CONSTRAINT fk_message_threads_tenant
            FOREIGN KEY (tenant_slug) REFERENCES tenant_registry(tenant_slug) ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_messages_thread') THEN
        ALTER TABLE tenant_messages
            ADD CONSTRAINT fk_messages_thread
            FOREIGN KEY (tenant_slug, thread_id)
            REFERENCES tenant_message_threads(tenant_slug, thread_id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_broadcasts_tenant') THEN
        ALTER TABLE tenant_broadcasts
            ADD CONSTRAINT fk_broadcasts_tenant
            FOREIGN KEY (tenant_slug) REFERENCES tenant_registry(tenant_slug) ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_broadcast_deliveries_broadcast') THEN
        ALTER TABLE tenant_broadcast_deliveries
            ADD CONSTRAINT fk_broadcast_deliveries_broadcast
            FOREIGN KEY (tenant_slug, broadcast_id)
            REFERENCES tenant_broadcasts(tenant_slug, broadcast_id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_knowledge_documents_tenant') THEN
        ALTER TABLE tenant_knowledge_documents
            ADD CONSTRAINT fk_knowledge_documents_tenant
            FOREIGN KEY (tenant_slug) REFERENCES tenant_registry(tenant_slug) ON DELETE RESTRICT;
    END IF;
END $$;
