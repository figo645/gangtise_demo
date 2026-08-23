import unittest
from unittest.mock import patch

from src.domain import ai_services


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params):
        self.query = query

    def fetchall(self):
        return self.rows


class _FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def cursor(self):
        return self.cursor_instance


class KnowledgeLiveHubTest(unittest.TestCase):
    def test_empty_legacy_knowledge_ids_are_not_collapsed(self):
        rows = [
            (11, "", "manual", "第一条历史知识", "摘要一", "正文一", "手动录入", "", "", "", {}, "2026-08-01"),
            (12, "", "file", "第二条历史知识", "摘要二", "正文二", "文件上传", "", "", "", {}, "2026-08-02"),
        ]
        cursor = _FakeCursor(rows)
        connection = _FakeConnection(cursor)
        tenant = {"slug": "laowang", "name": "财经老王研究院", "knowledge_hub_config": {}}

        with patch.object(ai_services, "resolve_tenant_knowledge_hub", return_value={"summary": "", "items": []}), patch.object(
            ai_services, "get_review_vector_db_connection", return_value=connection
        ), patch.object(ai_services, "_ensure_knowledge_embedding_table"):
            hub = ai_services.fetch_live_knowledge_hub(tenant, limit=160)

        self.assertEqual([item["title"] for item in hub["items"]], ["第一条历史知识", "第二条历史知识"])
        self.assertIn("COALESCE(NULLIF(BTRIM(knowledge_id), ''), CONCAT('__legacy_row_', id))", cursor.query)

