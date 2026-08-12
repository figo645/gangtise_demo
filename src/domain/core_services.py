from src.runtime import *
from src.domain.agent_workflows import *


def _market_services_module():
    from src.domain import market_services

    return market_services


def _ai_services_module():
    from src.domain import ai_services

    return ai_services


# Split app.py into domain modules after the fact means some legacy helpers still
# cross-call market/AI functions by bare name. Keep these as lazy shims so we do
# not reintroduce top-level circular imports.
def build_indicator_hub(*args, **kwargs):
    return _market_services_module().build_indicator_hub(*args, **kwargs)


def normalize_selected_indicator_refs(*args, **kwargs):
    return _market_services_module().normalize_selected_indicator_refs(*args, **kwargs)


def generate_smart_indicator_js(*args, **kwargs):
    return _market_services_module().generate_smart_indicator_js(*args, **kwargs)


def validate_smart_indicator_js(*args, **kwargs):
    return _market_services_module().validate_smart_indicator_js(*args, **kwargs)


def evaluate_smart_indicator_formula_js(*args, **kwargs):
    return _market_services_module().evaluate_smart_indicator_formula_js(*args, **kwargs)


def save_indicator_definition(*args, **kwargs):
    return _market_services_module().save_indicator_definition(*args, **kwargs)


def get_indicator_definition(*args, **kwargs):
    return _market_services_module().get_indicator_definition(*args, **kwargs)


def invalidate_indicator_hub_cache(*args, **kwargs):
    return _market_services_module().invalidate_indicator_hub_cache(*args, **kwargs)


def execute_indicator_source_landing(*args, **kwargs):
    return _market_services_module().execute_indicator_source_landing(*args, **kwargs)


def prepare_indicator_hub_store(*args, **kwargs):
    return _market_services_module().prepare_indicator_hub_store(*args, **kwargs)


def parse_task_interval_seconds(*args, **kwargs):
    return _market_services_module().parse_task_interval_seconds(*args, **kwargs)


def normalize_admin_task_config(*args, **kwargs):
    return _market_services_module().normalize_admin_task_config(*args, **kwargs)


def run_indicator_clean_job(*args, **kwargs):
    return _market_services_module().run_indicator_clean_job(*args, **kwargs)


def seed_mock_indicator_lake(*args, **kwargs):
    return _market_services_module().seed_mock_indicator_lake(*args, **kwargs)


def sync_real_indicator_history_from_market_cache(*args, **kwargs):
    return _market_services_module().sync_real_indicator_history_from_market_cache(*args, **kwargs)


def gen_watchlist_details(*args, **kwargs):
    return _market_services_module().gen_watchlist_details(*args, **kwargs)


def get_watchlist_detail_by_code(*args, **kwargs):
    return _market_services_module().get_watchlist_detail_by_code(*args, **kwargs)


def search_watchlist_candidates(*args, **kwargs):
    return _market_services_module().search_watchlist_candidates(*args, **kwargs)


def list_watchlist_kline_annotations(*args, **kwargs):
    return _market_services_module().list_watchlist_kline_annotations(*args, **kwargs)


def save_watchlist_kline_annotation(*args, **kwargs):
    return _market_services_module().save_watchlist_kline_annotation(*args, **kwargs)


def delete_watchlist_kline_annotation(*args, **kwargs):
    return _market_services_module().delete_watchlist_kline_annotation(*args, **kwargs)


def build_watchlist_annotation_context(*args, **kwargs):
    return _market_services_module().build_watchlist_annotation_context(*args, **kwargs)


def list_watchlist_comments(*args, **kwargs):
    return _market_services_module().list_watchlist_comments(*args, **kwargs)


def save_watchlist_comment(*args, **kwargs):
    return _market_services_module().save_watchlist_comment(*args, **kwargs)


def delete_watchlist_comment(*args, **kwargs):
    return _market_services_module().delete_watchlist_comment(*args, **kwargs)


def build_watchlist_comment_analytics(*args, **kwargs):
    return _market_services_module().build_watchlist_comment_analytics(*args, **kwargs)


def label_watchlist_comment_with_llm(*args, **kwargs):
    return _ai_services_module().label_watchlist_comment_with_llm(*args, **kwargs)


def build_simulated_indicator_kline(*args, **kwargs):
    return _market_services_module().build_simulated_indicator_kline(*args, **kwargs)


def NumberLike(*args, **kwargs):
    return _market_services_module().NumberLike(*args, **kwargs)


def get_default_llm_config(*args, **kwargs):
    return _ai_services_module().get_default_llm_config(*args, **kwargs)


def call_openai_compatible_llm(*args, **kwargs):
    return _ai_services_module().call_openai_compatible_llm(*args, **kwargs)


def build_knowledge_query_response(*args, **kwargs):
    return _ai_services_module().build_knowledge_query_response(*args, **kwargs)


def generate_review_draft_with_llm(*args, **kwargs):
    return _ai_services_module().generate_review_draft_with_llm(*args, **kwargs)


def polish_review_input_with_llm(*args, **kwargs):
    return _ai_services_module().polish_review_input_with_llm(*args, **kwargs)


def compose_review_draft_with_llm(*args, **kwargs):
    return _ai_services_module().compose_review_draft_with_llm(*args, **kwargs)


def analyze_review_watchlist_with_llm(*args, **kwargs):
    return _ai_services_module().analyze_review_watchlist_with_llm(*args, **kwargs)


def compose_review_structured_preview(*args, **kwargs):
    return _ai_services_module().compose_review_structured_preview(*args, **kwargs)


def process_review_publish_text(*args, **kwargs):
    return _ai_services_module().process_review_publish_text(*args, **kwargs)


def persist_review_publish_snapshot(*args, **kwargs):
    return _ai_services_module().persist_review_publish_snapshot(*args, **kwargs)


def save_manual_knowledge_entry(*args, **kwargs):
    return _ai_services_module().save_manual_knowledge_entry(*args, **kwargs)


def process_review_voice_upload(*args, **kwargs):
    return _ai_services_module().process_review_voice_upload(*args, **kwargs)

def normalize_llm_model_config(source, index=0):
    raw = source if isinstance(source, dict) else {}
    key = str(raw.get("key") or f"model_{index + 1}").strip() or f"model_{index + 1}"
    purpose = str(raw.get("purpose") or "general").strip().lower() or "general"
    return {
        "key": key,
        "label": str(raw.get("label") or key).strip() or key,
        "provider": str(raw.get("provider") or "openai").strip() or "openai",
        "model_name": str(raw.get("model_name") or "").strip(),
        "base_url": str(raw.get("base_url") or "").strip(),
        "api_key": str(raw.get("api_key") or "").strip(),
        "purpose": purpose,
        "enabled": bool(raw.get("enabled", True)),
    }


def normalize_llm_registry_config(source=None):
    raw = source if isinstance(source, dict) else {}
    items = raw.get("models") if isinstance(raw.get("models"), list) else []
    builtin_items = DEFAULT_LLM_MODELS if isinstance(DEFAULT_LLM_MODELS, list) else []
    combined_items = []
    seen_builtin_keys = set()
    for item in items:
        if isinstance(item, dict):
            combined_items.append(item)
    existing_keys = {
        str(item.get("key") or "").strip()
        for item in combined_items
        if isinstance(item, dict) and str(item.get("key") or "").strip()
    }
    for item in builtin_items:
        if not isinstance(item, dict):
            continue
        builtin_key = str(item.get("key") or "").strip()
        if not builtin_key or builtin_key in existing_keys or builtin_key in seen_builtin_keys:
            continue
        combined_items.append(copy.deepcopy(item))
        seen_builtin_keys.add(builtin_key)
    models = []
    for index, item in enumerate(combined_items[:40]):
        if not isinstance(item, dict):
            continue
        models.append(normalize_llm_model_config(item, index=index))
    default_model_key = str(raw.get("default_model_key") or "").strip()
    if default_model_key and not any(model["key"] == default_model_key for model in models):
        default_model_key = ""
    if not default_model_key and models:
        general_models = [model for model in models if model.get("purpose") == "general" and model.get("enabled")]
        default_model_key = (general_models[0] if general_models else models[0]).get("key") or ""
    feature_model_keys = {}
    raw_feature_model_keys = raw.get("feature_model_keys") if isinstance(raw.get("feature_model_keys"), dict) else {}
    valid_keys = {model["key"] for model in models}
    for feature_code, model_key in raw_feature_model_keys.items():
        feature_code_text = str(feature_code or "").strip()
        model_key_text = str(model_key or "").strip()
        if feature_code_text and model_key_text and model_key_text in valid_keys:
            feature_model_keys[feature_code_text] = model_key_text
    return {
        "default_model_key": default_model_key,
        "models": models,
        "feature_model_keys": feature_model_keys,
    }


def normalize_auth_settings_config(source=None):
    raw = source if isinstance(source, dict) else {}
    defaults = copy.deepcopy(DEFAULT_SITE_CONFIG["auth_settings"])
    wechat_raw = raw.get("wechat") if isinstance(raw.get("wechat"), dict) else {}
    wechat_defaults = defaults.get("wechat") or {}
    default_role = str(wechat_raw.get("default_role") or wechat_defaults.get("default_role") or "investor").strip().lower() or "investor"
    if default_role not in {"investor", "dav"}:
        default_role = "investor"
    return {
        "password_login_enabled": bool(raw.get("password_login_enabled", defaults.get("password_login_enabled", True))),
        "wechat_login_enabled": bool(raw.get("wechat_login_enabled", defaults.get("wechat_login_enabled", False))),
        "quick_select_enabled": bool(raw.get("quick_select_enabled", defaults.get("quick_select_enabled", True))),
        "wechat_runtime_test_enabled": bool(raw.get("wechat_runtime_test_enabled", defaults.get("wechat_runtime_test_enabled", True))),
        "wechat": {
            "app_id": str(wechat_raw.get("app_id") or wechat_defaults.get("app_id") or "").strip(),
            "app_secret": str(wechat_raw.get("app_secret") or "").strip(),
            "redirect_uri": str(wechat_raw.get("redirect_uri") or wechat_defaults.get("redirect_uri") or "").strip(),
            "scope": str(wechat_raw.get("scope") or wechat_defaults.get("scope") or "snsapi_userinfo").strip() or "snsapi_userinfo",
            "auto_register_enabled": bool(wechat_raw.get("auto_register_enabled", wechat_defaults.get("auto_register_enabled", False))),
            "default_role": default_role,
            "default_tenant_slug": str(wechat_raw.get("default_tenant_slug") or wechat_defaults.get("default_tenant_slug") or "").strip().lower(),
            "default_advisor_name": str(wechat_raw.get("default_advisor_name") or wechat_defaults.get("default_advisor_name") or "").strip(),
        },
    }


def normalize_knowledge_ingestion_config(source=None):
    raw = source if isinstance(source, dict) else {}
    return {
        "user_preview_enabled": bool(raw.get("user_preview_enabled", False)),
    }


