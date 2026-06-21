import os
import json
import sqlite3
import copy
import math
import statistics
import time
import re
import hashlib
from pathlib import Path
from html import escape as html_escape
from html.parser import HTMLParser
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, g, abort
import random
from datetime import datetime, timedelta
from urllib.parse import urlsplit, parse_qsl
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from hmac import compare_digest
import requests
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from psycopg2 import OperationalError
try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None
try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("GANGTISE_DEMO_SECRET_KEY", os.urandom(32)),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

AUTH_PASSWORD = os.environ.get("GANGTISE_DEMO_PASSWORD", "gangtise")
AUTH_SESSION_KEY = "gangtise_auth"
H5_USER_SESSION_KEY = "current_h5_username"
DB_PATH = os.environ.get("GANGTISE_DEMO_DB", os.path.join(os.path.dirname(__file__), "gangtise_demo.db"))
VECTOR_DB_HOST = os.environ.get("VECTOR_DB_HOST") or os.environ.get("IP") or "129.211.65.53"
VECTOR_DB_PORT = int(os.environ.get("VECTOR_DB_PORT", "5432"))
VECTOR_DB_NAME = os.environ.get("POSTGRES_DB", "sprint_dashboard")
VECTOR_DB_USER = os.environ.get("POSTGRES_USER", "postgres")
VECTOR_DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "your_password")
APP_DB_HOST = os.environ.get("APP_DB_HOST") or VECTOR_DB_HOST
APP_DB_PORT = int(os.environ.get("APP_DB_PORT", str(VECTOR_DB_PORT)))
APP_DB_NAME = os.environ.get("APP_DB_NAME") or VECTOR_DB_NAME
APP_DB_USER = os.environ.get("APP_DB_USER") or VECTOR_DB_USER
APP_DB_PASSWORD = os.environ.get("APP_DB_PASSWORD") or VECTOR_DB_PASSWORD
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_AUDIO_MODEL = os.environ.get("OPENAI_AUDIO_MODEL", "whisper-1").strip() or "whisper-1"
OPENAI_AUDIO_LANGUAGE = os.environ.get("OPENAI_AUDIO_LANGUAGE", "zh").strip() or "zh"
OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip() or "text-embedding-3-small"
LOCAL_WHISPER_MODEL_SIZE = os.environ.get("LOCAL_WHISPER_MODEL_SIZE", "small").strip() or "small"
LOCAL_WHISPER_DEVICE = os.environ.get("LOCAL_WHISPER_DEVICE", "cpu").strip() or "cpu"
LOCAL_WHISPER_COMPUTE_TYPE = os.environ.get("LOCAL_WHISPER_COMPUTE_TYPE", "int8").strip() or "int8"
LOCAL_EMBEDDING_MODEL_NAME = os.environ.get("LOCAL_EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh-v1.5").strip() or "BAAI/bge-small-zh-v1.5"
PGVECTOR_TARGET_DIM = int(os.environ.get("PGVECTOR_TARGET_DIM", "1536"))
VOICE_UPLOAD_MAX_BYTES = int(os.environ.get("VOICE_UPLOAD_MAX_BYTES", str(25 * 1024 * 1024)))
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".wav", ".webm", ".ogg", ".mpeg", ".mpga"}
SITE_CONFIG_KEY = "site_config"
FORECAST_WORKFLOW_KEY = "forecast_workflow_graph"
MARKET_DASHBOARD_REGISTRY_PATH = Path(
    os.environ.get(
        "MARKET_DASHBOARD_REGISTRY_PATH",
        "/Users/xuchenfei/PycharmProjects/market_dashboard/data_sources.json",
    )
)
MARKET_DASHBOARD_CACHE_DB_PATH = Path(
    os.environ.get(
        "MARKET_DASHBOARD_CACHE_DB_PATH",
        "/Users/xuchenfei/PycharmProjects/market_dashboard/market_cache.db",
    )
)
INDICATOR_DEFINITION_FIELDS = {
    "indicator_code",
    "indicator_name",
    "category",
    "description",
    "unit",
    "owner",
    "source_type",
    "source_type_label",
    "provider",
    "status_hint",
    "assessment_template",
    "alert_template",
    "watchers_json",
    "display_config_json",
    "enabled",
}
INDICATOR_SOURCE_FIELDS = {
    "source_code",
    "indicator_code",
    "provider",
    "base_url",
    "path",
    "method",
    "auth_type",
    "headers_json",
    "query_json",
    "body_json",
    "response_mapping_json",
    "response_sample_json",
    "source_status",
    "enabled",
    "last_test_status",
    "last_http_status",
    "last_tested_at",
    "last_test_detail",
}


class PgCompatCursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self._result = None

    def fetchone(self):
        row = self._cursor.fetchone()
        return dict(row) if isinstance(row, dict) else row

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [dict(row) if isinstance(row, dict) else row for row in rows]


class PgCompatConnection:
    def __init__(self, connection):
        self._connection = connection

    @staticmethod
    def _normalize_sql(sql):
        if not isinstance(sql, str):
            return sql
        normalized = sql.replace("?", "%s")
        normalized = normalized.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        normalized = normalized.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
        normalized = normalized.replace("SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS c", "SELECT LEFT(created_at, 10) AS day, COUNT(*) AS c")
        return normalized

    def execute(self, sql, params=None):
        cursor = self._connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(self._normalize_sql(sql), tuple(params or ()))
        return PgCompatCursor(cursor)

    def executemany(self, sql, seq_of_params):
        cursor = self._connection.cursor(cursor_factory=RealDictCursor)
        cursor.executemany(self._normalize_sql(sql), list(seq_of_params or []))
        return PgCompatCursor(cursor)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

DEFAULT_SMART_INDICATOR_DEFINITIONS = [
    {
        "indicator_code": "fed_rate_path",
        "indicator_name": "美联储路径",
        "category": "宏观流动性",
        "description": "用于跟踪全球流动性预期和成长风格风险偏好。",
        "unit": "",
        "owner": "平台宏观组",
        "source_type": "smart",
        "source_type_label": "智能指标",
        "provider": "平台研究运营",
        "status_hint": "good",
        "assessment_template": "若降息节奏继续兑现，成长和港股风险偏好会继续改善。",
        "alert_template": "当前无需报警",
        "watchers_json": json.dumps(["H5 基本面首页", "Hermes", "复盘专区"], ensure_ascii=False),
        "display_config_json": json.dumps({"show_in_admin": True, "show_in_h5": True}, ensure_ascii=False),
        "enabled": 1,
    },
    {
        "indicator_code": "southbound_flow",
        "indicator_name": "南向 / 北向资金",
        "category": "增量资金",
        "description": "用于跟踪跨市场增量资金是否形成共振。",
        "unit": "亿",
        "owner": "平台研究运营",
        "source_type": "smart",
        "source_type_label": "智能指标",
        "provider": "平台研究运营",
        "status_hint": "attention",
        "assessment_template": "流入延续但未到强共振，说明市场广度仍一般。",
        "alert_template": "关注是否连续 3 日放量",
        "watchers_json": json.dumps(["H5 智能指标区", "租户门户", "复盘报告"], ensure_ascii=False),
        "display_config_json": json.dumps({"show_in_admin": True, "show_in_h5": True}, ensure_ascii=False),
        "enabled": 1,
    },
    {
        "indicator_code": "ai_order_signal",
        "indicator_name": "AI 订单兑现",
        "category": "科技主线",
        "description": "用于判断 AI 主线是否从叙事走向订单和利润兑现。",
        "unit": "分",
        "owner": "平台研究运营",
        "source_type": "smart",
        "source_type_label": "智能指标",
        "provider": "平台研究运营",
        "status_hint": "warning",
        "assessment_template": "主题强度仍在，但必须继续验证订单、交付和利润率。",
        "alert_template": "若连续两周只见叙事不见订单，需要提高警惕",
        "watchers_json": json.dumps(["大V工作台", "复盘生产台", "自选股详情"], ensure_ascii=False),
        "display_config_json": json.dumps({"show_in_admin": True, "show_in_h5": True}, ensure_ascii=False),
        "enabled": 1,
    },
    {
        "indicator_code": "credit_pulse",
        "indicator_name": "国内信用脉冲",
        "category": "宏观信用",
        "description": "用于跟踪信用扩张与顺周期风格的验证强度。",
        "unit": "分",
        "owner": "平台研究运营",
        "source_type": "smart",
        "source_type_label": "智能指标",
        "provider": "平台研究运营",
        "status_hint": "warning",
        "assessment_template": "恢复力度偏弱，顺周期与高弹性资产仍需保守。",
        "alert_template": "需继续观察社融和中长期贷款",
        "watchers_json": json.dumps(["Admin 指标专区", "工作台数据分析", "H5 基本面首页"], ensure_ascii=False),
        "display_config_json": json.dumps({"show_in_admin": True, "show_in_h5": True}, ensure_ascii=False),
        "enabled": 1,
    },
]

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
        "dashboard_description": "和 H5 的智能指标定义同源，但在 Web 端用更完整的经营视角呈现。",
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

DEFAULT_USERS = [
    {
        "username": "投研达人_小陈",
        "password": "demo123",
        "role": "investor",
        "tenant_slug": DEFAULT_TENANTS[0]["slug"],
        "advisor_name": DEFAULT_TENANTS[0]["advisor"],
        "phone": "13800008821",
        "status": "active",
    },
    {
        "username": "财经老王",
        "password": "demo123",
        "role": "dav",
        "tenant_slug": DEFAULT_TENANTS[0]["slug"],
        "advisor_name": DEFAULT_TENANTS[0]["advisor"],
        "phone": "13900001111",
        "status": "active",
    },
    {
        "username": "平台管理员",
        "password": "admin123",
        "role": "admin",
        "tenant_slug": DEFAULT_TENANTS[0]["slug"],
        "advisor_name": "",
        "phone": "13700009999",
        "status": "active",
    },
]

ALLOWED_PORTAL_HTML_TAGS = {"p", "br", "strong", "b", "em", "i", "ul", "ol", "li", "h2", "h3", "blockquote", "a", "img", "table", "thead", "tbody", "tr", "th", "td"}


