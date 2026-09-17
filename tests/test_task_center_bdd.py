"""BDD contracts for shared market and daily broadcast scheduling."""

from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.domain import core_services, market_services


def test_market_top10_views_share_one_gangtise_edb_task():
    task = next(item for item in market_services.DEFAULT_ADMIN_TASKS if item["task_code"] == "market_snapshot_sync")
    assert task["schedule_type"] == "daily"
    assert task["schedule_value"] == "09:30,12:00,14:00,15:30"
    assert ".SWI" in task["description"]
    assert "申万一级行业" in task["description"]
    assert "标准市场指数" in task["description"]
    assert "按需获取" in task["description"]
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


def test_market_task_is_not_scheduled_during_midday_break():
    task = next(item for item in market_services.DEFAULT_ADMIN_TASKS if item["task_code"] == "market_snapshot_sync")
    assert "12:30" not in task["schedule_value"]
    assert "15:30" in task["schedule_value"]


def test_market_task_marks_an_incomplete_industry_snapshot_as_failed_in_the_shared_run_history():
    task = {"task_code": "market_snapshot_sync", "task_type": "sync_market_snapshot"}
    incomplete = {
        "complete": False,
        "overview_count": 9,
        "expected_overview_count": 9,
        "sector_count": 0,
        "expected_sector_count": 31,
        "errors": ["AKShare 申万一级行业行情未返回有效数据"],
    }
    with patch.object(core_services, "get_admin_task_config", return_value=task), patch.object(
        core_services, "clear_admin_task_stop_request"
    ), patch.object(core_services, "create_admin_task_run", return_value="run-001"), patch.object(
        core_services, "execute_admin_task", return_value=incomplete
    ), patch.object(core_services, "finish_admin_task_run") as finish:
        with pytest.raises(RuntimeError, match="market_snapshot_incomplete:overview=9/9:sectors=0/31"):
            core_services.run_admin_task("market_snapshot_sync", trigger_mode="tenant_manual", force=True)

    assert finish.call_args.kwargs["error_message"].startswith("market_snapshot_incomplete:")


def test_stopped_task_can_only_restart_after_the_current_platform_run_has_finished():
    stopped_task = {"task_code": "market_snapshot_sync", "last_run_status": "cancelled"}
    with patch.object(core_services, "get_admin_task_config", return_value=stopped_task), patch.object(
        core_services, "resume_admin_task", return_value={"task_code": "market_snapshot_sync", "enabled": True}
    ) as resume_task, patch.object(
        core_services, "run_admin_task", return_value={"run_code": "restart-001"}
    ) as run_task:
        result = core_services.restart_admin_task("market_snapshot_sync", trigger_mode="tenant_manual_restart", force=True)

    assert result["run_code"] == "restart-001"
    resume_task.assert_called_once_with("market_snapshot_sync")
    run_task.assert_called_once_with("market_snapshot_sync", trigger_mode="tenant_manual_restart", force=True)

    running_task = {"task_code": "market_snapshot_sync", "last_run_status": "running"}
    with patch.object(core_services, "get_admin_task_config", return_value=running_task), patch.object(
        core_services, "resume_admin_task"
    ) as resume_task, patch.object(core_services, "run_admin_task") as run_task:
        with pytest.raises(RuntimeError, match="admin_task_already_running"):
            core_services.restart_admin_task("market_snapshot_sync")

    resume_task.assert_not_called()
    run_task.assert_not_called()


def test_running_task_does_not_clear_a_pending_stop_request_when_a_second_run_is_rejected():
    task = {"task_code": "market_snapshot_sync", "task_type": "sync_market_snapshot"}
    with patch.object(core_services, "get_admin_task_config", return_value=task), patch.object(
        core_services, "create_admin_task_run", side_effect=RuntimeError("admin_task_already_running")
    ), patch.object(core_services, "clear_admin_task_stop_request") as clear_request:
        with pytest.raises(RuntimeError, match="admin_task_already_running"):
            core_services.run_admin_task("market_snapshot_sync", trigger_mode="tenant_manual", force=True)

    clear_request.assert_not_called()


def test_force_stopped_run_cannot_overwrite_the_newer_task_lifecycle_status():
    class CancelledRunDb:
        def __init__(self):
            self.committed = False

        def execute(self, *_args, **_kwargs):
            return SimpleNamespace(rowcount=0)

        def commit(self):
            self.committed = True

    db = CancelledRunDb()
    with patch.object(core_services, "get_db", return_value=db), patch.object(core_services, "update_admin_task_status") as update_status:
        core_services.finish_admin_task_run("old-run", "market_snapshot_sync", True, 0.0, summary="旧任务完成")

    assert db.committed is True
    update_status.assert_not_called()


def test_scheduler_startup_refreshes_only_shared_market_and_news_tasks():
    with patch.object(core_services, "run_admin_task", return_value={"run_code": "startup-run"}) as run_task:
        core_services.run_scheduler_startup_sync()

    assert [call.args[0] for call in run_task.call_args_list] == ["market_snapshot_sync", "news_title_impact_sync"]
    assert all(call.kwargs == {"trigger_mode": "scheduler_startup", "force": True} for call in run_task.call_args_list)


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
