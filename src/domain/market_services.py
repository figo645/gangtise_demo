from src.runtime import *
from src.domain.core_services import *
from src.domain.core_services import _load_json_app_setting, _save_json_app_setting
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from urllib.parse import urljoin
from email.utils import parsedate_to_datetime
import shutil
import subprocess
import threading
from zoneinfo import ZoneInfo

_watchlist_comments_schema_lock = threading.Lock()
_watchlist_comments_schema_ready = False
_user_watchlist_schema_lock = threading.Lock()
_user_watchlist_schema_targets = set()


def _parse_market_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if " " in text else text[:10], fmt)
        except (TypeError, ValueError):
            continue
    return None


def is_cn_stock_market_open(now=None):
    if now is not None:
        current = now
    else:
        try:
            current = datetime.now(ZoneInfo("Asia/Shanghai"))
        except Exception:
            current = datetime.now()
    if current.weekday() >= 5:
        return False
    minutes = current.hour * 60 + current.minute
    morning_open = 9 * 60 + 30
    morning_close = 11 * 60 + 30
    afternoon_open = 13 * 60
    afternoon_close = 15 * 60
    return (morning_open <= minutes < morning_close) or (afternoon_open <= minutes < afternoon_close)

def gen_funnel_data():
    base = [68000, 5400, 1260, 128, 36]
    return [{"layer": FUNNEL_LAYERS[i], "count": base[i], "rate": round(base[i]/base[0]*100, 2)} for i in range(5)]

def gen_channel_data():
    color_map = {
        "微信社群": "#07C160",
        "内容合作": "#FE2C55",
        "小红书": "#FF2442",
        "转介绍": "#E6162D",
        "直接流量": "#C8A96E",
    }
    fallback = [
        {"name": "微信社群", "users": 2100, "conversion": 6.4, "revenue": 28600, "color": "#07C160"},
        {"name": "内容合作", "users": 1400, "conversion": 4.8, "revenue": 19200, "color": "#FE2C55"},
        {"name": "小红书", "users": 980, "conversion": 3.6, "revenue": 13600, "color": "#FF2442"},
        {"name": "转介绍", "users": 620, "conversion": 12.1, "revenue": 24800, "color": "#E6162D"},
        {"name": "直接流量", "users": 300, "conversion": 15.0, "revenue": 16800, "color": "#C8A96E"},
    ]
    try:
        users = list_users()
    except Exception:
        return fallback
    stats = {
        channel: {"users": 0, "paid_users": 0}
        for channel in CHANNELS
    }
    for user in users:
        if str(user.get("status") or "").strip().lower() != "active":
            continue
        if str(user.get("role") or "").strip().lower() not in {"investor", "dav"}:
            continue
        channel = str(user.get("h5_channel_label") or user.get("source_label") or "").strip()
        if channel not in stats:
            continue
        stats[channel]["users"] += 1
        if str(user.get("role") or "").strip().lower() == "investor" and bool(user.get("is_paid_sample")):
            stats[channel]["paid_users"] += 1
    if not any(item["users"] for item in stats.values()):
        return fallback
    return [
        {
            "name": channel,
            "users": stats[channel]["users"],
            "conversion": round((stats[channel]["paid_users"] / stats[channel]["users"] * 100), 1) if stats[channel]["users"] else 0,
            "revenue": stats[channel]["paid_users"] * 500,
            "color": color_map.get(channel, "#C8A96E"),
        }
        for channel in CHANNELS
    ]


def build_admin_channel_payload():
    """Build channel metrics from persisted users without synthetic fallbacks."""
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows_by_channel = {}
    try:
        users = list_users()
    except Exception:
        raise
    for user in users or []:
        if not isinstance(user, dict) or str(user.get("status") or "").lower() != "active":
            continue
        if str(user.get("role") or "").lower() != "investor":
            continue
        channel = str(user.get("h5_channel_label") or user.get("source_label") or "未标注渠道").strip() or "未标注渠道"
        bucket = rows_by_channel.setdefault(channel, {"users": 0, "new_users_month": 0, "paid_users": 0, "revenue": 0})
        bucket["users"] += 1
        created_at = str(user.get("created_at") or "")[:19]
        try:
            created = datetime.fromisoformat(created_at)
        except ValueError:
            created = None
        if created and created >= month_start:
            bucket["new_users_month"] += 1
        if bool(user.get("is_paid_sample")):
            bucket["paid_users"] += 1
            tenant_slug = str(user.get("tenant_slug") or "").strip().lower()
            price = int(load_tenant_fan_ops_settings(tenant_slug).get("registration_price") or 0) if tenant_slug else 0
            bucket["revenue"] += price
    colors = {"微信社群": "#07C160", "内容合作": "#FE2C55", "小红书": "#FF2442", "转介绍": "#E6162D", "直接流量": "#C8A96E"}
    rows = []
    for channel, bucket in sorted(rows_by_channel.items(), key=lambda pair: (-pair[1]["users"], pair[0])):
        users_count = bucket["users"]
        paid_count = bucket["paid_users"]
        rows.append({
            "name": channel,
            "users": users_count,
            "new_users_month": bucket["new_users_month"],
            "paid_users": paid_count,
            "conversion": round(paid_count / users_count * 100, 1) if users_count else 0,
            "revenue": bucket["revenue"],
            "average_paid_value": round(bucket["revenue"] / paid_count, 2) if paid_count else 0,
            "cac": None,
            "roi": None,
            "color": colors.get(channel, "#C8A96E"),
            "status": "有真实用户" if users_count else "无数据",
        })
    total_users = sum(row["users"] for row in rows)
    total_new = sum(row["new_users_month"] for row in rows)
    total_paid = sum(row["paid_users"] for row in rows)
    total_revenue = sum(row["revenue"] for row in rows)
    return {
        "generated_at": now_ts(),
        "basis": "用户表渠道字段、注册时间、付费标注和租户注册单价",
        "active_channels": sum(1 for row in rows if row["users"] > 0),
        "total_users": total_users,
        "new_users_month": total_new,
        "paid_users": total_paid,
        "conversion": round(total_paid / total_users * 100, 1) if total_users else 0,
        "revenue": total_revenue,
        "cac_available": False,
        "roi_available": False,
        "rows": rows,
    }


def build_admin_funnel_payload():
    """Build the analytics funnel from persisted users and access events."""
    users = [
        user for user in list_users(role="investor")
        if isinstance(user, dict) and str(user.get("status") or "active").lower() == "active"
    ]
    channels = build_admin_channel_payload()
    tenant_prices = {}
    for tenant in get_tenant_configs():
        slug = str(tenant.get("slug") or "").strip().lower()
        if slug:
            tenant_prices[slug] = int(load_tenant_fan_ops_settings(slug).get("registration_price") or 0)

    onboarding_users = [user for user in users if str(user.get("onboarding_completed_at") or "").strip()]
    paid_users = [user for user in users if bool(user.get("is_paid_sample"))]
    high_frequency_users = [
        user for user in users
        if "高频用户" in (user.get("labels") if isinstance(user.get("labels"), list) else [])
    ]
    content_reach = 0
    try:
        since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        reach_row = get_db().execute(
            "SELECT COUNT(*) AS count FROM access_logs WHERE user_role = ? AND created_at >= ?",
            ("investor", since),
        ).fetchone()
        content_reach = int((reach_row or {}).get("count") or 0) if isinstance(reach_row, dict) else int(reach_row[0] or 0)
    except Exception:
        # A missing DB context or unavailable DB must never trigger a provider
        # call from the read path or manufacture a market value.
        pass

    stage_counts = [content_reach, len(users), len(onboarding_users), len(paid_users), len(high_frequency_users)]
    funnel = [
        {"layer": label, "count": count, "rate": round(count / content_reach * 100, 2) if content_reach else 0}
        for label, count in zip(FUNNEL_LAYERS, stage_counts)
    ]

    monthly = []
    cursor = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_starts = []
    for _ in range(12):
        month_starts.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    month_starts.reverse()
    for month_start in month_starts:
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        paid_until = [
            user for user in paid_users
            if (_parse_market_datetime(user.get("paid_sample_marked_at")) or _parse_market_datetime(user.get("created_at")))
            and (_parse_market_datetime(user.get("paid_sample_marked_at")) or _parse_market_datetime(user.get("created_at"))) < next_month
        ]
        monthly.append({
            "month": month_start.strftime("%Y-%m"),
            "revenue": sum(tenant_prices.get(str(user.get("tenant_slug") or "").lower(), 0) for user in paid_until),
            "users": len(paid_until),
        })

    segments = [
        {"segment": "未付费用户", "count": max(0, len(users) - len(paid_users))},
        {"segment": "付费用户", "count": len(paid_users)},
        {"segment": "高频付费用户", "count": sum(1 for user in paid_users if user in high_frequency_users)},
    ]
    tenant_rows = []
    for tenant in get_tenant_configs():
        slug = str(tenant.get("slug") or "").strip().lower()
        if not slug:
            continue
        tenant_fans = [user for user in users if str(user.get("tenant_slug") or "").lower() == slug]
        paid_count = sum(1 for user in tenant_fans if bool(user.get("is_paid_sample")))
        revenue = paid_count * tenant_prices.get(slug, 0)
        tenant_rows.append({
            "name": str(tenant.get("advisor") or tenant.get("name") or slug),
            "gmv": revenue,
            "commission": 0,
        })
    tenant_rows.sort(key=lambda item: (-item["gmv"], item["name"]))
    heatmap = []
    for row in channels.get("rows") or []:
        channel_users = [
            user for user in users
            if str(user.get("h5_channel_label") or user.get("source_label") or "未标注渠道").strip() == row["name"]
        ]
        channel_paid = sum(1 for user in channel_users if bool(user.get("is_paid_sample")))
        channel_onboarding = sum(1 for user in channel_users if str(user.get("onboarding_completed_at") or "").strip())
        heatmap.append({
            "channel": row["name"],
            "values": [100, round(channel_onboarding / len(channel_users) * 100, 1) if channel_users else 0,
                       round(channel_onboarding / len(channel_users) * 100, 1) if channel_users else 0,
                       round(channel_paid / len(channel_users) * 100, 1) if channel_users else 0,
                       round(sum(1 for user in channel_users if "高频用户" in (user.get("labels") or [])) / len(channel_users) * 100, 1) if channel_users else 0],
        })
    return {
        "generated_at": now_ts(),
        "basis": "访问日志、用户表注册/激活字段、付费标注、租户注册单价和用户渠道字段",
        "funnel": funnel,
        "channels": channels,
        "monthly": monthly,
        "kols": tenant_rows,
        "segments": segments,
        "heatmap": heatmap,
    }

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

