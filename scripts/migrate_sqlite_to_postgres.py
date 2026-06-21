import json
import os
import sqlite3
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values


ROOT_DIR = Path(__file__).resolve().parent.parent
SQLITE_DB_PATH = Path(os.environ.get("GANGTISE_DEMO_DB", ROOT_DIR / "gangtise_demo.db"))
PG_HOST = os.environ.get("APP_DB_HOST") or os.environ.get("VECTOR_DB_HOST") or os.environ.get("IP") or "129.211.65.53"
PG_PORT = int(os.environ.get("APP_DB_PORT") or os.environ.get("VECTOR_DB_PORT") or "5432")
PG_DB = os.environ.get("APP_DB_NAME") or os.environ.get("POSTGRES_DB") or "sprint_dashboard"
PG_USER = os.environ.get("APP_DB_USER") or os.environ.get("POSTGRES_USER") or "postgres"
PG_PASSWORD = os.environ.get("APP_DB_PASSWORD") or os.environ.get("POSTGRES_PASSWORD") or "your_password"

TABLES = [
    "app_settings",
    "users",
    "access_logs",
    "indicator_definitions",
    "indicator_source_defs",
    "indicator_source_tests",
    "indicator_load_batches",
    "indicator_latest_values",
    "indicator_series",
    "indicator_anomalies",
    "indicator_kline_points",
    "indicator_raw_records",
    "indicator_mapping_rules",
    "indicator_clean_jobs",
]


def fetch_sqlite_rows(conn, table_name):
    rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
    return [dict(row) for row in rows]


def truncate_table(pg_conn, table_name):
    with pg_conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE")


def bulk_insert(pg_conn, table_name, rows):
    if not rows:
        return
    columns = list(rows[0].keys())
    values = [[row.get(col) for col in columns] for row in rows]
    sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES %s"
    with pg_conn.cursor() as cur:
        execute_values(cur, sql, values)


def reset_sequence(pg_conn, table_name, pk_name="id"):
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            (table_name, pk_name),
        )
        if cur.fetchone() is None:
            return
        cur.execute(
            """
            SELECT pg_get_serial_sequence(%s, %s)
            """,
            (table_name, pk_name),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return
        seq_name = row[0]
        cur.execute(
            f"SELECT setval(%s, COALESCE((SELECT MAX({pk_name}) FROM {table_name}), 1), true)",
            (seq_name,),
        )


def migrate():
    if not SQLITE_DB_PATH.exists():
        raise FileNotFoundError(f"sqlite_db_not_found:{SQLITE_DB_PATH}")
    sqlite_conn = sqlite3.connect(str(SQLITE_DB_PATH))
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD,
        connect_timeout=8,
    )
    try:
        for table_name in TABLES:
            rows = fetch_sqlite_rows(sqlite_conn, table_name)
            truncate_table(pg_conn, table_name)
            bulk_insert(pg_conn, table_name, rows)
            reset_sequence(pg_conn, table_name)
        pg_conn.commit()
        print(json.dumps({
            "ok": True,
            "sqlite_db": str(SQLITE_DB_PATH),
            "postgres_db": PG_DB,
            "tables": TABLES,
        }, ensure_ascii=False))
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    migrate()
