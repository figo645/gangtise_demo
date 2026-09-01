from src.runtime import *
from src.services import *


def _knowledge_feature_disabled_response():
    if is_feature_enabled("knowledge"):
        return None
    return jsonify({"ok": False, "error": "knowledge_feature_disabled"}), 404


def _validate_review_source_mode(source_mode):
    normalized = str(source_mode or "manual").strip().lower() or "manual"
    if normalized == "voice" and not is_feature_enabled("review_voice_input"):
        raise ValueError("review_voice_input_disabled")
    if normalized == "url" and not is_feature_enabled("review_url_input"):
        raise ValueError("review_url_input_disabled")
    if normalized not in {"manual", "file", "voice", "url"}:
        raise ValueError("review_source_mode_invalid")
    return normalized


def _tenant_smart_indicator_write_guard(tenant_slug):
    """Require DAv capability and enforce tenant scope for mutations."""
    current_user = get_current_authenticated_user() or {}
    role = str(current_user.get("role") or "").strip().lower()
    if not has_role_capability(role, "dav"):
        return jsonify({"success": False, "error": "dav_required"}), 403
    current_tenant = str(current_user.get("tenant_slug") or "").strip().lower()
    requested_tenant = str(tenant_slug or "").strip().lower()
    if not has_role_capability(role, "admin") and current_tenant != requested_tenant:
        return jsonify({"success": False, "error": "tenant_scope_forbidden"}), 403
    return None

@app.route("/api/kol/workbench")
def api_kol_workbench():
    tenant = get_tenant_by_slug(request.args.get("tenant"))
    try:
        payload = gen_kol_workbench(tenant)
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while building workbench API, using fallback data")
        payload = gen_kol_workbench(tenant, fallback_mode=True)
    return jsonify(payload)


@app.route("/api/review/jobs")
def api_review_jobs():
    """Return the current DAv's active review jobs so the workspace is resumable."""
    current_user = get_current_authenticated_user() or {}
    current_role = str(current_user.get("role") or "").strip().lower()
    if not has_role_capability(current_role, "dav"):
        return jsonify({"ok": False, "error": "dav_required"}), 403
    current_tenant_slug = str(current_user.get("tenant_slug") or "").strip().lower()
    requested_tenant_slug = str(request.args.get("tenant_slug") or "").strip().lower()
    tenant_slug = requested_tenant_slug or current_tenant_slug
    if not has_role_capability(current_role, "admin") and current_tenant_slug and tenant_slug != current_tenant_slug:
        return jsonify({"ok": False, "error": "tenant_scope_forbidden"}), 403
    if not tenant_slug:
        return jsonify({"ok": False, "error": "tenant_required"}), 400
    jobs = list_user_async_jobs(tenant_slug=tenant_slug, limit=80)
    review_types = {
        "review_generate_draft",
        "review_prepare_preview",
        "review_sector_summary_constraint",
        "review_voice_transcribe",
        "review_polish_input",
        "review_compose_draft",
    }
    active_jobs = []
    for job in jobs:
        if job.get("job_type") not in review_types or job.get("status") not in {"pending", "running"}:
            continue
        safe_job = dict(job)
        safe_payload = dict(safe_job.get("payload") or {})
        safe_payload.pop("audio_base64", None)
        safe_job["payload"] = safe_payload
        active_jobs.append(safe_job)
    return jsonify({"ok": True, "tenant_slug": tenant_slug, "jobs": active_jobs})


@app.route("/api/review/jobs/<job_code>/cancel", methods=["POST"])
def api_cancel_review_job(job_code):
    """Stop a DAV-owned review generation job without deleting its source material."""
    current_user = get_current_authenticated_user() or {}
    current_role = str(current_user.get("role") or "").strip().lower()
    if not has_role_capability(current_role, "dav"):
        return jsonify({"ok": False, "error": "dav_required"}), 403
    job = get_user_async_job(job_code)
    if not job:
        return jsonify({"ok": False, "error": "job_not_found"}), 404
    cancellable_types = {
        "review_generate_draft",
        "review_prepare_preview",
        "review_sector_summary_constraint",
        "review_voice_transcribe",
        "review_polish_input",
        "review_compose_draft",
    }
    if job.get("job_type") not in cancellable_types:
        return jsonify({"ok": False, "error": "job_not_cancellable"}), 400
    current_tenant_slug = str(current_user.get("tenant_slug") or "").strip().lower()
    if not has_role_capability(current_role, "admin") and (
        not current_tenant_slug or str(job.get("tenant_slug") or "").strip().lower() != current_tenant_slug
    ):
        return jsonify({"ok": False, "error": "tenant_scope_forbidden"}), 403
    owner_label = str(job.get("owner_label") or "").strip()
    current_owner_labels = {
        str(current_user.get("advisor_name") or "").strip(),
        str(current_user.get("username") or "").strip(),
        str(current_user.get("name") or "").strip(),
    }
    current_owner_labels.discard("")
    if not has_role_capability(current_role, "admin") and owner_label and owner_label not in current_owner_labels:
        return jsonify({"ok": False, "error": "job_owner_forbidden"}), 403
    try:
        cancelled_job = cancel_user_async_job(job_code)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    safe_job = dict(cancelled_job)
    safe_payload = dict(safe_job.get("payload") or {})
    safe_payload.pop("audio_base64", None)
    safe_job["payload"] = safe_payload
    return jsonify({"ok": True, "job": safe_job, "message": "已停止生成，原始输入已保留"})