def normalize_hermes_settings_config(source=None):
    raw = source if isinstance(source, dict) else {}
    defaults = copy.deepcopy(DEFAULT_SITE_CONFIG["hermes_settings"])
    default_intent_tree = copy.deepcopy(defaults.get("intent_tree") or [])
    default_template_tree = copy.deepcopy(defaults.get("template_tree") or {})
    default_route_priority = list(defaults.get("route_priority") or [])
    default_chart_types = list(defaults.get("chart_types_enabled") or [])

    def _normalize_tree_items(items, fallback_items):
        fallback_map = {
            str(item.get("id") or "").strip(): copy.deepcopy(item)
            for item in (fallback_items if isinstance(fallback_items, list) else [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        normalized = []
        source_items = items if isinstance(items, list) and items else list(fallback_map.values())
        seen = set()
        for item in source_items:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            if not item_id or item_id in seen:
                continue
            base = copy.deepcopy(fallback_map.get(item_id) or {})
            merged = {**base, **copy.deepcopy(item)}
            merged["id"] = item_id
            merged["label"] = str(merged.get("label") or base.get("label") or item_id).strip() or item_id
            if "group" in merged:
                merged["group"] = str(merged.get("group") or base.get("group") or "").strip()
            if "display_mode" in merged:
                merged["display_mode"] = str(merged.get("display_mode") or base.get("display_mode") or "text").strip() or "text"
            for key in ["enabled", "allow_knowledge", "allow_web", "allow_files", "allow_chart"]:
                if key in merged:
                    merged[key] = bool(merged.get(key, base.get(key, False)))
            normalized.append(merged)
            seen.add(item_id)
        for item_id, base in fallback_map.items():
            if item_id not in seen:
                normalized.append(copy.deepcopy(base))
        return normalized

    template_tree = {}
    raw_template_tree = raw.get("template_tree") if isinstance(raw.get("template_tree"), dict) else {}
    for group_key, fallback_items in default_template_tree.items():
        template_tree[group_key] = _normalize_tree_items(raw_template_tree.get(group_key), fallback_items)

    route_priority = []
    for item in raw.get("route_priority") if isinstance(raw.get("route_priority"), list) else default_route_priority:
        value = str(item or "").strip()
        if value and value not in route_priority:
            route_priority.append(value)
    if not route_priority:
        route_priority = default_route_priority

    chart_types_enabled = []
    for item in raw.get("chart_types_enabled") if isinstance(raw.get("chart_types_enabled"), list) else default_chart_types:
        value = str(item or "").strip()
        if value and value not in chart_types_enabled:
            chart_types_enabled.append(value)
    if not chart_types_enabled:
        chart_types_enabled = default_chart_types

    return {
        "prompt_scope_guard_enabled": bool(raw.get("prompt_scope_guard_enabled", defaults["prompt_scope_guard_enabled"])),
        "investor_access_enabled": bool(raw.get("investor_access_enabled", defaults["investor_access_enabled"])),
        "dav_access_enabled": bool(raw.get("dav_access_enabled", defaults.get("dav_access_enabled", True))),
        "internet_answer_enabled": bool(raw.get("internet_answer_enabled", defaults.get("internet_answer_enabled", True))),
        "thinking_process_enabled": bool(raw.get("thinking_process_enabled", defaults.get("thinking_process_enabled", True))),
        "answer_save_to_knowledge_enabled": bool(raw.get("answer_save_to_knowledge_enabled", defaults.get("answer_save_to_knowledge_enabled", True))),
        "default_response_style": str(raw.get("default_response_style") or defaults.get("default_response_style") or "structured").strip() or "structured",
        "chart_types_enabled": chart_types_enabled,
        "route_priority": route_priority,
        "intent_tree": _normalize_tree_items(raw.get("intent_tree"), default_intent_tree),
        "template_tree": template_tree,
    }


def normalize_evidence_chain_config(source=None):
    raw = source if isinstance(source, dict) else {}
    defaults = copy.deepcopy(DEFAULT_SITE_CONFIG["evidence_chain"])
    return {
        "filter_prompt_system": str(raw.get("filter_prompt_system") or defaults["filter_prompt_system"]).strip()[:8000] or defaults["filter_prompt_system"],
        "filter_prompt_user_template": str(raw.get("filter_prompt_user_template") or defaults["filter_prompt_user_template"]).strip()[:12000] or defaults["filter_prompt_user_template"],
        "filter_timeout_seconds": max(5, min(int(raw.get("filter_timeout_seconds") or defaults["filter_timeout_seconds"]), 120)),
        "answer_timeout_seconds": max(5, min(int(raw.get("answer_timeout_seconds") or defaults["answer_timeout_seconds"]), 180)),
    }


def normalize_review_generation_config(source=None):
    raw = source if isinstance(source, dict) else {}
    defaults = copy.deepcopy(DEFAULT_SITE_CONFIG["review_generation"])
    return {
        "polish_system_prompt": str(raw.get("polish_system_prompt") or defaults["polish_system_prompt"]).strip()[:8000] or defaults["polish_system_prompt"],
        "polish_user_template": str(raw.get("polish_user_template") or defaults["polish_user_template"]).strip()[:12000] or defaults["polish_user_template"],
        "compose_system_prompt": str(raw.get("compose_system_prompt") or defaults["compose_system_prompt"]).strip()[:8000] or defaults["compose_system_prompt"],
        "compose_user_template": str(raw.get("compose_user_template") or defaults["compose_user_template"]).strip()[:16000] or defaults["compose_user_template"],
        "polish_timeout_seconds": max(5, min(int(raw.get("polish_timeout_seconds") or defaults["polish_timeout_seconds"]), 180)),
        "compose_timeout_seconds": max(5, min(int(raw.get("compose_timeout_seconds") or defaults["compose_timeout_seconds"]), 240)),
    }


def normalize_knowledge_processing_mode(value, skip_ai_processing=None):
    mode = str(value or "").strip().lower()
    if mode in {"none", "algorithm", "llm"}:
        return mode
    if skip_ai_processing is not None:
        return "none" if bool(skip_ai_processing) else "llm"
    return "algorithm"


def _split_semantic_sentences(text):
    raw = str(text or "").replace("\r", "\n")
    parts = re.split(r"[\n。！？；;]+", raw)
    return [part.strip(" \t-•*") for part in parts if str(part or "").strip(" \t-•*")]


def build_algorithmic_knowledge_processing(raw_text, source_type="", title="", source_detail=""):
    text = str(raw_text or "").strip()
    sentences = _split_semantic_sentences(text)
    if not sentences and text:
        sentences = [text]
    summary = "；".join(sentences[:3])[:220] if sentences else "暂无可提炼摘要。"
    key_points = sentences[:3] or ["待补充关键要点"]
    evidence = [item for item in sentences[3:6] if item] or key_points[:1]
    validation_nodes = []
    risk_points = []
    for item in sentences:
      if any(token in item for token in ("验证", "跟踪", "关注", "观察", "确认")) and len(validation_nodes) < 3:
        validation_nodes.append(item)
      if any(token in item for token in ("风险", "不确定", "波动", "警惕", "边界")) and len(risk_points) < 3:
        risk_points.append(item)
    if not validation_nodes:
        validation_nodes = ["继续跟踪数据兑现、时间节点和市场反馈。"]
    if not risk_points:
        risk_points = ["需结合后续事实验证，避免把单次素材直接当成结论。"]
    structured_sections = [
        f"标题：{str(title or '未命名知识').strip() or '未命名知识'}",
        f"来源：{str(source_detail or source_type or '原始输入').strip() or '原始输入'}",
        f"核心结论：{summary}",
        "关键要点：\n" + "\n".join(f"{index + 1}. {item}" for index, item in enumerate(key_points)),
        "证据与上下文：\n" + "\n".join(f"{index + 1}. {item}" for index, item in enumerate(evidence)),
        "验证节点：\n" + "\n".join(f"{index + 1}. {item}" for index, item in enumerate(validation_nodes[:3])),
        "风险边界：\n" + "\n".join(f"{index + 1}. {item}" for index, item in enumerate(risk_points[:3])),
    ]
    rendered_text = "\n\n".join(structured_sections).strip()
    return {
        "mode": "algorithm",
        "label": "算法加工",
        "summary": summary,
        "key_points": key_points,
        "validation_nodes": validation_nodes[:3],
        "risk_points": risk_points[:3],
        "template_name": "semantic_outline_v1",
        "rendered_text": rendered_text,
    }


def build_llm_knowledge_processing(raw_text, source_type="", title="", source_detail=""):
    workflow_definition = build_default_knowledge_processing_workflow_definition()

    def _knowledge_processing_input_executor(state, runtime, node, upstream):
        safe_text = str(runtime.get("raw_text") or "").strip()
        if not safe_text:
            raise ValueError("knowledge_body_required")
        return {
            "detail": "已接收原始知识材料。",
            "state_updates": {
                "safe_text": safe_text,
                "safe_title": str(runtime.get("title") or "未命名知识").strip() or "未命名知识",
                "safe_source": str(runtime.get("source_detail") or runtime.get("source_type") or "原始输入").strip() or "原始输入",
            },
            "context_preview": {
                "source_type": str(runtime.get("source_type") or "").strip() or "manual",
                "input_chars": len(safe_text),
            },
        }

    def _knowledge_processing_prepare_executor(state, runtime, node, upstream):
        system_prompt = (
            "你是知识加工助手。"
            "请把原始材料加工成适合大V知识库沉淀的结构化内容。"
            "输出必须使用中文，简洁、专业、避免编造。"
        )
        user_prompt = (
            f"知识标题：{state.get('safe_title') or '未命名知识'}\n"
            f"来源：{state.get('safe_source') or '原始输入'}\n"
            f"原始材料：\n{state.get('safe_text') or '暂无原始材料'}\n\n"
            "请严格按下面模板输出：\n"
            "一、核心结论\n"
            "二、关键要点（3条以内）\n"
            "三、验证节点（3条以内）\n"
            "四、风险边界（3条以内）\n"
            "五、可直接入库正文"
        )
        return {
            "detail": "已生成知识加工提示词。",
            "state_updates": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            },
            "context_preview": {"prompt_chars": len(user_prompt)},
        }

    def _knowledge_processing_llm_executor(state, runtime, node, upstream):
        llm_model = get_default_llm_config(purpose="general", feature_code="knowledge_processing_llm")
        if not llm_model:
            raise RuntimeError("knowledge_processing_llm_not_configured")
        rendered_text = call_openai_compatible_llm(
            llm_model,
            state.get("system_prompt") or "",
            state.get("user_prompt") or "",
            feature_code="knowledge_processing_llm",
            feature_label="知识加工生成",
            entry_point="knowledge_processing",
            metadata={
                "source_type": str(runtime.get("source_type") or "").strip(),
                "title": str(state.get("safe_title") or "").strip()[:80],
                "workflow_id": workflow_definition["id"],
            },
        )
        return {
            "detail": "大模型已完成知识加工。",
            "state_updates": {
                "rendered_text": rendered_text,
                "llm_model": {
                    "key": llm_model.get("key"),
                    "label": llm_model.get("label"),
                    "model_name": llm_model.get("model_name"),
                    "provider": llm_model.get("provider"),
                },
            },
            "context_preview": {"output_chars": len(str(rendered_text or ""))},
        }

    def _knowledge_processing_output_executor(state, runtime, node, upstream):
        rendered_text = str(state.get("rendered_text") or "").strip()
        sections = _split_semantic_sentences(rendered_text)
        summary = "；".join(sections[:3])[:220] if sections else (rendered_text[:220] if rendered_text else "暂无摘要")
        return {
            "detail": "已封装知识加工结果。",
            "state_updates": {
                "final_result": {
                    "mode": "llm",
                    "label": "大模型加工",
                    "summary": summary,
                    "key_points": sections[:3] or ["待补充关键要点"],
                    "validation_nodes": [item for item in sections if any(token in item for token in ("验证", "跟踪", "观察", "确认"))][:3] or ["待补充验证节点"],
                    "risk_points": [item for item in sections if any(token in item for token in ("风险", "边界", "不确定", "警惕"))][:3] or ["待补充风险边界"],
                    "template_name": "llm_outline_v1",
                    "rendered_text": rendered_text,
                    "llm_model": copy.deepcopy(state.get("llm_model") or {}),
                }
            },
            "context_preview": {"has_text": bool(rendered_text)},
        }

    execution = run_declared_agent_workflow(
        workflow_definition,
        runtime={
            "raw_text": raw_text,
            "source_type": source_type,
            "title": title,
            "source_detail": source_detail,
        },
        executor_registry={
            "knowledge_processing_input": _knowledge_processing_input_executor,
            "knowledge_processing_prepare": _knowledge_processing_prepare_executor,
            "knowledge_processing_llm": _knowledge_processing_llm_executor,
            "knowledge_processing_output": _knowledge_processing_output_executor,
        },
    )
    final_result = copy.deepcopy(execution["state"].get("final_result") or {})
    final_result["workflow_meta"] = build_declared_agent_workflow_meta(
        workflow_definition,
        extras={"last_execution_steps": copy.deepcopy(execution.get("node_results") or {})},
    )
    return final_result


def build_knowledge_processing_result(raw_text, processing_mode="algorithm", source_type="", title="", source_detail=""):
    normalized_mode = normalize_knowledge_processing_mode(processing_mode)
    if normalized_mode == "none":
        plain_text = str(raw_text or "").strip()
        return {
            "mode": "none",
            "label": "不加工",
            "summary": plain_text[:220] if plain_text else "保留原始输入，不做额外加工。",
            "key_points": ["保留原始输入"],
            "validation_nodes": [],
            "risk_points": [],
            "template_name": "raw_passthrough_v1",
            "rendered_text": plain_text,
        }
    if normalized_mode == "llm":
        return build_llm_knowledge_processing(raw_text, source_type=source_type, title=title, source_detail=source_detail)
    return build_algorithmic_knowledge_processing(raw_text, source_type=source_type, title=title, source_detail=source_detail)


def build_knowledge_sync_status(status_text="", sync_targets=None, queued_at="", synced_at="", failed_at=""):
    raw = str(status_text or "").strip()
    normalized = raw.lower()
    targets = [str(item).strip() for item in (sync_targets if isinstance(sync_targets, list) else []) if str(item).strip()]
    primary_target = targets[1] if len(targets) > 1 else (targets[0] if targets else "知识专区")
    if "失败" in raw or "error" in normalized:
        return {
            "code": "failed",
            "label": "同步失败",
            "class_name": "syncing",
            "detail": "原始内容已保留，等待重试同步",
            "target": primary_target,
            "queued_at": str(queued_at or "").strip(),
            "synced_at": str(synced_at or "").strip(),
            "failed_at": str(failed_at or "").strip(),
        }
    if "中" in raw or "pending" in normalized or "running" in normalized:
        return {
            "code": "syncing",
            "label": "同步中",
            "class_name": "syncing",
            "detail": f"正在同步到 {primary_target} 与 Hermes",
            "target": primary_target,
            "queued_at": str(queued_at or "").strip(),
            "synced_at": str(synced_at or "").strip(),
            "failed_at": str(failed_at or "").strip(),
        }
    if raw:
        return {
            "code": "ready",
            "label": "已同步",
            "class_name": "ready",
            "detail": f"已同步到 {primary_target} 与 Hermes",
            "target": primary_target,
            "queued_at": str(queued_at or "").strip(),
            "synced_at": str(synced_at or queued_at or "").strip(),
            "failed_at": str(failed_at or "").strip(),
        }
    return {
        "code": "syncing",
        "label": "待同步",
        "class_name": "syncing",
        "detail": f"等待同步到 {primary_target}",
        "target": primary_target,
        "queued_at": str(queued_at or "").strip(),
        "synced_at": str(synced_at or "").strip(),
        "failed_at": str(failed_at or "").strip(),
    }

DEFAULT_FORECAST_TUNING = {
    "factor_score_clip": 8.0,
    "factor_signal_limit": 12.0,
    "momentum_signal_limit": 18.0,
    "predicted_change_limit": 35.0,
    "fundamental_adjustment_limit": 3.0,
    "volatility_cap_multiplier": 1.35,
    "backtest_weight": 0.55,
    "confidence_penalty_scale": 0.2,
    "confidence_floor": 45.0,
    "range_bound_multiplier": 0.85,
}

FORECAST_WORKFLOW_NODE_CATALOG = (
    {
        "processor": "source",
        "label": "上下文输入",
        "description": "从运行时上下文取值，作为后续节点输入。",
        "params": ({"key": "source_key", "label": "来源键", "kind": "text"},),
    },
    {
        "processor": "raw_signal",
        "label": "原始信号合成",
        "description": "将动量、因子和基本面修正合成为原始目标涨跌幅。",
        "params": (),
    },
    {
        "processor": "clip",
        "label": "总涨幅限幅",
        "description": "按绝对上限裁剪原始目标涨跌幅。",
        "params": ({"key": "limit_key", "label": "限幅参数键", "kind": "text"},),
    },
    {
        "processor": "volatility_cap",
        "label": "波动率约束",
        "description": "基于近 30 日波动率压缩目标空间。",
        "params": ({"key": "multiplier_key", "label": "倍数参数键", "kind": "text"},),
    },
    {
        "processor": "backtest_blend",
        "label": "回测收缩",
        "description": "结合历史相似样本平均回报对目标做收缩。",
        "params": ({"key": "weight_key", "label": "权重参数键", "kind": "text"},),
    },
    {
        "processor": "confidence_guard",
        "label": "置信度惩罚",
        "description": "低置信度场景下进一步压缩预测空间。",
        "params": (
            {"key": "floor_key", "label": "安全线参数键", "kind": "text"},
            {"key": "scale_key", "label": "惩罚参数键", "kind": "text"},
            {"key": "range_key", "label": "震荡系数参数键", "kind": "text"},
        ),
    },
    {
        "processor": "output",
        "label": "输出结果",
        "description": "输出最终高概率目标涨跌幅。",
        "params": (),
    },
)


def _coerce_float(value, fallback):
    try:
        return float(value)
    except Exception:
        return float(fallback)


def normalize_brand_config(source=None):
    raw = source if isinstance(source, dict) else {}
    brand = copy.deepcopy(DEFAULT_BRAND_CONFIG)
    for key in brand:
        value = raw.get(key, brand[key])
        brand[key] = str(value or brand[key]).strip() or brand[key]
    return brand


def normalize_tenant_config(source=None, index=0):
    raw = source if isinstance(source, dict) else {}
    fallback = DEFAULT_TENANTS[min(index, len(DEFAULT_TENANTS) - 1)]
    tenant = {}
    for key, default_value in fallback.items():
        value = raw.get(key, default_value)
        tenant[key] = str(value or default_value).strip() or default_value
    slug = tenant.get("slug", "").strip().lower().replace(" ", "-").replace("_", "-")
    tenant["slug"] = slug or fallback["slug"]
    tenant["id"] = tenant.get("id") or f"tenant_{tenant['slug']}"
    tenant["dashboard_title"] = tenant.get("dashboard_title") or f"{tenant['short_name']} Dashboard"
    tenant["dashboard_description"] = tenant.get("dashboard_description") or fallback["dashboard_description"]
    if isinstance(raw.get("portal_cms"), dict):
        tenant["portal_cms"] = copy.deepcopy(raw["portal_cms"])
    if isinstance(raw.get("fund_dashboard_config"), dict):
        tenant["fund_dashboard_config"] = copy.deepcopy(raw["fund_dashboard_config"])
    if isinstance(raw.get("knowledge_hub_config"), dict):
        tenant["knowledge_hub_config"] = copy.deepcopy(raw["knowledge_hub_config"])
    if isinstance(raw.get("review_snapshots"), list):
        tenant["review_snapshots"] = copy.deepcopy(raw["review_snapshots"])
    if isinstance(raw.get("message_center_state"), dict):
        tenant["message_center_state"] = copy.deepcopy(raw["message_center_state"])
    if isinstance(raw.get("news_aggregation_algorithm"), dict):
        tenant["news_aggregation_algorithm"] = copy.deepcopy(raw["news_aggregation_algorithm"])
    return tenant


def _safe_card_id(value, fallback):
    return slugify_code(value, fallback or "card")


def sanitize_user_facing_source_text(value, fallback=""):
    raw = str(value or "").strip()
    if not raw:
        return str(fallback or "").strip()
    normalized = raw.replace("：", ":").replace("；", ";")
    normalized = re.sub(r"https?://\S+", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\b(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s;；，,]*)?", "", normalized)
    normalized = re.sub(r"\b[A-Za-z_][A-Za-z0-9_]*\([^)]*\)", "", normalized)
    replacements = [
        ("月度宏观接口", "月度宏观数据"),
        ("宏观接口", "宏观数据"),
        ("实时接口", "实时行情数据"),
        ("历史回退", "历史行情数据"),
        ("历史接口", "历史行情数据"),
        ("AKShare", "历史数据服务"),
        ("TuShare", "历史数据服务"),
        ("Wind", "数据服务"),
    ]
    for old, new in replacements:
        normalized = normalized.replace(old, new)
    parts = re.split(r"[;；]", normalized)
    cleaned_parts = []
    seen = set()
    for part in parts:
        text = re.sub(r"\s+", " ", str(part or "")).strip(" :：,，/·-")
        if not text:
            continue
        text = re.sub(r":\s*:", ":", text)
        text = re.sub(r"\s*:\s*", "：", text)
        text = re.sub(r"：{2,}", "：", text)
        text = re.sub(r"(实时行情数据|历史行情数据|月度宏观数据|宏观数据|历史数据服务|数据服务)(：\1)+", r"\1", text)
        if text in seen:
            continue
        seen.add(text)
        cleaned_parts.append(text)
    if cleaned_parts:
        return "；".join(cleaned_parts)
    fallback_text = str(fallback or "").strip()
    return fallback_text or "平台指标数据"


def sanitize_user_facing_source_list(values, fallback=""):
    normalized = []
    seen = set()
    for item in values if isinstance(values, list) else []:
        text = sanitize_user_facing_source_text(item, fallback=fallback)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def build_review_smart_cards(tenant, fund_dashboard, watchlist_details_map=None, news_items=None):
    tenant = tenant or get_tenant_by_slug()
    watchlist_details_map = watchlist_details_map if isinstance(watchlist_details_map, dict) else {}
    news_items = news_items if isinstance(news_items, list) else []
    cards = []
    dashboard_cards = fund_dashboard.get("cards") if isinstance(fund_dashboard, dict) else []
    for index, item in enumerate((dashboard_cards or [])[:4], start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("name") or f"核心指标 {index}").strip() or f"核心指标 {index}"
        assessment = str(item.get("assessment") or item.get("hint") or "").strip()
        alert = str(item.get("alert") or "").strip()
        cards.append(
            {
                "id": _safe_card_id(f"indicator_{title}", f"indicator_{index}"),
                "kind": "indicator",
                "title": title,
                "category": "指标卡",
                "summary": assessment or str(item.get("value") or "继续跟踪").strip() or "继续跟踪",
                "value": str(item.get("value") or "").strip(),
                "status": str(item.get("status") or "attention").strip() or "attention",
                "prompt": str(item.get("prompt") or f"请围绕 {title} 生成复盘中的指标说明。").strip(),
                "data_sources": sanitize_user_facing_source_list(
                    [
                        f"租户智能指标面板：{title}",
                        "指标湖 / Dashboard 同源卡片",
                    ]
                ),
                "news_sources": [alert] if alert else [],
                "evidence_note": "用于补充当前阶段判断、风险提醒和后续跟踪点。",
            }
        )
    focus_names = ["腾讯控股", "美团-W", "阿里巴巴-W"] if tenant.get("slug") == "lisa" else ["中芯国际", "腾讯控股", "贵州茅台"]
    details_by_name = {
        str(detail.get("name") or "").strip(): detail
        for detail in watchlist_details_map.values()
        if isinstance(detail, dict) and str(detail.get("name") or "").strip()
    }
    for name in focus_names:
        detail = details_by_name.get(name)
        if not detail:
            continue
        fundamental = detail.get("fundamental") if isinstance(detail.get("fundamental"), dict) else {}
        thesis = fundamental.get("thesis") if isinstance(fundamental.get("thesis"), list) else []
        related_indicator_names = detail.get("related_indicator_names") if isinstance(detail.get("related_indicator_names"), list) else []
        cards.append(
            {
                "id": _safe_card_id(f"watch_{detail.get('code') or name}", "watchlist"),
                "kind": "watchlist",
                "title": name,
                "category": "重点个股",
                "summary": str(detail.get("signal_summary") or fundamental.get("summary") or "继续跟踪").strip() or "继续跟踪",
                "value": f"{detail.get('change_pct', 0):+.1f}%",
                "status": str(detail.get("alert_level") or "normal").strip() or "normal",
                "prompt": f"围绕 {name} 生成重点个股复盘卡，包含当前判断、验证节点、风险边界和下一步观察。",
                "data_sources": sanitize_user_facing_source_list(
                    [f"自选股详情：{name}"] + [f"关联指标：{item}" for item in related_indicator_names[:2]]
                ),
                "news_sources": [str(item).strip() for item in thesis[:2] if str(item).strip()],
                "evidence_note": str(detail.get("alert_text") or "用于补充重点样本的验证节点与风险边界。").strip(),
            }
        )
    if news_items:
        top_news = [item for item in news_items[:3] if isinstance(item, dict)]
        if top_news:
            cards.append(
                {
                    "id": "market_news_digest",
                    "kind": "news",
                    "title": "相关新闻归纳",
                    "category": "新闻卡",
                    "summary": "从当前最相关的宏观、行业和自选股新闻中提炼复盘证据。",
                    "value": f"{len(top_news)} 条",
                    "status": "attention",
                    "prompt": "归纳相关新闻，只保留真正能支撑本次复盘判断的背景材料、催化和验证信息。",
                    "data_sources": sanitize_user_facing_source_list(["平台新闻流 / 指标库关联资讯"]),
                    "news_sources": [str(item.get("title") or "").strip() for item in top_news if str(item.get("title") or "").strip()],
                    "evidence_note": "用于给复盘补充事件背景和催化说明，不能替代大V自己的判断。",
                }
            )
    return cards[:8]


def sanitize_portal_html(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    parser = PortalHtmlSanitizer()
    parser.feed(raw)
    parser.close()
    return parser.get_html().strip()


def default_portal_workspace(tenant):
    is_lisa = tenant["slug"] == "lisa"
    workspace = {
        "summary": "租户门户是给粉丝看的父客户端主页。大V在这里像维护 WordPress 一样编辑门户结构：上半部做品牌介绍和价值主张，中间固定展示 Dashboard，下半部维护可自定义文案区，最后放扫码与联系方式。",
        "draft_status": "草稿待发布",
        "published_status": "线上已发布",
        "last_published_at": "2026-06-17 21:10",
        "theme_name": is_lisa and "港股价值蓝" or "科技主线金",
        "hero": {
            "headline": tenant["portal_headline"],
            "description": tenant["portal_description"],
            "audience": is_lisa and "适合先看港股互联网、估值修复与价值框架的粉丝" or "适合先看科技成长、复盘主线和重点样本的粉丝",
            "value_props": [
                is_lisa and "先看价值框架，再决定是否继续互动" or "先看阶段主线，再决定是否继续深挖个股",
                is_lisa and "把港股互联网研究口径整理成粉丝能直接理解的主页" or "把科技成长和重点样本整理成粉丝能直接消费的入口",
                "把复盘、Dashboard 和联系方式收拢成一个父客户端首页",
            ],
        },
        "cta": {
            "primary_label": "进入 H5 继续查看",
            "secondary_label": "先看最新复盘",
        },
        "modules": [
            {"id": "hero", "title": "门户介绍区", "type": "固定首屏", "desc": "介绍大V是谁、价值主张是什么、门户适合谁看。", "enabled": True},
            {"id": "dashboard", "title": "固定 Dashboard", "type": "固定中段", "desc": "中段固定展示关键经营 / 研究 Dashboard，不由大V随意删除。", "enabled": True},
            {"id": "custom-copy", "title": "自定义文案区", "type": "父客户端编辑", "desc": "大V自己写长文案、特色介绍、服务说明和专题说明。", "enabled": True},
            {"id": "contact", "title": "扫码与联系方式", "type": "固定尾部", "desc": "放企微、公众号、客服方式和线下联系入口。", "enabled": True},
        ],
        "presets": [
            {"label": "品牌主视觉", "desc": "突出主理人定位、价值主张和门户导语。"},
            {"label": "固定 Dashboard", "desc": "中段固定承接关键指标与研究总结，不与门户装修混用。"},
            {"label": "父客户端文案", "desc": "大V自己写特色介绍、服务说明和长期表达。"},
            {"label": "联系方式尾部", "desc": "把扫码、企微、公众号和联系信息固定收在页尾。"},
        ],
        "custom_sections": [
            {
                "title": is_lisa and "为什么这个门户值得先看" or "为什么先看这个门户而不是直接进功能页",
                "body": is_lisa and "我希望先把港股互联网的核心主线、估值框架和代表性样本讲清楚，再带你去看更具体的互动和跟踪。" or "我希望先把科技成长、重点样本和阶段判断讲清楚，再带你去看更具体的复盘、互动和工具。",
            },
            {
                "title": "我会持续更新什么",
                "body": "这里会持续更新复盘摘要、重点样本、价值主张和阶段判断。粉丝进入门户后，不需要先理解复杂功能，就能先看懂我当前在研究什么。",
            },
        ],
        "contact": {
            "qr_title": is_lisa and "扫码加入 Lisa 研究社" or "扫码加入老王研究群",
            "qr_hint": "扫码后可进入所属租户粉丝群或添加助手，后续接收复盘分享和互动提醒。",
            "wechat": is_lisa and "Lisa-Research-Assistant" or "Laowang-Research-Assistant",
            "phone": "400-889-6608",
            "email": is_lisa and "lisa@gangtise.demo" or "laowang@gangtise.demo",
        },
    }
    workspace["page_blocks"] = [
        {"id": "hero_block", "type": "hero", "title": "门户介绍", "html": "", "enabled": True},
        {"id": "dashboard_block", "type": "dashboard", "title": "固定 Dashboard", "html": "", "enabled": True},
        {
            "id": "copy_block_1",
            "type": "rich_text",
            "title": workspace["custom_sections"][0]["title"],
            "html": sanitize_portal_html(
                f"<h3>{workspace['custom_sections'][0]['title']}</h3><p>{workspace['custom_sections'][0]['body']}</p>"
            ),
            "enabled": True,
        },
        {
            "id": "copy_block_2",
            "type": "rich_text",
            "title": workspace["custom_sections"][1]["title"],
            "html": sanitize_portal_html(
                f"<h3>{workspace['custom_sections'][1]['title']}</h3><p>{workspace['custom_sections'][1]['body']}</p>"
            ),
            "enabled": True,
        },
        {"id": "contact_block", "type": "contact", "title": "联系方式", "html": "", "enabled": True},
    ]
    return workspace


def resolve_tenant_portal_workspace(tenant, cms=None):
    tenant = tenant or get_tenant_by_slug()
    base = default_portal_workspace(tenant)
    if isinstance(cms, dict):
        merged = normalize_portal_cms_config(cms, tenant)
        base.update({
            "summary": merged.get("summary", base["summary"]),
            "draft_status": merged.get("draft_status", base["draft_status"]),
            "published_status": merged.get("published_status", base["published_status"]),
            "last_published_at": merged.get("last_published_at", base["last_published_at"]),
            "theme_name": merged.get("theme_name", base["theme_name"]),
            "hero": merged.get("hero", base["hero"]),
            "cta": merged.get("cta", base["cta"]),
            "modules": merged.get("modules", base["modules"]),
            "presets": merged.get("presets", base["presets"]),
            "custom_sections": merged.get("custom_sections", base["custom_sections"]),
            "contact": merged.get("contact", base["contact"]),
            "page_blocks": merged.get("page_blocks", base["page_blocks"]),
        })
    return base


def default_tenant_review_snapshots(tenant):
    is_lisa = tenant["slug"] == "lisa"
    watchlist_focus = ["腾讯控股", "美团-W", "阿里巴巴-W"] if is_lisa else ["中芯国际", "腾讯控股", "贵州茅台"]
    return [
        {
            "id": f"{tenant['slug']}-review-day-default",
            "title": "收盘复盘：AI 算力强主线未变，港股互联网继续看回购与财报兑现",
            "period": "日复盘",
            "period_key": "day",
            "time": "2026-06-07 18:40",
            "tags": ["行业板块", "个股跟踪", "可直接分发"],
            "watchlist": watchlist_focus[:3],
            "summary": "先从全天资料压出短版提纲，再对中芯国际、腾讯控股和贵州茅台三个样本做个股投资复盘，保留主线、验证节点和下一步观察。",
            "content_text": "先从全天资料压出短版提纲，再对重点样本做个股投资复盘，保留主线、验证节点和下一步观察。",
            "source_mode": "voice",
            "paragraph_mode": "manual",
            "publisher": tenant["advisor"],
            "published_at": "2026-06-07 18:40",
            "snapshot_type": "published_review",
        },
        {
            "id": f"{tenant['slug']}-review-week-default",
            "title": "周度复盘：科技成长维持主线，消费与新能源需要继续等景气验证",
            "period": "周复盘",
            "period_key": "week",
            "time": "2026-06-06 20:10",
            "tags": ["周度框架", "板块归纳"],
            "watchlist": watchlist_focus[:3],
            "summary": "以行业板块为骨架，把 AI 算力、半导体、港股互联网、消费和新能源统一放进同一篇复盘，方便普通投资者快速查看。",
            "content_text": "以行业板块为骨架，把 AI 算力、半导体、港股互联网、消费和新能源统一放进同一篇复盘。",
            "source_mode": "file",
            "paragraph_mode": "ai",
            "publisher": tenant["advisor"],
            "published_at": "2026-06-06 20:10",
            "snapshot_type": "published_review",
        },
    ]


def normalize_review_snapshot_item(item, tenant, index=0):
    raw = item if isinstance(item, dict) else {}
    fallback = default_tenant_review_snapshots(tenant)[min(index, len(default_tenant_review_snapshots(tenant)) - 1)]
    watchlist = [str(name).strip() for name in (raw.get("watchlist") if isinstance(raw.get("watchlist"), list) else fallback.get("watchlist", [])) if str(name).strip()][:8]
    tags = [str(name).strip() for name in (raw.get("tags") if isinstance(raw.get("tags"), list) else fallback.get("tags", [])) if str(name).strip()][:8]
    title = str(raw.get("title") or fallback.get("title") or "").strip() or fallback["title"]
    content_text = str(raw.get("content_text") or raw.get("content") or raw.get("body_text") or fallback.get("content_text") or "").strip()
    summary = str(raw.get("summary") or fallback.get("summary") or content_text[:180]).strip() or fallback["summary"]
    published_at = normalize_datetime_text(raw.get("published_at") or raw.get("time") or fallback.get("published_at") or fallback.get("time"))
    attachments = []
    for offset, attachment in enumerate(raw.get("knowledge_attachments") if isinstance(raw.get("knowledge_attachments"), list) else []):
        if not isinstance(attachment, dict):
            continue
        attachments.append({
            "id": str(attachment.get("id") or attachment.get("knowledge_id") or f"{tenant['slug']}-knowledge-{index + offset + 1}").strip() or f"{tenant['slug']}-knowledge-{index + offset + 1}",
            "title": str(attachment.get("title") or "知识材料").strip()[:120] or "知识材料",
            "summary": str(attachment.get("summary") or attachment.get("body") or attachment.get("raw_input") or "").strip()[:360],
            "body": str(attachment.get("body") or attachment.get("raw_input") or attachment.get("summary") or "").strip()[:4000],
            "source_detail": sanitize_user_facing_source_text(attachment.get("source_detail") or attachment.get("source") or "")[:240],
            "url": str(attachment.get("url") or "").strip()[:500],
            "tags": [str(tag).strip() for tag in (attachment.get("tags") if isinstance(attachment.get("tags"), list) else []) if str(tag).strip()][:8],
        })
    selected_cards = []
    for card in raw.get("selected_cards") if isinstance(raw.get("selected_cards"), list) else []:
        if not isinstance(card, dict):
            continue
        selected_cards.append({
            "id": str(card.get("id") or "").strip()[:120],
            "title": str(card.get("title") or card.get("name") or "智能卡片").strip()[:120] or "智能卡片",
            "category": str(card.get("category") or card.get("kind") or "").strip()[:80],
            "summary": str(card.get("summary") or card.get("assessment") or card.get("hint") or "").strip()[:360],
            "value": str(card.get("value") or "").strip()[:120],
            "prompt": str(card.get("prompt") or "").strip()[:2000],
            "data_sources": sanitize_user_facing_source_list(card.get("data_sources") if isinstance(card.get("data_sources"), list) else [])[:8],
            "news_sources": [str(source).strip() for source in (card.get("news_sources") if isinstance(card.get("news_sources"), list) else []) if str(source).strip()][:8],
        })
    llm_models = []
    for model in raw.get("llm_models") if isinstance(raw.get("llm_models"), list) else []:
        if not isinstance(model, dict):
            continue
        llm_models.append({
            "stage": str(model.get("stage") or "").strip()[:80],
            "key": str(model.get("key") or "").strip()[:120],
            "label": str(model.get("label") or "").strip()[:120],
            "provider": str(model.get("provider") or "").strip()[:120],
            "model_name": str(model.get("model_name") or "").strip()[:240],
            "purpose": str(model.get("purpose") or "").strip()[:120],
        })
    user_input_raw = raw.get("user_input_section") if isinstance(raw.get("user_input_section"), dict) else {}
    watchlist_analysis_raw = raw.get("watchlist_analysis_section") if isinstance(raw.get("watchlist_analysis_section"), dict) else {}
    user_input_section = {
        "source_mode": str(user_input_raw.get("source_mode") or raw.get("source_mode") or fallback.get("source_mode") or "manual").strip().lower() or "manual",
        "source_mode_label": str(user_input_raw.get("source_mode_label") or "").strip()[:80],
        "display_text": str(
            user_input_raw.get("display_text")
            or user_input_raw.get("polished_text")
            or raw.get("polished_input_text")
            or content_text
            or summary
        ).strip()[:12000],
        "summary_source": str(user_input_raw.get("summary_source") or "").strip()[:120],
    }
    sector_profiles = []
    for profile in watchlist_analysis_raw.get("sector_profiles") if isinstance(watchlist_analysis_raw.get("sector_profiles"), list) else []:
        if not isinstance(profile, dict):
            continue
        sector_profiles.append({
            "sector": str(profile.get("sector") or "").strip()[:120],
            "stock_names": [str(name).strip() for name in (profile.get("stock_names") if isinstance(profile.get("stock_names"), list) else []) if str(name).strip()][:8],
            "representative_description": str(profile.get("representative_description") or "").strip()[:400],
        })
    watchlist_items = []
    for item in watchlist_analysis_raw.get("items") if isinstance(watchlist_analysis_raw.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        watchlist_items.append({
            "stock_name": str(item.get("stock_name") or "").strip()[:120],
            "stock_code": str(item.get("stock_code") or "").strip()[:60],
            "sector": str(item.get("sector") or "").strip()[:120],
            "board_role": str(item.get("board_role") or "").strip()[:180],
            "analysis_text": str(item.get("analysis_text") or "").strip()[:1200],
            "evidence": [str(value).strip() for value in (item.get("evidence") if isinstance(item.get("evidence"), list) else []) if str(value).strip()][:6],
        })
    annotation_evidence = []
    for item in watchlist_analysis_raw.get("annotation_evidence") if isinstance(watchlist_analysis_raw.get("annotation_evidence"), list) else []:
        if not isinstance(item, dict):
            continue
        annotation_evidence.append({
            "annotation_id": item.get("annotation_id"),
            "stock_name": str(item.get("stock_name") or "").strip()[:120],
            "stock_code": str(item.get("stock_code") or "").strip()[:60],
            "date_label": str(item.get("date_label") or "").strip()[:40],
            "title": str(item.get("title") or "").strip()[:120],
            "note": str(item.get("note") or "").strip()[:600],
            "trigger": str(item.get("trigger") or "").strip()[:240],
        })
    watchlist_analysis_section = {
        "sector_summary": str(watchlist_analysis_raw.get("sector_summary") or "").strip()[:200],
        "sector_profiles": sector_profiles,
        "items": watchlist_items,
        "annotation_evidence": annotation_evidence,
    }
    evidence_chain_raw = raw.get("evidence_chain_section") if isinstance(raw.get("evidence_chain_section"), dict) else {}
    evidence_chain_items = []
    for item in evidence_chain_raw.get("items") if isinstance(evidence_chain_raw.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        evidence_chain_items.append({
            "id": str(item.get("id") or "").strip()[:120],
            "kind": str(item.get("kind") or "").strip()[:40],
            "title": str(item.get("title") or "").strip()[:180],
            "summary": str(item.get("summary") or "").strip()[:400],
            "source_label": str(item.get("source_label") or "").strip()[:80],
            "source_detail": sanitize_user_facing_source_text(item.get("source_detail") or "")[:240],
            "published_at": str(item.get("published_at") or "").strip()[:120],
            "link": str(item.get("link") or "").strip()[:500],
            "score": float(item.get("score") or 0.0),
        })
    evidence_chain_model = evidence_chain_raw.get("llm_model") if isinstance(evidence_chain_raw.get("llm_model"), dict) else {}
    evidence_chain_section = {
        "status": str(evidence_chain_raw.get("status") or ("matched" if evidence_chain_items else "empty")).strip()[:40] or "empty",
        "query_text": str(evidence_chain_raw.get("query_text") or "").strip()[:280],
        "summary": str(evidence_chain_raw.get("summary") or ("暂无匹配的证据链" if not evidence_chain_items else "")).strip()[:400] or ("暂无匹配的证据链" if not evidence_chain_items else ""),
        "items": evidence_chain_items,
        "knowledge_match_count": max(0, int(evidence_chain_raw.get("knowledge_match_count") or len([item for item in evidence_chain_items if item.get("kind") == "knowledge"]))),
        "web_match_count": max(0, int(evidence_chain_raw.get("web_match_count") or len([item for item in evidence_chain_items if item.get("kind") == "web"]))),
        "llm_model": {
            "key": str(evidence_chain_model.get("key") or "").strip()[:120],
            "label": str(evidence_chain_model.get("label") or "").strip()[:120],
            "provider": str(evidence_chain_model.get("provider") or "").strip()[:120],
            "model_name": str(evidence_chain_model.get("model_name") or "").strip()[:240],
            "purpose": str(evidence_chain_model.get("purpose") or "").strip()[:120],
        } if evidence_chain_model else {},
    }
    return {
        "id": str(raw.get("id") or f"{tenant['slug']}-review-{index + 1}").strip() or f"{tenant['slug']}-review-{index + 1}",
        "title": title,
        "period": str(raw.get("period") or fallback.get("period") or "日复盘").strip() or "日复盘",
        "period_key": str(raw.get("period_key") or fallback.get("period_key") or "day").strip().lower() or "day",
        "time": published_at or fallback.get("time") or now_ts(),
        "published_at": published_at or fallback.get("published_at") or now_ts(),
        "tags": tags or copy.deepcopy(fallback.get("tags") or []),
        "watchlist": watchlist or copy.deepcopy(fallback.get("watchlist") or []),
        "summary": summary,
        "content_text": content_text or summary,
        "source_mode": str(raw.get("source_mode") or fallback.get("source_mode") or "manual").strip().lower() or "manual",
        "paragraph_mode": str(raw.get("paragraph_mode") or fallback.get("paragraph_mode") or "manual").strip().lower() or "manual",
        "publisher": str(raw.get("publisher") or tenant.get("advisor") or "").strip() or tenant.get("advisor") or "",
        "snapshot_type": str(raw.get("snapshot_type") or "published_review").strip() or "published_review",
        "knowledge_attachments": attachments,
        "selected_cards": selected_cards,
        "data_sources": sanitize_user_facing_source_list(raw.get("data_sources") if isinstance(raw.get("data_sources"), list) else [])[:12],
        "news_sources": [str(source).strip() for source in (raw.get("news_sources") if isinstance(raw.get("news_sources"), list) else []) if str(source).strip()][:12],
        "llm_models": llm_models,
        "polished_input_text": str(raw.get("polished_input_text") or "").strip()[:12000],
        "user_input_section": user_input_section,
        "watchlist_analysis_section": watchlist_analysis_section,
        "evidence_chain_section": evidence_chain_section,
    }


def resolve_tenant_review_snapshots(tenant, snapshots=None):
    tenant = tenant or get_tenant_by_slug()
    items = snapshots if isinstance(snapshots, list) else tenant.get("review_snapshots")
    source_items = items if isinstance(items, list) and items else default_tenant_review_snapshots(tenant)
    normalized = []
    for index, item in enumerate(source_items[:20]):
        normalized.append(normalize_review_snapshot_item(item, tenant, index=index))
    return normalized


def default_tenant_message_center_state(tenant):
    is_lisa = tenant["slug"] == "lisa"
    return {
        "summary": "消息板块不仅包含粉丝给大V的提问，也包含大V回复粉丝后的追问，以及复盘发布后需要第一时间触达的粉丝提醒。",
        "threads": [
            {
                "id": f"{tenant['slug']}-thread-fan-1",
                "type": "fan_interaction",
                "name": "投研达人_小陈",
                "time": "5分钟前",
                "content": is_lisa and "港股互联网还能继续配吗？想看你按 Hermes 价值框架压缩后的短版结论。" or "AI 算力还能继续跟吗？想看你按 Hermes 基本面判断后的短版结论。",
                "status": "待回复",
                "user_name": "投研达人_小陈",
                "user_avatar": "👨",
                "tier": "核心用户",
                "last_msg": is_lisa and "港股互联网还能继续配吗？" or "AI 算力还能继续跟吗？",
                "unread": 1,
                "vip_only": False,
                "messages": [
                    {"id": 1, "sender": "user", "content": is_lisa and "港股互联网还能继续配吗？想看你按 Hermes 价值框架压缩后的短版结论。" or "AI 算力还能继续跟吗？想看你按 Hermes 基本面判断后的短版结论。", "time": "2026-06-07 17:35", "type": "text"},
                ],
            },
            {
                "id": f"{tenant['slug']}-thread-review-1",
                "type": "review_notification",
                "name": "复盘发布提醒",
                "time": "12分钟前",
                "content": "你刚发布的日复盘已经推送给 92 位高频粉丝，首批打开率 41%。",
                "status": "已送达",
                "user_name": "复盘发布提醒",
                "user_avatar": "📝",
                "tier": "系统消息",
                "last_msg": "你刚发布的日复盘已经推送给 92 位高频粉丝",
                "unread": 0,
                "vip_only": False,
                "messages": [
                    {"id": 1, "sender": "kol", "content": "【最新复盘已发布】你刚发布的日复盘已经推送给高频粉丝，点击可查看送达情况。", "time": "2026-06-07 18:28", "type": "review"},
                ],
            },
            {
                "id": f"{tenant['slug']}-thread-fan-2",
                "type": "fan_interaction",
                "name": "价值猎人小林",
                "time": "23分钟前",
                "content": is_lisa and "最新那篇港股复盘我看完了，想继续问腾讯和美团的回购节奏怎么拆。" or "港股互联网那篇复盘我看完了，想继续问腾讯回购节奏和估值带怎么看。",
                "status": "待跟进",
                "user_name": "价值猎人小林",
                "user_avatar": "🧑",
                "tier": "观察用户",
                "last_msg": is_lisa and "最新那篇港股复盘我看完了" or "港股互联网那篇复盘我看完了",
                "unread": 1,
                "vip_only": False,
                "messages": [
                    {"id": 1, "sender": "user", "content": is_lisa and "最新那篇港股复盘我看完了，想继续问腾讯和美团的回购节奏怎么拆。" or "港股互联网那篇复盘我看完了，想继续问腾讯回购节奏和估值带怎么看。", "time": "2026-06-07 18:17", "type": "text"},
                ],
            },
        ],
        "broadcasts": [
            {"id": 1, "content": is_lisa and "本周港股互联网更新：继续看南向资金和回购兑现" or "本周策略更新：科技板块适合继续跟踪，重点看 AI 算力订单兑现", "time": "2026-05-20 08:00", "reach": 92, "open_rate": 68, "target": "all", "type": "broadcast"},
            {"id": 2, "content": is_lisa and "价值提醒：财报前估值修复较快，注意不要只盯单一平台" or "宏观提醒：美联储纪要偏鸽，但还要等国内资金面确认", "time": "2026-05-19 22:30", "reach": 108, "open_rate": 82, "target": "active", "type": "broadcast"},
            {"id": 3, "content": "周末复盘：本周操作回顾与下周观察重点", "time": "2026-05-18 18:00", "reach": 76, "open_rate": 55, "target": "review", "type": "broadcast"},
        ],
    }


def summarize_message_preview(content, limit=72):
    text = re.sub(r"\s+", " ", str(content or "").replace("\n", " ").strip())
    if len(text) <= limit:
        return text
    return f"{text[:max(0, limit - 1)]}…"


def normalize_message_thread_message_item(msg, msg_index=0):
    raw = msg if isinstance(msg, dict) else {}
    message_type = str(raw.get("type") or "text").strip() or "text"
    content = str(raw.get("content") or "").strip()
    preview = str(raw.get("preview") or "").strip()
    price = max(0, int(raw.get("price") or 0))
    if message_type == "paid" and not preview:
        preview = summarize_message_preview(content, limit=48) or "解锁查看完整内容"
    return {
        "id": int(raw.get("id") or (msg_index + 1)),
        "sender": str(raw.get("sender") or "user").strip() or "user",
        "content": content,
        "time": normalize_datetime_text(raw.get("time") or now_ts()) or now_ts(),
        "type": message_type,
        "price": price,
        "preview": preview,
    }


def build_thread_last_message(thread, messages):
    latest = messages[-1] if messages else {}
    latest_type = str((latest or {}).get("type") or "").strip()
    if latest_type == "review":
        return summarize_message_preview((latest or {}).get("content") or thread.get("last_msg") or "【最新复盘已发布】", limit=72)
    if latest_type == "broadcast":
        content = (latest or {}).get("content") or thread.get("last_msg") or "群发消息已发送"
        return f"【群发】{summarize_message_preview(content, limit=60)}"
    if latest_type == "paid":
        preview = (latest or {}).get("preview") or (latest or {}).get("content") or thread.get("last_msg") or "付费回复"
        return f"【付费回复】{summarize_message_preview(preview, limit=56)}"
    return summarize_message_preview((latest or {}).get("content") or thread.get("last_msg") or thread.get("content") or "", limit=72)


def normalize_message_thread_item(item, tenant, index=0):
    raw = item if isinstance(item, dict) else {}
    defaults = default_tenant_message_center_state(tenant)["threads"]
    fallback = defaults[min(index, len(defaults) - 1)]
    raw_messages = raw.get("messages") if isinstance(raw.get("messages"), list) else fallback.get("messages", [])
    messages = [normalize_message_thread_message_item(msg, msg_index=msg_index) for msg_index, msg in enumerate(raw_messages) if isinstance(msg, dict)]
    last_sender = str(
        raw.get("last_sender")
        or ((messages[-1] or {}).get("sender") if messages else "")
        or fallback.get("last_sender")
        or "user"
    ).strip() or "user"
    legacy_unread = max(0, int(raw.get("unread") or fallback.get("unread") or 0))
    kol_unread = max(
        0,
        int(
            raw.get("kol_unread")
            if raw.get("kol_unread") is not None
            else (legacy_unread if last_sender == "user" and str(raw.get("type") or fallback.get("type") or "").strip() == "fan_interaction" else 0)
        ),
    )
    user_unread = max(
        0,
        int(
            raw.get("user_unread")
            if raw.get("user_unread") is not None
            else (legacy_unread if last_sender == "kol" and str(raw.get("type") or fallback.get("type") or "").strip() == "fan_interaction" else 0)
        ),
    )
    thread_type = str(raw.get("type") or fallback.get("type") or "fan_interaction").strip() or "fan_interaction"
    last_message = messages[-1] if messages else {}
    last_msg = str(raw.get("last_msg") or "").strip() or build_thread_last_message(raw, messages)
    if not last_msg:
        last_msg = str(raw.get("content") or fallback.get("content") or "").strip()
    return {
        "id": str(raw.get("id") or fallback.get("id") or f"{tenant['slug']}-thread-{index + 1}").strip(),
        "type": thread_type,
        "name": str(raw.get("name") or fallback.get("name") or "").strip(),
        "time": str(raw.get("time") or fallback.get("time") or "").strip() or now_ts(),
        "content": str(raw.get("content") or fallback.get("content") or "").strip(),
        "status": str(raw.get("status") or fallback.get("status") or "").strip() or "待处理",
        "user_profile_id": str(raw.get("user_profile_id") or "").strip(),
        "user_name": str(raw.get("user_name") or fallback.get("user_name") or raw.get("name") or "").strip(),
        "user_avatar": str(raw.get("user_avatar") or fallback.get("user_avatar") or "👤").strip() or "👤",
        "tier": str(raw.get("tier") or fallback.get("tier") or "粉丝").strip() or "粉丝",
        "last_msg": last_msg,
        "unread": max(kol_unread, user_unread),
        "kol_unread": kol_unread,
        "user_unread": user_unread,
        "last_sender": last_sender,
        "updated_at": normalize_datetime_text(raw.get("updated_at") or (last_message or {}).get("time") or raw.get("time") or now_ts()) or now_ts(),
        "last_message_type": str((last_message or {}).get("type") or raw.get("last_message_type") or "text").strip() or "text",
        "vip_only": bool(raw.get("vip_only", fallback.get("vip_only", False))),
        "messages": messages,
    }


def normalize_message_broadcast_item(item, tenant, index=0):
    raw = item if isinstance(item, dict) else {}
    defaults = default_tenant_message_center_state(tenant)["broadcasts"]
    fallback = defaults[min(index, len(defaults) - 1)]
    return {
        "id": int(raw.get("id") or fallback.get("id") or (index + 1)),
        "content": str(raw.get("content") or fallback.get("content") or "").strip(),
        "time": str(raw.get("time") or fallback.get("time") or "").strip() or now_ts(),
        "reach": max(0, int(raw.get("reach") or fallback.get("reach") or 0)),
        "open_rate": max(0, int(raw.get("open_rate") or fallback.get("open_rate") or 0)),
        "target": str(raw.get("target") or fallback.get("target") or "all").strip() or "all",
        "type": str(raw.get("type") or fallback.get("type") or "broadcast").strip() or "broadcast",
    }


def resolve_tenant_message_center_state(tenant, state=None):
    tenant = tenant or get_tenant_by_slug()
    defaults = default_tenant_message_center_state(tenant)
    raw = state if isinstance(state, dict) else tenant.get("message_center_state")
    source = raw if isinstance(raw, dict) else {}
    threads_source = source.get("threads") if isinstance(source.get("threads"), list) else defaults["threads"]
    broadcasts_source = source.get("broadcasts") if isinstance(source.get("broadcasts"), list) else defaults["broadcasts"]
    threads = [normalize_message_thread_item(item, tenant, index=index) for index, item in enumerate(threads_source[:60])]
    broadcasts = [normalize_message_broadcast_item(item, tenant, index=index) for index, item in enumerate(broadcasts_source[:60])]
    summary = str(source.get("summary") or defaults["summary"]).strip() or defaults["summary"]
    return {
        "summary": summary,
        "threads": threads,
        "broadcasts": broadcasts,
    }


def _save_tenant_state_field(tenant_slug, field_name, value):
    site_config = get_site_config()
    tenants = get_tenant_configs(site_config)
    for index, tenant in enumerate(tenants):
        if tenant["slug"] != tenant_slug:
            continue
        tenants[index][field_name] = copy.deepcopy(value)
        next_config = dict(site_config)
        next_config["tenants"] = tenants
        return save_site_config(next_config)
    return None


def update_tenant_review_snapshots(tenant_slug, snapshots):
    tenant = get_tenant_by_slug(tenant_slug)
    normalized = resolve_tenant_review_snapshots(tenant, snapshots=snapshots)
    return _save_tenant_state_field(tenant_slug, "review_snapshots", normalized)


def update_tenant_message_center_state(tenant_slug, state):
    tenant = get_tenant_by_slug(tenant_slug)
    normalized = resolve_tenant_message_center_state(tenant, state=state)
    return _save_tenant_state_field(tenant_slug, "message_center_state", normalized)


def append_review_snapshot(tenant_slug, snapshot):
    tenant = get_tenant_by_slug(tenant_slug)
    current = resolve_tenant_review_snapshots(tenant, snapshots=tenant.get("review_snapshots"))
    next_items = [normalize_review_snapshot_item(snapshot, tenant, index=0)] + current
    deduped = []
    seen_ids = set()
    for index, item in enumerate(next_items):
        item_id = str(item.get("id") or f"{tenant_slug}-review-{index + 1}").strip()
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        deduped.append(normalize_review_snapshot_item(item, tenant, index=index))
    saved = update_tenant_review_snapshots(tenant_slug, deduped[:20])
    latest_tenant = get_tenant_by_slug(tenant_slug, saved) if saved else tenant
    return resolve_tenant_review_snapshots(latest_tenant, snapshots=latest_tenant.get("review_snapshots"))


def append_message_thread(tenant_slug, thread_item):
    tenant = get_tenant_by_slug(tenant_slug)
    state = resolve_tenant_message_center_state(tenant, state=tenant.get("message_center_state"))
    next_threads = [normalize_message_thread_item(thread_item, tenant, index=0)] + state["threads"]
    saved = update_tenant_message_center_state(tenant_slug, {
        "summary": state["summary"],
        "threads": next_threads[:60],
        "broadcasts": state["broadcasts"],
    })
    latest_tenant = get_tenant_by_slug(tenant_slug, saved) if saved else tenant
    return resolve_tenant_message_center_state(latest_tenant, state=latest_tenant.get("message_center_state"))


def append_broadcast_history(tenant_slug, broadcast_item):
    tenant = get_tenant_by_slug(tenant_slug)
    state = resolve_tenant_message_center_state(tenant, state=tenant.get("message_center_state"))
    next_broadcasts = [normalize_message_broadcast_item(broadcast_item, tenant, index=0)] + state["broadcasts"]
    saved = update_tenant_message_center_state(tenant_slug, {
        "summary": state["summary"],
        "threads": state["threads"],
        "broadcasts": next_broadcasts[:60],
    })
    latest_tenant = get_tenant_by_slug(tenant_slug, saved) if saved else tenant
    return resolve_tenant_message_center_state(latest_tenant, state=latest_tenant.get("message_center_state"))


def build_message_center_items(threads, limit=6):
    items = []
    for thread in (threads or [])[: max(1, int(limit or 6))]:
        thread_type = str(thread.get("type") or "").strip()
        status = str(thread.get("status") or "").strip() or "待处理"
        if thread_type == "review_notification":
            item_type = "系统消息"
        elif thread_type == "broadcast_notification":
            item_type = "群发通知"
        else:
            item_type = "粉丝提问" if status == "待回复" else "追问消息"
        items.append({
            "id": str(thread.get("id") or "").strip(),
            "name": thread.get("name") or thread.get("user_name") or "",
            "type": item_type,
            "time": thread.get("time") or "--",
            "content": thread.get("content") or thread.get("last_msg") or "",
            "status": status,
            "tier": thread.get("tier") or "",
            "kol_unread": max(0, int(thread.get("kol_unread") or 0)),
            "user_unread": max(0, int(thread.get("user_unread") or 0)),
        })
    return items


def build_message_center_stats(state):
    threads = state.get("threads") if isinstance(state, dict) else []
    fan_threads = [item for item in (threads or []) if str(item.get("type") or "").strip() == "fan_interaction"]
    unread_messages = sum(1 for item in fan_threads if int(item.get("kol_unread") or 0) > 0)
    pending_replies = sum(1 for item in fan_threads if str(item.get("status") or "").strip() == "待回复")
    investor_unread = sum(1 for item in fan_threads if int(item.get("user_unread") or 0) > 0)
    return {
        "unread_messages": unread_messages,
        "pending_replies": pending_replies,
        "investor_unread_threads": investor_unread,
    }


def build_dm_conversation_records(tenant, threads):
    tenant = tenant or get_tenant_by_slug()
    records = []
    for thread in threads or []:
        records.append({
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
            "type": str(thread.get("type") or "").strip(),
        })
    return records


def build_dm_center_payload(tenant_slug="", actor_role="", actor_profile_id="", include_fan_threads=True):
    resolved_slug = str(tenant_slug or "").strip().lower() or get_default_tenant_slug()
    tenant = get_tenant_by_slug(resolved_slug)
    state = resolve_tenant_message_center_state(tenant, tenant.get("message_center_state"))
    threads = []
    normalized_role = str(actor_role or "").strip().lower()
    normalized_profile_id = str(actor_profile_id or "").strip()
    for thread in state["threads"]:
        thread_type = str(thread.get("type") or "").strip()
        if thread_type == "fan_interaction" and not include_fan_threads:
            continue
        if normalized_role == "investor":
            if thread_type != "fan_interaction":
                continue
            if str(thread.get("user_profile_id") or "").strip() != normalized_profile_id:
                continue
        threads.append(copy.deepcopy(thread))
    filtered_state = {
        "summary": state["summary"],
        "threads": threads,
        "broadcasts": copy.deepcopy(state["broadcasts"]),
    }
    stats = build_message_center_stats(filtered_state)
    return {
        "tenant_slug": resolved_slug,
        "summary": filtered_state["summary"],
        "stats": stats,
        "threads": build_dm_conversation_records(tenant, threads),
        "thread_state": threads,
        "items": build_message_center_items(threads, limit=6),
        "broadcasts": copy.deepcopy(state["broadcasts"]),
    }


def mark_message_thread_read(tenant_slug, thread_id, actor_role):
    resolved_slug = str(tenant_slug or "").strip().lower() or get_default_tenant_slug()
    tenant = get_tenant_by_slug(resolved_slug)
    state = resolve_tenant_message_center_state(tenant, tenant.get("message_center_state"))
    threads = copy.deepcopy(state["threads"] or [])
    thread_index = find_message_thread_index(threads, thread_id=thread_id)
    if thread_index < 0:
        return None, state
    thread = dict(threads[thread_index])
    normalized_role = str(actor_role or "").strip().lower()
    if normalized_role == "dav":
        thread["kol_unread"] = 0
    elif normalized_role == "investor":
        thread["user_unread"] = 0
    normalized_thread = normalize_message_thread_item(thread, tenant, index=thread_index)
    threads[thread_index] = normalized_thread
    _, latest_state = save_tenant_message_threads(resolved_slug, state, threads)
    return normalized_thread, latest_state


def build_broadcast_thread_for_user(tenant, user_profile, broadcast_item):
    username = str((user_profile or {}).get("username") or "").strip()
    if not username:
        return None
    avatar = str((user_profile or {}).get("avatar") or "👤").strip() or "👤"
    membership = str((user_profile or {}).get("membership") or "粉丝").strip() or "粉丝"
    content = str((broadcast_item or {}).get("content") or "").strip()
    message = {
        "id": 1,
        "sender": "kol",
        "content": content,
        "time": now_ts(),
        "type": "broadcast",
    }
    return normalize_message_thread_item({
        "id": build_fan_thread_id(tenant.get("slug"), username),
        "type": "fan_interaction",
        "name": username,
        "time": "刚刚",
        "content": content,
        "status": "已触达",
        "user_profile_id": username,
        "user_name": username,
        "user_avatar": avatar,
        "tier": membership,
        "last_msg": f"【群发】{summarize_message_preview(content, limit=56)}",
        "kol_unread": 0,
        "user_unread": 1,
        "last_sender": "kol",
        "last_message_type": "broadcast",
        "vip_only": False,
        "messages": [message],
    }, tenant, index=0)


def push_broadcast_to_fan_threads(tenant_slug, broadcast_item):
    resolved_slug = str(tenant_slug or "").strip().lower() or get_default_tenant_slug()
    tenant = get_tenant_by_slug(resolved_slug)
    state = resolve_tenant_message_center_state(tenant, tenant.get("message_center_state"))
    threads = copy.deepcopy(state["threads"] or [])
    investor_users = list_users(role="investor", tenant_slug=resolved_slug)
    user_map = {
        str(item.get("username") or "").strip(): item
        for item in investor_users
        if str(item.get("username") or "").strip()
    }
    now_text = now_ts()
    message_content = str((broadcast_item or {}).get("content") or "").strip()
    thread_by_profile = {
        str(item.get("user_profile_id") or "").strip(): idx
        for idx, item in enumerate(threads)
        if str(item.get("type") or "").strip() == "fan_interaction" and str(item.get("user_profile_id") or "").strip()
    }
    touched_ids = set()
    for profile_id, user in user_map.items():
        if profile_id in thread_by_profile:
            idx = thread_by_profile[profile_id]
            thread = dict(threads[idx])
            messages = copy.deepcopy(thread.get("messages") or [])
            next_message_id = len(messages) + 1
            messages.append({
                "id": next_message_id,
                "sender": "kol",
                "content": message_content,
                "time": now_text,
                "type": "broadcast",
            })
            thread["messages"] = messages[-120:]
            thread["content"] = message_content
            thread["last_msg"] = f"【群发】{summarize_message_preview(message_content, limit=56)}"
            thread["time"] = "刚刚"
            thread["status"] = "已触达"
            thread["kol_unread"] = 0
            thread["user_unread"] = max(1, int(thread.get("user_unread") or 0) + 1)
            thread["last_sender"] = "kol"
            thread["last_message_type"] = "broadcast"
            threads[idx] = normalize_message_thread_item(thread, tenant, index=idx)
            touched_ids.add(profile_id)
    for profile_id, user in user_map.items():
        if profile_id in touched_ids:
            continue
        thread = build_broadcast_thread_for_user(tenant, user, broadcast_item)
        if thread:
            threads.insert(0, thread)
    _, latest_state = save_tenant_message_threads(resolved_slug, state, threads)
    return latest_state


def build_fan_thread_id(tenant_slug, username):
    normalized_tenant = str(tenant_slug or "").strip().lower() or "tenant"
    normalized_username = str(username or "").strip().lower() or "user"
    digest = hashlib.md5(f"{normalized_tenant}:{normalized_username}".encode("utf-8")).hexdigest()[:10]
    return f"{normalized_tenant}-thread-fan-{digest}"


def build_message_thread_for_user(user_profile, tenant, first_message=""):
    username = str((user_profile or {}).get("username") or "").strip()
    avatar = str((user_profile or {}).get("avatar") or "👤").strip() or "👤"
    membership = str((user_profile or {}).get("membership") or "粉丝").strip() or "粉丝"
    thread = {
        "id": build_fan_thread_id(tenant.get("slug"), username),
        "type": "fan_interaction",
        "name": username,
        "time": "刚刚" if first_message else "--",
        "content": str(first_message or "").strip(),
        "status": "待回复" if first_message else "待处理",
        "user_profile_id": username,
        "user_name": username,
        "user_avatar": avatar,
        "tier": membership,
        "last_msg": str(first_message or "").strip() or "欢迎交流",
        "unread": 1 if first_message else 0,
        "vip_only": False,
        "messages": [],
    }
    return normalize_message_thread_item(thread, tenant, index=0)


def find_message_thread_index(threads, thread_id=None, user_profile_id=None):
    normalized_thread_id = str(thread_id or "").strip()
    normalized_profile_id = str(user_profile_id or "").strip()
    for index, thread in enumerate(threads or []):
        if normalized_thread_id and str(thread.get("id") or "").strip() == normalized_thread_id:
            return index
        if normalized_profile_id and str(thread.get("user_profile_id") or "").strip() == normalized_profile_id:
            return index
    return -1


def save_tenant_message_threads(tenant_slug, state, threads):
    normalized_slug = str(tenant_slug or "").strip().lower() or get_default_tenant_slug()
    saved = update_tenant_message_center_state(normalized_slug, {
        "summary": state["summary"],
        "threads": threads[:60],
        "broadcasts": state["broadcasts"],
    })
    latest_tenant = get_tenant_by_slug(normalized_slug, saved) if saved else get_tenant_by_slug(normalized_slug)
    latest_state = resolve_tenant_message_center_state(latest_tenant, latest_tenant.get("message_center_state"))
    return latest_tenant, latest_state


def resolve_dm_actor(body=None, tenant_slug=""):
    raw = body if isinstance(body, dict) else {}
    sender_role = str(raw.get("sender_role") or request.args.get("sender_role") or "").strip().lower()
    sender_profile_id = str(raw.get("sender_profile_id") or request.args.get("sender_profile_id") or "").strip()
    sender_name = str(raw.get("sender_name") or request.args.get("sender_name") or sender_profile_id).strip()
    sender_avatar = str(raw.get("sender_avatar") or request.args.get("sender_avatar") or "👤").strip() or "👤"
    sender_membership = str(raw.get("sender_membership") or request.args.get("sender_membership") or "粉丝").strip() or "粉丝"
    resolved_tenant_slug = str(raw.get("tenant_slug") or tenant_slug or request.args.get("tenant") or get_default_tenant_slug()).strip().lower()
    if sender_role == "investor" and sender_profile_id:
        return {
            "role": "investor",
            "profile": {
                "username": sender_profile_id,
                "name": sender_name,
                "avatar": sender_avatar,
                "membership": sender_membership,
                "tenant": {"slug": resolved_tenant_slug},
            },
            "tenant_slug": resolved_tenant_slug,
        }
    if sender_role == "dav":
        return {
            "role": "dav",
            "profile": None,
            "tenant_slug": resolved_tenant_slug,
        }
    try:
        current_profile = get_current_demo_profile()
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        current_profile = None
    if current_profile:
        return {
            "role": str(current_profile.get("role") or "").strip(),
            "profile": current_profile,
            "tenant_slug": str((current_profile.get("tenant") or {}).get("slug") or resolved_tenant_slug).strip().lower(),
        }
    return {
        "role": "",
        "profile": None,
        "tenant_slug": resolved_tenant_slug,
    }


def normalize_portal_cms_config(source, tenant):
    defaults = default_portal_workspace(tenant)
    raw = source if isinstance(source, dict) else {}
    merged = _merge_site_config(copy.deepcopy(defaults), raw)
    hero = merged.get("hero") if isinstance(merged.get("hero"), dict) else {}
    cta = merged.get("cta") if isinstance(merged.get("cta"), dict) else {}
    contact = merged.get("contact") if isinstance(merged.get("contact"), dict) else {}
    custom_sections = merged.get("custom_sections") if isinstance(merged.get("custom_sections"), list) else []
    merged["hero"] = {
        "headline": str(hero.get("headline") or defaults["hero"]["headline"]).strip() or defaults["hero"]["headline"],
        "description": str(hero.get("description") or defaults["hero"]["description"]).strip() or defaults["hero"]["description"],
        "audience": str(hero.get("audience") or defaults["hero"]["audience"]).strip() or defaults["hero"]["audience"],
        "value_props": [
            str(item or "").strip()
            for item in (hero.get("value_props") if isinstance(hero.get("value_props"), list) else defaults["hero"]["value_props"])
        ][:3] or copy.deepcopy(defaults["hero"]["value_props"]),
    }
    while len(merged["hero"]["value_props"]) < 3:
        merged["hero"]["value_props"].append(defaults["hero"]["value_props"][len(merged["hero"]["value_props"])])
    merged["cta"] = {
        "primary_label": str(cta.get("primary_label") or defaults["cta"]["primary_label"]).strip() or defaults["cta"]["primary_label"],
        "secondary_label": str(cta.get("secondary_label") or defaults["cta"]["secondary_label"]).strip() or defaults["cta"]["secondary_label"],
    }
    normalized_sections = []
    for index, item in enumerate(custom_sections[:4]):
        if not isinstance(item, dict):
            continue
        fallback = defaults["custom_sections"][min(index, len(defaults["custom_sections"]) - 1)]
        normalized_sections.append(
            {
                "title": str(item.get("title") or fallback["title"]).strip() or fallback["title"],
                "body": str(item.get("body") or fallback["body"]).strip() or fallback["body"],
            }
        )
    if not normalized_sections:
        normalized_sections = copy.deepcopy(defaults["custom_sections"])
    merged["custom_sections"] = normalized_sections
    merged["contact"] = {
        "qr_title": str(contact.get("qr_title") or defaults["contact"]["qr_title"]).strip() or defaults["contact"]["qr_title"],
        "qr_hint": str(contact.get("qr_hint") or defaults["contact"]["qr_hint"]).strip() or defaults["contact"]["qr_hint"],
        "wechat": str(contact.get("wechat") or defaults["contact"]["wechat"]).strip() or defaults["contact"]["wechat"],
        "phone": str(contact.get("phone") or defaults["contact"]["phone"]).strip() or defaults["contact"]["phone"],
        "email": str(contact.get("email") or defaults["contact"]["email"]).strip() or defaults["contact"]["email"],
    }
    blocks = raw.get("page_blocks") if isinstance(raw.get("page_blocks"), list) else []
    normalized_blocks = []
    allowed_types = {"hero", "dashboard", "rich_text", "contact"}
    for index, block in enumerate(blocks[:8]):
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "").strip()
        if block_type not in allowed_types:
            continue
        normalized_blocks.append(
            {
                "id": str(block.get("id") or f"block_{index + 1}").strip() or f"block_{index + 1}",
                "type": block_type,
                "title": str(block.get("title") or "").strip(),
                "html": sanitize_portal_html(block.get("html") if block_type == "rich_text" else ""),
                "enabled": block.get("enabled") is not False,
            }
        )
    if not normalized_blocks:
        normalized_blocks = [
            {"id": "hero_block", "type": "hero", "title": "门户介绍", "html": "", "enabled": True},
            {"id": "dashboard_block", "type": "dashboard", "title": "固定 Dashboard", "html": "", "enabled": True},
            {
                "id": "copy_block_1",
                "type": "rich_text",
                "title": merged["custom_sections"][0]["title"],
                "html": sanitize_portal_html(
                    f"<h3>{html_escape(merged['custom_sections'][0]['title'])}</h3><p>{html_escape(merged['custom_sections'][0]['body'])}</p>"
                ),
                "enabled": True,
            },
            {
                "id": "copy_block_2",
                "type": "rich_text",
                "title": merged["custom_sections"][1]["title"],
                "html": sanitize_portal_html(
                    f"<h3>{html_escape(merged['custom_sections'][1]['title'])}</h3><p>{html_escape(merged['custom_sections'][1]['body'])}</p>"
                ),
                "enabled": True,
            },
            {"id": "contact_block", "type": "contact", "title": "联系方式", "html": "", "enabled": True},
        ]
    merged["page_blocks"] = normalized_blocks
    merged["draft_status"] = str(merged.get("draft_status") or defaults["draft_status"]).strip() or defaults["draft_status"]
    merged["published_status"] = str(merged.get("published_status") or defaults["published_status"]).strip() or defaults["published_status"]
    merged["last_published_at"] = str(merged.get("last_published_at") or defaults["last_published_at"]).strip() or defaults["last_published_at"]
    merged["theme_name"] = str(merged.get("theme_name") or defaults["theme_name"]).strip() or defaults["theme_name"]
    merged["summary"] = str(merged.get("summary") or defaults["summary"]).strip() or defaults["summary"]
    merged["modules"] = copy.deepcopy(defaults["modules"])
    merged["presets"] = copy.deepcopy(defaults["presets"])
    return merged


def update_tenant_portal_cms(tenant_slug, portal_cms):
    site_config = get_site_config()
    tenants = get_tenant_configs(site_config)
    updated = False
    for index, tenant in enumerate(tenants):
        if tenant.get("slug") != tenant_slug:
            continue
        tenants[index] = dict(tenant)
        tenants[index]["portal_cms"] = normalize_portal_cms_config(portal_cms, tenant)
        updated = True
        break
    if not updated:
        return None
    next_config = dict(site_config)
    next_config["tenants"] = tenants
    return save_site_config(next_config)


def default_tenant_knowledge_items(tenant):
    is_lisa = tenant["slug"] == "lisa"
    return [
        {
            "id": "kb-hk-internet-valuation",
            "type": "file",
            "title": "港股互联网估值框架",
            "source": "文件上传 · 12页 PDF",
            "source_detail": "来源：文件上传 · 港股互联网估值框架.pdf · 12页",
            "status": "可微调",
            "summary": "拆出回购强度、估值带与催化条件，已关联腾讯 / 美团 / 阿里。",
            "tags": ["估值框架", "港股互联网"],
            "raw_input": "原始材料重点包括：腾讯 / 美团 / 阿里的历史估值带、回购力度、自由现金流、财报兑现节奏，以及对行业竞争格局和监管预期的补充说明。",
            "key_points": ["回购强度直接影响估值修复斜率", "估值带必须结合利润兑现看，不单看 PS/PE", "催化条件要和财报、回购公告、南向资金一起验证"],
            "validation_nodes": ["财报后利润率是否兑现", "回购节奏是否持续", "南向资金是否继续净流入"],
            "sync_targets": ["租户知识队列", "知识专区", "Hermes 上下文", "港股互联网 Skill"],
            "tuning_focus": ["标题是否更贴近大V表达", "摘要是否保留关键判断", "关键要点是否足够结构化", "验证节点是否可直接复用到复盘"],
            "notes": "适合继续补公司层估值带、买回购和财报验证的先后顺序，以及哪些结论只适用于龙头公司。",
            "files": ["港股互联网估值框架.pdf"],
        },
        {
            "id": "kb-may-industry-call",
            "type": "voice",
            "title": "5月产业电话会录音整理",
            "source": "语音转写 · 28分钟",
            "source_detail": "来源：语音转写 · 产业电话会录音 · 28分钟",
            "status": "已同步 Hermes",
            "summary": "提炼固态电池、订单验证和量产节点，当前可直接被 Hermes 调用。",
            "tags": ["电话会", "新能源"],
            "raw_input": "原始语音中重点讨论了固态电池量产路径、下游车厂验证节奏、订单兑现的不确定项，以及短期市场情绪和长期产业趋势的区别。",
            "key_points": ["先分清产业趋势和交易情绪", "订单验证比概念热度更重要", "量产节点要拆成时间、客户、成本三层"],
            "validation_nodes": ["样品送测是否进入下一阶段", "订单是否从试产切换到量产", "成本曲线是否出现拐点"],
            "sync_targets": ["租户知识队列", "知识专区", "Hermes 上下文", "新能源相关复盘"],
            "tuning_focus": ["转写口语是否要收敛成书面结论", "关键判断是否已经拆成可复用节点", "风险边界是否写清", "是否适合直接进入复盘或 Hermes"],
            "notes": "建议把口语化表达进一步压缩成“观点 - 证据 - 验证节点 - 风险”四段式，便于 Hermes 后续直接调用。",
            "voice_minutes": 28,
        },
        {
            "id": "kb-semiconductor-cycle",
            "type": "url",
            "title": "半导体景气验证节点",
            "source": "网页 URL · 3篇行业资料",
            "source_detail": "来源：网页 URL · 3篇行业资料抓取摘要",
            "status": "同步中",
            "summary": "整理产能利用率、成熟制程价格与资本开支节奏，适合继续补充验证节点。",
            "tags": ["半导体", "网页资料"],
            "raw_input": "系统已抓取 3 篇行业网页资料，内容涉及成熟制程价格变化、产能利用率、资本开支收缩节奏，以及下游消费电子和服务器需求恢复情况。",
            "key_points": ["成熟制程价格是景气验证先行指标", "资本开支变化会领先反映景气预期", "不能只看单篇新闻，要归并成长期跟踪节点"],
            "validation_nodes": ["晶圆代工价格是否止跌", "主要厂商 capex 指引是否收缩", "下游需求恢复是否扩散到更多品类"],
            "sync_targets": ["租户知识队列", "知识专区", "Hermes 上下文"],
            "tuning_focus": ["网页摘要是否准确", "要点是否去噪", "验证节点是否可持续追踪", "是否需要补更多来源链接"],
            "notes": "当前更适合补充来源链接、删除噪音表述，并把验证节点改成可按月跟踪的版本。",
            "url": "https://example.com/semiconductor-cycle",
        },
        {
            "id": "kb-manual-thesis-note",
            "type": "manual",
            "title": is_lisa and "港股互联网判断口径手记" or "科技主线判断手记",
            "source": "纯文本编写",
            "source_detail": "来源：纯文本编写 · 186字",
            "status": "可微调",
            "summary": is_lisa and "手工整理港股互联网判断口径，保留估值、回购与财报验证顺序。" or "手工整理科技主线判断框架，保留景气、订单和验证节点顺序。",
            "tags": ["手动编写", "观点沉淀"],
            "raw_input": is_lisa and "观点：港股互联网先看回购与现金流，再看财报兑现，最后才看估值修复弹性。\n\n验证节点：回购节奏、利润率、南向资金。"
                or "观点：科技主线先看产业趋势和订单兑现，再看估值扩张是否有利润支撑。\n\n验证节点：订单、毛利率、资本开支。",
            "key_points": ["先写观点，再写证据", "验证节点要能持续跟踪", "风险边界要单独写清楚"],
            "validation_nodes": ["继续跟踪验证节点是否兑现"],
            "sync_targets": ["租户知识队列", "知识专区", "Hermes 上下文"],
            "tuning_focus": ["收敛表达", "补证据链", "补风险边界"],
            "notes": "适合直接从后台或 H5 手工录入，再继续细化成长期知识卡。",
            "body": is_lisa and "观点：港股互联网先看回购与现金流，再看财报兑现，最后才看估值修复弹性。\n\n验证节点：回购节奏、利润率、南向资金。"
                or "观点：科技主线先看产业趋势和订单兑现，再看估值扩张是否有利润支撑。\n\n验证节点：订单、毛利率、资本开支。",
        },
    ]


def normalize_knowledge_hub_config(source, tenant):
    defaults = {
        "summary": "知识库支持语音、文件、URL 和纯文本四种入口；历史内容允许点开弹框继续微调，修改后会重新同步到知识专区和 Hermes 上下文。",
        "items": default_tenant_knowledge_items(tenant),
    }
    raw = source if isinstance(source, dict) else {}
    summary = str(raw.get("summary") or defaults["summary"]).strip() or defaults["summary"]
    items = raw.get("items") if isinstance(raw.get("items"), list) else defaults["items"]
    normalized_items = []
    for index, item in enumerate(items[:80]):
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "manual").strip().lower()
        if item_type not in {"voice", "file", "url", "manual"}:
            item_type = "manual"
        title = str(item.get("title") or f"知识条目 {index + 1}").strip() or f"知识条目 {index + 1}"
        summary_text = str(item.get("summary") or "").strip()
        raw_input = str(item.get("raw_input") or item.get("body") or "").strip()
        notes = str(item.get("notes") or "").strip()
        processing_mode = normalize_knowledge_processing_mode(
            item.get("processing_mode"),
            item.get("skip_ai_processing") if "skip_ai_processing" in item else None,
        )
        processed = item.get("processed_content") if isinstance(item.get("processed_content"), dict) else {}
        queued_at = str(item.get("queued_at") or item.get("time") or "").strip()
        synced_at = str(item.get("synced_at") or "").strip()
        failed_at = str(item.get("failed_at") or "").strip()
        normalized_items.append({
            "id": str(item.get("id") or f"kb-{slugify_code(title, 'item')}-{index + 1}").strip() or f"kb-item-{index + 1}",
            "type": item_type,
            "title": title,
            "source": str(item.get("source") or "").strip() or ("纯文本编写" if item_type == "manual" else title),
            "source_detail": str(item.get("source_detail") or "").strip(),
            "status": str(item.get("status") or "可微调").strip() or "可微调",
            "summary": summary_text,
            "tags": [str(tag).strip() for tag in (item.get("tags") if isinstance(item.get("tags"), list) else []) if str(tag).strip()][:8],
            "raw_input": raw_input,
            "raw_html": str(item.get("raw_html") or "").strip(),
            "key_points": [str(point).strip() for point in (item.get("key_points") if isinstance(item.get("key_points"), list) else []) if str(point).strip()][:8],
            "validation_nodes": [str(point).strip() for point in (item.get("validation_nodes") if isinstance(item.get("validation_nodes"), list) else []) if str(point).strip()][:8],
            "sync_targets": [str(point).strip() for point in (item.get("sync_targets") if isinstance(item.get("sync_targets"), list) else []) if str(point).strip()][:8],
            "tuning_focus": [str(point).strip() for point in (item.get("tuning_focus") if isinstance(item.get("tuning_focus"), list) else []) if str(point).strip()][:8],
            "notes": notes,
            "notes_html": str(item.get("notes_html") or "").strip(),
            "files": [str(name).strip() for name in (item.get("files") if isinstance(item.get("files"), list) else []) if str(name).strip()][:12],
            "url": str(item.get("url") or "").strip(),
            "voice_minutes": item.get("voice_minutes") if isinstance(item.get("voice_minutes"), int) else None,
            "parse_meta": copy.deepcopy(item.get("parse_meta")) if isinstance(item.get("parse_meta"), (dict, list)) else None,
            "processing_mode": processing_mode,
            "processed_content": copy.deepcopy(processed) if processed else build_knowledge_processing_result(
                raw_input,
                processing_mode=processing_mode,
                source_type=item_type,
                title=title,
                source_detail=str(item.get("source_detail") or "").strip(),
            ),
            "graph_profile": copy.deepcopy(item.get("graph_profile")) if isinstance(item.get("graph_profile"), dict) else {},
            "sync_status": build_knowledge_sync_status(
                item.get("status"),
                item.get("sync_targets") if isinstance(item.get("sync_targets"), list) else None,
                queued_at=queued_at,
                synced_at=synced_at,
                failed_at=failed_at,
            ),
            "queued_at": queued_at,
            "synced_at": synced_at,
            "failed_at": failed_at,
            "body": str(item.get("body") or raw_input).strip(),
        })
    if not normalized_items:
        normalized_items = copy.deepcopy(defaults["items"])
    return {"summary": summary, "items": normalized_items}


def resolve_tenant_knowledge_hub(tenant, config=None):
    return normalize_knowledge_hub_config(config if isinstance(config, dict) else tenant.get("knowledge_hub_config"), tenant)


def update_tenant_knowledge_hub_config(tenant_slug, knowledge_hub_config):
    site_config = get_site_config()
    tenants = get_tenant_configs(site_config)
    updated = False
    for index, tenant in enumerate(tenants):
        if tenant.get("slug") != tenant_slug:
            continue
        tenants[index] = dict(tenant)
        tenants[index]["knowledge_hub_config"] = normalize_knowledge_hub_config(knowledge_hub_config, tenant)
        updated = True
        break
    if not updated:
        return None
    next_config = dict(site_config)
    next_config["tenants"] = tenants
    return save_site_config(next_config)


def get_dashboard_card_target(layout):
    layout_key = str(layout or "").strip().lower()
    if layout_key in {"3x3", "2x3"}:
        return 6
    if layout_key in {"4x4", "2x4", "4x2"}:
        return 8
    if layout_key in {"2x5", "5x2"}:
        return 10
    return 4


def normalize_dashboard_layout(layout):
    layout_key = str(layout or "").strip().lower()
    if layout_key == "3x3":
        return "2x3"
    if layout_key == "4x4":
        return "4x2"
    if layout_key == "2x4":
        return "4x2"
    if layout_key == "2x5":
        return "5x2"
    if layout_key in {"2x2", "2x3", "4x2", "5x2"}:
        return layout_key
    return "2x2"


def normalize_dashboard_mode(mode):
    mode_key = str(mode or "").strip().lower()
    if mode_key in {"market", "industry", "signal-stock"}:
        return mode_key
    return "market"


def get_dashboard_component_library(mode):
    mode_key = normalize_dashboard_mode(mode)
    library = {
        "market": [
            {"id": "market_breadth", "label": "广度改善分", "source": "全市场行情库", "metric": "上涨/下跌家数、站上MA20占比、新高-新低差", "window": "1D", "aggregation": "0-100评分", "default_weight": 0.35, "default_operator": "base", "default_selected": True},
            {"id": "northbound_flow", "label": "资金回流分", "source": "北向/南向资金库", "metric": "净流入占成交比、3日累计、连续净流入天数", "window": "1D / 3D", "aggregation": "0-100评分", "default_weight": 0.25, "default_operator": "+", "default_selected": True},
            {"id": "turnover_structure", "label": "主线参与分", "source": "成交结构库", "metric": "主线成交占比、5日变化、拥挤度惩罚", "window": "1D / 5D", "aggregation": "0-100评分", "default_weight": 0.25, "default_operator": "+", "default_selected": True},
            {"id": "style_rotation", "label": "防御压力分", "source": "风格因子库", "metric": "银行/红利相对成长超额、低波ETF净流入", "window": "1D / 5D", "aggregation": "0-100评分", "default_weight": 0.15, "default_operator": "-", "default_selected": True},
            {"id": "policy_heat", "label": "政策温度参考分", "source": "政策新闻流", "metric": "宏观政策热度与边际变化", "window": "3D", "aggregation": "辅助评分", "default_weight": 0.1, "default_operator": "+", "default_selected": False},
        ],
        "industry": [
            {"id": "industry_orders", "label": "订单景气分", "source": "行业指标库", "metric": "新增订单同比、在手订单覆盖、开工率", "window": "1W / 1M", "aggregation": "0-100评分", "default_weight": 0.30, "default_operator": "base", "default_selected": True},
            {"id": "industry_price", "label": "价格景气分", "source": "产业链价格库", "metric": "产品价格指数、价差、提价持续性", "window": "1W / 1M", "aggregation": "0-100评分", "default_weight": 0.25, "default_operator": "+", "default_selected": True},
            {"id": "industry_inventory", "label": "库存去化分", "source": "行业库存库", "metric": "库存天数、主动/被动补库、去库斜率", "window": "1M", "aggregation": "0-100评分", "default_weight": 0.20, "default_operator": "+", "default_selected": True},
            {"id": "industry_policy", "label": "政策催化分", "source": "行业新闻流", "metric": "政策热度、落地级别、持续性", "window": "5D / 20D", "aggregation": "0-100评分", "default_weight": 0.15, "default_operator": "+", "default_selected": True},
            {"id": "industry_capex", "label": "资本开支确认分", "source": "财报与经营数据", "metric": "Capex指引、扩产计划、设备招标", "window": "1Q", "aggregation": "0-100评分", "default_weight": 0.10, "default_operator": "+", "default_selected": True},
        ],
        "signal-stock": [
            {"id": "leader_strength", "label": "龙头强度分", "source": "个股行情库", "metric": "相对行业超额收益、回撤控制、成交额排名", "window": "5D / 20D", "aggregation": "0-100评分", "default_weight": 0.35, "default_operator": "base", "default_selected": True},
            {"id": "earnings_delivery", "label": "业绩兑现分", "source": "财报与预期库", "metric": "营收/利润兑现率、指引上修、订单兑现", "window": "1Q", "aggregation": "0-100评分", "default_weight": 0.30, "default_operator": "+", "default_selected": True},
            {"id": "support_flow", "label": "资金承接分", "source": "盘口与成交数据", "metric": "回调缩量、尾盘净流入、换手承接", "window": "3D / 5D", "aggregation": "0-100评分", "default_weight": 0.20, "default_operator": "+", "default_selected": True},
            {"id": "valuation_band", "label": "估值安全分", "source": "估值与财报库", "metric": "PE/PS分位、PEG、相对历史分位", "window": "1Q / 3Y", "aggregation": "0-100评分", "default_weight": 0.15, "default_operator": "+", "default_selected": True},
            {"id": "catalyst_window", "label": "催化窗口参考分", "source": "公司新闻流", "metric": "新品、财报、订单公告、政策催化时点", "window": "10D / 30D", "aggregation": "辅助评分", "default_weight": 0.10, "default_operator": "+", "default_selected": False},
        ],
    }
    return copy.deepcopy(library.get(mode_key) or library["market"])


def build_default_dashboard_components(mode):
    components = []
    defaults = [item for item in get_dashboard_component_library(mode) if item.get("default_selected", True)]
    for index, item in enumerate(defaults[:5]):
        components.append(
            {
                "id": item["id"],
                "label": item["label"],
                "source": item["source"],
                "metric": item["metric"],
                "window": item["window"],
                "aggregation": item["aggregation"],
                "weight": item["default_weight"],
                "operator": item.get("default_operator") or ("base" if index == 0 else "+"),
            }
        )
    return components


def normalize_dashboard_components(raw_components, mode):
    library = get_dashboard_component_library(mode)
    library_map = {item["id"]: item for item in library}
    source_list = raw_components if isinstance(raw_components, list) else []
    if not source_list:
        source_list = build_default_dashboard_components(mode)
    components = []
    for index, raw in enumerate(source_list[:6]):
        item = raw if isinstance(raw, dict) else {}
        component_id = str(item.get("id") or item.get("componentId") or "").strip()
        template = library_map.get(component_id) or library[min(index, len(library) - 1)]
        try:
            weight = round(float(item.get("weight") if item.get("weight") is not None else template.get("default_weight", 1.0)), 2)
        except (TypeError, ValueError):
            weight = float(template.get("default_weight", 1.0))
        components.append(
            {
                "id": template["id"],
                "label": str(item.get("label") or template["label"]).strip() or template["label"],
                "source": str(item.get("source") or template["source"]).strip() or template["source"],
                "metric": str(item.get("metric") or template["metric"]).strip() or template["metric"],
                "window": str(item.get("window") or template["window"]).strip() or template["window"],
                "aggregation": str(item.get("aggregation") or template["aggregation"]).strip() or template["aggregation"],
                "weight": weight,
                "operator": str(item.get("operator") or template.get("default_operator") or ("base" if index == 0 else "+")).strip() or ("base" if index == 0 else "+"),
            }
        )
    return components


def build_dashboard_formula_text(mode, components):
    items = components if isinstance(components, list) else []
    chunks = []
    for index, item in enumerate(items):
        label = str(item.get("label") or "").strip() or f"组件 {index + 1}"
        operator = str(item.get("operator") or "").strip()
        weight = item.get("weight")
        try:
            weight_value = float(weight)
        except (TypeError, ValueError):
            weight_value = 1.0
        weight_text = "" if abs(weight_value - 1.0) < 0.01 else f" x {weight_value:g}"
        prefix = ""
        if index > 0 and operator and operator != "base":
            prefix = f" {operator} "
        chunks.append(f"{prefix}{label}{weight_text}")
    formula_text = "".join(chunks).strip()
    if formula_text:
        return formula_text
    defaults = {
        "market": "总分 = 35%广度改善分 + 25%资金回流分 + 25%主线参与分 - 15%防御压力分",
        "industry": "总分 = 30%订单景气分 + 25%价格景气分 + 20%库存去化分 + 15%政策催化分 + 10%资本开支确认分",
        "signal-stock": "总分 = 35%龙头强度分 + 30%业绩兑现分 + 20%资金承接分 + 15%估值安全分",
    }
    return defaults.get(normalize_dashboard_mode(mode), defaults["market"])


def build_dashboard_sources_summary(mode, components):
    seen = set()
    sources = []
    for item in (components if isinstance(components, list) else []):
        source = str(item.get("source") or "").strip()
        if source and source not in seen:
            seen.add(source)
            sources.append(source)
    if sources:
        return sources
    return [item["source"] for item in get_dashboard_component_library(mode)[:3]]


def infer_dashboard_card_mode(source, fallback="market"):
    raw = source if isinstance(source, dict) else {}
    explicit = raw.get("mode") or raw.get("segmentId")
    if explicit:
        return normalize_dashboard_mode(explicit)
    text = " ".join(
        [
            str(raw.get("name") or "").strip(),
            str(raw.get("title") or "").strip(),
            str(raw.get("prompt") or "").strip(),
            str(raw.get("assessment") or "").strip(),
            str(raw.get("hint") or "").strip(),
        ]
    )
    if re.search(r"行业景气|行业订单|价格景气|库存节奏|景气验证|资本开支|竞争格局", text):
        return "industry"
    if re.search(r"信号个股|龙头强度|业绩兑现|相对行业|催化临近|资金承接|估值位置", text):
        return "signal-stock"
    if re.search(r"风险偏好|流动性|政策温度|市场广度|风格轮动|波动压力|主线热度", text):
        return "market"
    return normalize_dashboard_mode(fallback)


def ensure_dashboard_layout_for_card_count(card_count):
    count = max(0, int(card_count or 0))
    if count > 8:
        return "5x2"
    if count > 6:
        return "4x2"
    if count > 4:
        return "2x3"
    return "2x2"


def build_smart_indicator_algorithm_detail(prompt_text, selected_indicators):
    selected_items = normalize_selected_indicator_refs(selected_indicators)
    source_names = [item.get("indicator_name") or item.get("indicator_code") for item in selected_items]
    source_text = " / ".join(source_names) if source_names else "未选择底层指标"
    prompt_value = str(prompt_text or "").strip() or "未填写提示词"
    return f"引用指标：{source_text}。计算口径：{prompt_value}。系统会根据这段提示词自动生成内部公式，并按最新底层指标值实时计算结果。"


def build_smart_indicator_interpretation(indicator_name, prompt_text, selected_indicators, current_value, unit=""):
    name = str(indicator_name or "该智能指标").strip() or "该智能指标"
    prompt_value = str(prompt_text or "").strip() or "当前提示词"
    value_text = str(current_value or "--").strip() or "--"
    unit_text = str(unit or "").strip()
    display_value = f"{value_text}{unit_text}" if unit_text else value_text
    selected_items = normalize_selected_indicator_refs(selected_indicators)
    source_names = [item.get("indicator_name") or item.get("indicator_code") for item in selected_items]
    if source_names:
        return f"{name} 当前值为 {display_value}，由 {' / '.join(source_names)} 按“{prompt_value}”口径计算，适合用来看相对强弱和阶段变化。"
    return f"{name} 当前值为 {display_value}，系统会按“{prompt_value}”这条口径持续更新结果。"


def build_dashboard_base_indicator_options(tenant=None):
    hub = build_indicator_hub(tenant=tenant, admin_view=False)
    options = []
    for item in (hub.get("items") or []):
        numeric_value = item.get("numeric_value")
        if numeric_value is None:
            continue
        options.append(
            {
                "indicator_code": item.get("id"),
                "indicator_name": item.get("name"),
                "category": item.get("category") or "未分类指标",
                "value": item.get("value") or "--",
                "numeric_value": numeric_value,
                "unit": item.get("unit") or "",
                "source_type": item.get("source_type") or "",
                "source_type_label": item.get("source_type_label") or "",
            }
        )
    return options


def build_tenant_smart_indicator_tag_catalog(tenant=None):
    base_indicators = build_dashboard_base_indicator_options(tenant)
    watchlist_details = gen_watchlist_details()
    tags = []
    seen = set()
    for item in base_indicators:
        indicator_code = str(item.get("indicator_code") or "").strip()
        if not indicator_code:
            continue
        tag_code = f"indicator:{indicator_code}"
        seen.add(tag_code)
        tags.append(
            {
                "tag_code": tag_code,
                "label": item.get("indicator_name") or indicator_code,
                "tag_type": "indicator",
                "category": item.get("category") or "指标",
                "subtitle": item.get("source_type_label") or item.get("source_type") or "基础指标",
                "value": item.get("value") or "--",
                "unit": item.get("unit") or "",
                "selected_indicators": [
                    {
                        "indicator_code": indicator_code,
                        "indicator_name": item.get("indicator_name") or indicator_code,
                    }
                ],
            }
        )
    for detail in watchlist_details.values():
        stock_code = str(detail.get("code") or "").strip().upper()
        stock_name = str(detail.get("name") or stock_code).strip() or stock_code
        related_ids = detail.get("related_indicator_ids") if isinstance(detail.get("related_indicator_ids"), list) else []
        related_names = detail.get("related_indicator_names") if isinstance(detail.get("related_indicator_names"), list) else []
        selected_indicators = normalize_selected_indicator_refs(
            [
                {
                    "indicator_code": indicator_code,
                    "indicator_name": related_names[index] if index < len(related_names) else indicator_code,
                }
                for index, indicator_code in enumerate(related_ids)
                if indicator_code
            ]
        )
        if not selected_indicators:
            continue
        tag_code = f"watchlist:{stock_code}"
        if tag_code in seen:
            continue
        seen.add(tag_code)
        tags.append(
            {
                "tag_code": tag_code,
                "label": stock_name,
                "tag_type": "watchlist",
                "category": detail.get("industry") or "自选股",
                "subtitle": "自选股标签",
                "value": f"{detail.get('price', '--')}",
                "unit": "",
                "stock_code": stock_code,
                "selected_indicators": selected_indicators,
            }
        )
    return tags


def normalize_selected_tag_refs(raw_selected_tags):
    items = raw_selected_tags if isinstance(raw_selected_tags, list) else []
    normalized = []
    seen = set()
    for raw in items:
        if isinstance(raw, dict):
            tag_code = str(raw.get("tag_code") or raw.get("code") or "").strip()
            label = str(raw.get("label") or raw.get("name") or tag_code).strip() or tag_code
        else:
            tag_code = str(raw or "").strip()
            label = tag_code
        if not tag_code or tag_code in seen:
            continue
        seen.add(tag_code)
        normalized.append({"tag_code": tag_code, "label": label})
    return normalized


def resolve_smart_indicator_selected_refs(tenant, payload):
    body = payload if isinstance(payload, dict) else {}
    selected = normalize_selected_indicator_refs(body.get("selected_indicators") or body.get("selected_indicator_codes") or [])
    tag_catalog = {
        item.get("tag_code"): item
        for item in build_tenant_smart_indicator_tag_catalog(tenant)
        if item.get("tag_code")
    }
    for tag in normalize_selected_tag_refs(body.get("selected_tags") or body.get("selected_tag_codes") or []):
        tag_item = tag_catalog.get(tag["tag_code"])
        if tag_item:
            selected.extend(tag_item.get("selected_indicators") or [])
    selected = normalize_selected_indicator_refs(selected)
    indicator_name_map = {
        item.get("id"): item.get("name")
        for item in (build_indicator_hub(tenant=tenant, admin_view=False).get("items") or [])
        if item.get("id") and item.get("name")
    }
    return [
        {
            "indicator_code": item["indicator_code"],
            "indicator_name": indicator_name_map.get(item["indicator_code"]) or item.get("indicator_name") or item["indicator_code"],
        }
        for item in selected
    ]


def derive_smart_indicator_name(prompt_text, selected_indicators):
    prompt_value = re.sub(r"\s+", " ", str(prompt_text or "").strip())
    selected_items = normalize_selected_indicator_refs(selected_indicators)
    source_names = [item.get("indicator_name") or item.get("indicator_code") for item in selected_items]
    if source_names:
        if len(source_names) == 1:
            return f"{source_names[0]}智能指标"
        return f"{source_names[0]}组合指标"
    if prompt_value:
        compact = prompt_value.replace("【", "").replace("】", "").replace(" ", "")
        compact = compact[:14]
        return f"{compact}指标" if compact else "智能指标"
    return "智能指标"


def build_tenant_smart_indicator_catalog(tenant=None):
    hub = build_indicator_hub(tenant=tenant, admin_view=False)
    items = []
    for item in (hub.get("smart_items") or []):
        items.append(
            {
                "indicator_code": item.get("id"),
                "indicator_name": item.get("name"),
                "tenant_slug": item.get("tenant_slug") or "",
                "category": item.get("category") or "智能指标",
                "value": item.get("value") or "--",
                "numeric_value": item.get("numeric_value"),
                "unit": item.get("unit") or "",
                "assessment": item.get("assessment") or "",
                "status": item.get("status") or "attention",
                "alert": item.get("alert") or "",
                "prompt_text": item.get("prompt_text") or "",
                "formula_js": item.get("formula_js") or "",
                "algorithm_detail": item.get("description") or build_smart_indicator_algorithm_detail(item.get("prompt_text"), item.get("selected_indicators")),
                "interpretation": item.get("assessment") or build_smart_indicator_interpretation(item.get("name"), item.get("prompt_text"), item.get("selected_indicators"), item.get("value"), item.get("unit")),
                "selected_indicators": copy.deepcopy(item.get("selected_indicators") or []),
                "display_order": int(item.get("display_order") or 0),
                "last_updated": item.get("last_updated") or "",
            }
        )
    return sorted(items, key=lambda current: (current.get("display_order", 0), current.get("indicator_name") or ""))


def build_fund_dashboard_card_from_indicator(indicator_item, index=0):
    item = indicator_item if isinstance(indicator_item, dict) else {}
    selected_indicators = normalize_selected_indicator_refs(item.get("selected_indicators"))
    source_names = [source.get("indicator_name") for source in selected_indicators if source.get("indicator_name")]
    title = str(item.get("indicator_name") or item.get("name") or f"智能指标 {index + 1}").strip() or f"智能指标 {index + 1}"
    assessment = str(item.get("assessment") or item.get("alert") or "当前按自定义公式计算。").strip() or "当前按自定义公式计算。"
    return {
        "indicatorCode": str(item.get("indicator_code") or item.get("id") or "").strip(),
        "name": title,
        "value": str(item.get("value") or "--").strip() or "--",
        "unit": str(item.get("unit") or "").strip(),
        "assessment": assessment,
        "interpretation": str(item.get("interpretation") or assessment).strip() or assessment,
        "algorithmDetail": str(item.get("algorithm_detail") or item.get("description") or build_smart_indicator_algorithm_detail(item.get("prompt_text"), selected_indicators)).strip(),
        "status": str(item.get("status") or "attention").strip() or "attention",
        "alert": str(item.get("alert") or "").strip(),
        "prompt": str(item.get("prompt_text") or "").strip(),
        "sources": source_names,
        "selectedIndicators": selected_indicators,
        "updatedAt": str(item.get("last_updated") or item.get("updatedAt") or "").strip(),
        "isEmpty": False,
    }


def build_empty_fund_dashboard_card(index=0):
    return {
        "indicatorCode": "",
        "name": f"待添加智能指标 {index + 1}",
        "value": "--",
        "unit": "",
        "assessment": "点击加号创建新的智能指标。",
        "interpretation": "",
        "algorithmDetail": "",
        "status": "attention",
        "alert": "",
        "prompt": "",
        "sources": [],
        "selectedIndicators": [],
        "updatedAt": "",
        "isEmpty": True,
    }


def build_new_smart_indicator_code(tenant_slug):
    """Return a unique code for a newly created smart indicator.

    Names are display labels, not primary keys: two independent indicators may
    legitimately use the same name and must remain independently placeable on
    a dashboard.
    """
    tenant_code = slugify_code(tenant_slug, "tenant")
    timestamp = now_ts_ms().replace("-", "").replace(" ", "_").replace(":", "").replace(".", "")
    return f"{tenant_code}_smart_{timestamp}"


def is_empty_fund_dashboard_card_ref(item):
    card = item if isinstance(item, dict) else {}
    if card.get("isEmpty"):
        return True
    indicator_code = slugify_code(card.get("indicatorCode") or card.get("indicator_code"), "")
    name = str(card.get("name") or "").strip()
    return not indicator_code and bool(re.fullmatch(r"待添加智能指标\s*\d*", name))


def _run_smart_indicator_agent_workflow(tenant_slug, payload, persist=False):
    workflow_definition = build_default_smart_indicator_workflow_definition()
    tenant = get_tenant_by_slug(tenant_slug)
    body = payload if isinstance(payload, dict) else {}
    existing = get_indicator_definition(body.get("indicator_code")) if body.get("indicator_code") else None

    def _smart_input_executor(state, runtime, node, upstream):
        return {
            "detail": "已接收指标引用、提示词和展示配置。",
            "context_preview": {
                "persist_mode": bool(runtime.get("persist")),
                "has_existing": bool(runtime.get("existing")),
            },
        }

    def _smart_resolve_executor(state, runtime, node, upstream):
        selected_indicators = resolve_smart_indicator_selected_refs(runtime.get("tenant"), runtime.get("body"))
        if not selected_indicators:
            raise ValueError("selected_indicators_required")
        prompt_text = str((runtime.get("body") or {}).get("prompt_text") or (runtime.get("body") or {}).get("prompt") or "").strip()
        if not prompt_text:
            raise ValueError("prompt_text_required")
        indicator_name = str((runtime.get("body") or {}).get("indicator_name") or (runtime.get("body") or {}).get("name") or "").strip() or derive_smart_indicator_name(prompt_text, selected_indicators)
        algorithm_detail = str((runtime.get("body") or {}).get("description") or "").strip() or build_smart_indicator_algorithm_detail(prompt_text, selected_indicators)
        return {
            "detail": "已完成指标引用解析和提示词校验。",
            "state_updates": {
                "selected_indicators": selected_indicators,
                "prompt_text": prompt_text,
                "indicator_name": indicator_name,
                "algorithm_detail": algorithm_detail,
                "category": str((runtime.get("body") or {}).get("category") or "大V自定义指标").strip() or "大V自定义指标",
                "unit": str((runtime.get("body") or {}).get("unit") or "").strip(),
            },
            "context_preview": {
                "indicator_count": len(selected_indicators),
                "indicator_name": indicator_name,
            },
        }

    def _smart_compile_executor(state, runtime, node, upstream):
        provided_formula_js = str((runtime.get("body") or {}).get("formula_js") or "").strip()
        if provided_formula_js:
            generated = {
                "formula_js": validate_smart_indicator_js(provided_formula_js, state.get("selected_indicators") or []),
                "generator": "preview_confirmed",
                "llm_used": False,
            }
        else:
            generated = generate_smart_indicator_js(
                state.get("indicator_name") or "",
                state.get("prompt_text") or "",
                state.get("selected_indicators") or [],
                tenant_slug=runtime.get("tenant_slug") or "",
            )
        return {
            "detail": f"已完成公式编译：{generated.get('generator') or 'unknown'}。",
            "state_updates": {"generated_formula_meta": generated},
            "context_preview": {
                "llm_used": bool(generated.get("llm_used")),
                "generator": generated.get("generator") or "",
            },
        }

    def _smart_preview_executor(state, runtime, node, upstream):
        latest_map = {
            row["indicator_code"]: dict(row)
            for row in get_db().execute("SELECT * FROM indicator_latest_values").fetchall()
        }
        try:
            numeric_value = evaluate_smart_indicator_formula_js(
                (state.get("generated_formula_meta") or {}).get("formula_js"),
                state.get("selected_indicators") or [],
                latest_map,
            )
            value = f"{numeric_value:.4f}".rstrip("0").rstrip(".")
        except Exception:
            numeric_value = None
            value = "--"
        interpretation = build_smart_indicator_interpretation(
            state.get("indicator_name") or "",
            state.get("prompt_text") or "",
            state.get("selected_indicators") or [],
            value,
            state.get("unit") or "",
        )
        preview = {
            "indicator_code": "",
            "indicator_name": state.get("indicator_name") or "",
            "category": state.get("category") or "大V自定义指标",
            "value": value,
            "numeric_value": numeric_value,
            "unit": state.get("unit") or "",
            "assessment": interpretation,
            "interpretation": interpretation,
            "algorithm_detail": state.get("algorithm_detail") or "",
            "prompt_text": state.get("prompt_text") or "",
            "selected_indicators": copy.deepcopy(state.get("selected_indicators") or []),
            "updated_at": now_ts(),
            "formula_js": (state.get("generated_formula_meta") or {}).get("formula_js") or "",
            "formula_meta": copy.deepcopy(state.get("generated_formula_meta") or {}),
        }
        return {
            "detail": "已完成智能指标预览求值。",
            "state_updates": {"preview_result": preview},
            "context_preview": {"value": value, "has_numeric_value": numeric_value is not None},
        }

    def _smart_persist_executor(state, runtime, node, upstream):
        if not runtime.get("persist"):
            return {
                "status": "skipped",
                "detail": "当前为预览模式，未执行持久化。",
                "output": copy.deepcopy(state.get("preview_result") or {}),
                "state_key": "final_result",
            }
        save_payload = {
            **(runtime.get("existing") or {}),
            **(runtime.get("body") or {}),
            "tenant_slug": runtime.get("tenant_slug") or "",
            "indicator_name": state.get("indicator_name") or "",
            "category": state.get("category") or "大V自定义指标",
            "description": state.get("algorithm_detail") or "",
            "owner": ((runtime.get("tenant") or {}).get("advisor") or "大V"),
            "source_type": "smart",
            "source_type_label": "智能指标",
            "provider": "LLM / Prompt Formula",
            "status_hint": str((runtime.get("body") or {}).get("status_hint") or "good").strip() or "good",
            "assessment_template": str((runtime.get("body") or {}).get("assessment_template") or build_smart_indicator_interpretation(state.get("indicator_name"), state.get("prompt_text"), state.get("selected_indicators"), "实时值", (runtime.get("body") or {}).get("unit") or "")).strip(),
            "alert_template": str((runtime.get("body") or {}).get("alert_template") or "").strip(),
            "prompt_text": state.get("prompt_text") or "",
            "formula_js": (state.get("generated_formula_meta") or {}).get("formula_js") or "",
            "selected_indicators": copy.deepcopy(state.get("selected_indicators") or []),
            "display_order": int((runtime.get("body") or {}).get("display_order") or 0),
            "watchers": ["大V工作台", "H5 Dashboard", "租户门户"],
            "display_config": {"show_in_h5": True, "show_in_workbench": True},
            "enabled": (runtime.get("body") or {}).get("enabled", True),
        }
        # Only an explicit indicator_code means an edit. New definitions need
        # their own identity even when their display name matches an old one.
        if not runtime.get("existing"):
            save_payload["indicator_code"] = build_new_smart_indicator_code(runtime.get("tenant_slug") or "")
        definition = save_indicator_definition(
            {
                **save_payload,
            }
        )
        latest_snapshot = save_smart_indicator_latest_snapshot(definition)
        saved_site_config = None
        if (runtime.get("body") or {}).get("add_to_dashboard", True):
            saved_site_config = append_smart_indicator_to_dashboard(
                runtime.get("tenant_slug") or "",
                definition["indicator_code"],
                title=str((runtime.get("body") or {}).get("dashboard_title") or "智能指标 Dashboard").strip() or "智能指标 Dashboard",
                layout=(runtime.get("body") or {}).get("layout"),
                publisher=((runtime.get("tenant") or {}).get("advisor") or "大V"),
            )
        latest_tenant = get_tenant_by_slug(runtime.get("tenant_slug") or "", saved_site_config) if saved_site_config else runtime.get("tenant")
        result = {
            "definition": get_indicator_definition(definition["indicator_code"]),
            "latest_snapshot": latest_snapshot,
            "tenant": latest_tenant,
            "formula_meta": copy.deepcopy(state.get("generated_formula_meta") or {}),
        }
        return {
            "detail": "已保存智能指标定义并同步 Dashboard。",
            "output": result,
            "state_key": "final_result",
            "context_preview": {"indicator_code": definition.get("indicator_code") or "", "dashboard_sync": bool((runtime.get("body") or {}).get("add_to_dashboard", True))},
        }

    execution = run_declared_agent_workflow(
        workflow_definition,
        runtime={
            "tenant_slug": tenant_slug,
            "tenant": tenant,
            "body": body,
            "existing": existing,
            "persist": bool(persist),
        },
        executor_registry={
            "smart_indicator_input": _smart_input_executor,
            "smart_indicator_resolve": _smart_resolve_executor,
            "smart_indicator_compile": _smart_compile_executor,
            "smart_indicator_preview": _smart_preview_executor,
            "smart_indicator_publish": _smart_persist_executor,
        },
    )
    final_result = execution["state"].get("final_result") or {}
    if not persist:
        final_result = dict(final_result)
        final_result["workflow_meta"] = build_declared_agent_workflow_meta(
            workflow_definition,
            extras={"last_execution_steps": copy.deepcopy(execution.get("node_results") or {})},
        )
    else:
        final_result = dict(final_result)
        final_result["workflow_meta"] = build_declared_agent_workflow_meta(
            workflow_definition,
            extras={"last_execution_steps": copy.deepcopy(execution.get("node_results") or {})},
        )
    return final_result


def build_smart_indicator_preview(tenant_slug, payload):
    return _run_smart_indicator_agent_workflow(tenant_slug, payload, persist=False)


def build_default_fund_dashboard_cards(tenant, layout="2x2"):
    target_count = get_dashboard_card_target(layout)
    smart_items = build_tenant_smart_indicator_catalog(tenant)[:target_count]
    cards = [build_fund_dashboard_card_from_indicator(item, index=index) for index, item in enumerate(smart_items)]
    while len(cards) < target_count:
        cards.append(build_empty_fund_dashboard_card(len(cards)))
    return cards


def normalize_fund_dashboard_card_refs(raw_cards, layout):
    target_count = get_dashboard_card_target(layout)
    items = raw_cards if isinstance(raw_cards, list) else []
    # Dashboard cards are positional.  Empty entries must remain in the list so
    # a card deliberately placed in (for example) slot 5 is never compacted
    # into an earlier slot during a save/load round trip.
    normalized = []
    seen_codes = set()
    for index in range(target_count):
        item = items[index] if index < len(items) and isinstance(items[index], dict) else {}
        if is_empty_fund_dashboard_card_ref(item):
            normalized.append({})
            continue
        indicator_code = slugify_code(item.get("indicatorCode") or item.get("indicator_code"), "")
        if indicator_code:
            if indicator_code in seen_codes:
                normalized.append({})
            else:
                seen_codes.add(indicator_code)
                normalized.append({"indicatorCode": indicator_code})
        elif str(item.get("name") or "").strip():
            normalized.append(item)
        else:
            normalized.append({})
    return normalized


def normalize_fund_dashboard_view(source, tenant):
    defaults = {
        "layout": "2x2",
        "title": "智能指标 Dashboard",
        "note": "大V 通过选择底层指标并输入自然语言计算规则生成用户自定义智能指标，再发布到 H5 和 Web Dashboard。",
        "updatedAt": "默认模板",
        "publisher": "系统初始化",
    }
    raw = source if isinstance(source, dict) else {}
    layout = normalize_dashboard_layout(raw.get("layout") or defaults["layout"])
    hub = build_indicator_hub(tenant=tenant, admin_view=False)
    indicator_map = {item.get("id"): item for item in (hub.get("smart_items") or []) + (hub.get("lake_items") or []) if item.get("id")}
    raw_cards = normalize_fund_dashboard_card_refs(raw.get("cards"), layout)
    cards = []
    for index in range(get_dashboard_card_target(layout)):
        item = raw_cards[index] if index < len(raw_cards) and isinstance(raw_cards[index], dict) else {}
        indicator_code = slugify_code(item.get("indicatorCode") or item.get("indicator_code"), "")
        resolved = indicator_map.get(indicator_code) if indicator_code else None
        if resolved:
            cards.append(build_fund_dashboard_card_from_indicator(resolved, index=index))
            continue
        legacy_name = str(item.get("name") or "").strip()
        if legacy_name:
            cards.append(
                {
                    "indicatorCode": "",
                    "name": legacy_name,
                    "value": str(item.get("value") or "--").strip() or "--",
                    "unit": str(item.get("unit") or "").strip(),
                    "assessment": str(item.get("assessment") or item.get("hint") or "当前为历史配置，请改用智能指标方式重新生成。").strip(),
                    "interpretation": str(item.get("interpretation") or item.get("assessment") or item.get("hint") or "").strip(),
                    "status": str(item.get("status") or "attention").strip() or "attention",
                    "alert": str(item.get("alert") or "").strip(),
                    "prompt": str(item.get("prompt") or "").strip(),
                    "algorithmDetail": str(item.get("algorithmDetail") or "当前为历史配置，请改用智能指标方式重新生成。").strip(),
                    "sources": [str(source_name).strip() for source_name in (item.get("sources") or []) if str(source_name).strip()],
                    "selectedIndicators": normalize_selected_indicator_refs(item.get("selectedIndicators") or []),
                    "updatedAt": str(item.get("updatedAt") or raw.get("updatedAt") or "").strip(),
                    "isEmpty": False,
                }
            )
            continue
        cards.append(build_empty_fund_dashboard_card(index))
    title = str(raw.get("title") or defaults["title"]).strip() or defaults["title"]
    note = str(raw.get("note") or defaults["note"]).strip() or defaults["note"]
    updated_at = str(raw.get("updatedAt") or defaults["updatedAt"]).strip() or defaults["updatedAt"]
    publisher = str(raw.get("publisher") or defaults["publisher"]).strip() or defaults["publisher"]
    active_cards = [card for card in cards if not card.get("isEmpty")]
    summary = note if active_cards else "当前还没有已发布的智能指标，请先在大V工作台创建并发布。"
    cells = [
        {
            "indicatorCode": card.get("indicatorCode") or "",
            "title": card["name"] or f"核心指标 {index + 1}",
            "value": card["value"],
            "unit": card.get("unit") or "",
            "prompt": card["prompt"],
            "assessment": card["assessment"],
            "interpretation": card.get("interpretation") or card["assessment"],
            "algorithmDetail": card.get("algorithmDetail") or "",
            "status": card["status"],
            "alert": card["alert"],
            "sources": copy.deepcopy(card.get("sources") or []),
            "selectedIndicators": copy.deepcopy(card.get("selectedIndicators") or []),
            "updatedAt": str(card.get("updatedAt") or updated_at).strip(),
            "isEmpty": bool(card.get("isEmpty")),
        }
        for index, card in enumerate(cards)
    ]
    return {
        "layout": layout,
        "title": title,
        "note": note,
        "summary": summary,
        "updatedAt": updated_at,
        "publisher": publisher,
        "cards": cards,
        "cells": cells,
    }


def default_tenant_fund_dashboard_state(tenant):
    published = normalize_fund_dashboard_view(
        {
            "layout": "2x2",
            "title": "智能指标 Dashboard",
            "note": "大V 通过选择底层指标并输入自然语言计算规则生成智能指标，并发布到 H5 / Web Dashboard。",
            "updatedAt": "默认模板",
            "publisher": "系统初始化",
        },
        tenant,
    )
    return {
        "published": published,
        "draft": None,
    }


def resolve_tenant_fund_dashboard_state(tenant, config=None):
    tenant = tenant or get_tenant_by_slug()
    defaults = default_tenant_fund_dashboard_state(tenant)
    raw = config if isinstance(config, dict) else {}
    published = normalize_fund_dashboard_view(raw.get("published"), tenant) if isinstance(raw.get("published"), dict) else copy.deepcopy(defaults["published"])
    draft = normalize_fund_dashboard_view(raw.get("draft"), tenant) if isinstance(raw.get("draft"), dict) else None
    return {
        "published": published,
        "draft": draft,
    }


def build_tenant_fund_dashboard_payload(tenant=None, config=None):
    tenant = tenant or get_tenant_by_slug()
    state = resolve_tenant_fund_dashboard_state(tenant, config if config is not None else tenant.get("fund_dashboard_config"))
    return copy.deepcopy(state["published"])


def update_tenant_fund_dashboard_config(tenant_slug, action, dashboard=None):
    action_key = str(action or "").strip().lower()
    if action_key not in {"save_draft", "publish", "reset_draft"}:
        return None
    site_config = get_site_config()
    tenants = get_tenant_configs(site_config)
    updated = False
    for index, tenant in enumerate(tenants):
        if tenant.get("slug") != tenant_slug:
            continue
        current_state = resolve_tenant_fund_dashboard_state(tenant, tenant.get("fund_dashboard_config"))
        next_state = copy.deepcopy(current_state)
        if action_key == "save_draft":
            next_state["draft"] = normalize_fund_dashboard_view(dashboard, tenant)
        elif action_key == "publish":
            candidate = dashboard if isinstance(dashboard, dict) else next_state.get("draft") or next_state.get("published")
            next_state["published"] = normalize_fund_dashboard_view(candidate, tenant)
            next_state["draft"] = None
        elif action_key == "reset_draft":
            next_state["draft"] = None
        tenants[index] = dict(tenant)
        tenants[index]["fund_dashboard_config"] = next_state
        updated = True
        break
    if not updated:
        return None
    next_config = dict(site_config)
    next_config["tenants"] = tenants
    return save_site_config(next_config)


def save_smart_indicator_latest_snapshot(definition):
    normalized = definition if isinstance(definition, dict) else {}
    selected_indicators = normalize_selected_indicator_refs(normalized.get("selected_indicators"))
    if not selected_indicators:
        return None
    db = get_db()
    latest_map = {
        row["indicator_code"]: dict(row)
        for row in db.execute("SELECT * FROM indicator_latest_values").fetchall()
    }
    value = evaluate_smart_indicator_formula_js(normalized.get("formula_js"), selected_indicators, latest_map)
    timestamp = now_ts()
    assessment = build_smart_indicator_interpretation(
        normalized.get("indicator_name"),
        normalized.get("prompt_text"),
        selected_indicators,
        f"{value:.4f}".rstrip("0").rstrip("."),
        normalized.get("unit"),
    )
    alert = normalized.get("alert_template") or "如需修改计算口径，请在大V工作台重新编辑智能指标。"
    latest_status = normalized.get("status_hint") or "good"
    db.execute(
        """
        INSERT INTO indicator_latest_values (
            indicator_code, latest_value, latest_status, latest_assessment, latest_alert,
            updated_at, is_simulated, source_code, batch_code
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(indicator_code) DO UPDATE SET
            latest_value = excluded.latest_value,
            latest_status = excluded.latest_status,
            latest_assessment = excluded.latest_assessment,
            latest_alert = excluded.latest_alert,
            updated_at = excluded.updated_at,
            is_simulated = excluded.is_simulated,
            source_code = excluded.source_code,
            batch_code = excluded.batch_code
        """,
        (
            normalized.get("indicator_code"),
            f"{value:.4f}".rstrip("0").rstrip("."),
            latest_status,
            assessment,
            alert,
            timestamp,
            0,
            "tenant_smart_formula",
            f"smart_formula_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        ),
    )
    db.execute(
        """
        INSERT INTO indicator_series (
            indicator_code, point_time, point_value, point_status, is_simulated, source_code, batch_code, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalized.get("indicator_code"),
            timestamp,
            value,
            latest_status,
            0,
            "tenant_smart_formula",
            f"smart_formula_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            timestamp,
        ),
    )
    db.commit()
    invalidate_indicator_hub_cache()
    return {
        "value": value,
        "assessment": assessment,
        "alert": alert,
        "status": latest_status,
        "updated_at": timestamp,
        "unit": normalized.get("unit") or "",
    }


def append_smart_indicator_to_dashboard(tenant_slug, indicator_code, title="", layout=None, publisher=""):
    tenant = get_tenant_by_slug(tenant_slug)
    current_state = resolve_tenant_fund_dashboard_state(tenant, tenant.get("fund_dashboard_config"))
    base = copy.deepcopy(current_state.get("draft") or current_state.get("published") or {})
    next_layout = normalize_dashboard_layout(layout or base.get("layout") or ensure_dashboard_layout_for_card_count(0))
    existing_cards = normalize_fund_dashboard_card_refs(base.get("cards"), next_layout)
    next_cards = list(existing_cards)
    seen_codes = {
        slugify_code(raw.get("indicatorCode") or raw.get("indicator_code"), "")
        for raw in next_cards if isinstance(raw, dict)
    }
    seen_codes.discard("")
    normalized_code = slugify_code(indicator_code, "indicator")
    if normalized_code and normalized_code not in seen_codes:
        empty_index = next((index for index, raw in enumerate(next_cards) if not raw), None)
        if empty_index is None:
            next_layout = normalize_dashboard_layout(ensure_dashboard_layout_for_card_count(len(next_cards) + 1))
            next_cards = normalize_fund_dashboard_card_refs(next_cards, next_layout)
            empty_index = next((index for index, raw in enumerate(next_cards) if not raw), None)
        if empty_index is not None:
            next_cards[empty_index] = {"indicatorCode": normalized_code}
    dashboard = {
        "layout": next_layout,
        "title": title or "智能指标 Dashboard",
        "note": "大V 通过选择底层指标和自然语言规则生成智能指标，再发布到前台 Dashboard。",
        "updatedAt": now_ts(),
        "publisher": publisher or "系统同步",
        "cards": next_cards,
    }
    return update_tenant_fund_dashboard_config(tenant_slug, "save_draft", dashboard)


def remove_smart_indicator_from_dashboard(tenant_slug, indicator_code):
    tenant = get_tenant_by_slug(tenant_slug)
    current_state = resolve_tenant_fund_dashboard_state(tenant, tenant.get("fund_dashboard_config"))
    published = copy.deepcopy(current_state.get("published") or {})
    draft = copy.deepcopy(current_state.get("draft") or published or {})
    normalized_code = slugify_code(indicator_code, "indicator")
    def _strip_cards(source):
        layout = normalize_dashboard_layout(source.get("layout") or "2x2")
        source["cards"] = [
            {} if slugify_code((raw or {}).get("indicatorCode") or (raw or {}).get("indicator_code"), "") == normalized_code else raw
            for raw in normalize_fund_dashboard_card_refs(source.get("cards"), layout)
        ]
        source["layout"] = layout
        source["updatedAt"] = now_ts()
        source["publisher"] = tenant.get("advisor") or "大V"
        return source
    site_config = get_site_config()
    tenants = get_tenant_configs(site_config)
    for index, current_tenant in enumerate(tenants):
        if current_tenant.get("slug") != tenant_slug:
            continue
        tenants[index] = dict(current_tenant)
        tenants[index]["fund_dashboard_config"] = {
            "published": normalize_fund_dashboard_view(_strip_cards(published), tenant),
            "draft": normalize_fund_dashboard_view(_strip_cards(draft), tenant),
        }
        next_config = dict(site_config)
        next_config["tenants"] = tenants
        return save_site_config(next_config)
    return None


def create_or_update_tenant_smart_indicator(tenant_slug, payload):
    return _run_smart_indicator_agent_workflow(tenant_slug, payload, persist=True)


def normalize_tenant_configs(source=None):
    items = source if isinstance(source, list) else []
    normalized = []
    seen_slugs = set()
    if not items:
        items = copy.deepcopy(DEFAULT_TENANTS)
    for index, item in enumerate(items):
        tenant = normalize_tenant_config(item, index)
        base_slug = tenant["slug"]
        dedup_slug = base_slug
        suffix = 2
        while dedup_slug in seen_slugs:
            dedup_slug = f"{base_slug}-{suffix}"
            suffix += 1
        tenant["slug"] = dedup_slug
        tenant["id"] = tenant.get("id") or f"tenant_{dedup_slug}"
        seen_slugs.add(dedup_slug)
        normalized.append(tenant)
    return normalized


def normalize_site_config(source=None):
    merged = _merge_site_config(copy.deepcopy(DEFAULT_SITE_CONFIG), source or {})
    merged["brand"] = normalize_brand_config(merged.get("brand"))
    merged["auth_settings"] = normalize_auth_settings_config(merged.get("auth_settings"))
    merged["knowledge_ingestion"] = normalize_knowledge_ingestion_config(merged.get("knowledge_ingestion"))
    merged["hermes_settings"] = normalize_hermes_settings_config(merged.get("hermes_settings"))
    merged["evidence_chain"] = normalize_evidence_chain_config(merged.get("evidence_chain"))
    merged["review_generation"] = normalize_review_generation_config(merged.get("review_generation"))
    merged["llm_registry"] = normalize_llm_registry_config(merged.get("llm_registry"))
    merged["tenants"] = normalize_tenant_configs(merged.get("tenants"))
    tenant_slugs = [tenant["slug"] for tenant in merged["tenants"]]
    default_tenant_slug = str(merged.get("default_tenant_slug", "") or "").strip()
    merged["default_tenant_slug"] = default_tenant_slug if default_tenant_slug in tenant_slugs else tenant_slugs[0]
    return merged


def get_platform_brand(site_config=None):
    config = site_config or get_site_config()
    return normalize_brand_config(config.get("brand"))


def get_tenant_configs(site_config=None):
    config = site_config or get_site_config()
    return normalize_tenant_configs(config.get("tenants"))


def get_default_tenant_slug(site_config=None):
    config = site_config or get_site_config()
    return str(config.get("default_tenant_slug", "") or "").strip() or DEFAULT_TENANTS[0]["slug"]


def is_feature_enabled(feature_name, site_config=None):
    if not feature_name:
        return True
    config = site_config or get_site_config()
    feature_flags = config.get("feature_flags", {}) if isinstance(config, dict) else {}
    return feature_flags.get(feature_name) is not False


def get_auth_settings(site_config=None, include_secret=False):
    config = site_config or get_site_config()
    settings = normalize_auth_settings_config(config.get("auth_settings"))
    if include_secret:
        settings["wechat"]["app_secret"] = load_auth_wechat_secret()
    else:
        settings["wechat"]["app_secret"] = ""
    return settings


def get_hermes_settings(site_config=None):
    config = site_config or get_site_config()
    return normalize_hermes_settings_config(config.get("hermes_settings"))


def is_hermes_scope_guard_enabled(site_config=None):
    settings = get_hermes_settings(site_config)
    return settings.get("prompt_scope_guard_enabled") is True


def is_hermes_available_for_role(user_role="", site_config=None):
    config = site_config or get_site_config()
    if not is_feature_enabled("hermes", config):
        return False
    normalized_role = str(user_role or "").strip().lower()
    settings = get_hermes_settings(config)
    if normalized_role == "dav":
        return settings.get("dav_access_enabled") is True
    if normalized_role == "investor":
        return settings.get("investor_access_enabled") is True
    return settings.get("investor_access_enabled") is True


def get_h5_login_users(site_config=None):
    users = list_users()
    return [
        ensure_user_row_defaults(user, site_config)
        for user in users
        if user.get("role") in {"investor", "dav"} and user.get("status") == "active"
    ]


def get_h5_supported_channels():
    return list(CHANNELS)


def build_h5_user_onboarding_payload(user=None):
    user_payload = user if isinstance(user, dict) else {}
    selected_channel = str(user_payload.get("h5_channel_label") or "").strip()
    compliance_acknowledged_at = str(user_payload.get("compliance_acknowledged_at") or "").strip()
    completed_at = str(user_payload.get("onboarding_completed_at") or "").strip()
    requires_channel = selected_channel not in CHANNELS
    requires_compliance = not compliance_acknowledged_at
    return {
        "required": requires_channel or requires_compliance or not completed_at,
        "selected_channel": selected_channel if selected_channel in CHANNELS else "",
        "compliance_acknowledged_at": compliance_acknowledged_at,
        "compliance_version": str(user_payload.get("compliance_version") or "").strip(),
        "onboarding_completed_at": completed_at,
        "channels": get_h5_supported_channels(),
        "notice": copy.deepcopy(H5_COMPLIANCE_NOTICE),
    }


H5_PROFILE_SETTINGS_PREFIX = "h5_profile_settings:"
TENANT_FAN_OPS_SETTINGS_PREFIX = "tenant_fan_ops_settings:"
AUTH_WECHAT_SECRET_SETTING_KEY = "auth_settings:wechat_app_secret"


def _load_json_app_setting(setting_key, default_value=None):
    fallback = copy.deepcopy(default_value)
    try:
        row = get_db().execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?",
            (setting_key,),
        ).fetchone()
    except Exception as exc:
        if is_db_unavailable_error(exc):
            return fallback
        raise
    if not row or not row["setting_value"]:
        return fallback
    try:
        decoded = json.loads(row["setting_value"])
    except Exception:
        app.logger.exception("Failed to parse app setting: %s", setting_key)
        return fallback
    if isinstance(decoded, (dict, list)):
        return decoded
    return fallback


def _load_text_app_setting(setting_key, default_value=""):
    fallback = str(default_value or "")
    try:
        row = get_db().execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?",
            (setting_key,),
        ).fetchone()
    except Exception as exc:
        if is_db_unavailable_error(exc):
            return fallback
        raise
    if not row:
        return fallback
    return str(row["setting_value"] or fallback)


def _save_json_app_setting(setting_key, payload):
    db = get_db()
    db.execute(
        """
        INSERT INTO app_settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at = excluded.updated_at
        """,
        (
            setting_key,
            json.dumps(payload, ensure_ascii=False),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    db.commit()
    return copy.deepcopy(payload)


def _save_text_app_setting(setting_key, value):
    db = get_db()
    db.execute(
        """
        INSERT INTO app_settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at = excluded.updated_at
        """,
        (
            setting_key,
            str(value or ""),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    db.commit()
    return str(value or "")


def load_auth_wechat_secret():
    return _load_text_app_setting(AUTH_WECHAT_SECRET_SETTING_KEY, "")


def save_auth_wechat_secret(secret):
    return _save_text_app_setting(AUTH_WECHAT_SECRET_SETTING_KEY, str(secret or "").strip())


def strip_auth_settings_secret(payload=None):
    normalized = normalize_auth_settings_config(payload)
    normalized["wechat"]["app_secret"] = ""
    return normalized


def _normalize_profile_tag_list(items, limit=8):
    normalized = []
    seen = set()
    raw_items = items if isinstance(items, list) else []
    for value in raw_items:
        text = re.sub(r"\s+", " ", str(value or "").strip())
        if not text:
            continue
        if len(text) > 12:
            text = text[:12]
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _is_truthy_user_flag(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "paid"}


PAID_USER_LABEL = "付费用户"


def normalize_user_labels(value, is_paid_sample=False, limit=16):
    raw_labels = value if isinstance(value, list) else []
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            raw_labels = decoded if isinstance(decoded, list) else re.split(r"[,，;；]", value)
        except Exception:
            raw_labels = re.split(r"[,，;；]", value)
    labels = []
    seen = set()
    for raw_label in raw_labels:
        label = re.sub(r"\s+", " ", str(raw_label or "").strip())[:24]
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        labels.append(label)
        if len(labels) >= limit:
            break
    if is_paid_sample and PAID_USER_LABEL.lower() not in seen:
        labels.insert(0, PAID_USER_LABEL)
    return labels[:limit]


def update_tenant_user_labels(tenant_slug, user_ids, label, action="add"):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    normalized_label = re.sub(r"\s+", " ", str(label or "").strip())[:24]
    if not normalized_tenant or not normalized_label:
        raise ValueError("tenant_and_label_required")
    normalized_action = str(action or "add").strip().lower()
    if normalized_action not in {"add", "remove"}:
        raise ValueError("invalid_label_action")
    ids = []
    for value in user_ids if isinstance(user_ids, list) else []:
        try:
            user_id = int(value)
        except Exception:
            continue
        if user_id > 0 and user_id not in ids:
            ids.append(user_id)
    if not ids:
        raise ValueError("user_ids_required")
    placeholders = ",".join("?" for _ in ids)
    db = get_db()
    rows = db.execute(
        f"SELECT id, labels_json, is_paid_sample FROM users WHERE tenant_slug = ? AND role = 'investor' AND id IN ({placeholders})",
        tuple([normalized_tenant] + ids),
    ).fetchall()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated = []
    for row in rows:
        current = dict(row)
        labels = normalize_user_labels(current.get("labels_json"), is_paid_sample=bool(int(current.get("is_paid_sample") or 0)))
        if normalized_action == "add" and normalized_label.lower() not in {item.lower() for item in labels}:
            labels.append(normalized_label)
        if normalized_action == "remove":
            labels = [item for item in labels if item.lower() != normalized_label.lower()]
        is_paid = PAID_USER_LABEL.lower() in {item.lower() for item in labels}
        db.execute(
            "UPDATE users SET labels_json = ?, is_paid_sample = ?, paid_sample_marked_at = ?, updated_at = ? WHERE id = ?",
            (json.dumps(labels, ensure_ascii=False), 1 if is_paid else 0, now if is_paid else "", now, int(current["id"])),
        )
        updated.append(int(current["id"]))
    db.commit()
    return {"updated_user_ids": updated, "label": normalized_label, "action": normalized_action}


def _normalize_tenant_fan_ops_settings(payload=None):
    source = payload if isinstance(payload, dict) else {}
    try:
        registration_price = max(0, int(float(source.get("registration_price") or source.get("fan_registration_price") or 0)))
    except Exception:
        registration_price = 0
    return {
        "registration_price": registration_price,
        "currency": str(source.get("currency") or "CNY").strip().upper() or "CNY",
        "updated_at": str(source.get("updated_at") or "").strip(),
    }


def get_tenant_fan_ops_settings_key(tenant_slug):
    normalized = str(tenant_slug or "").strip().lower()
    return f"{TENANT_FAN_OPS_SETTINGS_PREFIX}{normalized}" if normalized else TENANT_FAN_OPS_SETTINGS_PREFIX


def load_tenant_fan_ops_settings(tenant_slug):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    if not normalized_tenant:
        return _normalize_tenant_fan_ops_settings({})
    payload = _load_json_app_setting(get_tenant_fan_ops_settings_key(normalized_tenant), {})
    return _normalize_tenant_fan_ops_settings(payload)


def save_tenant_fan_ops_settings(tenant_slug, payload=None):
    normalized_tenant = str(tenant_slug or "").strip().lower()
    if not normalized_tenant:
        raise ValueError("tenant_slug_required")
    normalized = _normalize_tenant_fan_ops_settings(payload)
    normalized["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save_json_app_setting(get_tenant_fan_ops_settings_key(normalized_tenant), normalized)
    return normalized


def get_h5_profile_settings_key(profile_id):
    normalized = str(profile_id or "").strip()
    if not normalized:
        return ""
    return f"{H5_PROFILE_SETTINGS_PREFIX}{normalized}"


def normalize_h5_profile_settings(source=None, user=None):
    payload = source if isinstance(source, dict) else {}
    user_payload = user if isinstance(user, dict) else {}
    role = str(user_payload.get("role") or "investor").strip().lower()
    default_avatar = str(user_payload.get("avatar") or ("👑" if role == "dav" else "👤")).strip() or ("👑" if role == "dav" else "👤")
    default_name = str(user_payload.get("username") or user_payload.get("name") or "").strip() or "投研用户"
    raw_avatar = str(payload.get("avatar") or default_avatar).strip() or default_avatar
    raw_name = re.sub(r"\s+", " ", str(payload.get("display_name") or default_name).strip()) or default_name
    raw_bio = str(payload.get("bio") or "").strip()
    if len(raw_name) > 24:
        raw_name = raw_name[:24]
    if len(raw_avatar) > 8:
        raw_avatar = raw_avatar[:8]
    if len(raw_bio) > 160:
        raw_bio = raw_bio[:160]
    return {
        "display_name": raw_name,
        "avatar": raw_avatar,
        "bio": raw_bio,
        "custom_tags": _normalize_profile_tag_list(payload.get("custom_tags") or payload.get("customTags") or []),
    }


def load_h5_profile_settings(user=None):
    user_payload = user if isinstance(user, dict) else {}
    setting_key = get_h5_profile_settings_key(user_payload.get("username"))
    defaults = normalize_h5_profile_settings({}, user_payload)
    if not setting_key:
        return defaults
    stored = _load_json_app_setting(setting_key, {})
    return normalize_h5_profile_settings(stored, user_payload)


def save_h5_profile_settings(user, source=None):
    user_payload = user if isinstance(user, dict) else {}
    setting_key = get_h5_profile_settings_key(user_payload.get("username"))
    if not setting_key:
        raise ValueError("h5_profile_not_found")
    normalized = normalize_h5_profile_settings(source, user_payload)
    _save_json_app_setting(setting_key, normalized)
    return normalized


def build_h5_account_settings_payload(user=None):
    user_payload = ensure_user_row_defaults(user or {}, get_site_config()) if isinstance(user, dict) else ensure_user_row_defaults({}, get_site_config())
    profile_settings = normalize_h5_profile_settings(user_payload.get("profile_settings"), user_payload)
    return {
        "editable": copy.deepcopy(profile_settings),
        "readonly": {
            "role_label": user_payload.get("roleLabel") or ("大V投顾" if user_payload.get("role") == "dav" else "投资者"),
            "tenant_name": ((user_payload.get("tenant") or {}).get("name")) or "--",
            "advisor_name": ((user_payload.get("tenant") or {}).get("advisor")) or user_payload.get("advisor_name") or "--",
            "membership": user_payload.get("membership") or "--",
            "relationship": user_payload.get("relationship") or "--",
            "rights": ((user_payload.get("tenant") or {}).get("rights")) or "--",
            "phone_masked": user_payload.get("phone_masked") or "--",
        },
        "system_badges": copy.deepcopy(user_payload.get("systemBadges") or user_payload.get("badges") or []),
    }


def build_h5_help_center_payload(role="investor"):
    normalized_role = str(role or "investor").strip().lower()
    role_label = "大V工作台与内容生产" if normalized_role == "dav" else "投资者跟踪与互动"
    articles = [
        {
            "id": "account",
            "category": "账号",
            "title": "账号设置怎么修改",
            "summary": "这里维护你的头像、昵称、简介和自定义关注标签。",
            "bullets": [
                "租户身份、当前关系和租户权益由系统管理，不支持手动修改。",
                "系统标签会根据角色、行为和租户关系自动生成。",
                "你自己可维护的是基础资料和自定义关注标签。",
            ],
            "action_label": "打开账号设置",
            "action_type": "account_settings",
        },
        {
            "id": "dm",
            "category": "消息",
            "title": "消息通知在哪里看",
            "summary": f"消息通知会直接进入消息板块，按 {role_label} 的视角查看会话。",
            "bullets": [
                "投资者默认只和所属大V租户互动。",
                "大V会在消息板块查看粉丝私信和系统提醒。",
                "复盘发布、私信回复和关键互动都会沉淀到消息链路。",
            ],
            "action_label": "打开消息板块",
            "action_type": "switch_tab",
            "action_value": "dm",
        },
        {
            "id": "hermes",
            "category": "Hermes",
            "title": "Hermes 能问什么",
            "summary": "Hermes 只承接平台研究相关问题，不做泛百科和高风险投资指令。",
            "bullets": [
                "优先查当前租户知识内容，再按需要补平台能力。",
                "适合问个股基本面、复盘证据链、知识框架和智能指标解释。",
                "超范围问题会被收口并引导回平台能力。",
            ],
            "action_label": "打开 Hermes",
            "action_type": "switch_tab",
            "action_value": "hermes",
        },
        {
            "id": "review",
            "category": "复盘",
            "title": "复盘内容怎么生成",
            "summary": "先形成用户复盘 Draft，再审核确认，最后生成摘要；如果选择了自选股，再追加归纳总结。",
            "bullets": [
                "手写、语音、文件都先进入用户输入整理阶段。",
                "确认 Draft 后一定会生成摘要；如果选择了自选股，再追加归纳总结。",
                "预览无误再发布，前后台展示同一篇正式复盘。",
            ],
            "action_label": "打开复盘",
            "action_type": "switch_tab",
            "action_value": "review",
        },
        {
            "id": "indicator",
            "category": "指标",
            "title": "智能指标怎么理解",
            "summary": "智能指标由提示词约束计算逻辑，真正保存的是系统生成并确认后的公式结果。",
            "bullets": [
                "单个原始指标或已存在智能指标可以直接预览。",
                "涉及新计算逻辑时会先临时生成，再给用户确认。",
                "普通用户查看结果与详情，大V额外在后台维护定义。",
            ],
            "action_label": "打开 Dashboard",
            "action_type": "switch_tab",
            "action_value": "feed",
        },
        {
            "id": "knowledge",
            "category": "知识",
            "title": "知识专区怎么用",
            "summary": "知识专区统一管理上传、清洗、同步和知识图谱关系。",
            "bullets": [
                "大V可维护当前租户知识内容，并在工作台里查看租户知识图谱。",
                "Admin 可以从平台总图切到单租户细看知识结构。",
                "Hermes 和复盘都会优先复用这些知识沉淀。",
            ],
            "action_label": "打开知识",
            "action_type": "switch_tab",
            "action_value": "knowledge",
        },
    ]
    categories = ["全部"] + [item["category"] for item in articles]
    deduped_categories = []
    for item in categories:
        if item not in deduped_categories:
            deduped_categories.append(item)
    return {
        "title": "帮助中心",
        "subtitle": "按功能查看使用说明，不做冗余运营文案。",
        "role": normalized_role,
        "categories": deduped_categories,
        "articles": articles,
    }


def get_current_demo_profile_id():
    cached = g.get("current_demo_profile_id")
    if cached is not None:
        return cached
    profile_id = str(session.get(H5_USER_SESSION_KEY) or "").strip()
    g.current_demo_profile_id = profile_id
    return profile_id


def save_current_demo_profile_id(profile_id):
    normalized = str(profile_id or "").strip()
    if normalized:
        session[H5_USER_SESSION_KEY] = normalized
        session.permanent = True
    else:
        session.pop(H5_USER_SESSION_KEY, None)
    g.current_demo_profile_id = normalized
    return normalized


def get_current_demo_profile(site_config=None):
    current_username = get_current_demo_profile_id()
    if not current_username:
        return None
    current_user = get_user_by_username(current_username)
    if not current_user:
        session.pop(H5_USER_SESSION_KEY, None)
        g.current_demo_profile_id = ""
        return None
    if current_user.get("role") not in {"investor", "dav"} or current_user.get("status") != "active":
        session.pop(H5_USER_SESSION_KEY, None)
        g.current_demo_profile_id = ""
        return None
    return ensure_user_row_defaults(current_user, site_config)


def get_current_authenticated_user():
    """Resolve the platform account in the shared login session, including admins."""
    current_username = get_current_demo_profile_id()
    if not current_username:
        return None
    current_user = get_user_by_username(current_username)
    if not current_user or current_user.get("role") not in {"investor", "dav", "admin"} or current_user.get("status") != "active":
        save_current_demo_profile_id("")
        return None
    return ensure_user_row_defaults(current_user)


def mask_phone(phone):
    value = str(phone or "").strip()
    if len(value) >= 7:
        return f"{value[:3]}****{value[-4:]}"
    return value


def list_users(role=None, tenant_slug=None):
    db = get_db()
    conditions = []
    params = []
    if role:
        conditions.append("role = ?")
        params.append(role)
    if tenant_slug:
        conditions.append("tenant_slug = ?")
        params.append(tenant_slug)
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = db.execute(
        f"""
        SELECT id, username, password, role, tenant_slug, advisor_name, phone, status,
               auth_provider, wechat_openid, wechat_unionid, wechat_nickname, wechat_bound_at,
               compliance_acknowledged_at, compliance_version, h5_channel_label, h5_channel_selected_at, onboarding_completed_at,
               source_label, is_paid_sample, paid_sample_marked_at, paid_sample_note, labels_json,
               created_at, updated_at
        FROM users
        {where_sql}
        ORDER BY id ASC
        """,
        tuple(params),
    ).fetchall()
    return [ensure_user_row_defaults(dict(row)) for row in rows]


def get_user_by_id(user_id):
    try:
        user_pk = int(user_id)
    except Exception:
        return None
    db = get_db()
    row = db.execute(
        """
        SELECT id, username, password, role, tenant_slug, advisor_name, phone, status,
               auth_provider, wechat_openid, wechat_unionid, wechat_nickname, wechat_bound_at,
               compliance_acknowledged_at, compliance_version, h5_channel_label, h5_channel_selected_at, onboarding_completed_at,
               source_label, is_paid_sample, paid_sample_marked_at, paid_sample_note, labels_json,
               created_at, updated_at
        FROM users
        WHERE id = ?
        """,
        (user_pk,),
    ).fetchone()
    return ensure_user_row_defaults(dict(row)) if row else None


def get_user_by_username(username):
    db = get_db()
    row = db.execute(
        """
        SELECT id, username, password, role, tenant_slug, advisor_name, phone, status,
               auth_provider, wechat_openid, wechat_unionid, wechat_nickname, wechat_bound_at,
               compliance_acknowledged_at, compliance_version, h5_channel_label, h5_channel_selected_at, onboarding_completed_at,
               source_label, is_paid_sample, paid_sample_marked_at, paid_sample_note, labels_json,
               created_at, updated_at
        FROM users
        WHERE username = ?
        """,
        (str(username or "").strip(),),
    ).fetchone()
    return ensure_user_row_defaults(dict(row)) if row else None


def get_user_by_wechat_identity(openid="", unionid=""):
    openid_text = str(openid or "").strip()
    unionid_text = str(unionid or "").strip()
    if not openid_text and not unionid_text:
        return None
    db = get_db()
    row = None
    if unionid_text:
        row = db.execute(
            """
            SELECT id, username, password, role, tenant_slug, advisor_name, phone, status,
                   auth_provider, wechat_openid, wechat_unionid, wechat_nickname, wechat_bound_at,
                   compliance_acknowledged_at, compliance_version, h5_channel_label, h5_channel_selected_at, onboarding_completed_at,
                   source_label, is_paid_sample, paid_sample_marked_at, paid_sample_note, labels_json,
                   created_at, updated_at
            FROM users
            WHERE wechat_unionid = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (unionid_text,),
        ).fetchone()
    if row is None and openid_text:
        row = db.execute(
            """
            SELECT id, username, password, role, tenant_slug, advisor_name, phone, status,
                   auth_provider, wechat_openid, wechat_unionid, wechat_nickname, wechat_bound_at,
                   compliance_acknowledged_at, compliance_version, h5_channel_label, h5_channel_selected_at, onboarding_completed_at,
                   source_label, is_paid_sample, paid_sample_marked_at, paid_sample_note, labels_json,
                   created_at, updated_at
            FROM users
            WHERE wechat_openid = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (openid_text,),
        ).fetchone()
    return ensure_user_row_defaults(dict(row)) if row else None


def verify_h5_password_login(username, password):
    user = get_user_by_username(username)
    if not user:
        raise ValueError("user_not_found")
    if user.get("role") not in {"investor", "dav", "admin"}:
        raise ValueError("user_role_not_allowed")
    if user.get("status") != "active":
        raise ValueError("user_disabled")
    if not compare_digest(str(user.get("password") or ""), str(password or "")):
        raise ValueError("password_invalid")
    return user


def verify_platform_password_login(username, password):
    user = get_user_by_username(username)
    if not user:
        raise ValueError("user_not_found")
    if user.get("role") not in {"investor", "dav", "admin"}:
        raise ValueError("user_role_not_allowed")
    if user.get("status") != "active":
        raise ValueError("user_disabled")
    if not compare_digest(str(user.get("password") or ""), str(password or "")):
        raise ValueError("password_invalid")
    return user


def bind_user_wechat_identity(user_id, openid="", unionid="", nickname=""):
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("user_not_found")
    openid_text = str(openid or "").strip()
    unionid_text = str(unionid or "").strip()
    if not openid_text and not unionid_text:
        raise ValueError("wechat_identity_required")
    existing = get_user_by_wechat_identity(openid=openid_text, unionid=unionid_text)
    if existing and int(existing.get("id") or 0) != int(user.get("id") or 0):
        raise ValueError("wechat_identity_bound")
    bound_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nickname_text = str(nickname or "").strip()[:80]
    db = get_db()
    db.execute(
        """
        UPDATE users
        SET auth_provider = ?, wechat_openid = ?, wechat_unionid = ?, wechat_nickname = ?, wechat_bound_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            "wechat",
            openid_text,
            unionid_text,
            nickname_text,
            bound_at,
            bound_at,
            int(user["id"]),
        ),
    )
    db.commit()
    return get_user_by_id(user["id"])


def create_wechat_h5_user(openid="", unionid="", nickname="", tenant_slug="", role="investor", advisor_name=""):
    openid_text = str(openid or "").strip()
    unionid_text = str(unionid or "").strip()
    if not openid_text and not unionid_text:
        raise ValueError("wechat_identity_required")
    existing = get_user_by_wechat_identity(openid=openid_text, unionid=unionid_text)
    if existing:
        return existing
    normalized_role = str(role or "investor").strip().lower()
    if normalized_role not in {"investor", "dav"}:
        normalized_role = "investor"
    resolved_tenant_slug = str(tenant_slug or get_default_tenant_slug()).strip().lower()
    tenant = get_tenant_by_slug(resolved_tenant_slug)
    resolved_advisor_name = str(advisor_name or tenant.get("advisor") or "").strip()
    nickname_seed = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_]+", "", str(nickname or "").strip())[:16]
    identity_seed = unionid_text or openid_text or str(int(time.time()))
    suffix = hashlib.sha1(identity_seed.encode("utf-8")).hexdigest()[:8]
    base_username = nickname_seed or f"wx_{suffix}"
    candidate = base_username
    counter = 2
    while get_user_by_username(candidate):
        candidate = f"{base_username}_{counter}"
        counter += 1
    pseudo_phone = f"wx_{suffix[:11]}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    db.execute(
        """
        INSERT INTO users (
            username, password, role, tenant_slug, advisor_name, phone, status,
            auth_provider, wechat_openid, wechat_unionid, wechat_nickname, wechat_bound_at,
            compliance_acknowledged_at, compliance_version, h5_channel_label, h5_channel_selected_at, onboarding_completed_at,
            source_label, is_paid_sample, paid_sample_marked_at, paid_sample_note, labels_json,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate,
            f"wechat:{suffix}",
            normalized_role,
            tenant.get("slug") or resolved_tenant_slug,
            resolved_advisor_name if normalized_role == "investor" else "",
            pseudo_phone,
            "active",
            "wechat",
            openid_text,
            unionid_text,
            str(nickname or "").strip()[:80],
            now,
            "",
            "",
            "",
            "",
            "",
            "微信登录自动注册",
            0,
            "",
            "",
            "[]",
            now,
            now,
        ),
    )
    db.commit()
    return get_user_by_username(candidate)


def create_user(payload):
    source = payload if isinstance(payload, dict) else {}
    username = str(source.get("username") or "").strip()
    password = str(source.get("password") or "").strip()
    role = str(source.get("role") or "investor").strip().lower()
    tenant_slug = str(source.get("tenant_slug") or get_default_tenant_slug()).strip().lower()
    advisor_name = str(source.get("advisor_name") or "").strip()
    phone = str(source.get("phone") or "").strip()
    status = str(source.get("status") or "active").strip().lower()
    source_label = str(source.get("source_label") or "").strip()[:80]
    is_paid_sample = 1 if _is_truthy_user_flag(source.get("is_paid_sample")) else 0
    paid_sample_note = str(source.get("paid_sample_note") or "").strip()[:240]
    labels = normalize_user_labels(source.get("labels"), is_paid_sample=bool(is_paid_sample and role == "investor"))
    auth_provider = str(source.get("auth_provider") or "local").strip().lower() or "local"
    wechat_openid = str(source.get("wechat_openid") or "").strip()
    wechat_unionid = str(source.get("wechat_unionid") or "").strip()
    wechat_nickname = str(source.get("wechat_nickname") or "").strip()[:80]
    compliance_acknowledged_at = str(source.get("compliance_acknowledged_at") or "").strip()
    compliance_version = str(source.get("compliance_version") or "").strip()
    h5_channel_label = str(source.get("h5_channel_label") or "").strip()
    h5_channel_selected_at = str(source.get("h5_channel_selected_at") or "").strip()
    onboarding_completed_at = str(source.get("onboarding_completed_at") or "").strip()
    if not username or not password or role not in {"investor", "dav", "admin"} or not phone:
        raise ValueError("invalid_user_payload")
    if get_user_by_username(username):
        raise ValueError("username_exists")
    if wechat_openid or wechat_unionid:
        existing = get_user_by_wechat_identity(openid=wechat_openid, unionid=wechat_unionid)
        if existing:
            raise ValueError("wechat_identity_bound")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    paid_sample_marked_at = now if role == "investor" and is_paid_sample else ""
    wechat_bound_at = now if wechat_openid or wechat_unionid else ""
    db = get_db()
    db.execute(
        """
        INSERT INTO users (
            username, password, role, tenant_slug, advisor_name, phone, status,
            auth_provider, wechat_openid, wechat_unionid, wechat_nickname, wechat_bound_at,
            compliance_acknowledged_at, compliance_version, h5_channel_label, h5_channel_selected_at, onboarding_completed_at,
            source_label, is_paid_sample, paid_sample_marked_at, paid_sample_note, labels_json,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            password,
            role,
            tenant_slug,
            advisor_name,
            phone,
            status,
            auth_provider,
            wechat_openid,
            wechat_unionid,
            wechat_nickname,
            wechat_bound_at,
            compliance_acknowledged_at,
            compliance_version,
            h5_channel_label,
            h5_channel_selected_at,
            onboarding_completed_at,
            source_label,
            is_paid_sample if role == "investor" else 0,
            paid_sample_marked_at if role == "investor" else "",
            paid_sample_note if role == "investor" else "",
            json.dumps(labels if role == "investor" else [], ensure_ascii=False),
            now,
            now,
        ),
    )
    db.commit()
    return get_user_by_username(username)


def complete_h5_user_onboarding(user, channel_label):
    user_payload = user if isinstance(user, dict) else {}
    user_id = int(user_payload.get("id") or 0)
    selected_channel = str(channel_label or "").strip()
    if user_id <= 0:
        raise ValueError("user_not_found")
    if selected_channel not in CHANNELS:
        raise ValueError("invalid_channel_label")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    db.execute(
        """
        UPDATE users
        SET compliance_acknowledged_at = ?,
            compliance_version = ?,
            h5_channel_label = ?,
            h5_channel_selected_at = ?,
            onboarding_completed_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            now,
            H5_COMPLIANCE_VERSION,
            selected_channel,
            now,
            now,
            now,
            user_id,
        ),
    )
    db.commit()
    return get_user_by_id(user_id)


def import_users(items):
    created = []
    for item in (items or []):
        try:
            user = create_user(item)
            if user:
                created.append(user)
        except ValueError:
            continue
    return created


def ensure_default_users():
    try:
        existing_users = list_users()
    except Exception:
        raise
    if existing_users:
        return {"created": [], "skipped": []}
    created = []
    skipped = []
    for item in DEFAULT_USERS:
        try:
            user = create_user(item)
            if user:
                created.append(user)
        except Exception as exc:
            skipped.append(
                {
                    "username": str((item or {}).get("username") or "").strip(),
                    "reason": str(exc),
                }
            )
    return {"created": created, "skipped": skipped}


USER_IMPORT_TEMPLATE_FIELDS = [
    "username",
    "password",
    "phone",
    "role",
    "tenant_slug",
    "advisor_name",
    "status",
    "is_paid_sample",
    "labels",
    "source_label",
    "paid_sample_note",
]


def build_user_import_template_csv(scope="admin", tenant_slug=""):
    normalized_scope = str(scope or "admin").strip().lower()
    rows = []
    if normalized_scope == "kol":
        active_tenant = get_tenant_by_slug(tenant_slug)
        rows.append({
            "username": "fan_demo_001",
            "password": "demo123456",
            "phone": "13800000001",
            "role": "investor",
            "tenant_slug": active_tenant.get("slug") or "",
            "advisor_name": active_tenant.get("advisor") or "",
            "status": "active",
            "is_paid_sample": "0",
            "labels": "",
            "source_label": "用户导入",
            "paid_sample_note": "",
        })
    else:
        default_tenant = get_tenant_by_slug(get_default_tenant_slug())
        rows.extend([
            {
                "username": "fan_demo_001",
                "password": "demo123456",
                "phone": "13800000001",
                "role": "investor",
                "tenant_slug": default_tenant.get("slug") or "",
                "advisor_name": default_tenant.get("advisor") or "",
                "status": "active",
                "is_paid_sample": "0",
                "labels": "",
                "source_label": "用户导入",
                "paid_sample_note": "",
            },
            {
                "username": "kol_demo_001",
                "password": "demo123456",
                "phone": "13800000002",
                "role": "dav",
                "tenant_slug": default_tenant.get("slug") or "",
                "advisor_name": default_tenant.get("advisor") or "",
                "status": "active",
                "is_paid_sample": "0",
                "labels": "",
                "source_label": "管理录入",
                "paid_sample_note": "",
            },
            {
                "username": "admin_demo_001",
                "password": "demo123456",
                "phone": "13800000003",
                "role": "admin",
                "tenant_slug": default_tenant.get("slug") or "",
                "advisor_name": "",
                "status": "active",
                "is_paid_sample": "0",
                "labels": "",
                "source_label": "管理录入",
                "paid_sample_note": "",
            },
        ])
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=USER_IMPORT_TEMPLATE_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in USER_IMPORT_TEMPLATE_FIELDS})
    return output.getvalue()


def _normalize_user_role_for_scope(role, scope):
    normalized_scope = str(scope or "admin").strip().lower()
    value = str(role or "investor").strip().lower() or "investor"
    if normalized_scope == "kol":
        return "investor"
    return value if value in {"investor", "dav", "admin"} else "investor"


def _normalize_user_status(value):
    normalized = str(value or "active").strip().lower()
    return normalized if normalized in {"active", "disabled"} else "active"


def build_user_import_context(scope="admin", tenant_slug=""):
    normalized_scope = str(scope or "admin").strip().lower()
    if normalized_scope == "kol":
        tenant = get_tenant_by_slug(tenant_slug)
        return {
            "scope": "kol",
            "tenant_slug": tenant.get("slug") or "",
            "advisor_name": tenant.get("advisor") or "",
            "allowed_roles": ["investor"],
        }
    return {
        "scope": "admin",
        "tenant_slug": "",
        "advisor_name": "",
        "allowed_roles": ["investor", "dav", "admin"],
    }


def normalize_user_payload(source, context=None):
    raw = source if isinstance(source, dict) else {}
    ctx = context or build_user_import_context()
    scope = ctx.get("scope") or "admin"
    target_tenant_slug = str(ctx.get("tenant_slug") or "").strip().lower()
    username = str(raw.get("username") or "").strip()
    password = str(raw.get("password") or "").strip()
    phone = str(raw.get("phone") or "").strip()
    role = _normalize_user_role_for_scope(raw.get("role"), scope)
    status = _normalize_user_status(raw.get("status"))
    tenant_slug = str(raw.get("tenant_slug") or target_tenant_slug or get_default_tenant_slug()).strip().lower()
    if scope == "kol":
        tenant_slug = target_tenant_slug
    tenant = get_tenant_by_slug(tenant_slug)
    advisor_name = str(raw.get("advisor_name") or "").strip()
    if scope == "kol":
        advisor_name = tenant.get("advisor") or ctx.get("advisor_name") or ""
    elif role == "investor" and not advisor_name:
        advisor_name = tenant.get("advisor") or ""
    elif role == "admin":
        advisor_name = ""
    is_paid_sample = _is_truthy_user_flag(raw.get("is_paid_sample")) if role == "investor" else False
    default_source_label = "用户导入" if scope == "kol" or role == "investor" else "管理录入"
    return {
        "username": username,
        "password": password,
        "phone": phone,
        "role": role,
        "tenant_slug": tenant_slug,
        "advisor_name": advisor_name,
        "status": status,
        "is_paid_sample": is_paid_sample,
        "labels": normalize_user_labels(raw.get("labels"), is_paid_sample=is_paid_sample),
        "source_label": str(raw.get("source_label") or default_source_label).strip()[:80],
        "paid_sample_note": str(raw.get("paid_sample_note") or "").strip()[:240],
    }


def parse_user_csv_import(file_storage, context=None):
    if file_storage is None:
        raise ValueError("csv_file_required")
    raw_bytes = file_storage.read() or b""
    if not raw_bytes:
        raise ValueError("csv_file_required")
    try:
        content = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw_bytes.decode("gb18030")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValueError("csv_header_required")
    rows = []
    for row in reader:
        if not isinstance(row, dict):
            continue
        if not any(str(value or "").strip() for value in row.values()):
            continue
        rows.append(normalize_user_payload(row, context=context))
    return rows


def bulk_create_users(items, context=None):
    ctx = context or build_user_import_context()
    created = []
    skipped = []
    for index, item in enumerate(items or [], start=1):
        try:
            payload = normalize_user_payload(item, context=ctx)
            user = create_user(payload)
            if user:
                created.append(user)
        except Exception as exc:
            skipped.append({
                "row_index": index,
                "username": str((item or {}).get("username") or "").strip() if isinstance(item, dict) else "",
                "reason": str(exc),
            })
    return created, skipped


def build_user_import_summary(scope="admin", tenant_slug=""):
    ctx = build_user_import_context(scope=scope, tenant_slug=tenant_slug)
    try:
        users = list_users(tenant_slug=ctx["tenant_slug"] or None)
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        users = []
    if ctx["scope"] == "kol":
        users = [user for user in users if user.get("role") == "investor"]
    paying_users = [user for user in users if user.get("role") == "investor" and bool(user.get("is_paid_sample"))]
    return {
        "scope": ctx["scope"],
        "tenant_slug": ctx["tenant_slug"],
        "total_users": len(users),
        "paying_users": len(paying_users),
        "settings": load_tenant_fan_ops_settings(ctx["tenant_slug"]) if ctx["tenant_slug"] else _normalize_tenant_fan_ops_settings({}),
        "role_split": {
            "investor": len([user for user in users if user.get("role") == "investor"]),
            "dav": len([user for user in users if user.get("role") == "dav"]),
            "admin": len([user for user in users if user.get("role") == "admin"]),
        },
        "users": users,
    }


def ensure_user_row_defaults(user, site_config=None):
    config = site_config or get_site_config()
    tenant = get_tenant_by_slug(user.get("tenant_slug"), config)
    role = str(user.get("role", "investor") or "investor").strip().lower()
    role_label_map = {"investor": "投资者", "dav": "大V投顾", "admin": "管理员"}
    default_stats = {
        "investor": {"posts": 23, "likes": 456, "following": 12, "followers": 89, "points": 3840, "compute_credits": 128, "level": 4, "level_name": "资深分析师", "membership": "投资者视角", "relationship": "核心订阅用户", "tenant_card_title": "所属大V租户", "workbench_label": "查看当前租户工作台（demo）", "workbench_hint": "投资者视角 · 查看租户服务与互动提醒", "stat_labels": ["帖子", "获赞", "自选", "社群互动"], "badges": ["🦞 Hermes达人", "📊 投研先锋", "🧭 长期跟踪", "📅 连续签到30天"], "avatar": "👨"},
        "dav": {"posts": 86, "likes": 3688, "following": 128, "followers": 1240, "points": 9820, "compute_credits": 420, "level": 6, "level_name": "租户主理人", "membership": "大V主理视角", "relationship": "租户主理人", "tenant_card_title": "当前管理租户", "workbench_label": "进入我的大V工作台", "workbench_hint": "大V投顾视角 · 管理粉丝、内容与协同收入", "stat_labels": ["内容", "获赞", "订阅用户", "私域线索"], "badges": ["👑 种子投顾", "🦞 Hermes高频用户", "🏆 协同标杆", "💬 私域主理人"], "avatar": "👑"},
        "admin": {"posts": 0, "likes": 0, "following": 0, "followers": 0, "points": 9999, "compute_credits": 999, "level": 9, "level_name": "平台管理员", "membership": "管理员视角", "relationship": "平台管理员", "tenant_card_title": "当前管理平台", "workbench_label": "进入平台后台", "workbench_hint": "管理员视角 · 管理平台用户与租户", "stat_labels": ["用户", "租户", "权限", "系统"], "badges": ["🛡️ 平台管理员"], "avatar": "🛡️"},
    }
    defaults = default_stats.get(role, default_stats["investor"])
    profile_settings = load_h5_profile_settings(user)
    advisor_name = str(user.get("advisor_name") or tenant.get("advisor") or "").strip()
    return {
        "id": user.get("id"),
        "username": str(user.get("username") or "").strip(),
        "password": str(user.get("password") or "").strip(),
        "role": role,
        "roleLabel": role_label_map.get(role, "投资者"),
        "avatar": str(profile_settings.get("avatar") or user.get("avatar") or defaults["avatar"]).strip() or defaults["avatar"],
        "name": str(profile_settings.get("display_name") or user.get("username") or "").strip(),
        "phone": str(user.get("phone") or "").strip(),
        "phone_masked": mask_phone(user.get("phone")),
        "status": str(user.get("status") or "active").strip(),
        "auth_provider": str(user.get("auth_provider") or "local").strip().lower() or "local",
        "wechat_openid": str(user.get("wechat_openid") or "").strip(),
        "wechat_unionid": str(user.get("wechat_unionid") or "").strip(),
        "wechat_nickname": str(user.get("wechat_nickname") or "").strip(),
        "wechat_bound_at": str(user.get("wechat_bound_at") or "").strip(),
        "wechat_bound": bool(str(user.get("wechat_openid") or "").strip() or str(user.get("wechat_unionid") or "").strip()),
        "compliance_acknowledged_at": str(user.get("compliance_acknowledged_at") or "").strip(),
        "compliance_version": str(user.get("compliance_version") or "").strip(),
        "h5_channel_label": str(user.get("h5_channel_label") or "").strip(),
        "h5_channel_selected_at": str(user.get("h5_channel_selected_at") or "").strip(),
        "onboarding_completed_at": str(user.get("onboarding_completed_at") or "").strip(),
        "source_label": str(user.get("source_label") or "").strip(),
        "is_paid_sample": bool(int(user.get("is_paid_sample") or 0)),
        "paid_sample_marked_at": str(user.get("paid_sample_marked_at") or "").strip(),
        "paid_sample_note": str(user.get("paid_sample_note") or "").strip(),
        "labels": normalize_user_labels(user.get("labels_json"), is_paid_sample=bool(int(user.get("is_paid_sample") or 0))),
        "tenant_slug": tenant.get("slug"),
        "advisor_name": advisor_name,
        "tenant": {
            "id": tenant.get("id"),
            "slug": tenant.get("slug"),
            "name": tenant.get("name"),
            "advisor": tenant.get("advisor"),
            "focus": tenant.get("focus"),
            "rights": tenant.get("rights"),
            "desc": tenant.get("description"),
        },
        "level": defaults["level"],
        "levelName": defaults["level_name"],
        "points": defaults["points"],
        "computeCredits": defaults["compute_credits"],
        "posts": defaults["posts"],
        "likes": defaults["likes"],
        "following": defaults["following"],
        "followers": defaults["followers"],
        "membership": defaults["membership"],
        "relationship": defaults["relationship"],
        "statLabels": defaults["stat_labels"],
        "tenantCardTitle": defaults["tenant_card_title"],
        "badges": defaults["badges"],
        "systemBadges": defaults["badges"],
        "customTags": profile_settings.get("custom_tags") or [],
        "bio": profile_settings.get("bio") or "",
        "profile_settings": profile_settings,
        "workbenchLabel": defaults["workbench_label"],
        "workbenchHint": defaults["workbench_hint"],
        "h5Onboarding": build_h5_user_onboarding_payload(user),
    }


def get_tenant_by_slug(slug=None, site_config=None):
    tenants = get_tenant_configs(site_config)
    target = str(slug or "").strip().lower()
    if not target:
        target = get_default_tenant_slug(site_config)
    for tenant in tenants:
        if tenant["slug"] == target:
            return tenant
    return tenants[0] if tenants else normalize_tenant_config({}, 0)


def get_active_tenant_from_request(site_config=None):
    return get_tenant_by_slug(request.args.get("tenant"), site_config)



def normalize_forecast_tuning_values(source=None):
    payload = source or {}
    normalized = {}
    for key, default_value in DEFAULT_FORECAST_TUNING.items():
        raw = payload.get(key, default_value)
        try:
            normalized[key] = float(raw)
        except Exception:
            normalized[key] = float(default_value)
    normalized["factor_score_clip"] = max(0.5, normalized["factor_score_clip"])
    normalized["factor_signal_limit"] = max(1.0, normalized["factor_signal_limit"])
    normalized["momentum_signal_limit"] = max(1.0, normalized["momentum_signal_limit"])
    normalized["predicted_change_limit"] = max(3.0, normalized["predicted_change_limit"])
    normalized["fundamental_adjustment_limit"] = max(0.0, normalized["fundamental_adjustment_limit"])
    normalized["volatility_cap_multiplier"] = max(0.2, normalized["volatility_cap_multiplier"])
    normalized["backtest_weight"] = max(0.0, min(1.0, normalized["backtest_weight"]))
    normalized["confidence_penalty_scale"] = max(0.0, normalized["confidence_penalty_scale"])
    normalized["confidence_floor"] = max(1.0, min(99.0, normalized["confidence_floor"]))
    normalized["range_bound_multiplier"] = max(0.4, min(1.0, normalized["range_bound_multiplier"]))
    return normalized


def build_forecast_node_catalog():
    return [copy.deepcopy(item) for item in FORECAST_WORKFLOW_NODE_CATALOG]


def build_default_forecast_workflow_graph(tuning=None):
    normalized = normalize_forecast_tuning_values(tuning)
    return {
        "version": 1,
        "title": "预测算法工作流",
        "summary": "展示目标价是怎么计算出来的，并允许在后台调整自动收敛参数。",
        "nodes": [
            {"id": "source_signals", "label": "市场信号输入", "processor": "source", "x": 32, "y": 48, "params": {"source_key": "signals_bundle"}},
            {"id": "source_volatility", "label": "波动率输入", "processor": "source", "x": 32, "y": 188, "params": {"source_key": "volatility_context"}},
            {"id": "source_backtest", "label": "回测输入", "processor": "source", "x": 32, "y": 328, "params": {"source_key": "backtest_context"}},
            {"id": "source_confidence", "label": "置信度输入", "processor": "source", "x": 32, "y": 468, "params": {"source_key": "confidence_context"}},
            {"id": "raw_signal", "label": "原始信号", "processor": "raw_signal", "x": 312, "y": 48, "params": {}},
            {"id": "predicted_clip", "label": "总涨幅限幅", "processor": "clip", "x": 580, "y": 48, "params": {"limit_key": "predicted_change_limit"}},
            {"id": "volatility_cap", "label": "波动率约束", "processor": "volatility_cap", "x": 848, "y": 118, "params": {"multiplier_key": "volatility_cap_multiplier"}},
            {"id": "backtest_shrink", "label": "回测收缩", "processor": "backtest_blend", "x": 1116, "y": 258, "params": {"weight_key": "backtest_weight"}},
            {"id": "confidence_penalty", "label": "置信度惩罚", "processor": "confidence_guard", "x": 1384, "y": 398, "params": {"floor_key": "confidence_floor", "scale_key": "confidence_penalty_scale", "range_key": "range_bound_multiplier"}},
            {"id": "final_output", "label": "最终目标涨跌幅", "processor": "output", "x": 1652, "y": 398, "params": {}},
        ],
        "edges": [
            {"id": "edge_signals_raw", "from": "source_signals", "to": "raw_signal"},
            {"id": "edge_raw_clip", "from": "raw_signal", "to": "predicted_clip"},
            {"id": "edge_clip_vol", "from": "predicted_clip", "to": "volatility_cap"},
            {"id": "edge_vol_ctx", "from": "source_volatility", "to": "volatility_cap"},
            {"id": "edge_vol_backtest", "from": "volatility_cap", "to": "backtest_shrink"},
            {"id": "edge_backtest_ctx", "from": "source_backtest", "to": "backtest_shrink"},
            {"id": "edge_backtest_conf", "from": "backtest_shrink", "to": "confidence_penalty"},
            {"id": "edge_conf_ctx", "from": "source_confidence", "to": "confidence_penalty"},
            {"id": "edge_conf_output", "from": "confidence_penalty", "to": "final_output"},
        ],
        "tuning": normalized,
    }


def normalize_forecast_workflow_graph(payload):
    source = payload if isinstance(payload, dict) else {}
    default_graph = build_default_forecast_workflow_graph(source.get("tuning") if isinstance(source.get("tuning"), dict) else None)
    nodes = source.get("nodes", default_graph["nodes"])
    edges = source.get("edges", default_graph["edges"])
    title = str(source.get("title", default_graph["title"]) or default_graph["title"])
    summary = str(source.get("summary", default_graph["summary"]) or default_graph["summary"])
    tuning = normalize_forecast_tuning_values(source.get("tuning") if isinstance(source.get("tuning"), dict) else default_graph["tuning"])
    catalog_map = {item["processor"]: item for item in FORECAST_WORKFLOW_NODE_CATALOG}
    normalized_nodes = []
    seen_ids = set()
    if isinstance(nodes, list):
        for index, item in enumerate(nodes):
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("id", "")).strip() or f"node_{index + 1}"
            if node_id in seen_ids:
                node_id = f"{node_id}_{index + 1}"
            seen_ids.add(node_id)
            processor = str(item.get("processor", "source")).strip() or "source"
            if processor not in catalog_map:
                processor = "source"
            fallback_node = default_graph["nodes"][min(index, len(default_graph["nodes"]) - 1)]
            normalized_nodes.append(
                {
                    "id": node_id,
                    "label": str(item.get("label", catalog_map[processor]["label"]) or catalog_map[processor]["label"]),
                    "processor": processor,
                    "x": _coerce_float(item.get("x"), fallback_node["x"]),
                    "y": _coerce_float(item.get("y"), fallback_node["y"]),
                    "params": dict(item.get("params", {})) if isinstance(item.get("params"), dict) else {},
                }
            )
    if not normalized_nodes:
        normalized_nodes = copy.deepcopy(default_graph["nodes"])
    node_ids = {item["id"] for item in normalized_nodes}
    normalized_edges = []
    seen_edge_ids = set()
    if isinstance(edges, list):
        for index, item in enumerate(edges):
            if not isinstance(item, dict):
                continue
            from_id = str(item.get("from", "")).strip()
            to_id = str(item.get("to", "")).strip()
            if from_id not in node_ids or to_id not in node_ids or from_id == to_id:
                continue
            edge_id = str(item.get("id", "")).strip() or f"edge_{index + 1}"
            if edge_id in seen_edge_ids:
                edge_id = f"{edge_id}_{index + 1}"
            if any(row["from"] == from_id and row["to"] == to_id for row in normalized_edges):
                continue
            seen_edge_ids.add(edge_id)
            normalized_edges.append({"id": edge_id, "from": from_id, "to": to_id})
    if not normalized_edges:
        normalized_edges = copy.deepcopy(default_graph["edges"])
    default_nodes = copy.deepcopy(default_graph["nodes"])
    default_node_map = {item["id"]: item for item in default_nodes}
    merged_nodes_map = {item["id"]: item for item in normalized_nodes}
    for default_node in default_nodes:
        if default_node["id"] not in merged_nodes_map:
            merged_nodes_map[default_node["id"]] = default_node
    ordered_nodes = [merged_nodes_map[node["id"]] for node in default_nodes if node["id"] in merged_nodes_map]
    ordered_nodes.extend([item for item in normalized_nodes if item["id"] not in default_node_map])
    default_edges = copy.deepcopy(default_graph["edges"])
    merged_edges = list(normalized_edges)
    existing_pairs = {(item["from"], item["to"]) for item in merged_edges}
    for default_edge in default_edges:
        pair = (default_edge["from"], default_edge["to"])
        if pair not in existing_pairs:
            merged_edges.append(default_edge)
            existing_pairs.add(pair)
    return {
        "version": 1,
        "title": title,
        "summary": summary,
        "nodes": ordered_nodes,
        "edges": merged_edges,
        "tuning": tuning,
    }


def workflow_graph_to_tuning(graph):
    normalized_graph = normalize_forecast_workflow_graph(graph)
    tuning = dict(normalized_graph.get("tuning", {}))
    for node in normalized_graph["nodes"]:
        params = node.get("params", {})
        if not isinstance(params, dict):
            continue
        for key in ("limit_key", "multiplier_key", "weight_key", "floor_key", "scale_key", "range_key"):
            tuning_key = str(params.get(key, "")).strip()
            if tuning_key in DEFAULT_FORECAST_TUNING and tuning_key not in tuning:
                tuning[tuning_key] = DEFAULT_FORECAST_TUNING[tuning_key]
    return normalize_forecast_tuning_values(tuning)


def _build_context_preview(context):
    if not isinstance(context, dict):
        return {}
    preview = {}
    for key, value in context.items():
        if isinstance(value, float):
            preview[key] = round(value, 3)
        elif isinstance(value, (int, str)):
            preview[key] = value
    return preview


def _topological_nodes(graph):
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    incoming = {item["id"]: 0 for item in nodes}
    outgoing = {item["id"]: [] for item in nodes}
    for edge in edges:
        if edge["from"] in outgoing and edge["to"] in incoming:
            outgoing[edge["from"]].append(edge["to"])
            incoming[edge["to"]] += 1
    queue = [item["id"] for item in nodes if incoming[item["id"]] == 0]
    ordered = []
    while queue:
        node_id = queue.pop(0)
        ordered.append(node_id)
        for target in outgoing.get(node_id, []):
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    if len(ordered) != len(nodes):
        return [item["id"] for item in nodes]
    return ordered


def _build_runtime_contexts(tuning):
    closes = [100 + idx * 0.28 + ((idx % 7) - 3) * 0.22 for idx in range(90)]
    returns = []
    for idx in range(1, len(closes)):
        prev = closes[idx - 1]
        returns.append((closes[idx] - prev) / prev)
    recent_returns = returns[-30:]
    realized_daily_vol = statistics.pstdev(recent_returns) if len(recent_returns) > 1 else 0.0
    volatility_cap = max(4.0, realized_daily_vol * math.sqrt(20) * 100 * tuning["volatility_cap_multiplier"])
    avg_return_pct = 6.8
    up_probability = 61.5
    sample_size = 18
    sample_confidence = min(1.0, sample_size / 12.0)
    backtest_anchor = avg_return_pct * (0.55 + 0.45 * sample_confidence)
    raw_factor_signal = 11.3
    factor_signal = max(-tuning["factor_signal_limit"], min(tuning["factor_signal_limit"], 9.2))
    momentum_signal = max(-tuning["momentum_signal_limit"], min(tuning["momentum_signal_limit"], 8.4))
    confidence = 68.0
    bullish_confidence = 63.0
    confidence_penalty = max(0.0, (tuning["confidence_floor"] - confidence) * tuning["confidence_penalty_scale"] / 10.0)
    return {
        "signals_bundle": {
            "stance": "震荡偏上",
            "raw_factor_signal": raw_factor_signal,
            "factor_signal": factor_signal,
            "momentum_signal": momentum_signal,
            "fundamental_adjustment": 1.1,
            "bullish_confidence": bullish_confidence,
        },
        "volatility_context": {
            "realized_daily_vol": realized_daily_vol,
            "volatility_cap": volatility_cap,
        },
        "backtest_context": {
            "avg_return_pct": avg_return_pct,
            "up_probability": up_probability,
            "sample_size": sample_size,
            "sample_confidence": sample_confidence,
            "backtest_anchor": backtest_anchor,
        },
        "confidence_context": {
            "confidence": confidence,
            "confidence_floor": tuning["confidence_floor"],
            "confidence_penalty": confidence_penalty,
            "range_bound_multiplier": tuning["range_bound_multiplier"],
        },
    }


def _execute_workflow_node(node, upstream_values, contexts, tuning):
    processor = node.get("processor", "source")
    params = node.get("params", {}) if isinstance(node.get("params"), dict) else {}
    if processor == "source":
        source_key = str(params.get("source_key", "")).strip()
        context = contexts.get(source_key, {})
        label = source_key or "unknown_context"
        return {
            "value": 0.0,
            "formula": f"context[{label}]",
            "note": "提供运行时上下文，不直接产生目标涨跌幅。",
            "context": context,
        }
    if processor == "raw_signal":
        signal_context = {}
        for item in upstream_values:
            if isinstance(item.get("context"), dict):
                signal_context.update(item["context"])
        value = float(signal_context.get("factor_signal", 0)) * 0.45 + float(signal_context.get("momentum_signal", 0)) * 0.35 + float(signal_context.get("fundamental_adjustment", 0)) * 0.2
        value = max(-tuning["factor_score_clip"], min(tuning["factor_score_clip"], value))
        return {
            "value": value,
            "formula": "0.45*因子信号 + 0.35*动量信号 + 0.20*基本面修正",
            "note": "先把多来源强弱合成为单一原始预测信号。",
            "context": signal_context,
        }
    if processor == "clip":
        limit = tuning.get(str(params.get("limit_key", "predicted_change_limit")).strip(), tuning["predicted_change_limit"])
        input_value = float(upstream_values[0].get("value", 0) if upstream_values else 0)
        value = max(-limit, min(limit, input_value))
        return {
            "value": value,
            "formula": f"clip(raw_signal, ±{round(limit, 2)})",
            "note": "限制单轮预测不超过全局上限。",
            "context": {"input_value": input_value, "limit": limit},
        }
    if processor == "volatility_cap":
        input_value = float(upstream_values[0].get("value", 0) if upstream_values else 0)
        volatility_context = {}
        for item in upstream_values:
            if isinstance(item.get("context"), dict):
                volatility_context.update(item["context"])
        cap = float(volatility_context.get("volatility_cap", 0))
        limited = max(-cap, min(cap, input_value))
        return {
            "value": limited,
            "formula": "clip(predicted_change, ±volatility_cap)",
            "note": "按近 30 日波动率压缩目标涨跌幅。",
            "context": dict(volatility_context, input_value=input_value),
        }
    if processor == "backtest_blend":
        input_value = float(upstream_values[0].get("value", 0) if upstream_values else 0)
        backtest_context = {}
        for item in upstream_values:
            if isinstance(item.get("context"), dict):
                backtest_context.update(item["context"])
        weight = tuning.get(str(params.get("weight_key", "backtest_weight")).strip(), tuning["backtest_weight"])
        anchor = float(backtest_context.get("backtest_anchor", 0))
        value = input_value * (1 - weight) + anchor * weight
        return {
            "value": value,
            "formula": f"(1-{round(weight, 2)})*波动率约束后结果 + {round(weight, 2)}*回测锚",
            "note": "把当前信号和历史相似样本均值做加权收缩。",
            "context": dict(backtest_context, input_value=input_value, weight=weight),
        }
    if processor == "confidence_guard":
        input_value = float(upstream_values[0].get("value", 0) if upstream_values else 0)
        confidence_context = {}
        for item in upstream_values:
            if isinstance(item.get("context"), dict):
                confidence_context.update(item["context"])
        penalty = float(confidence_context.get("confidence_penalty", 0))
        range_multiplier = tuning.get(str(params.get("range_key", "range_bound_multiplier")).strip(), tuning["range_bound_multiplier"])
        adjusted = input_value - penalty if input_value >= 0 else input_value + penalty
        adjusted *= range_multiplier
        return {
            "value": adjusted,
            "formula": f"(回测收缩结果 {'-' if input_value >= 0 else '+'} 置信度惩罚) * {round(range_multiplier, 2)}",
            "note": "置信度不够时继续收窄空间，避免目标价过度发散。",
            "context": dict(confidence_context, input_value=input_value, range_multiplier=range_multiplier),
        }
    input_value = float(upstream_values[0].get("value", 0) if upstream_values else 0)
    return {
        "value": input_value,
        "formula": "output(previous_step)",
        "note": "输出当前工作流最终结果。",
        "context": {"input_value": input_value},
    }


def run_forecast_workflow_graph(graph):
    normalized_graph = normalize_forecast_workflow_graph(graph)
    tuning = workflow_graph_to_tuning(normalized_graph)
    contexts = _build_runtime_contexts(tuning)
    ordered_nodes = _topological_nodes(normalized_graph)
    node_lookup = {item["id"]: item for item in normalized_graph["nodes"]}
    incoming_map = {item["id"]: [] for item in normalized_graph["nodes"]}
    for edge in normalized_graph["edges"]:
        incoming_map.setdefault(edge["to"], []).append(edge["from"])
    runtime_values = {}
    steps = []
    node_results = {}
    final_value = 0.0
    for node_id in ordered_nodes:
        node = node_lookup[node_id]
        upstream_values = [runtime_values[source_id] for source_id in incoming_map.get(node_id, []) if source_id in runtime_values]
        result = _execute_workflow_node(node, upstream_values, contexts, tuning)
        runtime_values[node_id] = result
        node_results[node_id] = {
            "label": node["label"],
            "processor": node["processor"],
            "value": round(float(result.get("value", 0) or 0), 2),
            "formula": str(result.get("formula", "")),
            "note": str(result.get("note", "")),
            "context_preview": _build_context_preview(result.get("context")),
        }
        if node["processor"] not in {"source", "output"}:
            steps.append(
                {
                    "key": node_id,
                    "label": node["label"],
                    "formula": str(result.get("formula", "")),
                    "value": round(float(result.get("value", 0) or 0), 2),
                    "note": str(result.get("note", "")),
                    "processor": node["processor"],
                }
            )
        if node["processor"] == "output":
            final_value = float(result.get("value", 0) or 0)
    workflow = {
        "inputs": {
            "raw_factor_signal": 11.3,
            "factor_signal_after_clip": 9.2,
            "momentum_signal": 8.4,
            "fundamental_adjustment": 1.1,
            "bullish_confidence": 63.0,
            "confidence": 68.0,
            "backtest_up_probability": 61.5,
            "backtest_avg_return_pct": 6.8,
            "backtest_sample_size": 18,
        },
        "steps": steps,
        "result": {
            "predicted_change_pct": round(final_value, 2),
            "volatility_cap": round(float(contexts["volatility_context"]["volatility_cap"]), 2),
            "backtest_anchor": round(float(contexts["backtest_context"]["backtest_anchor"]), 2),
            "confidence_penalty": round(float(contexts["confidence_context"]["confidence_penalty"]), 2),
        },
        "graph": normalized_graph,
        "node_results": node_results,
    }
    return final_value, workflow


def build_forecast_workflow_preview(graph):
    _, workflow = run_forecast_workflow_graph(graph)
    return {
        "inputs": workflow.get("inputs", {}),
        "result": workflow.get("result", {}),
        "steps": workflow.get("steps", []),
        "node_results": workflow.get("node_results", {}),
    }


def build_forecast_workflow_meta(graph):
    normalized_graph = normalize_forecast_workflow_graph(graph)
    preview = build_forecast_workflow_preview(normalized_graph)
    graph_with_preview = copy.deepcopy(normalized_graph)
    graph_with_preview["node_results"] = preview.get("node_results", {})
    return {
        "title": str(normalized_graph["title"]),
        "summary": str(normalized_graph["summary"]),
        "graph": graph_with_preview,
        "catalog": build_forecast_node_catalog(),
        "preview": preview,
    }

# Mock data
CHANNELS = ["微信社群", "内容合作", "小红书", "转介绍", "直接流量"]
H5_COMPLIANCE_VERSION = "2026-08"
H5_COMPLIANCE_NOTICE = {
    "title": "个人权益与合规须知",
    "summary": "首次进入前，请确认你已经阅读平台的个人权益说明与研究合规要求。",
    "sections": [
        {
            "title": "个人权益说明",
            "items": [
                "你可以查看与自己所属租户相关的研究内容、知识问答、复盘和互动服务。",
                "你的基础信息、交互记录和研究偏好会用于账号服务、知识记忆和运营分析。",
                "你可以在账号设置和后台治理流程中申请修正、清理或停止部分数据使用。",
            ],
        },
        {
            "title": "法律法规与合规要求",
            "items": [
                "平台内容仅用于研究交流和信息整理，不构成收益承诺或个性化投资建议。",
                "禁止传播违规信息、冒用身份、恶意营销、诱导交易或上传无合法授权的材料。",
                "涉及证券、基金、宏观和个股解读时，应结合公开信息与风险边界独立判断。",
            ],
        },
        {
            "title": "使用确认",
            "items": [
                "继续进入即表示你已知悉平台的研究属性、数据使用说明和合规边界。",
                "若不同意，请退出登录，不继续使用当前 H5 服务。",
            ],
        },
    ],
    "confirm_label": "我已阅读并知悉个人权益说明与合规要求",
}
FUNNEL_LAYERS = ["内容触达", "私域留资", "激活试用", "首次付费", "高频留存"]


def load_market_dashboard_indicators():
    if not MARKET_DASHBOARD_REGISTRY_PATH.exists():
        return []
    try:
        payload = json.loads(MARKET_DASHBOARD_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        app.logger.exception("Failed to load market dashboard source registry")
        return []
    if not isinstance(payload, list):
        return []
    return payload


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def now_ts_ms():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def safe_json_loads(value, default):
    if value in (None, ""):
        return copy.deepcopy(default)
    try:
        parsed = json.loads(value)
    except Exception:
        return copy.deepcopy(default)
    return parsed if isinstance(parsed, type(default)) else copy.deepcopy(default)


def slugify_code(value, fallback="item"):
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip()).strip("_").lower()
    return text or fallback


def _estimate_token_count(text):
    normalized = str(text or "")
    if not normalized:
        return 0
    return max(1, math.ceil(len(normalized) / 4))


def _extract_usage_tokens(payload):
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return 0, 0, 0
    input_tokens = int(
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("prompt_token_count")
        or 0
    )
    output_tokens = int(
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("candidates_token_count")
        or 0
    )
    total_tokens = int(usage.get("total_tokens") or 0)
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens
    return max(0, input_tokens), max(0, output_tokens), max(0, total_tokens)


def log_token_usage(
    usage_type="llm",
    feature_code="",
    feature_label="",
    tenant_slug="",
    entry_point="",
    model_provider="",
    model_name="",
    input_tokens=0,
    output_tokens=0,
    total_tokens=0,
    request_count=1,
    latency_ms=0,
    request_chars=0,
    response_chars=0,
    metadata=None,
):
    usage_code = f"usage_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    db = get_db()
    db.execute(
        """
        INSERT INTO token_usage_logs (
            usage_code, usage_type, feature_code, feature_label, tenant_slug, entry_point,
            model_provider, model_name, request_direction, input_tokens, output_tokens, total_tokens,
            request_count, latency_ms, request_chars, response_chars, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            usage_code,
            str(usage_type or "llm").strip(),
            slugify_code(feature_code, "unknown"),
            str(feature_label or feature_code or "未命名功能").strip()[:120],
            str(tenant_slug or "").strip().lower(),
            str(entry_point or "").strip()[:120],
            str(model_provider or "").strip()[:80],
            str(model_name or "").strip()[:160],
            "bidirectional",
            max(0, int(input_tokens or 0)),
            max(0, int(output_tokens or 0)),
            max(0, int(total_tokens or 0)),
            max(1, int(request_count or 1)),
            max(0, int(latency_ms or 0)),
            max(0, int(request_chars or 0)),
            max(0, int(response_chars or 0)),
            json.dumps(metadata or {}, ensure_ascii=False)[:4000],
            now_ts(),
        ),
    )
    db.commit()
    return usage_code


def build_token_usage_summary(hours=24 * 30):
    db = get_db()
    hours = max(1, min(int(hours or 24 * 30), 24 * 180))
    since_dt = datetime.now() - timedelta(hours=hours)
    since = since_dt.strftime("%Y-%m-%d %H:%M:%S")
    row = db.execute(
        """
        SELECT
            COUNT(*) AS request_count,
            COALESCE(SUM(input_tokens), 0) AS input_tokens,
            COALESCE(SUM(output_tokens), 0) AS output_tokens,
            COALESCE(SUM(total_tokens), 0) AS total_tokens,
            COALESCE(SUM(latency_ms), 0) AS latency_ms
        FROM token_usage_logs
        WHERE created_at >= ?
        """,
        (since,),
    ).fetchone()
    payload = dict(row or {})
    total_requests = int(payload.get("request_count") or 0)
    total_tokens = int(payload.get("total_tokens") or 0)
    latency_rows = db.execute(
        """
        SELECT latency_ms
        FROM token_usage_logs
        WHERE created_at >= ?
          AND latency_ms > 0
        ORDER BY latency_ms ASC
        """,
        (since,),
    ).fetchall()
    latencies = [int(row.get("latency_ms") or 0) for row in latency_rows if int(row.get("latency_ms") or 0) > 0]
    p95_latency_ms = 0
    max_latency_ms = 0
    total_latency_ms = int(payload.get("latency_ms") or 0)
    total_latency_seconds = round(total_latency_ms / 1000, 2)
    if latencies:
        p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1)
        p95_latency_ms = int(latencies[min(p95_index, len(latencies) - 1)])
        max_latency_ms = max(latencies)
    input_tokens = int(payload.get("input_tokens") or 0)
    output_tokens = int(payload.get("output_tokens") or 0)
    return {
        "request_count": total_requests,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "avg_tokens_per_request": round(total_tokens / total_requests, 2) if total_requests else 0,
        "avg_latency_ms": round(total_latency_ms / total_requests, 2) if total_requests else 0,
        "total_latency_ms": total_latency_ms,
        "total_latency_seconds": total_latency_seconds,
        "avg_total_tokens_per_second": round(total_tokens / (total_latency_ms / 1000), 2) if total_latency_ms > 0 else 0,
        "avg_input_tokens_per_second": round(input_tokens / (total_latency_ms / 1000), 2) if total_latency_ms > 0 else 0,
        "avg_output_tokens_per_second": round(output_tokens / (total_latency_ms / 1000), 2) if total_latency_ms > 0 else 0,
        "p95_latency_ms": p95_latency_ms,
        "max_latency_ms": max_latency_ms,
        "window_hours": hours,
    }


