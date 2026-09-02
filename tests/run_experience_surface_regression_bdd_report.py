"""Run the cross-surface BDD suite and publish a static regression report."""

from __future__ import annotations

import html
import io
import json
import sys
import traceback
import unittest
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_experience_surface_regression_bdd import BDD_SCENARIOS, ExperienceSurfaceRegressionBddTest


REPORT_DIR = PROJECT_ROOT / "static" / "downloads"
REPORT_HTML_PATH = REPORT_DIR / "experience_surface_regression_bdd_report.html"
REPORT_JSON_PATH = REPORT_DIR / "experience_surface_regression_bdd_report.json"


def _method_name(scenario: dict[str, object]) -> str:
    return "test_bdd_" + str(scenario["id"]).replace("-", "_")


def _safe_json(value: Any) -> str:
    return html.escape(json.dumps(value, ensure_ascii=False, indent=2, default=str)[:12000])


def run_scenarios() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    setup_ok = False
    try:
        ExperienceSurfaceRegressionBddTest.setUpClass()
        setup_ok = True
        for scenario in BDD_SCENARIOS:
            method = _method_name(scenario)
            case = ExperienceSurfaceRegressionBddTest(method)
            result = unittest.TestResult()
            try:
                case.run(result)
                if result.failures or result.errors:
                    evidence = {
                        "required_contracts": list(scenario.get("required", ())),
                        "forbidden_contracts": list(scenario.get("forbidden", ())),
                        "failures": [detail for _, detail in result.failures],
                        "errors": [detail for _, detail in result.errors],
                    }
                    detail = "断言失败" if result.failures else "执行异常"
                    passed = False
                else:
                    evidence = {
                        "check": scenario.get("check"),
                        "required_contracts": list(scenario.get("required", ())),
                        "forbidden_contracts": list(scenario.get("forbidden", ())),
                    }
                    detail = "真实 Flask 页面/鉴权链路与客户端 API 契约断言通过。"
                    passed = True
                results.append({**scenario, "method": method, "passed": passed, "detail": detail, "evidence": evidence})
            except Exception:
                results.append({
                    **scenario,
                    "method": method,
                    "passed": False,
                    "detail": "测试运行器发生未捕获异常。",
                    "evidence": {"traceback": traceback.format_exc()},
                })
    finally:
        if setup_ok:
            try:
                ExperienceSurfaceRegressionBddTest.tearDownClass()
            except Exception:
                results.append({
                    "id": "test-cleanup",
                    "surface": "测试运行时",
                    "name": "测试上下文回收",
                    "given": "所有体验 BDD 场景已执行。",
                    "when": "恢复全局鉴权测试夹具。",
                    "then": "后续测试不能继承本套件的身份状态。",
                    "check": "cleanup",
                    "method": "tearDownClass",
                    "passed": False,
                    "detail": "测试上下文回收失败。",
                    "evidence": {"traceback": traceback.format_exc()},
                })

    surface_counts = Counter(str(item["surface"]) for item in results)
    passed_counts = Counter(str(item["surface"]) for item in results if item.get("passed"))
    return {
        "title": "H5 与大V工作台全量体验回归 BDD 报告",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "execution_mode": "Flask 测试客户端渲染真实路由、真实模板和实际鉴权钩子；不写入业务数据、不提交 LLM 生成任务。页面启动按当前运行环境执行既有的只读数据库和市场数据探测，数据不可用时验证其回退渲染路径。",
        "scope": "H5、H5 大V工作台、Web 大V工作台、跨端 API 同源性与权限边界。",
        "scenario_count": len(results),
        "passed_count": sum(1 for item in results if item.get("passed")),
        "failed_count": sum(1 for item in results if not item.get("passed")),
        "surface_summary": [
            {"surface": surface, "total": surface_counts[surface], "passed": passed_counts[surface], "failed": surface_counts[surface] - passed_counts[surface]}
            for surface in sorted(surface_counts)
        ],
        "scenarios": results,
    }


