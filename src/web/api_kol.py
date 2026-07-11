from src.runtime import *
from src.services import *

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


@app.route("/api/kol/portal-cms", methods=["POST"])
def api_save_kol_portal_cms():
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
    tenant_slug = str(request.args.get("tenant_slug") or "").strip().lower()
    limit = min(max(int(request.args.get("limit", 120)), 1), 300)
    return jsonify({
        "ok": True,
        "items": list_admin_knowledge_items(tenant_slug=tenant_slug, limit=limit),
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
            "source_text": body.get("source_text"),
            "prompt_text": body.get("prompt_text"),
            "prompt_tags": body.get("prompt_tags") if isinstance(body.get("prompt_tags"), list) else [],
            "selected_watchlist": body.get("selected_watchlist") if isinstance(body.get("selected_watchlist"), list) else [],
            "dashboard_cards": body.get("dashboard_cards") if isinstance(body.get("dashboard_cards"), list) else [],
            "knowledge_items": body.get("knowledge_items") if isinstance(body.get("knowledge_items"), list) else [],
            "speaker_name": speaker_name,
            "entry_point": entry_point,
        }
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


@app.route("/api/tenant/<tenant_slug>/dashboard", methods=["POST"])
def api_save_tenant_dashboard(tenant_slug):
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or tenant["slug"] != tenant_slug:
        return jsonify({"success": False, "error": "tenant_not_found"}), 404
    body = request.get_json(silent=True) or {}
    action = str(body.get("action") or "").strip().lower()
    dashboard = body.get("dashboard") if isinstance(body.get("dashboard"), dict) else None
    saved = update_tenant_fund_dashboard_config(tenant_slug, action, dashboard)
    if not saved:
        return jsonify({"success": False, "error": "invalid_action"}), 400
    latest_tenant = get_tenant_by_slug(tenant_slug, saved)
    payload = build_tenant_dashboard_payload(latest_tenant)
    return jsonify({"success": True, "dashboard": payload, "fund_dashboard_state": payload.get("fund_dashboard_state")})


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
        if str(definition.get("tenant_slug") or "").strip().lower() not in {"", tenant_slug}:
            return jsonify({"success": False, "error": "indicator_forbidden"}), 403
        saved = remove_smart_indicator_from_dashboard(tenant_slug, indicator_code)
        delete_indicator_definition(indicator_code)
        latest_tenant = get_tenant_by_slug(tenant_slug, saved) if saved else tenant
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