def _build_token_usage_timeseries_sql(granularity):
    if granularity == "hour":
        bucket_expr = "TO_CHAR(DATE_TRUNC('hour', created_at::timestamp), 'YYYY-MM-DD HH24:00')"
    elif granularity == "month":
        bucket_expr = "TO_CHAR(DATE_TRUNC('month', created_at::timestamp), 'YYYY-MM')"
    else:
        bucket_expr = "TO_CHAR(DATE_TRUNC('day', created_at::timestamp), 'YYYY-MM-DD')"
    return f"""
        SELECT
            {bucket_expr} AS bucket,
            COUNT(*) AS request_count,
            COALESCE(SUM(input_tokens), 0) AS input_tokens,
            COALESCE(SUM(output_tokens), 0) AS output_tokens,
            COALESCE(SUM(total_tokens), 0) AS total_tokens,
            COALESCE(SUM(latency_ms), 0) AS total_latency_ms
        FROM token_usage_logs
        WHERE created_at >= ?
        GROUP BY 1
        ORDER BY 1 ASC
    """


def get_token_usage_timeseries(granularity="day", hours=24 * 30):
    db = get_db()
    hours = max(1, min(int(hours or 24 * 30), 24 * 365))
    since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    rows = db.execute(_build_token_usage_timeseries_sql(granularity), (since,)).fetchall()
    return [
        {
            "bucket": row.get("bucket"),
            "request_count": int(row.get("request_count") or 0),
            "input_tokens": int(row.get("input_tokens") or 0),
            "output_tokens": int(row.get("output_tokens") or 0),
            "total_tokens": int(row.get("total_tokens") or 0),
            "total_latency_ms": int(row.get("total_latency_ms") or 0),
            "avg_total_tokens_per_second": round(
                int(row.get("total_tokens") or 0) / (int(row.get("total_latency_ms") or 0) / 1000), 2
            ) if int(row.get("total_latency_ms") or 0) > 0 else 0,
            "avg_output_tokens_per_second": round(
                int(row.get("output_tokens") or 0) / (int(row.get("total_latency_ms") or 0) / 1000), 2
            ) if int(row.get("total_latency_ms") or 0) > 0 else 0,
        }
        for row in rows
    ]


