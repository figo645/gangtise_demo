"""Run theme_daily_report contract tests and a real Gangtise probe."""

from __future__ import annotations

import datetime as dt
import html
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPORT_DIR = ROOT / "tests" / "reports"
HTML_PATH = REPORT_DIR / "theme_daily_report_bdd_report.html"
JSON_PATH = REPORT_DIR / "theme_daily_report_bdd_report.json"
ENDPOINT = "/application/open-ai/agent/theme-tracking"
THEME_ID = "121000130"
TARGET_DATE = "2026-09-17"
PERIODS = (("morning", "晨报"), ("noon", "午间报"), ("night", "晚报"))


def run_contract_tests():
    junit = REPORT_DIR / "theme_daily_report_bdd.junit.xml"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_theme_daily_report_bdd.py", "--junitxml", str(junit)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    cases = []
    root = ET.parse(junit).getroot()
    for node in root.iter("testcase"):
        failure = node.find("failure") or node.find("error")
        cases.append({
            "name": node.attrib.get("name", ""),
            "status": "FAIL" if failure is not None else "PASS",
            "duration": float(node.attrib.get("time", 0)),
            "detail": (failure.attrib.get("message") if failure is not None else "BDD 断言通过") or "",
        })
    return result, cases


def live_probe():
    from src.runtime import app
    from src.domain.market_services import post_gangtise_openapi_json

    rows = []
    with app.app_context():
        for report_type, label in PERIODS:
            payload = {"themeId": THEME_ID, "type": [report_type]}
            try:
                status, response, duration = post_gangtise_openapi_json(ENDPOINT, payload, timeout=45)
                data = response.get("data") if isinstance(response, dict) else {}
                content = data.get("content") if isinstance(data, dict) else ""
                provider_date = ""
                if isinstance(data, dict):
                    provider_date = str(data.get("reportDate") or data.get("report_date") or data.get("date") or "")
                ok = status == 200 and isinstance(response, dict) and response.get("code") == "000000" and bool(str(content).strip())
                rows.append({
                    "period": report_type,
                    "label": label,
                    "status": "PASS" if ok else "FAIL",
                    "http_status": status,
                    "duration_ms": duration,
                    "provider_date": provider_date,
                    "content_chars": len(str(content or "")),
                    "content_preview": str(content or "")[:240],
                    "response_keys": sorted(response.keys()) if isinstance(response, dict) else [],
                    "message": str((response or {}).get("message") or (response or {}).get("msg") or "")[:500] if isinstance(response, dict) else "",
                })
            except Exception as exc:
                rows.append({
                    "period": report_type,
                    "label": label,
                    "status": "FAIL",
                    "http_status": 0,
                    "duration_ms": 0,
                    "provider_date": "",
                    "content_chars": 0,
                    "content_preview": "",
                    "response_keys": [],
                    "message": str(exc)[:800],
                })
    return rows


