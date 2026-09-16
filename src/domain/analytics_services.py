"""Product analytics event collection and reporting.

This module intentionally keeps product events separate from access_logs. The
fact table is append-only from the application perspective; reporting queries
derive counts, habits and behavior-based segments from the same vocabulary.
"""

import json
from datetime import date, datetime, timedelta

from src.runtime import request


ALLOWED_SURFACES = {"h5", "web", "admin", "tenant_portal", "unknown"}
ALLOWED_EVENT_CATEGORIES = {"page_view", "navigation", "interaction", "query", "conversion", "error", "system"}
MAX_PROPERTIES_BYTES = 8192
ANALYTICS_DEFAULT_DAYS = 30
SENSITIVE_PROPERTY_KEYS = {"question", "prompt", "input", "content", "body", "message", "raw_text"}

SURFACE_LABELS = {
    "h5": "H5",
    "web": "Web",
    "admin": "Admin",
    "tenant_portal": "租户门户",
    "unknown": "未知入口",
}
ROLE_LABELS = {
    "investor": "投资者",
    "dav": "大V",
    "admin": "管理员",
    "anonymous": "匿名访客",
}
EVENT_NAME_LABELS = {
    "page_view": "页面访问",
    "session_start": "会话开始",
    "session_end": "会话结束",
    "navigation_click": "导航切换",
    "feature_action": "功能操作",
    "query_submit": "提交查询",
    "query_success": "查询成功",
    "query_failed": "查询失败",
    "create": "创建",
    "save": "保存",
    "delete": "删除",
    "remove": "移除",
    "publish": "发布",
    "refresh": "刷新",
    "retry": "重试",
}
FEATURE_LABELS = {
    "h5.home": "H5 · 首页",
    "web.home": "Web · 首页",
    "tenant_portal.home": "租户门户 · 首页",
    "admin.overview": "Admin · 运营概览",
    "admin.event_analytics": "Admin · 埋点分析",
    "kol_workbench.overview": "大V工作台 · 工作台总览",
}
FEATURE_AREA_LABELS = {
    "home": "首页",
    "session": "会话",
    "overview": "总览",
    "watchlist": "自选股",
    "fundamental": "基本面",
    "market": "市场行情",
    "macro": "宏观经济",
    "news": "新闻",
    "review": "洞见",
    "insight": "洞见",
    "hermes": "小金智能体",
    "agent": "智能体",
    "task": "任务",
    "knowledge": "知识库",
    "dashboard": "智能看板",
    "indicator": "智能指标",
    "fans": "粉丝管理",
    "commerce": "订阅与收款",
    "portal": "大V门户",
    "analytics": "数据分析",
    "event_analytics": "埋点分析",
    "access": "访问审计",
    "settings": "系统配置",
    "users": "用户管理",
    "channels": "渠道管理",
    "commission": "收益结算",
    "published": "已发布内容",
}
ACTION_LABELS = {
    "open": "打开",
    "submit": "提交",
    "save": "保存",
    "delete": "删除",
    "remove": "移除",
    "add": "添加",
    "create": "创建",
    "publish": "发布",
    "search": "搜索",
    "query": "查询",
    "cancel": "取消",
    "retry": "重试",
    "preview": "预览",
    "refresh": "刷新",
    "load": "加载",
    "switch": "切换",
    "toggle": "切换开关",
    "select": "选择",
    "choose": "选择",
    "apply": "应用",
    "focus": "聚焦",
}


def _db():
    # Import lazily to avoid a core_services -> services -> analytics_services
    # import cycle during application bootstrap.
    from src.domain.core_services import get_db

    return get_db()


def _clean_text(value, limit, default=""):
    text = str(value or "").strip()
    return text[:limit] if text else default


def _normalise_surface(value):
    surface = _clean_text(value, 32, "unknown").lower().replace("-", "_")
    return surface if surface in ALLOWED_SURFACES else "unknown"


