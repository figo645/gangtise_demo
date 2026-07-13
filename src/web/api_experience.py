from src.runtime import *
from src.services import *
from src.web.api_core import gen_community_posts, gen_community_events

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


@app.route("/api/hermes/query", methods=["POST"])
def api_hermes_query():
    body = request.get_json(silent=True) or {}
    try:
        result = build_hermes_query_response(body)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    except Exception:
        app.logger.exception("Failed to execute Hermes query")
        return jsonify({"ok": False, "error": "hermes_query_failed"}), 500
    return jsonify(result)


@app.route("/api/hermes/usage/current")
def api_hermes_usage_current():
    requested_tenant = str(request.args.get("tenant_slug") or "").strip().lower()
    requested_user = str(request.args.get("user_profile_id") or "").strip()
    try:
        site_config = get_site_config()
        profiles = get_h5_login_users(site_config)
        current = get_current_demo_profile(site_config)
        matched = next(
            (
                item for item in profiles
                if str(item.get("username") or "").strip() == (requested_user or str((current or {}).get("username") or "").strip())
            ),
            None,
        )
        tenant_slug = requested_tenant or str((((matched or current) or {}).get("tenant") or {}).get("slug") or ((matched or current) or {}).get("tenant_slug") or "").strip().lower()
        user_profile_id = requested_user or str((matched or current or {}).get("username") or "").strip()
        if not user_profile_id:
            return jsonify({"ok": False, "error": "user_profile_id_required"}), 400
        quota_total = int((matched or current or {}).get("computeCredits") or 0)
        usage = build_user_hermes_usage_snapshot(
            tenant_slug=tenant_slug,
            user_profile_id=user_profile_id,
            quota_total=quota_total,
        )
        return jsonify({"ok": True, "usage": usage})
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while loading current Hermes usage, using fallback credits")
        fallback_config = normalize_site_config(DEFAULT_SITE_CONFIG)
        profiles, current = resolve_demo_profile_fallback(fallback_config)
        matched = next(
            (
                item for item in profiles
                if str(item.get("username") or "").strip() == (requested_user or str((current or {}).get("username") or "").strip())
            ),
            None,
        )
        tenant_slug = requested_tenant or str((((matched or current) or {}).get("tenant") or {}).get("slug") or ((matched or current) or {}).get("tenant_slug") or "").strip().lower()
        user_profile_id = requested_user or str((matched or current or {}).get("username") or "").strip()
        if not user_profile_id:
            return jsonify({"ok": False, "error": "user_profile_id_required"}), 400
        quota_total = int((matched or current or {}).get("computeCredits") or 0)
        return jsonify(
            {
                "ok": True,
                "usage": {
                    "tenant_slug": tenant_slug,
                    "user_profile_id": user_profile_id,
                    "user_display_name": str((matched or current or {}).get("name") or user_profile_id).strip() or user_profile_id,
                    "quota_total": quota_total,
                    "used_count": 0,
                    "remaining_count": quota_total,
                    "total_call_count": 0,
                    "today_call_count": 0,
                    "month_call_count": 0,
                    "month_compute_units": 0,
                    "latest_turn_at": "",
                    "generated_at": now_ts(),
                    "fallback_mode": True,
                },
            }
        )

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

@app.route("/api/dm/conversations")
def api_dm_conversations():
    tenant_slug = str(request.args.get("tenant") or "").strip().lower()
    include_fan_threads = is_feature_enabled("fan_interaction")
    return jsonify(gen_dm_conversations(tenant_slug=tenant_slug, include_fan_threads=include_fan_threads))


@app.route("/api/dm/center")
def api_dm_center():
    tenant_slug = str(request.args.get("tenant") or "").strip().lower()
    body = request.get_json(silent=True) or {}
    actor = resolve_dm_actor(body, tenant_slug=tenant_slug)
    payload = build_dm_center_payload(
        tenant_slug=actor.get("tenant_slug") or tenant_slug,
        actor_role=actor.get("role") or "",
        actor_profile_id=str((actor.get("profile") or {}).get("username") or "").strip(),
        include_fan_threads=is_feature_enabled("fan_interaction"),
    )
    return jsonify({"success": True, **payload})

@app.route("/api/dm/messages/<thread_id>")
def api_dm_messages(thread_id):
    tenant_slug = str(request.args.get("tenant") or "").strip().lower()
    actor = resolve_dm_actor({}, tenant_slug=tenant_slug)
    tenant = get_tenant_by_slug(actor.get("tenant_slug") or tenant_slug)
    state = resolve_tenant_message_center_state(tenant, tenant.get("message_center_state"))
    thread_index = find_message_thread_index(state["threads"], thread_id=thread_id)
    if thread_index < 0:
        return jsonify([])
    thread = state["threads"][thread_index]
    if str(actor.get("role") or "").strip().lower() == "investor":
      if str(thread.get("type") or "").strip() != "fan_interaction":
          return jsonify([])
      if str(thread.get("user_profile_id") or "").strip() != str((actor.get("profile") or {}).get("username") or "").strip():
          return jsonify([])
    return jsonify(copy.deepcopy(thread.get("messages") or []))


@app.route("/api/dm/threads/<thread_id>/read", methods=["POST"])
def api_dm_mark_read(thread_id):
    body = request.get_json(silent=True) or {}
    tenant_slug = str(body.get("tenant_slug") or request.args.get("tenant") or "").strip().lower()
    actor = resolve_dm_actor(body, tenant_slug=tenant_slug)
    normalized_thread, latest_state = mark_message_thread_read(actor.get("tenant_slug") or tenant_slug, thread_id, actor.get("role") or "")
    if not normalized_thread:
        return jsonify({"success": False, "error": "thread_not_found"}), 404
    payload = build_dm_center_payload(
        tenant_slug=actor.get("tenant_slug") or tenant_slug,
        actor_role=actor.get("role") or "",
        actor_profile_id=str((actor.get("profile") or {}).get("username") or "").strip(),
        include_fan_threads=is_feature_enabled("fan_interaction"),
    )
    return jsonify({"success": True, "thread": normalized_thread, "message_center_state": latest_state, **payload})