def render_html_report(report: dict[str, Any]) -> str:
    surface_summary = "".join(
        f"<tr><td>{html.escape(item['surface'])}</td><td>{item['total']}</td><td class='pass-text'>{item['passed']}</td><td class='{'fail-text' if item['failed'] else 'muted'}'>{item['failed']}</td></tr>"
        for item in report["surface_summary"]
    )
    rows = "".join(
        f"""
        <tr class=\"scenario-row {'pass' if item['passed'] else 'fail'}\" data-surface=\"{html.escape(item['surface'])}\" data-status=\"{'pass' if item['passed'] else 'fail'}\">
          <td class=\"status\"><span>{'PASS' if item['passed'] else 'FAIL'}</span></td>
          <td><div class=\"scenario-name\">{html.escape(item['name'])}</div><div class=\"scenario-id\">{html.escape(item['id'])}</div></td>
          <td>{html.escape(item['surface'])}</td>
          <td><b>Given</b> {html.escape(item['given'])}<br><b>When</b> {html.escape(item['when'])}<br><b>Then</b> {html.escape(item['then'])}</td>
          <td>{html.escape(item['detail'])}<details><summary>断言证据</summary><pre>{_safe_json(item['evidence'])}</pre></details></td>
        </tr>
        """
        for item in report["scenarios"]
    )
    filters = ["全部"] + [item["surface"] for item in report["surface_summary"]]
    filter_buttons = "".join(
        f"<button type=\"button\" class=\"filter{' active' if value == '全部' else ''}\" data-filter=\"{html.escape(value)}\">{html.escape(value)}</button>"
        for value in filters
    )
    result_status = "通过" if report["failed_count"] == 0 else "存在失败"
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
  <title>{html.escape(report['title'])}</title>
  <style>
    :root {{ --ink:#17324d; --muted:#66788a; --line:#dbe5ed; --panel:#ffffff; --bg:#f3f7fb; --blue:#206aaf; --green:#14724b; --red:#b42318; --gold:#a56a00; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:var(--bg); color:var(--ink); font:14px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; }}
    main {{ width:min(1440px,100%); margin:0 auto; padding:28px 20px 56px; }} .top {{ border-bottom:3px solid var(--blue); padding:0 0 20px; }}
    h1 {{ margin:0; font-size:28px; line-height:1.25; }} .sub {{ margin:8px 0 0; color:var(--muted); }} .notice {{ margin-top:14px; padding:10px 12px; border-left:3px solid var(--gold); background:#fff8e9; color:#705012; font-size:13px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin-top:20px; }} .metric {{ border:1px solid var(--line); background:var(--panel); padding:14px; min-height:88px; }} .metric-label {{ color:var(--muted); font-size:12px; }} .metric-value {{ margin-top:5px; font-size:28px; font-weight:800; }} .metric-value.pass {{ color:var(--green); }} .metric-value.fail {{ color:var(--red); }}
    section {{ margin-top:24px; }} h2 {{ margin:0 0 10px; font-size:18px; }} .summary-table,.scenario-table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); }} th,td {{ padding:11px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }} th {{ background:#eef5fb; color:#456078; font-size:12px; white-space:nowrap; }} .pass-text {{ color:var(--green); font-weight:700; }} .fail-text {{ color:var(--red); font-weight:700; }} .muted {{ color:var(--muted); }}
    .filters {{ display:flex; gap:8px; flex-wrap:wrap; margin:0 0 10px; }} .filter {{ border:1px solid #b9ccdd; background:#fff; color:#315978; padding:7px 10px; border-radius:6px; cursor:pointer; font-size:12px; }} .filter.active {{ border-color:var(--blue); background:var(--blue); color:#fff; }} .table-wrap {{ overflow:auto; border:1px solid var(--line); }} .scenario-table {{ min-width:1080px; border:0; }} .scenario-row.pass .status span,.scenario-row.fail .status span {{ display:inline-block; min-width:48px; padding:3px 7px; border-radius:4px; font-size:11px; font-weight:800; text-align:center; }} .scenario-row.pass .status span {{ background:#e7f5ed; color:var(--green); }} .scenario-row.fail .status span {{ background:#fbe9e7; color:var(--red); }} .scenario-name {{ font-weight:800; }} .scenario-id {{ color:var(--muted); font:11px ui-monospace,SFMono-Regular,Menlo,monospace; margin-top:3px; }} details {{ margin-top:8px; }} summary {{ cursor:pointer; color:var(--blue); font-size:12px; font-weight:700; }} pre {{ max-width:520px; margin:8px 0 0; padding:10px; overflow:auto; background:#122334; color:#edf5fb; font:11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; white-space:pre-wrap; word-break:break-word; }}
    .empty {{ display:none; margin-top:12px; color:var(--muted); }} @media(max-width:760px) {{ main {{ padding:20px 12px 40px; }} h1 {{ font-size:23px; }} .metrics {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
  </style>
</head>
<body>
  <main>
    <header class=\"top\">
      <h1>{html.escape(report['title'])}</h1>
      <p class=\"sub\">执行时间：{html.escape(report['generated_at'])} · 结果：<strong class=\"{'pass-text' if report['failed_count'] == 0 else 'fail-text'}\">{result_status}</strong></p>
      <div class=\"notice\">{html.escape(report['execution_mode'])}</div>
    </header>
    <div class=\"metrics\">
      <div class=\"metric\"><div class=\"metric-label\">BDD 场景</div><div class=\"metric-value\">{report['scenario_count']}</div></div>
      <div class=\"metric\"><div class=\"metric-label\">通过</div><div class=\"metric-value pass\">{report['passed_count']}</div></div>
      <div class=\"metric\"><div class=\"metric-label\">失败</div><div class=\"metric-value {'fail' if report['failed_count'] else 'pass'}\">{report['failed_count']}</div></div>
      <div class=\"metric\"><div class=\"metric-label\">覆盖范围</div><div class=\"metric-value\" style=\"font-size:17px\">三端 + 同源 + 权限</div></div>
    </div>
    <section><h2>覆盖汇总</h2><table class=\"summary-table\"><thead><tr><th>端</th><th>场景</th><th>通过</th><th>失败</th></tr></thead><tbody>{surface_summary}</tbody></table></section>
    <section><h2>BDD 场景</h2><div class=\"filters\">{filter_buttons}<button type=\"button\" class=\"filter\" data-filter=\"失败\">仅失败</button></div><div class=\"table-wrap\"><table class=\"scenario-table\"><thead><tr><th>结果</th><th>场景</th><th>端</th><th>行为</th><th>执行证据</th></tr></thead><tbody id=\"scenario-body\">{rows}</tbody></table></div><p id=\"empty\" class=\"empty\">当前筛选条件下没有场景。</p></section>
  </main>
  <script>
    const buttons = Array.from(document.querySelectorAll('.filter')); const rows = Array.from(document.querySelectorAll('.scenario-row')); const empty = document.getElementById('empty');
    buttons.forEach((button) => button.addEventListener('click', () => {{ const filter = button.dataset.filter; buttons.forEach((item) => item.classList.toggle('active', item === button)); let count = 0; rows.forEach((row) => {{ const visible = filter === '全部' || (filter === '失败' ? row.dataset.status === 'fail' : row.dataset.surface === filter); row.style.display = visible ? '' : 'none'; if (visible) count += 1; }}); empty.style.display = count ? 'none' : 'block'; }}));
  </script>
</body>
</html>"""


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = run_scenarios()
    REPORT_JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_HTML_PATH.write_text(render_html_report(report), encoding="utf-8")
    print(json.dumps({
        "ok": report["failed_count"] == 0,
        "html_report": str(REPORT_HTML_PATH),
        "json_report": str(REPORT_JSON_PATH),
        "passed": report["passed_count"],
        "failed": report["failed_count"],
    }, ensure_ascii=False))
    return 0 if report["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