def render(report):
    def esc(value):
        return html.escape(str(value or ""))

    contract_rows = "".join(
        f"<tr><td>{esc(item['status'])}</td><td>{esc(item['name'])}</td><td>{item['duration']:.3f}s</td><td>{esc(item['detail'])}</td></tr>"
        for item in report["contract_cases"]
    )
    live_cards = "".join(
        f"<article class='scenario {item['status'].lower()}'><header><h2>{esc(item['label'])} <code>type=[{esc(item['period'])}]</code></h2><b>{esc(item['status'])}</b></header>"
        f"<p><strong>When</strong> POST <code>{ENDPOINT}</code>，payload 为 <code>{{\"themeId\":\"{THEME_ID}\",\"type\":[\"{esc(item['period'])}\"]}}</code></p>"
        f"<p><strong>Then</strong> HTTP 200、业务码 <code>000000</code>、<code>data.content</code> 非空；目标日期：<code>{TARGET_DATE}</code>。</p>"
        f"<div class='evidence'>HTTP {item['http_status']} · {item['duration_ms']} ms · provider_date={esc(item['provider_date']) or '--'} · content_chars={item['content_chars']}</div>"
        f"<p class='message'>{esc(item['message']) or '未返回错误消息'}</p><details><summary>响应摘要</summary><pre>{esc(json.dumps(item, ensure_ascii=False, indent=2))}</pre></details></article>"
        for item in report["live_probe"]
    )
    contract_pass = sum(item["status"] == "PASS" for item in report["contract_cases"])
    contract_fail = len(report["contract_cases"]) - contract_pass
    live_pass = sum(item["status"] == "PASS" for item in report["live_probe"])
    live_fail = len(report["live_probe"]) - live_pass
    overall = "PASS" if contract_fail == 0 and live_fail == 0 else "FAIL"
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>theme_daily_report BDD 测试报告</title><style>
body{{margin:0;background:#f5f7f7;color:#172326;font:14px/1.65 -apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif}}main{{max-width:1160px;margin:auto;padding:30px 20px 60px}}h1{{margin:0 0 6px}}h2{{font-size:17px;margin:0}}.sub{{color:#607175}}.hero,.panel,.scenario{{background:#fff;border:1px solid #d8e2e1;border-radius:8px;padding:18px;margin:14px 0}}.hero{{background:#172b3a;color:#fff;border:0}}.metrics{{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}}.metric{{background:#ffffff16;border:1px solid #ffffff2b;border-radius:6px;padding:10px 14px;min-width:120px}}.metric strong{{display:block;font-size:23px}}.pass{{color:#087443}}.fail{{color:#b42318}}.hero .pass{{color:#9bf0bd}}.hero .fail{{color:#ffb2ac}}.scenario{{border-left:4px solid #087443}}.scenario.fail{{border-left-color:#b42318}}.scenario header{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}}.evidence{{background:#eef4f3;color:#52656a;padding:8px 10px;border-radius:4px;overflow-wrap:anywhere}}.message{{color:#607175}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px 8px;border-bottom:1px solid #e7eded;text-align:left;vertical-align:top}}th{{background:#edf5f4}}code,pre{{font:12px ui-monospace,SFMono-Regular,Menlo,monospace}}pre{{max-height:480px;overflow:auto;background:#172127;color:#e4f0ef;padding:12px;border-radius:4px;white-space:pre-wrap;word-break:break-word}}.note{{border-left:4px solid #006c69;background:#e7f4f2;padding:12px 14px}}details{{margin-top:10px}}summary{{cursor:pointer;font-weight:650}}@media(max-width:640px){{main{{padding:22px 14px}}.scenario header{{display:block}}}}
</style></head><body><main><section class='hero'><h1>Gangtise theme_daily_report BDD 测试报告</h1><div class='sub'>生成时间：{esc(report['generated_at'])} · 目标日期：{TARGET_DATE} · 主题 ID：{THEME_ID}</div><div style='margin-top:10px'>总体结果：<b class='{overall.lower()}'>{overall}</b></div><div class='metrics'><div class='metric'>契约场景<strong>{len(report['contract_cases'])}</strong></div><div class='metric'>契约通过<strong class='pass'>{contract_pass}</strong></div><div class='metric'>真实探针<strong>{len(report['live_probe'])}</strong></div><div class='metric'>真实通过<strong class='pass'>{live_pass}</strong></div><div class='metric'>真实失败<strong class='fail'>{live_fail}</strong></div></div></section>
<section class='panel'><h2>测试结论</h2><div class='note'>参考材料确认的主题日报接口为 <code>{ENDPOINT}</code>，请求体为 <code>{{themeId,type}}</code>，返回正文位于 <code>data.content</code>。接口示例没有日期字段，因此本报告不会把“请求成功”误判为“已获得 2026-09-17”；只有返回中出现可识别的日期并等于目标日期，才能完成日期断言。内容长度按最多 1000 字进行展示截断，原始响应不在本探针中发布。</div></section>
<section class='panel'><h2>Feature: 获取主题日报早报、午间报、晚报</h2>{live_cards}</section>
<section class='panel'><h2>离线契约 BDD 场景</h2><table><thead><tr><th>结果</th><th>场景</th><th>耗时</th><th>断言</th></tr></thead><tbody>{contract_rows}</tbody></table></section>
<section class='panel'><h2>接口与日期说明</h2><p>早报使用 <code>type=[morning]</code>，午间报使用 <code>type=[noon]</code>，晚报使用 <code>type=[night]</code>。当前 API 契约不包含 <code>startDate/endDate</code>，因此若服务端只返回最新一份主题日报，无法通过此接口强制读取历史 9 月 17 日版本；需要上游返回 <code>reportDate/date</code> 或提供历史查询参数后才能严格验收。</p></section></main></body></html>"""


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    pytest_result, cases = run_contract_tests()
    live = live_probe()
    report = {
        "title": "Gangtise theme_daily_report BDD 测试报告",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "contract_cases": cases,
        "live_probe": live,
        "contract_exit_code": pytest_result.returncode,
        "pytest_output": pytest_result.stdout[-12000:],
    }
    JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    HTML_PATH.write_text(render(report), encoding="utf-8")
    live_fail = sum(item["status"] == "FAIL" for item in live)
    contract_fail = sum(item["status"] == "FAIL" for item in cases)
    result = "PASS" if not live_fail and not contract_fail and pytest_result.returncode == 0 else "FAIL"
    print(json.dumps({"result": result, "html_report": str(HTML_PATH), "json_report": str(JSON_PATH), "contract_pass": len(cases) - contract_fail, "contract_fail": contract_fail, "live_pass": len(live) - live_fail, "live_fail": live_fail}, ensure_ascii=False))
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
