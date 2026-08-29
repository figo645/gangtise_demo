-- Auditable decisions made by configurable Hermes semantic interception Skills.
CREATE TABLE IF NOT EXISTS hermes_interception_audits (
    id BIGSERIAL PRIMARY KEY,
    audit_id TEXT NOT NULL UNIQUE,
    tenant_slug TEXT NOT NULL DEFAULT '',
    user_profile_id TEXT NOT NULL DEFAULT '',
    user_role TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    question_text TEXT NOT NULL DEFAULT '',
    router_plan_json TEXT NOT NULL DEFAULT '{}',
    skill_results_json TEXT NOT NULL DEFAULT '[]',
    matched_skill_ids_json TEXT NOT NULL DEFAULT '[]',
    action TEXT NOT NULL DEFAULT 'allow',
    decision_status TEXT NOT NULL DEFAULT 'disabled',
    final_reason TEXT NOT NULL DEFAULT '',
    tool_called INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hermes_interception_audits_tenant_created
ON hermes_interception_audits(tenant_slug, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hermes_interception_audits_action_created
ON hermes_interception_audits(action, created_at DESC);
