#!/usr/bin/env python3
"""Produce an honest BDD report for exact Gangtise market-card values.

The report separates deterministic contract evidence from a live probe.  A
network failure is reported as blocked, never replaced with fixture values.
"""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain import market_services


REPORT_DIR = PROJECT_ROOT / "tests" / "reports"
HTML_PATH = REPORT_DIR / "gangtise_market_exactness_bdd_report.html"
JSON_PATH = REPORT_DIR / "gangtise_market_exactness_bdd_report.json"
EXPECTED = {
    "source_shanghai_index": {"name": "上证指数", "security_code": "000001.SH", "value": 3911.87},
    "electronic": {"name": "电子", "security_code": "801080.SWI", "value": 8935.03, "change_pct": 2.95},
}


def _fixture(security_code: str) -> dict:
    records = {
        "000001.SH": [("2026-09-17", "3899.62"), ("2026-09-18", "3911.87")],
        "801080.SWI": [("2026-09-17", "8678.99"), ("2026-09-18", "8935.03")],
    }[security_code]
    return {
        "code": "000000",
        "status": True,
        "data": {
            "fieldList": ["securityCode", "securityName", "tradeDate", "open", "high", "low", "close", "volume"],
            "list": [[security_code, EXPECTED["source_shanghai_index" if security_code == "000001.SH" else "electronic"]["name"], date, close, close, close, close, "100"] for date, close in records],
        },
    }


def _contract_case() -> dict:
    requested_paths = []

    def fake_post(path, payload, **_kwargs):
        requested_paths.append({"path": path, "security_code": payload["securityList"][0], "end_date": payload["endDate"]})
        return 200, _fixture(payload["securityList"][0]), 4

    with patch.object(market_services, "post_gangtise_openapi_json", side_effect=fake_post), patch.object(
        market_services, "is_cn_stock_market_open", return_value=False
    ):
        index = market_services._build_market_index_snapshot_item(
            "source_shanghai_index",
            market_services.fetch_gangtise_market_index_history("source_shanghai_index", "2026-09-01", "2026-09-20"),
        )
        sectors, errors = market_services._fetch_gangtise_sector_overview("2026-09-01", "2026-09-20", ["电子"])
    passed = (
        errors == []
        and index.get("price") == EXPECTED["source_shanghai_index"]["value"]
        and sectors and sectors[0].get("value") == EXPECTED["electronic"]["value"]
        and sectors[0].get("change_pct") == EXPECTED["electronic"]["change_pct"]
        and all(row["path"] == market_services.GANGTISE_INDEX_KLINE_DAILY_PATH for row in requested_paths)
    )
    return {
        "name": "指数日K合同与卡片数值映射",
        "mode": "deterministic_contract",
        "passed": passed,
        "detail": "指数接口、最新交易日选择、点位及涨跌幅计算均为严格断言。",
        "evidence": {"requests": requested_paths, "market_card": index, "sector_card": sectors[0] if sectors else {}, "errors": errors},
    }


def _live_case() -> dict:
    index_result = market_services.fetch_gangtise_market_index_history("source_shanghai_index", "2026-09-01", "2026-09-20")
    index_card = market_services._build_market_index_snapshot_item("source_shanghai_index", index_result)
    sectors, sector_errors = market_services._fetch_gangtise_sector_overview("2026-09-01", "2026-09-20", ["电子"])
    sector_card = sectors[0] if sectors else {}
    available = bool(index_card.get("available") and sector_card.get("available"))
    exact = available and index_card.get("price") == EXPECTED["source_shanghai_index"]["value"] and sector_card.get("value") == EXPECTED["electronic"]["value"] and sector_card.get("change_pct") == EXPECTED["electronic"]["change_pct"]
    return {
        "name": "Gangtise 实时接口精确值核验",
        "mode": "live_api",
        "passed": exact,
        "blocked": not available,
        "detail": "实时调用未返回两张可用卡片" if not available else "实时接口已返回两张卡片，按验收锚点比对。",
        "evidence": {
            "index": {key: index_result.get(key) for key in ("http_status", "duration_ms", "path", "payload", "message")},
            "market_card": index_card,
            "sector_card": sector_card,
            "sector_errors": sector_errors,
        },
    }


def _render(report: dict) -> str:
    rows = "".join(
        f"<article class='case {'pass' if case['passed'] else 'blocked'}'><header><h2>{html.escape(case['name'])}</h2><strong>{'PASS' if case['passed'] else ('BLOCKED' if case.get('blocked') else 'FAIL')}</strong></header><p><b>Given</b> 已配置 Gangtise 指数日 K 合同与验收锚点。</p><p><b>When</b> {html.escape(case['mode'])}</p><p><b>Then</b> {html.escape(case['detail'])}</p><details><summary>查看脱敏证据</summary><pre>{html.escape(json.dumps(case['evidence'], ensure_ascii=False, indent=2, default=str))}</pre></details></article>"
        for case in report["cases"]
    )
    overall = "通过" if report["live_passed"] else "未完成实时核验"
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Gangtise 市场精确值 BDD 报告</title><style>
body{{margin:0;background:#eef3f7;color:#132a3d;font:14px/1.65 -apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif}}main{{max-width:1024px;margin:auto;padding:28px 16px 50px}}section,article{{background:#fff;border:1px solid #d8e1e8;border-radius:12px;padding:18px;margin-bottom:14px}}h1,h2{{margin:0 0 8px}}h1{{font-size:27px}}h2{{font-size:18px}}.hero{{border-top:5px solid #16704d}}.metric{{display:inline-block;margin:12px 10px 0 0;padding:8px 12px;border-radius:8px;background:#f5f8fa}}.pass{{border-left:5px solid #16704d}}.blocked{{border-left:5px solid #a66710}}header{{display:flex;justify-content:space-between;gap:12px}}.pass strong{{color:#16704d}}.blocked strong{{color:#a66710}}pre{{white-space:pre-wrap;word-break:break-word;background:#102b40;color:#eaf2f7;padding:12px;border-radius:8px;font-size:11px}}summary{{cursor:pointer;color:#1769aa;font-weight:700}}</style></head><body><main><section class='hero'><h1>Gangtise 市场精确值 BDD 报告</h1><p>生成时间：{html.escape(report['generated_at'])}（北京时间）</p><p>验收锚点：上证指数 <b>3911.87</b>；电子 <b>8935.03</b>；电子涨跌 <b>+2.95%</b>。</p><div class='metric'>合同场景：{report['contract_passed']}</div><div class='metric'>实时接口：{html.escape(overall)}</div><p>实时接口无数据时，本报告保持 BLOCKED，不使用测试夹具或历史快照替代。</p></section>{rows}</main></body></html>"""


def main() -> int:
    contract = _contract_case()
    live = _live_case()
    report = {
        "generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        "contract_passed": bool(contract["passed"]),
        "live_passed": bool(live["passed"]),
        "cases": [contract, live],
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    HTML_PATH.write_text(_render(report), encoding="utf-8")
    print(json.dumps({"html_report": str(HTML_PATH), "json_report": str(JSON_PATH), "contract_passed": report["contract_passed"], "live_passed": report["live_passed"]}, ensure_ascii=False))
    return 0 if contract["passed"] and live["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
