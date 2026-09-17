from unittest.mock import patch

from psycopg2.pool import PoolError

import src.runtime as runtime
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


def test_default_pool_budget_is_bounded_by_runtime_role(monkeypatch):
    for role, expected in (("web", 8), ("worker", 4), ("scheduler", 4), ("unknown", 4)):
        monkeypatch.setenv("GANGTISE_RUNTIME_ROLE", role)
        assert runtime._default_database_pool_max_connections() == expected


def test_application_connection_close_rolls_back_and_returns_socket_to_pool(monkeypatch):
    class RawConnection:
        def __init__(self):
            self.rollbacks = 0
            self.closed = False

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    class Pool:
        def __init__(self):
            self.returned = []

        def putconn(self, connection, close=False):
            self.returned.append((connection, close))

    raw = RawConnection()
    pool = Pool()
    monkeypatch.setattr(core_services, "_app_db_pool", pool)

    core_services._release_app_db_connection(raw)

    assert raw.rollbacks == 1
    assert raw.closed is False
    assert pool.returned == [(raw, False)]


def test_pool_exhaustion_is_not_silently_retried_as_a_new_connection():
    class ExhaustedPool:
        def getconn(self):
            raise PoolError("connection pool exhausted")

    with patch.object(core_services, "_get_app_db_pool", return_value=ExhaustedPool()):
        try:
            core_services.get_app_db_connection()
        except PoolError as exc:
            assert "exhausted" in str(exc)
        else:  # pragma: no cover - protects the intended fail-fast contract
            raise AssertionError("expected connection pool exhaustion")
