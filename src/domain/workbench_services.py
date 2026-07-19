from src.runtime import *
from src.domain.core_services import *
from src.domain.market_services import *
from src.domain.ai_services import *

FAN_STOCK_OBSERVATION_WINDOW_DAYS = 7
FAN_STOCK_OBSERVATION_EVENT_TYPES = {"watchlist_detail_view"}
FAN_STOCK_HERMES_INTENTS = {"watchlist_fundamental", "multi_tool_research"}


def _normalize_fan_stock_event_type(value):
    event_type = str(value or "").strip().lower()
    return event_type if event_type in FAN_STOCK_OBSERVATION_EVENT_TYPES else "watchlist_detail_view"


def _normalize_fan_stock_code(stock_code="", stock_name=""):
    code = find_watchlist_code_from_text(stock_code)
    if code:
        return code
    return find_watchlist_code_from_text(stock_name)


def _extract_recent_hermes_stock_codes(tags, memory_summary):
    raw_values = []
    if isinstance(tags, dict):
        raw_values.extend(tags.get("focus_symbols") if isinstance(tags.get("focus_symbols"), list) else [])
    if isinstance(memory_summary, dict):
        raw_values.extend(memory_summary.get("focus_symbols") if isinstance(memory_summary.get("focus_symbols"), list) else [])
    codes = []
    for item in raw_values:
        normalized = _normalize_fan_stock_code(stock_code=item)
        if normalized and normalized not in codes:
            codes.append(normalized)
    return codes


def _build_fan_stock_sector_note(sector_name, top_stock, sector_bucket, detail):
    stock_name = str((top_stock or {}).get("name") or (detail or {}).get("name") or sector_name or "该板块").strip() or sector_name or "该板块"
    focus_text = str(
        (detail or {}).get("focus")
        or ((detail or {}).get("fundamental") or {}).get("summary")
        or (detail or {}).get("signal_summary")
        or sector_name
        or "相关主线"
    ).strip()
    focus_text = re.sub(r"\s+", " ", focus_text)
    focus_text = focus_text[:42] + ("…" if len(focus_text) > 42 else "")
    if int((sector_bucket or {}).get("hermes_queries") or 0) >= int((sector_bucket or {}).get("detail_views") or 0):
        return f"粉丝更常通过 Hermes 追问 {stock_name}，关注点集中在 {focus_text}。"
    return f"{stock_name} 的详情页被反复打开，粉丝主要在看 {focus_text}。"