def get_token_usage_feature_breakdown(hours=24 * 30, limit=12):
    db = get_db()
    hours = max(1, min(int(hours or 24 * 30), 24 * 365))
    limit = max(1, min(int(limit or 12), 40))
    since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    rows = db.execute(
        """
        SELECT
            feature_code,
            MAX(feature_label) AS feature_label,
            usage_type,
            COUNT(*) AS request_count,
            COALESCE(SUM(input_tokens), 0) AS input_tokens,
            COALESCE(SUM(output_tokens), 0) AS output_tokens,
            COALESCE(SUM(total_tokens), 0) AS total_tokens
        FROM token_usage_logs
        WHERE created_at >= ?
        GROUP BY feature_code, usage_type
        ORDER BY total_tokens DESC, request_count DESC
        LIMIT ?
        """,
        (since, limit),
    ).fetchall()
    return [
        {
            "feature_code": row.get("feature_code") or "",
            "feature_label": row.get("feature_label") or row.get("feature_code") or "",
            "usage_type": row.get("usage_type") or "llm",
            "request_count": int(row.get("request_count") or 0),
            "input_tokens": int(row.get("input_tokens") or 0),
            "output_tokens": int(row.get("output_tokens") or 0),
            "total_tokens": int(row.get("total_tokens") or 0),
        }
        for row in rows
    ]


