"""Run the six Hermes scenarios against the real configured services.

This is intentionally not a unit test and does not mock any provider. It
reads the live PostgreSQL configuration, calls the configured LLM and, where
specified, calls Gangtise. Each run can consume provider credits.
"""

import html
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.domain.ai_services import build_hermes_query_response, get_hermes_llm_config
from src.runtime import app


OUTPUT = ROOT / "static" / "downloads" / "hermes_six_scenarios_real_bdd_report.html"


SCENARIOS = [
    {
        "id": "A",
        "title": "个股咨询分析",
        "question": "对今天中国银行的股票做下个股分析，看看今天整体情况怎么样",
        "expected_intent": "stock_today_observation",
        "expected_tool": "gangtise.stock_today_observation",
        "expected_provider": "Gangtise Agent助手 SSE",
        "expected_cost": 20,
        "expected_contract": "今日行情、核心逻辑、重要要闻和风险；单只股票；Gangtise 结果直接展示。",
    },
    {
        "id": "B",
        "title": "大盘综合分析",
        "question": "分析下今天大盘的整体走势，上证和深证指数表现如何",
        "expected_intent": "market_today_observation",
        "expected_tool": "gangtise.market_today_observation",
        "expected_provider": "Gangtise Agent助手 SSE",
        "expected_cost": 40,
        "expected_contract": "同时涉及上证和深证时，拆成两次单指数 Gangtise 调用；返回指数表现、板块资金和市场情绪展望后原样合并展示。",
    },
    {
        "id": "C",
        "title": "个股结构化分析报告",
        "question": "对中国银行做一下深入研究",
        "expected_intent": "stock_one_pager",
        "expected_tool": "gangtise.stock_one_pager",
        "expected_provider": "Gangtise OpenAPI",
        "expected_cost": 50,
        "expected_contract": "最近一期结构化报告，非当日研究；仅支持个股；Gangtise 结果直接展示。",
    },
    {
        "id": "D",
        "title": "个股看点摘要",
        "question": "我这里有3支股票，中国银行，建设银行，招商银行，帮我简单介绍分析下。",
        "expected_intent": "stock_highlights",
        "expected_tool": "gangtise.stock_highlights",
        "expected_provider": "Gangtise OpenAPI",
        "expected_cost": 9,
        "expected_contract": "三只股票的精炼看点；不生成组合结论；每条按 3 积分计。",
    },
    {
        "id": "E",
        "title": "多支自选股综合分析",
        "question": "我这里有3支股票，中国银行，建设银行，招商银行。我需要对于这三支股票做一下详细的综合分析。",
        "expected_intent": "multi_watchlist_analysis",
        "expected_tool": "gangtise.multi_watchlist_analysis",
        "expected_provider": "Gangtise Agent助手 SSE",
        "expected_cost": 20,
        "expected_contract": "至少两只股票；个股分析加组合综合结论；Gangtise 结果直接展示。",
    },
    {
        "id": "F",
        "title": "多轮闲聊能力",
        "question": "你好呀？",
        "expected_intent": "small_talk",
        "expected_tool": None,
        "expected_provider": "配置的通用 LLM",
        "expected_cost": 0,
        "expected_contract": "由配置的通用 LLM 回答；不调用 Gangtise，不调用 embedding。",
    },
]