class PortalHtmlSanitizer(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED_PORTAL_HTML_TAGS:
            return
        if tag == "br":
            self.parts.append("<br>")
            return
        attr_map = dict(attrs or [])
        if tag == "a":
            href = str(attr_map.get("href") or "").strip()
            parsed = urlsplit(href)
            is_allowed_href = href.startswith(("/", "#")) or parsed.scheme in {"http", "https", "mailto", "tel"}
            if is_allowed_href:
                safe_href = html_escape(href, quote=True)
                suffix = ' target="_blank" rel="noopener noreferrer"' if parsed.scheme in {"http", "https"} else ""
                self.parts.append(f'<a href="{safe_href}"{suffix}>')
                return
        if tag == "img":
            src = str(attr_map.get("src") or "").strip()
            alt = html_escape(str(attr_map.get("alt") or "").strip(), quote=True)
            parsed = urlsplit(src)
            is_allowed_src = src.startswith("data:image/") or parsed.scheme in {"http", "https"}
            if is_allowed_src:
                safe_src = html_escape(src, quote=True)
                self.parts.append(f'<img src="{safe_src}" alt="{alt}">')
                return
        self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in ALLOWED_PORTAL_HTML_TAGS and tag != "br":
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if data:
            self.parts.append(html_escape(data))

    def handle_entityref(self, name):
        self.parts.append(f"&{name};")

    def handle_charref(self, name):
        self.parts.append(f"&#{name};")

    def get_html(self):
        return "".join(self.parts)

DEFAULT_SITE_CONFIG = {
    "default_theme": "light",
    "default_accent": "blue",
    "password_gate_enabled": True,
    "voice_transcription": {
        "engine": "local",
    },
    "voice_embedding": {
        "engine": "local",
    },
    "llm_registry": {
        "default_model_key": "",
        "models": [],
    },
    "brand": DEFAULT_BRAND_CONFIG,
    "default_tenant_slug": DEFAULT_TENANTS[0]["slug"],
    "tenants": DEFAULT_TENANTS,
    "feature_flags": {
        "fundamental_analysis": True,
        "watchlist": True,
        "stock_forecast": False,
        "daily_review": True,
        "knowledge": True,
        "community": False,
        "hermes": False,
        "vip": False,
        "dm": True,
        "workbench": True,
    },
}

def normalize_llm_model_config(source, index=0):
    raw = source if isinstance(source, dict) else {}
    key = str(raw.get("key") or f"model_{index + 1}").strip() or f"model_{index + 1}"
    purpose = str(raw.get("purpose") or "general").strip().lower() or "general"
    return {
        "key": key,
        "label": str(raw.get("label") or key).strip() or key,
        "provider": str(raw.get("provider") or "openai").strip() or "openai",
        "model_name": str(raw.get("model_name") or "").strip(),
        "base_url": str(raw.get("base_url") or "").strip(),
        "api_key": str(raw.get("api_key") or "").strip(),
        "purpose": purpose,
        "enabled": bool(raw.get("enabled", True)),
    }


def normalize_llm_registry_config(source=None):
    raw = source if isinstance(source, dict) else {}
    items = raw.get("models") if isinstance(raw.get("models"), list) else []
    models = []
    for index, item in enumerate(items[:40]):
        if not isinstance(item, dict):
            continue
        models.append(normalize_llm_model_config(item, index=index))
    default_model_key = str(raw.get("default_model_key") or "").strip()
    if default_model_key and not any(model["key"] == default_model_key for model in models):
        default_model_key = ""
    if not default_model_key and models:
        general_models = [model for model in models if model.get("purpose") == "general" and model.get("enabled")]
        default_model_key = (general_models[0] if general_models else models[0]).get("key") or ""
    return {
        "default_model_key": default_model_key,
        "models": models,
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
    if isinstance(raw.get("portal_cms"), dict):
        tenant["portal_cms"] = copy.deepcopy(raw["portal_cms"])
    if isinstance(raw.get("fund_dashboard_config"), dict):
        tenant["fund_dashboard_config"] = copy.deepcopy(raw["fund_dashboard_config"])
    if isinstance(raw.get("knowledge_hub_config"), dict):
        tenant["knowledge_hub_config"] = copy.deepcopy(raw["knowledge_hub_config"])
    return tenant


def sanitize_portal_html(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    parser = PortalHtmlSanitizer()
    parser.feed(raw)
    parser.close()
    return parser.get_html().strip()


def default_portal_workspace(tenant):
    is_lisa = tenant["slug"] == "lisa"
    workspace = {
        "summary": "租户门户是给粉丝看的父客户端主页。大V在这里像维护 WordPress 一样编辑门户结构：上半部做品牌介绍和价值主张，中间固定展示 Dashboard，下半部维护可自定义文案区，最后放扫码与联系方式。",
        "draft_status": "草稿待发布",
        "published_status": "线上已发布",
        "last_published_at": "2026-06-17 21:10",
        "theme_name": is_lisa and "港股价值蓝" or "科技主线金",
        "hero": {
            "headline": tenant["portal_headline"],
            "description": tenant["portal_description"],
            "audience": is_lisa and "适合先看港股互联网、估值修复与价值框架的粉丝" or "适合先看科技成长、复盘主线和重点样本的粉丝",
            "value_props": [
                is_lisa and "先看价值框架，再决定是否继续互动" or "先看阶段主线，再决定是否继续深挖个股",
                is_lisa and "把港股互联网研究口径整理成粉丝能直接理解的主页" or "把科技成长和重点样本整理成粉丝能直接消费的入口",
                "把复盘、Dashboard 和联系方式收拢成一个父客户端首页",
            ],
        },
        "cta": {
            "primary_label": "进入 H5 继续查看",
            "secondary_label": "先看最新复盘",
        },
        "modules": [
            {"id": "hero", "title": "门户介绍区", "type": "固定首屏", "desc": "介绍大V是谁、价值主张是什么、门户适合谁看。", "enabled": True},
            {"id": "dashboard", "title": "固定 Dashboard", "type": "固定中段", "desc": "中段固定展示关键经营 / 研究 Dashboard，不由大V随意删除。", "enabled": True},
            {"id": "custom-copy", "title": "自定义文案区", "type": "父客户端编辑", "desc": "大V自己写长文案、特色介绍、服务说明和专题说明。", "enabled": True},
            {"id": "contact", "title": "扫码与联系方式", "type": "固定尾部", "desc": "放企微、公众号、客服方式和线下联系入口。", "enabled": True},
        ],
        "presets": [
            {"label": "品牌主视觉", "desc": "突出主理人定位、价值主张和门户导语。"},
            {"label": "固定 Dashboard", "desc": "中段固定承接关键指标与研究总结，不与门户装修混用。"},
            {"label": "父客户端文案", "desc": "大V自己写特色介绍、服务说明和长期表达。"},
            {"label": "联系方式尾部", "desc": "把扫码、企微、公众号和联系信息固定收在页尾。"},
        ],
        "custom_sections": [
            {
                "title": is_lisa and "为什么这个门户值得先看" or "为什么先看这个门户而不是直接进功能页",
                "body": is_lisa and "我希望先把港股互联网的核心主线、估值框架和代表性样本讲清楚，再带你去看更具体的互动和跟踪。" or "我希望先把科技成长、重点样本和阶段判断讲清楚，再带你去看更具体的复盘、互动和工具。",
            },
            {
                "title": "我会持续更新什么",
                "body": "这里会持续更新复盘摘要、重点样本、价值主张和阶段判断。粉丝进入门户后，不需要先理解复杂功能，就能先看懂我当前在研究什么。",
            },
        ],
        "contact": {
            "qr_title": is_lisa and "扫码加入 Lisa 研究社" or "扫码加入老王研究群",
            "qr_hint": "扫码后可进入所属租户粉丝群或添加助手，后续接收复盘分享和互动提醒。",
            "wechat": is_lisa and "Lisa-Research-Assistant" or "Laowang-Research-Assistant",
            "phone": "400-889-6608",
            "email": is_lisa and "lisa@gangtise.demo" or "laowang@gangtise.demo",
        },
    }
    workspace["page_blocks"] = [
        {"id": "hero_block", "type": "hero", "title": "门户介绍", "html": "", "enabled": True},
        {"id": "dashboard_block", "type": "dashboard", "title": "固定 Dashboard", "html": "", "enabled": True},
        {
            "id": "copy_block_1",
            "type": "rich_text",
            "title": workspace["custom_sections"][0]["title"],
            "html": sanitize_portal_html(
                f"<h3>{workspace['custom_sections'][0]['title']}</h3><p>{workspace['custom_sections'][0]['body']}</p>"
            ),
            "enabled": True,
        },
        {
            "id": "copy_block_2",
            "type": "rich_text",
            "title": workspace["custom_sections"][1]["title"],
            "html": sanitize_portal_html(
                f"<h3>{workspace['custom_sections'][1]['title']}</h3><p>{workspace['custom_sections'][1]['body']}</p>"
            ),
            "enabled": True,
        },
        {"id": "contact_block", "type": "contact", "title": "联系方式", "html": "", "enabled": True},
    ]
    return workspace


def resolve_tenant_portal_workspace(tenant, cms=None):
    tenant = tenant or get_tenant_by_slug()
    base = default_portal_workspace(tenant)
    if isinstance(cms, dict):
        merged = normalize_portal_cms_config(cms, tenant)
        base.update({
            "summary": merged.get("summary", base["summary"]),
            "draft_status": merged.get("draft_status", base["draft_status"]),
            "published_status": merged.get("published_status", base["published_status"]),
            "last_published_at": merged.get("last_published_at", base["last_published_at"]),
            "theme_name": merged.get("theme_name", base["theme_name"]),
            "hero": merged.get("hero", base["hero"]),
            "cta": merged.get("cta", base["cta"]),
            "modules": merged.get("modules", base["modules"]),
            "presets": merged.get("presets", base["presets"]),
            "custom_sections": merged.get("custom_sections", base["custom_sections"]),
            "contact": merged.get("contact", base["contact"]),
            "page_blocks": merged.get("page_blocks", base["page_blocks"]),
        })
    return base


def normalize_portal_cms_config(source, tenant):
    defaults = default_portal_workspace(tenant)
    raw = source if isinstance(source, dict) else {}
    merged = _merge_site_config(copy.deepcopy(defaults), raw)
    hero = merged.get("hero") if isinstance(merged.get("hero"), dict) else {}
    cta = merged.get("cta") if isinstance(merged.get("cta"), dict) else {}
    contact = merged.get("contact") if isinstance(merged.get("contact"), dict) else {}
    custom_sections = merged.get("custom_sections") if isinstance(merged.get("custom_sections"), list) else []
    merged["hero"] = {
        "headline": str(hero.get("headline") or defaults["hero"]["headline"]).strip() or defaults["hero"]["headline"],
        "description": str(hero.get("description") or defaults["hero"]["description"]).strip() or defaults["hero"]["description"],
        "audience": str(hero.get("audience") or defaults["hero"]["audience"]).strip() or defaults["hero"]["audience"],
        "value_props": [
            str(item or "").strip()
            for item in (hero.get("value_props") if isinstance(hero.get("value_props"), list) else defaults["hero"]["value_props"])
        ][:3] or copy.deepcopy(defaults["hero"]["value_props"]),
    }
    while len(merged["hero"]["value_props"]) < 3:
        merged["hero"]["value_props"].append(defaults["hero"]["value_props"][len(merged["hero"]["value_props"])])
    merged["cta"] = {
        "primary_label": str(cta.get("primary_label") or defaults["cta"]["primary_label"]).strip() or defaults["cta"]["primary_label"],
        "secondary_label": str(cta.get("secondary_label") or defaults["cta"]["secondary_label"]).strip() or defaults["cta"]["secondary_label"],
    }
    normalized_sections = []
    for index, item in enumerate(custom_sections[:4]):
        if not isinstance(item, dict):
            continue
        fallback = defaults["custom_sections"][min(index, len(defaults["custom_sections"]) - 1)]
        normalized_sections.append(
            {
                "title": str(item.get("title") or fallback["title"]).strip() or fallback["title"],
                "body": str(item.get("body") or fallback["body"]).strip() or fallback["body"],
            }
        )
    if not normalized_sections:
        normalized_sections = copy.deepcopy(defaults["custom_sections"])
    merged["custom_sections"] = normalized_sections
    merged["contact"] = {
        "qr_title": str(contact.get("qr_title") or defaults["contact"]["qr_title"]).strip() or defaults["contact"]["qr_title"],
        "qr_hint": str(contact.get("qr_hint") or defaults["contact"]["qr_hint"]).strip() or defaults["contact"]["qr_hint"],
        "wechat": str(contact.get("wechat") or defaults["contact"]["wechat"]).strip() or defaults["contact"]["wechat"],
        "phone": str(contact.get("phone") or defaults["contact"]["phone"]).strip() or defaults["contact"]["phone"],
        "email": str(contact.get("email") or defaults["contact"]["email"]).strip() or defaults["contact"]["email"],
    }
    blocks = raw.get("page_blocks") if isinstance(raw.get("page_blocks"), list) else []
    normalized_blocks = []
    allowed_types = {"hero", "dashboard", "rich_text", "contact"}
    for index, block in enumerate(blocks[:8]):
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "").strip()
        if block_type not in allowed_types:
            continue
        normalized_blocks.append(
            {
                "id": str(block.get("id") or f"block_{index + 1}").strip() or f"block_{index + 1}",
                "type": block_type,
                "title": str(block.get("title") or "").strip(),
                "html": sanitize_portal_html(block.get("html") if block_type == "rich_text" else ""),
                "enabled": block.get("enabled") is not False,
            }
        )
    if not normalized_blocks:
        normalized_blocks = [
            {"id": "hero_block", "type": "hero", "title": "门户介绍", "html": "", "enabled": True},
            {"id": "dashboard_block", "type": "dashboard", "title": "固定 Dashboard", "html": "", "enabled": True},
            {
                "id": "copy_block_1",
                "type": "rich_text",
                "title": merged["custom_sections"][0]["title"],
                "html": sanitize_portal_html(
                    f"<h3>{html_escape(merged['custom_sections'][0]['title'])}</h3><p>{html_escape(merged['custom_sections'][0]['body'])}</p>"
                ),
                "enabled": True,
            },
            {
                "id": "copy_block_2",
                "type": "rich_text",
                "title": merged["custom_sections"][1]["title"],
                "html": sanitize_portal_html(
                    f"<h3>{html_escape(merged['custom_sections'][1]['title'])}</h3><p>{html_escape(merged['custom_sections'][1]['body'])}</p>"
                ),
                "enabled": True,
            },
            {"id": "contact_block", "type": "contact", "title": "联系方式", "html": "", "enabled": True},
        ]
    merged["page_blocks"] = normalized_blocks
    merged["draft_status"] = str(merged.get("draft_status") or defaults["draft_status"]).strip() or defaults["draft_status"]
    merged["published_status"] = str(merged.get("published_status") or defaults["published_status"]).strip() or defaults["published_status"]
    merged["last_published_at"] = str(merged.get("last_published_at") or defaults["last_published_at"]).strip() or defaults["last_published_at"]
    merged["theme_name"] = str(merged.get("theme_name") or defaults["theme_name"]).strip() or defaults["theme_name"]
    merged["summary"] = str(merged.get("summary") or defaults["summary"]).strip() or defaults["summary"]
    merged["modules"] = copy.deepcopy(defaults["modules"])
    merged["presets"] = copy.deepcopy(defaults["presets"])
    return merged


def update_tenant_portal_cms(tenant_slug, portal_cms):
    site_config = get_site_config()
    tenants = get_tenant_configs(site_config)
    updated = False
    for index, tenant in enumerate(tenants):
        if tenant.get("slug") != tenant_slug:
            continue
        tenants[index] = dict(tenant)
        tenants[index]["portal_cms"] = normalize_portal_cms_config(portal_cms, tenant)
        updated = True
        break
    if not updated:
        return None
    next_config = dict(site_config)
    next_config["tenants"] = tenants
    return save_site_config(next_config)


def default_tenant_knowledge_items(tenant):
    is_lisa = tenant["slug"] == "lisa"
    return [
        {
            "id": "kb-hk-internet-valuation",
            "type": "file",
            "title": "港股互联网估值框架",
            "source": "文件上传 · 12页 PDF",
            "source_detail": "来源：文件上传 · 港股互联网估值框架.pdf · 12页",
            "status": "可微调",
            "summary": "拆出回购强度、估值带与催化条件，已关联腾讯 / 美团 / 阿里。",
            "tags": ["估值框架", "港股互联网"],
            "raw_input": "原始材料重点包括：腾讯 / 美团 / 阿里的历史估值带、回购力度、自由现金流、财报兑现节奏，以及对行业竞争格局和监管预期的补充说明。",
            "key_points": ["回购强度直接影响估值修复斜率", "估值带必须结合利润兑现看，不单看 PS/PE", "催化条件要和财报、回购公告、南向资金一起验证"],
            "validation_nodes": ["财报后利润率是否兑现", "回购节奏是否持续", "南向资金是否继续净流入"],
            "sync_targets": ["租户知识队列", "知识专区", "Hermes 上下文", "港股互联网 Skill"],
            "tuning_focus": ["标题是否更贴近大V表达", "摘要是否保留关键判断", "关键要点是否足够结构化", "验证节点是否可直接复用到复盘"],
            "notes": "适合继续补公司层估值带、买回购和财报验证的先后顺序，以及哪些结论只适用于龙头公司。",
            "files": ["港股互联网估值框架.pdf"],
        },
        {
            "id": "kb-may-industry-call",
            "type": "voice",
            "title": "5月产业电话会录音整理",
            "source": "语音转写 · 28分钟",
            "source_detail": "来源：语音转写 · 产业电话会录音 · 28分钟",
            "status": "已同步 Hermes",
            "summary": "提炼固态电池、订单验证和量产节点，当前可直接被 Hermes 调用。",
            "tags": ["电话会", "新能源"],
            "raw_input": "原始语音中重点讨论了固态电池量产路径、下游车厂验证节奏、订单兑现的不确定项，以及短期市场情绪和长期产业趋势的区别。",
            "key_points": ["先分清产业趋势和交易情绪", "订单验证比概念热度更重要", "量产节点要拆成时间、客户、成本三层"],
            "validation_nodes": ["样品送测是否进入下一阶段", "订单是否从试产切换到量产", "成本曲线是否出现拐点"],
            "sync_targets": ["租户知识队列", "知识专区", "Hermes 上下文", "新能源相关复盘"],
            "tuning_focus": ["转写口语是否要收敛成书面结论", "关键判断是否已经拆成可复用节点", "风险边界是否写清", "是否适合直接进入复盘或 Hermes"],
            "notes": "建议把口语化表达进一步压缩成“观点 - 证据 - 验证节点 - 风险”四段式，便于 Hermes 后续直接调用。",
            "voice_minutes": 28,
        },
        {
            "id": "kb-semiconductor-cycle",
            "type": "url",
            "title": "半导体景气验证节点",
            "source": "网页 URL · 3篇行业资料",
            "source_detail": "来源：网页 URL · 3篇行业资料抓取摘要",
            "status": "同步中",
            "summary": "整理产能利用率、成熟制程价格与资本开支节奏，适合继续补充验证节点。",
            "tags": ["半导体", "网页资料"],
            "raw_input": "系统已抓取 3 篇行业网页资料，内容涉及成熟制程价格变化、产能利用率、资本开支收缩节奏，以及下游消费电子和服务器需求恢复情况。",
            "key_points": ["成熟制程价格是景气验证先行指标", "资本开支变化会领先反映景气预期", "不能只看单篇新闻，要归并成长期跟踪节点"],
            "validation_nodes": ["晶圆代工价格是否止跌", "主要厂商 capex 指引是否收缩", "下游需求恢复是否扩散到更多品类"],
            "sync_targets": ["租户知识队列", "知识专区", "Hermes 上下文"],
            "tuning_focus": ["网页摘要是否准确", "要点是否去噪", "验证节点是否可持续追踪", "是否需要补更多来源链接"],
            "notes": "当前更适合补充来源链接、删除噪音表述，并把验证节点改成可按月跟踪的版本。",
            "url": "https://example.com/semiconductor-cycle",
        },
        {
            "id": "kb-manual-thesis-note",
            "type": "manual",
            "title": is_lisa and "港股互联网判断口径手记" or "科技主线判断手记",
            "source": "纯文本编写",
            "source_detail": "来源：纯文本编写 · 186字",
            "status": "可微调",
            "summary": is_lisa and "手工整理港股互联网判断口径，保留估值、回购与财报验证顺序。" or "手工整理科技主线判断框架，保留景气、订单和验证节点顺序。",
            "tags": ["手动编写", "观点沉淀"],
            "raw_input": is_lisa and "观点：港股互联网先看回购与现金流，再看财报兑现，最后才看估值修复弹性。\n\n验证节点：回购节奏、利润率、南向资金。"
                or "观点：科技主线先看产业趋势和订单兑现，再看估值扩张是否有利润支撑。\n\n验证节点：订单、毛利率、资本开支。",
            "key_points": ["先写观点，再写证据", "验证节点要能持续跟踪", "风险边界要单独写清楚"],
            "validation_nodes": ["继续跟踪验证节点是否兑现"],
            "sync_targets": ["租户知识队列", "知识专区", "Hermes 上下文"],
            "tuning_focus": ["收敛表达", "补证据链", "补风险边界"],
            "notes": "适合直接从后台或 H5 手工录入，再继续细化成长期知识卡。",
            "body": is_lisa and "观点：港股互联网先看回购与现金流，再看财报兑现，最后才看估值修复弹性。\n\n验证节点：回购节奏、利润率、南向资金。"
                or "观点：科技主线先看产业趋势和订单兑现，再看估值扩张是否有利润支撑。\n\n验证节点：订单、毛利率、资本开支。",
        },
    ]


def normalize_knowledge_hub_config(source, tenant):
    defaults = {
        "summary": "知识库支持语音、文件、URL 和纯文本四种入口；历史内容允许点开弹框继续微调，修改后会重新同步到知识专区和 Hermes 上下文。",
        "items": default_tenant_knowledge_items(tenant),
    }
    raw = source if isinstance(source, dict) else {}
    summary = str(raw.get("summary") or defaults["summary"]).strip() or defaults["summary"]
    items = raw.get("items") if isinstance(raw.get("items"), list) else defaults["items"]
    normalized_items = []
    for index, item in enumerate(items[:80]):
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "manual").strip().lower()
        if item_type not in {"voice", "file", "url", "manual"}:
            item_type = "manual"
        title = str(item.get("title") or f"知识条目 {index + 1}").strip() or f"知识条目 {index + 1}"
        summary_text = str(item.get("summary") or "").strip()
        raw_input = str(item.get("raw_input") or item.get("body") or "").strip()
        notes = str(item.get("notes") or "").strip()
        normalized_items.append({
            "id": str(item.get("id") or f"kb-{slugify_code(title, 'item')}-{index + 1}").strip() or f"kb-item-{index + 1}",
            "type": item_type,
            "title": title,
            "source": str(item.get("source") or "").strip() or ("纯文本编写" if item_type == "manual" else title),
            "source_detail": str(item.get("source_detail") or "").strip(),
            "status": str(item.get("status") or "可微调").strip() or "可微调",
            "summary": summary_text,
            "tags": [str(tag).strip() for tag in (item.get("tags") if isinstance(item.get("tags"), list) else []) if str(tag).strip()][:8],
            "raw_input": raw_input,
            "raw_html": str(item.get("raw_html") or "").strip(),
            "key_points": [str(point).strip() for point in (item.get("key_points") if isinstance(item.get("key_points"), list) else []) if str(point).strip()][:8],
            "validation_nodes": [str(point).strip() for point in (item.get("validation_nodes") if isinstance(item.get("validation_nodes"), list) else []) if str(point).strip()][:8],
            "sync_targets": [str(point).strip() for point in (item.get("sync_targets") if isinstance(item.get("sync_targets"), list) else []) if str(point).strip()][:8],
            "tuning_focus": [str(point).strip() for point in (item.get("tuning_focus") if isinstance(item.get("tuning_focus"), list) else []) if str(point).strip()][:8],
            "notes": notes,
            "notes_html": str(item.get("notes_html") or "").strip(),
            "files": [str(name).strip() for name in (item.get("files") if isinstance(item.get("files"), list) else []) if str(name).strip()][:12],
            "url": str(item.get("url") or "").strip(),
            "voice_minutes": item.get("voice_minutes") if isinstance(item.get("voice_minutes"), int) else None,
            "body": str(item.get("body") or raw_input).strip(),
        })
    if not normalized_items:
        normalized_items = copy.deepcopy(defaults["items"])
    return {"summary": summary, "items": normalized_items}


def resolve_tenant_knowledge_hub(tenant, config=None):
    return normalize_knowledge_hub_config(config if isinstance(config, dict) else tenant.get("knowledge_hub_config"), tenant)


def update_tenant_knowledge_hub_config(tenant_slug, knowledge_hub_config):
    site_config = get_site_config()
    tenants = get_tenant_configs(site_config)
    updated = False
    for index, tenant in enumerate(tenants):
        if tenant.get("slug") != tenant_slug:
            continue
        tenants[index] = dict(tenant)
        tenants[index]["knowledge_hub_config"] = normalize_knowledge_hub_config(knowledge_hub_config, tenant)
        updated = True
        break
    if not updated:
        return None
    next_config = dict(site_config)
    next_config["tenants"] = tenants
    return save_site_config(next_config)


def get_dashboard_card_target(layout):
    layout_key = str(layout or "").strip().lower()
    if layout_key == "3x3":
        return 6
    if layout_key == "4x4":
        return 8
    return 4


def normalize_dashboard_layout(layout):
    layout_key = str(layout or "").strip().lower()
    if layout_key in {"2x2", "3x3", "4x4"}:
        return layout_key
    return "2x2"


def build_default_fund_dashboard_cards(tenant, layout="2x2"):
    target_count = get_dashboard_card_target(layout)
    seeds = build_indicator_dashboard_seed_cards(tenant, count=target_count)
    cards = []
    for index in range(target_count):
        seed = seeds[index] if index < len(seeds) else {}
        cards.append(
            {
                "name": str(seed.get("name") or f"核心指标 {index + 1}").strip() or f"核心指标 {index + 1}",
                "value": str(seed.get("value") or "待跟踪").strip() or "待跟踪",
                "assessment": str(seed.get("assessment") or "继续观察").strip() or "继续观察",
                "status": str(seed.get("status") or "attention").strip() or "attention",
                "alert": str(seed.get("alert") or "").strip(),
                "hint": str(seed.get("hint") or seed.get("assessment") or "").strip(),
                "prompt": str(
                    seed.get("prompt")
                    or f"围绕 {seed.get('name') or f'核心指标 {index + 1}'} 生成适合普通投资者看的核心指标卡，说明当前状态、风险提醒和后续跟踪点。"
                ).strip(),
                "isEmpty": False,
            }
        )
    return cards


def normalize_fund_dashboard_view(source, tenant):
    defaults = {
        "layout": "2x2",
        "title": "今日核心指标面板",
        "note": "默认展示租户当前发布的核心指标，用于判断今天先看方向还是先控风险。",
        "updatedAt": "默认模板",
        "publisher": "系统初始化",
    }
    raw = source if isinstance(source, dict) else {}
    layout = normalize_dashboard_layout(raw.get("layout") or defaults["layout"])
    fallback_cards = build_default_fund_dashboard_cards(tenant, layout)
    raw_cards = raw.get("cards") if isinstance(raw.get("cards"), list) else []
    cards = []
    for index in range(get_dashboard_card_target(layout)):
        fallback = fallback_cards[index]
        item = raw_cards[index] if index < len(raw_cards) and isinstance(raw_cards[index], dict) else {}
        prompt = str(item.get("prompt") or fallback["prompt"]).strip()
        has_user_content = any(str(item.get(key) or "").strip() for key in ("name", "value", "assessment", "alert", "hint"))
        cards.append(
            {
                "name": str(item.get("name") or fallback["name"]).strip() or fallback["name"],
                "value": str(item.get("value") or fallback["value"]).strip() or fallback["value"],
                "assessment": str(item.get("assessment") or fallback["assessment"]).strip() or fallback["assessment"],
                "status": str(item.get("status") or fallback["status"]).strip() or fallback["status"],
                "alert": str(item.get("alert") or fallback["alert"]).strip(),
                "hint": str(item.get("hint") or fallback["hint"]).strip() or fallback["hint"],
                "prompt": prompt,
                "isEmpty": bool(item.get("isEmpty")) and not has_user_content and not prompt,
            }
        )
    title = str(raw.get("title") or defaults["title"]).strip() or defaults["title"]
    note = str(raw.get("note") or defaults["note"]).strip() or defaults["note"]
    updated_at = str(raw.get("updatedAt") or defaults["updatedAt"]).strip() or defaults["updatedAt"]
    publisher = str(raw.get("publisher") or defaults["publisher"]).strip() or defaults["publisher"]
    summary = note
    cells = [
        {
            "title": card["name"] or f"核心指标 {index + 1}",
            "value": card["value"],
            "prompt": card["prompt"],
            "assessment": card["assessment"],
            "status": card["status"],
            "alert": card["alert"],
            "hint": card["hint"],
        }
        for index, card in enumerate(cards)
    ]
    return {
        "layout": layout,
        "title": title,
        "note": note,
        "summary": summary,
        "updatedAt": updated_at,
        "publisher": publisher,
        "cards": cards,
        "cells": cells,
    }


def default_tenant_fund_dashboard_state(tenant):
    published = normalize_fund_dashboard_view(
        {
            "layout": "2x2",
            "title": "今日核心指标面板",
            "note": "默认展示租户当前发布的核心指标，用于判断今天先看方向还是先控风险。",
            "updatedAt": "默认模板",
            "publisher": "系统初始化",
        },
        tenant,
    )
    return {
        "published": published,
        "draft": None,
    }


def resolve_tenant_fund_dashboard_state(tenant, config=None):
    tenant = tenant or get_tenant_by_slug()
    defaults = default_tenant_fund_dashboard_state(tenant)
    raw = config if isinstance(config, dict) else {}
    published = normalize_fund_dashboard_view(raw.get("published"), tenant) if isinstance(raw.get("published"), dict) else copy.deepcopy(defaults["published"])
    draft = normalize_fund_dashboard_view(raw.get("draft"), tenant) if isinstance(raw.get("draft"), dict) else None
    return {
        "published": published,
        "draft": draft,
    }


def build_tenant_fund_dashboard_payload(tenant=None, config=None):
    tenant = tenant or get_tenant_by_slug()
    state = resolve_tenant_fund_dashboard_state(tenant, config if config is not None else tenant.get("fund_dashboard_config"))
    return copy.deepcopy(state["published"])


def update_tenant_fund_dashboard_config(tenant_slug, action, dashboard=None):
    action_key = str(action or "").strip().lower()
    if action_key not in {"save_draft", "publish", "reset_draft"}:
        return None
    site_config = get_site_config()
    tenants = get_tenant_configs(site_config)
    updated = False
    for index, tenant in enumerate(tenants):
        if tenant.get("slug") != tenant_slug:
            continue
        current_state = resolve_tenant_fund_dashboard_state(tenant, tenant.get("fund_dashboard_config"))
        next_state = copy.deepcopy(current_state)
        if action_key == "save_draft":
            next_state["draft"] = normalize_fund_dashboard_view(dashboard, tenant)
        elif action_key == "publish":
            candidate = dashboard if isinstance(dashboard, dict) else next_state.get("draft") or next_state.get("published")
            next_state["published"] = normalize_fund_dashboard_view(candidate, tenant)
            next_state["draft"] = None
        elif action_key == "reset_draft":
            next_state["draft"] = None
        tenants[index] = dict(tenant)
        tenants[index]["fund_dashboard_config"] = next_state
        updated = True
        break
    if not updated:
        return None
    next_config = dict(site_config)
    next_config["tenants"] = tenants
    return save_site_config(next_config)


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
    merged["llm_registry"] = normalize_llm_registry_config(merged.get("llm_registry"))
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


def is_feature_enabled(feature_name, site_config=None):
    if not feature_name:
        return True
    config = site_config or get_site_config()
    feature_flags = config.get("feature_flags", {}) if isinstance(config, dict) else {}
    return feature_flags.get(feature_name) is not False


def get_h5_login_users(site_config=None):
    users = list_users()
    return [
        ensure_user_row_defaults(user, site_config)
        for user in users
        if user.get("role") in {"investor", "dav"} and user.get("status") == "active"
    ]


def get_current_demo_profile_id():
    cached = g.get("current_demo_profile_id")
    if cached is not None:
        return cached
    profile_id = str(session.get(H5_USER_SESSION_KEY) or "").strip()
    g.current_demo_profile_id = profile_id
    return profile_id


def save_current_demo_profile_id(profile_id):
    normalized = str(profile_id or "").strip()
    if normalized:
        session[H5_USER_SESSION_KEY] = normalized
        session.permanent = True
    else:
        session.pop(H5_USER_SESSION_KEY, None)
    g.current_demo_profile_id = normalized
    return normalized


def get_current_demo_profile(site_config=None):
    current_username = get_current_demo_profile_id()
    if not current_username:
        return None
    current_user = get_user_by_username(current_username)
    if not current_user:
        session.pop(H5_USER_SESSION_KEY, None)
        g.current_demo_profile_id = ""
        return None
    if current_user.get("role") not in {"investor", "dav"} or current_user.get("status") != "active":
        session.pop(H5_USER_SESSION_KEY, None)
        g.current_demo_profile_id = ""
        return None
    return ensure_user_row_defaults(current_user, site_config)


def mask_phone(phone):
    value = str(phone or "").strip()
    if len(value) >= 7:
        return f"{value[:3]}****{value[-4:]}"
    return value


def list_users(role=None, tenant_slug=None):
    db = get_db()
    conditions = []
    params = []
    if role:
        conditions.append("role = ?")
        params.append(role)
    if tenant_slug:
        conditions.append("tenant_slug = ?")
        params.append(tenant_slug)
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = db.execute(
        f"""
        SELECT id, username, password, role, tenant_slug, advisor_name, phone, status, created_at, updated_at
        FROM users
        {where_sql}
        ORDER BY id ASC
        """,
        tuple(params),
    ).fetchall()
    return [ensure_user_row_defaults(dict(row)) for row in rows]


def get_user_by_username(username):
    db = get_db()
    row = db.execute(
        """
        SELECT id, username, password, role, tenant_slug, advisor_name, phone, status, created_at, updated_at
        FROM users
        WHERE username = ?
        """,
        (str(username or "").strip(),),
    ).fetchone()
    return ensure_user_row_defaults(dict(row)) if row else None


def create_user(payload):
    source = payload if isinstance(payload, dict) else {}
    username = str(source.get("username") or "").strip()
    password = str(source.get("password") or "").strip()
    role = str(source.get("role") or "investor").strip().lower()
    tenant_slug = str(source.get("tenant_slug") or get_default_tenant_slug()).strip().lower()
    advisor_name = str(source.get("advisor_name") or "").strip()
    phone = str(source.get("phone") or "").strip()
    status = str(source.get("status") or "active").strip().lower()
    if not username or not password or role not in {"investor", "dav", "admin"} or not phone:
        raise ValueError("invalid_user_payload")
    if get_user_by_username(username):
        raise ValueError("username_exists")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    db.execute(
        """
        INSERT INTO users (username, password, role, tenant_slug, advisor_name, phone, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (username, password, role, tenant_slug, advisor_name, phone, status, now, now),
    )
    db.commit()
    return get_user_by_username(username)


def import_users(items):
    created = []
    for item in (items or []):
        try:
            user = create_user(item)
            if user:
                created.append(user)
        except ValueError:
            continue
    return created


def ensure_user_row_defaults(user, site_config=None):
    config = site_config or get_site_config()
    tenant = get_tenant_by_slug(user.get("tenant_slug"), config)
    role = str(user.get("role", "investor") or "investor").strip().lower()
    role_label_map = {"investor": "投资者", "dav": "大V投顾", "admin": "管理员"}
    default_stats = {
        "investor": {"posts": 23, "likes": 456, "following": 12, "followers": 89, "points": 3840, "compute_credits": 128, "level": 4, "level_name": "资深分析师", "membership": "投资者视角", "relationship": "核心订阅用户", "tenant_card_title": "所属大V租户", "workbench_label": "查看当前租户工作台（demo）", "workbench_hint": "投资者视角 · 查看租户服务与互动提醒", "stat_labels": ["帖子", "获赞", "自选", "社群互动"], "badges": ["🦞 Hermes达人", "📊 投研先锋", "🧭 长期跟踪", "📅 连续签到30天"], "avatar": "👨"},
        "dav": {"posts": 86, "likes": 3688, "following": 128, "followers": 1240, "points": 9820, "compute_credits": 420, "level": 6, "level_name": "租户主理人", "membership": "大V主理视角", "relationship": "租户主理人", "tenant_card_title": "当前管理租户", "workbench_label": "进入我的大V工作台", "workbench_hint": "大V投顾视角 · 管理粉丝、内容与协同收入", "stat_labels": ["内容", "获赞", "订阅用户", "私域线索"], "badges": ["👑 种子投顾", "🦞 Hermes高频用户", "🏆 协同标杆", "💬 私域主理人"], "avatar": "👑"},
        "admin": {"posts": 0, "likes": 0, "following": 0, "followers": 0, "points": 9999, "compute_credits": 999, "level": 9, "level_name": "平台管理员", "membership": "管理员视角", "relationship": "平台管理员", "tenant_card_title": "当前管理平台", "workbench_label": "进入平台后台", "workbench_hint": "管理员视角 · 管理平台用户与租户", "stat_labels": ["用户", "租户", "权限", "系统"], "badges": ["🛡️ 平台管理员"], "avatar": "🛡️"},
    }
    defaults = default_stats.get(role, default_stats["investor"])
    advisor_name = str(user.get("advisor_name") or tenant.get("advisor") or "").strip()
    return {
        "id": user.get("id"),
        "username": str(user.get("username") or "").strip(),
        "password": str(user.get("password") or "").strip(),
        "role": role,
        "roleLabel": role_label_map.get(role, "投资者"),
        "avatar": str(user.get("avatar") or defaults["avatar"]).strip() or defaults["avatar"],
        "name": str(user.get("username") or "").strip(),
        "phone": str(user.get("phone") or "").strip(),
        "phone_masked": mask_phone(user.get("phone")),
        "status": str(user.get("status") or "active").strip(),
        "tenant_slug": tenant.get("slug"),
        "advisor_name": advisor_name,
        "tenant": {
            "id": tenant.get("id"),
            "slug": tenant.get("slug"),
            "name": tenant.get("name"),
            "advisor": tenant.get("advisor"),
            "focus": tenant.get("focus"),
            "rights": tenant.get("rights"),
            "desc": tenant.get("description"),
        },
        "level": defaults["level"],
        "levelName": defaults["level_name"],
        "points": defaults["points"],
        "computeCredits": defaults["compute_credits"],
        "posts": defaults["posts"],
        "likes": defaults["likes"],
        "following": defaults["following"],
        "followers": defaults["followers"],
        "membership": defaults["membership"],
        "relationship": defaults["relationship"],
        "statLabels": defaults["stat_labels"],
        "tenantCardTitle": defaults["tenant_card_title"],
        "badges": defaults["badges"],
        "workbenchLabel": defaults["workbench_label"],
        "workbenchHint": defaults["workbench_hint"],
    }


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
        "fund_dashboard_state": workbench["fund_dashboard_state"],
        "reviews": workbench["published_reviews"],
        "stats": workbench["stats"],
    }


def build_tenant_portal_payload(tenant=None):
    tenant = tenant or get_tenant_by_slug()
    workbench = gen_kol_workbench(tenant)
    portal_workspace = copy.deepcopy(workbench.get("portal_workspace") or {})
    dashboard_metrics = copy.deepcopy(workbench.get("dashboard_metrics") or {})
    fund_dashboard = copy.deepcopy(workbench.get("fund_dashboard") or {})
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
        "portal_workspace": portal_workspace,
        "dashboard_metrics": dashboard_metrics,
        "fund_dashboard": fund_dashboard,
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
            "primary_label": portal_workspace.get("cta", {}).get("primary_label") or "进入 H5 继续查看",
            "primary_href": f"/h5?tenant={tenant['slug']}",
            "secondary_label": portal_workspace.get("cta", {}).get("secondary_label") or "直接看最新复盘",
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


def load_market_dashboard_indicators():
    if not MARKET_DASHBOARD_REGISTRY_PATH.exists():
        return []
    try:
        payload = json.loads(MARKET_DASHBOARD_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        app.logger.exception("Failed to load market dashboard source registry")
        return []
    if not isinstance(payload, list):
        return []
    return payload


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_json_loads(value, default):
    if value in (None, ""):
        return copy.deepcopy(default)
    try:
        parsed = json.loads(value)
    except Exception:
        return copy.deepcopy(default)
    return parsed if isinstance(parsed, type(default)) else copy.deepcopy(default)


def slugify_code(value, fallback="item"):
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip()).strip("_").lower()
    return text or fallback


def coerce_float(value, default=None):
    try:
        text = str(value).replace("%", "").replace(",", "").strip()
        if not text:
            return default
        return float(text)
    except Exception:
        return default


def normalize_datetime_text(value):
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
    return text[:19].replace("T", " ")


def extract_timestamp_from_fields(fields, fallback=""):
    values = [str(item or "").strip() for item in fields if str(item or "").strip()]
    for item in values:
        normalized = normalize_datetime_text(item)
        if normalized:
            return normalized
    for index, item in enumerate(values[:-1]):
        if re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}", item) and re.fullmatch(r"\d{2}:\d{2}:\d{2}", values[index + 1]):
            return normalize_datetime_text(f"{item} {values[index + 1]}")
        if re.fullmatch(r"\d{2}:\d{2}:\d{2}", item) and re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}", values[index + 1]):
            return normalize_datetime_text(f"{values[index + 1]} {item}")
    return normalize_datetime_text(fallback or now_ts())


def extract_quoted_payload(detail):
    text = str(detail or "").strip()
    if not text:
        return ""
    match = re.search(r'="(.*)"', text)
    if match:
        return match.group(1)
    return ""


def split_endpoint_url(api_url):
    text = str(api_url or "").strip()
    if not text:
        return "", "", {}
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"}:
        return "", "", {}
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or ""
    if parsed.query:
        path = f"{path}?{parsed.query}" if path else f"?{parsed.query}"
    return base_url, path, {key: value for key, value in parse_qsl(parsed.query, keep_blank_values=True)}


def discover_payload_paths(payload, prefix=""):
    paths = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, (dict, list)):
                paths.extend(discover_payload_paths(value, next_prefix))
            else:
                paths.append(next_prefix)
    elif isinstance(payload, list):
        for index, value in enumerate(payload[:6]):
            next_prefix = f"{prefix}.{index}" if prefix else str(index)
            if isinstance(value, (dict, list)):
                paths.extend(discover_payload_paths(value, next_prefix))
            else:
                paths.append(next_prefix)
    elif prefix:
        paths.append(prefix)
    return paths


def build_source_sample_from_market_dashboard(raw):
    detail = str(raw.get("last_test_detail") or "").strip()
    extractor_type = str(raw.get("extractor_type") or "").strip().lower()
    last_tested_at = str(raw.get("last_tested_at") or "").strip()
    indicator_name = str(raw.get("indicator") or raw.get("id") or "指标").strip()
    sample = {
        "indicator": indicator_name,
        "provider": str(raw.get("provider") or "").strip(),
        "connector_type": "akshare" if str(raw.get("api_url") or "").startswith("akshare://") else ("http" if str(raw.get("api_url") or "").startswith(("http://", "https://")) else "manual"),
        "extractor_type": extractor_type or "sample",
        "status": "good" if "200" in str(raw.get("last_test_status") or "") else "attention",
        "timestamp": normalize_datetime_text(last_tested_at or now_ts()),
        "value": None,
        "raw_preview": detail[:600],
    }
    quoted = extract_quoted_payload(detail)
    if extractor_type == "text" and quoted:
        delimiter = "~" if "~" in quoted else ","
        fields = [part.strip() for part in quoted.split(delimiter)]
        sample["raw_delimiter"] = delimiter
        sample["raw_field_count"] = len(fields)
        sample["raw_fields"] = fields[:40]
        sample["timestamp"] = extract_timestamp_from_fields(fields, fallback=last_tested_at or now_ts())
        if delimiter == "~":
            sample["name"] = fields[1] if len(fields) > 1 else indicator_name
            sample["symbol"] = fields[2] if len(fields) > 2 else str(raw.get("id") or "")
            sample["value"] = coerce_float(fields[3], coerce_float(fields[0], 0.0))
            sample["prev_close"] = coerce_float(fields[4])
            sample["open"] = coerce_float(fields[5])
            sample["change"] = coerce_float(fields[31]) if len(fields) > 31 else None
            sample["change_pct"] = coerce_float(fields[32]) if len(fields) > 32 else None
            sample["high"] = coerce_float(fields[33]) if len(fields) > 33 else None
            sample["low"] = coerce_float(fields[34]) if len(fields) > 34 else None
        else:
            sample["name"] = fields[-1] if fields else indicator_name
            sample["symbol"] = str(raw.get("id") or "")
            sample["value"] = coerce_float(fields[0], 0.0)
            sample["change_pct"] = coerce_float(fields[1])
            sample["open"] = coerce_float(fields[2])
            sample["high"] = coerce_float(fields[4]) if len(fields) > 4 else None
            sample["low"] = coerce_float(fields[5]) if len(fields) > 5 else None
    elif extractor_type == "akshare":
        sample["record_summary"] = detail or f"{indicator_name} AKShare 样例"
        sample["value"] = coerce_float(re.search(r"(-?\\d+(?:\\.\\d+)?)", detail).group(1), None) if re.search(r"(-?\\d+(?:\\.\\d+)?)", detail) else None
    else:
        sample["record_summary"] = detail or f"{indicator_name} 样例预览"
    if sample["value"] is None:
        seeded_rng = random.Random(f"source-sample:{raw.get('id') or indicator_name}")
        sample["value"] = round(seeded_rng.uniform(80, 160), 2)
    change_pct = sample.get("change_pct")
    if isinstance(change_pct, (int, float)):
        if change_pct <= -1.5:
            sample["status"] = "warning"
        elif change_pct < 0:
            sample["status"] = "attention"
        else:
            sample["status"] = "good"
    return sample


def build_market_dashboard_response_mapping(raw, sample):
    return {
        "value_path": "value",
        "time_path": "timestamp",
        "status_path": "status",
        "connector_type": sample.get("connector_type") or "",
        "extractor_type": sample.get("extractor_type") or "",
        "extractor_path": str(raw.get("extractor_path") or "").strip(),
        "expected_contains": str(raw.get("expected_contains") or "").strip(),
        "request_blueprint": {
            "api_url": str(raw.get("api_url") or "").strip(),
            "request_method": str(raw.get("request_method") or "GET").strip().upper(),
            "notes": str(raw.get("notes") or "").strip(),
        },
        "discovered_paths": discover_payload_paths(sample),
    }


def build_indicator_source_seed_payload(raw, existing=None):
    api_url = str(raw.get("api_url") or "").strip()
    base_url, path, url_query = split_endpoint_url(api_url)
    headers = safe_json_loads(raw.get("headers_json"), {})
    body = safe_json_loads(raw.get("payload_json"), {})
    sample = build_source_sample_from_market_dashboard(raw)
    generated_mapping = build_market_dashboard_response_mapping(raw, sample)
    existing = existing or {}
    existing_mapping = existing.get("response_mapping") if isinstance(existing.get("response_mapping"), dict) else {}
    mapping = dict(generated_mapping)
    for key in ("value_path", "time_path", "status_path", "unit_override", "default_status", "transform_expr"):
        if existing_mapping.get(key):
            mapping[key] = existing_mapping[key]
    if existing_mapping.get("request_blueprint"):
        mapping["request_blueprint"] = existing_mapping["request_blueprint"]
    response_sample = existing.get("response_sample") if isinstance(existing.get("response_sample"), dict) and existing.get("response_sample") else sample
    source_code = slugify_code(raw.get("id") or f"{raw.get('indicator')}_source", "source")
    indicator_code = slugify_code(raw.get("id") or raw.get("indicator"), "lake_indicator")
    if api_url.startswith("akshare://"):
        base_url = existing.get("base_url") or ""
        path = existing.get("path") or ""
    return {
        "source_code": source_code,
        "indicator_code": indicator_code,
        "provider": str(raw.get("provider") or existing.get("provider") or "market_dashboard").strip(),
        "base_url": existing.get("base_url") or base_url,
        "path": existing.get("path") or path,
        "method": str(existing.get("method") or raw.get("request_method") or "GET").strip().upper(),
        "auth_type": str(existing.get("auth_type") or "none").strip(),
        "headers": existing.get("headers") if isinstance(existing.get("headers"), dict) and existing.get("headers") else headers,
        "query": existing.get("query") if isinstance(existing.get("query"), dict) and existing.get("query") else url_query,
        "body": existing.get("body") if isinstance(existing.get("body"), dict) and existing.get("body") else body,
        "response_mapping": mapping,
        "response_sample": response_sample,
        "source_status": str(existing.get("source_status") or raw.get("status") or "configured").strip(),
        "enabled": bool(existing.get("enabled", raw.get("enabled", True))),
        "last_test_status": str(existing.get("last_test_status") or raw.get("last_test_status") or "").strip(),
        "last_http_status": existing.get("last_http_status") if existing and existing.get("last_http_status") is not None else (200 if "200" in str(raw.get("last_test_status") or "") else None),
        "last_tested_at": str(existing.get("last_tested_at") or raw.get("last_tested_at") or "").strip(),
        "last_test_detail": str(existing.get("last_test_detail") or raw.get("last_test_detail") or raw.get("notes") or "").strip(),
    }


def suggest_mapping_from_payload(payload):
    paths = discover_payload_paths(payload)
    def pick(candidate_keys, fallback):
        for path in paths:
            tail = path.split(".")[-1].lower()
            if tail in candidate_keys:
                return path
        return fallback
    return {
        "value_path": pick({"value", "close", "price", "latest_value"}, "value"),
        "time_path": pick({"timestamp", "time", "date", "point_time"}, "timestamp"),
        "status_path": pick({"status", "state", "point_status"}, "status"),
    }


def build_indicator_source_preview(source_code):
    source = get_indicator_source_def(source_code)
    if not source:
        raise ValueError("indicator_source_not_found")
    sample_payload = source.get("response_sample") if isinstance(source.get("response_sample"), dict) else {}
    response_mapping = source.get("response_mapping") if isinstance(source.get("response_mapping"), dict) else {}
    suggested_mapping = suggest_mapping_from_payload(sample_payload)
    rules = list_indicator_mapping_rules(source_code=source["source_code"])
    current_rule = rules[0] if rules else None
    endpoint = f"{source.get('base_url') or ''}{source.get('path') or ''}".strip() or "未配置真实地址"
    return {
        "source_code": source["source_code"],
        "indicator_code": source["indicator_code"],
        "provider": source.get("provider") or "",
        "method": source.get("method") or "GET",
        "endpoint": endpoint,
        "connector_type": response_mapping.get("connector_type") or ("http" if str(source.get("base_url") or "").startswith(("http://", "https://")) else "sample"),
        "blueprint": {
            "extractor_type": response_mapping.get("extractor_type") or "",
            "extractor_path": response_mapping.get("extractor_path") or "",
            "expected_contains": response_mapping.get("expected_contains") or "",
            "request_blueprint": response_mapping.get("request_blueprint") if isinstance(response_mapping.get("request_blueprint"), dict) else {},
        },
        "sample_payload": sample_payload,
        "sample_payload_text": json.dumps(sample_payload, ensure_ascii=False, indent=2),
        "discovered_paths": discover_payload_paths(sample_payload)[:40],
        "suggested_mapping": {
            "value_path": response_mapping.get("value_path") or suggested_mapping["value_path"],
            "time_path": response_mapping.get("time_path") or suggested_mapping["time_path"],
            "status_path": response_mapping.get("status_path") or suggested_mapping["status_path"],
        },
        "mapping_rule": current_rule,
        "last_test_status": source.get("last_test_status") or "",
        "last_test_detail": source.get("last_test_detail") or "",
    }


def infer_source_connector_type(source):
    response_mapping = source.get("response_mapping") if isinstance(source.get("response_mapping"), dict) else {}
    connector_type = str(response_mapping.get("connector_type") or "").strip().lower()
    if connector_type:
        return connector_type
    request_blueprint = response_mapping.get("request_blueprint") if isinstance(response_mapping.get("request_blueprint"), dict) else {}
    api_url = str(request_blueprint.get("api_url") or "").strip()
    base_url = str(source.get("base_url") or "").strip()
    if api_url.startswith("akshare://"):
        return "akshare"
    if api_url.startswith(("http://", "https://")) or base_url.startswith(("http://", "https://")):
        return "http"
    return "manual"


def build_source_payload_from_text(source, raw_text):
    response_mapping = source.get("response_mapping") if isinstance(source.get("response_mapping"), dict) else {}
    base_sample = copy.deepcopy(source.get("response_sample")) if isinstance(source.get("response_sample"), dict) else {}
    payload = base_sample if isinstance(base_sample, dict) else {}
    payload.setdefault("indicator", source.get("indicator_code") or source.get("source_code") or "指标")
    payload.setdefault("provider", source.get("provider") or "")
    payload.setdefault("status", "attention")
    payload.setdefault("timestamp", now_ts())
    payload["raw_preview"] = str(raw_text or "")[:1200]
    quoted = extract_quoted_payload(raw_text)
    extractor_type = str(response_mapping.get("extractor_type") or payload.get("extractor_type") or "").strip().lower()
    text = quoted or str(raw_text or "").strip()
    delimiter = "~" if "~" in text else ("," if "," in text else "")
    if extractor_type == "text" and delimiter:
        fields = [part.strip() for part in text.split(delimiter)]
        payload["raw_delimiter"] = delimiter
        payload["raw_field_count"] = len(fields)
        payload["raw_fields"] = fields[:40]
        payload["timestamp"] = extract_timestamp_from_fields(fields, fallback=payload.get("timestamp") or now_ts())
        if delimiter == "~":
            payload["name"] = fields[1] if len(fields) > 1 else payload.get("indicator")
            payload["symbol"] = fields[2] if len(fields) > 2 else source.get("source_code")
            if coerce_float(fields[3] if len(fields) > 3 else None, None) is not None:
                payload["value"] = coerce_float(fields[3], payload.get("value"))
            payload["change"] = coerce_float(fields[31] if len(fields) > 31 else None, payload.get("change"))
            payload["change_pct"] = coerce_float(fields[32] if len(fields) > 32 else None, payload.get("change_pct"))
            payload["high"] = coerce_float(fields[33] if len(fields) > 33 else None, payload.get("high"))
            payload["low"] = coerce_float(fields[34] if len(fields) > 34 else None, payload.get("low"))
        else:
            if coerce_float(fields[0] if len(fields) > 0 else None, None) is not None:
                payload["value"] = coerce_float(fields[0], payload.get("value"))
            payload["change_pct"] = coerce_float(fields[1] if len(fields) > 1 else None, payload.get("change_pct"))
            payload["open"] = coerce_float(fields[2] if len(fields) > 2 else None, payload.get("open"))
            payload["high"] = coerce_float(fields[4] if len(fields) > 4 else None, payload.get("high"))
            payload["low"] = coerce_float(fields[5] if len(fields) > 5 else None, payload.get("low"))
            payload["name"] = fields[-1] if fields else payload.get("indicator")
    elif text:
        payload["record_summary"] = text[:240]
    if payload.get("value") is None:
        payload["value"] = round(random.Random(f"landing:{source.get('source_code')}").uniform(80, 160), 2)
    change_pct = coerce_float(payload.get("change_pct"), None)
    if change_pct is not None:
        payload["status"] = "warning" if change_pct <= -1.5 else ("attention" if change_pct < 0 else "good")
    return payload


def build_source_payload_from_live_response(source, raw_text):
    text = str(raw_text or "").strip()
    if text.startswith("{") or text.startswith("["):
        parsed = safe_json_loads(text, {})
        if isinstance(parsed, dict):
            parsed.setdefault("timestamp", now_ts())
            parsed.setdefault("status", "attention")
            return parsed
    return build_source_payload_from_text(source, text)


def persist_indicator_raw_record(source, raw_payload, fetch_mode, http_status=None, success=True, summary=""):
    timestamp = now_ts()
    batch_code = f"raw_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    db = get_db()
    payload_text = raw_payload if isinstance(raw_payload, str) else json.dumps(raw_payload, ensure_ascii=False)
    db.execute(
        """
        INSERT INTO indicator_raw_records (
            source_code, indicator_code, fetch_mode, raw_payload, http_status, success, fetched_at, batch_code, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source["source_code"],
            source["indicator_code"],
            fetch_mode,
            payload_text,
            http_status,
            1 if success else 0,
            timestamp,
            batch_code,
            timestamp,
        ),
    )
    db.execute(
        """
        INSERT INTO indicator_load_batches (
            batch_code, load_type, source_code, summary, total_points, total_indicators, success, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_code,
            "raw_landing",
            source["source_code"],
            (summary or f"已执行 {fetch_mode} 接入，原始数据已落地区。")[:240],
            1,
            1,
            1 if success else 0,
            timestamp,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM indicator_raw_records ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def execute_indicator_source_landing(source_code, prefer_live=False):
    source = get_indicator_source_def(source_code)
    if not source:
        raise ValueError("indicator_source_not_found")
    connector_type = infer_source_connector_type(source)
    response_mapping = source.get("response_mapping") if isinstance(source.get("response_mapping"), dict) else {}
    if connector_type == "http" and prefer_live and str(source.get("base_url") or "").strip():
        url = source["base_url"].rstrip("/") + "/" + source["path"].lstrip("/")
        query = source["query"] if isinstance(source["query"], dict) else {}
        if query:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}" + "&".join(f"{key}={value}" for key, value in query.items())
        body_data = None
        if source["method"] != "GET":
            body_data = json.dumps(source["body"], ensure_ascii=False).encode("utf-8")
        headers = source["headers"] if isinstance(source["headers"], dict) else {}
        if body_data is not None:
            headers = {**headers, "Content-Type": "application/json"}
        try:
            with urlopen(Request(url, data=body_data, method=source["method"], headers=headers), timeout=8) as resp:
                raw_text = resp.read().decode("utf-8", errors="ignore")
                payload = build_source_payload_from_live_response(source, raw_text)
                status_code = getattr(resp, "status", 200)
                record = persist_indicator_raw_record(
                    source,
                    payload,
                    fetch_mode="http_live",
                    http_status=status_code,
                    success=True,
                    summary=f"HTTP 实时接入成功，状态码 {status_code}。",
                )
                return {
                    "record": record,
                    "connector_type": connector_type,
                    "fetch_mode": "http_live",
                    "detail": "HTTP 实时接入成功。",
                    "used_sample": False,
                }
        except Exception as exc:
            fallback_payload = source.get("response_sample") if isinstance(source.get("response_sample"), dict) else {}
            fallback_payload = fallback_payload or {
                "value": round(random.uniform(80, 160), 2),
                "timestamp": now_ts(),
                "status": "attention",
                "fallback_reason": str(exc),
            }
            record = persist_indicator_raw_record(
                source,
                fallback_payload,
                fetch_mode="http_fallback_sample",
                http_status=None,
                success=False,
                summary=f"HTTP 实时接入失败，已回退样例：{str(exc)[:120]}",
            )
            return {
                "record": record,
                "connector_type": connector_type,
                "fetch_mode": "http_fallback_sample",
                "detail": f"HTTP 实时接入失败，已回退样例：{exc}",
                "used_sample": True,
            }
    sample_payload = source.get("response_sample") if isinstance(source.get("response_sample"), dict) else {}
    sample_payload = copy.deepcopy(sample_payload) if sample_payload else {
        "value": round(random.uniform(80, 160), 2),
        "timestamp": now_ts(),
        "status": "attention",
    }
    sample_payload.setdefault("timestamp", now_ts())
    sample_payload.setdefault("status", "attention")
    if connector_type == "http":
        fetch_mode = "http_blueprint_sample"
        summary = "HTTP Source 当前按蓝图样例入湖，可在下一步切换到真实实时接入。"
    elif connector_type == "akshare":
        sample_payload.setdefault("record_summary", str(source.get("last_test_detail") or "AKShare 蓝图样例"))
        fetch_mode = "akshare_blueprint"
        summary = "AKShare Source 当前按蓝图样例入湖，后续接真实执行器。"
    else:
        fetch_mode = "manual_blueprint"
        summary = "Manual Source 已按样例原始数据落地区。"
    record = persist_indicator_raw_record(source, sample_payload, fetch_mode=fetch_mode, http_status=200, success=True, summary=summary)
    return {
        "record": record,
        "connector_type": connector_type,
        "fetch_mode": fetch_mode,
        "detail": summary,
        "used_sample": True,
    }


def normalize_indicator_definition(payload, existing=None):
    base = dict(existing or {})
    base.update(payload or {})
    code = slugify_code(base.get("indicator_code") or base.get("indicator_name"), "indicator")
    return {
        "indicator_code": code,
        "indicator_name": str(base.get("indicator_name") or code).strip(),
        "category": str(base.get("category") or "未分类指标").strip(),
        "description": str(base.get("description") or "").strip(),
        "unit": str(base.get("unit") or "").strip(),
        "owner": str(base.get("owner") or "平台研究运营").strip(),
        "source_type": str(base.get("source_type") or "mock").strip() or "mock",
        "source_type_label": str(base.get("source_type_label") or "模拟指标").strip() or "模拟指标",
        "provider": str(base.get("provider") or "平台数据层").strip(),
        "status_hint": str(base.get("status_hint") or "attention").strip() or "attention",
        "assessment_template": str(base.get("assessment_template") or "").strip(),
        "alert_template": str(base.get("alert_template") or "").strip(),
        "watchers_json": json.dumps(base.get("watchers") if isinstance(base.get("watchers"), list) else safe_json_loads(base.get("watchers_json"), []), ensure_ascii=False),
        "display_config_json": json.dumps(base.get("display_config") if isinstance(base.get("display_config"), dict) else safe_json_loads(base.get("display_config_json"), {}), ensure_ascii=False),
        "enabled": 1 if bool(base.get("enabled", True)) else 0,
    }


def normalize_indicator_source_def(payload, existing=None):
    base = dict(existing or {})
    base.update(payload or {})
    indicator_code = slugify_code(base.get("indicator_code"), "indicator")
    source_code = slugify_code(base.get("source_code") or f"{indicator_code}_source", "source")
    method = str(base.get("method") or "GET").strip().upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        method = "GET"
    return {
        "source_code": source_code,
        "indicator_code": indicator_code,
        "provider": str(base.get("provider") or "待配置").strip(),
        "base_url": str(base.get("base_url") or "").strip(),
        "path": str(base.get("path") or "").strip(),
        "method": method,
        "auth_type": str(base.get("auth_type") or "none").strip(),
        "headers_json": json.dumps(base.get("headers") if isinstance(base.get("headers"), dict) else safe_json_loads(base.get("headers_json"), {}), ensure_ascii=False),
        "query_json": json.dumps(base.get("query") if isinstance(base.get("query"), dict) else safe_json_loads(base.get("query_json"), {}), ensure_ascii=False),
        "body_json": json.dumps(base.get("body") if isinstance(base.get("body"), dict) else safe_json_loads(base.get("body_json"), {}), ensure_ascii=False),
        "response_mapping_json": json.dumps(base.get("response_mapping") if isinstance(base.get("response_mapping"), dict) else safe_json_loads(base.get("response_mapping_json"), {}), ensure_ascii=False),
        "response_sample_json": json.dumps(base.get("response_sample") if isinstance(base.get("response_sample"), dict) else safe_json_loads(base.get("response_sample_json"), {}), ensure_ascii=False),
        "source_status": str(base.get("source_status") or "draft").strip() or "draft",
        "enabled": 1 if bool(base.get("enabled", True)) else 0,
        "last_test_status": str(base.get("last_test_status") or "").strip(),
        "last_http_status": base.get("last_http_status"),
        "last_tested_at": str(base.get("last_tested_at") or "").strip(),
        "last_test_detail": str(base.get("last_test_detail") or "").strip(),
    }


def row_to_indicator_definition(row):
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    item["watchers"] = safe_json_loads(item.get("watchers_json"), [])
    item["display_config"] = safe_json_loads(item.get("display_config_json"), {})
    return item


def row_to_indicator_source_def(row):
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    item["headers"] = safe_json_loads(item.get("headers_json"), {})
    item["query"] = safe_json_loads(item.get("query_json"), {})
    item["body"] = safe_json_loads(item.get("body_json"), {})
    item["response_mapping"] = safe_json_loads(item.get("response_mapping_json"), {})
    item["response_sample"] = safe_json_loads(item.get("response_sample_json"), {})
    return item


def list_indicator_definitions(source_type=None):
    db = get_db()
    query = "SELECT * FROM indicator_definitions"
    params = []
    if source_type:
        query += " WHERE source_type = ?"
        params.append(source_type)
    query += " ORDER BY category ASC, indicator_name ASC"
    return [row_to_indicator_definition(row) for row in db.execute(query, params).fetchall()]


def get_indicator_definition(indicator_code):
    if not indicator_code:
        return None
    db = get_db()
    row = db.execute(
        "SELECT * FROM indicator_definitions WHERE indicator_code = ?",
        (slugify_code(indicator_code, "indicator"),),
    ).fetchone()
    return row_to_indicator_definition(row) if row else None


def save_indicator_definition(payload):
    normalized = normalize_indicator_definition(payload)
    db = get_db()
    existing = get_indicator_definition(normalized["indicator_code"])
    timestamp = now_ts()
    db.execute(
        """
        INSERT INTO indicator_definitions (
            indicator_code, indicator_name, category, description, unit, owner, source_type,
            source_type_label, provider, status_hint, assessment_template, alert_template,
            watchers_json, display_config_json, enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(indicator_code) DO UPDATE SET
            indicator_name = excluded.indicator_name,
            category = excluded.category,
            description = excluded.description,
            unit = excluded.unit,
            owner = excluded.owner,
            source_type = excluded.source_type,
            source_type_label = excluded.source_type_label,
            provider = excluded.provider,
            status_hint = excluded.status_hint,
            assessment_template = excluded.assessment_template,
            alert_template = excluded.alert_template,
            watchers_json = excluded.watchers_json,
            display_config_json = excluded.display_config_json,
            enabled = excluded.enabled,
            updated_at = excluded.updated_at
        """,
        (
            normalized["indicator_code"],
            normalized["indicator_name"],
            normalized["category"],
            normalized["description"],
            normalized["unit"],
            normalized["owner"],
            normalized["source_type"],
            normalized["source_type_label"],
            normalized["provider"],
            normalized["status_hint"],
            normalized["assessment_template"],
            normalized["alert_template"],
            normalized["watchers_json"],
            normalized["display_config_json"],
            normalized["enabled"],
            existing["created_at"] if existing else timestamp,
            timestamp,
        ),
    )
    db.commit()
    return get_indicator_definition(normalized["indicator_code"])


def delete_indicator_definition(indicator_code):
    db = get_db()
    normalized_code = slugify_code(indicator_code, "indicator")
    db.execute("DELETE FROM indicator_definitions WHERE indicator_code = ?", (normalized_code,))
    db.execute("DELETE FROM indicator_source_defs WHERE indicator_code = ?", (normalized_code,))
    db.execute("DELETE FROM indicator_latest_values WHERE indicator_code = ?", (normalized_code,))
    db.execute("DELETE FROM indicator_series WHERE indicator_code = ?", (normalized_code,))
    db.execute("DELETE FROM indicator_anomalies WHERE indicator_code = ?", (normalized_code,))
    db.execute("DELETE FROM indicator_kline_points WHERE indicator_code = ?", (normalized_code,))
    db.commit()


def list_indicator_source_defs(indicator_code=None):
    db = get_db()
    query = "SELECT * FROM indicator_source_defs"
    params = []
    if indicator_code:
        query += " WHERE indicator_code = ?"
        params.append(slugify_code(indicator_code, "indicator"))
    query += " ORDER BY updated_at DESC, source_code ASC"
    return [row_to_indicator_source_def(row) for row in db.execute(query, params).fetchall()]


def get_indicator_source_def(source_code):
    if not source_code:
        return None
    db = get_db()
    row = db.execute(
        "SELECT * FROM indicator_source_defs WHERE source_code = ?",
        (slugify_code(source_code, "source"),),
    ).fetchone()
    return row_to_indicator_source_def(row) if row else None


def save_indicator_source_def(payload):
    normalized = normalize_indicator_source_def(payload)
    db = get_db()
    existing = get_indicator_source_def(normalized["source_code"])
    timestamp = now_ts()
    db.execute(
        """
        INSERT INTO indicator_source_defs (
            source_code, indicator_code, provider, base_url, path, method, auth_type,
            headers_json, query_json, body_json, response_mapping_json, response_sample_json,
            source_status, enabled, last_test_status, last_http_status, last_tested_at,
            last_test_detail, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_code) DO UPDATE SET
            indicator_code = excluded.indicator_code,
            provider = excluded.provider,
            base_url = excluded.base_url,
            path = excluded.path,
            method = excluded.method,
            auth_type = excluded.auth_type,
            headers_json = excluded.headers_json,
            query_json = excluded.query_json,
            body_json = excluded.body_json,
            response_mapping_json = excluded.response_mapping_json,
            response_sample_json = excluded.response_sample_json,
            source_status = excluded.source_status,
            enabled = excluded.enabled,
            last_test_status = excluded.last_test_status,
            last_http_status = excluded.last_http_status,
            last_tested_at = excluded.last_tested_at,
            last_test_detail = excluded.last_test_detail,
            updated_at = excluded.updated_at
        """,
        (
            normalized["source_code"],
            normalized["indicator_code"],
            normalized["provider"],
            normalized["base_url"],
            normalized["path"],
            normalized["method"],
            normalized["auth_type"],
            normalized["headers_json"],
            normalized["query_json"],
            normalized["body_json"],
            normalized["response_mapping_json"],
            normalized["response_sample_json"],
            normalized["source_status"],
            normalized["enabled"],
            normalized["last_test_status"],
            normalized["last_http_status"],
            normalized["last_tested_at"],
            normalized["last_test_detail"],
            existing["created_at"] if existing else timestamp,
            timestamp,
        ),
    )
    db.commit()
    saved = get_indicator_source_def(normalized["source_code"])
    ensure_indicator_mapping_rule_for_source(saved)
    return saved


def delete_indicator_source_def(source_code):
    db = get_db()
    normalized_code = slugify_code(source_code, "source")
    db.execute("DELETE FROM indicator_source_defs WHERE source_code = ?", (normalized_code,))
    db.execute("DELETE FROM indicator_source_tests WHERE source_code = ?", (normalized_code,))
    db.commit()


def record_indicator_source_test(source_code, success, http_status=None, latency_ms=None, response_sample="", error_message=""):
    db = get_db()
    timestamp = now_ts()
    normalized_code = slugify_code(source_code, "source")
    db.execute(
        """
        INSERT INTO indicator_source_tests (
            source_code, tested_at, success, http_status, latency_ms, response_sample, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalized_code,
            timestamp,
            1 if success else 0,
            http_status,
            latency_ms,
            response_sample[:4000],
            error_message[:1000],
        ),
    )
    db.execute(
        """
        UPDATE indicator_source_defs
        SET last_test_status = ?, last_http_status = ?, last_tested_at = ?, last_test_detail = ?, updated_at = ?
        WHERE source_code = ?
        """,
        (
            f"HTTP {http_status}" if http_status else ("SUCCESS" if success else "FAILED"),
            http_status,
            timestamp,
            (error_message or response_sample or "测试完成")[:240],
            timestamp,
            normalized_code,
        ),
    )
    db.commit()


def list_indicator_source_tests(source_code=None, limit=20):
    db = get_db()
    limit = max(1, min(int(limit or 20), 100))
    if source_code:
        rows = db.execute(
            """
            SELECT * FROM indicator_source_tests
            WHERE source_code = ?
            ORDER BY tested_at DESC, id DESC
            LIMIT ?
            """,
            (slugify_code(source_code, "source"), limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM indicator_source_tests
            ORDER BY tested_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def test_indicator_source(source_code):
    source = get_indicator_source_def(source_code)
    if not source:
        raise ValueError("indicator_source_not_found")
    start = time.time()
    if not source["base_url"]:
        sample = source["response_sample"] or {"message": "未配置真实地址，使用样例响应作为测试结果。"}
        latency_ms = int((time.time() - start) * 1000)
        sample_text = json.dumps(sample, ensure_ascii=False)
        record_indicator_source_test(source["source_code"], True, 200, latency_ms, sample_text, "")
        return {
            "success": True,
            "http_status": 200,
            "latency_ms": latency_ms,
            "response_sample": sample,
            "detail": "当前未配置真实接口地址，已使用样例响应完成测试。",
        }
    url = source["base_url"].rstrip("/") + "/" + source["path"].lstrip("/")
    query = source["query"] if isinstance(source["query"], dict) else {}
    if query:
        separator = "&" if "?" in url else "?"
        query_string = "&".join(f"{key}={value}" for key, value in query.items())
        url = f"{url}{separator}{query_string}"
    body_data = None
    if source["method"] != "GET":
        body_data = json.dumps(source["body"], ensure_ascii=False).encode("utf-8")
    headers = source["headers"] if isinstance(source["headers"], dict) else {}
    if body_data is not None:
        headers = {**headers, "Content-Type": "application/json"}
    request_obj = Request(url, data=body_data, method=source["method"], headers=headers)
    try:
        with urlopen(request_obj, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            latency_ms = int((time.time() - start) * 1000)
            status_code = getattr(resp, "status", 200)
            record_indicator_source_test(source["source_code"], True, status_code, latency_ms, raw, "")
            sample = safe_json_loads(raw, {}) if raw.strip().startswith(("{", "[")) else {"raw": raw[:1200]}
            return {
                "success": True,
                "http_status": status_code,
                "latency_ms": latency_ms,
                "response_sample": sample,
                "detail": "接口测试成功。",
            }
    except HTTPError as exc:
        latency_ms = int((time.time() - start) * 1000)
        error_text = f"HTTP {exc.code}: {exc.reason}"
        record_indicator_source_test(source["source_code"], False, exc.code, latency_ms, "", error_text)
        return {
            "success": False,
            "http_status": exc.code,
            "latency_ms": latency_ms,
            "response_sample": {},
            "detail": error_text,
        }
    except URLError as exc:
        latency_ms = int((time.time() - start) * 1000)
        error_text = f"NETWORK ERROR: {exc.reason}"
        record_indicator_source_test(source["source_code"], False, None, latency_ms, "", error_text)
        return {
            "success": False,
            "http_status": None,
            "latency_ms": latency_ms,
            "response_sample": {},
            "detail": error_text,
        }
    except Exception as exc:
        latency_ms = int((time.time() - start) * 1000)
        error_text = f"UNEXPECTED ERROR: {exc}"
        record_indicator_source_test(source["source_code"], False, None, latency_ms, "", error_text)
        return {
            "success": False,
            "http_status": None,
            "latency_ms": latency_ms,
            "response_sample": {},
            "detail": error_text,
        }


def normalize_indicator_mapping_rule(payload, existing=None):
    base = dict(existing or {})
    base.update(payload or {})
    indicator_code = slugify_code(base.get("indicator_code"), "indicator")
    source_code = slugify_code(base.get("source_code"), "source")
    rule_code = slugify_code(base.get("rule_code") or f"{indicator_code}_{source_code}_rule", "rule")
    return {
        "rule_code": rule_code,
        "indicator_code": indicator_code,
        "source_code": source_code,
        "value_path": str(base.get("value_path") or "").strip(),
        "time_path": str(base.get("time_path") or "").strip(),
        "status_path": str(base.get("status_path") or "").strip(),
        "unit_override": str(base.get("unit_override") or "").strip(),
        "default_status": str(base.get("default_status") or "attention").strip() or "attention",
        "transform_expr": str(base.get("transform_expr") or "").strip(),
        "enabled": 1 if bool(base.get("enabled", True)) else 0,
    }


def row_to_indicator_mapping_rule(row):
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    return item


def list_indicator_mapping_rules(indicator_code=None, source_code=None):
    db = get_db()
    query = "SELECT * FROM indicator_mapping_rules WHERE 1=1"
    params = []
    if indicator_code:
        query += " AND indicator_code = ?"
        params.append(slugify_code(indicator_code, "indicator"))
    if source_code:
        query += " AND source_code = ?"
        params.append(slugify_code(source_code, "source"))
    query += " ORDER BY updated_at DESC, rule_code ASC"
    return [row_to_indicator_mapping_rule(row) for row in db.execute(query, params).fetchall()]


def get_indicator_mapping_rule(rule_code):
    if not rule_code:
        return None
    db = get_db()
    row = db.execute(
        "SELECT * FROM indicator_mapping_rules WHERE rule_code = ?",
        (slugify_code(rule_code, "rule"),),
    ).fetchone()
    return row_to_indicator_mapping_rule(row) if row else None


def save_indicator_mapping_rule(payload):
    normalized = normalize_indicator_mapping_rule(payload)
    db = get_db()
    existing = get_indicator_mapping_rule(normalized["rule_code"])
    timestamp = now_ts()
    db.execute(
        """
        INSERT INTO indicator_mapping_rules (
            rule_code, indicator_code, source_code, value_path, time_path, status_path,
            unit_override, default_status, transform_expr, enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(rule_code) DO UPDATE SET
            indicator_code = excluded.indicator_code,
            source_code = excluded.source_code,
            value_path = excluded.value_path,
            time_path = excluded.time_path,
            status_path = excluded.status_path,
            unit_override = excluded.unit_override,
            default_status = excluded.default_status,
            transform_expr = excluded.transform_expr,
            enabled = excluded.enabled,
            updated_at = excluded.updated_at
        """,
        (
            normalized["rule_code"],
            normalized["indicator_code"],
            normalized["source_code"],
            normalized["value_path"],
            normalized["time_path"],
            normalized["status_path"],
            normalized["unit_override"],
            normalized["default_status"],
            normalized["transform_expr"],
            normalized["enabled"],
            existing["created_at"] if existing else timestamp,
            timestamp,
        ),
    )
    db.commit()
    return get_indicator_mapping_rule(normalized["rule_code"])


def ensure_indicator_mapping_rule_for_source(source):
    if not source:
        return None
    existing_rules = list_indicator_mapping_rules(source_code=source["source_code"])
    if existing_rules:
        return existing_rules[0]
    response_mapping = source.get("response_mapping") if isinstance(source.get("response_mapping"), dict) else {}
    return save_indicator_mapping_rule(
        {
            "rule_code": f"{source['indicator_code']}_{source['source_code']}_rule",
            "indicator_code": source["indicator_code"],
            "source_code": source["source_code"],
            "value_path": str(response_mapping.get("value_path") or response_mapping.get("value") or "value").strip(),
            "time_path": str(response_mapping.get("time_path") or response_mapping.get("timestamp") or "timestamp").strip(),
            "status_path": str(response_mapping.get("status_path") or response_mapping.get("status") or "status").strip(),
            "unit_override": str(response_mapping.get("unit_override") or "").strip(),
            "default_status": str(response_mapping.get("default_status") or "attention").strip() or "attention",
            "transform_expr": str(response_mapping.get("transform_expr") or "").strip(),
            "enabled": True,
        }
    )


def delete_indicator_mapping_rule(rule_code):
    db = get_db()
    db.execute("DELETE FROM indicator_mapping_rules WHERE rule_code = ?", (slugify_code(rule_code, "rule"),))
    db.commit()


def list_indicator_raw_records(source_code=None, limit=20):
    db = get_db()
    limit = max(1, min(int(limit or 20), 200))
    if source_code:
        rows = db.execute(
            """
            SELECT * FROM indicator_raw_records
            WHERE source_code = ?
            ORDER BY fetched_at DESC, id DESC
            LIMIT ?
            """,
            (slugify_code(source_code, "source"), limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM indicator_raw_records
            ORDER BY fetched_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_indicator_raw_record_from_source(source_code, use_last_test_sample=True):
    source = get_indicator_source_def(source_code)
    if not source:
        raise ValueError("indicator_source_not_found")
    if not use_last_test_sample:
        result = execute_indicator_source_landing(source_code, prefer_live=False)
        return result.get("record")
    tests = list_indicator_source_tests(source_code=source["source_code"], limit=1)
    test_record = tests[0] if tests else None
    if use_last_test_sample and test_record and test_record.get("response_sample"):
        raw_payload = test_record["response_sample"]
        http_status = test_record.get("http_status")
        fetch_mode = "last_test_sample"
        success = bool(test_record.get("success"))
    else:
        result = execute_indicator_source_landing(source_code, prefer_live=False)
        return result.get("record")
    return persist_indicator_raw_record(
        source,
        raw_payload,
        fetch_mode=fetch_mode,
        http_status=http_status,
        success=success,
        summary="已使用最近测试样例写入原始落地区。",
    )


def extract_path_value(payload, path):
    if not path:
        return payload
    current = payload
    for token in [part for part in str(path).split(".") if part]:
        if isinstance(current, dict):
            current = current.get(token)
        elif isinstance(current, list):
            try:
                current = current[int(token)]
            except Exception:
                return None
        else:
            return None
    return current


def run_indicator_clean_job(source_code=None, rule_code=None, raw_record_id=None):
    db = get_db()
    if raw_record_id:
        row = db.execute("SELECT * FROM indicator_raw_records WHERE id = ?", (raw_record_id,)).fetchone()
    else:
        row = None
    raw_record = dict(row) if row else None
    resolved_source_code = source_code
    if not resolved_source_code and raw_record:
        resolved_source_code = raw_record.get("source_code")
    source = get_indicator_source_def(resolved_source_code)
    if not source:
        raise ValueError("indicator_source_not_found")
    ensure_indicator_mapping_rule_for_source(source)
    rules = list_indicator_mapping_rules(source_code=source["source_code"])
    rule = get_indicator_mapping_rule(rule_code) if rule_code else (rules[0] if rules else None)
    if not rule:
        raise ValueError("mapping_rule_not_found")
    if raw_record is None:
        row = db.execute(
            "SELECT * FROM indicator_raw_records WHERE source_code = ? ORDER BY fetched_at DESC, id DESC LIMIT 1",
            (source["source_code"],),
        ).fetchone()
    if not row:
        raise ValueError("raw_record_not_found")
    raw_record = dict(row)
    payload = safe_json_loads(raw_record.get("raw_payload"), {})
    if not payload and isinstance(raw_record.get("raw_payload"), str):
        payload = {"raw": raw_record["raw_payload"]}
    job_code = f"clean_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    timestamp = now_ts()
    value = extract_path_value(payload, rule["value_path"]) if rule["value_path"] else payload.get("value", random.randint(70, 150))
    point_time = extract_path_value(payload, rule["time_path"]) if rule["time_path"] else payload.get("timestamp", timestamp)
    status = extract_path_value(payload, rule["status_path"]) if rule["status_path"] else payload.get("status", rule["default_status"])
    try:
        numeric_value = float(value)
    except Exception:
        numeric_value = float(random.randint(70, 150))
    status = str(status or rule["default_status"] or "attention")
    result_payload = {
        "indicator_code": source["indicator_code"],
        "source_code": source["source_code"],
        "point_time": str(point_time)[:19].replace("T", " "),
        "point_value": numeric_value,
        "point_status": status,
    }
    db.execute(
        """
        INSERT INTO indicator_clean_jobs (
            job_code, source_code, indicator_code, raw_record_id, mapping_rule_code,
            job_status, cleaned_points, result_summary, result_payload, error_message,
            created_at, finished_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_code,
            source["source_code"],
            source["indicator_code"],
            raw_record["id"],
            rule["rule_code"],
            "success",
            1,
            "已将原始响应标准化为单点指标数据。",
            json.dumps(result_payload, ensure_ascii=False),
            "",
            timestamp,
            timestamp,
        ),
    )
    batch_code = f"clean_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    db.execute(
        """
        INSERT INTO indicator_series (
            indicator_code, point_time, point_value, point_status, is_simulated, source_code, batch_code, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source["indicator_code"],
            result_payload["point_time"],
            numeric_value,
            status,
            0,
            source["source_code"],
            batch_code,
            timestamp,
        ),
    )
    definition = get_indicator_definition(source["indicator_code"])
    assessment = definition.get("assessment_template") if definition else "已完成标准化入湖。"
    alert = definition.get("alert_template") if definition else "已进入指标湖。"
    db.execute(
        """
        INSERT INTO indicator_latest_values (
            indicator_code, latest_value, latest_status, latest_assessment, latest_alert,
            updated_at, is_simulated, source_code, batch_code
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(indicator_code) DO UPDATE SET
            latest_value = excluded.latest_value,
            latest_status = excluded.latest_status,
            latest_assessment = excluded.latest_assessment,
            latest_alert = excluded.latest_alert,
            updated_at = excluded.updated_at,
            is_simulated = excluded.is_simulated,
            source_code = excluded.source_code,
            batch_code = excluded.batch_code
        """,
        (
            source["indicator_code"],
            f"{numeric_value:.2f}",
            status,
            assessment,
            alert,
            timestamp,
            0,
            source["source_code"],
            batch_code,
        ),
    )
    db.execute(
        """
        INSERT INTO indicator_load_batches (
            batch_code, load_type, source_code, summary, total_points, total_indicators, success, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_code,
            "clean_job",
            source["source_code"],
            "已从原始记录经映射规则清洗后写入指标湖。",
            1,
            1,
            1,
            timestamp,
        ),
    )
    db.commit()
    job_row = db.execute("SELECT * FROM indicator_clean_jobs WHERE job_code = ?", (job_code,)).fetchone()
    return dict(job_row) if job_row else None


def list_indicator_clean_jobs(source_code=None, limit=20):
    db = get_db()
    limit = max(1, min(int(limit or 20), 200))
    if source_code:
        rows = db.execute(
            """
            SELECT * FROM indicator_clean_jobs
            WHERE source_code = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (slugify_code(source_code, "source"), limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM indicator_clean_jobs
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def build_indicator_lake_trace(indicator_code, limit=12):
    normalized_code = slugify_code(indicator_code, "indicator")
    definition = get_indicator_definition(normalized_code)
    if not definition:
        raise ValueError("indicator_not_found")
    db = get_db()
    latest_row = db.execute(
        "SELECT * FROM indicator_latest_values WHERE indicator_code = ?",
        (normalized_code,),
    ).fetchone()
    latest = dict(latest_row) if latest_row else None
    series_rows = db.execute(
        """
        SELECT point_time, point_value, point_status, source_code, batch_code, is_simulated
        FROM indicator_series
        WHERE indicator_code = ?
        ORDER BY point_time DESC, id DESC
        LIMIT ?
        """,
        (normalized_code, limit),
    ).fetchall()
    series = [dict(row) for row in series_rows]
    source_defs = list_indicator_source_defs(indicator_code=normalized_code)
    source_codes = [item["source_code"] for item in source_defs]
    raw_records = []
    clean_jobs = []
    for source_code in source_codes[:6]:
        raw_records.extend(list_indicator_raw_records(source_code=source_code, limit=max(4, limit // 2)))
        clean_jobs.extend(list_indicator_clean_jobs(source_code=source_code, limit=max(4, limit // 2)))
    raw_records = sorted(raw_records, key=lambda item: (item.get("fetched_at") or "", item.get("id") or 0), reverse=True)[:limit]
    clean_jobs = sorted(clean_jobs, key=lambda item: (item.get("created_at") or "", item.get("id") or 0), reverse=True)[:limit]
    recent_batches = [
        dict(row)
        for row in db.execute(
            """
            SELECT * FROM indicator_load_batches
            WHERE source_code IN ({})
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """.format(",".join("?" for _ in source_codes) or "''"),
            [*source_codes, limit] if source_codes else [limit],
        ).fetchall()
    ] if source_codes else []
    timeline = []
    if latest:
        timeline.append(
            {
                "time": latest.get("updated_at") or "",
                "type": "latest",
                "summary": f"最新值 {latest.get('latest_value') or '--'} · {latest.get('latest_status') or '--'}",
            }
        )
    for item in raw_records[:6]:
        timeline.append(
            {
                "time": item.get("fetched_at") or "",
                "type": "raw",
                "summary": f"原始落地 {item.get('fetch_mode') or '--'} · {'成功' if item.get('success') else '失败'}",
            }
        )
    for item in clean_jobs[:6]:
        timeline.append(
            {
                "time": item.get("finished_at") or item.get("created_at") or "",
                "type": "clean",
                "summary": f"清洗任务 {item.get('job_status') or '--'} · 规则 {item.get('mapping_rule_code') or '--'}",
            }
        )
    timeline = sorted(timeline, key=lambda item: item.get("time") or "", reverse=True)[:12]
    return {
        "definition": definition,
        "latest": latest,
        "series": series,
        "source_defs": source_defs,
        "raw_records": raw_records,
        "clean_jobs": clean_jobs,
        "recent_batches": recent_batches,
        "timeline": timeline,
    }


def ensure_default_indicator_sources():
    existing = {item["source_code"] for item in list_indicator_source_defs()}
    imported = 0
    for raw in load_market_dashboard_indicators():
        indicator_name = str(raw.get("indicator", "")).strip()
        if not indicator_name:
            continue
        indicator_code = slugify_code(raw.get("id") or indicator_name, "lake_indicator")
        if not get_indicator_definition(indicator_code):
            save_indicator_definition(
                {
                    "indicator_code": indicator_code,
                    "indicator_name": indicator_name,
                    "category": str(raw.get("category") or "数据湖指标").strip(),
                    "description": str(raw.get("notes") or "用于市场与平台统一分析的外部指标源。").strip(),
                    "unit": "",
                    "owner": "market_dashboard 数据湖",
                    "source_type": "lake",
                    "source_type_label": "数据湖指标",
                    "provider": str(raw.get("provider") or "market_dashboard").strip(),
                    "status_hint": "attention",
                    "assessment_template": str(raw.get("notes") or "该指标来自 market_dashboard 数据湖，可用于平台与工作台统一分析。").strip(),
                    "alert_template": "需关注数据源刷新与连通状态",
                    "watchers": ["market_dashboard", "Admin 指标专区", "大V 工作台"],
                    "display_config": {"show_in_admin": True, "show_in_h5": False},
                    "enabled": bool(raw.get("enabled", True)),
                }
            )
        source_code = slugify_code(raw.get("id") or f"{indicator_code}_source", "source")
        existing_source = get_indicator_source_def(source_code)
        if source_code in existing and existing_source:
            seed_payload = build_indicator_source_seed_payload(raw, existing=existing_source)
            seed_payload["source_code"] = existing_source["source_code"]
            save_indicator_source_def(seed_payload)
            ensure_indicator_mapping_rule_for_source(get_indicator_source_def(source_code))
            continue
        save_indicator_source_def(build_indicator_source_seed_payload(raw))
        existing.add(source_code)
        ensure_indicator_mapping_rule_for_source(get_indicator_source_def(source_code))
        imported += 1
    for source in list_indicator_source_defs():
        ensure_indicator_mapping_rule_for_source(source)
    return imported


def build_simulated_indicator_series(indicator_id, status="good", points=8):
    rng = random.Random(f"indicator-series:{indicator_id}:{status}")
    base = round(rng.uniform(82, 128), 2)
    values = []
    current = base
    for _ in range(points):
        jump = rng.uniform(-5.8, 5.8)
        if status == "good":
            jump += rng.uniform(0.2, 1.8)
        elif status == "warning":
            jump -= rng.uniform(0.2, 1.8)
        current = round(max(18, current + jump), 2)
        values.append(current)
    start_date = datetime(2026, 5, 28)
    series = []
    for index, value in enumerate(values):
        point_status = "good"
        if status == "warning" and (index >= points - 2 or value <= min(values) + 1.2):
            point_status = "warning"
        elif status == "attention" and (index >= points - 2 or abs(value - values[max(0, index - 1)]) >= 3.5):
            point_status = "attention"
        series.append(
            {
                "date": (start_date + timedelta(days=index * 3)).strftime("%Y-%m-%d"),
                "value": value,
                "status": point_status,
            }
        )
    anomalies = []
    ranked_indexes = sorted(range(len(values)), key=lambda idx: abs(values[idx] - (values[idx - 1] if idx > 0 else values[idx])), reverse=True)
    anomaly_indexes = ranked_indexes[:1] if ranked_indexes else [0]
    if status == "warning" and len(ranked_indexes) >= 2:
        anomaly_indexes = ranked_indexes[:2]
    for idx in anomaly_indexes:
        point = series[idx]
        anomalies.append(
            {
                "date": point["date"],
                "value": point["value"],
                "status": point["status"],
                "label": "异常放大" if point["status"] == "warning" else "波动抬升",
            }
        )
    return series, anomalies


def build_simulated_indicator_kline(indicator_id, status="good", points=24):
    rng = random.Random(f"indicator-kline:{indicator_id}:{status}")
    current = round(rng.uniform(28, 68), 2)
    start_date = datetime(2026, 5, 18)
    candles = []
    for _ in range(points):
        open_price = round(current + rng.uniform(-1.6, 1.6), 2)
        close_delta = rng.uniform(-2.8, 2.8)
        if status == "good":
            close_delta += rng.uniform(0.1, 0.7)
        elif status == "warning":
            close_delta -= rng.uniform(0.1, 0.7)
        close_price = round(max(8, open_price + close_delta), 2)
        wick_high = rng.uniform(0.35, 1.6)
        wick_low = rng.uniform(0.35, 1.6)
        high_price = round(max(open_price, close_price) + wick_high, 2)
        low_price = round(max(5, min(open_price, close_price) - wick_low), 2)
        candles.append(
            {
                "date": (start_date + timedelta(days=len(candles))).strftime("%Y-%m-%d"),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
            }
        )
        current = close_price

    def moving_average(window):
        line = []
        for index, candle in enumerate(candles):
            if index + 1 < window:
                continue
            subset = candles[index - window + 1:index + 1]
            avg = round(sum(item["close"] for item in subset) / window, 2)
            line.append({"date": candle["date"], "value": avg})
        return line

    ranked_indexes = sorted(
        range(len(candles)),
        key=lambda idx: abs(candles[idx]["close"] - candles[idx]["open"]) + (candles[idx]["high"] - candles[idx]["low"]),
        reverse=True,
    )
    anomaly_indexes = ranked_indexes[:1] if ranked_indexes else [0]
    if status == "warning" and len(ranked_indexes) >= 2:
        anomaly_indexes = ranked_indexes[:2]
    anomalies = [
        {
            "date": candles[idx]["date"],
            "value": candles[idx]["close"],
            "status": status,
            "label": "波动抬升" if status != "warning" else "异常放大",
        }
        for idx in anomaly_indexes
    ]
    return {
        "candles": candles,
        "ma5": moving_average(5),
        "ma10": moving_average(10),
        "ma20": moving_average(20),
        "anomalies": anomalies,
    }


REAL_HISTORY_FACTOR_NAME_MAP = {
    "source_shanghai_index": "上证指数",
    "source_shenzhen_index": "深证指数",
    "source_hs300": "沪深300",
    "source_sse50": "上证50",
    "source_kc50": "科创50",
    "source_cyb": "创业板指",
    "source_hsi": "恒生指数",
    "source_dji": "道琼斯",
    "source_sp500": "标普500",
    "source_nasdaq": "纳斯达克",
    "source_gold": "黄金",
    "source_oil": "原油",
    "source_brent": "布伦特原油",
    "source_silver": "白银",
    "source_cpi": "CPI",
    "source_bdi": "BDI",
}


def load_market_dashboard_factor_history():
    cache_db = MARKET_DASHBOARD_CACHE_DB_PATH
    if not cache_db.exists():
        return {}
    try:
        conn = sqlite3.connect(str(cache_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT name, trade_date, close, volume
            FROM factor_history
            ORDER BY name ASC, trade_date ASC
            """
        ).fetchall()
    except Exception:
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass
    grouped = {}
    for row in rows:
        item = dict(row)
        grouped.setdefault(str(item["name"] or "").strip(), []).append(item)
    return grouped


def calc_moving_average(values, window):
    points = []
    if window <= 0:
        return points
    for index, item in enumerate(values):
        if index + 1 < window:
            continue
        subset = values[index - window + 1:index + 1]
        avg = round(sum(NumberLike(point.get("close")) for point in subset) / window, 2)
        points.append({"date": item["date"], "value": avg})
    return points


def NumberLike(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def build_real_indicator_status(latest_value, prev_value):
    if prev_value in {None, 0}:
        return "attention"
    change_ratio = (latest_value - prev_value) / abs(prev_value)
    if abs(change_ratio) >= 0.05:
        return "warning"
    if abs(change_ratio) >= 0.02:
        return "attention"
    return "good"


def build_real_indicator_anomalies(series):
    anomalies = []
    if len(series) < 2:
        return anomalies
    deltas = []
    for index in range(1, len(series)):
        prev_value = NumberLike(series[index - 1]["close"])
        current_value = NumberLike(series[index]["close"])
        if prev_value == 0:
            continue
        change_ratio = (current_value - prev_value) / abs(prev_value)
        deltas.append((index, change_ratio))
    ranked = sorted(deltas, key=lambda item: abs(item[1]), reverse=True)
    for index, change_ratio in ranked[:2]:
        point = series[index]
        status = "warning" if abs(change_ratio) >= 0.05 else "attention"
        anomalies.append(
            {
                "date": point["date"],
                "value": point["close"],
                "status": status,
                "severity": "高" if status == "warning" else "中",
                "label": "异常放大" if status == "warning" else "波动抬升",
            }
        )
    return anomalies


def build_real_indicator_kline_payload(series):
    candles = []
    for index, item in enumerate(series):
        close_value = round(NumberLike(item["close"]), 2)
        prev_close = round(NumberLike(series[index - 1]["close"]), 2) if index > 0 else close_value
        open_value = round(NumberLike(item.get("open")) or prev_close, 2)
        high_value = round(max(NumberLike(item.get("high")) or close_value, open_value, close_value), 2)
        low_value = round(min(NumberLike(item.get("low")) or close_value, open_value, close_value), 2)
        candles.append(
            {
                "date": item["date"],
                "open": open_value,
                "high": high_value,
                "low": low_value,
                "close": close_value,
            }
        )
    return {
        "candles": candles,
        "ma5": calc_moving_average(candles, 5),
        "ma10": calc_moving_average(candles, 10),
        "ma20": calc_moving_average(candles, 20),
        "anomalies": build_real_indicator_anomalies(candles),
    }


def sync_real_indicator_history_from_market_cache(force=False):
    history_map = load_market_dashboard_factor_history()
    if not history_map:
        return {"synced": False, "reason": "market_cache_unavailable", "updated": 0}
    db = get_db()
    definitions = list_indicator_definitions()
    timestamp = now_ts()
    batch_code = f"real_history_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    updated = 0
    total_points = 0
    active_sources = {item["indicator_code"]: item for item in list_indicator_source_defs()}
    for definition in definitions:
        indicator_code = definition["indicator_code"]
        factor_name = REAL_HISTORY_FACTOR_NAME_MAP.get(indicator_code)
        if not factor_name:
            continue
        source_rows = history_map.get(factor_name) or []
        if len(source_rows) < 2:
            continue
        rows = []
        for item in source_rows:
            trade_date = str(item.get("trade_date") or "").strip()
            if not trade_date:
                continue
            close_value = NumberLike(item.get("close"))
            rows.append(
                {
                    "date": trade_date,
                    "close": close_value,
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                }
            )
        rows = sorted(rows, key=lambda item: item["date"])
        if len(rows) < 2:
            continue
        source = active_sources.get(indicator_code)
        source_code = source["source_code"] if source else indicator_code
        if force:
            db.execute("DELETE FROM indicator_series WHERE indicator_code = ? AND source_code = ?", (indicator_code, source_code))
            db.execute("DELETE FROM indicator_kline_points WHERE indicator_code = ?", (indicator_code,))
            db.execute("DELETE FROM indicator_anomalies WHERE indicator_code = ?", (indicator_code,))
        else:
            existing_real = db.execute(
                "SELECT COUNT(*) AS c FROM indicator_series WHERE indicator_code = ? AND is_simulated = 0",
                (indicator_code,),
            ).fetchone()["c"]
            if existing_real:
                continue
            db.execute("DELETE FROM indicator_series WHERE indicator_code = ? AND is_simulated = 1", (indicator_code,))
            db.execute("DELETE FROM indicator_kline_points WHERE indicator_code = ? AND is_simulated = 1", (indicator_code,))
            db.execute("DELETE FROM indicator_anomalies WHERE indicator_code = ? AND is_simulated = 1", (indicator_code,))
        prev_close = NumberLike(rows[-2]["close"])
        latest_close = NumberLike(rows[-1]["close"])
        latest_status = build_real_indicator_status(latest_close, prev_close)
        for row in rows:
            point_status = build_real_indicator_status(NumberLike(row["close"]), prev_close if row["date"] == rows[-1]["date"] else NumberLike(row["close"]))
            db.execute(
                """
                INSERT INTO indicator_series (
                    indicator_code, point_time, point_value, point_status, is_simulated, source_code, batch_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indicator_code,
                    f"{row['date']} 00:00:00",
                    NumberLike(row["close"]),
                    point_status,
                    0,
                    source_code,
                    batch_code,
                    timestamp,
                ),
            )
            total_points += 1
        kline = build_real_indicator_kline_payload(rows[-60:])
        ma_lookup = {}
        for line_name in ("ma5", "ma10", "ma20"):
            for point in kline.get(line_name, []):
                ma_lookup.setdefault(point["date"], {})[line_name] = point["value"]
        for candle in kline.get("candles", []):
            ma_entry = ma_lookup.get(candle["date"], {})
            db.execute(
                """
                INSERT INTO indicator_kline_points (
                    indicator_code, point_date, open_value, high_value, low_value, close_value,
                    ma5, ma10, ma20, batch_code, is_simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indicator_code,
                    candle["date"],
                    candle["open"],
                    candle["high"],
                    candle["low"],
                    candle["close"],
                    ma_entry.get("ma5"),
                    ma_entry.get("ma10"),
                    ma_entry.get("ma20"),
                    batch_code,
                    0,
                    timestamp,
                ),
            )
        for anomaly in kline.get("anomalies", []):
            db.execute(
                """
                INSERT INTO indicator_anomalies (
                    indicator_code, anomaly_time, anomaly_value, severity, anomaly_status, anomaly_label, batch_code, is_simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indicator_code,
                    f"{anomaly['date']} 00:00:00",
                    anomaly["value"],
                    anomaly["severity"],
                    anomaly["status"],
                    anomaly["label"],
                    batch_code,
                    0,
                    timestamp,
                ),
            )
        assessment = definition.get("assessment_template") or f"{factor_name} 历史数据已从 market_dashboard 本地缓存同步入湖。"
        alert = definition.get("alert_template") or "已按真实历史数据更新。"
        db.execute(
            """
            INSERT INTO indicator_latest_values (
                indicator_code, latest_value, latest_status, latest_assessment, latest_alert,
                updated_at, is_simulated, source_code, batch_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(indicator_code) DO UPDATE SET
                latest_value = excluded.latest_value,
                latest_status = excluded.latest_status,
                latest_assessment = excluded.latest_assessment,
                latest_alert = excluded.latest_alert,
                updated_at = excluded.updated_at,
                is_simulated = excluded.is_simulated,
                source_code = excluded.source_code,
                batch_code = excluded.batch_code
            """,
            (
                indicator_code,
                f"{latest_close:.2f}",
                latest_status,
                assessment,
                alert,
                timestamp,
                0,
                source_code,
                batch_code,
            ),
        )
        updated += 1
    if updated:
        db.execute(
            """
            INSERT INTO indicator_load_batches (
                batch_code, load_type, source_code, summary, total_points, total_indicators, success, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_code,
                "market_cache_sync",
                "",
                "已从 market_dashboard 本地历史缓存同步真实指标历史，优先替代模拟序列。",
                total_points,
                updated,
                1,
                timestamp,
            ),
        )
        db.commit()
    return {"synced": bool(updated), "updated": updated, "total_points": total_points, "batch_code": batch_code if updated else ""}


def load_real_indicator_series_map(indicator_codes):
    if not indicator_codes:
        return {}
    db = get_db()
    placeholders = ",".join("?" for _ in indicator_codes)
    rows = db.execute(
        f"""
        SELECT indicator_code, point_time, point_value
        FROM indicator_series
        WHERE indicator_code IN ({placeholders}) AND is_simulated = 0
        ORDER BY point_time ASC, id ASC
        """,
        indicator_codes,
    ).fetchall()
    grouped = {}
    for row in rows:
        item = dict(row)
        grouped.setdefault(item["indicator_code"], []).append(
            {
                "date": str(item["point_time"] or "")[:10],
                "value": NumberLike(item["point_value"]),
            }
        )
    return grouped


def normalize_to_base(series, base=100.0):
    if not series:
        return []
    first = NumberLike(series[0]["value"])
    if first == 0:
        first = 1.0
    return [
        {"date": item["date"], "value": round((NumberLike(item["value"]) / first) * base, 2)}
        for item in series
    ]


def rolling_average(values, window):
    result = []
    if not values:
        return result
    for index, item in enumerate(values):
        if index + 1 < window:
            subset = values[:index + 1]
        else:
            subset = values[index - window + 1:index + 1]
        avg = round(sum(NumberLike(point["value"]) for point in subset) / max(len(subset), 1), 2)
        result.append({"date": item["date"], "value": avg})
    return result


def derive_smart_indicator_series():
    source_map = load_real_indicator_series_map([
        "source_cpi",
        "source_nasdaq",
        "source_sp500",
        "source_hsi",
        "source_hs300",
        "source_shanghai_index",
        "source_cyb",
        "source_kc50",
        "source_sse50",
        "source_gold",
    ])
    derived = {}

    nasdaq = normalize_to_base(source_map.get("source_nasdaq", []))
    sp500 = normalize_to_base(source_map.get("source_sp500", []))
    if nasdaq and sp500:
        series = []
        for left, right in zip(nasdaq, sp500):
            value = round(left["value"] * 0.6 + right["value"] * 0.4, 2)
            series.append({"date": left["date"], "value": value})
        derived["fed_rate_path"] = series

    hs300 = normalize_to_base(source_map.get("source_hs300", []))
    hsi = normalize_to_base(source_map.get("source_hsi", []))
    if hs300 and hsi:
        series = []
        for left, right in zip(hs300, hsi):
            value = round((left["value"] * 0.45 + right["value"] * 0.55), 2)
            series.append({"date": left["date"], "value": value})
        derived["southbound_flow"] = series

    sh_index = normalize_to_base(source_map.get("source_shanghai_index", []))
    cpi = normalize_to_base(source_map.get("source_cpi", []))
    if sh_index and cpi:
        series = []
        for left, right in zip(sh_index, cpi):
            value = round(left["value"] * 0.7 + (200 - right["value"]) * 0.3, 2)
            series.append({"date": left["date"], "value": value})
        derived["credit_pulse"] = rolling_average(series, 5)

    cyb = normalize_to_base(source_map.get("source_cyb", []))
    kc50 = normalize_to_base(source_map.get("source_kc50", []))
    sse50 = normalize_to_base(source_map.get("source_sse50", []))
    if cyb and kc50 and sse50:
        series = []
        for cyb_item, kc_item, sse_item in zip(cyb, kc50, sse50):
            value = round(cyb_item["value"] * 0.35 + kc_item["value"] * 0.45 + sse_item["value"] * 0.20, 2)
            series.append({"date": cyb_item["date"], "value": value})
        derived["ai_order_signal"] = rolling_average(series, 5)
    return derived


def sync_derived_smart_indicator_history(force=False):
    derived_map = derive_smart_indicator_series()
    if not derived_map:
        return {"synced": False, "reason": "real_factor_inputs_missing", "updated": 0}
    db = get_db()
    timestamp = now_ts()
    batch_code = f"derived_smart_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    updated = 0
    total_points = 0
    for indicator_code, series in derived_map.items():
        if len(series) < 2:
            continue
        if force:
            db.execute("DELETE FROM indicator_series WHERE indicator_code = ?", (indicator_code,))
            db.execute("DELETE FROM indicator_kline_points WHERE indicator_code = ?", (indicator_code,))
            db.execute("DELETE FROM indicator_anomalies WHERE indicator_code = ?", (indicator_code,))
        else:
            existing_real = db.execute(
                "SELECT COUNT(*) AS c FROM indicator_series WHERE indicator_code = ? AND is_simulated = 0",
                (indicator_code,),
            ).fetchone()["c"]
            if existing_real:
                continue
            db.execute("DELETE FROM indicator_series WHERE indicator_code = ? AND is_simulated = 1", (indicator_code,))
            db.execute("DELETE FROM indicator_kline_points WHERE indicator_code = ? AND is_simulated = 1", (indicator_code,))
            db.execute("DELETE FROM indicator_anomalies WHERE indicator_code = ? AND is_simulated = 1", (indicator_code,))
        last_prev = NumberLike(series[-2]["value"])
        last_value = NumberLike(series[-1]["value"])
        latest_status = build_real_indicator_status(last_value, last_prev)
        status_series = []
        prev_value = None
        for item in series:
            current_value = NumberLike(item["value"])
            point_status = build_real_indicator_status(current_value, prev_value if prev_value not in {None, 0} else current_value)
            prev_value = current_value
            status_series.append({"date": item["date"], "close": current_value, "status": point_status})
            db.execute(
                """
                INSERT INTO indicator_series (
                    indicator_code, point_time, point_value, point_status, is_simulated, source_code, batch_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indicator_code,
                    f"{item['date']} 00:00:00",
                    current_value,
                    point_status,
                    0,
                    "derived_real_factors",
                    batch_code,
                    timestamp,
                ),
            )
            total_points += 1
        kline = build_real_indicator_kline_payload(status_series[-60:])
        ma_lookup = {}
        for line_name in ("ma5", "ma10", "ma20"):
            for point in kline.get(line_name, []):
                ma_lookup.setdefault(point["date"], {})[line_name] = point["value"]
        for candle in kline.get("candles", []):
            ma_entry = ma_lookup.get(candle["date"], {})
            db.execute(
                """
                INSERT INTO indicator_kline_points (
                    indicator_code, point_date, open_value, high_value, low_value, close_value,
                    ma5, ma10, ma20, batch_code, is_simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indicator_code,
                    candle["date"],
                    candle["open"],
                    candle["high"],
                    candle["low"],
                    candle["close"],
                    ma_entry.get("ma5"),
                    ma_entry.get("ma10"),
                    ma_entry.get("ma20"),
                    batch_code,
                    0,
                    timestamp,
                ),
            )
        for anomaly in kline.get("anomalies", []):
            db.execute(
                """
                INSERT INTO indicator_anomalies (
                    indicator_code, anomaly_time, anomaly_value, severity, anomaly_status, anomaly_label, batch_code, is_simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indicator_code,
                    f"{anomaly['date']} 00:00:00",
                    anomaly["value"],
                    anomaly["severity"],
                    anomaly["status"],
                    anomaly["label"],
                    batch_code,
                    0,
                    timestamp,
                ),
            )
        definition = get_indicator_definition(indicator_code)
        assessment = definition.get("assessment_template") if definition else "已由真实底层因子推导生成。"
        alert = definition.get("alert_template") if definition else "已由真实底层因子推导生成。"
        db.execute(
            """
            INSERT INTO indicator_latest_values (
                indicator_code, latest_value, latest_status, latest_assessment, latest_alert,
                updated_at, is_simulated, source_code, batch_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(indicator_code) DO UPDATE SET
                latest_value = excluded.latest_value,
                latest_status = excluded.latest_status,
                latest_assessment = excluded.latest_assessment,
                latest_alert = excluded.latest_alert,
                updated_at = excluded.updated_at,
                is_simulated = excluded.is_simulated,
                source_code = excluded.source_code,
                batch_code = excluded.batch_code
            """,
            (
                indicator_code,
                f"{last_value:.2f}",
                latest_status,
                assessment,
                alert,
                timestamp,
                0,
                "derived_real_factors",
                batch_code,
            ),
        )
        updated += 1
    if updated:
        db.execute(
            """
            INSERT INTO indicator_load_batches (
                batch_code, load_type, source_code, summary, total_points, total_indicators, success, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_code,
                "derived_smart_sync",
                "derived_real_factors",
                "已由真实底层因子推导智能指标历史，替代原模拟序列。",
                total_points,
                updated,
                1,
                timestamp,
            ),
        )
        db.commit()
    return {"synced": bool(updated), "updated": updated, "total_points": total_points, "batch_code": batch_code if updated else ""}


def seed_mock_indicator_lake(force=False):
    ensure_default_indicator_sources()
    definitions = list_indicator_definitions()
    db = get_db()
    existing_latest_codes = {
        row["indicator_code"]
        for row in db.execute("SELECT indicator_code FROM indicator_latest_values").fetchall()
    }
    if existing_latest_codes and not force and len(existing_latest_codes) >= len(definitions):
        return {"seeded": False, "reason": "already_seeded"}
    if force:
        db.execute("DELETE FROM indicator_latest_values")
        db.execute("DELETE FROM indicator_series")
        db.execute("DELETE FROM indicator_anomalies")
        db.execute("DELETE FROM indicator_kline_points")
    batch_code = f"mock_seed_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    timestamp = now_ts()
    total_points = 0
    active_sources = {item["indicator_code"]: item for item in list_indicator_source_defs()}
    for definition in definitions:
        if not force and definition["indicator_code"] in existing_latest_codes:
            continue
        status = definition.get("status_hint") or "attention"
        series, anomalies = build_simulated_indicator_series(definition["indicator_code"], status=status)
        kline = build_simulated_indicator_kline(definition["indicator_code"], status=status)
        latest_point = series[-1] if series else {"value": 0, "status": status, "date": datetime.now().strftime("%Y-%m-%d")}
        latest_assessment = definition.get("assessment_template") or "当前已接入模拟指标数据。"
        latest_alert = definition.get("alert_template") or "已纳入指标监测。"
        source = active_sources.get(definition["indicator_code"])
        source_code = source["source_code"] if source else ""
        latest_value_text = f"{latest_point['value']:.2f}" if definition.get("unit") else f"{latest_point['value']:.2f}"
        db.execute(
            """
            INSERT INTO indicator_latest_values (
                indicator_code, latest_value, latest_status, latest_assessment, latest_alert,
                updated_at, is_simulated, source_code, batch_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(indicator_code) DO UPDATE SET
                latest_value = excluded.latest_value,
                latest_status = excluded.latest_status,
                latest_assessment = excluded.latest_assessment,
                latest_alert = excluded.latest_alert,
                updated_at = excluded.updated_at,
                is_simulated = excluded.is_simulated,
                source_code = excluded.source_code,
                batch_code = excluded.batch_code
            """,
            (
                definition["indicator_code"],
                latest_value_text,
                latest_point["status"],
                latest_assessment,
                latest_alert,
                timestamp,
                1,
                source_code,
                batch_code,
            ),
        )
        for point in series:
            total_points += 1
            db.execute(
                """
                INSERT INTO indicator_series (
                    indicator_code, point_time, point_value, point_status, is_simulated, source_code, batch_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    definition["indicator_code"],
                    f"{point['date']} 00:00:00",
                    point["value"],
                    point["status"],
                    1,
                    source_code,
                    batch_code,
                    timestamp,
                ),
            )
        for entry in anomalies:
            db.execute(
                """
                INSERT INTO indicator_anomalies (
                    indicator_code, anomaly_time, anomaly_value, severity, anomaly_status, anomaly_label, batch_code, is_simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    definition["indicator_code"],
                    f"{entry['date']} 00:00:00",
                    entry["value"],
                    "高" if entry["status"] == "warning" else "中",
                    entry["status"],
                    entry["label"],
                    batch_code,
                    1,
                    timestamp,
                ),
            )
        ma_lookup = {}
        for line_name in ("ma5", "ma10", "ma20"):
            for point in kline.get(line_name, []):
                ma_lookup.setdefault(point["date"], {})[line_name] = point["value"]
        for candle in kline.get("candles", []):
            ma_entry = ma_lookup.get(candle["date"], {})
            db.execute(
                """
                INSERT INTO indicator_kline_points (
                    indicator_code, point_date, open_value, high_value, low_value, close_value,
                    ma5, ma10, ma20, batch_code, is_simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    definition["indicator_code"],
                    candle["date"],
                    candle["open"],
                    candle["high"],
                    candle["low"],
                    candle["close"],
                    ma_entry.get("ma5"),
                    ma_entry.get("ma10"),
                    ma_entry.get("ma20"),
                    batch_code,
                    1,
                    timestamp,
                ),
            )
    db.execute(
        """
        INSERT INTO indicator_load_batches (
            batch_code, load_type, source_code, summary, total_points, total_indicators, success, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_code,
            "mock_seed",
            "",
            "首阶段使用模拟随机数据写入指标湖骨架，供 Admin / 工作台 / H5 统一读取。",
            total_points,
            len(definitions),
            1,
            timestamp,
        ),
    )
    db.commit()
    return {"seeded": True, "batch_code": batch_code, "total_indicators": len(definitions), "total_points": total_points}


def build_indicator_kline_from_rows(rows, anomalies):
    candles = []
    ma5 = []
    ma10 = []
    ma20 = []
    for row in rows:
        item = dict(row)
        candles.append(
            {
                "date": item["point_date"],
                "open": item["open_value"],
                "high": item["high_value"],
                "low": item["low_value"],
                "close": item["close_value"],
            }
        )
        if item["ma5"] is not None:
            ma5.append({"date": item["point_date"], "value": item["ma5"]})
        if item["ma10"] is not None:
            ma10.append({"date": item["point_date"], "value": item["ma10"]})
        if item["ma20"] is not None:
            ma20.append({"date": item["point_date"], "value": item["ma20"]})
    return {
        "candles": candles,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "anomalies": anomalies,
    }


def build_indicator_hub_from_store():
    ensure_default_indicator_sources()
    sync_real_indicator_history_from_market_cache(force=False)
    sync_derived_smart_indicator_history(force=False)
    seed_mock_indicator_lake(force=False)
    definitions = list_indicator_definitions()
    source_map = {}
    for source in list_indicator_source_defs():
        source_map.setdefault(source["indicator_code"], []).append(source)
    db = get_db()
    latest_map = {
        row["indicator_code"]: dict(row)
        for row in db.execute("SELECT * FROM indicator_latest_values").fetchall()
    }
    series_map = {}
    for row in db.execute(
        """
        SELECT indicator_code, point_time, point_value, point_status
        FROM indicator_series
        ORDER BY point_time ASC, id ASC
        """
    ).fetchall():
        item = dict(row)
        series_map.setdefault(item["indicator_code"], []).append(
            {
                "date": item["point_time"][:10],
                "value": item["point_value"],
                "status": item["point_status"],
            }
        )
    anomaly_map = {}
    for row in db.execute(
        """
        SELECT indicator_code, anomaly_time, anomaly_value, severity, anomaly_status, anomaly_label
        FROM indicator_anomalies
        ORDER BY anomaly_time DESC, id DESC
        """
    ).fetchall():
        item = dict(row)
        anomaly_map.setdefault(item["indicator_code"], []).append(
            {
                "date": item["anomaly_time"][:10],
                "value": item["anomaly_value"],
                "status": item["anomaly_status"],
                "label": item["anomaly_label"],
                "severity": item["severity"],
            }
        )
    kline_map = {}
    for row in db.execute(
        """
        SELECT indicator_code, point_date, open_value, high_value, low_value, close_value, ma5, ma10, ma20
        FROM indicator_kline_points
        ORDER BY point_date ASC, id ASC
        """
    ).fetchall():
        item = dict(row)
        kline_map.setdefault(item["indicator_code"], []).append(item)
    items = []
    for definition in definitions:
        latest = latest_map.get(definition["indicator_code"], {})
        anomalies = anomaly_map.get(definition["indicator_code"], [])
        sources = source_map.get(definition["indicator_code"], [])
        primary_source = sources[0] if sources else None
        latest_source_code = latest.get("source_code") or ""
        latest_is_simulated = bool(latest.get("is_simulated", 1))
        if latest_is_simulated:
            data_mode = "simulated"
            data_mode_label = "模拟数据"
        elif latest_source_code == "derived_real_factors":
            data_mode = "derived"
            data_mode_label = "真实因子推导"
        else:
            data_mode = "real"
            data_mode_label = "真实数据"
        item = {
            "id": definition["indicator_code"],
            "name": definition["indicator_name"],
            "category": definition["category"],
            "owner": definition["owner"],
            "value": latest.get("latest_value") or "--",
            "assessment": latest.get("latest_assessment") or definition.get("assessment_template") or "暂无说明",
            "status": latest.get("latest_status") or definition.get("status_hint") or "attention",
            "alert": latest.get("latest_alert") or definition.get("alert_template") or "暂无预警说明",
            "enabled": bool(definition.get("enabled")),
            "last_updated": latest.get("updated_at") or definition.get("updated_at") or "未记录",
            "watchers": definition.get("watchers", []),
            "history": [
                {
                    "date": point["date"],
                    "value": f"{point['value']:.2f}",
                    "status": point["status"],
                    "event": data_mode == "real" and "真实指标点已写入指标湖" or (data_mode == "derived" and "已由真实因子推导写入指标湖" or "模拟指标点已写入指标湖"),
                }
                for point in series_map.get(definition["indicator_code"], [])[-6:]
            ],
            "history_series": series_map.get(definition["indicator_code"], []),
            "history_anomalies": anomalies,
            "history_kline": build_indicator_kline_from_rows(kline_map.get(definition["indicator_code"], []), anomalies),
            "source_type": definition.get("source_type") or "mock",
            "source_type_label": definition.get("source_type_label") or "模拟指标",
            "provider": definition.get("provider") or (primary_source["provider"] if primary_source else "平台数据层"),
            "source_count": len(sources),
            "source_defs": sources,
            "latest_source_test": primary_source and {
                "status": primary_source.get("last_test_status") or "",
                "detail": primary_source.get("last_test_detail") or "",
                "tested_at": primary_source.get("last_tested_at") or "",
            } or None,
            "data_mode": data_mode,
            "data_mode_label": data_mode_label,
        }
        items.append(item)
    smart_items = [item for item in items if item["source_type"] == "smart"]
    lake_items = [item for item in items if item["source_type"] != "smart"]
    anomalies = []
    for item in items:
        for anomaly in anomaly_map.get(item["id"], [])[:2]:
            anomalies.append(
                {
                    "id": f"anomaly_{item['id']}_{anomaly['date']}",
                    "level": anomaly["severity"],
                    "title": f"{item['name']} 指标异动",
                    "summary": f"{anomaly['label']} · {item['alert']}",
                    "time": anomaly["date"],
                    "related_indicator_id": item["id"],
                }
            )
    summary = {
        "total": len(items),
        "smart_total": len(smart_items),
        "lake_total": len(lake_items),
        "enabled": sum(1 for item in items if item["enabled"]),
        "warnings": sum(1 for item in items if item["status"] == "warning"),
        "attention": sum(1 for item in items if item["status"] == "attention"),
        "anomalies": len(anomalies),
    }
    batches = [dict(row) for row in db.execute("SELECT * FROM indicator_load_batches ORDER BY created_at DESC, id DESC LIMIT 20").fetchall()]
    tests = list_indicator_source_tests(limit=20)
    raw_records = list_indicator_raw_records(limit=20)
    mapping_rules = list_indicator_mapping_rules()
    clean_jobs = list_indicator_clean_jobs(limit=20)
    return {
        "summary": summary,
        "items": items,
        "smart_items": smart_items,
        "lake_items": lake_items,
        "anomalies": anomalies,
        "definitions": definitions,
        "source_defs": list_indicator_source_defs(),
        "recent_tests": tests,
        "load_batches": batches,
        "raw_records": raw_records,
        "mapping_rules": mapping_rules,
        "clean_jobs": clean_jobs,
    }


def get_indicator_hub_snapshot():
    return build_indicator_hub_from_store()


def build_watchlist_indicator_context(indicator_hub=None):
    hub = indicator_hub or get_indicator_hub_snapshot()
    items = list(hub.get("smart_items") or []) + list(hub.get("lake_items") or [])
    by_id = {item.get("id"): item for item in items if item.get("id")}
    item_names = {str(item.get("name") or ""): item for item in items if item.get("name")}
    return {
        "hub": hub,
        "items": items,
        "by_id": by_id,
        "by_name": item_names,
        "warnings": [item for item in items if item.get("status") == "warning"],
        "attentions": [item for item in items if item.get("status") == "attention"],
        "anomalies": hub.get("anomalies") or [],
    }


def build_watchlist_signal_bundle(stock_code, stock_name, industry, context):
    normalized_code = str(stock_code or "").strip().upper()
    normalized_name = str(stock_name or "").strip()
    industry_text = str(industry or "").strip()
    items = context.get("items") or []
    warnings = context.get("warnings") or []
    attentions = context.get("attentions") or []
    anomalies = context.get("anomalies") or []

    board_signal_map = {
        "半导体制造": ["ai_order_signal", "credit_pulse", "source_hs300"],
        "动力电池": ["credit_pulse", "source_oil", "source_brent"],
        "港股互联网": ["southbound_flow", "fed_rate_path", "source_hsi"],
        "高端白酒": ["credit_pulse", "source_cpi", "source_shanghai_index"],
        "银行": ["credit_pulse", "fed_rate_path", "source_shanghai_index"],
    }
    related_ids = board_signal_map.get(industry_text, ["credit_pulse", "fed_rate_path", "southbound_flow"])
    related_items = [context["by_id"].get(item_id) for item_id in related_ids if context["by_id"].get(item_id)]
    if not related_items:
        related_items = warnings[:2] + attentions[:1]
    warning_count = sum(1 for item in related_items if item and item.get("status") == "warning")
    attention_count = sum(1 for item in related_items if item and item.get("status") == "attention")
    dominant_item = related_items[0] if related_items else (warnings[0] if warnings else (attentions[0] if attentions else None))
    board_alert_level = "warning" if warning_count else ("attention" if attention_count else "normal")
    if dominant_item:
        board_summary = f"{dominant_item.get('name') or '核心指标'}：{dominant_item.get('assessment') or dominant_item.get('alert') or '需继续观察'}"
        board_alert_text = dominant_item.get("alert") or dominant_item.get("assessment") or "当前无明显预警"
    else:
        board_summary = "当前未匹配到高优先级指标，继续观察价格、行业位置和验证节点。"
        board_alert_text = "当前无明显预警"
    relevant_anomalies = [
        item for item in anomalies
        if any(signal and item.get("related_indicator_id") == signal.get("id") for signal in related_items)
    ][:2]
    anomaly_text = "；".join(item.get("summary") or item.get("title") or "" for item in relevant_anomalies if (item.get("summary") or item.get("title")))
    thesis = []
    for item in related_items[:3]:
        if not item:
            continue
        thesis.append(f"{item.get('name')}: {item.get('assessment') or item.get('alert') or '继续观察'}")
    while len(thesis) < 3:
        thesis.append("当前需结合个股盈利、估值和行业位置继续判断。")
    metrics = []
    for item in related_items[:4]:
        if not item:
            continue
        metrics.append(
            {
                "label": item.get("name") or "指标",
                "value": item.get("value") or "--",
                "note": item.get("assessment") or item.get("alert") or "当前无说明",
            }
        )
    return {
        "stock_code": normalized_code,
        "stock_name": normalized_name,
        "industry": industry_text,
        "board_alert_level": board_alert_level,
        "board_alert_text": board_alert_text,
        "board_summary": board_summary,
        "anomaly_text": anomaly_text,
        "related_indicator_ids": [item.get("id") for item in related_items if item],
        "related_indicator_names": [item.get("name") for item in related_items if item],
        "thesis": thesis[:3],
        "metrics": metrics[:4],
        "warning_count": warning_count,
        "attention_count": attention_count,
    }


def build_fundamental_column_payload(tenant=None):
    tenant = tenant or get_tenant_by_slug()
    indicator_hub = build_indicator_hub(tenant=tenant, admin_view=False)
    return build_fundamental_column_payload_from_hub(tenant, indicator_hub)


def build_indicator_dashboard_seed_cards(tenant=None, count=8):
    tenant = tenant or get_tenant_by_slug()
    indicator_hub = build_indicator_hub(tenant=tenant, admin_view=False)
    return build_indicator_dashboard_seed_cards_from_hub(indicator_hub, count=count)


def build_data_lake_indicator_items():
    items = []
    for raw in load_market_dashboard_indicators():
        indicator_name = str(raw.get("indicator", "")).strip()
        if not indicator_name:
            continue
        enabled = bool(raw.get("enabled", True))
        source_status = str(raw.get("status", "")).strip().lower()
        test_status = str(raw.get("last_test_status", "")).strip()
        updated_at = str(raw.get("updated_at", "")).strip()
        tested_at = str(raw.get("last_tested_at", "")).strip()
        if not enabled:
            status = "warning"
        elif "200" in test_status or source_status == "configured":
            status = "good"
        elif test_status:
            status = "attention"
        else:
            status = "attention"
        current_value = test_status or ("已接入" if enabled else "未启用")
        if not enabled:
            assessment = "该数据湖指标当前被关闭，不会进入平台指标展示与异动监测。"
            alert = "需确认是否重新启用该指标"
        else:
            assessment = str(raw.get("notes", "")).strip() or "该指标来自 market_dashboard 数据湖，可用于平台与工作台统一分析。"
            alert = "已纳入数据湖指标监测" if status == "good" else "需关注数据源刷新与连通状态"
        simulated_series, simulated_anomalies = build_simulated_indicator_series(raw.get("id") or indicator_name, status=status)
        simulated_kline = build_simulated_indicator_kline(raw.get("id") or indicator_name, status=status)
        history = []
        if updated_at:
            history.append(
                {
                    "date": updated_at[:10],
                    "value": current_value,
                    "status": status,
                    "event": "数据湖源配置已同步到指标专区",
                }
            )
        if tested_at:
            history.append(
                {
                    "date": tested_at[:10],
                    "value": test_status or current_value,
                    "status": "good" if "200" in test_status else "attention",
                    "event": str(raw.get("last_test_detail", "")).strip()[:120] or "最近一次连通性测试已完成",
                }
            )
        items.append(
            {
                "id": f"lake_{raw.get('id') or indicator_name}",
                "name": indicator_name,
                "category": str(raw.get("category", "")).strip() or "数据湖指标",
                "owner": "market_dashboard 数据湖",
                "value": current_value,
                "assessment": assessment,
                "status": status,
                "alert": alert,
                "enabled": enabled,
                "last_updated": updated_at or tested_at or "未记录",
                "watchers": ["market_dashboard", "Admin 指标专区", "大V 工作台"],
                "history": history or [
                    {
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "value": current_value,
                        "status": status,
                        "event": "已从数据湖源注册表导入",
                    }
                ],
                "history_series": simulated_series,
                "history_anomalies": simulated_anomalies,
                "history_kline": simulated_kline,
                "source_type": "lake",
                "source_type_label": "数据湖指标",
                "provider": str(raw.get("provider", "")).strip() or "数据湖",
            }
        )
    return items


def build_indicator_hub(tenant=None, admin_view=False):
    tenant = tenant or get_tenant_by_slug()
    hub = copy.deepcopy(build_indicator_hub_from_store())
    advisor_name = tenant.get("advisor") if isinstance(tenant, dict) else ""
    for item in hub.get("smart_items", []):
        if advisor_name and item.get("owner") in {"平台研究运营", "平台宏观组", ""}:
            item["owner"] = advisor_name
    return hub


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


def gen_feed_boards_from_watchlist_details(watchlist_details):
    board_map = {}
    boards = []
    for item in (watchlist_details or {}).values():
        board_name = item.get("industry") or item.get("focus") or "自选股"
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
                "code": item.get("code"),
                "name": item.get("name"),
                "market": item.get("market"),
                "value": item.get("price", 0),
                "change": item.get("change", 0),
                "change_pct": item.get("change_pct", 0),
                "focus": item.get("focus") or item.get("industry") or "个股跟踪",
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

    details = {
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
    indicator_context = build_watchlist_indicator_context()
    for detail in details.values():
        signal_bundle = build_watchlist_signal_bundle(detail["code"], detail["name"], detail.get("industry"), indicator_context)
        detail["indicator_context"] = signal_bundle
        detail["focus"] = detail.get("industry") or detail.get("focus") or "个股跟踪"
        detail["alert_level"] = signal_bundle["board_alert_level"]
        detail["alert_text"] = signal_bundle["board_alert_text"]
        detail["signal_summary"] = signal_bundle["board_summary"]
        detail["anomaly_text"] = signal_bundle["anomaly_text"]
        detail["related_indicator_ids"] = signal_bundle["related_indicator_ids"]
        detail["related_indicator_names"] = signal_bundle["related_indicator_names"]
        fundamental = detail.get("fundamental") if isinstance(detail.get("fundamental"), dict) else {}
        base_summary = str(fundamental.get("summary") or "").strip()
        fundamental["summary"] = f"{base_summary} 当前关联指标信号：{signal_bundle['board_summary']}" if base_summary else signal_bundle["board_summary"]
        base_metrics = fundamental.get("metrics") if isinstance(fundamental.get("metrics"), list) else []
        metric_labels = {str(item.get('label') or '') for item in base_metrics if isinstance(item, dict)}
        for metric in signal_bundle["metrics"]:
            if metric["label"] not in metric_labels:
                base_metrics.append(metric)
        fundamental["metrics"] = base_metrics[:6]
        base_thesis = fundamental.get("thesis") if isinstance(fundamental.get("thesis"), list) else []
        fundamental["thesis"] = (base_thesis + [item for item in signal_bundle["thesis"] if item not in base_thesis])[:5]
        detail["fundamental"] = fundamental
        forecast = detail.get("forecast") if isinstance(detail.get("forecast"), dict) else {}
        if signal_bundle["board_alert_level"] == "warning":
            forecast["verdict"] = "重点观察"
            forecast["confidence"] = "中"
            forecast["band"] = f"{forecast.get('band') or ''} 当前行业关联指标存在预警，优先核查 {signal_bundle['related_indicator_names'][0] if signal_bundle['related_indicator_names'] else '核心信号'}。".strip()
        elif signal_bundle["board_alert_level"] == "attention":
            forecast["band"] = f"{forecast.get('band') or ''} 当前行业关联指标进入关注区间，建议跟踪 {signal_bundle['related_indicator_names'][0] if signal_bundle['related_indicator_names'] else '核心信号'}。".strip()
        drivers = forecast.get("drivers") if isinstance(forecast.get("drivers"), list) else []
        if signal_bundle["related_indicator_names"]:
            drivers = [
                {
                    "label": "指标湖联动",
                    "score": "+0.6" if signal_bundle["board_alert_level"] == "normal" else ("-0.9" if signal_bundle["board_alert_level"] == "warning" else "-0.3"),
                    "note": f"当前主要受 {signal_bundle['related_indicator_names'][0]} 影响",
                }
            ] + drivers
        forecast["drivers"] = drivers[:4]
        detail["forecast"] = forecast
    return details


def strip_watchlist_forecast_payload(detail):
    normalized = copy.deepcopy(detail or {})
    normalized.pop("forecast", None)
    return normalized


def apply_watchlist_feature_flags(detail, site_config=None):
    normalized = copy.deepcopy(detail or {})
    if not is_feature_enabled("stock_forecast", site_config):
        normalized = strip_watchlist_forecast_payload(normalized)
    return normalized

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


def get_app_db_connection():
    return psycopg2.connect(
        host=APP_DB_HOST,
        port=APP_DB_PORT,
        dbname=APP_DB_NAME,
        user=APP_DB_USER,
        password=APP_DB_PASSWORD,
        connect_timeout=8,
    )


def is_db_unavailable_error(error):
    return isinstance(error, OperationalError)


def build_default_demo_profiles(site_config=None):
    config = site_config or normalize_site_config(DEFAULT_SITE_CONFIG)
    profiles = []
    for item in DEFAULT_USERS:
        try:
          profiles.append(ensure_user_row_defaults(dict(item), config))
        except Exception:
          continue
    return [profile for profile in profiles if profile.get("role") in {"investor", "dav"} and profile.get("status") == "active"]


def resolve_demo_profile_fallback(site_config=None):
    profiles = build_default_demo_profiles(site_config)
    current_username = get_current_demo_profile_id()
    current = next((profile for profile in profiles if profile.get("username") == current_username), None)
    if current is None and profiles:
        current = profiles[0]
    return profiles, current


def build_tenant_dashboard_payload_fallback(tenant=None):
    tenant = tenant or normalize_tenant_config({}, 0)
    return {
        "title": tenant.get("dashboard_title") or f"{tenant.get('short_name') or tenant.get('name') or '租户'} Dashboard",
        "description": tenant.get("dashboard_description") or "当前展示为数据库不可达时的降级数据视图。",
        "tenant": tenant,
        "kpis": [
            {"label": "今日互动", "value": "128", "delta": "+12%"},
            {"label": "重点复盘", "value": "3", "delta": "待发布"},
            {"label": "关注信号", "value": "2", "delta": "优先跟踪"},
            {"label": "粉丝提问", "value": "19", "delta": "待回应"},
        ],
        "message_distribution": [],
        "message_trend": [],
        "publish_distribution": [],
        "publish_trend": [],
        "fund_dashboard": {
            "layout": "2x2",
            "cards": [],
        },
        "fund_dashboard_state": {
            "published": {"layout": "2x2", "cards": []},
            "draft": None,
        },
        "reviews": [],
        "stats": {},
    }


def build_indicator_hub_fallback(tenant=None, admin_view=False):
    tenant = tenant or normalize_tenant_config({}, 0)
    advisor_name = tenant.get("advisor") or ""
    smart_items = [
        {
            "id": "smart_market_heat",
            "name": "市场情绪温度",
            "category": "情绪信号",
            "owner": advisor_name or "平台研究运营",
            "value": "72",
            "assessment": "情绪处于偏活跃区间，适合输出结构化复盘而不是极端结论。",
            "status": "attention",
            "alert": "成交集中在主线方向，注意高位分化。",
            "enabled": True,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "watchers": [],
            "history": [],
            "history_series": [],
            "history_anomalies": [],
            "history_kline": [],
            "source_type": "smart",
            "source_type_label": "智能指标",
            "provider": "fallback",
            "source_count": 0,
            "source_defs": [],
            "latest_source_test": None,
            "data_mode": "fallback",
            "data_mode_label": "降级数据",
        },
        {
            "id": "smart_review_signal",
            "name": "复盘重点信号",
            "category": "内容生产",
            "owner": advisor_name or "平台研究运营",
            "value": "3 条",
            "assessment": "建议优先围绕强势主线、回撤风险和次日观察点组织内容。",
            "status": "normal",
            "alert": "当前无高危异常。",
            "enabled": True,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "watchers": [],
            "history": [],
            "history_series": [],
            "history_anomalies": [],
            "history_kline": [],
            "source_type": "smart",
            "source_type_label": "智能指标",
            "provider": "fallback",
            "source_count": 0,
            "source_defs": [],
            "latest_source_test": None,
            "data_mode": "fallback",
            "data_mode_label": "降级数据",
        },
    ]
    lake_items = [
        {
            "id": "lake_turnover",
            "name": "市场成交额",
            "category": "市场宽度",
            "owner": advisor_name or "平台宏观组",
            "value": "1.12 万亿",
            "assessment": "成交维持在相对活跃区间，说明主题轮动仍有承接。",
            "status": "normal",
            "alert": "量能暂未出现断崖式收缩。",
            "enabled": True,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "watchers": [],
            "history": [],
            "history_series": [],
            "history_anomalies": [],
            "history_kline": [],
            "source_type": "lake",
            "source_type_label": "数据湖指标",
            "provider": "fallback",
            "source_count": 0,
            "source_defs": [],
            "latest_source_test": None,
            "data_mode": "fallback",
            "data_mode_label": "降级数据",
        },
        {
            "id": "lake_northbound",
            "name": "北向资金净流向",
            "category": "资金流向",
            "owner": advisor_name or "平台宏观组",
            "value": "+18.6 亿",
            "assessment": "外资风险偏好温和修复，但还不足以支撑全面进攻判断。",
            "status": "attention",
            "alert": "若连续转负，需要同步调整复盘语气。",
            "enabled": True,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "watchers": [],
            "history": [],
            "history_series": [],
            "history_anomalies": [],
            "history_kline": [],
            "source_type": "lake",
            "source_type_label": "数据湖指标",
            "provider": "fallback",
            "source_count": 0,
            "source_defs": [],
            "latest_source_test": None,
            "data_mode": "fallback",
            "data_mode_label": "降级数据",
        },
    ]
    anomalies = [
        {
            "id": "fallback_anomaly_1",
            "level": "中",
            "title": "主线分化加剧",
            "summary": "高位题材出现分歧，复盘里应提示追高风险。",
            "time": datetime.now().strftime("%Y-%m-%d"),
            "related_indicator_id": "smart_market_heat",
        }
    ]
    items = smart_items + lake_items
    return {
        "summary": {
            "total": len(items),
            "smart_total": len(smart_items),
            "lake_total": len(lake_items),
            "enabled": len(items),
            "warnings": 0,
            "attention": 2,
            "anomalies": len(anomalies),
        },
        "items": items,
        "smart_items": smart_items,
        "lake_items": lake_items,
        "anomalies": anomalies,
        "definitions": [],
        "source_defs": [],
        "recent_tests": [],
        "load_batches": [],
        "raw_records": [],
        "mapping_rules": [],
        "clean_jobs": [],
    }


def build_fundamental_column_payload_from_hub(tenant, indicator_hub):
    tenant = tenant or get_tenant_by_slug()
    smart_items = list((indicator_hub or {}).get("smart_items") or [])
    anomalies = list((indicator_hub or {}).get("anomalies") or [])
    top_signals = sorted(
        smart_items,
        key=lambda item: (0 if item.get("status") == "warning" else (1 if item.get("status") == "attention" else 2), item.get("last_updated") or ""),
    )[:3]
    summary_bits = [f"{item.get('name')}: {item.get('assessment') or item.get('alert') or '继续观察'}" for item in top_signals]
    summary = "；".join(summary_bits) if summary_bits else f"{tenant.get('advisor') or '主理投顾'} 当前暂无新的重点指标解读。"
    entries = []
    for index, item in enumerate(top_signals):
        entries.append(
            {
                "title": item.get("name") or f"重点信号 {index + 1}",
                "source": "指标湖",
                "sourceDetail": item.get("category") or "核心指标",
                "summary": item.get("assessment") or item.get("alert") or "继续观察",
                "status": "ready",
                "angle": ["宏观视角", "行业视角", "验证节点"][index] if index < 3 else "研究视角",
            }
        )
    for anomaly in anomalies[:2]:
        entries.append(
            {
                "title": anomaly.get("title") or "异动提醒",
                "source": "异动监测",
                "sourceDetail": anomaly.get("time") or "最新",
                "summary": anomaly.get("summary") or "",
                "status": "ready",
                "angle": "异动跟踪",
            }
        )
    return {
        "summary": summary,
        "entries": entries[:4],
    }


def build_indicator_dashboard_seed_cards_from_hub(indicator_hub, count=8):
    cards = []
    for item in list((indicator_hub or {}).get("smart_items") or []) + list((indicator_hub or {}).get("lake_items") or []):
        cards.append(
            {
                "name": item.get("name") or "指标",
                "value": item.get("value") or "--",
                "assessment": item.get("assessment") or item.get("alert") or "继续观察",
                "status": item.get("status") or "attention",
                "alert": item.get("alert") or "",
                "hint": item.get("alert") or item.get("assessment") or "",
                "prompt": f"直接引用指标湖信号：{item.get('name') or '指标'}，用于工作台和前台基本面首页。",
                "sourceType": item.get("source_type") or "",
            }
        )
    return cards[:count]


def execute_sql_file(conn, sql_path):
    sql_text = Path(sql_path).read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql_text)
    conn.commit()


def init_db():
    sql_dir = Path(__file__).resolve().parent / "sql" / "postgres"
    with get_app_db_connection() as conn:
        execute_sql_file(conn, sql_dir / "002_app_core_tables.sql")
        execute_sql_file(conn, sql_dir / "010_review_voice_embeddings.sql")
        execute_sql_file(conn, sql_dir / "011_review_voice_embeddings_alter_legacy_columns.sql")
        try:
            execute_sql_file(conn, sql_dir / "001_enable_pgvector.sql")
            execute_sql_file(conn, sql_dir / "012_review_voice_embeddings_pgvector.sql")
            execute_sql_file(conn, sql_dir / "020_knowledge_embeddings.sql")
            execute_sql_file(conn, sql_dir / "021_knowledge_embeddings_pgvector.sql")
        except Exception:
            conn.rollback()
            execute_sql_file(conn, sql_dir / "020_knowledge_embeddings.sql")
        execute_sql_file(conn, sql_dir / "101_seed_app_core.sql")
        execute_sql_file(conn, sql_dir / "100_seed_master_data.sql")


def get_db():
    if "db" not in g:
        g.db = PgCompatConnection(get_app_db_connection())
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
    config = copy.deepcopy(DEFAULT_SITE_CONFIG)
    try:
        db = get_db()
        row = db.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?",
            (SITE_CONFIG_KEY,),
        ).fetchone()
        if row and row["setting_value"]:
            try:
                stored = json.loads(row["setting_value"])
                if isinstance(stored, dict):
                    config = _merge_site_config(config, stored)
            except Exception:
                app.logger.exception("Failed to parse site config")
    except Exception as exc:
        if is_db_unavailable_error(exc):
            app.logger.warning("Database unavailable while loading site config, using defaults")
        else:
            raise
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


def get_platform_name(site_config=None):
    return get_platform_brand(site_config).get("name", DEFAULT_BRAND_CONFIG["name"])


def get_platform_short_name(site_config=None):
    return get_platform_brand(site_config).get("short_name", DEFAULT_BRAND_CONFIG["short_name"])


def get_voice_transcription_config(site_config=None):
    config = site_config or get_site_config()
    section = config.get("voice_transcription") if isinstance(config, dict) else {}
    engine = str((section or {}).get("engine") or "local").strip().lower()
    if engine not in {"local", "api"}:
        engine = "local"
    return {"engine": engine}


def get_voice_embedding_config(site_config=None):
    config = site_config or get_site_config()
    section = config.get("voice_embedding") if isinstance(config, dict) else {}
    engine = str((section or {}).get("engine") or "local").strip().lower()
    if engine not in {"local", "api"}:
        engine = "local"
    return {"engine": engine}


def get_default_llm_config(site_config=None, purpose="general"):
    config = site_config or get_site_config()
    registry = normalize_llm_registry_config((config or {}).get("llm_registry"))
    purpose_key = str(purpose or "general").strip().lower() or "general"
    default_key = str(registry.get("default_model_key") or "").strip()
    models = registry.get("models") if isinstance(registry.get("models"), list) else []
    selected = None
    if default_key:
        for item in models:
            if not isinstance(item, dict):
                continue
            if str(item.get("key") or "").strip() == default_key:
                selected = item
                break
    if not selected:
        for item in models:
            if not isinstance(item, dict):
                continue
            if str(item.get("purpose") or "").strip().lower() != purpose_key:
                continue
            if item.get("enabled", True) is False:
                continue
            selected = item
            break
    if not selected or selected.get("enabled", True) is False:
        return None
    return normalize_llm_model_config(selected)


def _normalize_openai_compatible_base_url(base_url):
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        normalized = OPENAI_BASE_URL
    return normalized.rstrip("/")


def _extract_llm_text_content(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value.strip():
                parts.append(text_value.strip())
                continue
            if item.get("type") == "output_text" and isinstance(item.get("text"), str):
                parts.append(item.get("text").strip())
        return "\n".join(part for part in parts if part).strip()
    return ""


def call_openai_compatible_llm(model_config, system_prompt, user_prompt):
    config = normalize_llm_model_config(model_config)
    model_name = str(config.get("model_name") or "").strip()
    if not model_name:
        raise RuntimeError("llm_model_name_missing")
    api_key = str(config.get("api_key") or "").strip() or OPENAI_API_KEY
    if not api_key:
        raise RuntimeError("llm_api_key_missing")
    endpoint_base = _normalize_openai_compatible_base_url(config.get("base_url"))
    response = requests.post(
        f"{endpoint_base}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model_name,
            "temperature": 0.25,
            "messages": [
                {"role": "system", "content": str(system_prompt or "").strip()},
                {"role": "user", "content": str(user_prompt or "").strip()},
            ],
        },
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"llm_request_failed:{response.status_code}:{response.text[:240]}")
    payload = response.json()
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not choices or not isinstance(choices, list):
        raise RuntimeError("invalid_llm_payload")
    first_choice = choices[0] if isinstance(choices[0], dict) else {}
    message = first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {}
    content = _extract_llm_text_content(message.get("content"))
    if not content:
        raise RuntimeError("empty_llm_response")
    return content


def get_review_vector_db_connection():
    return psycopg2.connect(
        host=VECTOR_DB_HOST,
        port=VECTOR_DB_PORT,
        dbname=VECTOR_DB_NAME,
        user=VECTOR_DB_USER,
        password=VECTOR_DB_PASSWORD,
        connect_timeout=8,
    )


def _safe_audio_filename(filename):
    raw = os.path.basename(str(filename or "").strip())
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)
    return sanitized[:120] or f"review_voice_{int(time.time())}.webm"


def _guess_audio_content_type(filename, provided_type):
    content_type = str(provided_type or "").strip().lower()
    if content_type.startswith("audio/") or content_type in {"video/webm", "video/mp4"}:
        return content_type
    suffix = Path(str(filename or "")).suffix.lower()
    mapping = {
        ".mp3": "audio/mpeg",
        ".mp4": "audio/mp4",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
        ".mpeg": "audio/mpeg",
        ".mpga": "audio/mpeg",
    }
    return mapping.get(suffix, "application/octet-stream")


def _is_allowed_audio_upload(filename, content_type):
    suffix = Path(str(filename or "")).suffix.lower()
    normalized_type = str(content_type or "").strip().lower()
    if suffix in ALLOWED_AUDIO_EXTENSIONS:
        return True
    return normalized_type.startswith("audio/") or normalized_type in {"video/webm", "video/mp4"}


def _write_temp_audio_file(audio_bytes, filename):
    safe_suffix = Path(filename).suffix.lower() or ".webm"
    temp_dir = Path("/private/tmp") if Path("/private/tmp").exists() else Path("/tmp")
    temp_path = temp_dir / f"gangtise_review_{int(time.time() * 1000)}_{os.getpid()}{safe_suffix}"
    temp_path.write_bytes(audio_bytes)
    return temp_path


def _load_local_whisper_model():
    cached = g.get("local_whisper_model")
    if cached is not None:
        return cached
    if WhisperModel is None:
        raise RuntimeError("local_transcriber_dependency_missing")
    try:
        model = WhisperModel(
            LOCAL_WHISPER_MODEL_SIZE,
            device=LOCAL_WHISPER_DEVICE,
            compute_type=LOCAL_WHISPER_COMPUTE_TYPE,
        )
    except Exception as exc:
        raise RuntimeError(f"local_transcriber_init_failed:{exc}") from exc
    g.local_whisper_model = model
    return model


def _load_local_embedding_model():
    cached = g.get("local_embedding_model")
    if cached is not None:
        return cached
    if SentenceTransformer is None:
        raise RuntimeError("local_embedding_dependency_missing")
    try:
        model = SentenceTransformer(LOCAL_EMBEDDING_MODEL_NAME)
    except Exception as exc:
        raise RuntimeError(f"local_embedding_init_failed:{exc}") from exc
    g.local_embedding_model = model
    return model


def _ensure_review_voice_vector_table(conn):
    has_pgvector = False
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS review_voice_embeddings (
                id BIGSERIAL PRIMARY KEY,
                tenant_slug TEXT NOT NULL DEFAULT '',
                review_period TEXT NOT NULL DEFAULT '',
                entry_point TEXT NOT NULL DEFAULT '',
                vector_namespace TEXT NOT NULL DEFAULT '',
                speaker_name TEXT NOT NULL DEFAULT '',
                original_filename TEXT NOT NULL DEFAULT '',
                mime_type TEXT NOT NULL DEFAULT '',
                audio_size_bytes INTEGER NOT NULL DEFAULT 0,
                transcript_text TEXT NOT NULL,
                transcript_hash TEXT NOT NULL,
                transcription_engine TEXT NOT NULL DEFAULT '',
                transcript_model TEXT NOT NULL DEFAULT '',
                embedding_engine TEXT NOT NULL DEFAULT '',
                embedding_model TEXT NOT NULL DEFAULT '',
                embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_tenant_created ON review_voice_embeddings(tenant_slug, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_hash ON review_voice_embeddings(transcript_hash)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_namespace ON review_voice_embeddings(vector_namespace, created_at DESC)")
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception:
            conn.rollback()
            with conn.cursor() as retry_cur:
                retry_cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS review_voice_embeddings (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_slug TEXT NOT NULL DEFAULT '',
                        review_period TEXT NOT NULL DEFAULT '',
                        entry_point TEXT NOT NULL DEFAULT '',
                        vector_namespace TEXT NOT NULL DEFAULT '',
                        speaker_name TEXT NOT NULL DEFAULT '',
                        original_filename TEXT NOT NULL DEFAULT '',
                        mime_type TEXT NOT NULL DEFAULT '',
                        audio_size_bytes INTEGER NOT NULL DEFAULT 0,
                        transcript_text TEXT NOT NULL,
                        transcript_hash TEXT NOT NULL,
                        transcription_engine TEXT NOT NULL DEFAULT '',
                        transcript_model TEXT NOT NULL DEFAULT '',
                        embedding_engine TEXT NOT NULL DEFAULT '',
                        embedding_model TEXT NOT NULL DEFAULT '',
                        embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                retry_cur.execute("CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_tenant_created ON review_voice_embeddings(tenant_slug, created_at DESC)")
                retry_cur.execute("CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_hash ON review_voice_embeddings(transcript_hash)")
                retry_cur.execute("CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_namespace ON review_voice_embeddings(vector_namespace, created_at DESC)")
            conn.commit()
        with conn.cursor() as check_cur:
            check_cur.execute("ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS vector_namespace TEXT NOT NULL DEFAULT ''")
            check_cur.execute("ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS transcription_engine TEXT NOT NULL DEFAULT ''")
            check_cur.execute("ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS embedding_engine TEXT NOT NULL DEFAULT ''")
            check_cur.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            has_pgvector = bool(check_cur.fetchone()[0])
            if has_pgvector:
                check_cur.execute(
                    f"ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS embedding_vector vector({PGVECTOR_TARGET_DIM})"
                )
                try:
                    check_cur.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_vector
                        ON review_voice_embeddings
                        USING ivfflat (embedding_vector vector_cosine_ops)
                        """
                    )
                except Exception:
                    conn.rollback()
                    with conn.cursor() as recovery_cur:
                        recovery_cur.execute(
                            """
                            CREATE TABLE IF NOT EXISTS review_voice_embeddings (
                                id BIGSERIAL PRIMARY KEY,
                                tenant_slug TEXT NOT NULL DEFAULT '',
                                review_period TEXT NOT NULL DEFAULT '',
                                entry_point TEXT NOT NULL DEFAULT '',
                                speaker_name TEXT NOT NULL DEFAULT '',
                                original_filename TEXT NOT NULL DEFAULT '',
                                mime_type TEXT NOT NULL DEFAULT '',
                                audio_size_bytes INTEGER NOT NULL DEFAULT 0,
                                transcript_text TEXT NOT NULL,
                                transcript_hash TEXT NOT NULL,
                                transcript_model TEXT NOT NULL DEFAULT '',
                                embedding_model TEXT NOT NULL DEFAULT '',
                                embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                        recovery_cur.execute(
                            f"ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS embedding_vector vector({PGVECTOR_TARGET_DIM})"
                        )
    conn.commit()
    return has_pgvector


def _transcribe_audio_with_python(audio_bytes, filename, content_type):
    if not OPENAI_API_KEY:
        raise RuntimeError("openai_api_key_missing")
    response = requests.post(
        f"{OPENAI_BASE_URL}/audio/transcriptions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        data={
            "model": OPENAI_AUDIO_MODEL,
            "language": OPENAI_AUDIO_LANGUAGE,
            "response_format": "json",
            "prompt": "请尽量按原意转写中文金融复盘口述，保留主线、个股、风险提示和验证节点。",
        },
        files={"file": (filename, audio_bytes, content_type)},
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"transcription_request_failed:{response.status_code}:{response.text[:240]}")
    payload = response.json()
    transcript = str(payload.get("text") or "").strip()
    if not transcript:
        raise RuntimeError("empty_transcript")
    return transcript


def _transcribe_audio_locally(audio_bytes, filename):
    temp_path = _write_temp_audio_file(audio_bytes, filename)
    try:
        model = _load_local_whisper_model()
        segments, _info = model.transcribe(
            str(temp_path),
            language=OPENAI_AUDIO_LANGUAGE or "zh",
            vad_filter=True,
            beam_size=5,
        )
        transcript = " ".join((segment.text or "").strip() for segment in segments).strip()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"local_transcription_failed:{exc}") from exc
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
    if not transcript:
        raise RuntimeError("empty_transcript")
    return transcript


def transcribe_review_audio(audio_bytes, filename, content_type, engine="local"):
    normalized_engine = str(engine or "local").strip().lower()
    if normalized_engine == "local":
        return _transcribe_audio_locally(audio_bytes, filename), "local"
    if normalized_engine == "api":
        return _transcribe_audio_with_python(audio_bytes, filename, content_type), "api"
    raise RuntimeError("unsupported_transcription_engine")


def _build_text_embedding_with_api(text):
    if not OPENAI_API_KEY:
        raise RuntimeError("openai_api_key_missing")
    response = requests.post(
        f"{OPENAI_BASE_URL}/embeddings",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_EMBEDDING_MODEL,
            "input": text,
        },
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"embedding_request_failed:{response.status_code}:{response.text[:240]}")
    payload = response.json()
    items = payload.get("data") if isinstance(payload, dict) else None
    if not items or not isinstance(items, list):
        raise RuntimeError("invalid_embedding_payload")
    vector = items[0].get("embedding") if isinstance(items[0], dict) else None
    if not isinstance(vector, list) or not vector:
        raise RuntimeError("invalid_embedding_vector")
    return [float(value) for value in vector]


def _build_text_embedding_locally(text):
    model = _load_local_embedding_model()
    try:
        vector = model.encode(text, normalize_embeddings=True)
    except Exception as exc:
        raise RuntimeError(f"local_embedding_failed:{exc}") from exc
    try:
        values = vector.tolist()
    except Exception:
        values = list(vector)
    return [float(value) for value in values]


def build_text_embedding(text, engine="api"):
    normalized_engine = str(engine or "api").strip().lower()
    if normalized_engine == "local":
        return _build_text_embedding_locally(text), "local", LOCAL_EMBEDDING_MODEL_NAME
    if normalized_engine == "api":
        return _build_text_embedding_with_api(text), "api", OPENAI_EMBEDDING_MODEL
    raise RuntimeError("unsupported_embedding_engine")


def build_vector_namespace(embedding_engine, embedding_model):
    engine_key = str(embedding_engine or "").strip().lower() or "unknown"
    model_key = re.sub(r"[^a-z0-9]+", "_", str(embedding_model or "").strip().lower()).strip("_")
    return f"review_voice__{engine_key}__{model_key or 'default'}"


def _store_review_voice_embedding_record(
    tenant_slug,
    review_period,
    entry_point,
    vector_namespace,
    speaker_name,
    filename,
    content_type,
    audio_size_bytes,
    transcript,
    transcription_engine,
    transcript_model,
    embedding,
    embedding_engine,
    embedding_model,
):
    transcript_hash = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
    metadata = {
        "client_ip": get_client_ip(),
        "user_agent": request.headers.get("User-Agent", ""),
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "embedding_dimensions": len(embedding),
        "vector_namespace": vector_namespace,
    }
    with get_review_vector_db_connection() as conn:
        has_pgvector = _ensure_review_voice_vector_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO review_voice_embeddings (
                    tenant_slug, review_period, entry_point, vector_namespace, speaker_name,
                    original_filename, mime_type, audio_size_bytes,
                    transcript_text, transcript_hash, transcription_engine, transcript_model,
                    embedding_engine, embedding_model, embedding_json, metadata_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (
                    str(tenant_slug or "").strip(),
                    str(review_period or "").strip(),
                    str(entry_point or "").strip(),
                    str(vector_namespace or "").strip(),
                    str(speaker_name or "").strip(),
                    filename,
                    content_type,
                    int(audio_size_bytes),
                    transcript,
                    transcript_hash,
                    str(transcription_engine or "").strip(),
                    str(transcript_model or "").strip(),
                    str(embedding_engine or "").strip(),
                    str(embedding_model or "").strip(),
                    Json(embedding),
                    Json(metadata),
                ),
            )
            row = cur.fetchone()
            storage_mode = "jsonb"
            if has_pgvector and len(embedding) == PGVECTOR_TARGET_DIM:
                vector_literal = "[" + ",".join(f"{float(value):.10f}" for value in embedding) + "]"
                cur.execute(
                    "UPDATE review_voice_embeddings SET embedding_vector = %s::vector WHERE id = %s",
                    (vector_literal, row[0]),
                )
                storage_mode = "pgvector"
        conn.commit()
    return {
        "id": int(row[0]),
        "created_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
        "storage_mode": storage_mode,
        "embedding_dimensions": len(embedding),
        "transcript_hash": transcript_hash,
        "vector_namespace": vector_namespace,
    }


def _ensure_knowledge_embedding_table(conn):
    has_pgvector = False
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                id BIGSERIAL PRIMARY KEY,
                tenant_slug TEXT NOT NULL DEFAULT '',
                knowledge_id TEXT NOT NULL DEFAULT '',
                knowledge_type TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                body_text TEXT NOT NULL DEFAULT '',
                source_detail TEXT NOT NULL DEFAULT '',
                vector_namespace TEXT NOT NULL DEFAULT '',
                embedding_engine TEXT NOT NULL DEFAULT '',
                embedding_model TEXT NOT NULL DEFAULT '',
                embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_tenant_created ON knowledge_embeddings(tenant_slug, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_knowledge_id ON knowledge_embeddings(knowledge_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_namespace ON knowledge_embeddings(vector_namespace, created_at DESC)")
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception:
            conn.rollback()
            with conn.cursor() as retry_cur:
                retry_cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_slug TEXT NOT NULL DEFAULT '',
                        knowledge_id TEXT NOT NULL DEFAULT '',
                        knowledge_type TEXT NOT NULL DEFAULT '',
                        title TEXT NOT NULL DEFAULT '',
                        summary TEXT NOT NULL DEFAULT '',
                        body_text TEXT NOT NULL DEFAULT '',
                        source_detail TEXT NOT NULL DEFAULT '',
                        vector_namespace TEXT NOT NULL DEFAULT '',
                        embedding_engine TEXT NOT NULL DEFAULT '',
                        embedding_model TEXT NOT NULL DEFAULT '',
                        embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                retry_cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_tenant_created ON knowledge_embeddings(tenant_slug, created_at DESC)")
                retry_cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_knowledge_id ON knowledge_embeddings(knowledge_id)")
                retry_cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_namespace ON knowledge_embeddings(vector_namespace, created_at DESC)")
            conn.commit()
        with conn.cursor() as check_cur:
            check_cur.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            has_pgvector = bool(check_cur.fetchone()[0])
            if has_pgvector:
                check_cur.execute(
                    f"ALTER TABLE knowledge_embeddings ADD COLUMN IF NOT EXISTS embedding_vector vector({PGVECTOR_TARGET_DIM})"
                )
    conn.commit()
    return has_pgvector


def _store_knowledge_embedding_record(
    tenant_slug,
    knowledge_id,
    knowledge_type,
    title,
    summary,
    body_text,
    source_detail,
    vector_namespace,
    embedding,
    embedding_engine,
    embedding_model,
    metadata,
):
    with get_review_vector_db_connection() as conn:
        has_pgvector = _ensure_knowledge_embedding_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO knowledge_embeddings (
                    tenant_slug, knowledge_id, knowledge_type, title, summary, body_text, source_detail,
                    vector_namespace, embedding_engine, embedding_model, embedding_json, metadata_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (
                    str(tenant_slug or "").strip(),
                    str(knowledge_id or "").strip(),
                    str(knowledge_type or "").strip(),
                    str(title or "").strip(),
                    str(summary or "").strip(),
                    str(body_text or "").strip(),
                    str(source_detail or "").strip(),
                    str(vector_namespace or "").strip(),
                    str(embedding_engine or "").strip(),
                    str(embedding_model or "").strip(),
                    Json(embedding),
                    Json(metadata or {}),
                ),
            )
            row = cur.fetchone()
            storage_mode = "jsonb"
            if has_pgvector and len(embedding) == PGVECTOR_TARGET_DIM:
                vector_literal = "[" + ",".join(f"{float(value):.10f}" for value in embedding) + "]"
                cur.execute(
                    "UPDATE knowledge_embeddings SET embedding_vector = %s::vector WHERE id = %s",
                    (vector_literal, row[0]),
                )
                storage_mode = "pgvector"
        conn.commit()
    return {
        "id": int(row[0]),
        "created_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
        "storage_mode": storage_mode,
        "embedding_dimensions": len(embedding),
        "vector_namespace": vector_namespace,
    }


def save_manual_knowledge_entry(tenant_slug, title="", summary="", body="", raw_html="", notes="", notes_html="", knowledge_id="", skip_ai_processing=True):
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or tenant.get("slug") != tenant_slug:
        raise ValueError("tenant_not_found")
    normalized_title = str(title or "").strip() or "最新文本知识整理"
    normalized_summary = str(summary or "").strip() or "已通过纯文本方式沉淀知识内容。"
    normalized_body = str(body or "").strip() or normalized_summary
    embedding_cfg = get_voice_embedding_config()
    embedding, embedding_engine, embedding_model = build_text_embedding(
        f"{normalized_title}\n\n{normalized_summary}\n\n{normalized_body}",
        engine=embedding_cfg.get("engine", "api"),
    )
    vector_namespace = build_vector_namespace(embedding_engine, embedding_model)
    source_detail = f"来源：纯文本编写 · {max(1, len(normalized_body))}字"
    next_id = str(knowledge_id or f"kb-manual-{int(time.time() * 1000)}").strip()
    vector_record = _store_knowledge_embedding_record(
        tenant_slug=tenant_slug,
        knowledge_id=next_id,
        knowledge_type="manual",
        title=normalized_title,
        summary=normalized_summary,
        body_text=normalized_body,
        source_detail=source_detail,
        vector_namespace=vector_namespace,
        embedding=embedding,
        embedding_engine=embedding_engine,
        embedding_model=embedding_model,
        metadata={
            "notes": str(notes or "").strip(),
            "source": "纯文本编写",
            "skip_ai_processing": bool(skip_ai_processing),
        },
    )
    current_hub = resolve_tenant_knowledge_hub(tenant, tenant.get("knowledge_hub_config"))
    items = copy.deepcopy(current_hub.get("items") or [])
    entry = {
        "id": next_id,
        "type": "manual",
        "title": normalized_title,
        "source": "纯文本编写",
        "source_detail": source_detail,
        "status": "已同步 Hermes",
        "summary": normalized_summary,
        "tags": ["手动编写", "观点沉淀"],
        "raw_input": normalized_body,
        "raw_html": str(raw_html or "").strip(),
        "key_points": [segment.strip() for segment in re.split(r"[。；;\\n]+", normalized_summary) if segment.strip()][:3] or ["待补充关键要点"],
        "validation_nodes": ["待补充验证节点"],
        "sync_targets": ["租户知识队列", "知识专区", "Hermes 上下文", "向量知识库"],
        "tuning_focus": ["补充摘要", "补充验证节点", "继续细化表达"],
        "notes": str(notes or "纯文本知识已入库，可继续补充结构化要点。").strip(),
        "notes_html": str(notes_html or "").strip(),
        "files": [],
        "url": "",
        "skip_ai_processing": bool(skip_ai_processing),
        "body": normalized_body,
        "vector_record": vector_record,
    }
    replaced = False
    for index, item in enumerate(items):
        if str(item.get("id") or "") == next_id:
            items[index] = entry
            replaced = True
            break
    if not replaced:
        items.insert(0, entry)
    saved = update_tenant_knowledge_hub_config(tenant_slug, {
        "summary": current_hub.get("summary") or "",
        "items": items,
    })
    latest_tenant = get_tenant_by_slug(tenant_slug, saved) if saved else tenant
    latest_hub = resolve_tenant_knowledge_hub(latest_tenant, latest_tenant.get("knowledge_hub_config"))
    return {
        "entry": entry,
        "knowledge_hub": latest_hub,
        "vector_record": vector_record,
        "embedding_engine": embedding_engine,
        "embedding_model": embedding_model,
    }


def _build_live_knowledge_entry_from_record(record, config_item=None):
    config_item = config_item if isinstance(config_item, dict) else {}
    item_type = str(record.get("knowledge_type") or config_item.get("type") or "manual").strip().lower()
    if item_type not in {"voice", "file", "url", "manual"}:
        item_type = "manual"
    metadata = record.get("metadata_json") if isinstance(record.get("metadata_json"), dict) else {}
    summary_text = str(record.get("summary") or config_item.get("summary") or "").strip()
    body_text = str(record.get("body_text") or config_item.get("body") or config_item.get("raw_input") or summary_text).strip()
    source_text = str(
        config_item.get("source")
        or metadata.get("source")
        or ("纯文本编写" if item_type == "manual" else record.get("title") or "知识内容")
    ).strip()
    notes_text = str(config_item.get("notes") or metadata.get("notes") or "知识已进入向量库，可继续补充结构化信息。").strip()
    title_text = str(record.get("title") or config_item.get("title") or "知识内容").strip() or "知识内容"
    created_at = record.get("created_at")
    return {
        "id": str(record.get("knowledge_id") or config_item.get("id") or "").strip() or f"kb-live-{record.get('id')}",
        "type": item_type,
        "title": title_text,
        "source": source_text,
        "source_detail": str(record.get("source_detail") or config_item.get("source_detail") or "").strip(),
        "status": str(config_item.get("status") or "已同步 Hermes").strip() or "已同步 Hermes",
        "summary": summary_text,
        "tags": [str(tag).strip() for tag in (config_item.get("tags") if isinstance(config_item.get("tags"), list) else []) if str(tag).strip()][:8] or (
            ["手动编写", "观点沉淀"] if item_type == "manual" else [item_type.upper(), "已入向量库"]
        ),
        "raw_input": str(config_item.get("raw_input") or body_text).strip(),
        "raw_html": str(config_item.get("raw_html") or "").strip(),
        "key_points": [str(point).strip() for point in (config_item.get("key_points") if isinstance(config_item.get("key_points"), list) else []) if str(point).strip()][:8]
            or [segment.strip() for segment in re.split(r"[。；;\n]+", summary_text) if segment.strip()][:3]
            or ["待补充关键要点"],
        "validation_nodes": [str(point).strip() for point in (config_item.get("validation_nodes") if isinstance(config_item.get("validation_nodes"), list) else []) if str(point).strip()][:8]
            or ["待补充验证节点"],
        "sync_targets": [str(point).strip() for point in (config_item.get("sync_targets") if isinstance(config_item.get("sync_targets"), list) else []) if str(point).strip()][:8]
            or ["租户知识队列", "知识专区", "Hermes 上下文", "向量知识库"],
        "tuning_focus": [str(point).strip() for point in (config_item.get("tuning_focus") if isinstance(config_item.get("tuning_focus"), list) else []) if str(point).strip()][:8]
            or ["补充摘要", "补充验证节点", "继续细化表达"],
        "notes": notes_text,
        "notes_html": str(config_item.get("notes_html") or "").strip(),
        "files": [str(name).strip() for name in (config_item.get("files") if isinstance(config_item.get("files"), list) else []) if str(name).strip()][:12],
        "url": str(config_item.get("url") or "").strip(),
        "skip_ai_processing": bool(metadata.get("skip_ai_processing", config_item.get("skip_ai_processing", True))),
        "voice_minutes": config_item.get("voice_minutes") if isinstance(config_item.get("voice_minutes"), int) else None,
        "body": body_text,
        "time": created_at.strftime("%Y-%m-%d %H:%M") if hasattr(created_at, "strftime") else str(created_at or ""),
        "vector_record": {
            "id": int(record.get("id") or 0),
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or ""),
            "vector_namespace": str(record.get("vector_namespace") or "").strip(),
            "embedding_engine": str(record.get("embedding_engine") or "").strip(),
            "embedding_model": str(record.get("embedding_model") or "").strip(),
            "storage_mode": "pgvector" if str(record.get("vector_namespace") or "").strip() else "jsonb",
        },
    }


def fetch_live_knowledge_hub(tenant, limit=80):
    config_hub = resolve_tenant_knowledge_hub(tenant, tenant.get("knowledge_hub_config"))
    config_items = {
        str(item.get("id") or "").strip(): item
        for item in (config_hub.get("items") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    try:
        with get_review_vector_db_connection() as conn:
            _ensure_knowledge_embedding_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, knowledge_id, knowledge_type, title, summary, body_text, source_detail,
                           vector_namespace, embedding_engine, embedding_model, metadata_json, created_at
                    FROM (
                        SELECT DISTINCT ON (knowledge_id)
                            id, knowledge_id, knowledge_type, title, summary, body_text, source_detail,
                            vector_namespace, embedding_engine, embedding_model, metadata_json, created_at
                        FROM knowledge_embeddings
                        WHERE tenant_slug = %s
                        ORDER BY knowledge_id, created_at DESC, id DESC
                    ) latest
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (tenant.get("slug"), max(1, int(limit or 80))),
                )
                rows = cur.fetchall()
    except Exception:
        app.logger.exception("Failed to load live knowledge hub from vector database")
        return config_hub
    if not rows:
        return config_hub
    items = []
    for row in rows:
        record = {
            "id": row[0],
            "knowledge_id": row[1],
            "knowledge_type": row[2],
            "title": row[3],
            "summary": row[4],
            "body_text": row[5],
            "source_detail": row[6],
            "vector_namespace": row[7],
            "embedding_engine": row[8],
            "embedding_model": row[9],
            "metadata_json": row[10],
            "created_at": row[11],
        }
        items.append(_build_live_knowledge_entry_from_record(record, config_items.get(str(row[1] or "").strip())))
    return {
        "summary": config_hub.get("summary") or "知识库支持语音、文件、URL 和纯文本四种入口。",
        "items": items,
    }


def _cosine_similarity(vec_a, vec_b):
    if not isinstance(vec_a, list) or not isinstance(vec_b, list) or not vec_a or not vec_b:
        return 0.0
    size = min(len(vec_a), len(vec_b))
    if size <= 0:
        return 0.0
    dot = sum(float(vec_a[i]) * float(vec_b[i]) for i in range(size))
    norm_a = math.sqrt(sum(float(vec_a[i]) * float(vec_a[i]) for i in range(size)))
    norm_b = math.sqrt(sum(float(vec_b[i]) * float(vec_b[i]) for i in range(size)))
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (norm_a * norm_b)


def search_knowledge_embeddings(tenant_slug, query_text, limit=5):
    normalized_query = str(query_text or "").strip()
    if not normalized_query:
        raise ValueError("knowledge_query_required")
    embedding_cfg = get_voice_embedding_config()
    query_embedding, embedding_engine, embedding_model = build_text_embedding(
        normalized_query,
        engine=embedding_cfg.get("engine", "local"),
    )
    with get_review_vector_db_connection() as conn:
        _ensure_knowledge_embedding_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, knowledge_id, knowledge_type, title, summary, body_text, source_detail,
                       vector_namespace, embedding_engine, embedding_model, embedding_json, metadata_json, created_at
                FROM (
                    SELECT DISTINCT ON (knowledge_id)
                        id, knowledge_id, knowledge_type, title, summary, body_text, source_detail,
                        vector_namespace, embedding_engine, embedding_model, embedding_json, metadata_json, created_at
                    FROM knowledge_embeddings
                    WHERE tenant_slug = %s
                    ORDER BY knowledge_id, created_at DESC, id DESC
                ) latest
                ORDER BY created_at DESC, id DESC
                LIMIT 120
                """,
                (str(tenant_slug or "").strip(),),
            )
            rows = cur.fetchall()
    if not rows:
        return {
            "query": normalized_query,
            "answer": "当前知识库里还没有可检索的真实知识，请先完成至少一条知识入库。",
            "matches": [],
            "embedding_engine": embedding_engine,
            "embedding_model": embedding_model,
        }
    tenant = get_tenant_by_slug(tenant_slug)
    config_hub = resolve_tenant_knowledge_hub(tenant, tenant.get("knowledge_hub_config")) if tenant else {"items": []}
    config_items = {
        str(item.get("id") or "").strip(): item
        for item in (config_hub.get("items") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    scored = []
    for row in rows:
        stored_embedding = row[10] if isinstance(row[10], list) else []
        score = _cosine_similarity(query_embedding, stored_embedding)
        record = {
            "id": row[0],
            "knowledge_id": row[1],
            "knowledge_type": row[2],
            "title": row[3],
            "summary": row[4],
            "body_text": row[5],
            "source_detail": row[6],
            "vector_namespace": row[7],
            "embedding_engine": row[8],
            "embedding_model": row[9],
            "metadata_json": row[11],
            "created_at": row[12],
        }
        entry = _build_live_knowledge_entry_from_record(record, config_items.get(str(row[1] or "").strip()))
        entry["score"] = round(float(score), 4)
        scored.append(entry)
    scored.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    matches = scored[: max(1, int(limit or 5))]
    if matches:
        answer_lines = [
            f"已命中 {len(matches)} 条知识，最相关的是《{matches[0].get('title') or '未命名知识'}》。",
            f"核心摘要：{matches[0].get('summary') or matches[0].get('body') or '暂无摘要'}",
        ]
        for index, item in enumerate(matches[1:3], start=2):
            answer_lines.append(f"补充命中 {index}：{item.get('title') or '未命名知识'}，相关度 {item.get('score', 0)}。")
        answer = "\n".join(answer_lines)
    else:
        answer = "当前没有找到足够相关的知识条目。"
    return {
        "query": normalized_query,
        "answer": answer,
        "matches": matches,
        "embedding_engine": embedding_engine,
        "embedding_model": embedding_model,
    }


def build_knowledge_chat_prompts(query_text, matches, tenant_slug=""):
    query = str(query_text or "").strip()
    tenant = get_tenant_by_slug(tenant_slug)
    tenant_name = (tenant or {}).get("name") or (tenant or {}).get("short_name") or str(tenant_slug or "").strip() or "当前租户"
    context_blocks = []
    for index, item in enumerate(matches[:5], start=1):
        if not isinstance(item, dict):
            continue
        context_blocks.append(
            "\n".join([
                f"[知识 {index}] 标题：{str(item.get('title') or '未命名知识').strip()}",
                f"[知识 {index}] 摘要：{str(item.get('summary') or item.get('body') or item.get('raw_input') or '暂无摘要').strip()}",
                f"[知识 {index}] 原文：{str(item.get('body') or item.get('raw_input') or item.get('summary') or '').strip()}",
                f"[知识 {index}] 来源：{str(item.get('source_detail') or item.get('source') or '').strip()}",
                f"[知识 {index}] 相关度：{item.get('score', 0)}",
            ])
        )
    context_text = "\n\n".join(block for block in context_blocks if block.strip())
    system_prompt = (
        f"你是{tenant_name}的大V知识库助手。"
        "你的任务是基于召回到的知识条目回答问题。"
        "必须优先依据给定知识，不要编造未提供的事实。"
        "如果知识不足以完整回答，要明确指出边界。"
        "回答请使用中文，风格简洁、专业、适合大V内容生产和研究复盘。"
    )
    user_prompt = (
        f"用户问题：{query}\n\n"
        f"知识库召回结果：\n{context_text or '当前没有召回到有效知识。'}\n\n"
        "请输出：\n"
        "1. 直接回答用户问题\n"
        "2. 提炼2到4条关键依据\n"
        "3. 如果存在知识空白，补一句“知识边界”"
    )
    return system_prompt, user_prompt


def build_knowledge_query_response(tenant_slug, query_text, limit=5, submit_to_model=False):
    result = search_knowledge_embeddings(tenant_slug=tenant_slug, query_text=query_text, limit=limit)
    llm_requested = bool(submit_to_model)
    llm_enabled = False
    llm_mode = "retrieval_only"
    llm_model = None
    llm_notice = "当前为纯知识检索模式，未提交给大模型。"
    if llm_requested:
        llm_model = get_default_llm_config(purpose="general")
        if llm_model:
            system_prompt, user_prompt = build_knowledge_chat_prompts(
                query_text=result.get("query"),
                matches=result.get("matches") or [],
                tenant_slug=tenant_slug,
            )
            llm_enabled = True
            try:
                llm_answer = call_openai_compatible_llm(llm_model, system_prompt, user_prompt)
                result["answer"] = llm_answer
                llm_mode = "model_answered"
                llm_notice = f"当前回答已由通用模型生成：{llm_model.get('label') or llm_model.get('model_name') or llm_model.get('key')}。下方仍保留原始知识命中结果供校验。"
            except RuntimeError as exc:
                llm_enabled = False
                llm_mode = "fallback_retrieval"
                llm_notice = f"已尝试调用通用模型，但失败并回退到纯知识检索：{str(exc)}"
        else:
            llm_mode = "fallback_retrieval"
            llm_notice = "已勾选提交给大模型，但当前没有可用的通用模型配置，已自动回退到纯知识检索模式。"
    return {
        **result,
        "submit_to_model": llm_requested,
        "llm_enabled": llm_enabled,
        "llm_mode": llm_mode,
        "llm_notice": llm_notice,
        "llm_model": {
            "key": llm_model.get("key"),
            "label": llm_model.get("label"),
            "provider": llm_model.get("provider"),
            "model_name": llm_model.get("model_name"),
            "purpose": llm_model.get("purpose"),
        } if llm_model else None,
    }


def process_review_voice_upload(file_storage, tenant_slug="", review_period="", entry_point="", speaker_name=""):
    if file_storage is None:
        raise ValueError("audio_file_required")
    safe_name = _safe_audio_filename(getattr(file_storage, "filename", ""))
    content_type = _guess_audio_content_type(safe_name, getattr(file_storage, "mimetype", ""))
    if not _is_allowed_audio_upload(safe_name, content_type):
        raise ValueError("unsupported_audio_type")
    audio_bytes = file_storage.read() or b""
    if not audio_bytes:
        raise ValueError("empty_audio_file")
    if len(audio_bytes) > VOICE_UPLOAD_MAX_BYTES:
        raise ValueError("audio_file_too_large")
    transcription_cfg = get_voice_transcription_config()
    transcript, transcript_engine = transcribe_review_audio(
        audio_bytes=audio_bytes,
        filename=safe_name,
        content_type=content_type,
        engine=transcription_cfg.get("engine", "local"),
    )
    transcript_model = LOCAL_WHISPER_MODEL_SIZE if transcript_engine == "local" else OPENAI_AUDIO_MODEL
    return {
        "transcript": transcript,
        "transcript_engine": transcript_engine,
        "transcript_model": transcript_model,
    }


def process_review_publish_text(text, tenant_slug="", review_period="", entry_point="", speaker_name="", transcription_engine="manual", transcript_model="manual_input"):
    normalized_text = str(text or "").strip()
    if not normalized_text:
        raise ValueError("publish_text_required")
    embedding_cfg = get_voice_embedding_config()
    embedding, embedding_engine, embedding_model = build_text_embedding(
        normalized_text,
        engine=embedding_cfg.get("engine", "api"),
    )
    vector_namespace = build_vector_namespace(embedding_engine, embedding_model)
    record = _store_review_voice_embedding_record(
        tenant_slug=tenant_slug,
        review_period=review_period,
        entry_point=entry_point,
        vector_namespace=vector_namespace,
        speaker_name=speaker_name,
        filename="review_publish_text.txt",
        content_type="text/plain",
        audio_size_bytes=0,
        transcript=normalized_text,
        transcription_engine=transcript_engine,
        transcript_model=transcript_model,
        embedding=embedding,
        embedding_engine=embedding_engine,
        embedding_model=embedding_model,
    )
    return {
        "text": normalized_text,
        "record": record,
        "transcription_engine": transcription_engine,
        "embedding_engine": embedding_engine,
        "embedding_model": embedding_model,
    }


def process_review_manual_text(text, tenant_slug="", review_period="", entry_point="", speaker_name=""):
    normalized_text = str(text or "").strip()
    if not normalized_text:
        raise ValueError("manual_text_required")
    return {
        "text": normalized_text,
        "transcription_engine": "manual",
        "transcript_model": "manual_input",
    }


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def is_authenticated():
    return session.get(AUTH_SESSION_KEY) is True


def is_password_gate_enabled():
    try:
        return bool(get_site_config().get("password_gate_enabled", True))
    except Exception as exc:
        if is_db_unavailable_error(exc):
            app.logger.warning("Database unavailable while checking password gate, using default gate config")
            return bool(DEFAULT_SITE_CONFIG.get("password_gate_enabled", True))
        raise


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
    public_paths = {
        "/login",
        "/unlock",
        "/logout",
        "/api/demo-profiles",
        "/api/demo-profile/switch",
        "/api/h5/logout",
    }
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
    site_config = get_site_config()
    h5_fallback_mode = False
    demo_profiles = []
    current_demo_profile = None
    tenant = None
    indicator_hub = {}
    fundamental_column = {}
    dashboard_seed_cards = []
    tenant_dashboard_payload = {}
    try:
        current_demo_profile = get_current_demo_profile(site_config)
        tenant = get_tenant_by_slug(
            current_demo_profile.get("tenant", {}).get("slug") if current_demo_profile else None,
            site_config,
        )
        indicator_hub = build_indicator_hub(tenant=tenant, admin_view=False)
        fundamental_column = build_fundamental_column_payload(tenant)
        dashboard_seed_cards = build_indicator_dashboard_seed_cards(tenant, count=8)
        tenant_dashboard_payload = build_tenant_dashboard_payload(tenant)
        demo_profiles = get_h5_login_users(site_config)
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while building H5 page, using fallback data")
        h5_fallback_mode = True
        fallback_config = normalize_site_config(site_config)
        demo_profiles, current_demo_profile = resolve_demo_profile_fallback(fallback_config)
        tenant = get_tenant_by_slug(
            current_demo_profile.get("tenant", {}).get("slug") if current_demo_profile else None,
            fallback_config,
        )
        indicator_hub = build_indicator_hub_fallback(tenant=tenant, admin_view=False)
        fundamental_column = build_fundamental_column_payload_from_hub(tenant, indicator_hub)
        dashboard_seed_cards = build_indicator_dashboard_seed_cards_from_hub(indicator_hub, count=8)
        tenant_dashboard_payload = build_tenant_dashboard_payload_fallback(tenant)
    market = gen_market_data()
    news = gen_news_feed()
    watchlist_details = gen_watchlist_details()
    macro_indicators = [
        {
            "name": item.get("name") or "",
            "value": item.get("value") or "--",
            "status": item.get("status") or "attention",
            "assessment": item.get("assessment") or "",
            "alert": item.get("alert") or "",
            "hint": item.get("alert") or "",
        }
        for item in (indicator_hub.get("smart_items") or [])[:4]
    ]
    feed_boards = gen_feed_boards_from_watchlist_details(watchlist_details)
    return render_template(
        "h5.html",
        market=market,
        news=news,
        macro_indicators=macro_indicators,
        feed_boards=feed_boards,
        watchlist_details=watchlist_details,
        indicator_hub=indicator_hub,
        fundamental_column=fundamental_column,
        dashboard_seed_cards=dashboard_seed_cards,
        tenant_dashboard_payload=tenant_dashboard_payload,
        active_tenant=tenant,
        demo_profiles=demo_profiles,
        current_demo_profile=current_demo_profile,
        h5_fallback_mode=h5_fallback_mode,
    )

@app.route("/admin")
def admin():
    kols = gen_kol_data()
    segments = gen_user_segments()
    access_stats = get_access_summary()
    indicator_hub = build_indicator_hub(admin_view=True)
    return render_template(
        "admin.html",
        kols=kols,
        segments=segments,
        access_stats=access_stats,
        indicator_hub=indicator_hub,
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


@app.route("/api/review/voice-transcribe", methods=["POST"])
def api_review_voice_transcribe():
    audio_file = request.files.get("audio") or request.files.get("file")
    tenant_slug = str(request.form.get("tenant_slug") or "").strip().lower()
    review_period = str(request.form.get("period") or "").strip().lower()
    entry_point = str(request.form.get("entry_point") or "").strip().lower() or "unknown"
    speaker_name = str(request.form.get("speaker_name") or "").strip()
    try:
        result = process_review_voice_upload(
            file_storage=audio_file,
            tenant_slug=tenant_slug,
            review_period=review_period,
            entry_point=entry_point,
            speaker_name=speaker_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    except Exception:
        app.logger.exception("Failed to process review voice upload")
        return jsonify({"success": False, "error": "review_voice_transcribe_failed"}), 500
    return jsonify(
        {
            "success": True,
            "transcript": result["transcript"],
            "transcript_engine": result["transcript_engine"],
            "transcript_model": result["transcript_model"],
        }
    )


@app.route("/api/review/manual-embed", methods=["POST"])
def api_review_manual_embed():
    body = request.get_json(silent=True) or {}
    try:
        result = process_review_manual_text(
            text=body.get("text"),
            tenant_slug=str(body.get("tenant_slug") or "").strip().lower(),
            review_period=str(body.get("period") or "").strip().lower(),
            entry_point=str(body.get("entry_point") or "").strip().lower() or "unknown",
            speaker_name=str(body.get("speaker_name") or "").strip(),
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    except Exception:
        app.logger.exception("Failed to process review manual text")
        return jsonify({"success": False, "error": "review_manual_embed_failed"}), 500
    return jsonify(
        {
            "success": True,
            "text": result["text"],
            "transcript_engine": result["transcription_engine"],
            "transcript_model": result["transcript_model"],
        }
    )


@app.route("/api/review/publish-embed", methods=["POST"])
def api_review_publish_embed():
    body = request.get_json(silent=True) or {}
    try:
        result = process_review_publish_text(
            text=body.get("text"),
            tenant_slug=str(body.get("tenant_slug") or "").strip().lower(),
            review_period=str(body.get("period") or "").strip().lower(),
            entry_point=str(body.get("entry_point") or "").strip().lower() or "unknown",
            speaker_name=str(body.get("speaker_name") or "").strip(),
            transcription_engine=str(body.get("transcription_engine") or "manual").strip().lower() or "manual",
            transcript_model=str(body.get("transcript_model") or "manual_input").strip() or "manual_input",
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    except Exception:
        app.logger.exception("Failed to process review publish text")
        return jsonify({"success": False, "error": "review_publish_embed_failed"}), 500
    return jsonify(
        {
            "success": True,
            "text": result["text"],
            "vector_record": result["record"],
            "transcript_engine": result["transcription_engine"],
            "embedding_engine": result["embedding_engine"],
            "embedding_model": result["embedding_model"],
        }
    )

@app.route("/api/market")
def api_market():
    return jsonify(gen_market_data())


@app.route("/api/watchlist")
def api_watchlist():
    return jsonify(gen_market_data())


@app.route("/api/watchlist/<stock_code>")
def api_watchlist_detail(stock_code):
    site_config = get_site_config()
    details = gen_watchlist_details()
    payload = details.get(stock_code, {
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
    })
    return jsonify(apply_watchlist_feature_flags(payload, site_config))


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


@app.route("/api/admin/indicator-hub")
def api_admin_indicator_hub():
    return jsonify({"ok": True, "hub": build_indicator_hub_from_store()})


@app.route("/api/admin/indicator-definitions")
def api_admin_indicator_definitions():
    source_type = str(request.args.get("source_type") or "").strip() or None
    return jsonify({"ok": True, "definitions": list_indicator_definitions(source_type=source_type)})


@app.route("/api/admin/indicator-definitions", methods=["POST"])
def api_save_admin_indicator_definition():
    body = request.get_json(silent=True) or {}
    try:
        definition = save_indicator_definition(body)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "definition": definition, "definitions": list_indicator_definitions()})


@app.route("/api/admin/indicator-definitions/<indicator_code>", methods=["DELETE"])
def api_delete_admin_indicator_definition(indicator_code):
    if not get_indicator_definition(indicator_code):
        return jsonify({"ok": False, "error": "indicator_not_found"}), 404
    delete_indicator_definition(indicator_code)
    return jsonify({"ok": True, "definitions": list_indicator_definitions()})


@app.route("/api/admin/indicator-sources")
def api_admin_indicator_sources():
    indicator_code = str(request.args.get("indicator_code") or "").strip() or None
    return jsonify({"ok": True, "sources": list_indicator_source_defs(indicator_code=indicator_code)})


@app.route("/api/admin/indicator-sources", methods=["POST"])
def api_save_admin_indicator_source():
    body = request.get_json(silent=True) or {}
    try:
        source = save_indicator_source_def(body)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "source": source, "sources": list_indicator_source_defs()})


@app.route("/api/admin/indicator-sources/<source_code>", methods=["DELETE"])
def api_delete_admin_indicator_source(source_code):
    if not get_indicator_source_def(source_code):
        return jsonify({"ok": False, "error": "source_not_found"}), 404
    delete_indicator_source_def(source_code)
    return jsonify({"ok": True, "sources": list_indicator_source_defs()})


@app.route("/api/admin/indicator-sources/test", methods=["POST"])
def api_test_admin_indicator_source():
    body = request.get_json(silent=True) or {}
    source_code = str(body.get("source_code") or "").strip()
    if not source_code:
        return jsonify({"ok": False, "error": "source_code_required"}), 400
    try:
        result = test_indicator_source(source_code)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify(
        {
            "ok": result["success"],
            "result": result,
            "tests": list_indicator_source_tests(source_code=source_code),
            "source": get_indicator_source_def(source_code),
        }
    )


@app.route("/api/admin/indicator-sources/<source_code>/preview")
def api_admin_indicator_source_preview(source_code):
    try:
        preview = build_indicator_source_preview(source_code)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "preview": preview})


@app.route("/api/admin/indicator-batches/mock-seed", methods=["POST"])
def api_admin_indicator_mock_seed():
    body = request.get_json(silent=True) or {}
    force = bool(body.get("force"))
    result = seed_mock_indicator_lake(force=force)
    return jsonify({"ok": True, "result": result, "hub": build_indicator_hub_from_store()})


@app.route("/api/admin/indicator-batches/market-cache-sync", methods=["POST"])
def api_admin_indicator_market_cache_sync():
    body = request.get_json(silent=True) or {}
    force = bool(body.get("force"))
    result = sync_real_indicator_history_from_market_cache(force=force)
    return jsonify({"ok": True, "result": result, "hub": build_indicator_hub_from_store()})


@app.route("/api/admin/indicator-raw-records")
def api_admin_indicator_raw_records():
    source_code = str(request.args.get("source_code") or "").strip() or None
    limit = min(int(request.args.get("limit", 20)), 100)
    return jsonify({"ok": True, "records": list_indicator_raw_records(source_code=source_code, limit=limit)})


@app.route("/api/admin/indicator-raw-records/create", methods=["POST"])
def api_admin_create_indicator_raw_record():
    body = request.get_json(silent=True) or {}
    source_code = str(body.get("source_code") or "").strip()
    if not source_code:
        return jsonify({"ok": False, "error": "source_code_required"}), 400
    try:
        record = create_indicator_raw_record_from_source(source_code, use_last_test_sample=bool(body.get("use_last_test_sample", True)))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "record": record, "records": list_indicator_raw_records(source_code=source_code)})


@app.route("/api/admin/indicator-sources/landing", methods=["POST"])
def api_admin_execute_indicator_source_landing():
    body = request.get_json(silent=True) or {}
    source_code = str(body.get("source_code") or "").strip()
    if not source_code:
        return jsonify({"ok": False, "error": "source_code_required"}), 400
    try:
        result = execute_indicator_source_landing(source_code, prefer_live=bool(body.get("prefer_live")))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify(
        {
            "ok": True,
            "result": result,
            "records": list_indicator_raw_records(source_code=source_code),
            "hub": build_indicator_hub_from_store(),
        }
    )


@app.route("/api/admin/indicator-mapping-rules")
def api_admin_indicator_mapping_rules():
    indicator_code = str(request.args.get("indicator_code") or "").strip() or None
    source_code = str(request.args.get("source_code") or "").strip() or None
    return jsonify({"ok": True, "rules": list_indicator_mapping_rules(indicator_code=indicator_code, source_code=source_code)})


@app.route("/api/admin/indicator-mapping-rules", methods=["POST"])
def api_save_admin_indicator_mapping_rule():
    body = request.get_json(silent=True) or {}
    try:
        rule = save_indicator_mapping_rule(body)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "rule": rule, "rules": list_indicator_mapping_rules()})


@app.route("/api/admin/indicator-mapping-rules/<rule_code>", methods=["DELETE"])
def api_delete_admin_indicator_mapping_rule(rule_code):
    if not get_indicator_mapping_rule(rule_code):
        return jsonify({"ok": False, "error": "mapping_rule_not_found"}), 404
    delete_indicator_mapping_rule(rule_code)
    return jsonify({"ok": True, "rules": list_indicator_mapping_rules()})


@app.route("/api/admin/indicator-clean-jobs")
def api_admin_indicator_clean_jobs():
    source_code = str(request.args.get("source_code") or "").strip() or None
    limit = min(int(request.args.get("limit", 20)), 100)
    return jsonify({"ok": True, "jobs": list_indicator_clean_jobs(source_code=source_code, limit=limit)})


@app.route("/api/admin/indicator-clean-jobs/run", methods=["POST"])
def api_admin_run_indicator_clean_job():
    body = request.get_json(silent=True) or {}
    source_code = str(body.get("source_code") or "").strip()
    raw_record_id = body.get("raw_record_id")
    if not source_code and not raw_record_id:
        return jsonify({"ok": False, "error": "source_code_required"}), 400
    try:
        job = run_indicator_clean_job(
            source_code=source_code,
            rule_code=body.get("rule_code"),
            raw_record_id=raw_record_id,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    effective_source_code = source_code or (job.get("source_code") if isinstance(job, dict) else "")
    return jsonify({"ok": True, "job": job, "jobs": list_indicator_clean_jobs(source_code=effective_source_code), "hub": build_indicator_hub_from_store()})


@app.route("/api/admin/indicator-trace/<indicator_code>")
def api_admin_indicator_trace(indicator_code):
    limit = min(int(request.args.get("limit", 12)), 50)
    try:
        trace = build_indicator_lake_trace(indicator_code, limit=limit)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "trace": trace})


@app.route("/api/site-config")
def api_site_config():
    try:
        return jsonify(get_site_config())
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while serving site config API, using defaults")
        return jsonify(normalize_site_config(DEFAULT_SITE_CONFIG))


@app.route("/api/demo-profiles")
def api_demo_profiles():
    try:
        site_config = get_site_config()
        profiles = get_h5_login_users(site_config)
        current = get_current_demo_profile(site_config)
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while serving demo profiles, using defaults")
        fallback_config = normalize_site_config(DEFAULT_SITE_CONFIG)
        profiles, current = resolve_demo_profile_fallback(fallback_config)
    return jsonify({
        "profiles": profiles,
        "current_profile": current,
    })


@app.route("/api/demo-profile/switch", methods=["POST"])
def api_switch_demo_profile():
    try:
        site_config = get_site_config()
        profiles = get_h5_login_users(site_config)
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while switching demo profile, using defaults")
        fallback_config = normalize_site_config(DEFAULT_SITE_CONFIG)
        profiles, _ = resolve_demo_profile_fallback(fallback_config)
    body = request.get_json(silent=True) or {}
    profile_id = str(body.get("profile_id") or "").strip()
    matched = next((profile for profile in profiles if profile["username"] == profile_id), None)
    if not matched:
        return jsonify({"ok": False, "error": "demo_profile_not_found"}), 404
    save_current_demo_profile_id(matched["username"])
    return jsonify({
        "ok": True,
        "current_profile": matched,
        "profiles": profiles,
    })


@app.route("/api/h5/logout", methods=["POST"])
def api_h5_logout():
    save_current_demo_profile_id("")
    return jsonify({"ok": True})


@app.route("/api/admin/users")
def api_admin_users():
    return jsonify({"users": list_users()})


@app.route("/api/admin/users", methods=["POST"])
def api_create_admin_user():
    body = request.get_json(silent=True) or {}
    try:
        user = create_user(body)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "user": user, "users": list_users()})


@app.route("/api/admin/users/import", methods=["POST"])
def api_import_admin_users():
    body = request.get_json(silent=True) or {}
    users = body.get("users", [])
    created = import_users(users if isinstance(users, list) else [])
    return jsonify({"ok": True, "created": created, "users": list_users()})


@app.route("/api/kol/users")
def api_kol_users():
    tenant = get_active_tenant_from_request()
    return jsonify({"users": list_users(tenant_slug=tenant["slug"])})


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
            "voice_transcription": {
                "engine": str(
                    (
                        (payload.get("voice_transcription") or {}).get("engine")
                        or (current.get("voice_transcription") or {}).get("engine")
                        or "local"
                    )
                ).strip().lower() or "local"
            },
            "voice_embedding": {
                "engine": str(
                    (
                        (payload.get("voice_embedding") or {}).get("engine")
                        or (current.get("voice_embedding") or {}).get("engine")
                        or "local"
                    )
                ).strip().lower() or "local"
            },
            "llm_registry": normalize_llm_registry_config(
                payload.get("llm_registry")
                if isinstance(payload.get("llm_registry"), dict)
                else current.get("llm_registry")
            ),
            "brand": payload.get("brand", current.get("brand", {})),
            "default_tenant_slug": payload.get("default_tenant_slug", current.get("default_tenant_slug")),
            "tenants": payload.get("tenants", current.get("tenants", [])),
            "demo_profiles": payload.get("demo_profiles", current.get("demo_profiles", [])),
            "feature_flags": feature_flags,
        },
    )
    return jsonify({"success": True, "site_config": save_site_config(next_config)})


@app.route("/api/admin/forecast-config")
def api_admin_forecast_config():
    if not is_feature_enabled("stock_forecast"):
        return jsonify({"ok": False, "error": "stock_forecast_disabled"}), 403
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
    if not is_feature_enabled("stock_forecast"):
        return jsonify({"ok": False, "error": "stock_forecast_disabled"}), 403
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
    platform_name = get_platform_name()
    result = responses.get(topic, f"针对{topic}的深度分析：基于{platform_name}平台整合的券商研报、专家会议纪要及另类数据，当前该领域呈现结构性机会。建议结合个人风险偏好，参考试点作者的研究框架后做出自己的判断。")
    return jsonify({"topic": topic, "analysis": result, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "source": f"{platform_name}AI分析引擎 (DeepSeek + Kimi 2.6)"})

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
    platform_name = get_platform_name()
    result = HERMES_RESPONSES.get(key, f"【{mode} · {option}】\n\n基于{platform_name}平台整合的多维度数据，AI已完成深度分析。\n\n核心发现：该领域当前呈现结构性机会，关键指标向好。建议结合个人风险偏好，参考试点作者的研究框架后做出自己的判断。\n\n数据来源：券商研报库 + 专家纪要库 + 另类数据库\nAI引擎：DeepSeek R2 + Kimi 2.6 RAG架构\n分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
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
    tenant_users = list_users(tenant_slug=tenant["slug"])
    investor_users = [user for user in tenant_users if user["role"] == "investor"]
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
    fund_dashboard_state = resolve_tenant_fund_dashboard_state(tenant, tenant.get("fund_dashboard_config"))
    fund_dashboard = copy.deepcopy(fund_dashboard_state["published"])
    knowledge_hub = fetch_live_knowledge_hub(tenant)
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
                "desc": f"查看 {tenant['advisor']} 对外的专属租户门户，重点承接品牌表达、已发布内容和粉丝入口。"
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
            {
                "name": user["username"],
                "time": "刚刚",
                "msg": f"{kol_name} 老师，想看最新复盘和核心指标版。",
                "tier": user["membership"],
            }
            for user in investor_users[:5]
        ] or [
            {"name": "暂无粉丝", "time": "--", "msg": "请先通过 Admin 或工作台导入用户。", "tier": "--"}
        ],
        "broadcast_history": [
            {"id":1,"content":is_lisa and "本周港股互联网更新：继续看南向资金和回购兑现" or "本周策略更新：科技板块适合继续跟踪，重点看 AI 算力订单兑现","time":"2026-05-20 08:00","reach":92,"open_rate":68},
            {"id":2,"content":is_lisa and "价值提醒：财报前估值修复较快，注意不要只盯单一平台" or "宏观提醒：美联储纪要偏鸽，但还要等国内资金面确认","time":"2026-05-19 22:30","reach":108,"open_rate":82},
            {"id":3,"content":"周末复盘：本周操作回顾与下周观察重点","time":"2026-05-18 18:00","reach":76,"open_rate":55},
        ],
        "portal_workspace": resolve_tenant_portal_workspace(tenant, tenant.get("portal_cms")),
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
                "total_fans": len(investor_users),
                "new_fans_7d": min(len(investor_users), 6 if is_lisa else 8),
                "active_fans_30d": len(investor_users),
                "paying_fans": max(0, len(investor_users) // 3),
            },
            "fans": [
                {
                    "name": user["username"],
                    "tier": user["membership"],
                    "source": "用户导入",
                    "joined": str(user.get("created_at") or "--")[:10],
                    "value": f"手机号 {mask_phone(user.get('phone'))}",
                    "status": user["status"] == "active" and "活跃" or "已禁用",
                }
                for user in investor_users
            ] or [
                {"name": "暂无粉丝", "tier": "--", "source": "--", "joined": "--", "value": "请先在用户管理中添加普通用户", "status": "待录入"}
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
        "knowledge_hub": knowledge_hub,
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
            "summary": "自选股在前台已经改成顶部直接输入股票代码，进入个股详情后再添加自选；现在工作台与 H5 共用同一套指标湖增强信号，能同步看到行业预警、核心指标和异常摘要。",
            "items": [
                {
                    "name": detail["name"],
                    "code": detail["code"],
                    "market": "港股" if detail.get("market") == "HK" else "A股",
                    "focus": detail.get("focus") or detail.get("industry") or "个股跟踪",
                    "change": f"{detail.get('change_pct', 0):+.1f}%",
                    "thesis": detail.get("signal_summary") or detail.get("fundamental", {}).get("summary") or "继续跟踪",
                    "alert_level": detail.get("alert_level") or "normal",
                    "alert_text": detail.get("alert_text") or "当前无明显预警",
                    "related_indicator_names": detail.get("related_indicator_names") or [],
                }
                for detail in (
                    [watchlist_details_map.get(code) for code in ["00700", "03690", "09988"]] if is_lisa
                    else [watchlist_details_map.get(code) for code in ["688981", "00700", "600519"]]
                )
                if detail
            ],
        },
        "fund_dashboard": fund_dashboard,
        "fund_dashboard_state": fund_dashboard_state,
        "indicator_hub": build_indicator_hub(tenant=tenant, admin_view=False),
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
            return f"我只能基于公开数据分享研究观点，无法给具体买卖建议哦。你可以参考{get_platform_short_name()}Hermes的「AI资产配置」做组合规划，或在「AI行情预判」看历史区间和模型推演的概率分布，结合自己的风险偏好判断。"
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
            return f"明白。我补充一下数据视角：{get_platform_name()}平台最近的研报数据库里，{persona['focus'][0]}相关研报量周环比+12%，机构关注度在抬升。但研报关注≠股价上涨，仅作信号参考。你的仓位结构是怎样的？我可以帮你从大方向上看一下平衡性。"
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
        "data_source": f"基于{get_platform_short_name()}回测引擎(2015-2026)+ 多因子模型 + Black-Litterman 框架",
        "disclaimer": "本配置方案为模型推演结果，基于历史数据回测，不构成投资建议。市场有风险，实际收益可能与回测区间显著偏离。",
        "compute_used": 5,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })

@app.route("/api/ai/forecast", methods=["POST"])
def api_ai_forecast():
    """行情预判：历史可解读，未来仅区间不解读"""
    import math
    if not is_feature_enabled("stock_forecast"):
        return jsonify({
            "error": "stock_forecast_disabled",
            "message": "预测功能当前未开放。",
        }), 403
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
        "data_source": f"{get_platform_short_name()}多因子模型 + 历史波动率Monte Carlo推演 + RAG数据库",
        "compute_used": 8,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })

@app.route("/api/kol/workbench")
def api_kol_workbench():
    tenant = get_tenant_by_slug(request.args.get("tenant"))
    return jsonify(gen_kol_workbench(tenant))


@app.route("/api/kol/portal-cms", methods=["POST"])
def api_save_kol_portal_cms():
    tenant = get_tenant_by_slug(request.args.get("tenant"))
    if not tenant:
        return jsonify({"ok": False, "error": "tenant_not_found"}), 404
    body = request.get_json(silent=True) or {}
    saved = update_tenant_portal_cms(tenant["slug"], body.get("portal_cms", {}))
    if not saved:
        return jsonify({"ok": False, "error": "tenant_not_found"}), 404
    latest_tenant = get_tenant_by_slug(tenant["slug"], saved)
    return jsonify({
        "ok": True,
        "portal_workspace": gen_kol_workbench(latest_tenant).get("portal_workspace"),
        "portal": build_tenant_portal_payload(latest_tenant),
    })


@app.route("/api/kol/knowledge/manual", methods=["POST"])
def api_save_kol_manual_knowledge():
    body = request.get_json(silent=True) or {}
    tenant_slug = str(body.get("tenant_slug") or request.args.get("tenant") or "").strip().lower()
    try:
        result = save_manual_knowledge_entry(
            tenant_slug=tenant_slug,
            title=body.get("title"),
            summary=body.get("summary"),
            body=body.get("body"),
            raw_html=body.get("raw_html"),
            notes=body.get("notes"),
            notes_html=body.get("notes_html"),
            knowledge_id=body.get("id"),
            skip_ai_processing=bool(body.get("skip_ai_processing", True)),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    except Exception:
        app.logger.exception("Failed to save manual knowledge entry")
        return jsonify({"ok": False, "error": "knowledge_manual_save_failed"}), 500
    return jsonify({
        "ok": True,
        "entry": result["entry"],
        "knowledge_hub": result["knowledge_hub"],
        "vector_record": result["vector_record"],
        "embedding_engine": result["embedding_engine"],
        "embedding_model": result["embedding_model"],
    })


@app.route("/api/kol/knowledge/query", methods=["POST"])
def api_query_kol_knowledge():
    body = request.get_json(silent=True) or {}
    tenant_slug = str(body.get("tenant_slug") or request.args.get("tenant") or "").strip().lower()
    submit_to_model = bool(body.get("submit_to_model", False))
    try:
        result = build_knowledge_query_response(
            tenant_slug=tenant_slug,
            query_text=body.get("query"),
            limit=body.get("limit") or 5,
            submit_to_model=submit_to_model,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    except Exception:
        app.logger.exception("Failed to query knowledge embeddings")
        return jsonify({"ok": False, "error": "knowledge_query_failed"}), 500
    return jsonify({"ok": True, **result})


@app.route("/api/tenant/<tenant_slug>/dashboard")
def api_tenant_dashboard(tenant_slug):
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or tenant["slug"] != tenant_slug:
        return jsonify({"success": False, "error": "tenant_not_found"}), 404
    payload = build_tenant_dashboard_payload(tenant)
    return jsonify({"success": True, "dashboard": payload, "fund_dashboard_state": payload.get("fund_dashboard_state")})


@app.route("/api/tenant/<tenant_slug>/dashboard", methods=["POST"])
def api_save_tenant_dashboard(tenant_slug):
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or tenant["slug"] != tenant_slug:
        return jsonify({"success": False, "error": "tenant_not_found"}), 404
    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or "").strip().lower()
    dashboard = body.get("dashboard") if isinstance(body.get("dashboard"), dict) else None
    saved = update_tenant_fund_dashboard_config(tenant_slug, action, dashboard)
    if not saved:
        return jsonify({"success": False, "error": "invalid_action"}), 400
    latest_tenant = get_tenant_by_slug(tenant_slug, saved)
    payload = build_tenant_dashboard_payload(latest_tenant)
    return jsonify({"success": True, "dashboard": payload, "fund_dashboard_state": payload.get("fund_dashboard_state")})

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
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("DEBUG", "1").lower() in {"1", "true", "yes", "y"}
    app.run(host=host, port=port, debug=debug)
