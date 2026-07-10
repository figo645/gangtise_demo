from src.runtime import *
from src.domain.core_services import *
from src.domain.core_services import _estimate_token_count, _extract_usage_tokens
from src.domain.market_services import *
from src.web.request_helpers import get_client_ip
from flask import has_request_context

def get_platform_name(site_config=None):
    return get_platform_brand(site_config).get("name", DEFAULT_BRAND_CONFIG["name"])


def get_platform_short_name(site_config=None):
    return get_platform_brand(site_config).get("short_name", DEFAULT_BRAND_CONFIG["short_name"])


def get_voice_transcription_config(site_config=None):
    config = site_config or get_site_config()
    section = config.get("voice_transcription") if isinstance(config, dict) else {}
    engine = str((section or {}).get("engine") or "local").strip().lower()
    if engine not in {"local", "api"}:
        engine = "local"
    return {"engine": engine}


def get_voice_embedding_config(site_config=None):
    config = site_config or get_site_config()
    section = config.get("voice_embedding") if isinstance(config, dict) else {}
    engine = str((section or {}).get("engine") or "local").strip().lower()
    if engine not in {"local", "api"}:
        engine = "local"
    return {"engine": engine}


def get_evidence_chain_config(site_config=None):
    config = site_config or get_site_config()
    section = config.get("evidence_chain") if isinstance(config, dict) else {}
    return normalize_evidence_chain_config(section)


def get_review_generation_config(site_config=None):
    config = site_config or get_site_config()
    section = config.get("review_generation") if isinstance(config, dict) else {}
    return normalize_review_generation_config(section)


def get_default_llm_config(site_config=None, purpose="general"):
    config = site_config or get_site_config()
    registry = normalize_llm_registry_config((config or {}).get("llm_registry"))
    purpose_key = str(purpose or "general").strip().lower() or "general"
    default_key = str(registry.get("default_model_key") or "").strip()
    models = registry.get("models") if isinstance(registry.get("models"), list) else []
    selected = None
    if default_key:
        for item in models:
            if not isinstance(item, dict):
                continue
            if str(item.get("key") or "").strip() == default_key:
                selected = item
                break
    if not selected:
        for item in models:
            if not isinstance(item, dict):
                continue
            if str(item.get("purpose") or "").strip().lower() != purpose_key:
                continue
            if item.get("enabled", True) is False:
                continue
            selected = item
            break
    if not selected or selected.get("enabled", True) is False:
        return None
    return normalize_llm_model_config(selected)


def _normalize_openai_compatible_base_url(base_url):
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        normalized = OPENAI_BASE_URL
    return normalized.rstrip("/")


def _extract_llm_text_content(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value.strip():
                parts.append(text_value.strip())
                continue
            if item.get("type") == "output_text" and isinstance(item.get("text"), str):
                parts.append(item.get("text").strip())
        return "\n".join(part for part in parts if part).strip()
    return ""


def call_openai_compatible_llm(
    model_config,
    system_prompt,
    user_prompt,
    feature_code="",
    feature_label="",
    tenant_slug="",
    entry_point="",
    metadata=None,
    request_timeout_seconds=120,
):
    config = normalize_llm_model_config(model_config)
    model_name = str(config.get("model_name") or "").strip()
    if not model_name:
        raise RuntimeError("llm_model_name_missing")
    api_key = str(config.get("api_key") or "").strip() or OPENAI_API_KEY
    if not api_key:
        raise RuntimeError("llm_api_key_missing")
    endpoint_base = _normalize_openai_compatible_base_url(config.get("base_url"))
    request_started = time.perf_counter()
    system_text = str(system_prompt or "").strip()
    user_text = str(user_prompt or "").strip()
    response = requests.post(
        f"{endpoint_base}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model_name,
            "temperature": 0.25,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
        },
        timeout=max(5, int(request_timeout_seconds or 120)),
    )
    if response.status_code >= 400:
        raise RuntimeError(f"llm_request_failed:{response.status_code}:{response.text[:240]}")
    payload = response.json()
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not choices or not isinstance(choices, list):
        raise RuntimeError("invalid_llm_payload")
    first_choice = choices[0] if isinstance(choices[0], dict) else {}
    message = first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {}
    content = _extract_llm_text_content(message.get("content"))
    if not content:
        raise RuntimeError("empty_llm_response")
    input_tokens, output_tokens, total_tokens = _extract_usage_tokens(payload)
    if total_tokens <= 0:
        input_tokens = _estimate_token_count(system_text) + _estimate_token_count(user_text)
        output_tokens = _estimate_token_count(content)
        total_tokens = input_tokens + output_tokens
    log_token_usage(
        usage_type="llm",
        feature_code=feature_code or "general_llm",
        feature_label=feature_label or "通用大模型调用",
        tenant_slug=tenant_slug,
        entry_point=entry_point,
        model_provider=str(config.get("provider") or "").strip(),
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        latency_ms=int((time.perf_counter() - request_started) * 1000),
        request_chars=len(system_text) + len(user_text),
        response_chars=len(content),
        metadata=metadata or {},
    )
    return content


def _is_truthy_flag(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def enhance_review_voice_transcript_with_llm(transcript, entry_point="", speaker_name="", tenant_slug=""):
    normalized_transcript = str(transcript or "").strip()
    if not normalized_transcript:
        raise ValueError("empty_transcript")
    llm_model = get_default_llm_config(purpose="general")
    if not llm_model:
        raise RuntimeError("llm_model_unavailable")
    context_label = "语音转写增强"
    if entry_point:
        context_label = f"{context_label} · {entry_point}"
    speaker_label = str(speaker_name or "").strip() or "未命名用户"
    system_prompt = (
        "你是一个中文语音纪要整理助手。"
        "请基于原始转写内容做轻量增强整理，去掉明显口语噪音和重复，修复少量语病，"
        "保留原始事实、观点、风险提示与不确定性，不要补充原文没有提到的信息，不要编造数字。"
        "输出纯文本，优先按自然段组织；如果原文明显包含多个观点，可以拆成短段。"
    )
    user_prompt = (
        f"场景：{context_label}\n"
        f"说话人：{speaker_label}\n"
        "请输出更适合后续知识入库或文案编辑的整理稿。"
        "如果原始转写已经足够清晰，只做最少改动。\n\n"
        f"原始转写：\n{normalized_transcript}"
    )
    enhanced_text = call_openai_compatible_llm(
        llm_model,
        system_prompt,
        user_prompt,
        feature_code="review_voice_enhancement",
        feature_label="语音转写增强",
        tenant_slug=tenant_slug,
        entry_point=entry_point,
        metadata={"speaker_name": speaker_label},
    )
    normalized_enhanced = str(enhanced_text or "").strip()
    if not normalized_enhanced:
        raise RuntimeError("empty_llm_response")
    return {
        "text": normalized_enhanced,
        "model": {
            "key": llm_model.get("key"),
            "label": llm_model.get("label"),
            "provider": llm_model.get("provider"),
            "model_name": llm_model.get("model_name"),
            "purpose": llm_model.get("purpose"),
        },
    }


def generate_review_draft_with_llm(
    source_text,
    review_period="",
    source_mode="",
    prompt_text="",
    prompt_tags=None,
    selected_watchlist=None,
    speaker_name="",
    entry_point="",
    tenant_slug="",
    job_code="",
):
    normalized_source = str(source_text or "").strip()
    if not normalized_source:
        raise ValueError("review_source_text_required")
    llm_model = get_default_llm_config(purpose="general")
    if not llm_model:
        raise RuntimeError("review_draft_llm_not_configured")
    period_label_map = {
        "day": "日复盘",
        "week": "周复盘",
        "month": "月复盘",
        "quarter": "季复盘",
        "knowledge": "知识整理",
    }
    review_period_key = str(review_period or "").strip().lower()
    source_mode_key = str(source_mode or "").strip().lower()
    speaker_label = str(speaker_name or "").strip() or "未命名大V"
    watchlist_items = [str(item).strip() for item in (selected_watchlist or []) if str(item).strip()]
    tag_items = [str(item).strip() for item in (prompt_tags or []) if str(item).strip()]
    prompt_value = str(prompt_text or "").strip()
    system_prompt = (
        "你是一个中文投研复盘编辑助手。"
        "请把输入材料整理成适合直接发布前预览的完整复盘草稿。"
        "必须保留原始观点、风险提示和不确定性，不要编造事实、数字或结论。"
        "输出纯文本，用自然段组织；优先按市场主线、行业判断、重点个股、验证节点和风险提示展开。"
        "语言要专业、清晰、克制，避免空话和宣传语。"
    )
    user_prompt = "\n".join([
        f"复盘周期：{period_label_map.get(review_period_key, review_period_key or '未指定')}",
        f"输入来源：{source_mode_key or 'unknown'}",
        f"作者身份：{speaker_label}",
        f"触发入口：{entry_point or 'unknown'}",
        f"关注股票：{'、'.join(watchlist_items) if watchlist_items else '未指定'}",
        f"附加标签：{'、'.join(tag_items) if tag_items else '无'}",
        f"改写规则：{prompt_value or '无，请按专业复盘风格整理'}",
        "",
        "请直接输出最终复盘草稿，不要解释你的处理过程，不要输出标题前缀如“以下是整理结果”。",
        "",
        "原始材料：",
        normalized_source,
    ])
    if job_code:
        report_user_async_job_progress(
            job_code,
            stage="llm_preparing",
            percent=55,
            summary="正在整理原始材料并构建复盘提示词",
            log_text="已完成素材归并，正在调用大模型生成复盘草稿。",
        )
    rendered_text = call_openai_compatible_llm(
        llm_model,
        system_prompt,
        user_prompt,
        feature_code="review_draft_generation",
        feature_label="复盘草稿生成",
        tenant_slug=tenant_slug,
        entry_point=entry_point,
        metadata={
            "review_period": review_period_key,
            "source_mode": source_mode_key,
            "watchlist_count": len(watchlist_items),
            "job_code": job_code,
        },
    )
    normalized_text = str(rendered_text or "").strip()
    if not normalized_text:
        raise RuntimeError("empty_llm_response")
    if job_code:
        report_user_async_job_progress(
            job_code,
            stage="llm_postprocessing",
            percent=85,
            summary="大模型已返回草稿，正在整理预览结果",
            log_text="复盘草稿已生成，正在整理模型信息和预览内容。",
        )
    return {
        "text": normalized_text,
        "llm_model": {
            "key": llm_model.get("key"),
            "label": llm_model.get("label"),
            "provider": llm_model.get("provider"),
            "model_name": llm_model.get("model_name"),
            "purpose": llm_model.get("purpose"),
        },
    }


def _get_review_period_label(review_period):
    period_label_map = {
        "day": "日复盘",
        "week": "周复盘",
        "month": "月复盘",
        "quarter": "季复盘",
        "knowledge": "知识整理",
    }
    key = str(review_period or "").strip().lower()
    return period_label_map.get(key, key or "未指定")


def _format_review_dashboard_blocks(cards):
    blocks = []
    for index, item in enumerate(cards or [], start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or f"卡片 {index}").strip() or f"卡片 {index}"
        summary = str(item.get("summary") or item.get("assessment") or item.get("hint") or "").strip()
        value = str(item.get("value") or "").strip()
        prompt = str(item.get("prompt") or "").strip()
        data_sources = [str(source).strip() for source in (item.get("data_sources") or []) if str(source).strip()]
        news_sources = [str(source).strip() for source in (item.get("news_sources") or []) if str(source).strip()]
        evidence_note = str(item.get("evidence_note") or "").strip()
        parts = [
            f"卡片ID：{str(item.get('id') or '').strip() or f'card_{index}'}",
            f"卡片标题：{title}",
            f"卡片类型：{str(item.get('category') or item.get('kind') or '智能卡片').strip() or '智能卡片'}",
        ]
        if value:
            parts.append(f"关键值：{value}")
        if summary:
            parts.append(f"摘要：{summary}")
        if evidence_note:
            parts.append(f"补充说明：{evidence_note}")
        if prompt:
            parts.append(f"卡片提示词：{prompt}")
        parts.append(f"数据来源：{'；'.join(data_sources) if data_sources else '未提供'}")
        parts.append(f"新闻来源：{'；'.join(news_sources) if news_sources else '未提供'}")
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def _format_review_knowledge_blocks(items):
    blocks = []
    for index, item in enumerate(items or [], start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or f"知识材料 {index}").strip() or f"知识材料 {index}"
        summary = str(item.get("summary") or item.get("body") or item.get("raw_input") or "").strip()
        body = str(item.get("body") or item.get("raw_input") or summary).strip()
        source_detail = str(item.get("source_detail") or item.get("source") or "").strip()
        tags = [str(tag).strip() for tag in (item.get("tags") or []) if str(tag).strip()]
        blocks.append(
            "\n".join(
                [
                    f"知识ID：{str(item.get('id') or item.get('knowledge_id') or f'knowledge_{index}').strip()}",
                    f"知识标题：{title}",
                    f"来源说明：{source_detail or '未提供'}",
                    f"标签：{'、'.join(tags) if tags else '无'}",
                    f"摘要：{summary or '暂无摘要'}",
                    f"正文材料：{body or '暂无正文'}",
                ]
            )
        )
    return "\n\n".join(blocks)


def polish_review_input_with_llm(
    source_text,
    review_period="",
    source_mode="",
    speaker_name="",
    entry_point="",
    tenant_slug="",
    job_code="",
):
    normalized_source = str(source_text or "").strip()
    if not normalized_source:
        raise ValueError("review_source_text_required")
    llm_model = get_default_llm_config(purpose="general")
    if not llm_model:
        raise RuntimeError("review_polish_llm_not_configured")
    review_cfg = get_review_generation_config()
    speaker_label = str(speaker_name or "").strip() or "未命名大V"
    if job_code:
        report_user_async_job_progress(
            job_code,
            stage="llm_preparing",
            percent=38,
            summary="正在整理原始输入并准备润色",
            log_text="已进入输入润色阶段，正在构建提示词。",
        )
    system_prompt = review_cfg.get("polish_system_prompt") or DEFAULT_SITE_CONFIG["review_generation"]["polish_system_prompt"]
    user_prompt = (
        str(review_cfg.get("polish_user_template") or DEFAULT_SITE_CONFIG["review_generation"]["polish_user_template"])
        .replace("{period_label}", _get_review_period_label(review_period))
        .replace("{source_mode}", str(source_mode or "unknown").strip() or "unknown")
        .replace("{speaker_label}", speaker_label)
        .replace("{entry_point}", str(entry_point or "unknown").strip() or "unknown")
        .replace("{source_text}", normalized_source)
    )
    polished_text = call_openai_compatible_llm(
        llm_model,
        system_prompt,
        user_prompt,
        feature_code="review_input_polish",
        feature_label="复盘输入润色",
        tenant_slug=tenant_slug,
        entry_point=entry_point,
        metadata={
            "review_period": str(review_period or "").strip().lower(),
            "source_mode": str(source_mode or "").strip().lower(),
            "job_code": job_code,
            "stage": "polish",
        },
        request_timeout_seconds=review_cfg.get("polish_timeout_seconds", 45),
    )
    normalized_text = str(polished_text or "").strip()
    if not normalized_text:
        raise RuntimeError("empty_llm_response")
    if job_code:
        report_user_async_job_progress(
            job_code,
            stage="llm_postprocessing",
            percent=82,
            summary="输入润色完成，正在整理预览内容",
            log_text="大模型已返回润色结果，正在回填复盘输入。",
        )
    return {
        "text": normalized_text,
        "llm_model": {
            "key": llm_model.get("key"),
            "label": llm_model.get("label"),
            "provider": llm_model.get("provider"),
            "model_name": llm_model.get("model_name"),
            "purpose": llm_model.get("purpose"),
        },
    }


def compose_review_draft_with_llm(
    source_text,
    review_period="",
    prompt_text="",
    prompt_tags=None,
    selected_watchlist=None,
    speaker_name="",
    entry_point="",
    tenant_slug="",
    dashboard_cards=None,
    knowledge_items=None,
    job_code="",
):
    normalized_source = str(source_text or "").strip()
    if not normalized_source:
        raise ValueError("review_source_text_required")
    llm_model = get_default_llm_config(purpose="general")
    if not llm_model:
        raise RuntimeError("review_compose_llm_not_configured")
    review_cfg = get_review_generation_config()
    speaker_label = str(speaker_name or "").strip() or "未命名大V"
    watchlist_items = [str(item).strip() for item in (selected_watchlist or []) if str(item).strip()]
    tag_items = [str(item).strip() for item in (prompt_tags or []) if str(item).strip()]
    prompt_value = str(prompt_text or "").strip() or "无，请按专业复盘风格整理"
    dashboard_blocks = _format_review_dashboard_blocks(dashboard_cards or [])
    knowledge_blocks = _format_review_knowledge_blocks(knowledge_items or [])
    if job_code:
        report_user_async_job_progress(
            job_code,
            stage="llm_preparing",
            percent=46,
            summary="正在聚合智能仪表盘卡片并准备成稿",
            log_text="已完成卡片与输入拼接，准备调用大模型生成完整复盘。",
            extra_result={
                "selected_card_count": len(dashboard_cards or []),
                "knowledge_item_count": len(knowledge_items or []),
            },
        )
    system_prompt = review_cfg.get("compose_system_prompt") or DEFAULT_SITE_CONFIG["review_generation"]["compose_system_prompt"]
    user_prompt = (
        str(review_cfg.get("compose_user_template") or DEFAULT_SITE_CONFIG["review_generation"]["compose_user_template"])
        .replace("{period_label}", _get_review_period_label(review_period))
        .replace("{speaker_label}", speaker_label)
        .replace("{entry_point}", str(entry_point or "unknown").strip() or "unknown")
        .replace("{watchlist_text}", "、".join(watchlist_items) if watchlist_items else "未指定")
        .replace("{tag_text}", "、".join(tag_items) if tag_items else "无")
        .replace("{prompt_text}", prompt_value)
        .replace("{source_text}", normalized_source)
        .replace("{dashboard_blocks}", dashboard_blocks or "未选择智能仪表盘卡片")
        .replace("{knowledge_blocks}", knowledge_blocks or "未选择知识材料")
    )
    rendered_text = call_openai_compatible_llm(
        llm_model,
        system_prompt,
        user_prompt,
        feature_code="review_compose_generation",
        feature_label="复盘完整成稿",
        tenant_slug=tenant_slug,
        entry_point=entry_point,
        metadata={
            "review_period": str(review_period or "").strip().lower(),
            "watchlist_count": len(watchlist_items),
            "card_count": len(dashboard_cards or []),
            "knowledge_item_count": len(knowledge_items or []),
            "job_code": job_code,
            "stage": "compose",
        },
        request_timeout_seconds=review_cfg.get("compose_timeout_seconds", 60),
    )
    normalized_text = str(rendered_text or "").strip()
    if not normalized_text:
        raise RuntimeError("empty_llm_response")
    if job_code:
        report_user_async_job_progress(
            job_code,
            stage="llm_postprocessing",
            percent=88,
            summary="完整复盘草稿已返回，正在整理预览结果",
            log_text="复盘成稿已生成，正在回填卡片与模型信息。",
            extra_result={
                "selected_card_count": len(dashboard_cards or []),
                "knowledge_item_count": len(knowledge_items or []),
            },
        )
    return {
        "text": normalized_text,
        "llm_model": {
            "key": llm_model.get("key"),
            "label": llm_model.get("label"),
            "provider": llm_model.get("provider"),
            "model_name": llm_model.get("model_name"),
            "purpose": llm_model.get("purpose"),
        },
    }


def get_review_vector_db_connection():
    target = get_runtime_db_target().get("vector", {})
    return psycopg2.connect(
        host=target.get("host") or VECTOR_DB_HOST,
        port=target.get("port") or VECTOR_DB_PORT,
        dbname=target.get("dbname") or VECTOR_DB_NAME,
        user=target.get("user") or VECTOR_DB_USER,
        password=target.get("password") or VECTOR_DB_PASSWORD,
        connect_timeout=8,
    )


def _safe_audio_filename(filename):
    raw = os.path.basename(str(filename or "").strip())
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)
    return sanitized[:120] or f"review_voice_{int(time.time())}.webm"


