from src.runtime import *
from src.services import *
from src.web.api_core import get_access_summary
from src.web.request_helpers import safe_next_target


def resolve_login_destination(user, next_target):
    target = safe_next_target(next_target or "/h5")
    role = str((user or {}).get("role") or "").strip().lower()
    if role == "admin":
        # An administrator is not a tenant advisor. Never send the account
        # back into a role-specific page after an account switch.
        if target == "/admin" or target.startswith("/admin?") or target == "/intern-handbook":
            return target
        return url_for("admin")
    if role == "dav":
        return url_for("login_entry", next=target)
    if target == "/admin" or target.startswith("/admin?") or target == "/intern-handbook" or target.startswith("/kol-workbench"):
        return url_for("h5", tenant=str((user or {}).get("tenant_slug") or "").strip().lower() or None)
    return target


@app.route("/login", methods=["GET", "POST"])
def login():
    next_target = safe_next_target(request.args.get("next") or request.form.get("next") or "/h5")
    try:
        current_user = get_current_authenticated_user()
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        current_user = None
    if current_user:
        return redirect(resolve_login_destination(current_user, next_target))
    mode = "register" if request.args.get("mode") == "register" or request.form.get("mode") == "register" else "login"
    if request.method == "GET":
        return render_template("login.html", next_target=next_target, mode=mode, error=None, site_config=get_site_config())
    username = str(request.form.get("username") or "").strip()
    password = str(request.form.get("password") or "").strip()
    site_config = get_site_config()
    if mode == "register":
        display_name = str(request.form.get("display_name") or "").strip()
        confirm_password = str(request.form.get("confirm_password") or "").strip()
        if not display_name or not username or not password or not confirm_password:
            return render_template("login.html", next_target=next_target, mode=mode, error="请完整填写注册信息", site_config=site_config)
        if password != confirm_password:
            return render_template("login.html", next_target=next_target, mode=mode, error="两次输入的密码不一致", site_config=site_config)
        if len(password) < 6:
            return render_template("login.html", next_target=next_target, mode=mode, error="密码至少需要 6 位", site_config=site_config)
        try:
            tenant = get_tenant_by_slug(get_default_tenant_slug(site_config), site_config)
            suffix = int(time.time() * 1000) % 100000000
            user = create_user({
                "username": username,
                "password": password,
                "phone": f"139{suffix:08d}",
                "role": "investor",
                "tenant_slug": tenant.get("slug") or get_default_tenant_slug(site_config),
                "advisor_name": tenant.get("advisor") or "",
                "status": "active",
                "source_label": "Web账号注册",
            })
            save_h5_profile_settings(user, {"display_name": display_name})
            save_current_demo_profile_id(user["username"])
            return redirect(resolve_login_destination(user, next_target))
        except ValueError as exc:
            messages = {"username_exists": "用户名已存在，请更换一个", "invalid_user_payload": "注册信息无效，请检查填写内容"}
            return render_template("login.html", next_target=next_target, mode=mode, error=messages.get(str(exc), "注册失败，请稍后重试"), site_config=site_config)
        except Exception as exc:
            if is_db_unavailable_error(exc):
                return render_template("login.html", next_target=next_target, mode=mode, error="账户服务暂不可用，请稍后重试", site_config=site_config)
            raise
    if not username or not password:
        return render_template("login.html", next_target=next_target, mode=mode, error="请输入用户名和密码", site_config=site_config)
    try:
        user = verify_platform_password_login(username, password)
    except ValueError:
        return render_template("login.html", next_target=next_target, mode=mode, error="用户名或密码错误，或账号已停用", site_config=site_config)
    except Exception as exc:
        if is_db_unavailable_error(exc):
            return render_template("login.html", next_target=next_target, mode=mode, error="账户服务暂不可用，请稍后重试", site_config=site_config)
        raise
    save_current_demo_profile_id(user["username"])
    return redirect(resolve_login_destination(user, next_target))


