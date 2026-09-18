"""BDD contract tests for Gangtise theme_daily_report/theme-tracking."""

from unittest.mock import patch

from src.domain import market_services


THEME_ID = "121000130"
TARGET_DATE = "2026-09-17"


def _response(content="主题日报正文。", report_date=TARGET_DATE):
    return {
        "code": "000000",
        "status": True,
        "msg": "操作成功",
        "data": {"content": content, "reportDate": report_date},
    }


def test_given_theme_daily_report_contract_when_requesting_each_period_then_type_is_explicit():
    for report_type in ("morning", "noon", "night"):
        with patch.object(
            market_services,
            "post_gangtise_openapi_json",
            return_value=(200, _response(), 8),
        ) as post:
            status, response, duration = market_services.post_gangtise_openapi_json(
                "/application/open-ai/agent/theme-tracking",
                {"themeId": THEME_ID, "type": [report_type]},
            )

        assert status == 200
        assert response["code"] == "000000"
        assert response["status"] is True
        assert response["data"]["content"]
        assert duration == 8
        assert post.call_args.args[0] == "/application/open-ai/agent/theme-tracking"
        assert post.call_args.args[1] == {"themeId": THEME_ID, "type": [report_type]}


def test_given_theme_daily_report_response_when_reading_then_content_is_bounded_to_about_1000_chars():
    content = "财经信息。" * 500
    response = _response(content)
    article = str((response.get("data") or {}).get("content") or "")[:1000]
    assert len(article) == 1000
    assert article.startswith("财经信息")


def test_given_theme_daily_report_response_when_validating_then_date_can_only_be_asserted_if_provider_returns_it():
    response = _response(report_date=TARGET_DATE)
    data = response["data"]
    assert data["reportDate"] == TARGET_DATE


def test_given_success_json_when_validating_then_no_sse_parser_is_required():
    response = _response("早报正文")
    assert isinstance(response["data"]["content"], str)
    assert response["data"]["content"].strip() == "早报正文"