def _guess_audio_content_type(filename, provided_type):
    content_type = str(provided_type or "").strip().lower()
    if content_type.startswith("audio/") or content_type in {"video/webm", "video/mp4"}:
        return content_type
    suffix = Path(str(filename or "")).suffix.lower()
    mapping = {
        ".mp3": "audio/mpeg",
        ".mp4": "audio/mp4",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
        ".mpeg": "audio/mpeg",
        ".mpga": "audio/mpeg",
    }
    return mapping.get(suffix, "application/octet-stream")


def _is_allowed_audio_upload(filename, content_type):
    suffix = Path(str(filename or "")).suffix.lower()
    normalized_type = str(content_type or "").strip().lower()
    if suffix in ALLOWED_AUDIO_EXTENSIONS:
        return True
    return normalized_type.startswith("audio/") or normalized_type in {"video/webm", "video/mp4"}


def _write_temp_audio_file(audio_bytes, filename):
    safe_suffix = Path(filename).suffix.lower() or ".webm"
    temp_dir = Path("/private/tmp") if Path("/private/tmp").exists() else Path("/tmp")
    temp_path = temp_dir / f"gangtise_review_{int(time.time() * 1000)}_{os.getpid()}{safe_suffix}"
    temp_path.write_bytes(audio_bytes)
    return temp_path


def _load_local_whisper_model():
    cached = g.get("local_whisper_model")
    if cached is not None:
        return cached
    if WhisperModel is None:
        raise RuntimeError("local_transcriber_dependency_missing")
    try:
        model = WhisperModel(
            LOCAL_WHISPER_MODEL_SIZE,
            device=LOCAL_WHISPER_DEVICE,
            compute_type=LOCAL_WHISPER_COMPUTE_TYPE,
        )
    except Exception as exc:
        raise RuntimeError(f"local_transcriber_init_failed:{exc}") from exc
    g.local_whisper_model = model
    return model


def _load_local_embedding_model():
    cached = g.get("local_embedding_model")
    if cached is not None:
        return cached
    if SentenceTransformer is None:
        raise RuntimeError("local_embedding_dependency_missing")
    try:
        model = SentenceTransformer(LOCAL_EMBEDDING_MODEL_NAME)
    except Exception as exc:
        raise RuntimeError(f"local_embedding_init_failed:{exc}") from exc
    g.local_embedding_model = model
    return model