def gen_market_data(watchlist_details=None):
    # The public market endpoint keeps its legacy catalog when no owner is
    # supplied. H5 passes an explicit map, including {}, so a user's empty
    # watchlist cannot be replaced by the old demo catalog.
    if watchlist_details is not None:
        display_catalog = [
            {
                "code": str(code),
                "name": str(detail.get("name") or code),
                "market": str(detail.get("market") or _infer_watchlist_market(code)),
                "focus": str(detail.get("industry") or detail.get("focus") or "个股跟踪"),
                "board": str(detail.get("industry") or detail.get("focus") or "个股跟踪"),
            }
            for code, detail in (watchlist_details or {}).items()
            if isinstance(detail, dict)
        ]
        details_map = watchlist_details or {}
    else:
        display_catalog = [
            {"code": "600519", "name": "贵州茅台", "market": "SH", "focus": "高端白酒", "board": "稳健配置"},
            {"code": "300750", "name": "宁德时代", "market": "SZ", "focus": "动力电池", "board": "新能源"},
            {"code": "00700", "name": "腾讯控股", "market": "HK", "focus": "港股互联网", "board": "港股互联网"},
            {"code": "688981", "name": "中芯国际", "market": "SH", "focus": "半导体制造", "board": "科技成长"},
            {"code": "600036", "name": "招商银行", "market": "SH", "focus": "银行", "board": "稳健配置"},
        ]
        details_map = gen_watchlist_details()
    items = []
    for config in display_catalog:
        detail = get_watchlist_detail_by_code(
            stock_code=config["code"],
            stock_name=config["name"],
            details_map=details_map,
        ) or {}
        if not detail:
            continue
        authors = [
            str(item.get("name") or "").strip()
            for item in (detail.get("authors") or [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        items.append(
            {
                "code": config["code"],
                "name": detail.get("name") or config["name"],
                "market": detail.get("market") or config["market"],
                # A missing Gangtise quote must remain null through rendering.
                # Converting it with NumberLike would make the H5 claim 0.00.
                "value": round(NumberLike(detail.get("price")), 2) if not detail.get("data_unavailable") and numeric_value(detail.get("price")) is not None else None,
                "change": round(NumberLike(detail.get("change")), 2) if not detail.get("data_unavailable") and numeric_value(detail.get("change")) is not None else None,
                "change_pct": round(NumberLike(detail.get("change_pct")), 2) if not detail.get("data_unavailable") and numeric_value(detail.get("change_pct")) is not None else None,
                "focus": canonical_hot_industry_name(detail.get("industry") or detail.get("focus") or config["focus"]),
                "board": config["board"],
                "alert_level": detail.get("alert_level") or "attention",
                "alert_text": detail.get("alert_text") or ("Gangtise 行情暂未返回，当前先保留研究内容框架。" if detail.get("data_unavailable") else "当前无明显预警"),
                "signal_summary": detail.get("signal_summary") or detail.get("fundamental", {}).get("summary") or "继续结合租户知识和真实行情跟踪。",
                "authors": authors,
                "data_source": detail.get("data_source") or "gangtise_openapi",
                "data_unavailable": bool(detail.get("data_unavailable")),
            }
        )
    return items


def _normalize_user_watchlist_owner(tenant_slug="", user_profile_id=""):
    tenant = str(tenant_slug or "").strip().lower()
    profile = str(user_profile_id or "").strip()
    if not tenant:
        raise ValueError("tenant_slug_required")
    if not profile:
        raise ValueError("user_profile_id_required")
    return tenant, profile


def _ensure_user_watchlist_items_table(db=None):
    """Create the relation for databases deployed before migration 033."""
    global _user_watchlist_schema_targets
    database = db or get_db()
    connection = getattr(database, "_connection", None)
    # Test doubles and alternate adapters may not expose psycopg2's
    # connection. The normal query remains responsible for those adapters.
    if connection is None:
        return
    connection_info = getattr(connection, "info", None)
    target_key = str(getattr(connection_info, "dsn", "") or "").strip() or str(id(connection))
    with _user_watchlist_schema_lock:
        if target_key in _user_watchlist_schema_targets:
            return
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_watchlist_items (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_slug TEXT NOT NULL DEFAULT '',
                    user_profile_id TEXT NOT NULL DEFAULT '',
                    stock_code TEXT NOT NULL DEFAULT '',
                    stock_name TEXT NOT NULL DEFAULT '',
                    market TEXT NOT NULL DEFAULT '',
                    industry TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_user_watchlist_items_owner_stock
                ON user_watchlist_items(tenant_slug, user_profile_id, stock_code)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_watchlist_items_owner_updated
                ON user_watchlist_items(tenant_slug, user_profile_id, updated_at DESC, id DESC)
                """
            )
        connection.commit()
        _user_watchlist_schema_targets.add(target_key)


def list_user_watchlist_items(tenant_slug="", user_profile_id=""):
    tenant, profile = _normalize_user_watchlist_owner(tenant_slug, user_profile_id)
    db = get_db()
    _ensure_user_watchlist_items_table(db)
    rows = db.execute(
        """
        SELECT id, tenant_slug, user_profile_id, stock_code, stock_name, market, industry,
               created_at, updated_at
        FROM user_watchlist_items
        WHERE tenant_slug = ? AND user_profile_id = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (tenant, profile),
    ).fetchall()
    result = []
    for row in rows:
        code = str(row.get("stock_code") or "").strip().upper()
        if not code:
            continue
        detail = get_watchlist_detail_by_code(
            stock_code=code,
            stock_name=str(row.get("stock_name") or code),
            details_map={},
        ) or {}
        if detail:
            detail["watchlist_item_id"] = row.get("id")
            detail["watchlist_created_at"] = row.get("created_at")
            detail["watchlist_updated_at"] = row.get("updated_at")
            result.append(detail)
    return result


def add_user_watchlist_item(tenant_slug="", user_profile_id="", stock_code="", stock_name=""):
    tenant, profile = _normalize_user_watchlist_owner(tenant_slug, user_profile_id)
    raw_code = str(stock_code or "").strip()
    normalized_code = normalize_watchlist_indicator_code(raw_code) or raw_code.upper()
    if not normalized_code:
        raise ValueError("stock_code_required")
    detail = get_watchlist_detail_by_code(
        stock_code=normalized_code,
        stock_name=str(stock_name or normalized_code),
        details_map={},
    )
    if not detail:
        raise ValueError("watchlist_stock_not_found")
    now = now_ts()
    db = get_db()
    _ensure_user_watchlist_items_table(db)
    db.execute(
        """
        INSERT INTO user_watchlist_items
            (tenant_slug, user_profile_id, stock_code, stock_name, market, industry, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (tenant_slug, user_profile_id, stock_code)
        DO UPDATE SET stock_name = EXCLUDED.stock_name, market = EXCLUDED.market,
                      industry = EXCLUDED.industry, updated_at = EXCLUDED.updated_at
        """,
        (
            tenant,
            profile,
            normalized_code,
            str(detail.get("name") or stock_name or normalized_code).strip(),
            str(detail.get("market") or _infer_watchlist_market(normalized_code)).strip(),
            canonical_hot_industry_name(detail.get("industry") or detail.get("focus") or "个股跟踪"),
            now,
            now,
        ),
    )
    db.commit()
    return next((item for item in list_user_watchlist_items(tenant, profile) if item.get("code") == normalized_code), detail)


def remove_user_watchlist_item(tenant_slug="", user_profile_id="", stock_code=""):
    tenant, profile = _normalize_user_watchlist_owner(tenant_slug, user_profile_id)
    normalized_code = normalize_watchlist_indicator_code(stock_code) or str(stock_code or "").strip().upper()
    if not normalized_code:
        raise ValueError("stock_code_required")
    db = get_db()
    _ensure_user_watchlist_items_table(db)
    deleted = db.execute(
        "DELETE FROM user_watchlist_items WHERE tenant_slug = ? AND user_profile_id = ? AND stock_code = ?",
        (tenant, profile, normalized_code),
    ).rowcount or 0
    db.commit()
    return bool(deleted)


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


GANGTISE_OPENAPI_SUCCESS_CODE = "000000"
GANGTISE_OPENAPI_LOGIN_PATH = "/application/auth/oauth/open/loginV2"
_gangtise_env_loaded = False
_gangtise_token_lock = threading.Lock()
_gangtise_token_cache = {"token": "", "fetched_at": 0.0}
_intraday_fetch_locks = {}
_intraday_fetch_locks_guard = threading.Lock()
_watchlist_detail_fetch_locks = {}
_watchlist_detail_fetch_locks_guard = threading.Lock()

GANGTISE_INDICATOR_REGISTRY = {
    "source_shanghai_index": {
        "indicator_name": "上证指数",
        "category": "数据湖指标",
        "query_kind": "index_kline",
        "security_code": "000001.SH",
        "tencent_symbol": "sh000001",
        "search_keyword": "上证指数",
    },
    "source_shenzhen_index": {
        "indicator_name": "深证指数",
        "category": "数据湖指标",
        "query_kind": "index_kline",
        "security_code": "399001.SZ",
        "tencent_symbol": "sz399001",
        "search_keyword": "深证指数",
    },
    "source_hs300": {
        "indicator_name": "沪深300",
        "category": "数据湖指标",
        "query_kind": "index_kline",
        "security_code": "000300.SH",
        "tencent_symbol": "sh000300",
        "search_keyword": "沪深300",
    },
    "source_sse50": {
        "indicator_name": "上证50",
        "category": "数据湖指标",
        "query_kind": "index_kline",
        "security_code": "000016.SH",
        "tencent_symbol": "sh000016",
        "search_keyword": "上证50",
    },
    "source_kc50": {
        "indicator_name": "科创50",
        "category": "数据湖指标",
        "query_kind": "index_kline",
        "security_code": "000688.SH",
        "tencent_symbol": "sh000688",
        "search_keyword": "科创50",
    },
    "source_cyb": {
        "indicator_name": "创业板指",
        "category": "数据湖指标",
        "query_kind": "index_kline",
        "security_code": "399006.SZ",
        "tencent_symbol": "sz399006",
        "search_keyword": "创业板指",
    },
    "source_zz500": {
        "indicator_name": "中证500",
        "category": "数据湖指标",
        "query_kind": "index_kline",
        "security_code": "000905.SH",
        "search_keyword": "中证500",
    },
    "source_zz1000": {
        "indicator_name": "中证1000",
        "category": "数据湖指标",
        "query_kind": "index_kline",
        "security_code": "000852.SH",
        "search_keyword": "中证1000",
    },
    "source_zz800": {
        "indicator_name": "中证800",
        "category": "数据湖指标",
        "query_kind": "index_kline",
        "security_code": "000906.SH",
        "search_keyword": "中证800",
    },
    "source_a500": {
        "indicator_name": "中证A500",
        "category": "数据湖指标",
        "query_kind": "index_kline",
        "security_code": "000510.SH",
        "search_keyword": "中证A500",
    },
    "source_zz2000": {
        "indicator_name": "中证2000",
        "category": "数据湖指标",
        "query_kind": "index_kline",
        "security_code": "932000.CSI",
        "search_keyword": "中证2000",
    },
    "source_brent": {
        "indicator_name": "布伦特原油",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "search_keyword": "布伦特原油",
        "preferred_indicator_id": "S06000521",
    },
    "source_cpi": {
        "indicator_name": "中国CPI同比指数",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "search_keyword": "CPI:同比指数",
        "preferred_indicator_id": "M00000016",
        "expected_indicator_name": "CPI:同比指数:当月值",
        "expected_data_source": "国家统计局",
        "valid_value_range": (50, 200),
    },
    "source_dji": {
        "indicator_name": "道琼斯",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "market": "US",
        "search_keyword": "道琼斯工业平均指数",
        "preferred_indicator_id": "M00009829",
    },
    "source_gold": {
        "indicator_name": "黄金",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "search_keyword": "伦敦黄金",
        "preferred_indicator_id": "S04000018",
    },
    "source_hsi": {
        "indicator_name": "恒生指数",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "market": "HK",
        "search_keyword": "恒生指数",
        "preferred_indicator_id": "M00015437",
    },
    "source_hscei": {
        "indicator_name": "国企指数",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "market": "HK",
        "search_keyword": "恒生中国企业指数",
    },
    "source_hscci": {
        "indicator_name": "红筹指数",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "market": "HK",
        "search_keyword": "恒生红筹指数",
    },
    "source_industry_index": {
        "indicator_name": "行业指数",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "search_keyword": "Wind行业指数",
        "preferred_indicator_id": "S02002067",
    },
    "source_news": {
        "indicator_name": "新闻情绪",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "search_keyword": "新闻情绪指数",
        "preferred_indicator_id": "M00015816",
    },
    "source_nikkei": {
        "indicator_name": "日经225",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "market": "JP",
        "search_keyword": "日经225指数",
        "preferred_indicator_id": "M00015432",
    },
    "source_oil": {
        "indicator_name": "原油",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "search_keyword": "WTI原油",
        "preferred_indicator_id": "S00055151",
    },
    "source_silver": {
        "indicator_name": "白银",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "search_keyword": "COMEX白银",
        "preferred_indicator_id": "S04000637",
    },
    "source_sp500": {
        "indicator_name": "标普500",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "market": "US",
        "search_keyword": "标准普尔500指数",
        "preferred_indicator_id": "M00006167",
    },
    "source_nasdaq": {
        "indicator_name": "纳斯达克",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "market": "US",
        "search_keyword": "纳斯达克综合指数",
        "preferred_indicator_id": "M00009828",
    },
    "source_bdi": {
        "indicator_name": "BDI",
        "category": "数据湖指标",
        "query_kind": "edb_search",
        "search_keyword": "BDI",
    },
}


def _load_gangtise_env_file(env_path):
    path = Path(env_path)
    if not path.is_file():
        return False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = str(raw_line or "").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return True


def _ensure_gangtise_env_loaded():
    global _gangtise_env_loaded
    if _gangtise_env_loaded:
        return
    # Keep the application-owned credential file canonical. The path is
    # overrideable for container deployments, but never points at another
    # project by default.
    configured_path = str(os.environ.get("GANGTISE_OPENAPI_CREDENTIALS_FILE") or "").strip()
    env_path = Path(configured_path) if configured_path else PROJECT_ROOT / ".gangtise_openapi_credentials"
    for env_path in (env_path,):
        try:
            _load_gangtise_env_file(env_path)
        except Exception:
            app.logger.exception("Failed to load Gangtise OpenAPI environment file: %s", env_path)
    _gangtise_env_loaded = True


def get_gangtise_openapi_config():
    """Use the proven runtime credentials first, then PostgreSQL as migration fallback."""
    _ensure_gangtise_env_loaded()
    environment_credentials = {
        "base_url": str(os.environ.get("GANGTISE_API_BASE_URL") or "").strip().rstrip("/"),
        "access_key": str(os.environ.get("GANGTISE_ACCESS_KEY") or "").strip(),
        "secret_key": str(os.environ.get("GANGTISE_SECRET_KEY") or "").strip(),
        "long_token": str(os.environ.get("GANGTISE_LONG_TOKEN") or "").strip(),
    }
    if (
        (environment_credentials["access_key"] and environment_credentials["secret_key"])
        or environment_credentials["long_token"]
    ):
        environment_credentials["base_url"] = environment_credentials["base_url"] or GANGTISE_OPENAPI_DEFAULT_BASE_URL
        return environment_credentials
    database_credentials = load_gangtise_openapi_credentials()
    if database_credentials and (
        (database_credentials.get("access_key") and database_credentials.get("secret_key"))
        or database_credentials.get("long_token")
    ):
        return database_credentials
    return {
        "base_url": environment_credentials["base_url"] or GANGTISE_OPENAPI_DEFAULT_BASE_URL,
        "access_key": "",
        "secret_key": "",
        "long_token": "",
    }


def invalidate_gangtise_openapi_token_cache():
    """Forget the previous bearer token after an Admin credential update."""
    with _gangtise_token_lock:
        _gangtise_token_cache["token"] = ""
        _gangtise_token_cache["fetched_at"] = 0.0


def _gangtise_request_json(path, payload, headers=None, timeout=30):
    config = get_gangtise_openapi_config()
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if isinstance(headers, dict) and headers:
        request_headers.update(headers)
    started = time.perf_counter()
    request_obj = Request(f"{config['base_url']}{path}", data=body, headers=request_headers, method="POST")
    try:
        with urlopen(request_obj, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            parsed = decode_json_payload(raw)
            return response.status, parsed, round((time.perf_counter() - started) * 1000)
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        return error.code, decode_json_payload(raw), round((time.perf_counter() - started) * 1000)
    except URLError as error:
        return 0, {"message": f"Network error: {error.reason}"}, round((time.perf_counter() - started) * 1000)
    except Exception as error:
        return 0, {"message": f"Unexpected error: {error}"}, round((time.perf_counter() - started) * 1000)


def decode_json_payload(raw):
    try:
        value = json.loads(raw)
    except Exception:
        return {"raw": raw}
    return value if isinstance(value, dict) else {"data": value}


def numeric_value(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def obtain_gangtise_openapi_token(force_refresh=False):
    config = get_gangtise_openapi_config()
    access_key = config.get("access_key") or ""
    secret_key = config.get("secret_key") or ""
    long_token = config.get("long_token") or ""
    if not (access_key and secret_key) and not long_token:
        status = get_gangtise_openapi_credentials_status()
        reason = {
            "missing": "no encrypted credential record exists in the current PostgreSQL database",
            "unreadable": "the PostgreSQL credential record cannot be decrypted with the current application secret",
            "database_unavailable": "the current PostgreSQL database is unavailable",
            "malformed": "the PostgreSQL credential record is malformed",
        }.get(str(status.get("encryption_status") or ""), "the credential record has no usable Access Key/Secret Key or Long Token")
        return False, "", {"message": f"Gangtise OpenAPI credentials are not configured: {reason}."}, 0, 0
    now_value = time.time()
    with _gangtise_token_lock:
        cached_token = _gangtise_token_cache.get("token") or ""
        fetched_at = float(_gangtise_token_cache.get("fetched_at") or 0.0)
        if cached_token and not force_refresh and now_value - fetched_at < 45 * 60:
            return True, cached_token, {"source": "cache"}, 200, 0
        if access_key and secret_key:
            status, response, duration = _gangtise_request_json(
                GANGTISE_OPENAPI_LOGIN_PATH,
                {"accessKey": access_key, "secretKey": secret_key},
                timeout=20,
            )
            token = str(((response.get("data") or {}).get("accessToken") or "")).strip()
            ok = status == 200 and str(response.get("code") or "") == GANGTISE_OPENAPI_SUCCESS_CODE and bool(token)
            if ok:
                _gangtise_token_cache["token"] = token
                _gangtise_token_cache["fetched_at"] = now_value
                return True, token, response, status, duration
        if long_token:
            return True, long_token, {"source": "postgresql_credentials"}, 200, 0
        return False, "", {"message": "Gangtise OpenAPI token login failed."}, 0, 0


def _is_gangtise_token_invalid(response):
    if not isinstance(response, dict):
        return False
    message = " ".join(
        [
            str(response.get("msg") or "").strip(),
            str(response.get("message") or "").strip(),
            str(response.get("error") or "").strip(),
        ]
    ).strip().lower()
    return "token is invalid" in message or "invalid token" in message or "token invalid" in message


def post_gangtise_openapi_json(path, payload, token="", timeout=30, _retried=False):
    effective_token = str(token or "").strip()
    auth_status = None
    auth_response = {}
    auth_duration = 0
    if not effective_token:
        token_ok, fetched_token, auth_response, auth_status, auth_duration = obtain_gangtise_openapi_token()
        if not token_ok:
            return auth_status, auth_response, auth_duration
        effective_token = fetched_token
    headers = {"Authorization": effective_token if effective_token.startswith("Bearer ") else f"Bearer {effective_token}"}
    status, response, duration = _gangtise_request_json(path, payload, headers=headers, timeout=timeout)
    if not _retried and _is_gangtise_token_invalid(response):
        token_ok, refreshed_token, auth_response, auth_status, auth_duration = obtain_gangtise_openapi_token(force_refresh=True)
        if token_ok and refreshed_token:
            retried_status, retried_response, retried_duration = post_gangtise_openapi_json(
                path,
                payload,
                token=refreshed_token,
                timeout=timeout,
                _retried=True,
            )
            return retried_status, retried_response, auth_duration + retried_duration
    return status, response, duration


_GANGTISE_SSE_CONTROL_TEXTS = {
    "[DONE]",
    "DONE",
    "success",
    "ok",
    "started",
    "start",
    "processing",
    "pending",
    "thinking",
    "retrieving",
    "searching",
    "generating",
    "completed",
    "complete",
    "成功",
    "处理中",
    "正在生成",
    "已完成",
}


def _extract_gangtise_sse_text(value):
    """Extract assistant text from the known Agent SSE response envelopes.

    The Agent endpoint has returned several compatible envelopes over time:
    direct ``content``/``answer`` fields, OpenAI-style ``choices`` deltas, and
    JSON encoded again inside ``data``.  Status events are intentionally
    ignored so an HTTP 200 stream cannot be mistaken for an answer.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text or text in _GANGTISE_SSE_CONTROL_TEXTS or text.lower() in _GANGTISE_SSE_CONTROL_TEXTS:
            return ""
        if text.startswith(("{", "[")):
            try:
                nested = json.loads(text)
            except Exception:
                nested = None
            if isinstance(nested, (dict, list)):
                extracted = _extract_gangtise_sse_text(nested)
                if extracted:
                    return extracted
        return text
    if isinstance(value, list):
        parts = [_extract_gangtise_sse_text(item) for item in value]
        return "".join(item for item in parts if item)
    if not isinstance(value, dict):
        return ""

    # OpenAI-compatible streaming responses use choices[].delta.content,
    # while the non-streaming shape uses choices[].message.content.
    choices = value.get("choices")
    if isinstance(choices, list):
        candidate = _extract_gangtise_sse_text(choices)
        if candidate:
            return candidate

    for key in (
        "answer",
        "answerText",
        "content",
        "output",
        "output_text",
        "outputText",
        "text",
        "delta",
        "reply",
        "finalAnswer",
        "resultText",
        "answer_content",
        "contentList",
        "result",
        "message",
    ):
        candidate = _extract_gangtise_sse_text(value.get(key))
        if candidate:
            return candidate
    for key in (
        "data",
        "payload",
        "response",
        "body",
        "responseBody",
        "resultData",
        "answerData",
        "parts",
        "segments",
        "items",
        "messages",
        "events",
    ):
        candidate = _extract_gangtise_sse_text(value.get(key))
        if candidate:
            return candidate
    raw_value = str(value.get("raw") or "").strip()
    if not raw_value or raw_value in _GANGTISE_SSE_CONTROL_TEXTS or raw_value.lower() in _GANGTISE_SSE_CONTROL_TEXTS:
        return ""
    if raw_value.startswith(("{", "[")):
        return ""
    return raw_value


def _extract_gangtise_agent_answer_delta(value):
    """Extract only the publishable answer delta from Gangtise Agent events.

    The live Agent stream contains internal ``think``, ``search``,
    ``annotation`` and usage events in exactly the same JSON envelope as the
    answer.  Those are useful for diagnostics but must not become review copy.
    This is protocol decoding, not LLM post-processing.
    """
    if not isinstance(value, dict):
        return None
    if str(value.get("phase") or "").strip().lower() != "answer":
        return None
    result = value.get("result")
    if not isinstance(result, dict):
        return ""
    return str(result.get("delta") or "")


def _gangtise_sse_event_shape(value):
    """Return non-sensitive keys useful for diagnosing an empty HTTP 200 stream."""
    if isinstance(value, dict):
        shape = list(value.keys())[:20]
        for key in ("data", "payload", "response", "body", "responseBody", "resultData"):
            nested = value.get(key)
            if isinstance(nested, dict):
                shape.append(f"{key}:{{{','.join(list(nested.keys())[:12])}}}")
        return shape
    return [type(value).__name__]


def _merge_gangtise_sse_texts(candidates):
    """Merge either delta chunks or repeated full snapshots without duplication."""
    merged = ""
    for raw in candidates or []:
        # Keep the exact delta boundaries. In particular, Markdown headings and
        # paragraphs rely on a trailing newline from the upstream SSE event.
        text = str(raw or "")
        stripped_text = text.strip()
        if not stripped_text or stripped_text in {"[DONE]", "DONE"}:
            continue
        if not merged:
            merged = text
            continue
        if text == merged or text.startswith(merged):
            merged = text
            continue
        if merged.startswith(text):
            continue
        overlap = min(len(merged), len(text))
        while overlap and not merged.endswith(text[:overlap]):
            overlap -= 1
        merged += text[overlap:]
    return merged.strip()


def _gangtise_sse_event_has_analysis(parsed, raw_event):
    """Keep unknown non-status events available for direct inspection."""
    if _extract_gangtise_sse_text(parsed):
        return True
    if isinstance(parsed, dict):
        if set(parsed) == {"raw"}:
            raw_text = str(parsed.get("raw") or "").strip().lower()
            return bool(
                raw_text
                and raw_text not in {"[done]", "done"}
                and raw_text not in _GANGTISE_SSE_CONTROL_TEXTS
            )
        control_keys = {"type", "event", "status", "message", "msg", "code", "data", "payload"}
        if set(parsed).issubset(control_keys):
            return False
        return bool(parsed)
    raw_text = str(raw_event or "").strip().lower()
    return bool(raw_text and raw_text not in {"[done]", "done"} and raw_text not in _GANGTISE_SSE_CONTROL_TEXTS)


def post_gangtise_openapi_sse(path, payload, token="", timeout=180, progress_callback=None):
    """Call a Gangtise Agent SSE endpoint and retain the complete raw stream."""
    effective_token = str(token or "").strip()
    if not effective_token:
        token_ok, fetched_token, auth_response, auth_status, auth_duration = obtain_gangtise_openapi_token()
        if not token_ok:
            return {
                "ok": False,
                "status": auth_status or 0,
                "message": str((auth_response or {}).get("message") or "Gangtise OpenAPI 鉴权失败").strip(),
                "duration_ms": auth_duration,
                "text": "",
                "raw_text": "",
                "events": 0,
            }
        effective_token = fetched_token
    headers = {
        "Authorization": effective_token if effective_token.startswith("Bearer ") else f"Bearer {effective_token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
    }
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    request_obj = Request(
        f"{get_gangtise_openapi_config()['base_url']}{path}",
        data=body,
        headers=headers,
        method="POST",
    )
    started = time.perf_counter()
    candidates = []
    raw_events = []
    event_buffer = []
    event_count = 0
    event_shapes = []

    def consume_event():
        nonlocal event_count
        if not event_buffer:
            return
        raw_event = "\n".join(event_buffer).strip()
        event_buffer.clear()
        if not raw_event:
            return
        raw_events.append(raw_event)
        if raw_event == "[DONE]":
            return
        parsed = decode_json_payload(raw_event)
        event_shapes.append(_gangtise_sse_event_shape(parsed))
        agent_answer_delta = _extract_gangtise_agent_answer_delta(parsed)
        has_agent_phase = isinstance(parsed, dict) and bool(str(parsed.get("phase") or "").strip())
        # Gangtise Agent's phase-based stream includes its private reasoning
        # and metadata. Publish only phase=answer; retain every event in
        # raw_text for support diagnostics.
        if agent_answer_delta is not None:
            text = agent_answer_delta
        elif has_agent_phase:
            text = ""
        else:
            text = _extract_gangtise_sse_text(parsed)
        # A few SSE gateways emit one logical event as multiple data lines.
        # If the joined payload is not valid JSON, still parse each fragment.
        if agent_answer_delta is None and "\n" in raw_event and (
            not text
            or (isinstance(parsed, dict) and parsed.get("raw") == raw_event)
        ):
            fragment_texts = []
            for fragment in raw_event.splitlines():
                fragment_payload = decode_json_payload(fragment.strip())
                fragment_text = _extract_gangtise_sse_text(fragment_payload)
                if fragment_text:
                    fragment_texts.append(fragment_text)
            text = "".join(fragment_texts)
        if text:
            candidates.append(text)
        elif agent_answer_delta is None and not has_agent_phase and _gangtise_sse_event_has_analysis(parsed, raw_event):
            candidates.append(raw_event)
        event_count += 1
        if callable(progress_callback):
            try:
                progress_callback(event_count, text, False, raw_event)
            except TypeError:
                progress_callback(event_count, text)

    def notify_partial_on_error():
        partial_text = _merge_gangtise_sse_texts(candidates)
        raw_text = "\n\n".join(raw_events).strip()
        if not (partial_text or raw_text) or not callable(progress_callback):
            return
        try:
            progress_callback(event_count, partial_text, True, raw_text)
        except TypeError:
            progress_callback(event_count, partial_text)

    try:
        with urlopen(request_obj, timeout=timeout) as response:
            for raw_line in response:
                if time.perf_counter() - started >= max(float(timeout or 180), 1.0):
                    raise TimeoutError("gangtise_agent_sse_stream_timeout")
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    consume_event()
                elif line.startswith("data:"):
                    event_buffer.append(line[5:].lstrip())
                elif line.startswith(("event:", "id:", "retry:", ":")):
                    continue
                else:
                    # Some gateways preserve the SSE payload but strip the
                    # data: prefix. Treat each such line as a text event.
                    event_buffer.append(line)
            consume_event()
        text = _merge_gangtise_sse_texts(candidates)
        raw_text = "\n\n".join(raw_events).strip()
        response_status = getattr(response, "status", None)
        if response_status is None and hasattr(response, "getcode"):
            response_status = response.getcode()
        if response_status == 200 and not text:
            app.logger.warning(
                "Gangtise Agent SSE returned no usable analysis text status=%s events=%s event_shapes=%s",
                response_status,
                event_count,
                event_shapes[:6],
            )
        return {
            "ok": bool(response_status == 200 and text),
            "status": response_status or 0,
            "message": "" if text else "Gangtise Agent SSE 未返回可用分析文本",
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "text": text,
            "raw_text": raw_text,
            "events": event_count,
            "event_shapes": event_shapes[:6],
        }
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        if raw.strip():
            raw_events.append(raw.strip())
        notify_partial_on_error()
        parsed = decode_json_payload(raw)
        return {
            "ok": False,
            "status": error.code,
            "message": str(parsed.get("message") or parsed.get("msg") or raw or "Gangtise Agent SSE 请求失败").strip()[:500],
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "text": _merge_gangtise_sse_texts(candidates),
            "raw_text": "\n\n".join(raw_events).strip(),
            "events": event_count,
            "event_shapes": event_shapes[:6],
        }
    except URLError as error:
        notify_partial_on_error()
        return {
            "ok": False,
            "status": 0,
            "message": f"Gangtise Agent SSE 网络错误：{error.reason}",
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "text": _merge_gangtise_sse_texts(candidates),
            "raw_text": "\n\n".join(raw_events).strip(),
            "events": event_count,
            "event_shapes": event_shapes[:6],
        }
    except Exception as error:
        notify_partial_on_error()
        return {
            "ok": False,
            "status": 0,
            "message": f"Gangtise Agent SSE 调用异常：{error}",
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "text": _merge_gangtise_sse_texts(candidates),
            "raw_text": "\n\n".join(raw_events).strip(),
            "events": event_count,
            "event_shapes": event_shapes[:6],
        }


def call_gangtise_agent_sse(text, trace_id="", mode="deep_research", web_enable=True, timeout=180, progress_callback=None):
    """Use the tested multi-stock Agent Assistant SSE contract."""
    request_text = str(text or "").strip()
    if not request_text:
        raise ValueError("gangtise_agent_question_required")
    payload = {
        "text": request_text,
        "mode": str(mode or "deep_research").strip() or "deep_research",
        "askChatParam": {
            "iter": 2,
            "webEnable": bool(web_enable),
            "traceId": str(trace_id or f"gangtise-agent-{int(time.time() * 1000)}").strip(),
        },
    }
    result = post_gangtise_openapi_sse(
        "/application/open-ai/ai/chat/sse",
        payload,
        timeout=timeout,
        progress_callback=progress_callback,
    )
    if not result.get("ok"):
        event_shapes = result.get("event_shapes") or []
        shape_suffix = f":event_shapes={event_shapes[:3]}" if event_shapes else ""
        raise RuntimeError(
            f"gangtise_agent_sse_failed:http_status={result.get('status') or 0}:"
            f"{str(result.get('message') or 'empty_response').strip()[:400]}{shape_suffix}"
        )
    return {
        "text": str(result.get("text") or "").strip(),
        "raw_text": str(result.get("raw_text") or "").strip(),
        "duration_ms": int(result.get("duration_ms") or 0),
        "events": int(result.get("events") or 0),
        "mode": payload["mode"],
        "request": payload,
        "provider": "Gangtise Agent助手 SSE",
        "endpoint": "/application/open-ai/ai/chat/sse",
    }


def choose_gangtise_indicator_candidate(items, keyword="", preferred_indicator_id=""):
    rows = items if isinstance(items, list) else []
    if not rows:
        return None
    preferred = str(preferred_indicator_id or "").strip()
    if preferred:
        for item in rows:
            if str(item.get("indicatorId") or "").strip() == preferred:
                return item
    normalized_keyword = str(keyword or "").strip().lower()
    exact = [
        item for item in rows
        if normalized_keyword and normalized_keyword in str(item.get("indicatorName") or "").strip().lower()
    ]
    return (exact or rows)[0]


def _parse_gangtise_trade_date(value):
    """Return a market date only for unambiguous Gangtise trade-date values."""
    text = str(value or "").strip()
    if not text:
        return None
    matched = re.search(r"\d{4}[-/]\d{2}[-/]\d{2}|\d{8}", text)
    if not matched:
        return None
    candidate = matched.group(0)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return None


def _current_cn_market_date():
    try:
        return datetime.now(ZoneInfo("Asia/Shanghai")).date()
    except Exception:
        return datetime.now().date()


def _clamp_gangtise_trade_end_date(value):
    configured_date = _parse_gangtise_trade_date(value)
    return min(configured_date, _current_cn_market_date()) if configured_date else _current_cn_market_date()


def normalize_gangtise_kline_points(response, max_trade_date=None):
    data = response.get("data") if isinstance(response, dict) else {}
    if not isinstance(data, dict):
        return []
    headers = data.get("fieldList") if isinstance(data.get("fieldList"), list) else []
    rows = data.get("list") if isinstance(data.get("list"), list) else []
    field_index = {field: headers.index(field) for field in headers}
    required = ("tradeDate", "close")
    if any(name not in field_index for name in required):
        return []
    cutoff_date = _clamp_gangtise_trade_end_date(max_trade_date)
    points = []
    for row in rows:
        if not isinstance(row, list):
            continue
        try:
            trade_date = str(row[field_index["tradeDate"]] or "").strip()
            close_value = float(row[field_index["close"]])
        except Exception:
            continue
        parsed_trade_date = _parse_gangtise_trade_date(trade_date)
        # A day K line cannot be a future trading result. Do not expose an
        # upstream placeholder, erroneous row, or future-dated test record.
        if parsed_trade_date is None or parsed_trade_date > cutoff_date:
            continue
        open_value = numeric_value(row[field_index["open"]]) if "open" in field_index else None
        high_value = numeric_value(row[field_index["high"]]) if "high" in field_index else None
        low_value = numeric_value(row[field_index["low"]]) if "low" in field_index else None
        points.append(
            {
                "date": trade_date,
                "open": close_value if open_value is None else open_value,
                "high": close_value if high_value is None else high_value,
                "low": close_value if low_value is None else low_value,
                "close": close_value,
            }
        )
    points.sort(key=lambda item: item["date"])
    return points


def normalize_gangtise_source_line_points(response):
    data = response.get("data") if isinstance(response, dict) else {}
    headers = data.get("fieldList") if isinstance(data, dict) and isinstance(data.get("fieldList"), list) else []
    date_index = headers.index("tradeDate") if "tradeDate" in headers else -1
    close_index = headers.index("close") if "close" in headers else -1
    if date_index < 0 or close_index < 0:
        return []
    points = []
    for row in data.get("list", []) if isinstance(data, dict) else []:
        if not isinstance(row, list) or len(row) <= close_index:
            continue
        close_value = numeric_value(row[close_index])
        if close_value is None:
            continue
        points.append([row[date_index], close_value])
    return points


def _is_valid_cn_stock_intraday_time(value, trade_date=""):
    """Accept only a dated A-share trading-session minute timestamp."""
    text = str(value or "").strip()
    matched = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})(?::\d{2})?$", text)
    if not matched:
        return False
    date_text, hour_text, minute_text = matched.groups()
    expected_date = _parse_gangtise_trade_date(trade_date)
    actual_date = _parse_gangtise_trade_date(date_text)
    if actual_date is None or (expected_date is not None and actual_date != expected_date):
        return False
    minutes = int(hour_text) * 60 + int(minute_text)
    return (9 * 60 + 30) <= minutes <= (11 * 60 + 30) or (13 * 60) <= minutes <= (15 * 60)


def _valid_gangtise_intraday_points(points, trade_date=""):
    rows = points if isinstance(points, list) else []
    return [
        item for item in rows
        if isinstance(item, dict)
        and numeric_value(item.get("value")) is not None
        and _is_valid_cn_stock_intraday_time(item.get("date"), trade_date=trade_date)
    ]


def normalize_gangtise_minute_points(response, trade_date=""):
    data = response.get("data") if isinstance(response, dict) else {}
    if not isinstance(data, dict):
        return []
    headers = data.get("headers") if isinstance(data.get("headers"), list) else data.get("fieldList") if isinstance(data.get("fieldList"), list) else []
    time_index = headers.index("tradeTime") if "tradeTime" in headers else -1
    close_index = headers.index("close") if "close" in headers else -1
    if time_index < 0 or close_index < 0:
        return []
    points = []
    for row in data.get("list", []) if isinstance(data, dict) else []:
        if not isinstance(row, list) or len(row) <= max(time_index, close_index):
            continue
        time_value = str(row[time_index] or "").strip()
        close_value = numeric_value(row[close_index])
        if not _is_valid_cn_stock_intraday_time(time_value, trade_date=trade_date) or close_value is None:
            continue
        points.append({"date": time_value, "value": round(close_value, 2)})
    # OpenAPI can return rows in reverse order; preserve a strictly chronological
    # minute sequence and never turn a daily date into an intraday point.
    unique = {item["date"]: item for item in points}
    return [unique[key] for key in sorted(unique)]


def normalize_gangtise_source_ohlc_rows(response):
    data = response.get("data") if isinstance(response, dict) else {}
    headers = data.get("fieldList") if isinstance(data, dict) and isinstance(data.get("fieldList"), list) else []
    required = ("tradeDate", "open", "high", "low", "close")
    if any(field not in headers for field in required):
        return []
    indexes = {field: headers.index(field) for field in required}
    rows = []
    for row in data.get("list", []) if isinstance(data, dict) else []:
        if not isinstance(row, list) or len(row) <= max(indexes.values()):
            continue
        values = {field: numeric_value(row[index]) for field, index in indexes.items() if field != "tradeDate"}
        if any(value is None for value in values.values()):
            continue
        rows.append({"time": row[indexes["tradeDate"]], **values})
    return rows


def normalize_gangtise_edb_points(response):
    data = response.get("data") if isinstance(response, dict) else {}
    if not isinstance(data, dict):
        return []
    rows = data.get("dataList") if isinstance(data.get("dataList"), list) else data.get("list")
    rows = rows if isinstance(rows, list) else []
    points = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        point_value = numeric_value(row[1])
        trade_date = str(row[0] or "").strip()
        if point_value is None or not trade_date:
            continue
        points.append({"date": trade_date, "open": point_value, "high": point_value, "low": point_value, "close": point_value})
    points.sort(key=lambda item: item["date"])
    return points


def is_gangtise_openapi_success(status, response):
    return (
        int(status or 0) == 200
        and isinstance(response, dict)
        and str(response.get("code") or "").strip() == GANGTISE_OPENAPI_SUCCESS_CODE
        and response.get("status") is True
    )


def build_gangtise_market_kline_payload(security_code, start_date, end_date, limit=300):
    return {
        "securityList": [str(security_code or "").strip().upper()],
        "startDate": str(start_date or "").strip(),
        "endDate": str(end_date or "").strip(),
        "limit": max(20, min(int(limit or 300), 500)),
        "fieldList": ["securityCode", "securityName", "tradeDate", "open", "high", "low", "close", "volume"],
    }


def resolve_gangtise_market_date_window(days=180):
    end_date = _current_cn_market_date()
    start_date = end_date - timedelta(days=max(7, int(days or 180)))
    return start_date.isoformat(), end_date.isoformat()


def fetch_gangtise_market_kline_series(path, security_code, token="", start_date="", end_date="", limit=300, timeout=20):
    effective_start, effective_end = (
        (str(start_date or "").strip(), str(end_date or "").strip())
        if start_date and end_date else
        resolve_gangtise_market_date_window(days=180)
    )
    effective_end = _clamp_gangtise_trade_end_date(effective_end).isoformat()
    payload = build_gangtise_market_kline_payload(
        security_code=security_code,
        start_date=effective_start,
        end_date=effective_end,
        limit=limit,
    )
    status, response, duration = post_gangtise_openapi_json(path, payload, token=token, timeout=timeout)
    points = normalize_gangtise_kline_points(response, max_trade_date=effective_end)
    response_obj = response if isinstance(response, dict) else {}
    response_code = str(response_obj.get("code") or "").strip()
    response_status = response_obj.get("status")
    message = str(response_obj.get("msg") or response_obj.get("message") or "").strip()
    if is_gangtise_openapi_success(status, response_obj) and len(points) >= 2:
        app.logger.info(
            "Gangtise daily kline ok path=%s security_code=%s http_status=%s response_code=%s response_status=%s points=%s duration_ms=%s latest_trade_date=%s",
            path,
            str(security_code or "").strip().upper(),
            int(status or 0),
            response_code or "--",
            response_status,
            len(points),
            int(duration or 0),
            str((points[-1] or {}).get("date") or "--"),
        )
    else:
        app.logger.warning(
            "Gangtise daily kline unavailable path=%s security_code=%s http_status=%s response_code=%s response_status=%s points=%s duration_ms=%s message=%s",
            path,
            str(security_code or "").strip().upper(),
            int(status or 0),
            response_code or "--",
            response_status,
            len(points),
            int(duration or 0),
            message[:240] or "--",
        )
    return {
        "ok": is_gangtise_openapi_success(status, response) and len(points) >= 2,
        "http_status": int(status or 0),
        "duration_ms": int(duration or 0),
        "path": path,
        "payload": payload,
        "points": points,
        "response": response if isinstance(response, dict) else {},
        "message": message,
    }


def build_gangtise_market_runtime_diagnostic(probe_security_code="600519.SH"):
    """Diagnose the deployed market connector without exposing credentials."""
    config = get_gangtise_openapi_config()
    has_access_key = bool(config.get("access_key"))
    has_secret_key = bool(config.get("secret_key"))
    has_long_token = bool(config.get("long_token"))
    if not (has_access_key and has_secret_key) and not has_long_token:
        try:
            credential_status = get_gangtise_openapi_credentials_status()
        except RuntimeError:
            # CLI/test callers may not have a Flask request context. The
            # runtime connector still has the same observable outcome: no
            # usable credentials were loaded.
            credential_status = {
                "database_status": "unknown",
                "record_present": False,
                "encryption_status": "unknown",
                "updated_at": "",
            }
        status_message = {
            "missing": "生产 PostgreSQL 中没有 Gangtise 凭证记录",
            "unreadable": "生产 PostgreSQL 中有凭证记录，但当前应用 SECRET_KEY 无法解密；需要恢复生产密钥或在生产 Admin 重新保存凭证",
            "database_unavailable": "生产应用当前无法读取 PostgreSQL",
            "malformed": "生产 PostgreSQL 中的 Gangtise 凭证记录格式损坏",
        }.get(str(credential_status.get("encryption_status") or ""), "生产应用没有可用的 Gangtise 凭证")
        return {
            "ok": False,
            "status": "credentials_missing",
            "message": f"{status_message}。请在生产 Admin 的“市场数据 > Gangtise 数据连接”中保存 Access Key + Secret Key，或保存 Long Token。",
            "base_url": config.get("base_url"),
            "credential_mode": credential_status.get("credential_mode") or "missing",
            "credential_storage": {
                "database_status": credential_status.get("database_status"),
                "record_present": credential_status.get("record_present"),
                "encryption_status": credential_status.get("encryption_status"),
                "token_storage": credential_status.get("token_storage"),
                "updated_at": credential_status.get("updated_at"),
            },
            "probe": {},
        }
    start_date, end_date = resolve_gangtise_market_date_window(days=14)
    result = fetch_gangtise_market_kline_series(
        "/application/open-quote/kline/daily",
        probe_security_code,
        start_date=start_date,
        end_date=end_date,
        limit=30,
        timeout=20,
    )
    message = str(result.get("message") or "").strip()
    response = result.get("response") if isinstance(result.get("response"), dict) else {}
    status_code = int(result.get("http_status") or 0)
    if result.get("ok"):
        status = "ready"
        diagnosis = "Gangtise 日K探针调用成功。"
    elif status_code == 0:
        status = "network_unavailable"
        diagnosis = "生产运行环境无法连接 Gangtise OpenAPI。请检查服务器 DNS、出网策略、防火墙和代理配置。"
    elif status_code in {401, 403} or "token" in message.lower() or "auth" in message.lower():
        status = "authentication_failed"
        diagnosis = "Gangtise 凭证无效或已失效。请在 Admin 的“市场数据 > Gangtise 数据连接”中核对并重新保存凭证。"
    else:
        status = "upstream_unavailable"
        diagnosis = "Gangtise 接口未返回可用日K数据。请根据 HTTP 状态和接口消息继续核对。"
    points = result.get("points") if isinstance(result.get("points"), list) else []
    return {
        "ok": bool(result.get("ok")),
        "status": status,
        "message": diagnosis,
        "base_url": config.get("base_url"),
        "credential_mode": "access_key_secret" if has_access_key and has_secret_key else "long_token",
        "probe": {
            "security_code": probe_security_code,
            "path": result.get("path"),
            "http_status": status_code,
            "duration_ms": int(result.get("duration_ms") or 0),
            "points": len(points),
            "latest_trade_date": str((points[-1] or {}).get("date") or "") if points else "",
            "upstream_message": message[:240],
        },
    }


def _load_gangtise_intraday_snapshot(security_code, trade_date):
    effective_date = str(trade_date or "").strip()
    if not effective_date:
        return None
    cache_key = f"{str(security_code or '').strip().upper()}:{effective_date}"
    cached = _load_watchlist_cache("watchlist_intraday_cache", cache_key, 15 * 60)
    if not isinstance(cached, dict):
        return None
    cached_points = cached.get("points") if isinstance(cached.get("points"), list) else []
    valid_points = _valid_gangtise_intraday_points(cached_points, trade_date=effective_date)
    if len(valid_points) < 2:
        return None
    return {
        "ok": True,
        "available": True,
        "points": copy.deepcopy(valid_points),
        "message": str(cached.get("message") or "cached").strip() or "cached",
        "updated_at": str(cached.get("updated_at") or "").strip(),
        "source": "gangtise_openapi_cache",
        "duration_ms": 0,
    }


def fetch_gangtise_intraday_series(security_code, token="", trade_date="", limit=600, timeout=30, force_refresh=False):
    effective_date = str(trade_date or _current_cn_market_date().isoformat()).strip()
    cache_key = f"{str(security_code or '').strip().upper()}:{effective_date}"
    if not force_refresh:
        cached = _load_gangtise_intraday_snapshot(security_code, effective_date)
        if cached:
            return cached
    payload = {
        "securityCode": str(security_code or "").strip().upper(),
        "startTime": f"{effective_date} 09:30:00",
        "endTime": f"{effective_date} 15:00:00",
        "Limit": max(60, min(int(limit or 600), 600)),
        "fieldList": ["securityCode", "securityName", "tradeTime", "open", "high", "low", "close", "volume"],
    }
    status, response, duration = post_gangtise_openapi_json(
        "/application/open-quote/kline/minute",
        payload,
        token=token,
        timeout=timeout,
    )
    points = normalize_gangtise_minute_points(response, trade_date=effective_date)
    message = str((response or {}).get("msg") or (response or {}).get("message") or "").strip()
    response_obj = response if isinstance(response, dict) else {}
    response_code = str(response_obj.get("code") or "").strip()
    response_status = response_obj.get("status")
    if len(points) >= 2:
        app.logger.info(
            "Gangtise minute kline ok security_code=%s trade_date=%s http_status=%s response_code=%s response_status=%s points=%s duration_ms=%s",
            str(security_code or "").strip().upper(),
            effective_date,
            int(status or 0),
            response_code or "--",
            response_status,
            len(points),
            int(duration or 0),
        )
    else:
        app.logger.warning(
            "Gangtise minute kline unavailable security_code=%s trade_date=%s http_status=%s response_code=%s response_status=%s points=%s duration_ms=%s message=%s",
            str(security_code or "").strip().upper(),
            effective_date,
            int(status or 0),
            response_code or "--",
            response_status,
            len(points),
            int(duration or 0),
            message[:240] or "--",
        )
    result = {
        "ok": is_gangtise_openapi_success(status, response) and len(points) >= 2,
        "available": len(points) >= 2,
        "points": points[-240:],
        "message": message or ("ok" if len(points) >= 2 else "empty_intraday_series"),
        "updated_at": now_ts(),
        "source": "gangtise_openapi",
        "duration_ms": int(duration or 0),
    }
    if result["available"]:
        _save_watchlist_cache("watchlist_intraday_cache", cache_key, result)
    return result


def fetch_gangtise_indicator_series(indicator_code, start_date="", end_date="", token=""):
    entry = GANGTISE_INDICATOR_REGISTRY.get(slugify_code(indicator_code, "indicator"))
    if not entry:
        return {"ok": False, "message": "indicator_registry_not_found", "points": [], "response": {}, "duration_ms": 0, "source_meta": {}}
    effective_end = str(end_date or datetime.now().strftime("%Y-%m-%d")).strip()
    effective_start = str(start_date or (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")).strip()
    query_kind = str(entry.get("query_kind") or "").strip()
    if query_kind == "index_kline":
        payload = build_gangtise_market_kline_payload(
            security_code=entry["security_code"],
            start_date=effective_start,
            end_date=effective_end,
            limit=240,
        )
        status, response, duration = post_gangtise_openapi_json(
            "/application/open-quote/kline/daily",
            payload,
            token=token,
            timeout=30,
        )
        # Apply the same future-date guard used by stock K-lines. The API test
        # report is historical, but an upstream placeholder must never become
        # tomorrow's market value in the dashboard.
        points = normalize_gangtise_kline_points(response, max_trade_date=effective_end)
        close_points = normalize_gangtise_source_line_points(response)
        if not points:
            points = [
                {"date": str(item[0]).strip(), "open": item[1], "high": item[1], "low": item[1], "close": item[1]}
                for item in close_points
                if isinstance(item, list) and len(item) >= 2 and str(item[0]).strip()
            ]
        return {
            "ok": bool(is_gangtise_openapi_success(status, response) and len(points) >= 2),
            "message": (
                str((response or {}).get("msg") or (response or {}).get("message") or "").strip()
                if isinstance(response, dict) else
                ""
            ),
            "points": points,
            "response": response if isinstance(response, dict) else {},
            "duration_ms": int(duration or 0),
            "source_meta": {"type": "index_kline", "path": "/application/open-quote/kline/daily", "securityCode": entry["security_code"]},
        }
    search_payload = {"keyword": entry.get("search_keyword") or entry.get("indicator_name") or indicator_code, "Limit": 20}
    search_status, search_response, search_duration = post_gangtise_openapi_json("/application/open-alternative/EDB/search", search_payload, token=token, timeout=30)
    selected = choose_gangtise_indicator_candidate(
        search_response.get("data") or [],
        keyword=entry.get("search_keyword") or entry.get("indicator_name") or indicator_code,
        preferred_indicator_id=entry.get("preferred_indicator_id") or "",
    )
    search_keyword = str(entry.get("search_keyword") or entry.get("indicator_name") or indicator_code).strip().lower()
    selected_name = str((selected or {}).get("indicatorName") or "").strip().lower()
    preferred_id = str(entry.get("preferred_indicator_id") or "").strip()
    if selected and not preferred_id and search_keyword and search_keyword not in selected_name:
        selected = None
    if not is_gangtise_openapi_success(search_status, search_response) or not selected:
        return {
            "ok": False,
            "message": search_response.get("msg") or search_response.get("message") or "Gangtise EDB 未找到匹配指标",
            "points": [],
            "response": search_response,
            "duration_ms": search_duration,
            "source_meta": {"type": "edb_search", "keyword": search_payload["keyword"]},
        }
    expected_name = str(entry.get("expected_indicator_name") or "").strip()
    expected_source = str(entry.get("expected_data_source") or "").strip()
    actual_name = str(selected.get("indicatorName") or "").strip()
    actual_source = str(selected.get("dataSource") or "").strip()
    if (expected_name and actual_name != expected_name) or (expected_source and actual_source != expected_source):
        return {
            "ok": False,
            "message": f"Gangtise 指标主数据校验失败：期望 {expected_name or '指定指标'} / {expected_source or '指定数据源'}，实际 {actual_name or '--'} / {actual_source or '--'}",
            "points": [],
            "response": search_response,
            "duration_ms": search_duration,
            "source_meta": {
                "type": "edb_search",
                "indicatorId": selected.get("indicatorId") or "",
                "indicatorName": actual_name,
                "dataSource": actual_source,
            },
        }
    data_payload = {"indicatorIdList": [selected["indicatorId"]], "startDate": effective_start, "endDate": effective_end}
    status, response, duration = post_gangtise_openapi_json("/application/open-alternative/EDB/getData", data_payload, token=token, timeout=30)
    points = normalize_gangtise_edb_points(response)
    value_range = entry.get("valid_value_range")
    if isinstance(value_range, (list, tuple)) and len(value_range) == 2 and points:
        lower, upper = numeric_value(value_range[0]), numeric_value(value_range[1])
        latest_value = numeric_value(points[-1].get("close"))
        if lower is not None and upper is not None and latest_value is not None and not lower <= latest_value <= upper:
            return {
                "ok": False,
                "message": f"Gangtise 指标数值校验失败：{actual_name or indicator_code} 最新值 {latest_value} 不在允许区间 {lower} ~ {upper}",
                "points": [],
                "response": response,
                "duration_ms": search_duration + duration,
                "source_meta": {
                    "type": "edb",
                    "indicatorId": selected.get("indicatorId") or "",
                    "indicatorName": actual_name,
                    "dataSource": actual_source,
                },
            }
    return {
        "ok": is_gangtise_openapi_success(status, response) and len(points) >= 2,
        "message": response.get("msg") or response.get("message") or "",
        "points": points,
        "response": response,
        "duration_ms": search_duration + duration,
        "source_meta": {
            "type": "edb",
            "path": "/application/open-alternative/EDB/getData",
            "indicatorId": selected.get("indicatorId") or "",
            "indicatorName": selected.get("indicatorName") or "",
            "unit": selected.get("unit") or "",
        },
    }
def build_gangtise_raw_payload(indicator_code, series_result):
    points = series_result.get("points") if isinstance(series_result, dict) else []
    entry = GANGTISE_INDICATOR_REGISTRY.get(slugify_code(indicator_code, "indicator")) or {}
    if not points:
        return {}
    latest = points[-1]
    prev_close = numeric_value(points[-2]["close"]) if len(points) > 1 else numeric_value(latest.get("close"))
    latest_close = numeric_value(latest.get("close"))
    latest_status = build_real_indicator_status(latest_close, prev_close)
    source_meta = series_result.get("source_meta") if isinstance(series_result.get("source_meta"), dict) else {}
    raw_preview = json.dumps(
        {
            "source_meta": source_meta,
            "latest": latest,
            "points": [{"date": item["date"], "close": item["close"]} for item in points[-5:]],
        },
        ensure_ascii=False,
    )
    return {
        "indicator": entry.get("indicator_name") or indicator_code,
        "provider": "Gangtise OpenAPI",
        "connector_type": "gangtise_openapi",
        "extractor_type": str(entry.get("query_kind") or "gangtise_openapi"),
        "status": latest_status,
        "timestamp": f"{str(latest.get('date') or '')[:10]} 00:00:00",
        "value": latest_close,
        "open": numeric_value(latest.get("open")),
        "high": numeric_value(latest.get("high")),
        "low": numeric_value(latest.get("low")),
        "close": latest_close,
        "raw_preview": raw_preview[:1200],
        "record_summary": str(series_result.get("message") or "Gangtise OpenAPI 已返回时间序列")[:240],
        "source_meta": source_meta,
    }


def build_gangtise_source_seed_payload(indicator_code, existing=None):
    entry = GANGTISE_INDICATOR_REGISTRY.get(slugify_code(indicator_code, "indicator")) or {}
    existing = existing or {}
    query_kind = str(entry.get("query_kind") or "edb_search").strip()
    path = "/application/open-quote/kline/daily" if query_kind == "index_kline" else "/application/open-alternative/EDB/getData"
    search_keyword = str(entry.get("search_keyword") or entry.get("indicator_name") or indicator_code).strip()
    preferred_indicator_id = str(entry.get("preferred_indicator_id") or "").strip()
    response_sample = existing.get("response_sample") if isinstance(existing.get("response_sample"), dict) and existing.get("response_sample") else {
        "indicator": entry.get("indicator_name") or indicator_code,
        "provider": "Gangtise OpenAPI",
        "connector_type": "gangtise_openapi",
        "extractor_type": query_kind,
        "status": "unavailable",
        "timestamp": now_ts(),
        "value": None,
        "raw_preview": "",
        "source_meta": {"query_kind": query_kind, "search_keyword": search_keyword, "preferred_indicator_id": preferred_indicator_id},
        "record_summary": "Gangtise API 源已配置；如未同步到真实值，会明确显示未取到，不使用模拟值。",
    }
    response_mapping = {
        "value_path": "value",
        "time_path": "timestamp",
        "status_path": "status",
        "connector_type": "gangtise_openapi",
        "extractor_type": query_kind,
        "request_blueprint": {
            "path": path,
            "search_keyword": search_keyword,
            "security_code": entry.get("security_code") or "",
            "preferred_indicator_id": preferred_indicator_id,
        },
    }
    return {
        "source_code": slugify_code(indicator_code, "source"),
        "indicator_code": slugify_code(indicator_code, "indicator"),
        "provider": "Gangtise OpenAPI",
        "base_url": get_gangtise_openapi_config()["base_url"],
        "path": path,
        "method": "POST",
        "auth_type": "gangtise_openapi",
        "headers": {},
        "query": {},
        "body": {},
        "response_mapping": response_mapping,
        "response_sample": response_sample,
        "source_status": "configured",
        "enabled": bool(existing.get("enabled", True)),
        "last_test_status": str(existing.get("last_test_status") or "").strip(),
        "last_http_status": existing.get("last_http_status"),
        "last_tested_at": str(existing.get("last_tested_at") or "").strip(),
        "last_test_detail": str(existing.get("last_test_detail") or "Gangtise OpenAPI 数据源").strip(),
    }



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
        sample["record_summary"] = detail or f"{indicator_name} 历史数据样例"
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
    if connector_type == "gangtise_openapi":
        series_result = fetch_gangtise_indicator_series(source["indicator_code"])
        raw_payload = build_gangtise_raw_payload(source["indicator_code"], series_result)
        success = bool(series_result.get("ok")) and bool(raw_payload)
        if not raw_payload:
            raw_payload = {
                "indicator": source.get("indicator_code") or source.get("source_code") or "指标",
                "provider": "Gangtise OpenAPI",
                "connector_type": "gangtise_openapi",
                "extractor_type": str((source.get("response_mapping") or {}).get("extractor_type") or "gangtise_openapi"),
                "status": "unavailable",
                "timestamp": now_ts(),
                "value": None,
                "record_summary": str(series_result.get("message") or "Gangtise OpenAPI 当前未返回有效时间序列，未使用模拟值。")[:240],
                "source_meta": series_result.get("source_meta") if isinstance(series_result.get("source_meta"), dict) else {},
            }
        fetch_mode = "gangtise_openapi_live" if success else "gangtise_openapi_unavailable"
        summary = series_result.get("message") or ("Gangtise OpenAPI 实时接入成功。" if success else "Gangtise OpenAPI 当前未返回有效时间序列，未使用模拟值。")
        record = persist_indicator_raw_record(
            source,
            raw_payload,
            fetch_mode=fetch_mode,
            http_status=200 if success else None,
            success=success,
            summary=summary,
        )
        return {
            "record": record,
            "connector_type": connector_type,
            "fetch_mode": fetch_mode,
            "detail": summary,
            "used_sample": not success,
        }
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
        sample_payload.setdefault("record_summary", str(source.get("last_test_detail") or "历史数据蓝图样例"))
        fetch_mode = "akshare_blueprint"
        summary = "历史数据 Source 当前按蓝图样例入湖，后续接真实执行器。"
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


def parse_numeric_indicator_value(raw_value):
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
        value = float(raw_value)
        return value if math.isfinite(value) else None
    text = str(raw_value or "").strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        value = float(match.group(0))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def normalize_selected_indicator_refs(raw_selected):
    items = raw_selected if isinstance(raw_selected, list) else []
    normalized = []
    seen = set()
    for raw in items:
        if isinstance(raw, dict):
            indicator_code = slugify_code(raw.get("indicator_code") or raw.get("code"), "indicator")
            indicator_name = str(raw.get("indicator_name") or raw.get("name") or indicator_code).strip() or indicator_code
        else:
            indicator_code = slugify_code(raw, "indicator")
            indicator_name = indicator_code
        if not indicator_code or indicator_code in seen:
            continue
        seen.add(indicator_code)
        normalized.append({"indicator_code": indicator_code, "indicator_name": indicator_name})
    return normalized


def extract_json_payload_from_text(raw_text):
    text = str(raw_text or "").strip()
    if not text:
        return {}
    fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced_match:
        text = fenced_match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_smart_indicator_expression_fallback(prompt_text, selected_indicators):
    prompt = str(prompt_text or "").strip()
    items = normalize_selected_indicator_refs(selected_indicators)
    if not items:
        raise ValueError("selected_indicators_required")
    expression = prompt.replace("（", "(").replace("）", ")").replace("【", "[[").replace("】", "]]")
    expression = expression.replace("×", "*").replace("÷", "/")
    replaced = False
    for item in sorted(items, key=lambda current: len(current["indicator_name"]), reverse=True):
        code = item["indicator_code"]
        name = item["indicator_name"]
        token = f'Number(inputs["{code}"] || 0)'
        bracket_token = f"[[{name}]]"
        if bracket_token in expression:
            expression = expression.replace(bracket_token, token)
            replaced = True
        plain_pattern = re.compile(re.escape(name))
        if plain_pattern.search(expression):
            expression = plain_pattern.sub(token, expression)
            replaced = True
    if not replaced:
        first_token = f'Number(inputs["{items[0]["indicator_code"]}"] || 0)'
        if re.match(r"^[\+\-\*\/]", expression):
            expression = f"{first_token}{expression}"
        elif len(items) == 1:
            expression = first_token
        elif "/" in expression:
            second_token = f'Number(inputs["{items[1]["indicator_code"]}"] || 0)'
            expression = f"{first_token} / ({second_token} + 0.000001)"
        else:
            second_token = f'Number(inputs["{items[1]["indicator_code"]}"] || 0)'
            expression = f"{first_token} + {second_token}"
    expression = expression.strip()
    if not expression:
        raise ValueError("smart_indicator_expression_empty")
    if re.search(r"[^0-9A-Za-z_\.\+\-\*\/\(\)\[\]\"'\s|]", expression):
        raise ValueError("smart_indicator_expression_unsafe")
    return expression


def build_smart_indicator_js_fallback(prompt_text, selected_indicators):
    return f"return {build_smart_indicator_expression_fallback(prompt_text, selected_indicators)};"


def validate_smart_indicator_js(js_code, selected_indicators):
    code = str(js_code or "").strip()
    if not code:
        return ""
    if not code.startswith("return "):
        code = f"return {code.lstrip(';')}"
    if not code.endswith(";"):
        code = f"{code};"
    normalized = code.replace("\n", " ").strip()
    allowed_codes = {item["indicator_code"] for item in normalize_selected_indicator_refs(selected_indicators)}
    for token in re.findall(r'inputs\[(?:"|\')([^"\']+)(?:"|\')\]', normalized):
        if slugify_code(token, "indicator") not in allowed_codes:
            raise ValueError("smart_indicator_js_contains_unknown_indicator")
    if re.search(r"[^0-9A-Za-z_\.\+\-\*\/\(\)\[\]\"'\s|;]", normalized):
        raise ValueError("smart_indicator_js_unsafe")
    return normalized


def generate_smart_indicator_js(indicator_name, prompt_text, selected_indicators, tenant_slug=""):
    normalized_selected = normalize_selected_indicator_refs(selected_indicators)
    fallback_js = build_smart_indicator_js_fallback(prompt_text, normalized_selected)
    # A single source with a direct-name prompt is a projection, not an LLM
    # formula. Compile it locally so saving a renamed prompt cannot wait on an
    # external model service or produce a different formula for the same value.
    prompt_key = re.sub(r"[\s【】\[\]（）()：:，,]", "", str(prompt_text or "").strip()).lower()
    source_key = re.sub(
        r"[\s【】\[\]（）()：:，,]",
        "",
        str((normalized_selected[0] if len(normalized_selected) == 1 else {}).get("indicator_name") or "").strip(),
    ).lower()
    direct_aliases = {"cpi", "中国cpi", "中国居民消费价格指数"}
    if len(normalized_selected) == 1 and prompt_key and (prompt_key == source_key or prompt_key in direct_aliases):
        return {"formula_js": fallback_js, "generator": "direct_projection", "llm_used": False}
    model = get_default_llm_config(purpose="general", feature_code="smart_indicator_formula_generation")
    if not model:
        return {"formula_js": fallback_js, "generator": "fallback", "llm_used": False}
    try:
        raw = call_openai_compatible_llm(
            model,
            (
                "你是金融指标公式编译器。"
                "只返回 JSON。字段必须包含 formula_js。"
                "formula_js 必须是单行 JavaScript return 语句，只能使用 Number(inputs[\"indicator_code\"] || 0) 和 + - * / ()。"
            ),
            json.dumps(
                {
                    "indicator_name": indicator_name,
                    "tenant_slug": tenant_slug,
                    "prompt_text": str(prompt_text or "").strip(),
                    "selected_indicators": normalized_selected,
                    "fallback_formula_js": fallback_js,
                },
                ensure_ascii=False,
            ),
            feature_code="smart_indicator_formula_generation",
            feature_label="智能指标公式生成",
            tenant_slug=tenant_slug,
            entry_point="dashboard_smart_indicator",
            metadata={"indicator_name": indicator_name, "selected_indicator_count": len(normalized_selected)},
            request_timeout_seconds=45,
        )
        parsed = extract_json_payload_from_text(raw)
        formula_js = validate_smart_indicator_js(parsed.get("formula_js"), normalized_selected)
        if not formula_js:
            raise ValueError("llm_formula_js_missing")
        return {"formula_js": formula_js, "generator": "llm", "llm_used": True}
    except Exception:
        return {"formula_js": fallback_js, "generator": "fallback", "llm_used": False}


def evaluate_smart_indicator_formula_js(formula_js, selected_indicators, latest_value_map):
    code = validate_smart_indicator_js(formula_js, selected_indicators)
    expression = re.sub(r"^\s*return\s+", "", code).rstrip(" ;")
    for item in normalize_selected_indicator_refs(selected_indicators):
        indicator_code = item["indicator_code"]
        latest = latest_value_map.get(indicator_code) or {}
        numeric_value = parse_numeric_indicator_value(latest.get("latest_value"))
        numeric_text = str(0.0 if numeric_value is None else numeric_value)
        expression = expression.replace(f'Number(inputs["{indicator_code}"] || 0)', numeric_text)
        expression = expression.replace(f"inputs[\"{indicator_code}\"]", numeric_text)
        expression = expression.replace(f"inputs['{indicator_code}']", numeric_text)
    expression = expression.replace("|| 0", "").replace("||0", "")
    if re.search(r"[^0-9\.\+\-\*\/\(\)\s]", expression):
        raise ValueError("smart_indicator_expression_eval_unsafe")
    result = eval(expression, {"__builtins__": {}}, {})
    value = float(result)
    if not math.isfinite(value):
        raise ValueError("smart_indicator_expression_not_finite")
    return round(value, 4)


def normalize_indicator_definition(payload, existing=None):
    base = dict(existing or {})
    base.update(payload or {})
    tenant_slug = str(base.get("tenant_slug") or "").strip().lower()
    source_type = str(base.get("source_type") or "mock").strip() or "mock"
    code_seed = base.get("indicator_code") or base.get("indicator_name")
    if tenant_slug and source_type == "smart" and not base.get("indicator_code"):
        code_seed = f"{tenant_slug}_{code_seed or 'smart_indicator'}"
    code = slugify_code(code_seed, "indicator")
    selected_indicators = normalize_selected_indicator_refs(
        base.get("selected_indicators")
        if isinstance(base.get("selected_indicators"), list)
        else safe_json_loads(base.get("selected_indicators_json"), [])
    )
    return {
        "indicator_code": code,
        "tenant_slug": tenant_slug,
        "indicator_name": str(base.get("indicator_name") or code).strip(),
        "category": str(base.get("category") or "未分类指标").strip(),
        "description": str(base.get("description") or "").strip(),
        "unit": str(base.get("unit") or "").strip(),
        "owner": str(base.get("owner") or "平台研究运营").strip(),
        "source_type": source_type,
        "source_type_label": str(base.get("source_type_label") or "指标").strip() or "指标",
        "provider": str(base.get("provider") or "平台数据层").strip(),
        "status_hint": str(base.get("status_hint") or "attention").strip() or "attention",
        "assessment_template": str(base.get("assessment_template") or "").strip(),
        "alert_template": str(base.get("alert_template") or "").strip(),
        "prompt_text": str(base.get("prompt_text") or "").strip(),
        "formula_js": str(base.get("formula_js") or "").strip(),
        "selected_indicators_json": json.dumps(selected_indicators, ensure_ascii=False),
        "display_order": int(base.get("display_order") or 0),
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
    item["selected_indicators"] = normalize_selected_indicator_refs(safe_json_loads(item.get("selected_indicators_json"), []))
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


def list_indicator_definitions(source_type=None, tenant_slug=None, include_shared=True):
    db = get_db()
    query = "SELECT * FROM indicator_definitions"
    params = []
    filters = []
    if source_type:
        filters.append("source_type = ?")
        params.append(source_type)
    normalized_tenant_slug = str(tenant_slug or "").strip().lower()
    if normalized_tenant_slug:
        if include_shared:
            filters.append("(tenant_slug = ? OR tenant_slug = '')")
        else:
            filters.append("tenant_slug = ?")
        params.append(normalized_tenant_slug)
    if filters:
        query += " WHERE " + " AND ".join(filters)
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
            indicator_code, indicator_name, tenant_slug, category, description, unit, owner, source_type,
            source_type_label, provider, status_hint, assessment_template, alert_template, prompt_text,
            formula_js, selected_indicators_json, display_order, watchers_json, display_config_json,
            enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(indicator_code) DO UPDATE SET
            indicator_name = excluded.indicator_name,
            tenant_slug = excluded.tenant_slug,
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
            prompt_text = excluded.prompt_text,
            formula_js = excluded.formula_js,
            selected_indicators_json = excluded.selected_indicators_json,
            display_order = excluded.display_order,
            watchers_json = excluded.watchers_json,
            display_config_json = excluded.display_config_json,
            enabled = excluded.enabled,
            updated_at = excluded.updated_at
        """,
        (
            normalized["indicator_code"],
            normalized["indicator_name"],
            normalized["tenant_slug"],
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
            normalized["prompt_text"],
            normalized["formula_js"],
            normalized["selected_indicators_json"],
            normalized["display_order"],
            normalized["watchers_json"],
            normalized["display_config_json"],
            normalized["enabled"],
            existing["created_at"] if existing else timestamp,
            timestamp,
        ),
    )
    db.commit()
    invalidate_indicator_hub_cache()
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
    invalidate_indicator_hub_cache()


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
    invalidate_indicator_hub_cache()
    saved = get_indicator_source_def(normalized["source_code"])
    ensure_indicator_mapping_rule_for_source(saved)
    return saved


def delete_indicator_source_def(source_code):
    db = get_db()
    normalized_code = slugify_code(source_code, "source")
    db.execute("DELETE FROM indicator_source_defs WHERE source_code = ?", (normalized_code,))
    db.execute("DELETE FROM indicator_source_tests WHERE source_code = ?", (normalized_code,))
    db.commit()
    invalidate_indicator_hub_cache()


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
    invalidate_indicator_hub_cache()


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
    connector_type = infer_source_connector_type(source)
    if connector_type == "gangtise_openapi":
        series_result = fetch_gangtise_indicator_series(source["indicator_code"])
        latency_ms = int((time.time() - start) * 1000)
        sample_payload = build_gangtise_raw_payload(source["indicator_code"], series_result)
        success = bool(series_result.get("ok")) and bool(sample_payload)
        http_status = 200 if success else None
        response_text = json.dumps(sample_payload or series_result.get("response") or {}, ensure_ascii=False)
        error_text = "" if success else (series_result.get("message") or "Gangtise OpenAPI 未返回有效时间序列")
        record_indicator_source_test(source["source_code"], success, http_status, latency_ms, response_text if success else "", error_text)
        return {
            "success": success,
            "http_status": http_status,
            "latency_ms": latency_ms,
            "response_sample": sample_payload or {},
            "detail": "Gangtise OpenAPI 接口测试成功。" if success else error_text,
        }
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
    invalidate_indicator_hub_cache()
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
    invalidate_indicator_hub_cache()


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
    invalidate_indicator_hub_cache()
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
    for indicator_code, entry in GANGTISE_INDICATOR_REGISTRY.items():
        indicator_name = str(entry.get("indicator_name") or indicator_code).strip()
        if not get_indicator_definition(indicator_code):
            save_indicator_definition(
                {
                    "indicator_code": indicator_code,
                    "indicator_name": indicator_name,
                    "category": str(entry.get("category") or "数据湖指标").strip(),
                    "description": "用于市场与平台统一分析的 Gangtise OpenAPI 指标源。",
                    "unit": "",
                    "owner": "Gangtise OpenAPI 指标层",
                    "source_type": "lake",
                    "source_type_label": "数据湖指标",
                    "provider": "Gangtise OpenAPI",
                    "status_hint": "attention",
                    "assessment_template": f"{indicator_name} 已接入平台统一指标层，可用于 Dashboard、Hermes 和工作台分析。",
                    "alert_template": "需关注数据源刷新与连通状态",
                    "watchers": ["Gangtise OpenAPI", "Admin 指标专区", "大V 工作台"],
                    "display_config": {"show_in_admin": True, "show_in_h5": False},
                    "enabled": True,
                }
            )
        source_code = slugify_code(indicator_code, "source")
        existing_source = get_indicator_source_def(source_code)
        if source_code in existing and existing_source:
            seed_payload = build_gangtise_source_seed_payload(indicator_code, existing=existing_source)
            seed_payload["source_code"] = existing_source["source_code"]
            save_indicator_source_def(seed_payload)
            ensure_indicator_mapping_rule_for_source(get_indicator_source_def(source_code))
            continue
        save_indicator_source_def(build_gangtise_source_seed_payload(indicator_code))
        existing.add(source_code)
        ensure_indicator_mapping_rule_for_source(get_indicator_source_def(source_code))
        imported += 1
    for source in list_indicator_source_defs():
        ensure_indicator_mapping_rule_for_source(source)
    return imported


def invalidate_indicator_hub_cache():
    _indicator_hub_cache["expires_at"] = 0.0
    _indicator_hub_cache["value"] = None


def prepare_indicator_hub_store(force=False):
    imported = ensure_default_indicator_sources()
    purged_simulated = purge_simulated_indicator_store()
    real_sync = sync_real_indicator_history_from_market_cache(force=force)
    derived_sync = sync_derived_smart_indicator_history(force=force)
    invalidate_indicator_hub_cache()
    return {
        "imported_sources": imported,
        "purged_simulated": purged_simulated,
        "real_sync": real_sync,
        "derived_sync": derived_sync,
    }


DEFAULT_ADMIN_TASKS = [
    {
        "task_code": "indicator_prepare",
        "task_name": "指标中心预处理",
        "task_group": "indicator",
        "task_type": "prepare_indicator_hub",
        "description": "补齐指标源定义、清理模拟残留，并同步真实历史与真实因子推导结果。",
        "schedule_type": "interval",
        "schedule_value": "1800",
        "enabled": 1,
        "timeout_seconds": 900,
    },
    {
        "task_code": "indicator_gangtise_openapi_sync",
        "task_name": "Gangtise 指标同步",
        "task_group": "indicator",
        "task_type": "sync_real_indicator_history",
        "description": "从 Gangtise OpenAPI 同步真实因子历史到指标湖。",
        "schedule_type": "interval",
        "schedule_value": "3600",
        "enabled": 1,
        "timeout_seconds": 600,
    },
    {
        "task_code": "market_snapshot_sync",
        "task_name": "市场与热门行业快照同步",
        "task_group": "indicator",
        "task_type": "sync_market_snapshot",
        "description": "人工从 Gangtise OpenAPI 采集标准指数与申万一级行业日K，写入 PostgreSQL 快照供 H5 展示；前台不直接访问外部行情源。发布后确认数据稳定，再切换为定时执行。",
        "schedule_type": "manual",
        "schedule_value": "",
        "enabled": 1,
        "timeout_seconds": 900,
    },
    {
        "task_code": "indicator_raw_landing",
        "task_name": "指标原始数据落地",
        "task_group": "indicator",
        "task_type": "indicator_source_landing",
        "description": "按 source 配置把样例或实时响应落到原始记录区。",
        "schedule_type": "manual",
        "schedule_value": "",
        "enabled": 0,
        "timeout_seconds": 600,
    },
    {
        "task_code": "indicator_clean_pipeline",
        "task_name": "指标清洗入湖",
        "task_group": "indicator",
        "task_type": "indicator_clean_pipeline",
        "description": "把原始记录按映射规则标准化并写入指标湖。",
        "schedule_type": "manual",
        "schedule_value": "",
        "enabled": 0,
        "timeout_seconds": 600,
    },
    {
        "task_code": "knowledge_sync_manual",
        "task_name": "知识库同步入向量",
        "task_group": "knowledge",
        "task_type": "knowledge_manual_sync",
        "description": "把文本知识同步到租户知识库和向量库，支持批量补录。",
        "schedule_type": "manual",
        "schedule_value": "",
        "enabled": 0,
        "timeout_seconds": 1200,
    },
    {
        "task_code": "review_publish_embed",
        "task_name": "纪要文本向量补录",
        "task_group": "knowledge",
        "task_type": "review_publish_embed",
        "description": "把已有文本纪要补录到向量库，用于搜索和知识召回。",
        "schedule_type": "manual",
        "schedule_value": "",
        "enabled": 0,
        "timeout_seconds": 1200,
    },
    {
        "task_code": "knowledge_query_batch",
        "task_name": "知识检索批处理",
        "task_group": "knowledge",
        "task_type": "knowledge_query_batch",
        "description": "按任务参数批量执行知识检索与可选的大模型回答，用于验证召回效果。",
        "schedule_type": "manual",
        "schedule_value": "",
        "enabled": 0,
        "timeout_seconds": 1200,
    },
]


def normalize_admin_task_config(payload, existing=None):
    base = dict(existing or {})
    base.update(payload or {})
    task_code = slugify_code(base.get("task_code"), "task")
    schedule_type = str(base.get("schedule_type") or "manual").strip().lower()
    if schedule_type not in {"manual", "interval"}:
        schedule_type = "manual"
    schedule_value = str(base.get("schedule_value") or "").strip()
    try:
        timeout_seconds = int(base.get("timeout_seconds") or 600)
    except Exception:
        timeout_seconds = 600
    timeout_seconds = max(30, timeout_seconds)
    return {
        "task_code": task_code,
        "task_name": str(base.get("task_name") or task_code).strip() or task_code,
        "task_group": str(base.get("task_group") or "system").strip() or "system",
        "task_type": str(base.get("task_type") or "manual").strip() or "manual",
        "description": str(base.get("description") or "").strip(),
        "task_params_json": json.dumps(base.get("task_params") if isinstance(base.get("task_params"), dict) else (safe_json_loads(base.get("task_params_json"), {}) if base.get("task_params_json") else {}), ensure_ascii=False),
        "schedule_type": schedule_type,
        "schedule_value": schedule_value,
        "enabled": 1 if bool(base.get("enabled", True)) else 0,
        "timeout_seconds": timeout_seconds,
    }


def parse_task_interval_seconds(task):
    if not isinstance(task, dict):
        return None
    if str(task.get("schedule_type") or "").strip().lower() != "interval":
        return None
    try:
        seconds = int(str(task.get("schedule_value") or "0").strip() or "0")
    except Exception:
        return None
    return seconds if seconds > 0 else None


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


def build_empty_kline_payload():
    return {
        "candles": [],
        "ma5": [],
        "ma10": [],
        "ma20": [],
        "anomalies": [],
    }


def build_gangtise_unavailable_indicator_item(indicator_code, registry_entry=None, definition=None, sources=None, latest=None, reason=""):
    entry = registry_entry or {}
    definition = definition or {}
    sources = list(sources or [])
    latest = latest or {}
    primary_source = sources[0] if sources else None
    indicator_name = str(
        definition.get("indicator_name")
        or entry.get("indicator_name")
        or indicator_code
    ).strip() or indicator_code
    unavailable_reason = str(reason or "Gangtise API 当前未返回有效数据，未使用模拟值。").strip()
    return {
        "id": indicator_code,
        "name": indicator_name,
        "tenant_slug": str(definition.get("tenant_slug") or "").strip().lower(),
        "category": definition.get("category") or entry.get("category") or "数据湖指标",
        "unit": definition.get("unit") or "",
        "description": definition.get("description") or "",
        "owner": definition.get("owner") or "平台数据层",
        "value": "--",
        "numeric_value": None,
        "assessment": unavailable_reason,
        "status": "unavailable",
        "alert": unavailable_reason,
        "enabled": bool(definition.get("enabled", True)),
        "last_updated": latest.get("updated_at") or definition.get("updated_at") or "未同步",
        "watchers": definition.get("watchers", []),
        "prompt_text": str(definition.get("prompt_text") or "").strip(),
        "formula_js": str(definition.get("formula_js") or "").strip(),
        "selected_indicators": normalize_selected_indicator_refs(definition.get("selected_indicators")),
        "display_order": int(definition.get("display_order") or 0),
        "history": [],
        "history_series": [],
        "history_anomalies": [],
        "history_kline": build_empty_kline_payload(),
        "source_type": definition.get("source_type") or "indicator",
        "source_type_label": definition.get("source_type_label") or "指标",
        "provider": "Gangtise OpenAPI",
        "source_count": len(sources),
        "source_defs": sources,
        "latest_source_test": primary_source and {
            "status": primary_source.get("last_test_status") or "",
            "detail": primary_source.get("last_test_detail") or "",
            "tested_at": primary_source.get("last_tested_at") or "",
        } or None,
        "data_mode": "unavailable",
        "data_mode_label": "Gangtise 未取到",
        "data_source": "gangtise_openapi",
        "data_unavailable": True,
    }


def build_live_gangtise_indicator_detail(indicator_code, start_date="", end_date=""):
    normalized_code = slugify_code(indicator_code, "indicator")
    registry_entry = GANGTISE_INDICATOR_REGISTRY.get(normalized_code)
    if not registry_entry:
        return None
    if normalized_code in MARKET_OVERVIEW_INDEX_CODES:
        detail = build_market_overview_index_detail(normalized_code)
        if detail:
            return detail
        return {
            "id": normalized_code,
            "name": registry_entry.get("indicator_name") or normalized_code,
            "provider": "Gangtise OpenAPI",
            "data_source": "gangtise_openapi",
            "data_mode": "unavailable",
            "data_mode_label": "Gangtise 未取到",
            "data_unavailable": True,
            "history_series": [],
            "history_kline": build_empty_kline_payload(),
            "source_defs": [],
            "source_count": 0,
            "value": "--",
            "numeric_value": None,
            "assessment": "后台尚未同步 Gangtise 标准指数快照。",
            "alert": "请等待后台同步任务完成。",
        }
    definition = {}
    try:
        for item in list_indicator_definitions():
            if str(item.get("indicator_code") or "").strip() == normalized_code:
                definition = dict(item)
                break
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        definition = {}
    result = fetch_gangtise_indicator_series(normalized_code, start_date=start_date, end_date=end_date)
    if not result.get("ok"):
        return build_gangtise_unavailable_indicator_item(
            normalized_code,
            registry_entry=registry_entry,
            definition=definition,
            sources=[],
            latest={},
            reason=str(result.get("message") or "Gangtise API 当前未返回有效数据，未使用模拟值。").strip(),
        )
    points = [dict(item) for item in (result.get("points") or []) if isinstance(item, dict) and item.get("date")]
    if len(points) < 2:
        return build_gangtise_unavailable_indicator_item(
            normalized_code,
            registry_entry=registry_entry,
            definition=definition,
            sources=[],
            latest={},
            reason="Gangtise API 返回的数据点不足，未使用模拟值。",
        )
    latest_point = points[-1]
    latest_value = round(NumberLike(latest_point.get("close")), 4)
    previous_value = round(NumberLike(points[-2].get("close")), 4)
    latest_status = build_real_indicator_status(latest_value, previous_value)
    history_series = []
    prev_close = None
    for point in points:
        point_close = round(NumberLike(point.get("close")), 4)
        point_prev = point_close if prev_close is None else prev_close
        history_series.append(
            {
                "date": str(point.get("date") or "").strip(),
                "value": point_close,
                "status": build_real_indicator_status(point_close, point_prev),
            }
        )
        prev_close = point_close
    source_meta = result.get("source_meta") if isinstance(result.get("source_meta"), dict) else {}
    history_kline = (
        build_real_indicator_kline_payload(points[-60:])
        if any(point.get("open") is not None for point in points)
        else build_indicator_kline_from_series_points(history_series[-60:], [], status=latest_status, indicator_code=normalized_code)
    )
    anomalies = copy.deepcopy(history_kline.get("anomalies") or [])
    indicator_name = str(definition.get("indicator_name") or registry_entry.get("indicator_name") or normalized_code).strip() or normalized_code
    category = str(definition.get("category") or registry_entry.get("category") or "数据湖指标").strip() or "数据湖指标"
    source_path = str(source_meta.get("path") or "").strip()
    source_security_code = str(source_meta.get("securityCode") or "").strip()
    latest_date = str(latest_point.get("date") or "").strip()
    latest_open = round(NumberLike(latest_point.get("open")), 4)
    latest_high = round(NumberLike(latest_point.get("high")), 4)
    latest_low = round(NumberLike(latest_point.get("low")), 4)
    latest_close = round(NumberLike(latest_point.get("close")), 4)
    assessment = (
        str(definition.get("assessment_template") or "").strip()
        or f"{indicator_name} 已直接通过 Gangtise OpenAPI 拉取真实历史序列，最新值为 {latest_close}。"
    )
    alert = (
        str(definition.get("alert_template") or "").strip()
        or "需关注数据源刷新与连通状态"
    )
    source_defs = [
        {
            "source_code": f"{normalized_code}_gangtise_live",
            "indicator_code": normalized_code,
            "provider": "Gangtise OpenAPI",
            "base_url": get_gangtise_openapi_config().get("base_url") or "",
            "path": source_path,
            "method": "POST",
            "auth_type": "bearer",
            "source_meta": copy.deepcopy(source_meta),
        }
    ]
    history = [
        {
            "date": point["date"],
            "value": f"{NumberLike(point['value']):.2f}",
            "status": str(point.get("status") or latest_status).strip() or latest_status,
                    "event": "已直接从 Gangtise OpenAPI 获取真实历史点位",
        }
        for point in history_series[-6:]
    ]
    return {
        "id": normalized_code,
        "name": indicator_name,
        "tenant_slug": str(definition.get("tenant_slug") or "").strip().lower(),
        "category": category,
        "unit": str(definition.get("unit") or "").strip(),
        "description": str(definition.get("description") or "").strip(),
        "owner": str(definition.get("owner") or "Gangtise OpenAPI 指标层").strip(),
        "value": f"{latest_close:.4f}".rstrip("0").rstrip("."),
        "numeric_value": latest_close,
        "assessment": assessment,
        "status": latest_status,
        "alert": alert,
        "enabled": bool(definition.get("enabled", True)),
        "last_updated": f"{latest_date} 00:00:00" if latest_date else "未记录",
        "watchers": definition.get("watchers", []),
        "prompt_text": str(definition.get("prompt_text") or "").strip(),
        "formula_js": str(definition.get("formula_js") or "").strip(),
        "selected_indicators": normalize_selected_indicator_refs(definition.get("selected_indicators")),
        "display_order": int(definition.get("display_order") or 0),
        "history": history,
        "history_series": history_series,
        "history_anomalies": anomalies,
        "history_kline": history_kline,
        "source_type": str(definition.get("source_type") or "indicator").strip() or "indicator",
        "source_type_label": str(definition.get("source_type_label") or "指标").strip() or "指标",
        "provider": "Gangtise OpenAPI",
        "source_count": 1,
        "source_defs": source_defs,
        "latest_source_test": {
            "status": f"HTTP {int(result.get('http_status') or 0)}",
            "detail": f"{source_path} · {source_security_code} · {str(result.get('message') or '').strip() or '操作成功'}",
            "tested_at": now_ts(),
        },
        "data_mode": "real",
        "data_mode_label": "Gangtise 真实数据",
        "data_source": "gangtise_openapi",
        "data_unavailable": False,
        "source_meta": {
            **copy.deepcopy(source_meta),
            "latest": {
                "date": latest_date,
                "open": latest_open,
                "high": latest_high,
                "low": latest_low,
                "close": latest_close,
            },
            "duration_ms": int(result.get("duration_ms") or 0),
        },
    }


def normalize_gangtise_lake_items(items, definition_map, source_map, latest_map):
    lake_by_id = {
        str(item.get("id") or "").strip(): copy.deepcopy(item)
        for item in (items or [])
        if str(item.get("id") or "").strip()
    }
    normalized = []
    for indicator_code, registry_entry in GANGTISE_INDICATOR_REGISTRY.items():
        definition = definition_map.get(indicator_code) or {}
        all_sources = list(source_map.get(indicator_code) or [])
        gangtise_sources = [item for item in all_sources if infer_source_connector_type(item) == "gangtise_openapi"]
        latest = latest_map.get(indicator_code) or {}
        item = lake_by_id.get(indicator_code)
        latest_source_code = str(latest.get("source_code") or "").strip()
        gangtise_source_codes = {
            str(source.get("source_code") or "").strip()
            for source in gangtise_sources
            if str(source.get("source_code") or "").strip()
        }
        unavailable_reason = ""
        if not gangtise_sources:
            unavailable_reason = "该指标尚未配置 Gangtise API 数据源，未使用模拟值。"
        elif not latest:
            unavailable_reason = "Gangtise API 当前还没有同步出这条指标的真实值。"
        elif bool(latest.get("is_simulated", 0)):
            unavailable_reason = "该指标当前只有模拟数据，已按要求隐藏。"
        elif latest_source_code == "derived_real_factors":
            unavailable_reason = "该指标当前只有推导值，不是 Gangtise API 原始值。"
        elif latest_source_code not in gangtise_source_codes:
            unavailable_reason = "该指标当前最新值不是 Gangtise API 返回结果。"
        elif not item or str(item.get("data_mode") or "").strip() != "real":
            unavailable_reason = "Gangtise API 当前未返回有效真实值。"
        if unavailable_reason:
            normalized.append(
                build_gangtise_unavailable_indicator_item(
                    indicator_code,
                    registry_entry=registry_entry,
                    definition=definition,
                    sources=gangtise_sources or all_sources,
                    latest=latest,
                    reason=unavailable_reason,
                )
            )
            continue
        item["provider"] = "Gangtise OpenAPI"
        item["source_count"] = len(gangtise_sources)
        item["source_defs"] = gangtise_sources
        item["data_source"] = "gangtise_openapi"
        item["data_unavailable"] = False
        item["data_mode"] = "real"
        item["data_mode_label"] = "Gangtise 真实数据"
        normalized.append(item)
    return normalized


def purge_simulated_indicator_store():
    db = get_db()
    deleted_latest = db.execute("DELETE FROM indicator_latest_values WHERE is_simulated = 1").rowcount or 0
    deleted_series = db.execute("DELETE FROM indicator_series WHERE is_simulated = 1").rowcount or 0
    deleted_kline = db.execute("DELETE FROM indicator_kline_points WHERE is_simulated = 1").rowcount or 0
    deleted_anomalies = db.execute("DELETE FROM indicator_anomalies WHERE is_simulated = 1").rowcount or 0
    if deleted_latest or deleted_series or deleted_kline or deleted_anomalies:
        db.commit()
    return {
        "deleted_latest": int(deleted_latest),
        "deleted_series": int(deleted_series),
        "deleted_kline": int(deleted_kline),
        "deleted_anomalies": int(deleted_anomalies),
    }


def sync_real_indicator_history_from_market_cache(force=False):
    token_ok, token, token_response, token_status, _ = obtain_gangtise_openapi_token()
    if not token_ok:
        return {
            "synced": False,
            "reason": "gangtise_openapi_auth_failed",
            "updated": 0,
            "detail": token_response.get("msg") or token_response.get("message") or "Gangtise OpenAPI 鉴权失败",
            "http_status": token_status,
        }
    db = get_db()
    definitions = list_indicator_definitions()
    timestamp = now_ts()
    batch_code = f"gangtise_openapi_sync_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    updated = 0
    total_points = 0
    active_sources = {item["indicator_code"]: item for item in list_indicator_source_defs()}
    for definition in definitions:
        indicator_code = definition["indicator_code"]
        if indicator_code not in GANGTISE_INDICATOR_REGISTRY:
            continue
        series_result = fetch_gangtise_indicator_series(indicator_code, token=token)
        rows = list(series_result.get("points") or [])
        if len(rows) < 2:
            continue
        source = active_sources.get(indicator_code)
        source_code = source["source_code"] if source else indicator_code
        # The upstream response is the authoritative history for this source.
        # Replacing the successfully fetched real series keeps incremental runs
        # current; the previous implementation skipped any indicator that had
        # one real row, so monthly indicators could remain permanently stale.
        db.execute("DELETE FROM indicator_series WHERE indicator_code = ? AND source_code = ?", (indicator_code, source_code))
        db.execute("DELETE FROM indicator_series WHERE indicator_code = ? AND is_simulated = 1", (indicator_code,))
        db.execute("DELETE FROM indicator_kline_points WHERE indicator_code = ?", (indicator_code,))
        db.execute("DELETE FROM indicator_anomalies WHERE indicator_code = ?", (indicator_code,))
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
        assessment = definition.get("assessment_template") or f"{definition.get('indicator_name') or indicator_code} 历史数据已从 Gangtise OpenAPI 同步入湖。"
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
                "gangtise_openapi_sync",
                "",
                "已从 Gangtise OpenAPI 同步真实指标历史，优先替代模拟序列。",
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
    purged = purge_simulated_indicator_store()
    invalidate_indicator_hub_cache()
    return {
        "seeded": False,
        "disabled": True,
        "reason": "mock_seed_disabled_use_gangtise_only",
        "message": "模拟指标补种已关闭，当前仅允许 Gangtise 真实指标和真实因子推导结果进入指标湖。",
        "purged_simulated": purged,
    }


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


def build_indicator_kline_from_series_points(series_points, anomalies, status="attention", indicator_code=""):
    points = [dict(item) for item in (series_points or []) if isinstance(item, dict) and item.get("date")]
    if not points:
        return build_empty_kline_payload()
    rows = []
    previous_close = None
    for index, point in enumerate(points):
        close_value = round(NumberLike(point.get("value")), 2)
        if previous_close is None:
            previous_close = close_value * 0.994 if close_value else 0.0
        open_value = round(previous_close, 2)
        base_high = max(open_value, close_value)
        base_low = min(open_value, close_value)
        spread = max(abs(close_value - open_value) * 0.38, max(close_value * 0.0035, 0.12))
        rows.append(
            {
                "date": str(point.get("date") or "").strip(),
                "open": round(open_value, 2),
                "high": round(base_high + spread, 2),
                "low": round(max(0.01, base_low - spread), 2),
                "close": close_value,
            }
        )
        previous_close = close_value
    return build_real_indicator_kline_payload(rows[-60:])


def build_indicator_hub_from_store():
    definitions = list_indicator_definitions()
    definition_map = {
        str(item.get("indicator_code") or "").strip(): item
        for item in definitions
        if str(item.get("indicator_code") or "").strip()
    }
    source_map = {}
    for source in list_indicator_source_defs():
        indicator_code = str((source or {}).get("indicator_code") or "").strip()
        # Source definitions can be edited independently from indicators. Ignore
        # incomplete rows instead of breaking every indicator chart.
        if indicator_code:
            source_map.setdefault(indicator_code, []).append(source)
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
        latest_is_simulated = bool(latest.get("is_simulated", 0))
        if not latest:
            data_mode = "unavailable"
            data_mode_label = "暂无真实数据"
        elif latest_is_simulated:
            data_mode = "simulated"
            data_mode_label = "模拟数据"
        elif latest_source_code == "derived_real_factors":
            data_mode = "derived"
            data_mode_label = "真实因子推导"
        else:
            data_mode = "real"
            data_mode_label = "真实数据"
        history_series = series_map.get(definition["indicator_code"], [])
        raw_kline_rows = kline_map.get(definition["indicator_code"], [])
        history_kline = build_indicator_kline_from_rows(raw_kline_rows, anomalies) if raw_kline_rows else build_indicator_kline_from_series_points(
            history_series,
            anomalies,
            status=latest.get("latest_status") or definition.get("status_hint") or "attention",
            indicator_code=definition["indicator_code"],
        )
        item = {
            "id": definition["indicator_code"],
            "name": definition["indicator_name"],
            "tenant_slug": str(definition.get("tenant_slug") or "").strip().lower(),
            "category": definition["category"],
            "unit": definition.get("unit") or "",
            "description": definition.get("description") or "",
            "owner": definition["owner"],
            "value": latest.get("latest_value") or "--",
            "numeric_value": parse_numeric_indicator_value(latest.get("latest_value")),
            "assessment": latest.get("latest_assessment") or definition.get("assessment_template") or "暂无说明",
            "status": latest.get("latest_status") or definition.get("status_hint") or "attention",
            "alert": latest.get("latest_alert") or definition.get("alert_template") or "暂无预警说明",
            "enabled": bool(definition.get("enabled")),
            "last_updated": latest.get("updated_at") or definition.get("updated_at") or "未记录",
            "data_at": str((history_series[-1] if history_series else {}).get("date") or "").strip(),
            "watchers": definition.get("watchers", []),
            "prompt_text": str(definition.get("prompt_text") or "").strip(),
            "formula_js": str(definition.get("formula_js") or "").strip(),
            "selected_indicators": normalize_selected_indicator_refs(definition.get("selected_indicators")),
            "display_order": int(definition.get("display_order") or 0),
            "history": [
                {
                    "date": point["date"],
                    "value": f"{point['value']:.2f}",
                    "status": point["status"],
                    "event": (
                        "真实指标点已写入指标湖" if data_mode == "real"
                        else ("已由真实因子推导写入指标湖" if data_mode == "derived"
                              else ("模拟指标点已写入指标湖" if data_mode == "simulated" else "当前尚未同步到真实指标点"))
                    ),
                }
                for point in history_series[-6:]
            ],
            "history_series": history_series,
            "history_anomalies": anomalies,
            "history_kline": history_kline,
            "source_type": definition.get("source_type") or "indicator",
            "source_type_label": definition.get("source_type_label") or "指标",
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
    lake_items = normalize_gangtise_lake_items(
        [item for item in items if item["source_type"] != "smart"],
        definition_map,
        source_map,
        latest_map,
    )
    items = smart_items + lake_items
    item_map = {str(item.get("id") or ""): item for item in items if str(item.get("id") or "")}
    for item in smart_items:
        source_dates = [
            str((item_map.get(str(source.get("indicator_code") or "")) or {}).get("data_at") or "").strip()
            for source in (item.get("selected_indicators") or [])
        ]
        item["data_at"] = max((value for value in source_dates if value), default=str(item.get("data_at") or "").strip())
    anomalies = []
    for item in smart_items + lake_items:
        if item.get("data_unavailable"):
            continue
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


def get_indicator_hub_from_store_cached(force_refresh=False):
    now = time.time()
    cached_value = _indicator_hub_cache.get("value")
    expires_at = float(_indicator_hub_cache.get("expires_at") or 0.0)
    if not force_refresh and cached_value is not None and now < expires_at:
        return copy.deepcopy(cached_value)
    hub = build_indicator_hub_from_store()
    _indicator_hub_cache["value"] = copy.deepcopy(hub)
    _indicator_hub_cache["expires_at"] = now + INDICATOR_HUB_CACHE_TTL_SECONDS
    return copy.deepcopy(hub)


def get_indicator_hub_snapshot():
    try:
        return get_indicator_hub_from_store_cached()
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while loading indicator hub snapshot, returning unavailable payload")
        return {
            "summary": {"total": 0, "smart_total": 0, "lake_total": 0, "enabled": 0, "warnings": 0, "attention": 0, "anomalies": 0},
            "items": [],
            "smart_items": [],
            "lake_items": [],
            "anomalies": [],
            "definitions": [],
            "source_defs": [],
            "recent_tests": [],
            "load_batches": [],
            "raw_records": [],
            "mapping_rules": [],
            "clean_jobs": [],
            "data_unavailable": True,
        }


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

    def _sanitize_summary_text(text):
        cleaned = re.sub(r"[A-Za-z_][A-Za-z0-9_]*\(\)", "", str(text or "")).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"^[：:;\-，,\s]+", "", cleaned)
        cleaned = cleaned.replace("宏观接口", "宏观信号")
        return cleaned.strip("：:;，, ")

    board_summary_templates = {
        "半导体制造": {
            "warning": "景气验证仍有压力，优先盯产能利用率和盈利兑现。",
            "attention": "国产替代逻辑仍在，短期继续跟踪盈利兑现。",
            "normal": "产业趋势还在，当前按盈利兑现节奏继续观察。",
        },
        "动力电池": {
            "warning": "价格竞争仍在，先看利润率和海外出货是否稳住。",
            "attention": "情绪回落后更适合继续看技术路线和订单验证。",
            "normal": "行业主线未破坏，重点跟踪新技术和出货节奏。",
        },
        "港股互联网": {
            "warning": "估值修复放缓，先看财报兑现和资金延续。",
            "attention": "回购和财报兑现仍是两条主验证线。",
            "normal": "当前更适合围绕回购、利润率和南向资金继续跟踪。",
        },
        "高端白酒": {
            "warning": "消费修复仍需验证，先看需求和估值承接。",
            "attention": "盈利稳定但弹性有限，继续看消费修复持续性。",
            "normal": "品牌力和现金流仍稳，当前按消费修复节奏跟踪。",
        },
        "银行": {
            "warning": "防守价值还在，但要继续跟踪息差压力。",
            "attention": "适合作为组合稳定器，继续看股息和资产质量。",
            "normal": "股息和资产质量稳定，更适合稳健跟踪。",
        },
    }

    if dominant_item:
        default_summary = _sanitize_summary_text(dominant_item.get("assessment") or dominant_item.get("alert") or "需继续观察")
        board_summary = (
            board_summary_templates.get(industry_text, {}).get(board_alert_level)
            or default_summary
            or "当前需继续观察价格、行业位置和验证节点。"
        )
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
        thesis.append(
            sanitize_user_facing_source_text(
                f"{item.get('name')}: {item.get('assessment') or item.get('alert') or '继续观察'}",
                fallback=f"{item.get('name')}: 继续观察",
            )
        )
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
                "note": sanitize_user_facing_source_text(
                    item.get("assessment") or item.get("alert") or "当前无说明",
                    fallback="当前无说明",
                ),
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
    try:
        hub = build_indicator_hub_from_store()
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        return []
    return [
        copy.deepcopy(item)
        for item in (hub.get("lake_items") or [])
        if str(item.get("id") or "").strip() in GANGTISE_INDICATOR_REGISTRY
    ]


def build_indicator_hub(tenant=None, admin_view=False):
    tenant = tenant or get_tenant_by_slug()
    try:
        hub = get_indicator_hub_from_store_cached()
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while building indicator hub, returning unavailable payload")
        return {
            "summary": {"total": 0, "smart_total": 0, "lake_total": 0, "enabled": 0, "warnings": 0, "attention": 0, "anomalies": 0},
            "items": [],
            "smart_items": [],
            "lake_items": [],
            "anomalies": [],
            "definitions": [],
            "source_defs": [],
            "recent_tests": [],
            "load_batches": [],
            "raw_records": [],
            "mapping_rules": [],
            "clean_jobs": [],
            "data_unavailable": True,
        }
    hub = copy.deepcopy(hub)
    tenant_slug = str((tenant or {}).get("slug") or "").strip().lower()
    if not admin_view and tenant_slug:
        smart_items = [
            item for item in (hub.get("smart_items") or [])
            if str(item.get("tenant_slug") or "").strip().lower() in {"", tenant_slug}
        ]
        lake_items = list(hub.get("lake_items") or [])
        items = smart_items + lake_items
        smart_ids = {item.get("id") for item in smart_items if item.get("id")}
        hub["smart_items"] = smart_items
        hub["items"] = items
        hub["anomalies"] = [
            item for item in (hub.get("anomalies") or [])
            if item.get("related_indicator_id") in smart_ids or item.get("related_indicator_id") in {lake.get("id") for lake in lake_items}
        ]
        hub["summary"] = {
            "total": len(items),
            "smart_total": len(smart_items),
            "lake_total": len(lake_items),
            "enabled": sum(1 for item in items if item.get("enabled")),
            "warnings": sum(1 for item in items if item.get("status") == "warning"),
            "attention": sum(1 for item in items if item.get("status") == "attention"),
            "anomalies": len(hub["anomalies"]),
        }
    advisor_name = tenant.get("advisor") if isinstance(tenant, dict) else ""
    for item in hub.get("smart_items", []):
        if advisor_name and item.get("owner") in {"平台研究运营", "平台宏观组", ""}:
            item["owner"] = advisor_name
    return hub


HOT_INDUSTRY_NAME_MAP = {
    "高端白酒": "食品饮料",
    "白酒": "食品饮料",
    "动力电池": "电力设备",
    "新能源": "电力设备",
    "半导体制造": "电子",
    "消费电子材料": "电子",
    "港股互联网": "传媒",
    "互联网": "传媒",
    "酿酒行业": "食品饮料",
    "食品饮料": "食品饮料",
    "电池": "电力设备",
    "光伏设备": "电力设备",
    "风电设备": "电力设备",
    "半导体": "电子",
    "电子元件": "电子",
    "消费电子": "电子",
    "汽车整车": "汽车",
    "汽车零部件": "汽车",
    "汽车服务": "汽车",
    "证券": "非银金融",
    "保险": "非银金融",
    "多元金融": "非银金融",
    "软件开发": "计算机",
    "互联网服务": "计算机",
    "计算机设备": "计算机",
    "通信设备": "通信",
    "文化传媒": "传媒",
    "煤炭行业": "煤炭",
    "石油行业": "石油石化",
    "化学原料": "基础化工",
    "化学制品": "基础化工",
    "化肥行业": "基础化工",
    "贵金属": "有色金属",
    "小金属": "有色金属",
    "能源金属": "有色金属",
    # AKShare THS board names that need an unambiguous Shenwan level-one
    # destination. These mappings classify real provider rows only.
    "环境治理": "环保",
    "环保设备": "环保",
    "油气开采及服务": "石油石化",
    "石油加工贸易": "石油石化",
    "医疗服务": "医药生物",
    "生物制品": "医药生物",
    "中药": "医药生物",
    "化学制药": "医药生物",
}

THS_TO_SHENWAN_LEVEL1_KEYWORDS = {
    "农林牧渔": ("养殖", "饲料", "种植", "农产品", "农业"),
    "基础化工": ("化工", "化学", "化肥", "农化", "塑料", "橡胶", "化纤"),
    "钢铁": ("钢铁", "特钢"),
    "有色金属": ("金属", "贵金属", "小金属"),
    "电子": ("半导体", "元件", "消费电子", "光学", "电子"),
    "汽车": ("汽车", "车零部件", "摩托"),
    "家用电器": ("家电", "白色家电", "黑色家电", "小家电"),
    "食品饮料": ("食品", "饮料", "白酒", "乳业", "调味", "烘焙"),
    "纺织服饰": ("纺织", "服装", "饰品", "美容"),
    "轻工制造": ("包装", "造纸", "家居", "文娱", "家具"),
    "医药生物": ("医药", "医疗", "生物", "中药", "药"),
    "公用事业": ("电力", "燃气", "水务", "环保"),
    "交通运输": ("物流", "航运", "港口", "铁路", "航空", "机场"),
    "房地产": ("房地产", "房产"),
    "商贸零售": ("零售", "贸易", "商业", "免税"),
    "社会服务": ("酒店", "旅游", "景区", "教育", "服务"),
    "建筑材料": ("水泥", "玻璃", "建材"),
    "建筑装饰": ("建筑", "装修", "工程"),
    "电力设备": ("电池", "光伏", "风电", "电网", "储能", "电源设备"),
    "国防军工": ("军工", "航天", "船舶", "兵器"),
    "计算机": ("软件", "IT服务", "计算机", "数字"),
    "传媒": ("传媒", "影视", "游戏", "出版", "广告"),
    "通信": ("通信", "运营商"),
    "银行": ("银行",),
    "非银金融": ("证券", "保险", "多元金融"),
    "机械设备": ("机械", "自动化", "通用设备", "专用设备"),
    "煤炭": ("煤炭",),
    "石油石化": ("石油", "炼化"),
}


def canonical_hot_industry_name(value):
    """Use the Shenwan level-one name shown by the Hot Industries tab."""
    name = str(value or "").strip()
    return HOT_INDUSTRY_NAME_MAP.get(name, name or "其他行业")


def canonical_ths_industry_name(value):
    """Map a THS board to the existing Shenwan level-one display taxonomy."""
    raw_name = str(value or "").strip()
    direct = canonical_hot_industry_name(raw_name)
    if direct in SHENWAN_LEVEL1_INDUSTRIES:
        return direct
    for sector, keywords in THS_TO_SHENWAN_LEVEL1_KEYWORDS.items():
        if any(keyword in raw_name for keyword in keywords):
            return sector
    return ""


def gen_feed_boards(market_items):
    boards = []
    board_map = {}
    for item in market_items:
        board_name = canonical_hot_industry_name(item.get("industry") or item.get("focus") or item.get("board"))
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
        # A fundamental board is a quote-backed view. Keep the saved
        # watchlist relation, but do not expose an unavailable quote as a
        # stock card with fabricated zero-valued metrics.
        if not isinstance(item, dict) or item.get("data_unavailable"):
            continue
        if any(numeric_value(item.get(field)) is None for field in ("price", "change", "change_pct")):
            continue
        board_name = canonical_hot_industry_name(item.get("industry") or item.get("focus"))
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
                "value": NumberLike(item.get("price")),
                "change": NumberLike(item.get("change")),
                "change_pct": NumberLike(item.get("change_pct")),
                "focus": canonical_hot_industry_name(item.get("industry") or item.get("focus") or "个股跟踪"),
                "alert_level": item.get("alert_level", "normal"),
                "alert_text": item.get("alert_text", "当前无明显预警"),
                "signal_summary": item.get("signal_summary", ""),
            }
        )
    return boards


WATCHLIST_DYNAMIC_DETAIL_PRESETS = {
    "601988": {
        "name": "中国银行",
        "market": "SH",
        "price": 5.65,
        "change": -0.17,
        "change_pct": -2.92,
        "industry": "银行",
        "focus": "稳健配置",
        "authors": [
            {"id": 4, "name": "全球宏观James", "avatar": "🌐", "tier": "成长作者", "angle": "银行股更适合从息差、资产质量和股息稳定性三条线去拆。"},
            {"id": 3, "name": "量化老师陈明", "avatar": "📊", "tier": "成长作者", "angle": "这类资产更像组合稳定器，不适合用高弹性成长股的框架判断。"},
        ],
        "fundamental": {
            "summary": "核心看净息差、资产质量和股息稳定性，当前更偏防守型配置视角。",
            "metrics": [
                {"label": "净息差", "value": "1.59%", "note": "仍需关注利率环境变化"},
                {"label": "不良率", "value": "1.28%", "note": "整体保持可控"},
                {"label": "拨备覆盖率", "value": "189%", "note": "风险缓冲仍充足"},
                {"label": "股息率", "value": "5.4%", "note": "防守价值较突出"},
            ],
            "thesis": [
                "大行资产负债表稳健，适合防守型资金配置。",
                "利率和宏观信用周期会直接影响估值弹性。",
                "更适合看分红与稳健收益，不宜期待高弹性重估。",
            ],
        },
        "forecast": {
            "label": "基本面判断",
            "verdict": "稳健跟踪",
            "confidence": "中高",
            "band": "适合作为组合中的防守型样本，重点跟踪息差与资产质量变化。",
            "drivers": [
                {"label": "股息支撑", "score": "+2.0", "note": "分红稳定性较强"},
                {"label": "资产质量", "score": "+1.4", "note": "大行风险暴露相对可控"},
                {"label": "息差压力", "score": "-0.8", "note": "仍需观察利率环境"},
            ],
        },
    },
    "003015": {
        "name": "日久光电",
        "market": "SZ",
        "price": 10.38,
        "change": 0.12,
        "change_pct": 1.17,
        "industry": "消费电子材料",
        "focus": "显示材料",
        "authors": [
            {"id": 1, "name": "财经老王", "avatar": "👑", "tier": "种子作者", "angle": "先拆材料业务结构，再看消费电子链条景气和下游验证。"},
            {"id": 4, "name": "宏观策略师", "avatar": "🎯", "tier": "成长作者", "angle": "更适合结合订单节奏和板块轮动去判断阶段预期差。"},
        ],
        "fundamental": {
            "summary": "优先跟踪显示材料业务、客户结构和下游消费电子景气，当前更适合从业务拆解与订单验证切入。",
            "metrics": [
                {"label": "核心方向", "value": "显示材料", "note": "先看产品结构与客户绑定度"},
                {"label": "价格位置", "value": "10.38", "note": "用于观察当前位置与阶段预期差"},
                {"label": "研究重点", "value": "订单兑现", "note": "继续核查下游应用与出货节奏"},
                {"label": "波动属性", "value": "中高", "note": "适合结合行业情绪与资金面观察"},
            ],
            "thesis": [
                "先看产品结构和核心客户，再决定是否具备持续成长逻辑。",
                "若下游需求回暖，材料环节更容易出现阶段性预期差。",
                "需要继续补足财务与行业证据，避免只凭短期价格判断。",
            ],
        },
        "forecast": {
            "label": "基本面判断",
            "verdict": "继续跟踪",
            "confidence": "中",
            "band": "当前先以业务结构、订单验证和价格位置做第一轮判断，再补充财报与行业证据。",
            "drivers": [
                {"label": "业务拆解", "score": "+1.2", "note": "先确认核心产品和客户结构"},
                {"label": "订单验证", "score": "+0.8", "note": "下游需求回暖会放大弹性"},
                {"label": "波动风险", "score": "-0.6", "note": "需要警惕情绪驱动带来的回撤"},
            ],
        },
    },
}

WATCHLIST_QUERY_ALIAS_MAP = {
    "中国银行": "601988",
    "日久光新": "003015",
    "日久光电": "003015",
    "上证指数": "source_shanghai_index",
    "上证综合指数": "source_shanghai_index",
    "上证综指": "source_shanghai_index",
    "上海综合指数": "source_shanghai_index",
    "沪指": "source_shanghai_index",
    "大盘": "source_shanghai_index",
    "000001.SH": "source_shanghai_index",
    "SH000001": "source_shanghai_index",
    "SH.000001": "source_shanghai_index",
    "sh000001": "source_shanghai_index",
    "深证指数": "source_shenzhen_index",
    "深证成指": "source_shenzhen_index",
    "深圳成指": "source_shenzhen_index",
    "深指": "source_shenzhen_index",
    "399001.SZ": "source_shenzhen_index",
    "SZ399001": "source_shenzhen_index",
    "SZ.399001": "source_shenzhen_index",
    "sz399001": "source_shenzhen_index",
    "沪深300": "source_hs300",
    "沪深300指数": "source_hs300",
    "000300.SH": "source_hs300",
    "SH000300": "source_hs300",
    "sh000300": "source_hs300",
    "上证50": "source_sse50",
    "上证50指数": "source_sse50",
    "000016.SH": "source_sse50",
    "SH000016": "source_sse50",
    "sh000016": "source_sse50",
    "科创50": "source_kc50",
    "科创50指数": "source_kc50",
    "000688.SH": "source_kc50",
    "SH000688": "source_kc50",
    "sh000688": "source_kc50",
    "创业板指": "source_cyb",
    "创业板指数": "source_cyb",
    "399006.SZ": "source_cyb",
    "SZ399006": "source_cyb",
    "sz399006": "source_cyb",
    "中证500": "source_zz500",
    "中证500指数": "source_zz500",
    "000905.SH": "source_zz500",
    "SH000905": "source_zz500",
    "sh000905": "source_zz500",
    "中证1000": "source_zz1000",
    "中证1000指数": "source_zz1000",
    "000852.SH": "source_zz1000",
    "SH000852": "source_zz1000",
    "sh000852": "source_zz1000",
    "中证800": "source_zz800",
    "中证800指数": "source_zz800",
    "000906.SH": "source_zz800",
    "SH000906": "source_zz800",
    "sh000906": "source_zz800",
    "中证A500": "source_a500",
    "中证A500指数": "source_a500",
    "000510.SH": "source_a500",
    "SH000510": "source_a500",
    "sh000510": "source_a500",
    "中证2000": "source_zz2000",
    "中证2000指数": "source_zz2000",
    "932000.CSI": "source_zz2000",
    "恒生指数": "source_hsi",
    "恒指": "source_hsi",
    "国企指数": "source_hscei",
    "恒生国企指数": "source_hscei",
    "恒生中国企业指数": "source_hscei",
    "红筹指数": "source_hscci",
    "恒生红筹指数": "source_hscci",
    "日经225": "source_nikkei",
    "日经225指数": "source_nikkei",
    "标普500": "source_sp500",
    "标普500指数": "source_sp500",
    "SP500": "source_sp500",
    "S&P500": "source_sp500",
    "纳斯达克指数": "source_nasdaq",
    "纳指": "source_nasdaq",
    "NASDAQ": "source_nasdaq",
}
WATCHLIST_NAME_ALIAS_MAP = {
    "003015": "日久光电",
    "source_shanghai_index": "上证指数",
    "source_shenzhen_index": "深证指数",
    "source_hs300": "沪深300",
    "source_sse50": "上证50",
    "source_kc50": "科创50",
    "source_cyb": "创业板指",
    "source_zz500": "中证500",
    "source_zz1000": "中证1000",
    "source_zz800": "中证800",
    "source_a500": "中证A500",
    "source_zz2000": "中证2000",
    "source_hsi": "恒生指数",
    "source_hscei": "国企指数",
    "source_hscci": "红筹指数",
    "source_nikkei": "日经225",
    "source_sp500": "标普500",
    "source_nasdaq": "纳斯达克指数",
}
WATCHLIST_SEARCH_CACHE_TTL_SECONDS = 6 * 60 * 60
WATCHLIST_DETAIL_CACHE_TTL_SECONDS = 30 * 60
WATCHLIST_INDEX_DETAIL_CACHE_TTL_SECONDS = 5 * 60

MARKET_OVERVIEW_INDEX_CODES = (
    "source_shanghai_index",
    "source_shenzhen_index",
    "source_hsi",
    "source_hscei",
    "source_hscci",
    "source_dji",
    "source_nasdaq",
    "source_sp500",
    "source_nikkei",
)

AKSHARE_MARKET_INDEX_CATALOG = {
    "source_shanghai_index": {"kind": "cn", "symbol": "sh000001", "aliases": ("上证指数", "上证综指")},
    "source_shenzhen_index": {"kind": "cn", "symbol": "sz399001", "aliases": ("深证成指", "深证指数")},
    # Use AKShare's Sina-backed endpoints. The prior Eastmoney global-history
    # endpoint is not reliably reachable in deployed network environments.
    "source_hsi": {"kind": "hk_sina", "symbol": "HSI"},
    "source_hscei": {"kind": "hk_sina", "symbol": "HSCEI"},
    "source_hscci": {"kind": "hk_sina", "symbol": "HSCCI"},
    "source_dji": {"kind": "us_sina", "symbol": ".DJI"},
    "source_nasdaq": {"kind": "us_sina", "symbol": ".IXIC"},
    "source_sp500": {"kind": "us_sina", "symbol": ".INX"},
    "source_nikkei": {"kind": "global_sina", "symbol": "日经225指数"},
}

# The supplied Gangtise test report verifies the two domestic indices through
# the daily quote endpoint and six overseas indices through EDB. The two HK
# indices without a verified Gangtise mapping remain explicit unavailable rows;
# they must not silently switch back to another provider.
GANGTISE_MARKET_INDEX_CODES = frozenset(MARKET_OVERVIEW_INDEX_CODES)


def _load_akshare():
    try:
        import akshare as ak
    except Exception as exc:
        raise RuntimeError(f"AKShare 不可用：{exc}") from exc
    return ak


def _akshare_float(value):
    if value is None:
        return None
    try:
        numeric = float(str(value).replace(",", "").strip())
        return numeric if math.isfinite(numeric) else None
    except (TypeError, ValueError):
        return None


def _akshare_column(frame, candidates):
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return None


def _akshare_market_index_points(frame):
    """Normalize AKShare's domestic and global index frames into daily candles."""
    if frame is None or getattr(frame, "empty", True):
        return []
    date_column = _akshare_column(frame, ("日期", "date", "Date", "时间", "日期时间"))
    open_column = _akshare_column(frame, ("开盘", "open", "Open"))
    high_column = _akshare_column(frame, ("最高", "high", "High"))
    low_column = _akshare_column(frame, ("最低", "low", "Low"))
    close_column = _akshare_column(frame, ("收盘", "最新价", "close", "Close"))
    if not date_column or not close_column:
        return []
    points = []
    for _, row in frame.iterrows():
        close_value = _akshare_float(row.get(close_column))
        if close_value is None:
            continue
        date_value = str(row.get(date_column) or "").strip()[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
            continue
        open_value = _akshare_float(row.get(open_column)) if open_column else close_value
        high_value = _akshare_float(row.get(high_column)) if high_column else close_value
        low_value = _akshare_float(row.get(low_column)) if low_column else close_value
        points.append({
            "date": date_value,
            "open": open_value if open_value is not None else close_value,
            "high": high_value if high_value is not None else close_value,
            "low": low_value if low_value is not None else close_value,
            "close": close_value,
        })
    return sorted({item["date"]: item for item in points}.values(), key=lambda item: item["date"])


def _akshare_global_index_symbols(ak):
    """Compatibility shim for callers from the former Eastmoney collector."""
    return {}


def fetch_akshare_market_index_history(indicator_code, start_date, end_date, ak=None, global_symbols=None):
    """Fetch a real standard-index daily series for the controlled collector only."""
    config = AKSHARE_MARKET_INDEX_CATALOG.get(indicator_code)
    if not config:
        return {"ok": False, "points": [], "message": "未配置 AKShare 标准指数映射"}
    try:
        ak = ak or _load_akshare()
        kind = config.get("kind")
        symbol = config.get("symbol")
        if kind == "cn":
            frame = ak.stock_zh_index_daily(symbol=symbol)
        elif kind == "hk_sina":
            frame = ak.stock_hk_index_daily_sina(symbol=symbol)
        elif kind == "us_sina":
            frame = ak.index_us_stock_sina(symbol=symbol)
        elif kind == "global_sina":
            frame = ak.index_global_hist_sina(symbol=symbol)
        else:
            return {"ok": False, "points": [], "message": "AKShare 未配置该标准指数采集方式"}
        points = _akshare_market_index_points(frame)
        windowed = [item for item in points if start_date <= item["date"] <= end_date]
        points = windowed or points[-60:]
        if len(points) < 2:
            return {"ok": False, "points": points, "message": "AKShare 未返回足够的真实日线"}
        return {"ok": True, "points": points, "message": "", "provider": "AKShare"}
    except Exception as exc:
        return {"ok": False, "points": [], "message": f"AKShare 行情获取失败：{exc}"}


def fetch_gangtise_market_index_history(indicator_code, start_date, end_date, token=""):
    """Fetch a mainland broad-index series using the tested Gangtise contract."""
    if indicator_code not in GANGTISE_MARKET_INDEX_CODES:
        return {"ok": False, "points": [], "message": "该标准指数未配置 Gangtise 日K接口", "provider": "Gangtise OpenAPI"}
    result = fetch_gangtise_indicator_series(
        indicator_code,
        start_date=start_date,
        end_date=end_date,
        token=token,
    )
    points = list(result.get("points") or []) if isinstance(result, dict) else []
    return {
        "ok": bool((result or {}).get("ok")) and len(points) >= 2,
        "points": points,
        "message": str((result or {}).get("message") or "Gangtise 未返回足够的指数日K").strip(),
        "provider": "Gangtise OpenAPI",
        "source_meta": (result or {}).get("source_meta") or {},
        "duration_ms": int((result or {}).get("duration_ms") or 0),
    }


def fetch_akshare_market_index_intraday(indicator_code, trade_date="", ak=None):
    """AKShare only supplies minute data for mainland indices in this catalog."""
    config = AKSHARE_MARKET_INDEX_CATALOG.get(indicator_code) or {}
    if config.get("kind") != "cn":
        return {"ok": False, "available": False, "points": [], "message": "该指数暂无 AKShare 分时数据", "source": "AKShare"}
    try:
        ak = ak or _load_akshare()
        date_text = str(trade_date or datetime.now().strftime("%Y-%m-%d"))[:10]
        frame = ak.index_zh_a_hist_min_em(
            symbol=str(config["symbol"])[2:],
            period="1",
            start_date=f"{date_text} 09:30:00",
            end_date=f"{date_text} 15:00:00",
        )
        time_column = _akshare_column(frame, ("时间", "日期", "datetime", "date", "Date"))
        value_column = _akshare_column(frame, ("收盘", "最新价", "close", "Close"))
        if not time_column or not value_column:
            return {"ok": False, "available": False, "points": [], "message": "AKShare 分时响应缺少必要字段", "source": "AKShare"}
        points = []
        for _, row in frame.iterrows():
            value = _akshare_float(row.get(value_column))
            timestamp = str(row.get(time_column) or "").strip()
            if value is not None and timestamp:
                points.append({"date": timestamp, "value": value})
        if not points:
            return {"ok": False, "available": False, "points": [], "message": "AKShare 未返回真实分时", "source": "AKShare"}
        return {"ok": True, "available": True, "points": points, "message": "", "updated_at": points[-1]["date"], "source": "AKShare"}
    except Exception as exc:
        # Provider diagnostics belong in server logs. Do not leak proxy hosts,
        # request parameters, or vendor-specific code errors to end users.
        app.logger.warning("AKShare index intraday unavailable for %s: %s", indicator_code, exc)
        return {"ok": False, "available": False, "points": [], "message": "AKShare 分时暂不可用，已等待后端分钟数据补采", "source": "AKShare"}


def _build_market_index_snapshot_item(indicator_code, series_result):
    entry = GANGTISE_INDICATOR_REGISTRY.get(indicator_code) or {}
    data_source = str((series_result or {}).get("provider") or "Gangtise OpenAPI").strip() or "Gangtise OpenAPI"
    points = list((series_result or {}).get("points") or [])
    base = {
        "indicator_code": indicator_code,
        "name": entry.get("indicator_name") or indicator_code,
        "code": entry.get("security_code") or "",
        "market": entry.get("market") or "CN",
        "data_source": data_source,
    }
    if len(points) < 2:
        return {**base, "available": False, "message": str((series_result or {}).get("message") or f"{data_source} 暂未返回足够的真实行情").strip()}
    latest, previous = points[-1], points[-2]
    latest_value = numeric_value(latest.get("close"))
    previous_value = numeric_value(previous.get("close"))
    if latest_value is None or previous_value is None:
        return {**base, "available": False, "message": f"{data_source} 返回的行情缺少有效数值"}
    change = latest_value - previous_value
    return {
        **base,
        "price": round(latest_value, 2),
        "change": round(change, 2),
        "change_pct": round(change / previous_value * 100, 2) if previous_value else 0,
        "updated_at": str(latest.get("date") or "").strip(),
        "available": True,
        "message": "",
    }


_market_snapshot_refresh_lock = threading.Lock()
_market_snapshot_refresh_running = False


def sync_market_snapshot(force=False):
    """Collect Gangtise market snapshots and persist only verified real results."""
    assert_admin_task_not_stopped("market_snapshot_sync")
    start_date, end_date = resolve_gangtise_market_date_window(days=30)
    overview_items = []
    errors = []
    intraday_count = 0
    previous_overview = _load_market_snapshot_payload("market_overview", "standard_indices", 0) or _load_watchlist_cache("market_overview", "standard_indices", 0)
    previous_items = {
        str(item.get("indicator_code") or ""): item
        for item in ((previous_overview or {}).get("items") or [])
        if isinstance(item, dict) and item.get("available") and str(item.get("data_source") or "").lower() == "gangtise openapi"
    }
    for indicator_code in MARKET_OVERVIEW_INDEX_CODES:
        assert_admin_task_not_stopped("market_snapshot_sync")
        result = fetch_gangtise_market_index_history(indicator_code, start_date, end_date)
        item = _build_market_index_snapshot_item(indicator_code, result)
        if not item.get("available") and indicator_code in previous_items:
            # Do not replace a verified Gangtise point with an upstream outage.
            item = {**copy.deepcopy(previous_items[indicator_code]), "stale": True}
        overview_items.append(item)
        if not item.get("available"):
            errors.append(f"{item.get('name') or indicator_code}：{item.get('message') or '暂无数据'}")
            continue
        _save_watchlist_cache(
            "market_index_history",
            indicator_code,
            {
                "ok": True,
                "provider": result.get("provider") or "未知来源",
                "source_meta": result.get("source_meta") or {},
                "indicator_code": indicator_code,
                "points": result["points"],
                "updated_at": item.get("updated_at"),
            },
        )
    cached_sector_snapshot = None if force else (
        _load_market_snapshot_payload(
            "market_sector_overview",
            "shenwan_level1",
            MARKET_SECTOR_SNAPSHOT_REFRESH_TTL_SECONDS,
        )
        or _load_watchlist_cache(
            "market_sector_overview",
            "shenwan_level1",
            MARKET_SECTOR_SNAPSHOT_REFRESH_TTL_SECONDS,
        )
    )
    if isinstance(cached_sector_snapshot, dict) and str(cached_sector_snapshot.get("source") or "").lower() == "gangtise openapi" and cached_sector_snapshot.get("items"):
        sector_items = list(cached_sector_snapshot["items"])
    else:
        sector_items, sector_errors = _fetch_gangtise_sector_overview(start_date, end_date)
        errors.extend(sector_errors)
    if not sector_items:
        errors.append("Gangtise 申万一级行业日K未返回有效数据")
    updated_at = now_ts()
    overview_payload = {"ok": True, "snapshot_version": 6, "items": overview_items, "source": "Gangtise OpenAPI", "updated_at": updated_at}
    sector_payload = {"ok": True, "snapshot_version": 6, "items": sector_items, "total": len(sector_items), "catalog_size": len(SHENWAN_LEVEL1_INDUSTRIES), "source": "Gangtise OpenAPI", "updated_at": updated_at}
    if any(item.get("available") for item in overview_items):
        _save_market_snapshot_payload("market_overview", "standard_indices", overview_payload)
    if sector_items:
        _save_market_snapshot_payload("market_sector_overview", "shenwan_level1", sector_payload)
    return {"ok": bool(any(item.get("available") for item in overview_items) or sector_items), "updated": sum(1 for item in overview_items if item.get("available")) + len(sector_items) + intraday_count, "overview_count": sum(1 for item in overview_items if item.get("available")), "sector_count": len(sector_items), "intraday_count": intraday_count, "updated_at": updated_at, "errors": errors[:20]}


def request_market_snapshot_refresh():
    """Start one controlled backend refresh when a required cache is missing."""
    global _market_snapshot_refresh_running
    with _market_snapshot_refresh_lock:
        if _market_snapshot_refresh_running:
            return False
        _market_snapshot_refresh_running = True

    def worker():
        global _market_snapshot_refresh_running
        try:
            with app.app_context():
                sync_market_snapshot(force=False)
        except Exception as exc:
            app.logger.warning("Automatic market snapshot refresh failed: %s", exc)
        finally:
            with _market_snapshot_refresh_lock:
                _market_snapshot_refresh_running = False

    threading.Thread(target=worker, name="market-snapshot-refresh", daemon=True).start()
    return True


def build_market_overview_payload():
    """Read persisted real market data; never call a provider from an H5 GET."""
    cache_key = "standard_indices"
    cached = _load_market_snapshot_payload("market_overview", cache_key, MARKET_SNAPSHOT_CACHE_TTL_SECONDS)
    if cached is None:
        cached = _load_watchlist_cache("market_overview", cache_key, MARKET_SNAPSHOT_CACHE_TTL_SECONDS)
    if (
        isinstance(cached, dict)
        and isinstance(cached.get("items"), list)
        and cached.get("items")
        and str(cached.get("source") or "").lower() == "gangtise openapi"
        and cached.get("snapshot_version") == 6
    ):
        return cached
    stale = _load_market_snapshot_payload("market_overview", cache_key, 0)
    if stale is None:
        stale = _load_watchlist_cache("market_overview", cache_key, 0)
    if (
        isinstance(stale, dict)
        and isinstance(stale.get("items"), list)
        and stale.get("items")
        and str(stale.get("source") or "").lower() == "gangtise openapi"
        and stale.get("snapshot_version") == 6
    ):
        preserved = copy.deepcopy(stale)
        preserved["stale"] = True
        preserved["items"] = [{**item, "stale": True} if isinstance(item, dict) else item for item in preserved["items"]]
        preserved["message"] = "市场快照正在同步，当前展示最近一次已验证行情"
        return preserved
    return {"ok": True, "items": [], "source": "Gangtise OpenAPI", "refreshing": True, "message": "后台正在同步 Gangtise 市场快照"}


SHENWAN_LEVEL1_INDUSTRIES = (
    "农林牧渔", "基础化工", "钢铁", "有色金属", "电子", "汽车", "家用电器",
    "食品饮料", "纺织服饰", "轻工制造", "医药生物", "公用事业", "交通运输",
    "房地产", "商贸零售", "社会服务", "综合", "建筑材料", "建筑装饰", "电力设备",
    "国防军工", "计算机", "传媒", "通信", "银行", "非银金融", "机械设备",
    "煤炭", "石油石化", "环保", "美容护理",
)

# Verified by gangtise_industry_sector_report.html. These are quote symbols,
# not EDB indicator IDs; each symbol is queried through the daily K-line API.
GANGTISE_SHENWAN_LEVEL1_CODES = {
    "农林牧渔": "801010.SWI",
    "基础化工": "801030.SWI",
    "钢铁": "801040.SWI",
    "有色金属": "801050.SWI",
    "电子": "801080.SWI",
    "汽车": "801880.SWI",
    "家用电器": "801110.SWI",
    "食品饮料": "801120.SWI",
    "纺织服饰": "801130.SWI",
    "轻工制造": "801140.SWI",
    "医药生物": "801150.SWI",
    "公用事业": "801160.SWI",
    "交通运输": "801170.SWI",
    "房地产": "801180.SWI",
    "商贸零售": "801200.SWI",
    "社会服务": "801210.SWI",
    "综合": "801230.SWI",
    "建筑材料": "801710.SWI",
    "建筑装饰": "801720.SWI",
    "电力设备": "801730.SWI",
    "国防军工": "801740.SWI",
    "计算机": "801750.SWI",
    "传媒": "801760.SWI",
    "通信": "801770.SWI",
    "银行": "801780.SWI",
    "非银金融": "801790.SWI",
    "机械设备": "801890.SWI",
    "煤炭": "801950.SWI",
    "石油石化": "801960.SWI",
    "环保": "801970.SWI",
    "美容护理": "801980.SWI",
}
MARKET_SECTOR_OVERVIEW_CACHE_TTL_SECONDS = 5 * 60
# Industry overview data is an expensive daily snapshot. Reads within this
# window reuse the persisted PostgreSQL payload instead of calling Gangtise.
MARKET_SECTOR_SNAPSHOT_REFRESH_TTL_SECONDS = 24 * 60 * 60
MARKET_SNAPSHOT_CACHE_TTL_SECONDS = 26 * 60 * 60
MARKET_SECTOR_CATALOG_CACHE_TTL_SECONDS = 24 * 60 * 60

# The EDB catalogue uses a mixture of Wind and Shenwan names.  These aliases
# are only used to resolve a real indicator ID, never to manufacture a value.
SHENWAN_SECTOR_ALIASES = {
    "基础化工": ("基础化工", "化工"), "有色金属": ("有色金属", "有色"),
    "家用电器": ("家用电器", "家电"), "食品饮料": ("食品饮料", "食品", "饮料"),
    "纺织服饰": ("纺织服饰", "纺织", "服饰"), "轻工制造": ("轻工制造", "轻工"),
    "医药生物": ("医药生物", "医药"), "商贸零售": ("商贸零售", "商贸", "零售"),
    "社会服务": ("社会服务", "休闲服务"), "建筑材料": ("建筑材料", "建材"),
    "建筑装饰": ("建筑装饰", "建筑"), "电力设备": ("电力设备", "电气设备"),
    "国防军工": ("国防军工", "军工"), "非银金融": ("非银金融", "非银行金融"),
    "机械设备": ("机械设备", "机械"), "石油石化": ("石油石化", "石油"),
    "美容护理": ("美容护理", "美容"),
}


def _market_demo_data_enabled():
    # Market values must never be manufactured by a runtime flag. Tests and
    # demos use explicit fixtures at the call boundary instead.
    return False


def _build_market_demo_overview_payload():
    values = {
        "source_shanghai_index": (3867.03, 0.42), "source_shenzhen_index": (12105.88, 0.68),
        "source_hsi": (24836.12, -0.31), "source_hscei": (8920.44, -0.18),
        "source_hscci": (3642.08, 0.12), "source_dji": (43910.98, 0.27),
        "source_nasdaq": (18642.75, 0.51), "source_sp500": (6340.12, 0.35),
        "source_nikkei": (41820.44, -0.22),
    }
    items = []
    for indicator_code in MARKET_OVERVIEW_INDEX_CODES:
        entry = GANGTISE_INDICATOR_REGISTRY.get(indicator_code) or {}
        price, change_pct = values[indicator_code]
        previous = price / (1 + change_pct / 100)
        items.append({
            "indicator_code": indicator_code, "name": entry.get("indicator_name") or indicator_code,
            "code": entry.get("security_code") or "--", "market": entry.get("market") or "CN",
            "price": price, "change": round(price - previous, 2), "change_pct": change_pct,
            "updated_at": now_ts(), "available": True, "demo": True,
            "data_source": "演示数据（待真实快照）", "message": "",
        })
    return {"ok": True, "snapshot_version": 0, "items": items, "source": "演示数据", "demo": True, "updated_at": now_ts()}


def _build_market_demo_sector_payload():
    changes = [2.86, 2.41, 1.98, 1.72, 1.46, 1.18, 0.96, 0.74, 0.51, 0.28, -0.16, -0.38, -0.62, -0.85, -1.07, -1.29, -1.54, -1.82, -2.08, -2.36]
    items = []
    for index, sector in enumerate(SHENWAN_LEVEL1_INDUSTRIES):
        change_pct = changes[index % len(changes)]
        value = round(1000 + (len(sector) * 37) + index * 23, 2)
        items.append({
            "sector": sector, "code": f"DEMO{index + 1:02d}", "value": value,
            "change": round(value * change_pct / 100, 2), "change_pct": change_pct,
            "updated_at": now_ts(), "data_source": "演示数据（待真实快照）", "demo": True,
        })
    return {"ok": True, "snapshot_version": 0, "items": items, "total": len(items),
            "catalog_size": len(SHENWAN_LEVEL1_INDUSTRIES), "source": "演示数据", "demo": True, "updated_at": now_ts()}


def _resolve_gangtise_sector_catalog(candidates):
    """Resolve all available level-one industries from one EDB catalogue read."""
    rows = candidates if isinstance(candidates, list) else []
    selected = {}
    for sector in SHENWAN_LEVEL1_INDUSTRIES:
        aliases = SHENWAN_SECTOR_ALIASES.get(sector, (sector,))
        matches = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            name = str(item.get("indicatorName") or "").strip()
            indicator_id = str(item.get("indicatorId") or "").strip()
            if not indicator_id or "当日值" not in name:
                continue
            if any(alias in name for alias in aliases):
                matches.append(item)
        if matches:
            # Prefer the exact label, then a shorter canonical title.
            matches.sort(key=lambda item: (0 if sector in str(item.get("indicatorName") or "") else 1, len(str(item.get("indicatorName") or ""))))
            selected[sector] = matches[0]
    return selected


def _load_gangtise_sector_catalog():
    cached = _load_watchlist_cache("market_sector_catalog", "shenwan_level1", MARKET_SECTOR_CATALOG_CACHE_TTL_SECONDS)
    if isinstance(cached, dict) and isinstance(cached.get("items"), dict) and cached["items"]:
        return cached["items"], "cache"
    status, response, duration = post_gangtise_openapi_json(
        "/application/open-alternative/EDB/search",
        {"keyword": "Wind行业指数", "Limit": 500},
        timeout=30,
    )
    candidates = (response.get("data") or []) if isinstance(response, dict) else []
    selected = _resolve_gangtise_sector_catalog(candidates)
    if not is_gangtise_openapi_success(status, response) or not selected:
        message = str((response or {}).get("msg") or (response or {}).get("message") or "未找到申万一级行业 EDB 目录").strip()
        return {}, message
    _save_watchlist_cache(
        "market_sector_catalog",
        "shenwan_level1",
        {"items": selected, "provider": "Gangtise OpenAPI EDB", "duration_ms": int(duration or 0)},
    )
    return selected, "live"


def _normalize_gangtise_edb_batch_points(response, indicator_ids):
    data = response.get("data") if isinstance(response, dict) else {}
    headers = data.get("fieldList") if isinstance(data, dict) and isinstance(data.get("fieldList"), list) else []
    rows = data.get("dataList") if isinstance(data, dict) and isinstance(data.get("dataList"), list) else []
    date_index = next((index for index, field in enumerate(headers) if str(field).lower() in {"date", "tradedate", "time"}), -1)
    if date_index < 0:
        return {}
    indexes = {str(identifier): headers.index(identifier) for identifier in indicator_ids if identifier in headers}
    result = {identifier: [] for identifier in indexes}
    for row in rows:
        if not isinstance(row, list) or len(row) <= date_index:
            continue
        trade_date = str(row[date_index] or "").strip()
        if not trade_date:
            continue
        for identifier, value_index in indexes.items():
            if len(row) <= value_index:
                continue
            value = numeric_value(row[value_index])
            if value is not None:
                result[identifier].append({"date": trade_date, "close": value})
    for points in result.values():
        points.sort(key=lambda item: item["date"])
    return result


def _fetch_gangtise_sector_overview(start_date, end_date):
    """Fetch all 31 verified Shenwan level-one indices through Gangtise."""
    items = []
    missing = []
    for sector in SHENWAN_LEVEL1_INDUSTRIES:
        assert_admin_task_not_stopped("market_snapshot_sync")
        security_code = GANGTISE_SHENWAN_LEVEL1_CODES.get(sector)
        if not security_code:
            missing.append(f"{sector}(未配置代码)")
            continue
        series = fetch_gangtise_market_kline_series(
            "/application/open-quote/kline/daily",
            security_code,
            start_date=start_date,
            end_date=end_date,
            limit=240,
            timeout=30,
        )
        points = list(series.get("points") or []) if isinstance(series, dict) else []
        if not series.get("ok") or len(points) < 2:
            missing.append(f"{sector}({str(series.get('message') or '无有效日K')[:80]})")
            continue
        latest, previous = points[-1], points[-2]
        value = numeric_value(latest.get("close"))
        previous_value = numeric_value(previous.get("close"))
        if value is None or previous_value is None:
            missing.append(f"{sector}(数值无效)")
            continue
        change = value - previous_value
        items.append({
            "sector": sector,
            "code": security_code,
            "security_code": security_code,
            "indicator_name": f"申万一级行业指数:{sector}",
            "value": round(value, 2),
            "change": round(change, 4),
            "change_pct": round(change / previous_value * 100, 2) if previous_value else 0,
            "updated_at": str(latest.get("date") or "").strip(),
            "data_source": "Gangtise OpenAPI",
            "duration_ms": int(series.get("duration_ms") or 0),
        })
    errors = []
    if missing:
        errors.append("未返回有效申万行业：" + "、".join(missing[:10]))
    return items, errors


def _fetch_akshare_sector_overview(ak=None):
    """Read the 31 official Shenwan level-one index quotes from AKShare."""
    try:
        ak = ak or _load_akshare()
        frame = ak.index_realtime_sw(symbol="一级行业")
        name_column = _akshare_column(frame, ("指数名称", "行业名称", "名称", "name", "Name"))
        code_column = _akshare_column(frame, ("指数代码", "行业代码", "代码", "code", "Code"))
        value_column = _akshare_column(frame, ("最新价", "最新", "close", "Close"))
        previous_column = _akshare_column(frame, ("昨收盘", "昨收", "previous_close", "Previous Close"))
        if not name_column or not code_column or not value_column or not previous_column:
            return []
        items = []
        for _, row in frame.iterrows():
            sector_name = str(row.get(name_column) or "").strip()
            value = _akshare_float(row.get(value_column))
            previous_value = _akshare_float(row.get(previous_column))
            if sector_name not in SHENWAN_LEVEL1_INDUSTRIES or value is None or previous_value is None:
                continue
            change = value - previous_value
            items.append({
                "sector": sector_name,
                "code": str(row.get(code_column) or "").strip(),
                "indicator_name": f"申万一级行业指数:{sector_name}",
                "value": round(value, 2),
                "change": round(change, 2),
                "change_pct": round(change / previous_value * 100, 2) if previous_value else 0,
                "updated_at": now_ts(),
                "data_source": "AKShare 申万一级行业指数",
            })
        return items
    except Exception as exc:
        app.logger.warning("AKShare Shenwan level-one industry quote unavailable: %s", exc)
        return []


def build_market_sector_overview_payload(force_refresh=False):
    cache_key = "shenwan_level1"
    if not force_refresh:
        cached = _load_market_snapshot_payload("market_sector_overview", cache_key, MARKET_SNAPSHOT_CACHE_TTL_SECONDS)
        if cached is None:
            cached = _load_watchlist_cache("market_sector_overview", cache_key, MARKET_SNAPSHOT_CACHE_TTL_SECONDS)
        if isinstance(cached, dict) and isinstance(cached.get("items"), list) and cached["items"]:
            if cached.get("snapshot_version") == 6 and str(cached.get("source") or "").lower() == "gangtise openapi":
                return cached
    stale = _load_market_snapshot_payload("market_sector_overview", cache_key, 0)
    if stale is None:
        stale = _load_watchlist_cache("market_sector_overview", cache_key, 0)
    if isinstance(stale, dict) and isinstance(stale.get("items"), list) and stale.get("items"):
        source = str(stale.get("source") or "").lower()
        if source == "gangtise openapi" and stale.get("snapshot_version") == 6:
            preserved = copy.deepcopy(stale)
            preserved["stale"] = True
            preserved["message"] = "行业行情同步暂时失败，当前展示最近一次真实快照"
            return preserved
    return {"ok": True, "items": [], "total": 0, "catalog_size": len(SHENWAN_LEVEL1_INDUSTRIES), "source": "Gangtise OpenAPI", "refreshing": True, "message": "后台正在同步 Gangtise 申万行业快照"}


def normalize_watchlist_indicator_code(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    compact = raw.replace(" ", "")
    candidates = [raw, raw.upper(), raw.lower(), compact, compact.upper(), compact.lower()]
    for candidate in candidates:
        mapped = WATCHLIST_QUERY_ALIAS_MAP.get(candidate)
        if mapped and mapped in GANGTISE_INDICATOR_REGISTRY:
            return mapped
    slug_candidate = slugify_code(raw, "") if raw.lower().startswith("source_") else raw.lower()
    if slug_candidate in GANGTISE_INDICATOR_REGISTRY:
        return slug_candidate
    comparable = raw.replace(" ", "").replace("_", "").replace(".", "").lower()
    for indicator_code, entry in GANGTISE_INDICATOR_REGISTRY.items():
        for entry_candidate in [
            indicator_code,
            entry.get("indicator_name") or "",
            entry.get("security_code") or "",
            entry.get("tencent_symbol") or "",
            entry.get("search_keyword") or "",
        ]:
            normalized_entry = str(entry_candidate or "").replace(" ", "").replace("_", "").replace(".", "").lower()
            if normalized_entry and normalized_entry == comparable:
                return indicator_code
    return ""


def normalize_watchlist_detail_from_indicator(detail, indicator_code):
    if not isinstance(detail, dict) or not detail:
        return None
    normalized_code = normalize_watchlist_indicator_code(indicator_code) or slugify_code(indicator_code, "")
    registry_entry = GANGTISE_INDICATOR_REGISTRY.get(normalized_code) or {}
    normalized = copy.deepcopy(detail)
    name = str(
        normalized.get("name")
        or normalized.get("indicator_name")
        or registry_entry.get("indicator_name")
        or WATCHLIST_NAME_ALIAS_MAP.get(normalized_code)
        or normalized_code
    ).strip()
    history_kline = normalized.get("history_kline") if isinstance(normalized.get("history_kline"), dict) else {}
    candles = [
        item for item in (history_kline.get("candles") or [])
        if isinstance(item, dict) and str(item.get("date") or "").strip()
    ]
    history_series = [
        item for item in (normalized.get("history_series") or [])
        if isinstance(item, dict) and str(item.get("date") or "").strip()
    ]
    if not candles and history_series:
        candles = [
            {
                "date": str(item.get("date") or "").strip(),
                "open": NumberLike(item.get("value")),
                "high": NumberLike(item.get("value")),
                "low": NumberLike(item.get("value")),
                "close": NumberLike(item.get("value")),
            }
            for item in history_series
            if NumberLike(item.get("value")) > 0
        ]
        history_kline = build_real_indicator_kline_payload(candles) if candles else build_empty_kline_payload()
    latest_candle = candles[-1] if candles else {}
    previous_candle = candles[-2] if len(candles) >= 2 else latest_candle
    latest_value = NumberLike(normalized.get("numeric_value")) or NumberLike(normalized.get("value")) or NumberLike(latest_candle.get("close"))
    previous_value = NumberLike(previous_candle.get("close")) or latest_value
    change_value = round(latest_value - previous_value, 2) if latest_value is not None and previous_value is not None else 0
    change_pct = round((change_value / previous_value) * 100, 2) if previous_value else 0
    standard_code = str(registry_entry.get("security_code") or normalized.get("standard_code") or normalized.get("security_code") or "").strip().upper()
    display_code = standard_code or normalized_code
    normalized.update(
        {
            "id": normalized_code,
            "code": display_code,
            "indicator_code": normalized_code,
            "name": name,
            "market": str(registry_entry.get("market") or "CN").strip() or "CN",
            "security_code": standard_code,
            "standard_code": standard_code,
            "tencent_symbol": str(registry_entry.get("tencent_symbol") or normalized.get("tencent_symbol") or "").strip(),
            "price": round(latest_value, 2) if latest_value else 0,
            "change": change_value,
            "change_pct": change_pct,
            "industry": str(normalized.get("category") or registry_entry.get("category") or "数据湖指标").strip() or "数据湖指标",
            "focus": str(normalized.get("focus") or normalized.get("category") or registry_entry.get("indicator_name") or name).strip(),
            "kline": [
                {
                    "date": str(item.get("date") or "").strip(),
                    "open": round(NumberLike(item.get("open")), 2),
                    "high": round(NumberLike(item.get("high")), 2),
                    "low": round(NumberLike(item.get("low")), 2),
                    "close": round(NumberLike(item.get("close")), 2),
                }
                for item in candles[-60:]
                if NumberLike(item.get("close")) > 0
            ],
            "history_kline": history_kline if history_kline else build_empty_kline_payload(),
            "history_series": history_series,
            "data_source": str(normalized.get("data_source") or "indicator_lake").strip() or "indicator_lake",
            "source_type_label": str(normalized.get("source_type_label") or "大盘指数").strip() or "大盘指数",
            "standard_code": str(registry_entry.get("security_code") or "").strip(),
            "tencent_symbol": str(registry_entry.get("tencent_symbol") or "").strip(),
        }
    )
    return attach_watchlist_intraday(normalized)


def build_market_overview_index_detail(indicator_code):
    """Build an index detail from the same persisted market snapshot as H5."""
    history = _load_watchlist_cache("market_index_history", indicator_code, MARKET_SNAPSHOT_CACHE_TTL_SECONDS)
    points = list((history or {}).get("points") or []) if isinstance(history, dict) else []
    if len(points) < 2:
        return None
    entry = GANGTISE_INDICATOR_REGISTRY.get(indicator_code) or {}
    latest = points[-1]
    previous = points[-2]
    latest_close = numeric_value(latest.get("close"))
    previous_close = numeric_value(previous.get("close"))
    if latest_close is None or previous_close is None:
        return None
    history_series = [
        {
            "date": str(point.get("date") or "").strip(),
            "value": numeric_value(point.get("close")),
            "status": build_real_indicator_status(numeric_value(point.get("close")), numeric_value(points[index - 1].get("close")) if index else numeric_value(point.get("close"))),
        }
        for index, point in enumerate(points)
        if numeric_value(point.get("close")) is not None
    ]
    provider = str((history or {}).get("provider") or "市场快照").strip()
    return {
        "id": indicator_code,
        "indicator_code": indicator_code,
        "indicator_name": entry.get("indicator_name") or indicator_code,
        "name": entry.get("indicator_name") or indicator_code,
        "security_code": entry.get("security_code") or "",
        "standard_code": entry.get("security_code") or "",
        "market": entry.get("market") or "CN",
        "numeric_value": latest_close,
        "value": latest_close,
        "history_series": history_series,
        "history_kline": build_real_indicator_kline_payload(points),
        "data_source": provider,
        "provider": provider,
        "source_type": "market_index",
        "source_type_label": "大盘指数",
        "data_unavailable": False,
        "updated_at": str(latest.get("date") or "").strip(),
        "source_meta": {"provider": provider, "latest": latest, **((history or {}).get("source_meta") or {})},
        "assessment": f"{entry.get('indicator_name') or indicator_code} 已从 {provider} 获取真实历史序列，最新值为 {latest_close:.2f}。",
        "status": build_real_indicator_status(latest_close, previous_close),
        "alert": f"已按 {provider} 真实历史数据更新。",
        "history": [
            {"date": item["date"], "value": f"{numeric_value(item['value']):.2f}", "status": item["status"], "event": f"{provider} 真实历史点位"}
            for item in history_series[-6:]
        ],
        "data_mode": "real",
        "data_mode_label": f"{provider} 真实数据",
        "source_count": 1,
        "source_defs": [{
            "source_code": f"{indicator_code}_{slugify_code(provider, 'provider')}",
            "indicator_code": indicator_code,
            "provider": provider,
            "method": "Python SDK" if provider == "AKShare" else "OpenAPI",
        }],
        "fundamental": {
            "summary": "市场一览与详情均使用后台真实行情快照，不在前台实时请求外部行情。",
            "metrics": [
                {"label": "当前值", "value": f"{latest_close:.2f}", "note": f"{provider} 日线快照"},
                {"label": "日涨跌", "value": f"{latest_close - previous_close:+.2f}", "note": "相对上一交易日收盘"},
            ],
            "thesis": [],
        },
    }


def build_watchlist_indicator_detail(indicator_code, stock_name=""):
    normalized_code = normalize_watchlist_indicator_code(indicator_code)
    if not normalized_code:
        return None
    if normalized_code in MARKET_OVERVIEW_INDEX_CODES:
        detail = build_market_overview_index_detail(normalized_code)
        if detail:
            return normalize_watchlist_detail_from_indicator(detail, normalized_code)
        # The dashboard can already have a verified indicator-lake series while
        # the separate market snapshot task is still catching up. Keep both
        # entry points on the same canonical index instead of exposing source_*
        # as an unknown stock with a fabricated zero price.
        try:
            hub = get_indicator_hub_from_store_cached()
            for item in (hub.get("lake_items") or []):
                if str((item or {}).get("id") or "").strip() != normalized_code:
                    continue
                fallback = normalize_watchlist_detail_from_indicator(item, normalized_code)
                if fallback and (fallback.get("kline") or fallback.get("history_series")):
                    return fallback
        except Exception as exc:
            if not is_db_unavailable_error(exc):
                raise
        entry = GANGTISE_INDICATOR_REGISTRY.get(normalized_code) or {}
        return {
            "id": normalized_code,
            "indicator_code": normalized_code,
            "code": str(entry.get("security_code") or normalized_code).strip(),
            "standard_code": str(entry.get("security_code") or "").strip(),
            "security_code": str(entry.get("security_code") or "").strip(),
            "name": str(entry.get("indicator_name") or stock_name or normalized_code).strip(),
            "market": str(entry.get("market") or "CN").strip() or "CN",
            "industry": "大盘指数",
            "focus": str(entry.get("indicator_name") or stock_name or "大盘指数").strip(),
            "price": None,
            "change": None,
            "change_pct": None,
            "kline": [],
            "history_series": [],
            "history_kline": build_empty_kline_payload(),
            "data_source": "市场快照",
            "data_unavailable": True,
            "data_unavailable_message": "后台尚未完成该指数历史快照同步",
        }
    # Non-market indicators continue to read the persisted indicator lake
    # before attempting a controlled Gangtise recovery request.
    try:
        hub = get_indicator_hub_from_store_cached()
        for item in (hub.get("lake_items") or []):
            if str((item or {}).get("id") or "").strip() != normalized_code:
                continue
            detail = normalize_watchlist_detail_from_indicator(item, normalized_code)
            if detail and (detail.get("kline") or not detail.get("data_unavailable")):
                return detail
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
    detail = build_live_gangtise_indicator_detail(normalized_code)
    return normalize_watchlist_detail_from_indicator(detail, normalized_code) if detail else None


def _watchlist_cache_setting_key(prefix, value):
    normalized = slugify_code(str(value or "").strip(), prefix or "watchlist")
    return f"{prefix}:{normalized}"


def _load_market_snapshot_payload(snapshot_type, snapshot_key, ttl_seconds):
    """Load a market display snapshot from its dedicated database table."""
    try:
        db = get_db()
        row = db.execute(
            """
            SELECT payload_json, collected_at, updated_at
            FROM market_snapshot_payloads
            WHERE snapshot_type = ? AND snapshot_key = ?
            """,
            (snapshot_type, snapshot_key),
        ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    payload = safe_json_loads(row.get("payload_json"), {}) if isinstance(row, dict) else {}
    if not isinstance(payload, dict):
        return None
    captured_at = _parse_market_datetime((row.get("collected_at") if isinstance(row, dict) else "") or (row.get("updated_at") if isinstance(row, dict) else ""))
    if ttl_seconds and captured_at and (datetime.now() - captured_at).total_seconds() > ttl_seconds:
        return None
    return copy.deepcopy(payload)


def _save_market_snapshot_payload(snapshot_type, snapshot_key, payload):
    """Persist market UI snapshots without mixing them into app configuration."""
    if not isinstance(payload, dict):
        return False
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO market_snapshot_payloads (
                snapshot_type, snapshot_key, source, snapshot_version, payload_json, collected_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (snapshot_type, snapshot_key) DO UPDATE SET
                source = EXCLUDED.source,
                snapshot_version = EXCLUDED.snapshot_version,
                payload_json = EXCLUDED.payload_json,
                collected_at = EXCLUDED.collected_at,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                str(snapshot_type or "").strip(),
                str(snapshot_key or "").strip(),
                str(payload.get("source") or "").strip(),
                int(payload.get("snapshot_version") or 1),
                json.dumps(payload, ensure_ascii=False),
                str(payload.get("updated_at") or now_ts()),
            ),
        )
        db.commit()
    except Exception:
        return False
    return True


def _load_watchlist_cache(prefix, value, ttl_seconds):
    cache_key = _watchlist_cache_setting_key(prefix, value)
    try:
        db = get_db()
        row = db.execute(
            "SELECT setting_value, updated_at FROM app_settings WHERE setting_key = ?",
            (cache_key,),
        ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    payload = safe_json_loads(row.get("setting_value"), {}) if isinstance(row, dict) else {}
    cached_at_text = str(payload.get("cached_at") or row.get("updated_at") or "").strip()
    if cached_at_text:
        try:
            cached_at = datetime.fromisoformat(cached_at_text.replace("Z", "+00:00"))
            if cached_at.tzinfo is not None:
                cached_at = cached_at.astimezone().replace(tzinfo=None)
            if ttl_seconds and (datetime.now() - cached_at).total_seconds() > ttl_seconds:
                return None
        except Exception:
            return None
    return copy.deepcopy(payload.get("value"))


def _save_watchlist_cache(prefix, value, payload):
    cache_key = _watchlist_cache_setting_key(prefix, value)
    stored_value = json.dumps(
        {
            "cached_at": now_ts(),
            "value": payload,
        },
        ensure_ascii=False,
    )
    try:
        db = get_db()
        existing = db.execute(
            "SELECT setting_key FROM app_settings WHERE setting_key = ?",
            (cache_key,),
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE app_settings SET setting_value = ?, updated_at = ? WHERE setting_key = ?",
                (stored_value, now_ts(), cache_key),
            )
        else:
            db.execute(
                "INSERT INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                (cache_key, stored_value, now_ts()),
            )
        db.commit()
    except Exception:
        return False
    return True


def _normalize_watchlist_query_text(value):
    text = str(value or "").strip()
    return WATCHLIST_QUERY_ALIAS_MAP.get(text, text)


def _normalize_watchlist_comparable_code(value):
    normalized = str(value or "").strip().upper()
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]
    normalized = normalized.replace(" ", "")
    return normalized.lstrip("0") or "0"


def _build_gts_security_code(code, market):
    normalized_code = str(code or "").strip().upper()
    if not normalized_code:
        return ""
    if "." in normalized_code:
        return normalized_code
    suffix = str(market or "").strip().upper()
    if suffix in {"SH", "SZ", "BJ", "HK"}:
        return f"{normalized_code}.{suffix}"
    return normalized_code


def _normalize_watchlist_security_candidate(item):
    raw = item if isinstance(item, dict) else {}
    security_code = str(raw.get("gtsCode") or raw.get("security_code") or raw.get("code") or "").strip().upper()
    code = security_code.split(".", 1)[0] if "." in security_code else security_code
    suffix = security_code.split(".", 1)[1] if "." in security_code else str(raw.get("market") or "").strip().upper()
    name = str(raw.get("gtsName") or raw.get("name") or WATCHLIST_NAME_ALIAS_MAP.get(code) or code).strip()
    market = suffix if suffix in {"SH", "SZ", "BJ", "HK"} else _infer_watchlist_market(code)
    return {
        "code": code,
        "name": name or code,
        "market": market,
        "security_code": _build_gts_security_code(code, market),
        "category": str(raw.get("category") or "stock").strip() or "stock",
        "match_type": str(raw.get("matchType") or raw.get("match_type") or "").strip(),
        "match_score": NumberLike(raw.get("matchScore")),
        "source": str(raw.get("source") or "gangtise_openapi").strip() or "gangtise_openapi",
    }


def _search_security_master_candidates(query, top=8):
    """Resolve securities from the database master catalog before calling Gangtise."""
    normalized = str(query or "").strip()
    if not normalized:
        return []
    limit = max(1, min(int(top or 8), 50))
    pattern = f"%{normalized}%"
    try:
        rows = get_db().execute(
            """
            SELECT security_code, stock_code, name, market, industry,
                   security_type, search_aliases, source
            FROM security_master
            WHERE is_active = 1
              AND (
                stock_code = ? OR security_code = ? OR name = ?
                OR stock_code ILIKE ? OR security_code ILIKE ?
                OR name ILIKE ? OR COALESCE(search_aliases, '') ILIKE ?
              )
            ORDER BY
                CASE
                    WHEN stock_code = ? OR security_code = ? OR name = ? THEN 0
                    WHEN COALESCE(search_aliases, '') ILIKE ? THEN 1
                    ELSE 2
                END,
                name ASC
            LIMIT ?
            """,
            (
                normalized,
                normalized.upper(),
                normalized,
                pattern,
                pattern.upper(),
                pattern,
                pattern,
                normalized,
                normalized.upper(),
                normalized,
                pattern,
                limit,
            ),
        ).fetchall()
    except Exception as exc:
        # Older databases are upgraded by the numbered SQL migration. Keep
        # the existing seed/remote path usable while that migration rolls out.
        if not is_db_unavailable_error(exc):
            app.logger.debug("Security master lookup unavailable: %s", exc)
        return []

    items = []
    for row in rows or []:
        item = {
            "code": str(row.get("stock_code") or "").strip().upper(),
            "name": str(row.get("name") or "").strip(),
            "market": str(row.get("market") or "").strip().upper(),
            "security_code": str(row.get("security_code") or "").strip().upper(),
            "category": str(row.get("security_type") or "stock").strip() or "stock",
            "industry": str(row.get("industry") or "").strip(),
            "source": str(row.get("source") or "security_master").strip() or "security_master",
            "match_type": "security_master",
        }
        if item["code"] and item["name"] and item["security_code"]:
            items.append(item)
    return items


def _save_security_master_candidates(items):
    normalized_items = []
    for item in items or []:
        candidate = _normalize_watchlist_security_candidate(item)
        if candidate.get("code") and candidate.get("name") and candidate.get("security_code"):
            normalized_items.append(candidate)
    if not normalized_items:
        return
    try:
        db = get_db()
        now = now_ts()
        for item in normalized_items:
            db.execute(
                """
                INSERT INTO security_master
                    (security_code, stock_code, name, market, industry,
                     security_type, search_aliases, source, is_active,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT (security_code) DO UPDATE SET
                    stock_code = EXCLUDED.stock_code,
                    name = EXCLUDED.name,
                    market = EXCLUDED.market,
                    industry = CASE WHEN EXCLUDED.industry <> '' THEN EXCLUDED.industry ELSE security_master.industry END,
                    security_type = EXCLUDED.security_type,
                    source = EXCLUDED.source,
                    is_active = 1,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    item["security_code"],
                    item["code"],
                    item["name"],
                    item["market"],
                    str(item.get("industry") or "").strip(),
                    item.get("category") or "stock",
                    "",
                    item.get("source") or "gangtise_openapi",
                    now,
                    now,
                ),
            )
        db.commit()
    except Exception as exc:
        # Search must remain available if a legacy target has not run the
        # security-master migration yet; the remote result is still returned.
        if not is_db_unavailable_error(exc):
            app.logger.debug("Security master candidate persistence unavailable: %s", exc)


def _build_watchlist_seed_details():
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


def _search_local_watchlist_candidates(query, top=8):
    normalized = _normalize_watchlist_query_text(query)
    lowered = normalized.lower()
    comparable_query = _normalize_watchlist_comparable_code(normalized)
    database_items = _search_security_master_candidates(query, top=top)
    if database_items:
        return database_items[: max(1, int(top or 8))]
    details = _build_watchlist_seed_details()
    indicator_alias = normalize_watchlist_indicator_code(normalized)
    priority_index_codes = [
        "source_shanghai_index",
        "source_shenzhen_index",
        "source_hs300",
        "source_sse50",
        "source_kc50",
        "source_cyb",
        "source_zz500",
        "source_zz1000",
        "source_zz800",
        "source_a500",
        "source_zz2000",
        "source_hsi",
        "source_hscei",
        "source_hscci",
        "source_nikkei",
        "source_sp500",
        "source_nasdaq",
    ]
    priority_index_set = set(priority_index_codes)
    if indicator_alias and indicator_alias in GANGTISE_INDICATOR_REGISTRY:
        registry_entry = GANGTISE_INDICATOR_REGISTRY[indicator_alias]
        details.setdefault(
            indicator_alias,
            {
                "code": indicator_alias,
                "name": registry_entry.get("indicator_name") or indicator_alias,
                "market": "CN",
                "industry": registry_entry.get("category") or "数据湖指标",
                "focus": registry_entry.get("indicator_name") or registry_entry.get("search_keyword") or indicator_alias,
            },
        )
    if any(keyword in normalized for keyword in ("指数", "股指", "大盘", "标准指数", "标准库")):
        for indicator_code in priority_index_codes:
            registry_entry = GANGTISE_INDICATOR_REGISTRY.get(indicator_code)
            if not registry_entry:
                continue
            details.setdefault(
                indicator_code,
                {
                    "code": indicator_code,
                    "name": registry_entry.get("indicator_name") or indicator_code,
                    "market": "CN",
                    "industry": registry_entry.get("category") or "数据湖指标",
                    "focus": registry_entry.get("indicator_name") or registry_entry.get("search_keyword") or indicator_code,
                },
            )
        for indicator_code, registry_entry in GANGTISE_INDICATOR_REGISTRY.items():
            details.setdefault(
                indicator_code,
                {
                    "code": indicator_code,
                    "name": registry_entry.get("indicator_name") or indicator_code,
                    "market": "CN",
                    "industry": registry_entry.get("category") or "数据湖指标",
                    "focus": registry_entry.get("indicator_name") or registry_entry.get("search_keyword") or indicator_code,
                },
            )
    for code, preset in (WATCHLIST_DYNAMIC_DETAIL_PRESETS or {}).items():
        if not isinstance(preset, dict):
            continue
        details.setdefault(
            str(code or "").strip().upper(),
            {
                "code": str(code or "").strip().upper(),
                "name": str(preset.get("name") or code).strip(),
                "market": str(preset.get("market") or _infer_watchlist_market(code)).strip() or "CN",
                "industry": str(preset.get("industry") or "").strip(),
                "focus": str(preset.get("focus") or preset.get("industry") or "").strip(),
            },
        )
    scored = []
    for detail in (details or {}).values():
        if not isinstance(detail, dict):
            continue
        raw_code = str(detail.get("code") or "").strip()
        code = raw_code.upper()
        name = str(detail.get("name") or "").strip()
        if not code or not name:
            continue
        name_lower = name.lower()
        comparable_code = _normalize_watchlist_comparable_code(code)
        priority_rank = priority_index_codes.index(code.lower()) if code.lower() in priority_index_set else len(priority_index_codes) + 1
        score = None
        if comparable_code == comparable_query or code == normalized.upper():
            score = 0
        elif name == normalized:
            score = 1
        elif lowered and lowered in name_lower:
            score = 2
        elif comparable_query and comparable_query in comparable_code:
            score = 3
        elif any(keyword in normalized for keyword in ("指数", "股指", "大盘", "标准指数", "标准库")) and code.lower() in priority_index_set:
            score = 4
        if score is None:
            continue
        display_code = raw_code.lower() if raw_code.lower().startswith("source_") else code
        registry_entry = GANGTISE_INDICATOR_REGISTRY.get(display_code) if display_code.startswith("source_") else {}
        if registry_entry:
            display_code = str(registry_entry.get("security_code") or display_code).strip().upper()
        scored.append(
            (
                priority_rank,
                score,
                len(name),
                {
                    "code": display_code,
                    "indicator_code": raw_code.lower() if raw_code.lower().startswith("source_") else "",
                    "name": name,
                    "market": str(detail.get("market") or _infer_watchlist_market(code)).strip() or "CN",
                    "security_code": _build_gts_security_code(code, detail.get("market")),
                    "source": "local_watchlist",
                    "match_type": "local",
                    "match_score": max(0.0, 1.0 - score * 0.1),
                },
            )
        )
    scored.sort(key=lambda item: (item[0], item[1], item[2], item[3]["code"]))
    return [copy.deepcopy(item[3]) for item in scored[: max(1, int(top or 8))]]


def _search_remote_watchlist_candidates(query, top=8):
    normalized = _normalize_watchlist_query_text(query)
    if not normalized:
        return []
    cached = _load_watchlist_cache("watchlist_search_cache", normalized, WATCHLIST_SEARCH_CACHE_TTL_SECONDS)
    if isinstance(cached, list) and cached:
        return cached[: max(1, int(top or 8))]
    payload = {
        "keyword": normalized,
        "category": ["stock"],
        "top": max(1, min(int(top or 8), 12)),
    }
    status, response, _ = post_gangtise_openapi_json(
        "/application/open-reference/securities/search",
        payload,
        timeout=20,
    )
    rows = (((response.get("data") or {}).get("list") or []) if isinstance(response, dict) else []) if is_gangtise_openapi_success(status, response) else []
    items = [_normalize_watchlist_security_candidate(item) for item in rows if isinstance(item, dict)]
    if items:
        _save_security_master_candidates(items)
        _save_watchlist_cache("watchlist_search_cache", normalized, items)
    return items


def search_watchlist_candidates(query, top=8, include_remote=True):
    normalized = str(query or "").strip()
    if not normalized:
        return []
    merged = []
    seen = set()
    # Identity lookup is remote-first so a newly searched security gets the
    # latest Gangtise symbol/name mapping before the database fallback.
    if include_remote:
        for item in _search_remote_watchlist_candidates(normalized, top=top):
            code = str(item.get("code") or "").strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            merged.append(item)
            if len(merged) >= max(1, int(top or 8)):
                break
    if len(merged) < max(1, int(top or 8)):
        for item in _search_local_watchlist_candidates(normalized, top=top):
            code = str(item.get("code") or "").strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            merged.append(item)
            if len(merged) >= max(1, int(top or 8)):
                break
    return merged[: max(1, int(top or 8))]


def _resolve_watchlist_candidate(stock_code="", stock_name=""):
    query = str(stock_code or stock_name or "").strip()
    if not query:
        return None
    suggestions = search_watchlist_candidates(query, top=6, include_remote=True)
    if not suggestions:
        return None
    comparable_query = _normalize_watchlist_comparable_code(query)
    normalized_query = _normalize_watchlist_query_text(query).strip().upper()
    for item in suggestions:
        code = str(item.get("code") or "").strip().upper()
        name = str(item.get("name") or "").strip().upper()
        if code == normalized_query or _normalize_watchlist_comparable_code(code) == comparable_query or name == normalized_query:
            return copy.deepcopy(item)
    return copy.deepcopy(suggestions[0])


def _watchlist_detail_has_future_kline(detail):
    if not isinstance(detail, dict):
        return False
    cutoff_date = _current_cn_market_date()
    containers = [detail.get("kline"), detail.get("history_series")]
    history_kline = detail.get("history_kline") if isinstance(detail.get("history_kline"), dict) else {}
    containers.append(history_kline.get("candles"))
    for rows in containers:
        for item in rows if isinstance(rows, list) else []:
            if not isinstance(item, dict):
                continue
            trade_date = _parse_gangtise_trade_date(item.get("date"))
            if trade_date and trade_date > cutoff_date:
                return True
    return False


def _watchlist_detail_cache_is_usable(detail):
    if not isinstance(detail, dict) or not detail or detail.get("data_unavailable") is True:
        return False
    kline = detail.get("kline")
    if not isinstance(kline, list) or len(kline) < 2:
        return False
    return not _watchlist_detail_has_future_kline(detail)


def _build_watchlist_realtime_detail_from_candidate(candidate, stock_name=""):
    normalized = candidate if isinstance(candidate, dict) else {}
    security_code = str(normalized.get("security_code") or "").strip().upper()
    if not security_code:
        return _fetch_watchlist_realtime_detail_from_candidate(candidate, stock_name=stock_name)
    cached = _load_watchlist_cache("watchlist_detail_cache", security_code, WATCHLIST_DETAIL_CACHE_TTL_SECONDS)
    if _watchlist_detail_cache_is_usable(cached):
        app.logger.warning(
            "Watchlist detail cache hit security_code=%s code=%s kline_points=%s cache_source=%s",
            security_code,
            str(cached.get("code") or normalized.get("code") or "--").strip().upper(),
            len(cached.get("kline") or []),
            str(cached.get("data_source") or cached.get("source") or "--")[:80],
        )
        return attach_watchlist_intraday(cached)
    with _watchlist_detail_fetch_locks_guard:
        fetch_lock = _watchlist_detail_fetch_locks.setdefault(security_code, threading.Lock())
    with fetch_lock:
        cached = _load_watchlist_cache("watchlist_detail_cache", security_code, WATCHLIST_DETAIL_CACHE_TTL_SECONDS)
        if _watchlist_detail_cache_is_usable(cached):
            app.logger.warning(
                "Watchlist detail cache hit after wait security_code=%s code=%s kline_points=%s",
                security_code,
                str(cached.get("code") or normalized.get("code") or "--").strip().upper(),
                len(cached.get("kline") or []),
            )
            return attach_watchlist_intraday(cached)
        return _fetch_watchlist_realtime_detail_from_candidate(candidate, stock_name=stock_name)


def _fetch_watchlist_realtime_detail_from_candidate(candidate, stock_name=""):
    normalized = candidate if isinstance(candidate, dict) else {}
    security_code = str(normalized.get("security_code") or "").strip().upper()
    code = str(normalized.get("code") or "").strip().upper()
    name = str(normalized.get("name") or stock_name or WATCHLIST_NAME_ALIAS_MAP.get(code) or code).strip() or code
    if not security_code:
        app.logger.warning(
            "Watchlist realtime detail unavailable code=%s name=%s reason=security_code_unresolved",
            code or "--",
            name or "--",
        )
        return None
    market = str(normalized.get("market") or _infer_watchlist_market(code)).strip() or "CN"
    suffix = security_code.split(".", 1)[1] if "." in security_code else market
    if suffix == "HK":
        path = "/application/open-quote/kline-hk/daily"
    elif suffix in {"O", "N", "US"}:
        path = "/application/open-quote/kline-us/daily"
    else:
        path = "/application/open-quote/kline/daily"
    start_date, end_date = resolve_gangtise_market_date_window(days=180)
    series_result = fetch_gangtise_market_kline_series(
        path=path,
        security_code=security_code,
        start_date=start_date,
        end_date=end_date,
        limit=300,
        timeout=20,
    )
    points = series_result.get("points") or []
    if not series_result.get("ok") or len(points) < 2:
        app.logger.warning(
            "Watchlist realtime detail unavailable code=%s name=%s security_code=%s reason=daily_kline_not_ready http_status=%s points=%s message=%s",
            code or "--",
            name or "--",
            security_code,
            int(series_result.get("http_status") or 0),
            len(points),
            str(series_result.get("message") or "empty_daily_kline")[:240],
        )
        return None
    latest = points[-1]
    previous = points[-2]
    latest_close = NumberLike(latest.get("close"))
    previous_close = NumberLike(previous.get("close"))
    change_value = round(latest_close - previous_close, 2)
    change_pct = round((change_value / previous_close) * 100, 2) if previous_close else 0.0
    recent_points = points[-20:]
    recent_closes = [NumberLike(item.get("close")) for item in recent_points if isinstance(item, dict)]
    trend_anchor = recent_closes[0] if recent_closes else latest_close
    trend_delta = latest_close - trend_anchor
    interval_high = max([NumberLike(item.get("high")) for item in recent_points] + [latest_close])
    interval_low = min([NumberLike(item.get("low")) for item in recent_points] + [latest_close])
    interval_span_pct = round(((interval_high - interval_low) / interval_low) * 100, 2) if interval_low else 0.0
    market_label = {
        "SH": "A股主板",
        "SZ": "A股深市",
        "BJ": "北交所",
        "HK": "港股",
    }.get(market, "个股")
    industry = str(normalized.get("industry") or f"{market_label}个股").strip() or "个股跟踪"
    verdict = "偏强跟踪" if trend_delta > 0 and change_pct >= 0 else ("谨慎观察" if trend_delta < 0 and change_pct < 0 else "继续跟踪")
    detail = {
        "code": code,
        "name": name,
        "market": market,
        "price": round(latest_close, 2),
        "change": change_value,
        "change_pct": change_pct,
        "industry": industry,
        "focus": industry,
        "kline": [
            {
                "date": str(item.get("date") or "").strip(),
                "open": round(NumberLike(item.get("open")), 2),
                "high": round(NumberLike(item.get("high")), 2),
                "low": round(NumberLike(item.get("low")), 2),
                "close": round(NumberLike(item.get("close")), 2),
            }
            for item in recent_points
            if isinstance(item, dict)
        ],
        "history_kline": build_real_indicator_kline_payload(
            [
                {
                    "date": str(item.get("date") or "").strip(),
                    "open": round(NumberLike(item.get("open")), 2),
                    "high": round(NumberLike(item.get("high")), 2),
                    "low": round(NumberLike(item.get("low")), 2),
                    "close": round(NumberLike(item.get("close")), 2),
                }
                for item in points[-60:]
                if isinstance(item, dict)
            ]
        ),
        "history_series": [
            {
                "date": str(item.get("date") or "").strip(),
                "value": round(NumberLike(item.get("close")), 2),
                "status": build_real_indicator_status(
                    NumberLike(item.get("close")),
                    NumberLike(points[-60:][index - 1].get("close")) if index > 0 else NumberLike(item.get("close")),
                ),
            }
            for index, item in enumerate(points[-60:])
            if isinstance(item, dict)
        ],
        "authors": [],
        "fundamental": {
            "summary": f"当前已接入{name}的真实行情样本，先基于价格位置、波动区间和租户知识做第一轮基本面拆解；如需更深层业务与财务判断，可继续补充年报、纪要或研报。",
            "metrics": [
                {"label": "当前股价", "value": f"{round(latest_close, 2):.2f}", "note": "基于最近一个有效交易日收盘价"},
                {"label": "近20日区间", "value": f"{round(interval_low, 2):.2f} ~ {round(interval_high, 2):.2f}", "note": "帮助判断当前位置与压力支撑"},
                {"label": "近20日振幅", "value": f"{interval_span_pct:.2f}%", "note": "观察波动是否放大"},
                {"label": "近20日趋势", "value": "偏强" if trend_delta > 0 else ("偏弱" if trend_delta < 0 else "震荡"), "note": "结合最近收盘序列归纳"},
            ],
            "thesis": [
                f"{name}当前先以真实行情与阶段价格位置为起点做判断，避免继续使用演示随机价格。",
                "如果租户知识库暂未命中公司专属材料，Hermes 会先输出结构化研究框架，再等待补充证据。",
                "下一步应继续结合财报、行业景气和管理层纪要完善结论。",
            ],
        },
        "forecast": {
            "label": "基本面判断",
            "verdict": verdict,
            "confidence": "中",
            "band": f"当前更适合先结合近20日区间 {round(interval_low, 2):.2f} - {round(interval_high, 2):.2f} 判断位置，再补充业务、财务和行业证据。",
            "drivers": [
                {"label": "价格位置", "score": f"{change_pct:+.2f}%", "note": "最近一日相对前收盘变化"},
                {"label": "阶段波动", "score": f"{interval_span_pct:+.2f}%", "note": "近20日高低区间振幅"},
                {"label": "资料沉淀度", "score": "-0.40", "note": "若租户知识不足，需要继续补充财务与业务资料"},
            ],
        },
        "data_source": "gangtise_openapi",
        "source_meta": {
            "path": path,
            "security_code": security_code,
            "request_start_date": start_date,
            "request_end_date": end_date,
            "duration_ms": int(series_result.get("duration_ms") or 0),
            "message": str(series_result.get("message") or "").strip(),
        },
        "data_unavailable": False,
    }
    detail = attach_watchlist_intraday(detail)
    _save_watchlist_cache("watchlist_detail_cache", security_code, detail)
    return detail


def _resolve_watchlist_intraday_symbol(detail):
    if not isinstance(detail, dict):
        return ""
    source_meta = detail.get("source_meta") if isinstance(detail.get("source_meta"), dict) else {}
    standard_code = str(
        detail.get("standard_code")
        or detail.get("security_code")
        or source_meta.get("security_code")
        or source_meta.get("securityCode")
        or ""
    ).strip().upper()
    tencent_symbol = str(detail.get("tencent_symbol") or "").strip().lower()
    code = str(detail.get("code") or "").strip().upper()
    market = str(detail.get("market") or "").strip().upper()
    if re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", standard_code) or re.fullmatch(r"\d{5}\.HK", standard_code) or re.fullmatch(r"\d{6}\.CSI", standard_code):
        return standard_code
    if code and market in {"SH", "SZ"}:
        return f"{code}.{market}"
    if code and re.fullmatch(r"\d{6}", code):
        suffix = "SH" if code.startswith(("60", "68")) else ("SZ" if code.startswith(("00", "30")) else "SH")
        return f"{code}.{suffix}"
    tencent_match = re.fullmatch(r"(sh|sz)(\d{6})", tencent_symbol)
    if tencent_match:
        return f"{tencent_match.group(2)}.{tencent_match.group(1).upper()}"
    return ""


def _resolve_watchlist_intraday_trade_date(detail):
    """Use the latest real trading date outside the live China-market session."""
    if is_cn_stock_market_open():
        return ""
    source_meta = detail.get("source_meta") if isinstance(detail, dict) and isinstance(detail.get("source_meta"), dict) else {}
    candidates = [
        source_meta.get("latest", {}).get("date") if isinstance(source_meta.get("latest"), dict) else "",
        *(item.get("date") for item in (detail.get("kline") or []) if isinstance(item, dict)),
        *(item.get("date") for item in (detail.get("history_series") or []) if isinstance(item, dict)),
    ] if isinstance(detail, dict) else []
    dates = []
    for value in candidates:
        matched = re.search(r"\d{4}-\d{2}-\d{2}", str(value or ""))
        if matched:
            dates.append(matched.group(0))
    return max(dates) if dates else ""


def fetch_watchlist_intraday_series(detail, allow_provider_fetch=True):
    indicator_code = str((detail or {}).get("indicator_code") or (detail or {}).get("id") or "").strip()
    is_market_index = indicator_code in MARKET_OVERVIEW_INDEX_CODES
    if is_market_index:
        return {
            "ok": False,
            "available": False,
            "points": [],
            "message": "market_overview_intraday_disabled",
            "updated_at": "",
            "source": "market_overview",
        }
    symbol = _resolve_watchlist_intraday_symbol(detail)
    if not symbol:
        return {"ok": False, "available": False, "points": [], "message": "symbol_not_resolved", "updated_at": "", "source": "gangtise_openapi"}
    trade_date = _resolve_watchlist_intraday_trade_date(detail)
    cached = _load_gangtise_intraday_snapshot(symbol, trade_date)
    if cached:
        return cached
    if not allow_provider_fetch:
        return {"ok": False, "available": False, "points": [], "message": "intraday_snapshot_pending", "updated_at": "", "source": "gangtise_openapi_cache"}
    cache_identity = f"{symbol}:{trade_date or datetime.now().date().isoformat()}"
    with _intraday_fetch_locks_guard:
        fetch_lock = _intraday_fetch_locks.setdefault(cache_identity, threading.Lock())
    with fetch_lock:
        # Another detail request may have filled the PostgreSQL cache while this
        # request waited for the same symbol/date lock.
        cached = _load_gangtise_intraday_snapshot(symbol, trade_date)
        if cached:
            return cached
        akshare_error = ""
        if is_market_index:
            akshare_result = fetch_akshare_market_index_intraday(indicator_code, trade_date=trade_date)
            if akshare_result.get("available"):
                _save_watchlist_cache("market_index_intraday", indicator_code, akshare_result)
                return akshare_result
            akshare_error = str(akshare_result.get("message") or "").strip()
        result = fetch_gangtise_intraday_series(symbol, trade_date=trade_date)
        if not result.get("available") and akshare_error:
            result["message"] = f"{akshare_error}; {result.get('message') or 'Gangtise 未返回分钟数据'}"
        return result


def attach_watchlist_intraday(detail):
    if not isinstance(detail, dict) or not detail:
        return detail
    indicator_code = str(detail.get("indicator_code") or detail.get("id") or "").strip()
    if indicator_code in MARKET_OVERVIEW_INDEX_CODES:
        detail["intraday_supported"] = False
        detail["intraday_available"] = False
        detail["intraday_series"] = []
        detail["intraday_source"] = "market_overview"
        detail["intraday_updated_at"] = ""
        detail["intraday_message"] = "market_overview_intraday_disabled"
        return detail
    detail["intraday_supported"] = bool(_resolve_watchlist_intraday_symbol(detail))
    # The browser only reads our detail API. A missing PostgreSQL snapshot is
    # replenished here by the backend from the verified Gangtise minute K-line
    # endpoint, then reused from cache for the next fifteen minutes.
    result = fetch_watchlist_intraday_series(detail, allow_provider_fetch=True)
    detail["intraday_available"] = bool(result.get("available"))
    detail["intraday_series"] = copy.deepcopy(result.get("points") or [])
    detail["intraday_source"] = str(result.get("source") or "gangtise_openapi").strip() or "gangtise_openapi"
    detail["intraday_updated_at"] = str(result.get("updated_at") or "").strip()
    detail["intraday_trade_date"] = _resolve_watchlist_intraday_trade_date(detail) or _current_cn_market_date().isoformat()
    detail["intraday_message"] = str(result.get("message") or "").strip()
    return detail


def _merge_watchlist_detail_with_seed(seed_detail, realtime_detail=None, stock_code="", stock_name=""):
    seed = copy.deepcopy(seed_detail or {})
    realtime = copy.deepcopy(realtime_detail or {})
    code = str(realtime.get("code") or seed.get("code") or stock_code or "").strip().upper()
    name = str(realtime.get("name") or seed.get("name") or stock_name or code).strip() or code
    market = str(realtime.get("market") or seed.get("market") or _infer_watchlist_market(code)).strip() or "CN"
    industry = str(seed.get("industry") or realtime.get("industry") or "个股跟踪").strip() or "个股跟踪"
    focus = str(seed.get("focus") or realtime.get("focus") or industry).strip() or industry
    merged = seed
    merged.update(realtime)
    merged["code"] = code
    merged["name"] = name
    merged["market"] = market
    merged["industry"] = industry
    merged["focus"] = focus
    merged["authors"] = copy.deepcopy(seed.get("authors") or realtime.get("authors") or [])
    merged["fundamental"] = copy.deepcopy(seed.get("fundamental") or realtime.get("fundamental") or {"summary": "", "metrics": [], "thesis": []})
    merged["forecast"] = copy.deepcopy(seed.get("forecast") or realtime.get("forecast") or {"label": "基本面判断", "verdict": "继续跟踪", "confidence": "中", "band": "", "drivers": []})
    merged["kline"] = copy.deepcopy(realtime.get("kline") or merged.get("kline") or [])
    merged["history_kline"] = copy.deepcopy(realtime.get("history_kline") or build_empty_kline_payload())
    merged["history_series"] = copy.deepcopy(realtime.get("history_series") or merged.get("history_series") or [])
    merged["price"] = round(NumberLike(realtime.get("price")), 2)
    merged["change"] = round(NumberLike(realtime.get("change")), 2)
    merged["change_pct"] = round(NumberLike(realtime.get("change_pct")), 2)
    merged["data_source"] = str(realtime.get("data_source") or "gangtise_openapi").strip() or "gangtise_openapi"
    merged["data_unavailable"] = bool(realtime.get("data_unavailable"))
    return merged


def _build_watchlist_unavailable_detail(seed_detail=None, stock_code="", stock_name=""):
    seed = copy.deepcopy(seed_detail or {})
    code = str(seed.get("code") or stock_code or "").strip().upper()
    name = str(seed.get("name") or stock_name or code).strip() or code
    market = str(seed.get("market") or _infer_watchlist_market(code)).strip() or "CN"
    industry = str(seed.get("industry") or ("银行" if code.startswith(("600", "601", "603")) else "个股跟踪")).strip() or "个股跟踪"
    focus = str(seed.get("focus") or industry).strip() or industry
    # Static presets are only used for security metadata and research context.
    # Price/K-line values must never be fabricated when Gangtise has no data.
    preserved_price = None
    preserved_change = None
    preserved_change_pct = None
    kline_points = []
    history_kline = build_empty_kline_payload()
    history_series = []

    base_fundamental = copy.deepcopy(
        seed.get("fundamental")
        or {
            "summary": "Gangtise 行情当前暂未返回该股票的可用历史样本。现阶段仅保留研究框架，等待真实行情同步后再展示价格与 K 线。",
            "metrics": [],
            "thesis": [],
        }
    )
    summary_text = str(base_fundamental.get("summary") or "").strip()
    if "当前展示最近一次可用快照" not in summary_text:
        summary_text = (
            f"{summary_text} 当前展示最近一次可用快照，待 Gangtise 实时行情恢复后会自动刷新。".strip()
            if summary_text else
            "当前展示最近一次可用快照，待 Gangtise 实时行情恢复后会自动刷新。"
        )
    base_fundamental["summary"] = summary_text
    base_metrics = base_fundamental.get("metrics") if isinstance(base_fundamental.get("metrics"), list) else []
    if not any(str((item or {}).get("label") or "").strip() == "行情状态" for item in base_metrics if isinstance(item, dict)):
        base_metrics.insert(
            0,
            {
                "label": "行情状态",
                "value": "等待实时刷新",
                "note": "当前先展示最近一次可用快照，Gangtise 恢复后自动覆盖。",
            },
        )
    base_fundamental["metrics"] = base_metrics[:6]

    base_forecast = copy.deepcopy(
        seed.get("forecast")
        or {
            "label": "基本面判断",
            "verdict": "等待真实行情",
            "confidence": "低",
            "band": "",
            "drivers": [],
        }
    )
    forecast_band = str(base_forecast.get("band") or "").strip()
    if "最近一次可用快照" not in forecast_band:
        base_forecast["band"] = (
            f"{forecast_band} 当前先参考最近一次可用快照，待 Gangtise 实时行情恢复后再更新位置判断。".strip()
            if forecast_band else
            "当前先参考最近一次可用快照，待 Gangtise 实时行情恢复后再更新位置判断。"
        )
    return {
        "code": code,
        "name": name,
        "market": market,
        "price": preserved_price,
        "change": preserved_change,
        "change_pct": preserved_change_pct,
        "industry": industry,
        "focus": focus,
        "kline": kline_points,
        "history_kline": history_kline,
        "history_series": history_series,
        "authors": copy.deepcopy(seed.get("authors") or []),
        "fundamental": base_fundamental,
        "forecast": base_forecast,
        "data_source": "gangtise_openapi",
        "data_unavailable": True,
    }


def _build_watchlist_kline_series(stock_code, base_price):
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


def _infer_watchlist_market(stock_code):
    normalized = str(stock_code or "").strip().upper()
    if re.fullmatch(r"\d{5}", normalized):
        return "HK"
    if re.fullmatch(r"\d{6}", normalized):
        if normalized.startswith(("60", "68")):
            return "SH"
        if normalized.startswith(("00", "30")):
            return "SZ"
        if normalized.startswith(("43", "83", "87", "92")):
            return "BJ"
    return "CN"


def _build_dynamic_watchlist_detail(stock_code, stock_name=""):
    raw_code = str(stock_code or "").strip()
    indicator_code = normalize_watchlist_indicator_code(raw_code)
    normalized_code = indicator_code or raw_code.upper()
    if not normalized_code:
        return None
    if normalized_code in GANGTISE_INDICATOR_REGISTRY:
        detail = build_watchlist_indicator_detail(normalized_code, stock_name=stock_name)
        if isinstance(detail, dict) and detail:
            return detail
    resolved_candidate = _resolve_watchlist_candidate(stock_code=normalized_code, stock_name=stock_name)
    realtime_detail = _build_watchlist_realtime_detail_from_candidate(resolved_candidate, stock_name=stock_name)
    if isinstance(realtime_detail, dict) and realtime_detail:
        return realtime_detail
    preset = copy.deepcopy(WATCHLIST_DYNAMIC_DETAIL_PRESETS.get(normalized_code) or {})
    return _build_watchlist_unavailable_detail(preset, stock_code=normalized_code, stock_name=stock_name)


def _enrich_watchlist_details(details):
    normalized_details = copy.deepcopy(details or {})
    indicator_context = build_watchlist_indicator_context()
    for detail in normalized_details.values():
        research_industry = str(detail.get("research_industry") or detail.get("industry") or detail.get("focus") or "个股跟踪").strip() or "个股跟踪"
        canonical_industry = canonical_hot_industry_name(research_industry)
        detail["research_industry"] = research_industry
        detail["industry"] = canonical_industry
        detail["focus"] = canonical_industry
        signal_bundle = build_watchlist_signal_bundle(detail["code"], detail["name"], research_industry, indicator_context)
        detail["indicator_context"] = signal_bundle
        detail["alert_level"] = signal_bundle["board_alert_level"]
        detail["alert_text"] = sanitize_user_facing_source_text(signal_bundle["board_alert_text"], fallback="当前无明显预警")
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
        for metric in base_metrics:
            if not isinstance(metric, dict):
                continue
            metric["note"] = sanitize_user_facing_source_text(metric.get("note") or "", fallback=str(metric.get("note") or "").strip())
        fundamental["metrics"] = base_metrics[:6]
        base_thesis = fundamental.get("thesis") if isinstance(fundamental.get("thesis"), list) else []
        normalized_thesis = []
        seen_thesis = set()
        for item in base_thesis + [item for item in signal_bundle["thesis"] if item not in base_thesis]:
            text = sanitize_user_facing_source_text(item, fallback=str(item or "").strip())
            if not text or text in seen_thesis:
                continue
            seen_thesis.add(text)
            normalized_thesis.append(text)
        fundamental["thesis"] = normalized_thesis[:5]
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
    return normalized_details


def get_watchlist_detail_by_code(stock_code="", stock_name="", details_map=None, enrich=True):
    details = details_map if isinstance(details_map, dict) else gen_watchlist_details()
    raw_code = str(stock_code or "").strip()
    indicator_code = normalize_watchlist_indicator_code(raw_code)
    normalized_code = indicator_code or raw_code.upper()
    if normalized_code in GANGTISE_INDICATOR_REGISTRY:
        detail = build_watchlist_indicator_detail(normalized_code, stock_name=stock_name)
        if not detail:
            return None
        if not enrich:
            return copy.deepcopy(detail)
        return copy.deepcopy(detail)
    if not normalized_code and stock_name:
        normalized_code = _find_watchlist_code_from_text_local(stock_name)
    if not normalized_code:
        return None
    detail = copy.deepcopy((details or {}).get(normalized_code) or {})
    if detail:
        if not enrich:
            app.logger.warning(
                "Watchlist detail indicator result code=%s kline_points=%s data_unavailable=%s data_source=%s",
                normalized_code,
                len(detail.get("kline") or []) if isinstance(detail.get("kline"), list) else 0,
                bool(detail.get("data_unavailable")),
                str(detail.get("data_source") or "--")[:80],
            )
            return detail
        if detail.get("data_source") == "gangtise_openapi" or detail.get("data_unavailable"):
            app.logger.warning(
                "Watchlist detail seed result code=%s kline_points=%s data_unavailable=%s data_source=%s",
                normalized_code,
                len(detail.get("kline") or []) if isinstance(detail.get("kline"), list) else 0,
                bool(detail.get("data_unavailable")),
                str(detail.get("data_source") or "--")[:80],
            )
            return detail
        resolved_candidate = _resolve_watchlist_candidate(stock_code=normalized_code, stock_name=stock_name or detail.get("name") or normalized_code)
        realtime_detail = _build_watchlist_realtime_detail_from_candidate(resolved_candidate, stock_name=stock_name or detail.get("name") or normalized_code)
        merged = _merge_watchlist_detail_with_seed(
            detail,
            realtime_detail=realtime_detail,
            stock_code=normalized_code,
            stock_name=stock_name or detail.get("name") or normalized_code,
        ) if realtime_detail else _build_watchlist_unavailable_detail(detail, stock_code=normalized_code, stock_name=stock_name or detail.get("name") or normalized_code)
        result = copy.deepcopy((_enrich_watchlist_details({normalized_code: merged}).get(normalized_code)) or merged)
        app.logger.warning(
            "Watchlist detail merged result code=%s kline_points=%s data_unavailable=%s data_source=%s message=%s",
            normalized_code,
            len(result.get("kline") or []) if isinstance(result.get("kline"), list) else 0,
            bool(result.get("data_unavailable")),
            str(result.get("data_source") or "--")[:80],
            str(result.get("data_unavailable_message") or "")[:160],
        )
        return result
    fallback = _build_dynamic_watchlist_detail(normalized_code, stock_name=stock_name)
    if not fallback:
        return None
    result = copy.deepcopy((_enrich_watchlist_details({normalized_code: fallback}).get(normalized_code)) or fallback)
    app.logger.warning(
        "Watchlist detail fallback result code=%s kline_points=%s data_unavailable=%s data_source=%s message=%s",
        normalized_code,
        len(result.get("kline") or []) if isinstance(result.get("kline"), list) else 0,
        bool(result.get("data_unavailable")),
        str(result.get("data_source") or "--")[:80],
        str(result.get("data_unavailable_message") or "")[:160],
    )
    return result


def _normalize_watchlist_annotation_code(stock_code="", stock_name="", details_map=None):
    normalized_code = str(stock_code or "").strip().upper()
    if re.search(r"\b\d{5,6}\b", normalized_code):
        return re.search(r"\b\d{5,6}\b", normalized_code).group(0)
    candidate_name = str(stock_name or "").strip()
    details = details_map if isinstance(details_map, dict) else gen_watchlist_details()
    for code, detail in (details or {}).items():
        if normalized_code and normalized_code == str(code or "").strip().upper():
            return str(code or "").strip()
        if candidate_name and candidate_name == str((detail or {}).get("name") or "").strip():
            return str(code or "").strip()
        if normalized_code and normalized_code == str((detail or {}).get("name") or "").strip().upper():
            return str(code or "").strip()
    return normalized_code


def _find_watchlist_code_from_text_local(text):
    candidate = str(text or "").strip()
    if not candidate:
        return ""
    direct = re.search(r"\b\d{5,6}\b", candidate)
    if direct:
        return direct.group(0)
    normalized = _normalize_watchlist_query_text(candidate)
    if re.fullmatch(r"\d{5,6}", normalized):
        return normalized
    suggestions = search_watchlist_candidates(candidate, top=1, include_remote=False)
    if suggestions:
        return str((suggestions[0] or {}).get("code") or "").strip().upper()
    return ""


def _normalize_watchlist_annotation_row(row, detail=None):
    raw = dict(row or {}) if isinstance(row, dict) else {}
    candle = detail or {}
    stock_name = str(raw.get("stock_name") or candle.get("name") or raw.get("stock_code") or "").strip()
    stock_code = str(raw.get("stock_code") or "").strip().upper()
    title = str(raw.get("title") or "").strip()
    note = str(raw.get("note") or "").strip()
    trigger = str(raw.get("trigger") or "").strip()
    # Older rows used three authoring fields. Expose one canonical content
    # value so all downstream consumers can use the simplified model.
    content = note or "；".join(part for part in [title, trigger] if part)
    if title and note:
        content = "；".join(part for part in [title, note, trigger] if part)
    return {
        "id": raw.get("id"),
        "tenant_slug": str(raw.get("tenant_slug") or "").strip().lower(),
        "stock_code": stock_code,
        "stock_name": stock_name,
        "candle_index": int(raw.get("candle_index") or 0),
        "dateLabel": str(raw.get("candle_date") or "").strip(),
        "candle_date": str(raw.get("candle_date") or "").strip(),
        "title": title,
        "note": note,
        "trigger": trigger,
        "content": content,
        "updatedAt": str(raw.get("updated_at") or raw.get("created_at") or "").strip(),
        "createdAt": str(raw.get("created_at") or "").strip(),
        "open": round(float(raw.get("open_price") or 0), 2),
        "high": round(float(raw.get("high_price") or 0), 2),
        "low": round(float(raw.get("low_price") or 0), 2),
        "close": round(float(raw.get("close_price") or 0), 2),
        "created_by_name": str(raw.get("created_by_name") or "").strip(),
        "created_by_user_id": str(raw.get("created_by_user_id") or "").strip(),
        "created_by_role": str(raw.get("created_by_role") or "investor").strip().lower() or "investor",
        "source_client": str(raw.get("source_client") or "").strip() or "h5",
    }


def list_watchlist_kline_annotations(tenant_slug="", stock_code="", stock_name="", details_map=None, viewer_role="dav", viewer_profile_id=""):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    if not normalized_tenant:
        return []
    details = details_map if isinstance(details_map, dict) else gen_watchlist_details()
    normalized_code = _normalize_watchlist_annotation_code(stock_code=stock_code, stock_name=stock_name, details_map=details)
    if not normalized_code:
        return []
    rows = get_db().execute(
        """
        SELECT *
        FROM watchlist_kline_annotations
        WHERE tenant_slug = ? AND stock_code = ?
        ORDER BY candle_index ASC, updated_at ASC, id ASC
        """,
        (normalized_tenant, normalized_code),
    ).fetchall()
    detail = get_watchlist_detail_by_code(
        normalized_code,
        stock_name=stock_name,
        details_map=details,
        enrich=False,
    ) or {}
    normalized_rows = [_normalize_watchlist_annotation_row(row, detail=detail) for row in rows]
    normalized_role = str(viewer_role or "dav").strip().lower()
    normalized_profile_id = str(viewer_profile_id or "").strip()
    if normalized_role == "dav":
        return normalized_rows
    return [
        item for item in normalized_rows
        if item.get("created_by_role") == "dav" or (
            normalized_profile_id and item.get("created_by_user_id") == normalized_profile_id
        )
    ]


def save_watchlist_kline_annotation(
    tenant_slug="",
    stock_code="",
    stock_name="",
    candle_index=0,
    candle_date="",
    open_price=0,
    high_price=0,
    low_price=0,
    close_price=0,
    content="",
    title="",
    note="",
    trigger="",
    created_by_user_id="",
    created_by_name="",
    created_by_role="investor",
    source_client="h5",
):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    if not normalized_tenant:
        raise ValueError("tenant_slug_required")
    details = gen_watchlist_details()
    normalized_code = _normalize_watchlist_annotation_code(stock_code=stock_code, stock_name=stock_name, details_map=details)
    detail = get_watchlist_detail_by_code(normalized_code, stock_name=stock_name, details_map=details)
    if not detail:
        raise ValueError("watchlist_stock_not_found")
    content_text = str(content or "").strip()
    if not content_text:
        # Backward compatibility for existing clients that still send the
        # former title/note/trigger triplet.
        content_text = "；".join(
            part for part in [str(title or "").strip(), str(note or "").strip(), str(trigger or "").strip()]
            if part
        )
    if not content_text:
        raise ValueError("watchlist_annotation_content_required")
    try:
        normalized_index = max(0, int(candle_index or 0))
    except Exception:
        normalized_index = 0
    kline = detail.get("kline") if isinstance(detail.get("kline"), list) else []
    candle = kline[normalized_index] if normalized_index < len(kline) else {}
    now_text = now_ts()
    payload = {
        "tenant_slug": normalized_tenant,
        "stock_code": normalized_code,
        "stock_name": str(stock_name or detail.get("name") or normalized_code).strip() or normalized_code,
        "candle_index": normalized_index,
        "candle_date": str(candle_date or candle.get("date") or "").strip(),
        "open_price": float(open_price or candle.get("open") or 0),
        "high_price": float(high_price or candle.get("high") or 0),
        "low_price": float(low_price or candle.get("low") or 0),
        "close_price": float(close_price or candle.get("close") or 0),
        "title": "",
        "note": content_text[:2000],
        "trigger": "",
        "created_by_user_id": str(created_by_user_id or "").strip()[:120],
        "created_by_name": str(created_by_name or "").strip()[:120],
        "created_by_role": str(created_by_role or "investor").strip().lower() or "investor",
        "source_client": str(source_client or "h5").strip()[:40] or "h5",
        "created_at": now_text,
        "updated_at": now_text,
    }
    db = get_db()
    existing = db.execute(
        """
        SELECT id, created_at
        FROM watchlist_kline_annotations
        WHERE tenant_slug = ? AND stock_code = ? AND candle_index = ? AND created_by_user_id = ?
        """,
        (normalized_tenant, normalized_code, normalized_index, payload["created_by_user_id"]),
    ).fetchone()
    if existing:
        payload["id"] = existing.get("id")
        payload["created_at"] = str(existing.get("created_at") or now_text)
        db.execute(
            """
            UPDATE watchlist_kline_annotations
            SET stock_name = ?, candle_date = ?, open_price = ?, high_price = ?, low_price = ?, close_price = ?,
                title = ?, note = ?, trigger = ?, created_by_user_id = ?, created_by_name = ?, created_by_role = ?, source_client = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload["stock_name"],
                payload["candle_date"],
                payload["open_price"],
                payload["high_price"],
                payload["low_price"],
                payload["close_price"],
                payload["title"],
                payload["note"],
                payload["trigger"],
                payload["created_by_user_id"],
                payload["created_by_name"],
                payload["created_by_role"],
                payload["source_client"],
                payload["updated_at"],
                payload["id"],
            ),
        )
    else:
        db.execute(
            """
            INSERT INTO watchlist_kline_annotations (
                tenant_slug, stock_code, stock_name, candle_index, candle_date,
                open_price, high_price, low_price, close_price,
                title, note, trigger, created_by_user_id, created_by_name, created_by_role,
                source_client, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["tenant_slug"],
                payload["stock_code"],
                payload["stock_name"],
                payload["candle_index"],
                payload["candle_date"],
                payload["open_price"],
                payload["high_price"],
                payload["low_price"],
                payload["close_price"],
                payload["title"],
                payload["note"],
                payload["trigger"],
                payload["created_by_user_id"],
                payload["created_by_name"],
                payload["created_by_role"],
                payload["source_client"],
                payload["created_at"],
                payload["updated_at"],
            ),
        )
    db.commit()
    row = db.execute(
        """
        SELECT *
        FROM watchlist_kline_annotations
        WHERE tenant_slug = ? AND stock_code = ? AND candle_index = ? AND created_by_user_id = ?
        """,
        (normalized_tenant, normalized_code, normalized_index, payload["created_by_user_id"]),
    ).fetchone()
    return _normalize_watchlist_annotation_row(row, detail=detail)


def delete_watchlist_kline_annotation(tenant_slug="", stock_code="", stock_name="", annotation_id=None, candle_index=None, actor_profile_id=""):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    if not normalized_tenant:
        raise ValueError("tenant_slug_required")
    details = gen_watchlist_details()
    normalized_code = _normalize_watchlist_annotation_code(stock_code=stock_code, stock_name=stock_name, details_map=details)
    db = get_db()
    actor_id = str(actor_profile_id or "").strip()
    owner_clause = " AND created_by_user_id = ?" if actor_id else ""
    owner_params = (actor_id,) if actor_id else ()
    if annotation_id:
        db.execute(
            f"DELETE FROM watchlist_kline_annotations WHERE tenant_slug = ? AND id = ?{owner_clause}",
            (normalized_tenant, int(annotation_id), *owner_params),
        )
        db.commit()
        remaining = db.execute(
            f"SELECT id FROM watchlist_kline_annotations WHERE tenant_slug = ? AND id = ?{owner_clause}",
            (normalized_tenant, int(annotation_id), *owner_params),
        ).fetchone()
        if remaining and normalized_code and candle_index is not None:
            db.execute(
                f"DELETE FROM watchlist_kline_annotations WHERE tenant_slug = ? AND stock_code = ? AND candle_index = ?{owner_clause}",
                (normalized_tenant, normalized_code, int(candle_index or 0), *owner_params),
            )
            db.commit()
            remaining = db.execute(
                """
                SELECT id
                FROM watchlist_kline_annotations
                WHERE tenant_slug = ? AND stock_code = ? AND candle_index = ?{owner_clause}
                """,
                (normalized_tenant, normalized_code, int(candle_index or 0), *owner_params),
            ).fetchone()
        return remaining is None
    if normalized_code and candle_index is not None:
        db.execute(
            f"DELETE FROM watchlist_kline_annotations WHERE tenant_slug = ? AND stock_code = ? AND candle_index = ?{owner_clause}",
            (normalized_tenant, normalized_code, int(candle_index or 0), *owner_params),
        )
        db.commit()
        remaining = db.execute(
            """
            SELECT id
            FROM watchlist_kline_annotations
            WHERE tenant_slug = ? AND stock_code = ? AND candle_index = ?{owner_clause}
            """,
            (normalized_tenant, normalized_code, int(candle_index or 0), *owner_params),
        ).fetchone()
        return remaining is None
    raise ValueError("watchlist_annotation_target_required")


def build_watchlist_annotation_context(tenant_slug="", selected_watchlist=None, details_map=None):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    details = details_map if isinstance(details_map, dict) else gen_watchlist_details()
    items = []
    for raw_item in (selected_watchlist or []):
        normalized_code = _normalize_watchlist_annotation_code(stock_code=raw_item, stock_name=raw_item, details_map=details)
        if not normalized_code:
            continue
        detail = copy.deepcopy(get_watchlist_detail_by_code(normalized_code, stock_name=raw_item, details_map=details) or {})
        if not detail:
            continue
        try:
            annotations = list_watchlist_kline_annotations(normalized_tenant, stock_code=normalized_code, details_map=details) if normalized_tenant else []
        except Exception as exc:
            if not is_db_unavailable_error(exc):
                raise
            annotations = []
        annotation_summary = "；".join(
            f"{str(item.get('dateLabel') or item.get('candle_date') or '').strip()} {str(item.get('content') or item.get('note') or '').strip()}".strip()
            for item in annotations[:3]
            if str(item.get("content") or item.get("note") or "").strip()
        ).strip()
        detail["annotations"] = annotations
        detail["annotation_summary"] = annotation_summary
        detail["annotation_titles"] = [str(item.get("title") or "").strip() for item in annotations if str(item.get("title") or "").strip()][:6]
        detail["annotation_contents"] = [str(item.get("content") or item.get("note") or "").strip() for item in annotations if str(item.get("content") or item.get("note") or "").strip()][:6]
        items.append(detail)
    return items


def _normalize_watchlist_comment_row(row, detail=None, viewer_role="", viewer_profile_id=""):
    raw = dict(row or {}) if isinstance(row, dict) else {}
    candle = detail or {}
    created_by_role = str(raw.get("created_by_role") or "investor").strip().lower() or "investor"
    created_by_user_id = str(raw.get("created_by_user_id") or "").strip()
    normalized_viewer_role = str(viewer_role or "").strip().lower()
    normalized_viewer_profile_id = str(viewer_profile_id or "").strip()
    can_delete = False
    if normalized_viewer_role == "dav":
        can_delete = True
    elif normalized_viewer_role and normalized_viewer_profile_id and normalized_viewer_profile_id == created_by_user_id:
        can_delete = True
    return {
        "id": raw.get("id"),
        "tenant_slug": str(raw.get("tenant_slug") or "").strip().lower(),
        "stock_code": str(raw.get("stock_code") or candle.get("code") or "").strip().upper(),
        "stock_name": str(raw.get("stock_name") or candle.get("name") or raw.get("stock_code") or "").strip(),
        "comment_text": str(raw.get("comment_text") or "").strip(),
        "label_tags": [str(item).strip() for item in safe_json_loads(raw.get("label_tags_json"), []) if str(item).strip()],
        "keyword_tags": [str(item).strip() for item in safe_json_loads(raw.get("keyword_tags_json"), []) if str(item).strip()],
        "sentiment_label": str(raw.get("sentiment_label") or "").strip(),
        "topic_label": str(raw.get("topic_label") or "").strip(),
        "comment_summary": str(raw.get("comment_summary") or "").strip(),
        "labeling_source": str(raw.get("labeling_source") or "").strip(),
        "labeling_model_key": str(raw.get("labeling_model_key") or "").strip(),
        "labeling_model_name": str(raw.get("labeling_model_name") or "").strip(),
        "created_by_user_id": created_by_user_id,
        "created_by_name": str(raw.get("created_by_name") or "").strip() or created_by_user_id or "租户用户",
        "created_by_role": created_by_role,
        "created_by_role_label": "大V投顾" if created_by_role == "dav" else "粉丝用户",
        "source_client": str(raw.get("source_client") or "").strip() or "h5",
        "is_simulated": bool(raw.get("is_simulated")),
        "simulation_label": str(raw.get("simulation_label") or "").strip(),
        "simulation_batch_code": str(raw.get("simulation_batch_code") or "").strip(),
        "created_at": str(raw.get("created_at") or "").strip(),
        "updated_at": str(raw.get("updated_at") or raw.get("created_at") or "").strip(),
        "can_delete": can_delete,
    }


def _ensure_watchlist_comments_table(conn):
    global _watchlist_comments_schema_ready
    if _watchlist_comments_schema_ready:
        return
    with _watchlist_comments_schema_lock:
        if _watchlist_comments_schema_ready:
            return
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist_comments (
                    id BIGSERIAL PRIMARY KEY,
                    tenant_slug TEXT NOT NULL DEFAULT '',
                    stock_code TEXT NOT NULL DEFAULT '',
                    stock_name TEXT NOT NULL DEFAULT '',
                    comment_text TEXT NOT NULL DEFAULT '',
                    label_tags_json TEXT NOT NULL DEFAULT '[]',
                    keyword_tags_json TEXT NOT NULL DEFAULT '[]',
                    sentiment_label TEXT NOT NULL DEFAULT '',
                    topic_label TEXT NOT NULL DEFAULT '',
                    comment_summary TEXT NOT NULL DEFAULT '',
                    labeling_source TEXT NOT NULL DEFAULT '',
                    labeling_model_key TEXT NOT NULL DEFAULT '',
                    labeling_model_name TEXT NOT NULL DEFAULT '',
                    created_by_user_id TEXT NOT NULL DEFAULT '',
                    created_by_name TEXT NOT NULL DEFAULT '',
                    created_by_role TEXT NOT NULL DEFAULT 'investor',
                    source_client TEXT NOT NULL DEFAULT 'h5',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cur.execute(
                "ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS label_tags_json TEXT NOT NULL DEFAULT '[]'"
            )
            cur.execute(
                "ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS keyword_tags_json TEXT NOT NULL DEFAULT '[]'"
            )
            cur.execute(
                "ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS sentiment_label TEXT NOT NULL DEFAULT ''"
            )
            cur.execute(
                "ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS topic_label TEXT NOT NULL DEFAULT ''"
            )
            cur.execute(
                "ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS comment_summary TEXT NOT NULL DEFAULT ''"
            )
            cur.execute(
                "ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS labeling_source TEXT NOT NULL DEFAULT ''"
            )
            cur.execute(
                "ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS labeling_model_key TEXT NOT NULL DEFAULT ''"
            )
            cur.execute(
                "ALTER TABLE watchlist_comments ADD COLUMN IF NOT EXISTS labeling_model_name TEXT NOT NULL DEFAULT ''"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_watchlist_comments_tenant_stock_updated ON watchlist_comments(tenant_slug, stock_code, updated_at DESC, id DESC)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_watchlist_comments_tenant_user ON watchlist_comments(tenant_slug, created_by_user_id, updated_at DESC)"
            )
        conn.commit()
        _watchlist_comments_schema_ready = True


def _extract_watchlist_comment_keywords_by_rule(comment_text, stock_detail=None, limit=6):
    normalized = re.sub(r"\s+", " ", str(comment_text or "").strip())
    if not normalized:
        return []
    detail = stock_detail if isinstance(stock_detail, dict) else {}
    candidates = []
    for fixed_item in [
        str(detail.get("name") or "").strip(),
        str(detail.get("industry") or "").strip(),
        str(detail.get("focus") or "").strip(),
    ]:
        if fixed_item and fixed_item not in candidates:
            candidates.append(fixed_item)
    token_candidates = re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z][A-Za-z0-9.+-]{1,15}", normalized)
    stop_words = {
        "这个", "那个", "我们", "你们", "他们", "目前", "因为", "如果", "还是", "已经", "继续", "应该", "可以",
        "需要", "看到", "感觉", "这里", "一个", "这只", "股票", "公司", "板块", "市场", "今天", "最近", "以及",
        "但是", "还有", "就是", "自己", "觉得", "没有", "不是", "的话", "一下", "这个股", "一下子",
    }
    for item in token_candidates:
        token = str(item or "").strip()
        if len(token) < 2 or token in stop_words:
            continue
        if token not in candidates:
            candidates.append(token)
    return candidates[: max(1, int(limit or 6))]


def _label_watchlist_comment_without_llm(comment_text, stock_detail=None):
    normalized = re.sub(r"\s+", " ", str(comment_text or "").strip())
    detail = stock_detail if isinstance(stock_detail, dict) else {}
    keywords = _extract_watchlist_comment_keywords_by_rule(normalized, detail, limit=8)
    labels = []
    topic_label = "观点跟踪"
    sentiment_label = "中性"
    summary = normalized[:90]
    if any(keyword in normalized for keyword in ["风险", "回撤", "跌破", "谨慎", "承压", "减仓", "危险", "波动"]):
        sentiment_label = "谨慎"
        topic_label = "风险提示"
        labels.extend(["风险提示", "负向反馈"])
    elif any(keyword in normalized for keyword in ["看好", "增持", "突破", "修复", "超预期", "回暖", "加强", "机会"]):
        sentiment_label = "积极"
        topic_label = "机会判断"
        labels.extend(["机会判断", "正向反馈"])
    elif any(keyword in normalized for keyword in ["为什么", "请问", "？", "?", "怎么看", "能否", "是不是"]):
        sentiment_label = "追问"
        topic_label = "问题追踪"
        labels.extend(["问题追踪", "待验证"])
    if any(keyword in normalized for keyword in ["财报", "业绩", "利润", "收入", "毛利", "估值", "PE", "PB", "现金流"]):
        labels.append("基本面")
        if topic_label == "观点跟踪":
            topic_label = "基本面判断"
    if any(keyword in normalized for keyword in ["K线", "均线", "支撑", "压力", "放量", "缩量", "趋势", "形态"]):
        labels.append("技术面")
        if topic_label == "观点跟踪":
            topic_label = "走势观察"
    if any(keyword in normalized for keyword in ["催化", "政策", "订单", "回购", "纪要", "行业", "景气"]):
        labels.append("催化跟踪")
    labels = _unique_watchlist_texts(labels or ["观点跟踪"], limit=6)
    if not summary:
        summary = "围绕该股的阶段判断与追踪意见。"
    return {
        "labels": labels,
        "keywords": keywords,
        "sentiment_label": sentiment_label,
        "topic_label": topic_label,
        "summary": summary[:30],
        "source": "rule",
        "llm_model": {},
    }


def _unique_watchlist_texts(items, limit=12):
    seen = set()
    result = []
    for item in items if isinstance(items, list) else list(items or []):
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= max(1, int(limit or 12)):
            break
    return result


def list_watchlist_comments(
    tenant_slug="",
    stock_code="",
    stock_name="",
    viewer_role="",
    viewer_profile_id="",
    allow_fan_to_fan=True,
    details_map=None,
    limit=80,
):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    if not normalized_tenant:
        return []
    details = details_map if isinstance(details_map, dict) else gen_watchlist_details()
    normalized_code = _normalize_watchlist_annotation_code(stock_code=stock_code, stock_name=stock_name, details_map=details)
    if not normalized_code:
        return []
    normalized_viewer_role = str(viewer_role or "").strip().lower()
    normalized_viewer_profile_id = str(viewer_profile_id or "").strip()
    db = get_db()
    connection = getattr(db, "_connection", None)
    if connection is not None:
        _ensure_watchlist_comments_table(connection)
    rows = db.execute(
        """
        SELECT *
        FROM watchlist_comments
        WHERE tenant_slug = ? AND stock_code = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (normalized_tenant, normalized_code, max(1, min(int(limit or 80), 200))),
    ).fetchall()
    detail = get_watchlist_detail_by_code(
        normalized_code,
        stock_name=stock_name,
        details_map=details,
        enrich=False,
    ) or {}
    normalized_rows = [
        _normalize_watchlist_comment_row(
            row,
            detail=detail,
            viewer_role=normalized_viewer_role,
            viewer_profile_id=normalized_viewer_profile_id,
        )
        for row in rows
    ]
    if normalized_viewer_role == "dav" or allow_fan_to_fan:
        return normalized_rows
    visible_rows = []
    for item in normalized_rows:
        if str(item.get("created_by_role") or "").strip().lower() == "dav":
            visible_rows.append(item)
            continue
        if normalized_viewer_profile_id and str(item.get("created_by_user_id") or "").strip() == normalized_viewer_profile_id:
            visible_rows.append(item)
    return visible_rows


def save_watchlist_comment(
    tenant_slug="",
    stock_code="",
    stock_name="",
    comment_text="",
    created_by_user_id="",
    created_by_name="",
    created_by_role="investor",
    source_client="h5",
):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    if not normalized_tenant:
        raise ValueError("tenant_slug_required")
    details = gen_watchlist_details()
    normalized_code = _normalize_watchlist_annotation_code(stock_code=stock_code, stock_name=stock_name, details_map=details)
    detail = get_watchlist_detail_by_code(normalized_code, stock_name=stock_name, details_map=details)
    if not detail:
        raise ValueError("watchlist_stock_not_found")
    content = str(comment_text or "").strip()
    if not content:
        raise ValueError("watchlist_comment_text_required")
    created_by_user_id = str(created_by_user_id or "").strip()
    if not created_by_user_id:
        raise ValueError("watchlist_comment_user_required")
    normalized_role = str(created_by_role or "investor").strip().lower()
    if normalized_role not in {"investor", "dav"}:
        normalized_role = "investor"
    now_text = now_ts()
    payload = {
        "tenant_slug": normalized_tenant,
        "stock_code": normalized_code,
        "stock_name": str(stock_name or detail.get("name") or normalized_code).strip() or normalized_code,
        "comment_text": content[:1000],
        "created_by_user_id": created_by_user_id[:120],
        "created_by_name": str(created_by_name or created_by_user_id or "租户用户").strip()[:120] or "租户用户",
        "created_by_role": normalized_role,
        "source_client": str(source_client or "h5").strip()[:40] or "h5",
        "created_at": now_text,
        "updated_at": now_text,
    }
    label_result = _label_watchlist_comment_without_llm(payload["comment_text"], stock_detail=detail)
    payload["label_tags_json"] = json.dumps(label_result.get("labels") or [], ensure_ascii=False)
    payload["keyword_tags_json"] = json.dumps(label_result.get("keywords") or [], ensure_ascii=False)
    payload["sentiment_label"] = str(label_result.get("sentiment_label") or "").strip()[:40]
    payload["topic_label"] = str(label_result.get("topic_label") or "").strip()[:80]
    payload["comment_summary"] = str(label_result.get("summary") or "").strip()[:120]
    payload["labeling_source"] = "rule"
    payload["labeling_model_key"] = ""
    payload["labeling_model_name"] = ""
    db = get_db()
    _ensure_watchlist_comments_table(db._connection)
    db.execute(
        """
        INSERT INTO watchlist_comments (
            tenant_slug, stock_code, stock_name, comment_text,
            label_tags_json, keyword_tags_json, sentiment_label, topic_label, comment_summary,
            labeling_source, labeling_model_key, labeling_model_name,
            created_by_user_id, created_by_name, created_by_role, source_client,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["tenant_slug"],
            payload["stock_code"],
            payload["stock_name"],
            payload["comment_text"],
            payload["label_tags_json"],
            payload["keyword_tags_json"],
            payload["sentiment_label"],
            payload["topic_label"],
            payload["comment_summary"],
            payload["labeling_source"],
            payload["labeling_model_key"],
            payload["labeling_model_name"],
            payload["created_by_user_id"],
            payload["created_by_name"],
            payload["created_by_role"],
            payload["source_client"],
            payload["created_at"],
            payload["updated_at"],
        ),
    )
    db.commit()
    row = db.execute(
        """
        SELECT *
        FROM watchlist_comments
        WHERE tenant_slug = ? AND stock_code = ? AND created_by_user_id = ? AND created_at = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            payload["tenant_slug"],
            payload["stock_code"],
            payload["created_by_user_id"],
            payload["created_at"],
        ),
    ).fetchone()
    return _normalize_watchlist_comment_row(row, detail=detail, viewer_role=normalized_role, viewer_profile_id=payload["created_by_user_id"])


def build_watchlist_comment_analytics(tenant_slug="", limit=240):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    if not normalized_tenant:
        return {
            "summary": {"total_comments": 0, "dav_comments": 0, "investor_comments": 0, "stock_count": 0, "total_annotations": 0, "investor_annotations": 0, "dav_annotations": 0, "annotated_stock_count": 0},
            "keyword_cloud": [],
            "label_distribution": [],
            "sentiment_distribution": [],
            "topic_distribution": [],
            "sector_distribution": [],
            "sector_activity_distribution": [],
            "date_activity_distribution": [],
            "activity_records": [],
            "top_stocks": [],
            "recent_comments": [],
            "recent_annotations": [],
            "summary_text": "当前还没有足够的评论数据可供统计。",
        }
    try:
        db = get_db()
        _ensure_watchlist_comments_table(db._connection)
        rows = db.execute(
            """
            SELECT *
            FROM watchlist_comments
            WHERE tenant_slug = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (normalized_tenant, max(1, min(int(limit or 240), 1000))),
        ).fetchall()
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        return {
            "summary": {"total_comments": 0, "dav_comments": 0, "investor_comments": 0, "stock_count": 0, "total_annotations": 0, "investor_annotations": 0, "dav_annotations": 0, "annotated_stock_count": 0},
            "keyword_cloud": [],
            "label_distribution": [],
            "sentiment_distribution": [],
            "topic_distribution": [],
            "sector_distribution": [],
            "sector_activity_distribution": [],
            "date_activity_distribution": [],
            "activity_records": [],
            "top_stocks": [],
            "recent_comments": [],
            "recent_annotations": [],
            "fallback_mode": True,
            "summary_text": "当前还没有足够的评论数据可供统计。",
        }
    detail_map = gen_watchlist_details()
    annotation_rows = db.execute(
        """
        SELECT * FROM watchlist_kline_annotations
        WHERE tenant_slug = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (normalized_tenant, max(1, min(int(limit or 240), 1000))),
    ).fetchall()
    normalized_annotations = [
        _normalize_watchlist_annotation_row(
            row,
            detail=get_watchlist_detail_by_code(str((row or {}).get("stock_code") or "").strip(), details_map=detail_map) or {},
        )
        for row in annotation_rows
    ]
    normalized_rows = [
        _normalize_watchlist_comment_row(
            row,
            detail=get_watchlist_detail_by_code(str((row or {}).get("stock_code") or "").strip(), details_map=detail_map) or {},
            viewer_role="dav",
            viewer_profile_id="",
        )
        for row in rows
    ]
    label_counter = {}
    keyword_counter = {}
    sentiment_counter = {}
    topic_counter = {}
    sector_counter = {}
    stock_counter = {}
    activity_by_sector = {}
    activity_by_date = {}
    activity_records = []
    dav_comments = 0
    investor_comments = 0
    for item in normalized_rows:
        if str(item.get("created_by_role") or "").strip().lower() == "dav":
            dav_comments += 1
        else:
            investor_comments += 1
        stock_key = str(item.get("stock_code") or "").strip()
        if stock_key:
            stock_counter[stock_key] = stock_counter.get(stock_key, 0) + 1
            stock_detail = detail_map.get(stock_key) or {}
            sector_key = str(stock_detail.get("industry") or stock_detail.get("focus") or "").strip() or "未分类"
            sector_counter[sector_key] = sector_counter.get(sector_key, 0) + 1
        else:
            sector_key = "未分类"
        day_key = str(item.get("updated_at") or item.get("created_at") or "")[:10] or "未知日期"
        activity_by_sector.setdefault(sector_key, {"comments": 0, "annotations": 0})["comments"] += 1
        activity_by_date.setdefault(day_key, {"comments": 0, "annotations": 0})["comments"] += 1
        activity_records.append({
            "type": "comment",
            "type_label": "评论",
            "sector": sector_key,
            "day": day_key,
            "stock_name": item.get("stock_name") or item.get("stock_code") or "",
            "author": item.get("created_by_name") or "租户用户",
            "author_role": item.get("created_by_role_label") or "粉丝用户",
            "content": item.get("comment_text") or "",
            "timestamp": item.get("updated_at") or item.get("created_at") or "",
        })
        for tag in (item.get("label_tags") or []):
            label_counter[tag] = label_counter.get(tag, 0) + 1
        for keyword in (item.get("keyword_tags") or []):
            keyword_counter[keyword] = keyword_counter.get(keyword, 0) + 1
        sentiment = str(item.get("sentiment_label") or "").strip()
        if sentiment:
            sentiment_counter[sentiment] = sentiment_counter.get(sentiment, 0) + 1
        topic = str(item.get("topic_label") or "").strip()
        if topic:
            topic_counter[topic] = topic_counter.get(topic, 0) + 1

    def _sorted_counter(counter_map, label_key="label", value_key="value", limit_value=12):
        items = sorted(counter_map.items(), key=lambda pair: (-int(pair[1]), str(pair[0])))
        return [{label_key: key, value_key: value} for key, value in items[: max(1, int(limit_value or 12))] if str(key).strip()]

    top_stock_items = []
    for code, count in sorted(stock_counter.items(), key=lambda pair: (-int(pair[1]), str(pair[0]))):
        detail = detail_map.get(code) or {}
        top_stock_items.append({
            "stock_code": code,
            "stock_name": str(detail.get("name") or code).strip() or code,
            "industry": str(detail.get("industry") or detail.get("focus") or "").strip(),
            "value": count,
        })
    sector_items = _sorted_counter(sector_counter, label_key="label", value_key="value", limit_value=10)
    hot_sector = sector_items[0]["label"] if sector_items else ""
    annotation_stock_count = len({str(item.get("stock_code") or "").strip() for item in normalized_annotations if item.get("stock_code")})
    investor_annotations = sum(1 for item in normalized_annotations if item.get("created_by_role") != "dav")
    dav_annotations = len(normalized_annotations) - investor_annotations
    for item in normalized_annotations:
        stock_key = str(item.get("stock_code") or "").strip().upper()
        detail = detail_map.get(stock_key) or {}
        sector_key = str(detail.get("industry") or detail.get("focus") or "未分类").strip() or "未分类"
        day_key = str(item.get("updatedAt") or item.get("createdAt") or "")[:10] or "未知日期"
        activity_by_sector.setdefault(sector_key, {"comments": 0, "annotations": 0})["annotations"] += 1
        activity_by_date.setdefault(day_key, {"comments": 0, "annotations": 0})["annotations"] += 1
        activity_records.append({
            "type": "annotation",
            "type_label": "标注",
            "sector": sector_key,
            "day": day_key,
            "stock_name": item.get("stock_name") or stock_key,
            "author": item.get("created_by_name") or "租户用户",
            "author_role": "大V投顾" if item.get("created_by_role") == "dav" else "粉丝用户",
            "content": item.get("content") or item.get("note") or "",
            "timestamp": item.get("updatedAt") or item.get("createdAt") or "",
        })
    activity_sort_key = lambda value: (-int(value.get("comments") or 0) - int(value.get("annotations") or 0), str(value.get("label") or ""))
    sector_activity = [
        {"label": label, "comments": int(values.get("comments") or 0), "annotations": int(values.get("annotations") or 0)}
        for label, values in activity_by_sector.items()
    ]
    sector_activity.sort(key=activity_sort_key)
    date_activity = [
        {"label": label, "comments": int(values.get("comments") or 0), "annotations": int(values.get("annotations") or 0)}
        for label, values in activity_by_date.items()
    ]
    date_activity.sort(key=lambda value: str(value.get("label") or ""))
    return {
        "summary": {
            "total_comments": len(normalized_rows),
            "dav_comments": dav_comments,
            "investor_comments": investor_comments,
            "stock_count": len(stock_counter),
            "sector_count": len(sector_counter),
            "total_annotations": len(normalized_annotations),
            "investor_annotations": investor_annotations,
            "dav_annotations": dav_annotations,
            "annotated_stock_count": annotation_stock_count,
        },
        "keyword_cloud": _sorted_counter(keyword_counter, label_key="keyword", value_key="value", limit_value=24),
        "label_distribution": _sorted_counter(label_counter, label_key="label", value_key="value", limit_value=12),
        "sentiment_distribution": _sorted_counter(sentiment_counter, label_key="label", value_key="value", limit_value=8),
        "topic_distribution": _sorted_counter(topic_counter, label_key="label", value_key="value", limit_value=10),
        "sector_distribution": sector_items,
        "sector_activity_distribution": sector_activity[:20],
        "date_activity_distribution": date_activity[-31:],
        "activity_records": activity_records[:1000],
        "top_stocks": top_stock_items[:8],
        "recent_comments": normalized_rows[:20],
        "recent_annotations": normalized_annotations[:20],
        "hot_sector": hot_sector,
        "summary_text": (
            f"近 {len(normalized_rows)} 条评论中，粉丝主要关注 {hot_sector} 等行业板块。"
            if hot_sector else "当前评论已按行业板块完成归并统计。"
        ),
    }


def delete_watchlist_comment(
    tenant_slug="",
    stock_code="",
    stock_name="",
    comment_id=None,
    actor_role="",
    actor_profile_id="",
):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    if not normalized_tenant:
        raise ValueError("tenant_slug_required")
    try:
        normalized_id = int(comment_id or 0)
    except Exception:
        normalized_id = 0
    if normalized_id <= 0:
        raise ValueError("watchlist_comment_id_required")
    normalized_role = str(actor_role or "").strip().lower()
    normalized_profile_id = str(actor_profile_id or "").strip()
    db = get_db()
    _ensure_watchlist_comments_table(db._connection)
    row = db.execute(
        """
        SELECT *
        FROM watchlist_comments
        WHERE tenant_slug = ? AND id = ?
        """,
        (normalized_tenant, normalized_id),
    ).fetchone()
    if not row:
        return False
    owner_id = str(row.get("created_by_user_id") or "").strip()
    if normalized_role != "dav" and (not normalized_profile_id or normalized_profile_id != owner_id):
        raise ValueError("watchlist_comment_delete_forbidden")
    db.execute(
        "DELETE FROM watchlist_comments WHERE tenant_slug = ? AND id = ?",
        (normalized_tenant, normalized_id),
    )
    db.commit()
    remaining = db.execute(
        "SELECT id FROM watchlist_comments WHERE tenant_slug = ? AND id = ?",
        (normalized_tenant, normalized_id),
    ).fetchone()
    return remaining is None


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
    hydrated = {}
    for code, seed_detail in details.items():
        resolved_candidate = _resolve_watchlist_candidate(stock_code=code, stock_name=seed_detail.get("name") or code)
        realtime_detail = _build_watchlist_realtime_detail_from_candidate(resolved_candidate, stock_name=seed_detail.get("name") or code)
        if realtime_detail:
            hydrated[code] = _merge_watchlist_detail_with_seed(seed_detail, realtime_detail=realtime_detail, stock_code=code, stock_name=seed_detail.get("name") or code)
        else:
            hydrated[code] = _build_watchlist_unavailable_detail(seed_detail, stock_code=code, stock_name=seed_detail.get("name") or code)
    return _enrich_watchlist_details(hydrated)


def strip_watchlist_forecast_payload(detail):
    normalized = copy.deepcopy(detail or {})
    normalized.pop("forecast", None)
    return normalized


def apply_watchlist_feature_flags(detail, site_config=None):
    normalized = copy.deepcopy(detail or {})
    if not is_feature_enabled("stock_forecast", site_config):
        normalized = strip_watchlist_forecast_payload(normalized)
    return normalized

NEWS_LAKE_CACHE_KEY = "fundamental_news_lake:v1"
NEWS_SOURCE_STATUS_KEY = "fundamental_news_source_status:v1"
NEWS_LAKE_CACHE_TTL_SECONDS = 15 * 60
NEWS_SOURCE_MIN_ITEMS = 5
NEWS_AGGREGATION_WINDOW_DAYS = 3
NEWS_ALGORITHM_KEY_PREFIX = "tenant_news_aggregation_algorithm:"
NEWS_ALGORITHM_VERSION = "v3"
NEWS_RULE_PLAN_VERSION = "v1"
NEWS_MAJOR_SIGNAL_KEYWORDS = (
    "重大利好", "重大利空", "重大风险", "突发", "紧急", "重磅", "立案调查", "行政处罚",
    "停牌", "退市", "暴雷", "违约", "降准", "降息", "加息", "出口管制", "关税上调",
    "重大订单", "中标", "业绩预增", "业绩预亏", "回购", "增持", "减持", "并购重组", "重大资产重组",
)
NEWS_SECTOR_ALIASES = {
    "港股互联网": ("互联网", "平台经济", "港股", "腾讯", "阿里", "美团", "百度", "快手"),
    "半导体制造": ("半导体", "芯片", "集成电路", "晶圆", "存储", "光刻"),
    "高端白酒": ("白酒", "贵州茅台", "五粮液", "泸州老窖"),
    "动力电池": ("动力电池", "锂电", "新能源车", "宁德时代"),
    "银行": ("银行", "信贷", "息差", "存款", "贷款"),
}
DEFAULT_NEWS_RULE_PLAN = {
    "version": NEWS_RULE_PLAN_VERSION,
    "candidate_scope": {
        "watchlist_related": True,
        "major_events": True,
    },
    "priority_order": ["watchlist_sector", "major_market"],
    "filters": {
        "exclude_unrelated": True,
    },
    "presentation": {
        "home_limit": 10,
    },
    "diversity": {
        "max_per_source": 3,
        "max_per_group": 4,
    },
}
DEFAULT_NEWS_AGGREGATION_JS = """function rankNews(input) {
  const normalize = (value) => String(value || '').replace(/[\\s\\u3000·•/|_|-]+/g, ' ').trim();
  const compact = (value) => String(value || '').replace(/[\\s\\u3000·•/|_|-.]/g, '').trim();
  const tags = Array.isArray(input.item.tags) ? input.item.tags.map(normalize).filter(Boolean) : [];
  const text = normalize([input.item.title, input.item.content, input.item.summary].filter(Boolean).join(' '));
  const compactText = compact(text);
  const sectorTokens = Array.isArray(input.watchlistSectors) ? input.watchlistSectors.map(normalize).filter(Boolean) : [];
  const sectorAliases = {'港股互联网':['互联网','平台经济','港股','腾讯','阿里','美团','百度','快手'],'半导体制造':['半导体','芯片','集成电路','晶圆','存储','光刻'],'高端白酒':['白酒','贵州茅台','五粮液','泸州老窖'],'动力电池':['动力电池','锂电','新能源车','宁德时代'],'银行':['银行','信贷','息差','存款','贷款']};
  const symbolTokens = Array.isArray(input.watchlistSymbols) ? input.watchlistSymbols.map(normalize).filter(Boolean) : [];
  const majorKeywords = ['重大利好','重大利空','重大风险','突发','紧急','重磅','立案调查','行政处罚','停牌','退市','暴雷','违约','降准','降息','加息','出口管制','关税上调','重大订单','中标','业绩预增','业绩预亏','回购','增持','减持','并购重组','重大资产重组'];
  const sectorMatch = sectorTokens.some(tag => [tag, ...(sectorAliases[tag] || [])].some(term => text.includes(term)));
  const symbolMatch = symbolTokens.some(tag => text.includes(tag) || compactText.includes(compact(tag)));
  const majorSignal = Boolean(input.item.isMajorPositive || input.item.isMajorNegative)
    || majorKeywords.some(keyword => text.includes(keyword));
  return {
    score: ((sectorMatch || symbolMatch) ? 220 : 0) + (symbolMatch ? 65 : 0) + (majorSignal ? 100 : 0),
    bucket: (sectorMatch || symbolMatch) ? 'watchlist_sector' : (majorSignal ? 'major_market' : 'other'),
    reason: (sectorMatch || symbolMatch) ? '命中自选股行业板块或标的' : (majorSignal ? '命中社会性重大利好/利空或高影响事件' : '其他公开信息'),
    matched_topics: [
      ...new Set([
        ...(sectorTokens.filter(tag => [tag, ...(sectorAliases[tag] || [])].some(term => text.includes(term)))),
        ...(symbolTokens.filter(tag => text.includes(tag) || compactText.includes(compact(tag)))),
        ...(majorKeywords.filter(keyword => text.includes(keyword)))
      ])
    ]
  };
}"""
DEFAULT_NEWS_AGGREGATION_PROMPT = "先按自选股行业板块聚合，再看社会性重大利好/利空消息。普通用户只查看结果，大V可以在这里修改规则并预览效果。"
NEWS_SOURCE_WHITELIST = [
    # Frozen after the 2026-08-07 live validation. Runtime never promotes a new
    # source; a source must pass the five-item admission test first.
    {"code": "gov_cn_policy", "name": "中国政府网", "category": "政策", "source_group": "政策要闻", "url": "https://www.gov.cn/zhengce/index.htm", "indicator_code": "policy_news_heat", "validated_item_count": 20},
    {"code": "pboc_policy", "name": "中国人民银行", "category": "政策", "source_group": "政策要闻", "url": "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html", "indicator_code": "policy_news_heat", "validated_item_count": 18},
    {"code": "stats_macro", "name": "国家统计局", "category": "宏观", "source_group": "宏观要闻", "url": "https://www.stats.gov.cn/sj/zxfb/", "indicator_code": "macro_news_heat", "validated_item_count": 20},
    {"code": "csrc_regulation", "name": "中国证监会", "category": "监管", "source_group": "监管要闻", "url": "https://www.csrc.gov.cn/csrc/c101937/common_list.shtml", "indicator_code": "regulatory_event_count", "validated_item_count": 20},
    {"code": "cninfo_announcements", "name": "巨潮资讯", "category": "公司公告", "source_group": "公司公告", "url": "https://www.cninfo.com.cn/new/index", "indicator_code": "company_event_count", "validated_item_count": 19},
    {"code": "sse_disclosure", "name": "上海证券交易所", "category": "公司公告", "source_group": "公司公告", "url": "https://www.sse.com.cn/disclosure/listedinfo/announcement/", "indicator_code": "company_event_count", "validated_item_count": 11},
    {"code": "szse_disclosure", "name": "深圳证券交易所", "category": "公司公告", "source_group": "公司公告", "url": "https://www.szse.cn/disclosure/listed/notice/", "indicator_code": "company_event_count", "validated_item_count": 20},
]


def _extract_news_rule_plan_from_prompt(source_prompt):
    prompt = str(source_prompt or "").strip()
    plan = copy.deepcopy(DEFAULT_NEWS_RULE_PLAN)
    if not prompt:
        return plan
    compact_prompt = re.sub(r"\s+", "", prompt)
    if any(token in compact_prompt for token in ("重大消息优先", "重大新闻优先", "重大事件优先", "利好利空优先")):
        plan["priority_order"] = ["major_market", "watchlist_sector"]
    if any(token in compact_prompt for token in ("只看自选股", "仅看自选股", "只保留板块", "仅保留板块", "不补充重大")):
        plan["candidate_scope"]["major_events"] = False
    if any(token in compact_prompt for token in ("只看重大", "仅看重大", "只保留重大")):
        plan["candidate_scope"]["watchlist_related"] = False
        plan["candidate_scope"]["major_events"] = True
        plan["priority_order"] = ["major_market"]
    home_limit_match = re.search(r"(?:首页|主页|首屏)[^。；;，,]{0,16}?(\d{1,2})\s*条", compact_prompt)
    if not home_limit_match:
        home_limit_match = re.search(r"(?:只展示|展示|保留)[^。；;，,]{0,8}?(\d{1,2})\s*条", compact_prompt)
    if home_limit_match:
        plan["presentation"]["home_limit"] = max(1, min(20, int(home_limit_match.group(1))))
    source_cap_match = re.search(r"(?:每个来源|单一来源|同一来源)[^。；;，,]{0,8}?(\d{1,2})\s*条", compact_prompt)
    if source_cap_match:
        plan["diversity"]["max_per_source"] = max(1, min(10, int(source_cap_match.group(1))))
    group_cap_match = re.search(r"(?:每类|单一类型|同一类型)[^。；;，,]{0,8}?(\d{1,2})\s*条", compact_prompt)
    if group_cap_match:
        plan["diversity"]["max_per_group"] = max(1, min(10, int(group_cap_match.group(1))))
    if any(token in compact_prompt for token in ("不限制来源", "不限制类型", "不做来源去重")):
        plan["diversity"]["max_per_source"] = 10
        plan["diversity"]["max_per_group"] = 10
    return plan


def _normalize_news_rule_plan(payload=None, source_prompt=""):
    parsed_prompt_plan = _extract_news_rule_plan_from_prompt(source_prompt)
    raw = payload if isinstance(payload, dict) else {}
    plan = copy.deepcopy(DEFAULT_NEWS_RULE_PLAN)
    candidate_scope = raw.get("candidate_scope") if isinstance(raw.get("candidate_scope"), dict) else {}
    for key in ("watchlist_related", "major_events"):
        if key in candidate_scope:
            plan["candidate_scope"][key] = bool(candidate_scope[key])
        else:
            plan["candidate_scope"][key] = parsed_prompt_plan["candidate_scope"][key]
    if not any(plan["candidate_scope"].values()):
        plan["candidate_scope"]["watchlist_related"] = True
    allowed_buckets = {"watchlist_sector", "major_market"}
    raw_order = raw.get("priority_order") if isinstance(raw.get("priority_order"), list) else parsed_prompt_plan["priority_order"]
    priority_order = [str(item).strip() for item in raw_order if str(item).strip() in allowed_buckets]
    priority_order = list(dict.fromkeys(priority_order))
    for bucket, enabled in (("watchlist_sector", plan["candidate_scope"]["watchlist_related"]), ("major_market", plan["candidate_scope"]["major_events"])):
        if enabled and bucket not in priority_order:
            priority_order.append(bucket)
    plan["priority_order"] = [bucket for bucket in priority_order if (bucket != "watchlist_sector" or plan["candidate_scope"]["watchlist_related"]) and (bucket != "major_market" or plan["candidate_scope"]["major_events"])]
    filters = raw.get("filters") if isinstance(raw.get("filters"), dict) else {}
    plan["filters"]["exclude_unrelated"] = bool(filters.get("exclude_unrelated", parsed_prompt_plan["filters"]["exclude_unrelated"]))
    presentation = raw.get("presentation") if isinstance(raw.get("presentation"), dict) else {}
    home_limit = presentation.get("home_limit", parsed_prompt_plan["presentation"]["home_limit"])
    plan["presentation"]["home_limit"] = max(1, min(20, int(NumberLike(home_limit) or 10)))
    diversity = raw.get("diversity") if isinstance(raw.get("diversity"), dict) else {}
    for key in ("max_per_source", "max_per_group"):
        value = diversity.get(key, parsed_prompt_plan["diversity"][key])
        plan["diversity"][key] = max(1, min(10, int(NumberLike(value) or DEFAULT_NEWS_RULE_PLAN["diversity"][key])))
    plan["version"] = NEWS_RULE_PLAN_VERSION
    return plan


def _news_rule_plan_atoms(rule_plan):
    plan = _normalize_news_rule_plan(rule_plan)
    scope = plan["candidate_scope"]
    labels = []
    if scope["watchlist_related"]:
        labels.append({"group": "候选范围", "key": "watchlist_related", "label": "自选股关联"})
    if scope["major_events"]:
        labels.append({"group": "候选范围", "key": "major_events", "label": "重大事件补充"})
    labels.append({"group": "排序", "key": plan["priority_order"][0] if plan["priority_order"] else "watchlist_sector", "label": "行业优先" if plan["priority_order"][:1] == ["watchlist_sector"] else "重大事件优先"})
    labels.append({"group": "过滤", "key": "exclude_unrelated", "label": "过滤无关内容"})
    labels.append({"group": "展示", "key": "home_limit", "label": f"首页 {plan['presentation']['home_limit']} 条"})
    labels.append({"group": "配额", "key": "source_cap", "label": f"单一来源最多 {plan['diversity']['max_per_source']} 条"})
    labels.append({"group": "配额", "key": "group_cap", "label": f"单一类型最多 {plan['diversity']['max_per_group']} 条"})
    return labels


def _news_algorithm_setting_key(tenant_slug):
    normalized = str(tenant_slug or "").strip().lower() or "default"
    return f"{NEWS_ALGORITHM_KEY_PREFIX}{normalized}"


def _normalize_news_aggregation_algorithm(payload=None):
    raw = payload if isinstance(payload, dict) else {}
    strategy = str(raw.get("strategy") or "watchlist_sector_first").strip().lower()
    if strategy != "watchlist_sector_first":
        strategy = "watchlist_sector_first"
    source_prompt = str(raw.get("source_prompt") or "").strip()[:4000]
    rule_plan = _normalize_news_rule_plan(raw.get("rule_plan"), source_prompt=source_prompt)
    # Rule plans are the executable contract. script_js remains an internal,
    # compiled artifact for the Node ranking adapter and is never trusted from input.
    script = _build_news_aggregation_script_from_rule_plan(rule_plan)
    return {
        "version": NEWS_ALGORITHM_VERSION,
        "strategy": strategy,
        "script_js": script,
        "source_prompt": source_prompt,
        "rule_plan": rule_plan,
        "rule_atoms": _news_rule_plan_atoms(rule_plan),
        "updated_at": str(raw.get("updated_at") or "").strip(),
        "updated_by": str(raw.get("updated_by") or "system").strip()[:120],
    }


def _build_news_aggregation_script_from_rule_plan(rule_plan=None):
    plan = _normalize_news_rule_plan(rule_plan)
    priority = plan["priority_order"][:1]
    sector_weight = 120 if priority == ["watchlist_sector"] else 95
    symbol_weight = 35
    major_weight = 90 if priority == ["major_market"] else 80
    return (
        "function rankNews(input) {\n"
        "  const normalize = (value) => String(value || '').replace(/[\\s\\u3000·•/|_|-]+/g, ' ').trim();\n"
        "  const compact = (value) => String(value || '').replace(/[\\s\\u3000·•/|_|-.]/g, '').trim();\n"
        "  const tags = Array.isArray(input.item.tags) ? input.item.tags.map(normalize).filter(Boolean) : [];\n"
        "  const text = normalize([input.item.title, input.item.content, input.item.summary].filter(Boolean).join(' '));\n"
        "  const compactText = compact(text);\n"
        "  const sectorTokens = Array.isArray(input.watchlistSectors) ? input.watchlistSectors.map(normalize).filter(Boolean) : [];\n"
        "  const sectorAliases = {'港股互联网':['互联网','平台经济','港股','腾讯','阿里','美团','百度','快手'],'半导体制造':['半导体','芯片','集成电路','晶圆','存储','光刻'],'高端白酒':['白酒','贵州茅台','五粮液','泸州老窖'],'动力电池':['动力电池','锂电','新能源车','宁德时代'],'银行':['银行','信贷','息差','存款','贷款']};\n"
        "  const symbolTokens = Array.isArray(input.watchlistSymbols) ? input.watchlistSymbols.map(normalize).filter(Boolean) : [];\n"
        "  const majorKeywords = ['重大利好','重大利空','重大风险','突发','紧急','重磅','立案调查','行政处罚','停牌','退市','暴雷','违约','降准','降息','加息','出口管制','关税上调','重大订单','中标','业绩预增','业绩预亏','回购','增持','减持','并购重组','重大资产重组'];\n"
        "  const sectorMatch = sectorTokens.some(tag => [tag, ...(sectorAliases[tag] || [])].some(term => text.includes(term)));\n"
        "  const symbolMatch = symbolTokens.some(tag => text.includes(tag) || compactText.includes(compact(tag)));\n"
        "  const majorSignal = Boolean(input.item.isMajorPositive || input.item.isMajorNegative)\n"
        "    || majorKeywords.some(keyword => text.includes(keyword));\n"
        f"  const sectorWeight = {int(sector_weight)};\n"
        f"  const symbolWeight = {int(symbol_weight)};\n"
        f"  const majorWeight = {int(major_weight)};\n"
        "  return {\n"
        "    score: ((sectorMatch || symbolMatch) ? sectorWeight + 100 : 0) + (symbolMatch ? symbolWeight + 30 : 0) + (majorSignal ? majorWeight : 0),\n"
        "    bucket: (sectorMatch || symbolMatch) ? 'watchlist_sector' : (majorSignal ? 'major_market' : 'other'),\n"
        "    reason: (sectorMatch || symbolMatch) ? '命中自选股行业板块或标的' : (majorSignal ? '命中社会性重大利好/利空或高影响事件' : '其他公开信息'),\n"
        "    matched_topics: [\n"
        "      ...new Set([\n"
        "        ...sectorTokens.filter(tag => [tag, ...(sectorAliases[tag] || [])].some(term => text.includes(term))),\n"
        "        ...symbolTokens.filter(tag => text.includes(tag) || compactText.includes(compact(tag))),\n"
        "        ...majorKeywords.filter(keyword => text.includes(keyword))\n"
        "      ])\n"
        "    ]\n"
        "  };\n"
        "}"
    )


def _build_news_aggregation_script_from_prompt(source_prompt, fallback_script=None):
    return _build_news_aggregation_script_from_rule_plan(_extract_news_rule_plan_from_prompt(source_prompt))


def _find_tenant_news_algorithm_payload(tenant_slug):
    normalized = str(tenant_slug or "").strip().lower()
    if not normalized:
        return {}
    try:
        config = get_site_config()
        tenants = get_tenant_configs(config)
    except Exception:
        tenants = []
    for tenant in tenants if isinstance(tenants, list) else []:
        if isinstance(tenant, dict) and str(tenant.get("slug") or "").strip().lower() == normalized:
            payload = tenant.get("news_aggregation_algorithm")
            return payload if isinstance(payload, dict) else {}
    return {}


def normalize_news_aggregation_algorithm_payload(payload=None):
    return _normalize_news_aggregation_algorithm(payload)


def _news_aggregation_input_payload(item, sectors, symbols, tenant=None):
    text = " ".join(str(item.get(key) or "") for key in ("title", "content", "summary", "why", "tag", "source_group"))
    return {
        "tenant": {
            "slug": str((tenant or {}).get("slug") or "").strip().lower(),
            "name": str((tenant or {}).get("name") or "").strip(),
            "advisor": str((tenant or {}).get("advisor") or "").strip(),
        },
        "watchlistSectors": list(sectors or []),
        "watchlistSymbols": list(symbols or []),
        "item": {
            "title": str(item.get("title") or "").strip(),
            "content": str(item.get("content") or "").strip(),
            "summary": str(item.get("summary") or "").strip(),
            "text": text,
            "tags": [
                str(item.get(key) or "").strip()
                for key in ("category", "source_group", "tag")
                if str(item.get(key) or "").strip()
            ],
            "isMajorPositive": any(keyword in text for keyword in ("重大利好", "回购", "增持", "降息", "降准", "中标", "重大订单", "业绩预增", "并购重组")),
            "isMajorNegative": any(keyword in text for keyword in ("重大利空", "重大风险", "立案调查", "行政处罚", "停牌", "退市", "违约", "暴雷", "业绩预亏")),
            "publishedAt": str(item.get("published_at") or "").strip(),
            "sourceName": str(item.get("source_name") or "").strip(),
        },
    }


def _run_news_aggregation_js(script_js, item, sectors, symbols, tenant=None):
    script = str(script_js or "").strip()
    if not script or not shutil.which("node"):
        return None
    payload = _news_aggregation_input_payload(item, sectors, symbols, tenant=tenant)
    wrapper = (
        "const script = process.env.NEWS_SCRIPT || '';\n"
        "const payload = JSON.parse(process.env.NEWS_INPUT || '{}');\n"
        "try {\n"
        "  const rankNews = new Function('input', script + '\\nreturn typeof rankNews === \"function\" ? rankNews(input) : null;');\n"
        "  const result = rankNews(payload);\n"
        "  process.stdout.write(JSON.stringify(result || {}));\n"
        "} catch (error) {\n"
        "  process.stderr.write(String(error && error.message ? error.message : error));\n"
        "  process.exit(1);\n"
        "}\n"
    )
    env = os.environ.copy()
    env["NEWS_SCRIPT"] = script
    env["NEWS_INPUT"] = json.dumps(payload, ensure_ascii=False)
    try:
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", wrapper],
            env=env,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    raw_output = str(completed.stdout or "").strip()
    if not raw_output:
        return None
    try:
        parsed = json.loads(raw_output)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _fallback_news_rank(item, sectors, symbols):
    normalize = lambda value: str(value or "").replace("·", " ").replace("•", " ").replace("/", " ").replace("|", " ").replace("_", " ").replace("-", " ").strip()
    compact = lambda value: str(value or "").replace(" ", "").replace("·", "").replace("•", "").replace("/", "").replace("|", "").replace("_", "").replace("-", "").replace(".", "").strip()
    text = normalize(" ".join(str(item.get(key) or "") for key in ("title", "content", "summary", "why", "tag", "source_group")))
    sector_tokens = [normalize(sector) for sector in sectors if str(sector or "").strip()]
    symbol_tokens = [normalize(symbol) for symbol in symbols if str(symbol or "").strip()]
    def sector_matches(sector):
        aliases = NEWS_SECTOR_ALIASES.get(sector, ())
        return any(term and term in text for term in (sector, *aliases))

    matched_sectors = [sector for sector in sector_tokens if sector_matches(sector)]
    matched_symbols = [symbol for symbol in symbol_tokens if symbol and (symbol in text or compact(symbol) in compact(text))]
    major_signal = any(keyword in text for keyword in NEWS_MAJOR_SIGNAL_KEYWORDS)
    is_watchlist_related = bool(matched_sectors or matched_symbols)
    score = (220 if is_watchlist_related else 0) + (65 if matched_symbols else 0) + (100 if major_signal else 0)
    bucket = "watchlist_sector" if is_watchlist_related else ("major_market" if major_signal else "other")
    reason = "命中自选股行业板块或标的" if is_watchlist_related else ("命中社会性重大利好/利空或高影响事件" if major_signal else "其他公开信息")
    return {
        "score": score,
        "bucket": bucket,
        "reason": reason,
        "matched_topics": matched_sectors + matched_symbols,
    }


def load_tenant_news_aggregation_algorithm(tenant_slug=""):
    normalized = str(tenant_slug or "").strip().lower()
    payload = _find_tenant_news_algorithm_payload(normalized)
    if not isinstance(payload, dict) or not payload:
        try:
            payload = _load_json_app_setting(_news_algorithm_setting_key(normalized), {})
        except Exception:
            payload = {}
    return _normalize_news_aggregation_algorithm(payload)


def save_tenant_news_aggregation_algorithm(tenant_slug="", payload=None):
    normalized = str(tenant_slug or "").strip().lower()
    if not normalized:
        raise ValueError("tenant_slug_required")
    raw = payload if isinstance(payload, dict) else {}
    normalized_payload = _normalize_news_aggregation_algorithm(raw)
    normalized_payload["updated_at"] = now_ts()
    normalized_payload["updated_by"] = str(raw.get("updated_by") or "workbench").strip()[:120]
    _save_json_app_setting(_news_algorithm_setting_key(normalized), normalized_payload)
    try:
        site_config = get_site_config()
        tenants = site_config.get("tenants") if isinstance(site_config, dict) else []
        mutated = False
        for tenant in tenants if isinstance(tenants, list) else []:
            if isinstance(tenant, dict) and str(tenant.get("slug") or "").strip().lower() == normalized:
                tenant["news_aggregation_algorithm"] = copy.deepcopy(normalized_payload)
                mutated = True
                break
        if mutated:
            save_site_config(site_config)
    except Exception:
        pass
    return normalized_payload


def _news_watchlist_context(watchlist_details=None):
    values = watchlist_details.values() if isinstance(watchlist_details, dict) else (watchlist_details or [])
    sectors, symbols = set(), set()
    for detail in values:
        if not isinstance(detail, dict):
            continue
        for key in ("industry", "focus", "board", "sector"):
            value = str(detail.get(key) or "").strip()
            if len(value) >= 2:
                sectors.add(value)
        for key in ("name", "code", "stock_name", "stock_code"):
            value = str(detail.get(key) or "").strip()
            if value:
                symbols.add(value)
    return sorted(sectors, key=len, reverse=True), sorted(symbols, key=len, reverse=True)


def _news_watchlist_sector_groups(watchlist_details=None):
    values = watchlist_details.values() if isinstance(watchlist_details, dict) else (watchlist_details or [])
    groups = {}
    for detail in values or []:
        if not isinstance(detail, dict):
            continue
        sector = str(detail.get("industry") or detail.get("sector") or detail.get("focus") or detail.get("board") or "").strip()
        if not sector or len(sector) < 2:
            continue
        group = groups.setdefault(sector, {"sector": sector, "symbols": set()})
        for key in ("name", "code", "stock_name", "stock_code"):
            value = str(detail.get(key) or "").strip()
            if value:
                group["symbols"].add(value)
    normalized = []
    for sector, group in groups.items():
        normalized.append({"sector": sector, "symbols": sorted(group["symbols"], key=len, reverse=True)})
    return sorted(normalized, key=lambda item: item["sector"])


def _news_item_text(item):
    return " ".join(
        str(item.get(key) or "")
        for key in ("title", "content", "summary", "why", "tag", "source_group", "source_name")
    )


def _news_item_matches_sector_group(item, sector_group):
    if not isinstance(item, dict) or not isinstance(sector_group, dict):
        return False
    sector = str(sector_group.get("sector") or "").strip()
    if not sector:
        return False
    text = _news_item_text(item)
    compact_text = re.sub(r"[\s\u3000·•/|_\-.]+", "", text)
    candidates = [sector, *(NEWS_SECTOR_ALIASES.get(sector, ()) or []), *(sector_group.get("symbols") or [])]
    matched_topics = [
        str(topic or "").strip()
        for topic in (item.get("matched_topics") if isinstance(item.get("matched_topics"), list) else [])
        if str(topic or "").strip()
    ]
    for candidate in candidates:
        token = str(candidate or "").strip()
        if not token:
            continue
        compact_token = re.sub(r"[\s\u3000·•/|_\-.]+", "", token)
        if token in matched_topics or token in text or (compact_token and compact_token in compact_text):
            return True
    return False


def _rank_news_for_tenant(items, tenant=None, watchlist_details=None, algorithm_payload=None):
    tenant_slug = str((tenant or {}).get("slug") or "").strip().lower()
    raw_algorithm = algorithm_payload if isinstance(algorithm_payload, dict) else load_tenant_news_aggregation_algorithm(tenant_slug)
    algorithm = _normalize_news_aggregation_algorithm(raw_algorithm)
    sectors, symbols = _news_watchlist_context(watchlist_details)
    ranked = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        script_result = _run_news_aggregation_js(algorithm.get("script_js"), item, sectors, symbols, tenant=tenant)
        fallback_result = _fallback_news_rank(item, sectors, symbols)
        result = fallback_result if not isinstance(script_result, dict) else {
            "score": script_result.get("score"),
            "bucket": script_result.get("bucket"),
            "reason": script_result.get("reason"),
            "matched_topics": script_result.get("matched_topics"),
        }
        score = NumberLike(result.get("score"))
        if score == 0 and result.get("score") not in {0, "0", 0.0}:
            score = NumberLike(fallback_result.get("score"))
        bucket = str(result.get("bucket") or fallback_result.get("bucket") or "other").strip() or "other"
        reason = str(result.get("reason") or fallback_result.get("reason") or "其他公开信息").strip()
        matched_topics = result.get("matched_topics")
        if not isinstance(matched_topics, list):
            matched_topics = fallback_result.get("matched_topics") or []
        ranked_item = copy.deepcopy(item)
        ranked_item.update({
            "aggregation_bucket": bucket,
            "relevance_score": score,
            "matched_topics": matched_topics,
            "priority_reason": reason,
            "aggregation_algorithm_version": algorithm["version"],
            "aggregation_algorithm_script": algorithm.get("script_js") or "",
        })
        ranked.append(ranked_item)
    return sorted(ranked, key=lambda row: (int(row.get("relevance_score") or 0), str(row.get("published_at") or row.get("fetched_at") or "")), reverse=True)


def _parse_news_timestamp(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            try:
                parsed = datetime.strptime(raw[:10], "%Y-%m-%d")
            except ValueError:
                return None
    if parsed.tzinfo:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _filter_news_to_time_window(items, window_days=NEWS_AGGREGATION_WINDOW_DAYS, now=None):
    """Keep news in the inclusive +/- calendar-day window around now."""
    current = now or datetime.now()
    days = max(0, int(window_days or NEWS_AGGREGATION_WINDOW_DAYS))
    lower_bound = current - timedelta(days=days)
    upper_bound = current + timedelta(days=days)
    filtered = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        timestamp = _parse_news_timestamp(item.get("published_at") or item.get("fetched_at"))
        # Sources without a publication timestamp are retained because their
        # fetch timestamp is the only auditable time available in the lake.
        if timestamp is None or lower_bound <= timestamp <= upper_bound:
            filtered.append(item)
    return filtered


class _NewsAnchorCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._href = ""
        self._text = []
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a" or self._href:
            return
        attrs_map = dict(attrs)
        self._href = str(attrs_map.get("href") or "").strip()
        self._text = []

    def handle_data(self, data):
        if self._href:
            self._text.append(str(data or ""))

    def handle_endtag(self, tag):
        if tag.lower() != "a" or not self._href:
            return
        title = re.sub(r"\s+", " ", "".join(self._text)).strip()
        self.items.append({"href": self._href, "title": title})
        self._href = ""
        self._text = []


def _normalize_news_anchor_items(source, raw_html):
    parser = _NewsAnchorCollector()
    parser.feed(str(raw_html or "")[:1200000])
    root = source["url"]
    candidates = []
    seen = set()
    blocked_titles = {"首页", "返回", "登录", "注册", "搜索", "更多", "下一页", "上一页", "网站地图"}
    for item in parser.items:
        title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
        link = urljoin(root, str(item.get("href") or "").strip())
        if not title or len(title) < 8 or title in blocked_titles or not link.startswith(("http://", "https://")):
            continue
        if link == root or link in seen:
            continue
        seen.add(link)
        identity = hashlib.sha256(f"{link}|{title}".encode("utf-8")).hexdigest()[:24]
        candidates.append({
            "event_id": identity,
            "source_code": source["code"],
            "source_name": source["name"],
            "category": source["category"],
            "title": title[:180],
            "content": "该来源当前仅提供公告标题和原文链接，详细内容请查看原文。",
            "summary": "",
            "url": link[:500],
            "published_at": "",
            "fetched_at": now_ts(),
            "indicator_code": source["indicator_code"],
        })
        if len(candidates) >= 20:
            break
    return candidates


def _fetch_news_source(source):
    try:
        request = Request(source["url"], headers={"User-Agent": "GangtiseNewsLake/1.0"})
        with urlopen(request, timeout=8) as response:
            body = response.read(1200000).decode("utf-8", errors="ignore")
        items = _normalize_news_anchor_items(source, body)
        if len(items) < NEWS_SOURCE_MIN_ITEMS:
            return {"source": source, "included": False, "count": len(items), "reason": f"有效信息 {len(items)} 条，低于门槛 {NEWS_SOURCE_MIN_ITEMS} 条", "items": []}
        return {"source": source, "included": True, "count": len(items), "reason": "已达到来源纳入门槛", "items": items}
    except Exception as exc:
        return {"source": source, "included": False, "count": 0, "reason": str(exc)[:180], "items": []}


def _build_news_lake_indicators(items):
    counts = {}
    for item in items:
        code = str(item.get("indicator_code") or "news_event_count")
        counts[code] = counts.get(code, 0) + 1
    return [{"indicator_code": code, "value": count, "unit": "条/批次", "updated_at": now_ts(), "is_simulated": False} for code, count in sorted(counts.items())]


def _load_news_lake_cache(allow_stale=False):
    payload = _load_json_app_setting(NEWS_LAKE_CACHE_KEY, {})
    cached_at = str(payload.get("cached_at") or "").strip() if isinstance(payload, dict) else ""
    if not cached_at:
        return None
    try:
        cached_dt = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
        if cached_dt.tzinfo:
            cached_dt = cached_dt.astimezone().replace(tzinfo=None)
        if (datetime.now() - cached_dt).total_seconds() > NEWS_LAKE_CACHE_TTL_SECONDS and not allow_stale:
            return None
    except Exception:
        return None
    return payload


def _news_lake_payload_has_items(payload):
    return bool(isinstance(payload, dict) and payload.get("items"))


def _load_active_news_source_whitelist():
    try:
        state = _load_json_app_setting(NEWS_SOURCE_STATUS_KEY, {})
    except Exception:
        state = {}
    excluded_codes = {
        str(code).strip()
        for code in (state.get("excluded_codes") or [])
        if str(code).strip()
    } if isinstance(state, dict) else set()
    source_map = {str(source.get("code") or "").strip(): source for source in NEWS_SOURCE_WHITELIST}
    return [
        copy.deepcopy(source)
        for source in NEWS_SOURCE_WHITELIST
        # Only a source whose catalog admission count is below the threshold
        # is permanently excluded. Older runtime states may contain codes
        # written during a transient network failure; those must recover.
        if not (
            source["code"] in excluded_codes
            and int(source.get("validated_item_count") or 0) < NEWS_SOURCE_MIN_ITEMS
        )
        and int(source.get("validated_item_count") or 0) >= NEWS_SOURCE_MIN_ITEMS
    ]


def _persist_news_source_exclusions(results):
    newly_excluded = {
        result["source"]["code"]
        for result in results
        if not result.get("included") and int(result.get("count") or 0) < NEWS_SOURCE_MIN_ITEMS
        and str(result.get("reason") or "").startswith("有效信息")
    }
    if not newly_excluded:
        return
    try:
        state = _load_json_app_setting(NEWS_SOURCE_STATUS_KEY, {})
        excluded_codes = {
            str(code).strip()
            for code in (state.get("excluded_codes") or [])
            if str(code).strip()
        } if isinstance(state, dict) else set()
        _save_json_app_setting(
            NEWS_SOURCE_STATUS_KEY,
            {
                "excluded_codes": sorted(excluded_codes | newly_excluded),
                "updated_at": now_ts(),
                "rule": f"exclude source permanently after fewer than {NEWS_SOURCE_MIN_ITEMS} valid items",
            },
        )
    except Exception:
        pass


def _aggregate_real_news_sources(force_refresh=False):
    cached = _load_news_lake_cache()
    if cached and not force_refresh:
        return cached
    results = []
    active_sources = _load_active_news_source_whitelist()
    if not active_sources:
        stale_cached = _load_news_lake_cache(allow_stale=True)
        if _news_lake_payload_has_items(stale_cached):
            return stale_cached
        return {"cached_at": now_ts(), "items": [], "indicators": [], "sources": []}
    with ThreadPoolExecutor(max_workers=min(7, len(active_sources))) as executor:
        futures = [executor.submit(_fetch_news_source, source) for source in active_sources]
        for future in as_completed(futures):
            results.append(future.result())
    _persist_news_source_exclusions(results)
    included = [item for item in results if item.get("included")]
    items = []
    for result in included:
        source = result["source"]
        for item in result.get("items") or []:
            item["source_code"] = source["code"]
            item["source_name"] = source["name"]
            item["tag"] = source["source_group"]
            item["source_group"] = source["source_group"]
            item["time"] = item.get("published_at") or "来源未提供发布时间"
            item["hot"] = False
            item["why"] = f"来自{source['name']}，已完成公开信息清洗并达到每个来源至少 {NEWS_SOURCE_MIN_ITEMS} 条的纳入标准。"
            items.append(item)
    items = sorted(items, key=lambda item: (item.get("published_at") or item.get("fetched_at") or ""), reverse=True)[:60]
    payload = {
        "cached_at": now_ts(),
        "items": items,
        "indicators": _build_news_lake_indicators(items),
        "sources": [
            {"code": result["source"]["code"], "name": result["source"]["name"], "category": result["source"]["category"], "included": bool(result.get("included")), "count": int(result.get("count") or 0), "reason": result.get("reason") or ""}
            for result in sorted(results, key=lambda item: item["source"]["code"])
        ],
    }
    if not items:
        stale_cached = _load_news_lake_cache(allow_stale=True)
        if _news_lake_payload_has_items(stale_cached):
            return stale_cached
    try:
        _save_json_app_setting(NEWS_LAKE_CACHE_KEY, payload)
    except Exception:
        pass
    return payload


def build_admin_news_source_payload(force_refresh=False):
    """Expose the event-news lake as a governed data-source domain for Admin."""
    payload = _aggregate_real_news_sources(force_refresh=force_refresh)
    cached_sources = {
        str(item.get("code") or "").strip(): item
        for item in (payload.get("sources") or [])
        if isinstance(item, dict)
    }
    try:
        status = _load_json_app_setting(NEWS_SOURCE_STATUS_KEY, {})
    except Exception:
        status = {}
    historical_exclusions = {
        str(code).strip()
        for code in (status.get("excluded_codes") or [])
        if str(code).strip()
    } if isinstance(status, dict) else set()
    rows = []
    for source in NEWS_SOURCE_WHITELIST:
        code = str(source.get("code") or "").strip()
        runtime = cached_sources.get(code) or {}
        admission_count = int(source.get("validated_item_count") or 0)
        eligible = admission_count >= NEWS_SOURCE_MIN_ITEMS
        rows.append({
            "code": code,
            "name": str(source.get("name") or code),
            "category": str(source.get("category") or "其他"),
            "source_group": str(source.get("source_group") or "其他"),
            "url": str(source.get("url") or ""),
            "indicator_code": str(source.get("indicator_code") or ""),
            "admission_count": admission_count,
            "eligible": eligible,
            # A valid source is never made inactive solely by an old transient
            # runtime exclusion record.
            "active": eligible,
            "historical_exclusion": code in historical_exclusions,
            "last_fetch_count": int(runtime.get("count") or 0),
            "last_fetch_included": bool(runtime.get("included")),
            "last_fetch_reason": str(runtime.get("reason") or ("等待首次抓取" if not runtime else "")),
        })
    items = payload.get("items") or []
    return {
        "generated_at": now_ts(),
        "cached_at": str(payload.get("cached_at") or ""),
        "min_items": NEWS_SOURCE_MIN_ITEMS,
        "cache_ttl_seconds": NEWS_LAKE_CACHE_TTL_SECONDS,
        "total_sources": len(rows),
        "active_sources": sum(1 for row in rows if row["active"]),
        "included_sources": sum(1 for row in rows if row["last_fetch_included"]),
        "total_events": len(items),
        "sources": rows,
    }


def gen_news_feed(tenant=None, watchlist_details=None, algorithm_payload=None):
    try:
        payload = _aggregate_real_news_sources()
        items = _filter_news_to_time_window(payload.get("items") or [])
        # A cache created before the time-window rule can contain only older
        # items. Refresh once so the new window does not turn a valid source
        # into an empty homepage merely because the cache is still warm.
        # An empty cache is also stale for this feature. It can be produced by
        # a previous transient source outage and must not suppress future real
        # source retries.
        if not items and payload is not None:
            refreshed = _aggregate_real_news_sources(force_refresh=True)
            items = _filter_news_to_time_window(refreshed.get("items") or [])
        return _rank_news_for_tenant(
            items,
            tenant=tenant,
            watchlist_details=watchlist_details,
            algorithm_payload=algorithm_payload,
        )
    except Exception as exc:
        app.logger.warning("Real news aggregation unavailable: %s", exc)
        return []


def _select_fundamental_homepage_news(ranked_items, limit, rule_plan=None, watchlist_details=None):
    """Select relevant news while first covering each watchlist sector."""
    plan = _normalize_news_rule_plan(rule_plan)
    selected = []
    selected_keys = set()
    source_counts = {}
    group_counts = {}
    max_per_source = plan["diversity"]["max_per_source"]
    max_per_group = plan["diversity"]["max_per_group"]

    def item_key(item):
        return str(item.get("url") or item.get("link") or item.get("title") or id(item)).strip()

    def can_add(item, *, enforce_group=True):
        key = item_key(item)
        if key in selected_keys:
            return False
        source_key = str(item.get("source_code") or item.get("source_name") or item.get("source_group") or "unknown").strip()
        group_key = str(item.get("source_group") or "其他").strip()
        if source_counts.get(source_key, 0) >= max_per_source:
            return False
        if enforce_group and group_counts.get(group_key, 0) >= max_per_group:
            return False
        return True

    def add_item(item):
        selected.append(item)
        selected_keys.add(item_key(item))
        source_key = str(item.get("source_code") or item.get("source_name") or item.get("source_group") or "unknown").strip()
        group_key = str(item.get("source_group") or "其他").strip()
        source_counts[source_key] = source_counts.get(source_key, 0) + 1
        group_counts[group_key] = group_counts.get(group_key, 0) + 1

    if plan["candidate_scope"].get("watchlist_related"):
        for sector_group in _news_watchlist_sector_groups(watchlist_details):
            sector_candidates = [
                item for item in (ranked_items or [])
                if str(item.get("aggregation_bucket") or "").strip() == "watchlist_sector"
                and _news_item_matches_sector_group(item, sector_group)
                and can_add(item, enforce_group=False)
            ]
            if not sector_candidates:
                continue
            add_item(sector_candidates[0])
            if len(selected) >= limit:
                return selected

    for bucket in plan["priority_order"]:
        for item in ranked_items or []:
            if str(item.get("aggregation_bucket") or "").strip() != bucket:
                continue
            if not can_add(item):
                continue
            add_item(item)
            if len(selected) >= limit:
                return selected
    return selected


def build_fundamental_news_payload(tenant=None, watchlist_details=None, limit=10, algorithm_payload=None):
    algorithm = _normalize_news_aggregation_algorithm(algorithm_payload) if isinstance(algorithm_payload, dict) else load_tenant_news_aggregation_algorithm(str((tenant or {}).get("slug") or ""))
    ranked_items = gen_news_feed(tenant=tenant, watchlist_details=watchlist_details, algorithm_payload=algorithm)
    rule_plan = algorithm.get("rule_plan") or {}
    requested_limit = max(1, int(limit or 10))
    effective_limit = min(requested_limit, int((rule_plan.get("presentation") or {}).get("home_limit") or requested_limit))
    selected_items = _select_fundamental_homepage_news(ranked_items, effective_limit, rule_plan=rule_plan, watchlist_details=watchlist_details)
    source_buckets = {}
    for item in ranked_items:
        if not isinstance(item, dict):
            continue
        source_code = str(item.get("source_code") or item.get("source_group") or item.get("tag") or "source_all").strip() or "source_all"
        source_label = str(item.get("source_name") or item.get("source_group") or item.get("tag") or "综合要闻").strip() or "综合要闻"
        source_buckets.setdefault(source_code, {"label": source_label, "items": []})["items"].append(item)
    tabs = [
        {
            "key": "summary",
            "label": "归纳聚合",
            "count": len(selected_items),
            "items": selected_items,
        },
        {
            "key": "all",
            "label": "全部",
            "count": len(ranked_items),
            "items": ranked_items,
        }
    ]
    for source_code, group in sorted(
        source_buckets.items(),
        key=lambda item: (-len(item[1].get("items") or []), item[1].get("label") or item[0]),
    ):
        tabs.append({
            "key": source_code,
            "label": group["label"],
            "count": len(group.get("items") or []),
            "items": group.get("items") or [],
        })
    return {
        "items": selected_items,
        "tabs": tabs,
        "total": len(selected_items),
        "rule_plan": rule_plan,
        "rule_atoms": algorithm.get("rule_atoms") or _news_rule_plan_atoms(rule_plan),
    }

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
