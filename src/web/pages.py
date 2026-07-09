from src.runtime import *
from src.services import *

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
    requested_tenant_slug = str(request.args.get("tenant") or "").strip().lower()
    try:
        current_demo_profile = get_current_demo_profile(site_config)
        effective_tenant_slug = requested_tenant_slug or (current_demo_profile.get("tenant", {}).get("slug") if current_demo_profile else None)
        tenant = get_tenant_by_slug(effective_tenant_slug, site_config)
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
        effective_tenant_slug = requested_tenant_slug or (current_demo_profile.get("tenant", {}).get("slug") if current_demo_profile else None)
        tenant = get_tenant_by_slug(effective_tenant_slug, fallback_config)
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
    site_config = get_site_config()
    kols = gen_kol_data()
    segments = gen_user_segments()
    try:
        access_stats = get_access_summary()
        indicator_hub = build_indicator_hub(admin_view=True)
        task_center = build_admin_task_center_payload()
        token_usage = build_admin_token_usage_payload()
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while building admin page, using fallback data")
        access_stats = build_access_summary_fallback()
        indicator_hub = build_indicator_hub_fallback(
            tenant=get_tenant_by_slug(get_default_tenant_slug(site_config), site_config),
            admin_view=True,
        )
        task_center = {"summary": {"total": 0, "enabled": 0, "running": 0, "failed": 0, "now": now_ts()}, "tasks": [], "runs": [], "runtime": {}}
        token_usage = {
            "summary_24h": {
                "request_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "avg_tokens_per_request": 0,
                "avg_latency_ms": 0,
                "total_latency_ms": 0,
                "total_latency_seconds": 0,
                "avg_total_tokens_per_second": 0,
                "avg_input_tokens_per_second": 0,
                "avg_output_tokens_per_second": 0,
                "p95_latency_ms": 0,
                "max_latency_ms": 0,
            },
            "summary_30d": {
                "request_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "avg_tokens_per_request": 0,
                "avg_latency_ms": 0,
                "total_latency_ms": 0,
                "total_latency_seconds": 0,
                "avg_total_tokens_per_second": 0,
                "avg_input_tokens_per_second": 0,
                "avg_output_tokens_per_second": 0,
                "p95_latency_ms": 0,
                "max_latency_ms": 0,
            },
            "hourly": [],
            "daily": [],
            "monthly": [],
            "features": [],
            "models": [],
            "model_daily": [],
            "recent_logs": [],
            "generated_at": now_ts(),
        }
    return render_template(
        "admin.html",
        kols=kols,
        segments=segments,
        access_stats=access_stats,
        indicator_hub=indicator_hub,
        task_center=task_center,
        token_usage=token_usage,
        brand=get_platform_brand(site_config),
        tenants=get_tenant_configs(site_config),
        default_tenant=get_tenant_by_slug(get_default_tenant_slug(site_config), site_config),
        site_config=site_config,
    )

@app.route("/kol-workbench")
def kol_workbench():
    site_config = get_site_config()
    tenant = get_active_tenant_from_request(site_config)
    try:
        workbench = gen_kol_workbench(tenant)
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while building workbench page, using fallback data")
        tenant = get_tenant_by_slug(tenant.get("slug"), site_config) if isinstance(tenant, dict) else get_tenant_by_slug(site_config=site_config)
        workbench = gen_kol_workbench(tenant, fallback_mode=True)
    return render_template("kol_workbench.html", workbench=workbench, brand=get_platform_brand(site_config), active_tenant=tenant)


@app.route("/tenant/<tenant_slug>")
def tenant_portal(tenant_slug):
    site_config = get_site_config()
    tenant = get_tenant_by_slug(tenant_slug, site_config)
    if not tenant or tenant["slug"] != tenant_slug:
        abort(404)
    try:
        portal = build_tenant_portal_payload(tenant)
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while building tenant portal, using fallback data")
        portal = build_tenant_portal_payload(tenant, fallback_mode=True)
    return render_template("tenant_portal.html", portal=portal, brand=get_platform_brand(site_config), active_tenant=tenant)

@app.route("/dashboard")
def dashboard():
    tenant = get_active_tenant_from_request()
    return redirect(url_for("tenant_portal", tenant_slug=tenant["slug"]))

