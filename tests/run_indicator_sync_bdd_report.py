from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app as app_entry
import src.web.hooks as web_hooks
from src.domain.market_services import (
    GANGTISE_INDICATOR_REGISTRY,
    build_indicator_hub_from_store,
    ensure_default_indicator_sources,
    list_indicator_source_defs,
    obtain_gangtise_openapi_token,
    sync_derived_smart_indicator_history,
    sync_real_indicator_history_from_market_cache,
    test_indicator_source,
)
from src.domain.core_services import get_db
from src.services import get_tenant_configs


DEFAULT_ENV_PATH = PROJECT_ROOT.parent / "gangtise_api_test" / ".env"
REPORT_DIR = PROJECT_ROOT / "tests" / "reports"
REPORT_HTML_PATH = REPORT_DIR / "indicator_sync_bdd_report.html"
REPORT_JSON_PATH = REPORT_DIR / "indicator_sync_bdd_report.json"


def load_env_file(path: Path) -> dict[str, str]:
    loaded = {}
    if not path.exists():
        return loaded
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = str(raw_line or "").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        os.environ.setdefault(key, value)
        loaded[key] = value
    return loaded


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


def db_scalar(db, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = db.execute(sql, params).fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()))
    try:
        return row[0]
    except Exception:
        return None


def build_indicator_matrix(db) -> list[dict[str, Any]]:
    source_map = {item["indicator_code"]: item for item in list_indicator_source_defs()}
    rows = []
    for indicator_code, entry in sorted(GANGTISE_INDICATOR_REGISTRY.items()):
        latest = db.execute(
            "SELECT * FROM indicator_latest_values WHERE indicator_code = ?",
            (indicator_code,),
        ).fetchone()
        latest = dict(latest) if latest else {}
        real_series_count = db_scalar(
            db,
            "SELECT COUNT(*) FROM indicator_series WHERE indicator_code = ? AND is_simulated = 0",
            (indicator_code,),
        ) or 0
        real_kline_count = db_scalar(
            db,
            "SELECT COUNT(*) FROM indicator_kline_points WHERE indicator_code = ? AND is_simulated = 0",
            (indicator_code,),
        ) or 0
        anomaly_count = db_scalar(
            db,
            "SELECT COUNT(*) FROM indicator_anomalies WHERE indicator_code = ? AND is_simulated = 0",
            (indicator_code,),
        ) or 0
        source = source_map.get(indicator_code) or {}
        rows.append(
            {
                "indicator_code": indicator_code,
                "indicator_name": entry.get("indicator_name") or indicator_code,
                "query_kind": entry.get("query_kind") or "",
                "provider": source.get("provider") or "",
                "source_path": source.get("path") or "",
                "auth_type": source.get("auth_type") or "",
                "latest_value": latest.get("latest_value") or "",
                "latest_status": latest.get("latest_status") or "",
                "updated_at": latest.get("updated_at") or "",
                "is_simulated": bool(latest.get("is_simulated")) if latest else None,
                "real_series_count": int(real_series_count),
                "real_kline_count": int(real_kline_count),
                "anomaly_count": int(anomaly_count),
            }
        )
    return rows


def build_derived_matrix(db) -> list[dict[str, Any]]:
    rows = []
    for indicator_code in ("fed_rate_path", "southbound_flow", "credit_pulse", "ai_order_signal"):
        latest = db.execute(
            "SELECT * FROM indicator_latest_values WHERE indicator_code = ?",
            (indicator_code,),
        ).fetchone()
        latest = dict(latest) if latest else {}
        real_series_count = db_scalar(
            db,
            "SELECT COUNT(*) FROM indicator_series WHERE indicator_code = ? AND is_simulated = 0",
            (indicator_code,),
        ) or 0
        rows.append(
            {
                "indicator_code": indicator_code,
                "latest_value": latest.get("latest_value") or "",
                "latest_status": latest.get("latest_status") or "",
                "updated_at": latest.get("updated_at") or "",
                "is_simulated": bool(latest.get("is_simulated")) if latest else None,
                "real_series_count": int(real_series_count),
                "source_code": latest.get("source_code") or "",
            }
        )
    return rows


