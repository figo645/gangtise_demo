#!/usr/bin/env python3
"""Refresh persisted real Market Overview and Hot Industries snapshots."""

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.runtime import app
from src.domain.core_services import get_db
from src.domain.market_services import sync_market_snapshot


ADVISORY_LOCK_ID = 72951001


def main():
    with app.app_context():
        db = get_db()
        lock = db.execute("SELECT pg_try_advisory_lock(?) AS locked", (ADVISORY_LOCK_ID,)).fetchone()
        if not lock or not lock.get("locked"):
            print(json.dumps({"ok": True, "skipped": "market_snapshot_sync_already_running"}, ensure_ascii=False))
            return 0
        try:
            result = sync_market_snapshot(force=True)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result.get("ok") else 1
        finally:
            db.execute("SELECT pg_advisory_unlock(?)", (ADVISORY_LOCK_ID,))
            db.commit()


if __name__ == "__main__":
    raise SystemExit(main())
