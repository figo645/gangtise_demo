from src.runtime import *
from src.services import *

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
    use_llm_enhancement = _is_truthy_flag(request.form.get("use_llm_enhancement"))
    try:
        if audio_file is None:
            raise ValueError("audio_file_required")
        raw_bytes = audio_file.read() or b""
        if not raw_bytes:
            raise ValueError("empty_audio_file")
        if len(raw_bytes) > VOICE_UPLOAD_MAX_BYTES:
            raise ValueError("audio_file_too_large")
        payload = {
            "tenant_slug": tenant_slug,
            "period": review_period,
            "entry_point": entry_point,
            "speaker_name": speaker_name,
            "use_llm_enhancement": use_llm_enhancement,
            "filename": getattr(audio_file, "filename", "") or f"review-{int(time.time())}.webm",
            "content_type": getattr(audio_file, "mimetype", "") or "",
            "audio_base64": base64.b64encode(raw_bytes).decode("ascii"),
        }
        job = create_user_async_job(
            "review_voice_transcribe",
            payload=payload,
            tenant_slug=tenant_slug,
            entry_point=entry_point,
            owner_label=speaker_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    except Exception:
        app.logger.exception("Failed to queue review voice upload")
        return jsonify({"success": False, "error": "review_voice_transcribe_failed"}), 500
    return jsonify(
        {
            "success": True,
            "async": True,
            "job_code": job["job_code"],
            "job_status": job["status"],
            "message": "语音已提交处理，正在后台转写" + (" 并准备做大模型增强" if use_llm_enhancement else ""),
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
        tenant_slug = str(body.get("tenant_slug") or "").strip().lower()
        entry_point = str(body.get("entry_point") or "").strip().lower() or "unknown"
        speaker_name = str(body.get("speaker_name") or "").strip()
        payload = {
            "text": body.get("text"),
            "tenant_slug": tenant_slug,
            "period": str(body.get("period") or "").strip().lower(),
            "entry_point": entry_point,
            "speaker_name": speaker_name,
            "transcription_engine": str(body.get("transcription_engine") or "manual").strip().lower() or "manual",
            "transcript_model": str(body.get("transcript_model") or "manual_input").strip() or "manual_input",
            "source_mode": str(body.get("source_mode") or "manual").strip().lower() or "manual",
            "paragraph_mode": str(body.get("paragraph_mode") or "manual").strip().lower() or "manual",
            "selected_watchlist": body.get("selected_watchlist") if isinstance(body.get("selected_watchlist"), list) else [],
            "prompt_tags": body.get("prompt_tags") if isinstance(body.get("prompt_tags"), list) else [],
            "knowledge_attachments": body.get("knowledge_attachments") if isinstance(body.get("knowledge_attachments"), list) else [],
            "selected_cards": body.get("selected_cards") if isinstance(body.get("selected_cards"), list) else [],
            "data_sources": body.get("data_sources") if isinstance(body.get("data_sources"), list) else [],
            "news_sources": body.get("news_sources") if isinstance(body.get("news_sources"), list) else [],
            "llm_models": body.get("llm_models") if isinstance(body.get("llm_models"), list) else [],
            "polished_input_text": body.get("polished_input_text"),
        }
        if not str(payload.get("text") or "").strip():
            raise ValueError("publish_text_required")
        job = create_user_async_job(
            "review_publish_embed",
            payload=payload,
            tenant_slug=tenant_slug,
            entry_point=entry_point,
            owner_label=speaker_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503
    except Exception:
        app.logger.exception("Failed to queue review publish text")
        return jsonify({"success": False, "error": "review_publish_embed_failed"}), 500
    return jsonify(
        {
            "success": True,
            "async": True,
            "job_code": job["job_code"],
            "job_status": job["status"],
            "message": "复盘已提交发布，正在后台入向量库",
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


@app.route("/api/admin/tasks")
def api_admin_tasks():
    return jsonify({"ok": True, **build_admin_task_center_payload()})


@app.route("/api/admin/tasks", methods=["POST"])
def api_save_admin_task():
    body = request.get_json(silent=True) or {}
    try:
        task = save_admin_task_config(body)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "task": task, **build_admin_task_center_payload()})


@app.route("/api/admin/tasks/<task_code>/run", methods=["POST"])
def api_run_admin_task(task_code):
    body = request.get_json(silent=True) or {}
    force = bool(body.get("force"))
    try:
        result = run_admin_task(task_code, trigger_mode="manual", force=force)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "result": result, **build_admin_task_center_payload()})


@app.route("/api/admin/task-runs")
def api_admin_task_runs():
    task_code = str(request.args.get("task_code") or "").strip() or None
    limit = min(int(request.args.get("limit", 50)), TASK_CENTER_LOG_LIMIT)
    return jsonify({"ok": True, "runs": list_admin_task_runs(task_code=task_code, limit=limit)})


@app.route("/api/admin/user-jobs")
def api_admin_user_jobs():
    tenant_slug = str(request.args.get("tenant_slug") or "").strip().lower() or None
    status = str(request.args.get("status") or "").strip().lower() or None
    job_type = str(request.args.get("job_type") or "").strip().lower() or None
    limit = min(int(request.args.get("limit", 60)), USER_ASYNC_JOB_LOG_LIMIT)
    return jsonify({"ok": True, **build_user_async_jobs_payload(tenant_slug=tenant_slug, status=status, job_type=job_type, limit=limit)})


@app.route("/api/admin/token-usage")
def api_admin_token_usage():
    return jsonify({"ok": True, **build_admin_token_usage_payload()})


@app.route("/api/jobs/<job_code>")
def api_get_user_async_job(job_code):
    job = get_user_async_job(job_code)
    if not job:
        return jsonify({"ok": False, "error": "job_not_found"}), 404
    return jsonify({"ok": True, "job": job})


@app.route("/api/jobs/<job_code>/retry", methods=["POST"])
def api_retry_user_async_job(job_code):
    try:
        job = retry_user_async_job(job_code)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "job": job})


