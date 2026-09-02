"""Real-data BDD coverage for H5 DAv smart-indicator formulas.

This module intentionally has no provider mocks, synthetic prices, fallback
values, save operations, or dashboard mutations.  It calls the same preview
workflow behind the H5 DAv workbench endpoint using the active PostgreSQL
market snapshots.  Set ``LIVE_SMART_INDICATOR_BDD=1`` to run it explicitly.
"""

from __future__ import annotations

import math
import os
from datetime import datetime
from typing import Any

import app as app_entry
from src.domain import core_services


TENANT_SLUG = "laowang"
DAV_USERNAME = "财经老王"
LIVE_FLAG = "LIVE_SMART_INDICATOR_BDD"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _tag_label(tag: dict[str, Any]) -> str:
    return str(tag.get("label") or "").strip()


def _references_available(tag: dict[str, Any]) -> bool:
    refs = tag.get("selected_indicators") if isinstance(tag.get("selected_indicators"), list) else []
    if not refs:
        return False
    # Stock quotes are loaded only when explicitly selected.  This mirrors the
    # preview workflow and prevents the catalogue scan from manufacturing an
    # all-stocks snapshot map.
    latest_map = core_services.build_smart_indicator_latest_value_map(refs)
    for ref in refs:
        code = str((ref or {}).get("indicator_code") or "").strip()
        source = latest_map.get(code) or {}
        if core_services._market_services_module().parse_numeric_indicator_value(source.get("latest_value")) is None:
            return False
    return True


def _find_tag(tags: list[dict[str, Any]], *, category: str = "", codes: tuple[str, ...] = ()) -> dict[str, Any] | None:
    for tag in tags:
        if category and str(tag.get("category") or "") != category:
            continue
        refs = tag.get("selected_indicators") if isinstance(tag.get("selected_indicators"), list) else []
        ref_codes = {str((ref or {}).get("indicator_code") or "").strip() for ref in refs}
        if codes and not set(codes).issubset(ref_codes):
            continue
        if _tag_label(tag):
            return tag
    return None


def _formula_payload(name: str, parts: list[dict[str, Any] | str]) -> dict[str, Any]:
    prompt_parts: list[str] = []
    tokens: list[dict[str, Any]] = []
    selected_tags: list[str] = []
    for part in parts:
        if isinstance(part, str):
            prompt_parts.append(part)
            token_type = "number" if part.replace(".", "", 1).isdigit() else "operator"
            tokens.append({"type": token_type, "text": part})
            continue
        label = _tag_label(part)
        tag_code = str(part.get("tag_code") or "").strip()
        refs = part.get("selected_indicators") if isinstance(part.get("selected_indicators"), list) else []
        prompt_parts.append(f"【{label}】")
        tokens.append(
            {
                "type": "reference",
                "text": f"【{label}】",
                "label": label,
                "tagCode": tag_code,
                "indicatorCode": str((refs[0] or {}).get("indicator_code") or "") if len(refs) == 1 else "",
            }
        )
        selected_tags.append(tag_code)
    return {
        "action": "preview",
        "indicator_name": name,
        "prompt_text": "".join(prompt_parts),
        "selected_tag_codes": selected_tags,
        "formula_tokens": tokens,
    }


