import os
import json
import sqlite3
import copy
import math
import statistics
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, g, abort
import random
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from hmac import compare_digest

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("GANGTISE_DEMO_SECRET_KEY", os.urandom(32)),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

AUTH_PASSWORD = os.environ.get("GANGTISE_DEMO_PASSWORD", "gangtise")
AUTH_SESSION_KEY = "gangtise_auth"
DB_PATH = os.environ.get("GANGTISE_DEMO_DB", os.path.join(os.path.dirname(__file__), "gangtise_demo.db"))
SITE_CONFIG_KEY = "site_config"
FORECAST_WORKFLOW_KEY = "forecast_workflow_graph"

DEFAULT_BRAND_CONFIG = {
    "name": "洞见智研",
    "short_name": "洞见智研",
    "logo_mark": "洞",
    "logo_url": "",
    "tagline": "智能投研平台",
    "hero_tagline": "聚焦复盘、基本面分析、自选股诊断与证据链输出的智能投研能力",
    "hero_description": "当前定位不是泛金融 SaaS，而是面向研究场景的第三方智能投研工具与服务层。面向普通投资者、大V投顾租户和平台 Admin 提供多角色隔离、按需基本面、工作台协同与合规表达能力。",
    "footer_description": "整合券商研报、专家纪要与市场数据，以 AI 驱动的证据链和工作流工具服务研究型大V投顾、机构与普通投资者，持续沉淀可复用的方法论资产。",
}

DEFAULT_TENANTS = [
    {
        "id": "tenant_lw",
        "slug": "laowang",
        "name": "财经老王研究院",
        "short_name": "老王研究院",
        "logo_mark": "👑",
        "logo_url": "",
        "advisor": "财经老王",
        "tier": "旗舰租户",
        "focus": "A股科技 · 港股互联网 · 复盘专区",
        "rights": "复盘专区 · 知识专区 · Hermes 摘要 · 社群问答",
        "description": "面向 A 股科技、港股互联网和高频复盘粉丝用户的独立租户空间。",
        "portal_headline": "把每天该看的复盘、重点个股和研究框架，集中在一个粉丝能直接进入的专属门户里。",
        "portal_description": "这个门户不是给大V自己看的，而是给粉丝看的。你可以先看最新复盘、重点样本和研究框架，再决定是否继续去 H5 做自选股跟踪、Hermes 对话和专属问答。",
        "dashboard_title": "老王租户经营 Dashboard",
        "dashboard_description": "和 H5 核心指标面板同源，但在 Web 端用更完整的经营视角呈现。",
    },
    {
        "id": "tenant_lisa",
        "slug": "lisa",
        "name": "Lisa 港股研究社",
        "short_name": "Lisa 研究社",
        "logo_mark": "💎",
        "logo_url": "",
        "advisor": "投资女神Lisa",
        "tier": "专业租户",
        "focus": "港股互联网 · 南向资金 · 价值框架",
        "rights": "港股专栏 · 直播纪要 · Hermes 摘要 · 问答私域",
        "description": "面向港股互联网与价值投资粉丝的独立租户空间。",
        "portal_headline": "先把港股核心主线、代表性复盘和价值框架讲清楚，再把粉丝带进后续互动。",
        "portal_description": "这个门户面向粉丝展示 Lisa 的研究方向、最近复盘、代表性样本和互动权益，让用户先理解你在看什么、怎么判断，再进入 H5 跟踪和提问。",
        "dashboard_title": "Lisa 租户价值跟踪台",
        "dashboard_description": "突出港股估值、南向资金、回购与财报验证等核心经营与研究指标。",
    },
]

DEFAULT_SITE_CONFIG = {
    "default_theme": "light",
    "default_accent": "blue",
    "password_gate_enabled": True,
    "brand": DEFAULT_BRAND_CONFIG,
    "default_tenant_slug": DEFAULT_TENANTS[0]["slug"],
    "tenants": DEFAULT_TENANTS,
    "feature_flags": {
        "fundamental_analysis": True,
        "watchlist": True,
        "daily_review": True,
        "knowledge": True,
        "community": False,
        "hermes": False,
        "vip": False,
        "dm": False,
        "workbench": False,
    },
}

DEFAULT_FORECAST_TUNING = {
    "factor_score_clip": 8.0,
    "factor_signal_limit": 12.0,
    "momentum_signal_limit": 18.0,
    "predicted_change_limit": 35.0,
    "fundamental_adjustment_limit": 3.0,
    "volatility_cap_multiplier": 1.35,
    "backtest_weight": 0.55,
    "confidence_penalty_scale": 0.2,
    "confidence_floor": 45.0,
    "range_bound_multiplier": 0.85,
}

FORECAST_WORKFLOW_NODE_CATALOG = (
    {
        "processor": "source",
        "label": "上下文输入",
        "description": "从运行时上下文取值，作为后续节点输入。",
        "params": ({"key": "source_key", "label": "来源键", "kind": "text"},),
    },
    {
        "processor": "raw_signal",
        "label": "原始信号合成",
        "description": "将动量、因子和基本面修正合成为原始目标涨跌幅。",
        "params": (),
    },
    {
        "processor": "clip",
        "label": "总涨幅限幅",
        "description": "按绝对上限裁剪原始目标涨跌幅。",
        "params": ({"key": "limit_key", "label": "限幅参数键", "kind": "text"},),
    },
    {
        "processor": "volatility_cap",
        "label": "波动率约束",
        "description": "基于近 30 日波动率压缩目标空间。",
        "params": ({"key": "multiplier_key", "label": "倍数参数键", "kind": "text"},),
    },
    {
        "processor": "backtest_blend",
        "label": "回测收缩",
        "description": "结合历史相似样本平均回报对目标做收缩。",
        "params": ({"key": "weight_key", "label": "权重参数键", "kind": "text"},),
    },
    {
        "processor": "confidence_guard",
        "label": "置信度惩罚",
        "description": "低置信度场景下进一步压缩预测空间。",
        "params": (
            {"key": "floor_key", "label": "安全线参数键", "kind": "text"},
            {"key": "scale_key", "label": "惩罚参数键", "kind": "text"},
            {"key": "range_key", "label": "震荡系数参数键", "kind": "text"},
        ),
    },
    {
        "processor": "output",
        "label": "输出结果",
        "description": "输出最终高概率目标涨跌幅。",
        "params": (),
    },
)


def _coerce_float(value, fallback):
    try:
        return float(value)
    except Exception:
        return float(fallback)


def normalize_brand_config(source=None):
    raw = source if isinstance(source, dict) else {}
    brand = copy.deepcopy(DEFAULT_BRAND_CONFIG)
    for key in brand:
        value = raw.get(key, brand[key])
        brand[key] = str(value or brand[key]).strip() or brand[key]
    return brand


def normalize_tenant_config(source=None, index=0):
    raw = source if isinstance(source, dict) else {}
    fallback = DEFAULT_TENANTS[min(index, len(DEFAULT_TENANTS) - 1)]
    tenant = {}
    for key, default_value in fallback.items():
        value = raw.get(key, default_value)
        tenant[key] = str(value or default_value).strip() or default_value
    slug = tenant.get("slug", "").strip().lower().replace(" ", "-").replace("_", "-")
    tenant["slug"] = slug or fallback["slug"]
    tenant["id"] = tenant.get("id") or f"tenant_{tenant['slug']}"
    tenant["dashboard_title"] = tenant.get("dashboard_title") or f"{tenant['short_name']} Dashboard"
    tenant["dashboard_description"] = tenant.get("dashboard_description") or fallback["dashboard_description"]
    return tenant


def normalize_tenant_configs(source=None):
    items = source if isinstance(source, list) else []
    normalized = []
    seen_slugs = set()
    if not items:
        items = copy.deepcopy(DEFAULT_TENANTS)
    for index, item in enumerate(items):
        tenant = normalize_tenant_config(item, index)
        base_slug = tenant["slug"]
        dedup_slug = base_slug
        suffix = 2
        while dedup_slug in seen_slugs:
            dedup_slug = f"{base_slug}-{suffix}"
            suffix += 1
        tenant["slug"] = dedup_slug
        tenant["id"] = tenant.get("id") or f"tenant_{dedup_slug}"
        seen_slugs.add(dedup_slug)
        normalized.append(tenant)
    return normalized


def normalize_site_config(source=None):
    merged = _merge_site_config(copy.deepcopy(DEFAULT_SITE_CONFIG), source or {})
    merged["brand"] = normalize_brand_config(merged.get("brand"))
    merged["tenants"] = normalize_tenant_configs(merged.get("tenants"))
    tenant_slugs = [tenant["slug"] for tenant in merged["tenants"]]
    default_tenant_slug = str(merged.get("default_tenant_slug", "") or "").strip()
    merged["default_tenant_slug"] = default_tenant_slug if default_tenant_slug in tenant_slugs else tenant_slugs[0]
    return merged


def get_platform_brand(site_config=None):
    config = site_config or get_site_config()
    return normalize_brand_config(config.get("brand"))


def get_tenant_configs(site_config=None):
    config = site_config or get_site_config()
    return normalize_tenant_configs(config.get("tenants"))


def get_default_tenant_slug(site_config=None):
    config = site_config or get_site_config()
    return str(config.get("default_tenant_slug", "") or "").strip() or DEFAULT_TENANTS[0]["slug"]


def get_tenant_by_slug(slug=None, site_config=None):
    tenants = get_tenant_configs(site_config)
    target = str(slug or "").strip().lower()
    if not target:
        target = get_default_tenant_slug(site_config)
    for tenant in tenants:
        if tenant["slug"] == target:
            return tenant
    return tenants[0] if tenants else normalize_tenant_config({}, 0)


def get_active_tenant_from_request(site_config=None):
    return get_tenant_by_slug(request.args.get("tenant"), site_config)


def build_tenant_dashboard_payload(tenant=None):
    tenant = tenant or get_tenant_by_slug()
    workbench = gen_kol_workbench(tenant)
    dashboard_metrics = workbench["dashboard_metrics"]
    return {
        "title": tenant["dashboard_title"],
        "description": tenant["dashboard_description"],
        "tenant": tenant,
        "kpis": dashboard_metrics["kpis"],
        "message_distribution": dashboard_metrics["message_distribution"],
        "message_trend": dashboard_metrics["message_trend"],
        "publish_distribution": dashboard_metrics["publish_distribution"],
        "publish_trend": dashboard_metrics["publish_trend"],
        "fund_dashboard": workbench["fund_dashboard"],
        "reviews": workbench["published_reviews"],
        "stats": workbench["stats"],
    }


def build_tenant_portal_payload(tenant=None):
    tenant = tenant or get_tenant_by_slug()
    workbench = gen_kol_workbench(tenant)
    watchlist_items = copy.deepcopy(workbench["watchlist_hub"]["items"])
    reviews = copy.deepcopy(workbench["published_reviews"])
    knowledge_items = copy.deepcopy(workbench["knowledge_hub"]["items"])
    is_lisa = tenant["slug"] == "lisa"
    for review in reviews:
        review["detail_sections"] = [
            {
                "title": "这篇复盘主要解决什么",
                "body": review["summary"],
            },
            {
                "title": "本篇重点样本",
                "bullets": review.get("watchlist", []),
            },
            {
                "title": "适合什么人先看",
                "body": "适合已经在跟这位主理人研究口径、想先快速理解阶段主线和下一步观察点的粉丝用户。",
            },
        ]
    for item in watchlist_items:
        item["detail_sections"] = [
            {
                "title": "当前跟踪焦点",
                "body": item["focus"],
            },
            {
                "title": "当前判断",
                "body": item["thesis"],
            },
            {
                "title": "继续看什么",
                "bullets": [
                    "是否出现新的验证材料",
                    "主线是否继续强化而不是只剩情绪波动",
                    "后续复盘里是否仍被保留为重点样本",
                ],
            },
        ]
    research_framework = [
        {
            "title": is_lisa and "先看估值修复能否被业绩接住" or "先看主线有没有真实验证材料",
            "desc": is_lisa and "港股互联网优先看回购、利润率和财报兑现，不把情绪当结论。" or "科技成长优先看订单、景气和资金是否连续验证，不把热度直接当逻辑。",
            "detail_sections": [
                {
                    "title": "为什么先看这一层",
                    "body": "先判断主线是否有真实材料承接，能避免只看短期波动或单日情绪。",
                },
                {
                    "title": "常见验证点",
                    "bullets": is_lisa and ["回购节奏", "利润率兑现", "财报后的估值承接"] or ["订单兑现", "行业景气持续性", "资金验证是否连续"],
                },
            ],
        },
        {
            "title": "只保留真正值得跟踪的样本",
            "desc": "不是把所有股票都讲一遍，而是把最值得继续跟踪的样本收进固定池子里。",
            "detail_sections": [
                {
                    "title": "这样做的原因",
                    "body": "粉丝真正需要的不是覆盖越多越好，而是知道哪些样本值得持续看，哪些已经可以暂时放掉。",
                },
                {
                    "title": "粉丝能直接得到什么",
                    "bullets": ["更少的噪音", "更清晰的样本池", "更容易跟上后续复盘"],
                },
            ],
        },
        {
            "title": "结论必须带风险边界",
            "desc": "每次复盘都要写清楚什么条件成立、什么条件失效，避免只讲单边观点。",
            "detail_sections": [
                {
                    "title": "风险边界怎么用",
                    "body": "不是只写结论，而是同步写明失效条件和反证条件，帮助粉丝理解什么时候该继续跟、什么时候该停下来重看。",
                },
                {
                    "title": "通常会同步哪些内容",
                    "bullets": ["成立条件", "失效条件", "下一步观察项"],
                },
            ],
        },
    ]
    service_cards = [
        {
            "title": "复盘专区",
            "desc": "查看已发布的日复盘、周复盘和阶段主线整理。",
            "detail_sections": [
                {"title": "你会看到什么", "bullets": ["已发布复盘", "阶段主线", "重点样本和下一步观察"]},
                {"title": "适合什么时候用", "body": "适合先快速理解最近判断，再决定是否继续深挖。"},
            ],
        },
        {
            "title": "Hermes 对话",
            "desc": "基于当前租户研究口径继续问个股、板块和证据链。",
            "detail_sections": [
                {"title": "它和普通问答的区别", "body": "会承接当前租户的大V研究口径，而不是通用聊天。"},
                {"title": "常见适用问题", "bullets": ["这只股票为什么还在重点池里", "某条主线的验证点是什么", "当前判断的证据链来自哪里"]},
            ],
        },
        {
            "title": "自选股跟踪",
            "desc": "把你自己关注的样本加入自选，后续复盘会更贴近你的持仓和兴趣。",
            "detail_sections": [
                {"title": "带来的变化", "body": "系统会更容易把你的关注样本带入后续复盘和智能整理。"},
                {"title": "适合谁", "body": "适合已经有明确观察名单、希望门户内容更贴近自己的人。"},
            ],
        },
        {
            "title": "专属问答",
            "desc": "看完内容后可继续在消息区向所属大V提问。",
            "detail_sections": [
                {"title": "适合提什么", "bullets": ["样本为什么继续保留", "某个风险边界怎么理解", "后续更应该看哪一个验证节点"]},
                {"title": "提问前建议", "body": "先看完最新复盘和重点样本，再提问题，交流效率会更高。"},
            ],
        },
    ]
    for item in knowledge_items[:2]:
        item["detail_sections"] = [
            {
                "title": "这条知识沉淀的用途",
                "body": item["summary"],
            },
            {
                "title": "会影响哪些后续内容",
                "bullets": ["Hermes 对话", "后续复盘", "研究框架表达"],
            },
        ]
    return {
        "tenant": tenant,
        "brand": get_platform_brand(),
        "hero_stats": [
            {"label": "代表性方向", "value": tenant["focus"]},
            {"label": "当前开放权益", "value": tenant["rights"]},
            {"label": "最近更新", "value": reviews[0]["time"] if reviews else "持续更新中"},
        ],
        "highlights": [
            {
                "title": "先看主线",
                "desc": "进入门户先知道当前重点研究哪些方向，而不是先掉进复杂功能里。",
            },
            {
                "title": "先看复盘",
                "desc": "粉丝先消费已经确认发布的复盘，再决定是否继续深挖个股和框架。",
            },
            {
                "title": "再去互动",
                "desc": "理解研究口径以后，再进入 H5 做自选股跟踪、Hermes 对话和专属提问。",
            },
        ],
        "audience_sections": [
            {
                "title": "你在这里先得到什么",
                "desc": "不是把功能全摊开，而是先把粉丝最需要的内容入口收拢起来。",
                "items": [
                    {"title": "最新复盘", "desc": "先看已经发布的日复盘 / 周复盘，快速理解当前判断主线。"},
                    {"title": "重点样本", "desc": "直接看到当前最值得继续跟踪的几只样本，不用自己先筛一遍。"},
                    {"title": "研究框架", "desc": "知道这位大V平时怎么看估值、验证节点和风险边界。"},
                ],
            },
            {
                "title": "适合哪些粉丝",
                "desc": "这个门户不是泛流量首页，而是面向已经认可这位主理人研究风格的人。",
                "items": [
                    {"title": "高频复盘用户", "desc": "每天想快速看阶段主线和重点样本的人。"},
                    {"title": "框架型用户", "desc": "不只想看结论，也想知道判断依据和方法的人。"},
                    {"title": "互动型用户", "desc": "看完内容后，希望继续问个股、板块和验证节点的人。"},
                ],
            },
        ],
        "featured_reviews": reviews,
        "featured_watchlist": watchlist_items,
        "research_framework": research_framework,
        "service_cards": service_cards,
        "knowledge_spotlight": knowledge_items[:2],
        "cta": {
            "primary_label": "进入 H5 继续查看",
            "primary_href": f"/h5?tenant={tenant['slug']}",
            "secondary_label": "直接看最新复盘",
            "secondary_href": "#latest-review",
        },
    }