def run_scenario(scenario):
    question = scenario["question"]
    payload = {
        "tenant_slug": os.environ.get("HERMES_LIVE_TENANT", "laowang"),
        "user_role": "dav",
        "user_profile_id": os.environ.get("HERMES_LIVE_USER", "财经老王"),
        "user_name": os.environ.get("HERMES_LIVE_USER", "财经老王"),
        "entry_point": "hermes_six_scenarios_real_bdd",
        "question": question,
        "messages": [{"role": "user", "content": question}],
        "attachments": [],
        "selected_knowledge_ids": [],
        "preferred_mode": "basic",
        "web_answer": False,
    }
    started = time.perf_counter()
    llm_config = {}
    try:
        with app.test_request_context("/api/hermes/query", method="POST", json=payload):
            configured_model = get_hermes_llm_config("hermes_intent_router") or {}
            llm_config = {
                "key": configured_model.get("key"),
                "label": configured_model.get("label"),
                "provider": configured_model.get("provider"),
                "model_name": configured_model.get("model_name"),
                "base_url": configured_model.get("base_url"),
            }
            result = build_hermes_query_response(payload)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        traces = result.get("tool_trace") if isinstance(result.get("tool_trace"), list) else []
        actual_tools = [str(item.get("tool") or "") for item in traces if isinstance(item, dict)]
        actual_intent = result.get("intent")
        answer = str(result.get("answer") or "")
        checks = {
            "intent": actual_intent == scenario["expected_intent"],
            "tool": (scenario["expected_tool"] in actual_tools) if scenario["expected_tool"] else not actual_tools,
            "answer": bool(answer.strip()),
            "provider_mode": (
                result.get("answer_engine", {}).get("mode") == "gangtise_direct"
                if scenario["expected_tool"]
                else result.get("answer_engine", {}).get("mode") == "llm_synthesized"
            ),
        }
        return {
            "scenario": scenario,
            "status": "passed" if all(checks.values()) else "failed",
            "elapsed_ms": elapsed_ms,
            "checks": checks,
            "llm_config": llm_config,
            "result": {
                "intent": actual_intent,
                "answer_engine": result.get("answer_engine"),
                "router": result.get("router"),
                "tool_trace": traces,
                "tool_outputs": result.get("tool_outputs"),
                "securities": result.get("securities"),
                "answer": answer,
                "summary": result.get("summary"),
                "citations": result.get("citations"),
            },
        }
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "scenario": scenario,
            "status": "failed",
            "elapsed_ms": elapsed_ms,
            "checks": {"intent": False, "tool": False, "answer": False, "provider_mode": False},
            "llm_config": llm_config,
            "error": f"{type(exc).__name__}: {exc}",
        }


def render_check(value):
    return '<span class="pass">PASS</span>' if value else '<span class="fail">FAIL</span>'


def render_scenario(item):
    scenario = item["scenario"]
    result = item.get("result") or {}
    checks = item.get("checks") or {}
    answer = result.get("answer") or item.get("error") or "无返回内容"
    upstream_calls = []
    for output in (result.get("tool_outputs") or {}).values():
        if not isinstance(output, dict):
            continue
        if isinstance(output.get("requests"), list):
            upstream_calls.extend(output.get("requests") or [])
        elif output.get("request_text"):
            upstream_calls.append({
                "request_text": output.get("request_text"),
                "duration_ms": output.get("duration_ms"),
                "endpoint": output.get("endpoint"),
                "provider": output.get("provider"),
            })
    return f"""
    <article class="scenario {item['status']}">
      <header>
        <div><span class="scenario-id">{html.escape(scenario['id'])}</span><h2>{html.escape(scenario['title'])}</h2></div>
        <strong class="status">{html.escape(item['status'].upper())}</strong>
      </header>
      <div class="question"><b>问题</b><br>{html.escape(scenario['question'])}</div>
      <div class="contract"><b>预期契约</b> {html.escape(scenario['expected_contract'])}</div>
      <div class="meta">
        <span>预期意图：<code>{html.escape(scenario['expected_intent'])}</code></span>
        <span>实际意图：<code>{html.escape(str(result.get('intent') or '--'))}</code></span>
        <span>预期工具：<code>{html.escape(str(scenario['expected_tool'] or '无'))}</code></span>
        <span>耗时：<code>{item['elapsed_ms']} ms</code></span>
        <span>预估积分：<code>{scenario['expected_cost']}</code></span>
      </div>
      <div class="checks">
        <span>意图 {render_check(checks.get('intent'))}</span>
        <span>工具 {render_check(checks.get('tool'))}</span>
        <span>非空回答 {render_check(checks.get('answer'))}</span>
        <span>执行模式 {render_check(checks.get('provider_mode'))}</span>
      </div>
      <details open><summary>实际回答 / 错误</summary><pre class="answer">{html.escape(answer)}</pre></details>
      <details><summary>实际上游请求与耗时</summary><pre>{html.escape(json.dumps(upstream_calls, ensure_ascii=False, indent=2))}</pre></details>
      <details><summary>LLM 配置、路由和工具轨迹</summary><pre>{html.escape(json.dumps({'llm_config': item.get('llm_config'), 'router': result.get('router'), 'answer_engine': result.get('answer_engine'), 'tool_trace': result.get('tool_trace'), 'securities': result.get('securities')}, ensure_ascii=False, indent=2))}</pre></details>
    </article>
    """


