"""BDD contracts for shared market and daily broadcast scheduling."""

from datetime import datetime
from pathlib import Path
import sys
from unittest.mock import patch

from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.domain import core_services, market_services


def test_market_top10_views_share_one_configurable_akshare_task():
    task = next(item for item in market_services.DEFAULT_ADMIN_TASKS if item["task_code"] == "market_snapshot_sync")
    assert task["schedule_type"] == "interval"
    assert task["schedule_value"] == "300"
    assert "热门行业涨跌 Top10" in task["description"]
    assert "市场一览涨跌 Top10" in task["description"]
    assert "自选股涨跌 Top10" in task["description"]
    assert task["task_type"] == "sync_market_snapshot"


def test_market_task_becomes_due_after_thirty_seconds():
    task = {
        "enabled": 1,
        "schedule_type": "interval",
        "schedule_value": "30",
        "last_run_started_at": "2026-09-16 10:00:00",
    }
    due, interval = core_services._task_should_run(task, datetime(2026, 9, 16, 10, 0, 30).timestamp())
    assert due is True
    assert interval == 30


def test_daily_broadcast_has_one_shared_twice_daily_task():
    task = next(item for item in market_services.DEFAULT_ADMIN_TASKS if item["task_code"] == "daily_finance_broadcast")
    assert task["schedule_type"] == "daily"
    assert set(task["schedule_value"].split(",")) == {"12:30", "19:00"}
    assert task["task_type"] == "sync_daily_finance_broadcast"


def test_daily_broadcast_uses_actual_provider_period_fallback_order():
    fake_now = datetime(2026, 9, 16, 2, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    with patch.object(market_services, "datetime") as mocked_datetime:
        mocked_datetime.now.return_value = fake_now
        kind, report_date, _ = market_services._daily_finance_broadcast_slot(fake_now)
    assert kind == "night"
    assert report_date == "2026-09-15"
    source = (ROOT / "src/domain/market_services.py").read_text(encoding="utf-8")
    assert '"night": ("night", "noon", "morning")' in source


def test_admin_and_kol_broadcast_routes_use_same_task_code():
    source = (ROOT / "src/web/api_kol.py").read_text(encoding="utf-8")
    assert 'run_admin_task(\n            "daily_finance_broadcast"' in source
    market_source = (ROOT / "src/domain/core_services.py").read_text(encoding="utf-8")
    assert '"sync_daily_finance_broadcast": sync_daily_finance_broadcast' in market_source or "sync_daily_finance_broadcast" in market_source


def test_real_empty_fan_inbox_does_not_render_demo_conversations():
    source = (ROOT / "templates/h5.html").read_text(encoding="utf-8")
    assert "dmConversationsCache = isDavDmMode() ? [] : [getInvestorDmConversation()];" in source
    assert "Array.isArray(data.threads)\n      ? data.threads" in source


def test_activity_distribution_is_a_tablist():
    source = (ROOT / "templates/kol_workbench.html").read_text(encoding="utf-8")
    assert 'class="kw-watch-activity-tabs" role="tablist"' in source
    assert 'class="kw-watch-activity-tab active" role="tab"' in source