def normalize_forecast_tuning_values(source=None):
    payload = source or {}
    normalized = {}
    for key, default_value in DEFAULT_FORECAST_TUNING.items():
        raw = payload.get(key, default_value)
        try:
            normalized[key] = float(raw)
        except Exception:
            normalized[key] = float(default_value)
    normalized["factor_score_clip"] = max(0.5, normalized["factor_score_clip"])
    normalized["factor_signal_limit"] = max(1.0, normalized["factor_signal_limit"])
    normalized["momentum_signal_limit"] = max(1.0, normalized["momentum_signal_limit"])
    normalized["predicted_change_limit"] = max(3.0, normalized["predicted_change_limit"])
    normalized["fundamental_adjustment_limit"] = max(0.0, normalized["fundamental_adjustment_limit"])
    normalized["volatility_cap_multiplier"] = max(0.2, normalized["volatility_cap_multiplier"])
    normalized["backtest_weight"] = max(0.0, min(1.0, normalized["backtest_weight"]))
    normalized["confidence_penalty_scale"] = max(0.0, normalized["confidence_penalty_scale"])
    normalized["confidence_floor"] = max(1.0, min(99.0, normalized["confidence_floor"]))
    normalized["range_bound_multiplier"] = max(0.4, min(1.0, normalized["range_bound_multiplier"]))
    return normalized


def build_forecast_node_catalog():
    return [copy.deepcopy(item) for item in FORECAST_WORKFLOW_NODE_CATALOG]


def build_default_forecast_workflow_graph(tuning=None):
    normalized = normalize_forecast_tuning_values(tuning)
    return {
        "version": 1,
        "title": "预测算法工作流",
        "summary": "展示目标价是怎么计算出来的，并允许在后台调整自动收敛参数。",
        "nodes": [
            {"id": "source_signals", "label": "市场信号输入", "processor": "source", "x": 32, "y": 48, "params": {"source_key": "signals_bundle"}},
            {"id": "source_volatility", "label": "波动率输入", "processor": "source", "x": 32, "y": 188, "params": {"source_key": "volatility_context"}},
            {"id": "source_backtest", "label": "回测输入", "processor": "source", "x": 32, "y": 328, "params": {"source_key": "backtest_context"}},
            {"id": "source_confidence", "label": "置信度输入", "processor": "source", "x": 32, "y": 468, "params": {"source_key": "confidence_context"}},
            {"id": "raw_signal", "label": "原始信号", "processor": "raw_signal", "x": 312, "y": 48, "params": {}},
            {"id": "predicted_clip", "label": "总涨幅限幅", "processor": "clip", "x": 580, "y": 48, "params": {"limit_key": "predicted_change_limit"}},
            {"id": "volatility_cap", "label": "波动率约束", "processor": "volatility_cap", "x": 848, "y": 118, "params": {"multiplier_key": "volatility_cap_multiplier"}},
            {"id": "backtest_shrink", "label": "回测收缩", "processor": "backtest_blend", "x": 1116, "y": 258, "params": {"weight_key": "backtest_weight"}},
            {"id": "confidence_penalty", "label": "置信度惩罚", "processor": "confidence_guard", "x": 1384, "y": 398, "params": {"floor_key": "confidence_floor", "scale_key": "confidence_penalty_scale", "range_key": "range_bound_multiplier"}},
            {"id": "final_output", "label": "最终目标涨跌幅", "processor": "output", "x": 1652, "y": 398, "params": {}},
        ],
        "edges": [
            {"id": "edge_signals_raw", "from": "source_signals", "to": "raw_signal"},
            {"id": "edge_raw_clip", "from": "raw_signal", "to": "predicted_clip"},
            {"id": "edge_clip_vol", "from": "predicted_clip", "to": "volatility_cap"},
            {"id": "edge_vol_ctx", "from": "source_volatility", "to": "volatility_cap"},
            {"id": "edge_vol_backtest", "from": "volatility_cap", "to": "backtest_shrink"},
            {"id": "edge_backtest_ctx", "from": "source_backtest", "to": "backtest_shrink"},
            {"id": "edge_backtest_conf", "from": "backtest_shrink", "to": "confidence_penalty"},
            {"id": "edge_conf_ctx", "from": "source_confidence", "to": "confidence_penalty"},
            {"id": "edge_conf_output", "from": "confidence_penalty", "to": "final_output"},
        ],
        "tuning": normalized,
    }


def normalize_forecast_workflow_graph(payload):
    source = payload if isinstance(payload, dict) else {}
    default_graph = build_default_forecast_workflow_graph(source.get("tuning") if isinstance(source.get("tuning"), dict) else None)
    nodes = source.get("nodes", default_graph["nodes"])
    edges = source.get("edges", default_graph["edges"])
    title = str(source.get("title", default_graph["title"]) or default_graph["title"])
    summary = str(source.get("summary", default_graph["summary"]) or default_graph["summary"])
    tuning = normalize_forecast_tuning_values(source.get("tuning") if isinstance(source.get("tuning"), dict) else default_graph["tuning"])
    catalog_map = {item["processor"]: item for item in FORECAST_WORKFLOW_NODE_CATALOG}
    normalized_nodes = []
    seen_ids = set()
    if isinstance(nodes, list):
        for index, item in enumerate(nodes):
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("id", "")).strip() or f"node_{index + 1}"
            if node_id in seen_ids:
                node_id = f"{node_id}_{index + 1}"
            seen_ids.add(node_id)
            processor = str(item.get("processor", "source")).strip() or "source"
            if processor not in catalog_map:
                processor = "source"
            fallback_node = default_graph["nodes"][min(index, len(default_graph["nodes"]) - 1)]
            normalized_nodes.append(
                {
                    "id": node_id,
                    "label": str(item.get("label", catalog_map[processor]["label"]) or catalog_map[processor]["label"]),
                    "processor": processor,
                    "x": _coerce_float(item.get("x"), fallback_node["x"]),
                    "y": _coerce_float(item.get("y"), fallback_node["y"]),
                    "params": dict(item.get("params", {})) if isinstance(item.get("params"), dict) else {},
                }
            )
    if not normalized_nodes:
        normalized_nodes = copy.deepcopy(default_graph["nodes"])
    node_ids = {item["id"] for item in normalized_nodes}
    normalized_edges = []
    seen_edge_ids = set()
    if isinstance(edges, list):
        for index, item in enumerate(edges):
            if not isinstance(item, dict):
                continue
            from_id = str(item.get("from", "")).strip()
            to_id = str(item.get("to", "")).strip()
            if from_id not in node_ids or to_id not in node_ids or from_id == to_id:
                continue
            edge_id = str(item.get("id", "")).strip() or f"edge_{index + 1}"
            if edge_id in seen_edge_ids:
                edge_id = f"{edge_id}_{index + 1}"
            if any(row["from"] == from_id and row["to"] == to_id for row in normalized_edges):
                continue
            seen_edge_ids.add(edge_id)
            normalized_edges.append({"id": edge_id, "from": from_id, "to": to_id})
    if not normalized_edges:
        normalized_edges = copy.deepcopy(default_graph["edges"])
    default_nodes = copy.deepcopy(default_graph["nodes"])
    default_node_map = {item["id"]: item for item in default_nodes}
    merged_nodes_map = {item["id"]: item for item in normalized_nodes}
    for default_node in default_nodes:
        if default_node["id"] not in merged_nodes_map:
            merged_nodes_map[default_node["id"]] = default_node
    ordered_nodes = [merged_nodes_map[node["id"]] for node in default_nodes if node["id"] in merged_nodes_map]
    ordered_nodes.extend([item for item in normalized_nodes if item["id"] not in default_node_map])
    default_edges = copy.deepcopy(default_graph["edges"])
    merged_edges = list(normalized_edges)
    existing_pairs = {(item["from"], item["to"]) for item in merged_edges}
    for default_edge in default_edges:
        pair = (default_edge["from"], default_edge["to"])
        if pair not in existing_pairs:
            merged_edges.append(default_edge)
            existing_pairs.add(pair)
    return {
        "version": 1,
        "title": title,
        "summary": summary,
        "nodes": ordered_nodes,
        "edges": merged_edges,
        "tuning": tuning,
    }


def workflow_graph_to_tuning(graph):
    normalized_graph = normalize_forecast_workflow_graph(graph)
    tuning = dict(normalized_graph.get("tuning", {}))
    for node in normalized_graph["nodes"]:
        params = node.get("params", {})
        if not isinstance(params, dict):
            continue
        for key in ("limit_key", "multiplier_key", "weight_key", "floor_key", "scale_key", "range_key"):
            tuning_key = str(params.get(key, "")).strip()
            if tuning_key in DEFAULT_FORECAST_TUNING and tuning_key not in tuning:
                tuning[tuning_key] = DEFAULT_FORECAST_TUNING[tuning_key]
    return normalize_forecast_tuning_values(tuning)


def _build_context_preview(context):
    if not isinstance(context, dict):
        return {}
    preview = {}
    for key, value in context.items():
        if isinstance(value, float):
            preview[key] = round(value, 3)
        elif isinstance(value, (int, str)):
            preview[key] = value
    return preview


def _topological_nodes(graph):
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    incoming = {item["id"]: 0 for item in nodes}
    outgoing = {item["id"]: [] for item in nodes}
    for edge in edges:
        if edge["from"] in outgoing and edge["to"] in incoming:
            outgoing[edge["from"]].append(edge["to"])
            incoming[edge["to"]] += 1
    queue = [item["id"] for item in nodes if incoming[item["id"]] == 0]
    ordered = []
    while queue:
        node_id = queue.pop(0)
        ordered.append(node_id)
        for target in outgoing.get(node_id, []):
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    if len(ordered) != len(nodes):
        return [item["id"] for item in nodes]
    return ordered


def _build_runtime_contexts(tuning):
    closes = [100 + idx * 0.28 + ((idx % 7) - 3) * 0.22 for idx in range(90)]
    returns = []
    for idx in range(1, len(closes)):
        prev = closes[idx - 1]
        returns.append((closes[idx] - prev) / prev)
    recent_returns = returns[-30:]
    realized_daily_vol = statistics.pstdev(recent_returns) if len(recent_returns) > 1 else 0.0
    volatility_cap = max(4.0, realized_daily_vol * math.sqrt(20) * 100 * tuning["volatility_cap_multiplier"])
    avg_return_pct = 6.8
    up_probability = 61.5
    sample_size = 18
    sample_confidence = min(1.0, sample_size / 12.0)
    backtest_anchor = avg_return_pct * (0.55 + 0.45 * sample_confidence)
    raw_factor_signal = 11.3
    factor_signal = max(-tuning["factor_signal_limit"], min(tuning["factor_signal_limit"], 9.2))
    momentum_signal = max(-tuning["momentum_signal_limit"], min(tuning["momentum_signal_limit"], 8.4))
    confidence = 68.0
    bullish_confidence = 63.0
    confidence_penalty = max(0.0, (tuning["confidence_floor"] - confidence) * tuning["confidence_penalty_scale"] / 10.0)
    return {
        "signals_bundle": {
            "stance": "震荡偏上",
            "raw_factor_signal": raw_factor_signal,
            "factor_signal": factor_signal,
            "momentum_signal": momentum_signal,
            "fundamental_adjustment": 1.1,
            "bullish_confidence": bullish_confidence,
        },
        "volatility_context": {
            "realized_daily_vol": realized_daily_vol,
            "volatility_cap": volatility_cap,
        },
        "backtest_context": {
            "avg_return_pct": avg_return_pct,
            "up_probability": up_probability,
            "sample_size": sample_size,
            "sample_confidence": sample_confidence,
            "backtest_anchor": backtest_anchor,
        },
        "confidence_context": {
            "confidence": confidence,
            "confidence_floor": tuning["confidence_floor"],
            "confidence_penalty": confidence_penalty,
            "range_bound_multiplier": tuning["range_bound_multiplier"],
        },
    }


