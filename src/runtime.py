import os
import json
import sqlite3
import copy
import math
import statistics
import time
import threading
import re
import hashlib
import secrets
import base64
import csv
import io
import zipfile
from pathlib import Path
from html import escape as html_escape
from html.parser import HTMLParser
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, g, abort
import random
from datetime import datetime, timedelta
from urllib.parse import urlsplit, parse_qsl, urlencode
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
try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None
try:
    import pytesseract
except Exception:
    pytesseract = None
try:
    import fitz
except Exception:
    fitz = None
try:
    from PIL import Image
except Exception:
    Image = None
try:
    import docx
except Exception:
    docx = None
try:
    import openpyxl
except Exception:
    openpyxl = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_session_secret_key():
    configured = str(os.environ.get("GANGTISE_DEMO_SECRET_KEY") or "").strip()
    if configured:
        return configured

    # A random key generated at every restart invalidates every signed Flask
    # session. Keep a local fallback stable across debug reloads and restarts.
    secret_path = PROJECT_ROOT / ".gangtise_session_secret"
    try:
        if secret_path.exists():
            existing = secret_path.read_text(encoding="utf-8").strip()
            if len(existing) >= 32:
                return existing
        generated = secrets.token_urlsafe(48)
        descriptor = os.open(str(secret_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(generated)
        return generated
    except FileExistsError:
        return secret_path.read_text(encoding="utf-8").strip()
    except Exception:
        # This only applies to a read-only development checkout. Deployments
        # should always supply GANGTISE_DEMO_SECRET_KEY explicitly.
        return hashlib.sha256(f"{PROJECT_ROOT}|gangtise-session-fallback".encode("utf-8")).hexdigest()


def _resolve_session_ttl_minutes():
    try:
        return max(1, min(int(os.environ.get("GANGTISE_SESSION_TTL_MINUTES", "20")), 24 * 60))
    except (TypeError, ValueError):
        return 20

app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "templates"),
    static_folder=str(PROJECT_ROOT / "static"),
)
app.config.update(
    SECRET_KEY=_resolve_session_secret_key(),
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=_resolve_session_ttl_minutes()),
    SESSION_REFRESH_EACH_REQUEST=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