def _ensure_review_voice_vector_table(conn):
    has_pgvector = False
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS review_voice_embeddings (
                id BIGSERIAL PRIMARY KEY,
                tenant_slug TEXT NOT NULL DEFAULT '',
                review_period TEXT NOT NULL DEFAULT '',
                entry_point TEXT NOT NULL DEFAULT '',
                vector_namespace TEXT NOT NULL DEFAULT '',
                speaker_name TEXT NOT NULL DEFAULT '',
                original_filename TEXT NOT NULL DEFAULT '',
                mime_type TEXT NOT NULL DEFAULT '',
                audio_size_bytes INTEGER NOT NULL DEFAULT 0,
                transcript_text TEXT NOT NULL,
                transcript_hash TEXT NOT NULL,
                transcription_engine TEXT NOT NULL DEFAULT '',
                transcript_model TEXT NOT NULL DEFAULT '',
                embedding_engine TEXT NOT NULL DEFAULT '',
                embedding_model TEXT NOT NULL DEFAULT '',
                embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_tenant_created ON review_voice_embeddings(tenant_slug, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_hash ON review_voice_embeddings(transcript_hash)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_namespace ON review_voice_embeddings(vector_namespace, created_at DESC)")
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception:
            conn.rollback()
            with conn.cursor() as retry_cur:
                retry_cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS review_voice_embeddings (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_slug TEXT NOT NULL DEFAULT '',
                        review_period TEXT NOT NULL DEFAULT '',
                        entry_point TEXT NOT NULL DEFAULT '',
                        vector_namespace TEXT NOT NULL DEFAULT '',
                        speaker_name TEXT NOT NULL DEFAULT '',
                        original_filename TEXT NOT NULL DEFAULT '',
                        mime_type TEXT NOT NULL DEFAULT '',
                        audio_size_bytes INTEGER NOT NULL DEFAULT 0,
                        transcript_text TEXT NOT NULL,
                        transcript_hash TEXT NOT NULL,
                        transcription_engine TEXT NOT NULL DEFAULT '',
                        transcript_model TEXT NOT NULL DEFAULT '',
                        embedding_engine TEXT NOT NULL DEFAULT '',
                        embedding_model TEXT NOT NULL DEFAULT '',
                        embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                retry_cur.execute("CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_tenant_created ON review_voice_embeddings(tenant_slug, created_at DESC)")
                retry_cur.execute("CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_hash ON review_voice_embeddings(transcript_hash)")
                retry_cur.execute("CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_namespace ON review_voice_embeddings(vector_namespace, created_at DESC)")
            conn.commit()
        with conn.cursor() as check_cur:
            check_cur.execute("ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS vector_namespace TEXT NOT NULL DEFAULT ''")
            check_cur.execute("ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS transcription_engine TEXT NOT NULL DEFAULT ''")
            check_cur.execute("ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS embedding_engine TEXT NOT NULL DEFAULT ''")
            check_cur.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            has_pgvector = bool(check_cur.fetchone()[0])
            if has_pgvector:
                check_cur.execute(
                    f"ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS embedding_vector vector({PGVECTOR_TARGET_DIM})"
                )
                try:
                    check_cur.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_review_voice_embeddings_vector
                        ON review_voice_embeddings
                        USING ivfflat (embedding_vector vector_cosine_ops)
                        """
                    )
                except Exception:
                    conn.rollback()
                    with conn.cursor() as recovery_cur:
                        recovery_cur.execute(
                            """
                            CREATE TABLE IF NOT EXISTS review_voice_embeddings (
                                id BIGSERIAL PRIMARY KEY,
                                tenant_slug TEXT NOT NULL DEFAULT '',
                                review_period TEXT NOT NULL DEFAULT '',
                                entry_point TEXT NOT NULL DEFAULT '',
                                speaker_name TEXT NOT NULL DEFAULT '',
                                original_filename TEXT NOT NULL DEFAULT '',
                                mime_type TEXT NOT NULL DEFAULT '',
                                audio_size_bytes INTEGER NOT NULL DEFAULT 0,
                                transcript_text TEXT NOT NULL,
                                transcript_hash TEXT NOT NULL,
                                transcript_model TEXT NOT NULL DEFAULT '',
                                embedding_model TEXT NOT NULL DEFAULT '',
                                embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                        recovery_cur.execute(
                            f"ALTER TABLE review_voice_embeddings ADD COLUMN IF NOT EXISTS embedding_vector vector({PGVECTOR_TARGET_DIM})"
                        )
    conn.commit()
    return has_pgvector


def _transcribe_audio_with_python(audio_bytes, filename, content_type):
    if not OPENAI_API_KEY:
        raise RuntimeError("openai_api_key_missing")
    response = requests.post(
        f"{OPENAI_BASE_URL}/audio/transcriptions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        data={
            "model": OPENAI_AUDIO_MODEL,
            "language": OPENAI_AUDIO_LANGUAGE,
            "response_format": "json",
            "prompt": "请尽量按原意转写中文金融复盘口述，保留主线、个股、风险提示和验证节点。",
        },
        files={"file": (filename, audio_bytes, content_type)},
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"transcription_request_failed:{response.status_code}:{response.text[:240]}")
    payload = response.json()
    transcript = str(payload.get("text") or "").strip()
    if not transcript:
        raise RuntimeError("empty_transcript")
    return transcript


def _transcribe_audio_locally(audio_bytes, filename):
    temp_path = _write_temp_audio_file(audio_bytes, filename)
    try:
        model = _load_local_whisper_model()
        segments, _info = model.transcribe(
            str(temp_path),
            language=OPENAI_AUDIO_LANGUAGE or "zh",
            vad_filter=True,
            beam_size=5,
        )
        transcript = " ".join((segment.text or "").strip() for segment in segments).strip()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"local_transcription_failed:{exc}") from exc
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
    if not transcript:
        raise RuntimeError("empty_transcript")
    return transcript


def transcribe_review_audio(audio_bytes, filename, content_type, engine="local"):
    normalized_engine = str(engine or "local").strip().lower()
    if normalized_engine == "local":
        return _transcribe_audio_locally(audio_bytes, filename), "local"
    if normalized_engine == "api":
        return _transcribe_audio_with_python(audio_bytes, filename, content_type), "api"
    raise RuntimeError("unsupported_transcription_engine")


def _build_text_embedding_with_api(text, feature_code="", feature_label="", tenant_slug="", entry_point="", metadata=None):
    if not OPENAI_API_KEY:
        raise RuntimeError("openai_api_key_missing")
    request_started = time.perf_counter()
    response = requests.post(
        f"{OPENAI_BASE_URL}/embeddings",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_EMBEDDING_MODEL,
            "input": text,
        },
        timeout=120,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"embedding_request_failed:{response.status_code}:{response.text[:240]}")
    payload = response.json()
    items = payload.get("data") if isinstance(payload, dict) else None
    if not items or not isinstance(items, list):
        raise RuntimeError("invalid_embedding_payload")
    vector = items[0].get("embedding") if isinstance(items[0], dict) else None
    if not isinstance(vector, list) or not vector:
        raise RuntimeError("invalid_embedding_vector")
    input_tokens, output_tokens, total_tokens = _extract_usage_tokens(payload)
    if total_tokens <= 0:
        input_tokens = _estimate_token_count(text)
        output_tokens = 0
        total_tokens = input_tokens
    log_token_usage(
        usage_type="embedding",
        feature_code=feature_code or "general_embedding",
        feature_label=feature_label or "文本向量化",
        tenant_slug=tenant_slug,
        entry_point=entry_point,
        model_provider="openai_compatible",
        model_name=OPENAI_EMBEDDING_MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        latency_ms=int((time.perf_counter() - request_started) * 1000),
        request_chars=len(str(text or "")),
        response_chars=0,
        metadata=metadata or {},
    )
    return [float(value) for value in vector]


def _build_text_embedding_locally(text):
    model = _load_local_embedding_model()
    try:
        vector = model.encode(text, normalize_embeddings=True)
    except Exception as exc:
        raise RuntimeError(f"local_embedding_failed:{exc}") from exc
    try:
        values = vector.tolist()
    except Exception:
        values = list(vector)
    return [float(value) for value in values]


def build_text_embedding(text, engine="api", feature_code="", feature_label="", tenant_slug="", entry_point="", metadata=None):
    normalized_engine = str(engine or "api").strip().lower()
    if normalized_engine == "local":
        return _build_text_embedding_locally(text), "local", LOCAL_EMBEDDING_MODEL_NAME
    if normalized_engine == "api":
        return _build_text_embedding_with_api(
            text,
            feature_code=feature_code,
            feature_label=feature_label,
            tenant_slug=tenant_slug,
            entry_point=entry_point,
            metadata=metadata,
        ), "api", OPENAI_EMBEDDING_MODEL
    raise RuntimeError("unsupported_embedding_engine")


def build_vector_namespace(embedding_engine, embedding_model):
    engine_key = str(embedding_engine or "").strip().lower() or "unknown"
    model_key = re.sub(r"[^a-z0-9]+", "_", str(embedding_model or "").strip().lower()).strip("_")
    return f"review_voice__{engine_key}__{model_key or 'default'}"


def _store_review_voice_embedding_record(
    tenant_slug,
    review_period,
    entry_point,
    vector_namespace,
    speaker_name,
    filename,
    content_type,
    audio_size_bytes,
    transcript,
    transcription_engine,
    transcript_model,
    embedding,
    embedding_engine,
    embedding_model,
): 
    transcript_hash = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
    client_ip = "unknown"
    user_agent = ""
    if has_request_context():
        try:
            client_ip = get_client_ip()
        except Exception:
            client_ip = "unknown"
        try:
            user_agent = str(request.headers.get("User-Agent", "") or "")
        except Exception:
            user_agent = ""
    metadata = {
        "client_ip": client_ip,
        "user_agent": user_agent,
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "embedding_dimensions": len(embedding),
        "vector_namespace": vector_namespace,
    }
    with get_review_vector_db_connection() as conn:
        has_pgvector = _ensure_review_voice_vector_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO review_voice_embeddings (
                    tenant_slug, review_period, entry_point, vector_namespace, speaker_name,
                    original_filename, mime_type, audio_size_bytes,
                    transcript_text, transcript_hash, transcription_engine, transcript_model,
                    embedding_engine, embedding_model, embedding_json, metadata_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (
                    str(tenant_slug or "").strip(),
                    str(review_period or "").strip(),
                    str(entry_point or "").strip(),
                    str(vector_namespace or "").strip(),
                    str(speaker_name or "").strip(),
                    filename,
                    content_type,
                    int(audio_size_bytes),
                    transcript,
                    transcript_hash,
                    str(transcription_engine or "").strip(),
                    str(transcript_model or "").strip(),
                    str(embedding_engine or "").strip(),
                    str(embedding_model or "").strip(),
                    Json(embedding),
                    Json(metadata),
                ),
            )
            row = cur.fetchone()
            storage_mode = "jsonb"
            if has_pgvector and len(embedding) == PGVECTOR_TARGET_DIM:
                vector_literal = "[" + ",".join(f"{float(value):.10f}" for value in embedding) + "]"
                cur.execute(
                    "UPDATE review_voice_embeddings SET embedding_vector = %s::vector WHERE id = %s",
                    (vector_literal, row[0]),
                )
                storage_mode = "pgvector"
        conn.commit()
    return {
        "id": int(row[0]),
        "created_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
        "storage_mode": storage_mode,
        "embedding_dimensions": len(embedding),
        "transcript_hash": transcript_hash,
        "vector_namespace": vector_namespace,
    }


def _ensure_knowledge_embedding_table(conn):
    has_pgvector = False
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                id BIGSERIAL PRIMARY KEY,
                tenant_slug TEXT NOT NULL DEFAULT '',
                knowledge_id TEXT NOT NULL DEFAULT '',
                knowledge_type TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                body_text TEXT NOT NULL DEFAULT '',
                source_detail TEXT NOT NULL DEFAULT '',
                vector_namespace TEXT NOT NULL DEFAULT '',
                embedding_engine TEXT NOT NULL DEFAULT '',
                embedding_model TEXT NOT NULL DEFAULT '',
                embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_tenant_created ON knowledge_embeddings(tenant_slug, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_knowledge_id ON knowledge_embeddings(knowledge_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_namespace ON knowledge_embeddings(vector_namespace, created_at DESC)")
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        except Exception:
            conn.rollback()
            with conn.cursor() as retry_cur:
                retry_cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_slug TEXT NOT NULL DEFAULT '',
                        knowledge_id TEXT NOT NULL DEFAULT '',
                        knowledge_type TEXT NOT NULL DEFAULT '',
                        title TEXT NOT NULL DEFAULT '',
                        summary TEXT NOT NULL DEFAULT '',
                        body_text TEXT NOT NULL DEFAULT '',
                        source_detail TEXT NOT NULL DEFAULT '',
                        vector_namespace TEXT NOT NULL DEFAULT '',
                        embedding_engine TEXT NOT NULL DEFAULT '',
                        embedding_model TEXT NOT NULL DEFAULT '',
                        embedding_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                retry_cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_tenant_created ON knowledge_embeddings(tenant_slug, created_at DESC)")
                retry_cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_knowledge_id ON knowledge_embeddings(knowledge_id)")
                retry_cur.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_namespace ON knowledge_embeddings(vector_namespace, created_at DESC)")
            conn.commit()
        with conn.cursor() as check_cur:
            check_cur.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            has_pgvector = bool(check_cur.fetchone()[0])
            if has_pgvector:
                check_cur.execute(
                    f"ALTER TABLE knowledge_embeddings ADD COLUMN IF NOT EXISTS embedding_vector vector({PGVECTOR_TARGET_DIM})"
                )
    conn.commit()
    return has_pgvector


def _store_knowledge_embedding_record(
    tenant_slug,
    knowledge_id,
    knowledge_type,
    title,
    summary,
    body_text,
    source_detail,
    vector_namespace,
    embedding,
    embedding_engine,
    embedding_model,
    metadata,
):
    with get_review_vector_db_connection() as conn:
        has_pgvector = _ensure_knowledge_embedding_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO knowledge_embeddings (
                    tenant_slug, knowledge_id, knowledge_type, title, summary, body_text, source_detail,
                    vector_namespace, embedding_engine, embedding_model, embedding_json, metadata_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
                """,
                (
                    str(tenant_slug or "").strip(),
                    str(knowledge_id or "").strip(),
                    str(knowledge_type or "").strip(),
                    str(title or "").strip(),
                    str(summary or "").strip(),
                    str(body_text or "").strip(),
                    str(source_detail or "").strip(),
                    str(vector_namespace or "").strip(),
                    str(embedding_engine or "").strip(),
                    str(embedding_model or "").strip(),
                    Json(embedding),
                    Json(metadata or {}),
                ),
            )
            row = cur.fetchone()
            storage_mode = "jsonb"
            if has_pgvector and len(embedding) == PGVECTOR_TARGET_DIM:
                vector_literal = "[" + ",".join(f"{float(value):.10f}" for value in embedding) + "]"
                cur.execute(
                    "UPDATE knowledge_embeddings SET embedding_vector = %s::vector WHERE id = %s",
                    (vector_literal, row[0]),
                )
                storage_mode = "pgvector"
        conn.commit()
    return {
        "id": int(row[0]),
        "created_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
        "storage_mode": storage_mode,
        "embedding_dimensions": len(embedding),
        "vector_namespace": vector_namespace,
    }


def save_manual_knowledge_entry(
    tenant_slug,
    title="",
    summary="",
    body="",
    raw_html="",
    notes="",
    notes_html="",
    knowledge_id="",
    skip_ai_processing=True,
    knowledge_type="manual",
    source_label="",
    source_detail="",
    tags=None,
    files=None,
    source_url="",
    voice_minutes=None,
    parse_meta=None,
    processing_mode="algorithm",
    job_code="",
):
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or tenant.get("slug") != tenant_slug:
        raise ValueError("tenant_not_found")
    normalized_type = str(knowledge_type or "manual").strip().lower()
    if normalized_type not in {"voice", "file", "url", "manual"}:
        normalized_type = "manual"
    normalized_title = str(title or "").strip() or (
        "最新语音纪要整理" if normalized_type == "voice"
        else "最新文件资料整理" if normalized_type == "file"
        else "网页资料提炼" if normalized_type == "url"
        else "最新文本知识整理"
    )
    normalized_summary = str(summary or "").strip() or (
        "已通过语音方式沉淀知识内容。" if normalized_type == "voice"
        else "已通过文件方式沉淀知识内容。" if normalized_type == "file"
        else "已通过网页资料沉淀知识内容。" if normalized_type == "url"
        else "已通过纯文本方式沉淀知识内容。"
    )
    normalized_body = str(body or "").strip() or normalized_summary
    normalized_source_label = str(source_label or "").strip() or (
        "语音输入" if normalized_type == "voice"
        else "文件上传" if normalized_type == "file"
        else "网页 URL" if normalized_type == "url"
        else "纯文本编写"
    )
    normalized_source_detail = str(source_detail or "").strip() or (
        f"来源：语音转写 · {int(voice_minutes or 6)}分钟" if normalized_type == "voice"
        else f"来源：文件上传 · {' / '.join([str(item).strip() for item in (files or []) if str(item).strip()][:4]) or '未命名文件'}" if normalized_type == "file"
        else f"来源：网页 URL · {source_url or 'example.com'}" if normalized_type == "url"
        else f"来源：纯文本编写 · {max(1, len(normalized_body))}字"
    )
    normalized_processing_mode = normalize_knowledge_processing_mode(processing_mode, skip_ai_processing)
    processed_content = build_knowledge_processing_result(
        normalized_body,
        processing_mode=normalized_processing_mode,
        source_type=normalized_type,
        title=normalized_title,
        source_detail=normalized_source_detail,
    )
    processed_summary = str(processed_content.get("summary") or normalized_summary).strip() or normalized_summary
    processed_body = str(processed_content.get("rendered_text") or normalized_body).strip() or normalized_body
    embedding_cfg = get_voice_embedding_config()
    if job_code:
        report_user_async_job_progress(
            job_code,
            stage="knowledge_processing",
            percent=60,
            summary="知识内容已整理，正在生成向量",
            log_text="知识加工已完成，开始写入向量表示和知识库记录。",
        )
    embedding, embedding_engine, embedding_model = build_text_embedding(
        f"{normalized_title}\n\n{processed_summary}\n\n{processed_body}",
        engine=embedding_cfg.get("engine", "api"),
        feature_code="knowledge_embedding",
        feature_label="知识向量入库",
        tenant_slug=tenant_slug,
        entry_point=normalized_type,
        metadata={
            "knowledge_type": normalized_type,
            "processing_mode": normalized_processing_mode,
        },
    )
    vector_namespace = build_vector_namespace(embedding_engine, embedding_model)
    next_id = str(knowledge_id or f"kb-{normalized_type}-{int(time.time() * 1000)}").strip()
    normalized_tags = [str(tag).strip() for tag in (tags if isinstance(tags, list) else []) if str(tag).strip()][:8]
    if not normalized_tags:
        normalized_tags = (
            ["语音纪要", "方法框架"] if normalized_type == "voice"
            else ["PDF", "框架资料"] if normalized_type == "file"
            else ["网页资料", "外部来源"] if normalized_type == "url"
            else ["手动编写", "观点沉淀"]
        )
    normalized_files = [str(name).strip() for name in (files if isinstance(files, list) else []) if str(name).strip()][:12]
    vector_record = _store_knowledge_embedding_record(
        tenant_slug=tenant_slug,
        knowledge_id=next_id,
        knowledge_type=normalized_type,
        title=normalized_title,
        summary=processed_summary,
        body_text=processed_body,
        source_detail=normalized_source_detail,
        vector_namespace=vector_namespace,
        embedding=embedding,
        embedding_engine=embedding_engine,
        embedding_model=embedding_model,
        metadata={
            "notes": str(notes or "").strip(),
            "source": normalized_source_label,
            "skip_ai_processing": normalized_processing_mode == "none",
            "processing_mode": normalized_processing_mode,
            "files": normalized_files,
            "url": str(source_url or "").strip(),
            "voice_minutes": int(voice_minutes or 0) if normalized_type == "voice" else None,
        },
    )
    current_hub = resolve_tenant_knowledge_hub(tenant, tenant.get("knowledge_hub_config"))
    items = copy.deepcopy(current_hub.get("items") or [])
    entry = {
        "id": next_id,
        "type": normalized_type,
        "title": normalized_title,
        "source": normalized_source_label,
        "source_detail": normalized_source_detail,
        "status": "已同步 Hermes",
        "summary": processed_summary,
        "tags": normalized_tags,
        "raw_input": normalized_body,
        "raw_html": str(raw_html or "").strip(),
        "key_points": [str(point).strip() for point in (processed_content.get("key_points") if isinstance(processed_content.get("key_points"), list) else []) if str(point).strip()][:8] or ["待补充关键要点"],
        "validation_nodes": [str(point).strip() for point in (processed_content.get("validation_nodes") if isinstance(processed_content.get("validation_nodes"), list) else []) if str(point).strip()][:8] or ["待补充验证节点"],
        "sync_targets": ["租户知识队列", "知识专区", "Hermes 上下文", "向量知识库"],
        "tuning_focus": ["补充摘要", "补充验证节点", "继续细化表达"],
        "notes": str(notes or "知识已入库，可继续补充结构化要点。").strip(),
        "notes_html": str(notes_html or "").strip(),
        "files": normalized_files,
        "url": str(source_url or "").strip(),
        "skip_ai_processing": normalized_processing_mode == "none",
        "processing_mode": normalized_processing_mode,
        "voice_minutes": int(voice_minutes or 0) if normalized_type == "voice" else None,
        "parse_meta": copy.deepcopy(parse_meta) if isinstance(parse_meta, (dict, list)) else None,
        "processed_content": processed_content,
        "body": processed_body,
        "vector_record": vector_record,
        "queued_at": str(vector_record.get("created_at") or now_ts()).strip(),
        "synced_at": str(vector_record.get("created_at") or now_ts()).strip(),
        "failed_at": "",
    }
    entry["sync_status"] = build_knowledge_sync_status(
        entry.get("status"),
        entry.get("sync_targets"),
        queued_at=entry.get("queued_at"),
        synced_at=entry.get("synced_at"),
        failed_at=entry.get("failed_at"),
    )
    replaced = False
    for index, item in enumerate(items):
        if str(item.get("id") or "") == next_id:
            items[index] = entry
            replaced = True
            break
    if not replaced:
        items.insert(0, entry)
    saved = update_tenant_knowledge_hub_config(tenant_slug, {
        "summary": current_hub.get("summary") or "",
        "items": items,
    })
    latest_tenant = get_tenant_by_slug(tenant_slug, saved) if saved else tenant
    latest_hub = resolve_tenant_knowledge_hub(latest_tenant, latest_tenant.get("knowledge_hub_config"))
    return {
        "entry": entry,
        "knowledge_hub": latest_hub,
        "vector_record": vector_record,
        "embedding_engine": embedding_engine,
        "embedding_model": embedding_model,
    }


def _build_live_knowledge_entry_from_record(record, config_item=None):
    config_item = config_item if isinstance(config_item, dict) else {}
    item_type = str(record.get("knowledge_type") or config_item.get("type") or "manual").strip().lower()
    if item_type not in {"voice", "file", "url", "manual"}:
        item_type = "manual"
    metadata = record.get("metadata_json") if isinstance(record.get("metadata_json"), dict) else {}
    summary_text = str(record.get("summary") or config_item.get("summary") or "").strip()
    body_text = str(record.get("body_text") or config_item.get("body") or config_item.get("raw_input") or summary_text).strip()
    processing_mode = normalize_knowledge_processing_mode(
        config_item.get("processing_mode"),
        metadata.get("skip_ai_processing", config_item.get("skip_ai_processing", True)),
    )
    processed_content = config_item.get("processed_content") if isinstance(config_item.get("processed_content"), dict) else None
    if not processed_content:
        processed_content = build_knowledge_processing_result(
            body_text or str(config_item.get("raw_input") or "").strip(),
            processing_mode=processing_mode,
            source_type=item_type,
            title=str(record.get("title") or config_item.get("title") or "知识内容").strip(),
            source_detail=str(record.get("source_detail") or config_item.get("source_detail") or "").strip(),
        )
    source_text = str(
        config_item.get("source")
        or metadata.get("source")
        or ("纯文本编写" if item_type == "manual" else record.get("title") or "知识内容")
    ).strip()
    notes_text = str(config_item.get("notes") or metadata.get("notes") or "知识已进入向量库，可继续补充结构化信息。").strip()
    title_text = str(record.get("title") or config_item.get("title") or "知识内容").strip() or "知识内容"
    created_at = record.get("created_at")
    queued_at = str(config_item.get("queued_at") or (created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created_at, "strftime") else str(created_at or ""))).strip()
    synced_at = str(config_item.get("synced_at") or (created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created_at, "strftime") else str(created_at or ""))).strip()
    failed_at = str(config_item.get("failed_at") or "").strip()
    return {
        "id": str(record.get("knowledge_id") or config_item.get("id") or "").strip() or f"kb-live-{record.get('id')}",
        "type": item_type,
        "title": title_text,
        "source": source_text,
        "source_detail": str(record.get("source_detail") or config_item.get("source_detail") or "").strip(),
        "status": str(config_item.get("status") or "已同步 Hermes").strip() or "已同步 Hermes",
        "summary": summary_text,
        "tags": [str(tag).strip() for tag in (config_item.get("tags") if isinstance(config_item.get("tags"), list) else []) if str(tag).strip()][:8] or (
            ["手动编写", "观点沉淀"] if item_type == "manual" else [item_type.upper(), "已入向量库"]
        ),
        "raw_input": str(config_item.get("raw_input") or body_text).strip(),
        "raw_html": str(config_item.get("raw_html") or "").strip(),
        "key_points": [str(point).strip() for point in (config_item.get("key_points") if isinstance(config_item.get("key_points"), list) else []) if str(point).strip()][:8]
            or [segment.strip() for segment in re.split(r"[。；;\n]+", summary_text) if segment.strip()][:3]
            or ["待补充关键要点"],
        "validation_nodes": [str(point).strip() for point in (config_item.get("validation_nodes") if isinstance(config_item.get("validation_nodes"), list) else []) if str(point).strip()][:8]
            or ["待补充验证节点"],
        "sync_targets": [str(point).strip() for point in (config_item.get("sync_targets") if isinstance(config_item.get("sync_targets"), list) else []) if str(point).strip()][:8]
            or ["租户知识队列", "知识专区", "Hermes 上下文", "向量知识库"],
        "tuning_focus": [str(point).strip() for point in (config_item.get("tuning_focus") if isinstance(config_item.get("tuning_focus"), list) else []) if str(point).strip()][:8]
            or ["补充摘要", "补充验证节点", "继续细化表达"],
        "notes": notes_text,
        "notes_html": str(config_item.get("notes_html") or "").strip(),
        "files": [str(name).strip() for name in (config_item.get("files") if isinstance(config_item.get("files"), list) else []) if str(name).strip()][:12],
        "url": str(config_item.get("url") or "").strip(),
        "skip_ai_processing": processing_mode == "none",
        "processing_mode": processing_mode,
        "voice_minutes": config_item.get("voice_minutes") if isinstance(config_item.get("voice_minutes"), int) else None,
        "parse_meta": copy.deepcopy(config_item.get("parse_meta")) if isinstance(config_item.get("parse_meta"), (dict, list)) else None,
        "processed_content": copy.deepcopy(processed_content) if isinstance(processed_content, dict) else None,
        "sync_status": build_knowledge_sync_status(
            config_item.get("status") or "已同步 Hermes",
            config_item.get("sync_targets") if isinstance(config_item.get("sync_targets"), list) else None,
            queued_at=queued_at,
            synced_at=synced_at,
            failed_at=failed_at,
        ),
        "queued_at": queued_at,
        "synced_at": synced_at,
        "failed_at": failed_at,
        "body": body_text,
        "time": created_at.strftime("%Y-%m-%d %H:%M") if hasattr(created_at, "strftime") else str(created_at or ""),
        "vector_record": {
            "id": int(record.get("id") or 0),
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or ""),
            "vector_namespace": str(record.get("vector_namespace") or "").strip(),
            "embedding_engine": str(record.get("embedding_engine") or "").strip(),
            "embedding_model": str(record.get("embedding_model") or "").strip(),
            "storage_mode": "pgvector" if str(record.get("vector_namespace") or "").strip() else "jsonb",
        },
    }


def fetch_live_knowledge_hub(tenant, limit=80):
    config_hub = resolve_tenant_knowledge_hub(tenant, tenant.get("knowledge_hub_config"))
    config_items = {
        str(item.get("id") or "").strip(): item
        for item in (config_hub.get("items") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    try:
        with get_review_vector_db_connection() as conn:
            _ensure_knowledge_embedding_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, knowledge_id, knowledge_type, title, summary, body_text, source_detail,
                           vector_namespace, embedding_engine, embedding_model, metadata_json, created_at
                    FROM (
                        SELECT DISTINCT ON (knowledge_id)
                            id, knowledge_id, knowledge_type, title, summary, body_text, source_detail,
                            vector_namespace, embedding_engine, embedding_model, metadata_json, created_at
                        FROM knowledge_embeddings
                        WHERE tenant_slug = %s
                        ORDER BY knowledge_id, created_at DESC, id DESC
                    ) latest
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (tenant.get("slug"), max(1, int(limit or 80))),
                )
                rows = cur.fetchall()
    except Exception:
        exc = None
        try:
            raise
        except Exception as error:
            exc = error
        if exc is not None and is_db_unavailable_error(exc):
            app.logger.warning("Vector database unavailable while loading live knowledge hub, using config fallback")
        else:
            app.logger.exception("Failed to load live knowledge hub from vector database")
        return config_hub
    if not rows:
        return config_hub
    items = []
    for row in rows:
        record = {
            "id": row[0],
            "knowledge_id": row[1],
            "knowledge_type": row[2],
            "title": row[3],
            "summary": row[4],
            "body_text": row[5],
            "source_detail": row[6],
            "vector_namespace": row[7],
            "embedding_engine": row[8],
            "embedding_model": row[9],
            "metadata_json": row[10],
            "created_at": row[11],
        }
        items.append(_build_live_knowledge_entry_from_record(record, config_items.get(str(row[1] or "").strip())))
    return {
        "summary": config_hub.get("summary") or "知识库支持语音、文件、URL 和纯文本四种入口。",
        "items": items,
    }


def list_admin_knowledge_items(tenant_slug="", limit=120):
    site_config = get_site_config()
    tenants = get_tenant_configs(site_config)
    target_slug = str(tenant_slug or "").strip().lower()
    selected_tenants = [tenant for tenant in tenants if not target_slug or tenant.get("slug") == target_slug]
    results = []
    for tenant in selected_tenants:
        hub = fetch_live_knowledge_hub(tenant, limit=limit)
        for item in hub.get("items") or []:
            if not isinstance(item, dict):
                continue
            row = copy.deepcopy(item)
            row["tenant_slug"] = tenant.get("slug") or ""
            row["tenant_name"] = tenant.get("name") or tenant.get("slug") or ""
            results.append(row)
    results.sort(key=lambda item: str(item.get("time") or item.get("vector_record", {}).get("created_at") or ""), reverse=True)
    return results[:max(1, int(limit or 120))]


def _cosine_similarity(vec_a, vec_b):
    if not isinstance(vec_a, list) or not isinstance(vec_b, list) or not vec_a or not vec_b:
        return 0.0
    size = min(len(vec_a), len(vec_b))
    if size <= 0:
        return 0.0
    dot = sum(float(vec_a[i]) * float(vec_b[i]) for i in range(size))
    norm_a = math.sqrt(sum(float(vec_a[i]) * float(vec_a[i]) for i in range(size)))
    norm_b = math.sqrt(sum(float(vec_b[i]) * float(vec_b[i]) for i in range(size)))
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (norm_a * norm_b)


def search_knowledge_embeddings(tenant_slug, query_text, limit=5):
    normalized_query = str(query_text or "").strip()
    if not normalized_query:
        raise ValueError("knowledge_query_required")
    embedding_cfg = get_voice_embedding_config()
    query_embedding, embedding_engine, embedding_model = build_text_embedding(
        normalized_query,
        engine=embedding_cfg.get("engine", "local"),
        feature_code="knowledge_query_embedding",
        feature_label="知识检索向量查询",
        tenant_slug=tenant_slug,
        entry_point="knowledge_query",
        metadata={"query_length": len(normalized_query)},
    )
    with get_review_vector_db_connection() as conn:
        _ensure_knowledge_embedding_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, knowledge_id, knowledge_type, title, summary, body_text, source_detail,
                       vector_namespace, embedding_engine, embedding_model, embedding_json, metadata_json, created_at
                FROM (
                    SELECT DISTINCT ON (knowledge_id)
                        id, knowledge_id, knowledge_type, title, summary, body_text, source_detail,
                        vector_namespace, embedding_engine, embedding_model, embedding_json, metadata_json, created_at
                    FROM knowledge_embeddings
                    WHERE tenant_slug = %s
                    ORDER BY knowledge_id, created_at DESC, id DESC
                ) latest
                ORDER BY created_at DESC, id DESC
                LIMIT 120
                """,
                (str(tenant_slug or "").strip(),),
            )
            rows = cur.fetchall()
    if not rows:
        return {
            "query": normalized_query,
            "answer": "当前知识库里还没有可检索的真实知识，请先完成至少一条知识入库。",
            "matches": [],
            "embedding_engine": embedding_engine,
            "embedding_model": embedding_model,
        }
    tenant = get_tenant_by_slug(tenant_slug)
    config_hub = resolve_tenant_knowledge_hub(tenant, tenant.get("knowledge_hub_config")) if tenant else {"items": []}
    config_items = {
        str(item.get("id") or "").strip(): item
        for item in (config_hub.get("items") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    scored = []
    for row in rows:
        stored_embedding = row[10] if isinstance(row[10], list) else []
        score = _cosine_similarity(query_embedding, stored_embedding)
        record = {
            "id": row[0],
            "knowledge_id": row[1],
            "knowledge_type": row[2],
            "title": row[3],
            "summary": row[4],
            "body_text": row[5],
            "source_detail": row[6],
            "vector_namespace": row[7],
            "embedding_engine": row[8],
            "embedding_model": row[9],
            "metadata_json": row[11],
            "created_at": row[12],
        }
        entry = _build_live_knowledge_entry_from_record(record, config_items.get(str(row[1] or "").strip()))
        entry["score"] = round(float(score), 4)
        scored.append(entry)
    scored.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    matches = scored[: max(1, int(limit or 5))]
    if matches:
        answer_lines = [
            f"已命中 {len(matches)} 条知识，最相关的是《{matches[0].get('title') or '未命名知识'}》。",
            f"核心摘要：{matches[0].get('summary') or matches[0].get('body') or '暂无摘要'}",
        ]
        for index, item in enumerate(matches[1:3], start=2):
            answer_lines.append(f"补充命中 {index}：{item.get('title') or '未命名知识'}，相关度 {item.get('score', 0)}。")
        answer = "\n".join(answer_lines)
    else:
        answer = "当前没有找到足够相关的知识条目。"
    return {
        "query": normalized_query,
        "answer": answer,
        "matches": matches,
        "embedding_engine": embedding_engine,
        "embedding_model": embedding_model,
    }


def build_knowledge_chat_prompts(query_text, matches, tenant_slug=""):
    query = str(query_text or "").strip()
    tenant = get_tenant_by_slug(tenant_slug)
    tenant_name = (tenant or {}).get("name") or (tenant or {}).get("short_name") or str(tenant_slug or "").strip() or "当前租户"
    context_blocks = []
    for index, item in enumerate(matches[:5], start=1):
        if not isinstance(item, dict):
            continue
        context_blocks.append(
            "\n".join([
                f"[知识 {index}] 标题：{str(item.get('title') or '未命名知识').strip()}",
                f"[知识 {index}] 摘要：{str(item.get('summary') or item.get('body') or item.get('raw_input') or '暂无摘要').strip()}",
                f"[知识 {index}] 原文：{str(item.get('body') or item.get('raw_input') or item.get('summary') or '').strip()}",
                f"[知识 {index}] 来源：{str(item.get('source_detail') or item.get('source') or '').strip()}",
                f"[知识 {index}] 相关度：{item.get('score', 0)}",
            ])
        )
    context_text = "\n\n".join(block for block in context_blocks if block.strip())
    system_prompt = (
        f"你是{tenant_name}的大V知识库助手。"
        "你的任务是基于召回到的知识条目回答问题。"
        "必须优先依据给定知识，不要编造未提供的事实。"
        "如果知识不足以完整回答，要明确指出边界。"
        "回答请使用中文，风格简洁、专业、适合大V内容生产和研究复盘。"
    )
    user_prompt = (
        f"用户问题：{query}\n\n"
        f"知识库召回结果：\n{context_text or '当前没有召回到有效知识。'}\n\n"
        "请输出：\n"
        "1. 直接回答用户问题\n"
        "2. 提炼2到4条关键依据\n"
        "3. 如果存在知识空白，补一句“知识边界”"
    )
    return system_prompt, user_prompt


def normalize_evidence_source_types(source_types=None):
    allowed = {"knowledge"}
    raw_items = []
    if isinstance(source_types, (list, tuple, set)):
        raw_items = list(source_types)
    elif source_types not in (None, ""):
        raw_items = re.split(r"[,\s]+", str(source_types))
    normalized = []
    for item in raw_items:
        value = slugify_code(item, "")
        if value in allowed and value not in normalized:
            normalized.append(value)
    return normalized or ["knowledge"]


def _build_evidence_retrieval_answer(evidence_items):
    items = [item for item in (evidence_items if isinstance(evidence_items, list) else []) if isinstance(item, dict)]
    if not items:
        return "当前没有找到足够相关的证据条目。"
    answer_lines = [
        f"已命中 {len(items)} 条证据，最相关的是《{items[0].get('title') or '未命名条目'}》。",
        f"核心摘要：{items[0].get('summary') or items[0].get('body') or items[0].get('raw_input') or '暂无摘要'}",
    ]
    for index, item in enumerate(items[1:3], start=2):
        answer_lines.append(
            f"补充命中 {index}：{item.get('title') or '未命名条目'}，相关度 {item.get('score', 0)}。"
        )
    return "\n".join(answer_lines)


def build_evidence_chain_chat_prompts(query_text, evidence_items, tenant_slug=""):
    query = str(query_text or "").strip()
    tenant = get_tenant_by_slug(tenant_slug)
    tenant_name = (tenant or {}).get("name") or (tenant or {}).get("short_name") or str(tenant_slug or "").strip() or "当前租户"
    context_blocks = []
    for index, item in enumerate((evidence_items if isinstance(evidence_items, list) else [])[:6], start=1):
        if not isinstance(item, dict):
            continue
        context_blocks.append(
            "\n".join([
                f"[证据 {index}] 类型：{str(item.get('source_label') or item.get('source_type') or '未知来源').strip()}",
                f"[证据 {index}] 标题：{str(item.get('title') or '未命名证据').strip()}",
                f"[证据 {index}] 摘要：{str(item.get('summary') or item.get('body') or item.get('raw_input') or '暂无摘要').strip()}",
                f"[证据 {index}] 原文：{str(item.get('body') or item.get('raw_input') or item.get('summary') or '').strip()}",
                f"[证据 {index}] 来源：{str(item.get('source_detail') or item.get('source') or '').strip()}",
                f"[证据 {index}] 相关度：{item.get('score', 0)}",
            ])
        )
    context_text = "\n\n".join(block for block in context_blocks if block.strip())
    system_prompt = (
        f"你是{tenant_name}的证据链助手。"
        "你的任务是基于召回到的证据条目回答问题。"
        "必须优先依据给定证据，不要编造未提供的事实。"
        "如果证据不足以完整回答，要明确指出边界。"
        "回答请使用中文，风格简洁、专业，适合研究、复盘、Dashboard 和证据链归因场景。"
    )
    user_prompt = (
        f"用户问题：{query}\n\n"
        f"证据链召回结果：\n{context_text or '当前没有召回到有效证据。'}\n\n"
        "请输出：\n"
        "1. 直接回答用户问题\n"
        "2. 提炼2到4条关键依据\n"
        "3. 如果存在证据空白，补一句“证据边界”"
    )
    return system_prompt, user_prompt


def search_evidence_chain(tenant_slug, query_text, limit=5, source_types=None):
    normalized_query = str(query_text or "").strip()
    if not normalized_query:
        raise ValueError("evidence_query_required")
    normalized_sources = normalize_evidence_source_types(source_types)
    evidence_items = []
    source_summaries = []
    unsupported_sources = []
    for source_type in normalized_sources:
        if source_type == "knowledge":
            result = search_knowledge_embeddings(tenant_slug=tenant_slug, query_text=normalized_query, limit=limit)
            items = []
            for item in (result.get("matches") or []):
                if not isinstance(item, dict):
                    continue
                evidence_item = copy.deepcopy(item)
                evidence_item["source_type"] = "knowledge"
                evidence_item["source_label"] = "知识库"
                evidence_item["evidence_id"] = str(item.get("id") or item.get("knowledge_id") or "").strip()
                items.append(evidence_item)
            evidence_items.extend(items)
            source_summaries.append({
                "source_type": "knowledge",
                "source_label": "知识库",
                "request_count": len(items),
            })
        else:
            unsupported_sources.append(source_type)
    evidence_items.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    evidence_items = evidence_items[: max(1, int(limit or 5))]
    return {
        "query": normalized_query,
        "answer": _build_evidence_retrieval_answer(evidence_items),
        "evidence_items": evidence_items,
        "matches": copy.deepcopy(evidence_items),
        "source_types": normalized_sources,
        "source_summaries": source_summaries,
        "unsupported_source_types": unsupported_sources,
    }


def _extract_json_payload_from_llm_text(text, default):
    normalized = str(text or "").strip()
    if not normalized:
        return copy.deepcopy(default)
    candidates = [normalized]
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", normalized, flags=re.S)
    if fence_match:
        candidates.insert(0, fence_match.group(1).strip())
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, type(default)):
            return parsed
    return copy.deepcopy(default)


def filter_knowledge_matches_with_llm(query_text, matches, tenant_slug=""):
    normalized_query = str(query_text or "").strip()
    normalized_matches = [copy.deepcopy(item) for item in (matches if isinstance(matches, list) else []) if isinstance(item, dict)]
    if not normalized_query or not normalized_matches:
        return normalized_matches, {
            "filtered": False,
            "kept_count": len(normalized_matches),
            "dropped_count": 0,
            "reason": "no_matches_or_query",
        }, None
    llm_model = get_default_llm_config(purpose="general")
    if not llm_model:
        return normalized_matches, {
            "filtered": False,
            "kept_count": len(normalized_matches),
            "dropped_count": 0,
            "reason": "llm_unavailable",
        }, None
    candidate_blocks = []
    for index, item in enumerate(normalized_matches, start=1):
        candidate_blocks.append(
            "\n".join([
                f"候选ID：{str(item.get('id') or '').strip() or f'match_{index}'}",
                f"标题：{str(item.get('title') or '未命名知识').strip()}",
                f"摘要：{str(item.get('summary') or item.get('body') or item.get('raw_input') or '暂无摘要').strip()[:500]}",
                f"原文片段：{str(item.get('body') or item.get('raw_input') or item.get('summary') or '').strip()[:700]}",
                f"来源：{str(item.get('source_detail') or item.get('source') or '').strip()}",
                f"向量相关度：{item.get('score', 0)}",
            ])
        )
    evidence_chain_cfg = get_evidence_chain_config()
    system_prompt = evidence_chain_cfg.get("filter_prompt_system") or DEFAULT_SITE_CONFIG["evidence_chain"]["filter_prompt_system"]
    user_prompt_template = evidence_chain_cfg.get("filter_prompt_user_template") or DEFAULT_SITE_CONFIG["evidence_chain"]["filter_prompt_user_template"]
    user_prompt = (
        str(user_prompt_template)
        .replace("{query}", normalized_query)
        .replace("{candidate_blocks}", chr(10).join(candidate_blocks))
    )
    raw = call_openai_compatible_llm(
        llm_model,
        system_prompt,
        user_prompt,
        feature_code="knowledge_query_filter",
        feature_label="知识检索相关性过滤",
        tenant_slug=tenant_slug,
        entry_point="knowledge_query",
        metadata={"candidate_count": len(normalized_matches), "query_length": len(normalized_query)},
        request_timeout_seconds=evidence_chain_cfg.get("filter_timeout_seconds", 25),
    )
    parsed = _extract_json_payload_from_llm_text(raw, {"relevant_ids": [], "reason": ""})
    relevant_ids = {
        str(item).strip()
        for item in (parsed.get("relevant_ids") if isinstance(parsed.get("relevant_ids"), list) else [])
        if str(item).strip()
    }
    filtered_matches = [item for item in normalized_matches if str(item.get("id") or "").strip() in relevant_ids]
    filter_meta = {
        "filtered": True,
        "kept_count": len(filtered_matches),
        "dropped_count": max(0, len(normalized_matches) - len(filtered_matches)),
        "reason": str(parsed.get("reason") or "").strip()[:240],
    }
    return filtered_matches, filter_meta, llm_model


def build_evidence_chain_response(
    tenant_slug,
    query_text,
    limit=5,
    submit_to_model=False,
    source_types=None,
    entry_point="evidence_chain",
    feature_namespace="evidence_chain",
):
    result = search_evidence_chain(
        tenant_slug=tenant_slug,
        query_text=query_text,
        limit=limit,
        source_types=source_types,
    )
    llm_requested = bool(submit_to_model)
    llm_enabled = False
    llm_mode = "retrieval_only"
    llm_model = None
    llm_notice = "当前为纯知识检索模式，未提交给大模型。"
    if llm_requested:
        llm_model = get_default_llm_config(purpose="general")
        if llm_model:
            original_matches = result.get("evidence_items") or []
            try:
                filtered_matches, filter_meta, filter_model = filter_knowledge_matches_with_llm(
                    query_text=result.get("query"),
                    matches=original_matches,
                    tenant_slug=tenant_slug,
                )
                if filter_model:
                    llm_model = filter_model
                result["evidence_items"] = filtered_matches
                result["matches"] = copy.deepcopy(filtered_matches)
                if filter_meta.get("filtered"):
                    llm_notice = (
                        f"已先用通用模型过滤知识召回结果，保留 {filter_meta.get('kept_count', 0)} 条，"
                        f"过滤掉 {filter_meta.get('dropped_count', 0)} 条无关内容。"
                    )
                    if filter_meta.get("reason"):
                        llm_notice = f"{llm_notice} {filter_meta.get('reason')}"
                else:
                    llm_notice = "已勾选提交给大模型，当前未启用额外过滤，直接基于召回结果生成回答。"
            except Exception as exc:
                result["evidence_items"] = original_matches
                result["matches"] = copy.deepcopy(original_matches)
                llm_notice = f"相关性过滤调用失败，已回退到原始召回结果：{str(exc)}"
            filtered_matches = result.get("evidence_items") or []
            if not filtered_matches:
                llm_enabled = True
                llm_mode = "model_filtered_empty"
                result["answer"] = "当前召回结果经过大模型过滤后，没有发现与问题直接相关的知识条目。"
                return {
                    **result,
                    "submit_to_model": llm_requested,
                    "llm_enabled": llm_enabled,
                    "llm_mode": llm_mode,
                    "llm_notice": llm_notice,
                    "llm_model": {
                        "key": llm_model.get("key"),
                        "label": llm_model.get("label"),
                        "provider": llm_model.get("provider"),
                        "model_name": llm_model.get("model_name"),
                        "purpose": llm_model.get("purpose"),
                    } if llm_model else None,
                }
            system_prompt, user_prompt = build_evidence_chain_chat_prompts(
                query_text=result.get("query"),
                evidence_items=filtered_matches,
                tenant_slug=tenant_slug,
            )
            llm_enabled = True
            try:
                llm_answer = call_openai_compatible_llm(
                    llm_model,
                    system_prompt,
                    user_prompt,
                    feature_code=f"{feature_namespace}_answer",
                    feature_label="证据链问答生成",
                    tenant_slug=tenant_slug,
                    entry_point=entry_point,
                    metadata={"match_count": len(filtered_matches), "submit_to_model": True},
                    request_timeout_seconds=get_evidence_chain_config().get("answer_timeout_seconds", 45),
                )
                result["answer"] = llm_answer
                llm_mode = "model_answered"
                llm_notice = (
                    f"{llm_notice}\n\n"
                    f"当前回答已由通用模型生成：{llm_model.get('label') or llm_model.get('model_name') or llm_model.get('key')}。"
                    "下方保留的是过滤后的相关知识命中结果。"
                ).strip()
            except Exception as exc:
                llm_enabled = False
                llm_mode = "fallback_retrieval"
                llm_notice = f"{llm_notice}\n\n已尝试调用通用模型生成回答，但失败并回退到纯知识检索：{str(exc)}".strip()
        else:
            llm_mode = "fallback_retrieval"
            llm_notice = "已勾选提交给大模型，但当前没有可用的通用模型配置，已自动回退到纯知识检索模式。"
    return {
        **result,
        "submit_to_model": llm_requested,
        "llm_enabled": llm_enabled,
        "llm_mode": llm_mode,
        "llm_notice": llm_notice,
        "llm_model": {
            "key": llm_model.get("key"),
            "label": llm_model.get("label"),
            "provider": llm_model.get("provider"),
            "model_name": llm_model.get("model_name"),
            "purpose": llm_model.get("purpose"),
        } if llm_model else None,
    }


def build_knowledge_query_response(tenant_slug, query_text, limit=5, submit_to_model=False):
    result = build_evidence_chain_response(
        tenant_slug=tenant_slug,
        query_text=query_text,
        limit=limit,
        submit_to_model=submit_to_model,
        source_types=["knowledge"],
        entry_point="knowledge_query",
        feature_namespace="knowledge_query",
    )
    result["matches"] = copy.deepcopy(result.get("evidence_items") or [])
    return result


HERMES_QUERY_INTENT_PROMPT = (
    "你是 Hermes 的任务路由器。"
    "你的职责不是直接回答用户，而是把用户问题路由成最合适的任务类型，并决定需要调用哪些工具。"
    "只能从给定枚举里选择 intent 和 tools。"
    "禁止编造工具名。"
    "输出必须是 JSON。"
)

HERMES_ALLOWED_INTENTS = {
    "general_chat",
    "knowledge_lookup",
    "evidence_chain_analysis",
    "watchlist_fundamental",
    "multi_tool_research",
}

HERMES_ALLOWED_TOOLS = {
    "knowledge.search",
    "evidence.search",
    "watchlist.detail",
    "attachment.context",
}


def normalize_hermes_messages(messages):
    normalized = []
    for item in messages if isinstance(messages, list) else []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({
            "role": role,
            "content": content[:4000],
        })
    return normalized


def extract_hermes_question_text(messages, question_text=""):
    for message in reversed(normalize_hermes_messages(messages)):
        if message["role"] == "user" and message["content"]:
            return message["content"]
    return str(question_text or "").strip()


def format_hermes_message_context(messages, limit=8):
    lines = []
    for item in normalize_hermes_messages(messages)[-max(1, int(limit or 8)):]:
        role_label = "用户" if item["role"] == "user" else "Hermes"
        lines.append(f"{role_label}：{item['content']}")
    return "\n".join(lines)


def build_hermes_intent_router_prompt(question_text, has_attachments=False, selected_knowledge_ids=None, messages=None):
    conversation_block = format_hermes_message_context(messages, limit=6)
    conversation_section = f"最近多轮对话：\n{conversation_block}\n\n" if conversation_block else ""
    return (
        "请根据用户问题判断 Hermes 应该如何拆解任务。\n"
        "可选 intent：general_chat, knowledge_lookup, evidence_chain_analysis, watchlist_fundamental, multi_tool_research\n"
        "可选 tools：knowledge.search, evidence.search, watchlist.detail, attachment.context\n"
        "规则：\n"
        "1. 如果用户明确问复盘、证据链、依据、来源，优先考虑 evidence_chain_analysis。\n"
        "2. 如果用户明确问基本面、估值、盈利、行业位置、个股研究，且存在股票名/代码，优先考虑 watchlist_fundamental。\n"
        "3. 如果用户主要想问某条知识、某个框架、方法、纪要内容，优先考虑 knowledge_lookup。\n"
        "4. 如果问题同时涉及个股 + 证据/知识，多工具组合时用 multi_tool_research。\n"
        "5. 如果只是泛化闲聊或方向性提问，用 general_chat。\n"
        "6. 如果有附件，工具里可以包含 attachment.context。\n"
        "7. stock_code 只在能明显识别时输出，否则为空字符串。\n"
        "8. display_mode 只能是 text 或 structured。\n\n"
        f"{conversation_section}"
        f"用户问题：{str(question_text or '').strip()}\n"
        f"是否有附件：{'是' if has_attachments else '否'}\n"
        f"是否指定知识条目：{'是' if selected_knowledge_ids else '否'}\n\n"
        "输出 JSON 结构：\n"
        '{'
        '"intent":"...",'
        '"tools":["..."],'
        '"stock_code":"",'
        '"display_mode":"text",'
        '"reason":"简短中文说明"'
        '}'
    )


def default_hermes_intent_plan(question_text, selected_knowledge_ids=None, attachments=None, preferred_mode=""):
    question = str(question_text or "").strip()
    lowered = question.lower()
    attachments = attachments if isinstance(attachments, list) else []
    selected_knowledge_ids = selected_knowledge_ids if isinstance(selected_knowledge_ids, list) else []
    preferred_mode = str(preferred_mode or "").strip().lower()
    has_attachments = bool(attachments)
    stock_code = ""
    code_match = re.search(r"\b\d{5,6}\b", question)
    if code_match:
        stock_code = code_match.group(0)
    stock_keywords = ["基本面", "估值", "盈利", "财报", "行业位置", "个股", "自选股"]
    evidence_keywords = ["证据链", "证据", "依据", "来源", "纪要", "复盘"]
    knowledge_keywords = ["框架", "方法", "知识", "纪要", "研报"]
    if preferred_mode == "evidence":
        return {
            "intent": "evidence_chain_analysis" if not stock_code else "multi_tool_research",
            "tools": ["evidence.search"] + (["watchlist.detail"] if stock_code else []) + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "display_mode": "structured" if stock_code else "text",
            "reason": "分析方式偏向证据链归因",
        }
    if preferred_mode == "judgement" and stock_code:
        return {
            "intent": "watchlist_fundamental",
            "tools": ["watchlist.detail"] + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "display_mode": "structured",
            "reason": "分析方式偏向基本面判断",
        }
    if any(keyword in lowered for keyword in [item.lower() for item in evidence_keywords]):
        return {
            "intent": "evidence_chain_analysis" if not stock_code else "multi_tool_research",
            "tools": ["evidence.search"] + (["watchlist.detail"] if stock_code else []) + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "display_mode": "structured" if stock_code else "text",
            "reason": "命中复盘或证据链问题",
        }
    if stock_code or any(keyword in lowered for keyword in [item.lower() for item in stock_keywords]):
        return {
            "intent": "watchlist_fundamental" if not selected_knowledge_ids and not has_attachments else "multi_tool_research",
            "tools": ["watchlist.detail"] + (["knowledge.search"] if selected_knowledge_ids else []) + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "display_mode": "structured" if stock_code else "text",
            "reason": "命中个股基本面问题",
        }
    if selected_knowledge_ids or any(keyword in lowered for keyword in [item.lower() for item in knowledge_keywords]):
        return {
            "intent": "knowledge_lookup",
            "tools": ["knowledge.search"] + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "display_mode": "text",
            "reason": "命中知识或方法问题",
        }
    return {
        "intent": "general_chat",
        "tools": ["attachment.context"] if has_attachments else [],
        "stock_code": stock_code,
        "display_mode": "text",
        "reason": "默认通用对话",
    }


def route_hermes_query_intent(question_text, tenant_slug="", selected_knowledge_ids=None, attachments=None, preferred_mode="", messages=None):
    selected_knowledge_ids = selected_knowledge_ids if isinstance(selected_knowledge_ids, list) else []
    attachments = attachments if isinstance(attachments, list) else []
    messages = normalize_hermes_messages(messages)
    fallback = default_hermes_intent_plan(
        question_text=question_text,
        selected_knowledge_ids=selected_knowledge_ids,
        attachments=attachments,
        preferred_mode=preferred_mode,
    )
    llm_model = get_default_llm_config(purpose="general")
    if not llm_model:
        return fallback, None, "fallback_rule_router"
    try:
        raw = call_openai_compatible_llm(
            llm_model,
            HERMES_QUERY_INTENT_PROMPT,
            build_hermes_intent_router_prompt(
                question_text=question_text,
                has_attachments=bool(attachments),
                selected_knowledge_ids=selected_knowledge_ids,
                messages=messages,
            ),
            feature_code="hermes_intent_router",
            feature_label="Hermes 意图路由",
            tenant_slug=tenant_slug,
            entry_point="hermes_query",
            metadata={"attachment_count": len(attachments), "selected_knowledge_count": len(selected_knowledge_ids)},
            request_timeout_seconds=20,
        )
        parsed = _extract_json_payload_from_llm_text(raw, fallback)
        intent = str(parsed.get("intent") or fallback["intent"]).strip()
        if intent not in HERMES_ALLOWED_INTENTS:
            intent = fallback["intent"]
        raw_tools = parsed.get("tools") if isinstance(parsed.get("tools"), list) else fallback["tools"]
        tools = []
        for tool in raw_tools:
            value = str(tool or "").strip()
            if value in HERMES_ALLOWED_TOOLS and value not in tools:
                tools.append(value)
        if not tools:
            tools = fallback["tools"]
        stock_code = find_watchlist_code_from_text(str(parsed.get("stock_code") or "").strip()) or fallback["stock_code"]
        display_mode = str(parsed.get("display_mode") or fallback["display_mode"]).strip()
        if display_mode not in {"text", "structured"}:
            display_mode = fallback["display_mode"]
        return {
            "intent": intent,
            "tools": tools[:4],
            "stock_code": stock_code,
            "display_mode": display_mode,
            "reason": str(parsed.get("reason") or fallback["reason"]).strip()[:200] or fallback["reason"],
        }, llm_model, "llm_router"
    except Exception:
        app.logger.exception("Failed to route Hermes query intent")
        return fallback, llm_model, "fallback_rule_router"


def trim_hermes_text(value, limit=180):
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return f"{text[:max(0, limit - 1)]}…"


def find_watchlist_code_from_text(text):
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    details = gen_watchlist_details()
    code_match = re.search(r"\b\d{5,6}\b", normalized)
    if code_match:
        code = code_match.group(0)
        return code if code in details else code
    for code, detail in details.items():
        name = str((detail or {}).get("name") or "").strip()
        if name and name in normalized:
            return code
    return ""


def hermes_tool_attachment_context(attachments):
    items = []
    for index, item in enumerate(attachments if isinstance(attachments, list) else [], start=1):
        if not isinstance(item, dict):
            continue
        items.append({
            "id": index,
            "filename": str(item.get("filename") or "").strip(),
            "summary": str(item.get("summary") or "").strip(),
            "body": str(item.get("body") or "").strip()[:4000],
        })
    return {
        "count": len(items),
        "items": items,
    }


def hermes_tool_knowledge_search(tenant_slug, question_text, selected_knowledge_ids=None, limit=4):
    selected_knowledge_ids = selected_knowledge_ids if isinstance(selected_knowledge_ids, list) else []
    if selected_knowledge_ids:
        entries = []
        for entry_id in selected_knowledge_ids[:5]:
            entry = get_knowledge_entry_for_tenant(tenant_slug, entry_id)
            if entry:
                entries.append(entry)
        return {
            "mode": "selected_entries",
            "matches": entries,
            "answer": f"当前限定到 {len(entries)} 条指定知识。",
        }
    result = build_knowledge_query_response(
        tenant_slug=tenant_slug,
        query_text=question_text,
        limit=limit,
        submit_to_model=False,
    )
    return {
        "mode": "retrieval",
        "matches": copy.deepcopy(result.get("matches") or []),
        "answer": result.get("answer") or "",
        "llm_notice": result.get("llm_notice") or "",
    }


def get_knowledge_entry_for_tenant(tenant_slug, entry_id):
    tenant = get_tenant_by_slug(tenant_slug)
    tenant_id = str((tenant or {}).get("id") or "").strip()
    hub_items = list_admin_knowledge_items(tenant_slug=tenant_slug, limit=300)
    for item in hub_items:
        normalized_id = str(item.get("id") or item.get("knowledge_id") or "").strip()
        if normalized_id == str(entry_id or "").strip():
            return {
                "id": normalized_id,
                "title": str(item.get("title") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
                "body": str(item.get("body") or item.get("raw_input") or "").strip(),
                "source": str(item.get("source_detail") or item.get("source") or "").strip(),
                "tenant_id": tenant_id,
            }
    return None


def hermes_tool_evidence_search(tenant_slug, question_text, limit=4):
    result = build_evidence_chain_response(
        tenant_slug=tenant_slug,
        query_text=question_text,
        limit=limit,
        submit_to_model=False,
        source_types=["knowledge"],
        entry_point="hermes_query",
        feature_namespace="hermes_evidence",
    )
    return {
        "matches": copy.deepcopy(result.get("evidence_items") or []),
        "answer": result.get("answer") or "",
        "llm_notice": result.get("llm_notice") or "",
    }


def hermes_tool_watchlist_detail(stock_code):
    if not str(stock_code or "").strip():
        return {"found": False, "detail": None}
    site_config = get_site_config()
    details = gen_watchlist_details()
    payload = details.get(stock_code)
    if not payload:
        return {"found": False, "detail": None}
    return {
        "found": True,
        "detail": apply_watchlist_feature_flags(copy.deepcopy(payload), site_config),
    }


def get_hermes_tool_registry():
    return {
        "attachment.context": {
            "output_key": "attachment_context",
            "executor": lambda runtime: hermes_tool_attachment_context(runtime.get("attachments")),
        },
        "knowledge.search": {
            "output_key": "knowledge",
            "executor": lambda runtime: hermes_tool_knowledge_search(
                tenant_slug=runtime.get("tenant_slug") or "",
                question_text=runtime.get("question_text") or "",
                selected_knowledge_ids=runtime.get("selected_knowledge_ids") or [],
            ),
        },
        "evidence.search": {
            "output_key": "evidence",
            "executor": lambda runtime: hermes_tool_evidence_search(
                tenant_slug=runtime.get("tenant_slug") or "",
                question_text=runtime.get("question_text") or "",
            ),
        },
        "watchlist.detail": {
            "output_key": "watchlist",
            "executor": lambda runtime: hermes_tool_watchlist_detail(runtime.get("stock_code")),
        },
    }


def execute_hermes_tool_plan(plan, tenant_slug, question_text, selected_knowledge_ids=None, attachments=None):
    selected_knowledge_ids = selected_knowledge_ids if isinstance(selected_knowledge_ids, list) else []
    attachments = attachments if isinstance(attachments, list) else []
    outputs = {}
    trace = []
    registry = get_hermes_tool_registry()
    runtime = {
        "tenant_slug": tenant_slug,
        "question_text": question_text,
        "selected_knowledge_ids": selected_knowledge_ids,
        "attachments": attachments,
        "stock_code": str(plan.get("stock_code") or "").strip(),
    }
    for tool_name in plan.get("tools") or []:
        started_at = time.time()
        tool_spec = registry.get(tool_name)
        if not tool_spec:
            trace.append({
                "tool": tool_name,
                "status": "skipped",
                "elapsed_ms": int((time.time() - started_at) * 1000),
                "error": "tool_not_registered",
            })
            continue
        try:
            output_key = str(tool_spec.get("output_key") or tool_name.replace(".", "_")).strip()
            outputs[output_key] = tool_spec["executor"](runtime)
            trace.append({
                "tool": tool_name,
                "status": "ok",
                "elapsed_ms": int((time.time() - started_at) * 1000),
            })
        except Exception as exc:
            trace.append({
                "tool": tool_name,
                "status": "error",
                "elapsed_ms": int((time.time() - started_at) * 1000),
                "error": str(exc)[:200],
            })
            app.logger.exception("Hermes tool execution failed: %s", tool_name)
    return outputs, trace


def build_hermes_citations(tool_outputs):
    citations = []
    watchlist_detail = ((tool_outputs.get("watchlist") or {}).get("detail") or {}) if isinstance(tool_outputs, dict) else {}
    if watchlist_detail:
        name = str(watchlist_detail.get("name") or "").strip()
        code = str(watchlist_detail.get("code") or "").strip()
        market = str(watchlist_detail.get("market") or "").strip()
        label = " ".join(item for item in [name, code, market] if item).strip()
        if label:
            citations.append(label)
    knowledge_matches = ((tool_outputs.get("knowledge") or {}).get("matches") or []) if isinstance(tool_outputs, dict) else []
    for item in knowledge_matches[:4]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if title and title not in citations:
            citations.append(title)
    evidence_matches = ((tool_outputs.get("evidence") or {}).get("matches") or []) if isinstance(tool_outputs, dict) else []
    for item in evidence_matches[:4]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if title and title not in citations:
            citations.append(title)
    attachment_items = ((tool_outputs.get("attachment_context") or {}).get("items") or []) if isinstance(tool_outputs, dict) else []
    for item in attachment_items[:3]:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip()
        if filename and filename not in citations:
            citations.append(filename)
    return citations[:8]


def build_hermes_followups(plan, tool_outputs):
    intent = str((plan or {}).get("intent") or "").strip()
    watchlist_detail = (((tool_outputs or {}).get("watchlist") or {}).get("detail") or {}) if isinstance(tool_outputs, dict) else {}
    stock_name = str(watchlist_detail.get("name") or watchlist_detail.get("code") or "这个对象").strip()
    suggestions = []
    if intent in {"watchlist_fundamental", "multi_tool_research"} and stock_name:
        suggestions = [
            f"继续追问 {stock_name} 的盈利、估值和行业位置如何互相印证。",
            f"如果你要做复盘，可以让我把 {stock_name} 的证据链拆开重写。",
            f"也可以继续补充一个新变量，我再判断 {stock_name} 是否需要更新结论。",
        ]
    elif intent == "knowledge_lookup":
        suggestions = [
            "如果你要把这条知识落到场景，我可以继续拆成判断步骤。",
            "也可以指定某一条知识库内容，让我只围绕它继续展开。",
            "如果你有附件，接上文件后我可以把知识和文件一起比对。",
        ]
    elif intent == "evidence_chain_analysis":
        suggestions = [
            "如果要复盘，我可以继续区分事实、推断和待验证部分。",
            "如果你关心来源，我可以把本轮命中的知识和证据再按时间线整理。",
            "如果要落到个股层面，下一轮直接补股票名称或代码即可。",
        ]
    else:
        suggestions = [
            "可以继续补一个更具体的对象、变量或时间范围，我会明显答得更准。",
            "如果你需要结构化页面，直接问复盘、自选股、基本面或给出股票对象即可。",
            "如果有文件，也可以通过加号上传后继续问同一个问题。",
        ]
    return suggestions[:3]


def build_hermes_text_artifact(question_text, plan, synthesis, tool_outputs, citations):
    answer_text = str((synthesis or {}).get("answer") or "").strip()
    summary_text = str((synthesis or {}).get("summary") or "").strip()
    bullets = [
        str(item).strip()
        for item in ((synthesis or {}).get("bullets") if isinstance((synthesis or {}).get("bullets"), list) else [])
        if str(item).strip()
    ][:6]
    knowledge_matches = ((tool_outputs.get("knowledge") or {}).get("matches") or []) if isinstance(tool_outputs, dict) else []
    knowledge_entries = []
    for item in knowledge_matches[:3]:
        if not isinstance(item, dict):
            continue
        knowledge_entries.append({
            "title": str(item.get("title") or "未命名知识").strip(),
            "summary": str(item.get("summary") or item.get("body") or "").strip()[:160],
        })
    return {
        "type": "text_response",
        "question": str(question_text or "").strip(),
        "headline": trim_hermes_text(summary_text or answer_text or "已完成本轮查询", limit=90),
        "summary": trim_hermes_text(summary_text or str((plan or {}).get("reason") or "").strip(), limit=220),
        "body": answer_text,
        "bullets": bullets,
        "citations": citations[:6],
        "knowledge": knowledge_entries,
        "followups": build_hermes_followups(plan, tool_outputs),
        "footer": f"当前为文字回答。路由判断：{str((plan or {}).get('reason') or '').strip()}",
    }


def build_hermes_watchlist_artifact(detail, question_text, synthesis, tool_outputs, citations, tenant_slug="", user_role=""):
    detail = copy.deepcopy(detail if isinstance(detail, dict) else {})
    fundamental = detail.get("fundamental") if isinstance(detail.get("fundamental"), dict) else {}
    forecast = detail.get("forecast") if isinstance(detail.get("forecast"), dict) else {}
    metrics = [
        {
            "label": str(item.get("label") or "").strip(),
            "value": str(item.get("value") or "").strip(),
            "note": str(item.get("note") or "").strip(),
        }
        for item in (fundamental.get("metrics") if isinstance(fundamental.get("metrics"), list) else [])[:4]
        if isinstance(item, dict)
    ]
    knowledge_matches = ((tool_outputs.get("knowledge") or {}).get("matches") or []) if isinstance(tool_outputs, dict) else []
    evidence_matches = ((tool_outputs.get("evidence") or {}).get("matches") or []) if isinstance(tool_outputs, dict) else []
    bullets = [str(item).strip() for item in (synthesis.get("bullets") if isinstance(synthesis.get("bullets"), list) else []) if str(item).strip()][:3]
    if not bullets:
        bullets = [
            str(item).strip()
            for item in (fundamental.get("thesis") if isinstance(fundamental.get("thesis"), list) else [])
            if str(item).strip()
        ][:3]
    actions = []
    drivers = forecast.get("drivers") if isinstance(forecast.get("drivers"), list) else []
    for item in drivers[:2]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        note = str(item.get("note") or "").strip()
        if label or note:
            actions.append("：".join(part for part in [label, note] if part))
    if not actions:
        actions = [
            "继续跟踪盈利、估值和行业位置三个变量。",
            "补充下一轮验证节点，再决定是否继续深挖。",
        ]
    knowledge_entries = []
    for item in knowledge_matches[:3]:
        if not isinstance(item, dict):
            continue
        knowledge_entries.append({
            "title": str(item.get("title") or "未命名知识").strip(),
            "summary": str(item.get("summary") or item.get("body") or "").strip()[:160],
        })
    evidence = build_hermes_citations(tool_outputs)
    tenant = get_tenant_by_slug(tenant_slug)
    tenant_advisor = str((tenant or {}).get("advisor") or "").strip()
    title_prefix = "📌" if str(forecast.get("verdict") or "").strip() else "🧭"
    answer_text = str(synthesis.get("answer") or "").strip()
    headline = trim_hermes_text(synthesis.get("summary") or answer_text or f"{detail.get('name') or detail.get('code') or '该标的'} 已完成结构化分析", limit=90)
    summary = trim_hermes_text(synthesis.get("summary") or fundamental.get("summary") or answer_text, limit=220)
    return {
        "type": "watchlist_analysis",
        "question": str(question_text or "").strip(),
        "title": f"{title_prefix} 结构化分析",
        "headline": headline,
        "summary": summary,
        "body": answer_text,
        "symbol": {
            "name": str(detail.get("name") or "").strip(),
            "code": str(detail.get("code") or "").strip(),
            "market": str(detail.get("market") or "").strip(),
            "industry": str(detail.get("industry") or "").strip(),
        },
        "confidence": str(forecast.get("confidence") or "中").strip() or "中",
        "metrics": metrics,
        "judgement": bullets,
        "next_steps": actions,
        "citations": citations[:8],
        "knowledge": knowledge_entries,
        "chart": {
            "kind": "kline",
            "points": copy.deepcopy(detail.get("kline") or []),
        },
        "footer": (
            f"本轮问题：{str(question_text or '').strip()}"
            if not tenant_advisor else
            f"当前优先结合 {tenant_advisor} 租户知识、自选股和证据条目做解释。"
        ),
    }


def build_hermes_artifacts(plan, tool_outputs, synthesis, citations, tenant_slug="", user_role="", question_text=""):
    display_mode = str(plan.get("display_mode") or "text").strip() or "text"
    artifacts = []
    watchlist_result = tool_outputs.get("watchlist") if isinstance(tool_outputs, dict) else {}
    watchlist_detail = (watchlist_result or {}).get("detail") if isinstance(watchlist_result, dict) else None
    if display_mode == "structured" and isinstance(watchlist_detail, dict) and watchlist_detail:
        artifacts.append(
            build_hermes_watchlist_artifact(
                detail=watchlist_detail,
                question_text=question_text,
                synthesis=synthesis,
                tool_outputs=tool_outputs,
                citations=citations,
                tenant_slug=tenant_slug,
                user_role=user_role,
            )
        )
    if not artifacts:
        artifacts.append(
            build_hermes_text_artifact(
                question_text=question_text,
                plan=plan,
                synthesis=synthesis,
                tool_outputs=tool_outputs,
                citations=citations,
            )
        )
    return artifacts


def build_hermes_synthesis_prompt(question_text, plan, tool_outputs, tenant_slug="", user_role="", preferred_mode="", messages=None):
    tenant = get_tenant_by_slug(tenant_slug)
    tenant_name = (tenant or {}).get("name") or (tenant or {}).get("short_name") or str(tenant_slug or "").strip() or "当前租户"
    conversation_block = format_hermes_message_context(messages, limit=8)
    blocks = [
        f"租户：{tenant_name}",
        f"角色：{str(user_role or '').strip() or 'unknown'}",
        f"问题：{str(question_text or '').strip()}",
        f"意图：{str(plan.get('intent') or '').strip()}",
        f"偏好分析方式：{str(preferred_mode or '').strip() or 'auto'}",
        f"展示模式：{str(plan.get('display_mode') or 'text').strip()}",
        f"路由原因：{str(plan.get('reason') or '').strip()}",
        f"最近多轮对话：\n{conversation_block}" if conversation_block else "",
        f"工具结果：{json.dumps(tool_outputs, ensure_ascii=False)[:12000]}",
    ]
    blocks = [block for block in blocks if block]
    system_prompt = (
        "你是 Hermes 的答案合成器。"
        "你的职责是根据已执行的工具结果生成最终回答。"
        "优先依据工具结果，不要编造不存在的数据。"
        "如果证据不足，要明确说边界。"
        "输出必须是 JSON。"
    )
    user_prompt = (
        "\n\n".join(blocks) +
        "\n\n请输出 JSON："
        '{"answer":"中文最终回答","summary":"一句摘要","bullets":["..."],"citations":["..."]}'
    )
    return system_prompt, user_prompt


def synthesize_hermes_answer(question_text, plan, tool_outputs, tenant_slug="", user_role="", preferred_mode="", messages=None):
    fallback_answer = "我先按当前可用的知识和工具结果给你一个文字回答。"
    fallback = {
        "answer": fallback_answer,
        "summary": str(plan.get("reason") or "已完成工具组合查询").strip(),
        "bullets": [],
        "citations": [],
    }
    llm_model = get_default_llm_config(purpose="general")
    if not llm_model:
        return fallback, None, "fallback_plain_answer"
    try:
        system_prompt, user_prompt = build_hermes_synthesis_prompt(
            question_text=question_text,
            plan=plan,
            tool_outputs=tool_outputs,
            tenant_slug=tenant_slug,
            user_role=user_role,
            preferred_mode=preferred_mode,
            messages=messages,
        )
        raw = call_openai_compatible_llm(
            llm_model,
            system_prompt,
            user_prompt,
            feature_code="hermes_answer_synthesis",
            feature_label="Hermes 回答合成",
            tenant_slug=tenant_slug,
            entry_point="hermes_query",
            metadata={"intent": plan.get("intent"), "tool_count": len(plan.get("tools") or [])},
            request_timeout_seconds=40,
        )
        parsed = _extract_json_payload_from_llm_text(raw, fallback)
        answer = str(parsed.get("answer") or fallback_answer).strip() or fallback_answer
        summary = str(parsed.get("summary") or plan.get("reason") or "").strip()[:240]
        bullets = [str(item).strip() for item in (parsed.get("bullets") if isinstance(parsed.get("bullets"), list) else []) if str(item).strip()][:6]
        citations = [str(item).strip() for item in (parsed.get("citations") if isinstance(parsed.get("citations"), list) else []) if str(item).strip()][:8]
        return {
            "answer": answer,
            "summary": summary,
            "bullets": bullets,
            "citations": citations,
        }, llm_model, "llm_synthesized"
    except Exception:
        app.logger.exception("Failed to synthesize Hermes answer")
        return fallback, llm_model, "fallback_plain_answer"


def build_hermes_query_response(body):
    payload = body if isinstance(body, dict) else {}
    tenant_slug = str(payload.get("tenant_slug") or request.args.get("tenant") or get_default_tenant_slug()).strip().lower()
    user_role = str(payload.get("user_role") or "").strip().lower() or str((get_current_demo_profile() or {}).get("role") or "").strip().lower()
    selected_knowledge_ids = payload.get("selected_knowledge_ids") if isinstance(payload.get("selected_knowledge_ids"), list) else []
    attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
    preferred_mode = str(payload.get("preferred_mode") or "").strip().lower()
    messages = normalize_hermes_messages(payload.get("messages"))
    question_text = extract_hermes_question_text(messages, payload.get("question"))
    if not question_text:
        raise ValueError("hermes_question_required")
    intent_plan, router_model, route_mode = route_hermes_query_intent(
        question_text=question_text,
        tenant_slug=tenant_slug,
        selected_knowledge_ids=selected_knowledge_ids,
        attachments=attachments,
        preferred_mode=preferred_mode,
        messages=messages,
    )
    tool_outputs, tool_trace = execute_hermes_tool_plan(
        plan=intent_plan,
        tenant_slug=tenant_slug,
        question_text=question_text,
        selected_knowledge_ids=selected_knowledge_ids,
        attachments=attachments,
    )
    synthesis, answer_model, answer_mode = synthesize_hermes_answer(
        question_text=question_text,
        plan=intent_plan,
        tool_outputs=tool_outputs,
        tenant_slug=tenant_slug,
        user_role=user_role,
        preferred_mode=preferred_mode,
        messages=messages,
    )
    citations = build_hermes_citations(tool_outputs)
    artifacts = build_hermes_artifacts(
        plan=intent_plan,
        tool_outputs=tool_outputs,
        synthesis=synthesis,
        citations=citations,
        tenant_slug=tenant_slug,
        user_role=user_role,
        question_text=question_text,
    )
    response_display_mode = "structured" if any(str((item or {}).get("type") or "").strip() == "watchlist_analysis" for item in artifacts) else "text"
    return {
        "ok": True,
        "question": question_text,
        "tenant_slug": tenant_slug,
        "intent": intent_plan.get("intent"),
        "display_mode": response_display_mode,
        "answer": synthesis.get("answer") or "",
        "summary": synthesis.get("summary") or "",
        "bullets": synthesis.get("bullets") or [],
        "citations": (synthesis.get("citations") or []) + [item for item in citations if item not in (synthesis.get("citations") or [])],
        "artifacts": artifacts,
        "tool_trace": tool_trace,
        "tool_outputs": tool_outputs,
        "preferred_mode": preferred_mode or "auto",
        "router": {
            "mode": route_mode,
            "reason": intent_plan.get("reason") or "",
            "model": {
                "key": router_model.get("key"),
                "label": router_model.get("label"),
                "provider": router_model.get("provider"),
                "model_name": router_model.get("model_name"),
            } if router_model else None,
        },
        "answer_engine": {
            "mode": answer_mode,
            "model": {
                "key": answer_model.get("key"),
                "label": answer_model.get("label"),
                "provider": answer_model.get("provider"),
                "model_name": answer_model.get("model_name"),
            } if answer_model else None,
        },
        "usage": {
            "compute_used": 1,
        },
    }


def process_review_voice_upload(file_storage, tenant_slug="", review_period="", entry_point="", speaker_name="", use_llm_enhancement=False, job_code=""):
    if file_storage is None:
        raise ValueError("audio_file_required")
    safe_name = _safe_audio_filename(getattr(file_storage, "filename", ""))
    content_type = _guess_audio_content_type(safe_name, getattr(file_storage, "mimetype", ""))
    if not _is_allowed_audio_upload(safe_name, content_type):
        raise ValueError("unsupported_audio_type")
    audio_bytes = file_storage.read() or b""
    if not audio_bytes:
        raise ValueError("empty_audio_file")
    if len(audio_bytes) > VOICE_UPLOAD_MAX_BYTES:
        raise ValueError("audio_file_too_large")
    transcription_cfg = get_voice_transcription_config()
    transcript, transcript_engine = transcribe_review_audio(
        audio_bytes=audio_bytes,
        filename=safe_name,
        content_type=content_type,
        engine=transcription_cfg.get("engine", "local"),
    )
    transcript_model = LOCAL_WHISPER_MODEL_SIZE if transcript_engine == "local" else OPENAI_AUDIO_MODEL
    raw_transcript = str(transcript or "").strip()
    if job_code:
        report_user_async_job_progress(
            job_code,
            stage="transcribed",
            percent=50,
            summary="基础转写已完成，正在整理文本",
            log_text=f"已完成{transcript_engine}转写，准备输出可编辑文案。",
        )
    enhanced_transcript = ""
    llm_enhanced = False
    llm_notice = ""
    llm_model_info = None
    if use_llm_enhancement and raw_transcript:
        try:
            llm_result = enhance_review_voice_transcript_with_llm(
                raw_transcript,
                entry_point=entry_point,
                speaker_name=speaker_name,
                tenant_slug=tenant_slug,
            )
            enhanced_transcript = str(llm_result.get("text") or "").strip()
            llm_model_info = llm_result.get("model")
            llm_enhanced = bool(enhanced_transcript)
            if llm_enhanced:
                llm_notice = "已完成基础转写，并由大模型整理为更适合编辑和入库的文本。"
        except Exception as exc:
            llm_notice = f"已完成基础转写，但大模型增强失败，已回退原始转写：{str(exc)}"
    return {
        "transcript": raw_transcript,
        "display_transcript": enhanced_transcript or raw_transcript,
        "raw_transcript": raw_transcript,
        "enhanced_transcript": enhanced_transcript,
        "transcript_engine": transcript_engine,
        "transcript_model": transcript_model,
        "llm_enhancement_requested": bool(use_llm_enhancement),
        "llm_enhanced": llm_enhanced,
        "llm_notice": llm_notice,
        "llm_model": llm_model_info,
    }


def process_review_publish_text(text, tenant_slug="", review_period="", entry_point="", speaker_name="", transcription_engine="manual", transcript_model="manual_input", job_code=""):
    normalized_text = str(text or "").strip()
    if not normalized_text:
        raise ValueError("publish_text_required")
    embedding_cfg = get_voice_embedding_config()
    if job_code:
        report_user_async_job_progress(
            job_code,
            stage="embedding",
            percent=60,
            summary="正在计算复盘向量并准备入库",
            log_text="复盘正文已确认，正在生成向量表示。",
        )
    embedding, embedding_engine, embedding_model = build_text_embedding(
        normalized_text,
        engine=embedding_cfg.get("engine", "api"),
        feature_code="review_publish_embedding",
        feature_label="复盘发布向量入库",
        tenant_slug=tenant_slug,
        entry_point=entry_point,
        metadata={"review_period": review_period, "transcription_engine": transcription_engine},
    )
    vector_namespace = build_vector_namespace(embedding_engine, embedding_model)
    record = _store_review_voice_embedding_record(
        tenant_slug=tenant_slug,
        review_period=review_period,
        entry_point=entry_point,
        vector_namespace=vector_namespace,
        speaker_name=speaker_name,
        filename="review_publish_text.txt",
        content_type="text/plain",
        audio_size_bytes=0,
        transcript=normalized_text,
        transcription_engine=transcription_engine,
        transcript_model=transcript_model,
        embedding=embedding,
        embedding_engine=embedding_engine,
        embedding_model=embedding_model,
    )
    return {
        "text": normalized_text,
        "record": record,
        "transcription_engine": transcription_engine,
        "embedding_engine": embedding_engine,
        "embedding_model": embedding_model,
    }


def persist_review_publish_snapshot(
    tenant_slug,
    text,
    review_period="",
    speaker_name="",
    source_mode="manual",
    paragraph_mode="manual",
    selected_watchlist=None,
    prompt_tags=None,
    knowledge_attachments=None,
    selected_cards=None,
    data_sources=None,
    news_sources=None,
    llm_models=None,
    polished_input_text="",
):
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or tenant.get("slug") != tenant_slug:
        raise ValueError("tenant_not_found")
    period_key = str(review_period or "day").strip().lower() or "day"
    period_map = {"day": "日复盘", "week": "周复盘", "month": "月复盘"}
    period_label = period_map.get(period_key, "日复盘")
    cleaned_text = str(text or "").strip()
    title_seed = re.split(r"[。！？\n]", cleaned_text, 1)[0].strip() if cleaned_text else ""
    title = f"{period_label}：{title_seed or '最新复盘已发布'}"
    summary = re.sub(r"\s+", " ", cleaned_text).strip()[:160] if cleaned_text else f"{period_label}已发布。"
    snapshot = {
        "id": f"{tenant_slug}-review-{int(time.time() * 1000)}",
        "title": title[:80],
        "period": period_label,
        "period_key": period_key,
        "time": now_ts(),
        "published_at": now_ts(),
        "tags": [str(tag).strip() for tag in (prompt_tags if isinstance(prompt_tags, list) else []) if str(tag).strip()][:6] or (["自定义文案"] if paragraph_mode == "manual" else ["智能文案"]),
        "watchlist": [str(name).strip() for name in (selected_watchlist if isinstance(selected_watchlist, list) else []) if str(name).strip()][:8],
        "summary": summary or title[:80],
        "content_text": cleaned_text,
        "source_mode": str(source_mode or "manual").strip().lower() or "manual",
        "paragraph_mode": str(paragraph_mode or "manual").strip().lower() or "manual",
        "publisher": str(speaker_name or tenant.get("advisor") or "").strip() or tenant.get("advisor") or "",
        "snapshot_type": "published_review",
        "knowledge_attachments": copy.deepcopy(knowledge_attachments if isinstance(knowledge_attachments, list) else []),
        "selected_cards": copy.deepcopy(selected_cards if isinstance(selected_cards, list) else []),
        "data_sources": [str(source).strip() for source in (data_sources if isinstance(data_sources, list) else []) if str(source).strip()][:12],
        "news_sources": [str(source).strip() for source in (news_sources if isinstance(news_sources, list) else []) if str(source).strip()][:12],
        "llm_models": copy.deepcopy(llm_models if isinstance(llm_models, list) else []),
        "polished_input_text": str(polished_input_text or "").strip()[:12000],
    }
    snapshots = append_review_snapshot(tenant_slug, snapshot)
    review_message = {
        "id": f"{tenant_slug}-review-message-{int(time.time() * 1000)}",
        "type": "review_notification",
        "name": "复盘发布提醒",
        "time": "刚刚",
        "content": f"你刚发布的{period_label}已经同步到前台复盘专区，并准备推送给粉丝。",
        "status": "已送达",
        "user_name": "复盘发布提醒",
        "user_avatar": "📝",
        "tier": "系统消息",
        "last_msg": f"【最新复盘已发布】{title[:40]}",
        "unread": 0,
        "vip_only": False,
        "messages": [
            {
                "id": 1,
                "sender": "kol",
                "content": f"【最新复盘已发布】{title}\n已同步到复盘专区，当前纳入样本：{'、'.join(snapshot['watchlist']) if snapshot['watchlist'] else '未指定'}。\n现在可以直接去“复盘”页查看完整内容。",
                "time": now_ts(),
                "type": "review",
            }
        ],
    }
    message_state = append_message_thread(tenant_slug, review_message)
    review_broadcast = {
        "id": int(time.time() * 1000),
        "content": f"【最新复盘已发布】{title}\n已同步到复盘专区，当前纳入样本：{'、'.join(snapshot['watchlist']) if snapshot['watchlist'] else '未指定'}。\n现在可以直接去“复盘”页查看完整内容。",
        "time": now_ts(),
        "reach": max(1, len(list_users(role='investor', tenant_slug=tenant_slug))),
        "open_rate": random.randint(35, 78),
        "target": "review",
        "type": "broadcast",
    }
    message_state = append_broadcast_history(tenant_slug, review_broadcast)
    message_state = push_broadcast_to_fan_threads(tenant_slug, review_broadcast)
    return {
        "snapshot": snapshot,
        "snapshots": snapshots,
        "message_center_state": message_state,
    }


def process_review_manual_text(text, tenant_slug="", review_period="", entry_point="", speaker_name=""):
    normalized_text = str(text or "").strip()
    if not normalized_text:
        raise ValueError("manual_text_required")
    return {
        "text": normalized_text,
        "transcription_engine": "manual",
        "transcript_model": "manual_input",
    }


def _extract_text_from_html(html_text):
    if not str(html_text or "").strip():
        return ""
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.extract()
        return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True)).strip()
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(html_text))).strip()


def _extract_title_from_html(html_text, fallback="网页资料提炼"):
    if BeautifulSoup is not None and str(html_text or "").strip():
        soup = BeautifulSoup(html_text, "html.parser")
        title = ""
        if soup.title and soup.title.string:
            title = str(soup.title.string).strip()
        if not title:
            og = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "title"})
            if og and og.get("content"):
                title = str(og.get("content")).strip()
        if title:
            return title[:120]
    return str(fallback or "网页资料提炼").strip() or "网页资料提炼"