def run_api_checks(client, tenant_slug: str) -> list[dict[str, Any]]:
    checks = []
    api_cases = [
        ("H5 页面", "GET", f"/h5?tenant={tenant_slug}"),
        ("工作台接口", "GET", f"/api/kol/workbench?tenant={tenant_slug}"),
        ("租户 Dashboard 接口", "GET", f"/api/tenant/{tenant_slug}/dashboard"),
        ("智能指标接口", "GET", f"/api/tenant/{tenant_slug}/smart-indicators"),
    ]
    for title, method, path in api_cases:
        if method == "GET":
            response = client.get(path)
        else:
            response = client.open(path, method=method)
        payload = None
        text = response.get_data(as_text=True)
        if "application/json" in (response.content_type or ""):
            try:
                payload = response.get_json()
            except Exception:
                payload = None
        checks.append(
            {
                "title": title,
                "path": path,
                "status_code": response.status_code,
                "content_type": response.content_type,
                "ok": response.status_code == 200,
                "payload_preview": payload if isinstance(payload, dict) else text[:500],
            }
        )
    return checks


def render_json_preview(value: Any) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        text = repr(value)
    return escape(text[:12000])


def render_html_report(report: dict[str, Any]) -> str:
    scenarios = report["scenarios"]
    indicators = report["indicator_matrix"]
    derived = report["derived_matrix"]
    source_probes = report["source_probes"]
    api_checks = report["api_checks"]
    passed = sum(1 for item in scenarios if item["passed"])
    failed = len(scenarios) - passed
    indicator_rows = "".join(
        f"""
        <tr>
          <td>{escape(item['indicator_code'])}</td>
          <td>{escape(item['indicator_name'])}</td>
          <td>{escape(item['query_kind'])}</td>
          <td>{escape(item['provider'])}</td>
          <td><code>{escape(item['source_path'])}</code></td>
          <td>{escape(item['latest_value'])}</td>
          <td>{escape(item['latest_status'])}</td>
          <td>{'否' if item['is_simulated'] is False else ('是' if item['is_simulated'] is True else '--')}</td>
          <td>{item['real_series_count']}</td>
          <td>{item['real_kline_count']}</td>
          <td>{item['anomaly_count']}</td>
          <td>{escape(item['updated_at'])}</td>
        </tr>
        """
        for item in indicators
    )
    derived_rows = "".join(
        f"""
        <tr>
          <td>{escape(item['indicator_code'])}</td>
          <td>{escape(item['latest_value'])}</td>
          <td>{escape(item['latest_status'])}</td>
          <td>{'否' if item['is_simulated'] is False else ('是' if item['is_simulated'] is True else '--')}</td>
          <td>{item['real_series_count']}</td>
          <td>{escape(item['source_code'])}</td>
          <td>{escape(item['updated_at'])}</td>
        </tr>
        """
        for item in derived
    )
    probe_rows = "".join(
        f"""
        <tr>
          <td>{escape(item['indicator_code'])}</td>
          <td>{'通过' if item['success'] else '失败'}</td>
          <td>{escape(str(item['http_status'] or '--'))}</td>
          <td>{escape(str(item['latency_ms']))} ms</td>
          <td>{escape(item['detail'])}</td>
        </tr>
        """
        for item in source_probes
    )
    api_rows = "".join(
        f"""
        <tr>
          <td>{escape(item['title'])}</td>
          <td><code>{escape(item['path'])}</code></td>
          <td>{item['status_code']}</td>
          <td>{'通过' if item['ok'] else '失败'}</td>
          <td>{escape(item['content_type'])}</td>
        </tr>
        """
        for item in api_checks
    )
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
  <title>指标同步 BDD 测试报告</title>
  <style>
    :root {{
      --bg: #f4efe7;
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
    body {{ margin: 0; background: linear-gradient(180deg, #f7f3ec 0%, #eef4fb 100%); color: var(--ink); font: 14px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; }}
    main {{ max-width: 1360px; margin: 0 auto; padding: 28px 20px 56px; }}
    .hero {{ background: var(--panel); border: 1px solid var(--line); border-radius: 24px; padding: 24px 26px; box-shadow: 0 14px 48px rgba(22,34,48,0.08); }}
    h1 {{ margin: 0 0 8px; font-size: 34px; line-height: 1.05; }}
    .sub {{ color: var(--muted); margin: 0; }}
    .metrics {{ display: grid; grid-template-columns: repeat(6, minmax(0,1fr)); gap: 12px; margin-top: 18px; }}
    .metric {{ background: #fff; border: 1px solid var(--line); border-radius: 18px; padding: 14px 16px; }}
    .metric .name {{ color: var(--muted); font-size: 12px; }}
    .metric .value {{ font-size: 28px; font-weight: 800; margin-top: 6px; }}
    .section {{ margin-top: 20px; background: var(--panel); border: 1px solid var(--line); border-radius: 24px; padding: 20px; box-shadow: 0 10px 36px rgba(22,34,48,0.06); }}
    .section h2 {{ margin: 0 0 14px; font-size: 22px; }}
    .scenario-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
    .scenario {{ border: 1px solid var(--line); border-left: 5px solid var(--blue); border-radius: 18px; background: #fff; padding: 16px; }}
    .scenario.pass {{ border-left-color: var(--green); }}
    .scenario.fail {{ border-left-color: var(--red); }}
    .scenario-head {{ display: flex; justify-content: space-between; gap: 10px; align-items: start; }}
    .scenario-head h3 {{ margin: 0; font-size: 18px; }}
    .pill {{ display: inline-flex; align-items: center; justify-content: center; min-width: 58px; padding: 5px 10px; border-radius: 999px; background: rgba(47,116,192,0.10); color: var(--blue); font-size: 12px; font-weight: 700; }}
    .scenario.pass .pill {{ background: rgba(38,115,77,0.12); color: var(--green); }}
    .scenario.fail .pill {{ background: rgba(177,68,50,0.12); color: var(--red); }}
    .bdd-line {{ margin-top: 8px; }}
    .detail {{ margin: 10px 0 0; color: var(--muted); }}
    details {{ margin-top: 10px; }}
    summary {{ cursor: pointer; color: var(--blue); font-weight: 700; }}
    pre {{ margin: 10px 0 0; padding: 12px; border-radius: 12px; background: #13202d; color: #ecf3fb; overflow: auto; white-space: pre-wrap; word-break: break-word; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid var(--line); border-radius: 16px; overflow: hidden; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #ece4d8; text-align: left; vertical-align: top; }}
    th {{ background: #f6efe3; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }}
    code {{ font-size: 12px; }}
    .meta-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
    @media (max-width: 980px) {{
      .metrics, .scenario-grid, .meta-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>Gangtise 指标同步 BDD 测试报告</h1>
      <p class="sub">生成时间：{escape(report['generated_at'])} · 租户：{escape(report['tenant_slug'])} · 真实同步 + 本地 DB 校验 + 前台 API 校验</p>
      <div class="metrics">
        <div class="metric"><div class="name">Scenario</div><div class="value">{len(scenarios)}</div></div>
        <div class="metric"><div class="name">Pass</div><div class="value">{passed}</div></div>
        <div class="metric"><div class="name">Fail</div><div class="value">{failed}</div></div>
        <div class="metric"><div class="name">基础指标</div><div class="value">{len(indicators)}</div></div>
        <div class="metric"><div class="name">真实更新</div><div class="value">{report['real_sync'].get('updated', 0)}</div></div>
        <div class="metric"><div class="name">派生更新</div><div class="value">{report['derived_sync'].get('updated', 0)}</div></div>
      </div>
    </section>

    <section class="section">
      <h2>BDD 场景</h2>
      <div class="scenario-grid">{scenario_cards}</div>
    </section>

    <section class="section">
      <h2>执行摘要</h2>
      <div class="meta-grid">
        <div>
          <h3>认证结果</h3>
          <pre>{render_json_preview(report['auth'])}</pre>
        </div>
        <div>
          <h3>同步结果</h3>
          <pre>{render_json_preview({'real_sync': report['real_sync'], 'derived_sync': report['derived_sync'], 'hub_summary': report['hub_summary']})}</pre>
        </div>
      </div>
    </section>

    <section class="section">
      <h2>基础指标覆盖</h2>
      <table>
        <thead>
          <tr>
            <th>指标 Code</th>
            <th>指标名</th>
            <th>类型</th>
            <th>Provider</th>
            <th>Path</th>
            <th>最新值</th>
            <th>状态</th>
            <th>模拟</th>
            <th>真实序列</th>
            <th>K线点数</th>
            <th>异动数</th>
            <th>更新时间</th>
          </tr>
        </thead>
        <tbody>{indicator_rows}</tbody>
      </table>
    </section>

    <section class="section">
      <h2>派生智能指标覆盖</h2>
      <table>
        <thead>
          <tr>
            <th>指标 Code</th>
            <th>最新值</th>
            <th>状态</th>
            <th>模拟</th>
            <th>真实序列</th>
            <th>来源</th>
            <th>更新时间</th>
          </tr>
        </thead>
        <tbody>{derived_rows}</tbody>
      </table>
    </section>

    <section class="section">
      <h2>实时 Source Probe</h2>
      <table>
        <thead>
          <tr>
            <th>指标 Code</th>
            <th>结果</th>
            <th>HTTP</th>
            <th>耗时</th>
            <th>详情</th>
          </tr>
        </thead>
        <tbody>{probe_rows}</tbody>
      </table>
    </section>

    <section class="section">
      <h2>前台 API 验证</h2>
      <table>
        <thead>
          <tr>
            <th>检查项</th>
            <th>路径</th>
            <th>状态码</th>
            <th>结果</th>
            <th>Content-Type</th>
          </tr>
        </thead>
        <tbody>{api_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    env_path = Path(os.getenv("GANGTISE_SOURCE_ENV_PATH", str(DEFAULT_ENV_PATH)))
    loaded_env = load_env_file(env_path)
    original_is_authenticated = web_hooks.is_authenticated
    web_hooks.is_authenticated = lambda: True
    tenant_slug = pick_tenant_slug()
    report: dict[str, Any] = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tenant_slug": tenant_slug,
        "env_path": str(env_path),
        "loaded_env_keys": sorted(loaded_env.keys()),
        "scenarios": [],
        "indicator_matrix": [],
        "derived_matrix": [],
        "source_probes": [],
        "api_checks": [],
        "auth": {},
        "real_sync": {},
        "derived_sync": {},
        "hub_summary": {},
        "exception": "",
    }
    try:
        app_entry.app.config.update(TESTING=True)
        client = app_entry.app.test_client()
        with app_entry.app.app_context():
            ensure_default_indicator_sources()
            token_ok, token, token_response, token_status, token_duration = obtain_gangtise_openapi_token(force_refresh=True)
            report["auth"] = {
                "ok": bool(token_ok),
                "http_status": token_status,
                "duration_ms": token_duration,
                "message": token_response.get("msg") or token_response.get("message") or token_response.get("source") or "",
            }
            report["scenarios"].append(
                scenario_result(
                    name="Given 凭证配置 When 请求 Gangtise 鉴权 Then 返回可用 token",
                    given="本地存在可复用的 Gangtise OpenAPI 凭证配置。",
                    when="执行一次真实鉴权并请求 access token。",
                    then="系统能够拿到可用 token，后续同步可继续执行。",
                    passed=bool(token_ok),
                    detail=report["auth"]["message"] or ("Gangtise token 已获取" if token_ok else "Gangtise token 获取失败"),
                    evidence=report["auth"],
                )
            )

            source_defs = [item for item in list_indicator_source_defs() if item.get("indicator_code") in GANGTISE_INDICATOR_REGISTRY]
            source_alignment_ok = len(source_defs) == len(GANGTISE_INDICATOR_REGISTRY) and all(
                item.get("provider") == "Gangtise OpenAPI"
                and item.get("auth_type") == "gangtise_openapi"
                and item.get("method") == "POST"
                for item in source_defs
            )
            report["scenarios"].append(
                scenario_result(
                    name="Given 指标源定义 When 检查 source defs Then 全部切到 Gangtise OpenAPI",
                    given="基础指标 source 定义已经迁移到统一指标层。",
                    when="读取数据库中的 indicator_source_defs。",
                    then="所有基础指标 source 都应是 Gangtise OpenAPI 的 POST 配置。",
                    passed=source_alignment_ok,
                    detail=f"共校验 {len(source_defs)} / {len(GANGTISE_INDICATOR_REGISTRY)} 个 source 定义。",
                    evidence=[
                        {
                            "indicator_code": item.get("indicator_code"),
                            "provider": item.get("provider"),
                            "path": item.get("path"),
                            "auth_type": item.get("auth_type"),
                        }
                        for item in source_defs
                    ],
                )
            )

            source_probes = []
            for indicator_code in sorted(GANGTISE_INDICATOR_REGISTRY):
                probe = test_indicator_source(indicator_code)
                source_probes.append(
                    {
                        "indicator_code": indicator_code,
                        "success": bool(probe.get("success")),
                        "http_status": probe.get("http_status"),
                        "latency_ms": int(probe.get("latency_ms") or 0),
                        "detail": str(probe.get("detail") or "").strip(),
                    }
                )
            report["source_probes"] = source_probes
            probe_passed = all(item["success"] for item in source_probes)
            report["scenarios"].append(
                scenario_result(
                    name="Given 每个基础指标源 When 逐一执行实时探测 Then 每个 source 都应可取到真实数据",
                    given="每个基础指标都已经映射到真实 Gangtise OpenAPI 路径。",
                    when="逐一执行 source probe。",
                    then="所有 source 都应返回成功，不能只靠样例或 mock。",
                    passed=probe_passed,
                    detail=f"通过 {sum(1 for item in source_probes if item['success'])} / {len(source_probes)} 个 source probe。",
                    evidence=source_probes,
                )
            )

            report["real_sync"] = sync_real_indicator_history_from_market_cache(force=True)
            report["derived_sync"] = sync_derived_smart_indicator_history(force=True)
            db = get_db()
            report["indicator_matrix"] = build_indicator_matrix(db)
            report["derived_matrix"] = build_derived_matrix(db)
            hub = build_indicator_hub_from_store()
            report["hub_summary"] = hub.get("summary") if isinstance(hub, dict) else {}

            non_simulated_rows = [item for item in report["indicator_matrix"] if item["is_simulated"] is False and item["real_series_count"] >= 2]
            sync_passed = len(non_simulated_rows) == len(report["indicator_matrix"])
            report["scenarios"].append(
                scenario_result(
                    name="Given 真实同步任务 When 全量强制同步 Then 每个基础指标都应落成真实 latest 与序列",
                    given="基础指标已经完成 source 切换且可访问真实 OpenAPI。",
                    when="执行一次强制全量同步。",
                    then="每个基础指标都应写入非模拟 latest value 与至少 2 个真实序列点。",
                    passed=sync_passed,
                    detail=f"真实落库 {len(non_simulated_rows)} / {len(report['indicator_matrix'])} 个基础指标。",
                    evidence={
                        "real_sync": report["real_sync"],
                        "missing": [
                            item for item in report["indicator_matrix"]
                            if not (item["is_simulated"] is False and item["real_series_count"] >= 2)
                        ],
                    },
                )
            )

            index_rows = [item for item in report["indicator_matrix"] if item["query_kind"] == "index_kline"]
            kline_passed = all(item["real_kline_count"] >= 2 for item in index_rows)
            report["scenarios"].append(
                scenario_result(
                    name="Given 指数型指标 When 同步完成 Then 每个指数指标都应落 K 线点位",
                    given="指数型指标应走 index kline 接口。",
                    when="同步完成后检查 indicator_kline_points。",
                    then="每个指数型指标都应有真实 K 线点位，供前台图表直接消费。",
                    passed=kline_passed,
                    detail=f"指数型指标 K 线覆盖 {sum(1 for item in index_rows if item['real_kline_count'] >= 2)} / {len(index_rows)}。",
                    evidence=index_rows,
                )
            )

            derived_ready = [item for item in report["derived_matrix"] if item["is_simulated"] is False and item["real_series_count"] >= 2]
            derived_passed = len(derived_ready) == len(report["derived_matrix"])
            report["scenarios"].append(
                scenario_result(
                    name="Given 底层真实因子 When 派生智能指标重算 Then 四个核心派生指标都应完成刷新",
                    given="派生智能指标依赖的底层基础指标已具备真实序列。",
                    when="执行派生指标重算。",
                    then="四个核心派生指标都应生成非模拟序列并刷新 latest。",
                    passed=derived_passed,
                    detail=f"派生指标刷新 {len(derived_ready)} / {len(report['derived_matrix'])}。",
                    evidence={"derived_sync": report["derived_sync"], "derived_matrix": report["derived_matrix"]},
                )
            )

            report["api_checks"] = run_api_checks(client, tenant_slug)
            api_passed = all(item["ok"] for item in report["api_checks"])
            report["scenarios"].append(
                scenario_result(
                    name="Given 前台消费接口 When 读取 H5 与工作台相关接口 Then 指标数据链路应保持可用",
                    given="同步后的指标数据需要继续被前台和工作台消费。",
                    when="调用 H5 页面、工作台接口、租户 Dashboard 接口和智能指标接口。",
                    then="这些入口都应返回 200，证明迁移没有打断消费链路。",
                    passed=api_passed,
                    detail=f"通过 {sum(1 for item in report['api_checks'] if item['ok'])} / {len(report['api_checks'])} 个接口检查。",
                    evidence=report["api_checks"],
                )
            )
    except Exception as exc:
        report["exception"] = f"{exc}\n{traceback.format_exc()}"
        report["scenarios"].append(
            scenario_result(
                name="Given 报告执行 When 运行同步与测试 Then 不应抛出未处理异常",
                given="报告脚本需要完整执行同步和测试。",
                when="运行整个 BDD 报告流程。",
                then="脚本不应中途抛出未处理异常。",
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
