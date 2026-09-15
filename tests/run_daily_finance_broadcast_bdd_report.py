"""Run broadcast BDD checks and one real Gangtise probe, then publish HTML."""

from __future__ import annotations

import datetime as dt
import html
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "tests" / "reports"
HTML_PATH = REPORT_DIR / "daily_finance_broadcast_bdd_report.html"
JSON_PATH = REPORT_DIR / "daily_finance_broadcast_bdd_report.json"


def run_bdd():
    junit = REPORT_DIR / "daily_finance_broadcast_bdd.junit.xml"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_daily_finance_broadcast_bdd.py", "--junitxml", str(junit)],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    cases = []
    for node in ET.parse(junit).getroot().iter("testcase"):
        failure = node.find("failure") or node.find("error")
        cases.append({
            "name": node.attrib.get("name", ""),
            "status": "FAIL" if failure is not None else "PASS",
            "duration": float(node.attrib.get("time", 0)),
            "detail": ((failure.attrib.get("message") if failure is not None else None) or "BDD 断言通过"),
        })
    return result, cases


def live_probe():
    from src.runtime import app
    from src.domain.market_services import _daily_finance_broadcast_slot, fetch_gangtise_daily_finance_broadcast

    with app.app_context():
        kind, report_date, now = _daily_finance_broadcast_slot()
        try:
            result = fetch_gangtise_daily_finance_broadcast(kind, report_date, timeout=30)
            return {
                "status": "PASS", "classification": "真实接口通过", "slot": kind,
                "report_date": report_date, "checked_at": now.isoformat(),
                "http_status": 200, "duration_ms": result.get("duration_ms", 0),
                "content_chars": len(result.get("text") or ""),
                "endpoint": result.get("endpoint"),
                "selected_type": (result.get("selected_record") or {}).get("reportTypeName"),
                "preview": (result.get("text") or "")[:240],
            }
        except Exception as exc:
            return {
                "status": "FAIL", "classification": "环境/真实服务阻断", "slot": kind,
                "report_date": report_date, "checked_at": now.isoformat(),
                "error": str(exc), "endpoint": "/application/open-ai/hot-topic/getList",
            }


def render(report):
    live = report["live_probe"]
    rows = "".join(
        "<tr><td><b class='%s'>%s</b></td><td>%s</td><td>%.3fs</td><td><pre>%s</pre></td></tr>"
        % (case["status"].lower(), case["status"], html.escape(case["name"]), case["duration"], html.escape(case["detail"]))
        for case in report["bdd_cases"]
    )
    live_json = html.escape(json.dumps(live, ensure_ascii=False, indent=2))
    result_class = report["result"].lower()
    return """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>午间与晚间财经播报 BDD 真实测试报告</title><style>
body{margin:0;background:#f4f7fb;color:#172033;font:14px/1.65 -apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif}main{max-width:1180px;margin:auto;padding:30px 20px 60px}.hero{background:#10233f;color:#fff;border-radius:16px;padding:28px;box-shadow:0 12px 30px #10233f24}h1{margin:0 0 8px;font-size:26px}h2{font-size:18px;margin:0 0 14px}.muted{color:#bdcbe0;font-size:13px}.status{font-weight:800}.status.pass{color:#83e0a7}.status.fail{color:#ffaaa5}.metrics{display:flex;gap:10px;flex-wrap:wrap;margin-top:20px}.metric{min-width:120px;padding:11px 14px;border:1px solid #ffffff22;border-radius:9px;background:#ffffff12}.metric b{display:block;font-size:22px}.panel{margin-top:18px;padding:21px;background:#fff;border:1px solid #dfe6ef;border-radius:14px;overflow:auto}.note{padding:12px 14px;background:#f8fbff;border-left:4px solid #3977bd;line-height:1.7}table{width:100%%;border-collapse:collapse}th,td{padding:10px 8px;border-bottom:1px solid #e7edf3;text-align:left;vertical-align:top}th{background:#f7f9fc}pre{white-space:pre-wrap;word-break:break-word;margin:0;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}.pass{color:#137a3d}.fail{color:#b42318}code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace}
</style></head><body><main><section class='hero'><h1>午间与晚间财经播报 BDD 真实测试报告</h1><div class='muted'>生成时间：%s · 真实探针不写数据库、不发布消息</div><div style='margin-top:12px'>总体结果：<span class='status %s'>%s</span></div><div class='metrics'><div class='metric'>BDD 场景<b>%d</b></div><div class='metric'>断言通过<b>%d</b></div><div class='metric'>断言失败<b>%d</b></div><div class='metric'>真实接口<b class='%s'>%s</b></div></div></section>
<section class='panel'><h2>验收结论</h2><div class='note'>本测试分为两层：BDD 离线契约使用已记录的 Gangtise 成功 JSON 验证时段匹配、正文抽取、格式编排和异常阻断；真实探针使用当前工作区配置实际调用 Gangtise。只有真实探针拿到正文并完成时段匹配，才能认定生产播报链路可用。</div></section>
<section class='panel'><h2>真实 Gangtise 探针</h2><p>接口：<code>%s</code> · 时段：<code>%s</code> · 日期：<code>%s</code></p><pre>%s</pre></section>
<section class='panel'><h2>BDD 场景明细</h2><table><thead><tr><th>结果</th><th>场景</th><th>耗时</th><th>证据</th></tr></thead><tbody>%s</tbody></table></section>
<section class='panel'><h2>用户阅读体验验收标准</h2><div class='note'>通过条件：标题明确为早间、午间或晚间财经播报；优先使用目标时段的 closeReading，缺失时使用该时段主题摘要；内容被编排为标题、日期、播报正文和信息整理声明；只有时段和主题摘要都不可用时才阻断发布。</div></section>
<section class='panel'><h2>失败含义</h2><p>“热点话题”显示成功只能证明上游请求成功；任务还必须完成目标时段匹配和正文提取。当前真实探针失败时，报告会保留真实错误，不将其解释为播报已发布。</p></section></main></body></html>""" % (
        html.escape(report["generated_at"]), result_class, report["result"], len(report["bdd_cases"]),
        report["bdd_pass"], report["bdd_fail"], live["status"].lower(), live["status"],
        html.escape(live.get("endpoint", "")), html.escape(live.get("slot", "")),
        html.escape(live.get("report_date", "")), live_json, rows,
    )


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    pytest_result, cases = run_bdd()
    live = live_probe()
    failed = sum(case["status"] == "FAIL" for case in cases)
    report = {
        "title": "午间与晚间财经播报 BDD 真实测试报告",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "result": "PASS" if pytest_result.returncode == 0 and live["status"] == "PASS" else "FAIL",
        "bdd_pass": len(cases) - failed, "bdd_fail": failed, "bdd_cases": cases,
        "live_probe": live, "pytest_output": pytest_result.stdout[-12000:],
    }
    JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    HTML_PATH.write_text(render(report), encoding="utf-8")
    print(json.dumps({"result": report["result"], "html_report": str(HTML_PATH), "json_report": str(JSON_PATH), "bdd_pass": report["bdd_pass"], "bdd_fail": failed, "live_status": live["status"]}, ensure_ascii=False))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