H5_USER_SESSION_KEY = "current_h5_username"
DB_PATH = os.environ.get("GANGTISE_DEMO_DB", str(PROJECT_ROOT / "gangtise_demo.db"))
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
LOCAL_POSTGRES_HOST = os.environ.get("LOCAL_POSTGRES_HOST", "127.0.0.1").strip() or "127.0.0.1"
LOCAL_POSTGRES_PORT = int(os.environ.get("LOCAL_POSTGRES_PORT", str(APP_DB_PORT or 5432)))
LOCAL_POSTGRES_DB = os.environ.get("LOCAL_POSTGRES_DB") or APP_DB_NAME
LOCAL_POSTGRES_USER = os.environ.get("LOCAL_POSTGRES_USER") or APP_DB_USER
LOCAL_POSTGRES_PASSWORD = os.environ.get("LOCAL_POSTGRES_PASSWORD") or APP_DB_PASSWORD
LOCAL_VECTOR_DB_HOST = os.environ.get("LOCAL_VECTOR_DB_HOST") or LOCAL_POSTGRES_HOST
LOCAL_VECTOR_DB_PORT = int(os.environ.get("LOCAL_VECTOR_DB_PORT", str(VECTOR_DB_PORT or LOCAL_POSTGRES_PORT)))
LOCAL_VECTOR_DB_NAME = os.environ.get("LOCAL_VECTOR_DB_NAME") or VECTOR_DB_NAME
LOCAL_VECTOR_DB_USER = os.environ.get("LOCAL_VECTOR_DB_USER") or VECTOR_DB_USER
LOCAL_VECTOR_DB_PASSWORD = os.environ.get("LOCAL_VECTOR_DB_PASSWORD") or VECTOR_DB_PASSWORD
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
INDICATOR_HUB_CACHE_TTL_SECONDS = max(0, int(os.environ.get("INDICATOR_HUB_CACHE_TTL_SECONDS", "30")))
TASK_CENTER_POLL_INTERVAL_SECONDS = max(5, int(os.environ.get("TASK_CENTER_POLL_INTERVAL_SECONDS", "15")))
TASK_CENTER_LOG_LIMIT = 80
USER_ASYNC_JOB_POLL_INTERVAL_SECONDS = max(1, int(os.environ.get("USER_ASYNC_JOB_POLL_INTERVAL_SECONDS", "2")))
USER_ASYNC_JOB_LOG_LIMIT = 80
AUTO_INIT_DB_MODE = str(os.environ.get("AUTO_INIT_DB", "dev")).strip().lower()
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
DB_RUNTIME_CONFIG_PATH = PROJECT_ROOT / ".db_runtime.json"
DEFAULT_LLM_FEATURE_CATALOG = [
    {"feature_code": "knowledge_processing_llm", "feature_label": "知识加工", "default_purpose": "general"},
    {"feature_code": "review_voice_enhancement", "feature_label": "复盘语音增强", "default_purpose": "general"},
    {"feature_code": "review_input_polish", "feature_label": "复盘输入润色", "default_purpose": "general"},
    {"feature_code": "review_draft_generation", "feature_label": "复盘草稿生成", "default_purpose": "general"},
    {"feature_code": "review_compose_generation", "feature_label": "复盘完整成稿", "default_purpose": "general"},
    {"feature_code": "review_user_input_summary", "feature_label": "复盘用户输入摘要", "default_purpose": "general"},
    {"feature_code": "review_watchlist_analysis", "feature_label": "复盘自选股归纳", "default_purpose": "general"},
    {"feature_code": "watchlist_comment_labeling", "feature_label": "自选股评论标注", "default_purpose": "general"},
    {"feature_code": "knowledge_query_filter", "feature_label": "知识检索过滤", "default_purpose": "general"},
    {"feature_code": "knowledge_query_answer", "feature_label": "知识问答生成", "default_purpose": "general"},
    {"feature_code": "hermes_intent_router", "feature_label": "Hermes 意图路由", "default_purpose": "general"},
    {"feature_code": "hermes_answer_synthesis", "feature_label": "Hermes 回答合成", "default_purpose": "general"},
    {"feature_code": "smart_indicator_formula_generation", "feature_label": "智能指标公式生成", "default_purpose": "general"},
]
DEFAULT_LLM_MODELS = [
    {
        "key": "gangtise-gemma4-12b-bf16",
        "label": "Gangtise Gemma4 12B BF16",
        "provider": "openai",
        "model_name": "gemma4:12b-it-bf16",
        "base_url": "http://8.155.160.194:6031/api",
        "api_key": "sk-5da7f8f997d44a97ae6dcdeb74c45397",
        "purpose": "general",
        "enabled": True,
    },
    {
        "key": "gangtise-gemma4-31b-q4km",
        "label": "Gangtise Gemma4 31B Q4_K_M",
        "provider": "openai",
        "model_name": "gemma4:31b-it-q4_K_M",
        "base_url": "http://8.155.160.194:6031/api",
        "api_key": "sk-5da7f8f997d44a97ae6dcdeb74c45397",
        "purpose": "general",
        "enabled": True,
    },
]
INDICATOR_DEFINITION_FIELDS = {
    "indicator_code",
    "indicator_name",
    "tenant_slug",
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
    "prompt_text",
    "formula_js",
    "selected_indicators_json",
    "display_order",
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
_indicator_hub_cache = {"expires_at": 0.0, "value": None}
_task_center_lock = threading.Lock()
_task_center_thread = None
_task_center_started = False
_task_center_runtime = {}
_user_async_job_lock = threading.Lock()
_user_async_job_thread = None
_user_async_job_started = False
_user_async_job_runtime = {}

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
    "auth_settings": {
        "password_login_enabled": True,
        "wechat_login_enabled": False,
        "quick_select_enabled": True,
        "wechat_runtime_test_enabled": True,
        "wechat": {
            "app_id": "",
            "redirect_uri": "http://127.0.0.1:5001/api/h5/wechat/callback",
            "scope": "snsapi_userinfo",
            "auto_register_enabled": False,
            "default_role": "investor",
            "default_tenant_slug": "",
            "default_advisor_name": "",
        },
    },
    "voice_transcription": {
        "engine": "local",
        "post_process_mode": "rule_based",
        "domain_glossary_enabled": True,
    },
    "voice_embedding": {
        "engine": "local",
    },
    "knowledge_ingestion": {
        "user_preview_enabled": False,
    },
    "hermes_settings": {
        "prompt_scope_guard_enabled": True,
        "investor_access_enabled": False,
        "dav_access_enabled": True,
        "internet_answer_enabled": True,
        "thinking_process_enabled": True,
        "answer_save_to_knowledge_enabled": True,
        "default_response_style": "structured",
        "chart_types_enabled": ["kline_chart", "line_chart", "distribution_chart", "compare_chart"],
        "route_priority": [
            "session_load",
            "memory_read",
            "fast_path",
            "scope_guard",
            "intent_router",
            "knowledge.search",
            "platform_tools",
            "attachment.context",
            "web.search",
            "answer_synthesis",
        ],
        "intent_tree": [
            {
                "id": "knowledge_lookup",
                "label": "知识问答",
                "group": "knowledge_qa",
                "enabled": True,
                "display_mode": "text",
                "allow_knowledge": True,
                "allow_web": True,
                "allow_files": True,
                "allow_chart": False,
            },
            {
                "id": "watchlist_fundamental",
                "label": "个股 / 自选股",
                "group": "market_data_query",
                "enabled": True,
                "display_mode": "structured",
                "allow_knowledge": True,
                "allow_web": True,
                "allow_files": True,
                "allow_chart": True,
            },
            {
                "id": "smart_indicator_explain",
                "label": "指标 / 图表",
                "group": "chart_visualization",
                "enabled": True,
                "display_mode": "structured",
                "allow_knowledge": True,
                "allow_web": True,
                "allow_files": False,
                "allow_chart": True,
            },
            {
                "id": "evidence_chain_analysis",
                "label": "复盘 / 证据链",
                "group": "review_assistant",
                "enabled": True,
                "display_mode": "structured",
                "allow_knowledge": True,
                "allow_web": True,
                "allow_files": True,
                "allow_chart": False,
            },
            {
                "id": "dashboard_interpretation",
                "label": "Dashboard 解读",
                "group": "dashboard_indicator_assistant",
                "enabled": True,
                "display_mode": "structured",
                "allow_knowledge": True,
                "allow_web": False,
                "allow_files": False,
                "allow_chart": True,
            },
            {
                "id": "multi_tool_research",
                "label": "多工具研究",
                "group": "content_generation",
                "enabled": True,
                "display_mode": "structured",
                "allow_knowledge": True,
                "allow_web": True,
                "allow_files": True,
                "allow_chart": True,
            },
            {
                "id": "product_help",
                "label": "产品帮助",
                "group": "product_help_or_smalltalk",
                "enabled": True,
                "display_mode": "text",
                "allow_knowledge": True,
                "allow_web": False,
                "allow_files": False,
                "allow_chart": False,
            },
            {
                "id": "small_talk",
                "label": "轻度闲聊",
                "group": "product_help_or_smalltalk",
                "enabled": True,
                "display_mode": "text",
                "allow_knowledge": False,
                "allow_web": False,
                "allow_files": False,
                "allow_chart": False,
            },
        ],
        "template_tree": {
            "router": [
                {"id": "router.scope", "label": "范围识别", "enabled": True},
                {"id": "router.intent", "label": "意图识别", "enabled": True},
                {"id": "router.display_mode", "label": "展示模式判定", "enabled": True},
                {"id": "router.tool_plan", "label": "工具编排", "enabled": True},
            ],
            "tool": [
                {"id": "tool.knowledge.search", "label": "知识检索", "enabled": True},
                {"id": "tool.watchlist.detail", "label": "个股详情", "enabled": True},
                {"id": "tool.market.index", "label": "指数 / 指标数据", "enabled": True},
                {"id": "tool.file.parse", "label": "文件解析", "enabled": True},
                {"id": "tool.url.parse", "label": "URL 解析", "enabled": True},
                {"id": "tool.web.search", "label": "互联网补充", "enabled": True},
                {"id": "tool.chart.render", "label": "图表渲染", "enabled": True},
            ],
            "answer": [
                {"id": "answer.qa.structured", "label": "结构化问答", "enabled": True},
                {"id": "answer.market.deep", "label": "研究型回答", "enabled": True},
                {"id": "answer.report.evidence", "label": "报告 / 证据链回答", "enabled": True},
                {"id": "answer.redirect.soft", "label": "温和收口", "enabled": True},
            ],
            "render": [
                {"id": "render.text", "label": "文本结果", "enabled": True},
                {"id": "render.metric_cards", "label": "指标卡片", "enabled": True},
                {"id": "render.chart_kline", "label": "K 线图", "enabled": True},
                {"id": "render.chart_line", "label": "线性图", "enabled": True},
                {"id": "render.chart_distribution", "label": "分布图", "enabled": True},
                {"id": "render.followup_tags", "label": "追问标签", "enabled": True},
                {"id": "render.thinking_stream", "label": "思考过程", "enabled": True},
            ],
        },
    },
    "evidence_chain": {
        "filter_prompt_system": (
            "你是知识检索相关性过滤助手。"
            "你的任务是根据用户问题，从召回候选里剔除明显无关、仅语义相近但业务主题不一致的内容。"
            "判断标准必须严格，只有真正能回答问题、或能提供直接支撑信息的知识才能保留。"
            "如果问题是具体领域问题，例如 MES、制造、设备、工艺，就不要保留股票、行情、复盘、泛化观点等无关内容。"
            "输出必须是 JSON，不要输出任何额外解释。"
        ),
        "filter_prompt_user_template": (
            "用户问题：{query}\n\n"
            "候选知识：\n{candidate_blocks}\n\n"
            "请返回 JSON，格式如下：\n"
            "{\n"
            '  "relevant_ids": ["保留的候选ID"],\n'
            '  "reason": "一句话说明筛选结论"\n'
            "}\n"
            "如果没有任何相关知识，relevant_ids 返回空数组。"
        ),
        "filter_timeout_seconds": 25,
        "answer_timeout_seconds": 45,
    },
    "review_generation": {
        "polish_system_prompt": (
            "你是中文投研复盘助手。"
            "你的任务是先对大V输入的原始材料做轻量整理和润色，删除明显重复、口语噪音和无效赘述，"
            "但必须保留原有事实、判断、风险提示和不确定性。"
            "不要新增原文没有出现的观点、数据和投资建议。"
            "输出纯文本，按自然段组织，保持便于后续继续组合成完整复盘。"
        ),
        "polish_user_template": (
            "复盘周期：{period_label}\n"
            "输入来源：{source_mode}\n"
            "作者：{speaker_label}\n"
            "触发入口：{entry_point}\n\n"
            "请先把下面的原始输入整理成更干净、更适合后续继续生成复盘正文的中间稿。"
            "重点保留：市场主线、行业判断、重点个股、验证节点、风险边界。\n\n"
            "原始输入：\n{source_text}"
        ),
        "compose_system_prompt": (
            "你是中文投研复盘编辑助手。"
            "你要基于大V自己的输入，以及已选中的智能仪表盘卡片，生成一版完整复盘草稿。"
            "必须优先保留大V自己的核心判断和风险表达，智能仪表盘只用于补充证据、结构和验证节点。"
            "不要编造事实、数字、新闻或结论。"
            "输出纯文本，语言专业、克制、可直接给大V继续人工修改。"
            "尽量压缩表达，草稿长度默认应少于原始输入长度。"
        ),
        "compose_user_template": (
            "复盘周期：{period_label}\n"
            "作者：{speaker_label}\n"
            "触发入口：{entry_point}\n"
            "纳入样本：{watchlist_text}\n"
            "附加标签：{tag_text}\n"
            "额外要求：{prompt_text}\n\n"
            "这是大V最终确认前的复盘草稿，请基于以下两部分内容生成：\n"
            "1. 大V输入/润色稿\n"
            "2. 智能仪表盘卡片摘要（每张卡片都附有数据来源和新闻来源）\n"
            "3. 大V已选择的知识材料\n\n"
            "大V输入：\n{source_text}\n\n"
            "智能仪表盘卡片：\n{dashboard_blocks}\n\n"
            "知识材料：\n{knowledge_blocks}\n\n"
            "请直接输出最终复盘草稿，不要解释处理过程，不要输出“以下是结果”等前缀。"
        ),
        "polish_timeout_seconds": 45,
        "compose_timeout_seconds": 60,
    },
    "llm_registry": {
        "default_model_key": "gangtise-gemma4-31b-q4km",
        "models": copy.deepcopy(DEFAULT_LLM_MODELS),
        "feature_model_keys": {
            "review_voice_enhancement": "gangtise-gemma4-12b-bf16",
        },
    },
    "brand": DEFAULT_BRAND_CONFIG,
    "default_tenant_slug": DEFAULT_TENANTS[0]["slug"],
    "tenants": DEFAULT_TENANTS,
    "feature_flags": {
        "user_module": True,
        "kol_module": True,
        "fundamental_analysis": True,
        "watchlist": True,
        "stock_forecast": False,
        "daily_review": True,
        "knowledge": True,
        "community": False,
        "hermes": True,
        "channel_module": True,
        "analytics_module": True,
        "system_module": True,
        "vip": False,
        "dm": True,
        "fan_interaction": False,
        "watchlist_fan_comment_interaction": True,
        "paid_reply": False,
        "workbench": True,
    },
}

__all__ = [name for name in globals() if not name.startswith("__")]