def get_token_usage_model_breakdown(hours=24 * 30, limit=16):
    db = get_db()
    hours = max(1, min(int(hours or 24 * 30), 24 * 365))
    limit = max(1, min(int(limit or 16), 40))
    since = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    rows = db.execute(
        """
        SELECT
            model_provider,
            model_name,
            usage_type,
            COUNT(*) AS request_count,
            COALESCE(SUM(input_tokens), 0) AS input_tokens,
            COALESCE(SUM(output_tokens), 0) AS output_tokens,
            COALESCE(SUM(total_tokens), 0) AS total_tokens,
            COALESCE(SUM(latency_ms), 0) AS latency_ms
        FROM token_usage_logs
        WHERE created_at >= ?
        GROUP BY model_provider, model_name, usage_type
        ORDER BY total_tokens DESC, request_count DESC
        LIMIT ?
        """,
        (since, limit),
    ).fetchall()
    return [
        {
            "total_latency_ms": int(row.get("latency_ms") or 0),
            "total_latency_seconds": round(int(row.get("latency_ms") or 0) / 1000, 2),
            "model_provider": row.get("model_provider") or "",
            "model_name": row.get("model_name") or "",
            "usage_type": row.get("usage_type") or "llm",
            "request_count": int(row.get("request_count") or 0),
            "input_tokens": int(row.get("input_tokens") or 0),
            "output_tokens": int(row.get("output_tokens") or 0),
            "total_tokens": int(row.get("total_tokens") or 0),
            "avg_latency_ms": round(int(row.get("latency_ms") or 0) / max(1, int(row.get("request_count") or 1)), 2),
            "avg_total_tokens_per_second": round(
                int(row.get("total_tokens") or 0) / (int(row.get("latency_ms") or 0) / 1000), 2
            ) if int(row.get("latency_ms") or 0) > 0 else 0,
            "avg_input_tokens_per_second": round(
                int(row.get("input_tokens") or 0) / (int(row.get("latency_ms") or 0) / 1000), 2
            ) if int(row.get("latency_ms") or 0) > 0 else 0,
            "avg_output_tokens_per_second": round(
                int(row.get("output_tokens") or 0) / (int(row.get("latency_ms") or 0) / 1000), 2
            ) if int(row.get("latency_ms") or 0) > 0 else 0,
        }
        for row in rows
    ]


