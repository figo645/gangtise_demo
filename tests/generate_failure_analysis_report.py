from __future__ import annotations

import datetime as dt
import html
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/reports/full_system_bdd_report.json"
OUTPUT = ROOT / "tests/reports/full_system_bdd_failure_analysis.html"


def classify(case):
    text = f"{case.get('name', '')} {case.get('detail', '')}".lower()
    if "working outside of application context" in text:
        return "测试上下文缺失", "补齐 app.app_context() 或改用 Flask test client", "P1"
    if any(x in text for x in ("not found in '<!doctype html", "not found in '<html", "not found in \"<!doctype html")):
        return "页面 HTML/JS 契约不一致", "判断是模板已升级还是用户体验功能回归，再同步测试断言", "P2"
    if any(x in text for x in ("403 !=", "404 !=", "503 !=", "401 !=", "status code")):
        return "HTTP/会话/接口契约不一致", "核对登录会话、权限边界与当前路由契约", "P1"
    if "llm_feature_model_binding_missing" in text or "llm_api_key_missing" in text or "llm_not_configured" in text:
        return "LLM 配置或严格绑定缺失", "仅检查数据库中的 feature binding 与加密凭证，不使用环境变量回退", "P1"
    if "review_watchlist_analysis_disabled" in text or ("review_watchlist" in text and "gangtise" in text and "sse" in text):
        return "复盘/Gangtise 流程状态不一致", "确认旧自选股 SSE 流程是否仍是当前产品能力", "P1"
    if any(x in text for x in ("html", "not found in", "assert '")):
        return "页面 HTML/JS 契约不一致", "判断是模板已升级还是用户体验功能回归，再同步测试断言", "P2"
    if any(x in text for x in ("akshare", "snapshot", "market_", "index_", "intraday", "sector", "gangtise openapi")):
        return "行情数据源/快照契约不一致", "统一当前数据源、快照字段和交易日语义，再更新实现或测试", "P1"
    if any(x in text for x in ("indexerror", "keyerror", "list index", "empty", "tuple", "length")):
        return "数据夹具或返回结构不一致", "补齐空态与真实返回结构的测试数据", "P2"
    if "called" in text or "unexpectedly" in text or "!=" in text:
        return "行为断言不一致", "逐条确认当前业务规则，避免为通过测试而放宽逻辑", "P2"
    return "其他待分流", "结合原始断言确认实现问题或测试过期", "P3"


def compact_detail(value, limit=1800):
    text = str(value or "")
    if len(text) <= limit:
        return text
    head = int(limit * 0.72)
    tail = limit - head
    return text[:head] + "\n... [中间的大段 HTML/响应体已省略] ...\n" + text[-tail:]


def main():
    report = json.loads(SOURCE.read_text(encoding="utf-8"))
    failures = []
    for case in report["cases"]:
        if case["status"] != "FAIL":
            continue
        category, action, priority = classify(case)
        item = dict(case)
        item.update(category=category, action=action, priority=priority)
        failures.append(item)

    by_category = Counter(item["category"] for item in failures)
    by_module = Counter(item["module"] for item in failures)
    category_rows = "".join(
        f"<tr><td>{count}</td><td>{html.escape(category)}</td><td>{html.escape(next(i['action'] for i in failures if i['category'] == category))}</td></tr>"
        for category, count in by_category.most_common()
    )
    module_rows = "".join(
        f"<tr><td>{count}</td><td>{html.escape(module)}</td></tr>"
        for module, count in by_module.most_common()
    )
    case_rows = "".join(
        "<tr data-category='{category}' data-priority='{priority}'>"
        "<td><span class='pill {priority}'>{priority}</span></td>"
        "<td>{module}</td><td class='name'>{name}</td><td>{category}</td><td><pre>{detail}</pre></td></tr>".format(
            category=html.escape(item["category"]),
            priority=html.escape(item["priority"]),
            module=html.escape(item["module"]),
            name=html.escape(item["name"]),
            detail=html.escape(compact_detail(item["detail"])),
        )
        for item in failures
    )
    generated = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    content = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>全量 BDD 失败专项静态报告</title>