@app.route("/login/entry")
def login_entry():
    user = get_current_authenticated_user()
    if not user:
        return redirect(url_for("login", next=safe_next_target(request.args.get("next") or "/h5")))
    next_target = safe_next_target(request.args.get("next") or "/h5")
    if str(user.get("role") or "").strip().lower() != "dav":
        return redirect(next_target)
    tenant_slug = str(user.get("tenant_slug") or "").strip().lower()
    h5_target = f"/h5?tenant={tenant_slug}" if tenant_slug else "/h5"
    workbench_target = next_target if next_target.startswith("/kol-workbench") else url_for("kol_workbench", tenant=tenant_slug, section="overview")
    return render_template(
        "login_entry.html",
        user=user,
        h5_target=h5_target,
        workbench_target=workbench_target,
    )


@app.route("/logout")
def logout():
    # A shared Flask session also carries release-unlock and onboarding state.
    # Logout must remove all of it so a following /login cannot resolve the
    # previous DAv account and redirect back to the entry-choice page.
    session.clear()
    g.current_demo_profile_id = ""
    return redirect(url_for("login"))


@app.route("/switch-account")
def switch_account():
    """Clear the shared session and keep the intended destination for the next user."""
    next_target = safe_next_target(request.args.get("next") or "/h5")
    session.clear()
    g.current_demo_profile_id = ""
    return redirect(url_for("login", next=next_target))


@app.route("/")
def index():
    config = get_site_config()
    tenants = get_tenant_configs(config)
    default_tenant = get_tenant_by_slug(get_default_tenant_slug(config), config)
    return render_template(
        "index.html",
        brand=get_platform_brand(config),
        tenants=tenants,
        default_tenant=default_tenant,
        tenant_portal_enabled=is_feature_enabled("tenant_portal", config),
    )

@app.route("/h5")
def h5():
    current_authenticated_user = get_current_authenticated_user()
    if not current_authenticated_user:
        return redirect(url_for("login", next=safe_next_target(request.full_path.rstrip("?"))))
    # Admin is a platform-governance account, not a tenant-scoped H5 user.
    # Keep the role boundary explicit before building tenant/user watchlist data.
    if str(current_authenticated_user.get("role") or "").strip().lower() == "admin":
        return redirect(url_for("admin"))
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
        auth_settings = get_auth_settings(site_config)
        demo_profiles = get_h5_login_users(site_config) if auth_settings.get("quick_select_enabled") else []
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while building H5 page, using fallback data")
        h5_fallback_mode = True
        fallback_config = normalize_site_config(site_config)
        demo_profiles, current_demo_profile = resolve_demo_profile_fallback(fallback_config)
        auth_settings = get_auth_settings(fallback_config)
        if auth_settings.get("quick_select_enabled") is not True:
            demo_profiles = []
        effective_tenant_slug = requested_tenant_slug or (current_demo_profile.get("tenant", {}).get("slug") if current_demo_profile else None)
        tenant = get_tenant_by_slug(effective_tenant_slug, fallback_config)
        indicator_hub = build_indicator_hub_fallback(tenant=tenant, admin_view=False)
        fundamental_column = build_fundamental_column_payload_from_hub(tenant, indicator_hub)
        dashboard_seed_cards = build_indicator_dashboard_seed_cards_from_hub(indicator_hub, count=8)
        tenant_dashboard_payload = build_tenant_dashboard_payload_fallback(tenant)
    # H5 uses the persisted owner-scoped watchlist. An explicit empty map is
    # intentional: it prevents the legacy demo catalog from reappearing after
    # the user removes their last stock.
    owner = current_demo_profile or current_authenticated_user or {}
    owner_tenant_slug = str(owner.get("tenant_slug") or ((owner.get("tenant") or {}).get("slug") if isinstance(owner.get("tenant"), dict) else "") or effective_tenant_slug or "").strip().lower()
    owner_profile_id = str(owner.get("username") or owner.get("id") or "").strip()
    try:
        user_watchlist_details = {}
        if owner_tenant_slug and owner_profile_id:
            user_watchlist_details = {
                str(item.get("code") or "").strip().upper(): item
                for item in list_user_watchlist_items(owner_tenant_slug, owner_profile_id)
                if isinstance(item, dict) and str(item.get("code") or "").strip()
            }
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("User watchlist unavailable while building H5 page")
        user_watchlist_details = {}
    market = gen_market_data(watchlist_details=user_watchlist_details)
    watchlist_details = user_watchlist_details
    news_payload = build_fundamental_news_payload(tenant=tenant, watchlist_details=watchlist_details, limit=10)
    news = news_payload.get("items") or []
    news_tabs = news_payload.get("tabs") or []
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
        news_tabs=news_tabs,
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
    current_user = get_current_authenticated_user() or {}
    # Admin is a multi-area console. Loading every analytical dataset before
    # returning its HTML makes the first navigation wait on unrelated queries.
    # The client requests each area's live payload after the user enters it.
    site_config_payload = {
        "brand": get_platform_brand(site_config),
        "tenants": get_tenant_configs(site_config),
        "default_theme": site_config.get("default_theme", "light"),
        "default_accent": site_config.get("default_accent", "blue"),
        "default_tenant_slug": get_default_tenant_slug(site_config),
        "feature_flags": dict(site_config.get("feature_flags") or {}),
    }
    empty_indicator_hub = {
        "summary": {"total": 0, "smart_total": 0, "lake_total": 0, "enabled": 0, "warnings": 0, "attention": 0, "anomalies": 0},
        "items": [], "anomalies": [], "smart_items": [], "lake_items": [], "definitions": [], "source_defs": [],
        "recent_tests": [], "load_batches": [], "raw_records": [], "mapping_rules": [], "clean_jobs": [],
    }
    empty_token_summary = {
        "request_count": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        "avg_tokens_per_request": 0, "avg_latency_ms": 0, "total_latency_ms": 0, "total_latency_seconds": 0,
        "avg_total_tokens_per_second": 0, "avg_input_tokens_per_second": 0, "avg_output_tokens_per_second": 0,
        "p95_latency_ms": 0, "max_latency_ms": 0,
    }
    task_center = {"summary": {"total": 0, "enabled": 0, "running": 0, "failed": 0, "now": now_ts()}, "tasks": [], "runs": [], "runtime": {}, "user_jobs": [], "user_job_runtime": {}}
    token_usage = {"summary_24h": dict(empty_token_summary), "summary_30d": dict(empty_token_summary), "hourly": [], "daily": [], "monthly": [], "features": [], "models": [], "model_daily": [], "recent_logs": [], "generated_at": ""}
    access_stats = {"summary": {"total": 0, "unique_ips": 0, "today": 0, "paths": 0}, "top_paths": [], "top_ips": [], "daily_counts": [], "recent_logs": []}
    return render_template(
        "admin.html",
        kols=[],
        segments=[],
        access_stats=access_stats,
        indicator_hub=empty_indicator_hub,
        task_center=task_center,
        token_usage=token_usage,
        brand=get_platform_brand(site_config),
        tenants=get_tenant_configs(site_config),
        default_tenant=get_tenant_by_slug(get_default_tenant_slug(site_config), site_config),
        site_config=site_config_payload,
        current_user=current_user,
    )

