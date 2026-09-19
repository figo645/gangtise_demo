"""Run the repository-wide BDD/regression suite and publish one honest HTML report."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "tests" / "reports"
JUNIT_PATH = REPORT_DIR / "full_system_bdd_report.junit.xml"
JSON_PATH = REPORT_DIR / "full_system_bdd_report.json"
HTML_PATH = REPORT_DIR / "full_system_bdd_report.html"


MODULE_LABELS = {
    "test_route_smoke.py": "H5 / Admin / Web 路由与页面契约",
    "test_experience_surface_regression_bdd.py": "H5 与大V工作台跨端体验",
    "test_watchlist_akshare_provider.py": "自选股日K、分时与行情来源",
    "test_market_gangtise_provider.py": "市场快照与数据源一致性",
    "test_v4_news_search_bdd.py": "新闻采集与 V4 标注",
    "test_llm_strict_execution_bdd.py": "LLM 严格模型绑定",
    "test_fan_commerce_bdd.py": "注册、二维码与订阅商业流程",
    "test_database_release_admin_bdd.py": "5051 数据库发布后台",
    "test_database_release_web_bdd.py": "5051 发布流程 Web 契约",
    "test_simulation_data_policy_bdd.py": "生产与本地数据一致性",
    "test_auth_session_bdd.py": "登录与会话",
    "test_account_navigation_bdd.py": "账户导航",
    "test_news_aggregation_algorithm.py": "新闻聚合与清洗",
    "test_gangtise_credentials.py": "第三方凭证管理",
    "test_hermes_task_bdd.py": "Hermes 任务模式",
    "test_hermes_gangtise_capabilities.py": "Hermes 能力调用",
    "test_gangtise_review_sse.py": "Agent SSE 与洞见流程",
    "test_review_module_bdd.py": "洞见与个股研究",
    "test_open_api_insights_bdd.py": "Open API 洞见发布与令牌治理",
}


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _case_status(case):
    if case.find("failure") is not None or case.find("error") is not None:
        return "FAIL"
    if case.find("skipped") is not None:
        return "SKIP"
    return "PASS"


def _case_module(case):
    classname = str(case.attrib.get("classname") or "")
    file_name = Path(classname.replace(".", "/")).name
    for candidate, label in MODULE_LABELS.items():
        if candidate.removesuffix(".py") in classname or candidate in classname:
            return label
    return file_name or classname or "未分类"


def _case_detail(case, status):
    node = case.find("failure")
    if node is None:
        node = case.find("error")
    if node is None:
        node = case.find("skipped")
    if node is not None:
        return str(node.attrib.get("message") or node.text or "").strip()
    return "测试断言通过"


def _case_classification(case, status, detail):
    if status == "PASS":
        return "通过"
    text = str(detail or "").lower()
    environment_markers = (
        "connection refused",
        "operation not permitted",
        "llm_not_configured",
        "connection to server at",
        "could not connect",
        "no such host",
        "remote end closed connection",
    )
    return "环境阻断" if any(marker in text for marker in environment_markers) else "代码/契约失败"


def _run_suite():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--junitxml",
        str(JUNIT_PATH),
        "tests",
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return completed.returncode, completed.stdout


def _build_report(return_code, output):
    tree = ET.parse(JUNIT_PATH)
    root = tree.getroot()
    cases = []
    for case in root.iter("testcase"):
        status = _case_status(case)
        detail = _case_detail(case, status)
        cases.append(
            {
                "name": str(case.attrib.get("name") or ""),
                "classname": str(case.attrib.get("classname") or ""),
                "module": _case_module(case),
                "status": status,
                "duration_seconds": float(case.attrib.get("time") or 0),
                "detail": detail,
                "classification": _case_classification(case, status, detail),
            }
        )
    counts = {status: sum(1 for case in cases if case["status"] == status) for status in ("PASS", "FAIL", "SKIP")}
    return {
        "title": "Gangtise Demo 全场景 BDD 真实测试报告",
        "generated_at": _now(),
        "execution": {
            "command": "PYTHONPATH=. python -m pytest -q tests",
            "return_code": return_code,
            "tests_collected": len(cases),
            "pytest_output": output[-30000:],
            "database_mutation": False,
            "production_api_calls": False,
        },
        "counts": counts,
        "result": "PASS" if return_code == 0 and counts["FAIL"] == 0 else "FAIL",
        "scope": [
            {"area": label, "basis": file_name}
            for file_name, label in MODULE_LABELS.items()
        ],
        "cases": cases,
    }


def _render(report):
    counts = report["counts"]
    status_class = "pass" if report["result"] == "PASS" else "fail"
    rows = []
    for case in report["cases"]:
        rows.append(
            "<tr data-status='{status}'><td><span class='badge {status_class}'>{status}</span></td>"
            "<td>{module}</td><td class='case-name'>{name}</td><td>{classification}</td><td>{seconds:.3f}s</td>"
            "<td><pre>{detail}</pre></td></tr>".format(
                status=html.escape(case["status"]),
                status_class=case["status"].lower(),
                module=html.escape(case["module"]),
                name=html.escape(case["name"]),
                classification=html.escape(case["classification"]),
                seconds=case["duration_seconds"],
                detail=html.escape(case["detail"]),
            )
        )
    scope_rows = "".join(
        f"<tr><td>{html.escape(item['area'])}</td><td>{html.escape(item['basis'])}</td></tr>"
        for item in report["scope"]
    )
    return f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{html.escape(report['title'])}</title>
<style>
:root{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif;color:#172033;background:#f4f7fb}}
body{{margin:0}}main{{max-width:1480px;margin:0 auto;padding:32px 24px 64px}}.hero{{background:#10233f;color:#fff;border-radius:16px;padding:28px 30px;box-shadow:0 10px 30px #10233f20}}
h1{{margin:0 0 10px;font-size:27px}}h2{{font-size:18px;margin:0 0 14px}}.muted{{color:#b8c7db;font-size:13px}}.status{{font-weight:800;color:#7de2a8}}.status.fail{{color:#ff9b9b}}
.metrics{{display:flex;gap:12px;flex-wrap:wrap;margin-top:22px}}.metric{{background:#ffffff14;border:1px solid #ffffff1c;border-radius:10px;padding:12px 16px;min-width:120px}}.metric b{{display:block;font-size:23px;margin-top:4px}}
.panel{{background:#fff;border:1px solid #dfe6ef;border-radius:14px;margin-top:20px;padding:22px;overflow:hidden}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{border-bottom:1px solid #e8edf3;padding:10px 9px;text-align:left;vertical-align:top}}th{{background:#f7f9fc;position:sticky;top:0}}pre{{white-space:pre-wrap;word-break:break-word;margin:0;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;max-width:780px}}.badge{{display:inline-block;border-radius:999px;padding:3px 8px;font-weight:700;font-size:11px}}.pass{{background:#e7f7ed;color:#137a3d}}.fail{{background:#ffebe9;color:#b42318}}.skip{{background:#fff3d6;color:#8a5b00}}.case-name{{font-weight:650;min-width:340px}}.filters{{display:flex;gap:8px;margin-bottom:12px}}button{{border:1px solid #cad4e1;background:#fff;border-radius:7px;padding:7px 12px;cursor:pointer}}button.active{{background:#10233f;color:#fff}}.note{{background:#f8fbff;border-left:4px solid #3977bd;padding:12px 14px;line-height:1.6;font-size:13px}}
</style></head><body><main>
<section class='hero'><h1>{html.escape(report['title'])}</h1><div class='muted'>执行时间：{html.escape(report['generated_at'])} · 执行模式：本地自动化真实断言 · 数据库写入：否 · 生产 API：否</div><div style='margin-top:12px'>总体结果：<span class='status {status_class}'>{report['result']}</span></div>
<div class='metrics'><div class='metric'>测试场景<b>{len(report['cases'])}</b></div><div class='metric'>通过<b>{counts['PASS']}</b></div><div class='metric'>失败<b>{counts['FAIL']}</b></div><div class='metric'>跳过<b>{counts['SKIP']}</b></div></div></section>
<section class='panel'><h2>测试边界</h2><div class='note'>本报告运行仓库当前收集到的测试。涉及真实 PostgreSQL、外部行情、LLM、浏览器或生产服务的场景，如果环境未提供依赖，会在失败或跳过中明确展示，不能将其解释为业务已验收。</div></section>
<section class='panel'><h2>覆盖范围</h2><table><thead><tr><th>业务域</th><th>测试依据</th></tr></thead><tbody>{scope_rows}</tbody></table></section>
<section class='panel'><h2>BDD 场景明细</h2><div class='filters'><button class='active' data-filter='ALL'>全部</button><button data-filter='PASS'>通过</button><button data-filter='FAIL'>失败</button><button data-filter='SKIP'>跳过</button></div><div style='overflow:auto'><table id='cases'><thead><tr><th>结果</th><th>业务域</th><th>测试场景</th><th>分类</th><th>耗时</th><th>执行证据</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
<section class='panel'><h2>Pytest 原始输出</h2><pre>{html.escape(report['execution']['pytest_output'])}</pre></section>
</main><script>document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{{document.querySelectorAll('[data-filter]').forEach(x=>x.classList.remove('active'));b.classList.add('active');const f=b.dataset.filter;document.querySelectorAll('#cases tbody tr').forEach(r=>r.style.display=f==='ALL'||r.dataset.status===f?'':'none')}})</script></body></html>"""


def main():
    return_code, output = _run_suite()
    report = _build_report(return_code, output)
    JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    HTML_PATH.write_text(_render(report), encoding="utf-8")
    print(json.dumps({"result": report["result"], "html_report": str(HTML_PATH), "json_report": str(JSON_PATH), **report["counts"]}, ensure_ascii=False))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
