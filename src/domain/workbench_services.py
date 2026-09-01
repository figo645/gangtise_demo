from collections import Counter

from src.runtime import *
from src.domain.core_services import *
from src.domain.market_services import *
from src.domain.ai_services import *

FAN_STOCK_OBSERVATION_WINDOW_DAYS = 7
FAN_STOCK_OBSERVATION_EVENT_TYPES = {"watchlist_detail_view", "watchlist_add"}
FAN_STOCK_HERMES_INTENTS = {"watchlist_fundamental", "multi_tool_research"}


def _parse_workbench_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(datetime.now().strftime(fmt))], fmt)
        except Exception:
            continue
    return None


def _count_users_within(users, start_at=None, end_at=None, predicate=None):
    count = 0
    for user in (users or []):
        if predicate and not predicate(user):
            continue
        created_at = _parse_workbench_datetime(user.get("created_at"))
        if start_at and (created_at is None or created_at < start_at):
            continue
        if end_at and (created_at is None or created_at >= end_at):
            continue
        count += 1
    return count


def _calc_change_pct(current_value, previous_value):
    current = float(current_value or 0)
    previous = float(previous_value or 0)
    if previous > 0:
        return round(((current - previous) / previous) * 100, 1)
    if current > 0:
        return 100.0
    return 0.0


def _categorize_tenant_view_path(path_value, tenant_slug=""):
    path = str(path_value or "").strip().lower()
    normalized_tenant = str(tenant_slug or "").strip().lower()
    if path.startswith("/h5"):
        return "H5前台"
    if normalized_tenant and path.startswith(f"/tenant/{normalized_tenant}"):
        return "租户门户"
    if path.startswith("/kol-workbench"):
        return "Web工作台"
    if path.startswith("/dashboard"):
        return "Dashboard"
    if path.startswith("/admin"):
        return "Admin"
    if path in {"", "/"}:
        return "首页"
    return "其他页面"


