from src.runtime import *
from src.domain.core_services import *
from src.domain.core_services import _estimate_token_count, _extract_usage_tokens
from src.domain.agent_workflows import *
from src.domain.knowledge_graph_services import build_knowledge_graph_artifact
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
    workflow_definition = build_default_review_voice_enhancement_workflow_definition()

    def _voice_input_executor(state, runtime, node, upstream):
        normalized_transcript = str(runtime.get("transcript") or "").strip()
        if not normalized_transcript:
            raise ValueError("empty_transcript")
        speaker_label = str(runtime.get("speaker_name") or "").strip() or "未命名用户"
        context_label = "语音转写增强"
        if runtime.get("entry_point"):
            context_label = f"{context_label} · {runtime.get('entry_point')}"
        return {
            "detail": "已接收原始转写内容。",
            "state_updates": {
                "normalized_transcript": normalized_transcript,
                "speaker_label": speaker_label,
                "context_label": context_label,
            },
            "context_preview": {
                "source_chars": len(normalized_transcript),
                "speaker_name": speaker_label,
            },
        }

    def _voice_prepare_executor(state, runtime, node, upstream):
        system_prompt = (
            "你是一个中文语音纪要整理助手。"
            "请基于原始转写内容做轻量增强整理，去掉明显口语噪音和重复，修复少量语病，"
            "保留原始事实、观点、风险提示与不确定性，不要补充原文没有提到的信息，不要编造数字。"
            "输出纯文本，优先按自然段组织；如果原文明显包含多个观点，可以拆成短段。"
        )
        user_prompt = (
            f"场景：{state.get('context_label') or '语音转写增强'}\n"
            f"说话人：{state.get('speaker_label') or '未命名用户'}\n"
            "请输出更适合后续知识入库或文案编辑的整理稿。"
            "如果原始转写已经足够清晰，只做最少改动。\n\n"
            f"原始转写：\n{state.get('normalized_transcript') or ''}"
        )
        return {
            "detail": "已生成语音增强提示词。",
            "state_updates": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            },
            "context_preview": {"prompt_chars": len(user_prompt)},
        }

    def _voice_llm_executor(state, runtime, node, upstream):
        llm_model = get_default_llm_config(purpose="general")
        if not llm_model:
            raise RuntimeError("llm_model_unavailable")
        enhanced_text = call_openai_compatible_llm(
            llm_model,
            state.get("system_prompt") or "",
            state.get("user_prompt") or "",
            feature_code="review_voice_enhancement",
            feature_label="语音转写增强",
            tenant_slug=str(runtime.get("tenant_slug") or "").strip(),
            entry_point=str(runtime.get("entry_point") or "").strip(),
            metadata={
                "speaker_name": state.get("speaker_label") or "",
                "workflow_id": workflow_definition["id"],
            },
        )
        normalized_enhanced = str(enhanced_text or "").strip()
        if not normalized_enhanced:
            raise RuntimeError("empty_llm_response")
        return {
            "detail": "大模型已完成语音整理。",
            "state_updates": {
                "enhanced_text": normalized_enhanced,
                "llm_model": {
                    "key": llm_model.get("key"),
                    "label": llm_model.get("label"),
                    "provider": llm_model.get("provider"),
                    "model_name": llm_model.get("model_name"),
                    "purpose": llm_model.get("purpose"),
                },
            },
            "context_preview": {"output_chars": len(normalized_enhanced)},
        }

    def _voice_output_executor(state, runtime, node, upstream):
        return {
            "detail": "已封装语音增强结果。",
            "state_updates": {
                "final_result": {
                    "text": state.get("enhanced_text") or "",
                    "model": copy.deepcopy(state.get("llm_model") or {}),
                }
            },
            "context_preview": {"has_text": bool(state.get("enhanced_text"))},
        }

    execution = run_declared_agent_workflow(
        workflow_definition,
        runtime={
            "transcript": transcript,
            "entry_point": entry_point,
            "speaker_name": speaker_name,
            "tenant_slug": tenant_slug,
        },
        executor_registry={
            "review_voice_input": _voice_input_executor,
            "review_voice_prepare": _voice_prepare_executor,
            "review_voice_llm": _voice_llm_executor,
            "review_voice_output": _voice_output_executor,
        },
    )
    final_result = copy.deepcopy(execution["state"].get("final_result") or {})
    final_result["workflow_meta"] = build_declared_agent_workflow_meta(
        workflow_definition,
        extras={"last_execution_steps": copy.deepcopy(execution.get("node_results") or {})},
    )
    return final_result


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
    workflow_definition = build_default_review_draft_workflow_definition()

    def _review_draft_input_executor(state, runtime, node, upstream):
        normalized_source = str(runtime.get("source_text") or "").strip()
        if not normalized_source:
            raise ValueError("review_source_text_required")
        review_period_key = str(runtime.get("review_period") or "").strip().lower()
        source_mode_key = str(runtime.get("source_mode") or "").strip().lower()
        speaker_label = str(runtime.get("speaker_name") or "").strip() or "未命名大V"
        watchlist_items = [str(item).strip() for item in (runtime.get("selected_watchlist") or []) if str(item).strip()]
        tag_items = [str(item).strip() for item in (runtime.get("prompt_tags") or []) if str(item).strip()]
        return {
            "detail": "已接收复盘原始材料、标签和关注股票。",
            "state_updates": {
                "normalized_source": normalized_source,
                "review_period_key": review_period_key,
                "source_mode_key": source_mode_key,
                "speaker_label": speaker_label,
                "watchlist_items": watchlist_items,
                "tag_items": tag_items,
                "prompt_value": str(runtime.get("prompt_text") or "").strip(),
            },
            "context_preview": {
                "review_period": review_period_key or "unknown",
                "source_mode": source_mode_key or "unknown",
                "watchlist_count": len(watchlist_items),
                "tag_count": len(tag_items),
            },
        }

    def _review_draft_prepare_executor(state, runtime, node, upstream):
        period_label_map = {
            "day": "日复盘",
            "week": "周复盘",
            "month": "月复盘",
            "quarter": "季复盘",
            "knowledge": "知识整理",
        }
        system_prompt = (
            "你是一个中文投研复盘编辑助手。"
            "请把输入材料整理成适合直接发布前预览的完整复盘草稿。"
            "必须保留原始观点、风险提示和不确定性，不要编造事实、数字或结论。"
            "输出纯文本，用自然段组织；优先按市场主线、行业判断、重点个股、验证节点和风险提示展开。"
            "语言要专业、清晰、克制，避免空话和宣传语。"
        )
        user_prompt = "\n".join([
            f"复盘周期：{period_label_map.get(state.get('review_period_key'), state.get('review_period_key') or '未指定')}",
            f"输入来源：{state.get('source_mode_key') or 'unknown'}",
            f"作者身份：{state.get('speaker_label') or '未命名大V'}",
            f"触发入口：{runtime.get('entry_point') or 'unknown'}",
            f"关注股票：{'、'.join(state.get('watchlist_items') or []) if (state.get('watchlist_items') or []) else '未指定'}",
            f"附加标签：{'、'.join(state.get('tag_items') or []) if (state.get('tag_items') or []) else '无'}",
            f"改写规则：{state.get('prompt_value') or '无，请按专业复盘风格整理'}",
            "",
            "请直接输出最终复盘草稿，不要解释你的处理过程，不要输出标题前缀如“以下是整理结果”。",
            "",
            "原始材料：",
            state.get("normalized_source") or "",
        ])
        if runtime.get("job_code"):
            report_user_async_job_progress(
                runtime["job_code"],
                stage="llm_preparing",
                percent=55,
                summary="正在整理原始材料并构建复盘提示词",
                log_text="已完成素材归并，正在调用大模型生成复盘草稿。",
            )
        return {
            "detail": "已生成复盘草稿提示词。",
            "state_updates": {"system_prompt": system_prompt, "user_prompt": user_prompt},
            "context_preview": {"prompt_chars": len(user_prompt)},
        }

    def _review_draft_llm_executor(state, runtime, node, upstream):
        llm_model = get_default_llm_config(purpose="general")
        if not llm_model:
            raise RuntimeError("review_draft_llm_not_configured")
        rendered_text = call_openai_compatible_llm(
            llm_model,
            state.get("system_prompt") or "",
            state.get("user_prompt") or "",
            feature_code="review_draft_generation",
            feature_label="复盘草稿生成",
            tenant_slug=str(runtime.get("tenant_slug") or "").strip(),
            entry_point=str(runtime.get("entry_point") or "").strip(),
            metadata={
                "review_period": state.get("review_period_key") or "",
                "source_mode": state.get("source_mode_key") or "",
                "watchlist_count": len(state.get("watchlist_items") or []),
                "job_code": runtime.get("job_code") or "",
                "workflow_id": workflow_definition["id"],
            },
        )
        normalized_text = str(rendered_text or "").strip()
        if not normalized_text:
            raise RuntimeError("empty_llm_response")
        if runtime.get("job_code"):
            report_user_async_job_progress(
                runtime["job_code"],
                stage="llm_postprocessing",
                percent=85,
                summary="大模型已返回草稿，正在整理预览结果",
                log_text="复盘草稿已生成，正在整理模型信息和预览内容。",
            )
        return {
            "detail": "大模型已生成复盘 Draft。",
            "state_updates": {
                "rendered_text": normalized_text,
                "llm_model": {
                    "key": llm_model.get("key"),
                    "label": llm_model.get("label"),
                    "provider": llm_model.get("provider"),
                    "model_name": llm_model.get("model_name"),
                    "purpose": llm_model.get("purpose"),
                },
            },
            "context_preview": {"output_chars": len(normalized_text)},
        }

    def _review_draft_output_executor(state, runtime, node, upstream):
        result = {
            "text": state.get("rendered_text") or "",
            "llm_model": copy.deepcopy(state.get("llm_model") or {}),
            "workflow_meta": build_declared_agent_workflow_meta(
                workflow_definition,
                extras={"last_execution_steps": copy.deepcopy(upstream)},
            ),
        }
        return {
            "detail": "已封装复盘 Draft 结果。",
            "output": result,
            "state_key": "final_result",
            "context_preview": {"has_text": bool(result["text"]), "model": (result["llm_model"] or {}).get("model_name") or ""},
        }

    execution = run_declared_agent_workflow(
        workflow_definition,
        runtime={
            "source_text": source_text,
            "review_period": review_period,
            "source_mode": source_mode,
            "prompt_text": prompt_text,
            "prompt_tags": prompt_tags or [],
            "selected_watchlist": selected_watchlist or [],
            "speaker_name": speaker_name,
            "entry_point": entry_point,
            "tenant_slug": tenant_slug,
            "job_code": job_code,
        },
        executor_registry={
            "review_draft_input": _review_draft_input_executor,
            "review_draft_prepare": _review_draft_prepare_executor,
            "review_draft_llm": _review_draft_llm_executor,
            "review_draft_output": _review_draft_output_executor,
        },
    )
    return execution["state"]["final_result"]


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
    workflow_definition = build_default_review_polish_workflow_definition()

    def _polish_input_executor(state, runtime, node, upstream):
        normalized_source = str(runtime.get("source_text") or "").strip()
        if not normalized_source:
            raise ValueError("review_source_text_required")
        return {
            "detail": "已接收待润色的复盘输入。",
            "state_updates": {
                "normalized_source": normalized_source,
                "source_mode_key": str(runtime.get("source_mode") or "").strip().lower(),
                "speaker_label": str(runtime.get("speaker_name") or "").strip() or "未命名大V",
            },
            "context_preview": {"source_chars": len(normalized_source)},
        }

    def _polish_prepare_executor(state, runtime, node, upstream):
        review_cfg = get_review_generation_config()
        if runtime.get("job_code"):
            report_user_async_job_progress(
                runtime["job_code"],
                stage="llm_preparing",
                percent=38,
                summary="正在整理原始输入并准备润色",
                log_text="已进入输入润色阶段，正在构建提示词。",
            )
        system_prompt = review_cfg.get("polish_system_prompt") or DEFAULT_SITE_CONFIG["review_generation"]["polish_system_prompt"]
        user_prompt = (
            str(review_cfg.get("polish_user_template") or DEFAULT_SITE_CONFIG["review_generation"]["polish_user_template"])
            .replace("{period_label}", _get_review_period_label(runtime.get("review_period")))
            .replace("{source_mode}", state.get("source_mode_key") or "unknown")
            .replace("{speaker_label}", state.get("speaker_label") or "未命名大V")
            .replace("{entry_point}", str(runtime.get("entry_point") or "unknown").strip() or "unknown")
            .replace("{source_text}", state.get("normalized_source") or "")
        )
        return {
            "detail": "已生成输入润色提示词。",
            "state_updates": {
                "review_cfg": review_cfg,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            },
            "context_preview": {"prompt_chars": len(user_prompt)},
        }

    def _polish_llm_executor(state, runtime, node, upstream):
        llm_model = get_default_llm_config(purpose="general")
        if not llm_model:
            raise RuntimeError("review_polish_llm_not_configured")
        review_cfg = state.get("review_cfg") if isinstance(state.get("review_cfg"), dict) else get_review_generation_config()
        polished_text = call_openai_compatible_llm(
            llm_model,
            state.get("system_prompt") or "",
            state.get("user_prompt") or "",
            feature_code="review_input_polish",
            feature_label="复盘输入润色",
            tenant_slug=str(runtime.get("tenant_slug") or "").strip(),
            entry_point=str(runtime.get("entry_point") or "").strip(),
            metadata={
                "review_period": str(runtime.get("review_period") or "").strip().lower(),
                "source_mode": state.get("source_mode_key") or "",
                "job_code": runtime.get("job_code") or "",
                "stage": "polish",
                "workflow_id": workflow_definition["id"],
            },
            request_timeout_seconds=review_cfg.get("polish_timeout_seconds", 45),
        )
        normalized_text = str(polished_text or "").strip()
        if not normalized_text:
            raise RuntimeError("empty_llm_response")
        if runtime.get("job_code"):
            report_user_async_job_progress(
                runtime["job_code"],
                stage="llm_postprocessing",
                percent=82,
                summary="输入润色完成，正在整理预览内容",
                log_text="大模型已返回润色结果，正在回填复盘输入。",
            )
        return {
            "detail": "大模型已完成输入润色。",
            "state_updates": {
                "rendered_text": normalized_text,
                "llm_model": {
                    "key": llm_model.get("key"),
                    "label": llm_model.get("label"),
                    "provider": llm_model.get("provider"),
                    "model_name": llm_model.get("model_name"),
                    "purpose": llm_model.get("purpose"),
                },
            },
            "context_preview": {"output_chars": len(normalized_text)},
        }

    def _polish_output_executor(state, runtime, node, upstream):
        result = {
            "text": state.get("rendered_text") or "",
            "llm_model": copy.deepcopy(state.get("llm_model") or {}),
            "workflow_meta": build_declared_agent_workflow_meta(
                workflow_definition,
                extras={"last_execution_steps": copy.deepcopy(upstream)},
            ),
        }
        return {
            "detail": "已封装输入润色结果。",
            "output": result,
            "state_key": "final_result",
            "context_preview": {"has_text": bool(result["text"])},
        }

    execution = run_declared_agent_workflow(
        workflow_definition,
        runtime={
            "source_text": source_text,
            "review_period": review_period,
            "source_mode": source_mode,
            "speaker_name": speaker_name,
            "entry_point": entry_point,
            "tenant_slug": tenant_slug,
            "job_code": job_code,
        },
        executor_registry={
            "review_polish_input": _polish_input_executor,
            "review_polish_prepare": _polish_prepare_executor,
            "review_polish_llm": _polish_llm_executor,
            "review_polish_output": _polish_output_executor,
        },
    )
    return execution["state"]["final_result"]


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
    workflow_definition = build_default_review_compose_workflow_definition()

    def _compose_input_executor(state, runtime, node, upstream):
        normalized_source = str(runtime.get("source_text") or "").strip()
        if not normalized_source:
            raise ValueError("review_source_text_required")
        watchlist_items = [str(item).strip() for item in (runtime.get("selected_watchlist") or []) if str(item).strip()]
        tag_items = [str(item).strip() for item in (runtime.get("prompt_tags") or []) if str(item).strip()]
        return {
            "detail": "已接收复盘正文、卡片和知识材料。",
            "state_updates": {
                "normalized_source": normalized_source,
                "speaker_label": str(runtime.get("speaker_name") or "").strip() or "未命名大V",
                "watchlist_items": watchlist_items,
                "tag_items": tag_items,
                "prompt_value": str(runtime.get("prompt_text") or "").strip() or "无，请按专业复盘风格整理",
            },
            "context_preview": {
                "watchlist_count": len(watchlist_items),
                "card_count": len(runtime.get("dashboard_cards") or []),
                "knowledge_item_count": len(runtime.get("knowledge_items") or []),
            },
        }

    def _compose_context_executor(state, runtime, node, upstream):
        review_cfg = get_review_generation_config()
        dashboard_blocks = _format_review_dashboard_blocks(runtime.get("dashboard_cards") or [])
        knowledge_blocks = _format_review_knowledge_blocks(runtime.get("knowledge_items") or [])
        if runtime.get("job_code"):
            report_user_async_job_progress(
                runtime["job_code"],
                stage="llm_preparing",
                percent=46,
                summary="正在聚合智能仪表盘卡片并准备成稿",
                log_text="已完成卡片与输入拼接，准备调用大模型生成完整复盘。",
                extra_result={
                    "selected_card_count": len(runtime.get("dashboard_cards") or []),
                    "knowledge_item_count": len(runtime.get("knowledge_items") or []),
                },
            )
        system_prompt = review_cfg.get("compose_system_prompt") or DEFAULT_SITE_CONFIG["review_generation"]["compose_system_prompt"]
        user_prompt = (
            str(review_cfg.get("compose_user_template") or DEFAULT_SITE_CONFIG["review_generation"]["compose_user_template"])
            .replace("{period_label}", _get_review_period_label(runtime.get("review_period")))
            .replace("{speaker_label}", state.get("speaker_label") or "未命名大V")
            .replace("{entry_point}", str(runtime.get("entry_point") or "unknown").strip() or "unknown")
            .replace("{watchlist_text}", "、".join(state.get("watchlist_items") or []) if (state.get("watchlist_items") or []) else "未指定")
            .replace("{tag_text}", "、".join(state.get("tag_items") or []) if (state.get("tag_items") or []) else "无")
            .replace("{prompt_text}", state.get("prompt_value") or "无，请按专业复盘风格整理")
            .replace("{source_text}", state.get("normalized_source") or "")
            .replace("{dashboard_blocks}", dashboard_blocks or "未选择智能仪表盘卡片")
            .replace("{knowledge_blocks}", knowledge_blocks or "未选择知识材料")
        )
        return {
            "detail": "已完成复盘成稿上下文聚合。",
            "state_updates": {
                "review_cfg": review_cfg,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            },
            "context_preview": {
                "prompt_chars": len(user_prompt),
                "dashboard_count": len(runtime.get("dashboard_cards") or []),
                "knowledge_count": len(runtime.get("knowledge_items") or []),
            },
        }

    def _compose_llm_executor(state, runtime, node, upstream):
        llm_model = get_default_llm_config(purpose="general")
        if not llm_model:
            raise RuntimeError("review_compose_llm_not_configured")
        review_cfg = state.get("review_cfg") if isinstance(state.get("review_cfg"), dict) else get_review_generation_config()
        rendered_text = call_openai_compatible_llm(
            llm_model,
            state.get("system_prompt") or "",
            state.get("user_prompt") or "",
            feature_code="review_compose_generation",
            feature_label="复盘完整成稿",
            tenant_slug=str(runtime.get("tenant_slug") or "").strip(),
            entry_point=str(runtime.get("entry_point") or "").strip(),
            metadata={
                "review_period": str(runtime.get("review_period") or "").strip().lower(),
                "watchlist_count": len(state.get("watchlist_items") or []),
                "card_count": len(runtime.get("dashboard_cards") or []),
                "knowledge_item_count": len(runtime.get("knowledge_items") or []),
                "job_code": runtime.get("job_code") or "",
                "stage": "compose",
                "workflow_id": workflow_definition["id"],
            },
            request_timeout_seconds=review_cfg.get("compose_timeout_seconds", 60),
        )
        normalized_text = str(rendered_text or "").strip()
        if not normalized_text:
            raise RuntimeError("empty_llm_response")
        if runtime.get("job_code"):
            report_user_async_job_progress(
                runtime["job_code"],
                stage="llm_postprocessing",
                percent=88,
                summary="完整复盘草稿已返回，正在整理预览结果",
                log_text="复盘成稿已生成，正在回填卡片与模型信息。",
                extra_result={
                    "selected_card_count": len(runtime.get("dashboard_cards") or []),
                    "knowledge_item_count": len(runtime.get("knowledge_items") or []),
                },
            )
        return {
            "detail": "大模型已生成完整复盘成稿。",
            "state_updates": {
                "rendered_text": normalized_text,
                "llm_model": {
                    "key": llm_model.get("key"),
                    "label": llm_model.get("label"),
                    "provider": llm_model.get("provider"),
                    "model_name": llm_model.get("model_name"),
                    "purpose": llm_model.get("purpose"),
                },
            },
            "context_preview": {"output_chars": len(normalized_text)},
        }

    def _compose_output_executor(state, runtime, node, upstream):
        result = {
            "text": state.get("rendered_text") or "",
            "llm_model": copy.deepcopy(state.get("llm_model") or {}),
            "workflow_meta": build_declared_agent_workflow_meta(
                workflow_definition,
                extras={"last_execution_steps": copy.deepcopy(upstream)},
            ),
        }
        return {
            "detail": "已封装复盘成稿结果。",
            "output": result,
            "state_key": "final_result",
            "context_preview": {"has_text": bool(result["text"])},
        }

    execution = run_declared_agent_workflow(
        workflow_definition,
        runtime={
            "source_text": source_text,
            "review_period": review_period,
            "prompt_text": prompt_text,
            "prompt_tags": prompt_tags or [],
            "selected_watchlist": selected_watchlist or [],
            "speaker_name": speaker_name,
            "entry_point": entry_point,
            "tenant_slug": tenant_slug,
            "dashboard_cards": dashboard_cards or [],
            "knowledge_items": knowledge_items or [],
            "job_code": job_code,
        },
        executor_registry={
            "review_compose_input": _compose_input_executor,
            "review_compose_context": _compose_context_executor,
            "review_compose_llm": _compose_llm_executor,
            "review_compose_output": _compose_output_executor,
        },
    )
    return execution["state"]["final_result"]


def _normalize_review_source_mode_label(source_mode):
    mapping = {
        "voice": "语音口述",
        "manual": "手写正文",
        "file": "文件上传",
        "url": "网页链接",
    }
    key = str(source_mode or "").strip().lower()
    return mapping.get(key, key or "用户输入")


def _find_review_watchlist_detail(selected_item, details_map):
    normalized = str(selected_item or "").strip()
    if not normalized:
        return None
    for detail in (details_map or {}).values():
        if not isinstance(detail, dict):
            continue
        if normalized in {
            str(detail.get("name") or "").strip(),
            str(detail.get("code") or "").strip(),
        }:
            return copy.deepcopy(detail)
    return None