def record_fan_stock_observation_event(
    tenant_slug="",
    user_profile_id="",
    user_role="investor",
    stock_code="",
    stock_name="",
    event_type="watchlist_detail_view",
    entry_point="",
    source_detail="",
):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    normalized_user = str(user_profile_id or "").strip()
    normalized_role = str(user_role or "").strip().lower() or "investor"
    if not normalized_tenant or not normalized_user or normalized_role != "investor":
        return None
    normalized_code = _normalize_fan_stock_code(stock_code=stock_code, stock_name=stock_name)
    details = gen_watchlist_details()
    detail = get_watchlist_detail_by_code(stock_code=normalized_code, stock_name=stock_name, details_map=details)
    if not detail:
        return None
    payload = {
        "tenant_slug": normalized_tenant,
        "user_profile_id": normalized_user,
        "user_role": normalized_role,
        "stock_code": detail.get("code") or normalized_code,
        "stock_name": detail.get("name") or normalized_code,
        "sector_name": detail.get("industry") or detail.get("focus") or "其他板块",
        "event_type": _normalize_fan_stock_event_type(event_type),
        "entry_point": str(entry_point or "").strip()[:80],
        "source_detail": str(source_detail or "").strip()[:120],
        "created_at": now_ts(),
    }
    db = get_db()
    db.execute(
        """
        INSERT INTO fan_stock_observation_events (
            tenant_slug, user_profile_id, user_role, stock_code, stock_name, sector_name,
            event_type, entry_point, source_detail, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["tenant_slug"],
            payload["user_profile_id"],
            payload["user_role"],
            payload["stock_code"],
            payload["stock_name"],
            payload["sector_name"],
            payload["event_type"],
            payload["entry_point"],
            payload["source_detail"],
            payload["created_at"],
        ),
    )
    db.commit()
    return payload


def build_fan_stock_observation_payload(tenant=None, fallback_mode=False):
    tenant = tenant or get_tenant_by_slug()
    tenant_slug = str((tenant or {}).get("slug") or "").strip().lower()
    details_map = gen_watchlist_details()
    active_codes = [
        str((item or {}).get("code") or "").strip()
        for item in (build_tenant_watchlist_hub_items(tenant, details_map) or [])
        if str((item or {}).get("code") or "").strip()
    ]
    cutoff = (datetime.now() - timedelta(days=FAN_STOCK_OBSERVATION_WINDOW_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    detail_rows = []
    hermes_rows = []
    if not fallback_mode and tenant_slug:
        try:
            db = get_db()
            detail_rows = db.execute(
                """
                SELECT user_profile_id, stock_code, stock_name, sector_name, event_type, entry_point, source_detail, created_at
                FROM fan_stock_observation_events
                WHERE tenant_slug = ? AND created_at >= ?
                ORDER BY created_at DESC, id DESC
                """,
                (tenant_slug, cutoff),
            ).fetchall()
            hermes_rows = db.execute(
                """
                SELECT user_profile_id, question_text, intent, tags_json, memory_summary_json, created_at
                FROM hermes_conversation_turns
                WHERE tenant_slug = ? AND user_role = ? AND created_at >= ?
                ORDER BY created_at DESC, id DESC
                """,
                (tenant_slug, "investor", cutoff),
            ).fetchall()
        except Exception as exc:
            if not is_db_unavailable_error(exc):
                raise
            detail_rows = []
            hermes_rows = []
    sector_map = {}
    all_active_users = set()
    detail_view_total = 0
    hermes_query_total = 0

    def ensure_sector_bucket(sector_name):
        normalized_sector = str(sector_name or "其他板块").strip() or "其他板块"
        if normalized_sector not in sector_map:
            sector_map[normalized_sector] = {
                "name": normalized_sector,
                "visits": 0,
                "detail_views": 0,
                "hermes_queries": 0,
                "users": set(),
                "stocks_map": {},
                "note": "",
            }
        return sector_map[normalized_sector]

    def apply_stock_signal(stock_code, user_profile_id="", signal_type="detail"):
        nonlocal detail_view_total, hermes_query_total
        normalized_code = _normalize_fan_stock_code(stock_code=stock_code)
        detail = details_map.get(normalized_code)
        if not detail:
            return
        stock_name = str(detail.get("name") or normalized_code).strip() or normalized_code
        sector_name = str(detail.get("industry") or detail.get("focus") or "其他板块").strip() or "其他板块"
        sector_bucket = ensure_sector_bucket(sector_name)
        stock_bucket = sector_bucket["stocks_map"].get(normalized_code)
        if not stock_bucket:
            stock_bucket = {
                "code": normalized_code,
                "name": stock_name,
                "sector": sector_name,
                "visits": 0,
                "detail_views": 0,
                "hermes_queries": 0,
                "users": set(),
                "hint": str(
                    detail.get("signal_summary")
                    or ((detail.get("fundamental") or {}).get("summary"))
                    or detail.get("focus")
                    or sector_name
                ).strip(),
            }
            sector_bucket["stocks_map"][normalized_code] = stock_bucket
        if user_profile_id:
            stock_bucket["users"].add(str(user_profile_id).strip())
            sector_bucket["users"].add(str(user_profile_id).strip())
            all_active_users.add(str(user_profile_id).strip())
        stock_bucket["visits"] += 1
        sector_bucket["visits"] += 1
        if signal_type == "hermes":
            stock_bucket["hermes_queries"] += 1
            sector_bucket["hermes_queries"] += 1
            hermes_query_total += 1
        else:
            stock_bucket["detail_views"] += 1
            sector_bucket["detail_views"] += 1
            detail_view_total += 1

    for row in detail_rows:
        item = dict(row) if isinstance(row, dict) else {}
        apply_stock_signal(item.get("stock_code"), user_profile_id=item.get("user_profile_id"), signal_type="detail")

    for row in hermes_rows:
        item = dict(row) if isinstance(row, dict) else {}
        if str(item.get("intent") or "").strip() not in FAN_STOCK_HERMES_INTENTS:
            continue
        tags = safe_json_loads(item.get("tags_json"), {})
        memory_summary = safe_json_loads(item.get("memory_summary_json"), {})
        codes = _extract_recent_hermes_stock_codes(tags, memory_summary)
        if not codes:
            fallback_code = _normalize_fan_stock_code(
                stock_code=item.get("question_text"),
                stock_name=item.get("question_text"),
            )
            codes = [fallback_code] if fallback_code else []
        for code in codes:
            apply_stock_signal(code, user_profile_id=item.get("user_profile_id"), signal_type="hermes")

    sectors = []
    top_stocks = []
    for sector_name, sector_bucket in sector_map.items():
        stocks = sorted(
            sector_bucket["stocks_map"].values(),
            key=lambda item: (-int(item.get("visits") or 0), -int(item.get("hermes_queries") or 0), str(item.get("code") or "")),
        )
        if not stocks:
            continue
        top_stock = stocks[0]
        top_detail = details_map.get(top_stock.get("code")) or {}
        sector_bucket["note"] = _build_fan_stock_sector_note(sector_name, top_stock, sector_bucket, top_detail)
        normalized_stocks = []
        for stock in stocks[:6]:
            normalized_stock = {
                "code": stock.get("code") or "",
                "name": stock.get("name") or stock.get("code") or "",
                "sector": stock.get("sector") or sector_name,
                "visits": int(stock.get("visits") or 0),
                "detail_views": int(stock.get("detail_views") or 0),
                "hermes_queries": int(stock.get("hermes_queries") or 0),
                "user_count": len(stock.get("users") or []),
                "hint": stock.get("hint") or "",
            }
            normalized_stocks.append(normalized_stock)
            top_stocks.append(normalized_stock)
        sectors.append(
            {
                "name": sector_name,
                "visits": int(sector_bucket.get("visits") or 0),
                "detail_views": int(sector_bucket.get("detail_views") or 0),
                "hermes_queries": int(sector_bucket.get("hermes_queries") or 0),
                "user_count": len(sector_bucket.get("users") or []),
                "note": sector_bucket.get("note") or "",
                "stocks": normalized_stocks,
            }
        )

    sectors = sorted(
        sectors,
        key=lambda item: (-int(item.get("visits") or 0), -int(item.get("hermes_queries") or 0), str(item.get("name") or "")),
    )
    top_stocks = sorted(
        top_stocks,
        key=lambda item: (-int(item.get("visits") or 0), -int(item.get("hermes_queries") or 0), str(item.get("code") or "")),
    )[:6]
    total_interactions = detail_view_total + hermes_query_total
    hot_sector = sectors[0]["name"] if sectors else ""
    return {
        "window_days": FAN_STOCK_OBSERVATION_WINDOW_DAYS,
        "summary": (
            f"近 {FAN_STOCK_OBSERVATION_WINDOW_DAYS} 天共记录 {total_interactions} 次粉丝个股观察行为，"
            f"其中详情查看 {detail_view_total} 次、Hermes 个股追问 {hermes_query_total} 次。"
        ) if total_interactions else "当前近 7 天还没有粉丝个股观察数据。等粉丝查看个股详情或发起 Hermes 个股分析后，这里会自动开始累计。",
        "totals": {
            "interactions": total_interactions,
            "detail_views": detail_view_total,
            "hermes_queries": hermes_query_total,
            "active_fans": len(all_active_users),
            "sector_count": len(sectors),
        },
        "hot_sector": hot_sector,
        "sectors": sectors,
        "top_stocks": top_stocks,
        "fallback_mode": bool(fallback_mode),
        "tracked_stock_codes": active_codes[:8],
    }


def build_tenant_watchlist_hub_items(tenant, watchlist_details_map):
    is_lisa = tenant["slug"] == "lisa"
    target_codes = ["00700", "03690", "09988"] if is_lisa else ["688981", "00700", "600519"]
    return [
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
        for detail in [watchlist_details_map.get(code) for code in target_codes]
        if detail
    ]


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
        "smart_indicator_catalog": {
            "tenant_smart_indicators": build_tenant_smart_indicator_catalog(tenant),
            "base_indicators": build_dashboard_base_indicator_options(tenant),
            "available_tags": build_tenant_smart_indicator_tag_catalog(tenant),
        },
        "fan_stock_observation": workbench.get("fan_stock_observation") or {},
        "reviews": workbench["published_reviews"],
        "stats": workbench["stats"],
    }


def build_tenant_portal_payload(tenant=None, fallback_mode=False):
    tenant = tenant or get_tenant_by_slug()
    workbench = gen_kol_workbench(tenant, fallback_mode=fallback_mode)
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
        "fallback_mode": fallback_mode,
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



def gen_dm_conversations(tenant_slug=None, include_fan_threads=True):
    tenant = get_tenant_by_slug(tenant_slug)
    state = resolve_tenant_message_center_state(tenant, tenant.get("message_center_state"))
    current_profile = get_current_demo_profile()
    current_role = str((current_profile or {}).get("role") or "").strip().lower()
    current_profile_id = str((current_profile or {}).get("username") or "").strip()
    items = []
    for thread in state["threads"]:
        thread_type = str(thread.get("type") or "").strip()
        if thread_type == "fan_interaction" and not include_fan_threads:
            continue
        if thread_type == "fan_interaction" and current_role == "investor":
            if str(thread.get("user_profile_id") or "").strip() != current_profile_id:
                continue
        items.append({
            "id": thread.get("id"),
            "kol_name": tenant.get("advisor") or "",
            "kol_avatar": tenant.get("logo_mark") or "👑",
            "user_name": thread.get("user_name") or thread.get("name") or "",
            "user_avatar": thread.get("user_avatar") or "👤",
            "tier": thread.get("tier") or "粉丝",
            "last_msg": thread.get("last_msg") or thread.get("content") or "",
            "time": thread.get("time") or "",
            "unread": int(thread.get("unread") or 0),
            "kol_unread": int(thread.get("kol_unread") or 0),
            "user_unread": int(thread.get("user_unread") or 0),
            "last_sender": thread.get("last_sender") or "",
            "status": thread.get("status") or "",
            "vip_only": bool(thread.get("vip_only", False)),
            "type": thread_type,
        })
    return items


def gen_dm_messages(thread_id, tenant_slug=None):
    tenant = get_tenant_by_slug(tenant_slug)
    state = resolve_tenant_message_center_state(tenant, tenant.get("message_center_state"))
    for thread in state["threads"]:
        if str(thread.get("id")) == str(thread_id):
            return copy.deepcopy(thread.get("messages") or [])
    return [{"id": 1, "sender": "kol", "content": "欢迎关注！有投研问题随时交流。", "time": "2026-05-18 09:00", "type": "text"}]

def gen_kol_workbench(tenant=None, fallback_mode=False):
    tenant = tenant or get_tenant_by_slug()
    is_lisa = tenant["slug"] == "lisa"
    if fallback_mode:
        fallback_config = normalize_site_config(DEFAULT_SITE_CONFIG)
        tenant_users = [
            ensure_user_row_defaults(dict(item), fallback_config)
            for item in DEFAULT_USERS
            if str(item.get("tenant_slug") or "").strip().lower() == tenant["slug"]
        ]
    else:
        tenant_users = list_users(tenant_slug=tenant["slug"])
    investor_users = [user for user in tenant_users if user["role"] == "investor"]
    watchlist_details_map = gen_watchlist_details()
    kol_name = tenant["advisor"]
    kol_avatar = tenant.get("logo_mark") or "👑"
    base_followers = 86000 if is_lisa else 128000
    base_vip = 29 if is_lisa else 36
    base_revenue = 14200 if is_lisa else 18600
    revenue_change = 6.4 if is_lisa else 8.5
    today_views = 540 if is_lisa else 680
    engagement_rate = 7.6 if is_lisa else 6.8
    watchlist_focus = ["腾讯控股", "美团-W", "阿里巴巴-W"] if is_lisa else ["中芯国际", "腾讯控股", "贵州茅台"]
    fund_dashboard_state = resolve_tenant_fund_dashboard_state(tenant, tenant.get("fund_dashboard_config"))
    fund_dashboard = copy.deepcopy(fund_dashboard_state["published"])
    knowledge_hub = fetch_live_knowledge_hub(tenant)
    indicator_hub = build_indicator_hub_fallback(tenant=tenant, admin_view=False) if fallback_mode else build_indicator_hub(tenant=tenant, admin_view=False)
    news_items = gen_news_feed()
    message_center_state = resolve_tenant_message_center_state(tenant, tenant.get("message_center_state"))
    message_center_stats = build_message_center_stats(message_center_state)
    published_reviews = resolve_tenant_review_snapshots(tenant, tenant.get("review_snapshots"))
    fan_threads = [item for item in message_center_state["threads"] if item.get("type") == "fan_interaction"]
    review_notice_threads = [item for item in message_center_state["threads"] if item.get("type") == "review_notification"]
    broadcast_history = message_center_state["broadcasts"]
    review_smart_cards = build_review_smart_cards(tenant, fund_dashboard, watchlist_details_map, news_items)
    review_generation_cfg = get_review_generation_config()
    watchlist_hub_items = build_tenant_watchlist_hub_items(tenant, watchlist_details_map)
    fan_stock_observation = build_fan_stock_observation_payload(tenant, fallback_mode=fallback_mode)
    watchlist_comment_analytics = build_watchlist_comment_analytics(tenant_slug=tenant["slug"])
    return {
        "tenant": tenant,
        "fallback_mode": fallback_mode,
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
            "unread_messages": message_center_stats["unread_messages"],
            "pending_replies": message_center_stats["pending_replies"],
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
        "broadcast_history": broadcast_history,
        "portal_workspace": resolve_tenant_portal_workspace(tenant, tenant.get("portal_cms")),
        "message_center": {
            "summary": message_center_state["summary"],
            "items": build_message_center_items((fan_threads + review_notice_threads)[:6], limit=6),
            "threads": copy.deepcopy(message_center_state["threads"]),
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
                {"icon": "🔗", "label": "URL 资料", "desc": "抓取网页资料并抽取正文，适合作为复盘证据链和背景补充。"},
            ],
            "paragraph_modes": [
                {"label": "大V自定段落", "desc": "适合自己写主框架，只让智能体补摘要、证据链和风险提示。"},
                {"label": "智能文案", "desc": "适合先交信息给智能体，并补充修改规则或常用提示词标签后生成草稿。"},
            ],
            "default_flow": ["选择复盘周期", "确认本次自选股", "补充语音/手输/文件", "设置智能文案规则", "生成草稿预览", "确认后发布给粉丝"],
            "watchlist_focus": watchlist_focus,
            "periods": ["日复盘", "周复盘", "月复盘"],
            "smart_cards": review_smart_cards,
            "flow_nodes": [
                {"id": "cards", "label": "选择智能仪表盘卡片"},
                {"id": "input", "label": "录入个人内容"},
                {"id": "polish", "label": "输入润色"},
                {"id": "compose", "label": "完整成稿"},
                {"id": "preview", "label": "人工确认并发布"},
            ],
            "prompt_config": {
                "polish_system_prompt": review_generation_cfg.get("polish_system_prompt"),
                "polish_user_template": review_generation_cfg.get("polish_user_template"),
                "compose_system_prompt": review_generation_cfg.get("compose_system_prompt"),
                "compose_user_template": review_generation_cfg.get("compose_user_template"),
            },
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
            "items": watchlist_hub_items,
        },
        "fan_stock_observation": fan_stock_observation,
        "watchlist_comment_analytics": watchlist_comment_analytics,
        "fund_dashboard": fund_dashboard,
        "fund_dashboard_state": fund_dashboard_state,
        "indicator_hub": indicator_hub,
        "published_reviews": published_reviews,
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
