import re

from src.runtime import *
from src.domain.core_services import slugify_code


GRAPH_GENERIC_TAGS = {
    "手动编写", "观点沉淀", "pdf", "框架资料", "网页资料", "外部来源",
    "语音纪要", "方法框架", "已入向量库", "纯文本编写", "文件上传", "网页 url",
    "知识专区", "租户知识队列", "hermes 上下文", "向量知识库",
}

GRAPH_STOPWORDS = {
    "老师", "当前", "继续", "需要", "进行", "相关", "内容", "资料", "整理",
    "知识", "条目", "最新", "长期", "同步", "阶段", "观点", "框架", "方法", "验证",
}

GRAPH_ENTITY_ALIASES = {
    "上证50": ["上证50", "上证50指数", "sse 50"],
    "上证指数": ["上证指数", "上证综指", "沪指", "sh000001"],
    "纳斯达克指数": ["纳斯达克", "纳斯达克指数", "nasdaq", "纳指"],
    "腾讯控股": ["腾讯", "腾讯控股", "00700"],
    "美团-W": ["美团", "美团-w", "3690"],
    "阿里巴巴-W": ["阿里", "阿里巴巴", "阿里巴巴-w", "9988"],
    "中芯国际": ["中芯国际", "0981", "688981"],
    "贵州茅台": ["贵州茅台", "茅台", "600519"],
    "CPI": ["cpi", "居民消费价格指数"],
    "PPI": ["ppi", "工业生产者出厂价格指数"],
    "PMI": ["pmi", "采购经理指数"],
    "美联储": ["美联储", "fed", "fomc"],
    "南向资金": ["南向资金", "南下资金"],
    "北向资金": ["北向资金", "北上资金"],
    "人民币汇率": ["人民币汇率", "汇率", "usd/cny", "美元兑人民币"],
}

GRAPH_METHOD_MAP = {
    "复盘四步法": ["复盘四步法", "四步法"],
    "证据链过滤框架": ["证据链", "证据链过滤", "证据归因"],
    "基本面判断框架": ["基本面判断", "基本面分析", "基本面框架"],
    "智能指标公式": ["智能指标", "提示词公式", "公式引用"],
    "自选股归纳法": ["自选股归纳", "板块归纳", "逐股归纳"],
}

GRAPH_SIGNAL_MAP = {
    "南向资金回流": ["南向资金", "南下资金", "净流入"],
    "北向资金变化": ["北向资金", "北上资金", "净流入"],
    "成交结构变化": ["成交结构", "成交占比", "换手结构"],
    "估值修复": ["估值修复", "估值带", "估值扩张"],
    "利润率改善": ["利润率", "毛利率", "净利率"],
    "订单兑现": ["订单", "量产", "送测", "出货"],
    "库存去化": ["库存", "去库", "补库"],
    "资本开支变化": ["capex", "资本开支"],
    "汇率波动": ["人民币汇率", "汇率", "美元强弱"],
    "通胀压力": ["cpi", "ppi", "通胀"],
    "政策路径": ["政策", "降息", "美联储", "财政"],
}

GRAPH_TOPIC_HINTS = {
    "港股互联网": ["港股互联网", "腾讯控股", "美团-w", "阿里巴巴-w"],
    "AI算力": ["ai", "算力", "服务器", "gpu"],
    "半导体国产替代": ["半导体", "中芯国际", "国产替代", "晶圆"],
    "消费复苏": ["消费", "贵州茅台", "动销", "渠道"],
    "宏观通胀": ["cpi", "ppi", "通胀", "美联储"],
    "资金流与成交": ["南向资金", "北向资金", "成交结构", "换手"],
}