def _execute_workflow_node(node, upstream_values, contexts, tuning):
    processor = node.get("processor", "source")
    params = node.get("params", {}) if isinstance(node.get("params"), dict) else {}
    if processor == "source":
        source_key = str(params.get("source_key", "")).strip()
        context = contexts.get(source_key, {})
        label = source_key or "unknown_context"
        return {
            "value": 0.0,
            "formula": f"context[{label}]",
            "note": "提供运行时上下文，不直接产生目标涨跌幅。",
            "context": context,
        }
    if processor == "raw_signal":
        signal_context = {}
        for item in upstream_values:
            if isinstance(item.get("context"), dict):
                signal_context.update(item["context"])
        value = float(signal_context.get("factor_signal", 0)) * 0.45 + float(signal_context.get("momentum_signal", 0)) * 0.35 + float(signal_context.get("fundamental_adjustment", 0)) * 0.2
        value = max(-tuning["factor_score_clip"], min(tuning["factor_score_clip"], value))
        return {
            "value": value,
            "formula": "0.45*因子信号 + 0.35*动量信号 + 0.20*基本面修正",
            "note": "先把多来源强弱合成为单一原始预测信号。",
            "context": signal_context,
        }
    if processor == "clip":
        limit = tuning.get(str(params.get("limit_key", "predicted_change_limit")).strip(), tuning["predicted_change_limit"])
        input_value = float(upstream_values[0].get("value", 0) if upstream_values else 0)
        value = max(-limit, min(limit, input_value))
        return {
            "value": value,
            "formula": f"clip(raw_signal, ±{round(limit, 2)})",
            "note": "限制单轮预测不超过全局上限。",
            "context": {"input_value": input_value, "limit": limit},
        }
    if processor == "volatility_cap":
        input_value = float(upstream_values[0].get("value", 0) if upstream_values else 0)
        volatility_context = {}
        for item in upstream_values:
            if isinstance(item.get("context"), dict):
                volatility_context.update(item["context"])
        cap = float(volatility_context.get("volatility_cap", 0))
        limited = max(-cap, min(cap, input_value))
        return {
            "value": limited,
            "formula": "clip(predicted_change, ±volatility_cap)",
            "note": "按近 30 日波动率压缩目标涨跌幅。",
            "context": dict(volatility_context, input_value=input_value),
        }
    if processor == "backtest_blend":
        input_value = float(upstream_values[0].get("value", 0) if upstream_values else 0)
        backtest_context = {}
        for item in upstream_values:
            if isinstance(item.get("context"), dict):
                backtest_context.update(item["context"])
        weight = tuning.get(str(params.get("weight_key", "backtest_weight")).strip(), tuning["backtest_weight"])
        anchor = float(backtest_context.get("backtest_anchor", 0))
        value = input_value * (1 - weight) + anchor * weight
        return {
            "value": value,
            "formula": f"(1-{round(weight, 2)})*波动率约束后结果 + {round(weight, 2)}*回测锚",
            "note": "把当前信号和历史相似样本均值做加权收缩。",
            "context": dict(backtest_context, input_value=input_value, weight=weight),
        }
    if processor == "confidence_guard":
        input_value = float(upstream_values[0].get("value", 0) if upstream_values else 0)
        confidence_context = {}
        for item in upstream_values:
            if isinstance(item.get("context"), dict):
                confidence_context.update(item["context"])
        penalty = float(confidence_context.get("confidence_penalty", 0))
        range_multiplier = tuning.get(str(params.get("range_key", "range_bound_multiplier")).strip(), tuning["range_bound_multiplier"])
        adjusted = input_value - penalty if input_value >= 0 else input_value + penalty
        adjusted *= range_multiplier
        return {
            "value": adjusted,
            "formula": f"(回测收缩结果 {'-' if input_value >= 0 else '+'} 置信度惩罚) * {round(range_multiplier, 2)}",
            "note": "置信度不够时继续收窄空间，避免目标价过度发散。",
            "context": dict(confidence_context, input_value=input_value, range_multiplier=range_multiplier),
        }
    input_value = float(upstream_values[0].get("value", 0) if upstream_values else 0)
    return {
        "value": input_value,
        "formula": "output(previous_step)",
        "note": "输出当前工作流最终结果。",
        "context": {"input_value": input_value},
    }


def run_forecast_workflow_graph(graph):
    normalized_graph = normalize_forecast_workflow_graph(graph)
    tuning = workflow_graph_to_tuning(normalized_graph)
    contexts = _build_runtime_contexts(tuning)
    ordered_nodes = _topological_nodes(normalized_graph)
    node_lookup = {item["id"]: item for item in normalized_graph["nodes"]}
    incoming_map = {item["id"]: [] for item in normalized_graph["nodes"]}
    for edge in normalized_graph["edges"]:
        incoming_map.setdefault(edge["to"], []).append(edge["from"])
    runtime_values = {}
    steps = []
    node_results = {}
    final_value = 0.0
    for node_id in ordered_nodes:
        node = node_lookup[node_id]
        upstream_values = [runtime_values[source_id] for source_id in incoming_map.get(node_id, []) if source_id in runtime_values]
        result = _execute_workflow_node(node, upstream_values, contexts, tuning)
        runtime_values[node_id] = result
        node_results[node_id] = {
            "label": node["label"],
            "processor": node["processor"],
            "value": round(float(result.get("value", 0) or 0), 2),
            "formula": str(result.get("formula", "")),
            "note": str(result.get("note", "")),
            "context_preview": _build_context_preview(result.get("context")),
        }
        if node["processor"] not in {"source", "output"}:
            steps.append(
                {
                    "key": node_id,
                    "label": node["label"],
                    "formula": str(result.get("formula", "")),
                    "value": round(float(result.get("value", 0) or 0), 2),
                    "note": str(result.get("note", "")),
                    "processor": node["processor"],
                }
            )
        if node["processor"] == "output":
            final_value = float(result.get("value", 0) or 0)
    workflow = {
        "inputs": {
            "raw_factor_signal": 11.3,
            "factor_signal_after_clip": 9.2,
            "momentum_signal": 8.4,
            "fundamental_adjustment": 1.1,
            "bullish_confidence": 63.0,
            "confidence": 68.0,
            "backtest_up_probability": 61.5,
            "backtest_avg_return_pct": 6.8,
            "backtest_sample_size": 18,
        },
        "steps": steps,
        "result": {
            "predicted_change_pct": round(final_value, 2),
            "volatility_cap": round(float(contexts["volatility_context"]["volatility_cap"]), 2),
            "backtest_anchor": round(float(contexts["backtest_context"]["backtest_anchor"]), 2),
            "confidence_penalty": round(float(contexts["confidence_context"]["confidence_penalty"]), 2),
        },
        "graph": normalized_graph,
        "node_results": node_results,
    }
    return final_value, workflow


def build_forecast_workflow_preview(graph):
    _, workflow = run_forecast_workflow_graph(graph)
    return {
        "inputs": workflow.get("inputs", {}),
        "result": workflow.get("result", {}),
        "steps": workflow.get("steps", []),
        "node_results": workflow.get("node_results", {}),
    }


def build_forecast_workflow_meta(graph):
    normalized_graph = normalize_forecast_workflow_graph(graph)
    preview = build_forecast_workflow_preview(normalized_graph)
    graph_with_preview = copy.deepcopy(normalized_graph)
    graph_with_preview["node_results"] = preview.get("node_results", {})
    return {
        "title": str(normalized_graph["title"]),
        "summary": str(normalized_graph["summary"]),
        "graph": graph_with_preview,
        "catalog": build_forecast_node_catalog(),
        "preview": preview,
    }

# Mock data
CHANNELS = ["微信社群", "内容合作", "小红书", "转介绍", "直接流量"]
FUNNEL_LAYERS = ["内容触达", "私域留资", "激活试用", "首次付费", "高频留存"]

def gen_funnel_data():
    base = [68000, 5400, 1260, 128, 36]
    return [{"layer": FUNNEL_LAYERS[i], "count": base[i], "rate": round(base[i]/base[0]*100, 2)} for i in range(5)]

def gen_channel_data():
    data = [
        {"name": "微信社群", "users": 2100, "conversion": 6.4, "revenue": 28600, "color": "#07C160"},
        {"name": "内容合作", "users": 1400, "conversion": 4.8, "revenue": 19200, "color": "#FE2C55"},
        {"name": "小红书", "users": 980, "conversion": 3.6, "revenue": 13600, "color": "#FF2442"},
        {"name": "转介绍", "users": 620, "conversion": 12.1, "revenue": 24800, "color": "#E6162D"},
        {"name": "直接流量", "users": 300, "conversion": 15.0, "revenue": 16800, "color": "#C8A96E"},
    ]
    return data

def gen_kol_data():
    tenants = get_tenant_configs()
    tenant_rows = []
    for index, tenant in enumerate(tenants):
        tenant_rows.append(
            {
                "name": tenant["advisor"],
                "platform": "租户门户",
                "followers": 128000 - index * 18000,
                "gmv": 18600 - index * 2400,
                "commission": 2790 - index * 360,
                "tier": tenant["tier"],
                "tenant_name": tenant["name"],
                "tenant_slug": tenant["slug"],
            }
        )
    tenant_rows.extend(
        [
            {"name": "宏观策略师", "platform": "内容合作", "followers": 54000, "gmv": 9600, "commission": 1536, "tier": "观察"},
            {"name": "量化小白", "platform": "小红书", "followers": 32000, "gmv": 7800, "commission": 1170, "tier": "观察"},
            {"name": "港股研究员", "platform": "转介绍", "followers": 18000, "gmv": 5400, "commission": 810, "tier": "观察"},
        ]
    )
    return tenant_rows

def gen_market_data():
    indices = [
        {
            "code": "600519",
            "name": "贵州茅台",
            "market": "SH",
            "value": 1688.20,
            "change": 12.80,
            "change_pct": 0.76,
            "focus": "高端白酒",
            "board": "稳健配置",
            "alert_level": "normal",
            "alert_text": "估值回到中枢附近，当前无明显预警",
            "signal_summary": "盈利稳定，重点看消费修复持续性",
            "authors": ["财经老王", "量化老师陈明"],
        },
        {
            "code": "300750",
            "name": "宁德时代",
            "market": "SZ",
            "value": 212.36,
            "change": -3.84,
            "change_pct": -1.78,
            "focus": "动力电池",
            "board": "新能源",
            "alert_level": "warning",
            "alert_text": "价格竞争仍在，需继续跟踪利润率和海外出货",
            "signal_summary": "情绪回落，等待技术路线与订单验证",
            "authors": ["新能源猎手阿强", "全球宏观James"],
        },
        {
            "code": "00700",
            "name": "腾讯控股",
            "market": "HK",
            "value": 388.40,
            "change": 5.60,
            "change_pct": 1.46,
            "focus": "港股互联网",
            "board": "港股互联网",
            "alert_level": "attention",
            "alert_text": "财报前估值修复较快，关注南向资金是否继续放量",
            "signal_summary": "回购和财报兑现是两条主验证线",
            "authors": ["投资女神Lisa", "港股研究员"],
        },
        {
            "code": "688981",
            "name": "中芯国际",
            "market": "SH",
            "value": 46.52,
            "change": 1.18,
            "change_pct": 2.60,
            "focus": "半导体制造",
            "board": "科技成长",
            "alert_level": "attention",
            "alert_text": "景气恢复尚未完全兑现，需继续跟踪产能利用率",
            "signal_summary": "国产替代逻辑在，短期看盈利兑现",
            "authors": ["财经老王", "宏观策略师"],
        },
        {
            "code": "600036",
            "name": "招商银行",
            "market": "SH",
            "value": 41.86,
            "change": 0.22,
            "change_pct": 0.53,
            "focus": "银行",
            "board": "稳健配置",
            "alert_level": "normal",
            "alert_text": "股息和资产质量稳定，当前无明显报警",
            "signal_summary": "更适合作为组合稳定器跟踪",
            "authors": ["全球宏观James", "量化老师陈明"],
        },
    ]
    return indices


def gen_macro_indicators():
    return [
        {
            "name": "美联储年内降息预期",
            "value": "2次",
            "status": "good",
            "assessment": "偏利好风险资产",
            "alert": "当前无需报警",
            "hint": "市场已部分提前定价，后续看非农和通胀数据是否继续支持。",
        },
        {
            "name": "北向 / 南向资金",
            "value": "+28亿 / +41亿",
            "status": "attention",
            "assessment": "流入延续但未到强共振",
            "alert": "关注是否连续 3 日放量",
            "hint": "若资金只集中在单一主线，说明市场广度仍不够。",
        },
        {
            "name": "美元指数",
            "value": "103.4",
            "status": "good",
            "assessment": "偏回落，对港股与大宗更友好",
            "alert": "当前无需报警",
            "hint": "若美元重新走强，港股互联网和黄金链条都要重新评估。",
        },
        {
            "name": "国内信用脉冲",
            "value": "温和修复",
            "status": "warning",
            "assessment": "恢复力度偏弱",
            "alert": "需继续观察社融和中长期贷款",
            "hint": "若信用扩张迟迟不起来，顺周期与高弹性资产要谨慎。",
        },
    ]


def gen_feed_boards(market_items):
    boards = []
    board_map = {}
    for item in market_items:
        board_name = item.get("board") or "自选股"
        if board_name not in board_map:
            board_map[board_name] = {
                "name": board_name,
                "warning_count": 0,
                "items": [],
            }
            boards.append(board_map[board_name])
        if item.get("alert_level") in {"warning", "attention"}:
            board_map[board_name]["warning_count"] += 1
        board_map[board_name]["items"].append(
            {
                "code": item["code"],
                "name": item["name"],
                "market": item["market"],
                "value": item["value"],
                "change": item["change"],
                "change_pct": item["change_pct"],
                "focus": item["focus"],
                "alert_level": item.get("alert_level", "normal"),
                "alert_text": item.get("alert_text", "当前无明显预警"),
                "signal_summary": item.get("signal_summary", ""),
            }
        )
    return boards