def _build_review_watchlist_sector_profiles(details):
    sector_map = {}
    ordered_sectors = []
    for detail in details or []:
        if not isinstance(detail, dict):
            continue
        sector_name = str(detail.get("industry") or detail.get("focus") or "其他板块").strip() or "其他板块"
        if sector_name not in sector_map:
            sector_map[sector_name] = {
                "sector": sector_name,
                "stock_names": [],
                "stock_codes": [],
                "signal_points": [],
                "summary_points": [],
            }
            ordered_sectors.append(sector_name)
        bucket = sector_map[sector_name]
        stock_name = str(detail.get("name") or detail.get("code") or "").strip()
        stock_code = str(detail.get("code") or "").strip()
        if stock_name and stock_name not in bucket["stock_names"]:
            bucket["stock_names"].append(stock_name)
        if stock_code and stock_code not in bucket["stock_codes"]:
            bucket["stock_codes"].append(stock_code)
        signal_summary = str(detail.get("signal_summary") or detail.get("alert_text") or "").strip()
        base_summary = str((((detail.get("fundamental") or {}) if isinstance(detail.get("fundamental"), dict) else {}).get("summary")) or "").strip()
        if signal_summary and signal_summary not in bucket["signal_points"]:
            bucket["signal_points"].append(signal_summary)
        if base_summary and base_summary not in bucket["summary_points"]:
            bucket["summary_points"].append(base_summary)
    profiles = []
    for sector_name in ordered_sectors:
        bucket = sector_map[sector_name]
        stock_names = bucket["stock_names"][:4]
        representative_stock = stock_names[0] if stock_names else sector_name
        supporting = "；".join((bucket["signal_points"] or bucket["summary_points"])[:2]).strip()
        representative_description = (
            f"{sector_name}以{representative_stock}为代表，本次复盘更适合从板块景气、龙头验证和后续催化三个角度归纳。"
            if not supporting else
            f"{sector_name}以{representative_stock}为代表，当前代表性描述可概括为：{supporting}"
        )
        profiles.append({
            "sector": sector_name,
            "stock_names": stock_names,
            "representative_description": representative_description[:220],
        })
    if not profiles:
        return [], "当前未匹配到可归纳的板块样本。"
    if len(profiles) == 1:
        only = profiles[0]
        summary = f"本次自选股主要集中在{only['sector']}，代表性标的包括{'、'.join(only['stock_names'])}。"
    else:
        lead = profiles[0]
        others = "、".join(item["sector"] for item in profiles[1:3])
        summary = f"本次自选股横跨{lead['sector']}{f'、{others}' if others else ''}等板块，其中{lead['sector']}是最主要的代表性主线。"
    return profiles, summary[:150]


def _build_review_watchlist_llm_prompt(details, sector_profiles, source_text, review_period):
    stock_blocks = []
    for index, detail in enumerate(details or [], start=1):
        if not isinstance(detail, dict):
            continue
        fundamental = detail.get("fundamental") if isinstance(detail.get("fundamental"), dict) else {}
        forecast = detail.get("forecast") if isinstance(detail.get("forecast"), dict) else {}
        metrics = [
            f"{str(item.get('label') or '').strip()}：{str(item.get('value') or '').strip()}（{str(item.get('note') or '').strip()}）"
            for item in (fundamental.get("metrics") or [])
            if isinstance(item, dict) and str(item.get("label") or "").strip()
        ]
        theses = [str(item).strip() for item in (fundamental.get("thesis") or []) if str(item).strip()]
        drivers = [
            f"{str(item.get('label') or '').strip()}：{str(item.get('note') or '').strip()}（{str(item.get('score') or '').strip()}）"
            for item in (forecast.get("drivers") or [])
            if isinstance(item, dict) and str(item.get("label") or "").strip()
        ]
        stock_blocks.append(
            "\n".join(
                [
                    f"[股票 {index}] 名称：{str(detail.get('name') or '').strip()}",
                    f"代码：{str(detail.get('code') or '').strip()}",
                    f"所属板块：{str(detail.get('industry') or detail.get('focus') or '其他板块').strip()}",
                    f"信号摘要：{str(detail.get('signal_summary') or detail.get('alert_text') or '').strip() or '暂无'}",
                    f"基本面摘要：{str(fundamental.get('summary') or '').strip() or '暂无'}",
                    f"当前判断：{str(forecast.get('verdict') or '').strip() or '待观察'} / 置信度 {str(forecast.get('confidence') or '中').strip() or '中'}",
                    f"指标要点：{'；'.join(metrics[:4]) if metrics else '暂无'}",
                    f"核心论点：{'；'.join(theses[:3]) if theses else '暂无'}",
                    f"驱动因素：{'；'.join(drivers[:3]) if drivers else '暂无'}",
                ]
            )
        )
    sector_blocks = [
        f"{item['sector']}：代表股票 {'、'.join(item['stock_names'])}；代表性描述：{item['representative_description']}"
        for item in (sector_profiles or [])
        if isinstance(item, dict)
    ]
    period_label = _get_review_period_label(review_period)
    return "\n".join(
        [
            f"复盘周期：{period_label}",
            f"用户自主输入摘要参考：{trim_hermes_text(source_text, limit=300) if str(source_text or '').strip() else '未提供'}",
            "",
            "板块归并基础：",
            "\n".join(sector_blocks) if sector_blocks else "暂无板块归并",
            "",
            "股票上下文：",
            "\n\n".join(stock_blocks) if stock_blocks else "暂无股票上下文",
            "",
            "请输出 JSON，格式如下：",
            '{"sector_summary":"150字内的板块与主线归纳","items":[{"stock_name":"股票名","stock_code":"代码","sector":"板块","board_role":"该股在本次复盘中的代表角色","analysis_text":"80到160字的归纳分析","evidence":["证据1","证据2"]}]}',
            "要求：",
            "1. 先从已选自选股归纳板块代表性，不要脱离这些股票泛化发挥。",
            "2. 每只股票的 analysis_text 要强调它为什么被纳入本次复盘，以及当前更该跟踪什么。",
            "3. 语言要适合直接展示在复盘详情页，不输出过程说明，不要使用 Markdown。",
        ]
    )


def analyze_review_watchlist_with_llm(
    selected_watchlist=None,
    review_period="",
    source_text="",
    speaker_name="",
    entry_point="",
    tenant_slug="",
    job_code="",
):
    workflow_definition = build_default_review_watchlist_analysis_workflow_definition()

    def _watchlist_input_executor(state, runtime, node, upstream):
        watchlist_items = [str(item).strip() for item in (runtime.get("selected_watchlist") or []) if str(item).strip()]
        if not watchlist_items:
            raise ValueError("review_selected_watchlist_required")
        return {
            "detail": "已接收本次复盘的自选股列表和用户输入正文。",
            "state_updates": {
                "watchlist_items": watchlist_items,
                "normalized_source_text": str(runtime.get("source_text") or "").strip(),
                "speaker_label": str(runtime.get("speaker_name") or "").strip() or "未命名大V",
            },
            "context_preview": {"watchlist_count": len(watchlist_items)},
        }

    def _watchlist_context_executor(state, runtime, node, upstream):
        details_map = gen_watchlist_details()
        matched = []
        for item in state.get("watchlist_items") or []:
            detail = _find_review_watchlist_detail(item, details_map)
            if detail:
                matched.append(detail)
        if not matched:
            raise ValueError("review_watchlist_detail_not_found")
        if runtime.get("job_code"):
            report_user_async_job_progress(
                runtime["job_code"],
                stage="watchlist_context_loading",
                percent=54,
                summary="正在装载自选股上下文",
                log_text="已匹配股票基础信息、板块归属和信号摘要。",
                extra_result={"selected_watchlist": [str(item.get("name") or "").strip() for item in matched]},
            )
        return {
            "detail": "已加载个股基础信息、基本面摘要和板块信号。",
            "state_updates": {"matched_watchlist_details": matched},
            "context_preview": {"matched_count": len(matched)},
        }

    def _watchlist_sector_executor(state, runtime, node, upstream):
        matched = state.get("matched_watchlist_details") if isinstance(state.get("matched_watchlist_details"), list) else []
        sector_profiles, sector_summary = _build_review_watchlist_sector_profiles(matched)
        if runtime.get("job_code"):
            report_user_async_job_progress(
                runtime["job_code"],
                stage="watchlist_sector_merging",
                percent=68,
                summary="正在归并板块代表性",
                log_text="已按行业板块归并自选股，准备生成复盘第二部分。",
                extra_result={"sector_profiles": sector_profiles},
            )
        return {
            "detail": "已完成板块代表性归并。",
            "state_updates": {
                "sector_profiles": sector_profiles,
                "sector_summary_rule": sector_summary,
                "system_prompt": (
                    "你是中文投研复盘助手。"
                    "你负责根据本次已选自选股，生成可直接展示在复盘详情页里的“自选股归纳分析”部分。"
                    "必须聚焦给定股票和对应板块，不要扩写成泛市场评论。"
                    "输出必须是 JSON。"
                ),
                "user_prompt": _build_review_watchlist_llm_prompt(
                    matched,
                    sector_profiles,
                    state.get("normalized_source_text") or "",
                    runtime.get("review_period") or "",
                ),
            },
            "context_preview": {"sector_count": len(sector_profiles)},
        }

    def _watchlist_llm_executor(state, runtime, node, upstream):
        llm_model = get_default_llm_config(purpose="general")
        if not llm_model:
            raise RuntimeError("review_watchlist_analysis_llm_not_configured")
        raw = call_openai_compatible_llm(
            llm_model,
            state.get("system_prompt") or "",
            state.get("user_prompt") or "",
            feature_code="review_watchlist_analysis",
            feature_label="复盘自选股归纳",
            tenant_slug=str(runtime.get("tenant_slug") or "").strip(),
            entry_point=str(runtime.get("entry_point") or "").strip(),
            metadata={
                "review_period": str(runtime.get("review_period") or "").strip().lower(),
                "watchlist_count": len(state.get("watchlist_items") or []),
                "job_code": runtime.get("job_code") or "",
                "workflow_id": workflow_definition["id"],
            },
            request_timeout_seconds=60,
        )
        fallback = {
            "sector_summary": state.get("sector_summary_rule") or "",
            "items": [],
        }
        parsed = _extract_json_payload_from_llm_text(raw, fallback)
        llm_items = parsed.get("items") if isinstance(parsed.get("items"), list) else []
        matched = state.get("matched_watchlist_details") if isinstance(state.get("matched_watchlist_details"), list) else []
        normalized_items = []
        for detail in matched:
            stock_name = str(detail.get("name") or "").strip()
            stock_code = str(detail.get("code") or "").strip()
            sector_name = str(detail.get("industry") or detail.get("focus") or "其他板块").strip() or "其他板块"
            hit = next(
                (
                    item for item in llm_items
                    if isinstance(item, dict) and str(item.get("stock_name") or item.get("stock_code") or "").strip() in {stock_name, stock_code}
                ),
                None,
            )
            fundamental = detail.get("fundamental") if isinstance(detail.get("fundamental"), dict) else {}
            forecast = detail.get("forecast") if isinstance(detail.get("forecast"), dict) else {}
            default_analysis = "；".join(
                part for part in [
                    str(fundamental.get("summary") or "").strip(),
                    str(forecast.get("band") or "").strip(),
                ] if part
            ).strip() or f"{stock_name}当前更适合继续跟踪{sector_name}主线下的业绩兑现、估值位置和下一轮催化。"
            evidence = hit.get("evidence") if isinstance(hit, dict) and isinstance(hit.get("evidence"), list) else []
            normalized_items.append({
                "stock_name": stock_name,
                "stock_code": stock_code,
                "sector": str((hit or {}).get("sector") or sector_name).strip() or sector_name,
                "board_role": str((hit or {}).get("board_role") or f"{sector_name}代表样本").strip()[:80] or f"{sector_name}代表样本",
                "analysis_text": trim_hermes_text(str((hit or {}).get("analysis_text") or default_analysis).strip(), limit=220),
                "evidence": [trim_hermes_text(str(item).strip(), limit=60) for item in evidence if str(item).strip()][:4],
            })
        sector_summary = trim_hermes_text(
            str(parsed.get("sector_summary") or state.get("sector_summary_rule") or "").strip() or (state.get("sector_summary_rule") or ""),
            limit=150,
        )
        if runtime.get("job_code"):
            report_user_async_job_progress(
                runtime["job_code"],
                stage="watchlist_analysis_done",
                percent=82,
                summary="自选股归纳分析已生成",
                log_text="板块主线和逐股归纳已完成，正在整理发布结构。",
            )
        return {
            "detail": "已生成板块代表性和逐股归纳分析。",
            "state_updates": {
                "analysis_result": {
                    "sector_summary": sector_summary,
                    "sector_profiles": copy.deepcopy(state.get("sector_profiles") or []),
                    "items": normalized_items,
                    "llm_model": {
                        "key": llm_model.get("key"),
                        "label": llm_model.get("label"),
                        "provider": llm_model.get("provider"),
                        "model_name": llm_model.get("model_name"),
                        "purpose": llm_model.get("purpose"),
                        "stage": "watchlist_analysis",
                    },
                }
            },
            "context_preview": {"item_count": len(normalized_items)},
        }

    def _watchlist_output_executor(state, runtime, node, upstream):
        result = copy.deepcopy(state.get("analysis_result") or {})
        result["workflow_meta"] = build_declared_agent_workflow_meta(
            workflow_definition,
            extras={"last_execution_steps": copy.deepcopy(upstream)},
        )
        return {
            "detail": "已封装自选股归纳分析结果。",
            "output": result,
            "state_key": "final_result",
            "context_preview": {"has_items": bool((result.get("items") or []))},
        }

    execution = run_declared_agent_workflow(
        workflow_definition,
        runtime={
            "selected_watchlist": selected_watchlist or [],
            "review_period": review_period,
            "source_text": source_text,
            "speaker_name": speaker_name,
            "entry_point": entry_point,
            "tenant_slug": tenant_slug,
            "job_code": job_code,
        },
        executor_registry={
            "review_watchlist_input": _watchlist_input_executor,
            "review_watchlist_context": _watchlist_context_executor,
            "review_watchlist_sector_merge": _watchlist_sector_executor,
            "review_watchlist_llm": _watchlist_llm_executor,
            "review_watchlist_output": _watchlist_output_executor,
        },
    )
    return execution["state"]["final_result"]


def summarize_review_user_input_with_llm(
    source_text,
    review_period="",
    source_mode="",
    speaker_name="",
    entry_point="",
    tenant_slug="",
):
    normalized_source = str(source_text or "").strip()
    if not normalized_source:
        raise ValueError("review_source_text_required")
    llm_model = get_default_llm_config(purpose="general")
    if not llm_model:
        raise RuntimeError("review_summary_llm_not_configured")
    raw = call_openai_compatible_llm(
        llm_model,
        (
            "你是中文投研复盘摘要助手。"
            "你只能根据用户自主输入内容做摘要，不得引用自选股分析、外部扩展解释或额外推断。"
            "输出纯文本，一句话或两句话均可，控制在150个中文字符以内。"
        ),
        "\n".join(
            [
                f"复盘周期：{_get_review_period_label(review_period)}",
                f"输入来源：{_normalize_review_source_mode_label(source_mode)}",
                f"作者：{str(speaker_name or '').strip() or '未命名大V'}",
                f"入口：{str(entry_point or '').strip() or 'unknown'}",
                "",
                "请仅基于以下用户自主输入内容生成摘要：",
                normalized_source,
            ]
        ),
        feature_code="review_user_input_summary",
        feature_label="复盘用户输入摘要",
        tenant_slug=str(tenant_slug or "").strip(),
        entry_point=str(entry_point or "").strip(),
        metadata={
            "review_period": str(review_period or "").strip().lower(),
            "source_mode": str(source_mode or "").strip().lower(),
        },
        request_timeout_seconds=45,
    )
    summary = re.sub(r"\s+", " ", str(raw or "").strip())
    summary = summary.replace("摘要：", "").replace("总结：", "").strip()
    summary = summary[:150].strip() or re.sub(r"\s+", " ", normalized_source)[:150].strip()
    return {
        "summary": summary,
        "llm_model": {
            "key": llm_model.get("key"),
            "label": llm_model.get("label"),
            "provider": llm_model.get("provider"),
            "model_name": llm_model.get("model_name"),
            "purpose": llm_model.get("purpose"),
            "stage": "user_input_summary",
        },
    }


def _compose_review_watchlist_analysis_text(section):
    payload = section if isinstance(section, dict) else {}
    sector_summary = str(payload.get("sector_summary") or "").strip()
    sector_profiles = payload.get("sector_profiles") if isinstance(payload.get("sector_profiles"), list) else []
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    lines = []
    if sector_summary:
        lines.append(f"板块归纳：{sector_summary}")
    if sector_profiles:
        lines.append("板块代表性：")
        for profile in sector_profiles:
            if not isinstance(profile, dict):
                continue
            lines.append(
                f"- {str(profile.get('sector') or '').strip()}：{str(profile.get('representative_description') or '').strip()}"
            )
    if items:
        lines.append("逐股归纳：")
        for item in items:
            if not isinstance(item, dict):
                continue
            label = f"{str(item.get('stock_name') or '').strip()}（{str(item.get('sector') or '').strip() or '自选股'}）"
            body = str(item.get("analysis_text") or "").strip()
            if label or body:
                lines.append(f"- {label}：{body}")
    return "\n".join(line for line in lines if line).strip()


def compose_review_structured_preview(
    source_text,
    review_period="",
    source_mode="",
    selected_watchlist=None,
    speaker_name="",
    entry_point="",
    tenant_slug="",
    job_code="",
):
    normalized_source = str(source_text or "").strip()
    if not normalized_source:
        raise ValueError("review_source_text_required")
    watchlist_items = [str(item).strip() for item in (selected_watchlist or []) if str(item).strip()]
    if not watchlist_items:
        raise ValueError("review_selected_watchlist_required")
    if job_code:
        report_user_async_job_progress(
            job_code,
            stage="review_summary_generating",
            percent=24,
            summary="正在生成复盘摘要",
            log_text="摘要仅基于用户自主输入内容生成，不引用自选股归纳。",
        )
    summary_result = summarize_review_user_input_with_llm(
        source_text=normalized_source,
        review_period=review_period,
        source_mode=source_mode,
        speaker_name=speaker_name,
        entry_point=entry_point,
        tenant_slug=tenant_slug,
    )
    if job_code:
        report_user_async_job_progress(
            job_code,
            stage="review_watchlist_analyzing",
            percent=46,
            summary="正在归纳自选股与板块代表性",
            log_text="将按已选自选股归并板块，并生成逐股归纳分析。",
        )
    watchlist_result = analyze_review_watchlist_with_llm(
        selected_watchlist=watchlist_items,
        review_period=review_period,
        source_text=normalized_source,
        speaker_name=speaker_name,
        entry_point=entry_point,
        tenant_slug=tenant_slug,
        job_code=job_code,
    )
    user_input_section = {
        "source_mode": str(source_mode or "").strip().lower() or "manual",
        "source_mode_label": _normalize_review_source_mode_label(source_mode),
        "display_text": normalized_source,
        "summary_source": "llm_user_input_only",
    }
    watchlist_text = _compose_review_watchlist_analysis_text(watchlist_result)
    final_text = "\n\n".join(
        part for part in [
            f"【复盘摘要】\n{summary_result['summary']}",
            f"【用户输入转化内容】\n{user_input_section['display_text']}",
            f"【自选股归纳分析】\n{watchlist_text}" if watchlist_text else "",
        ] if part
    ).strip()
    llm_models = [summary_result.get("llm_model"), watchlist_result.get("llm_model")]
    result = {
        "review_summary": summary_result["summary"],
        "user_input_section": user_input_section,
        "watchlist_analysis_section": {
            "sector_summary": str(watchlist_result.get("sector_summary") or "").strip(),
            "sector_profiles": copy.deepcopy(watchlist_result.get("sector_profiles") or []),
            "items": copy.deepcopy(watchlist_result.get("items") or []),
        },
        "final_text": final_text,
        "llm_models": [item for item in llm_models if isinstance(item, dict)],
        "watchlist_workflow_meta": copy.deepcopy(watchlist_result.get("workflow_meta") or {}),
    }
    if job_code:
        report_user_async_job_progress(
            job_code,
            stage="review_preview_ready",
            percent=92,
            summary="双段式复盘预览已准备完成",
            log_text="用户输入部分和自选股归纳部分已合成，正在返回预览结果。",
        )
    return result


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
    graph_profile = build_knowledge_graph_artifact(
        {
            "id": next_id,
            "type": normalized_type,
            "title": normalized_title,
            "summary": processed_summary,
            "body": processed_body,
            "raw_input": normalized_body,
            "source_detail": normalized_source_detail,
            "tags": normalized_tags,
            "key_points": [str(point).strip() for point in (processed_content.get("key_points") if isinstance(processed_content.get("key_points"), list) else []) if str(point).strip()][:8],
            "validation_nodes": [str(point).strip() for point in (processed_content.get("validation_nodes") if isinstance(processed_content.get("validation_nodes"), list) else []) if str(point).strip()][:8],
            "notes": str(notes or "").strip(),
        },
        tenant_slug=tenant_slug,
        tenant_name=tenant.get("name") or tenant_slug,
    )
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
            "graph_profile": graph_profile,
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
        "graph_profile": graph_profile,
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
    graph_profile = metadata.get("graph_profile") if isinstance(metadata.get("graph_profile"), dict) else build_knowledge_graph_artifact(
        {
            "id": str(record.get("knowledge_id") or config_item.get("id") or "").strip(),
            "type": item_type,
            "title": title_text,
            "summary": summary_text,
            "body": body_text,
            "raw_input": str(config_item.get("raw_input") or body_text).strip(),
            "source_detail": str(record.get("source_detail") or config_item.get("source_detail") or "").strip(),
            "tags": config_item.get("tags") if isinstance(config_item.get("tags"), list) else [],
            "key_points": config_item.get("key_points") if isinstance(config_item.get("key_points"), list) else [],
            "validation_nodes": config_item.get("validation_nodes") if isinstance(config_item.get("validation_nodes"), list) else [],
            "notes": notes_text,
        },
        tenant_slug=str(metadata.get("tenant_slug") or config_item.get("tenant_slug") or "").strip(),
        tenant_name=str(metadata.get("tenant_name") or config_item.get("tenant_name") or "").strip(),
    )
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
        "graph_profile": copy.deepcopy(graph_profile) if isinstance(graph_profile, dict) else {},
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
    return _build_retrieval_agent_response(
        tenant_slug=tenant_slug,
        query_text=query_text,
        limit=limit,
        submit_to_model=submit_to_model,
        source_types=source_types,
        entry_point=entry_point,
        feature_namespace=feature_namespace,
        workflow_definition=build_default_evidence_chain_workflow_definition(),
    )


def build_knowledge_query_response(tenant_slug, query_text, limit=5, submit_to_model=False):
    result = _build_retrieval_agent_response(
        tenant_slug=tenant_slug,
        query_text=query_text,
        limit=limit,
        submit_to_model=submit_to_model,
        source_types=["knowledge"],
        entry_point="knowledge_query",
        feature_namespace="knowledge_query",
        workflow_definition=build_default_knowledge_query_workflow_definition(),
    )
    result["matches"] = copy.deepcopy(result.get("evidence_items") or [])
    return result


