"""BDD contracts for DaV access to the platform-owned shared data tasks."""

from pathlib import Path
from unittest.mock import patch

from src.runtime import app
from src.web import api_kol


DAV = {"id": "dav-1", "role": "dav", "tenant_slug": "laowang"}
OTHER_DAV = {"id": "dav-2", "role": "dav", "tenant_slug": "duoge"}
TASKS = {
    "market_snapshot_sync": {"task_code": "market_snapshot_sync", "task_name": "市场与行业指标同步", "enabled": True},
    "news_title_impact_sync": {"task_code": "news_title_impact_sync", "task_name": "新闻源采集同步", "enabled": True},
}


def _response_json(value):
    return value[0].get_json() if isinstance(value, tuple) else value.get_json()


def _status(value):
    return value[1] if isinstance(value, tuple) else value.status_code


def test_given_dav_when_loading_shared_tasks_then_it_reads_the_same_admin_configs_and_runs():
    runs = {code: [{"task_code": code, "run_status": "success"}] for code in TASKS}
    with app.test_request_context("/api/tenant/laowang/shared-data-tasks"), patch.object(
        api_kol, "get_current_authenticated_user", return_value=DAV
    ), patch.object(api_kol, "get_admin_task_config", side_effect=lambda code: TASKS.get(code)), patch.object(
        api_kol, "list_admin_task_runs", side_effect=lambda task_code, limit: runs[task_code]
    ) as list_runs:
        response = api_kol.api_tenant_shared_data_tasks("laowang")

    payload = _response_json(response)
    assert _status(response) == 200
    assert payload["ok"] is True
    assert [item["task"]["task_code"] for item in payload["tasks"]] == list(TASKS)
    assert [item["runs"] for item in payload["tasks"]] == [runs[code] for code in TASKS]
    assert [call.kwargs for call in list_runs.call_args_list] == [
        {"task_code": "market_snapshot_sync", "limit": 10},
        {"task_code": "news_title_impact_sync", "limit": 10},
    ]


def test_given_dav_when_running_shared_market_task_then_the_platform_task_is_run_without_tenant_copy():
    with app.test_request_context("/api/tenant/laowang/shared-data-tasks/market_snapshot_sync/run", method="POST"), patch.object(
        api_kol, "get_current_authenticated_user", return_value=DAV
    ), patch.object(
        api_kol, "run_admin_task", return_value={"run_code": "market-001", "summary": "完成", "result": {"count": 31}}
    ) as run_task:
        response = api_kol.api_run_tenant_shared_data_task("laowang", "market_snapshot_sync")

    assert _status(response) == 200
    assert _response_json(response)["run_code"] == "market-001"
    run_task.assert_called_once_with("market_snapshot_sync", trigger_mode="tenant_manual", force=True)


def test_given_dav_when_using_another_tenant_or_non_shared_task_then_access_is_denied():
    with app.test_request_context("/api/tenant/duoge/shared-data-tasks"), patch.object(
        api_kol, "get_current_authenticated_user", return_value=DAV
    ):
        denied = api_kol.api_tenant_shared_data_tasks("duoge")
    with app.test_request_context("/api/tenant/laowang/shared-data-tasks/daily_finance_broadcast/run", method="POST"), patch.object(
        api_kol, "get_current_authenticated_user", return_value=DAV
    ):
        unknown = api_kol.api_run_tenant_shared_data_task("laowang", "daily_finance_broadcast")

    assert _status(denied) == 403
    assert _response_json(denied)["error"] == "tenant_scope_forbidden"
    assert _status(unknown) == 404
    assert _response_json(unknown)["error"] == "shared_data_task_not_allowed"


def test_given_workbench_template_then_dav_can_read_and_run_the_two_shared_tasks_but_not_edit_schedule():
    source = (Path(__file__).resolve().parents[1] / "templates" / "kol_workbench.html").read_text(encoding="utf-8")
    assert 'data-section="shared-data-sync"' in source
    assert "市场与行业指标同步" in source
    assert "新闻源采集同步" in source
    assert "kwLoadSharedDataSyncPanel" in source
    assert "kwRunSharedDataSync" in source
    assert "/shared-data-tasks/${encodeURIComponent(taskCode)}/run" in source
    assert "平台共享任务。Admin 与全部大V查看同一配置" in source
    assert "schedule_type" not in source[source.index('id="workbench-section-shared-data-sync"'):source.index('id="workbench-section-published"')]