def gen_watchlist_details():
    def build_kline_series(stock_code, base_price):
        rng = random.Random(f"kline:{stock_code}")
        close = float(base_price) * (0.9 + rng.random() * 0.2)
        current_date = datetime.now() - timedelta(days=33)
        series = []
        while len(series) < 24:
            current_date += timedelta(days=1)
            if current_date.weekday() >= 5:
                continue
            open_price = close * (1 + rng.uniform(-0.018, 0.018))
            close_price = open_price * (1 + rng.uniform(-0.035, 0.035))
            high_price = max(open_price, close_price) * (1 + rng.uniform(0.004, 0.022))
            low_price = min(open_price, close_price) * (1 - rng.uniform(0.004, 0.022))
            series.append({
                "date": current_date.strftime("%m-%d"),
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
            })
            close = close_price
        return series

    return {
        "600519": {
            "code": "600519",
            "name": "贵州茅台",
            "market": "SH",
            "price": 1688.20,
            "change": 12.80,
            "change_pct": 0.76,
            "industry": "高端白酒",
            "kline": build_kline_series("600519", 1688.20),
            "authors": [
                {"id": 1, "name": "财经老王", "avatar": "👑", "tier": "种子作者", "angle": "消费龙头的现金流韧性仍在，核心要看估值是否已经反映需求修复。"},
                {"id": 3, "name": "量化老师陈明", "avatar": "📊", "tier": "成长作者", "angle": "从历史分位看，当前更适合做中期配置跟踪，不建议把短期波动当趋势。"},
            ],
            "fundamental": {
                "summary": "品牌力和现金流仍是最大护城河，当前争议主要集中在增速放缓后的估值承受力。",
                "metrics": [
                    {"label": "收入增速", "value": "15.2%", "note": "较去年同期放缓但仍稳健"},
                    {"label": "净利率", "value": "52.4%", "note": "维持高位"},
                    {"label": "ROE", "value": "31.8%", "note": "资本效率仍强"},
                    {"label": "估值分位", "value": "43%", "note": "回到中枢附近"},
                ],
                "thesis": [
                    "品牌定价权和渠道控制能力仍强。",
                    "若消费修复延续，盈利稳定性会继续支撑估值。",
                    "风险在于市场对高端消费增速放缓的容忍度下降。",
                ],
            },
            "forecast": {
                "label": "基本面判断",
                "verdict": "稳健跟踪",
                "confidence": "中高",
                "band": "未来 1-2 个季度更像利润兑现验证，而不是高弹性重估。",
                "drivers": [
                    {"label": "盈利稳定性", "score": "+2.4", "note": "现金流和利润率支撑强"},
                    {"label": "估值弹性", "score": "+0.8", "note": "缺少强扩张催化"},
                    {"label": "行业景气", "score": "+1.2", "note": "消费修复温和"},
                ],
            },
        },
        "300750": {
            "code": "300750",
            "name": "宁德时代",
            "market": "SZ",
            "price": 212.36,
            "change": -3.84,
            "change_pct": -1.78,
            "industry": "动力电池",
            "kline": build_kline_series("300750", 212.36),
            "authors": [
                {"id": 5, "name": "新能源猎手阿强", "avatar": "⚡", "tier": "观察作者", "angle": "更重要的是看新技术路线和海外出货，而不是单日股价波动。"},
                {"id": 4, "name": "全球宏观James", "avatar": "🌐", "tier": "成长作者", "angle": "海外需求和原材料价格波动会持续影响预期。"},
            ],
            "fundamental": {
                "summary": "核心变量不在于短期情绪，而在于全球份额、技术迭代和海外市场进度。",
                "metrics": [
                    {"label": "收入增速", "value": "18.6%", "note": "出口拉动明显"},
                    {"label": "毛利率", "value": "24.1%", "note": "原材料波动后修复"},
                    {"label": "研发占比", "value": "7.8%", "note": "维持高投入"},
                    {"label": "估值分位", "value": "36%", "note": "低于行业乐观期"},
                ],
                "thesis": [
                    "全球动力电池龙头地位仍稳固。",
                    "技术升级和海外布局决定中期估值空间。",
                    "要警惕行业价格竞争压缩利润率。",
                ],
            },
            "forecast": {
                "label": "基本面判断",
                "verdict": "继续观察",
                "confidence": "中",
                "band": "未来 1-2 个季度需要继续看价格战和新技术兑现。",
                "drivers": [
                    {"label": "技术路线", "score": "+2.0", "note": "新产品是正向变量"},
                    {"label": "价格竞争", "score": "-1.6", "note": "盈利承压"},
                    {"label": "海外出货", "score": "+1.5", "note": "中期支撑项"},
                ],
            },
        },
        "00700": {
            "code": "00700",
            "name": "腾讯控股",
            "market": "HK",
            "price": 388.40,
            "change": 5.60,
            "change_pct": 1.46,
            "industry": "港股互联网",
            "kline": build_kline_series("00700", 388.40),
            "authors": [
                {"id": 2, "name": "投资女神Lisa", "avatar": "💎", "tier": "种子作者", "angle": "广告、游戏和回购共同支撑估值修复，关键还是财报兑现。"},
                {"id": 2, "name": "港股研究员", "avatar": "🏙️", "tier": "观察作者", "angle": "这类资产更适合中期配置，而不是追逐情绪高点。"},
            ],
            "fundamental": {
                "summary": "估值修复逻辑仍在，核心看广告恢复、游戏流水和资本回报延续。",
                "metrics": [
                    {"label": "收入增速", "value": "9.8%", "note": "恢复中"},
                    {"label": "经营利润率", "value": "32.1%", "note": "效率改善"},
                    {"label": "回购强度", "value": "高", "note": "资本回报积极"},
                    {"label": "估值分位", "value": "28%", "note": "修复但未过热"},
                ],
                "thesis": [
                    "现金流和资产质量在港股互联网中仍属头部。",
                    "回购与业务恢复共同支撑估值中枢。",
                    "风险在于监管和宏观消费修复不及预期。",
                ],
            },
            "forecast": {
                "label": "基本面判断",
                "verdict": "偏积极",
                "confidence": "中高",
                "band": "若财报继续兑现，估值还有温和修复空间。",
                "drivers": [
                    {"label": "业务恢复", "score": "+2.1", "note": "广告与游戏改善"},
                    {"label": "股东回报", "score": "+1.9", "note": "回购支撑明确"},
                    {"label": "政策扰动", "score": "-0.8", "note": "仍需观察"},
                ],
            },
        },
        "688981": {
            "code": "688981",
            "name": "中芯国际",
            "market": "SH",
            "price": 46.52,
            "change": 1.18,
            "change_pct": 2.60,
            "industry": "半导体制造",
            "kline": build_kline_series("688981", 46.52),
            "authors": [
                {"id": 1, "name": "财经老王", "avatar": "👑", "tier": "种子作者", "angle": "要拆开看产能利用率、成熟制程景气和国产替代订单，不要只看情绪。"},
                {"id": 4, "name": "宏观策略师", "avatar": "🎯", "tier": "成长作者", "angle": "产业政策和资本开支周期决定中期想象空间。"},
            ],
            "fundamental": {
                "summary": "国产替代逻辑稳固，但盈利释放节奏仍依赖景气和产能利用率改善。",
                "metrics": [
                    {"label": "收入增速", "value": "14.1%", "note": "受益国产订单"},
                    {"label": "产能利用率", "value": "82%", "note": "仍在恢复"},
                    {"label": "资本开支", "value": "高位", "note": "扩产持续"},
                    {"label": "估值分位", "value": "49%", "note": "预期已反映部分利好"},
                ],
                "thesis": [
                    "国产替代是长期逻辑，订单确定性高。",
                    "短中期要看景气恢复与盈利兑现速度。",
                    "资本开支高、回报兑现慢会压制市场耐心。",
                ],
            },
            "forecast": {
                "label": "基本面判断",
                "verdict": "积极跟踪",
                "confidence": "中",
                "band": "更像中期产业趋势资产，短期波动会比较大。",
                "drivers": [
                    {"label": "国产替代", "score": "+2.6", "note": "长期主逻辑"},
                    {"label": "盈利兑现", "score": "+0.9", "note": "恢复中"},
                    {"label": "资本开支", "score": "-1.1", "note": "拖累利润释放"},
                ],
            },
        },
        "600036": {
            "code": "600036",
            "name": "招商银行",
            "market": "SH",
            "price": 41.86,
            "change": 0.22,
            "change_pct": 0.53,
            "industry": "银行",
            "kline": build_kline_series("600036", 41.86),
            "authors": [
                {"id": 4, "name": "全球宏观James", "avatar": "🌐", "tier": "成长作者", "angle": "利率环境和资产质量是银行股的核心框架。"},
                {"id": 3, "name": "量化老师陈明", "avatar": "📊", "tier": "成长作者", "angle": "这类资产更适合放在组合稳定器角色里看。"},
            ],
            "fundamental": {
                "summary": "核心看息差、资产质量与分红能力，作为组合稳定器价值仍在。",
                "metrics": [
                    {"label": "ROE", "value": "14.8%", "note": "银行中仍具优势"},
                    {"label": "不良率", "value": "0.96%", "note": "资产质量稳"},
                    {"label": "股息率", "value": "5.1%", "note": "防守价值明显"},
                    {"label": "估值分位", "value": "33%", "note": "偏低区间"},
                ],
                "thesis": [
                    "资产质量和零售能力构成核心护城河。",
                    "在低利率阶段，分红和稳健性更受重视。",
                    "息差继续承压会影响估值弹性。",
                ],
            },
            "forecast": {
                "label": "基本面判断",
                "verdict": "稳健配置",
                "confidence": "高",
                "band": "适合作为组合中的防守资产，预期收益更平稳。",
                "drivers": [
                    {"label": "股息支撑", "score": "+2.2", "note": "分红确定性强"},
                    {"label": "资产质量", "score": "+1.8", "note": "风险可控"},
                    {"label": "息差压力", "score": "-0.9", "note": "估值弹性有限"},
                ],
            },
        },
    }

def gen_news_feed():
    news = [
        {
            "title": "美联储6月议息会议前瞻：降息预期升温，市场如何定价？",
            "tag": "全球要闻",
            "time": "10分钟前",
            "hot": True,
            "source_group": "全球要闻",
            "why": "它会直接影响美元、港股互联网和大宗商品的估值锚，是当前最核心的宏观变量之一。",
        },
        {
            "title": "【深度】新能源车渗透率突破50%，产业链投资机会梳理",
            "tag": "自选股相关",
            "time": "32分钟前",
            "hot": True,
            "source_group": "自选股",
            "why": "你的自选股里有动力电池样本，且当前预警点正集中在价格竞争和技术路线验证。",
        },
        {
            "title": "高盛最新报告：A股估值修复空间测算",
            "tag": "全球要闻",
            "time": "1小时前",
            "hot": False,
            "source_group": "全球要闻",
            "why": "它决定科技成长板块当前估值是不是已经提前反映乐观预期，影响面广。",
        },
        {
            "title": "专家会议纪要：某头部消费品牌Q2经营数据点评",
            "tag": "大V关注趋势",
            "time": "2小时前",
            "hot": False,
            "source_group": "大V趋势",
            "why": "与大V近期关注的消费修复和高端白酒判断高度相关，适合作为租户知识延伸阅读。",
        },
        {
            "title": "另类数据：卫星图像显示主要港口吞吐量环比回升8%",
            "tag": "全球要闻",
            "time": "3小时前",
            "hot": False,
            "source_group": "全球要闻",
            "why": "它是宏观修复是否真正落地的交叉验证项，不是普通资讯，而是影响顺周期判断的旁证。",
        },
        {
            "title": "DeepSeek最新研究：AI算力需求2026年增速预测上调至180%",
            "tag": "大V关注趋势",
            "time": "4小时前",
            "hot": True,
            "source_group": "大V趋势",
            "why": "它和当前科技成长板块的核心主线一致，也会被大V方法模板优先引用为趋势依据。",
        },
    ]
    return news

def gen_revenue_trend():
    months = []
    base_date = datetime(2025, 7, 1)
    for i in range(12):
        d = base_date + timedelta(days=30*i)
        months.append({
            "month": d.strftime("%Y-%m"),
            "revenue": int(18000 + i * 5200 + random.randint(-1800, 2600)),
            "users": int(180 + i * 58 + random.randint(-12, 26)),
        })
    return months

def gen_user_segments():
    return [
        {"segment": "免费用户", "count": 880, "pct": 69.4},
        {"segment": "基础会员", "count": 214, "pct": 16.9},
        {"segment": "专业会员", "count": 128, "pct": 10.1},
        {"segment": "机构试点", "count": 34, "pct": 2.7},
        {"segment": "种子KOL", "count": 12, "pct": 0.9},
    ]


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                path TEXT NOT NULL,
                method TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                user_agent TEXT,
                referrer TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_created_at ON access_logs(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_ip ON access_logs(ip)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_path ON access_logs(path)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            "SELECT setting_key FROM app_settings WHERE setting_key = ?",
            (SITE_CONFIG_KEY,),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                (
                    SITE_CONFIG_KEY,
                    json.dumps(DEFAULT_SITE_CONFIG, ensure_ascii=False),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        conn.commit()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def _merge_site_config(base, override):
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_site_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_site_config():
    cached = g.get("site_config")
    if cached is not None:
        return cached
    db = get_db()
    row = db.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = ?",
        (SITE_CONFIG_KEY,),
    ).fetchone()
    config = copy.deepcopy(DEFAULT_SITE_CONFIG)
    if row and row["setting_value"]:
        try:
            stored = json.loads(row["setting_value"])
            if isinstance(stored, dict):
                config = _merge_site_config(config, stored)
        except Exception:
            app.logger.exception("Failed to parse site config")
    config = normalize_site_config(config)
    g.site_config = config
    return config


def save_site_config(config):
    merged = normalize_site_config(config)
    db = get_db()
    db.execute(
        """
        INSERT INTO app_settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at = excluded.updated_at
        """,
        (
            SITE_CONFIG_KEY,
            json.dumps(merged, ensure_ascii=False),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    db.commit()
    g.site_config = merged
    return merged


def load_forecast_workflow_graph():
    cached = g.get("forecast_workflow_graph")
    if cached is not None:
        return cached
    db = get_db()
    row = db.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = ?",
        (FORECAST_WORKFLOW_KEY,),
    ).fetchone()
    graph = build_default_forecast_workflow_graph()
    if row and row["setting_value"]:
        try:
            stored = json.loads(row["setting_value"])
            graph = normalize_forecast_workflow_graph(stored)
        except Exception:
            app.logger.exception("Failed to parse forecast workflow graph")
    g.forecast_workflow_graph = graph
    return graph


def save_forecast_workflow_graph(graph):
    normalized = normalize_forecast_workflow_graph(graph)
    db = get_db()
    db.execute(
        """
        INSERT INTO app_settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at = excluded.updated_at
        """,
        (
            FORECAST_WORKFLOW_KEY,
            json.dumps(normalized, ensure_ascii=False),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    db.commit()
    g.forecast_workflow_graph = normalized
    return normalized


@app.context_processor
def inject_site_config():
    config = get_site_config()
    return {
        "site_config": config,
        "brand_config": get_platform_brand(config),
        "tenant_configs": get_tenant_configs(config),
        "default_tenant_slug": get_default_tenant_slug(config),
    }


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def is_authenticated():
    return session.get(AUTH_SESSION_KEY) is True


def is_password_gate_enabled():
    return bool(get_site_config().get("password_gate_enabled", True))


def safe_next_target(target):
    if not target:
        return "/"
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return "/"
    if not target.startswith("/") or target.startswith("//"):
        return "/"
    return target


def get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()
    return request.remote_addr or "unknown"


def should_log_request():
    return not request.path.startswith("/static/") and not request.path.startswith("/api/")


def record_access(response):
    if not should_log_request():
        return response
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO access_logs (ip, path, method, status_code, created_at, user_agent, referrer)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                get_client_ip(),
                request.path,
                request.method,
                response.status_code,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                request.headers.get("User-Agent", ""),
                request.headers.get("Referer", ""),
            ),
        )
        db.commit()
    except Exception:
        app.logger.exception("Failed to write access log")
    return response


@app.before_request
def require_password_gate():
    if not is_password_gate_enabled():
        return None
    public_paths = {"/login", "/unlock", "/logout"}
    if request.path.startswith("/static/") or request.path in public_paths:
        return None
    if is_authenticated():
        return None
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "auth_required"}), 401
    return redirect(url_for("login", next=safe_next_target(request.full_path.rstrip("?"))))


@app.after_request
def log_access(response):
    return record_access(response)

# Routes
@app.route("/login", methods=["GET"])
def login():
    next_target = safe_next_target(request.args.get("next", "/"))
    if not is_password_gate_enabled():
        return redirect(next_target)
    return render_template("login.html", next_target=next_target, error=None)


@app.route("/unlock", methods=["POST"])
def unlock():
    next_target = safe_next_target(request.form.get("next", "/"))
    if not is_password_gate_enabled():
        session[AUTH_SESSION_KEY] = True
        session.permanent = True
        return redirect(next_target)
    password = request.form.get("password", "")
    if not compare_digest(password, AUTH_PASSWORD):
        return render_template("login.html", next_target=next_target, error="密码错误")
    session[AUTH_SESSION_KEY] = True
    session.permanent = True
    return redirect(next_target)


@app.route("/logout")
def logout():
    session.pop(AUTH_SESSION_KEY, None)
    if not is_password_gate_enabled():
        return redirect("/")
    return redirect(url_for("login"))


@app.route("/")
def index():
    config = get_site_config()
    tenants = get_tenant_configs(config)
    default_tenant = get_tenant_by_slug(get_default_tenant_slug(config), config)
    return render_template("index.html", brand=get_platform_brand(config), tenants=tenants, default_tenant=default_tenant)

@app.route("/h5")
def h5():
    tenant = get_active_tenant_from_request()
    market = gen_market_data()
    news = gen_news_feed()
    macro_indicators = gen_macro_indicators()
    feed_boards = gen_feed_boards(market)
    watchlist_details = gen_watchlist_details()
    return render_template(
        "h5.html",
        market=market,
        news=news,
        macro_indicators=macro_indicators,
        feed_boards=feed_boards,
        watchlist_details=watchlist_details,
        active_tenant=tenant,
    )

@app.route("/admin")
def admin():
    kols = gen_kol_data()
    segments = gen_user_segments()
    access_stats = get_access_summary()
    return render_template(
        "admin.html",
        kols=kols,
        segments=segments,
        access_stats=access_stats,
        brand=get_platform_brand(),
        tenants=get_tenant_configs(),
        default_tenant=get_tenant_by_slug(get_default_tenant_slug()),
    )

