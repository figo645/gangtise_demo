#!/usr/bin/env python3
"""Verify two PostgreSQL schemas without reading application table rows."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_database_release_diff import verify_schema_equivalence  # noqa: E402


def _target(prefix):
    return {
        "name": prefix.lower(),
        "db_host": os.environ[f"VERIFY_{prefix}_HOST"],
        "db_port": os.environ.get(f"VERIFY_{prefix}_PORT", "5432"),
        "db_name": os.environ.get(f"VERIFY_{prefix}_DB", "sprint_dashboard"),
        "db_user": os.environ.get(f"VERIFY_{prefix}_USER", "postgres"),
        "db_password": os.environ.get(f"VERIFY_{prefix}_PASSWORD", ""),
    }


def main():
    report = verify_schema_equivalence(_target("SOURCE"), _target("TARGET"))
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
