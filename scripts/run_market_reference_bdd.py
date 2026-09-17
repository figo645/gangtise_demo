#!/usr/bin/env python3
"""Run a live AKShare reference comparison and emit an auditable HTML report.

This command intentionally fails closed: unavailable providers or a stale
snapshot are reported as failures; no screenshot value is used as a fallback.
"""

from __future__ import annotations

import html
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain import market_services


REFERENCE = {
    "source_shanghai_index": ("上证指数", 3875.60, -0.41),
    "source_shenzhen_index": ("深证成指", 13409.91, -0.33),
    "source_hsi": ("恒生指数", 24604.29, -0.44),
    "source_hscei": ("国企指数", 8175.36, -0.38),
    "source_hscci": ("红筹指数", 4040.85, -0.92),
    "source_dji": ("道琼斯", 51461.90, -1.21),
    "source_nasdaq": ("纳斯达克", 25978.42, -0.01),
    "source_sp500": ("标普500", 7551.81, -0.45),
}
MAX_VALUE_DELTA = 0.02
MAX_PERCENT_DELTA = 0.02


def _result_row(code: str) -> dict:
    name, expected_value, expected_percent = REFERENCE[code]
    result = market_services.fetch_akshare_market_index_history(code, "2026-09-15", "2026-09-17")
    item = market_services._build_market_index_snapshot_item(code, result)
    if not item.get("available"):
        return {"code": code, "name": name, "expected_value": expected_value, "expected_percent": expected_percent,
                "actual_value": "--", "actual_percent": "--", "status": "BLOCKED", "detail": item.get("message") or result.get("message")}
    actual_value = float(item["price"])
    actual_percent = float(item["change_pct"])
    matched = abs(actual_value - expected_value) <= MAX_VALUE_DELTA and abs(actual_percent - expected_percent) <= MAX_PERCENT_DELTA
    return {"code": code, "name": name, "expected_value": expected_value, "expected_percent": expected_percent,
            "actual_value": actual_value, "actual_percent": actual_percent,
            "status": "PASS" if matched else "MISMATCH", "detail": item.get("updated_at") or ""}


def main() -> int:
    rows = [_result_row(code) for code in REFERENCE]
    sectors = market_services._fetch_akshare_sector_overview()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    passed = sum(row["status"] == "PASS" for row in rows)
    table_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{:.2f}</td><td>{:+.2f}%</td><td>{}</td><td>{}</td><td class='{}'>{}</td><td>{}</td></tr>".format(
            html.escape(row["code"]), html.escape(row["name"]), row["expected_value"], row["expected_percent"],
            row["actual_value"] if isinstance(row["actual_value"], str) else f"{row['actual_value']:.2f}",
            row["actual_percent"] if isinstance(row["actual_percent"], str) else f"{row['actual_percent']:+.2f}%",
            row["status"].lower(), row["status"], html.escape(str(row["detail"])),
        ) for row in rows
    )
    sector_status = "PASS" if len(sectors) == len(market_services.SHENWAN_LEVEL1_INDUSTRIES) else "BLOCKED"
    report = f"""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>市场实时基准 BDD 报告</title>
<style>body{{font:14px/1.6 sans-serif;margin:32px;color:#17233a}}table{{border-collapse:collapse;width:100%}}th,td{{padding:9px;border:1px solid #dce3eb;text-align:left}}th{{background:#eff5fb}}.pass{{color:#087443;font-weight:bold}}.blocked,.mismatch{{color:#b42318;font-weight:bold}}.note{{background:#fff7e6;padding:12px;border-left:4px solid #d89416}}</style>
<h1>市场实时基准 BDD 报告</h1><p>执行时间：{now}；基准截图时间：2026-09-17 16:14（北京时间）</p>
<p>指数通过：{passed}/{len(rows)}；申万一级行业：{len(sectors)}/{len(market_services.SHENWAN_LEVEL1_INDUSTRIES)} <b class='{sector_status.lower()}'>{sector_status}</b></p>
<table><tr><th>代码</th><th>指标</th><th>截图点位</th><th>截图涨跌幅</th><th>AKShare 点位</th><th>AKShare 涨跌幅</th><th>结论</th><th>明细</th></tr>{table_rows}</table>
<h2>口径规则</h2><div class='note'>行业截图的 <code>0180xxxx</code> 属于另一行业指数编码体系，不能与申万一级行业逐项判定相等。该任务只接受完整 31 个申万一级行业；少于 31 条即失败，不覆盖快照。</div>
<p>阈值：点位 ±{MAX_VALUE_DELTA}，涨跌幅 ±{MAX_PERCENT_DELTA} 个百分点。任何 API 不可达、日期不一致或超出阈值均为失败，不回退截图数据。</p></html>"""
    target = PROJECT_ROOT / "tests/reports/market_reference_bdd_report.html"
    target.write_text(report, encoding="utf-8")
    print(target)
    return 0 if passed == len(rows) and sector_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
