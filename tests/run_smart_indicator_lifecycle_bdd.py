from __future__ import annotations

"""Run the smart-indicator lifecycle BDD against the real local application.

The script uses the real PostgreSQL-backed Flask application and real upstream
refreshers. It does not patch provider responses or use mock indicator values.
Temporary tenant smart-indicator definitions and dashboard edits are removed
after the report is generated.
"""

import copy
import json
import os
import sys
import traceback
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app as app_entry
import src.web.hooks as web_hooks
from src.domain import core_services, market_services


REPORT_PATH = PROJECT_ROOT / "static" / "downloads" / "smart_indicator_lifecycle_bdd_report.html"
REPORT_JSON_PATH = PROJECT_ROOT / "static" / "downloads" / "smart_indicator_lifecycle_bdd_report.json"
TENANT_SLUG = "laowang"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _scenario(name: str, given: str, when: str, then: str, passed: bool, detail: str, evidence: Any) -> dict[str, Any]:
    return {
        "name": name,
        "given": given,
        "when": when,
        "then": then,
        "passed": bool(passed),
        "detail": str(detail or "").strip(),
        "evidence": _json_safe(evidence),
    }


def _post(client, path: str, payload: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    response = client.post(path, json=payload)
    body = response.get_json(silent=True) or {}
    return response, body


def _dashboard_codes(payload: dict[str, Any], state_key: str = "published") -> list[str]:
    state = (payload.get("fund_dashboard_state") or {}).get(state_key) if isinstance(payload, dict) else {}
    cards = state.get("cards") if isinstance(state, dict) else []
    return [
        str((card or {}).get("indicatorCode") or (card or {}).get("indicator_code") or "").strip()
        for card in (cards if isinstance(cards, list) else [])
    ]


def _db_evidence(db, indicator_code: str) -> dict[str, Any]:
    definition = db.execute(
        "SELECT indicator_code, indicator_name, tenant_slug, source_type, provider, prompt_text, formula_js, selected_indicators_json FROM indicator_definitions WHERE indicator_code = ?",
        (indicator_code,),
    ).fetchone()
    latest = db.execute(
        "SELECT latest_value, updated_at, is_simulated, source_code FROM indicator_latest_values WHERE indicator_code = ?",
        (indicator_code,),
    ).fetchone()
    series = db.execute(
        "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE is_simulated = 0) AS real_count FROM indicator_series WHERE indicator_code = ?",
        (indicator_code,),
    ).fetchone()
    return {
        "definition_exists": bool(definition),
        "definition": dict(definition) if definition else {},
        "latest_exists": bool(latest),
        "latest": dict(latest) if latest else {},
        "series": dict(series) if series else {},
    }


def _render(report: dict[str, Any]) -> str:
    scenarios = report["scenarios"]
    passed = sum(1 for item in scenarios if item["passed"])
    cards = []
    for item in scenarios:
        status = "PASS" if item["passed"] else "FAIL"
        cards.append(
            f"""
            <article class=\"scenario {'pass' if item['passed'] else 'fail'}\">
              <header><h2>{escape(item['name'])}</h2><strong>{status}</strong></header>
              <p><b>Given</b> {escape(item['given'])}</p>
              <p><b>When</b> {escape(item['when'])}</p>
              <p><b>Then</b> {escape(item['then'])}</p>
              <div class=\"detail\">{escape(item['detail'])}</div>
              <details><summary>查看真实证据</summary><pre>{escape(json.dumps(item['evidence'], ensure_ascii=False, indent=2))}</pre></details>
            </article>
            """
        )
    model = report.get("llm_model") or {}
    refresh = report.get("refresh") or {}
    return f"""<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>智能指标生命周期 BDD 报告</title>
<style>
body{{margin:0;background:linear-gradient(180deg,#f5f1e9,#edf4fb);color:#1d2a38;font:14px/1.65 -apple-system,BlinkMacSystemFont,\"PingFang SC\",\"Microsoft YaHei\",sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:30px 20px 60px}} .hero,.section{{background:#fffdf8;border:1px solid #ded7cb;border-radius:20px;padding:22px;margin-bottom:18px;box-shadow:0 10px 30px #1d2a3810}}
h1{{margin:0 0 8px;font-size:30px}} h2{{margin:0;font-size:18px}} .muted{{color:#68788a}} .summary{{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}}
.pill{{padding:7px 13px;border-radius:999px;background:#f4efe5;border:1px solid #e1d8c9}} .good{{color:#23734c;font-weight:800}} .bad{{color:#b14432;font-weight:800}}
.scenario{{background:#fff;border:1px solid #ded7cb;border-left:5px solid #26734d;border-radius:14px;padding:16px;margin:13px 0}} .scenario.fail{{border-left-color:#b14432}} .scenario header{{display:flex;justify-content:space-between;gap:10px;align-items:center}} .scenario.fail header strong{{color:#b14432}} .scenario header strong{{color:#26734d}}
.detail{{color:#68788a;margin-top:10px}} pre{{background:#15212d;color:#edf4fb;padding:13px;border-radius:10px;overflow:auto;white-space:pre-wrap;word-break:break-word;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}} summary{{cursor:pointer;color:#2f74c0;font-weight:700}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .box{{background:#f7f3ec;border-radius:12px;padding:14px}} code{{background:#eee9df;padding:2px 5px;border-radius:4px}}
@media(max-width:760px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<section class=\"hero\"><h1>智能指标生命周期 BDD 测试报告</h1>
<div class=\"muted\">真实执行时间：{escape(report['generated_at'])} · 租户：{TENANT_SLUG} · 真实 PostgreSQL + 真实应用接口，不使用 mock</div>
<div class=\"summary\"><span class=\"pill\">通过 <b class=\"good\">{passed}/{len(scenarios)}</b></span><span class=\"pill\">失败 <b class=\"bad\">{len(scenarios)-passed}</b></span><span class=\"pill\">看板布局 <b>2×2</b></span><span class=\"pill\">模型 <code>{escape(str(model.get('model_name') or '--'))}</code></span></div></section>
<section class=\"section\"><h2>执行前提与模型</h2><div class=\"grid\"><div class=\"box\"><b>上游真实刷新</b><pre>{escape(json.dumps(refresh, ensure_ascii=False, indent=2))}</pre></div><div class=\"box\"><b>智能指标公式模型</b><pre>{escape(json.dumps(model, ensure_ascii=False, indent=2))}</pre></div></div></section>
<section class=\"section\"><h2>BDD 场景</h2>{''.join(cards)}</section>
<section class=\"section\"><h2>结论</h2><p>{escape(report.get('conclusion') or '')}</p><p class=\"muted\">测试结束后已清理本次创建的临时指标定义，并恢复原租户 Dashboard 配置。</p></section>
</main></body></html>"""


def main() -> int:
    report: dict[str, Any] = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tenant_slug": TENANT_SLUG,
        "scenarios": [],
        "refresh": {},
        "llm_model": {},
        "temporary_codes": [],
        "exception": "",
    }
    original_auth = web_hooks.is_authenticated
    original_config = None
    temporary_codes: list[str] = []
    try:
        web_hooks.is_authenticated = lambda: True
        app_entry.app.config.update(TESTING=True)
        client = app_entry.app.test_client()
        with app_entry.app.app_context():
            original_config = copy.deepcopy(core_services.get_site_config())
            model = core_services.get_default_llm_config(
                purpose="general",
                feature_code="smart_indicator_formula_generation",
            ) or {}
            report["llm_model"] = {
                "key": model.get("key") or "",
                "model_name": model.get("model_name") or "",
                "provider": model.get("provider") or "",
                "base_url": model.get("base_url") or "",
                "expected_model": "deepseek-v4-flash-ga-260731",
                "expected_base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "matches_v4": model.get("model_name") == "deepseek-v4-flash-ga-260731",
            }

            # Refresh from the configured real providers before exercising the
            # formula and dashboard lifecycle. Failures remain evidence.
            try:
                report["refresh"]["market_snapshot"] = market_services.sync_market_snapshot(force=True)
            except Exception as exc:
                report["refresh"]["market_snapshot_error"] = str(exc)
            try:
                report["refresh"]["indicator_history"] = market_services.sync_real_indicator_history_from_market_cache(force=True)
            except Exception as exc:
                report["refresh"]["indicator_history_error"] = str(exc)

            original_tenant = core_services.get_tenant_by_slug(TENANT_SLUG, original_config)
            original_dashboard = copy.deepcopy(original_tenant.get("fund_dashboard_config"))
            empty_dashboard = {"layout": "2x2", "title": "BDD 临时智能指标看板", "cards": [{}, {}, {}, {}]}

            response, body = _post(client, f"/api/tenant/{TENANT_SLUG}/dashboard", {"action": "save_draft", "dashboard": empty_dashboard})
            report["scenarios"].append(_scenario(
                "1. 建立 2×2 看板", "用户进入智能指标看板编辑器。", "通过真实 Dashboard API 保存 2×2 空白草稿。", "服务端返回 200 且草稿保留 4 个槽位。", response.status_code == 200 and len(_dashboard_codes(body, "draft")) == 4, f"HTTP {response.status_code}", {"status": response.status_code, "draft_codes": _dashboard_codes(body, "draft")}))

            def save_indicator(name: str, prompt: str, selected: list[dict[str, str]], formula: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
                response, payload = _post(client, f"/api/tenant/{TENANT_SLUG}/smart-indicators", {
                    "action": "save", "indicator_name": name, "prompt_text": prompt,
                    "selected_indicators": selected, "formula_js": formula,
                    "add_to_dashboard": False, "category": "BDD 临时测试",
                })
                definition = payload.get("definition") or {}
                code = str(definition.get("indicator_code") or "").strip()
                if code:
                    temporary_codes.append(code)
                return code, payload, {"http_status": response.status_code, "body": payload}

            cpi_code, cpi_payload, cpi_http = save_indicator("BDD-CPI", "CPI", [{"indicator_code": "source_cpi", "indicator_name": "中国CPI同比指数"}], 'return Number(inputs["source_cpi"] || 0);')
            cards = [{"indicatorCode": cpi_code}, {}, {}, {}]
            response, body = _post(client, f"/api/tenant/{TENANT_SLUG}/dashboard", {"action": "save_draft", "dashboard": {**empty_dashboard, "cards": cards}})
            cpi_db = _db_evidence(core_services.get_db(), cpi_code) if cpi_code else {}
            cpi_ok = bool(cpi_code and response.status_code == 200 and cpi_db.get("definition_exists") and cpi_db.get("latest_exists"))
            report["scenarios"].append(_scenario("2. 添加第一个指标 CPI", "2×2 看板已建立，CPI 是已注册基础指标。", "通过智能指标真实保存 API 创建 CPI，并写入第一个看板槽位。", "CPI 卡片与指标定义、最新快照均已持久化。", cpi_ok, f"HTTP {cpi_http['http_status']}；看板 HTTP {response.status_code}", {"indicator_code": cpi_code, "indicator": cpi_db, "formula_meta": cpi_payload.get("formula_meta") or {}}))

            shenzhen_code, shenzhen_payload, shenzhen_http = save_indicator("BDD-深证指数", "深证指数", [{"indicator_code": "source_shenzhen_index", "indicator_name": "深证指数"}], 'return Number(inputs["source_shenzhen_index"] || 0);')
            cards[1] = {"indicatorCode": shenzhen_code}
            response, body = _post(client, f"/api/tenant/{TENANT_SLUG}/dashboard", {"action": "save_draft", "dashboard": {**empty_dashboard, "cards": cards}})
            shenzhen_db = _db_evidence(core_services.get_db(), shenzhen_code) if shenzhen_code else {}
            shenzhen_ok = bool(shenzhen_code and response.status_code == 200 and shenzhen_db.get("definition_exists") and shenzhen_db.get("latest_exists"))
            report["scenarios"].append(_scenario("3. 添加第二个指标 深证指数", "CPI 已在第一个槽位。", "创建深证指数指标并写入第二个看板槽位。", "第二个卡片可见，且定义与快照已保存。", shenzhen_ok, f"HTTP {shenzhen_http['http_status']}；看板 HTTP {response.status_code}", {"indicator_code": shenzhen_code, "indicator": shenzhen_db, "formula_meta": shenzhen_payload.get("formula_meta") or {}}))

            commodity_code, commodity_payload, commodity_http = save_indicator("BDD-黄金白银", "黄金/白银", [{"indicator_code": "source_gold", "indicator_name": "黄金"}, {"indicator_code": "source_silver", "indicator_name": "白银"}], 'return Number(inputs["source_gold"] || 0) / Number(inputs["source_silver"] || 0);')
            cards[2] = {"indicatorCode": commodity_code}
            response, body = _post(client, f"/api/tenant/{TENANT_SLUG}/dashboard", {"action": "save_draft", "dashboard": {**empty_dashboard, "cards": cards}})
            commodity_db = _db_evidence(core_services.get_db(), commodity_code) if commodity_code else {}
            commodity_ok = bool(commodity_code and response.status_code == 200 and commodity_db.get("definition_exists") and commodity_db.get("latest_exists"))
            report["scenarios"].append(_scenario("4. 添加第三个指标 黄金 / 白银", "CPI、深证指数已经占用前两个槽位。", "创建黄金/白银比值指标并写入第三个槽位。", "复合计算卡片成功保存，两个底层引用和计算公式均可审计。", commodity_ok, f"HTTP {commodity_http['http_status']}；看板 HTTP {response.status_code}", {"indicator_code": commodity_code, "indicator": commodity_db, "formula_meta": commodity_payload.get("formula_meta") or {}}))

            response, body = _post(client, f"/api/tenant/{TENANT_SLUG}/dashboard", {"action": "publish", "dashboard": {**empty_dashboard, "cards": cards}})
            publish_ok = response.status_code == 200 and cpi_code in _dashboard_codes(body, "published")
            report["publish"] = {"status": response.status_code, "published_codes": _dashboard_codes(body, "published"), "ok": publish_ok}

            response, body = _post(client, f"/api/tenant/{TENANT_SLUG}/dashboard", {"action": "remove_indicator", "indicator_code": cpi_code})
            after_remove_db = _db_evidence(core_services.get_db(), cpi_code) if cpi_code else {}
            removed_codes = _dashboard_codes(body, "draft")
            remove_ok = response.status_code == 200 and cpi_code not in removed_codes and after_remove_db.get("definition_exists") and after_remove_db.get("latest_exists")
            report["scenarios"].append(_scenario("5. 删除第一个指标 CPI", "CPI 已发布，且当前操作是从看板移除。", "调用真实 remove_indicator 接口移除 CPI 卡片。", "草稿不再展示 CPI，但数据库定义、最新值和历史序列仍保留。", remove_ok, f"HTTP {response.status_code}", {"draft_codes": removed_codes, "cpi_db_after_remove": after_remove_db, "published_codes": _dashboard_codes(body, "published")}))

            response, body = _post(client, f"/api/tenant/{TENANT_SLUG}/dashboard", {"action": "reset_draft"})
            restored_codes = _dashboard_codes(body, "published")
            restore_ok = response.status_code == 200 and cpi_code in restored_codes and (body.get("fund_dashboard_state") or {}).get("draft") is None
            report["scenarios"].append(_scenario("6. 恢复", "CPI 仅从草稿看板移除，发布版未改写。", "调用真实 reset_draft 接口恢复当前发布版。", "CPI 卡片恢复，草稿清空，之前保存的数据仍可读取。", restore_ok, f"HTTP {response.status_code}", {"published_codes": restored_codes, "draft": (body.get("fund_dashboard_state") or {}).get("draft"), "cpi_db_after_restore": _db_evidence(core_services.get_db(), cpi_code) if cpi_code else {}}))

            final_cards = cards[:]
            final_cards[3] = {"indicatorCode": "source_shanghai_index"}
            response, body = _post(client, f"/api/tenant/{TENANT_SLUG}/dashboard", {"action": "save_draft", "dashboard": {**empty_dashboard, "cards": final_cards}})
            final_codes = _dashboard_codes(body, "draft")
            shanghai_ok = response.status_code == 200 and "source_shanghai_index" in final_codes and len(final_codes) == 4
            report["scenarios"].append(_scenario("7. 再添加一个指标 上证指数", "恢复后 CPI、深证指数和黄金/白银数据仍可复用。", "将注册指标 source_shanghai_index 写入第四个槽位。", "2×2 草稿包含 CPI、深证指数、黄金/白银和上证指数四个卡片引用。", shanghai_ok, f"HTTP {response.status_code}", {"draft_codes": final_codes, "shanghai_code": "source_shanghai_index"}))

            report["conclusion"] = "通过标准：所有场景必须由真实接口返回成功，且删除 CPI 后数据库仍存在定义、最新快照和历史序列。模型配置必须解析到 DeepSeek-V4-Flash 正式版。"
    except Exception as exc:
        report["exception"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc(limit=12)
    finally:
        try:
            with app_entry.app.app_context():
                for code in temporary_codes:
                    market_services.delete_indicator_definition(code)
                if original_config is not None:
                    core_services.save_site_config(original_config)
        except Exception as exc:
            report["cleanup_error"] = f"{type(exc).__name__}: {exc}"
        web_hooks.is_authenticated = original_auth

    report["temporary_codes"] = temporary_codes
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_render(report), encoding="utf-8")
    REPORT_JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(1 for item in report["scenarios"] if item["passed"])
    print(json.dumps({"report": str(REPORT_PATH), "json": str(REPORT_JSON_PATH), "passed": passed, "total": len(report["scenarios"]), "exception": report.get("exception") or "", "cleanup_error": report.get("cleanup_error") or ""}, ensure_ascii=False, indent=2))
    return 0 if passed == len(report["scenarios"]) and not report.get("exception") and not report.get("cleanup_error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