def _snapshot_evidence(db) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT snapshot_type, snapshot_key, source, collected_at, updated_at
        FROM market_snapshot_payloads
        WHERE snapshot_type IN ('market_overview', 'market_sector_overview', 'macro_economic')
        ORDER BY updated_at DESC
        """
    ).fetchall()
    return [_json_safe(dict(row)) for row in rows]


def _resolve_live_cases() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tenant = core_services.get_tenant_by_slug(TENANT_SLUG)
    if not tenant:
        raise RuntimeError("live_tenant_not_found:laowang")
    tags = core_services.build_tenant_smart_indicator_tag_catalog(tenant)
    available_tags = [tag for tag in tags if _references_available(tag)]

    cpi = _find_tag(available_tags, codes=("source_cpi",))
    ppi = _find_tag(available_tags, codes=("source_ppi",))
    shanghai = _find_tag(available_tags, codes=("source_shanghai_index",))
    shenzhen = _find_tag(available_tags, codes=("source_shenzhen_index",))
    hs300 = _find_tag(available_tags, codes=("source_hs300",))
    industries = [tag for tag in available_tags if str(tag.get("tag_type") or "") == "industry"]
    stocks = [tag for tag in available_tags if str(tag.get("tag_type") or "") == "watchlist"]

    required = {
        "macro_cpi": cpi,
        "macro_ppi": ppi,
        "market_shanghai": shanghai,
        "market_shenzhen": shenzhen,
        "market_hs300": hs300,
        "industry_a": industries[0] if industries else None,
        "industry_b": industries[1] if len(industries) > 1 else None,
        "stock": stocks[0] if stocks else None,
    }
    missing = [name for name, tag in required.items() if tag is None]
    if missing:
        raise RuntimeError(f"live_data_unavailable:required_tags={','.join(missing)}")

    cases = [
        {
            "id": "macro-two-add",
            "category": "宏观 + 宏观",
            "name": "中国 CPI 与 PPI 相加",
            "payload": _formula_payload("BDD 宏观双指标", [cpi, "+", ppi]),
        },
        {
            "id": "macro-three-multiply-add",
            "category": "宏观 + 宏观 + 数值",
            "name": "中国 PPI 乘以 5 再加 CPI",
            "payload": _formula_payload("BDD 宏观三操作数", [ppi, "*", "5", "+", cpi]),
        },
        {
            "id": "market-two-subtract",
            "category": "市场 + 市场",
            "name": "上证指数减深证指数",
            "payload": _formula_payload("BDD 市场双指标", [shanghai, "-", shenzhen]),
        },
        {
            "id": "market-three-parentheses",
            "category": "市场 + 市场 + 市场",
            "name": "上证加深证后除以沪深300",
            "payload": _formula_payload("BDD 市场三指标", ["(", shanghai, "+", shenzhen, ")", "/", hs300]),
        },
        {
            "id": "industry-two-add",
            "category": "行业 + 行业",
            "name": f"{_tag_label(industries[0])} 与 {_tag_label(industries[1])}相加",
            "payload": _formula_payload("BDD 行业双指标", [industries[0], "+", industries[1]]),
        },
        {
            "id": "cross-market-macro",
            "category": "市场 + 宏观",
            "name": "上证指数与中国 CPI 相加",
            "payload": _formula_payload("BDD 市场宏观组合", [shanghai, "+", cpi]),
        },
        {
            "id": "cross-industry-market",
            "category": "行业 + 市场",
            "name": f"{_tag_label(industries[0])} 与上证指数相加",
            "payload": _formula_payload("BDD 行业市场组合", [industries[0], "+", shanghai]),
        },
        {
            "id": "cross-stock-macro",
            "category": "个股 + 宏观",
            "name": f"{_tag_label(stocks[0])} 与中国 CPI 相加",
            "payload": _formula_payload("BDD 个股宏观组合", [stocks[0], "+", cpi]),
        },
        {
            "id": "cross-stock-market-industry",
            "category": "个股 + 市场 + 行业",
            "name": f"{_tag_label(stocks[0])}、上证指数与 {_tag_label(industries[0])}相加",
            "payload": _formula_payload("BDD 个股市场行业组合", [stocks[0], "+", shanghai, "+", industries[0]]),
        },
    ]
    return cases, {
        "tag_catalog_total": len(tags),
        "available_tag_total": len(available_tags),
        "required_tags": {
            name: {
                "tag_code": tag.get("tag_code"),
                "label": _tag_label(tag),
                "tag_type": tag.get("tag_type"),
                "category": tag.get("category"),
                "selected_indicators": tag.get("selected_indicators"),
            }
            for name, tag in required.items()
        },
    }


def run_live_smart_indicator_formula_bdd() -> dict[str, Any]:
    """Execute the actual preview endpoint with a real DAv session and data."""
    if os.environ.get(LIVE_FLAG) != "1":
        raise RuntimeError(f"{LIVE_FLAG}=1 is required; live BDD is never run implicitly")

    report: dict[str, Any] = {
        "title": "H5 大V工作台智能指标公式真实数据 BDD 报告",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "execution_mode": "真实 PostgreSQL 当前快照 + 真实 H5 大V smart-indicators preview API；不使用 mock、模拟值、保存或看板写入。",
        "tenant_slug": TENANT_SLUG,
        "dav_username": DAV_USERNAME,
        "scenarios": [],
    }
    app_entry.app.config.update(TESTING=True)
    client = app_entry.app.test_client()
    with client.session_transaction() as session:
        session[core_services.H5_USER_SESSION_KEY] = DAV_USERNAME
    with app_entry.app.app_context():
        db = core_services.get_db()
        report["snapshots"] = _snapshot_evidence(db)
        cases, catalog_evidence = _resolve_live_cases()
        report["catalog"] = catalog_evidence

    for case in cases:
        response = client.post(f"/api/tenant/{TENANT_SLUG}/smart-indicators", json=case["payload"])
        body = response.get_json(silent=True) or {}
        preview = body.get("preview") if isinstance(body.get("preview"), dict) else {}
        formula_meta = preview.get("formula_meta") if isinstance(preview.get("formula_meta"), dict) else {}
        numeric_value = preview.get("numeric_value")
        is_finite = isinstance(numeric_value, (int, float)) and math.isfinite(float(numeric_value))
        selected = preview.get("selected_indicators") if isinstance(preview.get("selected_indicators"), list) else []
        with app_entry.app.app_context():
            latest_values = core_services.build_smart_indicator_latest_value_map(selected)
        source_snapshots = [
            {
                "indicator_code": item.get("indicator_code"),
                "indicator_name": item.get("indicator_name"),
                "latest_value": (latest_values.get(item.get("indicator_code")) or {}).get("latest_value"),
                "updated_at": (latest_values.get(item.get("indicator_code")) or {}).get("updated_at"),
                "source_code": (latest_values.get(item.get("indicator_code")) or {}).get("source_code"),
                "is_simulated": (latest_values.get(item.get("indicator_code")) or {}).get("is_simulated"),
            }
            for item in selected
        ]
        sources_are_real = bool(source_snapshots) and all(
            snapshot.get("latest_value") not in (None, "") and snapshot.get("is_simulated") in (False, 0)
            for snapshot in source_snapshots
        )
        passed = (
            response.status_code == 200
            and body.get("success") is True
            and preview.get("data_status") == "available"
            and is_finite
            and bool(selected)
            and sources_are_real
            and not preview.get("unavailable_indicators")
            and formula_meta.get("generator") == "arithmetic_expression"
            and formula_meta.get("llm_used") is False
        )
        report["scenarios"].append(
            {
                "id": case["id"],
                "category": case["category"],
                "name": case["name"],
                "given": "当前 PostgreSQL 已存在可用的注册指标快照。",
                "when": f"H5 大V以结构化标签 token 提交：{case['payload']['prompt_text']}",
                "then": "预览接口必须用真实快照完成确定性计算，且不返回不可用或回退值。",
                "passed": passed,
                "detail": (
                    f"HTTP {response.status_code}；data_status={preview.get('data_status') or '--'}；"
                    f"value={preview.get('value') or '--'}；generator={formula_meta.get('generator') or '--'}；"
                    f"llm_used={formula_meta.get('llm_used')}"
                ),
                "evidence": _json_safe(
                    {
                        "request": case["payload"],
                        "response_success": body.get("success"),
                        "response_error": body.get("error"),
                        "preview": {
                            "value": preview.get("value"),
                            "numeric_value": numeric_value,
                            "data_status": preview.get("data_status"),
                            "updated_at": preview.get("updated_at"),
                            "resolved_indicator_codes": preview.get("resolved_indicator_codes"),
                            "selected_indicators": selected,
                            "unavailable_indicators": preview.get("unavailable_indicators"),
                            "formula_js": preview.get("formula_js"),
                            "formula_meta": formula_meta,
                            "source_snapshots": source_snapshots,
                        },
                    }
                ),
            }
        )
    report["passed_count"] = sum(1 for item in report["scenarios"] if item["passed"])
    report["failed_count"] = len(report["scenarios"]) - report["passed_count"]
    return report