@app.route("/api/kol/portal-cms", methods=["POST"])
def api_save_kol_portal_cms():
    if not is_feature_enabled("tenant_portal", get_site_config()):
        return jsonify({"ok": False, "error": "tenant_portal_disabled"}), 404
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
    blocked = _knowledge_feature_disabled_response()
    if blocked:
        return blocked
    body = request.get_json(silent=True) or {}
    tenant_slug = str(body.get("tenant_slug") or request.args.get("tenant") or "").strip().lower()
    try:
        payload = {
            "tenant_slug": tenant_slug,
            "title": body.get("title"),
            "summary": body.get("summary"),
            "body": body.get("body"),
            "raw_html": body.get("raw_html"),
            "notes": body.get("notes"),
            "notes_html": body.get("notes_html"),
            "id": body.get("id"),
            "skip_ai_processing": bool(body.get("skip_ai_processing", True)),
            "processing_mode": body.get("processing_mode"),
        }
        if not tenant_slug:
            raise ValueError("tenant_not_found")
        if not str(payload.get("body") or payload.get("summary") or "").strip():
            raise ValueError("knowledge_body_required")
        job = create_user_async_job(
            "knowledge_manual_sync",
            payload=payload,
            tenant_slug=tenant_slug,
            entry_point="knowledge_manual",
            owner_label="knowledge_manual",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    except Exception:
        app.logger.exception("Failed to queue manual knowledge entry")
        return jsonify({"ok": False, "error": "knowledge_manual_save_failed"}), 500
    return jsonify({
        "ok": True,
        "async": True,
        "job_code": job["job_code"],
        "job_status": job["status"],
        "message": "知识已提交处理，正在后台同步",
    })


@app.route("/api/kol/knowledge/ingest", methods=["POST"])
def api_ingest_kol_knowledge():
    blocked = _knowledge_feature_disabled_response()
    if blocked:
        return blocked
    body = request.get_json(silent=True) or {}
    tenant_slug = str(body.get("tenant_slug") or request.args.get("tenant") or "").strip().lower()
    knowledge_type = str(body.get("knowledge_type") or "manual").strip().lower()
    if knowledge_type not in {"voice", "file", "url", "manual"}:
        return jsonify({"ok": False, "error": "knowledge_type_invalid"}), 400
    payload = {
        "tenant_slug": tenant_slug,
        "knowledge_type": knowledge_type,
        "title": body.get("title"),
        "summary": body.get("summary"),
        "body": body.get("body"),
        "raw_html": body.get("raw_html"),
        "notes": body.get("notes"),
        "notes_html": body.get("notes_html"),
        "id": body.get("id"),
        "skip_ai_processing": bool(body.get("skip_ai_processing", True)),
        "processing_mode": body.get("processing_mode"),
        "source_label": body.get("source_label"),
        "source_detail": body.get("source_detail"),
        "tags": body.get("tags"),
        "files": body.get("files"),
        "url": body.get("url"),
        "voice_minutes": body.get("voice_minutes"),
        "parse_meta": body.get("parse_meta"),
    }
    if not tenant_slug:
        return jsonify({"ok": False, "error": "tenant_not_found"}), 400
    if not str(payload.get("body") or payload.get("summary") or "").strip():
        return jsonify({"ok": False, "error": "knowledge_body_required"}), 400
    try:
        job = create_user_async_job(
            "knowledge_manual_sync",
            payload=payload,
            tenant_slug=tenant_slug,
            entry_point=f"knowledge_{knowledge_type}",
            owner_label=f"knowledge_{knowledge_type}",
        )
    except Exception:
        app.logger.exception("Failed to queue knowledge ingest")
        return jsonify({"ok": False, "error": "knowledge_ingest_failed"}), 500
    return jsonify({
        "ok": True,
        "async": True,
        "job_code": job["job_code"],
        "job_status": job["status"],
        "message": "知识已提交处理，正在后台同步",
    })


@app.route("/api/admin/knowledge-items")
def api_admin_knowledge_items():
    blocked = _knowledge_feature_disabled_response()
    if blocked:
        return blocked
    tenant_slug = str(request.args.get("tenant_slug") or "").strip().lower()
    limit = min(max(int(request.args.get("limit", 120)), 1), 300)
    return jsonify({
        "ok": True,
        "items": list_admin_knowledge_items(tenant_slug=tenant_slug, limit=limit),
    })


@app.route("/api/kol/knowledge-assets")
def api_kol_knowledge_assets():
    blocked = _knowledge_feature_disabled_response()
    if blocked:
        return blocked
    tenant = get_tenant_by_slug(request.args.get("tenant"))
    try:
        knowledge_hub = fetch_live_knowledge_hub(tenant, limit=160)
        payload = build_knowledge_asset_payload(
            knowledge_hub.get("items") or [],
            mode="tenant",
            tenant=tenant,
            platform_name=get_platform_brand().get("platform_name") or get_platform_brand().get("name") or "平台",
        )
    except Exception as exc:
        if is_db_unavailable_error(exc):
            app.logger.warning("Database unavailable while building tenant knowledge assets, using config fallback")
            fallback_hub = resolve_tenant_knowledge_hub(tenant, tenant.get("knowledge_hub_config"))
            payload = build_knowledge_asset_payload(
                fallback_hub.get("items") or [],
                mode="tenant",
                tenant=tenant,
                platform_name=get_platform_brand().get("platform_name") or get_platform_brand().get("name") or "平台",
            )
        else:
            app.logger.exception("Failed to build tenant knowledge assets")
            return jsonify({"ok": False, "error": "knowledge_assets_build_failed"}), 500
    return jsonify({
        "ok": True,
        "assets": payload,
        "workflow_meta": build_declared_agent_workflow_meta(build_default_knowledge_asset_workflow_definition()),
    })


@app.route("/api/admin/knowledge-assets")
def api_admin_knowledge_assets():
    blocked = _knowledge_feature_disabled_response()
    if blocked:
        return blocked
    tenant_slug = str(request.args.get("tenant_slug") or "").strip().lower()
    mode = "tenant" if tenant_slug else "platform"
    try:
        if tenant_slug:
            tenant = get_tenant_by_slug(tenant_slug)
            items = list_admin_knowledge_items(tenant_slug=tenant_slug, limit=240)
            payload = build_knowledge_asset_payload(
                items,
                mode="tenant",
                tenant=tenant,
                platform_name=get_platform_brand().get("platform_name") or get_platform_brand().get("name") or "平台",
            )
        else:
            items = list_admin_knowledge_items(limit=320)
            payload = build_knowledge_asset_payload(
                items,
                mode="platform",
                platform_name=get_platform_brand().get("platform_name") or get_platform_brand().get("name") or "平台",
            )
    except Exception as exc:
        if is_db_unavailable_error(exc):
            app.logger.warning("Database unavailable while building admin knowledge assets, using config fallback")
            site_config = normalize_site_config(DEFAULT_SITE_CONFIG)
            if tenant_slug:
                tenant = get_tenant_by_slug(tenant_slug, site_config)
                tenant_items = resolve_tenant_knowledge_hub(tenant, tenant.get("knowledge_hub_config")).get("items") or []
                payload = build_knowledge_asset_payload(
                    [{**item, "tenant_slug": tenant.get("slug") or "", "tenant_name": tenant.get("name") or ""} for item in tenant_items if isinstance(item, dict)],
                    mode="tenant",
                    tenant=tenant,
                    platform_name=get_platform_brand(site_config).get("platform_name") or get_platform_brand(site_config).get("name") or "平台",
                )
            else:
                aggregated = []
                for tenant in get_tenant_configs(site_config):
                    tenant_items = resolve_tenant_knowledge_hub(tenant, tenant.get("knowledge_hub_config")).get("items") or []
                    aggregated.extend(
                        [{**item, "tenant_slug": tenant.get("slug") or "", "tenant_name": tenant.get("name") or ""} for item in tenant_items if isinstance(item, dict)]
                    )
                payload = build_knowledge_asset_payload(
                    aggregated,
                    mode="platform",
                    platform_name=get_platform_brand(site_config).get("platform_name") or get_platform_brand(site_config).get("name") or "平台",
                )
        else:
            app.logger.exception("Failed to build admin knowledge assets")
            return jsonify({"ok": False, "error": "knowledge_assets_build_failed"}), 500
    return jsonify({
        "ok": True,
        "mode": mode,
        "assets": payload,
        "workflow_meta": build_declared_agent_workflow_meta(build_default_knowledge_asset_workflow_definition()),
    })


@app.route("/api/kol/knowledge-graph")
def api_kol_knowledge_graph():
    blocked = _knowledge_feature_disabled_response()
    if blocked:
        return blocked
    tenant = get_tenant_by_slug(request.args.get("tenant"))
    try:
        knowledge_hub = fetch_live_knowledge_hub(tenant, limit=120)
        payload = build_knowledge_graph_payload(
            knowledge_hub.get("items") or [],
            mode="tenant",
            tenant=tenant,
            platform_name=get_platform_brand().get("platform_name") or get_platform_brand().get("name") or "平台",
        )
    except Exception as exc:
        if is_db_unavailable_error(exc):
            app.logger.warning("Database unavailable while building tenant knowledge graph, using config fallback")
            fallback_hub = resolve_tenant_knowledge_hub(tenant, tenant.get("knowledge_hub_config"))
            payload = build_knowledge_graph_payload(
                fallback_hub.get("items") or [],
                mode="tenant",
                tenant=tenant,
                platform_name=get_platform_brand().get("platform_name") or get_platform_brand().get("name") or "平台",
            )
        else:
            app.logger.exception("Failed to build tenant knowledge graph")
            return jsonify({"ok": False, "error": "knowledge_graph_build_failed"}), 500
    return jsonify({
        "ok": True,
        "graph": payload,
        "workflow_meta": build_declared_agent_workflow_meta(build_default_knowledge_graph_workflow_definition()),
    })


def _resolve_kol_hermes_tenant():
    tenant_slug = str(request.args.get("tenant") or "").strip().lower()
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or str(tenant.get("slug") or "").strip().lower() != tenant_slug:
        raise ValueError("tenant_not_found")
    return tenant_slug


@app.route("/api/kol/hermes/usage-stats")
def api_kol_hermes_usage_stats():
    try:
        tenant_slug = _resolve_kol_hermes_tenant()
        return jsonify({"ok": True, "stats": build_admin_hermes_usage_stats(tenant_slug)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        if is_db_unavailable_error(exc):
            return jsonify({"ok": False, "error": "hermes_usage_db_unavailable"}), 503
        app.logger.exception("Failed to load tenant Hermes usage stats")
        return jsonify({"ok": False, "error": "hermes_usage_stats_failed"}), 500


@app.route("/api/kol/hermes/memory-summary")
def api_kol_hermes_memory_summary():
    try:
        tenant_slug = _resolve_kol_hermes_tenant()
        return jsonify({"ok": True, "summary": build_admin_hermes_memory_summary(tenant_slug)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        if is_db_unavailable_error(exc):
            return jsonify({"ok": False, "error": "hermes_memory_db_unavailable"}), 503
        app.logger.exception("Failed to load tenant Hermes memory summary")
        return jsonify({"ok": False, "error": "hermes_memory_summary_failed"}), 500


@app.route("/api/kol/hermes/capability-growth")
def api_kol_hermes_capability_growth():
    try:
        tenant_slug = _resolve_kol_hermes_tenant()
        return jsonify({"ok": True, "growth": build_kol_hermes_capability_growth(tenant_slug)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        if is_db_unavailable_error(exc):
            return jsonify({"ok": False, "error": "hermes_capability_db_unavailable"}), 503
        app.logger.exception("Failed to build tenant Hermes capability growth")
        return jsonify({"ok": False, "error": "hermes_capability_growth_failed"}), 500


@app.route("/api/admin/knowledge-graph")
def api_admin_knowledge_graph():
    blocked = _knowledge_feature_disabled_response()
    if blocked:
        return blocked
    tenant_slug = str(request.args.get("tenant_slug") or "").strip().lower()
    mode = "tenant" if tenant_slug else "platform"
    try:
        if tenant_slug:
            tenant = get_tenant_by_slug(tenant_slug)
            items = list_admin_knowledge_items(tenant_slug=tenant_slug, limit=240)
            payload = build_knowledge_graph_payload(
                items,
                mode="tenant",
                tenant=tenant,
                platform_name=get_platform_brand().get("platform_name") or get_platform_brand().get("name") or "平台",
            )
        else:
            items = list_admin_knowledge_items(limit=300)
            payload = build_knowledge_graph_payload(
                items,
                mode="platform",
                platform_name=get_platform_brand().get("platform_name") or get_platform_brand().get("name") or "平台",
            )
    except Exception as exc:
        if is_db_unavailable_error(exc):
            app.logger.warning("Database unavailable while building admin knowledge graph, using config fallback")
            site_config = normalize_site_config(DEFAULT_SITE_CONFIG)
            if tenant_slug:
                tenant = get_tenant_by_slug(tenant_slug, site_config)
                items = resolve_tenant_knowledge_hub(tenant, tenant.get("knowledge_hub_config")).get("items") or []
                items = [{**item, "tenant_slug": tenant.get("slug") or "", "tenant_name": tenant.get("name") or ""} for item in items if isinstance(item, dict)]
                payload = build_knowledge_graph_payload(
                    items,
                    mode="tenant",
                    tenant=tenant,
                    platform_name=get_platform_brand(site_config).get("platform_name") or get_platform_brand(site_config).get("name") or "平台",
                )
            else:
                aggregated = []
                for tenant in get_tenant_configs(site_config):
                    tenant_items = resolve_tenant_knowledge_hub(tenant, tenant.get("knowledge_hub_config")).get("items") or []
                    aggregated.extend(
                        [{**item, "tenant_slug": tenant.get("slug") or "", "tenant_name": tenant.get("name") or ""} for item in tenant_items if isinstance(item, dict)]
                    )
                payload = build_knowledge_graph_payload(
                    aggregated,
                    mode="platform",
                    platform_name=get_platform_brand(site_config).get("platform_name") or get_platform_brand(site_config).get("name") or "平台",
                )
        else:
            app.logger.exception("Failed to build admin knowledge graph")
            return jsonify({"ok": False, "error": "knowledge_graph_build_failed"}), 500
    return jsonify({
        "ok": True,
        "mode": mode,
        "graph": payload,
        "workflow_meta": build_declared_agent_workflow_meta(build_default_knowledge_graph_workflow_definition()),
    })


@app.route("/api/kol/knowledge/file-preview", methods=["POST"])
def api_preview_kol_knowledge_file():
    file_storage = request.files.get("file")
    try:
        preview = extract_text_from_uploaded_file(file_storage)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        app.logger.exception("Failed to preview knowledge file")
        return jsonify({"ok": False, "error": "knowledge_file_preview_failed"}), 500
    return jsonify({"ok": True, "preview": preview})


@app.route("/api/kol/knowledge/url-preview", methods=["POST"])
def api_preview_kol_knowledge_url():
    blocked = _knowledge_feature_disabled_response()
    if blocked:
        return blocked
    body = request.get_json(silent=True) or {}
    try:
        preview = fetch_url_preview(body.get("url"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        app.logger.exception("Failed to preview knowledge url")
        return jsonify({"ok": False, "error": "knowledge_url_preview_failed"}), 500
    return jsonify({"ok": True, "preview": preview})


@app.route("/api/kol/knowledge/query", methods=["POST"])
def api_query_kol_knowledge():
    blocked = _knowledge_feature_disabled_response()
    if blocked:
        return blocked
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


@app.route("/api/evidence-chain/query", methods=["POST"])
def api_query_evidence_chain():
    body = request.get_json(silent=True) or {}
    tenant_slug = str(body.get("tenant_slug") or request.args.get("tenant") or "").strip().lower()
    submit_to_model = bool(body.get("submit_to_model", False))
    try:
        result = build_evidence_chain_response(
            tenant_slug=tenant_slug,
            query_text=body.get("query"),
            limit=body.get("limit") or 5,
            submit_to_model=submit_to_model,
            source_types=body.get("source_types"),
            entry_point=str(body.get("entry_point") or "evidence_chain").strip() or "evidence_chain",
            feature_namespace="evidence_chain",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    except Exception:
        app.logger.exception("Failed to query evidence chain")
        return jsonify({"ok": False, "error": "evidence_chain_query_failed"}), 500
    return jsonify({"ok": True, **result})


@app.route("/api/review/generate-draft", methods=["POST"])
def api_generate_review_draft():
    body = request.get_json(silent=True) or {}
    try:
        tenant_slug = str(body.get("tenant_slug") or "").strip().lower()
        entry_point = str(body.get("entry_point") or "").strip() or "review_draft"
        speaker_name = str(body.get("speaker_name") or "").strip()
        payload = {
            "tenant_slug": tenant_slug,
            "period": str(body.get("period") or "").strip().lower(),
            "source_mode": str(body.get("source_mode") or "").strip().lower(),
            "source_text": body.get("source_text"),
            "prompt_text": body.get("prompt_text"),
            "prompt_tags": body.get("prompt_tags") if isinstance(body.get("prompt_tags"), list) else [],
            "selected_watchlist": body.get("selected_watchlist") if isinstance(body.get("selected_watchlist"), list) else [],
            "speaker_name": speaker_name,
            "entry_point": entry_point,
        }
        payload["source_mode"] = _validate_review_source_mode(payload.get("source_mode"))
        if not str(payload.get("source_text") or "").strip():
            raise ValueError("review_source_text_required")
        job = create_user_async_job(
            "review_generate_draft",
            payload=payload,
            tenant_slug=tenant_slug,
            entry_point=entry_point,
            owner_label=speaker_name,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    except Exception:
        app.logger.exception("Failed to generate review draft with LLM")
        return jsonify({"ok": False, "error": "review_draft_generation_failed"}), 500
    return jsonify({
        "ok": True,
        "async": True,
        "job_code": job["job_code"],
        "job_status": job["status"],
        "message": "复盘草稿已提交生成，正在后台调用大模型",
    })


@app.route("/api/review/polish-input", methods=["POST"])
def api_polish_review_input():
    body = request.get_json(silent=True) or {}
    try:
        tenant_slug = str(body.get("tenant_slug") or "").strip().lower()
        entry_point = str(body.get("entry_point") or "").strip() or "review_polish"
        speaker_name = str(body.get("speaker_name") or "").strip()
        payload = {
            "tenant_slug": tenant_slug,
            "period": str(body.get("period") or "").strip().lower(),
            "source_mode": str(body.get("source_mode") or "").strip().lower(),
            "source_text": body.get("source_text"),
            "speaker_name": speaker_name,
            "entry_point": entry_point,
        }
        payload["source_mode"] = _validate_review_source_mode(payload.get("source_mode"))
        if not str(payload.get("source_text") or "").strip():
            raise ValueError("review_source_text_required")
        job = create_user_async_job(
            "review_polish_input",
            payload=payload,
            tenant_slug=tenant_slug,
            entry_point=entry_point,
            owner_label=speaker_name,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    except Exception:
        app.logger.exception("Failed to polish review input with LLM")
        return jsonify({"ok": False, "error": "review_input_polish_failed"}), 500
    return jsonify({
        "ok": True,
        "async": True,
        "job_code": job["job_code"],
        "job_status": job["status"],
        "message": "复盘输入已提交润色，正在后台调用大模型",
    })


@app.route("/api/review/compose-draft", methods=["POST"])
def api_compose_review_draft():
    body = request.get_json(silent=True) or {}
    try:
        tenant_slug = str(body.get("tenant_slug") or "").strip().lower()
        entry_point = str(body.get("entry_point") or "").strip() or "review_compose"
        speaker_name = str(body.get("speaker_name") or "").strip()
        payload = {
            "tenant_slug": tenant_slug,
            "period": str(body.get("period") or "").strip().lower(),
            "source_mode": str(body.get("source_mode") or "").strip().lower(),
            "source_text": body.get("source_text"),
            "prompt_text": body.get("prompt_text"),
            "prompt_tags": body.get("prompt_tags") if isinstance(body.get("prompt_tags"), list) else [],
            "selected_watchlist": body.get("selected_watchlist") if isinstance(body.get("selected_watchlist"), list) else [],
            "dashboard_cards": body.get("dashboard_cards") if isinstance(body.get("dashboard_cards"), list) else [],
            "knowledge_items": body.get("knowledge_items") if isinstance(body.get("knowledge_items"), list) else [],
            "speaker_name": speaker_name,
            "entry_point": entry_point,
        }
        payload["source_mode"] = _validate_review_source_mode(payload.get("source_mode"))
        if not is_feature_enabled("knowledge"):
            payload["knowledge_items"] = []
        if not str(payload.get("source_text") or "").strip():
            raise ValueError("review_source_text_required")
        job = create_user_async_job(
            "review_compose_draft",
            payload=payload,
            tenant_slug=tenant_slug,
            entry_point=entry_point,
            owner_label=speaker_name,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    except Exception:
        app.logger.exception("Failed to compose review draft with LLM")
        return jsonify({"ok": False, "error": "review_compose_draft_failed"}), 500
    return jsonify({
        "ok": True,
        "async": True,
        "job_code": job["job_code"],
        "job_status": job["status"],
        "message": "复盘完整草稿已提交生成，正在后台调用大模型",
    })


@app.route("/api/tenant/<tenant_slug>/dashboard")
def api_tenant_dashboard(tenant_slug):
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or tenant["slug"] != tenant_slug:
        return jsonify({"success": False, "error": "tenant_not_found"}), 404
    try:
        payload = build_tenant_dashboard_payload(tenant)
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while building tenant dashboard API, using fallback data")
        payload = build_tenant_dashboard_payload_fallback(tenant)
    return jsonify({"success": True, "dashboard": payload, "fund_dashboard_state": payload.get("fund_dashboard_state")})


@app.route("/api/tenant/<tenant_slug>/reviews/<review_id>/view", methods=["POST"])
def api_record_tenant_review_view(tenant_slug, review_id):
    try:
        article = increment_tenant_review_snapshot_view_count(tenant_slug, review_id)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        if is_db_unavailable_error(exc):
            return jsonify({"ok": False, "error": "review_view_storage_unavailable"}), 503
        app.logger.exception("Failed to record tenant review view")
        return jsonify({"ok": False, "error": "review_view_record_failed"}), 500
    return jsonify({
        "ok": True,
        "review_id": str(review_id or "").strip(),
        "view_count": int((article or {}).get("view_count") or 0),
    })


@app.route("/api/tenant/<tenant_slug>/dashboard", methods=["POST"])
def api_save_tenant_dashboard(tenant_slug):
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or tenant["slug"] != tenant_slug:
        return jsonify({"success": False, "error": "tenant_not_found"}), 404
    denied = _tenant_smart_indicator_write_guard(tenant_slug)
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or "").strip().lower()
    dashboard = body.get("dashboard") if isinstance(body.get("dashboard"), dict) else None
    if action == "remove_indicator":
        indicator_code = str(body.get("indicator_code") or (dashboard or {}).get("indicator_code") or (dashboard or {}).get("indicatorCode") or "").strip()
        saved = remove_smart_indicator_from_dashboard(tenant_slug, indicator_code) if indicator_code else None
    else:
        saved = update_tenant_fund_dashboard_config(tenant_slug, action, dashboard)
    if not saved:
        return jsonify({"success": False, "error": "invalid_action"}), 400
    latest_tenant = get_tenant_by_slug(tenant_slug, saved)
    payload = build_tenant_dashboard_payload(latest_tenant)
    return jsonify({"success": True, "dashboard": payload, "fund_dashboard_state": payload.get("fund_dashboard_state")})


@app.route("/api/tenant/<tenant_slug>/fan-stock-observation", methods=["GET", "POST"])
def api_tenant_fan_stock_observation(tenant_slug):
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or tenant["slug"] != tenant_slug:
        return jsonify({"ok": False, "error": "tenant_not_found"}), 404
    recorded_payload = None
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        actor = resolve_hermes_actor_context(body, tenant_slug=tenant_slug, user_role=body.get("user_role"))
        try:
            recorded_payload = record_fan_stock_observation_event(
                tenant_slug=tenant_slug,
                user_profile_id=actor.get("profile_id") or "",
                user_role=actor.get("user_role") or "",
                stock_code=body.get("stock_code"),
                stock_name=body.get("stock_name"),
                event_type=body.get("event_type"),
                entry_point=body.get("entry_point"),
                source_detail=body.get("source_detail"),
            )
        except Exception as exc:
            if not is_db_unavailable_error(exc):
                raise
            app.logger.warning("Database unavailable while recording fan stock observation event, using fallback payload")
    try:
        payload = build_fan_stock_observation_payload(tenant)
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable while building fan stock observation payload, using fallback data")
        payload = (build_tenant_dashboard_payload_fallback(tenant) or {}).get("fan_stock_observation") or {}
    return jsonify(
        {
            "ok": True,
            "recorded": bool(recorded_payload),
            "fan_stock_observation": payload,
        }
    )


@app.route("/api/tenant/<tenant_slug>/smart-indicators", methods=["GET", "POST"])
def api_tenant_smart_indicators(tenant_slug):
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or tenant["slug"] != tenant_slug:
        return jsonify({"success": False, "error": "tenant_not_found"}), 404
    if request.method == "GET":
        try:
            payload = build_tenant_dashboard_payload(tenant)
        except Exception as exc:
            if not is_db_unavailable_error(exc):
                raise
            app.logger.warning("Database unavailable while building tenant smart indicators API, using fallback data")
            payload = build_tenant_dashboard_payload_fallback(tenant)
        return jsonify(
            {
                "success": True,
                "smart_indicator_catalog": payload.get("smart_indicator_catalog") or {
                    "tenant_smart_indicators": [],
                    "base_indicators": [],
                },
                "dashboard": payload,
            }
        )
    denied = _tenant_smart_indicator_write_guard(tenant_slug)
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or "save").strip().lower()
    if action == "preview":
        try:
            preview = build_smart_indicator_preview(tenant_slug, body)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400
        except Exception as exc:
            app.logger.exception("Failed to preview tenant smart indicator")
            return jsonify({"success": False, "error": str(exc)}), 500
        return jsonify(
            {
                "success": True,
                "preview": preview,
                "formula_meta": preview.get("formula_meta") or {},
                "workflow_meta": preview.get("workflow_meta") or {},
                "smart_indicator_catalog": {
                    "tenant_smart_indicators": build_tenant_smart_indicator_catalog(tenant),
                    "base_indicators": build_dashboard_base_indicator_options(tenant),
                    "available_tags": build_tenant_smart_indicator_tag_catalog(tenant),
                },
            }
        )
    if action == "delete":
        indicator_code = str(body.get("indicator_code") or "").strip()
        definition = get_indicator_definition(indicator_code)
        if not definition:
            return jsonify({"success": False, "error": "indicator_not_found"}), 404
        if str(definition.get("source_type") or "").strip().lower() != "smart":
            return jsonify({"success": False, "error": "only_smart_indicators_can_be_deleted"}), 403
        if str(definition.get("tenant_slug") or "").strip().lower() != tenant_slug:
            return jsonify({"success": False, "error": "indicator_forbidden"}), 403
        saved = delete_tenant_smart_indicator(tenant_slug, indicator_code)
        if not saved:
            return jsonify({"success": False, "error": "indicator_delete_failed"}), 409
        latest_tenant = get_tenant_by_slug(tenant_slug, saved)
        payload = build_tenant_dashboard_payload(latest_tenant)
        return jsonify({"success": True, "dashboard": payload, "smart_indicator_catalog": payload.get("smart_indicator_catalog")})
    try:
        result = create_or_update_tenant_smart_indicator(tenant_slug, body)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Failed to save tenant smart indicator")
        return jsonify({"success": False, "error": str(exc)}), 500
    payload = build_tenant_dashboard_payload(result["tenant"])
    return jsonify(
        {
            "success": True,
            "definition": result["definition"],
            "latest_snapshot": result["latest_snapshot"],
            "formula_meta": result["formula_meta"],
            "workflow_meta": result.get("workflow_meta") or {},
            "dashboard": payload,
            "smart_indicator_catalog": payload.get("smart_indicator_catalog"),
            "fund_dashboard_state": payload.get("fund_dashboard_state"),
        }
    )

@app.route("/api/kol/broadcast", methods=["POST"])
def api_kol_broadcast():
    body = request.get_json(silent=True) or {}
    tenant_slug = str(body.get("tenant_slug") or request.args.get("tenant") or "").strip().lower()
    content = str(body.get("content") or "").strip()
    target = str(body.get("target") or "all").strip() or "all"
    if not content:
        return jsonify({"success": False, "error": "broadcast_content_required"}), 400
    broadcast_item = {
        "id": int(time.time() * 1000),
        "content": content,
        "time": now_ts(),
        "reach": random.randint(2000, 5000),
        "open_rate": random.randint(45, 86),
        "target": target,
        "type": "broadcast",
    }
    resolved_slug = tenant_slug or get_default_tenant_slug()
    state = append_broadcast_history(resolved_slug, broadcast_item)
    state = push_broadcast_to_fan_threads(resolved_slug, broadcast_item)
    payload = build_dm_center_payload(
        tenant_slug=resolved_slug,
        actor_role="dav",
        actor_profile_id="",
        include_fan_threads=True,
    )
    return jsonify({"success": True, **broadcast_item, "broadcasts": state["broadcasts"], "message_center_state": state, **payload})

@app.route("/api/kol/reply", methods=["POST"])
def api_kol_reply():
    body = request.get_json(silent=True) or {}
    tenant_slug = str(body.get("tenant_slug") or request.args.get("tenant") or "").strip().lower()
    thread_id = str(body.get("thread_id") or "").strip()
    content = str(body.get("content") or "").strip()
    is_paid = bool(body.get("is_paid", False))
    if not content:
        return jsonify({"success": False, "error": "reply_content_required"}), 400
    if not thread_id:
        return jsonify({"success": False, "error": "thread_id_required"}), 400
    resolved_slug = tenant_slug or get_default_tenant_slug()
    tenant = get_tenant_by_slug(resolved_slug)
    state = resolve_tenant_message_center_state(tenant, tenant.get("message_center_state"))
    threads = copy.deepcopy(state["threads"] or [])
    thread_index = find_message_thread_index(threads, thread_id=thread_id)
    if thread_index < 0:
        return jsonify({"success": False, "error": "thread_not_found"}), 404
    thread = dict(threads[thread_index])
    if str(thread.get("type") or "").strip() != "fan_interaction":
        return jsonify({"success": False, "error": "thread_type_invalid"}), 400
    messages = copy.deepcopy(thread.get("messages") or [])
    next_message_id = len(messages) + 1
    message_type = "paid" if is_paid else "text"
    message = {
        "id": next_message_id,
        "sender": "kol",
        "content": content,
        "time": now_ts(),
        "type": message_type,
    }
    if is_paid:
        message["price"] = 50
        message["preview"] = summarize_message_preview(content, limit=48) or "解锁查看完整内容"
    messages.append(message)
    thread["messages"] = messages[-120:]
    thread["content"] = content
    thread["last_msg"] = build_thread_last_message(thread, messages)
    thread["time"] = "刚刚"
    thread["status"] = "已回复"
    thread["kol_unread"] = 0
    thread["user_unread"] = max(1, int(thread.get("user_unread") or 0) + 1)
    thread["last_sender"] = "kol"
    thread["last_message_type"] = message_type
    normalized_thread = normalize_message_thread_item(thread, tenant, index=thread_index)
    threads.pop(thread_index)
    threads.insert(0, normalized_thread)
    _, latest_state = save_tenant_message_threads(resolved_slug, state, threads)
    payload = build_dm_center_payload(
        tenant_slug=resolved_slug,
        actor_role="dav",
        actor_profile_id="",
        include_fan_threads=True,
    )
    return jsonify({
        "success": True,
        "thread_id": normalized_thread["id"],
        "message": message,
        "status": normalized_thread["status"],
        "is_paid": is_paid,
        "revenue": 50 if is_paid else 0,
        "message_center_state": latest_state,
        **payload,
        "threads": gen_dm_conversations(tenant_slug=resolved_slug, include_fan_threads=True),
    })

@app.route("/prd")
def prd():
    return render_template("prd.html")
