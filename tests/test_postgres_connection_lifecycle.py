from unittest.mock import patch

from src.domain import ai_services, database_release_services
from src.domain import core_services


class FakeConnection:
    def __init__(self):
        self.entered = False
        self.exited = False
        self.closed = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exited = True
        return False

    def close(self):
        self.closed = True


def test_release_connection_commits_or_rolls_back_and_closes_socket():
    raw_connection = FakeConnection()
    with patch.object(database_release_services.psycopg2, "connect", return_value=raw_connection):
        with database_release_services._managed_release_connection(host="127.0.0.1") as connection:
            assert connection is raw_connection

    assert raw_connection.entered is True
    assert raw_connection.exited is True
    assert raw_connection.closed is True


def test_review_vector_connection_closes_socket_after_transaction():
    raw_connection = FakeConnection()
    target = {"host": "127.0.0.1", "port": 5432, "dbname": "dashboard", "user": "postgres", "password": "secret"}
    with patch.object(ai_services, "get_runtime_db_target", return_value={"vector": target}), patch.object(
        ai_services.psycopg2, "connect", return_value=raw_connection
    ):
        with ai_services.get_review_vector_db_connection() as connection:
            assert connection is raw_connection

    assert raw_connection.entered is True
    assert raw_connection.exited is True
    assert raw_connection.closed is True


def test_application_pool_sessions_include_runtime_role_and_transaction_guard(monkeypatch):
    monkeypatch.setenv("GANGTISE_RUNTIME_ENV", "staging")
    monkeypatch.setenv("GANGTISE_RUNTIME_ROLE", "scheduler")
    target = {"host": "127.0.0.1", "port": 5432, "dbname": "dashboard", "user": "postgres", "password": "secret"}
    with patch.object(core_services, "get_runtime_db_target", return_value={"app": target}):
        config = core_services._app_db_pool_config()

    assert config["application_name"].startswith("gangtise-staging-scheduler-")
    assert config["options"] == "-c idle_in_transaction_session_timeout=60000"