@app.route("/kol-workbench")
def kol_workbench():
    tenant = get_active_tenant_from_request()
    workbench = gen_kol_workbench(tenant)
    return render_template("kol_workbench.html", workbench=workbench, brand=get_platform_brand(), active_tenant=tenant)


@app.route("/tenant/<tenant_slug>")
def tenant_portal(tenant_slug):
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or tenant["slug"] != tenant_slug:
        abort(404)
    portal = build_tenant_portal_payload(tenant)
    return render_template("tenant_portal.html", portal=portal, brand=get_platform_brand(), active_tenant=tenant)

@app.route("/dashboard")
def dashboard():
    tenant = get_active_tenant_from_request()
    return redirect(url_for("tenant_portal", tenant_slug=tenant["slug"]))

# API endpoints
@app.route("/api/funnel")
def api_funnel():
    return jsonify(gen_funnel_data())

@app.route("/api/channels")
def api_channels():
    return jsonify(gen_channel_data())

@app.route("/api/kols")
def api_kols():
    return jsonify(gen_kol_data())

@app.route("/api/revenue")
def api_revenue():
    return jsonify(gen_revenue_trend())

@app.route("/api/segments")
def api_segments():
    return jsonify(gen_user_segments())

@app.route("/api/market")
def api_market():
    return jsonify(gen_market_data())


@app.route("/api/watchlist")
def api_watchlist():
    return jsonify(gen_market_data())


@app.route("/api/watchlist/<stock_code>")
def api_watchlist_detail(stock_code):
    details = gen_watchlist_details()
    return jsonify(details.get(stock_code, {
        "code": stock_code,
        "name": stock_code,
        "market": "CN",
        "price": 0,
        "change": 0,
        "change_pct": 0,
        "industry": "待识别",
        "kline": [],
        "authors": [],
        "fundamental": {
            "summary": "暂无样本数据，可通过 Hermes 继续补充。",
            "metrics": [],
            "thesis": [],
        },
        "forecast": {
            "label": "基本面判断",
            "verdict": "待分析",
            "confidence": "低",
            "band": "等待更多财务、行业和作者样本。",
            "drivers": [],
        },
    }))


def get_access_summary():
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS c FROM access_logs").fetchone()["c"]
    unique_ips = db.execute("SELECT COUNT(DISTINCT ip) AS c FROM access_logs").fetchone()["c"]
    today = datetime.now().strftime("%Y-%m-%d")
    today_count = db.execute(
        "SELECT COUNT(*) AS c FROM access_logs WHERE created_at >= ?",
        (f"{today} 00:00:00",),
    ).fetchone()["c"]
    path_rows = db.execute(
        """
        SELECT path, COUNT(*) AS c
        FROM access_logs
        GROUP BY path
        ORDER BY c DESC, path ASC
        LIMIT 10
        """
    ).fetchall()
    ip_rows = db.execute(
        """
        SELECT ip, COUNT(*) AS c
        FROM access_logs
        GROUP BY ip
        ORDER BY c DESC, ip ASC
        LIMIT 10
        """
    ).fetchall()
    daily_rows = db.execute(
        """
        SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS c
        FROM access_logs
        GROUP BY day
        ORDER BY day DESC
        LIMIT 14
        """
    ).fetchall()
    recent_rows = db.execute(
        """
        SELECT ip, path, method, status_code, created_at
        FROM access_logs
        ORDER BY id DESC
        LIMIT 50
        """
    ).fetchall()
    return {
        "summary": {
            "total": total,
            "unique_ips": unique_ips,
            "today": today_count,
            "paths": len(path_rows),
        },
        "top_paths": [{"path": r["path"], "count": r["c"]} for r in path_rows],
        "top_ips": [{"ip": r["ip"], "count": r["c"]} for r in ip_rows],
        "daily_counts": [{"day": r["day"], "count": r["c"]} for r in reversed(daily_rows)],
        "recent_logs": [dict(r) for r in recent_rows],
    }


@app.route("/api/admin/access-stats")
def api_admin_access_stats():
    return jsonify(get_access_summary())


