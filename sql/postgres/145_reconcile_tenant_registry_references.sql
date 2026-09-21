-- Reconcile valid historic tenant references before enforcing tenant-owned
-- aggregates on deployments that predate tenant_registry ownership FKs.
-- This is insert-only metadata repair: no domain record is changed or removed.
INSERT INTO tenant_registry (tenant_slug, tenant_name, created_at, updated_at)
SELECT DISTINCT source.tenant_slug, source.tenant_slug, CURRENT_TIMESTAMP::text, CURRENT_TIMESTAMP::text
FROM (
    SELECT tenant_slug FROM tenant_insight_drafts
    UNION
    SELECT tenant_slug FROM open_api_tokens
) source
LEFT JOIN tenant_registry registry ON registry.tenant_slug = source.tenant_slug
WHERE source.tenant_slug = lower(btrim(source.tenant_slug))
  AND btrim(source.tenant_slug) <> ''
  AND registry.tenant_slug IS NULL
ON CONFLICT (tenant_slug) DO NOTHING;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM open_api_tokens
        WHERE tenant_slug IS NULL
           OR btrim(tenant_slug) = ''
           OR tenant_slug <> lower(btrim(tenant_slug))
    ) THEN
        RAISE EXCEPTION 'tenant_registry_reference_invalid:open_api_tokens';
    END IF;
END $$;
