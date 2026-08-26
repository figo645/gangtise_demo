import math
import re
from collections import Counter
from zoneinfo import ZoneInfo

from src.runtime import *
from src.domain.core_services import *
from src.domain.core_services import _estimate_token_count, _extract_usage_tokens
from src.domain.agent_workflows import *
from src.domain.knowledge_graph_services import build_knowledge_graph_artifact
from src.domain.market_services import *
from src.domain.market_services import _merge_gangtise_sse_texts
from src.web.request_helpers import get_client_ip
from flask import has_request_context

def get_platform_name(site_config=None):
    return get_platform_brand(site_config).get("name", DEFAULT_BRAND_CONFIG["name"])


def get_platform_short_name(site_config=None):
    return get_platform_brand(site_config).get("short_name", DEFAULT_BRAND_CONFIG["short_name"])


def get_voice_transcription_config(site_config=None):
    config = site_config or get_site_config()
    return normalize_voice_transcription_config(
        config.get("voice_transcription") if isinstance(config, dict) else {}
    )


def get_voice_embedding_config(site_config=None):
    config = site_config or get_site_config()
    return normalize_voice_embedding_config(
        config.get("voice_embedding") if isinstance(config, dict) else {}
    )


def get_evidence_chain_config(site_config=None):
    config = site_config or get_site_config()
    section = config.get("evidence_chain") if isinstance(config, dict) else {}
    return normalize_evidence_chain_config(section)


def get_review_generation_config(site_config=None):
    config = site_config or get_site_config()
    section = config.get("review_generation") if isinstance(config, dict) else {}
    return normalize_review_generation_config(section)


def get_default_llm_config(site_config=None, purpose="general", feature_code=""):
    config = site_config or get_site_config()
    registry = normalize_llm_registry_config((config or {}).get("llm_registry"))
    purpose_key = str(purpose or "general").strip().lower() or "general"
    default_key = str(registry.get("default_model_key") or "").strip()
    feature_key = str(feature_code or "").strip()
    models = registry.get("models") if isinstance(registry.get("models"), list) else []
    feature_model_keys = registry.get("feature_model_keys") if isinstance(registry.get("feature_model_keys"), dict) else {}
    selected = None
    if feature_key:
        bound_model_key = str(feature_model_keys.get(feature_key) or "").strip()
        if bound_model_key:
            for item in models:
                if not isinstance(item, dict):
                    continue
                if str(item.get("key") or "").strip() != bound_model_key:
                    continue
                if item.get("enabled", True) is False:
                    break
                selected = item
                break
    if default_key:
        if selected is None:
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
    return str(base_url or "").strip().rstrip("/")


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


VOICE_TRANSCRIPT_ALIAS_TERMS = {
    "上证指数": ["上证综指", "上证综合指数", "沪指", "sh000001"],
    "CPI": ["cpi", "居民消费价格指数"],
    "PPI": ["ppi", "工业生产者出厂价格指数"],
    "PMI": ["pmi", "采购经理人指数"],
    "GDP": ["gdp", "国内生产总值"],
    "PE": ["pe", "市盈率"],
    "PB": ["pb", "市净率"],
    "PS": ["ps", "市销率"],
    "ROE": ["roe", "净资产收益率"],
    "EPS": ["eps", "每股收益"],
    "AI": ["ai", "a i", "a. i."],
    "AI算力": ["ai 算力", "人工智能算力"],
    "腾讯控股": ["腾讯", "00700"],
    "中芯国际": ["中芯国际", "688981", "0981"],
    "贵州茅台": ["茅台", "600519"],
    "宁德时代": ["300750"],
    "中国银行": ["601988"],
    "招商银行": ["600036"],
    "比亚迪": ["002594"],
    "寒武纪": ["688256"],
    "美团-W": ["美团"],
    "阿里巴巴-W": ["阿里", "阿里巴巴"],
}

VOICE_TRANSCRIPT_REGEX_REPLACEMENTS = [
    (re.compile(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])"), ""),
    (re.compile(r"[ \t]+\n"), "\n"),
    (re.compile(r"\n{3,}"), "\n\n"),
    (re.compile(r"[ ]{2,}"), " "),
    (re.compile(r"[,，]{2,}"), "，"),
    (re.compile(r"[。\.]{2,}"), "。"),
    (re.compile(r"[；;]{2,}"), "；"),
    (re.compile(r"[!！]{2,}"), "！"),
    (re.compile(r"[?？]{2,}"), "？"),
    (re.compile(r"(?<![A-Za-z])(pe|pb|ps|roe|eps|cpi|ppi|pmi|gdp)(?![A-Za-z])", re.IGNORECASE), lambda match: match.group(1).upper()),
    (re.compile(r"\bai\b", re.IGNORECASE), "AI"),
    (re.compile(r"\ba\s*i\b", re.IGNORECASE), "AI"),
]