def main():
    started = datetime.now().astimezone()
    results = []
    for scenario in SCENARIOS:
        print(f"[{scenario['id']}/{len(SCENARIOS)}] {scenario['title']} ...", flush=True)
        item = run_scenario(scenario)
        results.append(item)
        print(f"    {item['status']} ({item['elapsed_ms']} ms)", flush=True)

    passed = sum(item["status"] == "passed" for item in results)
    cost = sum(int(item["scenario"].get("expected_cost") or 0) for item in results if item["status"] != "failed")
    report = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hermes 六场景真实 BDD 报告</title>
<style>
body{{margin:0;background:#f4f1eb;color:#252525;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.65}}
main{{max-width:1180px;margin:0 auto;padding:36px 20px 60px}} h1{{margin:0 0 8px;font-size:30px}} h2{{display:inline;margin:0 0 0 12px;font-size:20px}}
.subtitle{{color:#706b63;margin-bottom:24px}} .summary{{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0 28px}}
.pill{{background:#fff;border:1px solid #ddd5c9;border-radius:999px;padding:6px 14px}} .pass{{color:#16734a;font-weight:700}} .fail{{color:#b42318;font-weight:700}}
.scenario{{background:#fff;border:1px solid #ddd5c9;border-left:5px solid #16734a;border-radius:14px;padding:20px;margin:18px 0;box-shadow:0 4px 15px #5c493014}}
.scenario.failed{{border-left-color:#b42318}} header{{display:flex;justify-content:space-between;align-items:center;gap:12px}} .scenario-id{{color:#9a6d1f;font-weight:800}} .status{{font-size:13px;color:#16734a}} .failed .status{{color:#b42318}}
.question,.contract{{background:#faf8f4;border-radius:9px;padding:12px 14px;margin-top:14px}} .contract{{color:#5c554b}} .meta,.checks{{display:flex;gap:16px;flex-wrap:wrap;margin:14px 0;font-size:13px}} code{{background:#f0ece6;border-radius:4px;padding:2px 5px}}
.checks{{border-top:1px solid #eee7dd;border-bottom:1px solid #eee7dd;padding:11px 0}} details{{margin-top:12px}} summary{{cursor:pointer;font-weight:700}} pre{{white-space:pre-wrap;overflow:auto;background:#17191d;color:#e9edf0;padding:14px;border-radius:9px;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace}} .answer{{max-height:700px}}
.foot{{color:#706b63;font-size:13px;margin-top:28px}}
</style></head><body><main>
<h1>Hermes 六场景真实 BDD 报告</h1>
<div class="subtitle">真实执行时间：{html.escape(started.strftime('%Y-%m-%d %H:%M:%S %Z'))} · 不使用 mock · 读取实际 PostgreSQL、通用 LLM 和 Gangtise 配置</div>
<div class="summary"><span class="pill">通过 <b class="pass">{passed}/6</b></span><span class="pill">预估成功调用积分 <b>{cost}</b></span><span class="pill">测试账号 <b>{html.escape(os.environ.get('HERMES_LIVE_USER', '财经老王'))}</b></span></div>
{''.join(render_scenario(item) for item in results)}
<div class="foot">说明：本报告记录的是实际调用结果。Gangtise 返回内容按当前契约直接展示，不经过本地 LLM 二次改写；闲聊场景只使用配置的通用 LLM。报告生成器：scripts/run_real_hermes_six_scenarios.py</div>
</main></body></html>"""
    OUTPUT.write_text(report, encoding="utf-8")
    print(f"REPORT={OUTPUT}", flush=True)
    print(f"SUMMARY={passed}/6 passed; estimated successful cost={cost}", flush=True)


if __name__ == "__main__":
    main()
