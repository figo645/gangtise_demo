import json
import unittest
from unittest.mock import patch

from src.domain import market_services


class V4NewsSearchBDDTest(unittest.TestCase):
    """BDD contract for the Admin-triggered shared V4 news snapshot."""

    def test_when_admin_runs_news_task_then_sources_are_fully_classified_in_v4_batches(self):
        model = {
            "key": "volcengine-deepseek-v4-flash",
            "label": "DeepSeek-V4-Flash正式版",
            "provider": "volcengine",
            "model_name": "deepseek-v4-flash-ga-260731",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "api_key": "test-key",
            "enabled": True,
        }
        source_items = [{
            "event_id": f"news-{index}",
            "title": f"汽车产业政策发布 {index}",
            "url": f"https://source.example/news/{index}",
            "source_name": "中国政府网",
            "source_code": "gov_cn_policy",
            "source_group": "政策要闻",
        } for index in range(100)]
        responses = []
        for start in range(0, 100, market_services.NEWS_LLM_CLASSIFIER_BATCH_SIZE):
            responses.append(json.dumps([{
                "news_id": item["event_id"],
                "impact": "positive",
                "industry_code": "automotive",
            } for item in source_items[start:start + market_services.NEWS_LLM_CLASSIFIER_BATCH_SIZE]]))
        saved = {}

        def save_setting(key, value):
            saved[key] = value

        with patch("src.domain.ai_services.resolve_llm_config", return_value=model) as resolve_model, \
             patch("src.domain.ai_services.call_openai_compatible_llm", side_effect=responses) as call_v4, \
             patch.object(market_services, "_aggregate_real_news_sources", return_value={"items": source_items, "sources": [{"code": "gov_cn_policy"}]}), \
             patch.object(market_services, "_save_json_app_setting", side_effect=save_setting):
            result = market_services.sync_news_title_classifications(force=True)

        resolve_model.assert_called_once_with(feature_code="news_title_impact_classification", purpose="general")
        self.assertEqual(call_v4.call_count, 4)
        self.assertEqual(result["input_count"], 100)
        self.assertEqual(result["classified_count"], 100)
        self.assertEqual(result["batches_succeeded"], 4)
        self.assertEqual(result["model_name"], "deepseek-v4-flash-ga-260731")
        self.assertIn(market_services.NEWS_LAKE_CACHE_KEY, saved)
        self.assertEqual(saved[market_services.NEWS_LAKE_CACHE_KEY]["items"][0]["url"], "https://source.example/news/0")
        self.assertEqual(saved[market_services.NEWS_LAKE_CACHE_KEY]["items"][0]["impact"], "positive")

    def test_incomplete_v4_batch_fails_without_overwriting_shared_snapshot(self):
        items = [{"event_id": f"news-{index}", "title": f"标题 {index}", "url": f"https://example.com/{index}"} for index in range(31)]
        saved = []
        with patch("src.domain.ai_services.resolve_llm_config", return_value={"model_name": "v4", "provider": "volcengine", "enabled": True}), \
             patch("src.domain.ai_services.call_openai_compatible_llm", return_value="[]"), \
             patch.object(market_services, "_aggregate_real_news_sources", return_value={"items": items}), \
             patch.object(market_services, "_save_json_app_setting", side_effect=lambda key, value: saved.append((key, value))):
            with self.assertRaisesRegex(RuntimeError, "news_title_classifier_incomplete"):
                market_services.sync_news_title_classifications(force=True)
        self.assertEqual(saved, [])

    def test_when_feature_model_binding_is_missing_then_resolution_fails_without_default_fallback(self):
        from src.domain import ai_services

        config = {
            "llm_registry": {
                "default_model_key": "volcengine-deepseek-v4-flash",
                "models": [{
                    "key": "volcengine-deepseek-v4-flash",
                    "model_name": "deepseek-v4-flash-ga-260731",
                    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                    "enabled": True,
                    "purpose": "general",
                }],
                "feature_model_keys": {},
            }
        }
        with self.assertRaisesRegex(RuntimeError, "llm_feature_model_binding_missing:news_title_impact_classification"):
            ai_services.resolve_llm_config(
                feature_code="news_title_impact_classification",
                purpose="general",
                site_config=config,
            )

    def test_when_feature_model_is_disabled_then_resolution_returns_the_real_error(self):
        from src.domain import ai_services

        config = {
            "llm_registry": {
                "models": [{
                    "key": "v4-disabled",
                    "model_name": "deepseek-v4-flash-ga-260731",
                    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                    "enabled": False,
                    "purpose": "general",
                }],
                "feature_model_keys": {"news_title_impact_classification": "v4-disabled"},
            }
        }
        with self.assertRaisesRegex(RuntimeError, "llm_feature_model_disabled:news_title_impact_classification:v4-disabled"):
            ai_services.resolve_llm_config(
                feature_code="news_title_impact_classification",
                purpose="general",
                site_config=config,
            )


if __name__ == "__main__":
    unittest.main()
