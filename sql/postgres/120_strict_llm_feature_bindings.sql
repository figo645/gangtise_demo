-- Make every registered LLM capability use an explicit model binding.
-- Existing Admin choices win; only missing bindings receive the initial
-- deployment allocation. Runtime code never falls back to the default model.
UPDATE app_settings
SET setting_value = jsonb_set(
    setting_value::jsonb,
    '{llm_registry,feature_model_keys}',
    '{
      "knowledge_processing_llm":"volcengine-deepseek-v4-flash",
      "review_voice_enhancement":"gangtise-gemma4-12b-bf16",
      "review_input_polish":"volcengine-deepseek-v4-flash",
      "review_draft_generation":"volcengine-deepseek-v4-flash",
      "review_compose_generation":"volcengine-deepseek-v4-flash",
      "review_user_input_summary":"volcengine-deepseek-v4-flash",
      "review_sector_summary_constraint":"volcengine-deepseek-v4-flash",
      "review_evidence_chain_synthesis":"volcengine-deepseek-v4-flash",
      "watchlist_comment_labeling":"volcengine-deepseek-v4-flash",
      "knowledge_query_filter":"volcengine-deepseek-v4-flash",
      "knowledge_query_answer":"volcengine-deepseek-v4-flash",
      "voice_transcription_api":"volcengine-deepseek-v4-flash",
      "embedding_api":"volcengine-deepseek-v4-flash",
      "hermes_intent_router":"volcengine-deepseek-v4-flash",
      "hermes_interception_skill":"volcengine-deepseek-v4-flash",
      "hermes_answer_synthesis":"volcengine-deepseek-v4-flash",
      "hermes_today_user_interaction_task_intent":"volcengine-deepseek-v4-flash",
      "hermes_today_user_interaction_task":"volcengine-deepseek-v4-flash",
      "smart_indicator_formula_generation":"volcengine-deepseek-v4-flash",
      "news_title_impact_classification":"volcengine-deepseek-v4-flash"
    }'::jsonb || COALESCE(setting_value::jsonb #> '{llm_registry,feature_model_keys}', '{}'::jsonb)
)
WHERE setting_key = 'site_config'
  AND setting_value IS NOT NULL
  AND jsonb_typeof(setting_value::jsonb #> '{llm_registry}') = 'object';

-- The news workflow is now source ingestion plus V4 title classification.
-- Explicitly replace any earlier temporary Lite binding so existing installs
-- cannot silently continue using the retired classifier allocation.
UPDATE app_settings
SET setting_value = jsonb_set(
    setting_value::jsonb,
    '{llm_registry,feature_model_keys,news_title_impact_classification}',
    '"volcengine-deepseek-v4-flash"'::jsonb
)
WHERE setting_key = 'site_config'
  AND setting_value IS NOT NULL
  AND jsonb_typeof(setting_value::jsonb #> '{llm_registry}') = 'object';
