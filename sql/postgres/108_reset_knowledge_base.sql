-- Reset the knowledge base to an empty, explicit baseline.
-- This removes knowledge content and vector records only. It keeps the
-- application schema and non-knowledge product configuration intact so the
-- redesigned knowledge base can be rebuilt deliberately.

TRUNCATE TABLE knowledge_embeddings;
TRUNCATE TABLE review_voice_embeddings;

UPDATE app_settings
SET setting_value = jsonb_set(
    jsonb_set(
        setting_value::jsonb,
        '{tenants}',
        COALESCE(
            (
                SELECT jsonb_agg(
                    tenant - 'knowledge_hub_config' || jsonb_build_object(
                        'knowledge_hub_config', jsonb_build_object(
                            'summary', '知识库尚未初始化。完成新的知识库设计后，再从管理端录入知识源。',
                            'items', '[]'::jsonb
                        ),
                        'review_snapshots', (
                            SELECT COALESCE(jsonb_agg(snapshot - 'knowledge_attachments'), '[]'::jsonb)
                            FROM jsonb_array_elements(COALESCE(tenant->'review_snapshots', '[]'::jsonb)) AS snapshot
                        )
                    )
                )
                FROM jsonb_array_elements(COALESCE(setting_value::jsonb->'tenants', '[]'::jsonb)) AS tenant
            ),
            '[]'::jsonb
        ),
        true
    ),
    '{knowledge_ingestion,user_preview_enabled}',
    'false'::jsonb,
    true
)::text,
updated_at = to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
WHERE setting_key = 'site_config'
  AND jsonb_typeof(setting_value::jsonb) = 'object';

SELECT 'knowledge_base_reset_complete' AS status;
