from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app as app_entry
import src.web.hooks as web_hooks
from src.domain import ai_services
from src.services import get_tenant_configs


REPORT_DIR = PROJECT_ROOT / "tests" / "reports"
REPORT_HTML_PATH = REPORT_DIR / "hermes_bdd_report.html"
REPORT_JSON_PATH = REPORT_DIR / "hermes_bdd_report.json"


def pick_tenant_slug() -> str:
    try:
        tenants = get_tenant_configs()
    except Exception:
        return "laowang"
    for item in tenants:
        slug = str(item.get("slug") or "").strip()
        if slug:
            return slug
    return "laowang"


def scenario_result(name: str, given: str, when: str, then: str, passed: bool, detail: str, evidence: Any) -> dict[str, Any]:
    return {
        "name": name,
        "given": given,
        "when": when,
        "then": then,
        "passed": bool(passed),
        "detail": str(detail or "").strip(),
        "evidence": evidence,
    }


def render_json_preview(value: Any) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        text = repr(value)
    return escape(text[:16000])


def first_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
    return artifacts[0] if artifacts and isinstance(artifacts[0], dict) else {}


def call_hermes(client, tenant_slug: str, question: str, **extra: Any) -> dict[str, Any]:
    body = {
        "tenant_slug": tenant_slug,
        "user_role": "dav",
        "user_profile_id": "bdd-hermes-dav",
        "user_name": "BDD Hermes 大V",
        "entry_point": "hermes_chat",
        "session_id": "bdd-hermes-session",
        "question": question,
        "messages": [{"role": "user", "content": question}],
        "preferred_mode": extra.pop("preferred_mode", "basic"),
        "web_answer": False,
    }
    body.update(extra)
    response = client.post("/api/hermes/query", json=body)
    payload = response.get_json(silent=True) or {}
    payload["_http_status"] = response.status_code
    return payload


def run_api_scenario(
    client,
    tenant_slug: str,
    question: str,
    name: str,
    given: str,
    when: str,
    then: str,
    validator,
    **extra: Any,
) -> dict[str, Any]:
    payload = call_hermes(client, tenant_slug, question, **extra)
    try:
        passed, detail = validator(payload)
    except Exception as exc:
        passed = False
        detail = f"validator_error:{exc}"
    artifact = first_artifact(payload)
    evidence = {
        "question": question,
        "http_status": payload.get("_http_status"),
        "ok": payload.get("ok"),
        "intent": payload.get("intent"),
        "task_family": payload.get("task_family"),
        "capability_label": payload.get("capability_label"),
        "display_mode": payload.get("display_mode"),
        "preferred_mode": payload.get("preferred_mode"),
        "router": payload.get("router"),
        "tool_trace": payload.get("tool_trace"),
        "artifact": {
            "type": artifact.get("type"),
            "title": artifact.get("title"),
            "headline": artifact.get("headline"),
            "summary": artifact.get("summary"),
            "body": artifact.get("body"),
            "symbol": artifact.get("symbol"),
            "chart": artifact.get("chart"),
            "chart_html_present": bool(artifact.get("chart_html") or artifact.get("chartHtml")),
        },
        "settings_snapshot": payload.get("settings_snapshot"),
    }
    return scenario_result(name, given, when, then, passed, detail, evidence)


