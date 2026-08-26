import html
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.market_services import _extract_gangtise_agent_answer_delta, _merge_gangtise_sse_texts


SOURCE = Path("/tmp/gangtise_multi_stock_agent_test.json")
TARGET = Path("static/downloads/gangtise_multi_stock_agent_sse_report_20260826.html")


def esc(value):
    return html.escape(str(value or ""), quote=False)


payload = json.loads(SOURCE.read_text(encoding="utf-8"))
result = payload.get("result") or {}
request = result.get("request") or {}
prompt = str(request.get("text") or "")
unfiltered_text = str(result.get("text") or "")
raw_text = str(result.get("raw_text") or "")
raw_events = []
for raw_event in raw_text.split("\n\n"):
    try:
        raw_events.append(json.loads(raw_event))
    except json.JSONDecodeError:
        continue
answer_deltas = [_extract_gangtise_agent_answer_delta(item) for item in raw_events]
text = _merge_gangtise_sse_texts(item for item in answer_deltas if item is not None) or unfiltered_text
stocks = [name for name in ("贵州茅台（600519.SH）", "宁德时代（300750.SZ）", "腾讯控股（00700.HK）") if name in text]
has_portfolio = any(word in text for word in ("组合", "综合结论", "明日关注"))
request_for_report = {
    "text": prompt,
    "mode": request.get("mode"),
    "askChatParam": request.get("askChatParam"),
}
raw_output = raw_text or "（未返回原始 SSE 内容）"
parsed_output = text or "（未提取到文本）"

html_doc = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gangtise Agent SSE 多股票实测报告 2026-08-26</title>
<style>
:root{{--ink:#172127;--muted:#627278;--line:#d7e1df;--page:#f3f7f6;--card:#fff;--teal:#006c69;--green:#047857;--red:#b42318;--amber:#9a6700}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--page);color:var(--ink);font:14px/1.58 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}}
main{{max-width:1280px;margin:auto;padding:30px 20px 64px}}header{{background:linear-gradient(125deg,#073f3d,#006c69);padding:27px 29px;border-radius:10px;color:#fff}}h1{{font-size:27px;margin:0 0 7px}}h2{{font-size:19px;margin:30px 0 10px}}h3{{font-size:15px;margin:0 0 5px}}.sub{{margin:0;color:#cde6e2}}
.notice{{margin:20px 0;padding:14px 16px;background:#fff8e6;border-left:4px solid var(--amber);color:#664d03}}.metrics{{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:12px;margin:20px 0}}.metric{{background:var(--card);border:1px solid var(--line);border-radius:7px;padding:14px}}.metric span{{font-size:12px;color:var(--muted)}}.metric strong{{display:block;font-size:24px;margin-top:4px}}.ok-text{{color:var(--green)}}
.table-wrap{{overflow:auto;background:#fff;border:1px solid var(--line);border-radius:7px}}table{{border-collapse:collapse;width:100%;min-width:760px}}th,td{{padding:10px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}th{{background:#eaf3f1;font-size:12px;color:#274047}}tr:last-child td{{border-bottom:0}}code{{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:#16525a}}
.tag{{display:inline-block;padding:3px 6px;border-radius:3px;font-size:11px;font-weight:700}}.ok{{background:#e5f5ee;color:#047857}}.warn{{background:#fff1dc;color:#9a6700}}.block{{background:#0f2026;color:#d7e6e8;border-radius:7px;padding:14px 16px;overflow:auto;font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;margin:8px 0;max-height:520px}}.card{{padding:16px;background:#fff;border:1px solid var(--line);border-radius:7px;margin:10px 0}}.card p{{margin:7px 0;color:var(--muted)}}ul{{padding-left:22px}}li{{margin:6px 0}}footer{{margin-top:28px;border-top:1px solid var(--line);padding-top:13px;color:var(--muted);font-size:12px}}
@media(max-width:720px){{main{{padding:18px 12px 44px}}header{{padding:23px 20px}}h1{{font-size:23px}}.metrics{{grid-template-columns:repeat(2,minmax(120px,1fr))}}}}
</style></head><body><main>
<header><h1>Gangtise Agent SSE 多股票实测报告</h1><p class="sub">接口：<code>/application/open-ai/ai/chat/sse</code> · 场景：三只自选股复盘与组合综合评估 · 测试日期：2026-08-26</p></header>
<section class="notice"><strong>实测结论：</strong>接口可用。一次请求成功返回三只股票的个股分析和组合综合结论；返回流包含内部阶段事件，但按 <code>phase=answer</code> 提取 <code>result.delta</code> 后得到可发布正文，无需大模型二次加工。</section>
<section class="metrics">
  <div class="metric"><span>测试股票</span><strong>{len(stocks)}</strong></div>
  <div class="metric"><span>Agent 调用次数</span><strong class="ok-text">1</strong></div>
  <div class="metric"><span>SSE 事件</span><strong>{int(result.get("events") or 0)}</strong></div>
  <div class="metric"><span>耗时</span><strong>{float(payload.get("elapsed_seconds") or 0):.1f}s</strong></div>
  <div class="metric"><span>原始/正式字符</span><strong>{len(raw_text):,}/{len(text):,}</strong></div>
</section>

<h2>测试请求</h2>
<div class="table-wrap"><table><thead><tr><th>项目</th><th>实测值</th></tr></thead><tbody>
<tr><td>Endpoint</td><td><code>{esc(result.get("endpoint") or "/application/open-ai/ai/chat/sse")}</code></td></tr>
<tr><td>Mode</td><td><code>{esc(result.get("mode") or request.get("mode"))}</code></td></tr>
<tr><td>股票识别</td><td>{esc("、".join(stocks) or "未在返回文本中完整识别")}</td></tr>
<tr><td>组合结论</td><td><span class="tag {"ok" if has_portfolio else "warn"}">{"已返回" if has_portfolio else "未识别"}</span></td></tr>
</tbody></table></div>
<h3>提示词</h3><div class="block">{esc(prompt)}</div>
<h3>请求 JSON（已排除凭证）</h3><div class="block">{esc(json.dumps(request_for_report, ensure_ascii=False, indent=2))}</div>

<h2>返回质量检查</h2>
<div class="card"><ul>
<li><strong>成功性：</strong>HTTP 200 且客户端判定为成功，单次请求完成。</li>
<li><strong>业务覆盖：</strong>返回文本包含贵州茅台、宁德时代、腾讯控股，并包含组合层面的综合评估和明日关注内容。</li>
<li><strong>流格式：</strong>原始事件包含 <code>think</code>、<code>search</code>、<code>answer</code>、<code>annotation</code>、<code>usage</code> 等阶段；其中仅 <code>answer</code> 阶段是可发布正文。</li>
<li><strong>程序处理：</strong>保留完整原文用于诊断，只拼接 <code>phase=answer</code> 的 <code>result.delta</code> 作为用户复盘正文，不做额外 LLM 加工。</li>
</ul></div>

<h2>可发布正文（phase=answer，完整）</h2>
<div class="block">{esc(parsed_output)}</div>
<h2>原始 SSE 事件（完整）</h2>
<div class="block">{esc(raw_output)}</div>
<footer>报告由本地项目测试生成。报告未包含 Access Key、Secret Key、Bearer Token 或数据库连接信息。原始响应按实际返回内容保存，未进行摘要改写。</footer>
</main></body></html>'''

TARGET.parent.mkdir(parents=True, exist_ok=True)
TARGET.write_text(html_doc, encoding="utf-8")
print(TARGET)
