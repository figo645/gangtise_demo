"""BDD contracts for shared Gangtise EDB market snapshots."""

from pathlib import Path
from unittest.mock import patch


def test_gangtise_market_snapshot_uses_four_platform_schedule_slots():
    from src.domain import market_services

    task = next(item for item in market_services.DEFAULT_ADMIN_TASKS if item["task_code"] == "market_snapshot_sync")
    assert task["task_name"] == "Gangtise 市场与行业指标同步"
    assert task["schedule_type"] == "daily"
    assert task["schedule_value"] == "09:30,12:00,14:00,15:30"
    migration = (Path(__file__).resolve().parents[1] / "sql/postgres/135_use_gangtise_market_snapshots.sql").read_text(encoding="utf-8")
    assert "Gangtise EDB" in migration


def test_gangtise_edb_batch_parser_keeps_each_indicator_column_separate():
    from src.domain import market_services

    response = {"data": {"fieldList": ["date", "M1", "M2"], "dataList": [["2026-09-16", "100", "200"], ["2026-09-17", "101", "202"]]}}
    parsed = market_services._normalize_gangtise_edb_batch(response, ["M1", "M2"])
    assert parsed["M1"][-1] == {"date": "2026-09-17", "close": 101.0}
    assert parsed["M2"][-1] == {"date": "2026-09-17", "close": 202.0}


def test_gangtise_edb_fetch_respects_the_ten_indicator_batch_limit():
    from src.domain import market_services

    resolved = {
        str(index): {"indicator_id": f"M{index}"}
        for index in range(31)
    }
    response = {"code": "000000", "status": True, "data": {"fieldList": ["date"], "dataList": []}}
    with patch.object(market_services, "post_gangtise_openapi_json", return_value=(200, response, 1)) as post:
        market_services._fetch_gangtise_market_snapshot_series(resolved)
    assert len(post.call_args_list) == 4
    assert all(len(call.args[1]["indicatorIdList"]) <= 10 for call in post.call_args_list)
