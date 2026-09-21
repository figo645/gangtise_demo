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


def test_inventory_compares_only_mdm_master_data_and_ignores_runtime_tables():
    local_connections = [FakeConnection(), FakeConnection()]
    target_connections = [FakeConnection(), FakeConnection()]
    local_target = {"host": "127.0.0.1", "port": 5432, "dbname": "local", "user": "postgres", "password": "secret"}
    target = {"name": "staging", "db_host": "staging", "db_port": 5432, "db_name": "dashboard", "db_user": "postgres", "db_password": "secret"}
    local_tables = ["daily_quiz_sets", "security_master", "users"]
    target_tables = [*local_tables, "database_release_packages"]

    with patch.object(database_release_services, "get_database_release_target", return_value=target), patch.object(
        audit_database_release_diff,
        "_connect",
        side_effect=[local_connections[0], target_connections[0], local_connections[1], target_connections[1]],
    ), patch.object(
        audit_database_release_diff,
        "_public_tables",
        side_effect=lambda connection: local_tables if connection in local_connections else target_tables,
    ), patch.object(
        audit_database_release_diff,
        "_table_schema",
        return_value={"hash": "same"},
    ), patch.object(
        audit_database_release_diff,
        "_stable_master_difference",
        return_value={"local_only": [], "target_only": [], "changed_shared": ["600519.SH"]},
    ) as compare, patch(
        "src.domain.core_services.get_local_app_db_target", return_value=local_target
    ):
        inventory = database_release_services.get_database_table_inventory("staging")

    by_name = {row["table_name"]: row for row in inventory["rows"]}
    assert compare.call_count == 1
    assert by_name["security_master"]["category_label"] == "主数据"
    assert by_name["security_master"]["data_status"] == "有差异"
    assert by_name["daily_quiz_sets"]["category_label"] == "内容运行数据"
    assert by_name["daily_quiz_sets"]["data_status"] == "运行数据（忽略）"
    assert by_name["users"]["data_status"] == "账户数据（保留）"
    assert by_name["database_release_packages"]["schema_status"] == "发布控制表（忽略）"
    assert inventory["difference_summary"]["data_tables"] == 1
    assert inventory["difference_summary"]["schema_tables"] == 0