def _build_retrieval_agent_response(
    tenant_slug,
    query_text,
    limit=5,
    submit_to_model=False,
    source_types=None,
    entry_point="evidence_chain",
    feature_namespace="evidence_chain",
    workflow_definition=None,
):
    workflow_definition = normalize_declared_agent_workflow_definition(
        workflow_definition or build_default_evidence_chain_workflow_definition()
    )
    answer_feature_label = "知识问答生成" if workflow_definition.get("id") == "knowledge_query_agent" else "证据链问答生成"

    def _retrieval_input_executor(state, runtime, node, upstream):
        normalized_query = str(runtime.get("query_text") or "").strip()
        if not normalized_query:
            raise ValueError("evidence_query_required")
        normalized_sources = normalize_evidence_source_types(runtime.get("source_types"))
        return {
            "detail": "已接收检索问题与来源范围。",
            "state_updates": {
                "normalized_query": normalized_query,
                "normalized_sources": normalized_sources,
                "llm_requested": bool(runtime.get("submit_to_model")),
            },
            "context_preview": {
                "query_chars": len(normalized_query),
                "source_count": len(normalized_sources),
            },
        }

    def _retrieval_fetch_executor(state, runtime, node, upstream):
        try:
            result = search_evidence_chain(
                tenant_slug=str(runtime.get("tenant_slug") or "").strip(),
                query_text=state.get("normalized_query") or "",
                limit=runtime.get("limit") or 5,
                source_types=state.get("normalized_sources") or [],
            )
        except Exception as exc:
            if not is_db_unavailable_error(exc) and not isinstance(exc, RuntimeError):
                raise
            app.logger.warning("Retrieval agent dependency unavailable, using empty fallback result: %s", str(exc)[:200])
            result = {
                "query": state.get("normalized_query") or "",
                "answer": "当前检索依赖暂不可用，已回退为空结果。请稍后重试。",
                "evidence_items": [],
                "matches": [],
                "source_types": copy.deepcopy(state.get("normalized_sources") or []),
                "source_summaries": [],
                "unsupported_source_types": [],
            }
        return {
            "detail": f"已召回 {len(result.get('evidence_items') or [])} 条候选结果。",
            "state_updates": {"retrieval_result": result},
            "context_preview": {"match_count": len(result.get("evidence_items") or [])},
        }

    def _retrieval_filter_executor(state, runtime, node, upstream):
        result = copy.deepcopy(state.get("retrieval_result") or {})
        llm_requested = bool(state.get("llm_requested"))
        if not llm_requested:
            return {
                "status": "skipped",
                "detail": "未提交给大模型，保留原始召回结果。",
                "state_updates": {
                    "filtered_result": result,
                    "llm_notice": "当前为纯知识检索模式，未提交给大模型。",
                    "llm_mode": "retrieval_only",
                    "llm_enabled": False,
                    "llm_model": None,
                },
                "context_preview": {"filtered": False, "kept_count": len(result.get("evidence_items") or [])},
            }
        llm_model = get_default_llm_config(purpose="general")
        if not llm_model:
            return {
                "status": "skipped",
                "detail": "当前没有可用模型，已回退到纯检索。",
                "state_updates": {
                    "filtered_result": result,
                    "llm_notice": "已勾选提交给大模型，但当前没有可用的通用模型配置，已自动回退到纯知识检索模式。",
                    "llm_mode": "fallback_retrieval",
                    "llm_enabled": False,
                    "llm_model": None,
                },
                "context_preview": {"filtered": False, "kept_count": len(result.get("evidence_items") or [])},
            }
        original_matches = result.get("evidence_items") or []
        try:
            filtered_matches, filter_meta, filter_model = filter_knowledge_matches_with_llm(
                query_text=result.get("query"),
                matches=original_matches,
                tenant_slug=str(runtime.get("tenant_slug") or "").strip(),
            )
            active_model = filter_model or llm_model
            result["evidence_items"] = filtered_matches
            result["matches"] = copy.deepcopy(filtered_matches)
            llm_notice = (
                f"已先用通用模型过滤知识召回结果，保留 {filter_meta.get('kept_count', 0)} 条，"
                f"过滤掉 {filter_meta.get('dropped_count', 0)} 条无关内容。"
            ) if filter_meta.get("filtered") else "已勾选提交给大模型，当前未启用额外过滤，直接基于召回结果生成回答。"
            if filter_meta.get("reason"):
                llm_notice = f"{llm_notice} {filter_meta.get('reason')}".strip()
            return {
                "detail": f"已完成相关性过滤，保留 {len(filtered_matches)} 条结果。",
                "state_updates": {
                    "filtered_result": result,
                    "llm_notice": llm_notice,
                    "llm_mode": "filtered",
                    "llm_enabled": False,
                    "llm_model": {
                        "key": active_model.get("key"),
                        "label": active_model.get("label"),
                        "provider": active_model.get("provider"),
                        "model_name": active_model.get("model_name"),
                        "purpose": active_model.get("purpose"),
                    },
                },
                "context_preview": {
                    "filtered": True,
                    "kept_count": len(filtered_matches),
                    "dropped_count": max(0, len(original_matches) - len(filtered_matches)),
                },
            }
        except Exception as exc:
            result["evidence_items"] = original_matches
            result["matches"] = copy.deepcopy(original_matches)
            return {
                "status": "error",
                "detail": "相关性过滤失败，已回退到原始召回结果。",
                "state_updates": {
                    "filtered_result": result,
                    "llm_notice": f"相关性过滤调用失败，已回退到原始召回结果：{str(exc)}",
                    "llm_mode": "fallback_retrieval",
                    "llm_enabled": False,
                    "llm_model": {
                        "key": llm_model.get("key"),
                        "label": llm_model.get("label"),
                        "provider": llm_model.get("provider"),
                        "model_name": llm_model.get("model_name"),
                        "purpose": llm_model.get("purpose"),
                    },
                },
                "context_preview": {"filtered": False, "kept_count": len(original_matches)},
            }

    def _retrieval_answer_executor(state, runtime, node, upstream):
        result = copy.deepcopy(state.get("filtered_result") or state.get("retrieval_result") or {})
        llm_requested = bool(state.get("llm_requested"))
        llm_model = copy.deepcopy(state.get("llm_model") or {})
        llm_notice = str(state.get("llm_notice") or "当前为纯知识检索模式，未提交给大模型。").strip()
        llm_enabled = bool(state.get("llm_enabled"))
        llm_mode = str(state.get("llm_mode") or "retrieval_only").strip() or "retrieval_only"
        if llm_requested and llm_model:
            filtered_matches = result.get("evidence_items") or []
            if not filtered_matches:
                llm_enabled = True
                llm_mode = "model_filtered_empty"
                result["answer"] = "当前召回结果经过大模型过滤后，没有发现与问题直接相关的知识条目。"
            else:
                system_prompt, user_prompt = build_evidence_chain_chat_prompts(
                    query_text=result.get("query"),
                    evidence_items=filtered_matches,
                    tenant_slug=str(runtime.get("tenant_slug") or "").strip(),
                )
                try:
                    answer_model = normalize_llm_model_config(llm_model)
                    llm_answer = call_openai_compatible_llm(
                        answer_model,
                        system_prompt,
                        user_prompt,
                        feature_code=f"{runtime.get('feature_namespace')}_answer",
                        feature_label=answer_feature_label,
                        tenant_slug=str(runtime.get("tenant_slug") or "").strip(),
                        entry_point=str(runtime.get("entry_point") or "").strip(),
                        metadata={
                            "match_count": len(filtered_matches),
                            "submit_to_model": True,
                            "workflow_id": workflow_definition["id"],
                        },
                        request_timeout_seconds=get_evidence_chain_config().get("answer_timeout_seconds", 45),
                    )
                    result["answer"] = llm_answer
                    llm_enabled = True
                    llm_mode = "model_answered"
                    llm_notice = (
                        f"{llm_notice}\n\n"
                        f"当前回答已由通用模型生成：{answer_model.get('label') or answer_model.get('model_name') or answer_model.get('key')}。"
                        "下方保留的是过滤后的相关知识命中结果。"
                    ).strip()
                except Exception as exc:
                    llm_enabled = False
                    llm_mode = "fallback_retrieval"
                    llm_notice = f"{llm_notice}\n\n已尝试调用通用模型生成回答，但失败并回退到纯知识检索：{str(exc)}".strip()
        return {
            "detail": "已完成结果回答整合。",
            "state_updates": {
                "final_result": {
                    **result,
                    "submit_to_model": llm_requested,
                    "llm_enabled": llm_enabled,
                    "llm_mode": llm_mode,
                    "llm_notice": llm_notice,
                    "llm_model": llm_model or None,
                }
            },
            "context_preview": {
                "answer_chars": len(str(result.get("answer") or "")),
                "llm_mode": llm_mode,
            },
        }

    def _retrieval_output_executor(state, runtime, node, upstream):
        return {
            "detail": "已封装检索智能体结果。",
            "state_updates": {
                "final_result": copy.deepcopy(state.get("final_result") or {})
            },
            "context_preview": {
                "match_count": len(((state.get("final_result") or {}).get("evidence_items") or [])),
                "llm_enabled": bool((state.get("final_result") or {}).get("llm_enabled")),
            },
        }

    execution = run_declared_agent_workflow(
        workflow_definition,
        runtime={
            "tenant_slug": tenant_slug,
            "query_text": query_text,
            "limit": limit,
            "submit_to_model": submit_to_model,
            "source_types": source_types,
            "entry_point": entry_point,
            "feature_namespace": feature_namespace,
        },
        executor_registry={
            "knowledge_query_input": _retrieval_input_executor,
            "knowledge_query_retrieval": _retrieval_fetch_executor,
            "knowledge_query_filter": _retrieval_filter_executor,
            "knowledge_query_answer": _retrieval_answer_executor,
            "knowledge_query_output": _retrieval_output_executor,
            "evidence_query_input": _retrieval_input_executor,
            "evidence_query_retrieval": _retrieval_fetch_executor,
            "evidence_query_filter": _retrieval_filter_executor,
            "evidence_query_answer": _retrieval_answer_executor,
            "evidence_query_output": _retrieval_output_executor,
        },
    )
    final_result = copy.deepcopy(execution["state"].get("final_result") or {})
    final_result["workflow_meta"] = build_declared_agent_workflow_meta(
        workflow_definition,
        extras={"last_execution_steps": copy.deepcopy(execution.get("node_results") or {})},
    )
    return final_result


HERMES_QUERY_INTENT_PROMPT = (
    "你是 Hermes 的任务路由器。"
    "你的职责不是直接回答用户，而是把用户问题路由成最合适的任务类型，并决定需要调用哪些工具。"
    "只能从给定枚举里选择 intent 和 tools。"
    "禁止编造工具名。"
    "输出必须是 JSON。"
)

HERMES_ALLOWED_INTENTS = {
    "small_talk",
    "product_help",
    "knowledge_lookup",
    "evidence_chain_analysis",
    "watchlist_fundamental",
    "smart_indicator_explain",
    "dashboard_interpretation",
    "multi_tool_research",
    "out_of_scope_redirect",
}