@app.route("/api/dm/send", methods=["POST"])
def api_dm_send():
    if not is_feature_enabled("fan_interaction"):
        return jsonify({"success": False, "error": "fan_interaction_disabled"}), 403
    body = request.get_json(silent=True) or {}
    thread_id = str(body.get("thread_id") or body.get("kol_id") or "").strip()
    tenant_slug = str(body.get("tenant_slug") or request.args.get("tenant") or "").strip().lower()
    content = str(body.get("content") or "").strip()
    if not content:
        return jsonify({"success": False, "error": "content_required"}), 400
    actor = resolve_dm_actor(body, tenant_slug=tenant_slug)
    actor_role = actor.get("role") or ""
    actor_profile = actor.get("profile") or {}
    tenant_slug = actor.get("tenant_slug") or tenant_slug or get_default_tenant_slug()
    tenant = get_tenant_by_slug(tenant_slug)
    state = resolve_tenant_message_center_state(tenant, tenant.get("message_center_state"))
    threads = copy.deepcopy(state["threads"] or [])
    now_text = now_ts()

    if actor_role == "investor":
        if not actor_profile:
            return jsonify({"success": False, "error": "investor_profile_required"}), 403
        profile_id = str(actor_profile.get("username") or "").strip()
        thread_index = find_message_thread_index(
            threads,
            thread_id=thread_id,
            user_profile_id=profile_id,
        )
        if thread_index < 0:
            base_thread = build_message_thread_for_user(actor_profile, tenant, first_message=content)
            threads.insert(0, base_thread)
            thread_index = 0
        elif str(threads[thread_index].get("type") or "").strip() != "fan_interaction":
            return jsonify({"success": False, "error": "thread_type_invalid"}), 400
        thread = dict(threads[thread_index])
        messages = copy.deepcopy(thread.get("messages") or [])
        next_message_id = len(messages) + 1
        messages.append({"id": next_message_id, "sender": "user", "content": content, "time": now_text, "type": "text"})
        thread["messages"] = messages[-120:]
        thread["content"] = content
        thread["last_msg"] = summarize_message_preview(content, limit=72)
        thread["time"] = "刚刚"
        thread["status"] = "待回复"
        thread["kol_unread"] = max(1, int(thread.get("kol_unread") or 0) + 1)
        thread["user_unread"] = 0
        thread["last_sender"] = "user"
        thread["last_message_type"] = "text"
        thread["user_profile_id"] = profile_id
        thread["user_name"] = actor_profile.get("username") or thread.get("user_name")
        thread["user_avatar"] = actor_profile.get("avatar") or thread.get("user_avatar")
        thread["tier"] = actor_profile.get("membership") or thread.get("tier")
        normalized_thread = normalize_message_thread_item(thread, tenant, index=thread_index)
        threads.pop(thread_index)
        threads.insert(0, normalized_thread)
        _, latest_state = save_tenant_message_threads(tenant_slug, state, threads)
        payload = build_dm_center_payload(
            tenant_slug=tenant_slug,
            actor_role=actor_role,
            actor_profile_id=profile_id,
            include_fan_threads=True,
        )
        return jsonify({
            "success": True,
            "thread_id": normalized_thread["id"],
            "message": messages[-1],
            "status": normalized_thread["status"],
            "message_center_state": latest_state,
            **payload,
            "threads": gen_dm_conversations(tenant_slug=tenant_slug, include_fan_threads=True),
        })

    if actor_role == "dav":
        if not thread_id:
            return jsonify({"success": False, "error": "thread_id_required"}), 400
        thread_index = find_message_thread_index(threads, thread_id=thread_id)
        if thread_index < 0:
            return jsonify({"success": False, "error": "thread_not_found"}), 404
        thread = dict(threads[thread_index])
        if str(thread.get("type") or "").strip() != "fan_interaction":
            return jsonify({"success": False, "error": "thread_type_invalid"}), 400
        messages = copy.deepcopy(thread.get("messages") or [])
        next_message_id = len(messages) + 1
        messages.append({"id": next_message_id, "sender": "kol", "content": content, "time": now_text, "type": "text"})
        thread["messages"] = messages[-120:]
        thread["content"] = content
        thread["last_msg"] = summarize_message_preview(content, limit=72)
        thread["time"] = "刚刚"
        thread["status"] = "已回复"
        thread["kol_unread"] = 0
        thread["user_unread"] = max(1, int(thread.get("user_unread") or 0) + 1)
        thread["last_sender"] = "kol"
        thread["last_message_type"] = "text"
        normalized_thread = normalize_message_thread_item(thread, tenant, index=thread_index)
        threads.pop(thread_index)
        threads.insert(0, normalized_thread)
        _, latest_state = save_tenant_message_threads(tenant_slug, state, threads)
        payload = build_dm_center_payload(
            tenant_slug=tenant_slug,
            actor_role=actor_role,
            actor_profile_id="",
            include_fan_threads=True,
        )
        return jsonify({
            "success": True,
            "thread_id": normalized_thread["id"],
            "message": messages[-1],
            "status": normalized_thread["status"],
            "message_center_state": latest_state,
            **payload,
            "threads": gen_dm_conversations(tenant_slug=tenant_slug, include_fan_threads=True),
        })

    return jsonify({"success": False, "error": "sender_role_invalid"}), 403

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
