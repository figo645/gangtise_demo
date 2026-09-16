-- Preserve rich review content, including pasted and uploaded images.
ALTER TABLE tenant_insight_drafts
    ADD COLUMN IF NOT EXISTS content_html TEXT NOT NULL DEFAULT '';

UPDATE tenant_insight_drafts
SET content_html = CASE
    WHEN COALESCE(content_html, '') = '' AND COALESCE(content_text, '') <> ''
    THEN '<p>' || replace(replace(replace(content_text, '&', '&amp;'), '<', '&lt;'), '>', '&gt;') || '</p>'
    ELSE content_html
END;
