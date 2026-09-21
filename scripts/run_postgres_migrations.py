#!/usr/bin/env python3
"""Execute immutable PostgreSQL migrations with the application Python runtime.

SQL files remain the migration source of truth. This runner owns database
connections, advisory locking, per-file transactions, checksum verification,
and writes to ``schema_migrations``. It deliberately has no dependency on the
``psql`` executable, so CI/CD and 5051 use the same execution path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import psycopg2


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SQL_DIR = ROOT_DIR / "sql" / "postgres"
MIGRATION_LOCK_ID = 7_346_181_059
OBSOLETE_MIGRATIONS = {
    "035_local_simulation_data_visibility.sql",
    "041_keep_control_plane_accounts_real.sql",
    "042_fix_simulation_provenance_trigger.sql",
}
# Several historic 100+ files are DDL, not master data. Keep this classification
# exactly aligned with the prior shell runner so schema-only behavior is stable.
POST_100_SCHEMA_VERSIONS = {
    "113", "114", "115", "122", "123", "124", "125", "126", "127",
    "128", "129", "131", "132", "133", "134", "135", "137", "138",
    "139", "140", "141", "142", "143", "144", "145",
}


def _load_credentials(path: Path) -> None:
    """Load simple KEY=VALUE credentials without executing shell content."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def _connection_config() -> dict[str, object]:
    return {
        "host": os.environ.get("PGHOST") or os.environ.get("APP_DB_HOST") or "127.0.0.1",
        "port": int(os.environ.get("PGPORT") or os.environ.get("APP_DB_PORT") or "5432"),
        "dbname": os.environ.get("PGDATABASE") or os.environ.get("APP_DB_NAME") or "sprint_dashboard",
        "user": os.environ.get("PGUSER") or os.environ.get("APP_DB_USER") or "postgres",
        "password": os.environ.get("PGPASSWORD") or os.environ.get("APP_DB_PASSWORD") or "your_password",
        "connect_timeout": 8,
        "application_name": "gangtise_python_migration_runner",
    }


def _migration_scope(name: str) -> str:
    version = name.split("_", 1)[0]
    if version.startswith("0") or version in POST_100_SCHEMA_VERSIONS:
        return "schema"
    return "master_data"


def _migration_files(sql_dir: Path) -> list[Path]:
    files = sorted(sql_dir.glob("[0-9][0-9][0-9]_*.sql"))
    if not files:
        raise ValueError(f"No numbered SQL migrations found in {sql_dir}")
    return files


def _validate_migration_catalog(sql_dir: Path) -> list[Path]:
    """Reject non-versioned SQL files before a CI/CD release can use them."""
    pattern = re.compile(r"^[0-9]{3}_[A-Za-z0-9][A-Za-z0-9_.-]*\.sql$")
    files = sorted(path for path in sql_dir.glob("*.sql") if path.name != "README.md")
    invalid = [path.name for path in files if not pattern.fullmatch(path.name)]
    if invalid:
        raise ValueError("migration_filename_invalid:" + ",".join(invalid))
    if not (sql_dir / "004_schema_migrations.sql").is_file():
        raise ValueError("schema_migrations_bootstrap_missing")
    return _migration_files(sql_dir)


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_release_manifest(path: Path, sql_dir: Path, schema_only: bool) -> dict:
    """Validate the immutable release contract before opening a write path."""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"release_manifest_invalid:{path}:{exc}") from exc
    if not isinstance(manifest, dict) or not str(manifest.get("release_version") or "").strip():
        raise ValueError("release_manifest_release_version_required")
    migrations = manifest.get("migrations")
    if not isinstance(migrations, list) or not migrations:
        raise ValueError("release_manifest_migrations_required")
    verified = []
    names = set()
    for item in migrations:
        if not isinstance(item, dict):
            raise ValueError("release_manifest_migration_invalid")
        name = str(item.get("name") or "").strip()
        expected = str(item.get("sha256") or "").strip().lower()
        scope = str(item.get("scope") or _migration_scope(name)).strip()
        if not name or not expected or scope not in {"schema", "master_data"}:
            raise ValueError(f"release_manifest_migration_invalid:{name or 'unknown'}")
        if name in names:
            raise ValueError(f"release_manifest_migration_duplicate:{name}")
        migration_path = (sql_dir / name).resolve()
        if migration_path.parent != sql_dir.resolve() or not migration_path.is_file():
            raise ValueError(f"release_manifest_migration_missing:{name}")
        if _migration_scope(name) != scope:
            raise ValueError(f"release_manifest_migration_scope_invalid:{name}")
        if schema_only and scope != "schema":
            raise ValueError(f"release_manifest_master_data_excluded:{name}")
        actual = _checksum(migration_path)
        if actual != expected:
            raise ValueError(f"release_manifest_checksum_mismatch:{name}")
        verified.append({"name": name, "sha256": expected, "scope": scope})
        names.add(name)
    return {"release_version": str(manifest["release_version"]), "migrations": verified}