@app.route("/api/admin/indicator-hub")
def api_admin_indicator_hub():
    return jsonify({"ok": True, "hub": get_indicator_hub_from_store_cached()})


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
        payload = normalize_user_payload(body, context=build_user_import_context(scope="admin"))
        user = create_user(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "user": user, "users": list_users()})


@app.route("/api/admin/users/import", methods=["POST"])
def api_import_admin_users():
    body = request.get_json(silent=True) or {}
    users = body.get("users", [])
    created, skipped = bulk_create_users(users if isinstance(users, list) else [], context=build_user_import_context(scope="admin"))
    return jsonify({"ok": True, "created": created, "skipped": skipped, "users": list_users()})


@app.route("/api/admin/users/import-csv", methods=["POST"])
def api_import_admin_users_csv():
    try:
        rows = parse_user_csv_import(request.files.get("file"), context=build_user_import_context(scope="admin"))
        created, skipped = bulk_create_users(rows, context=build_user_import_context(scope="admin"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "created": created, "skipped": skipped, "users": list_users()})


@app.route("/api/admin/users/template.csv")
def api_admin_users_template():
    content = build_user_import_template_csv(scope="admin")
    return app.response_class(
        content,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="admin_user_import_template.csv"'},
    )


@app.route("/api/kol/users")
def api_kol_users():
    tenant = get_active_tenant_from_request()
    summary = build_user_import_summary(scope="kol", tenant_slug=tenant["slug"])
    return jsonify({"users": summary["users"], "summary": summary})


@app.route("/api/kol/users", methods=["POST"])
def api_create_kol_user():
    tenant = get_active_tenant_from_request()
    body = request.get_json(silent=True) or {}
    try:
        payload = normalize_user_payload(body, context=build_user_import_context(scope="kol", tenant_slug=tenant["slug"]))
        user = create_user(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    summary = build_user_import_summary(scope="kol", tenant_slug=tenant["slug"])
    return jsonify({"ok": True, "user": user, "users": summary["users"], "summary": summary})


@app.route("/api/kol/users/import", methods=["POST"])
def api_import_kol_users():
    tenant = get_active_tenant_from_request()
    body = request.get_json(silent=True) or {}
    users = body.get("users", [])
    created, skipped = bulk_create_users(
        users if isinstance(users, list) else [],
        context=build_user_import_context(scope="kol", tenant_slug=tenant["slug"]),
    )
    summary = build_user_import_summary(scope="kol", tenant_slug=tenant["slug"])
    return jsonify({"ok": True, "created": created, "skipped": skipped, "users": summary["users"], "summary": summary})


@app.route("/api/kol/users/import-csv", methods=["POST"])
def api_import_kol_users_csv():
    tenant = get_active_tenant_from_request()
    try:
        rows = parse_user_csv_import(
            request.files.get("file"),
            context=build_user_import_context(scope="kol", tenant_slug=tenant["slug"]),
        )
        created, skipped = bulk_create_users(
            rows,
            context=build_user_import_context(scope="kol", tenant_slug=tenant["slug"]),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    summary = build_user_import_summary(scope="kol", tenant_slug=tenant["slug"])
    return jsonify({"ok": True, "created": created, "skipped": skipped, "users": summary["users"], "summary": summary})


@app.route("/api/kol/users/template.csv")
def api_kol_users_template():
    tenant = get_active_tenant_from_request()
    content = build_user_import_template_csv(scope="kol", tenant_slug=tenant["slug"])
    return app.response_class(
        content,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{tenant["slug"]}_fan_import_template.csv"'},
    )


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
            "knowledge_ingestion": normalize_knowledge_ingestion_config(
                payload.get("knowledge_ingestion")
                if isinstance(payload.get("knowledge_ingestion"), dict)
                else current.get("knowledge_ingestion")
            ),
            "evidence_chain": normalize_evidence_chain_config(
                payload.get("evidence_chain")
                if isinstance(payload.get("evidence_chain"), dict)
                else current.get("evidence_chain")
            ),
            "review_generation": normalize_review_generation_config(
                payload.get("review_generation")
                if isinstance(payload.get("review_generation"), dict)
                else current.get("review_generation")
            ),
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