HERMES_ALLOWED_TOOLS = {
    "knowledge.search",
    "evidence.search",
    "watchlist.detail",
    "dashboard.context",
    "attachment.context",
    "web.search",
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


HERMES_SCOPE_KEYWORDS = {
    "watchlist": ["股票", "个股", "自选股", "基本面", "估值", "盈利", "财报", "行业位置", "港股", "a股", "美股"],
    "evidence": ["复盘", "证据链", "证据", "依据", "来源", "纪要", "逻辑链"],
    "knowledge": ["知识库", "知识", "框架", "方法", "研报", "材料", "纪要速读", "方法论"],
    "indicator": ["智能指标", "指标", "公式", "提示词", "算法", "js", "计算", "引用指标"],
    "dashboard": ["dashboard", "看板", "面板", "卡片", "2x2", "2x3", "4x2", "布局"],
    "product": ["功能", "页面", "按钮", "工作台", "专区", "上传", "发布", "预览", "后台", "admin", "h5", "web", "怎么用", "如何用"],
}

HERMES_SMALL_TALK_KEYWORDS = [
    "你好", "您好", "hi", "hello", "在吗", "谢谢", "感谢", "辛苦了", "早上好", "晚上好", "午安",
]

HERMES_BLOCKED_TRADING_KEYWORDS = [
    "买入", "卖出", "梭哈", "满仓", "半仓", "仓位", "止盈", "止损", "带单", "喊单", "荐股", "财富密码",
    "明天买", "今天买", "直接买", "直接卖", "短线暴富",
]

HERMES_OUT_OF_SCOPE_KEYWORDS = [
    "天气", "菜谱", "做饭", "旅游", "酒店", "机票", "情书", "简历", "面试题", "数学作业", "翻译论文", "法律诉状",
    "看病", "减肥", "星座", "宠物", "装修", "游戏攻略", "八卦新闻",
]

HERMES_PRODUCT_ACTION_KEYWORDS = ["怎么", "如何", "创建", "新增", "发布", "预览", "修改", "配置", "上传", "切换", "打开", "进入", "使用"]


def _contains_any_keyword(text, keywords):
    normalized = str(text or "").strip().lower()
    for item in keywords:
        keyword = str(item or "").strip().lower()
        if keyword and keyword in normalized:
            return True
    return False


def _hermes_scope_feature_flags(question_text, selected_knowledge_ids=None, attachments=None):
    selected_knowledge_ids = selected_knowledge_ids if isinstance(selected_knowledge_ids, list) else []
    attachments = attachments if isinstance(attachments, list) else []
    text = str(question_text or "").strip()
    flags = {
        "watchlist": bool(find_watchlist_code_from_text(text)) or _contains_any_keyword(text, HERMES_SCOPE_KEYWORDS["watchlist"]),
        "evidence": _contains_any_keyword(text, HERMES_SCOPE_KEYWORDS["evidence"]),
        "knowledge": bool(selected_knowledge_ids) or _contains_any_keyword(text, HERMES_SCOPE_KEYWORDS["knowledge"]),
        "indicator": _contains_any_keyword(text, HERMES_SCOPE_KEYWORDS["indicator"]),
        "dashboard": _contains_any_keyword(text, HERMES_SCOPE_KEYWORDS["dashboard"]),
        "product": _contains_any_keyword(text, HERMES_SCOPE_KEYWORDS["product"]),
        "attachments": bool(attachments),
        "small_talk": _contains_any_keyword(text, HERMES_SMALL_TALK_KEYWORDS),
        "blocked_trading": _contains_any_keyword(text, HERMES_BLOCKED_TRADING_KEYWORDS),
        "out_of_scope": _contains_any_keyword(text, HERMES_OUT_OF_SCOPE_KEYWORDS),
    }
    flags["platform_related"] = any(
        flags[key]
        for key in ["watchlist", "evidence", "knowledge", "indicator", "dashboard", "product", "attachments"]
    )
    return flags


def hermes_scope_guard(question_text, selected_knowledge_ids=None, attachments=None):
    text = str(question_text or "").strip()
    flags = _hermes_scope_feature_flags(
        question_text=text,
        selected_knowledge_ids=selected_knowledge_ids,
        attachments=attachments,
    )
    suggestions = [
        "可以改问个股 / 自选股基本面。",
        "也可以改问复盘依据、知识框架或智能指标。",
        "如果想问功能使用，直接说页面或操作目标即可。",
    ]
    if flags["blocked_trading"] and (flags["watchlist"] or "股票" in text or "大盘" in text or "指数" in text):
        return {
            "status": "blocked",
            "reason": "当前问题更像直接交易指令或仓位建议，超出 Hermes 的服务边界。",
            "message": "Hermes 不直接提供买卖、仓位或喊单式指令。你可以改问标的的基本面、证据链、风险边界或跟踪变量。",
            "suggestions": suggestions,
            "intent_hint": "out_of_scope_redirect",
            "flags": flags,
        }
    if flags["platform_related"]:
        intent_hint = "knowledge_lookup"
        if flags["product"] and _contains_any_keyword(text, HERMES_PRODUCT_ACTION_KEYWORDS):
            intent_hint = "product_help"
        elif flags["indicator"] and not flags["dashboard"]:
            intent_hint = "smart_indicator_explain"
        elif flags["dashboard"]:
            intent_hint = "dashboard_interpretation"
        elif flags["product"]:
            intent_hint = "product_help"
        elif flags["watchlist"]:
            intent_hint = "watchlist_fundamental"
        elif flags["evidence"]:
            intent_hint = "evidence_chain_analysis"
        return {
            "status": "allowed",
            "reason": "问题落在 Hermes 的研究或产品能力范围内。",
            "message": "",
            "suggestions": suggestions,
            "intent_hint": intent_hint,
            "flags": flags,
        }
    if flags["small_talk"]:
        return {
            "status": "soft_allowed",
            "reason": "识别为轻度闲聊或寒暄，可保留简短对话。",
            "message": "",
            "suggestions": [
                "如果继续聊研究内容，可以直接补股票、复盘或指标对象。",
                "也可以问某个功能怎么用。",
            ],
            "intent_hint": "small_talk",
            "flags": flags,
        }
    redirect_reason = "当前问题没有落在平台研究、复盘、知识、智能指标或产品使用范围内。"
    if flags["out_of_scope"]:
        redirect_reason = "当前问题更偏生活化或通用百科，不属于 Hermes 的主要服务范围。"
    return {
        "status": "redirected",
        "reason": redirect_reason,
        "message": "Hermes 主要回答个股/自选股、复盘证据链、知识框架、智能指标和平台功能使用相关问题。你可以换成这些方向继续问。",
        "suggestions": suggestions,
        "intent_hint": "out_of_scope_redirect",
        "flags": flags,
    }


HERMES_FUNCTION_TAG_MAP = {
    "small_talk": ["闲聊"],
    "product_help": ["产品帮助"],
    "knowledge_lookup": ["知识"],
    "evidence_chain_analysis": ["证据链", "复盘"],
    "watchlist_fundamental": ["个股"],
    "smart_indicator_explain": ["指标"],
    "dashboard_interpretation": ["Dashboard", "指标"],
    "multi_tool_research": ["个股", "知识", "证据链"],
    "out_of_scope_redirect": ["超范围收口"],
}

HERMES_STYLE_KEYWORDS = {
    "结构化偏好": ["结构化", "分点", "拆开", "按步骤", "按模块"],
    "摘要偏好": ["摘要", "概括", "一句话", "简短", "直接结论", "先给结论"],
    "短线": ["短线", "日内", "明天", "今天", "本周"],
    "中线": ["中线", "波段", "一两个月", "季度"],
    "长期": ["长期", "一年", "长线", "长期跟踪"],
    "保守": ["稳健", "保守", "防守", "低风险"],
    "激进": ["激进", "进攻", "高弹性", "高波动"],
}

HERMES_TOPIC_KEYWORDS = {
    "港股互联网": ["港股", "互联网", "腾讯", "阿里", "美团"],
    "AI算力": ["ai", "算力", "gpu", "服务器", "光模块"],
    "半导体": ["半导体", "芯片", "中芯国际"],
    "消费": ["消费", "白酒", "贵州茅台"],
    "宏观流动性": ["宏观", "流动性", "降息", "美联储", "cpi"],
    "复盘方法": ["复盘", "证据链", "依据", "纪要"],
    "智能指标": ["智能指标", "提示词", "公式", "dashboard", "看板"],
}

HERMES_MARKET_KEYWORDS = {
    "A股": ["a股", "上证", "深证", "创业板"],
    "港股": ["港股", "恒生", "腾讯", "美团", "阿里"],
    "美股": ["美股", "纳斯达克", "标普", "道琼斯", "apple", "tesla", "nvda"],
}

HERMES_RESPONSE_STYLE_PRIORITY = ["结构化偏好", "摘要偏好", "长期", "中线", "短线", "保守", "激进"]


def _hermes_unique_texts(items, limit=12):
    result = []
    seen = set()
    for item in items if isinstance(items, list) else []:
        value = re.sub(r"\s+", " ", str(item or "").strip())
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= max(1, int(limit or 12)):
            break
    return result


def _hermes_json_text(value, fallback):
    return json.dumps(value if value is not None else fallback, ensure_ascii=False)


def _hermes_trim_text(value, limit=240):
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= max(1, int(limit or 240)):
        return text
    return f"{text[:max(0, int(limit or 240) - 1)]}…"


def _clamp_score(value, minimum=0, maximum=100):
    try:
        numeric = int(value)
    except Exception:
        numeric = minimum
    return max(minimum, min(maximum, numeric))


def resolve_hermes_actor_context(payload, tenant_slug="", user_role=""):
    source = payload if isinstance(payload, dict) else {}
    current_profile = None
    if has_request_context():
        try:
            current_profile = get_current_demo_profile()
        except Exception:
            current_profile = None
    normalized_role = str(source.get("user_role") or user_role or (current_profile or {}).get("role") or "investor").strip().lower() or "investor"
    profile_id = str(source.get("user_profile_id") or (current_profile or {}).get("username") or "").strip()
    if not profile_id:
        profile_id = f"{normalized_role or 'guest'}_guest"
    display_name = str(source.get("user_name") or (current_profile or {}).get("name") or (current_profile or {}).get("username") or profile_id).strip() or profile_id
    membership = str(source.get("user_membership") or (current_profile or {}).get("membership") or "").strip()
    tenant = (current_profile or {}).get("tenant") if isinstance((current_profile or {}).get("tenant"), dict) else {}
    return {
        "tenant_slug": str(tenant_slug or tenant.get("slug") or "").strip().lower(),
        "user_role": normalized_role,
        "profile_id": profile_id,
        "display_name": display_name,
        "membership": membership,
        "is_anonymous": profile_id.endswith("_guest"),
    }


def resolve_hermes_session_id(payload, actor_context=None):
    source = payload if isinstance(payload, dict) else {}
    provided = slugify_code(source.get("session_id"), "")
    if provided:
        return provided
    actor = actor_context if isinstance(actor_context, dict) else {}
    base = "|".join([
        str(actor.get("tenant_slug") or "").strip().lower(),
        str(actor.get("profile_id") or "").strip().lower(),
        str(actor.get("user_role") or "").strip().lower(),
    ])
    digest = hashlib.md5(base.encode("utf-8")).hexdigest()[:16] if base else hashlib.md5(now_ts_ms().encode("utf-8")).hexdigest()[:16]
    return f"hermes_session_{digest}"


def _extract_json_text_field(row, key, default):
    if not isinstance(row, dict):
        return copy.deepcopy(default)
    value = row.get(key)
    if isinstance(default, dict):
        return safe_json_loads(value, {})
    if isinstance(default, list):
        return safe_json_loads(value, [])
    return str(value or "").strip()


def _load_hermes_db_rows(actor_context, session_id, limit=6):
    actor = actor_context if isinstance(actor_context, dict) else {}
    tenant_slug = str(actor.get("tenant_slug") or "").strip().lower()
    profile_id = str(actor.get("profile_id") or "").strip()
    result = {
        "session": None,
        "user_memory": None,
        "user_profile": None,
        "recent_turns": [],
    }
    if not tenant_slug or not session_id:
        return result
    db = get_db()
    result["session"] = db.execute(
        """
        SELECT session_id, tenant_slug, user_profile_id, user_role, user_display_name, turn_count,
               recent_topics_json, recent_symbols_json, recent_intents_json, working_memory_json,
               summary_text, last_intent, last_tags_json, first_seen_at, last_seen_at
        FROM hermes_session_memory
        WHERE tenant_slug = ? AND session_id = ?
        """,
        (tenant_slug, session_id),
    ).fetchone()
    if profile_id:
        result["user_memory"] = db.execute(
            """
            SELECT tenant_slug, user_profile_id, user_role, user_display_name, total_turns, last_session_id,
                   fact_memory_json, working_memory_json, recent_topics_json, focus_symbols_json,
                   last_tags_json, preferred_response_style, preferred_intents_json, created_at, updated_at
            FROM hermes_user_memory
            WHERE tenant_slug = ? AND user_profile_id = ?
            """,
            (tenant_slug, profile_id),
        ).fetchone()
        result["user_profile"] = db.execute(
            """
            SELECT tenant_slug, user_profile_id, user_role, user_display_name, persona_primary, persona_secondary,
                   interest_topics_json, focus_symbols_json, function_tags_json, behavior_tags_json,
                   style_tags_json, commercial_tags_json, intent_distribution_json, research_depth_score,
                   engagement_score, conversion_signal_score, total_queries, last_intent, last_scope_status,
                   last_activity_at, metadata_json, created_at, updated_at
            FROM hermes_user_profiles
            WHERE tenant_slug = ? AND user_profile_id = ?
            """,
            (tenant_slug, profile_id),
        ).fetchone()
    result["recent_turns"] = db.execute(
        """
        SELECT turn_id, question_text, answer_summary, intent, scope_status, tags_json, created_at
        FROM hermes_conversation_turns
        WHERE tenant_slug = ? AND session_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (tenant_slug, session_id, max(1, int(limit or 6))),
    ).fetchall()
    return result


def build_hermes_memory_context_text(memory_state):
    snapshot = memory_state if isinstance(memory_state, dict) else {}
    session = snapshot.get("session") if isinstance(snapshot.get("session"), dict) else {}
    user_memory = snapshot.get("user_memory") if isinstance(snapshot.get("user_memory"), dict) else {}
    user_profile = snapshot.get("user_profile") if isinstance(snapshot.get("user_profile"), dict) else {}
    recent_turns = snapshot.get("recent_turns") if isinstance(snapshot.get("recent_turns"), list) else []
    parts = []
    persona_primary = str(user_profile.get("persona_primary") or "").strip()
    if persona_primary:
        parts.append(f"用户主定位：{persona_primary}")
    interest_topics = _hermes_unique_texts((user_profile.get("interest_topics") or user_memory.get("recent_topics") or []), limit=4)
    if interest_topics:
        parts.append("长期关注主题：" + " / ".join(interest_topics))
    focus_symbols = _hermes_unique_texts((user_profile.get("focus_symbols") or user_memory.get("focus_symbols") or []), limit=4)
    if focus_symbols:
        parts.append("重点关注对象：" + " / ".join(focus_symbols))
    preferred_style = str(user_memory.get("preferred_response_style") or "").strip()
    if preferred_style:
        parts.append(f"回答偏好：{preferred_style}")
    recent_topics = _hermes_unique_texts(session.get("recent_topics") or [], limit=3)
    if recent_topics:
        parts.append("当前会话最近主题：" + " / ".join(recent_topics))
    turn_summaries = []
    for item in recent_turns[:3]:
        if not isinstance(item, dict):
            continue
        question = _hermes_trim_text(item.get("question_text"), limit=48)
        answer_summary = _hermes_trim_text(item.get("answer_summary"), limit=60)
        if question:
            turn_summaries.append(f"Q:{question} | A:{answer_summary}")
    if turn_summaries:
        parts.append("最近追问：" + " || ".join(turn_summaries))
    return "\n".join(parts)


def load_hermes_memory_state(actor_context, session_id, limit=6):
    actor = actor_context if isinstance(actor_context, dict) else {}
    fallback = {
        "available": False,
        "storage_mode": "memoryless_fallback",
        "session_id": session_id,
        "session": {
            "turn_count": 0,
            "recent_topics": [],
            "recent_symbols": [],
            "recent_intents": [],
            "working_memory": {},
            "summary_text": "",
            "last_intent": "",
            "last_tags": {},
        },
        "user_memory": {
            "total_turns": 0,
            "fact_memory": {},
            "working_memory": {},
            "recent_topics": [],
            "focus_symbols": [],
            "last_tags": {},
            "preferred_response_style": "",
            "preferred_intents": [],
        },
        "user_profile": {
            "persona_primary": "",
            "persona_secondary": "",
            "interest_topics": [],
            "focus_symbols": [],
            "function_tags": [],
            "behavior_tags": [],
            "style_tags": [],
            "commercial_tags": [],
            "intent_distribution": {},
            "research_depth_score": 0,
            "engagement_score": 0,
            "conversion_signal_score": 0,
            "total_queries": 0,
            "last_intent": "",
            "last_scope_status": "",
            "last_activity_at": "",
            "metadata": {},
        },
        "recent_turns": [],
        "context_text": "",
        "actor": copy.deepcopy(actor),
    }
    if not str(actor.get("tenant_slug") or "").strip() or not str(session_id or "").strip():
        return fallback
    try:
        rows = _load_hermes_db_rows(actor_context=actor, session_id=session_id, limit=limit)
        session_row = rows.get("session") if isinstance(rows.get("session"), dict) else {}
        user_memory_row = rows.get("user_memory") if isinstance(rows.get("user_memory"), dict) else {}
        user_profile_row = rows.get("user_profile") if isinstance(rows.get("user_profile"), dict) else {}
        recent_turns = []
        for item in rows.get("recent_turns") or []:
            if not isinstance(item, dict):
                continue
            recent_turns.append({
                "turn_id": str(item.get("turn_id") or "").strip(),
                "question_text": str(item.get("question_text") or "").strip(),
                "answer_summary": str(item.get("answer_summary") or "").strip(),
                "intent": str(item.get("intent") or "").strip(),
                "scope_status": str(item.get("scope_status") or "").strip(),
                "tags": _extract_json_text_field(item, "tags_json", {}),
                "created_at": str(item.get("created_at") or "").strip(),
            })
        state = {
            "available": True,
            "storage_mode": "db",
            "session_id": session_id,
            "session": {
                "turn_count": int(session_row.get("turn_count") or 0),
                "recent_topics": _extract_json_text_field(session_row, "recent_topics_json", []),
                "recent_symbols": _extract_json_text_field(session_row, "recent_symbols_json", []),
                "recent_intents": _extract_json_text_field(session_row, "recent_intents_json", []),
                "working_memory": _extract_json_text_field(session_row, "working_memory_json", {}),
                "summary_text": str(session_row.get("summary_text") or "").strip(),
                "last_intent": str(session_row.get("last_intent") or "").strip(),
                "last_tags": _extract_json_text_field(session_row, "last_tags_json", {}),
                "first_seen_at": str(session_row.get("first_seen_at") or "").strip(),
                "last_seen_at": str(session_row.get("last_seen_at") or "").strip(),
            },
            "user_memory": {
                "total_turns": int(user_memory_row.get("total_turns") or 0),
                "fact_memory": _extract_json_text_field(user_memory_row, "fact_memory_json", {}),
                "working_memory": _extract_json_text_field(user_memory_row, "working_memory_json", {}),
                "recent_topics": _extract_json_text_field(user_memory_row, "recent_topics_json", []),
                "focus_symbols": _extract_json_text_field(user_memory_row, "focus_symbols_json", []),
                "last_tags": _extract_json_text_field(user_memory_row, "last_tags_json", {}),
                "preferred_response_style": str(user_memory_row.get("preferred_response_style") or "").strip(),
                "preferred_intents": _extract_json_text_field(user_memory_row, "preferred_intents_json", []),
                "last_session_id": str(user_memory_row.get("last_session_id") or "").strip(),
            },
            "user_profile": {
                "persona_primary": str(user_profile_row.get("persona_primary") or "").strip(),
                "persona_secondary": str(user_profile_row.get("persona_secondary") or "").strip(),
                "interest_topics": _extract_json_text_field(user_profile_row, "interest_topics_json", []),
                "focus_symbols": _extract_json_text_field(user_profile_row, "focus_symbols_json", []),
                "function_tags": _extract_json_text_field(user_profile_row, "function_tags_json", []),
                "behavior_tags": _extract_json_text_field(user_profile_row, "behavior_tags_json", []),
                "style_tags": _extract_json_text_field(user_profile_row, "style_tags_json", []),
                "commercial_tags": _extract_json_text_field(user_profile_row, "commercial_tags_json", []),
                "intent_distribution": _extract_json_text_field(user_profile_row, "intent_distribution_json", {}),
                "research_depth_score": int(user_profile_row.get("research_depth_score") or 0),
                "engagement_score": int(user_profile_row.get("engagement_score") or 0),
                "conversion_signal_score": int(user_profile_row.get("conversion_signal_score") or 0),
                "total_queries": int(user_profile_row.get("total_queries") or 0),
                "last_intent": str(user_profile_row.get("last_intent") or "").strip(),
                "last_scope_status": str(user_profile_row.get("last_scope_status") or "").strip(),
                "last_activity_at": str(user_profile_row.get("last_activity_at") or "").strip(),
                "metadata": _extract_json_text_field(user_profile_row, "metadata_json", {}),
            },
            "recent_turns": recent_turns,
            "actor": copy.deepcopy(actor),
        }
        state["context_text"] = build_hermes_memory_context_text(state)
        return state
    except Exception as exc:
        if has_request_context():
            app.logger.warning("Hermes memory state unavailable, fallback only: %s", str(exc)[:180])
        return fallback


def _detect_hermes_focus_symbols(text, tool_outputs=None):
    normalized = str(text or "").strip()
    symbols = []
    watchlist_detail = (((tool_outputs or {}).get("watchlist") or {}).get("detail") or {}) if isinstance(tool_outputs, dict) else {}
    if isinstance(watchlist_detail, dict) and watchlist_detail:
        name = str(watchlist_detail.get("name") or "").strip()
        code = str(watchlist_detail.get("code") or "").strip()
        if name:
            symbols.append(name)
        if code:
            symbols.append(code)
    try:
        details = gen_watchlist_details()
    except Exception:
        details = {}
    for code, detail in details.items():
        name = str((detail or {}).get("name") or "").strip()
        if name and name in normalized:
            symbols.append(name)
            symbols.append(str(code or "").strip())
    code_match = re.findall(r"\b\d{5,6}\b", normalized)
    symbols.extend(code_match)
    return _hermes_unique_texts(symbols, limit=6)


def _detect_hermes_topics(text, plan=None, tool_outputs=None):
    normalized = str(text or "").strip().lower()
    topics = []
    for topic, keywords in HERMES_TOPIC_KEYWORDS.items():
        if any(str(keyword or "").strip().lower() in normalized for keyword in keywords):
            topics.append(topic)
    dashboard_context = (tool_outputs.get("dashboard_context") or {}) if isinstance(tool_outputs, dict) else {}
    for item in (dashboard_context.get("smart_indicators") or [])[:6]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("indicator_name") or "").strip()
        if name and name.lower() in normalized:
            topics.append(name)
    if str((plan or {}).get("intent") or "").strip() == "dashboard_interpretation":
        topics.append("Dashboard")
    if str((plan or {}).get("intent") or "").strip() == "smart_indicator_explain":
        topics.append("智能指标")
    return _hermes_unique_texts(topics, limit=6)


def _detect_hermes_markets(text):
    normalized = str(text or "").strip().lower()
    markets = []
    for market, keywords in HERMES_MARKET_KEYWORDS.items():
        if any(str(keyword or "").strip().lower() in normalized for keyword in keywords):
            markets.append(market)
    return _hermes_unique_texts(markets, limit=4)


def _detect_hermes_style_tags(question_text, plan=None):
    normalized = str(question_text or "").strip().lower()
    tags = []
    for tag, keywords in HERMES_STYLE_KEYWORDS.items():
        if any(str(keyword or "").strip().lower() in normalized for keyword in keywords):
            tags.append(tag)
    if str((plan or {}).get("display_mode") or "").strip() == "structured" and "结构化偏好" not in tags:
        tags.append("结构化偏好")
    return _hermes_unique_texts(tags, limit=6)


def _resolve_hermes_preferred_response_style(style_tags, existing_value=""):
    values = _hermes_unique_texts(style_tags, limit=6)
    for item in HERMES_RESPONSE_STYLE_PRIORITY:
        if item in values:
            return item
    return str(existing_value or "").strip()


def _compute_hermes_behavior_tags(question_text, plan=None, memory_state=None):
    plan = plan if isinstance(plan, dict) else {}
    memory_state = memory_state if isinstance(memory_state, dict) else {}
    normalized = str(question_text or "").strip().lower()
    previous_session_turns = int(((memory_state.get("session") or {}).get("turn_count") or 0))
    historical_turns = int(((memory_state.get("user_profile") or {}).get("total_queries") or (memory_state.get("user_memory") or {}).get("total_turns") or 0))
    tags = []
    if previous_session_turns == 0 and historical_turns == 0:
        tags.append("首次提问")
    if previous_session_turns > 0:
        tags.append("连续追问")
    if historical_turns >= 5:
        tags.append("高频用户")
    intent = str(plan.get("intent") or "").strip()
    if intent in {"watchlist_fundamental", "knowledge_lookup", "evidence_chain_analysis", "smart_indicator_explain", "dashboard_interpretation", "multi_tool_research"}:
        tags.append("深度研究型")
    if any(keyword in normalized for keyword in ["结论", "一句话", "简短", "先说重点", "摘要"]):
        tags.append("只看结论型")
    return _hermes_unique_texts(tags, limit=6)


def _compute_hermes_commercial_tags(actor_context, behavior_tags, research_depth_score, existing_tags=None):
    actor = actor_context if isinstance(actor_context, dict) else {}
    tags = list(existing_tags if isinstance(existing_tags, list) else [])
    role = str(actor.get("user_role") or "").strip().lower()
    membership = str(actor.get("membership") or "").strip()
    if role == "dav":
        tags.append("大V高频生产用户")
    elif research_depth_score >= 65 or "深度研究型" in behavior_tags:
        tags.append("活跃研究用户")
    else:
        tags.append("普通观察用户")
    if role == "investor" and (research_depth_score >= 75 or membership and any(keyword in membership for keyword in ["专业", "机构", "核心"])):
        tags.append("高价值潜客")
    return _hermes_unique_texts(tags, limit=6)


def _compute_hermes_personas(function_tags, style_tags, actor_context):
    actor = actor_context if isinstance(actor_context, dict) else {}
    role = str(actor.get("user_role") or "").strip().lower()
    if role == "dav":
        primary = "大V研究生产者"
    elif "个股" in function_tags:
        primary = "个股研究型用户"
    elif "证据链" in function_tags or "复盘" in function_tags:
        primary = "证据链复盘用户"
    elif "知识" in function_tags:
        primary = "方法框架型用户"
    elif "产品帮助" in function_tags:
        primary = "功能学习型用户"
    elif "闲聊" in function_tags:
        primary = "轻互动用户"
    else:
        primary = "研究观察用户"
    secondary = ""
    if "结构化偏好" in style_tags:
        secondary = "结构化表达偏好"
    elif "摘要偏好" in style_tags:
        secondary = "摘要结论偏好"
    elif "长期" in style_tags:
        secondary = "长期跟踪偏好"
    elif "中线" in style_tags:
        secondary = "中线研究偏好"
    elif "短线" in style_tags:
        secondary = "短线关注偏好"
    return primary, secondary


def extract_hermes_memory_payload(question_text, plan, synthesis, tool_outputs=None, actor_context=None, memory_state=None):
    plan = plan if isinstance(plan, dict) else {}
    synthesis = synthesis if isinstance(synthesis, dict) else {}
    tool_outputs = tool_outputs if isinstance(tool_outputs, dict) else {}
    actor = actor_context if isinstance(actor_context, dict) else {}
    memory_state = memory_state if isinstance(memory_state, dict) else {}
    question = str(question_text or "").strip()
    answer = str(synthesis.get("answer") or "").strip()
    summary = str(synthesis.get("summary") or "").strip() or _hermes_trim_text(answer, limit=120)
    intent = str(plan.get("intent") or "").strip()
    scope_status = str(plan.get("scope_status") or "allowed").strip() or "allowed"
    function_tags = _hermes_unique_texts(HERMES_FUNCTION_TAG_MAP.get(intent, []), limit=6)
    style_tags = _detect_hermes_style_tags(question, plan=plan)
    behavior_tags = _compute_hermes_behavior_tags(question, plan=plan, memory_state=memory_state)
    topic_tags = _detect_hermes_topics(question, plan=plan, tool_outputs=tool_outputs)
    market_tags = _detect_hermes_markets(question)
    focus_symbols = _detect_hermes_focus_symbols(question, tool_outputs=tool_outputs)
    previous_total = int(((memory_state.get("user_profile") or {}).get("total_queries") or (memory_state.get("user_memory") or {}).get("total_turns") or 0))
    depth_base = {
        "small_talk": 10,
        "product_help": 28,
        "knowledge_lookup": 60,
        "evidence_chain_analysis": 72,
        "watchlist_fundamental": 70,
        "smart_indicator_explain": 64,
        "dashboard_interpretation": 56,
        "multi_tool_research": 82,
        "out_of_scope_redirect": 8,
    }.get(intent, 40)
    research_depth_score = _clamp_score(
        round((((memory_state.get("user_profile") or {}).get("research_depth_score") or 0) * min(previous_total, 6) + depth_base) / max(1, min(previous_total, 6) + 1))
    )
    engagement_score = _clamp_score(20 + min(previous_total + 1, 8) * 8 + (12 if "连续追问" in behavior_tags else 0))
    commercial_tags = _compute_hermes_commercial_tags(
        actor_context=actor,
        behavior_tags=behavior_tags,
        research_depth_score=research_depth_score,
        existing_tags=((memory_state.get("user_profile") or {}).get("commercial_tags") or []),
    )
    conversion_signal_score = _clamp_score(
        18
        + (30 if "高价值潜客" in commercial_tags else 0)
        + (18 if "活跃研究用户" in commercial_tags else 0)
        + (10 if str(actor.get("user_role") or "").strip().lower() == "dav" else 0)
    )
    persona_primary, persona_secondary = _compute_hermes_personas(function_tags, style_tags, actor)
    preferred_response_style = _resolve_hermes_preferred_response_style(
        style_tags,
        existing_value=str((memory_state.get("user_memory") or {}).get("preferred_response_style") or "").strip(),
    )
    intent_distribution = copy.deepcopy((memory_state.get("user_profile") or {}).get("intent_distribution") or {})
    intent_distribution[intent] = int(intent_distribution.get(intent) or 0) + 1
    existing_topics = list((memory_state.get("user_profile") or {}).get("interest_topics") or (memory_state.get("user_memory") or {}).get("recent_topics") or [])
    existing_symbols = list((memory_state.get("user_profile") or {}).get("focus_symbols") or (memory_state.get("user_memory") or {}).get("focus_symbols") or [])
    interest_topics = _hermes_unique_texts(existing_topics + topic_tags + market_tags, limit=12)
    merged_symbols = _hermes_unique_texts(existing_symbols + focus_symbols, limit=12)
    previous_style_tags = list((memory_state.get("user_profile") or {}).get("style_tags") or [])
    previous_behavior_tags = list((memory_state.get("user_profile") or {}).get("behavior_tags") or [])
    previous_function_tags = list((memory_state.get("user_profile") or {}).get("function_tags") or [])
    profile_snapshot = {
        "tenant_slug": str(actor.get("tenant_slug") or "").strip().lower(),
        "user_profile_id": str(actor.get("profile_id") or "").strip(),
        "user_role": str(actor.get("user_role") or "").strip().lower(),
        "user_display_name": str(actor.get("display_name") or "").strip(),
        "persona_primary": persona_primary,
        "persona_secondary": persona_secondary,
        "interest_topics": interest_topics,
        "focus_symbols": merged_symbols,
        "function_tags": _hermes_unique_texts(previous_function_tags + function_tags, limit=12),
        "behavior_tags": _hermes_unique_texts(previous_behavior_tags + behavior_tags, limit=12),
        "style_tags": _hermes_unique_texts(previous_style_tags + style_tags, limit=12),
        "commercial_tags": commercial_tags,
        "intent_distribution": intent_distribution,
        "research_depth_score": research_depth_score,
        "engagement_score": engagement_score,
        "conversion_signal_score": conversion_signal_score,
        "total_queries": previous_total + 1,
        "last_intent": intent,
        "last_scope_status": scope_status,
        "last_activity_at": now_ts(),
        "metadata": {
            "topic_tags": topic_tags,
            "market_tags": market_tags,
            "preferred_response_style": preferred_response_style,
        },
    }
    existing_fact_memory = copy.deepcopy((memory_state.get("user_memory") or {}).get("fact_memory") or {})
    existing_working_memory = copy.deepcopy((memory_state.get("user_memory") or {}).get("working_memory") or {})
    preferred_intents = _hermes_unique_texts(
        list((memory_state.get("user_memory") or {}).get("preferred_intents") or []) + [intent],
        limit=8,
    )
    user_memory_snapshot = {
        "total_turns": int((memory_state.get("user_memory") or {}).get("total_turns") or 0) + 1,
        "last_session_id": str(memory_state.get("session_id") or "").strip(),
        "fact_memory": {
            "interest_topics": interest_topics,
            "focus_symbols": merged_symbols,
            "preferred_response_style": preferred_response_style,
            "preferred_intents": preferred_intents,
            "persona_primary": persona_primary,
        },
        "working_memory": {
            "last_question": _hermes_trim_text(question, limit=180),
            "last_answer_summary": _hermes_trim_text(summary, limit=220),
            "recent_questions": _hermes_unique_texts(
                list(existing_working_memory.get("recent_questions") or []) + [_hermes_trim_text(question, limit=120)],
                limit=4,
            ),
            "recent_topics": _hermes_unique_texts(
                list(existing_working_memory.get("recent_topics") or []) + topic_tags + market_tags,
                limit=6,
            ),
            "recent_symbols": _hermes_unique_texts(
                list(existing_working_memory.get("recent_symbols") or []) + focus_symbols,
                limit=6,
            ),
        },
        "recent_topics": _hermes_unique_texts(list((memory_state.get("user_memory") or {}).get("recent_topics") or []) + topic_tags + market_tags, limit=8),
        "focus_symbols": merged_symbols,
        "last_tags": {
            "function_tags": function_tags,
            "behavior_tags": behavior_tags,
            "style_tags": style_tags,
            "commercial_tags": commercial_tags,
            "topic_tags": topic_tags,
            "market_tags": market_tags,
            "focus_symbols": focus_symbols,
        },
        "preferred_response_style": preferred_response_style,
        "preferred_intents": preferred_intents,
    }
    session_summary = copy.deepcopy((memory_state.get("session") or {}).get("summary_text") or "")
    session_recent_questions = list((((memory_state.get("session") or {}).get("working_memory") or {}).get("recent_questions") or []))
    session_snapshot = {
        "turn_count": int((memory_state.get("session") or {}).get("turn_count") or 0) + 1,
        "recent_topics": _hermes_unique_texts(list((memory_state.get("session") or {}).get("recent_topics") or []) + topic_tags + market_tags, limit=6),
        "recent_symbols": _hermes_unique_texts(list((memory_state.get("session") or {}).get("recent_symbols") or []) + focus_symbols, limit=6),
        "recent_intents": _hermes_unique_texts(list((memory_state.get("session") or {}).get("recent_intents") or []) + [intent], limit=6),
        "working_memory": {
            "recent_questions": _hermes_unique_texts(session_recent_questions + [_hermes_trim_text(question, limit=120)], limit=4),
            "recent_answers": _hermes_unique_texts(list((((memory_state.get("session") or {}).get("working_memory") or {}).get("recent_answers") or [])) + [_hermes_trim_text(summary, limit=140)], limit=4),
            "recent_topics": _hermes_unique_texts(topic_tags + market_tags, limit=6),
            "recent_symbols": _hermes_unique_texts(focus_symbols, limit=6),
        },
        "summary_text": _hermes_trim_text(summary or session_summary or question, limit=220),
        "last_intent": intent,
        "last_tags": {
            "function_tags": function_tags,
            "behavior_tags": behavior_tags,
            "style_tags": style_tags,
            "commercial_tags": commercial_tags,
            "topic_tags": topic_tags,
            "market_tags": market_tags,
            "focus_symbols": focus_symbols,
        },
    }
    turn_tags = {
        "function_tags": function_tags,
        "behavior_tags": behavior_tags,
        "style_tags": style_tags,
        "commercial_tags": commercial_tags,
        "topic_tags": topic_tags,
        "market_tags": market_tags,
        "focus_symbols": focus_symbols,
    }
    return {
        "turn_record": {
            "question_text": question,
            "answer_text": answer,
            "answer_summary": summary,
            "intent": intent,
            "scope_status": scope_status,
            "display_mode": str(plan.get("display_mode") or "text").strip() or "text",
            "preferred_mode": str(plan.get("preferred_mode") or "").strip(),
            "web_answer": bool(plan.get("web_answer")),
            "citations": [str(item).strip() for item in (synthesis.get("citations") if isinstance(synthesis.get("citations"), list) else []) if str(item).strip()][:8],
            "tags": turn_tags,
            "memory_summary": {
                "persona_primary": persona_primary,
                "persona_secondary": persona_secondary,
                "research_depth_score": research_depth_score,
                "engagement_score": engagement_score,
                "conversion_signal_score": conversion_signal_score,
                "interest_topics": interest_topics[:6],
                "focus_symbols": merged_symbols[:6],
            },
        },
        "session_snapshot": session_snapshot,
        "user_memory_snapshot": user_memory_snapshot,
        "profile_snapshot": profile_snapshot,
        "memory_context_text": build_hermes_memory_context_text(
            {
                "session_id": str(memory_state.get("session_id") or "").strip(),
                "session": session_snapshot,
                "user_memory": user_memory_snapshot,
                "user_profile": profile_snapshot,
                "recent_turns": (memory_state.get("recent_turns") or [])[:2],
            }
        ),
        "existing_fact_memory": existing_fact_memory,
    }


def persist_hermes_turn_and_memory(actor_context, session_id, entry_point, memory_payload, tool_trace=None):
    actor = actor_context if isinstance(actor_context, dict) else {}
    payload = memory_payload if isinstance(memory_payload, dict) else {}
    turn_record = payload.get("turn_record") if isinstance(payload.get("turn_record"), dict) else {}
    session_snapshot = payload.get("session_snapshot") if isinstance(payload.get("session_snapshot"), dict) else {}
    user_memory_snapshot = payload.get("user_memory_snapshot") if isinstance(payload.get("user_memory_snapshot"), dict) else {}
    created_at = now_ts()
    turn_id = f"{slugify_code(str(actor.get('profile_id') or 'guest'), 'guest')}_{now_ts_ms().replace(' ', '_').replace(':', '').replace('-', '').replace('.', '')}"
    fallback = {
        "storage_mode": "memoryless_fallback",
        "turn_id": turn_id,
        "session_id": session_id,
        "created_at": created_at,
    }
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO hermes_conversation_turns (
                turn_id, session_id, tenant_slug, user_profile_id, user_role, user_display_name, entry_point,
                question_text, answer_text, answer_summary, intent, scope_status, display_mode, preferred_mode,
                web_answer, citations_json, tool_trace_json, tags_json, memory_summary_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn_id,
                session_id,
                actor.get("tenant_slug") or "",
                actor.get("profile_id") or "",
                actor.get("user_role") or "",
                actor.get("display_name") or "",
                str(entry_point or "").strip(),
                _hermes_trim_text(turn_record.get("question_text"), limit=4000),
                _hermes_trim_text(turn_record.get("answer_text"), limit=8000),
                _hermes_trim_text(turn_record.get("answer_summary"), limit=1200),
                turn_record.get("intent") or "",
                turn_record.get("scope_status") or "",
                turn_record.get("display_mode") or "text",
                turn_record.get("preferred_mode") or "",
                1 if turn_record.get("web_answer") else 0,
                _hermes_json_text(turn_record.get("citations") or [], []),
                _hermes_json_text(tool_trace if isinstance(tool_trace, list) else [], []),
                _hermes_json_text(turn_record.get("tags") or {}, {}),
                _hermes_json_text(turn_record.get("memory_summary") or {}, {}),
                created_at,
            ),
        )
        db.execute(
            """
            INSERT INTO hermes_session_memory (
                session_id, tenant_slug, user_profile_id, user_role, user_display_name, turn_count,
                recent_topics_json, recent_symbols_json, recent_intents_json, working_memory_json, summary_text,
                last_intent, last_tags_json, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                tenant_slug = excluded.tenant_slug,
                user_profile_id = excluded.user_profile_id,
                user_role = excluded.user_role,
                user_display_name = excluded.user_display_name,
                turn_count = excluded.turn_count,
                recent_topics_json = excluded.recent_topics_json,
                recent_symbols_json = excluded.recent_symbols_json,
                recent_intents_json = excluded.recent_intents_json,
                working_memory_json = excluded.working_memory_json,
                summary_text = excluded.summary_text,
                last_intent = excluded.last_intent,
                last_tags_json = excluded.last_tags_json,
                last_seen_at = excluded.last_seen_at
            """,
            (
                session_id,
                actor.get("tenant_slug") or "",
                actor.get("profile_id") or "",
                actor.get("user_role") or "",
                actor.get("display_name") or "",
                int(session_snapshot.get("turn_count") or 0),
                _hermes_json_text(session_snapshot.get("recent_topics") or [], []),
                _hermes_json_text(session_snapshot.get("recent_symbols") or [], []),
                _hermes_json_text(session_snapshot.get("recent_intents") or [], []),
                _hermes_json_text(session_snapshot.get("working_memory") or {}, {}),
                str(session_snapshot.get("summary_text") or "").strip(),
                str(session_snapshot.get("last_intent") or "").strip(),
                _hermes_json_text(session_snapshot.get("last_tags") or {}, {}),
                created_at,
                created_at,
            ),
        )
        db.execute(
            """
            INSERT INTO hermes_user_memory (
                tenant_slug, user_profile_id, user_role, user_display_name, total_turns, last_session_id,
                fact_memory_json, working_memory_json, recent_topics_json, focus_symbols_json, last_tags_json,
                preferred_response_style, preferred_intents_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_slug, user_profile_id) DO UPDATE SET
                user_role = excluded.user_role,
                user_display_name = excluded.user_display_name,
                total_turns = excluded.total_turns,
                last_session_id = excluded.last_session_id,
                fact_memory_json = excluded.fact_memory_json,
                working_memory_json = excluded.working_memory_json,
                recent_topics_json = excluded.recent_topics_json,
                focus_symbols_json = excluded.focus_symbols_json,
                last_tags_json = excluded.last_tags_json,
                preferred_response_style = excluded.preferred_response_style,
                preferred_intents_json = excluded.preferred_intents_json,
                updated_at = excluded.updated_at
            """,
            (
                actor.get("tenant_slug") or "",
                actor.get("profile_id") or "",
                actor.get("user_role") or "",
                actor.get("display_name") or "",
                int(user_memory_snapshot.get("total_turns") or 0),
                session_id,
                _hermes_json_text(user_memory_snapshot.get("fact_memory") or {}, {}),
                _hermes_json_text(user_memory_snapshot.get("working_memory") or {}, {}),
                _hermes_json_text(user_memory_snapshot.get("recent_topics") or [], []),
                _hermes_json_text(user_memory_snapshot.get("focus_symbols") or [], []),
                _hermes_json_text(user_memory_snapshot.get("last_tags") or {}, {}),
                str(user_memory_snapshot.get("preferred_response_style") or "").strip(),
                _hermes_json_text(user_memory_snapshot.get("preferred_intents") or [], []),
                created_at,
                created_at,
            ),
        )
        db.commit()
        return {
            "storage_mode": "db",
            "turn_id": turn_id,
            "session_id": session_id,
            "created_at": created_at,
        }
    except Exception as exc:
        try:
            get_db().rollback()
        except Exception:
            pass
        if has_request_context():
            app.logger.warning("Hermes turn memory persistence skipped: %s", str(exc)[:180])
        return fallback


def persist_hermes_user_profile(actor_context, profile_snapshot):
    actor = actor_context if isinstance(actor_context, dict) else {}
    snapshot = profile_snapshot if isinstance(profile_snapshot, dict) else {}
    updated_at = now_ts()
    fallback = {
        "storage_mode": "memoryless_fallback",
        "profile_snapshot": copy.deepcopy(snapshot),
    }
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO hermes_user_profiles (
                tenant_slug, user_profile_id, user_role, user_display_name, persona_primary, persona_secondary,
                interest_topics_json, focus_symbols_json, function_tags_json, behavior_tags_json, style_tags_json,
                commercial_tags_json, intent_distribution_json, research_depth_score, engagement_score,
                conversion_signal_score, total_queries, last_intent, last_scope_status, last_activity_at,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_slug, user_profile_id) DO UPDATE SET
                user_role = excluded.user_role,
                user_display_name = excluded.user_display_name,
                persona_primary = excluded.persona_primary,
                persona_secondary = excluded.persona_secondary,
                interest_topics_json = excluded.interest_topics_json,
                focus_symbols_json = excluded.focus_symbols_json,
                function_tags_json = excluded.function_tags_json,
                behavior_tags_json = excluded.behavior_tags_json,
                style_tags_json = excluded.style_tags_json,
                commercial_tags_json = excluded.commercial_tags_json,
                intent_distribution_json = excluded.intent_distribution_json,
                research_depth_score = excluded.research_depth_score,
                engagement_score = excluded.engagement_score,
                conversion_signal_score = excluded.conversion_signal_score,
                total_queries = excluded.total_queries,
                last_intent = excluded.last_intent,
                last_scope_status = excluded.last_scope_status,
                last_activity_at = excluded.last_activity_at,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                actor.get("tenant_slug") or "",
                actor.get("profile_id") or "",
                actor.get("user_role") or "",
                actor.get("display_name") or "",
                snapshot.get("persona_primary") or "",
                snapshot.get("persona_secondary") or "",
                _hermes_json_text(snapshot.get("interest_topics") or [], []),
                _hermes_json_text(snapshot.get("focus_symbols") or [], []),
                _hermes_json_text(snapshot.get("function_tags") or [], []),
                _hermes_json_text(snapshot.get("behavior_tags") or [], []),
                _hermes_json_text(snapshot.get("style_tags") or [], []),
                _hermes_json_text(snapshot.get("commercial_tags") or [], []),
                _hermes_json_text(snapshot.get("intent_distribution") or {}, {}),
                int(snapshot.get("research_depth_score") or 0),
                int(snapshot.get("engagement_score") or 0),
                int(snapshot.get("conversion_signal_score") or 0),
                int(snapshot.get("total_queries") or 0),
                snapshot.get("last_intent") or "",
                snapshot.get("last_scope_status") or "",
                snapshot.get("last_activity_at") or updated_at,
                _hermes_json_text(snapshot.get("metadata") or {}, {}),
                updated_at,
                updated_at,
            ),
        )
        db.commit()
        return {
            "storage_mode": "db",
            "profile_snapshot": copy.deepcopy(snapshot),
        }
    except Exception as exc:
        try:
            get_db().rollback()
        except Exception:
            pass
        if has_request_context():
            app.logger.warning("Hermes user profile persistence skipped: %s", str(exc)[:180])
        return fallback


HERMES_ADMIN_MEMORY_RANGE_OPTIONS = [
    {"key": "1m", "label": "最近 1 个月", "days": 30},
    {"key": "3m", "label": "最近 3 个月", "days": 90},
    {"key": "6m", "label": "最近 6 个月", "days": 180},
    {"key": "1y", "label": "最近 1 年", "days": 365},
    {"key": "all", "label": "全部清除", "days": None},
]

HERMES_ADMIN_MEMORY_RANGE_MAP = {
    item["key"]: item for item in HERMES_ADMIN_MEMORY_RANGE_OPTIONS
}


def normalize_hermes_memory_range_key(range_key):
    key = str(range_key or "").strip().lower()
    if key in HERMES_ADMIN_MEMORY_RANGE_MAP:
        return key
    aliases = {
        "month": "1m",
        "month_1": "1m",
        "1month": "1m",
        "quarter": "3m",
        "3month": "3m",
        "month_3": "3m",
        "half_year": "6m",
        "6month": "6m",
        "month_6": "6m",
        "year": "1y",
        "1year": "1y",
        "year_1": "1y",
        "full": "all",
        "clear_all": "all",
    }
    return aliases.get(key, "3m")


def resolve_hermes_memory_cutoff(range_key):
    normalized = normalize_hermes_memory_range_key(range_key)
    config = HERMES_ADMIN_MEMORY_RANGE_MAP.get(normalized) or {}
    if normalized == "all" or config.get("days") is None:
        return ""
    return (datetime.now() - timedelta(days=int(config.get("days") or 0))).strftime("%Y-%m-%d %H:%M:%S")


def _build_hermes_admin_turn_where(tenant_slug, range_key="all", alias=""):
    tenant = str(tenant_slug or "").strip().lower()
    if not tenant:
        raise ValueError("tenant_slug_required")
    prefix = f"{alias}." if alias else ""
    clauses = [f"{prefix}tenant_slug = ?"]
    params = [tenant]
    cutoff = resolve_hermes_memory_cutoff(range_key)
    if cutoff:
        clauses.append(f"{prefix}created_at >= ?")
        params.append(cutoff)
    return " AND ".join(clauses), params


def _serialize_hermes_backup_row(row):
    data = dict(row) if isinstance(row, dict) else {}
    for key, default in [
        ("citations_json", []),
        ("tool_trace_json", []),
        ("tags_json", {}),
        ("memory_summary_json", {}),
        ("recent_topics_json", []),
        ("recent_symbols_json", []),
        ("recent_intents_json", []),
        ("working_memory_json", {}),
        ("last_tags_json", {}),
        ("fact_memory_json", {}),
        ("focus_symbols_json", []),
        ("preferred_intents_json", []),
        ("interest_topics_json", []),
        ("function_tags_json", []),
        ("behavior_tags_json", []),
        ("style_tags_json", []),
        ("commercial_tags_json", []),
        ("intent_distribution_json", {}),
        ("metadata_json", {}),
    ]:
        if key in data:
            data[key] = _extract_json_text_field(data, key, default)
    return data


def _build_sql_in_clause(values):
    items = list(values or [])
    if not items:
        return "(NULL)"
    return "(" + ",".join(["?"] * len(items)) + ")"


def _load_hermes_turn_rows_for_rebuild(db, tenant_slug, session_id="", user_profile_id=""):
    clauses = ["tenant_slug = ?"]
    params = [str(tenant_slug or "").strip().lower()]
    if str(session_id or "").strip():
        clauses.append("session_id = ?")
        params.append(str(session_id or "").strip())
    if str(user_profile_id or "").strip():
        clauses.append("user_profile_id = ?")
        params.append(str(user_profile_id or "").strip())
    rows = db.execute(
        f"""
        SELECT turn_id, session_id, tenant_slug, user_profile_id, user_role, user_display_name, entry_point,
               question_text, answer_text, answer_summary, intent, scope_status, display_mode, preferred_mode,
               web_answer, citations_json, tool_trace_json, tags_json, memory_summary_json, created_at
        FROM hermes_conversation_turns
        WHERE {" AND ".join(clauses)}
        ORDER BY created_at ASC, id ASC
        """,
        tuple(params),
    ).fetchall()
    normalized = []
    for row in rows:
        item = dict(row) if isinstance(row, dict) else {}
        item["tags"] = _extract_json_text_field(item, "tags_json", {})
        item["memory_summary"] = _extract_json_text_field(item, "memory_summary_json", {})
        normalized.append(item)
    return normalized


def _collect_recent_hermes_tag_values(rows, tag_key, limit=6):
    collected = []
    for row in reversed(rows if isinstance(rows, list) else []):
        tags = row.get("tags") if isinstance(row.get("tags"), dict) else {}
        values = tags.get(tag_key) if isinstance(tags.get(tag_key), list) else []
        collected.extend(values)
    return _hermes_unique_texts(collected, limit=limit)


def _build_rebuilt_hermes_session_row(rows):
    if not rows:
        return None
    last_row = rows[-1]
    recent_questions = _hermes_unique_texts(
        [_hermes_trim_text(row.get("question_text"), limit=120) for row in reversed(rows)],
        limit=4,
    )
    recent_answers = _hermes_unique_texts(
        [_hermes_trim_text(row.get("answer_summary"), limit=140) for row in reversed(rows)],
        limit=4,
    )
    return {
        "session_id": str(last_row.get("session_id") or "").strip(),
        "tenant_slug": str(last_row.get("tenant_slug") or "").strip().lower(),
        "user_profile_id": str(last_row.get("user_profile_id") or "").strip(),
        "user_role": str(last_row.get("user_role") or "").strip(),
        "user_display_name": str(last_row.get("user_display_name") or "").strip(),
        "turn_count": len(rows),
        "recent_topics": _hermes_unique_texts(
            _collect_recent_hermes_tag_values(rows, "topic_tags", limit=6)
            + _collect_recent_hermes_tag_values(rows, "market_tags", limit=6),
            limit=6,
        ),
        "recent_symbols": _collect_recent_hermes_tag_values(rows, "focus_symbols", limit=6),
        "recent_intents": _hermes_unique_texts(
            [str(row.get("intent") or "").strip() for row in reversed(rows)],
            limit=6,
        ),
        "working_memory": {
            "recent_questions": recent_questions,
            "recent_answers": recent_answers,
            "recent_topics": _hermes_unique_texts(
                _collect_recent_hermes_tag_values(rows, "topic_tags", limit=6)
                + _collect_recent_hermes_tag_values(rows, "market_tags", limit=6),
                limit=6,
            ),
            "recent_symbols": _collect_recent_hermes_tag_values(rows, "focus_symbols", limit=6),
        },
        "summary_text": _hermes_trim_text(
            last_row.get("answer_summary") or last_row.get("question_text") or "",
            limit=220,
        ),
        "last_intent": str(last_row.get("intent") or "").strip(),
        "last_tags": copy.deepcopy(last_row.get("tags") or {}),
        "first_seen_at": str(rows[0].get("created_at") or "").strip(),
        "last_seen_at": str(last_row.get("created_at") or "").strip(),
    }


def _build_rebuilt_hermes_user_memory_row(rows):
    if not rows:
        return None
    last_row = rows[-1]
    last_summary = last_row.get("memory_summary") if isinstance(last_row.get("memory_summary"), dict) else {}
    style_tags = _collect_recent_hermes_tag_values(rows, "style_tags", limit=8)
    preferred_response_style = _resolve_hermes_preferred_response_style(style_tags, existing_value="")
    recent_topics = _hermes_unique_texts(
        _collect_recent_hermes_tag_values(rows, "topic_tags", limit=8)
        + _collect_recent_hermes_tag_values(rows, "market_tags", limit=8),
        limit=8,
    )
    focus_symbols = _hermes_unique_texts(
        list(last_summary.get("focus_symbols") or []) + _collect_recent_hermes_tag_values(rows, "focus_symbols", limit=8),
        limit=8,
    )
    preferred_intents = _hermes_unique_texts(
        [str(row.get("intent") or "").strip() for row in reversed(rows)],
        limit=8,
    )
    return {
        "tenant_slug": str(last_row.get("tenant_slug") or "").strip().lower(),
        "user_profile_id": str(last_row.get("user_profile_id") or "").strip(),
        "user_role": str(last_row.get("user_role") or "").strip(),
        "user_display_name": str(last_row.get("user_display_name") or "").strip(),
        "total_turns": len(rows),
        "last_session_id": str(last_row.get("session_id") or "").strip(),
        "fact_memory": {
            "interest_topics": list(last_summary.get("interest_topics") or recent_topics[:6]),
            "focus_symbols": focus_symbols[:6],
            "preferred_response_style": preferred_response_style,
            "preferred_intents": preferred_intents,
            "persona_primary": str(last_summary.get("persona_primary") or "").strip(),
        },
        "working_memory": {
            "last_question": _hermes_trim_text(last_row.get("question_text"), limit=180),
            "last_answer_summary": _hermes_trim_text(last_row.get("answer_summary"), limit=220),
            "recent_questions": _hermes_unique_texts(
                [_hermes_trim_text(row.get("question_text"), limit=120) for row in reversed(rows)],
                limit=4,
            ),
            "recent_topics": recent_topics[:6],
            "recent_symbols": focus_symbols[:6],
        },
        "recent_topics": recent_topics,
        "focus_symbols": focus_symbols,
        "last_tags": copy.deepcopy(last_row.get("tags") or {}),
        "preferred_response_style": preferred_response_style,
        "preferred_intents": preferred_intents,
        "created_at": str(rows[0].get("created_at") or "").strip(),
        "updated_at": str(last_row.get("created_at") or "").strip(),
    }


def _build_rebuilt_hermes_user_profile_row(rows):
    if not rows:
        return None
    last_row = rows[-1]
    last_summary = last_row.get("memory_summary") if isinstance(last_row.get("memory_summary"), dict) else {}
    function_tags = _collect_recent_hermes_tag_values(rows, "function_tags", limit=8)
    behavior_tags = _collect_recent_hermes_tag_values(rows, "behavior_tags", limit=8)
    style_tags = _collect_recent_hermes_tag_values(rows, "style_tags", limit=8)
    commercial_tags = _collect_recent_hermes_tag_values(rows, "commercial_tags", limit=8)
    topic_tags = _collect_recent_hermes_tag_values(rows, "topic_tags", limit=8)
    market_tags = _collect_recent_hermes_tag_values(rows, "market_tags", limit=6)
    focus_symbols = _hermes_unique_texts(
        list(last_summary.get("focus_symbols") or []) + _collect_recent_hermes_tag_values(rows, "focus_symbols", limit=8),
        limit=8,
    )
    intent_distribution = {}
    for row in rows:
        intent = str(row.get("intent") or "").strip()
        if not intent:
            continue
        intent_distribution[intent] = int(intent_distribution.get(intent) or 0) + 1
    persona_primary = str(last_summary.get("persona_primary") or "").strip()
    persona_secondary = str(last_summary.get("persona_secondary") or "").strip()
    if not persona_primary:
        persona_primary, derived_secondary = _compute_hermes_personas(
            function_tags=function_tags,
            style_tags=style_tags,
            actor_context={"user_role": str(last_row.get("user_role") or "").strip()},
        )
        if not persona_secondary:
            persona_secondary = derived_secondary
    return {
        "tenant_slug": str(last_row.get("tenant_slug") or "").strip().lower(),
        "user_profile_id": str(last_row.get("user_profile_id") or "").strip(),
        "user_role": str(last_row.get("user_role") or "").strip(),
        "user_display_name": str(last_row.get("user_display_name") or "").strip(),
        "persona_primary": persona_primary,
        "persona_secondary": persona_secondary,
        "interest_topics": list(last_summary.get("interest_topics") or _hermes_unique_texts(topic_tags + market_tags, limit=8)),
        "focus_symbols": focus_symbols,
        "function_tags": function_tags,
        "behavior_tags": behavior_tags,
        "style_tags": style_tags,
        "commercial_tags": commercial_tags,
        "intent_distribution": intent_distribution,
        "research_depth_score": _clamp_score(int(last_summary.get("research_depth_score") or 0)),
        "engagement_score": _clamp_score(int(last_summary.get("engagement_score") or 0)),
        "conversion_signal_score": _clamp_score(int(last_summary.get("conversion_signal_score") or 0)),
        "total_queries": len(rows),
        "last_intent": str(last_row.get("intent") or "").strip(),
        "last_scope_status": str(last_row.get("scope_status") or "").strip(),
        "last_activity_at": str(last_row.get("created_at") or "").strip(),
        "metadata": {
            "topic_tags": topic_tags,
            "market_tags": market_tags,
            "recent_session_id": str(last_row.get("session_id") or "").strip(),
            "preferred_response_style": _resolve_hermes_preferred_response_style(style_tags, existing_value=""),
        },
        "created_at": str(rows[0].get("created_at") or "").strip(),
        "updated_at": str(last_row.get("created_at") or "").strip(),
    }


def _upsert_rebuilt_hermes_session_rows(db, rows):
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict) or not str(item.get("session_id") or "").strip():
            continue
        db.execute(
            """
            INSERT INTO hermes_session_memory (
                session_id, tenant_slug, user_profile_id, user_role, user_display_name, turn_count,
                recent_topics_json, recent_symbols_json, recent_intents_json, working_memory_json, summary_text,
                last_intent, last_tags_json, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                tenant_slug = excluded.tenant_slug,
                user_profile_id = excluded.user_profile_id,
                user_role = excluded.user_role,
                user_display_name = excluded.user_display_name,
                turn_count = excluded.turn_count,
                recent_topics_json = excluded.recent_topics_json,
                recent_symbols_json = excluded.recent_symbols_json,
                recent_intents_json = excluded.recent_intents_json,
                working_memory_json = excluded.working_memory_json,
                summary_text = excluded.summary_text,
                last_intent = excluded.last_intent,
                last_tags_json = excluded.last_tags_json,
                first_seen_at = excluded.first_seen_at,
                last_seen_at = excluded.last_seen_at
            """,
            (
                item.get("session_id") or "",
                item.get("tenant_slug") or "",
                item.get("user_profile_id") or "",
                item.get("user_role") or "",
                item.get("user_display_name") or "",
                int(item.get("turn_count") or 0),
                _hermes_json_text(item.get("recent_topics") or [], []),
                _hermes_json_text(item.get("recent_symbols") or [], []),
                _hermes_json_text(item.get("recent_intents") or [], []),
                _hermes_json_text(item.get("working_memory") or {}, {}),
                str(item.get("summary_text") or "").strip(),
                str(item.get("last_intent") or "").strip(),
                _hermes_json_text(item.get("last_tags") or {}, {}),
                item.get("first_seen_at") or now_ts(),
                item.get("last_seen_at") or now_ts(),
            ),
        )


def _upsert_rebuilt_hermes_user_memory_rows(db, rows):
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict) or not str(item.get("tenant_slug") or "").strip() or not str(item.get("user_profile_id") or "").strip():
            continue
        db.execute(
            """
            INSERT INTO hermes_user_memory (
                tenant_slug, user_profile_id, user_role, user_display_name, total_turns, last_session_id,
                fact_memory_json, working_memory_json, recent_topics_json, focus_symbols_json, last_tags_json,
                preferred_response_style, preferred_intents_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_slug, user_profile_id) DO UPDATE SET
                user_role = excluded.user_role,
                user_display_name = excluded.user_display_name,
                total_turns = excluded.total_turns,
                last_session_id = excluded.last_session_id,
                fact_memory_json = excluded.fact_memory_json,
                working_memory_json = excluded.working_memory_json,
                recent_topics_json = excluded.recent_topics_json,
                focus_symbols_json = excluded.focus_symbols_json,
                last_tags_json = excluded.last_tags_json,
                preferred_response_style = excluded.preferred_response_style,
                preferred_intents_json = excluded.preferred_intents_json,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                item.get("tenant_slug") or "",
                item.get("user_profile_id") or "",
                item.get("user_role") or "",
                item.get("user_display_name") or "",
                int(item.get("total_turns") or 0),
                item.get("last_session_id") or "",
                _hermes_json_text(item.get("fact_memory") or {}, {}),
                _hermes_json_text(item.get("working_memory") or {}, {}),
                _hermes_json_text(item.get("recent_topics") or [], []),
                _hermes_json_text(item.get("focus_symbols") or [], []),
                _hermes_json_text(item.get("last_tags") or {}, {}),
                str(item.get("preferred_response_style") or "").strip(),
                _hermes_json_text(item.get("preferred_intents") or [], []),
                item.get("created_at") or now_ts(),
                item.get("updated_at") or now_ts(),
            ),
        )


def _upsert_rebuilt_hermes_user_profile_rows(db, rows):
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict) or not str(item.get("tenant_slug") or "").strip() or not str(item.get("user_profile_id") or "").strip():
            continue
        db.execute(
            """
            INSERT INTO hermes_user_profiles (
                tenant_slug, user_profile_id, user_role, user_display_name, persona_primary, persona_secondary,
                interest_topics_json, focus_symbols_json, function_tags_json, behavior_tags_json, style_tags_json,
                commercial_tags_json, intent_distribution_json, research_depth_score, engagement_score,
                conversion_signal_score, total_queries, last_intent, last_scope_status, last_activity_at,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_slug, user_profile_id) DO UPDATE SET
                user_role = excluded.user_role,
                user_display_name = excluded.user_display_name,
                persona_primary = excluded.persona_primary,
                persona_secondary = excluded.persona_secondary,
                interest_topics_json = excluded.interest_topics_json,
                focus_symbols_json = excluded.focus_symbols_json,
                function_tags_json = excluded.function_tags_json,
                behavior_tags_json = excluded.behavior_tags_json,
                style_tags_json = excluded.style_tags_json,
                commercial_tags_json = excluded.commercial_tags_json,
                intent_distribution_json = excluded.intent_distribution_json,
                research_depth_score = excluded.research_depth_score,
                engagement_score = excluded.engagement_score,
                conversion_signal_score = excluded.conversion_signal_score,
                total_queries = excluded.total_queries,
                last_intent = excluded.last_intent,
                last_scope_status = excluded.last_scope_status,
                last_activity_at = excluded.last_activity_at,
                metadata_json = excluded.metadata_json,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                item.get("tenant_slug") or "",
                item.get("user_profile_id") or "",
                item.get("user_role") or "",
                item.get("user_display_name") or "",
                item.get("persona_primary") or "",
                item.get("persona_secondary") or "",
                _hermes_json_text(item.get("interest_topics") or [], []),
                _hermes_json_text(item.get("focus_symbols") or [], []),
                _hermes_json_text(item.get("function_tags") or [], []),
                _hermes_json_text(item.get("behavior_tags") or [], []),
                _hermes_json_text(item.get("style_tags") or [], []),
                _hermes_json_text(item.get("commercial_tags") or [], []),
                _hermes_json_text(item.get("intent_distribution") or {}, {}),
                int(item.get("research_depth_score") or 0),
                int(item.get("engagement_score") or 0),
                int(item.get("conversion_signal_score") or 0),
                int(item.get("total_queries") or 0),
                item.get("last_intent") or "",
                item.get("last_scope_status") or "",
                item.get("last_activity_at") or "",
                _hermes_json_text(item.get("metadata") or {}, {}),
                item.get("created_at") or now_ts(),
                item.get("updated_at") or now_ts(),
            ),
        )


def _rebuild_hermes_admin_aggregates(db, tenant_slug, session_ids=None, user_profile_ids=None):
    session_values = [str(item or "").strip() for item in (session_ids or []) if str(item or "").strip()]
    user_values = [str(item or "").strip() for item in (user_profile_ids or []) if str(item or "").strip()]
    if session_values:
        session_rows = []
        for session_id in session_values:
            rows = _load_hermes_turn_rows_for_rebuild(db, tenant_slug, session_id=session_id)
            rebuilt = _build_rebuilt_hermes_session_row(rows)
            if rebuilt:
                session_rows.append(rebuilt)
            else:
                db.execute(
                    "DELETE FROM hermes_session_memory WHERE tenant_slug = ? AND session_id = ?",
                    (str(tenant_slug or "").strip().lower(), session_id),
                )
        _upsert_rebuilt_hermes_session_rows(db, session_rows)
    if user_values:
        user_memory_rows = []
        user_profile_rows = []
        for user_profile_id in user_values:
            rows = _load_hermes_turn_rows_for_rebuild(db, tenant_slug, user_profile_id=user_profile_id)
            rebuilt_memory = _build_rebuilt_hermes_user_memory_row(rows)
            rebuilt_profile = _build_rebuilt_hermes_user_profile_row(rows)
            if rebuilt_memory:
                user_memory_rows.append(rebuilt_memory)
            else:
                db.execute(
                    "DELETE FROM hermes_user_memory WHERE tenant_slug = ? AND user_profile_id = ?",
                    (str(tenant_slug or "").strip().lower(), user_profile_id),
                )
            if rebuilt_profile:
                user_profile_rows.append(rebuilt_profile)
            else:
                db.execute(
                    "DELETE FROM hermes_user_profiles WHERE tenant_slug = ? AND user_profile_id = ?",
                    (str(tenant_slug or "").strip().lower(), user_profile_id),
                )
        _upsert_rebuilt_hermes_user_memory_rows(db, user_memory_rows)
        _upsert_rebuilt_hermes_user_profile_rows(db, user_profile_rows)


def build_admin_hermes_memory_summary(tenant_slug):
    tenant = str(tenant_slug or "").strip().lower()
    if not tenant:
        raise ValueError("tenant_slug_required")
    db = get_db()
    turns = db.execute(
        """
        SELECT COUNT(*) AS turn_count,
               COUNT(DISTINCT session_id) AS session_count,
               COUNT(DISTINCT user_profile_id) AS user_count,
               MIN(created_at) AS first_turn_at,
               MAX(created_at) AS last_turn_at
        FROM hermes_conversation_turns
        WHERE tenant_slug = ?
        """,
        (tenant,),
    ).fetchone() or {}
    session_rows = db.execute(
        "SELECT COUNT(*) AS total FROM hermes_session_memory WHERE tenant_slug = ?",
        (tenant,),
    ).fetchone() or {}
    user_memory_rows = db.execute(
        "SELECT COUNT(*) AS total FROM hermes_user_memory WHERE tenant_slug = ?",
        (tenant,),
    ).fetchone() or {}
    profile_rows = db.execute(
        "SELECT COUNT(*) AS total FROM hermes_user_profiles WHERE tenant_slug = ?",
        (tenant,),
    ).fetchone() or {}
    recent_30d_cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    recent_30d = db.execute(
        """
        SELECT COUNT(*) AS turn_count, COUNT(DISTINCT user_profile_id) AS active_user_count
        FROM hermes_conversation_turns
        WHERE tenant_slug = ? AND created_at >= ?
        """,
        (tenant, recent_30d_cutoff),
    ).fetchone() or {}
    return {
        "tenant_slug": tenant,
        "range_options": copy.deepcopy(HERMES_ADMIN_MEMORY_RANGE_OPTIONS),
        "turn_count": int(turns.get("turn_count") or 0),
        "session_count": int(turns.get("session_count") or 0),
        "user_count": int(turns.get("user_count") or 0),
        "session_memory_count": int(session_rows.get("total") or 0),
        "user_memory_count": int(user_memory_rows.get("total") or 0),
        "profile_count": int(profile_rows.get("total") or 0),
        "recent_30d_turn_count": int(recent_30d.get("turn_count") or 0),
        "recent_30d_active_user_count": int(recent_30d.get("active_user_count") or 0),
        "first_turn_at": str(turns.get("first_turn_at") or "").strip(),
        "last_turn_at": str(turns.get("last_turn_at") or "").strip(),
        "generated_at": now_ts(),
    }


def _parse_hermes_tool_trace_json(raw_text):
    try:
        payload = json.loads(raw_text or "[]")
    except Exception:
        return []
    return payload if isinstance(payload, list) else []


def _safe_json_dict(raw_text):
    try:
        payload = json.loads(raw_text or "{}")
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_hermes_mode_label(intent, answer_mode="", preferred_mode="", entry_point=""):
    intent_key = str(intent or "").strip().lower()
    answer_key = str(answer_mode or "").strip().lower()
    preferred_key = str(preferred_mode or "").strip().lower()
    entry = str(entry_point or "").strip().lower()
    if intent_key == "watchlist_fundamental":
        return "自选股诊断"
    if intent_key == "evidence_chain_analysis":
        return "证据链归因"
    if intent_key == "knowledge_lookup":
        return "研报精读"
    if intent_key == "dashboard_interpretation":
        return "Dashboard 解读"
    if intent_key == "smart_indicator_explain":
        return "智能指标解读"
    if intent_key == "product_help":
        return "产品帮助"
    if intent_key == "multi_tool_research":
        return "多工具研究"
    if intent_key == "small_talk":
        return "轻度闲聊"
    if "review" in entry:
        return "复盘速写"
    if answer_key == "llm_synthesized" and preferred_key == "deep":
        return "深度研究问答"
    return "通用研究问答"


def _extract_hermes_turn_metrics(turn_row):
    row = dict(turn_row or {})
    metadata = _safe_json_dict(row.get("memory_summary_json"))
    tags = _safe_json_dict(row.get("tags_json"))
    tool_trace = _parse_hermes_tool_trace_json(row.get("tool_trace_json"))
    answer_text = str(row.get("answer_text") or "")
    question_text = str(row.get("question_text") or "")
    answer_mode = str(metadata.get("answer_mode") or "").strip()
    preferred_mode = str(row.get("preferred_mode") or "").strip()
    mode_label = _normalize_hermes_mode_label(
        row.get("intent"),
        answer_mode=answer_mode,
        preferred_mode=preferred_mode,
        entry_point=row.get("entry_point"),
    )
    function_tags = tags.get("function_tags") if isinstance(tags.get("function_tags"), list) else []
    style_tags = tags.get("style_tags") if isinstance(tags.get("style_tags"), list) else []
    commercial_tags = tags.get("commercial_tags") if isinstance(tags.get("commercial_tags"), list) else []
    return {
        "mode_label": mode_label,
        "tool_trace": tool_trace,
        "tool_count": len(tool_trace),
        "latency_ms": int(metadata.get("latency_ms") or 0),
        "compute_units": int(metadata.get("compute_used") or max(1, len(tool_trace) or 1)),
        "response_chars": len(answer_text),
        "request_chars": len(question_text),
        "function_tags": function_tags,
        "style_tags": style_tags,
        "commercial_tags": commercial_tags,
    }


def build_admin_hermes_usage_stats(tenant_slug=""):
    tenant = str(tenant_slug or "").strip().lower()
    db = get_db()
    now_dt = datetime.now()
    today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    month_start = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    params_today = [today_start]
    params_month = [month_start]
    turn_where = ["created_at >= ?"]
    month_where = ["created_at >= ?"]
    if tenant:
        turn_where.append("tenant_slug = ?")
        month_where.append("tenant_slug = ?")
        params_today.append(tenant)
        params_month.append(tenant)
    turn_where_sql = " AND ".join(turn_where)
    month_where_sql = " AND ".join(month_where)

    today_row = db.execute(
        f"""
        SELECT COUNT(*) AS call_count,
               COUNT(DISTINCT user_profile_id) AS user_count
        FROM hermes_conversation_turns
        WHERE {turn_where_sql}
        """,
        tuple(params_today),
    ).fetchone() or {}
    month_row = db.execute(
        f"""
        SELECT COUNT(*) AS call_count,
               COUNT(DISTINCT user_profile_id) AS user_count
        FROM hermes_conversation_turns
        WHERE {month_where_sql}
        """,
        tuple(params_month),
    ).fetchone() or {}

    token_where = ["created_at >= ?", "usage_type = 'llm'", "(feature_code LIKE 'hermes_%' OR entry_point LIKE 'hermes%')"]
    token_params = [month_start]
    if tenant:
        token_where.append("tenant_slug = ?")
        token_params.append(tenant)
    token_where_sql = " AND ".join(token_where)
    token_month = db.execute(
        f"""
        SELECT COALESCE(SUM(total_tokens), 0) AS total_tokens,
               COALESCE(SUM(request_count), 0) AS request_count,
               COALESCE(SUM(latency_ms), 0) AS latency_ms
        FROM token_usage_logs
        WHERE {token_where_sql}
        """,
        tuple(token_params),
    ).fetchone() or {}
    token_today = db.execute(
        f"""
        SELECT COALESCE(SUM(total_tokens), 0) AS total_tokens
        FROM token_usage_logs
        WHERE created_at >= ? AND usage_type = 'llm' AND (feature_code LIKE 'hermes_%' OR entry_point LIKE 'hermes%')
        {'AND tenant_slug = ?' if tenant else ''}
        """,
        tuple([today_start] + ([tenant] if tenant else [])),
    ).fetchone() or {}

    turn_rows = db.execute(
        f"""
        SELECT user_profile_id, user_display_name, user_role, entry_point, intent, preferred_mode, tool_trace_json, tags_json, memory_summary_json, created_at
        FROM hermes_conversation_turns
        WHERE {month_where_sql}
        ORDER BY created_at DESC, id DESC
        """,
        tuple(params_month),
    ).fetchall()

    mode_today = {}
    mode_month = {}
    user_rank = {}
    total_compute_units = 0
    total_latency = 0
    total_calls = 0
    for row in turn_rows:
        metrics = _extract_hermes_turn_metrics(row)
        mode_label = metrics["mode_label"]
        bucket = mode_month.setdefault(mode_label, {"mode_label": mode_label, "today_calls": 0, "month_calls": 0, "compute_units": 0, "latency_ms_total": 0})
        bucket["month_calls"] += 1
        bucket["compute_units"] += metrics["compute_units"]
        bucket["latency_ms_total"] += metrics["latency_ms"]
        total_compute_units += metrics["compute_units"]
        total_latency += metrics["latency_ms"]
        total_calls += 1

        created_at = str((dict(row)).get("created_at") or "")
        if created_at >= today_start:
          bucket["today_calls"] += 1

        user_id = str((dict(row)).get("user_profile_id") or "").strip() or "guest"
        user_bucket = user_rank.setdefault(user_id, {
            "user_profile_id": user_id,
            "user_name": str((dict(row)).get("user_display_name") or user_id).strip() or user_id,
            "user_role": str((dict(row)).get("user_role") or "").strip(),
            "month_calls": 0,
            "compute_units": 0,
            "mode_counts": {},
        })
        user_bucket["month_calls"] += 1
        user_bucket["compute_units"] += metrics["compute_units"]
        user_bucket["mode_counts"][mode_label] = int(user_bucket["mode_counts"].get(mode_label) or 0) + 1

        for tool_item in metrics["tool_trace"]:
            tool_name = str((tool_item or {}).get("tool") or (tool_item or {}).get("name") or "").strip() or "未命名工具"
            tool_bucket = mode_today.setdefault(tool_name, {"tool_name": tool_name, "today_calls": 0, "month_calls": 0, "ok_count": 0, "error_count": 0})
            tool_bucket["month_calls"] += 1
            status = str((tool_item or {}).get("status") or "").strip().lower()
            if created_at >= today_start:
                tool_bucket["today_calls"] += 1
            if status == "ok":
                tool_bucket["ok_count"] += 1
            elif status == "error":
                tool_bucket["error_count"] += 1

    month_call_count = int(month_row.get("call_count") or 0)
    today_call_count = int(today_row.get("call_count") or 0)
    month_user_count = max(1, int(month_row.get("user_count") or 0))
    today_token_total = int(token_today.get("total_tokens") or 0)
    month_token_total = int(token_month.get("total_tokens") or 0)

    mode_rows = []
    for item in sorted(mode_month.values(), key=lambda row: (-row["month_calls"], row["mode_label"])):
        month_calls = int(item["month_calls"] or 0)
        avg_latency_ms = round((item["latency_ms_total"] / month_calls), 2) if month_calls else 0
        share_ratio = round((month_calls / month_call_count) * 100, 1) if month_call_count else 0
        status_label = "高负载" if avg_latency_ms >= 4500 else "正常"
        status_class = "tag-gold" if avg_latency_ms >= 4500 else "tag-green"
        mode_rows.append({
            "mode_label": item["mode_label"],
            "today_calls": int(item["today_calls"] or 0),
            "month_calls": month_calls,
            "share_ratio": share_ratio,
            "avg_latency_ms": avg_latency_ms,
            "status_label": status_label,
            "status_class": status_class,
            "compute_units": int(item["compute_units"] or 0),
        })

    tool_rows = []
    for item in sorted(mode_today.values(), key=lambda row: (-row["month_calls"], row["tool_name"])):
        month_calls = int(item["month_calls"] or 0)
        ok_count = int(item["ok_count"] or 0)
        error_count = int(item["error_count"] or 0)
        success_ratio = round((ok_count / month_calls) * 100, 1) if month_calls else 0
        tool_rows.append({
            "tool_name": item["tool_name"],
            "today_calls": int(item["today_calls"] or 0),
            "month_calls": month_calls,
            "ok_count": ok_count,
            "error_count": error_count,
            "success_ratio": success_ratio,
            "status_label": "正常" if error_count == 0 else "有报错",
            "status_class": "tag-green" if error_count == 0 else "tag-gold",
        })

    rank_rows = []
    role_rank_labels = {
        "dav": {"label": "种子投顾", "class_name": "tier-s"},
        "investor": {"label": "专业会员", "class_name": "tag tag-blue"},
        "admin": {"label": "平台管理员", "class_name": "tag tag-gold"},
    }
    sorted_users = sorted(user_rank.values(), key=lambda row: (-row["compute_units"], -row["month_calls"], row["user_name"]))
    for index, item in enumerate(sorted_users[:8], start=1):
        mode_counts = item.get("mode_counts") or {}
        top_mode = sorted(mode_counts.items(), key=lambda pair: (-pair[1], pair[0]))[0][0] if mode_counts else "通用研究问答"
        role_meta = role_rank_labels.get(str(item.get("user_role") or "").strip().lower(), {"label": "普通用户", "class_name": "tag tag-blue"})
        rank_rows.append({
            "rank": index,
            "user_name": item["user_name"],
            "level_label": role_meta["label"],
            "level_class": role_meta["class_name"],
            "month_calls": int(item["month_calls"] or 0),
            "compute_units": int(item["compute_units"] or 0),
            "top_mode": top_mode,
        })

    total_pool = max(50000, month_token_total * 6 if month_token_total else total_compute_units * 20)
    consumed = max(total_compute_units, month_token_total)
    remaining = max(0, total_pool - consumed)
    usage_ratio = round((consumed / total_pool) * 100, 1) if total_pool else 0

    return {
        "tenant_slug": tenant,
        "summary": {
            "today_calls": today_call_count,
            "month_calls": month_call_count,
            "avg_calls_per_user": round(month_call_count / month_user_count, 2) if month_user_count else 0,
            "compute_consumed": consumed,
            "today_tokens": today_token_total,
            "month_tokens": month_token_total,
            "avg_latency_ms": round(total_latency / total_calls, 2) if total_calls else 0,
            "generated_at": now_ts(),
        },
        "tool_modes": mode_rows[:8],
        "tool_actions": tool_rows[:12],
        "user_ranking": rank_rows,
        "compute_pool": {
            "total": int(total_pool),
            "consumed": int(consumed),
            "remaining": int(remaining),
            "usage_ratio": usage_ratio,
        },
    }


def build_admin_hermes_memory_clear_preview(tenant_slug, range_key):
    tenant = str(tenant_slug or "").strip().lower()
    normalized_range = normalize_hermes_memory_range_key(range_key)
    where_sql, params = _build_hermes_admin_turn_where(tenant, normalized_range)
    db = get_db()
    summary = db.execute(
        f"""
        SELECT COUNT(*) AS turns_to_clear,
               COUNT(DISTINCT session_id) AS sessions_affected,
               COUNT(DISTINCT user_profile_id) AS users_affected,
               MIN(created_at) AS first_turn_at,
               MAX(created_at) AS last_turn_at
        FROM hermes_conversation_turns
        WHERE {where_sql}
        """,
        tuple(params),
    ).fetchone() or {}
    return {
        "tenant_slug": tenant,
        "range_key": normalized_range,
        "range_label": (HERMES_ADMIN_MEMORY_RANGE_MAP.get(normalized_range) or {}).get("label") or normalized_range,
        "cutoff": resolve_hermes_memory_cutoff(normalized_range),
        "turns_to_clear": int(summary.get("turns_to_clear") or 0),
        "sessions_affected": int(summary.get("sessions_affected") or 0),
        "users_affected": int(summary.get("users_affected") or 0),
        "profiles_affected": int(summary.get("users_affected") or 0),
        "first_turn_at": str(summary.get("first_turn_at") or "").strip(),
        "last_turn_at": str(summary.get("last_turn_at") or "").strip(),
        "requires_strong_confirm": normalized_range == "all",
        "generated_at": now_ts(),
    }


def _load_admin_hermes_backup_rows(db, tenant_slug, range_key):
    tenant = str(tenant_slug or "").strip().lower()
    normalized_range = normalize_hermes_memory_range_key(range_key)
    where_sql, params = _build_hermes_admin_turn_where(tenant, normalized_range)
    turns = db.execute(
        f"""
        SELECT *
        FROM hermes_conversation_turns
        WHERE {where_sql}
        ORDER BY created_at DESC, id DESC
        """,
        tuple(params),
    ).fetchall()
    if normalized_range == "all":
        sessions = db.execute(
            "SELECT * FROM hermes_session_memory WHERE tenant_slug = ? ORDER BY last_seen_at DESC",
            (tenant,),
        ).fetchall()
        user_memory = db.execute(
            "SELECT * FROM hermes_user_memory WHERE tenant_slug = ? ORDER BY updated_at DESC",
            (tenant,),
        ).fetchall()
        profiles = db.execute(
            "SELECT * FROM hermes_user_profiles WHERE tenant_slug = ? ORDER BY updated_at DESC",
            (tenant,),
        ).fetchall()
        return turns, sessions, user_memory, profiles
    session_ids = _hermes_unique_texts([str((row or {}).get("session_id") or "").strip() for row in turns], limit=5000)
    user_ids = _hermes_unique_texts([str((row or {}).get("user_profile_id") or "").strip() for row in turns], limit=5000)
    sessions = []
    user_memory = []
    profiles = []
    if session_ids:
        session_rows = db.execute(
            f"""
            SELECT *
            FROM hermes_session_memory
            WHERE tenant_slug = ? AND session_id IN {_build_sql_in_clause(session_ids)}
            ORDER BY last_seen_at DESC
            """,
            tuple([tenant] + session_ids),
        ).fetchall()
        sessions = session_rows
    if user_ids:
        user_memory_rows = db.execute(
            f"""
            SELECT *
            FROM hermes_user_memory
            WHERE tenant_slug = ? AND user_profile_id IN {_build_sql_in_clause(user_ids)}
            ORDER BY updated_at DESC
            """,
            tuple([tenant] + user_ids),
        ).fetchall()
        profile_rows = db.execute(
            f"""
            SELECT *
            FROM hermes_user_profiles
            WHERE tenant_slug = ? AND user_profile_id IN {_build_sql_in_clause(user_ids)}
            ORDER BY updated_at DESC
            """,
            tuple([tenant] + user_ids),
        ).fetchall()
        user_memory = user_memory_rows
        profiles = profile_rows
    return turns, sessions, user_memory, profiles


def build_admin_hermes_memory_backup_zip(tenant_slug, range_key):
    tenant = str(tenant_slug or "").strip().lower()
    normalized_range = normalize_hermes_memory_range_key(range_key)
    db = get_db()
    preview = build_admin_hermes_memory_clear_preview(tenant, normalized_range)
    turns, sessions, user_memory, profiles = _load_admin_hermes_backup_rows(db, tenant, normalized_range)
    manifest = {
        "tenant_slug": tenant,
        "range_key": normalized_range,
        "range_label": (HERMES_ADMIN_MEMORY_RANGE_MAP.get(normalized_range) or {}).get("label") or normalized_range,
        "generated_at": now_ts(),
        "preview": preview,
        "counts": {
            "conversation_turns": len(turns),
            "session_memory": len(sessions),
            "user_memory": len(user_memory),
            "user_profiles": len(profiles),
        },
    }
    buffer = io.BytesIO()
    filename = f"hermes_memory_{tenant}_{normalized_range}_{datetime.now().strftime('%Y%m%d%H%M%S')}.zip"
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        archive.writestr(
            "hermes_conversation_turns.json",
            json.dumps([_serialize_hermes_backup_row(row) for row in turns], ensure_ascii=False, indent=2).encode("utf-8"),
        )
        archive.writestr(
            "hermes_session_memory.json",
            json.dumps([_serialize_hermes_backup_row(row) for row in sessions], ensure_ascii=False, indent=2).encode("utf-8"),
        )
        archive.writestr(
            "hermes_user_memory.json",
            json.dumps([_serialize_hermes_backup_row(row) for row in user_memory], ensure_ascii=False, indent=2).encode("utf-8"),
        )
        archive.writestr(
            "hermes_user_profiles.json",
            json.dumps([_serialize_hermes_backup_row(row) for row in profiles], ensure_ascii=False, indent=2).encode("utf-8"),
        )
    return {
        "filename": filename,
        "content_bytes": buffer.getvalue(),
        "manifest": manifest,
    }


def clear_admin_hermes_memory(tenant_slug, range_key, confirm_text=""):
    tenant = str(tenant_slug or "").strip().lower()
    normalized_range = normalize_hermes_memory_range_key(range_key)
    confirm_value = str(confirm_text or "").strip()
    if normalized_range == "all" and confirm_value != "CONFIRM":
        raise ValueError("confirm_text_required")
    preview = build_admin_hermes_memory_clear_preview(tenant, normalized_range)
    db = get_db()
    if normalized_range == "all":
        try:
            db.execute("DELETE FROM hermes_conversation_turns WHERE tenant_slug = ?", (tenant,))
            db.execute("DELETE FROM hermes_session_memory WHERE tenant_slug = ?", (tenant,))
            db.execute("DELETE FROM hermes_user_memory WHERE tenant_slug = ?", (tenant,))
            db.execute("DELETE FROM hermes_user_profiles WHERE tenant_slug = ?", (tenant,))
            db.commit()
        except Exception:
            db.rollback()
            raise
    else:
        target_rows = db.execute(
            """
            SELECT session_id, user_profile_id
            FROM hermes_conversation_turns
            WHERE tenant_slug = ? AND created_at >= ?
            ORDER BY created_at DESC, id DESC
            """,
            (tenant, resolve_hermes_memory_cutoff(normalized_range)),
        ).fetchall()
        session_ids = _hermes_unique_texts([str((row or {}).get("session_id") or "").strip() for row in target_rows], limit=5000)
        user_ids = _hermes_unique_texts([str((row or {}).get("user_profile_id") or "").strip() for row in target_rows], limit=5000)
        try:
            db.execute(
                "DELETE FROM hermes_conversation_turns WHERE tenant_slug = ? AND created_at >= ?",
                (tenant, resolve_hermes_memory_cutoff(normalized_range)),
            )
            _rebuild_hermes_admin_aggregates(db, tenant, session_ids=session_ids, user_profile_ids=user_ids)
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {
        "tenant_slug": tenant,
        "range_key": normalized_range,
        "preview": preview,
        "post_summary": build_admin_hermes_memory_summary(tenant),
        "cleared_at": now_ts(),
    }


def build_hermes_intent_router_prompt(question_text, has_attachments=False, selected_knowledge_ids=None, messages=None, memory_context_text=""):
    conversation_block = format_hermes_message_context(messages, limit=6)
    conversation_section = f"最近多轮对话：\n{conversation_block}\n\n" if conversation_block else ""
    memory_section = f"历史记忆摘要：\n{str(memory_context_text or '').strip()}\n\n" if str(memory_context_text or "").strip() else ""
    return (
        "请根据用户问题判断 Hermes 应该如何拆解任务。\n"
        "可选 intent：small_talk, product_help, knowledge_lookup, evidence_chain_analysis, watchlist_fundamental, smart_indicator_explain, dashboard_interpretation, multi_tool_research, out_of_scope_redirect\n"
        "可选 tools：knowledge.search, evidence.search, watchlist.detail, dashboard.context, attachment.context\n"
        "规则：\n"
        "1. 如果用户明确问复盘、证据链、依据、来源，优先考虑 evidence_chain_analysis。\n"
        "2. 如果用户明确问基本面、估值、盈利、行业位置、个股研究，且存在股票名/代码，优先考虑 watchlist_fundamental。\n"
        "3. 如果用户主要想问某条知识、某个框架、方法、纪要内容，优先考虑 knowledge_lookup。\n"
        "4. 如果用户在问智能指标怎么计算、提示词/公式怎么理解，优先考虑 smart_indicator_explain，并使用 dashboard.context。\n"
        "5. 如果用户在问 Dashboard 面板、看板卡片、布局、发布后的展示逻辑，优先考虑 dashboard_interpretation，并使用 dashboard.context。\n"
        "6. 如果用户主要在问 H5 / Web / Admin / 工作台里的功能如何使用，优先考虑 product_help。\n"
        "7. 如果问题同时涉及个股 + 证据/知识，多工具组合时用 multi_tool_research。\n"
        "8. 如果只是寒暄或轻度闲聊，用 small_talk。\n"
        "9. 如果问题明显超范围，但能温和收口，用 out_of_scope_redirect，且不要安排任何工具。\n"
        "10. 如果有附件，工具里可以包含 attachment.context。\n"
        "11. stock_code 只在能明显识别时输出，否则为空字符串。\n"
        "12. display_mode 只能是 text 或 structured。\n\n"
        f"{memory_section}"
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
    stock_code = find_watchlist_code_from_text(question)
    scope_flags = _hermes_scope_feature_flags(question, selected_knowledge_ids=selected_knowledge_ids, attachments=attachments)
    stock_keywords = HERMES_SCOPE_KEYWORDS["watchlist"]
    evidence_keywords = HERMES_SCOPE_KEYWORDS["evidence"]
    knowledge_keywords = HERMES_SCOPE_KEYWORDS["knowledge"]
    indicator_keywords = HERMES_SCOPE_KEYWORDS["indicator"]
    dashboard_keywords = HERMES_SCOPE_KEYWORDS["dashboard"]
    product_keywords = HERMES_SCOPE_KEYWORDS["product"]
    product_action_keywords = HERMES_PRODUCT_ACTION_KEYWORDS
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
    if any(keyword in lowered for keyword in [item.lower() for item in product_keywords]) and any(
        keyword in lowered for keyword in [item.lower() for item in product_action_keywords]
    ):
        product_tools = []
        if scope_flags["dashboard"] or scope_flags["indicator"]:
            product_tools.append("dashboard.context")
        if selected_knowledge_ids:
            product_tools.append("knowledge.search")
        if has_attachments:
            product_tools.append("attachment.context")
        return {
            "intent": "product_help",
            "tools": product_tools,
            "stock_code": stock_code,
            "display_mode": "text",
            "reason": "命中平台功能操作问题",
        }
    if any(keyword in lowered for keyword in [item.lower() for item in indicator_keywords]):
        return {
            "intent": "smart_indicator_explain",
            "tools": ["dashboard.context"] + (["knowledge.search"] if selected_knowledge_ids else []) + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "display_mode": "text",
            "reason": "命中智能指标或公式说明问题",
        }
    if any(keyword in lowered for keyword in [item.lower() for item in dashboard_keywords]):
        return {
            "intent": "dashboard_interpretation",
            "tools": ["dashboard.context"] + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "display_mode": "text",
            "reason": "命中 Dashboard 面板理解问题",
        }
    if any(keyword in lowered for keyword in [item.lower() for item in product_keywords]):
        product_tools = []
        if scope_flags["dashboard"] or scope_flags["indicator"]:
            product_tools.append("dashboard.context")
        if selected_knowledge_ids:
            product_tools.append("knowledge.search")
        if has_attachments:
            product_tools.append("attachment.context")
        return {
            "intent": "product_help",
            "tools": product_tools,
            "stock_code": stock_code,
            "display_mode": "text",
            "reason": "命中平台功能使用问题",
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
    if scope_flags["small_talk"]:
        return {
            "intent": "small_talk",
            "tools": ["attachment.context"] if has_attachments else [],
            "stock_code": stock_code,
            "display_mode": "text",
            "reason": "轻度闲聊或寒暄",
        }
    return {
        "intent": "out_of_scope_redirect",
        "tools": [],
        "stock_code": stock_code,
        "display_mode": "text",
        "reason": "当前问题超出 Hermes 的主要服务范围，建议收口到平台相关问题。",
    }


def build_hermes_scope_plan(scope_result, question_text, selected_knowledge_ids=None, attachments=None, preferred_mode=""):
    scope = scope_result if isinstance(scope_result, dict) else {}
    if str(scope.get("status") or "").strip() in {"redirected", "blocked"}:
        return {
            "intent": "out_of_scope_redirect",
            "tools": [],
            "stock_code": "",
            "display_mode": "text",
            "reason": str(scope.get("reason") or "").strip() or "问题超出 Hermes 的主要服务范围。",
            "scope_status": str(scope.get("status") or "").strip() or "redirected",
            "guard_message": str(scope.get("message") or "").strip(),
            "guard_suggestions": [
                str(item).strip()
                for item in (scope.get("suggestions") if isinstance(scope.get("suggestions"), list) else [])
                if str(item).strip()
            ][:4],
        }
    plan = default_hermes_intent_plan(
        question_text=question_text,
        selected_knowledge_ids=selected_knowledge_ids,
        attachments=attachments,
        preferred_mode=preferred_mode,
    )
    if scope.get("status") == "soft_allowed":
        plan["intent"] = "small_talk"
        plan["reason"] = str(scope.get("reason") or plan.get("reason") or "").strip() or plan.get("reason") or ""
    plan["scope_status"] = str(scope.get("status") or "allowed").strip() or "allowed"
    return plan


def build_hermes_scope_synthesis(plan):
    intent_plan = plan if isinstance(plan, dict) else {}
    message = str(intent_plan.get("guard_message") or "").strip()
    suggestions = [
        str(item).strip()
        for item in (intent_plan.get("guard_suggestions") if isinstance(intent_plan.get("guard_suggestions"), list) else [])
        if str(item).strip()
    ][:4]
    answer = message or "Hermes 这轮先不直接展开，因为当前问题没有落在平台的核心服务范围内。"
    return {
        "answer": answer,
        "summary": str(intent_plan.get("reason") or "问题已被范围守卫收口。").strip(),
        "bullets": suggestions,
        "citations": [],
    }


def route_hermes_query_intent(question_text, tenant_slug="", selected_knowledge_ids=None, attachments=None, preferred_mode="", messages=None, scope_result=None, memory_state=None):
    selected_knowledge_ids = selected_knowledge_ids if isinstance(selected_knowledge_ids, list) else []
    attachments = attachments if isinstance(attachments, list) else []
    messages = normalize_hermes_messages(messages)
    if isinstance(scope_result, dict) and str(scope_result.get("status") or "").strip() in {"redirected", "blocked"}:
        return build_hermes_scope_plan(
            scope_result=scope_result,
            question_text=question_text,
            selected_knowledge_ids=selected_knowledge_ids,
            attachments=attachments,
            preferred_mode=preferred_mode,
        ), None, "scope_guard"
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
                memory_context_text=str((memory_state or {}).get("context_text") or "").strip(),
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
    code_match = re.search(r"\b\d{5,6}\b", normalized)
    if code_match:
        return code_match.group(0)
    try:
        details = gen_watchlist_details()
    except Exception:
        details = {}
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


def hermes_tool_dashboard_context(tenant_slug):
    tenant = get_tenant_by_slug(tenant_slug)
    state = resolve_tenant_fund_dashboard_state(tenant, tenant.get("fund_dashboard_config"))
    published = copy.deepcopy((state or {}).get("published") or {})
    smart_indicator_catalog = build_tenant_smart_indicator_catalog(tenant)
    hub = build_indicator_hub(tenant=tenant, admin_view=False)
    cards = []
    for item in (published.get("cells") or [])[:8]:
        if not isinstance(item, dict) or item.get("isEmpty"):
            continue
        cards.append(
            {
                "indicator_code": str(item.get("indicatorCode") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "value": str(item.get("value") or "").strip(),
                "unit": str(item.get("unit") or "").strip(),
                "interpretation": str(item.get("interpretation") or item.get("assessment") or "").strip()[:220],
                "algorithm_detail": str(item.get("algorithmDetail") or "").strip()[:240],
                "updated_at": str(item.get("updatedAt") or "").strip(),
            }
        )
    smart_items = []
    for item in smart_indicator_catalog[:8]:
        if not isinstance(item, dict):
            continue
        smart_items.append(
            {
                "indicator_code": str(item.get("indicator_code") or "").strip(),
                "indicator_name": str(item.get("indicator_name") or "").strip(),
                "value": str(item.get("value") or "").strip(),
                "unit": str(item.get("unit") or "").strip(),
                "prompt_text": str(item.get("prompt_text") or "").strip()[:220],
                "algorithm_detail": str(item.get("algorithm_detail") or "").strip()[:240],
                "interpretation": str(item.get("interpretation") or "").strip()[:220],
                "last_updated": str(item.get("last_updated") or "").strip(),
            }
        )
    base_items = []
    for item in (hub.get("items") or [])[:10]:
        if not isinstance(item, dict):
            continue
        base_items.append(
            {
                "indicator_code": str(item.get("id") or "").strip(),
                "indicator_name": str(item.get("name") or "").strip(),
                "category": str(item.get("category") or "").strip(),
                "value": str(item.get("value") or "").strip(),
                "unit": str(item.get("unit") or "").strip(),
            }
        )
    return {
        "layout": str(published.get("layout") or "").strip(),
        "title": str(published.get("title") or "").strip(),
        "summary": str(published.get("summary") or published.get("note") or "").strip()[:220],
        "published_cards": cards,
        "smart_indicators": smart_items,
        "base_indicators": base_items,
    }


def hermes_tool_web_search(question_text, limit=4):
    query = str(question_text or "").strip()
    if not query:
        return {
            "mode": "web_search_skipped",
            "matches": [],
            "answer": "当前没有可用于互联网补充的问题文本。",
        }
    try:
        response = requests.get(
            "https://news.google.com/rss/search",
            params={
                "q": query,
                "hl": "zh-CN",
                "gl": "CN",
                "ceid": "CN:zh-Hans",
            },
            headers={
                "User-Agent": "Mozilla/5.0 HermesResearchAgent/1.0",
            },
            timeout=12,
        )
        response.raise_for_status()
        xml_text = str(response.text or "").strip()
        matches = []
        if BeautifulSoup is not None:
            soup = BeautifulSoup(xml_text, "xml")
            for item in soup.find_all("item")[: max(1, int(limit or 4))]:
                title = re.sub(r"\s+", " ", str(item.title.text if item.title else "").strip())
                link = str(item.link.text if item.link else "").strip()
                pub_date = re.sub(r"\s+", " ", str(item.pubDate.text if item.pubDate else "").strip())
                description = re.sub(r"\s+", " ", str(item.description.text if item.description else "").strip())
                if title:
                    matches.append({
                        "title": title[:180],
                        "link": link[:500],
                        "published_at": pub_date[:120],
                        "summary": description[:240],
                        "source": "Google News RSS",
                    })
        if not matches:
            item_blocks = re.findall(r"<item>(.*?)</item>", xml_text, flags=re.S | re.I)
            for block in item_blocks[: max(1, int(limit or 4))]:
                title_match = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", block, flags=re.S | re.I)
                link_match = re.search(r"<link>(.*?)</link>", block, flags=re.S | re.I)
                date_match = re.search(r"<pubDate>(.*?)</pubDate>", block, flags=re.S | re.I)
                desc_match = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>", block, flags=re.S | re.I)
                title = re.sub(r"\s+", " ", str((title_match.group(1) or title_match.group(2) or "") if title_match else "").strip())
                link = re.sub(r"\s+", " ", str(link_match.group(1) if link_match else "").strip())
                pub_date = re.sub(r"\s+", " ", str(date_match.group(1) if date_match else "").strip())
                description = re.sub(r"\s+", " ", str((desc_match.group(1) or desc_match.group(2) or "") if desc_match else "").strip())
                if title:
                    matches.append({
                        "title": title[:180],
                        "link": link[:500],
                        "published_at": pub_date[:120],
                        "summary": description[:240],
                        "source": "Google News RSS",
                    })
        answer = (
            f"已补充 {len(matches)} 条公开信息结果，最相关的是《{matches[0].get('title') or '未命名结果'}》。"
            if matches else
            "当前没有补充到足够相关的互联网公开信息。"
        )
        return {
            "mode": "web_search",
            "matches": matches,
            "answer": answer,
            "provider": "google_news_rss",
        }
    except Exception as exc:
        return {
            "mode": "web_search_unavailable",
            "matches": [],
            "answer": "互联网公开信息暂不可用，当前已回退为只基于租户知识和平台内工具回答。",
            "error": str(exc)[:200],
            "provider": "google_news_rss",
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
        "dashboard.context": {
            "output_key": "dashboard_context",
            "executor": lambda runtime: hermes_tool_dashboard_context(
                tenant_slug=runtime.get("tenant_slug") or "",
            ),
        },
        "watchlist.detail": {
            "output_key": "watchlist",
            "executor": lambda runtime: hermes_tool_watchlist_detail(runtime.get("stock_code")),
        },
        "web.search": {
            "output_key": "web_search",
            "executor": lambda runtime: hermes_tool_web_search(
                question_text=runtime.get("question_text") or "",
            ),
        },
    }


def build_hermes_tool_execution_plan(plan, web_answer=False):
    plan = plan if isinstance(plan, dict) else {}
    requested = [
        str(item).strip()
        for item in (plan.get("tools") if isinstance(plan.get("tools"), list) else [])
        if str(item).strip()
    ]
    ordered = []

    def _push(tool_name):
        if tool_name in HERMES_ALLOWED_TOOLS and tool_name not in ordered:
            ordered.append(tool_name)

    # Hermes 固定先查租户知识，再走其它平台内工具，最后才补互联网公开信息。
    _push("knowledge.search")
    for tool_name in requested:
        if tool_name != "knowledge.search":
            _push(tool_name)
    if web_answer:
        _push("web.search")
    return ordered


def execute_hermes_tool_plan(plan, tenant_slug, question_text, selected_knowledge_ids=None, attachments=None, web_answer=False):
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
        "web_answer": bool(web_answer),
    }
    for tool_name in build_hermes_tool_execution_plan(plan, web_answer=web_answer):
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


HERMES_INTENT_LABELS = {
    "watchlist_fundamental": "个股基本面分析",
    "smart_indicator_explain": "智能指标解读",
    "dashboard_interpretation": "Dashboard 解读",
    "product_help": "产品功能帮助",
    "knowledge_lookup": "知识检索问答",
    "evidence_chain_analysis": "证据链归因",
    "multi_tool_research": "多工具研究",
    "small_talk": "轻度闲聊",
    "out_of_scope_redirect": "超范围收口",
}

HERMES_TOOL_LABELS = {
    "attachment.context": "附件解析",
    "knowledge.search": "知识检索",
    "evidence.search": "证据链检索",
    "dashboard.context": "Dashboard 上下文",
    "watchlist.detail": "个股详情分析",
    "web.search": "互联网补充",
}


def build_hermes_agent_trace(intent_plan, tool_trace, route_mode="", answer_mode="", preferred_mode="", web_answer=False, attachments=None, selected_knowledge_ids=None, scope_result=None):
    attachments = attachments if isinstance(attachments, list) else []
    selected_knowledge_ids = selected_knowledge_ids if isinstance(selected_knowledge_ids, list) else []
    scope = scope_result if isinstance(scope_result, dict) else {}
    intent = str((intent_plan or {}).get("intent") or "").strip()
    tools = [str(item).strip() for item in ((intent_plan or {}).get("tools") or []) if str(item).strip()]
    planned_tool_labels = [HERMES_TOOL_LABELS.get(item, item) for item in tools]
    ok_count = sum(1 for item in (tool_trace or []) if str((item or {}).get("status") or "").strip() == "ok")
    error_count = sum(1 for item in (tool_trace or []) if str((item or {}).get("status") or "").strip() == "error")
    route_label = "LLM 路由" if route_mode == "llm_router" else "规则路由"
    answer_label = "模型整合回答" if answer_mode == "llm_synthesized" else "规则降级回答"
    planning_bits = []
    if preferred_mode and preferred_mode != "auto":
        planning_bits.append(f"偏好模式：{preferred_mode}")
    planning_bits.append("先查当前租户知识库")
    if web_answer:
        planning_bits.append("已启用互联网补充")
    if attachments:
        planning_bits.append(f"附件 {len(attachments)} 份")
    if selected_knowledge_ids:
        planning_bits.append(f"知识范围 {len(selected_knowledge_ids)} 条")
    if planned_tool_labels:
        planning_bits.append("工具：" + " / ".join(planned_tool_labels))
    gather_items = []
    for item in tool_trace or []:
        if not isinstance(item, dict):
            continue
        tool_name = HERMES_TOOL_LABELS.get(str(item.get("tool") or "").strip(), str(item.get("tool") or "").strip() or "未知工具")
        status = str(item.get("status") or "").strip() or "skipped"
        elapsed_ms = int(item.get("elapsed_ms") or 0)
        detail = f"{tool_name} · {elapsed_ms}ms"
        if status == "error" and item.get("error"):
            detail = f"{detail} · {str(item.get('error') or '').strip()[:80]}"
        gather_items.append({
            "title": tool_name,
            "status": status,
            "detail": detail,
        })
    scope_status = str(scope.get("status") or "allowed").strip() or "allowed"
    scope_status_map = {
        "allowed": ("ok", "问题落在平台研究或产品能力范围内。"),
        "soft_allowed": ("ok", "当前属于轻度闲聊，允许简短承接。"),
        "redirected": ("skipped", str(scope.get("reason") or "已收口到平台相关问题。").strip()),
        "blocked": ("error", str(scope.get("reason") or "已识别为高风险或超边界问题。").strip()),
    }
    scope_trace_status, scope_detail = scope_status_map.get(scope_status, ("ok", "已完成范围识别。"))
    steps = [
        {
            "key": "scope",
            "title": "范围识别",
            "status": scope_trace_status,
            "detail": scope_detail,
        },
        {
            "key": "intent",
            "title": "问题拆解",
            "status": "ok",
            "detail": (
                "范围守卫已直接收口，无需继续做常规路由。"
                if route_mode == "scope_guard" else
                f"{route_label}识别为“{HERMES_INTENT_LABELS.get(intent, intent or '通用研究问答')}”。"
            ),
        },
        {
            "key": "plan",
            "title": "执行规划",
            "status": "ok",
            "detail": "；".join(planning_bits) if planning_bits else "未指定额外约束，按默认 Agent 流程执行。",
        },
        {
            "key": "tools",
            "title": "资料调取",
            "status": "error" if error_count and not ok_count else ("ok" if ok_count else "skipped"),
            "detail": (
                f"已执行 {len(tool_trace or [])} 个工具，成功 {ok_count} 个"
                + (f"，失败 {error_count} 个。" if error_count else "。")
            ) if tool_trace else "本轮未触发外部资料工具。",
            "items": gather_items,
        },
        {
            "key": "answer",
            "title": "结论整合",
            "status": "ok" if answer_mode != "fallback_plain_answer" else "skipped",
            "detail": answer_label + "，输出面向用户的结论、依据和下一步建议。",
        },
    ]
    return {
        "headline": "Hermes Agent 已完成本轮编排",
        "summary": "先拆解问题，再调度知识、个股、附件等工具，最后整合成可读回答。",
        "steps": steps,
    }


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
    dashboard_cards = ((tool_outputs.get("dashboard_context") or {}).get("published_cards") or []) if isinstance(tool_outputs, dict) else []
    for item in dashboard_cards[:4]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if title and title not in citations:
            citations.append(title)
    smart_items = ((tool_outputs.get("dashboard_context") or {}).get("smart_indicators") or []) if isinstance(tool_outputs, dict) else []
    for item in smart_items[:4]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("indicator_name") or "").strip()
        if title and title not in citations:
            citations.append(title)
    attachment_items = ((tool_outputs.get("attachment_context") or {}).get("items") or []) if isinstance(tool_outputs, dict) else []
    for item in attachment_items[:3]:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip()
        if filename and filename not in citations:
            citations.append(filename)
    web_matches = ((tool_outputs.get("web_search") or {}).get("matches") or []) if isinstance(tool_outputs, dict) else []
    for item in web_matches[:4]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if title and title not in citations:
            citations.append(title)
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
    elif intent == "smart_indicator_explain":
        suggestions = [
            "可以继续问这个智能指标引用了哪些底层指标。",
            "也可以继续问这条提示词适不适合改成别的计算口径。",
            "如果要落到看板展示，我可以继续解释它适合放在哪个格子。",
        ]
    elif intent == "dashboard_interpretation":
        suggestions = [
            "可以继续问当前看板里哪张卡片最值得先看。",
            "也可以继续问某个格子为什么适合放这个指标。",
            "如果要改布局，我可以继续按 2x2 / 2x3 方式解释取舍。",
        ]
    elif intent == "product_help":
        suggestions = [
            "可以直接说你在哪个页面、点到了哪个按钮。",
            "也可以问某个操作的前后顺序，我会按步骤拆给你。",
            "如果卡在报错或空白状态，可以把现象直接描述给我。",
        ]
    elif intent == "out_of_scope_redirect":
        suggestions = [
            "可以改问个股或自选股基本面。",
            "也可以改问复盘依据、知识框架或智能指标。",
            "如果是页面操作问题，直接说 H5 / Web / Admin 里的目标动作。",
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
    dashboard_context = (tool_outputs.get("dashboard_context") or {}) if isinstance(tool_outputs, dict) else {}
    for item in (dashboard_context.get("smart_indicators") or [])[:2]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("indicator_name") or "").strip()
        if not title:
            continue
        knowledge_entries.append({
            "title": title,
            "summary": str(item.get("algorithm_detail") or item.get("interpretation") or "").strip()[:160],
        })
    web_matches = ((tool_outputs.get("web_search") or {}).get("matches") or []) if isinstance(tool_outputs, dict) else []
    footer_suffix = "已先查租户知识，再补充互联网公开信息。" if web_matches else "已优先基于当前租户知识库和平台内工具回答。"
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
        "footer": f"当前为文字回答。路由判断：{str((plan or {}).get('reason') or '').strip()}。{footer_suffix}",
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
    web_matches = ((tool_outputs.get("web_search") or {}).get("matches") or []) if isinstance(tool_outputs, dict) else []
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
            f"本轮问题：{str(question_text or '').strip()}。{'已补充互联网公开信息。' if web_matches else '当前优先基于租户知识与平台内工具。'}"
            if not tenant_advisor else
            f"当前优先结合 {tenant_advisor} 租户知识、自选股和证据条目做解释。{' 已补充互联网公开信息。' if web_matches else ''}"
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


def build_hermes_synthesis_prompt(question_text, plan, tool_outputs, tenant_slug="", user_role="", preferred_mode="", messages=None, web_answer=False, memory_state=None):
    tenant = get_tenant_by_slug(tenant_slug)
    tenant_name = (tenant or {}).get("name") or (tenant or {}).get("short_name") or str(tenant_slug or "").strip() or "当前租户"
    conversation_block = format_hermes_message_context(messages, limit=8)
    memory_context_text = str((memory_state or {}).get("context_text") or "").strip()
    blocks = [
        f"租户：{tenant_name}",
        f"角色：{str(user_role or '').strip() or 'unknown'}",
        f"问题：{str(question_text or '').strip()}",
        f"意图：{str(plan.get('intent') or '').strip()}",
        f"偏好分析方式：{str(preferred_mode or '').strip() or 'auto'}",
        f"互联网补充模式：{'是' if web_answer else '否'}",
        f"展示模式：{str(plan.get('display_mode') or 'text').strip()}",
        f"路由原因：{str(plan.get('reason') or '').strip()}",
        f"历史记忆摘要：\n{memory_context_text}" if memory_context_text else "",
        f"最近多轮对话：\n{conversation_block}" if conversation_block else "",
        f"工具结果：{json.dumps(tool_outputs, ensure_ascii=False)[:12000]}",
    ]
    blocks = [block for block in blocks if block]
    system_prompt = (
        "你是 Hermes 的答案合成器。"
        "你的职责是根据已执行的工具结果生成最终回答。"
        "优先依据工具结果，不要编造不存在的数据。"
        "必须先依据租户知识结果，再参考平台内工具，最后才参考互联网补充结果。"
        "如果存在互联网补充结果，可以按公开信息口径组织回答，但不能把互联网信息盖过租户知识。"
        "如果证据不足，要明确说边界。"
        "输出必须是 JSON。"
    )
    user_prompt = (
        "\n\n".join(blocks) +
        "\n\n请输出 JSON："
        '{"answer":"中文最终回答","summary":"一句摘要","bullets":["..."],"citations":["..."]}'
    )
    return system_prompt, user_prompt


def synthesize_hermes_answer(question_text, plan, tool_outputs, tenant_slug="", user_role="", preferred_mode="", messages=None, web_answer=False, memory_state=None):
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
            web_answer=web_answer,
            memory_state=memory_state,
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
    web_answer = bool(payload.get("web_answer"))
    entry_point = str(payload.get("entry_point") or "hermes_chat").strip() or "hermes_chat"
    messages = normalize_hermes_messages(payload.get("messages"))
    question_text = extract_hermes_question_text(messages, payload.get("question"))
    if not question_text:
        raise ValueError("hermes_question_required")
    actor_context = resolve_hermes_actor_context(payload, tenant_slug=tenant_slug, user_role=user_role)
    session_id = resolve_hermes_session_id(payload, actor_context=actor_context)
    workflow_definition = build_default_hermes_agent_workflow_definition()

    def _hermes_input_executor(state, runtime, node, upstream):
        return {
            "detail": "已接收问题、附件、知识范围和会话上下文。",
            "state_updates": {"question_text": runtime.get("question_text") or ""},
            "context_preview": {
                "attachment_count": len(runtime.get("attachments") or []),
                "knowledge_count": len(runtime.get("selected_knowledge_ids") or []),
                "message_count": len(runtime.get("messages") or []),
                "session_id": runtime.get("session_id") or "",
            },
        }

    def _hermes_session_load_executor(state, runtime, node, upstream):
        memory_state = load_hermes_memory_state(
            actor_context=runtime.get("actor_context") or {},
            session_id=runtime.get("session_id") or "",
            limit=6,
        )
        session_state = memory_state.get("session") if isinstance(memory_state.get("session"), dict) else {}
        return {
            "status": "ok" if memory_state.get("available") else "skipped",
            "detail": "已装载当前会话记忆。" if memory_state.get("available") else "当前没有可读的历史会话记忆，按新会话继续。",
            "state_updates": {
                "memory_state": memory_state,
            },
            "context_preview": {
                "session_turn_count": int(session_state.get("turn_count") or 0),
                "storage_mode": memory_state.get("storage_mode") or "",
            },
        }

    def _hermes_memory_read_executor(state, runtime, node, upstream):
        memory_state = state.get("memory_state") if isinstance(state.get("memory_state"), dict) else {}
        user_profile_state = memory_state.get("user_profile") if isinstance(memory_state.get("user_profile"), dict) else {}
        user_memory_state = memory_state.get("user_memory") if isinstance(memory_state.get("user_memory"), dict) else {}
        return {
            "status": "ok" if memory_state.get("available") else "skipped",
            "detail": "已读取用户事实记忆、工作记忆和画像。" if memory_state.get("available") else "当前未命中历史记忆，按首轮问答继续。",
            "state_updates": {
                "memory_context_text": memory_state.get("context_text") or "",
            },
            "context_preview": {
                "total_turns": int(user_profile_state.get("total_queries") or user_memory_state.get("total_turns") or 0),
                "persona_primary": user_profile_state.get("persona_primary") or "",
            },
        }

    def _hermes_scope_executor(state, runtime, node, upstream):
        scope_result = hermes_scope_guard(
            question_text=runtime.get("question_text") or "",
            selected_knowledge_ids=runtime.get("selected_knowledge_ids") or [],
            attachments=runtime.get("attachments") or [],
        )
        scope_status = str(scope_result.get("status") or "allowed").strip() or "allowed"
        detail_map = {
            "allowed": "问题已通过范围识别。",
            "soft_allowed": "问题属于轻度闲聊，允许简短承接。",
            "redirected": "问题超出主要范围，已改为平台能力收口。",
            "blocked": "问题涉及高风险或超边界诉求，已阻断直接回答。",
        }
        return {
            "status": "error" if scope_status == "blocked" else ("skipped" if scope_status == "redirected" else "ok"),
            "detail": detail_map.get(scope_status, "已完成范围识别。"),
            "state_updates": {
                "scope_result": scope_result,
            },
            "context_preview": {
                "scope_status": scope_status,
                "intent_hint": scope_result.get("intent_hint") or "",
            },
        }

    def _hermes_router_executor(state, runtime, node, upstream):
        intent_plan, router_model, route_mode = route_hermes_query_intent(
            question_text=runtime.get("question_text") or "",
            tenant_slug=runtime.get("tenant_slug") or "",
            selected_knowledge_ids=runtime.get("selected_knowledge_ids") or [],
            attachments=runtime.get("attachments") or [],
            preferred_mode=runtime.get("preferred_mode") or "",
            messages=runtime.get("messages") or [],
            scope_result=state.get("scope_result") or {},
            memory_state=state.get("memory_state") or {},
        )
        return {
            "detail": f"已完成意图路由：{str(intent_plan.get('reason') or '').strip() or '默认通用对话'}",
            "state_updates": {
                "intent_plan": intent_plan,
                "router_model": router_model,
                "route_mode": route_mode,
            },
            "context_preview": {
                "intent": intent_plan.get("intent") or "",
                "tool_count": len(intent_plan.get("tools") or []),
                "display_mode": intent_plan.get("display_mode") or "",
            },
        }

    def _hermes_tool_executor(state, runtime, node, upstream):
        intent_plan = state.get("intent_plan") or {}
        if str(intent_plan.get("intent") or "").strip() == "out_of_scope_redirect":
            return {
                "status": "skipped",
                "detail": "当前问题已被范围守卫收口，本轮不再调度平台工具。",
                "state_updates": {
                    "tool_outputs": {},
                    "tool_trace": [],
                },
                "context_preview": {
                    "tool_count": 0,
                    "ok_count": 0,
                },
            }
        tool_outputs, tool_trace = execute_hermes_tool_plan(
            plan=intent_plan,
            tenant_slug=runtime.get("tenant_slug") or "",
            question_text=runtime.get("question_text") or "",
            selected_knowledge_ids=runtime.get("selected_knowledge_ids") or [],
            attachments=runtime.get("attachments") or [],
            web_answer=bool(runtime.get("web_answer")),
        )
        return {
            "detail": f"已执行 {len(tool_trace or [])} 个工具。",
            "state_updates": {
                "tool_outputs": tool_outputs,
                "tool_trace": tool_trace,
            },
            "context_preview": {
                "tool_count": len(tool_trace or []),
                "ok_count": len([item for item in (tool_trace or []) if str((item or {}).get('status') or '') == 'ok']),
            },
        }

    def _hermes_synthesis_executor(state, runtime, node, upstream):
        if str((state.get("intent_plan") or {}).get("intent") or "").strip() == "out_of_scope_redirect":
            synthesis = build_hermes_scope_synthesis(state.get("intent_plan") or {})
            return {
                "status": "skipped",
                "detail": "已生成范围守卫的收口回复。",
                "state_updates": {
                    "synthesis": synthesis,
                    "answer_model": None,
                    "answer_mode": "scope_guard_reply",
                },
                "context_preview": {
                    "answer_chars": len(str((synthesis or {}).get("answer") or "")),
                    "bullet_count": len((synthesis or {}).get("bullets") or []),
                },
            }
        synthesis, answer_model, answer_mode = synthesize_hermes_answer(
            question_text=runtime.get("question_text") or "",
            plan=state.get("intent_plan") or {},
            tool_outputs=state.get("tool_outputs") or {},
            tenant_slug=runtime.get("tenant_slug") or "",
            user_role=runtime.get("user_role") or "",
            preferred_mode=runtime.get("preferred_mode") or "",
            messages=runtime.get("messages") or [],
            web_answer=bool(runtime.get("web_answer")),
            memory_state=state.get("memory_state") or {},
        )
        return {
            "detail": "已完成答案合成。",
            "state_updates": {
                "synthesis": synthesis,
                "answer_model": answer_model,
                "answer_mode": answer_mode,
            },
            "context_preview": {
                "answer_chars": len(str((synthesis or {}).get("answer") or "")),
                "bullet_count": len((synthesis or {}).get("bullets") or []),
            },
        }

    def _hermes_memory_extract_executor(state, runtime, node, upstream):
        intent_plan = copy.deepcopy(state.get("intent_plan") or {})
        intent_plan["preferred_mode"] = runtime.get("preferred_mode") or ""
        intent_plan["web_answer"] = bool(runtime.get("web_answer"))
        memory_payload = extract_hermes_memory_payload(
            question_text=runtime.get("question_text") or "",
            plan=intent_plan,
            synthesis=state.get("synthesis") or {},
            tool_outputs=state.get("tool_outputs") or {},
            actor_context=runtime.get("actor_context") or {},
            memory_state=state.get("memory_state") or {},
        )
        return {
            "detail": "已提炼本轮记忆、标签和用户画像更新内容。",
            "state_updates": {
                "memory_payload": memory_payload,
            },
            "context_preview": {
                "interest_topics": len(((memory_payload.get("profile_snapshot") or {}).get("interest_topics") or [])),
                "focus_symbols": len(((memory_payload.get("profile_snapshot") or {}).get("focus_symbols") or [])),
            },
        }

    def _hermes_memory_write_executor(state, runtime, node, upstream):
        persist_result = persist_hermes_turn_and_memory(
            actor_context=runtime.get("actor_context") or {},
            session_id=runtime.get("session_id") or "",
            entry_point=runtime.get("entry_point") or "",
            memory_payload=state.get("memory_payload") or {},
            tool_trace=state.get("tool_trace") or [],
        )
        return {
            "status": "ok" if persist_result.get("storage_mode") == "db" else "skipped",
            "detail": "已写入问答原文、会话记忆和用户记忆。" if persist_result.get("storage_mode") == "db" else "当前未写入数据库，保留内存态结果。",
            "state_updates": {
                "memory_persist_result": persist_result,
            },
            "context_preview": {
                "storage_mode": persist_result.get("storage_mode") or "",
                "turn_id": persist_result.get("turn_id") or "",
            },
        }

    def _hermes_user_profile_update_executor(state, runtime, node, upstream):
        profile_result = persist_hermes_user_profile(
            actor_context=runtime.get("actor_context") or {},
            profile_snapshot=((state.get("memory_payload") or {}).get("profile_snapshot") or {}),
        )
        return {
            "status": "ok" if profile_result.get("storage_mode") == "db" else "skipped",
            "detail": "已更新 Hermes 用户画像。" if profile_result.get("storage_mode") == "db" else "当前未写入画像表，保留内存态画像结果。",
            "state_updates": {
                "profile_persist_result": profile_result,
            },
            "context_preview": {
                "storage_mode": profile_result.get("storage_mode") or "",
                "persona_primary": ((profile_result.get("profile_snapshot") or {}).get("persona_primary") or ""),
            },
        }

    def _hermes_artifact_executor(state, runtime, node, upstream):
        intent_plan = state.get("intent_plan") or {}
        tool_outputs = state.get("tool_outputs") or {}
        tool_trace = state.get("tool_trace") or []
        synthesis = state.get("synthesis") or {}
        route_mode = state.get("route_mode") or ""
        answer_mode = state.get("answer_mode") or ""
        memory_payload = state.get("memory_payload") if isinstance(state.get("memory_payload"), dict) else {}
        profile_snapshot = (memory_payload.get("profile_snapshot") or {}) if isinstance(memory_payload, dict) else {}
        user_memory_snapshot = (memory_payload.get("user_memory_snapshot") or {}) if isinstance(memory_payload, dict) else {}
        session_snapshot = (memory_payload.get("session_snapshot") or {}) if isinstance(memory_payload, dict) else {}
        memory_state = state.get("memory_state") if isinstance(state.get("memory_state"), dict) else {}
        citations = build_hermes_citations(tool_outputs)
        agent_trace = build_hermes_agent_trace(
            intent_plan=intent_plan,
            tool_trace=tool_trace,
            route_mode=route_mode,
            answer_mode=answer_mode,
            preferred_mode=runtime.get("preferred_mode") or "",
            web_answer=bool(runtime.get("web_answer")),
            attachments=runtime.get("attachments") or [],
            selected_knowledge_ids=runtime.get("selected_knowledge_ids") or [],
            scope_result=state.get("scope_result") or {},
        )
        artifacts = build_hermes_artifacts(
            plan=intent_plan,
            tool_outputs=tool_outputs,
            synthesis=synthesis,
            citations=citations,
            tenant_slug=runtime.get("tenant_slug") or "",
            user_role=runtime.get("user_role") or "",
            question_text=runtime.get("question_text") or "",
        )
        response_display_mode = "structured" if any(str((item or {}).get("type") or "").strip() == "watchlist_analysis" for item in artifacts) else "text"
        result = {
            "ok": True,
            "question": runtime.get("question_text") or "",
            "tenant_slug": runtime.get("tenant_slug") or "",
            "session_id": runtime.get("session_id") or "",
            "intent": intent_plan.get("intent"),
            "scope_status": intent_plan.get("scope_status") or str(((state.get("scope_result") or {}).get("status") or "allowed")).strip(),
            "display_mode": response_display_mode,
            "answer": synthesis.get("answer") or "",
            "summary": synthesis.get("summary") or "",
            "bullets": synthesis.get("bullets") or [],
            "citations": (synthesis.get("citations") or []) + [item for item in citations if item not in (synthesis.get("citations") or [])],
            "artifacts": artifacts,
            "tool_trace": tool_trace,
            "tool_outputs": tool_outputs,
            "agent_trace": agent_trace,
            "preferred_mode": runtime.get("preferred_mode") or "auto",
            "web_answer": bool(runtime.get("web_answer")),
            "source_policy": {
                "knowledge_first": True,
                "web_supplement_enabled": bool(runtime.get("web_answer")),
            },
            "memory_meta": {
                "session_id": runtime.get("session_id") or "",
                "storage_mode": (
                    (state.get("profile_persist_result") or {}).get("storage_mode")
                    or (state.get("memory_persist_result") or {}).get("storage_mode")
                    or (memory_state.get("storage_mode") or "memoryless_fallback")
                ),
                "previous_session_turn_count": int(((memory_state.get("session") or {}).get("turn_count") or 0)),
                "session_turn_count": int(session_snapshot.get("turn_count") or 0),
                "total_turns": int(profile_snapshot.get("total_queries") or user_memory_snapshot.get("total_turns") or 0),
                "preferred_response_style": user_memory_snapshot.get("preferred_response_style") or "",
                "interest_topics": copy.deepcopy((profile_snapshot.get("interest_topics") or [])[:6]),
                "focus_symbols": copy.deepcopy((profile_snapshot.get("focus_symbols") or [])[:6]),
            },
            "user_profile_snapshot": copy.deepcopy(profile_snapshot),
            "router": {
                "mode": route_mode,
                "reason": intent_plan.get("reason") or "",
                "model": {
                    "key": (state.get("router_model") or {}).get("key"),
                    "label": (state.get("router_model") or {}).get("label"),
                    "provider": (state.get("router_model") or {}).get("provider"),
                    "model_name": (state.get("router_model") or {}).get("model_name"),
                } if state.get("router_model") else None,
            },
            "answer_engine": {
                "mode": answer_mode,
                "model": {
                    "key": (state.get("answer_model") or {}).get("key"),
                    "label": (state.get("answer_model") or {}).get("label"),
                    "provider": (state.get("answer_model") or {}).get("provider"),
                    "model_name": (state.get("answer_model") or {}).get("model_name"),
                } if state.get("answer_model") else None,
            },
            "usage": {
                "compute_used": 1,
            },
            "workflow_meta": build_declared_agent_workflow_meta(
                workflow_definition,
                extras={"last_execution_steps": copy.deepcopy(upstream)},
            ),
        }
        return {
            "detail": "已生成最终回答与展示工件。",
            "output": result,
            "state_key": "response_payload",
            "context_preview": {"artifact_count": len(artifacts), "display_mode": response_display_mode},
        }

    execution = run_declared_agent_workflow(
        workflow_definition,
        runtime={
            "tenant_slug": tenant_slug,
            "user_role": user_role,
            "selected_knowledge_ids": selected_knowledge_ids,
            "attachments": attachments,
            "preferred_mode": preferred_mode,
            "web_answer": web_answer,
            "messages": messages,
            "question_text": question_text,
            "entry_point": entry_point,
            "session_id": session_id,
            "actor_context": actor_context,
        },
        executor_registry={
            "question_input": _hermes_input_executor,
            "session_load": _hermes_session_load_executor,
            "memory_read": _hermes_memory_read_executor,
            "scope_guard": _hermes_scope_executor,
            "intent_router": _hermes_router_executor,
            "tool_dispatch": _hermes_tool_executor,
            "answer_synthesis": _hermes_synthesis_executor,
            "memory_extract": _hermes_memory_extract_executor,
            "memory_write": _hermes_memory_write_executor,
            "user_profile_update": _hermes_user_profile_update_executor,
            "artifact_render": _hermes_artifact_executor,
        },
    )
    return execution["state"]["response_payload"]


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
    llm_workflow_meta = None
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
            llm_workflow_meta = copy.deepcopy(llm_result.get("workflow_meta") or {})
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
        "workflow_meta": llm_workflow_meta or {},
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
    review_summary="",
    user_input_section=None,
    watchlist_analysis_section=None,
):
    tenant = get_tenant_by_slug(tenant_slug)
    if not tenant or tenant.get("slug") != tenant_slug:
        raise ValueError("tenant_not_found")
    period_key = str(review_period or "day").strip().lower() or "day"
    period_map = {"day": "日复盘", "week": "周复盘", "month": "月复盘"}
    period_label = period_map.get(period_key, "日复盘")
    cleaned_text = str(text or "").strip()
    normalized_user_input_section = copy.deepcopy(user_input_section if isinstance(user_input_section, dict) else {})
    normalized_watchlist_analysis = copy.deepcopy(watchlist_analysis_section if isinstance(watchlist_analysis_section, dict) else {})
    title_source_text = str(
        normalized_user_input_section.get("display_text")
        or normalized_user_input_section.get("polished_text")
        or polished_input_text
        or cleaned_text
        or ""
    ).strip()
    title_seed = re.split(r"[。！？\n]", title_source_text, 1)[0].strip() if title_source_text else ""
    title = f"{period_label}：{title_seed or '最新复盘已发布'}"
    summary = str(review_summary or "").strip()
    if not summary:
        summary_source_text = str(
            normalized_user_input_section.get("display_text")
            or normalized_user_input_section.get("polished_text")
            or polished_input_text
            or cleaned_text
            or ""
        ).strip()
        summary = re.sub(r"\s+", " ", summary_source_text).strip()[:150] if summary_source_text else f"{period_label}已发布。"
    else:
        summary = re.sub(r"\s+", " ", summary).strip()[:150]
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
        "user_input_section": normalized_user_input_section,
        "watchlist_analysis_section": normalized_watchlist_analysis,
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