def _ensure_ledger(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              migration_name TEXT PRIMARY KEY,
              migration_scope TEXT NOT NULL CHECK (migration_scope IN ('schema', 'master_data')),
              checksum_sha256 TEXT NOT NULL,
              applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
              execution_ms INTEGER NOT NULL DEFAULT 0
            )
            """
        )
    connection.commit()


def _recorded_checksum(connection, migration_name: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT checksum_sha256 FROM schema_migrations WHERE migration_name = %s",
            (migration_name,),
        )
        row = cursor.fetchone()
    connection.rollback()  # End the read transaction before the next migration.
    return str(row[0]) if row else ""


def _apply_one(connection, path: Path, scope: str, checksum: str) -> int:
    sql_text = path.read_text(encoding="utf-8")
    started = time.monotonic()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '10s'")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
            cursor.execute(sql_text)
            elapsed_ms = round((time.monotonic() - started) * 1000)
            cursor.execute(
                """
                INSERT INTO schema_migrations
                    (migration_name, migration_scope, checksum_sha256, execution_ms)
                VALUES (%s, %s, %s, %s)
                """,
                (path.name, scope, checksum, elapsed_ms),
            )
        connection.commit()
        return elapsed_ms
    except Exception:
        connection.rollback()
        raise


def _verify_release_manifest_ledger(connection, manifest: dict) -> None:
    names = [item["name"] for item in manifest["migrations"]]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT migration_name, migration_scope, checksum_sha256 FROM schema_migrations WHERE migration_name = ANY(%s)",
            (names,),
        )
        recorded = {str(name): {"scope": str(scope), "sha256": str(checksum)} for name, scope, checksum in cursor.fetchall()}
    connection.rollback()
    missing = [name for name in names if name not in recorded]
    mismatched = [
        item["name"] for item in manifest["migrations"]
        if item["name"] in recorded
        and (recorded[item["name"]]["scope"] != item["scope"] or recorded[item["name"]]["sha256"] != item["sha256"])
    ]
    if missing or mismatched:
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if mismatched:
            detail.append("mismatched=" + ",".join(mismatched))
        raise RuntimeError("release_manifest_ledger_verification_failed:" + ";".join(detail))
    print(f"Release manifest verified: {manifest['release_version']} ({len(names)} migrations)")


def run_migrations(sql_dir: Path, schema_only: bool, release_manifest: dict | None = None) -> tuple[int, int]:
    config = _connection_config()
    connection = psycopg2.connect(**config)
    connection.autocommit = False
    applied = 0
    skipped = 0
    locked = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
            locked = bool(cursor.fetchone()[0])
        connection.commit()
        if not locked:
            raise RuntimeError("postgres_migration_lock_unavailable")

        _ensure_ledger(connection)
        files = _validate_migration_catalog(sql_dir)
        if release_manifest:
            paths_by_name = {path.name: path for path in files}
            # The versioned manifest can intentionally order a metadata repair
            # before a later FK migration that depends on that repair.
            files = [paths_by_name[item["name"]] for item in release_manifest["migrations"]]
        for path in files:
            name = path.name
            version = name.split("_", 1)[0]
            if version == "000":
                continue
            if name in OBSOLETE_MIGRATIONS:
                print(f"SKIP  {name} (obsolete environment simulation migration)")
                skipped += 1
                continue
            scope = _migration_scope(name)
            if schema_only and scope != "schema":
                print(f"SKIP  {name} (master-data migration excluded by --schema-only)")
                skipped += 1
                continue
            digest = _checksum(path)
            recorded = _recorded_checksum(connection, name)
            if recorded:
                if recorded != digest:
                    raise RuntimeError(
                        f"Checksum mismatch for {name}. Do not edit an applied migration; add a new numbered file."
                    )
                print(f"SKIP  {name} (already applied)")
                skipped += 1
                continue
            print(f"APPLY {name}")
            elapsed_ms = _apply_one(connection, path, scope, digest)
            print(f"DONE  {name} ({elapsed_ms}ms)")
            applied += 1
        if release_manifest:
            _verify_release_manifest_ledger(connection, release_manifest)
        print(
            "Postgres updates completed: "
            f"applied={applied}, skipped={skipped}, database={config['dbname']}, "
            f"host={config['host']}:{config['port']}"
        )
        print("Audit: SELECT migration_name, migration_scope, applied_at, execution_ms FROM schema_migrations ORDER BY applied_at;")
        return applied, skipped
    finally:
        if locked:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))
                connection.commit()
            except psycopg2.Error:
                connection.rollback()
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run immutable PostgreSQL migrations through Python")
    parser.add_argument("--schema-only", action="store_true", help="Skip master-data migrations")
    parser.add_argument("--sql-dir", default=str(DEFAULT_SQL_DIR), help="Fixed directory containing numbered SQL migrations")
    parser.add_argument(
        "--release-manifest",
        default="",
        help="Versioned JSON manifest whose migration names and SHA-256 values must be present in the ledger after execution",
    )
    parser.add_argument(
        "--verify-release-manifest",
        action="store_true",
        help="Validate a release manifest against local SQL files without connecting to PostgreSQL",
    )
    parser.add_argument(
        "--credentials-file",
        default=os.environ.get("POSTGRES_CREDENTIALS_FILE", str(ROOT_DIR / ".gangtise_postgres_credentials")),
        help="Optional APP_DB_* credential file",
    )
    args = parser.parse_args()
    _load_credentials(Path(args.credentials_file))
    sql_dir = Path(args.sql_dir).resolve()
    if not sql_dir.is_dir():
        raise SystemExit(f"SQL directory not found: {sql_dir}")
    try:
        if args.verify_release_manifest and not args.release_manifest:
            raise ValueError("release_manifest_required")
        release_manifest = _load_release_manifest(Path(args.release_manifest), sql_dir, args.schema_only) if args.release_manifest else None
        if args.verify_release_manifest:
            files = _validate_migration_catalog(sql_dir)
            print(f"Release manifest file contract valid: {release_manifest['release_version']} ({len(files)} SQL files)")
            return 0
        run_migrations(sql_dir, args.schema_only, release_manifest)
    except (OSError, ValueError, psycopg2.Error, RuntimeError) as exc:
        print(f"Postgres migration failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
