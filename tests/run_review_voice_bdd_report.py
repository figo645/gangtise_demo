from __future__ import annotations

import html
import io
import json
import sys
import traceback
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_review_module_bdd import ReviewModuleBddTest


REPORT_DIR = PROJECT_ROOT / "tests" / "reports"
REPORT_HTML_PATH = REPORT_DIR / "review_voice_bdd_report.html"
REPORT_JSON_PATH = REPORT_DIR / "review_voice_bdd_report.json"

SCENARIOS = [
    {
        "method": "test_given_existing_llm_registry_when_normalized_then_builtin_gemma4_12b_model_is_appended",
        "name": "内置 12B 模型注册",
        "given": "系统存在自定义通用模型，且需要自动补齐内置 Gangtise 模型。",
        "when": "规范化 llm_registry。",
        "then": "Gemma4 12B BF16 必须作为内置模型追加进可用列表。",
    },
    {
        "method": "test_given_default_site_config_when_normalized_then_review_voice_enhancement_maps_to_gemma4_12b",
        "name": "语音增强默认映射 12B",
        "given": "系统使用默认站点配置。",
        "when": "解析 review_voice_enhancement 的功能级模型映射。",
        "then": "语音转录整理应默认绑定到 gemma4:12b-it-bf16。",
    },
    {
        "method": "test_given_review_voice_enhancement_when_running_then_gemma4_12b_model_is_used",
        "name": "语音增强执行使用 12B",
        "given": "用户启用语音增强整理，且配置中已存在默认映射。",
        "when": "执行 enhance_review_voice_transcript_with_llm。",
        "then": "实际送入 LLM 调用的模型配置必须是 gemma4:12b-it-bf16。",
    },
    {
        "method": "test_given_h5_when_review_file_or_url_is_processed_then_editor_handoff_logic_exists",
        "name": "H5 文件与 URL 自动回到手动撰写",
        "given": "H5 端复盘与知识录入完成文件解析或 URL 抽取。",
        "when": "前端渲染对应页面脚本。",
        "then": "抽取结果必须自动带入手动编辑区，并切到可继续修改的模式。",
    },
    {
        "method": "test_given_workbench_when_review_file_or_url_is_processed_then_editor_handoff_logic_exists",
        "name": "Workbench 文件与 URL 自动回到手动撰写",
        "given": "大V 工作台完成文件解析或 URL 抽取。",
        "when": "前端渲染工作台脚本。",
        "then": "抽取结果必须自动带入手动编辑区，并切到可继续修改的模式。",
    },
]


def render_json_preview(value: Any) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        text = repr(value)
    return html.escape(text[:12000])


def run_scenarios() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    suite_cls = ReviewModuleBddTest
    setup_ok = False
    try:
        suite_cls.setUpClass()
        setup_ok = True
        for scenario in SCENARIOS:
            method = scenario["method"]
            case = suite_cls(method)
            result = unittest.TestResult()
            log_buffer = io.StringIO()
            try:
                case.run(result)
                if result.failures or result.errors:
                    detail_parts = []
                    evidence = {"failures": [], "errors": []}
                    for test_case, failure in result.failures:
                        detail_parts.append(f"{test_case.id()}: assertion failed")
                        evidence["failures"].append(failure)
                    for test_case, error in result.errors:
                        detail_parts.append(f"{test_case.id()}: runtime error")
                        evidence["errors"].append(error)
                    results.append({
                        **scenario,
                        "passed": False,
                        "detail": "；".join(detail_parts) or "执行失败",
                        "evidence": evidence,
                    })
                else:
                    results.append({
                        **scenario,
                        "passed": True,
                        "detail": "场景断言通过。",
                        "evidence": {"result": "ok"},
                    })
            except Exception:
                results.append({
                    **scenario,
                    "passed": False,
                    "detail": "执行过程中发生未捕获异常。",
                    "evidence": {"traceback": traceback.format_exc(), "log": log_buffer.getvalue()},
                })
    finally:
        if setup_ok:
            try:
                suite_cls.tearDownClass()
            except Exception:
                results.append({
                    "method": "tearDownClass",
                    "name": "测试回收",
                    "given": "BDD 场景已全部执行。",
                    "when": "回收测试上下文。",
                    "then": "测试资源应被正常回收。",
                    "passed": False,
                    "detail": "tearDownClass 执行失败。",
                    "evidence": {"traceback": traceback.format_exc()},
                })
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scenario_count": len(results),
        "passed_count": sum(1 for item in results if item.get("passed")),
        "failed_count": sum(1 for item in results if not item.get("passed")),
        "scenarios": results,
    }