def build_tenant_view_analytics(tenant_slug=""):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    today_start = datetime.now().strftime("%Y-%m-%d 00:00:00")
    if not normalized_tenant:
        return {
            "total_views": 0,
            "active_viewers": 0,
            "distribution": [],
            "trend_7d": [],
        }
    try:
        rows = get_db().execute(
            """
            SELECT path, user_profile_id, ip, created_at
            FROM access_logs
            WHERE tenant_slug = ? AND user_role = ? AND created_at >= ?
            ORDER BY created_at DESC, id DESC
            """,
            (normalized_tenant, "investor", today_start),
        ).fetchall()
        trend_rows = get_db().execute(
            """
            SELECT created_at
            FROM access_logs
            WHERE tenant_slug = ? AND user_role = ? AND created_at >= ?
            ORDER BY created_at ASC, id ASC
            """,
            (
                normalized_tenant,
                "investor",
                (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d 00:00:00"),
            ),
        ).fetchall()
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        return {
            "total_views": 0,
            "active_viewers": 0,
            "distribution": [],
            "trend_7d": [],
            "fallback_mode": True,
        }
    category_counter = {}
    active_viewers = set()
    daily_counter = {}
    for row in rows:
        item = dict(row)
        category = _categorize_tenant_view_path(item.get("path"), normalized_tenant)
        category_counter[category] = category_counter.get(category, 0) + 1
        viewer_key = str(item.get("user_profile_id") or "").strip() or str(item.get("ip") or "").strip()
        if viewer_key:
            active_viewers.add(viewer_key)
    for row in trend_rows:
        item = dict(row)
        day_key = str(item.get("created_at") or "")[:10]
        if day_key:
            daily_counter[day_key] = daily_counter.get(day_key, 0) + 1
    trend = []
    for offset in range(6, -1, -1):
        target_day = (datetime.now() - timedelta(days=offset)).strftime("%Y-%m-%d")
        trend.append({
            "day": target_day[5:],
            "count": int(daily_counter.get(target_day, 0)),
        })
    distribution = [
        {"label": label, "value": value}
        for label, value in sorted(category_counter.items(), key=lambda pair: (-int(pair[1]), str(pair[0])))
    ]
    return {
        "total_views": len(rows),
        "active_viewers": len(active_viewers),
        "distribution": distribution,
        "trend_7d": trend,
    }


def build_tenant_ops_stats(tenant=None, investor_users=None, watchlist_comment_analytics=None):
    tenant = tenant or get_tenant_by_slug()
    tenant_slug = str((tenant or {}).get("slug") or "").strip().lower()
    users = investor_users if isinstance(investor_users, list) else list_users(role="investor", tenant_slug=tenant_slug)
    comment_analytics = watchlist_comment_analytics if isinstance(watchlist_comment_analytics, dict) else build_watchlist_comment_analytics(tenant_slug=tenant_slug)
    settings = load_tenant_fan_ops_settings(tenant_slug)
    registration_price = int(settings.get("registration_price") or 0)
    now = datetime.now()
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_month_end = current_month_start
    previous_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    paid_users = [user for user in users if bool(user.get("is_paid_sample"))]
    total_paid_samples = len(paid_users)
    new_paid_current_month = _count_users_within(
        paid_users,
        start_at=current_month_start,
        end_at=now + timedelta(seconds=1),
    )
    new_paid_previous_month = _count_users_within(
        paid_users,
        start_at=previous_month_start,
        end_at=previous_month_end,
    )
    monthly_revenue = registration_price * total_paid_samples
    paid_before_current_month = len([
        user for user in paid_users
        if (_parse_workbench_datetime(user.get("paid_sample_marked_at")) or _parse_workbench_datetime(user.get("created_at")))
        and (_parse_workbench_datetime(user.get("paid_sample_marked_at")) or _parse_workbench_datetime(user.get("created_at"))) < current_month_start
    ])
    previous_month_revenue = registration_price * paid_before_current_month
    revenue_change = _calc_change_pct(monthly_revenue, previous_month_revenue)
    paid_sample_delta = new_paid_current_month - new_paid_previous_month
    view_analytics = build_tenant_view_analytics(tenant_slug)
    total_fans = len(users)
    active_viewers = int(view_analytics.get("active_viewers") or 0)
    engagement_rate = round((active_viewers / total_fans) * 100, 1) if total_fans > 0 else 0.0
    comment_summary = comment_analytics.get("summary") if isinstance(comment_analytics.get("summary"), dict) else {}
    return {
        "total_followers": total_fans,
        "vip_subscribers": total_paid_samples,
        "monthly_revenue": monthly_revenue,
        "revenue_change": revenue_change,
        "registration_price": registration_price,
        "new_paid_samples_month": new_paid_current_month,
        "paid_sample_delta": paid_sample_delta,
        "today_views": int(view_analytics.get("total_views") or 0),
        "today_active_viewers": active_viewers,
        "today_view_distribution": view_analytics.get("distribution") or [],
        "today_view_trend_7d": view_analytics.get("trend_7d") or [],
        "engagement_rate": engagement_rate,
        "stock_comment_count": int(comment_summary.get("total_comments") or 0),
        "stock_comment_stock_count": int(comment_summary.get("stock_count") or 0),
        "fan_ops_settings": settings,
    }


def build_tenant_business_analytics(investor_users=None, ops_stats=None):
    users = investor_users if isinstance(investor_users, list) else []
    stats = ops_stats if isinstance(ops_stats, dict) else {}
    price = int(stats.get("registration_price") or 0)
    active_users = [user for user in users if str(user.get("status") or "active") == "active"]
    paid_users = [user for user in users if bool(user.get("is_paid_sample"))]
    high_frequency_users = [user for user in users if "高频用户" in (user.get("labels") or [])]
    label_counter = Counter()
    source_groups = {}
    now = datetime.now()
    month_starts = []
    cursor = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for _ in range(6):
        month_starts.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    month_starts.reverse()
    monthly_series = []
    for month_start in month_starts:
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        paid_added = 0
        paid_cumulative = 0
        fan_added = 0
        for user in users:
            created_at = _parse_workbench_datetime(user.get("created_at"))
            paid_at = _parse_workbench_datetime(user.get("paid_sample_marked_at")) or created_at
            if created_at and month_start <= created_at < next_month:
                fan_added += 1
            if bool(user.get("is_paid_sample")) and paid_at:
                if month_start <= paid_at < next_month:
                    paid_added += 1
                if paid_at < next_month:
                    paid_cumulative += 1
        monthly_series.append({
            "month": month_start.strftime("%Y-%m"),
            "fans_added": fan_added,
            "paid_added": paid_added,
            "paid_cumulative": paid_cumulative,
            "revenue": paid_cumulative * price,
        })
    for user in users:
        labels = user.get("labels") if isinstance(user.get("labels"), list) else []
        for label in labels:
            if str(label or "").strip():
                label_counter[str(label).strip()] += 1
        source = str(user.get("source_label") or "未标注来源").strip() or "未标注来源"
        bucket = source_groups.setdefault(source, {"label": source, "fans": 0, "paid": 0, "revenue": 0})
        bucket["fans"] += 1
        if bool(user.get("is_paid_sample")):
            bucket["paid"] += 1
            bucket["revenue"] += price
    funnel = [
        {"label": "租户粉丝", "count": len(users)},
        {"label": "活跃粉丝", "count": len(active_users)},
        {"label": "付费用户", "count": len(paid_users)},
        {"label": "高频用户", "count": len(high_frequency_users)},
    ]
    for bucket in source_groups.values():
        bucket["conversion_rate"] = round((bucket["paid"] / bucket["fans"]) * 100, 1) if bucket["fans"] else 0.0
    paid_high_frequency = len([user for user in paid_users if "高频用户" in (user.get("labels") or [])])
    segments = [
        {"label": "未付费用户", "count": max(0, len(users) - len(paid_users)), "revenue": 0},
        {"label": "付费用户", "count": max(0, len(paid_users) - paid_high_frequency), "revenue": max(0, len(paid_users) - paid_high_frequency) * price},
        {"label": "高频用户", "count": paid_high_frequency, "revenue": paid_high_frequency * price},
    ]
    return {
        "pricing": price,
        "total_fans": len(users),
        "active_fans": len(active_users),
        "paid_fans": len(paid_users),
        "high_frequency_fans": len(high_frequency_users),
        "estimated_revenue": price * len(paid_users),
        "funnel": funnel,
        "source_rows": sorted(source_groups.values(), key=lambda item: (-item["fans"], item["label"])),
        "label_distribution": [{"label": label, "value": count} for label, count in sorted(label_counter.items(), key=lambda item: (-item[1], item[0]))],
        "monthly_series": monthly_series,
        "segments": segments,
    }


def build_admin_commission_payload():
    """Build settlement estimates from persisted tenant fan/payment data."""
    rows = []
    for tenant in get_tenant_configs():
        tenant_slug = str(tenant.get("slug") or "").strip().lower()
        if not tenant_slug:
            continue
        users = [user for user in list_users(role="investor", tenant_slug=tenant_slug) if isinstance(user, dict)]
        ops_stats = build_tenant_ops_stats(tenant=tenant, investor_users=users)
        revenue = int(ops_stats.get("monthly_revenue") or 0)
        raw_rate = tenant.get("commission_rate", tenant.get("settlement_rate", 0))
        try:
            rate = float(raw_rate or 0)
        except (TypeError, ValueError):
            rate = 0.0
        if rate > 1:
            rate /= 100
        rate = max(0.0, min(1.0, rate))
        payable = round(revenue * rate, 2)
        rows.append({
            "tenant_slug": tenant_slug,
            "advisor": str(tenant.get("advisor") or tenant.get("name") or tenant_slug),
            "tenant_name": str(tenant.get("name") or tenant_slug),
            "tier": str(tenant.get("tier") or "未分层"),
            "source": "付费用户标注 × 注册单价",
            "fan_count": len(users),
            "paid_count": int(ops_stats.get("vip_subscribers") or 0),
            "registration_price": int(ops_stats.get("registration_price") or 0),
            "revenue": revenue,
            "share_rate": round(rate * 100, 2),
            "payable": payable,
            "status": "待结算" if payable > 0 else "暂无应结算",
        })
    pending = round(sum(float(row["payable"]) for row in rows), 2)
    active_rows = [row for row in rows if row["revenue"] > 0]
    return {
        "basis": "真实用户表中的付费标注与租户注册单价",
        "settlement_records_supported": False,
        "pending_total": pending,
        "settled_total": 0,
        "advisor_count": len(active_rows),
        "average_payable": round(pending / len(active_rows), 2) if active_rows else 0,
        "rows": rows,
        "generated_at": now_ts(),
    }


def build_admin_revenue_analytics_payload(tenant_slug=""):
    """Build revenue charts from actual paid markers and tenant pricing."""
    normalized_tenant = str(tenant_slug or "").strip().lower()
    users = [
        user for user in (
            list_users(role="investor", tenant_slug=normalized_tenant)
            if normalized_tenant else list_users(role="investor")
        )
        if isinstance(user, dict)
    ]
    tenant_configs = get_tenant_configs()
    if normalized_tenant:
        tenant_configs = [
            tenant for tenant in tenant_configs
            if str(tenant.get("slug") or "").strip().lower() == normalized_tenant
        ]
    tenants = {str(tenant.get("slug") or "").strip().lower(): tenant for tenant in tenant_configs}
    prices = {}
    for slug in tenants:
        prices[slug] = int(load_tenant_fan_ops_settings(slug).get("registration_price") or 0)
    tenant_revenue = []
    for slug, tenant in tenants.items():
        tenant_users = [user for user in users if str(user.get("tenant_slug") or "").strip().lower() == slug]
        paid_count = sum(1 for user in tenant_users if bool(user.get("is_paid_sample")))
        tenant_revenue.append({
            "tenant_slug": slug,
            "name": str(tenant.get("advisor") or tenant.get("name") or slug),
            "fans": len(tenant_users),
            "paid_users": paid_count,
            "registration_price": prices[slug],
            "revenue": paid_count * prices[slug],
        })
    tenant_revenue.sort(key=lambda item: (-item["revenue"], item["name"]))
    now = datetime.now()
    cursor = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_starts = []
    for _ in range(12):
        month_starts.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    month_starts.reverse()
    monthly = []
    for month_start in month_starts:
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        paid_users = []
        for user in users:
            if not bool(user.get("is_paid_sample")):
                continue
            paid_at = _parse_workbench_datetime(user.get("paid_sample_marked_at")) or _parse_workbench_datetime(user.get("created_at"))
            if paid_at and paid_at < next_month:
                paid_users.append(user)
        revenue = sum(prices.get(str(user.get("tenant_slug") or "").lower(), 0) for user in paid_users)
        monthly.append({"month": month_start.strftime("%Y-%m"), "revenue": revenue, "users": len(paid_users)})
    channel_revenue = {}
    for user in users:
        if not bool(user.get("is_paid_sample")):
            continue
        channel = str(user.get("h5_channel_label") or user.get("source_label") or "未标注渠道").strip() or "未标注渠道"
        channel_revenue[channel] = channel_revenue.get(channel, 0) + prices.get(str(user.get("tenant_slug") or "").lower(), 0)
    current_paid = monthly[-1]["users"] if monthly else 0
    current_revenue = monthly[-1]["revenue"] if monthly else 0
    previous_revenue = monthly[-2]["revenue"] if len(monthly) > 1 else 0
    mom = round((current_revenue - previous_revenue) / previous_revenue * 100, 1) if previous_revenue else 0
    cohorts = []
    for month_start in month_starts:
        cohort_users = [
            user for user in users
            if (_parse_workbench_datetime(user.get("created_at")) or now).strftime("%Y-%m") == month_start.strftime("%Y-%m")
        ]
        cohorts.append({"cohort": month_start.strftime("%Y-%m"), "data": [100] + [None] * 5, "users": len(cohort_users)})
    priced_tenants = [item for item in tenant_revenue if item["registration_price"] > 0]
    return {
        "generated_at": now_ts(),
        "basis": "用户表付费标注、付费时间、租户注册单价",
        "kol_filter": normalized_tenant,
        "kol_options": build_admin_kol_options(tenant_configs),
        "monthly": monthly,
        "tier_revenue": [
            {"name": "未付费用户", "data": [0] * len(monthly)},
            {"name": "付费用户", "data": [item["revenue"] for item in monthly]},
        ],
        "channel_revenue": [{"name": name, "revenue": value} for name, value in sorted(channel_revenue.items(), key=lambda item: (-item[1], item[0]))],
        "cohorts": cohorts,
        "tenant_revenue": tenant_revenue,
        "active_tenants": len(priced_tenants),
        "average_price": round(sum(item["registration_price"] for item in priced_tenants) / len(priced_tenants), 2) if priced_tenants else 0,
        "mrr": current_revenue,
        "arr": current_revenue * 12,
        "mom": mom,
        "paid_users": current_paid,
    }


def build_admin_kol_analytics_payload(tenant_slug=""):
    """Build KOL collaboration analytics from real tenant fan data."""
    normalized_tenant = str(tenant_slug or "").strip().lower()
    rows = []
    tenant_configs = get_tenant_configs()
    if normalized_tenant:
        tenant_configs = [
            tenant for tenant in tenant_configs
            if str(tenant.get("slug") or "").strip().lower() == normalized_tenant
        ]
    for tenant in tenant_configs:
        slug = str(tenant.get("slug") or "").strip().lower()
        if not slug:
            continue
        users = [user for user in list_users(role="investor", tenant_slug=slug) if isinstance(user, dict)]
        settings = load_tenant_fan_ops_settings(slug)
        price = int(settings.get("registration_price") or 0)
        paid_count = sum(1 for user in users if bool(user.get("is_paid_sample")))
        revenue = paid_count * price
        raw_rate = tenant.get("commission_rate", tenant.get("settlement_rate", 0))
        try:
            rate = float(raw_rate or 0)
        except (TypeError, ValueError):
            rate = 0.0
        if rate > 1:
            rate /= 100
        rows.append({
            "name": str(tenant.get("advisor") or tenant.get("name") or slug),
            "platform": str(tenant.get("name") or "租户门户"),
            "fans": len(users),
            "gmv": revenue,
            "commission": round(revenue * rate, 2),
            "rate": round(rate * 100, 2),
            "tier": str(tenant.get("tier") or "未分层"),
            "trend": "--",
        })
    rows.sort(key=lambda item: (-item["gmv"], item["name"]))
    tier_counts = {}
    for row in rows:
        tier_counts[row["tier"]] = tier_counts.get(row["tier"], 0) + 1
    months = []
    cursor = datetime.now().replace(day=1).replace(hour=0, minute=0, second=0, microsecond=0)
    for _ in range(12):
        months.append(cursor.strftime("%Y-%m"))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    months.reverse()
    growth = {tier: [None] * 11 + [count] for tier, count in tier_counts.items()}
    rates = [row["rate"] for row in rows if row["rate"] > 0]
    return {
        "generated_at": now_ts(),
        "basis": "租户配置、粉丝用户表、付费标注与注册单价",
        "kol_filter": normalized_tenant,
        "kol_options": build_admin_kol_options(tenant_configs),
        "rows": rows,
        "total_kols": len(rows),
        "total_revenue": sum(row["gmv"] for row in rows),
        "average_rate": round(sum(rates) / len(rates), 2) if rates else 0,
        "top_kol": rows[0]["name"] if rows else "--",
        "months": months,
        "tier_growth": growth,
        "tier_counts": tier_counts,
    }


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
    user_names = {}
    if not fallback_mode and tenant_slug:
        try:
            db = get_db()
            detail_rows = db.execute(
                """
                SELECT user_profile_id, stock_code, stock_name, sector_name, event_type, entry_point, source_detail, created_at,
                       is_simulated, simulation_batch_code, simulation_label
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
            user_names = {
                str(item.get("username") or "").strip(): str(item.get("username") or "").strip()
                for item in list_users(role="investor", tenant_slug=tenant_slug)
                if str(item.get("username") or "").strip()
            }
        except Exception as exc:
            if not is_db_unavailable_error(exc):
                raise
            detail_rows = []
            hermes_rows = []
    sector_map = {}
    fan_watchlist_map = {}
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
        if str(item.get("event_type") or "").strip().lower() == "watchlist_add":
            code = _normalize_fan_stock_code(stock_code=item.get("stock_code"), stock_name=item.get("stock_name"))
            detail = details_map.get(code) if code else None
            user_profile_id = str(item.get("user_profile_id") or "").strip()
            if detail and user_profile_id:
                fan_watchlist_map[(user_profile_id, code)] = {
                    "user_profile_id": user_profile_id,
                    "fan_name": user_names.get(user_profile_id) or user_profile_id,
                    "code": code,
                    "name": str(detail.get("name") or code).strip() or code,
                    "market": "港股" if str(detail.get("market") or "").upper() == "HK" else "A股",
                    "focus": str(detail.get("industry") or detail.get("focus") or "其他板块").strip() or "其他板块",
                    "change": (
                        f"{float(detail.get('change_pct')):+.1f}%"
                        if detail.get("change_pct") is not None and not bool(detail.get("data_unavailable"))
                        else "行情待同步"
                    ),
                    "thesis": str(detail.get("signal_summary") or ((detail.get("fundamental") or {}).get("summary")) or "继续跟踪").strip() or "继续跟踪",
                    "added_at": str(item.get("created_at") or "").strip(),
                    "is_simulated": bool(item.get("is_simulated")),
                    "simulation_label": str(item.get("simulation_label") or "").strip(),
                    "simulation_batch_code": str(item.get("simulation_batch_code") or "").strip(),
                }
            continue
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
    fan_watchlist_items = sorted(
        fan_watchlist_map.values(),
        key=lambda item: (str(item.get("fan_name") or ""), str(item.get("code") or "")),
    )
    fan_watchlist_sector_counter = Counter(item.get("focus") or "其他板块" for item in fan_watchlist_items)
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
        "fan_watchlist_items": fan_watchlist_items,
        "fan_watchlist_sector_distribution": [
            {"label": sector, "value": count}
            for sector, count in sorted(fan_watchlist_sector_counter.items(), key=lambda pair: (-pair[1], pair[0]))
        ],
        "fallback_mode": bool(fallback_mode),
        "tracked_stock_codes": active_codes[:8],
    }


TENANT_WATCHLIST_CODES = {
    "laowang": ["600519", "300750", "00700", "688981", "600036"],
    "lisa": ["00700", "03690", "09988"],
}


def build_tenant_watchlist_hub_items(tenant, watchlist_details_map):
    tenant_slug = str((tenant or {}).get("slug") or "").strip().lower()
    target_codes = TENANT_WATCHLIST_CODES.get(tenant_slug, TENANT_WATCHLIST_CODES["laowang"])
    return [
        {
            "name": detail["name"],
            "code": detail["code"],
            "market": "港股" if detail.get("market") == "HK" else "A股",
            "focus": detail.get("focus") or detail.get("industry") or "个股跟踪",
            "change": (
                f"{float(detail.get('change_pct')):+.1f}%"
                if detail.get("change_pct") is not None and not bool(detail.get("data_unavailable"))
                else "行情待同步"
            ),
            "thesis": detail.get("signal_summary") or detail.get("fundamental", {}).get("summary") or "继续跟踪",
            "alert_level": detail.get("alert_level") or "normal",
            "alert_text": detail.get("alert_text") or "当前无明显预警",
            "related_indicator_names": detail.get("related_indicator_names") or [],
        }
        for detail in [watchlist_details_map.get(code) for code in target_codes]
        if detail
    ]


def build_workbench_data_lake_payload(tenant, watchlist_details=None, news_items=None):
    """Unify persisted market, sector, and cleaned-news assets for the KOL view."""
    market_payload = build_market_overview_payload()
    sector_payload = build_market_sector_overview_payload()
    market_items = [item for item in (market_payload.get("items") or []) if isinstance(item, dict)]
    sector_items = [item for item in (sector_payload.get("items") or []) if isinstance(item, dict)]
    news_rows = [item for item in (news_items or []) if isinstance(item, dict)]
    return {
        "market_overview": {
            "items": market_items,
            "source": str(market_payload.get("source") or "Gangtise OpenAPI"),
            "updated_at": str(market_payload.get("updated_at") or ""),
            "stale": bool(market_payload.get("stale")),
            "message": str(market_payload.get("message") or ""),
            "expected_count": len(MARKET_OVERVIEW_INDEX_CODES),
        },
        "sectors": {
            "items": sector_items,
            "source": str(sector_payload.get("source") or "Gangtise OpenAPI"),
            "updated_at": str(sector_payload.get("updated_at") or ""),
            "stale": bool(sector_payload.get("stale")),
            "message": str(sector_payload.get("message") or ""),
            "expected_count": len(SHENWAN_LEVEL1_INDUSTRIES),
        },
        "news": {
            "items": news_rows,
            "source": "国内公开信息源清洗新闻湖",
            "updated_at": max((str(item.get("published_at") or item.get("fetched_at") or "") for item in news_rows), default=""),
            "message": "只纳入通过清洗且满足每来源最少 5 条有效信息门槛的数据源。",
        },
    }


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
        "watchlist_comment_analytics": workbench.get("watchlist_comment_analytics") or {},
        "fan_management": workbench.get("fan_management") or {},
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
            "title": "小金智能体对话",
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
    # Keep tenant-specific demo metrics consistent with the other workbench builders.
    is_lisa = str(tenant.get("slug") or "").strip().lower() == "lisa"
    tenant_portal_enabled = is_feature_enabled("tenant_portal")
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
    # Review selection must use the DAv's persisted watchlist. The old
    # tenant-level demo list made the workbench disagree with H5.
    watchlist_items = []
    if not fallback_mode:
        try:
            dav_users = list_users(role="dav", tenant_slug=tenant["slug"])
            dav_user = next(
                (
                    item for item in dav_users
                    if str(item.get("advisor_name") or item.get("username") or "").strip() == kol_name
                ),
                dav_users[0] if dav_users else None,
            )
            dav_profile_id = str((dav_user or {}).get("username") or kol_name).strip()
            if dav_profile_id:
                watchlist_items = list_user_watchlist_items(tenant["slug"], dav_profile_id)
        except Exception as exc:
            if not is_db_unavailable_error(exc):
                raise
            watchlist_items = []
    watchlist_focus = [
        str(item.get("name") or "").strip()
        for item in watchlist_items
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    fund_dashboard_state = resolve_tenant_fund_dashboard_state(tenant, tenant.get("fund_dashboard_config"))
    fund_dashboard = copy.deepcopy(fund_dashboard_state["published"])
    knowledge_enabled = is_feature_enabled("knowledge")
    knowledge_hub = fetch_live_knowledge_hub(tenant) if knowledge_enabled else {"items": [], "summary": {}}
    indicator_hub = build_indicator_hub_fallback(tenant=tenant, admin_view=False) if fallback_mode else build_indicator_hub(tenant=tenant, admin_view=False)
    news_items = gen_news_feed(tenant=tenant, watchlist_details=watchlist_details_map)
    data_lake = build_workbench_data_lake_payload(tenant, watchlist_details_map, news_items)
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
    ops_stats = build_tenant_ops_stats(
        tenant=tenant,
        investor_users=investor_users,
        watchlist_comment_analytics=watchlist_comment_analytics,
    )
    business_analytics = build_tenant_business_analytics(investor_users=investor_users, ops_stats=ops_stats)
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
                "label": "纯 Admin 后台",
                "url": "/admin?section=kols",
                "desc": "查看平台侧的大V租户管理、能力开关、一致性巡检和审计入口。"
            },
        ] + ([{
            "label": "租户门户",
            "url": f"/tenant/{tenant['slug']}",
            "desc": f"查看 {tenant['advisor']} 对外的专属租户门户，重点承接品牌表达、已发布内容和粉丝入口。"
        }] if tenant_portal_enabled else []),
        "stats": {
            "total_followers": ops_stats["total_followers"],
            "vip_subscribers": ops_stats["vip_subscribers"],
            "monthly_revenue": ops_stats["monthly_revenue"],
            "revenue_change": ops_stats["revenue_change"],
            "unread_messages": message_center_stats["unread_messages"],
            "pending_replies": message_center_stats["pending_replies"],
            "today_views": ops_stats["today_views"],
            "today_active_viewers": ops_stats["today_active_viewers"],
            "today_view_distribution": ops_stats["today_view_distribution"],
            "today_view_trend_7d": ops_stats["today_view_trend_7d"],
            "engagement_rate": ops_stats["engagement_rate"],
            "registration_price": ops_stats["registration_price"],
            "new_paid_samples_month": ops_stats["new_paid_samples_month"],
            "paid_sample_delta": ops_stats["paid_sample_delta"],
            "stock_comment_count": ops_stats["stock_comment_count"],
            "stock_comment_stock_count": ops_stats["stock_comment_stock_count"],
            "fan_ops_settings": ops_stats["fan_ops_settings"],
        },
        "business_analytics": business_analytics,
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
        "portal_workspace": resolve_tenant_portal_workspace(tenant, tenant.get("portal_cms")) if tenant_portal_enabled else {},
        "message_center": {
            "summary": message_center_state["summary"],
            "items": build_message_center_items((fan_threads + review_notice_threads)[:6], limit=6),
            "threads": copy.deepcopy(message_center_state["threads"]),
        },
        "fan_management": {
            "summary": "这里看的是大V自己的粉丝分层，不是平台总用户。重点管理高频互动、付费意向、机构试点和沉默粉丝的经营动作。",
            "stats": {
                "total_fans": len(investor_users),
                "new_fans_7d": _count_users_within(
                    investor_users,
                    start_at=datetime.now() - timedelta(days=7),
                    end_at=datetime.now() + timedelta(seconds=1),
                ),
                "active_fans_30d": len(investor_users),
                "paying_fans": ops_stats["vip_subscribers"],
            },
            "settings": ops_stats["fan_ops_settings"],
            "fans": [
                {
                    "id": user.get("id"),
                    "name": user["username"],
                    "tier": user["membership"],
                    "source": user.get("source_label") or "用户导入",
                    "joined": str(user.get("created_at") or "--")[:10],
                    "value": f"手机号 {mask_phone(user.get('phone'))}",
                    "status": user["status"] == "active" and "活跃" or "已禁用",
                    "is_paid_sample": bool(user.get("is_paid_sample")),
                    "paid_sample_note": user.get("paid_sample_note") or "",
                    "labels": user.get("labels") or [],
                }
                for user in investor_users
            ] or [
                {"name": "暂无粉丝", "tier": "--", "source": "--", "joined": "--", "value": "请先在用户管理中添加普通用户", "status": "待录入"}
            ],
        },
        "dashboard_metrics": {
            "summary": "这里整合的是大V自己的经营 Dashboard，口径覆盖粉丝增长、粉丝注册费、总注册收入、其他收入、token 消耗、消息数量分布和趋势、发布数量及类型趋势。",
            "kpis": [
                {"label": "本月协同收入", "value": f"¥{ops_stats['monthly_revenue']:,}", "sub": "付费样本 × 当前定价", "trend": "up" if ops_stats["monthly_revenue"] >= 0 else "down", "badge": f"{ops_stats['revenue_change']:+.1f}%"},
                {"label": "当前注册定价", "value": f"¥{ops_stats['registration_price']:,}", "sub": "每位付费样本单价", "trend": "up", "badge": "可在粉丝管理修改"},
                {"label": "高频付费样本", "value": str(ops_stats["vip_subscribers"]), "sub": "当前租户已标注", "trend": "up", "badge": f"本月新增 {ops_stats['new_paid_samples_month']} 位"},
                {"label": "个股留言数量", "value": str(ops_stats["stock_comment_count"]), "sub": f"覆盖 {ops_stats['stock_comment_stock_count']} 只股票", "trend": "up", "badge": "含粉丝与大V留言"},
                {"label": "今日浏览", "value": str(ops_stats["today_views"]), "sub": f"活跃粉丝 {ops_stats['today_active_viewers']} 位", "trend": "up", "badge": "来自粉丝用户访问"},
            ],
            "message_distribution": [
                {"label": "粉丝私信", "value": len(fan_threads)},
                {"label": "复盘提醒", "value": len(review_notice_threads)},
                {"label": "个股留言", "value": ops_stats["stock_comment_count"]},
                {"label": "个股观察", "value": int((fan_stock_observation.get("totals") or {}).get("interactions") or 0)},
            ],
            "message_trend": ops_stats["today_view_trend_7d"],
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
                        {"label": "小金智能体问答", "value": 24},
                        {"label": "消息追问", "value": 18},
                        {"label": "自选股跟踪", "value": 16},
                    ],
                    "heatmap_columns": ["内容触达", "私域留资", "激活试用", "首次付费", "高频留存"],
                    "heatmap_rows": [
                        {"label": "复盘专区", "values": [100, 18.2, 8.4, 2.2, 0.8]},
                        {"label": "小金智能体", "values": [100, 14.8, 9.6, 3.4, 1.2]},
                        {"label": "消息区", "values": [100, 22.1, 11.2, 3.8, 1.5]},
                        {"label": "自选股", "values": [100, 12.4, 6.7, 2.1, 0.9]},
                    ],
                },
                "channel": {
                    "summary": "看当前租户各获客和互动来源的质量，而不是平台总渠道。",
                    "cards": [
                        {"label": "复盘转化", "users": "620", "conv": "8.4%", "revenue": "¥26,800", "score": 88},
                        {"label": "小金智能体转化", "users": "410", "conv": "11.2%", "revenue": "¥24,300", "score": 92},
                        {"label": "消息追问", "users": "260", "conv": "15.6%", "revenue": "¥18,600", "score": 95},
                        {"label": "社群转介绍", "users": "170", "conv": "18.1%", "revenue": "¥16,200", "score": 97},
                    ],
                    "quality_rows": [
                        {"label": "复盘转化", "users": 620, "cac": 32, "ltv": 620, "conv": "8.4%", "score": 88, "trend": "上升"},
                        {"label": "小金智能体转化", "users": 410, "cac": 24, "ltv": 760, "conv": "11.2%", "score": 92, "trend": "上升"},
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
                *([{"icon": "🎙️", "label": "语音口述", "desc": "收盘后直接口述行业主线、关键公司和操作复盘，智能体自动转写并抽取段落。"}] if is_feature_enabled("review_voice_input") else []),
                {"icon": "✍️", "label": "手动撰写", "desc": "提供富文本手写区域，大V自己决定文章段落、标题和表达顺序。"},
                {"icon": "📎", "label": "文件上传", "desc": "上传研报、纪要、Excel 和 PDF，由智能体统一抽取要点并转成复盘文案。"},
                *([{"icon": "🔗", "label": "URL 资料", "desc": "抓取网页资料并抽取正文，适合作为复盘证据链和背景补充。"}] if is_feature_enabled("review_url_input") else []),
            ],
            "paragraph_modes": [
                {"label": "大V自定段落", "desc": "适合自己写主框架，只让智能体补摘要、证据链和风险提示。"},
                {"label": "智能文案", "desc": "适合先交信息给智能体，并补充修改规则或常用提示词标签后生成草稿。"},
            ],
            "default_flow": ["选择复盘周期", "确认本次自选股", "补充手输/文件", "设置智能文案规则", "生成草稿预览", "确认后发布给粉丝"],
            "watchlist_focus": watchlist_focus,
            "watchlist_items": watchlist_items,
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
        "watchlist_hub": {
            "summary": "维护大V自己的重点跟踪标的。行情、行业预警和关联指标与 H5 个股详情使用同一套数据口径。",
            "items": watchlist_hub_items,
        },
        "fan_stock_observation": fan_stock_observation,
        "watchlist_comment_analytics": watchlist_comment_analytics,
        "fund_dashboard": fund_dashboard,
        "fund_dashboard_state": fund_dashboard_state,
        "indicator_hub": indicator_hub,
        "data_lake": data_lake,
        "published_reviews": published_reviews,
        "consistency_notes": [
            {"title": "前后台分离", "desc": "首页同时展示纯 Admin 后台和大V web 工作台两个入口，角色职责分开。"},
            {"title": "消息口径一致", "desc": "H5、工作台和 Admin 都把“粉丝消息 + 大V回复 + 复盘提醒”视为同一消息链路。"},
            {"title": "小金智能体口径一致", "desc": "前台支持工作区版和小金纯对话版，后台也按同样两种产品模式管理。"},
            {"title": "知识库口径一致", "desc": "历史知识内容允许继续微调，修改后会重新同步到知识专区和 Hermes。"},
        ],
        "role_split": [
            {"side": "平台 Admin 保留", "items": ["功能控开", "访问审计", "活动管理", "平台级用户与渠道管理"]},
            {"side": "大V工作台保留", "items": ["粉丝消息", "群发助手", "复盘生产", "Hermes 研究与租户知识经营"]},
        ],
    }