def get_token_usage_model_daily_breakdown(days=30, limit=8):
    db = get_db()
    days = max(1, min(int(days or 30), 180))
    limit = max(1, min(int(limit or 8), 20))
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    top_models = db.execute(
        """
        SELECT model_provider, model_name
        FROM token_usage_logs
        WHERE created_at >= ?
        GROUP BY model_provider, model_name
        ORDER BY COALESCE(SUM(total_tokens), 0) DESC
        LIMIT ?
        """,
        (since, limit),
    ).fetchall()
    pairs = [(row.get("model_provider") or "", row.get("model_name") or "") for row in top_models]
    if not pairs:
        return []
    conditions = " OR ".join(["(model_provider = ? AND model_name = ?)"] * len(pairs))
    params = [since]
    for provider, name in pairs:
        params.extend([provider, name])
    rows = db.execute(
        f"""
        SELECT
            TO_CHAR(DATE_TRUNC('day', created_at::timestamp), 'YYYY-MM-DD') AS bucket,
            model_provider,
            model_name,
            COALESCE(SUM(total_tokens), 0) AS total_tokens
        FROM token_usage_logs
        WHERE created_at >= ?
          AND ({conditions})
        GROUP BY 1, model_provider, model_name
        ORDER BY bucket ASC, total_tokens DESC
        """,
        tuple(params),
    ).fetchall()
    return [
        {
            "bucket": row.get("bucket") or "",
            "model_provider": row.get("model_provider") or "",
            "model_name": row.get("model_name") or "",
            "total_tokens": int(row.get("total_tokens") or 0),
        }
        for row in rows
    ]