@app.route("/api/admin/access-logs")
def api_admin_access_logs():
    limit = min(int(request.args.get("limit", 50)), 200)
    db = get_db()
    rows = db.execute(
        """
        SELECT ip, path, method, status_code, created_at, user_agent, referrer
        FROM access_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/site-config")
def api_site_config():
    return jsonify(get_site_config())


@app.route("/api/admin/site-config", methods=["GET", "POST"])
def api_admin_site_config():
    if request.method == "GET":
        return jsonify(get_site_config())
    payload = request.get_json(silent=True) or {}
    current = get_site_config()
    feature_flags = dict(current.get("feature_flags", {}))
    incoming_flags = payload.get("feature_flags", {})
    for key in feature_flags:
        if key in incoming_flags:
            feature_flags[key] = bool(incoming_flags[key])
    next_config = _merge_site_config(
        current,
        {
            "default_theme": payload.get("default_theme", current.get("default_theme", "light")),
            "default_accent": payload.get("default_accent", current.get("default_accent", "blue")),
            "password_gate_enabled": bool(payload.get("password_gate_enabled", current.get("password_gate_enabled", True))),
            "brand": payload.get("brand", current.get("brand", {})),
            "default_tenant_slug": payload.get("default_tenant_slug", current.get("default_tenant_slug")),
            "tenants": payload.get("tenants", current.get("tenants", [])),
            "feature_flags": feature_flags,
        },
    )
    return jsonify({"success": True, "site_config": save_site_config(next_config)})


@app.route("/api/admin/forecast-config")
def api_admin_forecast_config():
    graph = load_forecast_workflow_graph()
    return jsonify(
        {
            "ok": True,
            "config": workflow_graph_to_tuning(graph),
            "workflow_meta": build_forecast_workflow_meta(graph),
        }
    )


@app.route("/api/admin/forecast-config", methods=["POST"])
def api_save_admin_forecast_config():
    body = request.get_json(silent=True) or {}
    if body.get("reset_default"):
        default_graph = save_forecast_workflow_graph(build_default_forecast_workflow_graph())
        return jsonify(
            {
                "ok": True,
                "config": workflow_graph_to_tuning(default_graph),
                "workflow_meta": build_forecast_workflow_meta(default_graph),
            }
        )
    raw_graph = body.get("graph")
    raw_config = body.get("config", {})
    if raw_graph is None and not isinstance(raw_config, dict):
        return jsonify({"ok": False, "error": "graph or config must be provided"}), 400
    base_graph = load_forecast_workflow_graph()
    if raw_graph is None:
        graph_payload = dict(base_graph)
        graph_payload["tuning"] = dict(raw_config)
    else:
        graph_payload = raw_graph
        if isinstance(raw_config, dict) and raw_config:
            graph_payload = dict(raw_graph) if isinstance(raw_graph, dict) else {}
            graph_payload["tuning"] = dict(raw_config)
    normalized_graph = normalize_forecast_workflow_graph(graph_payload)
    saved_graph = save_forecast_workflow_graph(normalized_graph)
    normalized = workflow_graph_to_tuning(saved_graph)
    return jsonify(
        {
            "ok": True,
            "config": normalized,
            "workflow_meta": build_forecast_workflow_meta(saved_graph),
        }
    )

@app.route("/api/ai-analysis", methods=["POST"])
def api_ai_analysis():
    from flask import request
    topic = request.json.get("topic", "市场分析")
    responses = {
        "宏观经济": "基于最新宏观数据，美联储降息预期升温，国内货币政策保持宽松。建议关注利率敏感型资产，适当增配债券及高股息板块。风险提示：地缘政治不确定性仍存。",
        "A股策略": "当前A股估值处于历史中位偏低水平，外资持续流入信号积极。科技成长与高股息防御双主线并行，建议均衡配置。关注Q2财报季业绩超预期机会。",
        "港股机会": "港股互联网板块受益于AI应用落地加速，估值修复逻辑清晰。南向资金持续净流入，流动性改善。重点关注平台经济政策边际变化。",
        "新能源": "新能源车渗透率突破50%里程碑，产业链进入成熟期竞争。电池技术迭代加速，固态电池商业化时间表前移。关注具备技术壁垒的核心零部件企业。",
        "AI科技": "AI算力需求持续超预期，国产替代加速推进。DeepSeek等国内大模型商业化落地提速，应用层投资机会涌现。关注算力基础设施及AI应用双主线。",
    }
    result = responses.get(topic, f"针对{topic}的深度分析：基于洞见智研平台整合的券商研报、专家会议纪要及另类数据，当前该领域呈现结构性机会。建议结合个人风险偏好，参考试点作者的研究框架后做出自己的判断。")
    return jsonify({"topic": topic, "analysis": result, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "source": "洞见智研AI分析引擎 (DeepSeek + Kimi 2.6)"})

def gen_community_posts():
    return [
        {"id":1,"author":"财经老王","avatar":"👑","tier":"试点作者","badge":"种子合作作者","platform":"微信社群","time":"8分钟前",
         "content":"今天美联储会议纪要出来后，市场会先交易降息预期，但更关键的还是订单兑现和风险偏好是否持续。A股科技板块适合继续跟踪，不建议用单一事件做过度判断。","likes":142,"comments":37,"shares":16,"tags":["宏观","A股","AI"],"hot":True,"points_reward":20},
        {"id":2,"author":"投资女神Lisa","avatar":"💎","tier":"试点作者","badge":"种子合作作者","platform":"内容合作","time":"23分钟前",
         "content":"港股互联网仍在估值修复区间，南向资金是信号，但最终还得看业绩验证。更适合做中期框架研究，而不是短线冲动交易。","likes":118,"comments":34,"shares":11,"tags":["港股","互联网"],"hot":True,"points_reward":20},
        {"id":3,"author":"宏观策略师","avatar":"🎯","tier":"试点作者","badge":"成长作者","platform":"微信社群","time":"1小时前",
         "content":"分享一个另类数据视角：平台监测到长三角工业园区夜间灯光指数环比回升，说明工业活动有修复迹象。这个信号还需要和 PMI 以及货运数据继续交叉验证。","likes":96,"comments":23,"shares":12,"tags":["另类数据","宏观","顺周期"],"hot":False,"points_reward":15},
        {"id":4,"author":"量化小白","avatar":"📊","tier":"认证用户","badge":"研究样本","platform":"小红书","time":"2小时前",
         "content":"用 Hermes 跑了一轮新能源板块因子筛选，发现固态电池相关公司的专利信号在抬升，但价格还没有完全反映。更适合先做样本跟踪。","likes":58,"comments":19,"shares":9,"tags":["量化","新能源","固态电池"],"hot":False,"points_reward":10},
        {"id":5,"author":"港股研究员","avatar":"🏙️","tier":"认证用户","badge":"研究样本","platform":"转介绍","time":"3小时前",
         "content":"刚参加完一场消费品牌专家电话会，Q2 动销数据略好于预期，渠道库存也在改善。还需要继续确认持续性，但这类一手纪要对研究判断很有帮助。","likes":46,"comments":12,"shares":6,"tags":["消费","专家纪要"],"hot":False,"points_reward":10},
        {"id":6,"author":"普通用户_阿明","avatar":"😊","tier":"普通","badge":"","platform":"","time":"4小时前",
         "content":"第一次用洞见智研的Hermes分析工具，选了「研报精读」模式，把高盛的A股报告喂进去，AI给出的摘要和关键数据提取真的很准。比自己读省了至少2小时。积分也涨了，感觉很值！","likes":45,"comments":18,"shares":8,"tags":["使用体验","Hermes"],"hot":False,"points_reward":10},
    ]

def gen_community_events():
    return [
        {"id":1,"title":"【作者直播】财经老王：下半年A股跟踪框架","type":"直播","date":"2026-05-22 20:00","host":"财经老王","participants":128,"points":100,"status":"报名中","badge":"🔴 即将开始"},
        {"id":2,"title":"【研报解读挑战赛】最佳分析师评选","type":"活动","date":"2026-05-20 ~ 06-05","host":"洞见智研官方","participants":214,"points":500,"status":"进行中","badge":"🏆 进行中"},
        {"id":3,"title":"【专家会议】新能源产业链Q2展望","type":"会议","date":"2026-05-24 14:00","host":"行业专家团","participants":68,"points":200,"status":"报名中","badge":"🎙️ 专家"},
        {"id":4,"title":"【积分翻倍】本周发帖积分×2","type":"活动","date":"2026-05-20 ~ 05-26","host":"洞见智研官方","participants":186,"points":0,"status":"进行中","badge":"⚡ 限时"},
    ]

def gen_user_profile():
    return {
        "name": "投研达人_小陈",
        "level": 4,
        "level_name": "资深分析师",
        "points": 1260,
        "points_to_next": 5000,
        "compute_credits": 36,
        "badges": ["早鸟用户","研报体验官","产品共创"],
        "posts": 8,
        "likes_received": 67,
        "following": 12,
        "followers": 14,
        "tier": "专业会员",
    }

def gen_points_rules():
    return [
        {"action":"每日登录","points":5,"limit":"每日1次"},
        {"action":"发布帖子","points":10,"limit":"每日5次"},
        {"action":"帖子获赞","points":2,"limit":"无上限"},
        {"action":"参与活动","points":50,"limit":"每活动1次"},
        {"action":"邀请好友注册","points":100,"limit":"每人1次"},
        {"action":"完成AI分析任务","points":20,"limit":"每日3次"},
        {"action":"作者帖子互动","points":5,"limit":"每日10次"},
        {"action":"分享内容到社交平台","points":15,"limit":"每日3次"},
    ]

def gen_compute_exchange():
    return [
        {"name":"Hermes基础算力包","credits":50,"compute":"100次AI分析","desc":"适合日常使用"},
        {"name":"Hermes专业算力包","credits":200,"compute":"500次AI分析","desc":"适合深度研究"},
        {"name":"Hermes量化算力包","credits":500,"compute":"1500次AI分析+量化回测","desc":"适合量化策略"},
        {"name":"作者直播席位","credits":100,"compute":"1场专属直播","desc":"与试点作者实时互动"},
        {"name":"专家会议席位","credits":200,"compute":"1场专家电话会议","desc":"一手行业信息"},
    ]

HERMES_MODES = {
    "研报精读": {
        "icon": "📋",
        "desc": "上传或选择研报，AI提炼核心观点、关键数据、风险提示",
        "steps": ["选择研报来源", "选择分析深度", "获取结构化摘要"],
        "options": [
            {"label": "高盛 A股策略报告", "tag": "券商研报"},
            {"label": "中金 新能源深度", "tag": "券商研报"},
            {"label": "摩根士丹利 港股展望", "tag": "券商研报"},
            {"label": "国泰君安 AI算力专题", "tag": "券商研报"},
        ]
    },
    "专家纪要速读": {
        "icon": "🎙️",
        "desc": "专家会议纪要AI摘要，提炼核心观点和数据",
        "steps": ["选择行业方向", "选择时间范围", "获取纪要摘要"],
        "options": [
            {"label": "新能源产业链", "tag": "行业"},
            {"label": "AI与算力", "tag": "行业"},
            {"label": "消费复苏", "tag": "行业"},
            {"label": "医药生物", "tag": "行业"},
        ]
    },
    "另类数据解读": {
        "icon": "🛰️",
        "desc": "卫星图像、消费数据、舆情等另类数据的AI解读",
        "steps": ["选择数据类型", "选择分析维度", "获取信号解读"],
        "options": [
            {"label": "卫星工业活动指数", "tag": "另类数据"},
            {"label": "消费热力图", "tag": "另类数据"},
            {"label": "社交媒体情绪", "tag": "另类数据"},
            {"label": "港口吞吐量", "tag": "另类数据"},
        ]
    },
    "投资组合诊断": {
        "icon": "🔬",
        "desc": "输入持仓，AI分析风险敞口、相关性、优化建议",
        "steps": ["输入持仓结构", "选择风险偏好", "获取诊断报告"],
        "options": [
            {"label": "偏成长型组合", "tag": "风格"},
            {"label": "偏价值型组合", "tag": "风格"},
            {"label": "均衡配置组合", "tag": "风格"},
            {"label": "高股息防御组合", "tag": "风格"},
        ]
    },
    "市场情绪扫描": {
        "icon": "📡",
        "desc": "实时扫描市场情绪指标，识别极端情绪和拐点信号",
        "steps": ["选择市场范围", "选择情绪维度", "获取情绪报告"],
        "options": [
            {"label": "A股全市场", "tag": "市场"},
            {"label": "港股市场", "tag": "市场"},
            {"label": "美股科技板块", "tag": "市场"},
            {"label": "大宗商品", "tag": "市场"},
        ]
    },
    "量化因子筛选": {
        "icon": "⚙️",
        "desc": "基于多因子模型筛选股票，支持自定义因子权重",
        "steps": ["选择因子组合", "设置筛选条件", "获取股票列表"],
        "options": [
            {"label": "动量+质量因子", "tag": "因子"},
            {"label": "低估值+高股息", "tag": "因子"},
            {"label": "成长+盈利改善", "tag": "因子"},
            {"label": "技术面突破", "tag": "因子"},
        ]
    },
}

HERMES_RESPONSES = {
    "研报精读_高盛 A股策略报告": "【高盛A股策略报告精读】\n\n核心观点：维持A股「超配」评级，目标点位上调至4200点。\n\n关键数据：\n• 外资净流入连续8周正值，累计+420亿\n• 企业盈利预测上调3.2%\n• 估值PE 12.8x，低于历史均值15%\n\n主要逻辑：政策宽松周期+盈利复苏共振，科技板块受益AI应用落地。\n\n风险提示：地缘政治、汇率波动、房地产尾部风险。\n\n洞见智研评级：★★★★☆ 高质量研报",
    "专家纪要速读_新能源产业链": "【新能源产业链专家纪要摘要】\n\n会议时间：2026年5月18日\n参与专家：3位产业链核心专家\n\n核心观点：\n• 固态电池量产时间表提前至2027年Q3\n• 碳酸锂价格底部已现，Q3有望反弹\n• 海外市场拓展加速，欧洲工厂投产在即\n\n数据亮点：\n• 某头部电池企业Q2出货量环比+18%\n• 储能业务占比提升至35%\n\n投资含义：产业链底部已过，关注技术壁垒强的核心零部件企业。",
    "另类数据解读_卫星工业活动指数": "【卫星工业活动指数解读】\n\n数据时间：2026年5月第3周\n覆盖范围：长三角、珠三角、京津冀三大工业区\n\n核心信号：\n• 夜间灯光指数：+6.2%（环比）\n• 工厂烟囱热成像活跃度：+4.8%\n• 停车场占用率（工业园区）：+9.1%\n\n综合判断：工业活动明显回暖，领先PMI约2-3周。预计5月PMI数据将超预期。\n\n交叉验证：与货运数据、用电量数据形成三重共振，信号可靠性高。\n\n洞见智研信号强度：🟢🟢🟢🟢⚪ 强烈看多",
    "市场情绪扫描_A股全市场": "【A股市场情绪扫描报告】\n\n扫描时间：2026-05-20 实时\n\n情绪指标：\n• 恐贪指数：62（偏贪婪区间）\n• 融资余额：+3.2%（周环比）\n• 北向资金：今日净流入+28亿\n• 涨停板数量：47只（近期高位）\n\n情绪解读：市场处于温和乐观状态，未到极度贪婪。短期动能较强，但需警惕情绪过热后的回调风险。\n\n历史对比：当前情绪水平对应历史上未来1个月正收益概率约68%。\n\n操作建议：可适度参与，但控制仓位，避免追高。",
}

# New routes
@app.route("/api/community/posts")
def api_community_posts():
    return jsonify(gen_community_posts())

@app.route("/api/community/events")
def api_community_events():
    return jsonify(gen_community_events())

@app.route("/api/community/like", methods=["POST"])
def api_community_like():
    post_id = request.json.get("post_id")
    return jsonify({"success": True, "post_id": post_id, "points_earned": 2})

@app.route("/api/user/profile")
def api_user_profile():
    return jsonify(gen_user_profile())

@app.route("/api/user/points-rules")
def api_points_rules():
    return jsonify(gen_points_rules())

@app.route("/api/user/compute-exchange")
def api_compute_exchange():
    return jsonify(gen_compute_exchange())

@app.route("/api/hermes/modes")
def api_hermes_modes():
    return jsonify(list(HERMES_MODES.keys()))

@app.route("/api/hermes/mode-detail")
def api_hermes_mode_detail():
    mode = request.args.get("mode", "研报精读")
    return jsonify(HERMES_MODES.get(mode, {}))

@app.route("/api/hermes/analyze", methods=["POST"])
def api_hermes_analyze():
    mode = request.json.get("mode", "研报精读")
    option = request.json.get("option", "")
    key = f"{mode}_{option}"
    result = HERMES_RESPONSES.get(key, f"【{mode} · {option}】\n\n基于洞见智研平台整合的多维度数据，AI已完成深度分析。\n\n核心发现：该领域当前呈现结构性机会，关键指标向好。建议结合个人风险偏好，参考试点作者的研究框架后做出自己的判断。\n\n数据来源：券商研报库 + 专家纪要库 + 另类数据库\nAI引擎：DeepSeek R2 + Kimi 2.6 RAG架构\n分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return jsonify({
        "mode": mode,
        "option": option,
        "result": result,
        "compute_used": 1,
        "points_earned": 20,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })

def gen_dm_conversations():
    return [
        {"id":1,"kol_name":"财经老王","kol_avatar":"👑","tier":"种子作者","last_msg":"好的，我周四直播会详细讲这个方向，记得来看","time":"5分钟前","unread":1,"vip_only":False},
        {"id":2,"kol_name":"投资女神Lisa","kol_avatar":"💎","tier":"种子作者","last_msg":"港股互联网的配置建议我已经发到专属频道了","time":"2小时前","unread":0,"vip_only":False},
        {"id":3,"kol_name":"量化老师陈明","kol_avatar":"📊","tier":"成长作者","last_msg":"[付费内容] 本周多因子模型调仓建议","time":"昨天","unread":0,"vip_only":True},
        {"id":4,"kol_name":"全球宏观James","kol_avatar":"🌐","tier":"成长作者","last_msg":"美联储会议纪要解读已更新，查看详情","time":"昨天","unread":0,"vip_only":False},
        {"id":5,"kol_name":"新能源猎手阿强","kol_avatar":"⚡","tier":"观察作者","last_msg":"固态电池调研纪要整理好了，分享给你","time":"3天前","unread":0,"vip_only":False},
    ]

def gen_dm_messages(kol_id):
    conversations = {
        1: [
            {"id":1,"sender":"kol","content":"欢迎关注我的专属频道！我会在这里分享一些不方便公开发的深度观点。","time":"2026-05-18 09:00","type":"text"},
            {"id":2,"sender":"user","content":"老王好！想请教一下，AI算力板块现在还能追吗？感觉涨了不少了","time":"2026-05-18 10:30","type":"text"},
            {"id":3,"sender":"kol","content":"好问题。短期确实有些过热，但中长期逻辑没变。我的建议是分批建仓，不要一把梭。具体标的我周四直播会讲。","time":"2026-05-18 11:00","type":"text"},
            {"id":4,"sender":"user","content":"明白，那我先建1/3仓位，等回调再加","time":"2026-05-20 08:15","type":"text"},
            {"id":5,"sender":"kol","content":"好的，我周四直播会详细讲这个方向，记得来看","time":"2026-05-20 08:20","type":"text"},
        ],
        2: [
            {"id":1,"sender":"kol","content":"Hi～欢迎加入我的专属圈子！港股互联网是我的核心研究方向，有问题随时问。","time":"2026-05-17 14:00","type":"text"},
            {"id":2,"sender":"user","content":"Lisa姐，南向资金最近流入很多，是不是该加仓港股了？","time":"2026-05-19 09:00","type":"text"},
            {"id":3,"sender":"kol","content":"港股互联网的配置建议我已经发到专属频道了","time":"2026-05-20 10:00","type":"text"},
            {"id":4,"sender":"kol","content":"简单说：当前估值20%分位，南向连续14天净买入，我觉得可以加到标配+5%。但注意分散，别只买一只。","time":"2026-05-20 10:02","type":"text"},
        ],
        3: [
            {"id":1,"sender":"kol","content":"欢迎！我的频道主要分享量化策略和因子研究，每周更新调仓建议。","time":"2026-05-15 09:00","type":"text"},
            {"id":2,"sender":"kol","content":"[付费内容] 本周多因子模型调仓建议","time":"2026-05-19 20:00","type":"paid","price":50,"preview":"本周价值因子持续占优，动量因子衰减...（解锁查看完整内容）"},
        ],
    }
    return conversations.get(kol_id, [
        {"id":1,"sender":"kol","content":"欢迎关注！有投研问题随时交流。","time":"2026-05-18 09:00","type":"text"},
    ])

def gen_kol_workbench(tenant=None):
    tenant = tenant or get_tenant_by_slug()
    is_lisa = tenant["slug"] == "lisa"
    watchlist_details_map = gen_watchlist_details()
    kol_name = tenant["advisor"]
    kol_avatar = tenant.get("logo_mark") or "👑"
    base_followers = 86000 if is_lisa else 128000
    base_vip = 29 if is_lisa else 36
    base_revenue = 14200 if is_lisa else 18600
    revenue_change = 6.4 if is_lisa else 8.5
    unread_messages = 5 if is_lisa else 7
    pending_replies = 2 if is_lisa else 3
    today_views = 540 if is_lisa else 680
    engagement_rate = 7.6 if is_lisa else 6.8
    watchlist_focus = ["腾讯控股", "美团-W", "阿里巴巴-W"] if is_lisa else ["中芯国际", "腾讯控股", "贵州茅台"]
    fund_cells = (
        [
            {"title": "南向资金", "value": "连续净流入", "prompt": "跟踪南向资金连续性与港股互联网情绪"},
            {"title": "回购节奏", "value": "持续兑现", "prompt": "跟踪腾讯和头部互联网平台回购力度"},
            {"title": "财报验证", "value": "等待披露", "prompt": "跟踪财报窗口的估值与盈利兑现"},
            {"title": "平台政策", "value": "边际友好", "prompt": "跟踪平台经济监管边际变化"},
        ]
        if is_lisa
        else [
            {"title": "美联储路径", "value": "偏鸽", "prompt": "跟踪美联储降息路径与风险资产影响"},
            {"title": "港股互联网", "value": "估值修复中", "prompt": "跟踪港股互联网回购、财报与估值带"},
            {"title": "AI 订单兑现", "value": "继续验证", "prompt": "跟踪 AI 算力订单兑现和利润率"},
            {"title": "增量资金", "value": "连续净流入", "prompt": "跟踪南向和北向资金的连续性"},
        ]
    )
    return {
        "tenant": tenant,
        "kol_name": kol_name,
        "kol_avatar": kol_avatar,
        "tier": tenant["tier"],
        "watchlist_details": watchlist_details_map,
        "entry_points": [
            {
                "label": "H5 前台演示",
                "url": f"/h5?tenant={tenant['slug']}",
                "desc": f"查看普通投资者和大V在 H5 里实际看到的 {tenant['name']} Hermes、复盘、知识和自选股路径。"
            },
            {
                "label": "租户门户",
                "url": f"/tenant/{tenant['slug']}",
                "desc": f"查看 {tenant['advisor']} 对外的专属租户门户，包括品牌介绍与 Web 化 Dashboard。"
            },
            {
                "label": "纯 Admin 后台",
                "url": "/admin?section=kols",
                "desc": "查看平台侧的大V租户管理、能力开关、一致性巡检和审计入口。"
            },
        ],
        "stats": {
            "total_followers": base_followers,
            "vip_subscribers": base_vip,
            "monthly_revenue": base_revenue,
            "revenue_change": revenue_change,
            "unread_messages": unread_messages,
            "pending_replies": pending_replies,
            "today_views": today_views,
            "engagement_rate": engagement_rate,
        },
        "recent_fans": [
            {"name":"投研达人_小陈","time":"5分钟前","msg":f"{kol_name} 老师，想看最新核心指标版。","tier":"专业会员"},
            {"name":"价值猎人小林","time":"23分钟前","msg":is_lisa and "请问港股互联网还能继续配吗？" or "请问港股互联网怎么看？","tier":"基础会员"},
            {"name":"量化新手_阿明","time":"1小时前","msg":"想学习多因子模型，有推荐吗？","tier":"免费用户"},
            {"name":"机构用户_张总","time":"2小时前","msg":"能否安排一次闭门交流？","tier":"机构试点"},
            {"name":"小白投资者","time":"3小时前","msg":"新能源板块现在能入吗？","tier":"基础会员"},
        ],
        "broadcast_history": [
            {"id":1,"content":is_lisa and "本周港股互联网更新：继续看南向资金和回购兑现" or "本周策略更新：科技板块适合继续跟踪，重点看 AI 算力订单兑现","time":"2026-05-20 08:00","reach":92,"open_rate":68},
            {"id":2,"content":is_lisa and "价值提醒：财报前估值修复较快，注意不要只盯单一平台" or "宏观提醒：美联储纪要偏鸽，但还要等国内资金面确认","time":"2026-05-19 22:30","reach":108,"open_rate":82},
            {"id":3,"content":"周末复盘：本周操作回顾与下周观察重点","time":"2026-05-18 18:00","reach":76,"open_rate":55},
        ],
        "message_center": {
            "summary": "消息板块不仅包含粉丝给大V的提问，也包含大V回复粉丝后的追问，以及复盘发布后需要第一时间触达的粉丝提醒。",
            "items": [
                {
                    "name": "投研达人_小陈",
                    "type": "粉丝提问",
                    "time": "5分钟前",
                    "content": is_lisa and "港股互联网还能继续配吗？想看你按 Hermes 价值框架压缩后的短版结论。" or "AI 算力还能继续跟吗？想看你按 Hermes 基本面判断后的短版结论。",
                    "status": "待回复",
                },
                {
                    "name": "复盘发布提醒",
                    "type": "系统消息",
                    "time": "12分钟前",
                    "content": "你刚发布的日复盘已经推送给 92 位高频粉丝，首批打开率 41%。",
                    "status": "已送达",
                },
                {
                    "name": "价值猎人小林",
                    "type": "追问消息",
                    "time": "23分钟前",
                    "content": is_lisa and "最新那篇港股复盘我看完了，想继续问腾讯和美团的回购节奏怎么拆。" or "港股互联网那篇复盘我看完了，想继续问腾讯回购节奏和估值带怎么看。",
                    "status": "待跟进",
                },
            ],
        },
        "fan_management": {
            "summary": "这里看的是大V自己的粉丝分层，不是平台总用户。重点管理高频互动、付费意向、机构试点和沉默粉丝的经营动作。",
            "stats": {
                "total_fans": base_followers,
                "new_fans_7d": 1420 if is_lisa else 1860,
                "active_fans_30d": 5120 if is_lisa else 6840,
                "paying_fans": 248 if is_lisa else 312,
            },
            "fans": [
                {"name": "投研达人_小陈", "tier": "专业会员", "source": "H5 Hermes", "joined": "2026-05-20", "value": "高频提问", "status": "活跃"},
                {"name": "价值猎人小林", "tier": "基础会员", "source": "复盘转化", "joined": "2026-04-16", "value": "高频复盘阅读", "status": "待升级"},
                {"name": "机构用户_张总", "tier": "机构试点", "source": "闭门交流", "joined": "2026-03-08", "value": "高价值线索", "status": "重点跟进"},
                {"name": "小白投资者", "tier": "基础会员", "source": "群发助手", "joined": "2026-05-28", "value": "新粉", "status": "观察中"},
                {"name": "量化新手_阿明", "tier": "免费用户", "source": "社区帖子", "joined": "2026-05-03", "value": "低频互动", "status": "待激活"},
            ],
        },
        "dashboard_metrics": {
            "summary": "这里整合的是大V自己的经营 Dashboard，口径覆盖粉丝增长、粉丝注册费、总注册收入、其他收入、token 消耗、消息数量分布和趋势、发布数量及类型趋势。",
            "kpis": [
                {"label": "粉丝增长量", "value": is_lisa and "+1,420" or "+1,860", "sub": "近7日新增", "trend": "up", "badge": is_lisa and "+9.8%" or "+12.4%"},
                {"label": "粉丝注册费用", "value": is_lisa and "¥42" or "¥39", "sub": "单粉平均注册成本", "trend": "down", "badge": is_lisa and "-4.1%" or "-6.2%"},
                {"label": "总注册收入", "value": is_lisa and "¥69,800" or "¥86,400", "sub": "近30日累计", "trend": "up", "badge": is_lisa and "+15.2%" or "+18.7%"},
                {"label": "其他收入", "value": is_lisa and "¥9,600" or "¥12,800", "sub": "群发 / 定制 / 线下活动", "trend": "up", "badge": is_lisa and "+7.4%" or "+9.5%"},
                {"label": "Token 消耗量", "value": is_lisa and "102,300" or "128,400", "sub": "近30日 Hermes 消耗", "trend": "up", "badge": is_lisa and "+11.6%" or "+14.1%"},
            ],
            "message_distribution": [
                {"label": "粉丝提问", "value": 42},
                {"label": "复盘提醒反馈", "value": 28},
                {"label": "大V回复追问", "value": 19},
                {"label": "系统触达回执", "value": 11},
            ],
            "message_trend": [
                {"day": "06-01", "count": 26},
                {"day": "06-02", "count": 31},
                {"day": "06-03", "count": 34},
                {"day": "06-04", "count": 29},
                {"day": "06-05", "count": 40},
                {"day": "06-06", "count": 44},
                {"day": "06-07", "count": 52},
            ],
            "publish_distribution": [
                {"label": "日复盘", "value": 18},
                {"label": "周复盘", "value": 4},
                {"label": "基本面解读", "value": 12},
                {"label": "群发提醒", "value": 9},
            ],
            "publish_trend": [
                {"day": "06-01", "count": 2},
                {"day": "06-02", "count": 3},
                {"day": "06-03", "count": 1},
                {"day": "06-04", "count": 4},
                {"day": "06-05", "count": 3},
                {"day": "06-06", "count": 2},
                {"day": "06-07", "count": 5},
            ],
            "analytics_sections": {
                "funnel": {
                    "summary": "从内容触达到高频留存，观察当前租户粉丝在复盘、问答和 H5 内的转化路径。",
                    "kpis": [
                        {"label": "内容触达", "value": "12,800", "sub": "近30日门户/H5 内容触达"},
                        {"label": "私域留资", "value": "1,460", "sub": "留资率 11.4%"},
                        {"label": "激活试用", "value": "620", "sub": "激活率 42.5%"},
                        {"label": "首次付费", "value": "128", "sub": "付费率 20.6%"},
                        {"label": "高频留存", "value": "36", "sub": "稳定跟踪样本用户"},
                    ],
                    "funnel": [
                        {"label": "内容触达", "count": 12800, "rate": 100.0},
                        {"label": "私域留资", "count": 1460, "rate": 11.4},
                        {"label": "激活试用", "count": 620, "rate": 4.8},
                        {"label": "首次付费", "count": 128, "rate": 1.0},
                        {"label": "高频留存", "count": 36, "rate": 0.3},
                    ],
                    "channel_mix": [
                        {"label": "复盘阅读", "value": 42},
                        {"label": "Hermes 问答", "value": 24},
                        {"label": "消息追问", "value": 18},
                        {"label": "自选股跟踪", "value": 16},
                    ],
                    "heatmap_columns": ["内容触达", "私域留资", "激活试用", "首次付费", "高频留存"],
                    "heatmap_rows": [
                        {"label": "复盘专区", "values": [100, 18.2, 8.4, 2.2, 0.8]},
                        {"label": "Hermes", "values": [100, 14.8, 9.6, 3.4, 1.2]},
                        {"label": "消息区", "values": [100, 22.1, 11.2, 3.8, 1.5]},
                        {"label": "自选股", "values": [100, 12.4, 6.7, 2.1, 0.9]},
                    ],
                },
                "channel": {
                    "summary": "看当前租户各获客和互动来源的质量，而不是平台总渠道。",
                    "cards": [
                        {"label": "复盘转化", "users": "620", "conv": "8.4%", "revenue": "¥26,800", "score": 88},
                        {"label": "Hermes 转化", "users": "410", "conv": "11.2%", "revenue": "¥24,300", "score": 92},
                        {"label": "消息追问", "users": "260", "conv": "15.6%", "revenue": "¥18,600", "score": 95},
                        {"label": "社群转介绍", "users": "170", "conv": "18.1%", "revenue": "¥16,200", "score": 97},
                    ],
                    "quality_rows": [
                        {"label": "复盘转化", "users": 620, "cac": 32, "ltv": 620, "conv": "8.4%", "score": 88, "trend": "上升"},
                        {"label": "Hermes 转化", "users": 410, "cac": 24, "ltv": 760, "conv": "11.2%", "score": 92, "trend": "上升"},
                        {"label": "消息追问", "users": 260, "cac": 18, "ltv": 880, "conv": "15.6%", "score": 95, "trend": "稳定"},
                        {"label": "社群转介绍", "users": 170, "cac": 12, "ltv": 960, "conv": "18.1%", "score": 97, "trend": "上升"},
                    ],
                },
                "kol": {
                    "summary": "这里不再比较全平台所有大V，而是拆解当前租户自己的协同效率与增长阶段。",
                    "kpis": [
                        {"label": "本月协同收入", "value": is_lisa and "¥69,800" or "¥86,400", "sub": "当前租户口径"},
                        {"label": "高价值线索", "value": "18", "sub": "近30日重点粉丝"},
                        {"label": "复盘带动付费", "value": "42%", "sub": "主要转化来源"},
                        {"label": "私域追问率", "value": "31%", "sub": "复盘后继续追问"},
                    ],
                    "stage_cards": [
                        {"label": "种子线索", "value": 42},
                        {"label": "持续互动", "value": 28},
                        {"label": "稳定付费", "value": 12},
                        {"label": "高频留存", "value": 6},
                    ],
                    "table_rows": [
                        {"label": "机构试点张总", "source": "闭门交流", "focus": "港股互联网 / 宏观", "revenue": "¥18,000", "share": "30%", "stage": "高价值", "change": "+12%"},
                        {"label": "投研达人小陈", "source": "Hermes", "focus": "AI 算力 / 半导体", "revenue": "¥8,600", "share": "22%", "stage": "稳定付费", "change": "+8%"},
                        {"label": "价值猎人小林", "source": "复盘", "focus": "港股互联网", "revenue": "¥4,200", "share": "18%", "stage": "成长中", "change": "+6%"},
                    ],
                },
                "revenue": {
                    "summary": "把当前租户的收入来源、订阅结构和月度变化拆开看。",
                    "kpis": [
                        {"label": "月度收入", "value": is_lisa and "¥79,400" or "¥99,200", "sub": "订阅 + 定制 + 活动"},
                        {"label": "专业会员占比", "value": "46%", "sub": "当前主力收入层"},
                        {"label": "高价值服务", "value": "¥12,800", "sub": "群发 / 定制 / 线下"},
                        {"label": "30日留存收入", "value": "73%", "sub": "非一次性收入"},
                    ],
                    "monthly_revenue": [
                        {"label": "1月", "value": 42},
                        {"label": "2月", "value": 48},
                        {"label": "3月", "value": 56},
                        {"label": "4月", "value": 63},
                        {"label": "5月", "value": 71},
                        {"label": "6月", "value": 79 if is_lisa else 89},
                    ],
                    "tier_revenue": [
                        {"label": "基础会员", "value": 18},
                        {"label": "专业会员", "value": 36},
                        {"label": "机构试点", "value": 22},
                        {"label": "其他服务", "value": 12},
                    ],
                    "cohort_columns": ["M0", "M1", "M2", "M3", "M4", "M5"],
                    "cohort_rows": [
                        {"label": "2026-01", "values": [100, 64, 51, 42, 36, 29]},
                        {"label": "2026-02", "values": [100, 66, 54, 45, 38, None]},
                        {"label": "2026-03", "values": [100, 68, 56, 47, None, None]},
                        {"label": "2026-04", "values": [100, 69, 58, None, None, None]},
                    ],
                },
                "segment": {
                    "summary": "看当前租户不同粉丝层级的规模、ARPU 和留存，而不是平台总用户。",
                    "tiers": [
                        {"label": "免费用户", "users": 3680, "ret7": "24%", "ret30": "9%", "ret90": "3%", "arpu": "¥0", "ltv": "¥0"},
                        {"label": "基础会员", "users": 880, "ret7": "58%", "ret30": "41%", "ret90": "24%", "arpu": "¥49", "ltv": "¥186"},
                        {"label": "专业会员", "users": 248, "ret7": "72%", "ret30": "63%", "ret90": "46%", "arpu": "¥138", "ltv": "¥620"},
                        {"label": "机构试点", "users": 18, "ret7": "88%", "ret30": "82%", "ret90": "71%", "arpu": "¥860", "ltv": "¥4,800"},
                    ],
                    "lifecycle": [
                        {"label": "免费", "value": 3680},
                        {"label": "基础", "value": 880},
                        {"label": "专业", "value": 248},
                        {"label": "机构", "value": 18},
                    ],
                },
            },
        },
        "review_studio": {
            "sources": [
                {"icon": "🎙️", "label": "语音口述", "desc": "收盘后直接口述行业主线、关键公司和操作复盘，智能体自动转写并抽取段落。"},
                {"icon": "✍️", "label": "手动撰写", "desc": "提供富文本手写区域，大V自己决定文章段落、标题和表达顺序。"},
                {"icon": "📎", "label": "文件上传", "desc": "上传研报、纪要、Excel 和 PDF，由智能体统一抽取要点并转成复盘文案。"},
            ],
            "paragraph_modes": [
                {"label": "大V自定段落", "desc": "适合自己写主框架，只让智能体补摘要、证据链和风险提示。"},
                {"label": "智能文案", "desc": "适合先交信息给智能体，并补充修改规则或常用提示词标签后生成草稿。"},
            ],
            "default_flow": ["选择复盘周期", "确认本次自选股", "补充语音/手输/文件", "设置智能文案规则", "生成草稿预览", "确认后发布给粉丝"],
            "watchlist_focus": watchlist_focus,
            "periods": ["日复盘", "周复盘", "月复盘"],
        },
        "knowledge_hub": {
            "summary": "知识库支持语音、文件和 URL 三种入口；历史内容允许点开弹框继续微调，修改后会重新同步到知识专区和 Hermes 上下文。",
            "items": [
                {
                    "title": "港股互联网估值框架",
                    "source": "文件上传 · 12页 PDF",
                    "status": "可微调",
                    "summary": "拆出回购强度、估值带与催化条件，已关联腾讯 / 美团 / 阿里。",
                    "tags": ["估值框架", "港股互联网"],
                },
                {
                    "title": "5月产业电话会录音整理",
                    "source": "语音转写 · 28分钟",
                    "status": "已同步 Hermes",
                    "summary": "提炼固态电池、订单验证和量产节点，当前可直接被 Hermes 调用。",
                    "tags": ["电话会", "新能源"],
                },
                {
                    "title": "半导体景气验证节点",
                    "source": "网页 URL · 3篇行业资料",
                    "status": "同步中",
                    "summary": "整理产能利用率、成熟制程价格与资本开支节奏，适合继续补充验证节点。",
                    "tags": ["半导体", "网页资料"],
                },
            ],
        },
        "hermes_hub": {
            "summary": "Hermes 对大V保留两种演示版本：工作区版承接股票、skills、提示词和结构化结果；龙虾纯对话版只保留 skills + 对话，按知识库直接聊天。",
            "versions": [
                {
                    "name": "工作区版",
                    "desc": "适合带股票代码、skills、提示词建议和图表结果一起演示。",
                    "points": ["股票代码输入", "结构化结果卡", "图表 + 指标 + 证据链"],
                },
                {
                    "name": "龙虾纯对话版",
                    "desc": "纯提示词聊天，不强制单独输入股票代码；若问题里自然带了股票对象，会自动进入个股分析。",
                    "points": ["纯对话输入", "skills 保持一致", "知识库自动带入上下文"],
                },
            ],
            "skills": [
                {"label": "基本面分析", "type": "系统", "knowledge": 3},
                {"label": "基本面判断", "type": "系统", "knowledge": 2},
                {"label": "证据链归因", "type": "系统", "knowledge": 3},
                {"label": "龙头股估值框架", "type": "自定义", "knowledge": 2},
            ],
        },
        "watchlist_hub": {
            "summary": "自选股在前台已经改成顶部直接输入股票代码，进入个股详情后再添加自选；详情页展示基础 K 线和 5 / 10 / 20 日线。",
            "items": is_lisa and [
                {
                    "name": "腾讯控股",
                    "code": "00700",
                    "market": "港股",
                    "focus": "回购 + 财报",
                    "change": "+1.4%",
                    "thesis": "回购和现金流支撑估值修复，但仍需财报确认。",
                },
                {
                    "name": "美团-W",
                    "code": "03690",
                    "market": "港股",
                    "focus": "外卖 + 到店",
                    "change": "+0.9%",
                    "thesis": "看履约效率和广告变现恢复斜率。",
                },
                {
                    "name": "阿里巴巴-W",
                    "code": "09988",
                    "market": "港股",
                    "focus": "云 + 电商",
                    "change": "+1.1%",
                    "thesis": "组织调整和云业务兑现是核心观察点。",
                },
            ] or [
                {
                    "name": "中芯国际",
                    "code": "688981",
                    "market": "A股",
                    "focus": "半导体景气",
                    "change": "+2.8%",
                    "thesis": "订单兑现和国产替代仍是核心验证点。",
                },
                {
                    "name": "腾讯控股",
                    "code": "00700",
                    "market": "港股",
                    "focus": "回购 + 财报",
                    "change": "+1.4%",
                    "thesis": "回购和现金流支撑估值修复，但仍需财报确认。",
                },
                {
                    "name": "贵州茅台",
                    "code": "600519",
                    "market": "A股",
                    "focus": "稳健配置",
                    "change": "-0.6%",
                    "thesis": "更适合作为长期稳健样本，不宜只按短期波动下结论。",
                },
            ],
        },
        "fund_dashboard": {
            "summary": f"{tenant['advisor']} 租户的核心指标面板默认展示总结态；没有指标时显示加号，点击单格后输入独立提示词，保存即生成该格指标摘要。",
            "layout": "2x2",
            "cells": fund_cells,
        },
        "published_reviews": [
            {
                "title": "收盘复盘：AI 算力强主线未变，港股互联网继续看回购与财报兑现",
                "period": "日复盘",
                "time": "2026-06-07 18:40",
                "tags": ["行业板块", "个股跟踪", "可直接分发"],
                "watchlist": watchlist_focus[:3],
                "summary": "先从全天资料压出短版提纲，再对中芯国际、腾讯控股和贵州茅台三个样本做个股投资复盘，保留主线、验证节点和下一步观察。"
            },
            {
                "title": "周度复盘：科技成长维持主线，消费与新能源需要继续等景气验证",
                "period": "周复盘",
                "time": "2026-06-06 20:10",
                "tags": ["周度框架", "板块归纳"],
                "watchlist": watchlist_focus[:3],
                "summary": "以行业板块为骨架，把 AI 算力、半导体、港股互联网、消费和新能源统一放进同一篇复盘，方便普通投资者快速查看。"
            },
        ],
        "consistency_notes": [
            {"title": "前后台分离", "desc": "首页同时展示纯 Admin 后台和大V web 工作台两个入口，角色职责分开。"},
            {"title": "消息口径一致", "desc": "H5、工作台和 Admin 都把“粉丝消息 + 大V回复 + 复盘提醒”视为同一消息链路。"},
            {"title": "Hermes 口径一致", "desc": "前台支持工作区版和龙虾纯对话版，后台也按同样两种产品模式管理。"},
            {"title": "知识库口径一致", "desc": "历史知识内容允许继续微调，修改后会重新同步到知识专区和 Hermes。"},
        ],
        "role_split": [
            {"side": "平台 Admin 保留", "items": ["功能控开", "访问审计", "活动管理", "平台级用户与渠道管理"]},
            {"side": "大V工作台保留", "items": ["粉丝消息", "群发助手", "复盘生产", "Hermes 研究与租户知识经营"]},
        ],
    }

@app.route("/api/dm/conversations")
def api_dm_conversations():
    return jsonify(gen_dm_conversations())

@app.route("/api/dm/messages/<int:kol_id>")
def api_dm_messages(kol_id):
    return jsonify(gen_dm_messages(kol_id))

@app.route("/api/dm/send", methods=["POST"])
def api_dm_send():
    kol_id = request.json.get("kol_id")
    content = request.json.get("content", "")
    history = request.json.get("history", [])
    # 作者角色画像 + 上下文感知（合规：用"关注/参考/可考虑"措辞，不出现"买/卖/必涨/必跌"）
    KOL_PERSONA = {
        1: {"name":"财经老王","style":"宏观+科技，偏稳健","focus":["AI算力","半导体","美联储","降息"]},
        2: {"name":"投资女神Lisa","style":"港股+互联网，价值派","focus":["港股","互联网","南向资金","平台经济"]},
        3: {"name":"量化老师陈明","style":"量化+因子，数据驱动","focus":["因子","量化","回测","动量","价值"]},
        4: {"name":"全球宏观James","style":"宏观+大宗，海外视角","focus":["美联储","美元","黄金","大宗"]},
        5: {"name":"新能源猎手阿强","style":"产业链调研，新能源","focus":["新能源","固态电池","锂电","光伏"]},
    }
    persona = KOL_PERSONA.get(kol_id, KOL_PERSONA[1])
    text = content.lower()
    turn = len(history) + 1

    # 关键词触发的多轮回复（每个作者不同风格）
    def reply_for(kw_match):
        base = persona["name"]
        if "买" in content or "卖" in content or "推荐" in content or "代码" in content:
            return f"我只能基于公开数据分享研究观点，无法给具体买卖建议哦。你可以参考洞见智研Hermes的「AI资产配置」做组合规划，或在「AI行情预判」看历史区间和模型推演的概率分布，结合自己的风险偏好判断。"
        if "新能源" in text or "电池" in text or "锂" in text:
            if kol_id == 5:
                return f"我刚跑完一轮产业链调研：固态电池量产时间表略有提前迹象，中游材料端景气度在恢复。可以关注以下三个维度：①电解质技术路线分化 ②碳酸锂价格底部信号 ③海外工厂投产节奏。具体标的我不点名，避免合规风险，你可以用Hermes的量化因子筛选自己跑一下。"
            return f"新能源这条线我不是最强的，建议直接看新能源猎手阿强的频道，他的产业链调研做得很扎实。从宏观角度，当下新能源板块处于估值修复阶段，可以适度关注。"
        if "港股" in text or "互联网" in text or "恒生" in text:
            if kol_id == 2:
                return f"港股互联网这波我跟得比较紧。当前估值大约在历史20-25%分位，南向资金已经连续14个交易日净买入。但要注意两点：①Q2财报季验证基本面 ②美联储路径不确定性。我个人会把仓位控制在标配+5%以内，分批操作。"
            return f"港股不是我的主战场，建议看Lisa的频道。从大方向看，估值确实有修复空间，但短期波动会比较大，注意控制仓位。"
        if "ai" in text or "算力" in text or "科技" in text or "芯片" in text:
            if kol_id == 1:
                return f"AI算力短期确实热，但要拆开看：①云厂商资本开支节奏 ②国产替代订单兑现度 ③估值消化空间。我现在是逢回调关注，不追高。具体节奏，可以参考Hermes里高盛和中金最新的研报精读，我也是基于这些证据做判断的。"
            return f"科技板块我会更多看宏观资金面和外资流向，不做个股推荐。可以参考一下老王的频道，他对这条线跟得更细。"
        if "宏观" in text or "美联储" in text or "降息" in text or "美元" in text:
            if kol_id == 4:
                return f"美联储这边我跟最紧：CME利率期货显示年内降息2次概率68%，鲍威尔最近讲话偏鸽。美元指数承压，对应：①新兴市场股票偏好上升 ②黄金中长期支撑 ③大宗商品反弹。这些只是大类资产框架，不是具体建议哈。"
            return f"宏观层面，降息预期升温对风险资产是利好，但要警惕预期透支后的回吐。建议看James的频道，他对海外宏观跟得更深。"
        if "量化" in text or "因子" in text:
            if kol_id == 3:
                return f"我跑了最新一轮多因子回测：价值因子最近4周相对动量因子超额+3.2%，建议把组合往价值方向调一调。这只是因子层面的判断，不构成个股推荐。你可以在Hermes里用「量化因子筛选」自己跑一遍。"
            return f"量化的事建议找陈明老师，他这块比我专业。"
        if turn <= 2:
            return f"你这个问题挺好。我先简单回应：基于我最近跟踪的数据（{('、'.join(persona['focus'][:2]))}方向），目前的情况是结构性机会大于系统性机会。要不你具体说说你的关注点？是想看赛道、还是想做资产配置？"
        if turn <= 4:
            return f"明白。我补充一下数据视角：洞见智研平台最近的研报数据库里，{persona['focus'][0]}相关研报量周环比+12%，机构关注度在抬升。但研报关注≠股价上涨，仅作信号参考。你的仓位结构是怎样的？我可以帮你从大方向上看一下平衡性。"
        return f"咱们聊了几轮，我建议你这样做：①用Hermes的「AI资产配置」生成一份组合参考 ②用「AI行情预判」看一下你关注标的的历史走势区间 ③有具体观点了，再回来跟我对一对。最终决策一定是你自己做，我们这边只能给数据和研究框架。"

    reply = reply_for(content)
    return jsonify({
        "success": True,
        "kol_id": kol_id,
        "msg_id": random.randint(100,999),
        "auto_reply": reply,
        "disclaimer": "以上为试点作者个人研究观点，仅供参考，不构成投资建议",
        "turn": turn,
    })

@app.route("/api/ai/allocation", methods=["POST"])
def api_ai_allocation():
    risk = request.json.get("risk", "稳健")
    horizon = request.json.get("horizon", "中期(6-12月)")
    # 合规：给区间不给单点，标注模型来源
    PROFILES = {
        "保守": {
            "alloc":[{"name":"股票","ratio":20,"range":"15-25%","color":"#E74C3C"},
                     {"name":"债券","ratio":50,"range":"45-55%","color":"#3498DB"},
                     {"name":"黄金","ratio":15,"range":"10-20%","color":"#F39C12"},
                     {"name":"现金","ratio":15,"range":"10-20%","color":"#9A9590"}],
            "expected_return":"3-5%/年(回测区间)","max_drawdown":"-5% ~ -8%",
            "rebalance":"季度再平衡","sector":["高股息","公用事业","必需消费"]
        },
        "稳健": {
            "alloc":[{"name":"股票","ratio":45,"range":"40-50%","color":"#E74C3C"},
                     {"name":"债券","ratio":30,"range":"25-35%","color":"#3498DB"},
                     {"name":"黄金","ratio":10,"range":"5-15%","color":"#F39C12"},
                     {"name":"现金","ratio":15,"range":"10-20%","color":"#9A9590"}],
            "expected_return":"6-10%/年(回测区间)","max_drawdown":"-10% ~ -15%",
            "rebalance":"季度再平衡","sector":["科技","消费","医药","金融"]
        },
        "积极": {
            "alloc":[{"name":"股票","ratio":70,"range":"65-75%","color":"#E74C3C"},
                     {"name":"债券","ratio":10,"range":"5-15%","color":"#3498DB"},
                     {"name":"黄金","ratio":10,"range":"5-15%","color":"#F39C12"},
                     {"name":"现金","ratio":10,"range":"5-15%","color":"#9A9590"}],
            "expected_return":"10-18%/年(回测区间)","max_drawdown":"-18% ~ -25%",
            "rebalance":"月度再平衡","sector":["科技成长","新能源","半导体","港股互联网"]
        },
        "激进": {
            "alloc":[{"name":"股票","ratio":85,"range":"80-90%","color":"#E74C3C"},
                     {"name":"债券","ratio":0,"range":"0-5%","color":"#3498DB"},
                     {"name":"黄金","ratio":5,"range":"0-10%","color":"#F39C12"},
                     {"name":"现金","ratio":10,"range":"5-15%","color":"#9A9590"}],
            "expected_return":"15-30%/年(回测区间)","max_drawdown":"-30% ~ -45%",
            "rebalance":"月度再平衡","sector":["AI算力","固态电池","创新药","小盘成长"]
        },
    }
    p = PROFILES.get(risk, PROFILES["稳健"])
    return jsonify({
        "risk": risk, "horizon": horizon,
        "allocation": p["alloc"],
        "expected_return": p["expected_return"],
        "max_drawdown": p["max_drawdown"],
        "rebalance": p["rebalance"],
        "sector_focus": p["sector"],
        "data_source": "基于洞见智研回测引擎(2015-2026)+ 多因子模型 + Black-Litterman 框架",
        "disclaimer": "本配置方案为模型推演结果，基于历史数据回测，不构成投资建议。市场有风险，实际收益可能与回测区间显著偏离。",
        "compute_used": 5,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })

@app.route("/api/ai/forecast", methods=["POST"])
def api_ai_forecast():
    """行情预判：历史可解读，未来仅区间不解读"""
    import math
    target = request.json.get("target", "上证指数")
    target_type = request.json.get("type", "大盘")
    # 30天历史 + 20天未来
    TARGETS = {
        "上证指数":     {"base":3428.56,"vol":0.012,"trend":0.0008},
        "沪深300":      {"base":3920.20,"vol":0.013,"trend":0.0007},
        "恒生指数":     {"base":23156.78,"vol":0.018,"trend":0.0012},
        "纳斯达克":     {"base":19234.56,"vol":0.015,"trend":0.0009},
        "贵州茅台":     {"base":1685.20,"vol":0.014,"trend":0.0004},
        "宁德时代":     {"base":248.50,"vol":0.022,"trend":0.0010},
        "中证白酒":     {"base":12450.30,"vol":0.016,"trend":-0.0003},
        "新能源ETF":    {"base":0.882,"vol":0.021,"trend":0.0008},
    }
    cfg = TARGETS.get(target, TARGETS["上证指数"])
    base, vol, trend = cfg["base"], cfg["vol"], cfg["trend"]
    random.seed(hash(target) & 0xFFFF)
    history = []
    price = base * (1 - trend*15)
    for i in range(30):
        price = price * (1 + trend + random.uniform(-vol, vol))
        history.append(round(price, 2))
    # 未来 20 天：三条带状区间 (看空/中性/看好)
    last = history[-1]
    bear = []
    base_line = []
    bull = []
    for i in range(1, 21):
        # 区间宽度随时间增大 (类似 fan chart)
        width = vol * math.sqrt(i) * 1.96
        center = last * (1 + trend * i)
        bear.append(round(center * (1 - width), 2))
        base_line.append(round(center, 2))
        bull.append(round(center * (1 + width), 2))
    # 历史可解读
    pct_30d = round((history[-1]/history[0]-1)*100, 2)
    high = max(history); low = min(history)
    history_commentary = [
        f"过去30个交易日累计涨跌：{('+' if pct_30d>=0 else '')}{pct_30d}%",
        f"区间高点 {high}（第{history.index(high)+1}个交易日），区间低点 {low}（第{history.index(low)+1}个交易日）",
        f"振幅 {round((high-low)/low*100,2)}%，{'波动较大' if vol>0.018 else '波动温和'}",
        f"近5日趋势：{'温和上行' if history[-1]>history[-6] else '温和回调'}，量能{'放大' if random.random()>0.5 else '收敛'}",
    ]
    # 相关性 (合规：仅展示数据，不解读)
    correlations = [
        {"name":"北向资金净流入","corr":round(random.uniform(0.4,0.78),2)},
        {"name":"美元指数(反向)","corr":round(-random.uniform(0.3,0.62),2)},
        {"name":"10Y国债收益率","corr":round(random.uniform(-0.4,0.35),2)},
        {"name":"VIX恐慌指数(反向)","corr":round(-random.uniform(0.5,0.75),2)},
        {"name":"原油价格","corr":round(random.uniform(-0.2,0.4),2)},
    ]
    return jsonify({
        "target": target,
        "type": target_type,
        "history": history,
        "forecast_bear": bear,
        "forecast_base": base_line,
        "forecast_bull": bull,
        "history_commentary": history_commentary,
        "forecast_disclaimer": "⚠️ 未来区间为模型基于历史波动率推演的概率分布，不构成方向判断和投资建议。实际走势受多重因素影响，可能显著偏离区间。",
        "correlations": correlations,
        "data_source": "洞见智研多因子模型 + 历史波动率Monte Carlo推演 + RAG数据库",
        "compute_used": 8,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })

@app.route("/api/kol/workbench")
def api_kol_workbench():
    tenant = get_tenant_by_slug(request.args.get("tenant"))
    return jsonify(gen_kol_workbench(tenant))


@app.route("/api/tenant/<tenant_slug>/dashboard")
def api_tenant_dashboard(tenant_slug):
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or tenant["slug"] != tenant_slug:
        return jsonify({"success": False, "error": "tenant_not_found"}), 404
    return jsonify({"success": True, "dashboard": build_tenant_dashboard_payload(tenant)})

@app.route("/api/kol/broadcast", methods=["POST"])
def api_kol_broadcast():
    content = request.json.get("content", "")
    target = request.json.get("target", "all")
    return jsonify({"success": True, "reach": random.randint(2000, 5000), "content": content, "target": target})

@app.route("/api/kol/reply", methods=["POST"])
def api_kol_reply():
    fan_name = request.json.get("fan_name", "")
    content = request.json.get("content", "")
    is_paid = request.json.get("is_paid", False)
    return jsonify({"success": True, "fan_name": fan_name, "is_paid": is_paid, "revenue": 50 if is_paid else 0})

@app.route("/prd")
def prd():
    return render_template("prd.html")

init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