def render_html_report(report: dict[str, Any]) -> str:
    scenario_cards = "".join(
        f"""
        <article class="scenario {'pass' if item['passed'] else 'fail'}">
          <div class="scenario-head">
            <h3>{html.escape(item['name'])}</h3>
            <span class="pill">{'PASS' if item['passed'] else 'FAIL'}</span>
          </div>
          <div class="bdd-line"><strong>Given</strong> {html.escape(item['given'])}</div>
          <div class="bdd-line"><strong>When</strong> {html.escape(item['when'])}</div>
          <div class="bdd-line"><strong>Then</strong> {html.escape(item['then'])}</div>
          <p class="detail">{html.escape(item['detail'])}</p>
          <details>
            <summary>查看证据</summary>
            <pre>{render_json_preview(item['evidence'])}</pre>
          </details>
        </article>
        """
        for item in report["scenarios"]
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>语音转录 BDD 测试报告</title>
  <style>
    :root {{
      --bg: #f6f2ea;
      --panel: #fffdf8;
      --ink: #1d2a38;
      --muted: #66778a;
      --line: #dfd7ca;
      --green: #26734d;
      --red: #b14432;
      --blue: #2f74c0;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: linear-gradient(180deg, #f8f3ea 0%, #eef5fb 100%); color: var(--ink); font: 14px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px 20px 56px; }}
    .hero, .section {{ background: var(--panel); border: 1px solid var(--line); border-radius: 24px; box-shadow: 0 14px 48px rgba(22,34,48,0.08); }}
    .hero {{ padding: 24px 26px; }}
    .section {{ margin-top: 20px; padding: 20px; }}
    h1 {{ margin: 0 0 8px; font-size: 34px; line-height: 1.08; }}
    .sub {{ color: var(--muted); margin: 0; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; margin-top: 18px; }}
    .metric {{ background: #fff; border: 1px solid var(--line); border-radius: 18px; padding: 14px 16px; }}
    .metric .name {{ color: var(--muted); font-size: 12px; }}
    .metric .value {{ font-size: 28px; font-weight: 800; margin-top: 6px; }}
    .scenario-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
    .scenario {{ border: 1px solid var(--line); border-left: 5px solid var(--blue); border-radius: 18px; background: #fff; padding: 16px; }}
    .scenario.pass {{ border-left-color: var(--green); }}
    .scenario.fail {{ border-left-color: var(--red); }}
    .scenario-head {{ display: flex; justify-content: space-between; gap: 10px; align-items: start; }}
    .scenario-head h3 {{ margin: 0; font-size: 17px; }}
    .pill {{ display: inline-flex; align-items: center; justify-content: center; min-width: 58px; padding: 5px 10px; border-radius: 999px; background: rgba(47,116,192,0.10); color: var(--blue); font-size: 12px; font-weight: 700; }}
    .scenario.pass .pill {{ background: rgba(38,115,77,0.12); color: var(--green); }}
    .scenario.fail .pill {{ background: rgba(177,68,50,0.12); color: var(--red); }}
    .bdd-line {{ margin-top: 8px; }}
    .detail {{ margin: 10px 0 0; color: var(--muted); }}
    details {{ margin-top: 10px; }}
    summary {{ cursor: pointer; color: var(--blue); font-weight: 700; }}
    pre {{ margin: 10px 0 0; padding: 12px; border-radius: 12px; background: #13202d; color: #ecf3fb; overflow: auto; white-space: pre-wrap; word-break: break-word; }}
    @media (max-width: 900px) {{ .metrics, .scenario-grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>语音转录 BDD 测试报告</h1>
      <p class="sub">生成时间：{html.escape(report['generated_at'])} · 覆盖语音转录整理模型映射、执行路径，以及文件 / URL 进入手动撰写的关键交互。</p>
      <div class="metrics">
        <div class="metric"><div class="name">Scenario</div><div class="value">{report['scenario_count']}</div></div>
        <div class="metric"><div class="name">Pass</div><div class="value">{report['passed_count']}</div></div>
        <div class="metric"><div class="name">Fail</div><div class="value">{report['failed_count']}</div></div>
        <div class="metric"><div class="name">Target Model</div><div class="value" style="font-size:18px">gemma4:12b-it-bf16</div></div>
      </div>
    </section>
    <section class="section">
      <div class="scenario-grid">{scenario_cards}</div>
    </section>
  </main>
</body>
</html>
"""


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