def render_html_report(report: dict[str, Any]) -> str:
    scenarios = report["scenarios"]
    passed = sum(1 for item in scenarios if item["passed"])
    failed = len(scenarios) - passed
    scenario_cards = "".join(
        f"""
        <article class="scenario {'pass' if item['passed'] else 'fail'}">
          <div class="scenario-head">
            <h3>{escape(item['name'])}</h3>
            <span class="pill">{'PASS' if item['passed'] else 'FAIL'}</span>
          </div>
          <div class="bdd-line"><strong>Given</strong> {escape(item['given'])}</div>
          <div class="bdd-line"><strong>When</strong> {escape(item['when'])}</div>
          <div class="bdd-line"><strong>Then</strong> {escape(item['then'])}</div>
          <p class="detail">{escape(item['detail'])}</p>
          <details>
            <summary>查看证据</summary>
            <pre>{render_json_preview(item['evidence'])}</pre>
          </details>
        </article>
        """
        for item in scenarios
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Hermes BDD 测试报告</title>
  <style>
    :root {{
      --bg: #f6f2ea;
      --panel: #fffdf8;
      --ink: #1d2a38;
      --muted: #66778a;
      --line: #dfd7ca;
      --gold: #b5833a;
      --green: #26734d;
      --red: #b14432;
      --blue: #2f74c0;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: linear-gradient(180deg, #f8f3ea 0%, #eef5fb 100%); color: var(--ink); font: 14px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 28px 20px 56px; }}
    .hero {{ background: var(--panel); border: 1px solid var(--line); border-radius: 24px; padding: 24px 26px; box-shadow: 0 14px 48px rgba(22,34,48,0.08); }}
    h1 {{ margin: 0 0 8px; font-size: 34px; line-height: 1.08; }}
    .sub {{ color: var(--muted); margin: 0; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; margin-top: 18px; }}
    .metric {{ background: #fff; border: 1px solid var(--line); border-radius: 18px; padding: 14px 16px; }}
    .metric .name {{ color: var(--muted); font-size: 12px; }}
    .metric .value {{ font-size: 28px; font-weight: 800; margin-top: 6px; }}
    .section {{ margin-top: 20px; background: var(--panel); border: 1px solid var(--line); border-radius: 24px; padding: 20px; box-shadow: 0 10px 36px rgba(22,34,48,0.06); }}
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
      <h1>Hermes BDD 测试报告</h1>
      <p class="sub">生成时间：{escape(report['generated_at'])} · 租户：{escape(report['tenant_slug'])} · 覆盖路由、工具、结构化 artifact、图表数据与前台渲染入口</p>
      <div class="metrics">
        <div class="metric"><div class="name">Scenario</div><div class="value">{len(scenarios)}</div></div>
        <div class="metric"><div class="name">Pass</div><div class="value">{passed}</div></div>
        <div class="metric"><div class="name">Fail</div><div class="value">{failed}</div></div>
        <div class="metric"><div class="name">LLM</div><div class="value">Fallback</div></div>
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
    original_is_authenticated = web_hooks.is_authenticated
    web_hooks.is_authenticated = lambda: True
    tenant_slug = pick_tenant_slug()
    report: dict[str, Any] = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tenant_slug": tenant_slug,
        "scenarios": [],
        "exception": "",
    }
    try:
        app_entry.app.config.update(TESTING=True)
        client = app_entry.app.test_client()
        with app_entry.app.app_context(), patch("src.domain.ai_services.get_default_llm_config", return_value=None):
            report["scenarios"].append(
                run_api_scenario(
                    client,
                    tenant_slug,
                    "我想看看中国银行这支股票的K线图以及分析",
                    name="个股 K 线 + 分析",
                    given="用户明确输入中国银行这只股票，并要求看 K 线图和分析。",
                    when="调用 /api/hermes/query，且 LLM 不可用时走规则降级链路。",
                    then="Hermes 必须返回自选股结构化 artifact，包含 K 线图数据和可读分析正文。",
                    validator=lambda payload: (
                        payload.get("ok") is True
                        and payload.get("intent") == "watchlist_fundamental"
                        and payload.get("display_mode") == "structured"
                        and first_artifact(payload).get("type") == "watchlist_analysis"
                        and ((first_artifact(payload).get("symbol") or {}).get("code") == "601988")
                        and ((first_artifact(payload).get("chart") or {}).get("kind") == "kline")
                        and len((first_artifact(payload).get("chart") or {}).get("points") or []) > 0
                        and "中国银行" in str(first_artifact(payload).get("body") or "")
                        and not str(first_artifact(payload).get("body") or "").startswith("分析方式偏向"),
                        "已返回中国银行自选股 K 线 artifact，并生成正文分析。"
                    ),
                )
            )
            report["scenarios"].append(
                run_api_scenario(
                    client,
                    tenant_slug,
                    "给我展示下到现在为止3个月的上证综合指数的K线图并做一下解读分析",
                    name="指数 K 线 + 解读",
                    given="用户明确要求查看上证综合指数最近 3 个月 K 线图并解读。",
                    when="调用 Hermes 查询接口。",
                    then="Hermes 必须返回指标结构化 artifact，图表类型为 kline，并带有解读正文。",
                    validator=lambda payload: (
                        payload.get("ok") is True
                        and payload.get("intent") == "smart_indicator_explain"
                        and payload.get("display_mode") == "structured"
                        and first_artifact(payload).get("type") == "indicator_analysis"
                        and ((first_artifact(payload).get("chart") or {}).get("kind") == "kline")
                        and len(((first_artifact(payload).get("chart") or {}).get("kline") or {}).get("candles") or []) > 0
                        and "上证" in str(first_artifact(payload).get("body") or first_artifact(payload).get("summary") or ""),
                        "已返回上证指数 K 线指标 artifact，并包含指标解读。"
                    ),
                )
            )
            report["scenarios"].append(
                run_api_scenario(
                    client,
                    tenant_slug,
                    "请展示最近3个月的上证指数的历史数据线图（单纯的线性趋势图）",
                    name="指数线性趋势图",
                    given="用户明确要求线图，不要 K 线。",
                    when="调用 Hermes 查询接口。",
                    then="Hermes 必须把图表类型解析为 trend/line，而不是 kline。",
                    validator=lambda payload: (
                        payload.get("ok") is True
                        and first_artifact(payload).get("type") == "indicator_analysis"
                        and ((first_artifact(payload).get("chart") or {}).get("kind") == "trend")
                        and len((first_artifact(payload).get("chart") or {}).get("series") or []) > 0,
                        "线图需求已解析为 trend，未误用 K 线图。"
                    ),
                )
            )
            report["scenarios"].append(
                run_api_scenario(
                    client,
                    tenant_slug,
                    "知识库里关于固态电池的研究框架是什么？",
                    name="知识库问答",
                    given="用户围绕租户知识库提问。",
                    when="调用 Hermes 查询接口。",
                    then="Hermes 必须先执行 knowledge.search，并以文字回答承接。",
                    validator=lambda payload: (
                        payload.get("ok") is True
                        and payload.get("intent") == "knowledge_lookup"
                        and any((item or {}).get("tool") == "knowledge.search" for item in (payload.get("tool_trace") or []))
                        and first_artifact(payload).get("type") == "text_response",
                        "知识库问答已进入 knowledge_lookup，并先查知识库。"
                    ),
                )
            )
            report["scenarios"].append(
                run_api_scenario(
                    client,
                    tenant_slug,
                    "帮我解读一下刚上传的研报，提炼三条核心观点",
                    name="报告解读",
                    given="用户上传文件后要求 Hermes 解读报告。",
                    when="带附件调用 Hermes 查询接口。",
                    then="Hermes 必须执行 attachment.context，并按报告解读/知识问答链路输出。",
                    attachments=[{"filename": "demo_report.txt", "summary": "银行板块研报", "body": "银行板块需要关注净息差、资产质量和股息稳定性。"}],
                    validator=lambda payload: (
                        payload.get("ok") is True
                        and any((item or {}).get("tool") == "attachment.context" for item in (payload.get("tool_trace") or []))
                        and first_artifact(payload).get("type") == "text_response",
                        "附件已进入 attachment.context，报告解读链路可用。"
                    ),
                )
            )
            report["scenarios"].append(
                run_api_scenario(
                    client,
                    tenant_slug,
                    "H5 里的智能指标怎么创建和发布？",
                    name="产品帮助",
                    given="用户询问平台功能使用。",
                    when="调用 Hermes 查询接口。",
                    then="Hermes 必须进入 product_help，而不是错误调用图表能力。",
                    validator=lambda payload: (
                        payload.get("ok") is True
                        and payload.get("intent") == "product_help"
                        and first_artifact(payload).get("type") == "text_response",
                        "产品帮助场景路由正确。"
                    ),
                )
            )
            scope = ai_services.hermes_scope_guard("今天天气什么时候来上海？", tenant_slug=tenant_slug)
            plan, _, route_mode = ai_services.route_hermes_query_intent(
                "今天天气什么时候来上海？",
                tenant_slug=tenant_slug,
                scope_result=scope,
                scope_guard_enabled=True,
            )
            report["scenarios"].append(
                scenario_result(
                    name="范围守卫收口",
                    given="固定范围约束开启时，用户提出明显非平台研究问题。",
                    when="直接执行 scope_guard 与规则路由。",
                    then="Hermes 应温和收口到平台能力，不调度工具。",
                    passed=scope.get("status") == "redirected" and plan.get("intent") == "out_of_scope_redirect" and route_mode == "scope_guard",
                    detail="范围守卫可按配置生效；如果后台关闭约束，API 层可继续开放承接。",
                    evidence={"scope": scope, "plan": plan, "route_mode": route_mode},
                )
            )
            page_response = client.get(f"/h5?tenant={tenant_slug}")
            h5_html = page_response.get_data(as_text=True)
            frontend_ready = (
                page_response.status_code == 200
                and "function buildHermesWatchlistKlineSvg" in h5_html
                and "function buildHermesIndicatorKlineSvg" in h5_html
                and "window.GangtiseEcharts.render" in h5_html
                and "normalizeHermesArtifact" in h5_html
            )
            report["scenarios"].append(
                scenario_result(
                    name="前台图表渲染入口",
                    given="后端已经返回 watchlist/indicator chart payload。",
                    when="渲染 H5 Hermes 页面源码。",
                    then="前端必须具备 ECharts K线/线图渲染与 artifact normalize 入口。",
                    passed=frontend_ready,
                    detail="H5 页面具备 Hermes 图表 normalize 与 ECharts 渲染函数。",
                    evidence={
                        "status_code": page_response.status_code,
                        "has_watchlist_kline_renderer": "function buildHermesWatchlistKlineSvg" in h5_html,
                        "has_indicator_kline_renderer": "function buildHermesIndicatorKlineSvg" in h5_html,
                        "has_echarts_render": "window.GangtiseEcharts.render" in h5_html,
                        "has_artifact_normalizer": "normalizeHermesArtifact" in h5_html,
                    },
                )
            )
    except Exception as exc:
        report["exception"] = f"{exc}\n{traceback.format_exc()}"
        report["scenarios"].append(
            scenario_result(
                name="报告执行完整性",
                given="BDD 报告脚本需要完整执行 Hermes 核心场景。",
                when="运行整个报告流程。",
                then="脚本不应抛出未处理异常。",
                passed=False,
                detail=str(exc),
                evidence={"traceback": traceback.format_exc()},
            )
        )
    finally:
        web_hooks.is_authenticated = original_is_authenticated

    REPORT_JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_HTML_PATH.write_text(render_html_report(report), encoding="utf-8")
    print(json.dumps({
        "html_report": str(REPORT_HTML_PATH),
        "json_report": str(REPORT_JSON_PATH),
        "scenario_count": len(report["scenarios"]),
        "passed": sum(1 for item in report["scenarios"] if item["passed"]),
        "failed": sum(1 for item in report["scenarios"] if not item["passed"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
