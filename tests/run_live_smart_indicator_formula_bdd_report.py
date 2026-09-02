"""Generate the static report for explicit real-data formula BDD runs."""

from __future__ import annotations

import html
import json
import sys
import traceback
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.live_smart_indicator_formula_bdd import LIVE_FLAG, run_live_smart_indicator_formula_bdd


REPORT_DIR = PROJECT_ROOT / "static" / "downloads"
REPORT_HTML_PATH = REPORT_DIR / "live_smart_indicator_formula_bdd_report.html"
REPORT_JSON_PATH = REPORT_DIR / "live_smart_indicator_formula_bdd_report.json"


def _json(value: Any) -> str:
    return html.escape(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def render_html(report: dict[str, Any]) -> str:
    rows = "".join(
        f"""
        <article class=\"scenario {'pass' if item['passed'] else 'fail'}\">
          <header><div><span class=\"category\">{html.escape(item['category'])}</span><h2>{html.escape(item['name'])}</h2></div><strong>{'PASS' if item['passed'] else 'FAIL'}</strong></header>
          <p><b>Given</b> {html.escape(item['given'])}</p><p><b>When</b> {html.escape(item['when'])}</p><p><b>Then</b> {html.escape(item['then'])}</p>
          <div class=\"detail\">{html.escape(item['detail'])}</div><details><summary>查看真实请求与快照证据</summary><pre>{_json(item['evidence'])}</pre></details>
        </article>"""
        for item in report.get("scenarios", [])
    )
    status = "通过" if not report.get("failed_count") else "存在失败"
    return f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>{html.escape(report['title'])}</title><style>
:root{{--ink:#19324c;--muted:#617287;--paper:#fffdf9;--line:#d9e1e7;--blue:#1769aa;--green:#16704d;--red:#ae342a;--gold:#9b6a12}}*{{box-sizing:border-box}}body{{margin:0;background:#eef4f7;color:var(--ink);font:14px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}}main{{max-width:1160px;margin:auto;padding:28px 18px 60px}}.hero,.panel,.scenario{{background:var(--paper);border:1px solid var(--line);border-radius:10px}}.hero{{padding:23px;border-top:4px solid var(--blue)}}h1{{font-size:28px;margin:0 0 8px}}h2{{font-size:18px;margin:5px 0 0}}.muted,.detail{{color:var(--muted)}}.notice{{margin-top:14px;padding:11px 13px;border-left:3px solid var(--gold);background:#fff6df;color:#76530e}}.metrics{{display:flex;gap:10px;flex-wrap:wrap;margin-top:17px}}.metric{{padding:8px 12px;border:1px solid var(--line);border-radius:7px;background:#fff}}.pass-text{{color:var(--green);font-weight:800}}.fail-text{{color:var(--red);font-weight:800}}.panel{{padding:16px;margin-top:18px}}.scenario{{padding:16px;margin:13px 0;border-left:5px solid var(--green)}}.scenario.fail{{border-left-color:var(--red)}}.scenario header{{display:flex;justify-content:space-between;gap:12px;align-items:start}}.scenario header strong{{color:var(--green)}}.scenario.fail header strong{{color:var(--red)}}.category{{font-size:11px;color:var(--blue);font-weight:800}}p{{margin:8px 0}}details{{margin-top:10px}}summary{{cursor:pointer;color:var(--blue);font-weight:700}}pre{{margin:8px 0 0;padding:12px;border-radius:7px;overflow:auto;background:#13283a;color:#eaf2f8;white-space:pre-wrap;word-break:break-word;font:11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}}@media(max-width:640px){{main{{padding:18px 12px 40px}}h1{{font-size:23px}}}}
</style></head><body><main><section class=\"hero\"><h1>{html.escape(report['title'])}</h1><div class=\"muted\">执行时间：{html.escape(report['generated_at'])} · 租户：{html.escape(report['tenant_slug'])} · 大V会话：{html.escape(report['dav_username'])} · 结果：<b class=\"{'pass-text' if not report.get('failed_count') else 'fail-text'}\">{status}</b></div><div class=\"notice\">{html.escape(report['execution_mode'])}</div><div class=\"metrics\"><div class=\"metric\">场景 <b>{len(report.get('scenarios', []))}</b></div><div class=\"metric\">通过 <b class=\"pass-text\">{report.get('passed_count', 0)}</b></div><div class=\"metric\">失败 <b class=\"{'fail-text' if report.get('failed_count') else 'pass-text'}\">{report.get('failed_count', 0)}</b></div><div class=\"metric\">公式执行 <b>确定性算术，不调用 LLM</b></div></div></section><section class=\"panel\"><h2>当前真实快照</h2><pre>{_json(report.get('snapshots', []))}</pre></section><section class=\"panel\"><h2>标签目录选择</h2><pre>{_json(report.get('catalog', {}))}</pre></section><section class=\"panel\"><h2>BDD 场景</h2>{rows}</section></main></body></html>"""


def main() -> int:
    if __import__("os").environ.get(LIVE_FLAG) != "1":
        print(f"Refusing live execution: set {LIVE_FLAG}=1")
        return 2
    try:
        report = run_live_smart_indicator_formula_bdd()
    except Exception as exc:
        report = {
            "title": "H5 大V工作台智能指标公式真实数据 BDD 报告",
            "generated_at": "执行失败",
            "tenant_slug": "laowang",
            "dav_username": "财经老王",
            "execution_mode": "真实数据测试初始化失败；未降级为 mock 或回退数据。",
            "scenarios": [],
            "passed_count": 0,
            "failed_count": 1,
            "catalog": {},
            "snapshots": [],
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    REPORT_HTML_PATH.write_text(render_html(report), encoding="utf-8")
    print(json.dumps({"ok": report["failed_count"] == 0, "html_report": str(REPORT_HTML_PATH), "json_report": str(REPORT_JSON_PATH), "passed": report["passed_count"], "failed": report["failed_count"]}, ensure_ascii=False))
    return 0 if report["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