<style>
:root{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif;color:#172033;background:#f4f7fb}}
body{{margin:0}}main{{max-width:1500px;margin:auto;padding:28px 20px 60px}}.hero{{background:#10233f;color:#fff;border-radius:16px;padding:26px 28px}}h1{{margin:0 0 8px;font-size:26px}}h2{{font-size:18px;margin:0 0 12px}}.muted{{color:#becce0;font-size:13px}}.metrics{{display:flex;gap:10px;flex-wrap:wrap;margin-top:20px}}.metric{{min-width:105px;padding:11px 14px;border:1px solid #ffffff22;border-radius:9px;background:#ffffff12}}.metric b{{display:block;font-size:22px;margin-top:4px}}.panel{{margin-top:18px;padding:20px;background:#fff;border:1px solid #dfe6ef;border-radius:13px;overflow:hidden}}.note{{padding:12px 14px;background:#f5f9ff;border-left:4px solid #3977bd;line-height:1.65;font-size:13px}}.risk{{background:#fff5f4;border-color:#c2413b}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{padding:9px 8px;border-bottom:1px solid #e8edf3;text-align:left;vertical-align:top}}th{{background:#f7f9fc}}.pill{{display:inline-block;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:700}}.P1{{background:#ffe9e7;color:#b42318}}.P2{{background:#fff2d6;color:#8a5b00}}.P3{{background:#edf4fc;color:#2f6198}}.failure-table{{table-layout:fixed;min-width:1120px}}.failure-table th:nth-child(1),.failure-table td:nth-child(1){{width:7%}}.failure-table th:nth-child(2),.failure-table td:nth-child(2){{width:15%}}.failure-table th:nth-child(3),.failure-table td:nth-child(3){{width:22%}}.failure-table th:nth-child(4),.failure-table td:nth-child(4){{width:15%}}.failure-table th:nth-child(5),.failure-table td:nth-child(5){{width:41%}}.name{{font-weight:650;overflow-wrap:anywhere}}pre{{white-space:pre-wrap;word-break:break-word;margin:0;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;max-width:none;max-height:260px;overflow:auto}}.filters{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}}button{{border:1px solid #cad4e1;background:#fff;border-radius:7px;padding:7px 11px;cursor:pointer}}button.active{{background:#10233f;color:#fff}}
</style></head><body><main>
<section class='hero'><h1>Gangtise Demo 全量 BDD 失败专项静态报告</h1><div class='muted'>来源：full_system_bdd_report.json · 最新回归时间：{html.escape(report['generated_at'])} · 报告生成：{generated}</div><div class='metrics'><div class='metric'>失败场景<b>{len(failures)}</b></div><div class='metric'>全量通过<b>{report['counts']['PASS']}</b></div><div class='metric'>跳过<b>{report['counts']['SKIP']}</b></div><div class='metric'>P1<b>{sum(i['priority']=='P1' for i in failures)}</b></div></div></section>
<section class='panel'><h2>结论</h2><div class='note risk'><strong>当前不能验收为全通过。</strong> 80 个失败不是 80 个已确认业务 Bug，包含测试上下文缺失、权限/会话未建立、旧页面或旧数据源契约、严格 LLM 配置缺失，以及少量需要产品决策的功能状态差异。本报告不把这些问题隐藏或自动标记为通过。</div><div class='note' style='margin-top:10px'><strong>凭证边界：</strong>本轮报告未注入用户提供的 LLM key；正式程序仍只读取数据库凭证。本报告也未调用生产 API、未修改数据库。</div></section>
<section class='panel'><h2>按失败类型</h2><table><thead><tr><th>数量</th><th>类型</th><th>建议处理</th></tr></thead><tbody>{category_rows}</tbody></table></section>
<section class='panel'><h2>按业务模块</h2><table><thead><tr><th>数量</th><th>模块</th></tr></thead><tbody>{module_rows}</tbody></table></section>
<section class='panel'><h2>失败用例明细</h2><div class='filters'><button class='active' data-filter='ALL'>全部</button><button data-filter='P1'>P1</button><button data-filter='P2'>P2</button><button data-filter='P3'>P3</button></div><div style='overflow:auto'><table id='cases' class='failure-table'><colgroup><col style='width:7%'><col style='width:15%'><col style='width:22%'><col style='width:15%'><col style='width:41%'></colgroup><thead><tr><th>优先级</th><th>模块</th><th>测试用例</th><th>失败类型</th><th>原始断言/错误</th></tr></thead><tbody>{case_rows}</tbody></table></div></section>
</main><script>document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{{document.querySelectorAll('[data-filter]').forEach(x=>x.classList.remove('active'));b.classList.add('active');const f=b.dataset.filter;document.querySelectorAll('#cases tbody tr').forEach(r=>r.style.display=f==='ALL'||r.dataset.priority===f?'':'none')}})</script></body></html>"""
    OUTPUT.write_text(content, encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