def _apply_voice_transcript_rule_cleanup(text, domain_glossary_enabled=True):
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    for pattern, replacement in VOICE_TRANSCRIPT_REGEX_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)
    if domain_glossary_enabled:
        for canonical, aliases in VOICE_TRANSCRIPT_ALIAS_TERMS.items():
            for alias in aliases:
                alias_text = str(alias or "").strip()
                if not alias_text:
                    continue
                if re.fullmatch(r"[A-Za-z0-9 ._-]+", alias_text):
                    cleaned = re.sub(
                        rf"(?<![A-Za-z0-9]){re.escape(alias_text)}(?![A-Za-z0-9])",
                        canonical,
                        cleaned,
                        flags=re.IGNORECASE,
                    )
                else:
                    cleaned = cleaned.replace(alias_text, canonical)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


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
    api_key = str(config.get("api_key") or "").strip() or get_llm_api_key(config.get("key"))
    if not api_key:
        raise RuntimeError("llm_api_key_missing")
    endpoint_base = _normalize_openai_compatible_base_url(config.get("base_url"))
    if not endpoint_base:
        raise RuntimeError("llm_base_url_missing")
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

    def _strip_transcript_editorial_preface(text):
        normalized = str(text or "").strip()
        if not normalized:
            return ""
        normalized = re.sub(r"^```[\w-]*\s*", "", normalized)
        normalized = re.sub(r"\s*```$", "", normalized).strip()
        preface_patterns = [
            r"^(?:以下(?:是|为)?|下面(?:是|为)?)(?:整理后|修正后|修订后|润色后|优化后|加工后|增强后)?(?:的)?(?:文本|内容|版本|结果|正文|转写稿|整理稿)[：:\s]*",
            r"^(?:已|已经)?(?:在不改变原意的前提下|不改变原意地)?(?:将|把)?(?:原始)?转写(?:内容)?(?:进行|做了)?(?:轻度|轻量)?(?:整理|修复|润色|优化|加工)[：:\s]*",
            r"^由于原始转写存在.{0,80}?(?:表达|版本|内容)[：:\s]*",
            r"^(?:说明|注|备注)[：:\s].{0,120}$",
            r"^(?:我已|我会|现已|这里已)(?:在不改变原意的前提下)?.{0,80}?(?:如下|如下所示)[：:\s]*",
        ]
        previous = None
        while normalized and normalized != previous:
            previous = normalized
            for pattern in preface_patterns:
                candidate = re.sub(pattern, "", normalized, flags=re.IGNORECASE | re.DOTALL).strip()
                if candidate != normalized:
                    normalized = candidate
            normalized = re.sub(r"^(?:整理稿|修订稿|优化稿|最终文本|正文)[：:\s]*", "", normalized).strip()
            normalized = re.sub(r"^\s*[•\-]\s*", "", normalized).strip()
        return normalized

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
            "不要输出任何解释、说明、前言、后记、免责声明、处理备注或“以下是整理稿”之类的引导语，只输出最终正文。"
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
        llm_model = get_default_llm_config(purpose="general", feature_code="review_voice_enhancement")
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
        normalized_enhanced = _strip_transcript_editorial_preface(enhanced_text)
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
        llm_model = get_default_llm_config(purpose="general", feature_code="review_draft_generation")
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
        llm_model = get_default_llm_config(purpose="general", feature_code="review_input_polish")
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
        llm_model = get_default_llm_config(purpose="general", feature_code="review_compose_generation")
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
                "annotation_points": [],
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
        annotation_summary = str(detail.get("annotation_summary") or "").strip()
        if annotation_summary and annotation_summary not in bucket["annotation_points"]:
            bucket["annotation_points"].append(annotation_summary)
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
        supporting = "；".join((bucket["annotation_points"] or bucket["signal_points"] or bucket["summary_points"])[:2]).strip()
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
    normalized_watchlist = [str(item).strip() for item in (selected_watchlist or []) if str(item).strip()]
    if not normalized_watchlist:
        return {
            "sector_summary": "",
            "sector_profiles": [],
            "items": [],
            "annotation_evidence": [],
            "llm_model": None,
            "workflow_meta": {
                "status": "skipped",
                "reason": "watchlist_not_selected",
            },
        }

    def _watchlist_input_executor(state, runtime, node, upstream):
        watchlist_items = [str(item).strip() for item in (runtime.get("selected_watchlist") or []) if str(item).strip()]
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
        matched = build_watchlist_annotation_context(
            tenant_slug=str(runtime.get("tenant_slug") or "").strip().lower(),
            selected_watchlist=state.get("watchlist_items") or [],
            details_map=details_map,
        )
        if not matched:
            raise ValueError("review_watchlist_detail_not_found")
        if runtime.get("job_code"):
            report_user_async_job_progress(
                runtime["job_code"],
                stage="watchlist_context_loading",
                percent=54,
                summary="正在装载自选股上下文",
                log_text="已匹配股票基础信息，并优先装载 K 线标注、板块归属和信号摘要。",
                extra_result={"selected_watchlist": [str(item.get("name") or "").strip() for item in matched]},
            )
        return {
            "detail": "已加载个股基础信息、K 线标注、基本面摘要和板块信号。",
            "state_updates": {"matched_watchlist_details": matched},
            "context_preview": {
                "matched_count": len(matched),
                "annotation_count": sum(len(item.get("annotations") or []) for item in matched if isinstance(item, dict)),
            },
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
            },
            "context_preview": {"sector_count": len(sector_profiles)},
        }

    def _watchlist_llm_executor(state, runtime, node, upstream):
        matched = state.get("matched_watchlist_details") if isinstance(state.get("matched_watchlist_details"), list) else []
        labels = []
        for detail in matched:
            if not isinstance(detail, dict):
                continue
            name = str(detail.get("name") or detail.get("code") or "").strip()
            code = str(detail.get("code") or "").strip()
            security_code = str(detail.get("security_code") or detail.get("gtsCode") or "").strip().upper()
            if not security_code and code:
                market = str(detail.get("market") or "").strip().upper()
                security_code = f"{code}.{market}" if market in {"SH", "SZ", "BJ", "HK"} else code
            if name:
                labels.append(f"{name}{f'（{security_code or code}）' if (security_code or code) else ''}")
        if not labels:
            raise RuntimeError("review_watchlist_analysis_missing_item")
        request_text = f"请进行{_get_review_period_label(runtime.get('review_period'))}，分析以下自选股：{'、'.join(labels)}。"
        if runtime.get("job_code"):
            report_user_async_job_progress(
                runtime["job_code"],
                stage="watchlist_gangtise_sse_started",
                percent=70,
                summary="正在调用 Gangtise Agent SSE",
                log_text=f"已提交 {len(labels)} 只自选股，等待多股综合分析返回。",
                extra_result={"endpoint": "/application/open-ai/ai/chat/sse", "watchlist_count": len(labels)},
            )
        progress_state = {"last_at": 0.0, "last_count": 0}
        sse_chunks = []
        sse_raw_events = []

        def _report_sse_progress(event_count, event_text, force=False, raw_event=""):
            if not runtime.get("job_code"):
                return
            if event_text:
                sse_chunks.append(str(event_text))
            if raw_event:
                sse_raw_events.append(str(raw_event))
            now_value = time.time()
            if not force and event_count - progress_state["last_count"] < 4 and now_value - progress_state["last_at"] < 5:
                return
            progress_state["last_at"] = now_value
            progress_state["last_count"] = event_count
            partial_text = _merge_gangtise_sse_texts(sse_chunks)
            raw_text = "\n\n".join(sse_raw_events).strip()
            report_user_async_job_progress(
                runtime["job_code"],
                stage="watchlist_gangtise_sse_streaming",
                percent=min(80, 70 + min(10, event_count // 4)),
                summary="Gangtise Agent SSE 正在返回多股分析",
                extra_result={
                    "event_count": event_count,
                    "partial_text": partial_text[:12000],
                    "raw_text": raw_text[:12000],
                },
            )

        gangtise_result = call_gangtise_agent_sse(
            request_text,
            trace_id=f"review-{runtime.get('job_code') or int(time.time() * 1000)}",
            mode="deep_research",
            web_enable=True,
            timeout=180,
            progress_callback=_report_sse_progress,
        )
        raw_text = str(gangtise_result.get("raw_text") or "").strip()
        # ``text`` is the protocol-decoded phase=answer stream. Keep the
        # complete SSE response separately for diagnostics, never as review copy.
        combined_text = str(gangtise_result.get("text") or "").strip()
        if not combined_text:
            raise RuntimeError("review_watchlist_gangtise_empty_response")
        annotation_evidence = []
        for detail in matched:
            stock_name = str(detail.get("name") or "").strip()
            stock_code = str(detail.get("code") or "").strip()
            annotations = detail.get("annotations") if isinstance(detail.get("annotations"), list) else []
            for item in annotations[:4]:
                if not isinstance(item, dict):
                    continue
                annotation_evidence.append({
                    "annotation_id": item.get("id"),
                    "stock_name": stock_name,
                    "stock_code": stock_code,
                    "date_label": str(item.get("dateLabel") or item.get("candle_date") or "").strip(),
                    "content": get_watchlist_annotation_content(item),
                    # Retain legacy-shaped fields for previously published reviews.
                    "title": str(item.get("title") or "").strip(),
                    "note": str(item.get("note") or "").strip(),
                    "trigger": str(item.get("trigger") or "").strip(),
                })
        if runtime.get("job_code"):
            report_user_async_job_progress(
                runtime["job_code"],
                stage="watchlist_analysis_done",
                percent=82,
                summary="Gangtise 多股综合分析已生成",
                log_text="Gangtise Agent SSE 已返回完整多股分析，正在与大V输入合并。",
                extra_result={"duration_ms": gangtise_result.get("duration_ms") or 0, "event_count": gangtise_result.get("events") or 0},
            )
        return {
            "detail": "已通过 Gangtise Agent SSE 生成完整多股综合分析。",
            "state_updates": {
                "analysis_result": {
                    "sector_summary": "",
                    "sector_profiles": copy.deepcopy(state.get("sector_profiles") or []),
                    "items": [],
                    "combined_text": combined_text,
                    "raw_text": raw_text,
                    "provider": gangtise_result.get("provider") or "Gangtise Agent助手 SSE",
                    "endpoint": gangtise_result.get("endpoint") or "/application/open-ai/ai/chat/sse",
                    "request_text": request_text,
                    "annotation_evidence": annotation_evidence,
                    "llm_model": {
                        "key": "gangtise_agent_sse",
                        "label": gangtise_result.get("provider") or "Gangtise Agent助手 SSE",
                        "provider": "Gangtise",
                        "model_name": "deep_research",
                        "purpose": "multi_stock_review",
                        "stage": "watchlist_gangtise_sse",
                    },
                }
            },
            "context_preview": {"item_count": len(labels), "provider": "Gangtise Agent助手 SSE"},
        }

    def _watchlist_output_executor(state, runtime, node, upstream):
        result = copy.deepcopy(state.get("analysis_result") or {})
        result["workflow_meta"] = build_declared_agent_workflow_meta(
            workflow_definition,
            extras={"last_execution_steps": copy.deepcopy(upstream)},
        )
        return {
            "detail": "已封装 Gangtise Agent SSE 多股综合分析结果。",
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
    llm_model = get_default_llm_config(purpose="general", feature_code="review_user_input_summary")
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
    summary = summary[:150].strip()
    if not summary:
        raise RuntimeError("review_summary_empty_llm_response")
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


def _extract_watchlist_comment_keywords_by_rule(comment_text, stock_detail=None, limit=6):
    normalized = re.sub(r"\s+", " ", str(comment_text or "").strip())
    if not normalized:
        return []
    detail = stock_detail if isinstance(stock_detail, dict) else {}
    candidates = []
    for fixed_item in [
        str(detail.get("name") or "").strip(),
        str(detail.get("industry") or "").strip(),
        str(detail.get("focus") or "").strip(),
    ]:
        if fixed_item and fixed_item not in candidates:
            candidates.append(fixed_item)
    token_candidates = re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z][A-Za-z0-9.+-]{1,15}", normalized)
    stop_words = {
        "这个", "那个", "我们", "你们", "他们", "目前", "因为", "如果", "还是", "已经", "继续", "应该", "可以",
        "需要", "看到", "感觉", "这里", "一个", "这只", "股票", "公司", "板块", "市场", "今天", "最近", "以及",
        "但是", "还有", "就是", "自己", "觉得", "没有", "不是", "的话", "一下", "这个股", "一下子",
    }
    for item in token_candidates:
        token = str(item or "").strip()
        if len(token) < 2 or token in stop_words:
            continue
        if token not in candidates:
            candidates.append(token)
    return candidates[: max(1, int(limit or 6))]


def _build_watchlist_comment_labeling_fallback(comment_text, stock_detail=None):
    normalized = re.sub(r"\s+", " ", str(comment_text or "").strip())
    detail = stock_detail if isinstance(stock_detail, dict) else {}
    lowered = normalized.lower()
    keywords = _extract_watchlist_comment_keywords_by_rule(normalized, detail, limit=8)
    labels = []
    topic_label = "观点跟踪"
    sentiment_label = "中性"
    summary = normalized[:90]
    if any(keyword in normalized for keyword in ["风险", "回撤", "跌破", "谨慎", "承压", "减仓", "危险", "波动"]):
        sentiment_label = "谨慎"
        topic_label = "风险提示"
        labels.extend(["风险提示", "负向反馈"])
    elif any(keyword in normalized for keyword in ["看好", "增持", "突破", "修复", "超预期", "回暖", "加强", "机会"]):
        sentiment_label = "积极"
        topic_label = "机会判断"
        labels.extend(["机会判断", "正向反馈"])
    elif any(keyword in normalized for keyword in ["为什么", "请问", "？", "?", "怎么看", "能否", "是不是"]):
        sentiment_label = "追问"
        topic_label = "问题追踪"
        labels.extend(["问题追踪", "待验证"])
    if any(keyword in normalized for keyword in ["财报", "业绩", "利润", "收入", "毛利", "估值", "PE", "PB", "现金流"]):
        labels.append("基本面")
        if topic_label == "观点跟踪":
            topic_label = "基本面判断"
    if any(keyword in normalized for keyword in ["K线", "均线", "支撑", "压力", "放量", "缩量", "趋势", "形态"]):
        labels.append("技术面")
        if topic_label == "观点跟踪":
            topic_label = "走势观察"
    if any(keyword in normalized for keyword in ["催化", "政策", "订单", "回购", "纪要", "行业", "景气"]):
        labels.append("催化跟踪")
    labels = _hermes_unique_texts(labels or ["观点跟踪"], limit=6)
    if not summary:
        summary = "围绕该股的阶段判断与追踪意见。"
    return {
        "labels": labels,
        "keywords": keywords,
        "sentiment_label": sentiment_label,
        "topic_label": topic_label,
        "summary": summary,
        "source": "rule",
        "llm_model": None,
    }


def label_watchlist_comment_with_llm(comment_text, stock_detail=None, tenant_slug="", entry_point="watchlist_comment"):
    normalized = re.sub(r"\s+", " ", str(comment_text or "").strip())
    fallback = _build_watchlist_comment_labeling_fallback(normalized, stock_detail=stock_detail)
    if not normalized:
        return fallback
    llm_model = get_default_llm_config(purpose="general", feature_code="watchlist_comment_labeling")
    if not llm_model:
        return fallback
    detail = stock_detail if isinstance(stock_detail, dict) else {}
    system_prompt = (
        "你是投研社区评论标注助手。"
        "请对自选股评论做轻量结构化标注，方便大V后台统计评论趋势。"
        "你不能编造不存在的信息。"
        "输出必须是 JSON。"
    )
    user_prompt = "\n".join(
        [
            f"股票：{str(detail.get('name') or detail.get('code') or '未指明股票').strip()}",
            f"代码：{str(detail.get('code') or '').strip()}",
            f"板块：{str(detail.get('industry') or detail.get('focus') or '未指明板块').strip()}",
            "请根据下面评论输出 JSON：",
            '{"labels":["标签1","标签2"],"keywords":["关键词1","关键词2"],"sentiment_label":"积极/中性/谨慎/追问","topic_label":"一句话主题","summary":"30字内摘要"}',
            "要求：",
            "1. labels 控制在 2 到 5 个，适合做运营统计。",
            "2. keywords 控制在 3 到 6 个，尽量提炼具体名词或判断点。",
            "3. summary 控制在 30 个中文字符内。",
            "4. 只输出 JSON，不要解释。",
            "",
            f"评论内容：{normalized}",
        ]
    )
    try:
        raw = call_openai_compatible_llm(
            llm_model,
            system_prompt,
            user_prompt,
            feature_code="watchlist_comment_labeling",
            feature_label="自选股评论标注",
            tenant_slug=str(tenant_slug or "").strip().lower(),
            entry_point=str(entry_point or "").strip() or "watchlist_comment",
            metadata={
                "stock_code": str(detail.get("code") or "").strip(),
                "stock_name": str(detail.get("name") or "").strip(),
            },
            request_timeout_seconds=35,
        )
        parsed = _extract_json_payload_from_llm_text(raw, {})
    except Exception:
        return fallback
    llm_labels = [str(item).strip() for item in (parsed.get("labels") if isinstance(parsed.get("labels"), list) else []) if str(item).strip()]
    llm_keywords = [str(item).strip() for item in (parsed.get("keywords") if isinstance(parsed.get("keywords"), list) else []) if str(item).strip()]
    sentiment_label = str(parsed.get("sentiment_label") or "").strip()
    topic_label = str(parsed.get("topic_label") or "").strip()
    summary = str(parsed.get("summary") or "").strip()
    return {
        "labels": _hermes_unique_texts(llm_labels or fallback.get("labels") or [], limit=6),
        "keywords": _hermes_unique_texts(llm_keywords or fallback.get("keywords") or [], limit=8),
        "sentiment_label": sentiment_label or fallback.get("sentiment_label") or "中性",
        "topic_label": topic_label or fallback.get("topic_label") or "观点跟踪",
        "summary": (summary or fallback.get("summary") or "")[:60].strip(),
        "source": "llm",
        "llm_model": {
            "key": llm_model.get("key"),
            "label": llm_model.get("label"),
            "provider": llm_model.get("provider"),
            "model_name": llm_model.get("model_name"),
            "purpose": llm_model.get("purpose"),
        },
    }


def _compose_review_watchlist_analysis_text(section):
    payload = section if isinstance(section, dict) else {}
    combined_text = str(payload.get("combined_text") or "").strip()
    if combined_text:
        return combined_text
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
    include_summary=True,
):
    normalized_source = str(source_text or "").strip()
    if not normalized_source:
        raise ValueError("review_source_text_required")
    watchlist_items = [str(item).strip() for item in (selected_watchlist or []) if str(item).strip()]
    if include_summary and job_code:
        report_user_async_job_progress(
            job_code,
            stage="review_summary_generating",
            percent=24,
            summary="正在生成复盘摘要",
            log_text="摘要仅基于用户自主输入内容生成，不引用自选股归纳。",
        )
    if include_summary:
        summary_result = summarize_review_user_input_with_llm(
            source_text=normalized_source,
            review_period=review_period,
            source_mode=source_mode,
            speaker_name=speaker_name,
            entry_point=entry_point,
            tenant_slug=tenant_slug,
        )
    else:
        summary_result = {
            "summary": "",
            "llm_model": None,
        }
    if watchlist_items:
        if job_code:
            report_user_async_job_progress(
                job_code,
                stage="review_watchlist_analyzing",
                percent=46,
                summary="正在准备 Gangtise 多股综合分析",
                log_text="正在装载已选自选股上下文，随后调用 Gangtise Agent SSE 生成个股与组合分析。",
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
    else:
        if job_code:
            report_user_async_job_progress(
                job_code,
                stage="review_watchlist_skipped",
                percent=46,
                summary="未选择自选股，跳过归纳总结",
                log_text="本轮仅生成摘要和用户输入转化内容，不追加自选股归纳。",
            )
        watchlist_result = {
            "sector_summary": "",
            "sector_profiles": [],
            "items": [],
            "annotation_evidence": [],
            "llm_model": None,
            "workflow_meta": {
                "status": "skipped",
                "reason": "watchlist_not_selected",
            },
        }
    user_input_section = {
        "source_mode": str(source_mode or "").strip().lower() or "manual",
        "source_mode_label": _normalize_review_source_mode_label(source_mode),
        "display_text": normalized_source,
        "summary_source": "llm_user_input_only",
    }
    watchlist_text = _compose_review_watchlist_analysis_text(watchlist_result)
    watchlist_heading = "Gangtise 多股综合分析" if str(watchlist_result.get("combined_text") or "").strip() else "自选股归纳分析"
    final_text = "\n\n".join(
        part for part in [
            f"【复盘摘要】\n{summary_result['summary']}" if str(summary_result.get("summary") or "").strip() else "",
            f"【用户输入转化内容】\n{user_input_section['display_text']}",
            f"【{watchlist_heading}】\n{watchlist_text}" if watchlist_text else "",
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
            "combined_text": str(watchlist_result.get("combined_text") or "").strip(),
            "raw_text": str(watchlist_result.get("raw_text") or "").strip(),
            "provider": str(watchlist_result.get("provider") or "").strip(),
            "endpoint": str(watchlist_result.get("endpoint") or "").strip(),
            "request_text": str(watchlist_result.get("request_text") or "").strip(),
            "annotation_evidence": copy.deepcopy(watchlist_result.get("annotation_evidence") or []),
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
            summary="复盘预览已准备完成",
            log_text=(
                "用户输入部分和 Gangtise 多股综合分析已合成，正在返回预览结果。"
                if watchlist_items else
                "摘要和用户输入转化内容已合成，正在返回预览结果。"
            ),
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


def _load_local_whisper_model(transcription_cfg=None):
    config = transcription_cfg or get_voice_transcription_config()
    cache_key = "local_whisper_model:" + "|".join([
        str(config.get("local_model_size") or ""),
        str(config.get("local_device") or ""),
        str(config.get("local_compute_type") or ""),
    ])
    cached = g.get(cache_key)
    if cached is not None:
        return cached
    if WhisperModel is None:
        raise RuntimeError("local_transcriber_dependency_missing")
    try:
        model = WhisperModel(
            config["local_model_size"],
            device=config["local_device"],
            compute_type=config["local_compute_type"],
        )
    except Exception as exc:
        raise RuntimeError(f"local_transcriber_init_failed:{exc}") from exc
    setattr(g, cache_key, model)
    return model


def _load_local_embedding_model(embedding_cfg=None):
    config = embedding_cfg or get_voice_embedding_config()
    model_name = str(config.get("local_model_name") or "").strip()
    cache_key = f"local_embedding_model:{model_name}"
    cached = g.get(cache_key)
    if cached is not None:
        return cached
    if SentenceTransformer is None:
        raise RuntimeError("local_embedding_dependency_missing")
    try:
        model = SentenceTransformer(model_name)
    except Exception as exc:
        raise RuntimeError(f"local_embedding_init_failed:{exc}") from exc
    setattr(g, cache_key, model)
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


def _get_external_feature_model(feature_code):
    model = get_default_llm_config(purpose="general", feature_code=feature_code)
    if not model:
        raise RuntimeError(f"feature_model_not_configured:{feature_code}")
    api_key = get_llm_api_key(model.get("key"))
    if not api_key:
        raise RuntimeError(f"feature_model_api_key_missing:{feature_code}")
    base_url = _normalize_openai_compatible_base_url(model.get("base_url"))
    if not base_url:
        raise RuntimeError(f"feature_model_base_url_missing:{feature_code}")
    return model, api_key, base_url


def _transcribe_audio_with_python(audio_bytes, filename, content_type, transcription_cfg=None):
    config = transcription_cfg or get_voice_transcription_config()
    _model, api_key, base_url = _get_external_feature_model("voice_transcription_api")
    response = requests.post(
        f"{base_url}/audio/transcriptions",
        headers={"Authorization": f"Bearer {api_key}"},
        data={
            "model": config["api_model"],
            "language": config["api_language"],
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


def _transcribe_audio_locally(audio_bytes, filename, transcription_cfg=None):
    config = transcription_cfg or get_voice_transcription_config()
    temp_path = _write_temp_audio_file(audio_bytes, filename)
    try:
        model = _load_local_whisper_model(config)
        segments, _info = model.transcribe(
            str(temp_path),
            language=config["api_language"] or "zh",
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
    config = get_voice_transcription_config()
    normalized_engine = str(engine or "local").strip().lower()
    if normalized_engine == "local":
        return _transcribe_audio_locally(audio_bytes, filename, config), "local"
    if normalized_engine == "api":
        return _transcribe_audio_with_python(audio_bytes, filename, content_type, config), "api"
    raise RuntimeError("unsupported_transcription_engine")


def _build_text_embedding_with_api(text, feature_code="", feature_label="", tenant_slug="", entry_point="", metadata=None):
    config = get_voice_embedding_config()
    model_config, api_key, base_url = _get_external_feature_model("embedding_api")
    model_name = str(config.get("api_model") or model_config.get("model_name") or "").strip()
    if not model_name:
        raise RuntimeError("embedding_model_name_missing")
    request_started = time.perf_counter()
    response = requests.post(
        f"{base_url}/embeddings",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model_name,
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
        model_name=model_name,
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
        local_model_name = get_voice_embedding_config().get("local_model_name")
        return _build_text_embedding_locally(text), "local", local_model_name
    if normalized_engine == "api":
        return _build_text_embedding_with_api(
            text,
            feature_code=feature_code,
            feature_label=feature_label,
            tenant_slug=tenant_slug,
            entry_point=entry_point,
            metadata=metadata,
        ), "api", get_voice_embedding_config().get("api_model")
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
                        -- Legacy rows can have an empty knowledge_id. They are independent
                        -- entries and must not collapse into a single DISTINCT group.
                        SELECT DISTINCT ON (COALESCE(NULLIF(BTRIM(knowledge_id), ''), CONCAT('__legacy_row_', id)))
                            id, knowledge_id, knowledge_type, title, summary, body_text, source_detail,
                            vector_namespace, embedding_engine, embedding_model, metadata_json, created_at
                        FROM knowledge_embeddings
                        WHERE tenant_slug = %s
                        ORDER BY COALESCE(NULLIF(BTRIM(knowledge_id), ''), CONCAT('__legacy_row_', id)), created_at DESC, id DESC
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
                    -- Keep legacy records with an empty knowledge_id as separate entries.
                    SELECT DISTINCT ON (COALESCE(NULLIF(BTRIM(knowledge_id), ''), CONCAT('__legacy_row_', id)))
                        id, knowledge_id, knowledge_type, title, summary, body_text, source_detail,
                        vector_namespace, embedding_engine, embedding_model, embedding_json, metadata_json, created_at
                    FROM knowledge_embeddings
                    WHERE tenant_slug = %s
                    ORDER BY COALESCE(NULLIF(BTRIM(knowledge_id), ''), CONCAT('__legacy_row_', id)), created_at DESC, id DESC
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


def build_shared_agent_evidence_policy():
    return {
        "shared_capability": "evidence_chain",
        "knowledge_first": True,
        "priority": [
            "knowledge_vector_retrieval",
            "evidence_relevance_filter",
            "platform_context_merge",
            "llm_synthesis",
        ],
        "description": "智能体在需要事实依据、研究上下文或证据归因时，优先从当前租户知识库向量库召回，再进入统一证据链整理。",
    }


def _extract_json_payload_from_llm_text(text, default, strict=False):
    normalized = str(text or "").strip()
    if not normalized:
        if strict:
            raise RuntimeError("invalid_llm_json_response:empty")
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
    if strict:
        raise RuntimeError("invalid_llm_json_response")
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
    llm_model = get_default_llm_config(purpose="general", feature_code="knowledge_query_filter")
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
    parsed = _extract_json_payload_from_llm_text(
        raw,
        {"relevant_ids": [], "reason": ""},
        strict=True,
    )
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
    shared_policy = build_shared_agent_evidence_policy()

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
                "shared_retrieval_policy": copy.deepcopy(shared_policy),
            },
            "context_preview": {
                "query_chars": len(normalized_query),
                "source_count": len(normalized_sources),
                "knowledge_first": True,
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
            app.logger.exception("Retrieval agent dependency failed")
            raise RuntimeError(f"evidence_retrieval_failed:{str(exc)[:240]}") from exc
        return {
            "detail": f"已召回 {len(result.get('evidence_items') or [])} 条候选结果。",
            "state_updates": {"retrieval_result": result},
            "context_preview": {
                "match_count": len(result.get("evidence_items") or []),
                "shared_capability": "evidence_chain",
            },
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
        llm_model = get_default_llm_config(
            purpose="general",
            feature_code=f"{runtime.get('feature_namespace')}_answer",
        )
        if not llm_model:
            raise RuntimeError(
                f"{runtime.get('feature_namespace')}_answer_llm_not_configured"
            )
        original_matches = result.get("evidence_items") or []
        if not original_matches:
            return {
                "status": "ok",
                "detail": "没有召回候选条目，保留空证据集并交由大模型明确说明证据边界。",
                "state_updates": {
                    "filtered_result": result,
                    "llm_notice": "已提交给大模型；当前没有召回到候选证据。",
                    "llm_mode": "model_pending",
                    "llm_enabled": True,
                    "llm_model": copy.deepcopy(llm_model),
                },
                "context_preview": {"filtered": False, "kept_count": 0},
            }
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
                    # The answer stage needs the endpoint as well as the model label.
                    # Keep the normalized backend-only config intact across workflow state.
                    "llm_model": copy.deepcopy(active_model),
                },
                "context_preview": {
                    "filtered": True,
                    "kept_count": len(filtered_matches),
                    "dropped_count": max(0, len(original_matches) - len(filtered_matches)),
                },
            }
        except Exception as exc:
            app.logger.exception("Evidence relevance filtering failed")
            raise RuntimeError(f"evidence_relevance_filter_failed:{str(exc)[:240]}") from exc

    def _retrieval_answer_executor(state, runtime, node, upstream):
        result = copy.deepcopy(state.get("filtered_result") or state.get("retrieval_result") or {})
        llm_requested = bool(state.get("llm_requested"))
        llm_model = copy.deepcopy(state.get("llm_model") or {})
        llm_notice = str(state.get("llm_notice") or "当前为纯知识检索模式，未提交给大模型。").strip()
        llm_enabled = bool(state.get("llm_enabled"))
        llm_mode = str(state.get("llm_mode") or "retrieval_only").strip() or "retrieval_only"
        if llm_requested:
            if not llm_model:
                raise RuntimeError(
                    f"{runtime.get('feature_namespace')}_answer_llm_not_configured"
                )
            filtered_matches = result.get("evidence_items") or []
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
            except Exception as exc:
                app.logger.exception("Evidence chain answer generation failed")
                raise RuntimeError(f"{runtime.get('feature_namespace')}_answer_llm_failed:{str(exc)[:240]}") from exc
            if not str(llm_answer or "").strip():
                raise RuntimeError(f"{runtime.get('feature_namespace')}_answer_empty_llm_response")
            result["answer"] = str(llm_answer).strip()
            llm_enabled = True
            llm_mode = "model_answered"
            llm_notice = (
                f"{llm_notice}\n\n"
                f"当前回答已由通用模型生成：{answer_model.get('label') or answer_model.get('model_name') or answer_model.get('key')}。"
                "下方保留的是过滤后的相关知识命中结果。"
            ).strip()
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
    final_result["retrieval_policy"] = copy.deepcopy(execution["state"].get("shared_retrieval_policy") or shared_policy)
    final_result["workflow_meta"] = build_declared_agent_workflow_meta(
        workflow_definition,
        extras={"last_execution_steps": copy.deepcopy(execution.get("node_results") or {})},
    )
    return final_result


HERMES_QUERY_INTENT_PROMPT = (
    "你是小金智能体的任务路由器。"
    "你的职责不是直接回答用户，而是只使用大模型语义理解，把用户问题路由成最合适的任务类型，并决定需要调用哪些工具。"
    "不要使用 embedding、向量检索或关键词初筛来猜测意图。"
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
    "watchlist.detail",
    "indicator.detail",
    "dashboard.context",
    "attachment.context",
}

HERMES_INTENT_ROUTE_GROUPS = {
    "knowledge_lookup": "knowledge_qa",
    "watchlist_fundamental": "market_data_query",
    "smart_indicator_explain": "chart_visualization",
    "evidence_chain_analysis": "review_assistant",
    "dashboard_interpretation": "dashboard_indicator_assistant",
    "multi_tool_research": "content_generation",
    "product_help": "product_help_or_smalltalk",
    "small_talk": "product_help_or_smalltalk",
    "out_of_scope_redirect": "product_help_or_smalltalk",
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
    "indicator": ["智能指标", "指标", "公式", "提示词", "算法", "js", "计算", "引用指标", "指数", "k线", "k线图", "趋势", "趋势图", "走势图", "分布", "分布图", "可视化", "蜡烛图"],
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

HERMES_VISUAL_MODE_KEYWORDS = {
    "distribution_chart": ["分布图", "分布统计", "分布", "直方图", "柱状分布", "区间分布"],
    "kline_chart": ["k线图", "k线走势", "k线", "蜡烛图", "candlestick"],
    "line_chart": ["线性趋势图", "历史数据线图", "折线图", "线性图", "趋势线图", "趋势线", "线图", "趋势图", "走势图", "line chart"],
}

HERMES_TASK_FAMILY_LABELS = {
    "small_talk": "闲聊",
    "data_visualization": "数据展示",
    "report_interpretation": "报告解读",
    "content_generation": "内容生成",
    "product_help": "产品帮助",
    "research_qa": "研究问答",
    "out_of_scope_redirect": "范围收口",
}

HERMES_CONTENT_GENERATION_KEYWORDS = [
    "生成", "起草", "草稿", "改写", "润色", "整理", "重写", "写一段", "写一个", "写篇", "摘要", "总结",
    "提炼", "内容生成", "发布文案", "标题", "提纲",
]

HERMES_REPORT_INTERPRETATION_KEYWORDS = [
    "报告", "研报", "文件", "上传", "pdf", "docx", "txt", "csv", "解读", "速读", "拆解", "读一下", "看一下",
]


def _contains_any_keyword(text, keywords):
    normalized = str(text or "").strip().lower()
    for item in keywords:
        keyword = str(item or "").strip().lower()
        if keyword and keyword in normalized:
            return True
    return False


def infer_hermes_visual_mode(question_text, preferred_mode=""):
    preferred_key = str(preferred_mode or "").strip().lower()
    if preferred_key in {"line_chart", "kline_chart", "distribution_chart"}:
        return preferred_key
    normalized = str(question_text or "").strip().lower()
    if not normalized:
        return ""
    for mode_key in ["distribution_chart", "kline_chart", "line_chart"]:
        if _contains_any_keyword(normalized, HERMES_VISUAL_MODE_KEYWORDS.get(mode_key) or []):
            return mode_key
    return ""


def infer_hermes_task_family(question_text="", preferred_mode="", attachments=None, selected_knowledge_ids=None, intent=""):
    text = str(question_text or "").strip()
    lowered = text.lower()
    attachments = attachments if isinstance(attachments, list) else []
    selected_knowledge_ids = selected_knowledge_ids if isinstance(selected_knowledge_ids, list) else []
    intent_key = str(intent or "").strip().lower()
    visual_mode = infer_hermes_visual_mode(text, preferred_mode=preferred_mode)
    preferred_key = str(preferred_mode or "").strip().lower()
    if intent_key == "out_of_scope_redirect":
        return "out_of_scope_redirect"
    if intent_key == "small_talk":
        return "small_talk"
    if visual_mode:
        return "data_visualization"
    if preferred_key == "report_interpretation":
        return "report_interpretation"
    if preferred_key == "content_generation":
        return "content_generation"
    if preferred_key in {"small_talk", "chat"}:
        return "small_talk"
    if intent_key == "product_help":
        return "product_help"
    if attachments and _contains_any_keyword(lowered, HERMES_REPORT_INTERPRETATION_KEYWORDS):
        return "report_interpretation"
    if selected_knowledge_ids and _contains_any_keyword(lowered, HERMES_REPORT_INTERPRETATION_KEYWORDS):
        return "report_interpretation"
    if _contains_any_keyword(lowered, HERMES_CONTENT_GENERATION_KEYWORDS):
        return "content_generation"
    if _contains_any_keyword(lowered, HERMES_REPORT_INTERPRETATION_KEYWORDS) and attachments:
        return "report_interpretation"
    return "research_qa"


def finalize_hermes_intent_plan(plan, question_text="", attachments=None, selected_knowledge_ids=None):
    normalized_plan = copy.deepcopy(plan if isinstance(plan, dict) else {})
    resolved_mode = infer_hermes_visual_mode(
        question_text,
        preferred_mode=normalized_plan.get("preferred_mode") or "",
    )
    if resolved_mode:
        normalized_plan["preferred_mode"] = resolved_mode
        stock_code = str(normalized_plan.get("stock_code") or "").strip()
        indicator_code = str(normalized_plan.get("indicator_code") or "").strip()
        if stock_code and not indicator_code:
            existing_tools = [
                str(item).strip()
                for item in (normalized_plan.get("tools") if isinstance(normalized_plan.get("tools"), list) else [])
                if str(item).strip()
            ]
            preserved_tools = []
            for tool_name in ["attachment.context"]:
                if tool_name in existing_tools and tool_name not in preserved_tools:
                    preserved_tools.append(tool_name)
            normalized_plan["intent"] = "watchlist_fundamental"
            normalized_plan["display_mode"] = "structured"
            normalized_plan["tools"] = ["watchlist.detail"] + preserved_tools
        if str(normalized_plan.get("intent") or "").strip() == "smart_indicator_explain":
            normalized_plan["display_mode"] = "structured"
    task_family = infer_hermes_task_family(
        question_text=question_text,
        preferred_mode=normalized_plan.get("preferred_mode") or "",
        attachments=attachments,
        selected_knowledge_ids=selected_knowledge_ids,
        intent=normalized_plan.get("intent") or "",
    )
    normalized_plan["task_family"] = task_family
    normalized_plan["capability_label"] = HERMES_TASK_FAMILY_LABELS.get(task_family, "研究问答")
    if task_family == "small_talk" or str(normalized_plan.get("intent") or "").strip() == "small_talk":
        # A greeting must remain a model-only conversation even if the router
        # accidentally returns a research tool in its JSON plan.
        normalized_plan["tools"] = []
    normalized_plan["intent_group"] = HERMES_INTENT_ROUTE_GROUPS.get(
        str(normalized_plan.get("intent") or "").strip(),
        "knowledge_qa",
    )
    return normalized_plan


def _hermes_scope_feature_flags(question_text, selected_knowledge_ids=None, attachments=None, tenant_slug="", preferred_mode=""):
    selected_knowledge_ids = selected_knowledge_ids if isinstance(selected_knowledge_ids, list) else []
    attachments = attachments if isinstance(attachments, list) else []
    text = str(question_text or "").strip()
    preferred_key = str(preferred_mode or "").strip().lower()
    indicator_match = find_indicator_reference_from_text(text, tenant_slug=tenant_slug)
    flags = {
        "watchlist": bool(find_watchlist_code_from_text(text)) or _contains_any_keyword(text, HERMES_SCOPE_KEYWORDS["watchlist"]),
        "evidence": _contains_any_keyword(text, HERMES_SCOPE_KEYWORDS["evidence"]),
        "knowledge": bool(selected_knowledge_ids) or _contains_any_keyword(text, HERMES_SCOPE_KEYWORDS["knowledge"]),
        "indicator": bool(indicator_match) or _contains_any_keyword(text, HERMES_SCOPE_KEYWORDS["indicator"]),
        "dashboard": _contains_any_keyword(text, HERMES_SCOPE_KEYWORDS["dashboard"]),
        "product": _contains_any_keyword(text, HERMES_SCOPE_KEYWORDS["product"]),
        "report": preferred_key == "report_interpretation" or _contains_any_keyword(text, HERMES_REPORT_INTERPRETATION_KEYWORDS),
        "content_generation": preferred_key == "content_generation" or _contains_any_keyword(text, HERMES_CONTENT_GENERATION_KEYWORDS),
        "attachments": bool(attachments),
        "small_talk": _contains_any_keyword(text, HERMES_SMALL_TALK_KEYWORDS),
        "blocked_trading": _contains_any_keyword(text, HERMES_BLOCKED_TRADING_KEYWORDS),
        "out_of_scope": _contains_any_keyword(text, HERMES_OUT_OF_SCOPE_KEYWORDS),
    }
    flags["platform_related"] = any(
        flags[key]
        for key in ["watchlist", "evidence", "knowledge", "indicator", "dashboard", "product", "report", "content_generation", "attachments"]
    )
    return flags


def hermes_scope_guard(question_text, selected_knowledge_ids=None, attachments=None, tenant_slug="", preferred_mode=""):
    text = str(question_text or "").strip()
    flags = _hermes_scope_feature_flags(
        question_text=text,
        selected_knowledge_ids=selected_knowledge_ids,
        attachments=attachments,
        tenant_slug=tenant_slug,
        preferred_mode=preferred_mode,
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
        elif flags["report"] or flags["attachments"]:
            intent_hint = "knowledge_lookup"
        elif flags["content_generation"]:
            intent_hint = "multi_tool_research"
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


def build_hermes_open_scope_result(question_text="", preferred_mode="", selected_knowledge_ids=None, attachments=None, tenant_slug=""):
    flags = _hermes_scope_feature_flags(
        question_text=question_text,
        selected_knowledge_ids=selected_knowledge_ids,
        attachments=attachments,
        tenant_slug=tenant_slug,
        preferred_mode=preferred_mode,
    )
    return {
        "status": "allowed",
        "reason": "当前未启用 Hermes 提示词范围约束，允许按更开放的问题范围继续编排。",
        "message": "",
        "suggestions": [],
        "intent_hint": "small_talk" if flags.get("small_talk") else "",
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
    missing_capability = detect_hermes_missing_capability(question, plan=plan, tool_outputs=tool_outputs)
    missing_capability_tags = []
    if isinstance(missing_capability, dict) and str(missing_capability.get("label") or "").strip():
        missing_capability_tags.append(str(missing_capability.get("label") or "").strip())
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
            "missing_capability": copy.deepcopy(missing_capability) if missing_capability else None,
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
            "missing_capability_tags": missing_capability_tags,
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
            "missing_capability_tags": missing_capability_tags,
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
        "missing_capability_tags": missing_capability_tags,
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
                "missing_capability": copy.deepcopy(missing_capability) if missing_capability else None,
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


def _capability_growth_month_key(value):
    text = str(value or "").strip()
    return text[:7] if re.match(r"^\d{4}-\d{2}", text) else ""


def _capability_growth_labels(values, limit=8):
    counter = Counter(str(value or "").strip() for value in (values or []) if str(value or "").strip())
    return [
        {"label": label, "count": int(count)}
        for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def build_kol_hermes_capability_growth(tenant_slug):
    """Expose auditable research assets before they are used to tune Hermes."""
    tenant_key = str(tenant_slug or "").strip().lower()
    tenant = get_tenant_by_slug(tenant_key)
    if not tenant or str(tenant.get("slug") or "").strip().lower() != tenant_key:
        raise ValueError("tenant_not_found")

    db = get_db()
    turns = db.execute(
        """
        SELECT intent, entry_point, tags_json, memory_summary_json, created_at
        FROM hermes_conversation_turns
        WHERE tenant_slug = ?
        ORDER BY created_at DESC, id DESC
        """,
        (tenant_key,),
    ).fetchall()
    reviews = resolve_tenant_review_snapshots(tenant, tenant.get("review_snapshots"))
    knowledge_available = True
    knowledge_items = []
    try:
        live_knowledge_items = fetch_live_knowledge_hub(tenant, limit=240).get("items") or []
        # A config fallback is useful in the knowledge UI, but it is not proof
        # that an asset reached the vector store. Capability growth counts only
        # records with a persisted vector row.
        knowledge_items = [
            item for item in live_knowledge_items
            if isinstance(item, dict) and int((item.get("vector_record") or {}).get("id") or 0) > 0
        ]
    except Exception as exc:
        if is_db_unavailable_error(exc):
            raise
        knowledge_available = False
        app.logger.warning("Capability growth knowledge load failed for tenant %s: %s", tenant_key, exc)

    now_dt = datetime.now()
    recent_cutoff = (now_dt - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    prior_cutoff = (now_dt - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")
    topic_values, object_values, method_values = [], [], []
    monthly = {}
    current_turns = 0
    prior_turns = 0
    for raw_row in turns:
        row = dict(raw_row or {})
        created_at = str(row.get("created_at") or "").strip()
        if created_at >= recent_cutoff:
            current_turns += 1
        elif created_at >= prior_cutoff:
            prior_turns += 1
        month_key = _capability_growth_month_key(created_at)
        if month_key:
            monthly.setdefault(month_key, {"month": month_key, "knowledge": 0, "reviews": 0, "research_turns": 0})["research_turns"] += 1
        metrics = _extract_hermes_turn_metrics(row)
        method_values.append(metrics.get("mode_label") or "")
        tags = _safe_json_dict(row.get("tags_json"))
        topic_values.extend(tags.get("function_tags") if isinstance(tags.get("function_tags"), list) else [])
        topic_values.extend(tags.get("style_tags") if isinstance(tags.get("style_tags"), list) else [])
        metadata = _safe_json_dict(row.get("memory_summary_json"))
        topic_values.extend(metadata.get("topics") if isinstance(metadata.get("topics"), list) else [])
        object_values.extend(metadata.get("focus_symbols") if isinstance(metadata.get("focus_symbols"), list) else [])

    validated_review_count = 0
    review_count = 0
    for review in reviews:
        if not isinstance(review, dict):
            continue
        review_count += 1
        topic_values.extend(review.get("tags") if isinstance(review.get("tags"), list) else [])
        object_values.extend(review.get("watchlist") if isinstance(review.get("watchlist"), list) else [])
        analysis = review.get("watchlist_analysis_section") if isinstance(review.get("watchlist_analysis_section"), dict) else {}
        for profile in analysis.get("sector_profiles") if isinstance(analysis.get("sector_profiles"), list) else []:
            if isinstance(profile, dict):
                topic_values.append(profile.get("sector"))
        evidence = review.get("evidence_chain_section") if isinstance(review.get("evidence_chain_section"), dict) else {}
        has_validation = bool(evidence.get("items")) or bool(analysis.get("annotation_evidence"))
        if has_validation:
            validated_review_count += 1
        method_values.append("证据链复盘" if evidence.get("items") else "复盘归纳")
        month_key = _capability_growth_month_key(review.get("published_at") or review.get("time"))
        if month_key:
            monthly.setdefault(month_key, {"month": month_key, "knowledge": 0, "reviews": 0, "research_turns": 0})["reviews"] += 1

    for item in knowledge_items:
        if not isinstance(item, dict):
            continue
        topic_values.extend(item.get("tags") if isinstance(item.get("tags"), list) else [])
        topic_values.append(item.get("knowledge_type"))
        month_key = _capability_growth_month_key((item.get("vector_record") or {}).get("created_at") or item.get("time"))
        if month_key:
            monthly.setdefault(month_key, {"month": month_key, "knowledge": 0, "reviews": 0, "research_turns": 0})["knowledge"] += 1

    active_months = [(now_dt - timedelta(days=31 * offset)).strftime("%Y-%m") for offset in range(5, -1, -1)]
    trend = [monthly.get(month, {"month": month, "knowledge": 0, "reviews": 0, "research_turns": 0}) for month in active_months]
    source_count = len(knowledge_items) + review_count + len(turns)
    coverage_count = len(_capability_growth_labels(topic_values, limit=240)) + len(_capability_growth_labels(object_values, limit=240))
    verification_ratio = round((validated_review_count / review_count) * 100, 1) if review_count else 0.0
    readiness_score = min(100, round(
        min(35, len(knowledge_items) * 3)
        + min(25, review_count * 5)
        + min(20, len(turns) * 1.2)
        + min(20, verification_ratio * 0.2)
    ))
    stage = "起步沉淀" if readiness_score < 35 else "结构化积累" if readiness_score < 65 else "可验证增长"
    return {
        "tenant_slug": tenant_key,
        "summary": {
            "readiness_score": readiness_score,
            "stage": stage,
            "source_asset_count": source_count,
            "knowledge_count": len(knowledge_items),
            "knowledge_available": knowledge_available,
            "review_count": review_count,
            "research_turn_count": len(turns),
            "coverage_count": coverage_count,
            "validated_review_count": validated_review_count,
            "verification_ratio": verification_ratio,
            "recent_turn_count": current_turns,
            "previous_turn_count": prior_turns,
            "generated_at": now_ts(),
        },
        "trend": trend,
        "topics": _capability_growth_labels(topic_values),
        "objects": _capability_growth_labels(object_values),
        "methods": _capability_growth_labels(method_values),
        "principles": [
            "只统计当前租户已入库的知识、已发布复盘和 Hermes 对话聚合。",
            "能力指数反映可追溯资产的沉淀程度，不等同于模型训练完成或投资建议质量。",
            "复盘含证据链或标注时计入验证闭环；未验证内容只计入资产，不计入闭环。",
        ],
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
    if preferred_key == "line_chart":
        return "线性图"
    if preferred_key == "kline_chart":
        return "K线图"
    if preferred_key == "distribution_chart":
        return "分布图"
    if preferred_key == "report_interpretation":
        return "报告解读"
    if preferred_key == "content_generation":
        return "内容生成"
    if preferred_key in {"small_talk", "chat"}:
        return "轻度闲聊"
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
    missing_capability = metadata.get("missing_capability") if isinstance(metadata.get("missing_capability"), dict) else {}
    missing_capability_tags = tags.get("missing_capability_tags") if isinstance(tags.get("missing_capability_tags"), list) else []
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
        "missing_capability": missing_capability,
        "missing_capability_tags": missing_capability_tags,
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

    # Conversation records are the source of truth for this page. Fetch them
    # before optional token telemetry so a legacy token table cannot abort the
    # transaction and hide otherwise valid Hermes usage statistics.
    turn_rows = db.execute(
        f"""
        SELECT user_profile_id, user_display_name, user_role, entry_point, intent, preferred_mode,
               question_text, tool_trace_json, tags_json, memory_summary_json, created_at
        FROM hermes_conversation_turns
        WHERE {month_where_sql}
        ORDER BY created_at DESC, id DESC
        """,
        tuple(params_month),
    ).fetchall()

    token_usage_available = True
    token_month = {}
    token_today = {}
    try:
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
    except Exception as exc:
        if is_db_unavailable_error(exc):
            raise
        token_usage_available = False
        app.logger.warning(
            "Hermes token telemetry is unavailable for tenant %s; using conversation records only: %s",
            tenant or "all",
            exc,
        )

    mode_today = {}
    mode_month = {}
    user_rank = {}
    missing_capability_rank = {}
    total_compute_units = 0
    total_latency = 0
    total_calls = 0
    missing_capability_turns = 0
    for row in turn_rows:
        metrics = _extract_hermes_turn_metrics(row)
        row_data = dict(row) if isinstance(row, dict) else {}
        mode_label = metrics["mode_label"]
        bucket = mode_month.setdefault(mode_label, {"mode_label": mode_label, "today_calls": 0, "month_calls": 0, "compute_units": 0, "latency_ms_total": 0})
        bucket["month_calls"] += 1
        bucket["compute_units"] += metrics["compute_units"]
        bucket["latency_ms_total"] += metrics["latency_ms"]
        total_compute_units += metrics["compute_units"]
        total_latency += metrics["latency_ms"]
        total_calls += 1

        created_at = str(row_data.get("created_at") or "")
        if created_at >= today_start:
          bucket["today_calls"] += 1

        user_id = str(row_data.get("user_profile_id") or "").strip() or "guest"
        user_bucket = user_rank.setdefault(user_id, {
            "user_profile_id": user_id,
            "user_name": str(row_data.get("user_display_name") or user_id).strip() or user_id,
            "user_role": str(row_data.get("user_role") or "").strip(),
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

        missing_capability = metrics.get("missing_capability") if isinstance(metrics.get("missing_capability"), dict) else {}
        missing_label = str(missing_capability.get("label") or "").strip()
        if missing_label:
            missing_capability_turns += 1
            capability_code = str(missing_capability.get("code") or missing_label).strip() or missing_label
            capability_bucket = missing_capability_rank.setdefault(capability_code, {
                "code": capability_code,
                "label": missing_label,
                "category": str(missing_capability.get("category") or "能力缺口").strip() or "能力缺口",
                "intent": str(missing_capability.get("intent") or "").strip(),
                "mentions": 0,
                "users": set(),
                "latest_question": "",
                "latest_created_at": "",
                "target_date": str(missing_capability.get("target_date") or "").strip(),
                "object_name": str(missing_capability.get("object_name") or "").strip(),
            })
            capability_bucket["mentions"] += 1
            capability_bucket["users"].add(user_id)
            if created_at >= str(capability_bucket.get("latest_created_at") or ""):
                capability_bucket["latest_created_at"] = created_at
                capability_bucket["latest_question"] = str(row_data.get("question_text") or "").strip()
                capability_bucket["target_date"] = str(missing_capability.get("target_date") or capability_bucket.get("target_date") or "").strip()
                capability_bucket["object_name"] = str(missing_capability.get("object_name") or capability_bucket.get("object_name") or "").strip()

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

    missing_rows = []
    sorted_missing = sorted(
        missing_capability_rank.values(),
        key=lambda row: (-int(row.get("mentions") or 0), -len(row.get("users") or []), row.get("label") or ""),
    )
    for item in sorted_missing[:12]:
        missing_rows.append({
            "code": item.get("code") or "",
            "label": item.get("label") or "",
            "category": item.get("category") or "能力缺口",
            "intent": item.get("intent") or "",
            "mentions": int(item.get("mentions") or 0),
            "user_count": len(item.get("users") or []),
            "latest_question": _hermes_trim_text(item.get("latest_question") or "", limit=88),
            "latest_created_at": str(item.get("latest_created_at") or "").strip(),
            "target_date": str(item.get("target_date") or "").strip(),
            "object_name": str(item.get("object_name") or "").strip(),
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
            "token_usage_available": token_usage_available,
            "avg_latency_ms": round(total_latency / total_calls, 2) if total_calls else 0,
            "missing_capability_turns": int(missing_capability_turns or 0),
            "missing_capability_count": len(missing_rows),
            "generated_at": now_ts(),
        },
        "tool_modes": mode_rows[:8],
        "tool_actions": tool_rows[:12],
        "user_ranking": rank_rows,
        "missing_capabilities": missing_rows,
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


def build_user_hermes_usage_snapshot(tenant_slug="", user_profile_id="", quota_total=0):
    tenant = str(tenant_slug or "").strip().lower()
    user_id = str(user_profile_id or "").strip()
    if not user_id:
        raise ValueError("user_profile_id_required")
    db = get_db()
    now_dt = datetime.now()
    today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    month_start = now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    where_sql = "user_profile_id = ?"
    params = [user_id]
    if tenant:
        where_sql += " AND tenant_slug = ?"
        params.append(tenant)
    rows = db.execute(
        f"""
        SELECT user_profile_id, user_display_name, tenant_slug, tool_trace_json, memory_summary_json, created_at
        FROM hermes_conversation_turns
        WHERE {where_sql}
        ORDER BY created_at DESC, id DESC
        """,
        tuple(params),
    ).fetchall()
    total_call_count = 0
    today_call_count = 0
    month_call_count = 0
    total_compute_units = 0
    month_compute_units = 0
    latest_turn_at = ""
    display_name = ""
    resolved_tenant = tenant
    for row in rows:
        row_dict = dict(row or {})
        total_call_count += 1
        latest_turn_at = latest_turn_at or str(row_dict.get("created_at") or "").strip()
        display_name = display_name or str(row_dict.get("user_display_name") or "").strip()
        resolved_tenant = resolved_tenant or str(row_dict.get("tenant_slug") or "").strip().lower()
        metrics = _extract_hermes_turn_metrics(row_dict)
        created_at = str(row_dict.get("created_at") or "").strip()
        if created_at >= today_start:
            today_call_count += 1
        if created_at >= month_start:
            month_call_count += 1
            month_compute_units += int(metrics.get("compute_units") or 0)
        total_compute_units += int(metrics.get("compute_units") or 0)
    quota_total = max(0, int(quota_total or 0))
    remaining_count = max(0, quota_total - total_compute_units) if quota_total else 0
    return {
        "tenant_slug": resolved_tenant,
        "user_profile_id": user_id,
        "user_display_name": display_name or user_id,
        "quota_total": quota_total,
        "used_count": total_compute_units,
        "remaining_count": remaining_count,
        "total_call_count": total_call_count,
        "today_call_count": today_call_count,
        "month_call_count": month_call_count,
        "month_compute_units": month_compute_units,
        "latest_turn_at": latest_turn_at,
        "generated_at": now_ts(),
    }


HERMES_SESSION_INTENT_LABELS = {
    "small_talk": "轻度闲聊",
    "product_help": "产品帮助",
    "watchlist_fundamental": "个股研究",
    "knowledge_lookup": "知识问答",
    "evidence_chain_analysis": "证据链分析",
    "smart_indicator_explain": "指标解读",
    "dashboard_interpretation": "Dashboard解读",
    "multi_tool_research": "综合研究",
    "out_of_scope_redirect": "范围收口",
}


def get_hermes_intent_label(intent):
    key = str(intent or "").strip()
    return HERMES_SESSION_INTENT_LABELS.get(key) or key or "Hermes 对话"


def build_hermes_session_list(actor_context, limit=24, keyword=""):
    actor = actor_context if isinstance(actor_context, dict) else {}
    tenant_slug = str(actor.get("tenant_slug") or "").strip().lower()
    user_profile_id = str(actor.get("profile_id") or "").strip()
    if not tenant_slug or not user_profile_id:
        return []
    db = get_db()
    safe_limit = max(1, min(int(limit or 24), 80))
    rows = db.execute(
        """
        SELECT
            sm.session_id,
            sm.user_display_name,
            sm.turn_count,
            sm.summary_text,
            sm.last_intent,
            sm.first_seen_at,
            sm.last_seen_at,
            COALESCE((
                SELECT question_text
                FROM hermes_conversation_turns t1
                WHERE t1.tenant_slug = sm.tenant_slug AND t1.user_profile_id = sm.user_profile_id AND t1.session_id = sm.session_id
                ORDER BY t1.created_at ASC, t1.id ASC
                LIMIT 1
            ), '') AS first_question,
            COALESCE((
                SELECT question_text
                FROM hermes_conversation_turns t2
                WHERE t2.tenant_slug = sm.tenant_slug AND t2.user_profile_id = sm.user_profile_id AND t2.session_id = sm.session_id
                ORDER BY t2.created_at DESC, t2.id DESC
                LIMIT 1
            ), '') AS last_question,
            COALESCE((
                SELECT answer_summary
                FROM hermes_conversation_turns t3
                WHERE t3.tenant_slug = sm.tenant_slug AND t3.user_profile_id = sm.user_profile_id AND t3.session_id = sm.session_id
                ORDER BY t3.created_at DESC, t3.id DESC
                LIMIT 1
            ), '') AS last_answer_summary,
            COALESCE((
                SELECT answer_text
                FROM hermes_conversation_turns t4
                WHERE t4.tenant_slug = sm.tenant_slug AND t4.user_profile_id = sm.user_profile_id AND t4.session_id = sm.session_id
                ORDER BY t4.created_at DESC, t4.id DESC
                LIMIT 1
            ), '') AS last_answer_text
        FROM hermes_session_memory sm
        WHERE sm.tenant_slug = ? AND sm.user_profile_id = ?
        ORDER BY sm.last_seen_at DESC, sm.session_id DESC
        LIMIT ?
        """,
        (tenant_slug, user_profile_id, safe_limit),
    ).fetchall()
    normalized_keyword = str(keyword or "").strip().lower()
    sessions = []
    for row in rows:
        item = dict(row or {})
        title = trim_hermes_text(item.get("first_question") or item.get("summary_text") or item.get("last_question") or "新会话", limit=36)
        preview = trim_hermes_text(
            item.get("last_answer_summary") or item.get("summary_text") or item.get("last_answer_text") or item.get("last_question") or "",
            limit=72,
        )
        last_question = trim_hermes_text(item.get("last_question") or item.get("first_question") or "", limit=72)
        corpus = " ".join([
            str(title or ""),
            str(preview or ""),
            str(last_question or ""),
        ]).lower()
        if normalized_keyword and normalized_keyword not in corpus:
            continue
        sessions.append({
            "session_id": str(item.get("session_id") or "").strip(),
            "title": title or "新会话",
            "preview": preview,
            "last_question": last_question,
            "turn_count": int(item.get("turn_count") or 0),
            "last_intent": str(item.get("last_intent") or "").strip(),
            "last_intent_label": get_hermes_intent_label(item.get("last_intent")),
            "first_seen_at": str(item.get("first_seen_at") or "").strip(),
            "last_seen_at": str(item.get("last_seen_at") or "").strip(),
            "user_display_name": str(item.get("user_display_name") or actor.get("display_name") or user_profile_id).strip() or user_profile_id,
        })
    return sessions


def build_hermes_session_detail(actor_context, session_id):
    actor = actor_context if isinstance(actor_context, dict) else {}
    tenant_slug = str(actor.get("tenant_slug") or "").strip().lower()
    user_profile_id = str(actor.get("profile_id") or "").strip()
    normalized_session_id = slugify_code(session_id, "")
    if not tenant_slug or not user_profile_id or not normalized_session_id:
        raise ValueError("hermes_session_id_required")
    db = get_db()
    session_row = db.execute(
        """
        SELECT session_id, tenant_slug, user_profile_id, user_role, user_display_name, turn_count,
               summary_text, last_intent, first_seen_at, last_seen_at
        FROM hermes_session_memory
        WHERE tenant_slug = ? AND user_profile_id = ? AND session_id = ?
        """,
        (tenant_slug, user_profile_id, normalized_session_id),
    ).fetchone()
    turn_rows = db.execute(
        """
        SELECT turn_id, question_text, answer_text, answer_summary, intent, scope_status,
               display_mode, preferred_mode, tags_json, memory_summary_json, citations_json, created_at
        FROM hermes_conversation_turns
        WHERE tenant_slug = ? AND user_profile_id = ? AND session_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (tenant_slug, user_profile_id, normalized_session_id),
    ).fetchall()
    turns = []
    for row in turn_rows:
        item = dict(row or {})
        turns.append({
            "turn_id": str(item.get("turn_id") or "").strip(),
            "question_text": str(item.get("question_text") or "").strip(),
            "answer_text": str(item.get("answer_text") or "").strip(),
            "answer_summary": str(item.get("answer_summary") or "").strip(),
            "intent": str(item.get("intent") or "").strip(),
            "intent_label": get_hermes_intent_label(item.get("intent")),
            "scope_status": str(item.get("scope_status") or "").strip(),
            "display_mode": str(item.get("display_mode") or "").strip() or "text",
            "preferred_mode": str(item.get("preferred_mode") or "").strip(),
            "tags": _extract_json_text_field(item, "tags_json", {}),
            "memory_summary": _extract_json_text_field(item, "memory_summary_json", {}),
            "citations": _extract_json_text_field(item, "citations_json", []),
            "created_at": str(item.get("created_at") or "").strip(),
        })
    if not session_row and not turns:
        raise ValueError("hermes_session_not_found")
    session_item = dict(session_row or {})
    title = trim_hermes_text(
        (turns[0].get("question_text") if turns else "")
        or session_item.get("summary_text")
        or (turns[-1].get("question_text") if turns else "")
        or "新会话",
        limit=36,
    )
    preview = trim_hermes_text(
        (turns[-1].get("answer_summary") if turns else "")
        or session_item.get("summary_text")
        or (turns[-1].get("answer_text") if turns else "")
        or "",
        limit=72,
    )
    return {
        "session": {
            "session_id": normalized_session_id,
            "title": title or "新会话",
            "preview": preview,
            "turn_count": int(session_item.get("turn_count") or len(turns)),
            "last_intent": str(session_item.get("last_intent") or (turns[-1].get("intent") if turns else "") or "").strip(),
            "last_intent_label": get_hermes_intent_label(session_item.get("last_intent") or (turns[-1].get("intent") if turns else "")),
            "first_seen_at": str(session_item.get("first_seen_at") or (turns[0].get("created_at") if turns else "") or "").strip(),
            "last_seen_at": str(session_item.get("last_seen_at") or (turns[-1].get("created_at") if turns else "") or "").strip(),
            "user_display_name": str(session_item.get("user_display_name") or actor.get("display_name") or user_profile_id).strip() or user_profile_id,
        },
        "turns": turns,
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


def build_hermes_intent_router_prompt(question_text, has_attachments=False, selected_knowledge_ids=None, messages=None, memory_context_text="", scope_result=None):
    conversation_block = format_hermes_message_context(messages, limit=6)
    conversation_section = f"最近多轮对话：\n{conversation_block}\n\n" if conversation_block else ""
    memory_section = f"历史记忆摘要：\n{str(memory_context_text or '').strip()}\n\n" if str(memory_context_text or "").strip() else ""
    scope = scope_result if isinstance(scope_result, dict) else {}
    scope_section = ""
    if str(scope.get("status") or "").strip() in {"blocked", "redirected"}:
        scope_section = (
            f"规则守卫提示（仅作为安全边界参考，最终意图仍由你判断）："
            f"{str(scope.get('reason') or '').strip()}\n\n"
        )
    return (
        "请根据用户问题判断 Hermes 应该如何拆解任务。\n"
        "可选 intent：small_talk, product_help, knowledge_lookup, evidence_chain_analysis, watchlist_fundamental, smart_indicator_explain, dashboard_interpretation, multi_tool_research, out_of_scope_redirect\n"
        "可选 tools：watchlist.detail, indicator.detail, dashboard.context, attachment.context\n"
        "规则：\n"
        "1. 如果用户明确问复盘、证据链、依据、来源，使用 evidence_chain_analysis；不要调用知识检索工具。\n"
        "2. 如果用户明确问基本面、估值、盈利、行业位置、个股研究，且存在股票名/代码，使用 watchlist_fundamental 并调用 watchlist.detail。\n"
        "3. 如果用户主要想问知识、框架、方法、纪要内容，使用 knowledge_lookup；这类问题直接交给答案模型，不调用 embedding 或知识检索工具。\n"
        "4. 如果用户在问智能指标怎么计算、提示词/公式怎么理解，使用 smart_indicator_explain，并按需调用 indicator.detail、dashboard.context。\n"
        "5. 如果用户在问 Dashboard 面板、看板卡片、布局或发布后的展示逻辑，使用 dashboard_interpretation，并调用 dashboard.context。\n"
        "6. 如果用户在问 H5 / Web / Admin / 工作台里的功能、页面或操作，使用 product_help，不调用任何知识检索工具。\n"
        "7. 如果问题同时涉及个股和证据，多工具组合时使用 multi_tool_research，但只调用实时个股、指标、Dashboard 或附件工具。\n"
        "8. 如果只是寒暄或轻度闲聊，使用 small_talk，tools 必须为空数组。\n"
        "9. 如果问题明显超范围但仍可温和收口，使用 out_of_scope_redirect，tools 必须为空数组。\n"
        "10. 如果有附件，工具里可以包含 attachment.context。\n"
        "11. stock_code 只在能明显识别时输出，否则为空字符串。\n"
        "12. display_mode 只能是 text 或 structured。\n"
        "13. 如果用户问‘你是谁’或‘你的功能有哪些’，优先使用 product_help 或 small_talk，直接说明小金智能体当前能力。\n"
        "14. 禁止返回 knowledge.search、evidence.search 或任何未列出的工具。\n\n"
        f"{memory_section}"
        f"{conversation_section}"
        f"{scope_section}"
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


def default_hermes_intent_plan(question_text, selected_knowledge_ids=None, attachments=None, preferred_mode="", tenant_slug="", scope_guard_enabled=True):
    question = str(question_text or "").strip()
    lowered = question.lower()
    attachments = attachments if isinstance(attachments, list) else []
    selected_knowledge_ids = selected_knowledge_ids if isinstance(selected_knowledge_ids, list) else []
    preferred_mode = str(preferred_mode or "").strip().lower()
    has_attachments = bool(attachments)
    stock_code = find_watchlist_code_from_text(question)
    indicator_match = find_indicator_reference_from_text(question, tenant_slug=tenant_slug)
    indicator_code = str((indicator_match or {}).get("indicator_code") or "").strip()
    scope_flags = _hermes_scope_feature_flags(question, selected_knowledge_ids=selected_knowledge_ids, attachments=attachments, tenant_slug=tenant_slug)
    stock_keywords = HERMES_SCOPE_KEYWORDS["watchlist"]
    evidence_keywords = HERMES_SCOPE_KEYWORDS["evidence"]
    knowledge_keywords = HERMES_SCOPE_KEYWORDS["knowledge"]
    indicator_keywords = HERMES_SCOPE_KEYWORDS["indicator"]
    dashboard_keywords = HERMES_SCOPE_KEYWORDS["dashboard"]
    product_keywords = HERMES_SCOPE_KEYWORDS["product"]
    product_action_keywords = HERMES_PRODUCT_ACTION_KEYWORDS
    inferred_visual_mode = infer_hermes_visual_mode(question, preferred_mode=preferred_mode)
    if inferred_visual_mode:
        preferred_mode = inferred_visual_mode
    if preferred_mode in {"small_talk", "chat"}:
        return finalize_hermes_intent_plan({
            "intent": "small_talk",
            "tools": ["attachment.context"] if has_attachments else [],
            "stock_code": stock_code,
            "display_mode": "text",
            "preferred_mode": preferred_mode,
            "reason": "分析方式偏向轻度闲聊承接",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if preferred_mode == "report_interpretation":
        report_tools = ["attachment.context"]
        return finalize_hermes_intent_plan({
            "intent": "knowledge_lookup",
            "tools": report_tools,
            "stock_code": stock_code,
            "display_mode": "text",
            "preferred_mode": preferred_mode,
            "reason": "分析方式偏向上传材料或报告解读",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if preferred_mode == "content_generation":
        generation_tools = (["attachment.context"] if has_attachments else [])
        if stock_code:
            generation_tools.append("watchlist.detail")
        return finalize_hermes_intent_plan({
            "intent": "multi_tool_research" if generation_tools else "knowledge_lookup",
            "tools": generation_tools,
            "stock_code": stock_code,
            "display_mode": "text",
            "preferred_mode": preferred_mode,
            "reason": "分析方式偏向内容生成与结构化整理",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if preferred_mode == "evidence":
        return finalize_hermes_intent_plan({
            "intent": "evidence_chain_analysis" if not stock_code else "multi_tool_research",
            "tools": (["watchlist.detail"] if stock_code else []) + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "display_mode": "structured" if stock_code else "text",
            "reason": "分析方式偏向证据链归因",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if preferred_mode in {"line_chart", "kline_chart", "distribution_chart"}:
        return finalize_hermes_intent_plan({
            "intent": "smart_indicator_explain",
            "tools": ["indicator.detail", "dashboard.context"] + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "indicator_code": indicator_code,
            "display_mode": "structured" if indicator_code else "text",
            "preferred_mode": preferred_mode,
            "reason": f"分析方式偏向{ {'line_chart': '线性图', 'kline_chart': 'K线图', 'distribution_chart': '分布图'}.get(preferred_mode, '图表可视化') }",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if preferred_mode == "judgement" and stock_code:
        return finalize_hermes_intent_plan({
            "intent": "watchlist_fundamental",
            "tools": ["watchlist.detail"] + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "display_mode": "structured",
            "reason": "分析方式偏向基本面判断",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if any(keyword in lowered for keyword in [item.lower() for item in product_keywords]) and any(
        keyword in lowered for keyword in [item.lower() for item in product_action_keywords]
    ):
        product_tools = []
        if scope_flags["dashboard"] or scope_flags["indicator"]:
            product_tools.append("dashboard.context")
        if has_attachments:
            product_tools.append("attachment.context")
        return finalize_hermes_intent_plan({
            "intent": "product_help",
            "tools": product_tools,
            "stock_code": stock_code,
            "display_mode": "text",
            "reason": "命中平台功能操作问题",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if any(keyword in lowered for keyword in [item.lower() for item in indicator_keywords]):
        return finalize_hermes_intent_plan({
            "intent": "smart_indicator_explain",
            "tools": ["indicator.detail", "dashboard.context"] + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "indicator_code": indicator_code,
            "display_mode": "structured" if indicator_code else "text",
            "reason": f"命中指标或股指问题：{(indicator_match or {}).get('indicator_name') or '智能指标 / 公式说明'}",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if indicator_code:
        return finalize_hermes_intent_plan({
            "intent": "smart_indicator_explain",
            "tools": ["indicator.detail", "dashboard.context"] + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "indicator_code": indicator_code,
            "display_mode": "structured",
            "reason": f"命中指标或股指问题：{(indicator_match or {}).get('indicator_name') or indicator_code}",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if any(keyword in lowered for keyword in [item.lower() for item in dashboard_keywords]):
        return finalize_hermes_intent_plan({
            "intent": "dashboard_interpretation",
            "tools": ["dashboard.context"] + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "display_mode": "text",
            "reason": "命中 Dashboard 面板理解问题",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if any(keyword in lowered for keyword in [item.lower() for item in product_keywords]):
        product_tools = []
        if scope_flags["dashboard"] or scope_flags["indicator"]:
            product_tools.append("dashboard.context")
        if has_attachments:
            product_tools.append("attachment.context")
        return finalize_hermes_intent_plan({
            "intent": "product_help",
            "tools": product_tools,
            "stock_code": stock_code,
            "display_mode": "text",
            "reason": "命中平台功能使用问题",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if any(keyword in lowered for keyword in [item.lower() for item in evidence_keywords]):
        return finalize_hermes_intent_plan({
            "intent": "evidence_chain_analysis" if not stock_code else "multi_tool_research",
            "tools": (["watchlist.detail"] if stock_code else []) + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "display_mode": "structured" if stock_code else "text",
            "reason": "命中复盘或证据链问题",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if stock_code or any(keyword in lowered for keyword in [item.lower() for item in stock_keywords]):
        return finalize_hermes_intent_plan({
            "intent": "watchlist_fundamental" if not selected_knowledge_ids and not has_attachments else "multi_tool_research",
            "tools": ["watchlist.detail"] + (["attachment.context"] if has_attachments else []),
            "stock_code": stock_code,
            "display_mode": "structured" if stock_code else "text",
            "reason": "命中个股基本面问题",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if selected_knowledge_ids or any(keyword in lowered for keyword in [item.lower() for item in knowledge_keywords]):
        return finalize_hermes_intent_plan({
            "intent": "knowledge_lookup",
            "tools": ["attachment.context"] if has_attachments else [],
            "stock_code": stock_code,
            "display_mode": "text",
            "reason": "命中知识或方法问题",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if scope_flags["small_talk"]:
        return finalize_hermes_intent_plan({
            "intent": "small_talk",
            "tools": ["attachment.context"] if has_attachments else [],
            "stock_code": stock_code,
            "display_mode": "text",
            "reason": "轻度闲聊或寒暄",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    if not scope_guard_enabled:
        return finalize_hermes_intent_plan({
            "intent": "small_talk",
            "tools": ["attachment.context"] if has_attachments else [],
            "stock_code": stock_code,
            "display_mode": "text",
            "preferred_mode": preferred_mode or "chat",
            "reason": "当前未启用固定范围约束，按开放问答继续承接。",
        }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    return finalize_hermes_intent_plan({
        "intent": "out_of_scope_redirect",
        "tools": [],
        "stock_code": stock_code,
        "display_mode": "text",
        "reason": "当前问题超出 Hermes 的主要服务范围，建议收口到平台相关问题。",
    }, question_text=question, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)


def build_hermes_scope_plan(scope_result, question_text, selected_knowledge_ids=None, attachments=None, preferred_mode="", scope_guard_enabled=True):
    scope = scope_result if isinstance(scope_result, dict) else {}
    if str(scope.get("status") or "").strip() in {"redirected", "blocked"}:
        return finalize_hermes_intent_plan({
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
        }, question_text=question_text, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids)
    plan = default_hermes_intent_plan(
        question_text=question_text,
        selected_knowledge_ids=selected_knowledge_ids,
        attachments=attachments,
        preferred_mode=preferred_mode,
        tenant_slug="",
        scope_guard_enabled=scope_guard_enabled,
    )
    if scope.get("status") == "soft_allowed":
        plan["intent"] = "small_talk"
        plan["reason"] = str(scope.get("reason") or plan.get("reason") or "").strip() or plan.get("reason") or ""
    plan["scope_status"] = str(scope.get("status") or "allowed").strip() or "allowed"
    return finalize_hermes_intent_plan(
        plan,
        question_text=question_text,
        attachments=attachments,
        selected_knowledge_ids=selected_knowledge_ids,
    )


def build_hermes_scope_synthesis(plan):
    intent_plan = plan if isinstance(plan, dict) else {}
    message = str(intent_plan.get("guard_message") or "").strip()
    suggestions = [
        str(item).strip()
        for item in (intent_plan.get("guard_suggestions") if isinstance(intent_plan.get("guard_suggestions"), list) else [])
        if str(item).strip()
    ][:4]
    answer = ensure_hermes_positive_opening(
        message or "Hermes 这轮先不直接展开，因为当前问题没有落在平台的核心服务范围内。",
        question_text=str(intent_plan.get("question_text") or "").strip(),
        intent=str(intent_plan.get("intent") or "").strip(),
        scope_status=str(intent_plan.get("scope_status") or "redirected").strip(),
    )
    return {
        "answer": answer,
        "summary": str(intent_plan.get("reason") or "问题已被范围守卫收口。").strip(),
        "bullets": suggestions,
        "citations": [],
    }


def route_hermes_query_intent(question_text, tenant_slug="", selected_knowledge_ids=None, attachments=None, preferred_mode="", messages=None, scope_result=None, memory_state=None, scope_guard_enabled=True):
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
            scope_guard_enabled=scope_guard_enabled,
        ), None, "scope_guard"
    llm_model = get_default_llm_config(purpose="general", feature_code="hermes_intent_router")
    if not llm_model:
        raise RuntimeError("hermes_intent_router_llm_not_configured")
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
                scope_result=scope_result,
            ),
            feature_code="hermes_intent_router",
            feature_label="Hermes 意图路由",
            tenant_slug=tenant_slug,
            entry_point="hermes_query",
            metadata={"attachment_count": len(attachments), "selected_knowledge_count": len(selected_knowledge_ids)},
            request_timeout_seconds=20,
        )
        parsed = _extract_json_payload_from_llm_text(raw, {}, strict=True)
        intent = str(parsed.get("intent") or "").strip()
        if intent not in HERMES_ALLOWED_INTENTS:
            raise RuntimeError("hermes_intent_router_invalid_intent")
        raw_tools = parsed.get("tools") if isinstance(parsed.get("tools"), list) else []
        tools = []
        for tool in raw_tools:
            value = str(tool or "").strip()
            if value in HERMES_ALLOWED_TOOLS and value not in tools:
                tools.append(value)
        if "tools" not in parsed or not isinstance(parsed.get("tools"), list):
            raise RuntimeError("hermes_intent_router_invalid_tools")
        stock_code = find_watchlist_code_from_text(str(parsed.get("stock_code") or "").strip())
        display_mode = str(parsed.get("display_mode") or "text").strip()
        if display_mode not in {"text", "structured"}:
            raise RuntimeError("hermes_intent_router_invalid_display_mode")
        normalized_scope_status = str((scope_result or {}).get("status") or "allowed").strip() or "allowed"
        if normalized_scope_status == "blocked":
            intent = "out_of_scope_redirect"
            tools = []
        return finalize_hermes_intent_plan({
            "intent": intent,
            "tools": tools[:4],
            "stock_code": stock_code,
            "indicator_code": str(parsed.get("indicator_code") or "").strip(),
            "display_mode": display_mode,
            "reason": str(parsed.get("reason") or "").strip()[:200] or "LLM 路由",
            "preferred_mode": str(parsed.get("preferred_mode") or preferred_mode or "").strip().lower(),
            "scope_status": normalized_scope_status,
            "guard_message": str((scope_result or {}).get("message") or "").strip() if normalized_scope_status == "blocked" else "",
            "guard_suggestions": copy.deepcopy((scope_result or {}).get("suggestions") or []) if normalized_scope_status == "blocked" else [],
        }, question_text=question_text, attachments=attachments, selected_knowledge_ids=selected_knowledge_ids), llm_model, "llm_router"
    except RuntimeError:
        raise
    except Exception as exc:
        app.logger.exception("Failed to route Hermes query intent")
        raise RuntimeError(f"hermes_intent_router_llm_failed:{str(exc)[:240]}") from exc


def trim_hermes_text(value, limit=180):
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) <= limit:
        return text
    return f"{text[:max(0, limit - 1)]}…"


def get_watchlist_annotation_content(annotation):
    """Return the canonical single-field annotation text with legacy support."""
    item = annotation if isinstance(annotation, dict) else {}
    content = str(item.get("content") or "").strip()
    if content:
        return content
    return "；".join(
        part for part in [
            str(item.get("title") or "").strip(),
            str(item.get("note") or "").strip(),
            str(item.get("trigger") or "").strip(),
        ]
        if part
    )


def resolve_hermes_watchlist_annotation_context(tenant_slug="", question_text="", limit=3):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    empty_result = {"available": False, "items": [], "summary": "", "annotation_count": 0, "stock_count": 0}
    if not normalized_tenant:
        return empty_result
    details_map = gen_watchlist_details()
    selected_watchlist = []
    direct_code = find_watchlist_code_from_text(question_text)
    if direct_code:
        selected_watchlist.append(direct_code)
    try:
        tenant = get_tenant_by_slug(normalized_tenant)
    except Exception:
        tenant = None
    try:
        snapshots = resolve_tenant_review_snapshots(tenant) if tenant else []
    except Exception:
        snapshots = []
    candidate_limit = max(limit * 2, 4)
    for snapshot in snapshots[:2]:
        if not isinstance(snapshot, dict):
            continue
        watchlist = snapshot.get("watchlist") if isinstance(snapshot.get("watchlist"), list) else []
        for item in watchlist:
            normalized_item = str(item or "").strip()
            if normalized_item and normalized_item not in selected_watchlist:
                selected_watchlist.append(normalized_item)
            if len(selected_watchlist) >= candidate_limit:
                break
        if len(selected_watchlist) >= candidate_limit:
            break
    if not selected_watchlist:
        return empty_result
    try:
        matched = build_watchlist_annotation_context(
            tenant_slug=normalized_tenant,
            selected_watchlist=selected_watchlist,
            details_map=details_map,
        )
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        matched = []
    items = []
    annotation_count = 0
    for item in matched[:limit]:
        if not isinstance(item, dict):
            continue
        annotation_titles = [
            str(title).strip()
            for title in (item.get("annotation_titles") if isinstance(item.get("annotation_titles"), list) else [])
            if str(title).strip()
        ][:4]
        annotation_summary = trim_hermes_text(item.get("annotation_summary") or "", limit=120)
        annotation_contents = [
            str(content).strip()
            for content in (item.get("annotation_contents") if isinstance(item.get("annotation_contents"), list) else [])
            if str(content).strip()
        ][:4]
        annotations = item.get("annotations") if isinstance(item.get("annotations"), list) else []
        annotation_count += len(annotations)
        if not annotation_summary and not annotation_titles and not annotation_contents:
            continue
        items.append({
            "name": str(item.get("name") or item.get("code") or "自选股").strip(),
            "code": str(item.get("code") or "").strip(),
            "industry": str(item.get("industry") or "").strip(),
            "annotation_summary": annotation_summary,
            "annotation_titles": annotation_titles,
            "annotation_contents": annotation_contents,
        })
    summary = "；".join(
        f"{entry['name']}：{entry['annotation_summary'] or '已存在K线标注'}"
        for entry in items
        if entry.get("name")
    ).strip()
    return {
        "available": bool(items),
        "items": items,
        "summary": trim_hermes_text(summary, limit=320),
        "annotation_count": annotation_count,
        "stock_count": len(items),
    }


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
    extra_aliases = {
        "中国银行": "601988",
        "日久光新": "003015",
        "日久光电": "003015",
    }
    for alias, code in extra_aliases.items():
        if alias in normalized:
            return code
    try:
        candidates = search_watchlist_candidates(normalized, top=3, include_remote=True)
    except Exception:
        candidates = []
    if candidates:
        return str((candidates[0] or {}).get("code") or "").strip()
    return ""


def find_indicator_reference_from_text(text, tenant_slug=""):
    normalized = str(text or "").strip()
    if not normalized:
        return None
    lowered = normalized.lower()
    alias_map = {
        "上证指数": ["上证指数", "上证综指", "上证综合指数", "沪指", "sh000001"],
        "沪深300": ["沪深300", "hs300"],
        "上证50": ["上证50", "上证50指数", "sse50"],
        "科创50": ["科创50", "科创50指数"],
        "创业板指": ["创业板", "创业板指"],
        "恒生指数": ["恒生指数", "恒指", "hsi"],
        "纳斯达克": ["纳斯达克", "纳斯达克指数", "纳指", "nasdaq"],
        "标普500": ["标普500", "标普", "sp500", "s&p500"],
        "道琼斯": ["道琼斯", "道指", "dji"],
        "CPI": ["cpi", "居民消费价格指数"],
    }
    hub = build_indicator_hub(tenant=get_tenant_by_slug(tenant_slug) if tenant_slug else get_tenant_by_slug(), admin_view=False)
    items = []
    for item in (hub.get("items") or []):
        if isinstance(item, dict):
            items.append(item)
    for item in sorted(items, key=lambda current: len(str(current.get("name") or "")), reverse=True):
        code = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        aliases = [code, name]
        aliases.extend(alias_map.get(name, []))
        for alias in aliases:
            candidate = str(alias or "").strip()
            if candidate and candidate.lower() in lowered:
                return {
                    "indicator_code": code,
                    "indicator_name": name or code,
                }
    for indicator_code, registry_entry in GANGTISE_INDICATOR_REGISTRY.items():
        name = str(registry_entry.get("indicator_name") or indicator_code).strip()
        aliases = [indicator_code, name]
        aliases.extend(alias_map.get(name, []))
        for alias in aliases:
            candidate = str(alias or "").strip()
            if candidate and candidate.lower() in lowered:
                return {
                    "indicator_code": indicator_code,
                    "indicator_name": name or indicator_code,
                }
    return None


def extract_hermes_explicit_date(question_text):
    text = str(question_text or "").strip()
    if not text:
        return ""
    match = re.search(r"\b(20\d{2})[-/年\.](\d{1,2})[-/月\.](\d{1,2})日?\b", text)
    if match:
        year, month, day = [int(item) for item in match.groups()]
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    match = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})日", text)
    if match:
        month, day = [int(item) for item in match.groups()]
        year = datetime.now().year
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return ""


def _normalize_hermes_date_text(value):
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    return match.group(1) if match else text[:10]


def build_hermes_indicator_fetch_window(question_text):
    target_date = extract_hermes_explicit_date(question_text)
    if not target_date:
        return "", ""
    try:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        return "", ""
    start_dt = target_dt - timedelta(days=180)
    return start_dt.strftime("%Y-%m-%d"), target_date


def resolve_hermes_indicator_target_snapshot(detail, question_text=""):
    detail = detail if isinstance(detail, dict) else {}
    target_date = extract_hermes_explicit_date(question_text)
    if not target_date:
        return None
    candles = ((detail.get("history_kline") or {}).get("candles") or []) if isinstance(detail.get("history_kline"), dict) else []
    normalized_candles = [item for item in candles if isinstance(item, dict) and _normalize_hermes_date_text(item.get("date"))]
    normalized_candles.sort(key=lambda item: _normalize_hermes_date_text(item.get("date")))
    exact_index = next((idx for idx, item in enumerate(normalized_candles) if _normalize_hermes_date_text(item.get("date")) == target_date), -1)
    matched_index = exact_index
    matched_exact = True
    if matched_index < 0 and normalized_candles:
        eligible_indexes = [
            idx for idx, item in enumerate(normalized_candles)
            if _normalize_hermes_date_text(item.get("date")) <= target_date
        ]
        if eligible_indexes:
            matched_index = eligible_indexes[-1]
            matched_exact = _normalize_hermes_date_text(normalized_candles[matched_index].get("date")) == target_date
    if matched_index >= 0:
        candle = dict(normalized_candles[matched_index])
        previous_candle = dict(normalized_candles[matched_index - 1]) if matched_index > 0 else {}
        close_value = NumberLike(candle.get("close"))
        prev_close = NumberLike(previous_candle.get("close")) if previous_candle else close_value
        change_value = round(close_value - prev_close, 4)
        change_pct = round((change_value / prev_close) * 100, 2) if prev_close else 0.0
        return {
            "target_date": target_date,
            "matched_date": _normalize_hermes_date_text(candle.get("date")),
            "matched_exact": matched_exact,
            "open": round(NumberLike(candle.get("open")), 4),
            "high": round(NumberLike(candle.get("high")), 4),
            "low": round(NumberLike(candle.get("low")), 4),
            "close": round(close_value, 4),
            "prev_close": round(prev_close, 4),
            "change": change_value,
            "change_pct": change_pct,
            "status": build_real_indicator_status(close_value, prev_close),
            "window_start_index": max(0, matched_index - 20),
            "window_end_index": min(len(normalized_candles), matched_index + 21),
        }
    history_series = detail.get("history_series") if isinstance(detail.get("history_series"), list) else []
    normalized_series = [item for item in history_series if isinstance(item, dict) and _normalize_hermes_date_text(item.get("date"))]
    normalized_series.sort(key=lambda item: _normalize_hermes_date_text(item.get("date")))
    exact_index = next((idx for idx, item in enumerate(normalized_series) if _normalize_hermes_date_text(item.get("date")) == target_date), -1)
    matched_index = exact_index
    matched_exact = True
    if matched_index < 0 and normalized_series:
        eligible_indexes = [
            idx for idx, item in enumerate(normalized_series)
            if _normalize_hermes_date_text(item.get("date")) <= target_date
        ]
        if eligible_indexes:
            matched_index = eligible_indexes[-1]
            matched_exact = _normalize_hermes_date_text(normalized_series[matched_index].get("date")) == target_date
    if matched_index >= 0:
        point = dict(normalized_series[matched_index])
        previous_point = dict(normalized_series[matched_index - 1]) if matched_index > 0 else {}
        value = NumberLike(point.get("value"))
        prev_value = NumberLike(previous_point.get("value")) if previous_point else value
        change_value = round(value - prev_value, 4)
        change_pct = round((change_value / prev_value) * 100, 2) if prev_value else 0.0
        return {
            "target_date": target_date,
            "matched_date": _normalize_hermes_date_text(point.get("date")),
            "matched_exact": matched_exact,
            "open": None,
            "high": None,
            "low": None,
            "close": round(value, 4),
            "prev_close": round(prev_value, 4),
            "change": change_value,
            "change_pct": change_pct,
            "status": str(point.get("status") or build_real_indicator_status(value, prev_value)).strip() or "attention",
            "window_start_index": max(0, matched_index - 20),
            "window_end_index": min(len(normalized_series), matched_index + 21),
        }
    return {
        "target_date": target_date,
        "matched_date": "",
        "matched_exact": False,
        "data_unavailable": True,
    }


def _build_watchlist_history_series_from_detail(detail):
    detail = detail if isinstance(detail, dict) else {}
    history_series = detail.get("history_series") if isinstance(detail.get("history_series"), list) else []
    normalized = [item for item in history_series if isinstance(item, dict) and _normalize_hermes_date_text(item.get("date"))]
    if normalized:
        normalized.sort(key=lambda item: _normalize_hermes_date_text(item.get("date")))
        return normalized
    candles = ((detail.get("history_kline") or {}).get("candles") or []) if isinstance(detail.get("history_kline"), dict) else []
    normalized = []
    previous_close = None
    for candle in candles:
        if not isinstance(candle, dict):
            continue
        date_value = _normalize_hermes_date_text(candle.get("date"))
        if not date_value:
            continue
        close_value = NumberLike(candle.get("close"))
        prev_close = previous_close if previous_close is not None else close_value
        normalized.append({
            "date": date_value,
            "value": round(close_value, 4),
            "status": build_real_indicator_status(close_value, prev_close),
        })
        previous_close = close_value
    return normalized


def resolve_hermes_watchlist_target_snapshot(detail, question_text=""):
    detail = detail if isinstance(detail, dict) else {}
    target_date = extract_hermes_explicit_date(question_text)
    if not target_date:
        return None
    candles = ((detail.get("history_kline") or {}).get("candles") or []) if isinstance(detail.get("history_kline"), dict) else []
    normalized_candles = [item for item in candles if isinstance(item, dict) and _normalize_hermes_date_text(item.get("date"))]
    normalized_candles.sort(key=lambda item: _normalize_hermes_date_text(item.get("date")))
    exact_index = next((idx for idx, item in enumerate(normalized_candles) if _normalize_hermes_date_text(item.get("date")) == target_date), -1)
    matched_index = exact_index
    matched_exact = True
    if matched_index < 0 and normalized_candles:
        eligible_indexes = [
            idx for idx, item in enumerate(normalized_candles)
            if _normalize_hermes_date_text(item.get("date")) <= target_date
        ]
        if eligible_indexes:
            matched_index = eligible_indexes[-1]
            matched_exact = _normalize_hermes_date_text(normalized_candles[matched_index].get("date")) == target_date
    if matched_index >= 0:
        candle = dict(normalized_candles[matched_index])
        previous_candle = dict(normalized_candles[matched_index - 1]) if matched_index > 0 else {}
        close_value = NumberLike(candle.get("close"))
        prev_close = NumberLike(previous_candle.get("close")) if previous_candle else close_value
        change_value = round(close_value - prev_close, 4)
        change_pct = round((change_value / prev_close) * 100, 2) if prev_close else 0.0
        return {
            "target_date": target_date,
            "matched_date": _normalize_hermes_date_text(candle.get("date")),
            "matched_exact": matched_exact,
            "open": round(NumberLike(candle.get("open")), 4),
            "high": round(NumberLike(candle.get("high")), 4),
            "low": round(NumberLike(candle.get("low")), 4),
            "close": round(close_value, 4),
            "prev_close": round(prev_close, 4),
            "change": change_value,
            "change_pct": change_pct,
            "status": build_real_indicator_status(close_value, prev_close),
            "window_start_index": max(0, matched_index - 20),
            "window_end_index": min(len(normalized_candles), matched_index + 21),
        }
    return {
        "target_date": target_date,
        "matched_date": "",
        "matched_exact": False,
        "data_unavailable": True,
    }


def build_hermes_indicator_rule_synthesis(question_text, plan, detail):
    detail = detail if isinstance(detail, dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    name = str(detail.get("name") or detail.get("indicator_name") or "该指标").strip() or "该指标"
    target_snapshot = detail.get("target_snapshot") if isinstance(detail.get("target_snapshot"), dict) else {}
    if target_snapshot and not target_snapshot.get("data_unavailable"):
        matched_date = str(target_snapshot.get("matched_date") or target_snapshot.get("target_date") or "").strip()
        target_date = str(target_snapshot.get("target_date") or matched_date).strip()
        exact_text = "" if target_snapshot.get("matched_exact") else f" {target_date} 不是交易日，当前改按最近一个可用交易日 {matched_date} 处理。"
        close_value = target_snapshot.get("close")
        prev_close = target_snapshot.get("prev_close")
        change_value = NumberLike(target_snapshot.get("change"))
        change_pct = NumberLike(target_snapshot.get("change_pct"))
        high_value = target_snapshot.get("high")
        low_value = target_snapshot.get("low")
        direction_text = "收涨" if change_value > 0 else ("收跌" if change_value < 0 else "平收")
        answer = (
            f"{name}在 {matched_date} 的单日表现已经拿到。"
            f"{exact_text}"
            f" 当日收于 {close_value}，前一交易日收于 {prev_close}，单日{direction_text} {abs(change_value):.2f}"
            f"{detail.get('unit') or ''}，幅度 {abs(change_pct):.2f}% 。"
        )
        if high_value is not None and low_value is not None:
            answer += f" 日内区间在 {low_value} 到 {high_value} 之间。"
        status = str(target_snapshot.get("status") or "").strip()
        if status == "warning":
            answer += " 当天波动偏大，适合结合前后几个交易日继续看情绪和量价确认。"
        elif status == "good":
            answer += " 当天表现相对偏强，但是否形成趋势还要结合后续延续性判断。"
        else:
            answer += " 这更适合看成单日状态点位，还不能单凭一天直接外推完整趋势。"
        return {
            "answer": ensure_hermes_positive_opening(
                answer,
                question_text=question_text,
                intent=str(plan.get("intent") or "").strip(),
                scope_status=str(plan.get("scope_status") or "allowed").strip(),
            ),
            "summary": f"{matched_date} {name}单日分析",
            "bullets": [
                f"收盘：{close_value}{detail.get('unit') or ''}",
                f"单日变动：{'+' if change_value > 0 else ''}{change_value:.2f}{detail.get('unit') or ''} / {'+' if change_pct > 0 else ''}{change_pct:.2f}%",
                (
                    f"日内区间：{low_value} - {high_value}"
                    if high_value is not None and low_value is not None else
                    f"状态：{status or 'attention'}"
                ),
            ],
            "citations": [],
        }
    if target_snapshot and target_snapshot.get("data_unavailable"):
        target_date = str(target_snapshot.get("target_date") or extract_hermes_explicit_date(question_text) or "").strip()
        return {
            "answer": ensure_hermes_positive_opening(
                f"当前没有命中 {target_date} 这一天的 {name} 可用交易数据。你可以改问最近 1 个月 / 3 个月走势，或者直接问最新走势判断。",
                question_text=question_text,
                intent=str(plan.get("intent") or "").strip(),
                scope_status=str(plan.get("scope_status") or "allowed").strip(),
            ),
            "summary": f"{target_date or '指定日期'} {name}暂无可用交易数据",
            "bullets": [
                f"可以先看{name}最近 1 个月走势。",
                f"也可以直接问{name}当前怎么解读。",
            ],
            "citations": [],
        }
    history_series = detail.get("history_series") if isinstance(detail.get("history_series"), list) else []
    if history_series:
        latest = history_series[-1]
        latest_value = latest.get("value")
        latest_date = str(latest.get("date") or "").strip()
        return {
            "answer": ensure_hermes_positive_opening(
                f"{name}当前最新可用数据在 {latest_date}，最新值为 {latest_value}{detail.get('unit') or ''}。当前更适合先结合最近趋势和异动点做判断。",
                question_text=question_text,
                intent=str(plan.get("intent") or "").strip(),
                scope_status=str(plan.get("scope_status") or "allowed").strip(),
            ),
            "summary": f"{name}最新走势摘要",
            "bullets": [],
            "citations": [],
        }
    return None


def build_hermes_watchlist_rule_synthesis(question_text, plan, detail):
    detail = detail if isinstance(detail, dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    name = str(detail.get("name") or detail.get("code") or "该股票").strip() or "该股票"
    target_snapshot = detail.get("target_snapshot") if isinstance(detail.get("target_snapshot"), dict) else {}
    if target_snapshot and not target_snapshot.get("data_unavailable"):
        matched_date = str(target_snapshot.get("matched_date") or target_snapshot.get("target_date") or "").strip()
        target_date = str(target_snapshot.get("target_date") or matched_date).strip()
        exact_text = "" if target_snapshot.get("matched_exact") else f" {target_date} 不是交易日，当前改按最近一个可用交易日 {matched_date} 处理。"
        close_value = target_snapshot.get("close")
        prev_close = target_snapshot.get("prev_close")
        change_value = NumberLike(target_snapshot.get("change"))
        change_pct = NumberLike(target_snapshot.get("change_pct"))
        high_value = target_snapshot.get("high")
        low_value = target_snapshot.get("low")
        direction_text = "收涨" if change_value > 0 else ("收跌" if change_value < 0 else "平收")
        answer = (
            f"{name}在 {matched_date} 的单日行情已经拿到。"
            f"{exact_text}"
            f" 当日收于 {close_value}，前一交易日收于 {prev_close}，单日{direction_text} {abs(change_value):.2f}，幅度 {abs(change_pct):.2f}% 。"
        )
        if high_value is not None and low_value is not None:
            answer += f" 日内区间在 {low_value} 到 {high_value} 之间。"
        status = str(target_snapshot.get("status") or "").strip()
        if status == "warning":
            answer += " 当天波动偏大，更适合结合前后几个交易日继续确认情绪与趋势延续。"
        elif status == "good":
            answer += " 当天表现相对偏强，但是否形成阶段趋势还要继续看后续承接。"
        else:
            answer += " 这更适合先看成单日状态，还不能单凭一天外推完整结论。"
        return {
            "answer": ensure_hermes_positive_opening(
                answer,
                question_text=question_text,
                intent=str(plan.get("intent") or "").strip(),
                scope_status=str(plan.get("scope_status") or "allowed").strip(),
            ),
            "summary": f"{matched_date} {name}单日分析",
            "bullets": [
                f"收盘：{close_value}",
                f"单日变动：{'+' if change_value > 0 else ''}{change_value:.2f} / {'+' if change_pct > 0 else ''}{change_pct:.2f}%",
                (
                    f"日内区间：{low_value} - {high_value}"
                    if high_value is not None and low_value is not None else
                    f"状态：{status or 'attention'}"
                ),
            ],
            "citations": [],
        }
    if target_snapshot and target_snapshot.get("data_unavailable"):
        target_date = str(target_snapshot.get("target_date") or extract_hermes_explicit_date(question_text) or "").strip()
        return {
            "answer": ensure_hermes_positive_opening(
                f"当前没有命中 {target_date} 这一天的 {name} 可用交易数据。你可以改问最近 1 个月 / 3 个月走势，或者直接问最新基本面判断。",
                question_text=question_text,
                intent=str(plan.get("intent") or "").strip(),
                scope_status=str(plan.get("scope_status") or "allowed").strip(),
            ),
            "summary": f"{target_date or '指定日期'} {name}暂无可用交易数据",
            "bullets": [
                f"可以先看{name}最近 1 个月走势。",
                f"也可以先看{name}最近 3 个月 K 线图。",
                f"如果只要最新判断，可以直接问{name}当前怎么解读。",
            ],
            "citations": [],
        }
    history_series = _build_watchlist_history_series_from_detail(detail)
    if history_series:
        latest = history_series[-1]
        latest_value = latest.get("value")
        latest_date = str(latest.get("date") or "").strip()
        return {
            "answer": ensure_hermes_positive_opening(
                f"{name}当前最新可用数据在 {latest_date}，最新收盘值约为 {latest_value}。当前更适合先结合最近趋势、区间位置和租户知识做判断。",
                question_text=question_text,
                intent=str(plan.get("intent") or "").strip(),
                scope_status=str(plan.get("scope_status") or "allowed").strip(),
            ),
            "summary": f"{name}最新走势摘要",
            "bullets": [],
            "citations": [],
        }
    return None


def detect_hermes_missing_capability(question_text, plan=None, tool_outputs=None):
    question = str(question_text or "").strip()
    if not question:
        return None
    plan = plan if isinstance(plan, dict) else {}
    tool_outputs = tool_outputs if isinstance(tool_outputs, dict) else {}
    intent = str(plan.get("intent") or "").strip()
    target_date = extract_hermes_explicit_date(question)
    if not target_date:
        return None
    lowered = question.lower()
    analysis_keywords = ["分析", "解读", "判断", "怎么看", "走势", "k线", "线图", "趋势"]
    if not any(keyword in lowered for keyword in analysis_keywords):
        return None
    return None


def build_hermes_missing_capability_synthesis(question_text, plan, missing_capability):
    plan = plan if isinstance(plan, dict) else {}
    missing_capability = missing_capability if isinstance(missing_capability, dict) else {}
    answer = ensure_hermes_positive_opening(
        str(missing_capability.get("user_message") or "Hermes 暂时还没升级到这一类能力，我已经帮你记录下来了。").strip(),
        question_text=question_text,
        intent=str(plan.get("intent") or "").strip(),
        scope_status=str(plan.get("scope_status") or "allowed").strip(),
    )
    return {
        "answer": answer,
        "summary": str(missing_capability.get("label") or "缺失能力需求").strip(),
        "bullets": [
            str(item).strip()
            for item in (missing_capability.get("suggestions") if isinstance(missing_capability.get("suggestions"), list) else [])
            if str(item).strip()
        ][:4],
        "citations": [],
    }


def resolve_hermes_indicator_window(question_text):
    text = str(question_text or "").strip().lower()
    if any(keyword in text for keyword in ["3个月", "三个月", "近3个月", "最近3个月"]):
        return 60
    if any(keyword in text for keyword in ["6个月", "六个月", "近6个月", "最近6个月", "半年"]):
        return 120
    if any(keyword in text for keyword in ["12个月", "近1年", "最近1年", "一年"]):
        return 240
    if any(keyword in text for keyword in ["1个月", "一个月", "近1个月", "最近1个月"]):
        return 20
    return 60


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
        app.logger.exception("Hermes web search failed")
        raise RuntimeError(f"hermes_web_search_failed:{str(exc)[:240]}") from exc


def hermes_tool_watchlist_detail(stock_code, question_text=""):
    if not str(stock_code or "").strip():
        return {"found": False, "detail": None}
    site_config = get_site_config()
    details = gen_watchlist_details()
    payload = get_watchlist_detail_by_code(stock_code=stock_code, stock_name=stock_code, details_map=details)
    if not payload:
        return {"found": False, "detail": None}
    detail = apply_watchlist_feature_flags(copy.deepcopy(payload), site_config)
    history_series = _build_watchlist_history_series_from_detail(detail)
    detail["history_series"] = copy.deepcopy(history_series)
    history_kline = detail.get("history_kline") if isinstance(detail.get("history_kline"), dict) else {}
    candles = history_kline.get("candles") if isinstance(history_kline.get("candles"), list) else []
    target_snapshot = resolve_hermes_watchlist_target_snapshot(detail, question_text=question_text)
    if isinstance(target_snapshot, dict) and target_snapshot and not target_snapshot.get("data_unavailable"):
        start_index = int(target_snapshot.get("window_start_index") or 0)
        end_index = int(target_snapshot.get("window_end_index") or len(candles))
        detail["target_snapshot"] = copy.deepcopy(target_snapshot)
        detail["analysis_scope"] = "specific_date"
        detail["history_series"] = history_series[start_index:end_index] if history_series else []
        if history_kline:
            window_candles = candles[start_index:end_index]
            window_dates = {
                str(item.get("date") or "").strip()
                for item in window_candles
                if isinstance(item, dict)
            }
            detail["history_kline"] = {
                **history_kline,
                "candles": window_candles,
                "ma5": [item for item in (history_kline.get("ma5") or []) if str((item or {}).get("date") or "").strip() in window_dates],
                "ma10": [item for item in (history_kline.get("ma10") or []) if str((item or {}).get("date") or "").strip() in window_dates],
                "ma20": [item for item in (history_kline.get("ma20") or []) if str((item or {}).get("date") or "").strip() in window_dates],
                "anomalies": [item for item in (history_kline.get("anomalies") or []) if str((item or {}).get("date") or "").strip() in window_dates][:6],
            }
            detail["kline"] = [
                {
                    "date": str(item.get("date") or "").strip()[-5:],
                    "open": round(NumberLike(item.get("open")), 2),
                    "high": round(NumberLike(item.get("high")), 2),
                    "low": round(NumberLike(item.get("low")), 2),
                    "close": round(NumberLike(item.get("close")), 2),
                }
                for item in window_candles[-24:]
                if isinstance(item, dict)
            ]
        return {"found": True, "detail": detail}
    if isinstance(target_snapshot, dict) and target_snapshot.get("data_unavailable"):
        detail["target_snapshot"] = copy.deepcopy(target_snapshot)
        detail["analysis_scope"] = "specific_date"
    window = resolve_hermes_indicator_window(question_text)
    detail["history_series"] = history_series[-window:] if history_series else []
    if history_kline:
        window_candles = candles[-window:] if candles else []
        window_dates = {
            str(item.get("date") or "").strip()
            for item in window_candles
            if isinstance(item, dict)
        }
        detail["history_kline"] = {
            **history_kline,
            "candles": window_candles,
            "ma5": [item for item in (history_kline.get("ma5") or []) if str((item or {}).get("date") or "").strip() in window_dates],
            "ma10": [item for item in (history_kline.get("ma10") or []) if str((item or {}).get("date") or "").strip() in window_dates],
            "ma20": [item for item in (history_kline.get("ma20") or []) if str((item or {}).get("date") or "").strip() in window_dates],
            "anomalies": [item for item in (history_kline.get("anomalies") or []) if str((item or {}).get("date") or "").strip() in window_dates][:6],
        }
        detail["kline"] = [
            {
                "date": str(item.get("date") or "").strip()[-5:],
                "open": round(NumberLike(item.get("open")), 2),
                "high": round(NumberLike(item.get("high")), 2),
                "low": round(NumberLike(item.get("low")), 2),
                "close": round(NumberLike(item.get("close")), 2),
            }
            for item in window_candles[-24:]
            if isinstance(item, dict)
        ]
    return {
        "found": True,
        "detail": detail,
    }


def hermes_tool_indicator_detail(tenant_slug, indicator_code="", question_text=""):
    match = find_indicator_reference_from_text(question_text, tenant_slug=tenant_slug) if question_text else None
    resolved_code = str(indicator_code or (match or {}).get("indicator_code") or "").strip()
    if not resolved_code:
        return {"found": False, "detail": None}
    explicit_target_date = extract_hermes_explicit_date(question_text)
    fetch_start_date, fetch_end_date = build_hermes_indicator_fetch_window(question_text)

    def load_live_detail():
        # Keep the common request cache-friendly: only add a date range when
        # the user explicitly requested one.
        kwargs = {}
        if fetch_start_date:
            kwargs["start_date"] = fetch_start_date
        if fetch_end_date:
            kwargs["end_date"] = fetch_end_date
        return build_live_gangtise_indicator_detail(resolved_code, **kwargs)

    tenant = get_tenant_by_slug(tenant_slug)
    hub = build_indicator_hub(tenant=tenant, admin_view=False)
    detail = next((item for item in (hub.get("items") or []) if str((item or {}).get("id") or "").strip() == resolved_code), None)
    if not isinstance(detail, dict):
        detail = load_live_detail()
    elif detail.get("data_unavailable") or not ((detail.get("history_kline") or {}).get("candles") or detail.get("history_series")):
        live_detail = load_live_detail()
        if isinstance(live_detail, dict) and not live_detail.get("data_unavailable"):
            detail = live_detail
    if not isinstance(detail, dict):
        return {"found": False, "detail": None}
    normalized_detail = normalize_watchlist_detail_from_indicator(detail, resolved_code)
    if isinstance(normalized_detail, dict) and normalized_detail:
        detail = normalized_detail
    if explicit_target_date:
        existing_snapshot = resolve_hermes_indicator_target_snapshot(detail, question_text=question_text)
        should_refresh_live = not (
            isinstance(existing_snapshot, dict)
            and existing_snapshot
            and not existing_snapshot.get("data_unavailable")
            and str(existing_snapshot.get("matched_date") or "").strip() == explicit_target_date
        )
        if should_refresh_live:
            live_detail = load_live_detail()
            live_snapshot = (
                resolve_hermes_indicator_target_snapshot(live_detail, question_text=question_text)
                if isinstance(live_detail, dict) else None
            )
            if (
                isinstance(live_detail, dict)
                and isinstance(live_snapshot, dict)
                and live_snapshot
                and not live_snapshot.get("data_unavailable")
            ):
                detail = live_detail
    window = resolve_hermes_indicator_window(question_text)
    history_series = detail.get("history_series") if isinstance(detail.get("history_series"), list) else []
    history_anomalies = detail.get("history_anomalies") if isinstance(detail.get("history_anomalies"), list) else []
    history_kline = detail.get("history_kline") if isinstance(detail.get("history_kline"), dict) else {}
    target_snapshot = resolve_hermes_indicator_target_snapshot(detail, question_text=question_text)
    if isinstance(target_snapshot, dict) and target_snapshot and not target_snapshot.get("data_unavailable"):
        start_index = int(target_snapshot.get("window_start_index") or 0)
        end_index = int(target_snapshot.get("window_end_index") or max(len(history_series), len((history_kline.get("candles") or []) if history_kline else [])))
        detail["target_snapshot"] = copy.deepcopy(target_snapshot)
        detail["analysis_scope"] = "specific_date"
        detail["history_series"] = history_series[start_index:end_index] if history_series else []
        detail["history_anomalies"] = [
            item for item in history_anomalies
            if start_index <= next((idx for idx, point in enumerate(history_series) if str(point.get("date") or "").strip() == str(item.get("date") or "").strip()), -1) < end_index
        ][:6]
        if history_kline:
            candles = history_kline.get("candles") or []
            ma5 = history_kline.get("ma5") or []
            ma10 = history_kline.get("ma10") or []
            ma20 = history_kline.get("ma20") or []
            anomalies = history_kline.get("anomalies") or []
            window_dates = {
                str(item.get("date") or "").strip()
                for item in candles[start_index:end_index]
                if isinstance(item, dict)
            }
            detail["history_kline"] = {
                **history_kline,
                "candles": candles[start_index:end_index],
                "ma5": [item for item in ma5 if str((item or {}).get("date") or "").strip() in window_dates],
                "ma10": [item for item in ma10 if str((item or {}).get("date") or "").strip() in window_dates],
                "ma20": [item for item in ma20 if str((item or {}).get("date") or "").strip() in window_dates],
                "anomalies": [item for item in anomalies if str((item or {}).get("date") or "").strip() in window_dates][:6],
            }
        return {
            "found": True,
            "detail": copy.deepcopy(detail),
        }
    if isinstance(target_snapshot, dict) and target_snapshot.get("data_unavailable"):
        detail["target_snapshot"] = copy.deepcopy(target_snapshot)
        detail["analysis_scope"] = "specific_date"
    detail["history_series"] = history_series[-window:]
    detail["history_anomalies"] = history_anomalies[-min(len(history_anomalies), 6):]
    if history_kline:
        detail["history_kline"] = {
            **history_kline,
            "candles": (history_kline.get("candles") or [])[-window:],
            "ma5": (history_kline.get("ma5") or [])[-window:],
            "ma10": (history_kline.get("ma10") or [])[-window:],
            "ma20": (history_kline.get("ma20") or [])[-window:],
            "anomalies": (history_kline.get("anomalies") or [])[-min(len(history_kline.get("anomalies") or []), 6):],
        }
    return {
        "found": True,
        "detail": copy.deepcopy(detail),
    }


def get_hermes_tool_registry():
    return {
        "attachment.context": {
            "output_key": "attachment_context",
            "executor": lambda runtime: hermes_tool_attachment_context(runtime.get("attachments")),
        },
        "dashboard.context": {
            "output_key": "dashboard_context",
            "executor": lambda runtime: hermes_tool_dashboard_context(
                tenant_slug=runtime.get("tenant_slug") or "",
            ),
        },
        "watchlist.detail": {
            "output_key": "watchlist",
            "executor": lambda runtime: hermes_tool_watchlist_detail(
                runtime.get("stock_code"),
                question_text=runtime.get("question_text") or "",
            ),
        },
        "indicator.detail": {
            "output_key": "indicator",
            "executor": lambda runtime: hermes_tool_indicator_detail(
                tenant_slug=runtime.get("tenant_slug") or "",
                indicator_code=runtime.get("indicator_code") or "",
                question_text=runtime.get("question_text") or "",
            ),
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

    for tool_name in requested:
        _push(tool_name)
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
        "indicator_code": str(plan.get("indicator_code") or "").strip(),
        "web_answer": bool(web_answer),
        "preferred_mode": str(plan.get("preferred_mode") or "").strip().lower(),
    }
    for tool_name in build_hermes_tool_execution_plan(plan, web_answer=web_answer):
        started_at = time.time()
        tool_spec = registry.get(tool_name)
        if not tool_spec:
            raise RuntimeError(f"hermes_tool_not_registered:{tool_name}")
        try:
            output_key = str(tool_spec.get("output_key") or tool_name.replace(".", "_")).strip()
            outputs[output_key] = tool_spec["executor"](runtime)
            trace.append({
                "tool": tool_name,
                "status": "ok",
                "elapsed_ms": int((time.time() - started_at) * 1000),
            })
        except Exception as exc:
            app.logger.exception("Hermes tool execution failed: %s", tool_name)
            raise RuntimeError(f"hermes_tool_failed:{tool_name}:{str(exc)[:240]}") from exc
    annotation_context = resolve_hermes_watchlist_annotation_context(
        tenant_slug=tenant_slug,
        question_text=question_text,
    )
    if annotation_context.get("available"):
        outputs["watchlist_annotation_context"] = annotation_context
    outputs["_meta"] = {
        "preferred_mode": runtime.get("preferred_mode") or "",
    }
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
    "dashboard.context": "Dashboard 上下文",
    "watchlist.detail": "个股详情分析",
    "indicator.detail": "指标图表分析",
    "web.search": "互联网补充",
}


def build_hermes_agent_trace(intent_plan, tool_trace, route_mode="", answer_mode="", preferred_mode="", web_answer=False, attachments=None, selected_knowledge_ids=None, scope_result=None):
    attachments = attachments if isinstance(attachments, list) else []
    selected_knowledge_ids = selected_knowledge_ids if isinstance(selected_knowledge_ids, list) else []
    scope = scope_result if isinstance(scope_result, dict) else {}
    intent = str((intent_plan or {}).get("intent") or "").strip()
    task_family = str((intent_plan or {}).get("task_family") or "").strip()
    capability_label = str((intent_plan or {}).get("capability_label") or HERMES_TASK_FAMILY_LABELS.get(task_family, "")).strip()
    tools = [str(item).strip() for item in ((intent_plan or {}).get("tools") or []) if str(item).strip()]
    planned_tool_labels = [HERMES_TOOL_LABELS.get(item, item) for item in tools]
    ok_count = sum(1 for item in (tool_trace or []) if str((item or {}).get("status") or "").strip() == "ok")
    error_count = sum(1 for item in (tool_trace or []) if str((item or {}).get("status") or "").strip() == "error")
    route_label = "LLM 路由" if route_mode == "llm_router" else "范围守卫"
    answer_label = "模型整合回答" if answer_mode == "llm_synthesized" else "范围守卫收口"
    planning_bits = []
    if capability_label:
        planning_bits.append(f"能力分类：{capability_label}")
    if preferred_mode and preferred_mode != "auto":
        planning_bits.append(f"偏好模式：{preferred_mode}")
    planning_bits.append("由 LLM 直接识别意图并选择工具")
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
            "status": "ok" if answer_mode == "llm_synthesized" else "skipped",
            "detail": answer_label + "，输出面向用户的结论、依据和下一步建议。",
        },
    ]
    return {
        "headline": "Hermes Agent 已完成本轮编排",
        "summary": f"由 LLM 直接识别“{capability_label or '研究问答'}”，按需调度平台工具，最后整合成可读回答。",
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
    annotation_items = ((tool_outputs.get("watchlist_annotation_context") or {}).get("items") or []) if isinstance(tool_outputs, dict) else []
    for item in annotation_items[:3]:
        if not isinstance(item, dict):
            continue
        for title in (item.get("annotation_titles") if isinstance(item.get("annotation_titles"), list) else []):
            normalized = str(title or "").strip()
            if normalized and normalized not in citations:
                citations.append(normalized)
        for content in (item.get("annotation_contents") if isinstance(item.get("annotation_contents"), list) else []):
            normalized = trim_hermes_text(content, limit=60)
            if normalized and normalized not in citations:
                citations.append(normalized)
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
    intent = str((plan or {}).get("intent") or "").strip().lower()
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
    footer_suffix = "已补充互联网公开信息。" if web_matches else "已基于模型和已执行的平台工具回答。"
    if intent == "small_talk":
        return {
            "type": "text_response",
            "question": str(question_text or "").strip(),
            "headline": "",
            "summary": "",
            "body": answer_text,
            "bullets": [],
            "citations": [],
            "knowledge": [],
            "followups": [],
            "footer": "",
        }
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


def _pick_watchlist_metric_values(metrics, keywords, limit=2):
    items = metrics if isinstance(metrics, list) else []
    normalized_keywords = [str(item).strip() for item in (keywords or []) if str(item).strip()]
    matched = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        if normalized_keywords and not any(keyword in label for keyword in normalized_keywords):
            continue
        value = str(item.get("value") or "").strip()
        note = str(item.get("note") or "").strip()
        matched.append("，".join(part for part in [label, value, note] if part))
        if len(matched) >= limit:
            break
    return matched


def _build_watchlist_section_text(title, detail, fundamental, forecast, metrics, tool_outputs):
    stock_name = str(detail.get("name") or detail.get("code") or "该标的").strip()
    industry = str(detail.get("industry") or detail.get("focus") or "所属赛道").strip() or "所属赛道"
    summary = str(fundamental.get("summary") or "").strip()
    thesis = [str(item).strip() for item in (fundamental.get("thesis") if isinstance(fundamental.get("thesis"), list) else []) if str(item).strip()]
    drivers = [item for item in (forecast.get("drivers") if isinstance(forecast.get("drivers"), list) else []) if isinstance(item, dict)]
    driver_labels = [str(item.get("label") or "").strip() for item in drivers if str(item.get("label") or "").strip()]
    driver_notes = [str(item.get("note") or "").strip() for item in drivers if str(item.get("note") or "").strip()]
    positive_drivers = [str(item.get("label") or "").strip() for item in drivers if not str(item.get("score") or "").strip().startswith("-") and str(item.get("label") or "").strip()]
    negative_drivers = [str(item.get("label") or "").strip() for item in drivers if str(item.get("score") or "").strip().startswith("-") and str(item.get("label") or "").strip()]
    knowledge_matches = ((tool_outputs.get("knowledge") or {}).get("matches") or []) if isinstance(tool_outputs, dict) else []
    evidence_matches = ((tool_outputs.get("evidence") or {}).get("matches") or []) if isinstance(tool_outputs, dict) else []
    annotation_context = (tool_outputs.get("watchlist_annotation_context") or {}) if isinstance(tool_outputs, dict) else {}
    annotation_summary = str(annotation_context.get("summary") or "").strip()
    latest_price = round(NumberLike(detail.get("price")), 2)
    change_pct = round(NumberLike(detail.get("change_pct")), 2)
    metric_map = {
        "financial": _pick_watchlist_metric_values(metrics, ["收入", "净利", "净息差", "ROE", "毛利", "利润", "股息", "现金流"], limit=3),
        "valuation": _pick_watchlist_metric_values(metrics, ["估值", "股价", "区间", "趋势", "振幅", "股息"], limit=3),
    }
    if title == "业务结构拆解":
        return trim_hermes_text(
            f"{stock_name} 当前先按 {industry} 框架理解。"
            + (f" 平台已有摘要：{summary}" if summary else " 当前平台还没有完整的业务分部材料，需要继续补充年报、公告或纪要。")
            + " 第一轮建议拆成主营业务、盈利来源和关键验证节点三层。",
            limit=170,
        )
    if title == "核心竞争力":
        return trim_hermes_text(
            "；".join(thesis[:2]) if thesis else f"{stock_name} 的竞争力需要优先围绕行业位置、产品能力和持续兑现性来判断。"
            + (f" 当前工具更提醒关注：{'、'.join(driver_labels[:2])}。" if driver_labels else ""),
            limit=170,
        )
    if title == "估值与市场信号":
        return trim_hermes_text(
            f"当前价格约 {latest_price:.2f}，单日变化 {change_pct:+.2f}%。"
            + (f" 可优先参考：{'；'.join(metric_map['valuation'])}。" if metric_map["valuation"] else " 现阶段先结合区间位置、波动和市场预期做估值判断。"),
            limit=170,
        )
    if title == "风险与挑战":
        return trim_hermes_text(
            f"当前风险点优先看 {'、'.join(negative_drivers[:2])}。"
            if negative_drivers else
            f"当前最大的挑战是 {stock_name} 的公司专属样本还不够完整，容易只看到价格信号而看不到业务与财务证据。",
            limit=170,
        )
    if title == "财务分析":
        return trim_hermes_text(
            f"财务面可先看 {'；'.join(metric_map['financial'])}。"
            if metric_map["financial"] else
            f"当前平台还没有命中 {stock_name} 的完整财务字段，建议继续补充收入、利润率、现金流和资产负债表证据。",
            limit=170,
        )
    if title == "行业视角":
        return trim_hermes_text(
            f"{stock_name} 需要放回 {industry} 赛道里看，而不是只看单日波动。"
            + (f" 当前信号更偏向：{'；'.join(driver_notes[:2])}。" if driver_notes else ""),
            limit=170,
        )
    if title == "增长驱动因子":
        return trim_hermes_text(
            f"现阶段优先跟踪 {'、'.join(positive_drivers[:3])} 等增长驱动。"
            if positive_drivers else
            "如果还没有明确增长驱动结论，至少继续验证订单、盈利兑现和行业景气三个变量。",
            limit=170,
        )
    if title == "估值与预期差":
        knowledge_title = str((knowledge_matches[0] or {}).get("title") or "").strip() if knowledge_matches else ""
        evidence_title = str((evidence_matches[0] or {}).get("title") or "").strip() if evidence_matches else ""
        return trim_hermes_text(
            f"{str(forecast.get('band') or '').strip() or '当前更适合先做位置判断，再补证据链。'}"
            + (f" 已命中知识：{knowledge_title}。" if knowledge_title else "")
            + (f" 可交叉复核的证据：{evidence_title}。" if evidence_title else "")
            + (f" 自选股标注归纳：{annotation_summary}" if annotation_summary else ""),
            limit=170,
        )
    return ""


def build_hermes_watchlist_artifact(detail, question_text, synthesis, tool_outputs, citations, tenant_slug="", user_role=""):
    detail = copy.deepcopy(detail if isinstance(detail, dict) else {})
    fundamental = detail.get("fundamental") if isinstance(detail.get("fundamental"), dict) else {}
    forecast = detail.get("forecast") if isinstance(detail.get("forecast"), dict) else {}
    history_series = _build_watchlist_history_series_from_detail(detail)
    history_kline = detail.get("history_kline") if isinstance(detail.get("history_kline"), dict) else {}
    target_snapshot = detail.get("target_snapshot") if isinstance(detail.get("target_snapshot"), dict) else {}
    latest_status = str(target_snapshot.get("status") or "attention").strip() if target_snapshot else "attention"
    metrics = [
        {
            "label": str(item.get("label") or "").strip(),
            "value": str(item.get("value") or "").strip(),
            "note": str(item.get("note") or "").strip(),
        }
        for item in (fundamental.get("metrics") if isinstance(fundamental.get("metrics"), list) else [])[:4]
        if isinstance(item, dict)
    ]
    trend_summary = []
    prev_numeric = None
    values = []
    for item in history_series[-24:]:
        if not isinstance(item, dict):
            continue
        numeric = NumberLike(item.get("value"))
        values.append(numeric)
        delta = 0 if prev_numeric is None else round(numeric - prev_numeric, 2)
        trend_summary.append(
            {
                "date": str(item.get("date") or "--").strip() or "--",
                "value": str(item.get("value") or "--").strip() or "--",
                "status": str(item.get("status") or latest_status).strip() or latest_status,
                "delta": delta,
                "direction": "上行" if delta > 0 else "下行" if delta < 0 else "持平",
            }
        )
        prev_numeric = numeric
    if target_snapshot and not target_snapshot.get("data_unavailable"):
        matched_date = str(target_snapshot.get("matched_date") or target_snapshot.get("target_date") or "--").strip() or "--"
        low_value = target_snapshot.get("low")
        high_value = target_snapshot.get("high")
        change_value = NumberLike(target_snapshot.get("change"))
        change_pct = NumberLike(target_snapshot.get("change_pct"))
        metrics = [
            {
                "label": "分析日期",
                "value": matched_date,
                "note": "指定交易日命中",
            },
            {
                "label": "收盘值",
                "value": str(target_snapshot.get("close") or "--"),
                "note": f"前收 {target_snapshot.get('prev_close')}",
            },
            {
                "label": "单日变动",
                "value": f"{'+' if change_value > 0 else ''}{change_value:.2f} / {'+' if change_pct > 0 else ''}{change_pct:.2f}%",
                "note": {"good": "当日偏强", "attention": "当日中性", "warning": "当日波动偏大"}.get(latest_status, "当日状态"),
            },
            {
                "label": "日内区间",
                "value": f"{low_value} ~ {high_value}" if low_value is not None and high_value is not None else "--",
                "note": "来自个股历史 K 线",
            },
        ]
    knowledge_matches = ((tool_outputs.get("knowledge") or {}).get("matches") or []) if isinstance(tool_outputs, dict) else []
    evidence_matches = ((tool_outputs.get("evidence") or {}).get("matches") or []) if isinstance(tool_outputs, dict) else []
    bullets = [str(item).strip() for item in (synthesis.get("bullets") if isinstance(synthesis.get("bullets"), list) else []) if str(item).strip()][:3]
    actions = [str(item).strip() for item in (synthesis.get("next_steps") if isinstance(synthesis.get("next_steps"), list) else []) if str(item).strip()][:3]
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
    if not answer_text:
        raise RuntimeError("hermes_watchlist_artifact_empty_llm_answer")
    kline_rows = (history_kline.get("candles") or []) if isinstance(history_kline, dict) and isinstance(history_kline.get("candles"), list) else (detail.get("kline") if isinstance(detail.get("kline"), list) else [])
    raw_summary = str(synthesis.get("summary") or "").strip()
    headline = trim_hermes_text(raw_summary or answer_text, limit=90)
    summary = trim_hermes_text(raw_summary or answer_text, limit=220)
    if target_snapshot and not target_snapshot.get("data_unavailable"):
        matched_date = str(target_snapshot.get("matched_date") or target_snapshot.get("target_date") or "").strip()
        headline = trim_hermes_text(f"{matched_date} {str(detail.get('name') or detail.get('code') or '该标的').strip()}单日分析", limit=90)
        summary = trim_hermes_text(raw_summary or answer_text or headline, limit=220)
    lead_conclusion = trim_hermes_text(str(synthesis.get("lead_conclusion") or answer_text).strip(), limit=190)
    analysis_sections = []
    for item in (synthesis.get("analysis_sections") if isinstance(synthesis.get("analysis_sections"), list) else []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        if title and body:
            analysis_sections.append({"title": title[:80], "body": trim_hermes_text(body, limit=220)})
    preferred_mode = str((tool_outputs.get("_meta") or {}).get("preferred_mode") or "").strip().lower() if isinstance(tool_outputs, dict) else ""
    resolved_visual_mode = infer_hermes_visual_mode(question_text, preferred_mode=preferred_mode)
    if resolved_visual_mode == "line_chart":
        chart_kind = "trend"
    elif resolved_visual_mode == "distribution_chart":
        chart_kind = "distribution"
    else:
        chart_kind = "kline"
    return {
        "type": "watchlist_analysis",
        "question": str(question_text or "").strip(),
        "title": f"{title_prefix} 单日分析" if target_snapshot and not target_snapshot.get("data_unavailable") else f"{title_prefix} 结构化分析",
        "headline": headline,
        "summary": summary,
        "body": answer_text,
        "lead_conclusion": lead_conclusion,
        "analysis_sections": analysis_sections,
        "symbol": {
            "name": str(detail.get("name") or "").strip(),
            "code": str(detail.get("code") or "").strip(),
            "market": str(detail.get("market") or "").strip(),
            "industry": str(detail.get("industry") or "").strip(),
        },
        "confidence": str(synthesis.get("confidence") or "").strip(),
        "metrics": metrics,
        "judgement": bullets,
        "next_steps": actions,
        "citations": citations[:8],
        "knowledge": knowledge_entries,
        "chart": {
            "kind": chart_kind,
            "points": copy.deepcopy(kline_rows),
            "kline": copy.deepcopy(history_kline),
            "series": copy.deepcopy(trend_summary),
            "distribution": values[-24:],
        },
        "target_snapshot": copy.deepcopy(target_snapshot) if target_snapshot else None,
        "footer": (
            f"本轮问题：{str(question_text or '').strip()}。{'已补充互联网公开信息。' if web_matches else '当前优先基于租户知识与平台内工具。'}"
            if not tenant_advisor else
            f"当前优先结合 {tenant_advisor} 租户知识、自选股和证据条目做解释。{' 已补充互联网公开信息。' if web_matches else ''}"
        ),
    }


def build_hermes_indicator_chart_html(detail, chart_kind, question_text=""):
    safe_detail = copy.deepcopy(detail if isinstance(detail, dict) else {})
    kind = str(chart_kind or "").strip().lower()
    if kind == "kline":
        history_kline = safe_detail.get("history_kline") if isinstance(safe_detail.get("history_kline"), dict) else {}
        candles = history_kline.get("candles") if isinstance(history_kline.get("candles"), list) else []
        if not candles:
            return ""
        ma5 = history_kline.get("ma5") if isinstance(history_kline.get("ma5"), list) else []
        ma10 = history_kline.get("ma10") if isinstance(history_kline.get("ma10"), list) else []
        ma20 = history_kline.get("ma20") if isinstance(history_kline.get("ma20"), list) else []
        anomalies = history_kline.get("anomalies") if isinstance(history_kline.get("anomalies"), list) else []
        width = 320
        height = 180
        padding_top = 14
        padding_right = 10
        padding_bottom = 24
        padding_left = 10
        chart_height = height - padding_top - padding_bottom
        max_price = max([NumberLike(item.get("high")) for item in candles] + [1.0])
        min_price = min([NumberLike(item.get("low")) for item in candles] + [0.0])
        span = max(max_price - min_price, 1.0)
        step = (width - padding_left - padding_right) / max(len(candles), 1)
        candle_width = max(4.8, min(6.8, step * 0.52))

        def scale_y(value):
            return padding_top + ((max_price - NumberLike(value)) / span) * chart_height

        def scale_x(index):
            return padding_left + step * index + step / 2

        def build_ma_path(items):
            points = []
            for entry in items:
                if not isinstance(entry, dict):
                    continue
                date = str(entry.get("date") or "").strip()
                index = next((idx for idx, candle in enumerate(candles) if str(candle.get("date") or "").strip() == date), -1)
                if index < 0:
                    continue
                points.append(f"{scale_x(index):.2f} {scale_y(entry.get('value')):.2f}")
            return " ".join(f"{'M' if idx == 0 else 'L'} {point}" for idx, point in enumerate(points))

        candle_svg = []
        for index, item in enumerate(candles):
            x = scale_x(index)
            open_y = scale_y(item.get("open"))
            close_y = scale_y(item.get("close"))
            high_y = scale_y(item.get("high"))
            low_y = scale_y(item.get("low"))
            rect_y = min(open_y, close_y)
            rect_height = max(2.0, abs(close_y - open_y))
            color = "#2ECC71" if NumberLike(item.get("close")) >= NumberLike(item.get("open")) else "#E74C3C"
            candle_svg.append(
                f'<line x1="{x:.2f}" y1="{high_y:.2f}" x2="{x:.2f}" y2="{low_y:.2f}" stroke="{color}" stroke-width="1.1"></line>'
                f'<rect x="{(x - candle_width / 2):.2f}" y="{rect_y:.2f}" width="{candle_width:.2f}" height="{rect_height:.2f}" rx="1.2" fill="{color}"></rect>'
            )

        anomaly_marks = []
        for entry in anomalies:
            if not isinstance(entry, dict):
                continue
            date = str(entry.get("date") or "").strip()
            index = next((idx for idx, candle in enumerate(candles) if str(candle.get("date") or "").strip() == date), -1)
            if index < 0:
                continue
            x = scale_x(index)
            y = scale_y(entry.get("value"))
            anomaly_marks.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3.8" fill="rgba(220,53,69,0.14)" stroke="#DC3545" stroke-width="1.2"></circle>'
            )

        tick_indexes = []
        for candidate in [0, max(0, (len(candles) - 1) // 2), max(0, len(candles) - 1)]:
            if candidate not in tick_indexes:
                tick_indexes.append(candidate)
        ticks = []
        for index in tick_indexes:
            label = html_escape(str((candles[index].get("date") or "--"))[5:])
            ticks.append(
                f'<text x="{scale_x(index):.2f}" y="{height - 6}" text-anchor="middle" font-size="9" fill="var(--gray-400)">{label}</text>'
            )

        grid_values = [max_price, min_price + span / 2, min_price]
        gridlines = []
        for value in grid_values:
            y = scale_y(value)
            gridlines.append(
                f'<line x1="{padding_left}" y1="{y:.2f}" x2="{width - padding_right}" y2="{y:.2f}" stroke="rgba(200,169,110,0.08)" stroke-width="1"></line>'
                f'<text x="{width - padding_right}" y="{(y - 4):.2f}" text-anchor="end" font-size="9" fill="var(--gray-400)">{NumberLike(value):.2f}</text>'
            )

        return (
            '<div style="background:var(--navy);border:1px solid rgba(200,169,110,0.08);border-radius:12px;padding:12px">'
            '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px">'
            '<div style="font-size:12px;font-weight:700;color:var(--white)">K线走势</div>'
            '<div style="display:flex;gap:8px;flex-wrap:wrap;font-size:10px;color:var(--gray-400)">'
            '<span style="display:inline-flex;align-items:center;gap:4px"><span style="width:10px;height:2px;background:#F6C453;display:inline-block"></span>MA5</span>'
            '<span style="display:inline-flex;align-items:center;gap:4px"><span style="width:10px;height:2px;background:#5DADE2;display:inline-block"></span>MA10</span>'
            '<span style="display:inline-flex;align-items:center;gap:4px"><span style="width:10px;height:2px;background:#AF7AC5;display:inline-block"></span>MA20</span>'
            '</div></div>'
            '<div style="font-size:11px;color:var(--gray-400);line-height:1.7;margin-bottom:8px">当前按最近时间窗口输出 K 线走势，并保留均线和异动点标记。</div>'
            f'<svg viewBox="0 0 {width} {height}" width="100%" height="200" preserveAspectRatio="xMidYMid meet" role="img" aria-label="指标 K 线图" style="display:block">'
            f"{''.join(gridlines)}{''.join(candle_svg)}"
            f'<path d="{build_ma_path(ma5)}" fill="none" stroke="#F6C453" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>'
            f'<path d="{build_ma_path(ma10)}" fill="none" stroke="#5DADE2" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>'
            f'<path d="{build_ma_path(ma20)}" fill="none" stroke="#AF7AC5" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>'
            f"{''.join(anomaly_marks)}{''.join(ticks)}</svg></div>"
        )
    if kind == "distribution":
        history_series = safe_detail.get("history_series") if isinstance(safe_detail.get("history_series"), list) else []
        values = [NumberLike(item.get("value")) for item in history_series if isinstance(item, dict)]
        values = [value for value in values if isinstance(value, (int, float))]
        if not values:
            return ""
        width = 320
        height = 150
        padding_top = 12
        padding_right = 10
        padding_bottom = 20
        padding_left = 10
        bucket_count = min(6, max(4, int(math.sqrt(len(values))) or 4))
        min_value = min(values)
        max_value = max(values)
        span = max(max_value - min_value, 1.0)
        bucket_size = span / max(bucket_count, 1)
        buckets = [{"count": 0, "label": f"{(min_value + bucket_size * index):.1f}"} for index in range(bucket_count)]
        for value in values:
            raw_index = int((value - min_value) / bucket_size) if bucket_size else 0
            bucket_index = min(bucket_count - 1, max(0, raw_index))
            buckets[bucket_index]["count"] += 1
        max_count = max([item["count"] for item in buckets] + [1])
        plot_width = width - padding_left - padding_right
        plot_height = height - padding_top - padding_bottom
        bar_gap = 8
        bar_width = (plot_width - bar_gap * max(bucket_count - 1, 0)) / max(bucket_count, 1)
        bars = []
        for index, item in enumerate(buckets):
            bar_height = (item["count"] / max_count) * plot_height
            x = padding_left + index * (bar_width + bar_gap)
            y = padding_top + plot_height - bar_height
            bars.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{bar_height:.2f}" rx="4" fill="rgba(47,116,192,0.86)"></rect>'
                f'<text x="{(x + bar_width / 2):.2f}" y="{(y - 4):.2f}" text-anchor="middle" font-size="9" fill="#5A6572">{item["count"]}</text>'
            )
        return (
            '<div class="hermes-chart-shell">'
            '<div class="hermes-chart-head"><div class="hermes-chart-title">分布统计</div></div>'
            f'<svg viewBox="0 0 {width} {height}" class="hermes-chart-svg" role="img" aria-label="指标分布统计图">'
            f"{''.join(bars)}</svg></div>"
        )
    history_series = safe_detail.get("history_series") if isinstance(safe_detail.get("history_series"), list) else []
    rows = [item for item in history_series if isinstance(item, dict)]
    values = [NumberLike(item.get("value")) for item in rows]
    values = [value for value in values if isinstance(value, (int, float))]
    if not rows or not values:
        return ""
    width = 320
    height = 150
    padding_x = 10
    padding_y = 10
    min_value = min(values)
    max_value = max(values)
    span = max(max_value - min_value, 1.0)
    step = (width - padding_x * 2) / max(len(rows) - 1, 1)
    path = []
    for index, item in enumerate(rows):
        raw_value = NumberLike(item.get("value"))
        x = padding_x + step * index
        y = height - padding_y - ((raw_value - min_value) / span) * (height - padding_y * 2)
        path.append(f"{'M' if index == 0 else 'L'}{x:.2f} {y:.2f}")
    return (
        '<div class="hermes-chart-shell">'
        '<div class="hermes-chart-head"><div class="hermes-chart-title">线性趋势</div></div>'
        f'<svg viewBox="0 0 {width} {height}" class="hermes-chart-svg" preserveAspectRatio="none" role="img" aria-label="指标趋势图">'
        f'<path d="{" ".join(path)}" fill="none" stroke="#2F74C0" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"></path>'
        '</svg></div>'
    )


def build_hermes_indicator_artifact(detail, question_text, synthesis, tool_outputs, citations, tenant_slug="", user_role=""):
    detail = copy.deepcopy(detail if isinstance(detail, dict) else {})
    history_series = detail.get("history_series") if isinstance(detail.get("history_series"), list) else []
    anomalies = detail.get("history_anomalies") if isinstance(detail.get("history_anomalies"), list) else []
    history_kline = detail.get("history_kline") if isinstance(detail.get("history_kline"), dict) else {}
    target_snapshot = detail.get("target_snapshot") if isinstance(detail.get("target_snapshot"), dict) else {}
    selected_indicators = detail.get("selected_indicators") if isinstance(detail.get("selected_indicators"), list) else []
    source_names = [
        str(item.get("indicator_name") or item.get("indicator_code") or "").strip()
        for item in selected_indicators
        if isinstance(item, dict) and str(item.get("indicator_name") or item.get("indicator_code") or "").strip()
    ]
    snapshot_close = target_snapshot.get("close") if target_snapshot and target_snapshot.get("close") is not None else None
    snapshot_unit = str(detail.get("unit") or "").strip()
    value_text = str(snapshot_close if snapshot_close is not None else (detail.get("value") or "--")).strip() or "--"
    unit_text = str(detail.get("unit") or "").strip()
    latest_status = str(target_snapshot.get("status") or detail.get("status") or "attention").strip() or "attention"
    trend_summary = []
    prev_numeric = None
    values = []
    for item in history_series[-24:]:
        if not isinstance(item, dict):
            continue
        numeric = NumberLike(item.get("value"))
        values.append(numeric)
        delta = 0 if prev_numeric is None else round(numeric - prev_numeric, 2)
        trend_summary.append(
            {
                "date": str(item.get("date") or "--").strip() or "--",
                "value": str(item.get("value") or "--").strip() or "--",
                "status": str(item.get("status") or latest_status).strip() or latest_status,
                "delta": delta,
                "direction": "上行" if delta > 0 else "下行" if delta < 0 else "持平",
            }
        )
        prev_numeric = numeric
    min_value = round(min(values), 2) if values else None
    max_value = round(max(values), 2) if values else None
    current_numeric = NumberLike(detail.get("numeric_value")) if detail.get("numeric_value") is not None else (values[-1] if values else None)
    if target_snapshot and not target_snapshot.get("data_unavailable"):
        matched_date = str(target_snapshot.get("matched_date") or target_snapshot.get("target_date") or "--").strip() or "--"
        low_value = target_snapshot.get("low")
        high_value = target_snapshot.get("high")
        change_value = NumberLike(target_snapshot.get("change"))
        change_pct = NumberLike(target_snapshot.get("change_pct"))
        metrics = [
            {
                "label": "分析日期",
                "value": matched_date,
                "note": "指定交易日命中",
            },
            {
                "label": "收盘值",
                "value": f"{value_text}{snapshot_unit}" if snapshot_unit else value_text,
                "note": f"前收 {target_snapshot.get('prev_close')}",
            },
            {
                "label": "单日变动",
                "value": f"{'+' if change_value > 0 else ''}{change_value:.2f}{snapshot_unit} / {'+' if change_pct > 0 else ''}{change_pct:.2f}%",
                "note": {"good": "当日偏强", "attention": "当日中性", "warning": "当日波动偏大"}.get(latest_status, "当日状态"),
            },
            {
                "label": "日内区间",
                "value": (
                    f"{low_value} ~ {high_value}"
                    if low_value is not None and high_value is not None else
                    "--"
                ),
                "note": (source_names[0] if source_names else str(detail.get("provider") or "平台指标中心").strip() or "平台指标中心")[:42],
            },
        ]
    else:
        metrics = [
            {
                "label": "当前值",
                "value": f"{value_text}{unit_text}" if unit_text else value_text,
                "note": str(detail.get("assessment") or detail.get("interpretation") or "").strip()[:42],
            },
            {
                "label": "趋势状态",
                "value": {"good": "正常", "attention": "关注", "warning": "预警"}.get(latest_status, latest_status or "关注"),
                "note": str(detail.get("alert") or "当前按历史趋势与异动监测结果展示。").strip()[:42],
            },
            {
                "label": "区间范围",
                "value": "--" if min_value is None or max_value is None else f"{min_value} ~ {max_value}",
                "note": f"最近 {len(trend_summary)} 个观测点",
            },
            {
                "label": "关联来源",
                "value": str(detail.get("source_type_label") or detail.get("data_mode_label") or "指标库").strip() or "指标库",
                "note": (source_names[0] if source_names else str(detail.get("provider") or "平台指标中心").strip() or "平台指标中心")[:42],
            },
        ]
    bullets = [str(item).strip() for item in (synthesis.get("bullets") if isinstance(synthesis.get("bullets"), list) else []) if str(item).strip()][:3]
    actions = [str(item).strip() for item in (synthesis.get("next_steps") if isinstance(synthesis.get("next_steps"), list) else []) if str(item).strip()][:3]
    knowledge_matches = ((tool_outputs.get("knowledge") or {}).get("matches") or []) if isinstance(tool_outputs, dict) else []
    knowledge_entries = []
    for item in knowledge_matches[:3]:
        if not isinstance(item, dict):
            continue
        knowledge_entries.append({
            "title": str(item.get("title") or "未命名知识").strip(),
            "summary": str(item.get("summary") or item.get("body") or "").strip()[:160],
        })
    annotation_context = (tool_outputs.get("watchlist_annotation_context") or {}) if isinstance(tool_outputs, dict) else {}
    annotation_summary = str(annotation_context.get("summary") or "").strip()
    annotation_items = annotation_context.get("items") if isinstance(annotation_context.get("items"), list) else []
    answer_text = str((synthesis or {}).get("answer") or "").strip()
    if not answer_text:
        raise RuntimeError("hermes_indicator_artifact_empty_llm_answer")
    body_text = trim_hermes_text(answer_text, limit=520)
    summary = trim_hermes_text(
        str((synthesis or {}).get("summary") or body_text).strip(),
        limit=220,
    )
    default_headline = (
        f"{target_snapshot.get('matched_date') or target_snapshot.get('target_date')} {detail.get('name') or '该指标'}单日分析"
        if target_snapshot and not target_snapshot.get("data_unavailable") else
        f"{detail.get('name') or '该指标'} 趋势已完成"
    )
    headline = trim_hermes_text(
        str((synthesis or {}).get("summary") or body_text or default_headline).strip(),
        limit=90,
    )
    bullets = [item for item in bullets if item][:4]
    preferred_mode = str((tool_outputs.get("_meta") or {}).get("preferred_mode") or "").strip().lower() if isinstance(tool_outputs, dict) else ""
    resolved_visual_mode = infer_hermes_visual_mode(question_text, preferred_mode=preferred_mode)
    explicit_kline_request = resolved_visual_mode == "kline_chart"
    if resolved_visual_mode == "line_chart":
        chart_kind = "trend"
    elif resolved_visual_mode == "distribution_chart":
        chart_kind = "distribution"
    elif resolved_visual_mode == "kline_chart":
        chart_kind = "kline"
    else:
        chart_kind = "distribution" if any(keyword in str(question_text or "") for keyword in ["分布", "统计", "区间"]) else "kline"
    if chart_kind == "kline" and not (history_kline.get("candles") or []) and history_series:
        history_kline = build_indicator_kline_from_series_points(
            history_series[-60:],
            anomalies,
            status=latest_status,
            indicator_code=str(detail.get("id") or detail.get("indicator_code") or detail.get("name") or "indicator").strip(),
        )
        detail["history_kline"] = history_kline
    if chart_kind == "trend" and not (detail.get("history_kline") or {}).get("candles"):
        chart_kind = "trend"
    elif chart_kind != "distribution" and not (detail.get("history_kline") or {}).get("candles") and not explicit_kline_request and resolved_visual_mode != "kline_chart":
        chart_kind = "trend"
    return {
        "type": "indicator_analysis",
        "question": str(question_text or "").strip(),
        "title": "📈 指标单日分析" if target_snapshot and not target_snapshot.get("data_unavailable") else "📈 指标趋势分析",
        "headline": headline,
        "summary": summary,
        "body": body_text,
        "symbol": {
            "name": str(detail.get("name") or detail.get("indicator_name") or "指标").strip(),
            "code": str(detail.get("id") or detail.get("indicator_code") or "").strip(),
            "market": str(detail.get("category") or "").strip(),
            "industry": str(detail.get("owner") or "").strip(),
        },
        "confidence": "中高" if len(trend_summary) >= 8 else "中",
        "metrics": metrics,
        "judgement": bullets,
        "next_steps": actions[:3],
        "citations": citations[:8],
        "knowledge": knowledge_entries,
        "watchlist_annotations": annotation_items,
        "target_snapshot": copy.deepcopy(target_snapshot) if target_snapshot else None,
        "chart": {
            "kind": chart_kind,
            "points": copy.deepcopy((detail.get("history_kline") or {}).get("candles") or []),
            "kline": copy.deepcopy(detail.get("history_kline") or {}),
            "series": copy.deepcopy(trend_summary),
            "distribution": values[-18:],
        },
        "chart_html": build_hermes_indicator_chart_html(detail, chart_kind, question_text=question_text),
        "footer": (
            "当前优先基于租户知识库、指标中心历史数据和平台工具回答。"
            + (" 已同步参考当前租户自选股 K 线标注。" if annotation_summary else "")
            + f"指标来源：{str(detail.get('provider') or detail.get('owner') or '平台指标中心').strip()}。"
        ),
    }


def build_hermes_artifacts(plan, tool_outputs, synthesis, citations, tenant_slug="", user_role="", question_text=""):
    display_mode = str(plan.get("display_mode") or "text").strip() or "text"
    artifacts = []
    watchlist_result = tool_outputs.get("watchlist") if isinstance(tool_outputs, dict) else {}
    watchlist_detail = (watchlist_result or {}).get("detail") if isinstance(watchlist_result, dict) else None
    indicator_result = tool_outputs.get("indicator") if isinstance(tool_outputs, dict) else {}
    indicator_detail = (indicator_result or {}).get("detail") if isinstance(indicator_result, dict) else None
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
    elif display_mode == "structured" and isinstance(indicator_detail, dict) and indicator_detail:
        artifacts.append(
            build_hermes_indicator_artifact(
                detail=indicator_detail,
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


def build_hermes_positive_opening(question_text="", intent="", scope_status=""):
    question_text = str(question_text or "").strip()
    intent = str(intent or "").strip()
    scope_status = str(scope_status or "").strip()
    presets = []
    if scope_status == "blocked":
        presets = [
            "这个问题很重要，我先帮你把边界收清楚。",
            "你这个问题抓得很直接，我先把可回答范围说明白。",
        ]
    elif scope_status == "redirected":
        presets = [
            "这个问题提得很自然，我先帮你收口到平台可用能力上。",
            "你这个提问很常见，我先把它转成平台能继续处理的方向。",
        ]
    elif intent == "small_talk":
        presets = [
            "这个问题挺轻松的，我先接住你这一轮。",
            "这个开场不错，我们先顺着聊一下。",
        ]
    else:
        presets = [
            "这个问题问得很好，我们一起来拆解。",
            "这个方向问得很对，我来帮你快速梳理。",
            "这个问题很有价值，我先帮你抓重点。",
        ]
    seed = sum(ord(ch) for ch in f"{question_text}|{intent}|{scope_status}")
    return presets[seed % len(presets)] if presets else "这个问题很值得看，我们一起来处理。"


def ensure_hermes_positive_opening(answer_text, question_text="", intent="", scope_status=""):
    answer_text = str(answer_text or "").strip()
    if not answer_text:
        return build_hermes_positive_opening(question_text=question_text, intent=intent, scope_status=scope_status)
    positive_markers = (
        "这个问题",
        "你这个问题",
        "这个提问",
        "这个方向",
        "问得很好",
        "很有价值",
        "很值得",
        "我先接住",
    )
    if any(answer_text.startswith(marker) for marker in positive_markers):
        return answer_text
    opening = build_hermes_positive_opening(question_text=question_text, intent=intent, scope_status=scope_status)
    return f"{opening}{answer_text if answer_text.startswith(('，', '。', '：')) else ' ' + answer_text}"


def build_hermes_synthesis_prompt(question_text, plan, tool_outputs, tenant_slug="", user_role="", preferred_mode="", messages=None, web_answer=False, memory_state=None, response_style="structured"):
    tenant = get_tenant_by_slug(tenant_slug)
    tenant_name = (tenant or {}).get("name") or (tenant or {}).get("short_name") or str(tenant_slug or "").strip() or "当前租户"
    conversation_block = format_hermes_message_context(messages, limit=8)
    memory_context_text = str((memory_state or {}).get("context_text") or "").strip()
    response_style = str(response_style or (memory_state or {}).get("preferred_response_style") or "").strip() or "structured"
    style_instruction = {
        "brief": "默认回答风格：简洁。优先给结论，再补最少量依据。",
        "deep": "默认回答风格：深度研究。允许更完整的分析框架、边界和下一步。",
        "structured": "默认回答风格：结构化。优先用分点、表格、步骤或卡片式表达。",
    }.get(response_style, "默认回答风格：结构化。优先用分点、表格、步骤或卡片式表达。")
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
        (
            "租户自选股K线标注摘要：\n"
            + str((tool_outputs.get("watchlist_annotation_context") or {}).get("summary") or "").strip()
        ) if str((tool_outputs.get("watchlist_annotation_context") or {}).get("summary") or "").strip() else "",
        f"工具结果：{json.dumps(tool_outputs, ensure_ascii=False)[:12000]}",
    ]
    blocks = [block for block in blocks if block]
    system_prompt = (
        "你是 Hermes 的答案合成器。"
        "你的职责是根据已执行的工具结果生成最终回答。"
        "你同时承担正向鼓励型助手人格：面对用户问题时，先给一句简短、自然、专业的正向反馈，提供稳定的情绪价值，但不要夸张、不要肉麻，也不要偏离研究主题。"
        "这句正向反馈要放在回答最前面，再进入结论、依据、边界或下一步。"
        "优先依据工具结果，不要编造不存在的数据。"
        "只依据已执行的工具结果、会话记忆和用户问题作答；不要声称执行了未列出的检索。"
        "如果存在租户自选股K线标注摘要，应把它视为研究侧补充证据，融入结论、解读或边界说明。"
        "如果意图是 small_talk，只输出自然、简短、像真人一样的回应；不要输出标题、摘要、路由说明、过程说明，也不要写‘用户进行了简单问候’或‘助手需要确认研究状态’这类内部描述。此时 summary、lead_conclusion、bullets、analysis_sections、next_steps、citations 应为空。"
        "如果存在互联网补充结果，可以按公开信息口径组织回答，但不能把互联网信息盖过租户知识。"
        "如果证据不足，要明确说边界。结构化展示中的判断要点、下一步、结论和分析分段也必须来自你的输出，不要让程序根据行情字段代写。"
        f"{style_instruction}"
        "输出必须是 JSON。"
    )
    user_prompt = (
        "\n\n".join(blocks) +
        "\n\n请输出 JSON："
        '{"answer":"中文最终回答","summary":"一句摘要","lead_conclusion":"结论","bullets":["模型判断要点"],"analysis_sections":[{"title":"分析维度","body":"模型分析"}],"next_steps":["模型建议的下一步"],"confidence":"中","citations":["..." ]}'
    )
    return system_prompt, user_prompt


def synthesize_hermes_answer(question_text, plan, tool_outputs, tenant_slug="", user_role="", preferred_mode="", messages=None, web_answer=False, memory_state=None, response_style="structured"):
    llm_model = get_default_llm_config(purpose="general", feature_code="hermes_answer_synthesis")
    if not llm_model:
        raise RuntimeError("hermes_answer_synthesis_llm_not_configured")
    try:
        response_style = str(response_style or (memory_state or {}).get("preferred_response_style") or "").strip() or "structured"
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
            response_style=response_style,
        )
        raw = call_openai_compatible_llm(
            llm_model,
            system_prompt,
            user_prompt,
            feature_code="hermes_answer_synthesis",
            feature_label="Hermes 回答合成",
            tenant_slug=tenant_slug,
            entry_point="hermes_query",
            metadata={"intent": plan.get("intent"), "tool_count": len(plan.get("tools") or []), "response_style": response_style},
            request_timeout_seconds=40,
        )
        parsed = _extract_json_payload_from_llm_text(raw, {}, strict=True)
        answer = str(parsed.get("answer") or "").strip()
        summary = str(parsed.get("summary") or "").strip()[:240]
        if not answer:
            raise RuntimeError("hermes_answer_synthesis_empty_answer")
        bullets = [str(item).strip() for item in (parsed.get("bullets") if isinstance(parsed.get("bullets"), list) else []) if str(item).strip()][:6]
        citations = [str(item).strip() for item in (parsed.get("citations") if isinstance(parsed.get("citations"), list) else []) if str(item).strip()][:8]
        analysis_sections = []
        for item in (parsed.get("analysis_sections") if isinstance(parsed.get("analysis_sections"), list) else []):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            body = str(item.get("body") or "").strip()
            if title and body:
                analysis_sections.append({"title": title[:80], "body": body[:600]})
        return {
            "answer": answer,
            "summary": summary,
            "lead_conclusion": str(parsed.get("lead_conclusion") or "").strip()[:240],
            "bullets": bullets,
            "analysis_sections": analysis_sections[:8],
            "next_steps": [str(item).strip() for item in (parsed.get("next_steps") if isinstance(parsed.get("next_steps"), list) else []) if str(item).strip()][:6],
            "confidence": str(parsed.get("confidence") or "").strip()[:20],
            "citations": citations,
        }, llm_model, "llm_synthesized"
    except RuntimeError:
        raise
    except Exception as exc:
        app.logger.exception("Failed to synthesize Hermes answer")
        raise RuntimeError(f"hermes_answer_synthesis_llm_failed:{str(exc)[:240]}") from exc


def build_hermes_query_response(body):
    payload = body if isinstance(body, dict) else {}
    tenant_slug = str(payload.get("tenant_slug") or request.args.get("tenant") or get_default_tenant_slug()).strip().lower()
    user_role = str(payload.get("user_role") or "").strip().lower() or str((get_current_demo_profile() or {}).get("role") or "").strip().lower()
    site_config = get_site_config()
    if not is_hermes_available_for_role(user_role, site_config):
        if is_feature_enabled("hermes", site_config):
            raise ValueError("hermes_investor_access_disabled")
        raise ValueError("hermes_disabled")
    hermes_scope_guard_enabled = is_hermes_scope_guard_enabled(site_config)
    hermes_settings = get_hermes_settings(site_config)
    selected_knowledge_ids = payload.get("selected_knowledge_ids") if isinstance(payload.get("selected_knowledge_ids"), list) else []
    attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
    preferred_mode = str(payload.get("preferred_mode") or "").strip().lower()
    # Internet search is intentionally not part of the current Hermes
    # product surface. Keep this server-side guard so stale clients cannot
    # re-enable it by posting web_answer=true.
    web_answer = False
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
            tenant_slug=runtime.get("tenant_slug") or "",
            preferred_mode=runtime.get("preferred_mode") or "",
        ) if runtime.get("scope_guard_enabled") else build_hermes_open_scope_result(
            question_text=runtime.get("question_text") or "",
            selected_knowledge_ids=runtime.get("selected_knowledge_ids") or [],
            attachments=runtime.get("attachments") or [],
            tenant_slug=runtime.get("tenant_slug") or "",
            preferred_mode=runtime.get("preferred_mode") or "",
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
            "detail": "当前未启用 Hermes 提示词范围约束，本轮跳过固定范围拦截。 " if not runtime.get("scope_guard_enabled") else detail_map.get(scope_status, "已完成范围识别。"),
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
            scope_guard_enabled=bool(runtime.get("scope_guard_enabled", True)),
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
        missing_capability = detect_hermes_missing_capability(
            runtime.get("question_text") or "",
            plan=state.get("intent_plan") or {},
            tool_outputs=state.get("tool_outputs") or {},
        )
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
            response_style=runtime.get("default_response_style") or "structured",
        )
        return {
            "detail": "已完成答案合成。",
            "state_updates": {
                "synthesis": synthesis,
                "answer_model": answer_model,
                "answer_mode": answer_mode,
                "missing_capability": missing_capability,
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
        missing_capability = state.get("missing_capability") if isinstance(state.get("missing_capability"), dict) else {}
        if missing_capability:
            artifacts = [
                build_hermes_text_artifact(
                    question_text=runtime.get("question_text") or "",
                    plan=intent_plan,
                    synthesis=synthesis,
                    tool_outputs=tool_outputs,
                    citations=citations,
                )
            ]
        response_display_mode = "structured" if any(
            str((item or {}).get("type") or "").strip() in {"watchlist_analysis", "indicator_analysis"}
            for item in artifacts
        ) and not missing_capability else "text"
        result = {
            "ok": True,
            "question": runtime.get("question_text") or "",
            "tenant_slug": runtime.get("tenant_slug") or "",
            "session_id": runtime.get("session_id") or "",
            "intent": intent_plan.get("intent"),
            "task_family": intent_plan.get("task_family") or "research_qa",
            "capability_label": intent_plan.get("capability_label") or "研究问答",
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
            "missing_capability": copy.deepcopy(missing_capability) if missing_capability else None,
            "source_policy": {
                "knowledge_first": False,
                "intent_routing": "llm_only",
                "embedding_query_enabled": False,
                "web_supplement_enabled": bool(runtime.get("web_answer")),
                "global_web_enabled": hermes_settings.get("internet_answer_enabled") is True,
            },
            "route_priority": copy.deepcopy(hermes_settings.get("route_priority") or []),
            "template_tree": copy.deepcopy(hermes_settings.get("template_tree") or {}),
            "intent_tree": copy.deepcopy(hermes_settings.get("intent_tree") or []),
            "settings_snapshot": {
                "prompt_scope_guard_enabled": hermes_settings.get("prompt_scope_guard_enabled") is True,
                "internet_answer_enabled": hermes_settings.get("internet_answer_enabled") is True,
                "thinking_process_enabled": hermes_settings.get("thinking_process_enabled") is True,
                "answer_save_to_knowledge_enabled": hermes_settings.get("answer_save_to_knowledge_enabled") is True,
                "default_response_style": hermes_settings.get("default_response_style") or "structured",
                "chart_types_enabled": copy.deepcopy(hermes_settings.get("chart_types_enabled") or []),
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
                "intent_group": intent_plan.get("intent_group") or "",
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
            "scope_guard_enabled": hermes_scope_guard_enabled,
            "default_response_style": hermes_settings.get("default_response_style") or "structured",
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
    transcript_model = (
        transcription_cfg.get("local_model_size")
        if transcript_engine == "local"
        else transcription_cfg.get("api_model")
    )
    raw_transcript = str(transcript or "").strip()
    if use_llm_enhancement and not raw_transcript:
        raise RuntimeError("review_voice_transcript_empty")
    cleaned_transcript = raw_transcript
    cleanup_mode = "none"
    cleanup_steps = []
    if raw_transcript and transcription_cfg.get("post_process_mode") == "rule_based":
        cleaned_transcript = _apply_voice_transcript_rule_cleanup(
            raw_transcript,
            domain_glossary_enabled=transcription_cfg.get("domain_glossary_enabled", True),
        )
        if cleaned_transcript:
            cleanup_mode = "rule_based"
            cleanup_steps = ["punctuation_normalize", "finance_term_normalize"]
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
        llm_result = enhance_review_voice_transcript_with_llm(
            cleaned_transcript or raw_transcript,
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
    elif cleaned_transcript and cleaned_transcript != raw_transcript:
        llm_notice = "已完成基础转写，并做术语纠错与规则清洗。"
    return {
        "transcript": raw_transcript,
        "display_transcript": enhanced_transcript or cleaned_transcript or raw_transcript,
        "raw_transcript": raw_transcript,
        "cleaned_transcript": cleaned_transcript,
        "enhanced_transcript": enhanced_transcript,
        "transcript_engine": transcript_engine,
        "transcript_model": transcript_model,
        "post_process_mode": cleanup_mode,
        "post_process_steps": cleanup_steps,
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


def _build_review_evidence_query_text(review_text="", review_title=""):
    title_text = re.sub(r"^(日复盘|周复盘|月复盘)\s*[:：-]?\s*", "", str(review_title or "").strip())
    def _split_review_sentences(text):
        raw = str(text or "").replace("\r", "\n")
        parts = re.split(r"[\n。！？；;]+", raw)
        return [part.strip(" \t-•*") for part in parts if str(part or "").strip(" \t-•*")]
    parts = []
    if title_text:
        parts.append(title_text)
    for sentence in _split_review_sentences(review_text):
        cleaned = str(sentence or "").strip()
        if not cleaned:
            continue
        next_text = "；".join(parts + [cleaned]) if parts else cleaned
        if len(next_text) > 240:
            break
        parts.append(cleaned)
        if len(parts) >= 4:
            break
    query_text = "；".join(part for part in parts if part).strip()
    if query_text:
        return query_text[:240]
    fallback = str(review_text or "").replace("\n", " ").strip()
    return fallback[:240]


def _summarize_review_evidence_chain_fallback(knowledge_items, web_matches):
    knowledge_count = len(knowledge_items)
    web_count = len(web_matches)
    if not knowledge_count and not web_count:
        return "暂无匹配的证据链"
    if knowledge_count and web_count:
        return f"已基于用户复盘命中 {knowledge_count} 条知识库证据，并补充 {web_count} 条互联网公开信息。"
    if knowledge_count:
        return f"已基于用户复盘命中 {knowledge_count} 条知识库证据。"
    return f"当前知识库未命中，已补充 {web_count} 条互联网公开信息。"


def build_review_evidence_chain_section(review_text="", tenant_slug="", review_title="", entry_point="review_publish"):
    normalized_text = str(review_text or "").strip()
    query_text = _build_review_evidence_query_text(normalized_text, review_title=review_title)
    empty_payload = {
        "status": "empty",
        "query_text": query_text,
        "summary": "暂无匹配的证据链",
        "items": [],
        "knowledge_match_count": 0,
        "web_match_count": 0,
        "llm_model": None,
    }
    if not query_text:
        return empty_payload

    knowledge_result = build_evidence_chain_response(
        tenant_slug=tenant_slug,
        query_text=query_text,
        limit=4,
        submit_to_model=True,
        source_types=["knowledge"],
        entry_point=entry_point,
        feature_namespace="review_evidence_chain",
    )
    try:
        web_result = hermes_tool_web_search(query_text, limit=4)
    except Exception as exc:
        app.logger.exception("Review evidence web search failed")
        raise RuntimeError(f"review_evidence_web_search_failed:{str(exc)[:240]}") from exc

    knowledge_items = [copy.deepcopy(item) for item in ((knowledge_result.get("evidence_items") or []) if isinstance(knowledge_result, dict) else []) if isinstance(item, dict)]
    web_matches = [copy.deepcopy(item) for item in ((web_result.get("matches") or []) if isinstance(web_result, dict) else []) if isinstance(item, dict)]
    if not knowledge_items and not web_matches:
        return empty_payload

    llm_model = copy.deepcopy((knowledge_result.get("llm_model") or {}) if isinstance(knowledge_result, dict) else {}) or None
    items = []
    for index, item in enumerate(knowledge_items[:4], start=1):
        items.append({
            "id": str(item.get("evidence_id") or item.get("id") or f"knowledge_{index}").strip() or f"knowledge_{index}",
            "kind": "knowledge",
            "title": str(item.get("title") or "知识库证据").strip()[:180] or "知识库证据",
            "summary": str(item.get("summary") or item.get("body") or item.get("raw_input") or "暂无摘要").strip()[:320],
            "source_label": str(item.get("source_label") or "知识库").strip()[:80] or "知识库",
            "source_detail": sanitize_user_facing_source_text(item.get("source_detail") or item.get("source") or "")[:240],
            "published_at": "",
            "link": str(item.get("url") or "").strip()[:500],
            "score": float(item.get("score") or 0.0),
        })
    for index, item in enumerate(web_matches[:4], start=1):
        items.append({
            "id": f"web_{index}",
            "kind": "web",
            "title": str(item.get("title") or "互联网公开信息").strip()[:180] or "互联网公开信息",
            "summary": str(item.get("summary") or item.get("published_at") or "暂无摘要").strip()[:320],
            "source_label": "互联网公开信息",
            "source_detail": str(item.get("source") or "Google News RSS").strip()[:120] or "Google News RSS",
            "published_at": str(item.get("published_at") or "").strip()[:120],
            "link": str(item.get("link") or "").strip()[:500],
            "score": 0.0,
        })

    summary = _summarize_review_evidence_chain_fallback(knowledge_items, web_matches)
    synthesis_model = get_default_llm_config(purpose="general", feature_code="review_evidence_chain_synthesis")
    if not synthesis_model:
        raise RuntimeError("review_evidence_chain_synthesis_llm_not_configured")
    if items:
        evidence_blocks = []
        for idx, item in enumerate(items[:6], start=1):
            evidence_blocks.append(
                "\n".join([
                    f"[命中 {idx}] 类型：{item.get('source_label') or item.get('kind')}",
                    f"[命中 {idx}] 标题：{item.get('title') or '未命名命中'}",
                    f"[命中 {idx}] 摘要：{item.get('summary') or '暂无摘要'}",
                    f"[命中 {idx}] 来源：{item.get('source_detail') or ''}",
                    f"[命中 {idx}] 时间：{item.get('published_at') or ''}",
                ])
            )
        try:
            summary = call_openai_compatible_llm(
                synthesis_model,
                "你是复盘证据链整理助手。请基于用户正文和命中证据，输出一句简洁的中文总结。"
                "如果证据与正文关联弱，要明确说“暂无充分匹配证据”。不要编造。",
                (
                    f"用户复盘正文：\n{normalized_text[:1500] or '暂无正文'}\n\n"
                    f"证据命中：\n{chr(10).join(evidence_blocks)}\n\n"
                    "请只输出 1 到 2 句总结。"
                ),
                feature_code="review_evidence_chain_synthesis",
                feature_label="复盘证据链总结",
                tenant_slug=tenant_slug,
                entry_point=entry_point,
                metadata={
                    "knowledge_match_count": len(knowledge_items),
                    "web_match_count": len(web_matches),
                },
                request_timeout_seconds=25,
            ).strip()
            if not summary:
                raise RuntimeError("review_evidence_chain_synthesis_empty_llm_response")
            llm_model = {
                "key": synthesis_model.get("key"),
                "label": synthesis_model.get("label"),
                "provider": synthesis_model.get("provider"),
                "model_name": synthesis_model.get("model_name"),
                "purpose": synthesis_model.get("purpose"),
            }
        except Exception as exc:
            app.logger.exception("Review evidence chain synthesis failed")
            raise RuntimeError(f"review_evidence_chain_synthesis_llm_failed:{str(exc)[:240]}") from exc

    summary = str(summary or "").strip() or "暂无匹配的证据链"
    if "暂无" in summary and not knowledge_items and not web_matches:
        return empty_payload
    return {
        "status": "matched" if items else "empty",
        "query_text": query_text,
        "summary": summary[:320],
        "items": items[:8],
        "knowledge_match_count": len(knowledge_items),
        "web_match_count": len(web_matches),
        "llm_model": llm_model,
    }


def persist_review_publish_snapshot(
    tenant_slug,
    text,
    review_period="",
    review_title="",
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
    explicit_title = str(review_title or "").strip()
    title_source_text = str(
        normalized_user_input_section.get("display_text")
        or normalized_user_input_section.get("polished_text")
        or polished_input_text
        or cleaned_text
        or ""
    ).strip()
    title_seed = re.split(r"[。！？\n]", title_source_text, 1)[0].strip() if title_source_text else ""
    title = explicit_title or f"{period_label}：{title_seed or '最新复盘已发布'}"
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
    evidence_chain_section = build_review_evidence_chain_section(
        review_text=title_source_text or cleaned_text,
        tenant_slug=tenant_slug,
        review_title=explicit_title or title,
        entry_point="review_publish",
    )
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
        "evidence_chain_section": evidence_chain_section,
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