@app.route("/intern-handbook")
def intern_handbook():
    site_config = get_site_config()
    return render_template(
        "intern_handbook.html",
        brand=get_platform_brand(site_config),
        default_tenant=get_tenant_by_slug(get_default_tenant_slug(site_config), site_config),
    )

@app.route("/kol-workbench")
def kol_workbench():
    site_config = get_site_config()
    current_user = get_current_authenticated_user() or {}
    tenant = get_active_tenant_from_request(site_config)
    try:
        workbench = gen_kol_workbench(tenant)
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while building workbench page, using fallback data")
        tenant = get_tenant_by_slug(tenant.get("slug"), site_config) if isinstance(tenant, dict) else get_tenant_by_slug(site_config=site_config)
        workbench = gen_kol_workbench(tenant, fallback_mode=True)
    return render_template(
        "kol_workbench.html",
        workbench=workbench,
        brand=get_platform_brand(site_config),
        active_tenant=tenant,
        tenant_portal_enabled=is_feature_enabled("tenant_portal", site_config),
        current_user=current_user,
    )


@app.route("/tenant/<tenant_slug>")
def tenant_portal(tenant_slug):
    site_config = get_site_config()
    if not is_feature_enabled("tenant_portal", site_config):
        abort(404)
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
    if not is_feature_enabled("tenant_portal", get_site_config()):
        abort(404)
    tenant = get_active_tenant_from_request()
    return redirect(url_for("tenant_portal", tenant_slug=tenant["slug"]))