def _normalize_graph_text(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_graph_key(value):
    return re.sub(r"\s+", "", str(value or "").strip()).lower()


def _graph_trim_text(value, limit=56):
    text = _normalize_graph_text(value)
    if len(text) <= limit:
        return text
    return f"{text[:max(0, limit - 1)]}…"


def _collect_graph_source_text(item):
    tags = item.get("tags") if isinstance(item.get("tags"), list) else []
    key_points = item.get("key_points") if isinstance(item.get("key_points"), list) else []
    validation_nodes = item.get("validation_nodes") if isinstance(item.get("validation_nodes"), list) else []
    tuning_focus = item.get("tuning_focus") if isinstance(item.get("tuning_focus"), list) else []
    segments = [
        item.get("title"),
        item.get("summary"),
        item.get("raw_input"),
        item.get("body"),
        item.get("source_detail"),
        item.get("notes"),
        " ".join(str(tag) for tag in tags),
        " ".join(str(tag) for tag in key_points),
        " ".join(str(tag) for tag in validation_nodes),
        " ".join(str(tag) for tag in tuning_focus),
    ]
    return _normalize_graph_text("\n".join(str(segment or "") for segment in segments if str(segment or "").strip()))


def _dedupe_text_list(items, limit=8):
    normalized = []
    seen = set()
    for raw in items if isinstance(items, list) else []:
        text = _normalize_graph_text(raw)
        if not text:
            continue
        key = _normalize_graph_key(text)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _split_topic_fragments(*values):
    fragments = []
    for value in values:
        text = _normalize_graph_text(value)
        if not text:
            continue
        pieces = re.split(r"[、,，/；;\n·\|\(\)（）【】]+", text)
        for piece in pieces:
            candidate = _normalize_graph_text(piece)
            if not candidate or len(candidate) < 2 or len(candidate) > 18:
                continue
            if _normalize_graph_key(candidate) in GRAPH_GENERIC_TAGS:
                continue
            if candidate in GRAPH_STOPWORDS:
                continue
            fragments.append(candidate)
    return _dedupe_text_list(fragments, limit=12)


def _extract_bracket_entities(text):
    matches = re.findall(r"[【\[]([^】\]]+)[】\]]", str(text or ""))
    return _dedupe_text_list(matches, limit=8)


def _match_alias_entities(text):
    normalized_text = _normalize_graph_key(text)
    matches = []
    for canonical, aliases in GRAPH_ENTITY_ALIASES.items():
        alias_keys = [_normalize_graph_key(alias) for alias in aliases]
        if any(alias_key and alias_key in normalized_text for alias_key in alias_keys):
            matches.append(canonical)
    return _dedupe_text_list(matches, limit=12)


def _match_keyword_labels(text, mapping, limit=8):
    normalized_text = _normalize_graph_key(text)
    matches = []
    for label, aliases in mapping.items():
        alias_keys = [_normalize_graph_key(alias) for alias in aliases]
        if any(alias_key and alias_key in normalized_text for alias_key in alias_keys):
            matches.append(label)
    return _dedupe_text_list(matches, limit=limit)


def _extract_topics(item, text):
    tags = [tag for tag in (item.get("tags") if isinstance(item.get("tags"), list) else []) if _normalize_graph_key(tag) not in GRAPH_GENERIC_TAGS]
    title_fragments = _split_topic_fragments(item.get("title"), item.get("summary"))
    hints = []
    normalized_text = _normalize_graph_key(text)
    for label, aliases in GRAPH_TOPIC_HINTS.items():
        if any(_normalize_graph_key(alias) in normalized_text for alias in aliases):
            hints.append(label)
    return _dedupe_text_list(list(tags) + title_fragments + hints, limit=10)


def _extract_graph_questions(item, topics, entities):
    explicit = re.findall(r"[^。！？!?]{4,40}[？?]", _collect_graph_source_text(item))
    if explicit:
        return _dedupe_text_list(explicit, limit=3)
    subject = topics[0] if topics else (entities[0] if entities else _normalize_graph_text(item.get("title") or "当前知识主题"))
    return [f"{subject} 当前应该如何理解和跟踪？"]


def _extract_graph_claims(item):
    summary = _normalize_graph_text(item.get("summary"))
    key_points = _dedupe_text_list(item.get("key_points") if isinstance(item.get("key_points"), list) else [], limit=2)
    claims = []
    if summary:
      claims.append(summary)
    for point in key_points:
      if len(claims) >= 2:
          break
      if _normalize_graph_key(point) != _normalize_graph_key(summary):
          claims.append(point)
    return _dedupe_text_list(claims, limit=2)


def _extract_graph_signals(item, text):
    signals = _match_keyword_labels(text, GRAPH_SIGNAL_MAP, limit=8)
    validation_nodes = _dedupe_text_list(item.get("validation_nodes") if isinstance(item.get("validation_nodes"), list) else [], limit=4)
    fallback = []
    for value in validation_nodes:
        if any(token in value for token in ("资金", "成交", "利润", "订单", "库存", "汇率", "政策", "估值")):
            fallback.append(value)
    return _dedupe_text_list(signals + fallback, limit=8)


def _extract_graph_methods(text):
    return _match_keyword_labels(text, GRAPH_METHOD_MAP, limit=6)


def _extract_graph_invalid_conditions(item):
    candidates = []
    for value in (item.get("validation_nodes") if isinstance(item.get("validation_nodes"), list) else []):
        text = _normalize_graph_text(value)
        if any(token in text for token in ("风险", "失效", "回落", "不及预期", "止跌", "收缩")):
            candidates.append(text)
    return _dedupe_text_list(candidates, limit=4)


def build_knowledge_graph_artifact(item, tenant_slug="", tenant_name=""):
    if not isinstance(item, dict):
        return {
            "question_set": [],
            "keywords": [],
            "values": [],
            "topics": [],
            "entities": [],
            "methods": [],
            "claims": [],
            "signals": [],
            "evidence_points": [],
            "invalid_conditions": [],
        }
    text = _collect_graph_source_text(item)
    entities = _dedupe_text_list(_extract_bracket_entities(text) + _match_alias_entities(text), limit=12)
    topics = _extract_topics(item, text)
    methods = _extract_graph_methods(text)
    claims = _extract_graph_claims(item)
    signals = _extract_graph_signals(item, text)
    evidence_points = _dedupe_text_list(item.get("key_points") if isinstance(item.get("key_points"), list) else [], limit=6)
    invalid_conditions = _extract_graph_invalid_conditions(item)
    question_set = _extract_graph_questions(item, topics, entities)
    keywords = _dedupe_text_list(topics + entities + methods + signals, limit=18)
    values = _dedupe_text_list(claims + evidence_points + invalid_conditions, limit=10)
    return {
        "source_entry_id": str(item.get("id") or "").strip(),
        "source_title": _normalize_graph_text(item.get("title") or "知识条目"),
        "source_type": _normalize_graph_text(item.get("type") or "manual"),
        "tenant_slug": _normalize_graph_text(tenant_slug),
        "tenant_name": _normalize_graph_text(tenant_name),
        "question_set": question_set,
        "keywords": keywords,
        "values": values,
        "topics": topics,
        "entities": entities,
        "methods": methods,
        "claims": claims,
        "signals": signals,
        "evidence_points": evidence_points,
        "invalid_conditions": invalid_conditions,
    }


def _normalize_artifact(item, tenant_slug="", tenant_name=""):
    if isinstance(item.get("graph_profile"), dict):
        graph_profile = copy.deepcopy(item.get("graph_profile"))
    else:
        graph_profile = build_knowledge_graph_artifact(item, tenant_slug=tenant_slug, tenant_name=tenant_name)
    graph_profile["tenant_slug"] = _normalize_graph_text(graph_profile.get("tenant_slug") or tenant_slug)
    graph_profile["tenant_name"] = _normalize_graph_text(graph_profile.get("tenant_name") or tenant_name)
    graph_profile["source_entry_id"] = _normalize_graph_text(graph_profile.get("source_entry_id") or item.get("id"))
    graph_profile["source_title"] = _normalize_graph_text(graph_profile.get("source_title") or item.get("title") or "知识条目")
    return graph_profile


def build_knowledge_graph_payload(items, mode="tenant", tenant=None, platform_name="平台"):
    normalized_items = [copy.deepcopy(item) for item in (items or []) if isinstance(item, dict)]
    tenant_payload = tenant if isinstance(tenant, dict) else {}
    tenant_slug = _normalize_graph_text(tenant_payload.get("slug") or "")
    tenant_name = _normalize_graph_text(tenant_payload.get("name") or tenant_slug or "当前租户")
    platform_label = _normalize_graph_text(platform_name or "平台") or "平台"
    is_platform_mode = str(mode or "tenant").strip().lower() == "platform"
    nodes = []
    edges = []
    node_map = {}
    edge_set = set()

    def push_node(node):
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            return
        if node_id not in node_map:
            next_node = copy.deepcopy(node)
            next_node.setdefault("source_entries", [])
            next_node.setdefault("keywords", [])
            next_node.setdefault("qkv", {})
            next_node.setdefault("weight", 0)
            next_node.setdefault("source_count", 0)
            node_map[node_id] = next_node
            nodes.append(next_node)
        target = node_map[node_id]
        target["weight"] = max(int(target.get("weight") or 0), int(node.get("weight") or 0))
        source_entries = node.get("source_entries") if isinstance(node.get("source_entries"), list) else []
        if source_entries:
            existing = {
                str(item.get("id") or "").strip()
                for item in (target.get("source_entries") if isinstance(target.get("source_entries"), list) else [])
                if isinstance(item, dict)
            }
            merged_entries = list(target.get("source_entries") or [])
            for entry in source_entries:
                entry_id = str(entry.get("id") or "").strip()
                if entry_id and entry_id not in existing:
                    merged_entries.append(copy.deepcopy(entry))
                    existing.add(entry_id)
            target["source_entries"] = merged_entries[:6]
            target["source_count"] = len(existing)
        keywords = node.get("keywords") if isinstance(node.get("keywords"), list) else []
        if keywords:
            target["keywords"] = _dedupe_text_list(list(target.get("keywords") or []) + list(keywords), limit=16)
        if not target.get("summary") and node.get("summary"):
            target["summary"] = node.get("summary")
        if not target.get("tenant_slug") and node.get("tenant_slug"):
            target["tenant_slug"] = node.get("tenant_slug")
        if not target.get("tenant_name") and node.get("tenant_name"):
            target["tenant_name"] = node.get("tenant_name")
        if not target.get("qkv") and node.get("qkv"):
            target["qkv"] = copy.deepcopy(node.get("qkv"))

    def push_edge(from_id, to_id, edge_type="related_to", weight=1):
        edge_id = f"{from_id}__{to_id}__{edge_type}"
        if not from_id or not to_id or edge_id in edge_set:
            return
        edge_set.add(edge_id)
        edges.append({
            "id": edge_id,
            "from": from_id,
            "to": to_id,
            "type": edge_type,
            "weight": int(weight or 1),
        })

    root_id = is_platform_mode and "graph:platform-root" or f"graph:tenant-root:{tenant_slug or 'default'}"
    push_node({
        "id": root_id,
        "label": is_platform_mode and f"{platform_label} 知识图谱" or f"{tenant_name} 知识图谱",
        "kind": "root",
        "level": 1,
        "summary": is_platform_mode and "从平台总图查看各租户知识主题，再逐层展开到观点与验证信号。" or "从当前租户的知识对象查看主题、实体、方法、观点与验证信号。",
        "weight": 10,
    })

    def build_source_entry(item, artifact):
        return {
            "id": artifact.get("source_entry_id") or item.get("id") or "",
            "title": artifact.get("source_title") or item.get("title") or "知识条目",
            "summary": _normalize_graph_text(item.get("summary") or ""),
            "time": _normalize_graph_text(item.get("time") or item.get("queued_at") or item.get("synced_at") or ""),
            "tenant_slug": _normalize_graph_text(artifact.get("tenant_slug") or tenant_slug),
            "tenant_name": _normalize_graph_text(artifact.get("tenant_name") or tenant_name),
        }

    stats = {
        "artifact_count": len(normalized_items),
        "tenant_count": 0,
        "topic_count": 0,
        "entity_count": 0,
        "method_count": 0,
        "claim_count": 0,
        "signal_count": 0,
    }

    tenant_seen = set()
    for index, item in enumerate(normalized_items):
        item_tenant_slug = _normalize_graph_text(item.get("tenant_slug") or tenant_slug)
        item_tenant_name = _normalize_graph_text(item.get("tenant_name") or tenant_name or item_tenant_slug or "当前租户")
        artifact = _normalize_artifact(item, tenant_slug=item_tenant_slug, tenant_name=item_tenant_name)
        source_entry = build_source_entry(item, artifact)
        source_keywords = artifact.get("keywords") if isinstance(artifact.get("keywords"), list) else []
        source_qkv = {
            "questions": artifact.get("question_set") if isinstance(artifact.get("question_set"), list) else [],
            "keywords": source_keywords,
            "values": artifact.get("values") if isinstance(artifact.get("values"), list) else [],
        }
        tenant_root_id = root_id
        if is_platform_mode:
            tenant_root_id = f"graph:tenant:{slugify_code(item_tenant_slug or item_tenant_name, 'tenant')}"
            push_node({
                "id": tenant_root_id,
                "label": item_tenant_name,
                "kind": "tenant",
                "level": 2,
                "summary": f"{item_tenant_name} 当前知识主题与观点关系。",
                "tenant_slug": item_tenant_slug,
                "tenant_name": item_tenant_name,
                "weight": 6,
            })
            push_edge(root_id, tenant_root_id, edge_type="belongs_to")
            tenant_seen.add(item_tenant_slug or item_tenant_name)
        level_two_base = 3 if is_platform_mode else 2
        claim_level = 4 if is_platform_mode else 3
        signal_level = 5 if is_platform_mode else 4

        connector_nodes = []
        for kind, labels in (
            ("topic", artifact.get("topics") if isinstance(artifact.get("topics"), list) else []),
            ("entity", artifact.get("entities") if isinstance(artifact.get("entities"), list) else []),
            ("method", artifact.get("methods") if isinstance(artifact.get("methods"), list) else []),
        ):
            for label in labels[:6]:
                normalized_label = _normalize_graph_text(label)
                if not normalized_label:
                    continue
                node_id = f"graph:{kind}:{slugify_code((item_tenant_slug + '-' if is_platform_mode else '') + normalized_label, kind)}"
                push_node({
                    "id": node_id,
                    "label": normalized_label,
                    "kind": kind,
                    "level": level_two_base,
                    "tenant_slug": item_tenant_slug,
                    "tenant_name": item_tenant_name,
                    "summary": f"{normalized_label} 相关的知识主题与结论聚合节点。",
                    "source_entries": [source_entry],
                    "keywords": source_keywords,
                    "qkv": source_qkv,
                    "weight": len(source_keywords) + 1,
                })
                push_edge(tenant_root_id, node_id, edge_type="belongs_to")
                connector_nodes.append(node_id)
                if kind == "topic":
                    stats["topic_count"] += 1
                elif kind == "entity":
                    stats["entity_count"] += 1
                else:
                    stats["method_count"] += 1

        if not connector_nodes:
            fallback_topic = artifact.get("topics")[0] if isinstance(artifact.get("topics"), list) and artifact.get("topics") else (artifact.get("entities")[0] if isinstance(artifact.get("entities"), list) and artifact.get("entities") else "未分类知识主题")
            fallback_id = f"graph:topic:{slugify_code((item_tenant_slug + '-' if is_platform_mode else '') + fallback_topic, 'topic')}"
            push_node({
                "id": fallback_id,
                "label": fallback_topic,
                "kind": "topic",
                "level": level_two_base,
                "tenant_slug": item_tenant_slug,
                "tenant_name": item_tenant_name,
                "summary": f"{fallback_topic} 相关的知识主题与结论聚合节点。",
                "source_entries": [source_entry],
                "keywords": source_keywords,
                "qkv": source_qkv,
                "weight": len(source_keywords) + 1,
            })
            push_edge(tenant_root_id, fallback_id, edge_type="belongs_to")
            connector_nodes.append(fallback_id)
            stats["topic_count"] += 1

        claim_candidates = artifact.get("claims") if isinstance(artifact.get("claims"), list) else []
        claim_text = claim_candidates[0] if claim_candidates else _normalize_graph_text(item.get("summary") or item.get("title") or f"知识结论 {index + 1}")
        claim_id = f"graph:claim:{slugify_code(item_tenant_slug + '-' + (artifact.get('source_entry_id') or str(index + 1)), 'claim')}"
        push_node({
            "id": claim_id,
            "label": _graph_trim_text(claim_text, limit=26),
            "full_label": claim_text,
            "kind": "claim",
            "level": claim_level,
            "tenant_slug": item_tenant_slug,
            "tenant_name": item_tenant_name,
            "summary": claim_text,
            "source_entries": [source_entry],
            "keywords": source_keywords,
            "qkv": source_qkv,
            "weight": max(2, len(source_keywords)),
        })
        stats["claim_count"] += 1
        for connector_id in connector_nodes[:8]:
            push_edge(connector_id, claim_id, edge_type="supports")

        for signal in (artifact.get("signals") if isinstance(artifact.get("signals"), list) else [])[:6]:
            signal_label = _normalize_graph_text(signal)
            if not signal_label:
                continue
            signal_id = f"graph:signal:{slugify_code((item_tenant_slug + '-' if is_platform_mode else '') + signal_label, 'signal')}"
            push_node({
                "id": signal_id,
                "label": _graph_trim_text(signal_label, limit=24),
                "full_label": signal_label,
                "kind": "signal",
                "level": signal_level,
                "tenant_slug": item_tenant_slug,
                "tenant_name": item_tenant_name,
                "summary": signal_label,
                "source_entries": [source_entry],
                "keywords": source_keywords,
                "qkv": source_qkv,
                "weight": 1 + len(source_keywords) // 4,
            })
            push_edge(claim_id, signal_id, edge_type="explains")
            stats["signal_count"] += 1

    if is_platform_mode:
        stats["tenant_count"] = len(tenant_seen)
    else:
        stats["tenant_count"] = 1 if tenant_slug or tenant_name else 0

    stats["topic_count"] = len([node for node in nodes if node.get("kind") == "topic"])
    stats["entity_count"] = len([node for node in nodes if node.get("kind") == "entity"])
    stats["method_count"] = len([node for node in nodes if node.get("kind") == "method"])
    stats["claim_count"] = len([node for node in nodes if node.get("kind") == "claim"])
    stats["signal_count"] = len([node for node in nodes if node.get("kind") == "signal"])

    return {
        "mode": "platform" if is_platform_mode else "tenant",
        "root_id": root_id,
        "default_depth": 3,
        "max_depth": 5 if is_platform_mode else 4,
        "nodes": nodes,
        "edges": edges,
        "stats": stats,
        "filters": {
            "node_types": ["all", "topic", "entity", "method", "claim", "signal"],
        },
    }


def _knowledge_asset_maturity_score(item, artifact):
    score = 0
    if str(item.get("summary") or "").strip():
        score += 14
    if str(item.get("body") or item.get("raw_input") or "").strip():
        score += 10
    if str(((item.get("vector_record") or {}) if isinstance(item.get("vector_record"), dict) else {}).get("vector_namespace") or "").strip():
        score += 18
    if artifact.get("topics"):
        score += 10
    if artifact.get("entities"):
        score += 10
    if artifact.get("methods"):
        score += 8
    if artifact.get("claims"):
        score += 8
    if artifact.get("signals"):
        score += 8
    if artifact.get("evidence_points"):
        score += 8
    if artifact.get("question_set"):
        score += 6
    return min(100, int(score))


def _knowledge_asset_maturity_meta(score):
    if score >= 85:
        return {"label": "成熟", "tone": "ready"}
    if score >= 65:
        return {"label": "成型", "tone": "growing"}
    if score >= 40:
        return {"label": "生长", "tone": "building"}
    return {"label": "种子", "tone": "seed"}


def _build_relationship_bucket():
    return {"count": 0, "entry_ids": [], "entry_titles": [], "keywords": []}


def _append_relationship_bucket(target, label, item, artifact):
    normalized_label = _normalize_graph_text(label)
    if not normalized_label:
        return
    bucket = target.setdefault(normalized_label, _build_relationship_bucket())
    bucket["count"] += 1
    entry_id = str(item.get("id") or artifact.get("source_entry_id") or "").strip()
    entry_title = _normalize_graph_text(item.get("title") or artifact.get("source_title") or "知识条目")
    if entry_id and entry_id not in bucket["entry_ids"]:
        bucket["entry_ids"].append(entry_id)
    if entry_title and entry_title not in bucket["entry_titles"]:
        bucket["entry_titles"].append(entry_title)
    bucket["keywords"] = _dedupe_text_list(list(bucket.get("keywords") or []) + list(artifact.get("keywords") or []), limit=10)


def build_knowledge_asset_payload(items, mode="tenant", tenant=None, platform_name="平台"):
    normalized_items = [copy.deepcopy(item) for item in (items or []) if isinstance(item, dict)]
    tenant_payload = tenant if isinstance(tenant, dict) else {}
    tenant_slug = _normalize_graph_text(tenant_payload.get("slug") or "")
    tenant_name = _normalize_graph_text(tenant_payload.get("name") or tenant_slug or "当前租户")
    is_platform_mode = str(mode or "tenant").strip().lower() == "platform"
    topic_map = {}
    entity_map = {}
    method_map = {}
    signal_map = {}
    source_breakdown = {}
    tenant_breakdown = {}
    entries = []
    ready_count = 0
    total_score = 0
    relation_total = 0
    keyword_total = 0
    for item in normalized_items:
        item_tenant_slug = _normalize_graph_text(item.get("tenant_slug") or tenant_slug)
        item_tenant_name = _normalize_graph_text(item.get("tenant_name") or tenant_name or item_tenant_slug or "当前租户")
        artifact = _normalize_artifact(item, tenant_slug=item_tenant_slug, tenant_name=item_tenant_name)
        score = _knowledge_asset_maturity_score(item, artifact)
        maturity = _knowledge_asset_maturity_meta(score)
        ready_count += 1 if score >= 65 else 0
        total_score += score
        relation_count = sum(
            len(artifact.get(key) or [])
            for key in ("topics", "entities", "methods", "signals", "claims")
        )
        relation_total += relation_count
        keyword_count = len(artifact.get("keywords") or [])
        keyword_total += keyword_count
        source_label = _normalize_graph_text(item.get("source") or item.get("type") or "知识录入")
        source_breakdown[source_label] = int(source_breakdown.get(source_label) or 0) + 1
        if is_platform_mode:
            tenant_label = item_tenant_name or item_tenant_slug or "未命名租户"
            tenant_breakdown[tenant_label] = int(tenant_breakdown.get(tenant_label) or 0) + 1
        for label in artifact.get("topics") or []:
            _append_relationship_bucket(topic_map, label, item, artifact)
        for label in artifact.get("entities") or []:
            _append_relationship_bucket(entity_map, label, item, artifact)
        for label in artifact.get("methods") or []:
            _append_relationship_bucket(method_map, label, item, artifact)
        for label in artifact.get("signals") or []:
            _append_relationship_bucket(signal_map, label, item, artifact)
        entries.append({
            "id": str(item.get("id") or artifact.get("source_entry_id") or "").strip(),
            "title": _normalize_graph_text(item.get("title") or artifact.get("source_title") or "知识条目"),
            "type": _normalize_graph_text(item.get("type") or "manual"),
            "source": source_label,
            "source_detail": _normalize_graph_text(item.get("source_detail") or ""),
            "summary": _normalize_graph_text(item.get("summary") or ""),
            "time": _normalize_graph_text(item.get("time") or item.get("queued_at") or item.get("synced_at") or ""),
            "tenant_slug": item_tenant_slug,
            "tenant_name": item_tenant_name,
            "tags": _dedupe_text_list(item.get("tags") if isinstance(item.get("tags"), list) else [], limit=8),
            "maturity_score": score,
            "maturity_label": maturity["label"],
            "maturity_tone": maturity["tone"],
            "relation_count": relation_count,
            "keyword_count": keyword_count,
            "qkv": {
                "questions": _dedupe_text_list(artifact.get("question_set") if isinstance(artifact.get("question_set"), list) else [], limit=3),
                "keywords": _dedupe_text_list(artifact.get("keywords") if isinstance(artifact.get("keywords"), list) else [], limit=10),
                "values": _dedupe_text_list(artifact.get("values") if isinstance(artifact.get("values"), list) else [], limit=4),
            },
            "relations": {
                "topics": _dedupe_text_list(artifact.get("topics") if isinstance(artifact.get("topics"), list) else [], limit=6),
                "entities": _dedupe_text_list(artifact.get("entities") if isinstance(artifact.get("entities"), list) else [], limit=6),
                "methods": _dedupe_text_list(artifact.get("methods") if isinstance(artifact.get("methods"), list) else [], limit=4),
                "claims": _dedupe_text_list(artifact.get("claims") if isinstance(artifact.get("claims"), list) else [], limit=2),
                "signals": _dedupe_text_list(artifact.get("signals") if isinstance(artifact.get("signals"), list) else [], limit=5),
                "evidence_points": _dedupe_text_list(artifact.get("evidence_points") if isinstance(artifact.get("evidence_points"), list) else [], limit=4),
            },
            "vector_record": copy.deepcopy(item.get("vector_record")) if isinstance(item.get("vector_record"), dict) else {},
        })
    entries.sort(
        key=lambda current: (
            -int(current.get("maturity_score") or 0),
            -int(current.get("relation_count") or 0),
            str(current.get("time") or ""),
        )
    )

    def _sorted_relationships(mapping, limit=10):
        rows = []
        for label, bucket in mapping.items():
            rows.append({
                "label": label,
                "count": int(bucket.get("count") or 0),
                "entry_ids": list(bucket.get("entry_ids") or [])[:8],
                "entry_titles": list(bucket.get("entry_titles") or [])[:4],
                "keywords": _dedupe_text_list(bucket.get("keywords") if isinstance(bucket.get("keywords"), list) else [], limit=8),
            })
        rows.sort(key=lambda item: (-int(item.get("count") or 0), item.get("label") or ""))
        return rows[:limit]

    source_rows = [{"label": label, "count": count} for label, count in source_breakdown.items()]
    source_rows.sort(key=lambda item: (-int(item.get("count") or 0), item.get("label") or ""))
    tenant_rows = [{"label": label, "count": count} for label, count in tenant_breakdown.items()]
    tenant_rows.sort(key=lambda item: (-int(item.get("count") or 0), item.get("label") or ""))

    return {
        "mode": "platform" if is_platform_mode else "tenant",
        "tenant_slug": tenant_slug,
        "tenant_name": tenant_name,
        "platform_name": _normalize_graph_text(platform_name or "平台") or "平台",
        "summary": {
            "entry_count": len(entries),
            "ready_count": ready_count,
            "avg_maturity_score": round((total_score / len(entries)), 1) if entries else 0,
            "avg_relation_count": round((relation_total / len(entries)), 1) if entries else 0,
            "avg_keyword_count": round((keyword_total / len(entries)), 1) if entries else 0,
            "topic_count": len(topic_map),
            "entity_count": len(entity_map),
            "method_count": len(method_map),
            "signal_count": len(signal_map),
            "source_type_count": len(source_rows),
            "tenant_count": len(tenant_rows) if is_platform_mode else (1 if entries else 0),
        },
        "relationship_groups": {
            "topics": _sorted_relationships(topic_map, limit=8),
            "entities": _sorted_relationships(entity_map, limit=8),
            "methods": _sorted_relationships(method_map, limit=6),
            "signals": _sorted_relationships(signal_map, limit=8),
        },
        "source_breakdown": source_rows,
        "tenant_breakdown": tenant_rows,
        "entries": entries[:80],
    }
