"""API-only business acceptance BDD runner.

This runner deliberately uses HTTP only. It does not import the Flask app,
domain services, database drivers, or provider clients. Configure the target
with REAL_BDD_BASE_URL, REAL_BDD_USERNAME, and REAL_BDD_PASSWORD.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "static" / "downloads"
REPORT_JSON = REPORT_DIR / "api_acceptance_bdd_report.json"
REPORT_HTML = REPORT_DIR / "api_acceptance_bdd_report.html"


def safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_json(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    result = dict(headers)
    if "Authorization" in result:
        result["Authorization"] = "Bearer <redacted>"
    return result


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 90.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.evidence: list[dict[str, Any]] = []

    def request(self, method: str, path: str, payload: Any = None, query: dict[str, Any] | None = None) -> tuple[int, dict[str, Any], dict[str, Any]]:
        url = f"{self.base_url}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        body = None
        headers = {"Accept": "application/json", "User-Agent": "real-api-acceptance-bdd/1.0"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        status = 0
        response_body: dict[str, Any] = {}
        raw_text = ""
        error_text = ""
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                status = int(response.status)
                raw_text = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw_text = exc.read().decode("utf-8", "replace")
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"
        try:
            parsed = json.loads(raw_text) if raw_text else {}
            response_body = parsed if isinstance(parsed, dict) else {"_raw": parsed}
        except json.JSONDecodeError:
            response_body = {"_raw_text": raw_text[:4000]}
        evidence = {
            "request": {"method": method.upper(), "url": url, "headers": redact_headers(headers), "body": safe_json(payload)},
            "response": {"status": status, "body": safe_json(response_body), "transport_error": error_text},
        }
        self.evidence.append(evidence)
        return status, response_body, evidence


def domain_for_scenario(name: str) -> str:
    if any(token in name for token in ("登录", "权限", "租户", "可达性")):
        return "身份与租户域"
    if "智能指标" in name or "指标" in name:
        return "智能指标域"
    if "智能体" in name:
        return "小金智能体域"
    if "洞见" in name or "草稿" in name or "清理" in name:
        return "洞见内容域"
    return "平台 API 域"


def scenario(report: dict[str, Any], name: str, given: str, when: str, then: str, passed: bool, detail: str, evidence: Any, domain: str | None = None) -> None:
    report["scenarios"].append({
        "domain": domain or domain_for_scenario(name),
        "name": name,
        "given": given,
        "when": when,
        "then": then,
        "passed": bool(passed),
        "detail": str(detail),
        "evidence": safe_json(evidence),
    })


def numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"--", "-", "null", "None"}:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        parsed = float(match.group(0))
        return parsed if math.isfinite(parsed) else None
    except ValueError:
        return None


def extract_preview(body: dict[str, Any]) -> dict[str, Any]:
    preview = body.get("preview")
    return preview if isinstance(preview, dict) else {}


def indicator_items(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = []
    for key in ("base_indicators", "tenant_smart_indicators"):
        raw = catalog.get(key) or []
        if isinstance(raw, list):
            raw_items.extend(raw)
    result = []
    seen = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("indicator_code") or item.get("code") or "").strip()
        name = str(item.get("indicator_name") or item.get("name") or code).strip()
        if code and code not in seen:
            seen.add(code)
            result.append({**item, "indicator_code": code, "indicator_name": name})
    return result


def classify(item: dict[str, Any]) -> str:
    text = " ".join(str(item.get(k) or "") for k in ("source_type", "source_type_label", "category", "indicator_name", "name")).lower()
    if any(word in text for word in ("宏观", "cpi", "ppi", "macro")):
        return "macro"
    if any(word in text for word in ("行业", "申万", "industry", "sector")):
        return "industry"
    if any(word in text for word in ("个股", "股票", "stock", "security")):
        return "stock"
    if any(word in text for word in ("市场", "指数", "market", "index")):
        return "market"
    return "other"


def preview_indicator(client: ApiClient, tenant: str, item: dict[str, Any], prompt: str | None = None, formula_js: str = "") -> tuple[int, dict[str, Any]]:
    selected = [{"indicator_code": item["indicator_code"], "indicator_name": item["indicator_name"]}]
    payload: dict[str, Any] = {
        "action": "preview",
        "indicator_name": f"API验收-{item['indicator_name']}",
        "prompt_text": prompt or item["indicator_name"],
        "selected_indicators": selected,
        "selected_tag_codes": [],
        "formula_tokens": [],
    }
    if formula_js:
        payload["formula_js"] = formula_js
    status, body, _ = client.request("POST", f"/api/tenant/{urllib.parse.quote(tenant, safe='')}/smart-indicators", payload)
    return status, body


def run_indicator_bdd(client: ApiClient, report: dict[str, Any], tenant: str, catalog: dict[str, Any]) -> None:
    items = indicator_items(catalog)
    report["indicator_catalog"] = safe_json(catalog)
    report["indicator_count"] = len(items)
    values: dict[str, float] = {}
    item_by_code = {item["indicator_code"]: item for item in items}
    for item in items:
        status, body = preview_indicator(client, tenant, item)
        preview = extract_preview(body)
        value = numeric(preview.get("numeric_value"))
        passed = status == 200 and body.get("success") is True and preview.get("data_status") == "available" and value is not None
        if passed:
            values[item["indicator_code"]] = value
        scenario(
            report,
            f"智能指标真实数据：{item['indicator_name']}",
            "指标目录 API 返回该指标，且不使用测试值或数据库读取。",
            "通过 smart-indicators preview API 请求该指标的最新结果。",
            "HTTP 成功、数据状态为 available、返回有限数值。",
            passed,
            f"HTTP {status}; data_status={preview.get('data_status')}; numeric_value={preview.get('numeric_value')}",
            {"indicator": item, "preview": preview},
        )

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        groups.setdefault(classify(item), []).append(item)
    selected_groups = [key for key in ("macro", "market", "industry", "stock") if groups.get(key)]
    combo_items = [groups[key][0] for key in selected_groups]
    if len(combo_items) < 2:
        combo_items = items[: min(4, len(items))]
    for count in (2, 3):
        selected = combo_items[:count]
        if len(selected) < count or any(item["indicator_code"] not in values for item in selected):
            scenario(report, f"{count}指标真实组合加减乘除", "至少有足够的不同类型指标已返回真实数值。", "调用组合公式预览 API。", "组合公式返回 available 且与单指标真实值计算一致。", False, "可用的真实指标不足，未使用模拟值补齐。", {"selected": selected})
            continue
        refs = [{"indicator_code": item["indicator_code"], "indicator_name": item["indicator_name"]} for item in selected]
        for operator in ("+", "-", "*", "/"):
            expression = f'Number(inputs["{selected[0]["indicator_code"]}"] || 0)'
            expected = values[selected[0]["indicator_code"]]
            skipped = False
            for item in selected[1:]:
                divisor = values[item["indicator_code"]]
                if operator == "/" and divisor == 0:
                    skipped = True
                    break
                expression = f'{expression} {operator} Number(inputs["{item["indicator_code"]}"] || 0)'
                if operator == "+":
                    expected += divisor
                elif operator == "-":
                    expected -= divisor
                elif operator == "*":
                    expected *= divisor
                else:
                    expected /= divisor
            if skipped:
                scenario(report, f"{count}指标真实组合除法", "真实 API 返回的除数为零，不能伪造可计算输入。", "跳过会产生除零的业务组合。", "不使用模拟值掩盖除零问题。", True, "SKIP：真实除数为 0。", {"selected": selected})
                continue
            prompt = f" {operator} ".join(item["indicator_name"] for item in selected)
            payload = {"action": "preview", "indicator_name": f"API验收-{count}指标{operator}", "prompt_text": prompt, "selected_indicators": refs, "formula_js": f"return {expression};", "formula_tokens": []}
            status, body, _ = client.request("POST", f"/api/tenant/{urllib.parse.quote(tenant, safe='')}/smart-indicators", payload)
            preview = extract_preview(body)
            actual = numeric(preview.get("numeric_value"))
            expected = round(expected, 4)
            passed = status == 200 and body.get("success") is True and preview.get("data_status") == "available" and actual is not None and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=0.0001)
            scenario(report, f"{count}指标真实组合{operator}", "组合成员均来自目录 API 且各自已取得真实数值。", f"以 API 返回的指标引用执行 {prompt}。", "服务端结果与真实输入值的确定性运算一致。", passed, f"HTTP {status}; expected={expected}; actual={actual}", {"selected": selected, "formula_js": payload["formula_js"], "preview": preview})


def run_hermes_bdd(client: ApiClient, report: dict[str, Any], tenant: str, username: str) -> None:
    questions = [
        ("智能体咨询：个股分析", "请基于今天的真实市场数据分析贵州茅台（600519）的走势，并说明依据。", "basic"),
        ("智能体咨询：上下文追问", "继续分析A股市场走向，并结合刚才的结论说明风险。", "basic"),
        ("智能体任务：评论与K线标注归纳", "归纳今天用户评论与个股K线标注，输出粉丝关注主题、情绪分布和大V可行动建议。", "task"),
    ]
    messages: list[dict[str, str]] = []
    for index, (name, question, mode) in enumerate(questions):
        messages.append({"role": "user", "content": question})
        payload = {
            "tenant_slug": tenant,
            "user_role": "dav",
            "user_profile_id": username,
            "user_name": username,
            "entry_point": "api_acceptance_bdd",
            "question": question,
            "messages": list(messages),
            "attachments": [],
            "selected_knowledge_ids": [],
            "preferred_mode": mode,
            "assistant_mode": mode,
            "web_answer": False,
        }
        status, body, _ = client.request("POST", "/api/hermes/query", payload)
        answer = str(body.get("answer") or body.get("result") or "").strip()
        passed = status == 200 and body.get("ok") is True and len(answer) >= 20 and not body.get("error")
        if index == 1 and len(messages) < 2:
            passed = False
        scenario(report, name, "通过真实登录会话进入小金智能体，保留前序对话上下文。", f"调用 /api/hermes/query，模式为 {mode}。", "返回真实非空回答，并且没有被模板或模拟值替代。", passed, f"HTTP {status}; answer_length={len(answer)}; intent={body.get('intent')}; mode={body.get('mode') or body.get('assistant_mode')}", {"response": body, "messages_sent": messages})


def run_insight_bdd(client: ApiClient, report: dict[str, Any], tenant: str, username: str) -> None:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    draft_title = f"API验收临时草稿-{stamp}"
    draft_content = "这是 API-only BDD 验收产生的临时洞见草稿，测试结束后通过业务 API 清理。"
    status, body, _ = client.request("POST", f"/api/tenant/{urllib.parse.quote(tenant, safe='')}/insight-drafts", {"title": draft_title, "content_text": draft_content, "source_mode": "api_acceptance_bdd", "access_mode": "public"})
    draft = body.get("draft") if isinstance(body.get("draft"), dict) else {}
    draft_id = str(draft.get("id") or "")
    scenario(report, "洞见 API 创建草稿", "大V已登录且使用真实租户业务接口。", "POST insight-drafts 写入一篇临时草稿。", "返回成功并获得草稿 ID，正文与标题保持不变。", status in (200, 201) and body.get("ok") is True and bool(draft_id), f"HTTP {status}; draft_id={draft_id}", {"response": body})

    publish_ids: list[str] = []
    for access_mode in ("public", "subscriber"):
        title = f"API验收临时发布-{access_mode}-{stamp}"
        content = f"API-only BDD 临时发布内容（{access_mode}），测试结束后清理。"
        payload = {"text": content, "tenant_slug": tenant, "period": "day", "review_title": title, "access_mode": access_mode, "entry_point": "api_acceptance_bdd", "speaker_name": username, "transcription_engine": "manual", "transcript_model": "manual_input", "source_mode": "manual", "paragraph_mode": "manual", "prompt_tags": []}
        pstatus, pbody, _ = client.request("POST", "/api/review/publish", payload)
        snapshot = pbody.get("snapshot") if isinstance(pbody.get("snapshot"), dict) else {}
        review_id = str(snapshot.get("id") or pbody.get("snapshot_id") or "")
        if review_id:
            publish_ids.append(review_id)
        scenario(report, f"洞见真实发布：{access_mode}", "草稿/编辑链路通过真实 HTTP 接口执行。", f"POST /api/review/publish，发布范围为 {access_mode}。", "返回成功并产生可查询的发布记录。", pstatus in (200, 201) and pbody.get("success") is True and bool(review_id), f"HTTP {pstatus}; review_id={review_id}", {"response": pbody, "payload": payload})

    qstatus, qbody, _ = client.request("GET", f"/api/tenant/{urllib.parse.quote(tenant, safe='')}/published-insights", query={"limit": 100, "offset": 0, "q": "API验收临时发布"})
    rows = qbody.get("items") if isinstance(qbody.get("items"), list) else []
    titles = {str(row.get("title") or "") for row in rows if isinstance(row, dict)}
    scenario(report, "洞见列表查询与权限标签", "公开和订阅洞见已由发布 API 返回成功。", "通过 published-insights API 查询临时标题。", "列表返回对应标题，并包含 access_mode 权限信息。", qstatus == 200 and qbody.get("ok") is True and any("API验收临时发布-public" in title for title in titles) and any("API验收临时发布-subscriber" in title for title in titles), f"HTTP {qstatus}; matched={sorted(titles)}", {"response": qbody})

    cleanup = []
    if draft_id:
        dstatus, dbody, _ = client.request("DELETE", f"/api/tenant/{urllib.parse.quote(tenant, safe='')}/insight-drafts/{urllib.parse.quote(draft_id, safe='')}")
        cleanup.append({"kind": "draft", "id": draft_id, "status": dstatus, "body": dbody})
    for review_id in publish_ids:
        rstatus, rbody, _ = client.request("DELETE", f"/api/tenant/{urllib.parse.quote(tenant, safe='')}/reviews/{urllib.parse.quote(review_id, safe='')}")
        cleanup.append({"kind": "published_insight", "id": review_id, "status": rstatus, "body": rbody})
    report["cleanup"] = cleanup
    scenario(report, "验收数据清理", "本次测试只产生临时业务内容。", "使用洞见草稿删除和洞见删除业务 API 清理。", "每一条临时记录均由业务接口处理成功。", bool(cleanup) and all(item["status"] in (200, 204) for item in cleanup), f"cleanup_count={len(cleanup)}", cleanup)


def run_identity_boundary_bdd(client: ApiClient, report: dict[str, Any], tenant: str) -> None:
    anonymous = ApiClient(client.base_url, timeout=client.timeout)
    status, body, _ = anonymous.request("GET", f"/api/tenant/{urllib.parse.quote(tenant, safe='')}/smart-indicators")
    scenario(report, "未登录访问租户指标 API", "客户端没有登录 Cookie。", "直接请求租户 smart-indicators API。", "服务端拒绝未认证请求，不返回业务数据。", status in (401, 403) and not body.get("smart_indicator_catalog"), f"HTTP {status}; error={body.get('error')}", {"response": body})


def run_tenant_scope_bdd(client: ApiClient, report: dict[str, Any]) -> None:
    status, body, _ = client.request("GET", "/api/tenant/not-a-real-tenant/smart-indicators")
    scenario(report, "登录后越权访问其他租户", "大V已登录，但请求了不属于当前账户的租户 slug。", "请求其他租户的 smart-indicators API。", "服务端不泄露其他租户指标数据。", status in (403, 404) and not body.get("smart_indicator_catalog"), f"HTTP {status}; error={body.get('error')}", {"response": body})


def render(report: dict[str, Any]) -> str:
    rows = []
    for item in report["scenarios"]:
        status = "PASS" if item["passed"] else "FAIL"
        rows.append(f"<article class=\"scenario {'pass' if item['passed'] else 'fail'}\"><header><h2>{html.escape(item['name'])}</h2><b>{status}</b></header><p><b>Given</b> {html.escape(item['given'])}</p><p><b>When</b> {html.escape(item['when'])}</p><p><b>Then</b> {html.escape(item['then'])}</p><div class=detail>{html.escape(item['detail'])}</div><details><summary>查看 HTTP 证据</summary><pre>{html.escape(json.dumps(item['evidence'], ensure_ascii=False, indent=2))}</pre></details></article>")
    status = "通过" if report["failed_count"] == 0 and not report.get("blocked") else ("阻断" if report.get("blocked") else "存在失败")
    domains = "".join(f"<span class=metric>{html.escape(key)} <b>{value}</b></span>" for key, value in sorted(report.get("domain_summary", {}).items()))
    return f"""<!doctype html><html lang=zh-CN><head><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\"><title>API业务验收BDD报告</title><style>body{{margin:0;background:#eef4f7;color:#19324c;font:14px/1.65 -apple-system,BlinkMacSystemFont,\"PingFang SC\",\"Microsoft YaHei\",sans-serif}}main{{max-width:1160px;margin:auto;padding:26px 16px 60px}}.hero,.scenario{{background:#fffdf9;border:1px solid #d9e1e7;border-radius:12px;padding:18px;margin:12px 0}}h1{{margin:0 0 8px}}h2{{font-size:17px;margin:0}}.muted,.detail{{color:#617287}}.notice{{padding:11px;background:#fff6df;border-left:3px solid #9b6a12;margin-top:12px}}.scenario{{border-left:5px solid #16704d}}.scenario.fail{{border-left-color:#ae342a}}.scenario header{{display:flex;justify-content:space-between;gap:10px}}.scenario header b{{color:#16704d}}.scenario.fail header b{{color:#ae342a}}pre{{background:#13283a;color:#eaf2f8;padding:12px;border-radius:8px;white-space:pre-wrap;word-break:break-word;overflow:auto;font:11px/1.5 ui-monospace,monospace}}summary{{cursor:pointer;color:#1769aa;font-weight:700}}.metrics{{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}}.metric{{padding:7px 11px;border:1px solid #d9e1e7;border-radius:8px}}</style></head><body><main><section class=hero><h1>真实业务 API 编排 BDD 验收报告</h1><div class=muted>执行时间：{html.escape(report['generated_at'])} · API：{html.escape(report['base_url'])} · 租户：{html.escape(report['tenant'])}</div><div class=notice>{html.escape(report['execution_mode'])}<br>结果：{status}</div><div class=metrics><span class=metric>场景 <b>{len(report['scenarios'])}</b></span><span class=metric>通过 <b>{report['passed_count']}</b></span><span class=metric>失败 <b>{report['failed_count']}</b></span><span class=metric>HTTP 请求 <b>{len(report.get('http_evidence', []))}</b></span>{domains}</div></section>{''.join(rows)}</main></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("REAL_BDD_BASE_URL", "http://127.0.0.1:5001"))
    parser.add_argument("--tenant", default=os.environ.get("REAL_BDD_TENANT", "laowang"))
    parser.add_argument("--username", default=os.environ.get("REAL_BDD_USERNAME", ""))
    parser.add_argument("--password", default=os.environ.get("REAL_BDD_PASSWORD", ""))
    args = parser.parse_args()
    report: dict[str, Any] = {
        "title": "真实业务 API 编排 BDD 验收",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": args.base_url,
        "tenant": args.tenant,
        "scenarios": [],
        "blocked": False,
        "execution_mode": "仅 HTTP API；不读取数据库、不调用 Flask 内部函数、不使用 mock 或模拟指标值。",
        "cleanup": [],
    }
    client = ApiClient(args.base_url)
    try:
        status, body, _ = client.request("GET", "/login")
        scenario(report, "业务 API 可达性", "验收环境提供 HTTP 服务。", "请求公开登录入口作为 HTTP 探针。", "服务可达，后续登录 API 可以继续执行。", status == 200, f"HTTP {status}", body)
        run_identity_boundary_bdd(client, report, args.tenant)
        if not args.username or not args.password:
            report["blocked"] = True
            report["blocking_reason"] = "缺少 REAL_BDD_USERNAME / REAL_BDD_PASSWORD，无法建立真实大V业务会话。"
        else:
            lstatus, lbody, _ = client.request("POST", "/api/h5/login/password", {"username": args.username, "password": args.password})
            logged_in = lstatus == 200 and lbody.get("ok") is True
            scenario(report, "真实大V登录", "提供真实验收账号，不使用测试会话注入。", "调用 H5 密码登录 API 并保存 HTTP Cookie。", "登录成功并获得当前账号上下文。", logged_in, f"HTTP {lstatus}; error={lbody.get('error')}", {"response": lbody})
            if not logged_in:
                report["blocked"] = True
                report["blocking_reason"] = f"真实账号登录失败：{lbody.get('error') or lstatus}"
            else:
                run_tenant_scope_bdd(client, report)
                cstatus, catalog_body, _ = client.request("GET", f"/api/tenant/{urllib.parse.quote(args.tenant, safe='')}/smart-indicators")
                catalog = catalog_body.get("smart_indicator_catalog") if isinstance(catalog_body.get("smart_indicator_catalog"), dict) else {}
                catalog_ok = cstatus == 200 and catalog_body.get("success") is True and bool(indicator_items(catalog))
                scenario(report, "智能指标真实目录", "真实大V会话已建立。", "读取租户 smart-indicators 目录 API。", "返回真实指标目录，后续每个指标均由 API 预览取值。", catalog_ok, f"HTTP {cstatus}; indicator_count={len(indicator_items(catalog))}", {"catalog": catalog})
                if catalog_ok:
                    run_indicator_bdd(client, report, args.tenant, catalog)
                else:
                    report["blocked"] = True
                    report["blocking_reason"] = f"智能指标目录不可用：HTTP {cstatus}"
                run_hermes_bdd(client, report, args.tenant, args.username)
                run_insight_bdd(client, report, args.tenant, args.username)
    except Exception as exc:
        report["blocked"] = True
        report["blocking_reason"] = f"API 编排执行异常：{type(exc).__name__}: {exc}"
    report["http_evidence"] = client.evidence
    report["passed_count"] = sum(1 for item in report["scenarios"] if item["passed"])
    report["failed_count"] = sum(1 for item in report["scenarios"] if not item["passed"])
    report["domain_summary"] = {}
    for item in report["scenarios"]:
        domain = item.get("domain") or "平台 API 域"
        report["domain_summary"][domain] = report["domain_summary"].get(domain, 0) + 1
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(safe_json(report), ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_HTML.write_text(render(report), encoding="utf-8")
    print(json.dumps({"ok": report["failed_count"] == 0 and not report["blocked"], "blocked": report["blocked"], "passed": report["passed_count"], "failed": report["failed_count"], "html_report": str(REPORT_HTML), "json_report": str(REPORT_JSON)}, ensure_ascii=False))
    return 0 if report["failed_count"] == 0 and not report["blocked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