def fetch_url_preview(url):
    normalized_url = str(url or "").strip()
    if not normalized_url:
        raise ValueError("url_required")
    parsed = urlsplit(normalized_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("url_scheme_invalid")
    request_obj = Request(
        normalized_url,
        headers={
            "User-Agent": "Mozilla/5.0 GangtiseDemoBot/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request_obj, timeout=10) as resp:
        raw_bytes = resp.read()
        content_type = str(resp.headers.get("Content-Type") or "")
    html_text = raw_bytes.decode("utf-8", errors="ignore")
    title = _extract_title_from_html(html_text, fallback=parsed.netloc or "网页资料提炼")
    plain_text = _extract_text_from_html(html_text)
    summary = plain_text[:280] if plain_text else f"已抓取 {parsed.netloc or normalized_url}，可继续提炼行业主线、关键数据与验证节点。"
    return {
        "url": normalized_url,
        "domain": parsed.netloc or "",
        "title": title,
        "summary": summary,
        "body": plain_text[:12000],
        "content_type": content_type,
        "extraction_modes": ["html_text"],
        "ocr_used": False,
    }


def _extract_text_from_docx_bytes(file_bytes):
    if docx is None:
        return {"text": "", "stats": {"tables_found": 0, "ocr_pages": 0, "images_found": 0, "pages_processed": 0}}
    from io import BytesIO
    document = docx.Document(BytesIO(file_bytes))
    lines = [str(paragraph.text or "").strip() for paragraph in document.paragraphs if str(paragraph.text or "").strip()]
    table_count = 0
    for table in document.tables:
        table_rows = []
        for row in table.rows:
            cells = [str(cell.text or "").strip() for cell in row.cells if str(cell.text or "").strip()]
            if cells:
                table_rows.append(" | ".join(cells))
        if table_rows:
            table_count += 1
            lines.append("[table]")
            lines.extend(table_rows)
    image_ocr_parts = []
    image_count = 0
    rels = getattr(document.part, "rels", {})
    for rel in rels.values():
        target_ref = str(getattr(rel, "target_ref", "") or "")
        if "image" not in target_ref:
            continue
        image_count += 1
        try:
            image_bytes = rel.target_part.blob
        except Exception:
            continue
        ocr_text = _extract_ocr_text_from_image_bytes(image_bytes)
        if ocr_text:
            image_ocr_parts.append(ocr_text)
    if image_ocr_parts:
        lines.append("[ocr_images]")
        lines.extend(image_ocr_parts)
    return {
        "text": "\n".join(lines).strip(),
        "stats": {
            "tables_found": table_count,
            "ocr_pages": len(image_ocr_parts),
            "images_found": image_count,
            "pages_processed": 0,
        },
    }


def _extract_text_from_xlsx_bytes(file_bytes):
    if openpyxl is None:
        return {"text": "", "stats": {"tables_found": 0, "ocr_pages": 0, "images_found": 0, "pages_processed": 0}}
    from io import BytesIO
    workbook = openpyxl.load_workbook(BytesIO(file_bytes), data_only=True)
    lines = []
    rows_read = 0
    for sheet in workbook.worksheets[:3]:
        lines.append(f"[sheet] {sheet.title}")
        for row in sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 20), values_only=True):
            values = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
            if values:
                lines.append(" | ".join(values))
                rows_read += 1
    return {
        "text": "\n".join(lines).strip(),
        "stats": {
            "tables_found": 1 if rows_read else 0,
            "ocr_pages": 0,
            "images_found": 0,
            "pages_processed": min(len(workbook.worksheets), 3),
        },
    }


def _extract_text_from_pdf_bytes(file_bytes):
    if fitz is None:
        return {"text": "", "stats": {"tables_found": 0, "ocr_pages": 0, "images_found": 0, "pages_processed": 0}, "page_summaries": []}
    text_parts = []
    table_parts = []
    ocr_parts = []
    tables_found = 0
    page_summaries = []
    pages_processed = 0
    document = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        for page in document[: min(document.page_count, 8)]:
            pages_processed += 1
            page_text = str(page.get_text("text") or "").strip()
            if page_text:
                text_parts.append(page_text)
            if hasattr(page, "find_tables"):
                try:
                    tables = page.find_tables()
                    for table in getattr(tables, "tables", [])[:3]:
                        extracted = table.extract()
                        if not extracted:
                            continue
                        tables_found += 1
                        table_parts.append("[table]")
                        for row in extracted[:20]:
                            cells = [str(cell).strip() for cell in (row or []) if str(cell or "").strip()]
                            if cells:
                                table_parts.append(" | ".join(cells))
                except Exception:
                    continue
            if not page_text:
                ocr_text = _extract_ocr_text_from_pdf_page(page)
                if ocr_text:
                    ocr_parts.append(ocr_text)
                    page_text = ocr_text
            page_summaries.append({
                "page": pages_processed,
                "summary": str(page_text or "").replace("\n", " ")[:200],
                "used_ocr": bool(not str(page.get_text("text") or "").strip() and str(page_text or "").strip()),
            })
    finally:
        document.close()
    merged = [part.strip() for part in text_parts if str(part).strip()]
    if table_parts:
        merged.extend(table_parts)
    if ocr_parts:
        merged.append("[ocr]")
        merged.extend([part.strip() for part in ocr_parts if str(part).strip()])
    return {
        "text": "\n".join(merged).strip(),
        "stats": {
            "tables_found": tables_found,
            "ocr_pages": len(ocr_parts),
            "images_found": 0,
            "pages_processed": pages_processed,
        },
        "page_summaries": page_summaries,
    }


def _run_tesseract_on_image(image):
    if pytesseract is None or Image is None or image is None:
        return ""
    try:
        return str(pytesseract.image_to_string(image, lang="chi_sim+eng") or "").strip()
    except Exception:
        try:
            return str(pytesseract.image_to_string(image, lang="eng") or "").strip()
        except Exception:
            return ""


def _extract_ocr_text_from_pdf_page(page):
    if fitz is None or Image is None:
        return ""
    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        mode = "RGB" if pix.n < 4 else "RGBA"
        image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        return _run_tesseract_on_image(image)
    except Exception:
        return ""


def _extract_ocr_text_from_image_bytes(file_bytes):
    if Image is None:
        return ""
    from io import BytesIO
    try:
        image = Image.open(BytesIO(file_bytes))
    except Exception:
        return ""
    return _run_tesseract_on_image(image)


def extract_text_from_uploaded_file(file_storage):
    if file_storage is None:
        raise ValueError("file_required")
    filename = str(getattr(file_storage, "filename", "") or "").strip() or "upload.bin"
    suffix = Path(filename).suffix.lower()
    file_bytes = file_storage.read() or b""
    if not file_bytes:
        raise ValueError("empty_file")
    text = ""
    extraction_modes = []
    stats = {"tables_found": 0, "ocr_pages": 0, "images_found": 0, "pages_processed": 0}
    page_summaries = []
    if suffix in {".txt", ".md", ".csv"}:
        text = file_bytes.decode("utf-8", errors="ignore")
        extraction_modes.append("plain_text")
    elif suffix in {".html", ".htm"}:
        text = _extract_text_from_html(file_bytes.decode("utf-8", errors="ignore"))
        extraction_modes.append("html_text")
    elif suffix == ".docx":
        payload = _extract_text_from_docx_bytes(file_bytes)
        text = payload.get("text") or ""
        stats = payload.get("stats") or stats
        extraction_modes.append("docx_paragraphs_tables")
    elif suffix in {".xlsx", ".xlsm"}:
        payload = _extract_text_from_xlsx_bytes(file_bytes)
        text = payload.get("text") or ""
        stats = payload.get("stats") or stats
        extraction_modes.append("xlsx_cells")
    elif suffix == ".pdf":
        payload = _extract_text_from_pdf_bytes(file_bytes)
        text = payload.get("text") or ""
        stats = payload.get("stats") or stats
        page_summaries = payload.get("page_summaries") or []
        extraction_modes.append("pdf_text_tables_ocr")
    elif suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}:
        text = _extract_ocr_text_from_image_bytes(file_bytes)
        extraction_modes.append("image_ocr")
        stats["ocr_pages"] = 1 if text else 0
        stats["images_found"] = 1
    else:
        text = file_bytes.decode("utf-8", errors="ignore")
        extraction_modes.append("fallback_decode")
    text = str(text or "").strip()
    summary = text[:280] if text else f"已接收文件 {filename}，可继续补充摘要与验证节点。"
    return {
        "filename": filename,
        "suffix": suffix,
        "body": text[:12000],
        "summary": summary,
        "extraction_modes": extraction_modes,
        "ocr_used": any("ocr" in mode for mode in extraction_modes),
        "parse_stats": stats,
        "page_summaries": page_summaries[:8],
    }
