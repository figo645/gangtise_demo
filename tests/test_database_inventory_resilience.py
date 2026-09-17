from unittest.mock import patch

import psycopg2

from src.domain import database_release_services
from tools import audit_database_release_diff, database_release_web


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_inventory_returns_local_governance_when_target_is_unavailable():
    local_connection = FakeConnection()
    local_target = {"host": "127.0.0.1", "port": 5432, "dbname": "local", "user": "postgres", "password": "secret"}
    target = {"name": "staging", "db_host": "staging", "db_port": 5432, "db_name": "dashboard", "db_user": "postgres", "db_password": "secret"}
    with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(
        audit_database_release_diff, "_connect", side_effect=[local_connection, psycopg2.OperationalError("too many clients")]
    ), patch.object(audit_database_release_diff, "_public_tables", return_value=["users"]), patch(
        "src.domain.core_services.get_local_app_db_target", return_value=local_target
    ):
        inventory = database_release_services.get_database_table_inventory("staging")

    assert inventory["target_available"] is False
    assert "too many clients" in inventory["target_error"]
    assert inventory["rows"][0]["status"] == "目标暂不可用"
    assert local_connection.closed is True


def test_inventory_endpoint_returns_json_error_for_source_connection_failure():
    client = database_release_web.app.test_client()
    with patch.object(database_release_web, "get_database_table_inventory", side_effect=RuntimeError("database_release_inventory_source_unavailable: offline")):
        response = client.get("/api/schema-inventory?target=staging")

    assert response.status_code == 400
    assert response.get_json()["error"] == "database_release_inventory_source_unavailable: offline"
