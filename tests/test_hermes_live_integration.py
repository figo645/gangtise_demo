"""Opt-in live tests for the Hermes market-research service chain.

These tests intentionally use the configured PostgreSQL, LLM and Gangtise
credentials. They are excluded from normal test runs because the Gangtise
Agent SSE scenarios consume credits.
"""

import os
import unittest

from src.domain.ai_services import build_hermes_query_response
from src.runtime import app


@unittest.skipUnless(
    os.environ.get("RUN_HERMES_LIVE_INTEGRATION") == "1",
    "Set RUN_HERMES_LIVE_INTEGRATION=1 to call the real LLM and Gangtise APIs.",
)
class HermesLiveIntegrationTest(unittest.TestCase):
    def test_given_today_stock_question_when_real_service_chain_runs_then_gangtise_report_is_returned(self):
        question = "对今天中国银行的股票做下个股分析，看看今天整体情况怎么样"
        payload = {
            "tenant_slug": os.environ.get("HERMES_LIVE_TENANT", "laowang"),
            "user_role": "dav",
            "user_profile_id": os.environ.get("HERMES_LIVE_USER", "财经老王"),
            "user_name": os.environ.get("HERMES_LIVE_USER", "财经老王"),
            "entry_point": "hermes_live_integration",
            "question": question,
            "messages": [{"role": "user", "content": question}],
            "attachments": [],
            "selected_knowledge_ids": [],
            "preferred_mode": "basic",
            "web_answer": False,
        }

        with app.test_request_context("/api/hermes/query", method="POST", json=payload):
            result = build_hermes_query_response(payload)

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("intent"), "stock_today_observation")
        self.assertEqual((result.get("answer_engine") or {}).get("mode"), "gangtise_direct")
        self.assertTrue(str(result.get("answer") or "").strip())
        self.assertEqual(
            (result.get("tool_trace") or [{}])[0].get("tool"),
            "gangtise.stock_today_observation",
        )
        self.assertEqual((result.get("tool_trace") or [{}])[0].get("status"), "ok")