def _normalise_properties(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, raw in list(value.items())[:40]:
        safe_key = _clean_text(key, 64)
        if not safe_key or safe_key.startswith("__"):
            continue
        if safe_key.lower() in SENSITIVE_PROPERTY_KEYS:
            continue
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            result[safe_key] = raw if not isinstance(raw, str) else raw[:500]
        elif isinstance(raw, list):
            result[safe_key] = [str(item)[:120] for item in raw[:20]]
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_PROPERTIES_BYTES:
        result = {"truncated": True}
    return result


def _actor_key_sql(alias=""):
    prefix = f"{alias}." if alias else ""
    return (
        f"COALESCE(NULLIF({prefix}user_profile_id, ''), "
        f"NULLIF({prefix}user_id, ''), NULLIF({prefix}anonymous_id, ''), "
        f"NULLIF({prefix}session_id, ''), 'anonymous')"
    )


def _surface_for_request():
    path = _request_value("path")
    if path == "/admin" or path.startswith("/admin/"):
        return "admin"
    if path.startswith("/kol-workbench"):
        return "web"
    if path == "/web" or path.startswith("/web/"):
        return "web"
    if path.startswith("/tenant/"):
        return "tenant_portal"
    if path == "/h5" or path.startswith("/h5/"):
        return "h5"
    return "unknown"


def _request_value(name, default=""):
    try:
        return getattr(request, name, default) or default
    except RuntimeError:
        return default


def record_analytics_event(
    event_name,
    feature_key,
    *,
    event_category="interaction",
    surface=None,
    tenant_slug="",
    user_id="",
    user_profile_id="",
    user_role="",
    session_id="",
    anonymous_id="",
    object_type="",
    object_id="",
    path=None,
    referrer=None,
    event_at=None,
    duration_ms=None,
    success=None,
    error_code="",
    properties=None,
    db=None,
):
    """Write one validated event and return its id.

    The function is also used by the request hook, so it accepts an existing
    request-scoped connection to keep page logging atomic with access_logs.
    """
    event_name = _clean_text(event_name, 80)
    feature_key = _clean_text(feature_key, 160)
    if not event_name or not feature_key:
        raise ValueError("analytics_event_name_and_feature_required")
    category = _clean_text(event_category, 32, "interaction").lower()
    if category not in ALLOWED_EVENT_CATEGORIES:
        category = "interaction"
    surface = _normalise_surface(surface or _surface_for_request())
    duration = None
    if duration_ms not in (None, ""):
        try:
            duration = max(0, min(int(duration_ms), 86_400_000))
        except (TypeError, ValueError):
            duration = None
    success_value = success if isinstance(success, bool) else None
    props = _normalise_properties(properties)
    connection = db or _db()
    cursor = connection.execute(
        """
        INSERT INTO analytics_events (
            event_name, event_category, feature_key, surface, tenant_slug,
            user_id, user_profile_id, user_role, session_id, anonymous_id,
            object_type, object_id, path, referrer, event_at, duration_ms,
            success, error_code, properties_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?, ?::jsonb)
        RETURNING id
        """,
        (
            event_name,
            category,
            feature_key,
            surface,
            _clean_text(tenant_slug, 80).lower(),
            _clean_text(user_id, 120),
            _clean_text(user_profile_id, 120),
            _clean_text(user_role, 40).lower(),
            _clean_text(session_id, 160),
            _clean_text(anonymous_id, 160),
            _clean_text(object_type, 80),
            _clean_text(object_id, 160),
            _clean_text(path if path is not None else _request_value("path"), 500),
            _clean_text(referrer if referrer is not None else _request_value("referrer"), 500),
            event_at,
            duration,
            success_value,
            _clean_text(error_code, 120),
            json.dumps(props, ensure_ascii=False, separators=(",", ":")),
        ),
    )
    row = cursor.fetchone()
    return int(row["id"] if isinstance(row, dict) else row[0])


def _parse_analytics_filters(filters=None):
    raw = filters if isinstance(filters, dict) else {}
    days_raw = str(raw.get("days") or ANALYTICS_DEFAULT_DAYS).strip().lower()
    try:
        days = max(1, min(int(days_raw.rstrip("d")), 365))
    except ValueError:
        days = ANALYTICS_DEFAULT_DAYS
    end = datetime.now()
    start = end - timedelta(days=days)
    raw_surface = _clean_text(raw.get("surface"), 32).lower()
    surface = "" if raw_surface in {"", "all", "全部"} else _normalise_surface(raw_surface)
    role = _clean_text(raw.get("user_role"), 40).lower()
    tenant = _clean_text(raw.get("tenant_slug"), 80).lower()
    feature = _clean_text(raw.get("feature_key"), 160)
    conditions = ["event_at >= ?", "event_at < ?"]
    params = [start, end]
    if surface:
        conditions.append("surface = ?")
        params.append(surface)
    if role:
        conditions.append("user_role = ?")
        params.append(role)
    if tenant:
        conditions.append("tenant_slug = ?")
        params.append(tenant)
    if feature:
        conditions.append("feature_key = ?")
        params.append(feature)
    return {
        "days": days,
        "start": start,
        "end": end,
        "where": " AND ".join(conditions),
        "params": params,
        "surface": surface,
        "user_role": role,
        "tenant_slug": tenant,
        "feature_key": feature,
    }


def _row_dicts(rows):
    result = []
    for row in rows or []:
        item = dict(row)
        for key, value in list(item.items()):
            if isinstance(value, (datetime, date)):
                item[key] = value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
        result.append(item)
    return result


def _feature_label(feature_key):
    """Return a stable Chinese display label while preserving the raw key."""
    key = _clean_text(feature_key, 160)
    if not key:
        return "未标记功能"
    if key in FEATURE_LABELS:
        return FEATURE_LABELS[key]
    parts = key.split(".")
    surface = SURFACE_LABELS.get(parts[0], parts[0])
    if len(parts) == 1:
        return surface
    if parts[1] == "action":
        action_and_target = parts[2] if len(parts) > 2 else "操作"
        action, _, inline_target = action_and_target.partition("_")
        if action not in ACTION_LABELS:
            action, inline_target = action_and_target, ""
        action_label = ACTION_LABELS.get(action, action)
        target_parts = ([inline_target] if inline_target else []) + parts[3:]
        target = " · ".join(FEATURE_AREA_LABELS.get(item, item) for item in target_parts)
        return f"{surface} · {action_label}{(' · ' + target) if target else ''}"
    labels = [FEATURE_AREA_LABELS.get(item, item) for item in parts[1:]]
    return f"{surface} · {' · '.join(labels)}"


def _event_label(event_name):
    key = _clean_text(event_name, 80).lower()
    if key in EVENT_NAME_LABELS:
        return EVENT_NAME_LABELS[key]
    return " · ".join(FEATURE_AREA_LABELS.get(item, item) for item in key.split("_")) or "未标记事件"


def build_analytics_summary(filters=None):
    parsed = _parse_analytics_filters(filters)
    db = _db()
    where, params = parsed["where"], parsed["params"]
    summary = db.execute(
        f"""
        SELECT COUNT(*) AS event_count,
               COUNT(DISTINCT {_actor_key_sql()}) AS active_users,
               COUNT(DISTINCT NULLIF(session_id, '')) AS active_sessions,
               COUNT(DISTINCT feature_key) AS feature_count,
               COUNT(*) FILTER (WHERE success IS TRUE) AS success_count,
               COUNT(*) FILTER (WHERE success IS NOT NULL) AS measured_count,
               COALESCE(AVG(duration_ms) FILTER (WHERE duration_ms IS NOT NULL), 0) AS avg_duration_ms
        FROM analytics_events
        WHERE {where}
        """,
        params,
    ).fetchone() or {}
    event_count = int(summary.get("event_count") or 0)
    active_users = int(summary.get("active_users") or 0)
    measured_count = int(summary.get("measured_count") or 0)
    return {
        "event_count": event_count,
        "active_users": active_users,
        "active_sessions": int(summary.get("active_sessions") or 0),
        "feature_count": int(summary.get("feature_count") or 0),
        "avg_events_per_user": round((event_count / active_users), 2) if active_users else 0,
        "success_rate": round((int(summary.get("success_count") or 0) / measured_count) * 100, 1) if measured_count else None,
        "avg_duration_ms": round(float(summary.get("avg_duration_ms") or 0)),
        "days": parsed["days"],
    }


def build_analytics_features(filters=None, limit=30):
    parsed = _parse_analytics_filters(filters)
    limit = max(1, min(int(limit or 30), 100))
    rows = _db().execute(
        f"""
        SELECT feature_key,
               surface,
               COUNT(*) AS event_count,
               COUNT(DISTINCT {_actor_key_sql()}) AS active_users,
               COUNT(*) FILTER (WHERE success IS TRUE) AS success_count,
               COUNT(*) FILTER (WHERE success IS NOT NULL) AS measured_count,
               MAX(event_at) AS last_used_at
        FROM analytics_events
        WHERE {parsed['where']}
        GROUP BY feature_key, surface
        ORDER BY event_count DESC, active_users DESC, feature_key ASC
        LIMIT ?
        """,
        parsed["params"] + [limit],
    ).fetchall()
    result = []
    for row in _row_dicts(rows):
        measured = int(row.get("measured_count") or 0)
        result.append({
            "feature_key": row.get("feature_key") or "",
            "feature_label": _feature_label(row.get("feature_key")),
            "surface": row.get("surface") or "unknown",
            "surface_label": SURFACE_LABELS.get(row.get("surface") or "unknown", "未知入口"),
            "event_count": int(row.get("event_count") or 0),
            "active_users": int(row.get("active_users") or 0),
            "success_rate": round((int(row.get("success_count") or 0) / measured) * 100, 1) if measured else None,
            "last_used_at": row.get("last_used_at"),
        })
    return result


def build_analytics_habits(filters=None):
    parsed = _parse_analytics_filters(filters)
    db = _db()
    hourly = db.execute(
        f"""
        SELECT EXTRACT(HOUR FROM event_at)::int AS hour, COUNT(*) AS event_count,
               COUNT(DISTINCT {_actor_key_sql()}) AS active_users
        FROM analytics_events WHERE {parsed['where']}
        GROUP BY hour ORDER BY hour
        """,
        parsed["params"],
    ).fetchall()
    daily = db.execute(
        f"""
        SELECT event_at::date AS day, COUNT(*) AS event_count,
               COUNT(DISTINCT {_actor_key_sql()}) AS active_users
        FROM analytics_events WHERE {parsed['where']}
        GROUP BY day ORDER BY day
        """,
        parsed["params"],
    ).fetchall()
    transitions = db.execute(
        f"""
        WITH ordered AS (
            SELECT {_actor_key_sql()} AS actor_key, feature_key, event_at, id,
                   LEAD(feature_key) OVER (
                       PARTITION BY {_actor_key_sql()} ORDER BY event_at, id
                   ) AS next_feature
            FROM analytics_events
            WHERE {parsed['where']}
        )
        SELECT feature_key AS from_feature, next_feature AS to_feature, COUNT(*) AS transition_count
        FROM ordered
        WHERE next_feature IS NOT NULL AND next_feature <> feature_key
        GROUP BY feature_key, next_feature
        ORDER BY transition_count DESC, from_feature ASC, to_feature ASC
        LIMIT 12
        """,
        parsed["params"],
    ).fetchall()
    transition_items = []
    for item in _row_dicts(transitions):
        item["from_feature_label"] = _feature_label(item.get("from_feature"))
        item["to_feature_label"] = _feature_label(item.get("to_feature"))
        transition_items.append(item)
    return {
        "hourly": _row_dicts(hourly),
        "daily": _row_dicts(daily),
        "transitions": transition_items,
    }


def _persona_label(feature_key):
    key = str(feature_key or "").lower()
    if any(token in key for token in ("hermes", "agent", "ai")):
        return "智能体型"
    if any(token in key for token in ("review", "insight", "news", "research")):
        return "研究内容型"
    if any(token in key for token in ("watchlist", "fundamental", "market", "macro", "stock")):
        return "行情观察型"
    if any(token in key for token in ("workbench", "admin", "commerce", "fan")):
        return "运营管理型"
    return "综合使用型"


def build_analytics_personas(filters=None, min_sample=5):
    parsed = _parse_analytics_filters(filters)
    min_sample = max(1, min(int(min_sample or 5), 100))
    rows = _db().execute(
        f"""
        WITH actor_feature_counts AS (
            SELECT {_actor_key_sql()} AS actor_key, feature_key, COUNT(*) AS usage_count
            FROM analytics_events WHERE {parsed['where']}
            GROUP BY actor_key, feature_key
        ), ranked AS (
            SELECT actor_key, feature_key, usage_count,
                   ROW_NUMBER() OVER (PARTITION BY actor_key ORDER BY usage_count DESC, feature_key) AS rank_no
            FROM actor_feature_counts
        )
        SELECT feature_key, COUNT(*) AS user_count, SUM(usage_count) AS event_count
        FROM ranked WHERE rank_no = 1
        GROUP BY feature_key ORDER BY user_count DESC, event_count DESC
        """,
        parsed["params"],
    ).fetchall()
    buckets = _db().execute(
        f"""
        WITH actor_counts AS (
            SELECT {_actor_key_sql()} AS actor_key, COUNT(*) AS event_count
            FROM analytics_events WHERE {parsed['where']}
            GROUP BY actor_key
        )
        SELECT CASE WHEN event_count = 1 THEN '首次/轻度'
                    WHEN event_count BETWEEN 2 AND 5 THEN '持续使用'
                    WHEN event_count BETWEEN 6 AND 20 THEN '高频使用'
                    ELSE '重度使用' END AS activity_level,
               COUNT(*) AS user_count
        FROM actor_counts GROUP BY activity_level
        ORDER BY user_count DESC
        """,
        parsed["params"],
    ).fetchall()
    role_rows = _db().execute(
        f"""
        SELECT COALESCE(NULLIF(user_role, ''), 'anonymous') AS role,
               COUNT(DISTINCT {_actor_key_sql()}) AS user_count
        FROM analytics_events WHERE {parsed['where']}
        GROUP BY role ORDER BY user_count DESC, role ASC
        """,
        parsed["params"],
    ).fetchall()
    surface_rows = _db().execute(
        f"""
        SELECT surface, COUNT(DISTINCT {_actor_key_sql()}) AS user_count
        FROM analytics_events WHERE {parsed['where']}
        GROUP BY surface ORDER BY user_count DESC, surface ASC
        """,
        parsed["params"],
    ).fetchall()
    preferences = []
    hidden_count = 0
    for row in _row_dicts(rows):
        user_count = int(row.get("user_count") or 0)
        if user_count < min_sample:
            hidden_count += user_count
            continue
        preferences.append({
            "persona": _persona_label(row.get("feature_key")),
            "leading_feature": row.get("feature_key") or "",
            "user_count": user_count,
            "event_count": int(row.get("event_count") or 0),
            "inference": "基于主要使用功能推断，不代表用户真实身份属性。",
        })
    grouped = {}
    for item in preferences:
        current = grouped.setdefault(item["persona"], {"persona": item["persona"], "user_count": 0, "event_count": 0, "leading_features": [], "inference": item["inference"]})
        current["user_count"] += item["user_count"]
        current["event_count"] += item["event_count"]
        current["leading_features"].append(item["leading_feature"])
    return {
        "min_sample": min_sample,
        "preferences": sorted(grouped.values(), key=lambda item: (-item["user_count"], item["persona"])),
        "activity_levels": _row_dicts(buckets),
        "role_distribution": _row_dicts(role_rows),
        "surface_distribution": _row_dicts(surface_rows),
        "hidden_small_sample_users": hidden_count,
        "note": "画像仅为行为推断；小于最小样本量的细分不会展示。",
    }


def list_analytics_events(filters=None, limit=100):
    parsed = _parse_analytics_filters(filters)
    limit = max(1, min(int(limit or 100), 500))
    rows = _db().execute(
        f"""
        SELECT id, event_at, event_name, event_category, feature_key, surface,
               tenant_slug, user_profile_id, user_role, object_type, object_id,
               duration_ms, success, error_code, properties_json
        FROM analytics_events WHERE {parsed['where']}
        ORDER BY event_at DESC, id DESC LIMIT ?
        """,
        parsed["params"] + [limit],
    ).fetchall()
    result = []
    for row in _row_dicts(rows):
        if isinstance(row.get("properties_json"), str):
            try:
                row["properties_json"] = json.loads(row["properties_json"])
            except json.JSONDecodeError:
                row["properties_json"] = {}
        row["event_label"] = _event_label(row.get("event_name"))
        row["feature_label"] = _feature_label(row.get("feature_key"))
        row["surface_label"] = SURFACE_LABELS.get(row.get("surface") or "unknown", "未知入口")
        row["user_role_label"] = ROLE_LABELS.get(row.get("user_role") or "anonymous", "未标记角色")
        result.append(row)
    return result


def build_admin_analytics_payload(filters=None):
    normalized = _parse_analytics_filters(filters)
    public_filters = {
        "days": normalized["days"],
        "surface": normalized["surface"],
        "user_role": normalized["user_role"],
        "tenant_slug": normalized["tenant_slug"],
        "feature_key": normalized["feature_key"],
    }
    return {
        "ok": True,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "filters": public_filters,
        "summary": build_analytics_summary(public_filters),
        "features": build_analytics_features(public_filters),
        "habits": build_analytics_habits(public_filters),
        "personas": build_analytics_personas(public_filters),
        "events": list_analytics_events(public_filters, limit=80),
    }