def get_token_usage_recent_logs(limit=80):
    db = get_db()
    rows = db.execute(
        """
        SELECT *
        FROM token_usage_logs
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (max(1, min(int(limit or 80), 200)),),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        total_latency_ms = int(item.get("latency_ms") or 0)
        input_tokens = int(item.get("input_tokens") or 0)
        output_tokens = int(item.get("output_tokens") or 0)
        total_tokens = int(item.get("total_tokens") or 0)
        item["avg_total_tokens_per_second"] = round(total_tokens / (total_latency_ms / 1000), 2) if total_latency_ms > 0 else 0
        item["avg_input_tokens_per_second"] = round(input_tokens / (total_latency_ms / 1000), 2) if total_latency_ms > 0 else 0
        item["avg_output_tokens_per_second"] = round(output_tokens / (total_latency_ms / 1000), 2) if total_latency_ms > 0 else 0
        items.append(item)
    return items


def build_admin_token_usage_payload():
    return {
        "summary_24h": build_token_usage_summary(hours=24),
        "summary_30d": build_token_usage_summary(hours=24 * 30),
        "hourly": get_token_usage_timeseries(granularity="hour", hours=24),
        "daily": get_token_usage_timeseries(granularity="day", hours=24 * 30),
        "monthly": get_token_usage_timeseries(granularity="month", hours=24 * 180),
        "features": get_token_usage_feature_breakdown(hours=24 * 30, limit=16),
        "models": get_token_usage_model_breakdown(hours=24 * 30, limit=16),
        "model_daily": get_token_usage_model_daily_breakdown(days=30, limit=8),
        "recent_logs": get_token_usage_recent_logs(limit=80),
        "generated_at": now_ts(),
    }


def coerce_float(value, default=None):
    try:
        text = str(value).replace("%", "").replace(",", "").strip()
        if not text:
            return default
        return float(text)
    except Exception:
        return default


def normalize_datetime_text(value):
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
    return text[:19].replace("T", " ")


def extract_timestamp_from_fields(fields, fallback=""):
    values = [str(item or "").strip() for item in fields if str(item or "").strip()]
    for item in values:
        normalized = normalize_datetime_text(item)
        if normalized:
            return normalized
    for index, item in enumerate(values[:-1]):
        if re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}", item) and re.fullmatch(r"\d{2}:\d{2}:\d{2}", values[index + 1]):
            return normalize_datetime_text(f"{item} {values[index + 1]}")
        if re.fullmatch(r"\d{2}:\d{2}:\d{2}", item) and re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}", values[index + 1]):
            return normalize_datetime_text(f"{values[index + 1]} {item}")
    return normalize_datetime_text(fallback or now_ts())


def load_db_runtime_config():
    defaults = {"use_staging": False}
    try:
        if not DB_RUNTIME_CONFIG_PATH.exists():
            return dict(defaults)
        payload = json.loads(DB_RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(defaults)
    if not isinstance(payload, dict):
        return dict(defaults)
    return {
        "use_staging": bool(payload.get("use_staging", False)),
        "updated_at": str(payload.get("updated_at") or "").strip(),
    }


def save_db_runtime_config(use_staging):
    payload = {
        "use_staging": bool(use_staging),
        "updated_at": now_ts(),
    }
    DB_RUNTIME_CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def get_runtime_db_target():
    runtime = load_db_runtime_config()
    use_staging = bool(runtime.get("use_staging"))
    if use_staging:
        app_db = {
            "host": APP_DB_HOST,
            "port": APP_DB_PORT,
            "dbname": APP_DB_NAME,
            "user": APP_DB_USER,
            "password": APP_DB_PASSWORD,
            "label": "staging",
        }
        vector_db = {
            "host": VECTOR_DB_HOST,
            "port": VECTOR_DB_PORT,
            "dbname": VECTOR_DB_NAME,
            "user": VECTOR_DB_USER,
            "password": VECTOR_DB_PASSWORD,
            "label": "staging",
        }
    else:
        app_db = {
            "host": LOCAL_POSTGRES_HOST,
            "port": LOCAL_POSTGRES_PORT,
            "dbname": LOCAL_POSTGRES_DB,
            "user": LOCAL_POSTGRES_USER,
            "password": LOCAL_POSTGRES_PASSWORD,
            "label": "local",
        }
        vector_db = {
            "host": LOCAL_VECTOR_DB_HOST,
            "port": LOCAL_VECTOR_DB_PORT,
            "dbname": LOCAL_VECTOR_DB_NAME,
            "user": LOCAL_VECTOR_DB_USER,
            "password": LOCAL_VECTOR_DB_PASSWORD,
            "label": "local",
        }
    return {
        "use_staging": use_staging,
        "mode": "staging" if use_staging else "local",
        "updated_at": runtime.get("updated_at") or "",
        "app": app_db,
        "vector": vector_db,
    }


def get_staging_app_db_target():
    return {
        "host": APP_DB_HOST,
        "port": APP_DB_PORT,
        "dbname": APP_DB_NAME,
        "user": APP_DB_USER,
        "password": APP_DB_PASSWORD,
        "label": "staging",
    }


def get_local_app_db_target():
    return {
        "host": LOCAL_POSTGRES_HOST,
        "port": LOCAL_POSTGRES_PORT,
        "dbname": LOCAL_POSTGRES_DB,
        "user": LOCAL_POSTGRES_USER,
        "password": LOCAL_POSTGRES_PASSWORD,
        "label": "local",
    }


def reset_request_runtime_state():
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass
    g.pop("site_config", None)
    g.pop("forecast_workflow_graph", None)


def build_admin_site_config_payload(site_config=None):
    payload = copy.deepcopy(site_config or get_site_config())
    payload["auth_settings"] = get_auth_settings(payload, include_secret=True)
    runtime_target = get_runtime_db_target()
    payload["db_runtime"] = {
        "use_staging": runtime_target.get("use_staging", False),
        "mode": runtime_target.get("mode", "local"),
        "updated_at": runtime_target.get("updated_at", ""),
        "app_host": runtime_target.get("app", {}).get("host", ""),
        "app_port": runtime_target.get("app", {}).get("port", ""),
        "app_db_name": runtime_target.get("app", {}).get("dbname", ""),
        "vector_host": runtime_target.get("vector", {}).get("host", ""),
        "vector_port": runtime_target.get("vector", {}).get("port", ""),
        "vector_db_name": runtime_target.get("vector", {}).get("dbname", ""),
    }
    payload["llm_feature_catalog"] = copy.deepcopy(DEFAULT_LLM_FEATURE_CATALOG)
    payload["news_aggregation_algorithm_defaults"] = {
        "version": "v3",
        "script_js": (
            "function rankNews(input) {\n"
            "  const normalize = (value) => String(value || '').replace(/[\\s\\u3000·•/|_|-]+/g, ' ').trim();\n"
            "  const compact = (value) => String(value || '').replace(/[\\s\\u3000·•/|_|-.]/g, '').trim();\n"
            "  const tags = Array.isArray(input.item.tags) ? input.item.tags.map(normalize).filter(Boolean) : [];\n"
            "  const text = normalize([input.item.title, input.item.content, input.item.summary].filter(Boolean).join(' '));\n"
            "  const compactText = compact(text);\n"
            "  const sectorTokens = Array.isArray(input.watchlistSectors) ? input.watchlistSectors.map(normalize).filter(Boolean) : [];\n"
            "  const sectorAliases = {'港股互联网':['互联网','平台经济','港股','腾讯','阿里','美团','百度','快手'],'半导体制造':['半导体','芯片','集成电路','晶圆','存储','光刻'],'高端白酒':['白酒','贵州茅台','五粮液','泸州老窖'],'动力电池':['动力电池','锂电','新能源车','宁德时代'],'银行':['银行','信贷','息差','存款','贷款']};\n"
            "  const symbolTokens = Array.isArray(input.watchlistSymbols) ? input.watchlistSymbols.map(normalize).filter(Boolean) : [];\n"
            "  const majorKeywords = ['重大利好','重大利空','重大风险','突发','紧急','重磅','立案调查','行政处罚','停牌','退市','暴雷','违约','降准','降息','加息','出口管制','关税上调','重大订单','中标','业绩预增','业绩预亏','回购','增持','减持','并购重组','重大资产重组'];\n"
            "  const sectorMatch = sectorTokens.some(tag => [tag, ...(sectorAliases[tag] || [])].some(term => text.includes(term)));\n"
            "  const symbolMatch = symbolTokens.some(tag => text.includes(tag) || compactText.includes(compact(tag)));\n"
            "  const majorSignal = Boolean(input.item.isMajorPositive || input.item.isMajorNegative)\n"
            "    || majorKeywords.some(keyword => text.includes(keyword));\n"
            "  return {\n"
            "    score: ((sectorMatch || symbolMatch) ? 220 : 0) + (symbolMatch ? 65 : 0) + (majorSignal ? 100 : 0),\n"
            "    bucket: (sectorMatch || symbolMatch) ? 'watchlist_sector' : (majorSignal ? 'major_market' : 'other'),\n"
            "    reason: (sectorMatch || symbolMatch) ? '命中自选股行业板块或标的' : (majorSignal ? '命中社会性重大利好/利空或高影响事件' : '其他公开信息'),\n"
            "    matched_topics: [\n"
            "      ...new Set([\n"
            "        ...sectorTokens.filter(tag => [tag, ...(sectorAliases[tag] || [])].some(term => text.includes(term))),\n"
            "        ...symbolTokens.filter(tag => text.includes(tag) || compactText.includes(compact(tag))),\n"
            "        ...majorKeywords.filter(keyword => text.includes(keyword))\n"
            "      ])\n"
            "    ]\n"
            "  };\n"
            "}"
        ),
        "strategy": "watchlist_sector_first",
        "rule_plan": {
            "version": "v1",
            "candidate_scope": {"watchlist_related": True, "major_events": True},
            "priority_order": ["watchlist_sector", "major_market"],
            "filters": {"exclude_unrelated": True},
            "presentation": {"home_limit": 10},
            "diversity": {"max_per_source": 3, "max_per_group": 4},
        },
        "rule_atoms": [
            {"group": "候选范围", "key": "watchlist_related", "label": "自选股关联"},
            {"group": "候选范围", "key": "major_events", "label": "重大事件补充"},
            {"group": "排序", "key": "watchlist_sector", "label": "行业优先"},
            {"group": "过滤", "key": "exclude_unrelated", "label": "过滤无关内容"},
            {"group": "展示", "key": "home_limit", "label": "首页 10 条"},
            {"group": "配额", "key": "source_cap", "label": "单一来源最多 3 条"},
        ],
    }
    return payload



def get_app_db_connection():
    target = get_runtime_db_target().get("app", {})
    return psycopg2.connect(
        host=target.get("host") or APP_DB_HOST,
        port=target.get("port") or APP_DB_PORT,
        dbname=target.get("dbname") or APP_DB_NAME,
        user=target.get("user") or APP_DB_USER,
        password=target.get("password") or APP_DB_PASSWORD,
        connect_timeout=8,
    )


def get_db_connection_for_target(target):
    db_target = target if isinstance(target, dict) else {}
    return psycopg2.connect(
        host=db_target.get("host") or APP_DB_HOST,
        port=db_target.get("port") or APP_DB_PORT,
        dbname=db_target.get("dbname") or APP_DB_NAME,
        user=db_target.get("user") or APP_DB_USER,
        password=db_target.get("password") or APP_DB_PASSWORD,
        connect_timeout=8,
    )


def _extract_site_config_payload(row):
    raw_value = None
    if isinstance(row, dict):
        raw_value = row.get("setting_value")
    elif row is not None:
        try:
            raw_value = row["setting_value"]
        except Exception:
            raw_value = None
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str) and raw_value.strip():
        try:
            decoded = json.loads(raw_value)
        except Exception:
            app.logger.exception("Failed to decode site config payload from direct db read")
            return {}
        if isinstance(decoded, dict):
            return decoded
    return {}


def load_site_config_from_db_target(target):
    config = copy.deepcopy(DEFAULT_SITE_CONFIG)
    connection = get_db_connection_for_target(target)
    try:
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = %s",
            (SITE_CONFIG_KEY,),
        )
        stored = _extract_site_config_payload(cursor.fetchone())
        if stored:
            config = _merge_site_config(config, stored)
    finally:
        connection.close()
    return normalize_site_config(config)


def save_site_config_to_db_target(config, target):
    merged = normalize_site_config(config)
    connection = get_db_connection_for_target(target)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO app_settings (setting_key, setting_value, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT(setting_key) DO UPDATE SET
                setting_value = excluded.setting_value,
                updated_at = excluded.updated_at
            """,
            (
                SITE_CONFIG_KEY,
                json.dumps(merged, ensure_ascii=False),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return merged


def sync_local_llm_registry_from_staging():
    local_target = get_local_app_db_target()
    staging_target = get_staging_app_db_target()
    local_site_config = load_site_config_from_db_target(local_target)
    staging_site_config = load_site_config_from_db_target(staging_target)
    next_local_site_config = copy.deepcopy(local_site_config)
    next_local_site_config["llm_registry"] = normalize_llm_registry_config(
        staging_site_config.get("llm_registry")
    )
    saved_local_site_config = save_site_config_to_db_target(next_local_site_config, local_target)
    runtime_target = get_runtime_db_target()
    if not bool(runtime_target.get("use_staging")):
        g.site_config = saved_local_site_config
    registry = normalize_llm_registry_config(saved_local_site_config.get("llm_registry"))
    return {
        "local_site_config": saved_local_site_config,
        "local_llm_registry": registry,
        "synced_model_count": len(registry.get("models") or []),
        "default_model_key": registry.get("default_model_key") or "",
        "current_runtime_uses_staging": bool(runtime_target.get("use_staging")),
        "local_db_target": {
            "label": local_target.get("label") or "local",
            "host": local_target.get("host") or "",
            "port": local_target.get("port") or "",
            "dbname": local_target.get("dbname") or "",
        },
        "staging_db_target": {
            "label": staging_target.get("label") or "staging",
            "host": staging_target.get("host") or "",
            "port": staging_target.get("port") or "",
            "dbname": staging_target.get("dbname") or "",
        },
    }


def is_db_unavailable_error(error):
    return isinstance(error, OperationalError)


def build_default_demo_profiles(site_config=None):
    config = site_config or normalize_site_config(DEFAULT_SITE_CONFIG)
    profiles = []
    for item in DEFAULT_USERS:
        try:
          profiles.append(ensure_user_row_defaults(dict(item), config))
        except Exception:
          continue
    return [profile for profile in profiles if profile.get("role") in {"investor", "dav"} and profile.get("status") == "active"]


def resolve_demo_profile_fallback(site_config=None):
    profiles = build_default_demo_profiles(site_config)
    current_username = get_current_demo_profile_id()
    current = next((profile for profile in profiles if profile.get("username") == current_username), None)
    if current is None and profiles:
        current = profiles[0]
    return profiles, current


def build_access_summary_fallback():
    return {
        "summary": {
            "total": 0,
            "unique_ips": 0,
            "today": 0,
            "paths": 0,
        },
        "top_paths": [],
        "top_ips": [],
        "daily_counts": [],
        "recent_logs": [],
        "fallback_mode": True,
    }


def build_tenant_dashboard_payload_fallback(tenant=None):
    tenant = tenant or normalize_tenant_config({}, 0)
    return {
        "title": tenant.get("dashboard_title") or f"{tenant.get('short_name') or tenant.get('name') or '租户'} Dashboard",
        "description": tenant.get("dashboard_description") or "当前展示为数据库不可达时的降级数据视图。",
        "tenant": tenant,
        "kpis": [
            {"label": "今日互动", "value": "128", "delta": "+12%"},
            {"label": "重点复盘", "value": "3", "delta": "待发布"},
            {"label": "关注信号", "value": "2", "delta": "优先跟踪"},
            {"label": "粉丝提问", "value": "19", "delta": "待回应"},
        ],
        "message_distribution": [],
        "message_trend": [],
        "publish_distribution": [],
        "publish_trend": [],
        "fund_dashboard": {
            "layout": "2x2",
            "cards": [],
        },
        "fund_dashboard_state": {
            "published": {"layout": "2x2", "cards": []},
            "draft": None,
        },
        "smart_indicator_catalog": {
            "tenant_smart_indicators": [],
            "base_indicators": [],
            "available_tags": [],
        },
        "fan_stock_observation": {
            "window_days": 7,
            "summary": "当前展示为数据库不可达时的降级视图，暂不提供真实粉丝个股观察数据。",
            "totals": {
                "interactions": 0,
                "detail_views": 0,
                "hermes_queries": 0,
                "active_fans": 0,
                "sector_count": 0,
            },
            "hot_sector": "",
            "sectors": [],
            "top_stocks": [],
            "fallback_mode": True,
            "tracked_stock_codes": [],
        },
        "watchlist_comment_analytics": {
            "summary": {
                "total_comments": 0,
                "investor_comments": 0,
                "dav_comments": 0,
                "stock_count": 0,
            },
            "keyword_cloud": [],
            "label_distribution": [],
            "sentiment_distribution": [],
            "recent_comments": [],
            "fallback_mode": True,
        },
        "fan_management": {
            "summary": "数据库不可达时暂不展示真实粉丝管理数据。",
            "stats": {
                "total_fans": 0,
                "new_fans_7d": 0,
                "active_fans_30d": 0,
                "paying_fans": 0,
            },
            "settings": _normalize_tenant_fan_ops_settings({}),
            "fans": [],
        },
        "reviews": [],
        "stats": {
            "total_followers": 0,
            "vip_subscribers": 0,
            "monthly_revenue": 0,
            "revenue_change": 0.0,
            "unread_messages": 0,
            "pending_replies": 0,
            "today_views": 0,
            "today_active_viewers": 0,
            "today_view_distribution": [],
            "today_view_trend_7d": [],
            "engagement_rate": 0.0,
            "registration_price": 0,
            "new_paid_samples_month": 0,
            "paid_sample_delta": 0,
            "stock_comment_count": 0,
            "stock_comment_stock_count": 0,
            "fan_ops_settings": _normalize_tenant_fan_ops_settings({}),
        },
    }


def build_indicator_hub_fallback(tenant=None, admin_view=False):
    return {
        "summary": {"total": 0, "smart_total": 0, "lake_total": 0, "enabled": 0, "warnings": 0, "attention": 0, "anomalies": 0},
        "items": [],
        "smart_items": [],
        "lake_items": [],
        "anomalies": [],
        "definitions": [],
        "source_defs": [],
        "recent_tests": [],
        "load_batches": [],
        "raw_records": [],
        "mapping_rules": [],
        "clean_jobs": [],
        "data_unavailable": True,
    }


def build_fundamental_column_payload_from_hub(tenant, indicator_hub):
    tenant = tenant or get_tenant_by_slug()
    smart_items = list((indicator_hub or {}).get("smart_items") or [])
    anomalies = list((indicator_hub or {}).get("anomalies") or [])
    top_signals = sorted(
        smart_items,
        key=lambda item: (0 if item.get("status") == "warning" else (1 if item.get("status") == "attention" else 2), item.get("last_updated") or ""),
    )[:3]
    summary_bits = [f"{item.get('name')}: {item.get('assessment') or item.get('alert') or '继续观察'}" for item in top_signals]
    summary = "；".join(summary_bits) if summary_bits else f"{tenant.get('advisor') or '主理投顾'} 当前暂无新的重点指标解读。"
    entries = []
    for index, item in enumerate(top_signals):
        entries.append(
            {
                "title": item.get("name") or f"重点信号 {index + 1}",
                "source": "指标湖",
                "sourceDetail": item.get("category") or "核心指标",
                "summary": item.get("assessment") or item.get("alert") or "继续观察",
                "status": "ready",
                "angle": ["宏观视角", "行业视角", "验证节点"][index] if index < 3 else "研究视角",
            }
        )
    for anomaly in anomalies[:2]:
        entries.append(
            {
                "title": anomaly.get("title") or "异动提醒",
                "source": "异动监测",
                "sourceDetail": anomaly.get("time") or "最新",
                "summary": anomaly.get("summary") or "",
                "status": "ready",
                "angle": "异动跟踪",
            }
        )
    return {
        "summary": summary,
        "entries": entries[:4],
    }


def build_indicator_dashboard_seed_cards_from_hub(indicator_hub, count=8):
    cards = []
    for item in list((indicator_hub or {}).get("smart_items") or []) + list((indicator_hub or {}).get("lake_items") or []):
        cards.append(
            {
                "name": item.get("name") or "指标",
                "value": item.get("value") or "--",
                "assessment": item.get("assessment") or item.get("alert") or "继续观察",
                "status": item.get("status") or "attention",
                "alert": item.get("alert") or "",
                "hint": item.get("alert") or item.get("assessment") or "",
                "prompt": f"直接引用指标湖信号：{item.get('name') or '指标'}，用于工作台和前台基本面首页。",
                "sourceType": item.get("source_type") or "",
            }
        )
    return cards[:count]


def execute_sql_file(conn, sql_path):
    sql_text = Path(sql_path).read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql_text)
    conn.commit()


def init_db():
    sql_dir = PROJECT_ROOT / "sql" / "postgres"
    with get_app_db_connection() as conn:
        execute_sql_file(conn, sql_dir / "002_app_core_tables.sql")
        execute_sql_file(conn, sql_dir / "003_admin_task_configs_task_params.sql")
        execute_sql_file(conn, sql_dir / "004_schema_migrations.sql")
        execute_sql_file(conn, sql_dir / "010_review_voice_embeddings.sql")
        execute_sql_file(conn, sql_dir / "011_review_voice_embeddings_alter_legacy_columns.sql")
        try:
            execute_sql_file(conn, sql_dir / "001_enable_pgvector.sql")
            execute_sql_file(conn, sql_dir / "012_review_voice_embeddings_pgvector.sql")
            execute_sql_file(conn, sql_dir / "020_knowledge_embeddings.sql")
            execute_sql_file(conn, sql_dir / "021_knowledge_embeddings_pgvector.sql")
        except Exception:
            conn.rollback()
            execute_sql_file(conn, sql_dir / "020_knowledge_embeddings.sql")
        execute_sql_file(conn, sql_dir / "022_hermes_memory_profile.sql")
        execute_sql_file(conn, sql_dir / "023_fan_stock_observation_events.sql")
        execute_sql_file(conn, sql_dir / "024_watchlist_kline_annotations.sql")
        execute_sql_file(conn, sql_dir / "025_watchlist_comments.sql")
        execute_sql_file(conn, sql_dir / "026_tenant_fan_ops.sql")
        execute_sql_file(conn, sql_dir / "027_h5_auth_wechat.sql")
        execute_sql_file(conn, sql_dir / "028_h5_user_onboarding.sql")
        execute_sql_file(conn, sql_dir / "029_user_labels.sql")
        execute_sql_file(conn, sql_dir / "030_market_snapshot_payloads.sql")
        execute_sql_file(conn, sql_dir / "032_simulated_fan_data_management.sql")
        execute_sql_file(conn, sql_dir / "100_seed_master_data.sql")
        execute_sql_file(conn, sql_dir / "101_seed_app_core.sql")
        execute_sql_file(conn, sql_dir / "102_seed_market_sector_catalog.sql")
        execute_sql_file(conn, sql_dir / "103_seed_market_index_catalog.sql")


def init_db_safe():
    try:
        init_db()
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable during startup init, skipping init_db")


def should_auto_init_db():
    if AUTO_INIT_DB_MODE in {"1", "true", "yes", "on", "always"}:
        return True
    if AUTO_INIT_DB_MODE in {"0", "false", "no", "off", "never"}:
        return False
    if AUTO_INIT_DB_MODE == "dev":
        return os.environ.get("DEBUG", "1").lower() in {"1", "true", "yes", "y"}
    return False


def is_debug_mode_enabled():
    return os.environ.get("DEBUG", "1").lower() in {"1", "true", "yes", "y"}


def is_werkzeug_reloader_parent():
    return is_debug_mode_enabled() and os.environ.get("WERKZEUG_RUN_MAIN") != "true"


def startup_bootstrap():
    if is_werkzeug_reloader_parent():
        app.logger.info("Skipping startup bootstrap in Werkzeug reloader parent process")
        return
    if should_auto_init_db():
        init_db_safe()
    try:
        with app.app_context():
            seed_result = ensure_default_users()
            if seed_result["created"]:
                app.logger.info("Seeded %s default users into app database", len(seed_result["created"]))
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable during default user init, skipping default user seed")
    try:
        with app.app_context():
            ensure_default_admin_tasks()
    except Exception as exc:
        if not is_db_unavailable_error(exc):
            raise
        app.logger.warning("Database unavailable during task-center init, skipping default tasks")
    ensure_task_center_started()
    ensure_user_async_job_worker_started()


def get_db():
    if "db" not in g:
        g.db = PgCompatConnection(get_app_db_connection())
    return g.db


def ensure_default_admin_tasks():
    from src.domain.market_services import DEFAULT_ADMIN_TASKS, normalize_admin_task_config

    db = get_db()
    timestamp = now_ts()
    for raw in DEFAULT_ADMIN_TASKS:
        item = normalize_admin_task_config(raw)
        existing = db.execute(
            "SELECT task_code FROM admin_task_configs WHERE task_code = ?",
            (item["task_code"],),
        ).fetchone()
        if existing:
            continue
        db.execute(
            """
            INSERT INTO admin_task_configs (
                task_code, task_name, task_group, task_type, description, task_params_json, schedule_type,
                schedule_value, enabled, timeout_seconds, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["task_code"],
                item["task_name"],
                item["task_group"],
                item["task_type"],
                item["description"],
                item["task_params_json"],
                item["schedule_type"],
                item["schedule_value"],
                item["enabled"],
                item["timeout_seconds"],
                timestamp,
                timestamp,
            ),
        )
    db.commit()


def row_to_admin_task_config(row):
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    item["timeout_seconds"] = int(item.get("timeout_seconds") or 600)
    item["task_params"] = safe_json_loads(item.get("task_params_json"), {})
    return item


def row_to_user_async_job(row):
    item = dict(row)
    item["payload"] = safe_json_loads(item.get("payload_json"), {})
    item["result"] = safe_json_loads(item.get("result_json"), {})
    item["progress_percent"] = int(item.get("progress_percent") or 0)
    item["retry_count"] = int(item.get("retry_count") or 0)
    return item


def create_user_async_job(job_type, payload=None, tenant_slug="", entry_point="", owner_label="", trigger_source="user"):
    payload = payload if isinstance(payload, dict) else {}
    timestamp = now_ts()
    job_code = f"{slugify_code(job_type, 'job')}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    db = get_db()
    db.execute(
        """
        INSERT INTO user_async_jobs (
            job_code, job_type, tenant_slug, entry_point, trigger_source, owner_label,
            payload_json, status, progress_stage, progress_percent, summary,
            error_message, result_json, retry_count, created_at, started_at, finished_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_code,
            slugify_code(job_type, "job"),
            str(tenant_slug or "").strip().lower(),
            str(entry_point or "").strip(),
            str(trigger_source or "user").strip(),
            str(owner_label or "").strip(),
            json.dumps(payload, ensure_ascii=False),
            "pending",
            "queued",
            0,
            "任务已进入队列",
            "",
            "{}",
            0,
            timestamp,
            "",
            "",
            timestamp,
        ),
    )
    db.commit()
    return get_user_async_job(job_code)


def get_user_async_job(job_code):
    if not job_code:
        return None
    db = get_db()
    row = db.execute(
        "SELECT * FROM user_async_jobs WHERE job_code = ?",
        (str(job_code).strip(),),
    ).fetchone()
    return row_to_user_async_job(row) if row else None


def list_user_async_jobs(tenant_slug=None, status=None, job_type=None, limit=50):
    db = get_db()
    limit = max(1, min(int(limit or 50), USER_ASYNC_JOB_LOG_LIMIT))
    filters = []
    params = []
    if tenant_slug:
        filters.append("tenant_slug = ?")
        params.append(str(tenant_slug).strip().lower())
    if status:
        filters.append("status = ?")
        params.append(str(status).strip().lower())
    if job_type:
        filters.append("job_type = ?")
        params.append(slugify_code(job_type, "job"))
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    rows = db.execute(
        f"""
        SELECT * FROM user_async_jobs
        {where}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        params + [limit],
    ).fetchall()
    return [row_to_user_async_job(row) for row in rows]


def update_user_async_job(job_code, **fields):
    if not job_code or not fields:
        return None
    allowed = {
        "status",
        "progress_stage",
        "progress_percent",
        "summary",
        "error_message",
        "result_json",
        "started_at",
        "finished_at",
        "retry_count",
        "payload_json",
    }
    updates = []
    params = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        updates.append(f"{key} = ?")
        params.append(value)
    if not updates:
        return get_user_async_job(job_code)
    updates.append("updated_at = ?")
    params.append(now_ts())
    params.append(str(job_code).strip())
    db = get_db()
    db.execute(f"UPDATE user_async_jobs SET {', '.join(updates)} WHERE job_code = ?", params)
    db.commit()
    return get_user_async_job(job_code)


def report_user_async_job_progress(job_code, stage="", percent=None, summary="", log_text="", extra_result=None):
    job = get_user_async_job(job_code)
    if not job:
        return None
    result_payload = copy.deepcopy(job.get("result")) if isinstance(job.get("result"), dict) else {}
    live_log = result_payload.get("live_log") if isinstance(result_payload.get("live_log"), list) else []
    if log_text:
        live_log.append({
            "at": now_ts(),
            "stage": str(stage or job.get("progress_stage") or "").strip(),
            "text": str(log_text).strip()[:240],
        })
        result_payload["live_log"] = live_log[-12:]
    if isinstance(extra_result, dict):
        result_payload.update(copy.deepcopy(extra_result))
    fields = {
        "result_json": json.dumps(result_payload, ensure_ascii=False)[:20000],
    }
    if stage:
        fields["progress_stage"] = str(stage).strip()
    if percent is not None:
        fields["progress_percent"] = max(0, min(100, int(percent)))
    if summary:
        fields["summary"] = str(summary).strip()[:240]
    return update_user_async_job(job_code, **fields)


def retry_user_async_job(job_code):
    job = get_user_async_job(job_code)
    if not job:
        raise ValueError("job_not_found")
    update_user_async_job(
        job_code,
        status="pending",
        progress_stage="queued",
        progress_percent=0,
        summary="任务已重新排队",
        error_message="",
        result_json="{}",
        started_at="",
        finished_at="",
        retry_count=int(job.get("retry_count") or 0) + 1,
    )
    return get_user_async_job(job_code)


def _build_voice_file_storage_from_job_payload(payload):
    raw_base64 = str(payload.get("audio_base64") or "").strip()
    if not raw_base64:
        raise ValueError("audio_payload_required")
    try:
        audio_bytes = base64.b64decode(raw_base64)
    except Exception as exc:
        raise ValueError("audio_payload_invalid") from exc
    filename = str(payload.get("filename") or "review-audio.webm").strip() or "review-audio.webm"
    content_type = str(payload.get("content_type") or "").strip()

    class _MemoryUpload:
        def __init__(self, data, upload_name, mimetype):
            self._data = data
            self.filename = upload_name
            self.mimetype = mimetype

        def read(self):
            return self._data

    return _MemoryUpload(audio_bytes, filename, content_type)


def execute_user_async_job(job):
    job_type = str(job.get("job_type") or "").strip()
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    job_code = str(job.get("job_code") or "").strip()
    if job_type == "review_voice_transcribe":
        file_storage = _build_voice_file_storage_from_job_payload(payload)
        return process_review_voice_upload(
            file_storage=file_storage,
            tenant_slug=str(payload.get("tenant_slug") or "").strip().lower(),
            review_period=str(payload.get("period") or "").strip().lower(),
            entry_point=str(payload.get("entry_point") or "").strip().lower(),
            speaker_name=str(payload.get("speaker_name") or "").strip(),
            use_llm_enhancement=bool(payload.get("use_llm_enhancement")),
            job_code=job_code,
        )
    if job_type == "review_generate_draft":
        return generate_review_draft_with_llm(
            source_text=payload.get("source_text"),
            review_period=str(payload.get("period") or "").strip().lower(),
            source_mode=str(payload.get("source_mode") or "").strip().lower(),
            prompt_text=payload.get("prompt_text"),
            prompt_tags=payload.get("prompt_tags") if isinstance(payload.get("prompt_tags"), list) else [],
            selected_watchlist=payload.get("selected_watchlist") if isinstance(payload.get("selected_watchlist"), list) else [],
            speaker_name=str(payload.get("speaker_name") or "").strip(),
            entry_point=str(payload.get("entry_point") or "").strip(),
            tenant_slug=str(payload.get("tenant_slug") or "").strip().lower(),
            job_code=job_code,
        )
    if job_type == "review_polish_input":
        return polish_review_input_with_llm(
            source_text=payload.get("source_text"),
            review_period=str(payload.get("period") or "").strip().lower(),
            source_mode=str(payload.get("source_mode") or "").strip().lower(),
            speaker_name=str(payload.get("speaker_name") or "").strip(),
            entry_point=str(payload.get("entry_point") or "").strip(),
            tenant_slug=str(payload.get("tenant_slug") or "").strip().lower(),
            job_code=job_code,
        )
    if job_type == "review_compose_draft":
        return compose_review_draft_with_llm(
            source_text=payload.get("source_text"),
            review_period=str(payload.get("period") or "").strip().lower(),
            prompt_text=payload.get("prompt_text"),
            prompt_tags=payload.get("prompt_tags") if isinstance(payload.get("prompt_tags"), list) else [],
            selected_watchlist=payload.get("selected_watchlist") if isinstance(payload.get("selected_watchlist"), list) else [],
            speaker_name=str(payload.get("speaker_name") or "").strip(),
            entry_point=str(payload.get("entry_point") or "").strip(),
            tenant_slug=str(payload.get("tenant_slug") or "").strip().lower(),
            dashboard_cards=payload.get("dashboard_cards") if isinstance(payload.get("dashboard_cards"), list) else [],
            knowledge_items=payload.get("knowledge_items") if isinstance(payload.get("knowledge_items"), list) else [],
            job_code=job_code,
        )
    if job_type == "review_prepare_preview":
        return compose_review_structured_preview(
            source_text=payload.get("source_text"),
            review_period=str(payload.get("period") or "").strip().lower(),
            source_mode=str(payload.get("source_mode") or "").strip().lower(),
            selected_watchlist=payload.get("selected_watchlist") if isinstance(payload.get("selected_watchlist"), list) else [],
            speaker_name=str(payload.get("speaker_name") or "").strip(),
            entry_point=str(payload.get("entry_point") or "").strip(),
            tenant_slug=str(payload.get("tenant_slug") or "").strip().lower(),
            job_code=job_code,
            include_summary=bool(payload.get("include_summary", True)),
        )
    if job_type == "review_publish_embed":
        tenant_slug = str(payload.get("tenant_slug") or "").strip().lower()
        publish_result = process_review_publish_text(
            text=payload.get("text"),
            tenant_slug=tenant_slug,
            review_period=str(payload.get("period") or "").strip().lower(),
            entry_point=str(payload.get("entry_point") or "").strip().lower(),
            speaker_name=str(payload.get("speaker_name") or "").strip(),
            transcription_engine=str(payload.get("transcription_engine") or "manual").strip().lower() or "manual",
            transcript_model=str(payload.get("transcript_model") or "manual_input").strip() or "manual_input",
            job_code=job_code,
        )
        if payload.get("snapshot_sync_applied"):
            tenant = get_tenant_by_slug(tenant_slug)
            snapshots = resolve_tenant_review_snapshots(tenant, tenant.get("review_snapshots"))
            message_state = resolve_tenant_message_center_state(tenant, tenant.get("message_center_state"))
            snapshot_id = str(payload.get("snapshot_id") or "").strip()
            snapshot = next((item for item in snapshots if str(item.get("id") or "").strip() == snapshot_id), None)
            snapshot_result = {
                "snapshot": snapshot or (snapshots[0] if snapshots else None),
                "snapshots": snapshots,
                "message_center_state": message_state,
            }
        else:
            snapshot_result = persist_review_publish_snapshot(
                tenant_slug=tenant_slug,
                text=payload.get("text"),
                review_period=str(payload.get("period") or "").strip().lower(),
                review_title=str(payload.get("review_title") or "").strip(),
                speaker_name=str(payload.get("speaker_name") or "").strip(),
                source_mode=str(payload.get("source_mode") or "manual").strip().lower() or "manual",
                paragraph_mode=str(payload.get("paragraph_mode") or "manual").strip().lower() or "manual",
                selected_watchlist=payload.get("selected_watchlist") if isinstance(payload.get("selected_watchlist"), list) else [],
                prompt_tags=payload.get("prompt_tags") if isinstance(payload.get("prompt_tags"), list) else [],
                knowledge_attachments=payload.get("knowledge_attachments") if isinstance(payload.get("knowledge_attachments"), list) else [],
                selected_cards=payload.get("selected_cards") if isinstance(payload.get("selected_cards"), list) else [],
                data_sources=payload.get("data_sources") if isinstance(payload.get("data_sources"), list) else [],
                news_sources=payload.get("news_sources") if isinstance(payload.get("news_sources"), list) else [],
                llm_models=payload.get("llm_models") if isinstance(payload.get("llm_models"), list) else [],
                polished_input_text=payload.get("polished_input_text"),
                review_summary=payload.get("review_summary"),
                user_input_section=payload.get("user_input_section") if isinstance(payload.get("user_input_section"), dict) else {},
                watchlist_analysis_section=payload.get("watchlist_analysis_section") if isinstance(payload.get("watchlist_analysis_section"), dict) else {},
            )
        return {
            **publish_result,
            **snapshot_result,
        }
    if job_type == "knowledge_manual_sync":
        return save_manual_knowledge_entry(
            tenant_slug=str(payload.get("tenant_slug") or "").strip().lower(),
            title=payload.get("title"),
            summary=payload.get("summary"),
            body=payload.get("body"),
            raw_html=payload.get("raw_html"),
            notes=payload.get("notes"),
            notes_html=payload.get("notes_html"),
            knowledge_id=payload.get("id"),
            skip_ai_processing=bool(payload.get("skip_ai_processing", True)),
            processing_mode=payload.get("processing_mode"),
            knowledge_type=str(payload.get("knowledge_type") or "manual").strip().lower(),
            source_label=payload.get("source_label"),
            source_detail=payload.get("source_detail"),
            tags=payload.get("tags"),
            files=payload.get("files"),
            source_url=payload.get("url"),
            voice_minutes=payload.get("voice_minutes"),
            parse_meta=payload.get("parse_meta"),
            job_code=job_code,
        )
    raise ValueError(f"unsupported_user_async_job_type:{job_type}")


def _summarize_user_async_job_result(job_type, result):
    if job_type == "review_voice_transcribe":
        return "语音转写完成"
    if job_type == "review_polish_input":
        return "复盘输入润色完成"
    if job_type == "review_compose_draft":
        return "复盘完整成稿完成"
    if job_type == "review_generate_draft":
        return "复盘草稿生成完成"
    if job_type == "review_prepare_preview":
        return "复盘结构化预览完成"
    if job_type == "review_publish_embed":
        return "复盘发布入向量完成"
    if job_type == "knowledge_manual_sync":
        return "知识入库同步完成"
    return "任务执行完成"


def build_user_async_jobs_payload(tenant_slug=None, status=None, job_type=None, limit=50):
    jobs = list_user_async_jobs(tenant_slug=tenant_slug, status=status, job_type=job_type, limit=limit)
    summary = {
        "total": len(jobs),
        "pending": sum(1 for item in jobs if item.get("status") == "pending"),
        "running": sum(1 for item in jobs if item.get("status") == "running"),
        "failed": sum(1 for item in jobs if item.get("status") == "failed"),
        "success": sum(1 for item in jobs if item.get("status") == "success"),
    }
    return {"summary": summary, "jobs": jobs}


def list_admin_task_configs():
    ensure_default_admin_tasks()
    db = get_db()
    rows = db.execute(
        """
        SELECT * FROM admin_task_configs
        ORDER BY task_group ASC, task_code ASC
        """
    ).fetchall()
    return [row_to_admin_task_config(row) for row in rows]


def get_admin_task_config(task_code):
    if not task_code:
        return None
    ensure_default_admin_tasks()
    db = get_db()
    row = db.execute(
        "SELECT * FROM admin_task_configs WHERE task_code = ?",
        (slugify_code(task_code, "task"),),
    ).fetchone()
    return row_to_admin_task_config(row) if row else None


def save_admin_task_config(payload):
    from src.domain.market_services import normalize_admin_task_config

    normalized = normalize_admin_task_config(payload, existing=get_admin_task_config(payload.get("task_code")))
    existing = get_admin_task_config(normalized["task_code"])
    db = get_db()
    timestamp = now_ts()
    db.execute(
        """
        INSERT INTO admin_task_configs (
            task_code, task_name, task_group, task_type, description, task_params_json, schedule_type,
            schedule_value, enabled, timeout_seconds, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(task_code) DO UPDATE SET
            task_name = excluded.task_name,
            task_group = excluded.task_group,
            task_type = excluded.task_type,
            description = excluded.description,
            task_params_json = excluded.task_params_json,
            schedule_type = excluded.schedule_type,
            schedule_value = excluded.schedule_value,
            enabled = excluded.enabled,
            timeout_seconds = excluded.timeout_seconds,
            updated_at = excluded.updated_at
        """,
        (
            normalized["task_code"],
            normalized["task_name"],
            normalized["task_group"],
            normalized["task_type"],
            normalized["description"],
            normalized["task_params_json"],
            normalized["schedule_type"],
            normalized["schedule_value"],
            normalized["enabled"],
            normalized["timeout_seconds"],
            existing["created_at"] if existing else timestamp,
            timestamp,
        ),
    )
    db.commit()
    return get_admin_task_config(normalized["task_code"])


def list_admin_task_runs(task_code=None, limit=50):
    ensure_default_admin_tasks()
    db = get_db()
    limit = max(1, min(int(limit or 50), TASK_CENTER_LOG_LIMIT))
    if task_code:
        rows = db.execute(
            """
            SELECT * FROM admin_task_runs
            WHERE task_code = ?
            ORDER BY started_at DESC, id DESC
            LIMIT ?
            """,
            (slugify_code(task_code, "task"), limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM admin_task_runs
            ORDER BY started_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_admin_task_status(task_code, **fields):
    if not task_code or not fields:
        return
    db = get_db()
    timestamp = now_ts()
    allowed = {
        "last_run_started_at",
        "last_run_finished_at",
        "last_run_status",
        "last_run_message",
        "last_run_duration_ms",
        "last_next_run_at",
        "last_error_at",
        "last_error_message",
    }
    updates = []
    params = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        updates.append(f"{key} = ?")
        params.append(value)
    if not updates:
        return
    updates.append("updated_at = ?")
    params.append(timestamp)
    params.append(slugify_code(task_code, "task"))
    db.execute(
        f"UPDATE admin_task_configs SET {', '.join(updates)} WHERE task_code = ?",
        params,
    )
    db.commit()


def create_admin_task_run(task, trigger_mode="scheduler"):
    db = get_db()
    run_code = f"{task['task_code']}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    timestamp = now_ts()
    db.execute(
        """
        INSERT INTO admin_task_runs (
            run_code, task_code, trigger_mode, run_status, started_at, finished_at,
            duration_ms, summary, error_message, result_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_code,
            task["task_code"],
            trigger_mode,
            "running",
            timestamp,
            "",
            0,
            "",
            "",
            "{}",
            timestamp,
        ),
    )
    db.commit()
    update_admin_task_status(
        task["task_code"],
        last_run_started_at=timestamp,
        last_run_status="running",
        last_run_message=f"任务已开始（{trigger_mode}）",
    )
    return run_code


def finish_admin_task_run(run_code, task_code, success, started_at_perf, summary="", error_message="", result=None):
    db = get_db()
    finished_at = now_ts()
    duration_ms = int((time.perf_counter() - started_at_perf) * 1000)
    run_status = "success" if success else "failed"
    db.execute(
        """
        UPDATE admin_task_runs
        SET run_status = ?, finished_at = ?, duration_ms = ?, summary = ?, error_message = ?, result_json = ?
        WHERE run_code = ?
        """,
        (
            run_status,
            finished_at,
            duration_ms,
            (summary or "")[:500],
            (error_message or "")[:2000],
            json.dumps(result or {}, ensure_ascii=False)[:12000],
            run_code,
        ),
    )
    db.commit()
    updates = {
        "last_run_finished_at": finished_at,
        "last_run_status": run_status,
        "last_run_message": (summary or error_message or run_status)[:240],
        "last_run_duration_ms": duration_ms,
    }
    if success:
        updates["last_error_message"] = ""
    else:
        updates["last_error_at"] = finished_at
        updates["last_error_message"] = (error_message or summary or "任务执行失败")[:500]
    update_admin_task_status(task_code, **updates)


def execute_admin_task_by_type(task_type, force=False):
    from src.domain.market_services import (
        invalidate_indicator_hub_cache,
        prepare_indicator_hub_store,
        sync_market_snapshot,
        seed_mock_indicator_lake,
        sync_real_indicator_history_from_market_cache,
    )

    if task_type == "prepare_indicator_hub":
        return prepare_indicator_hub_store(force=force)
    if task_type == "sync_real_indicator_history":
        result = sync_real_indicator_history_from_market_cache(force=force)
        invalidate_indicator_hub_cache()
        return result
    if task_type == "sync_market_snapshot":
        return sync_market_snapshot(force=force)
    if task_type == "seed_mock_indicator_lake":
        result = seed_mock_indicator_lake(force=force)
        invalidate_indicator_hub_cache()
        return result
    raise ValueError(f"unsupported_task_type:{task_type}")


def execute_admin_task(task, force=False):
    task_type = task["task_type"]
    params = task.get("task_params") if isinstance(task.get("task_params"), dict) else {}
    if task_type in {"prepare_indicator_hub", "sync_real_indicator_history", "seed_mock_indicator_lake"}:
        return execute_admin_task_by_type(task_type, force=force)
    if task_type == "indicator_source_landing":
        source_code = str(params.get("source_code") or "").strip()
        if not source_code:
            raise ValueError("task_source_code_required")
        prefer_live = bool(params.get("prefer_live"))
        return execute_indicator_source_landing(source_code=source_code, prefer_live=prefer_live or force)
    if task_type == "indicator_clean_pipeline":
        source_code = str(params.get("source_code") or "").strip() or None
        rule_code = str(params.get("rule_code") or "").strip() or None
        raw_record_id = params.get("raw_record_id")
        if not source_code and not raw_record_id:
            raise ValueError("task_source_code_or_raw_record_required")
        return run_indicator_clean_job(source_code=source_code, rule_code=rule_code, raw_record_id=raw_record_id)
    if task_type == "knowledge_manual_sync":
        tenant_slug = str(params.get("tenant_slug") or "").strip().lower()
        body = str(params.get("body") or "").strip()
        if not tenant_slug:
            raise ValueError("task_tenant_slug_required")
        if not body:
            raise ValueError("task_body_required")
        return save_manual_knowledge_entry(
            tenant_slug=tenant_slug,
            title=params.get("title"),
            summary=params.get("summary"),
            body=body,
            raw_html=params.get("raw_html"),
            notes=params.get("notes"),
            notes_html=params.get("notes_html"),
            knowledge_id=params.get("knowledge_id"),
            skip_ai_processing=bool(params.get("skip_ai_processing", True)),
            processing_mode=params.get("processing_mode"),
        )
    if task_type == "review_publish_embed":
        tenant_slug = str(params.get("tenant_slug") or "").strip().lower()
        text = str(params.get("text") or "").strip()
        if not tenant_slug:
            raise ValueError("task_tenant_slug_required")
        if not text:
            raise ValueError("task_text_required")
        return process_review_publish_text(
            text=text,
            tenant_slug=tenant_slug,
            review_period=str(params.get("review_period") or "").strip(),
            entry_point=str(params.get("entry_point") or "task_center").strip(),
            speaker_name=str(params.get("speaker_name") or "").strip(),
            transcription_engine=str(params.get("transcription_engine") or "manual").strip(),
            transcript_model=str(params.get("transcript_model") or "manual_input").strip(),
        )
    if task_type == "knowledge_query_batch":
        tenant_slug = str(params.get("tenant_slug") or "").strip().lower()
        queries = params.get("queries")
        if isinstance(queries, str):
            queries = [item.strip() for item in re.split(r"[\n]+", queries) if item.strip()]
        if not tenant_slug:
            raise ValueError("task_tenant_slug_required")
        if not isinstance(queries, list) or not queries:
            raise ValueError("task_queries_required")
        results = []
        for query in queries[:20]:
            results.append(
                build_knowledge_query_response(
                    tenant_slug=tenant_slug,
                    query_text=str(query),
                    limit=int(params.get("limit") or 5),
                    submit_to_model=bool(params.get("submit_to_model")),
                )
            )
        return {
            "tenant_slug": tenant_slug,
            "count": len(results),
            "results": results,
        }
    raise ValueError(f"unsupported_task_type:{task_type}")


def run_admin_task(task_code, trigger_mode="manual", force=False):
    task = get_admin_task_config(task_code)
    if not task:
        raise ValueError("task_not_found")
    start_perf = time.perf_counter()
    run_code = create_admin_task_run(task, trigger_mode=trigger_mode)
    try:
        result = execute_admin_task(task, force=force)
        summary = "任务执行完成"
        if task["task_type"] == "prepare_indicator_hub":
            summary = "指标中心预处理完成"
        elif task["task_type"] == "sync_real_indicator_history":
            summary = "真实历史同步完成"
        elif task["task_type"] == "seed_mock_indicator_lake":
            summary = "模拟指标入口已关闭"
        elif task["task_type"] == "indicator_source_landing":
            summary = "指标原始数据落地完成"
        elif task["task_type"] == "indicator_clean_pipeline":
            summary = "指标清洗入湖完成"
        elif task["task_type"] == "knowledge_manual_sync":
            summary = "知识库同步入向量完成"
        elif task["task_type"] == "review_publish_embed":
            summary = "纪要文本向量补录完成"
        elif task["task_type"] == "knowledge_query_batch":
            summary = "知识检索批处理完成"
        finish_admin_task_run(run_code, task["task_code"], True, start_perf, summary=summary, result=result)
        return {"run_code": run_code, "task": task, "summary": summary, "result": result}
    except Exception as exc:
        finish_admin_task_run(
            run_code,
            task["task_code"],
            False,
            start_perf,
            summary="任务执行失败",
            error_message=str(exc),
            result={"error_type": type(exc).__name__},
        )
        raise


def build_admin_task_center_payload():
    tasks = list_admin_task_configs()
    runs = list_admin_task_runs(limit=60)
    user_jobs = list_user_async_jobs(limit=60)
    now_ts_text = now_ts()
    with _task_center_lock:
        runtime = copy.deepcopy(_task_center_runtime)
    with _user_async_job_lock:
        user_job_runtime = copy.deepcopy(_user_async_job_runtime)
    summary = {
        "total": len(tasks),
        "enabled": sum(1 for task in tasks if task.get("enabled")),
        "running": sum(1 for task in tasks if str(task.get("last_run_status") or "") == "running"),
        "failed": sum(1 for task in tasks if str(task.get("last_run_status") or "") == "failed"),
        "now": now_ts_text,
    }
    return {
        "summary": summary,
        "tasks": tasks,
        "runs": runs,
        "runtime": runtime,
        "user_jobs": user_jobs,
        "user_job_runtime": user_job_runtime,
    }


def _task_should_run(task, now_epoch):
    from src.domain.market_services import parse_task_interval_seconds

    if not task.get("enabled"):
        return False, None
    interval_seconds = parse_task_interval_seconds(task)
    if not interval_seconds:
        return False, None
    last_started = str(task.get("last_run_started_at") or "").strip()
    if not last_started:
        return True, interval_seconds
    try:
        last_dt = datetime.strptime(last_started, "%Y-%m-%d %H:%M:%S")
        due = last_dt.timestamp() + interval_seconds
    except Exception:
        return True, interval_seconds
    return now_epoch >= due, interval_seconds


def _task_center_loop():
    while True:
        try:
            with app.app_context():
                tasks = list_admin_task_configs()
                now_epoch = time.time()
                next_run_map = {}
                for task in tasks:
                    should_run, interval_seconds = _task_should_run(task, now_epoch)
                    if interval_seconds:
                        if task.get("last_run_started_at"):
                            try:
                                last_dt = datetime.strptime(task["last_run_started_at"], "%Y-%m-%d %H:%M:%S")
                                next_run_map[task["task_code"]] = datetime.fromtimestamp(last_dt.timestamp() + interval_seconds).strftime("%Y-%m-%d %H:%M:%S")
                            except Exception:
                                next_run_map[task["task_code"]] = ""
                        else:
                            next_run_map[task["task_code"]] = now_ts()
                        update_admin_task_status(task["task_code"], last_next_run_at=next_run_map[task["task_code"]])
                    if not should_run:
                        continue
                    run_admin_task(task["task_code"], trigger_mode="scheduler", force=False)
                with _task_center_lock:
                    _task_center_runtime["last_poll_at"] = now_ts()
                    _task_center_runtime["tasks_seen"] = len(tasks)
        except Exception as exc:
            with _task_center_lock:
                _task_center_runtime["last_poll_error"] = str(exc)
                _task_center_runtime["last_poll_at"] = now_ts()
        time.sleep(TASK_CENTER_POLL_INTERVAL_SECONDS)


def ensure_task_center_started():
    global _task_center_thread, _task_center_started
    if _task_center_started:
        return
    with _task_center_lock:
        if _task_center_started:
            return
        _task_center_thread = threading.Thread(target=_task_center_loop, name="admin-task-center", daemon=True)
        _task_center_thread.start()
        _task_center_started = True
        _task_center_runtime["started_at"] = now_ts()


def _claim_next_user_async_job():
    conn = get_app_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, job_code
                FROM user_async_jobs
                WHERE status = 'pending'
                ORDER BY created_at ASC, id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None
            started_at = now_ts()
            cur.execute(
                """
                UPDATE user_async_jobs
                SET status = %s,
                    progress_stage = %s,
                    progress_percent = %s,
                    summary = %s,
                    started_at = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                ("running", "processing", 15, "任务开始执行", started_at, started_at, row["id"]),
            )
        conn.commit()
    finally:
        conn.close()
    with app.app_context():
        return get_user_async_job(row["job_code"])


def _complete_user_async_job(job_code, success, summary="", result=None, error_message=""):
    with app.app_context():
        update_user_async_job(
            job_code,
            status="success" if success else "failed",
            progress_stage="completed" if success else "failed",
            progress_percent=100 if success else 100,
            summary=(summary or ("任务执行完成" if success else "任务执行失败"))[:240],
            error_message=(error_message or "")[:2000],
            result_json=json.dumps(result or {}, ensure_ascii=False)[:20000],
            finished_at=now_ts(),
        )


def _user_async_job_loop():
    while True:
        try:
            job = _claim_next_user_async_job()
            if not job:
                with _user_async_job_lock:
                    _user_async_job_runtime["last_poll_at"] = now_ts()
                    _user_async_job_runtime["queue_state"] = "idle"
                time.sleep(USER_ASYNC_JOB_POLL_INTERVAL_SECONDS)
                continue
            with _user_async_job_lock:
                _user_async_job_runtime["last_poll_at"] = now_ts()
                _user_async_job_runtime["queue_state"] = "running"
                _user_async_job_runtime["current_job_code"] = job.get("job_code")
                _user_async_job_runtime["current_job_type"] = job.get("job_type")
            with app.app_context():
                update_user_async_job(job["job_code"], progress_stage="processing", progress_percent=45, summary="任务处理中")
                result = execute_user_async_job(job)
                summary = _summarize_user_async_job_result(job.get("job_type"), result)
                _complete_user_async_job(job["job_code"], True, summary=summary, result=result)
        except Exception as exc:
            current_job_code = ""
            with _user_async_job_lock:
                current_job_code = str(_user_async_job_runtime.get("current_job_code") or "")
                _user_async_job_runtime["last_error_at"] = now_ts()
                _user_async_job_runtime["last_error_message"] = str(exc)
            if current_job_code:
                _complete_user_async_job(
                    current_job_code,
                    False,
                    summary="任务执行失败",
                    result={"error_type": type(exc).__name__},
                    error_message=str(exc),
                )
            elif is_db_unavailable_error(exc):
                app.logger.warning("User async job loop database unavailable, retrying: %s", exc)
                time.sleep(USER_ASYNC_JOB_POLL_INTERVAL_SECONDS)
            else:
                app.logger.exception("User async job loop failed without claimed job")
                time.sleep(USER_ASYNC_JOB_POLL_INTERVAL_SECONDS)
        finally:
            with _user_async_job_lock:
                _user_async_job_runtime["last_poll_at"] = now_ts()
                _user_async_job_runtime["current_job_code"] = ""
                _user_async_job_runtime["current_job_type"] = ""


def ensure_user_async_job_worker_started():
    global _user_async_job_thread, _user_async_job_started
    if is_werkzeug_reloader_parent():
        return
    if _user_async_job_started:
        return
    with _user_async_job_lock:
        if _user_async_job_started:
            return
        _user_async_job_thread = threading.Thread(target=_user_async_job_loop, name="user-async-jobs", daemon=True)
        _user_async_job_thread.start()
        _user_async_job_started = True
        _user_async_job_runtime["started_at"] = now_ts()
        _user_async_job_runtime["queue_state"] = "booting"


def _merge_site_config(base, override):
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_site_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_site_config():
    cached = g.get("site_config")
    if cached is not None:
        return cached
    g.site_config_db_unavailable = False
    config = copy.deepcopy(DEFAULT_SITE_CONFIG)
    try:
        db = get_db()
        row = db.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?",
            (SITE_CONFIG_KEY,),
        ).fetchone()
        if row and row["setting_value"]:
            try:
                stored = json.loads(row["setting_value"])
                if isinstance(stored, dict):
                    config = _merge_site_config(config, stored)
            except Exception:
                app.logger.exception("Failed to parse site config")
    except Exception as exc:
        if is_db_unavailable_error(exc):
            g.site_config_db_unavailable = True
            app.logger.warning("Database unavailable while loading site config, using defaults")
        else:
            raise
    config = normalize_site_config(config)
    g.site_config = config
    return config


def save_site_config(config):
    merged = normalize_site_config(config)
    db = get_db()
    db.execute(
        """
        INSERT INTO app_settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at = excluded.updated_at
        """,
        (
            SITE_CONFIG_KEY,
            json.dumps(merged, ensure_ascii=False),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    db.commit()
    g.site_config = merged
    return merged


def load_forecast_workflow_graph():
    cached = g.get("forecast_workflow_graph")
    if cached is not None:
        return cached
    db = get_db()
    row = db.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = ?",
        (FORECAST_WORKFLOW_KEY,),
    ).fetchone()
    graph = build_default_forecast_workflow_graph()
    if row and row["setting_value"]:
        try:
            stored = json.loads(row["setting_value"])
            graph = normalize_forecast_workflow_graph(stored)
        except Exception:
            app.logger.exception("Failed to parse forecast workflow graph")
    g.forecast_workflow_graph = graph
    return graph


def save_forecast_workflow_graph(graph):
    normalized = normalize_forecast_workflow_graph(graph)
    db = get_db()
    db.execute(
        """
        INSERT INTO app_settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at = excluded.updated_at
        """,
        (
            FORECAST_WORKFLOW_KEY,
            json.dumps(normalized, ensure_ascii=False),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    db.commit()
    g.forecast_workflow_graph = normalized
    return normalized


@app.context_processor
def inject_site_config():
    config = get_site_config()
    return {
        "site_config": config,
        "brand_config": get_platform_brand(config),
        "tenant_configs": get_tenant_configs(config),
        "default_tenant_slug": get_default_tenant_slug(config),
    }
