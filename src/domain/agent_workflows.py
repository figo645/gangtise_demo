import copy
import time


DECLARED_AGENT_WORKFLOW_CATALOG = {
    "hermes_agent": {
        "id": "hermes_agent",
        "title": "小金智能体",
        "summary": "围绕问题拆解、工具调度、答案合成和结果渲染的统一 Agent 主链路。",
        "category": "对话智能体",
        "feature_key": "hermes",
        "execution_mode": "declared_agent_workflow",
        "tags": ["H5", "LLM 路由", "自选股", "Dashboard", "会话记忆"],
        "nodes": [
            {"id": "question_input", "label": "问题输入", "processor": "input", "kind": "source", "x": 36, "y": 88, "description": "接收用户问题、附件、知识范围和上下文。"},
            {"id": "session_load", "label": "会话装载", "processor": "session_load", "kind": "context", "x": 228, "y": 88, "description": "读取当前用户在本次小金智能体会话下的历史轮次与会话摘要。"},
            {"id": "memory_read", "label": "记忆读取", "processor": "memory_read", "kind": "context", "x": 430, "y": 88, "description": "读取用户事实记忆、工作记忆和已有画像。"},
            {"id": "scope_guard", "label": "安全边界", "processor": "scope_guard", "kind": "guardrail", "x": 646, "y": 88, "description": "记录安全边界提示，最终意图由 LLM 统一判断。"},
            {"id": "intent_router", "label": "意图路由", "processor": "router", "kind": "llm", "x": 876, "y": 88, "description": "必须调用 LLM 识别意图和工具计划，模型失败即终止本轮。"},
            {"id": "tool_dispatch", "label": "工具调度", "processor": "tool_dispatch", "kind": "tooling", "x": 1110, "y": 88, "description": "按 LLM 路由计划调用个股、指标、Dashboard 或附件工具。"},
            {"id": "answer_synthesis", "label": "答案合成", "processor": "llm_synthesis", "kind": "llm", "x": 1348, "y": 88, "description": "根据工具结果或范围守卫结果做最终回答整合。"},
            {"id": "memory_extract", "label": "记忆抽取", "processor": "memory_extract", "kind": "planner", "x": 1578, "y": 88, "description": "从本轮问答中提炼标签、偏好、关注主题和可沉淀记忆。"},
            {"id": "memory_write", "label": "记忆写入", "processor": "memory_write", "kind": "storage", "x": 1806, "y": 88, "description": "写入问答原文、会话记忆和用户记忆。"},
            {"id": "user_profile_update", "label": "画像更新", "processor": "user_profile_update", "kind": "storage", "x": 2036, "y": 88, "description": "把本轮标签与行为结果汇总成用户定位画像。"},
            {"id": "artifact_render", "label": "结果渲染", "processor": "artifact", "kind": "output", "x": 2268, "y": 88, "description": "生成结构化卡片或纯文本回答，并附带思考流与工具轨迹。"},
        ],
        "edges": [
            {"id": "edge_hermes_1", "from": "question_input", "to": "session_load"},
            {"id": "edge_hermes_2", "from": "session_load", "to": "memory_read"},
            {"id": "edge_hermes_3", "from": "memory_read", "to": "scope_guard"},
            {"id": "edge_hermes_4", "from": "scope_guard", "to": "intent_router"},
            {"id": "edge_hermes_5", "from": "intent_router", "to": "tool_dispatch"},
            {"id": "edge_hermes_6", "from": "tool_dispatch", "to": "answer_synthesis"},
            {"id": "edge_hermes_7", "from": "answer_synthesis", "to": "memory_extract"},
            {"id": "edge_hermes_8", "from": "memory_extract", "to": "memory_write"},
            {"id": "edge_hermes_9", "from": "memory_write", "to": "user_profile_update"},
            {"id": "edge_hermes_10", "from": "user_profile_update", "to": "artifact_render"},
        ],
    },
    "review_generate_draft": {
        "id": "review_generate_draft",
        "title": "复盘 Draft 生成",
        "summary": "把手写、录音或文件整理后的原始材料转换为第一版可审核 Draft。",
        "category": "复盘智能体",
        "feature_key": "daily_review",
        "execution_mode": "declared_agent_workflow",
        "tags": ["大V", "Draft", "LLM"],
        "nodes": [
            {"id": "review_draft_input", "label": "素材输入", "processor": "input", "kind": "source", "x": 36, "y": 88, "description": "接收复盘原文、周期、来源模式、标签和关注股票。"},
            {"id": "review_draft_prepare", "label": "提示词整理", "processor": "prompt_prepare", "kind": "planner", "x": 330, "y": 88, "description": "整理发布口径、风险边界和原始材料。"},
            {"id": "review_draft_llm", "label": "草稿生成", "processor": "llm_generation", "kind": "llm", "x": 640, "y": 88, "description": "调用通用模型生成完整复盘 Draft。"},
            {"id": "review_draft_output", "label": "结果封装", "processor": "output", "kind": "output", "x": 946, "y": 88, "description": "输出 Draft 正文与模型信息。"},
        ],
        "edges": [
            {"id": "edge_review_draft_1", "from": "review_draft_input", "to": "review_draft_prepare"},
            {"id": "edge_review_draft_2", "from": "review_draft_prepare", "to": "review_draft_llm"},
            {"id": "edge_review_draft_3", "from": "review_draft_llm", "to": "review_draft_output"},
        ],
    },
    "review_polish_input": {
        "id": "review_polish_input",
        "title": "复盘输入润色",
        "summary": "用户选择智能优化后，先把原始输入整理成更适合审核和成稿的版本。",
        "category": "复盘智能体",
        "feature_key": "daily_review",
        "execution_mode": "declared_agent_workflow",
        "tags": ["大V", "输入优化", "LLM"],
        "nodes": [
            {"id": "review_polish_input", "label": "输入接收", "processor": "input", "kind": "source", "x": 36, "y": 88, "description": "接收待润色的手写、口述转写或上传内容。"},
            {"id": "review_polish_prepare", "label": "润色规则装配", "processor": "prompt_prepare", "kind": "planner", "x": 336, "y": 88, "description": "组合周期、来源、说话人和系统规则。"},
            {"id": "review_polish_llm", "label": "内容润色", "processor": "llm_generation", "kind": "llm", "x": 648, "y": 88, "description": "调用模型进行输入优化。"},
            {"id": "review_polish_output", "label": "返回审核稿", "processor": "output", "kind": "output", "x": 952, "y": 88, "description": "返回润色后的内容，供后续 Draft 审核继续使用。"},
        ],
        "edges": [
            {"id": "edge_review_polish_1", "from": "review_polish_input", "to": "review_polish_prepare"},
            {"id": "edge_review_polish_2", "from": "review_polish_prepare", "to": "review_polish_llm"},
            {"id": "edge_review_polish_3", "from": "review_polish_llm", "to": "review_polish_output"},
        ],
    },
    "review_compose_draft": {
        "id": "review_compose_draft",
        "title": "复盘完整成稿",
        "summary": "把正文、智能指标卡片和知识材料整合成最终可预览的完整复盘。",
        "category": "复盘智能体",
        "feature_key": "daily_review",
        "execution_mode": "declared_agent_workflow",
        "tags": ["大V", "复盘成稿", "知识材料", "LLM"],
        "nodes": [
            {"id": "review_compose_input", "label": "复盘上下文输入", "processor": "input", "kind": "source", "x": 36, "y": 88, "description": "接收正文、Dashboard 卡片、知识材料和标签规则。"},
            {"id": "review_compose_context", "label": "上下文聚合", "processor": "context_assembly", "kind": "planner", "x": 342, "y": 88, "description": "把复盘正文、卡片和知识内容整合成统一上下文。"},
            {"id": "review_compose_llm", "label": "完整成稿生成", "processor": "llm_generation", "kind": "llm", "x": 652, "y": 88, "description": "调用模型输出完整复盘成稿。"},
            {"id": "review_compose_output", "label": "成稿封装", "processor": "output", "kind": "output", "x": 960, "y": 88, "description": "输出正文和模型信息，进入最终预览。"},
        ],
        "edges": [
            {"id": "edge_review_compose_1", "from": "review_compose_input", "to": "review_compose_context"},
            {"id": "edge_review_compose_2", "from": "review_compose_context", "to": "review_compose_llm"},
            {"id": "edge_review_compose_3", "from": "review_compose_llm", "to": "review_compose_output"},
        ],
    },
    "review_watchlist_analysis": {
        "id": "review_watchlist_analysis",
        "title": "复盘多股综合分析",
        "summary": "围绕本次选中的自选股，装载本地上下文后调用 Gangtise Agent SSE 输出个股与组合综合分析。",
        "category": "复盘智能体",
        "feature_key": "daily_review",
        "execution_mode": "declared_agent_workflow",
        "tags": ["大V", "自选股", "组合分析", "Gangtise Agent SSE"],
        "nodes": [
            {"id": "review_watchlist_input", "label": "自选股输入", "processor": "input", "kind": "source", "x": 36, "y": 88, "description": "接收本次复盘已选中的股票列表、用户输入正文和复盘周期。"},
            {"id": "review_watchlist_context", "label": "股票上下文装载", "processor": "context_load", "kind": "context", "x": 324, "y": 88, "description": "加载个股基础信息、行业归属、信号摘要和基本面判断。"},
            {"id": "review_watchlist_sector_merge", "label": "板块上下文归并", "processor": "sector_merge", "kind": "planner", "x": 632, "y": 88, "description": "按行业或板块归并自选股，为 Gangtise 多股分析准备上下文。"},
            {"id": "review_watchlist_llm", "label": "Gangtise 多股分析", "processor": "gangtise_agent_sse", "kind": "tooling", "x": 946, "y": 88, "description": "调用 /application/open-ai/ai/chat/sse，以 deep_research 模式生成个股与组合综合分析。"},
            {"id": "review_watchlist_output", "label": "分析结果封装", "processor": "output", "kind": "output", "x": 1260, "y": 88, "description": "保留 Gangtise 完整分析正文和调用元数据，供审核、编辑和发布复用。"},
        ],
        "edges": [
            {"id": "edge_review_watchlist_1", "from": "review_watchlist_input", "to": "review_watchlist_context"},
            {"id": "edge_review_watchlist_2", "from": "review_watchlist_context", "to": "review_watchlist_sector_merge"},
            {"id": "edge_review_watchlist_3", "from": "review_watchlist_sector_merge", "to": "review_watchlist_llm"},
            {"id": "edge_review_watchlist_4", "from": "review_watchlist_llm", "to": "review_watchlist_output"},
        ],
    },
    "review_voice_enhancement": {
        "id": "review_voice_enhancement",
        "title": "复盘语音增强",
        "summary": "把基础转写结果整理成更适合审核、编辑和入库的文本。",
        "category": "复盘智能体",
        "feature_key": "daily_review",
        "execution_mode": "declared_agent_workflow",
        "tags": ["大V", "语音转写", "LLM"],
        "nodes": [
            {"id": "review_voice_input", "label": "转写输入", "processor": "input", "kind": "source", "x": 36, "y": 88, "description": "接收原始转写内容、入口和说话人。"},
            {"id": "review_voice_prepare", "label": "整理规则装配", "processor": "prompt_prepare", "kind": "planner", "x": 336, "y": 88, "description": "组合场景说明和增强约束。"},
            {"id": "review_voice_llm", "label": "轻量增强", "processor": "llm_generation", "kind": "llm", "x": 648, "y": 88, "description": "调用模型做去噪、修句和轻量结构整理。"},
            {"id": "review_voice_output", "label": "返回整理稿", "processor": "output", "kind": "output", "x": 952, "y": 88, "description": "输出可继续审核和编辑的整理稿。"},
        ],
        "edges": [
            {"id": "edge_review_voice_1", "from": "review_voice_input", "to": "review_voice_prepare"},
            {"id": "edge_review_voice_2", "from": "review_voice_prepare", "to": "review_voice_llm"},
            {"id": "edge_review_voice_3", "from": "review_voice_llm", "to": "review_voice_output"},
        ],
    },
    "smart_indicator_agent": {
        "id": "smart_indicator_agent",
        "title": "智能指标编译智能体",
        "summary": "把用户的指标引用和自然语言公式编译成临时 JS，并在确认后持久化。",
        "category": "指标智能体",
        "feature_key": "analytics_module",
        "execution_mode": "declared_agent_workflow",
        "tags": ["Dashboard", "Prompt to JS", "LLM"],
        "nodes": [
            {"id": "smart_indicator_input", "label": "指标引用输入", "processor": "input", "kind": "source", "x": 36, "y": 88, "description": "接收用户选择的底层指标、提示词和展示配置。"},
            {"id": "smart_indicator_resolve", "label": "引用解析", "processor": "reference_resolve", "kind": "planner", "x": 336, "y": 88, "description": "规范化指标引用与标签，校验输入完整性。"},
            {"id": "smart_indicator_compile", "label": "公式编译", "processor": "formula_compile", "kind": "llm", "x": 636, "y": 88, "description": "调用模型把提示词编译成受限 JavaScript return 表达式。"},
            {"id": "smart_indicator_preview", "label": "预览求值", "processor": "preview_eval", "kind": "runtime", "x": 942, "y": 88, "description": "使用最新指标值执行临时 JS，生成用户确认前预览。"},
            {"id": "smart_indicator_publish", "label": "确认持久化", "processor": "persist", "kind": "output", "x": 1248, "y": 88, "description": "用户确认后保存公式 JS、指标定义和 Dashboard 卡片引用。"},
        ],
        "edges": [
            {"id": "edge_indicator_1", "from": "smart_indicator_input", "to": "smart_indicator_resolve"},
            {"id": "edge_indicator_2", "from": "smart_indicator_resolve", "to": "smart_indicator_compile"},
            {"id": "edge_indicator_3", "from": "smart_indicator_compile", "to": "smart_indicator_preview"},
            {"id": "edge_indicator_4", "from": "smart_indicator_preview", "to": "smart_indicator_publish"},
        ],
    },
    "knowledge_query_agent": {
        "id": "knowledge_query_agent",
        "title": "知识问答智能体",
        "summary": "围绕知识库检索、相关性过滤与答案生成的知识问答链路。",
        "category": "知识智能体",
        "feature_key": "knowledge_module",
        "execution_mode": "declared_agent_workflow",
        "tags": ["知识库", "检索", "LLM"],
        "nodes": [
            {"id": "knowledge_query_input", "label": "问题输入", "processor": "input", "kind": "source", "x": 36, "y": 88, "description": "接收知识问题、租户和检索范围。"},
            {"id": "knowledge_query_retrieval", "label": "知识召回", "processor": "retrieval", "kind": "tooling", "x": 320, "y": 88, "description": "基于向量检索召回知识条目。"},
            {"id": "knowledge_query_filter", "label": "相关性过滤", "processor": "llm_filter", "kind": "llm", "x": 614, "y": 88, "description": "调用 LLM 过滤低相关内容，模型失败即终止本轮。"},
            {"id": "knowledge_query_answer", "label": "答案整合", "processor": "llm_generation", "kind": "llm", "x": 910, "y": 88, "description": "必须由 LLM 基于过滤后的命中结果生成回答。"},
            {"id": "knowledge_query_output", "label": "结果封装", "processor": "output", "kind": "output", "x": 1206, "y": 88, "description": "输出知识回答、命中结果与工作流元信息。"},
        ],
        "edges": [
            {"id": "edge_knowledge_query_1", "from": "knowledge_query_input", "to": "knowledge_query_retrieval"},
            {"id": "edge_knowledge_query_2", "from": "knowledge_query_retrieval", "to": "knowledge_query_filter"},
            {"id": "edge_knowledge_query_3", "from": "knowledge_query_filter", "to": "knowledge_query_answer"},
            {"id": "edge_knowledge_query_4", "from": "knowledge_query_answer", "to": "knowledge_query_output"},
        ],
    },
    "evidence_chain_agent": {
        "id": "evidence_chain_agent",
        "title": "证据链问答智能体",
        "summary": "围绕证据召回、相关性过滤与证据链回答生成的统一链路。",
        "category": "知识智能体",
        "feature_key": "knowledge_module",
        "execution_mode": "declared_agent_workflow",
        "tags": ["证据链", "检索", "LLM"],
        "nodes": [
            {"id": "evidence_query_input", "label": "问题输入", "processor": "input", "kind": "source", "x": 36, "y": 88, "description": "接收证据链问题、来源范围和租户。"},
            {"id": "evidence_query_retrieval", "label": "证据召回", "processor": "retrieval", "kind": "tooling", "x": 320, "y": 88, "description": "基于证据来源召回候选条目。"},
            {"id": "evidence_query_filter", "label": "相关性过滤", "processor": "llm_filter", "kind": "llm", "x": 614, "y": 88, "description": "调用 LLM 过滤不直接相关的证据，模型失败即终止本轮。"},
            {"id": "evidence_query_answer", "label": "证据回答生成", "processor": "llm_generation", "kind": "llm", "x": 910, "y": 88, "description": "必须由 LLM 基于证据生成回答。"},
            {"id": "evidence_query_output", "label": "结果封装", "processor": "output", "kind": "output", "x": 1206, "y": 88, "description": "输出证据回答、召回结果与工作流元信息。"},
        ],
        "edges": [
            {"id": "edge_evidence_query_1", "from": "evidence_query_input", "to": "evidence_query_retrieval"},
            {"id": "edge_evidence_query_2", "from": "evidence_query_retrieval", "to": "evidence_query_filter"},
            {"id": "edge_evidence_query_3", "from": "evidence_query_filter", "to": "evidence_query_answer"},
            {"id": "edge_evidence_query_4", "from": "evidence_query_answer", "to": "evidence_query_output"},
        ],
    },
    "knowledge_processing_agent": {
        "id": "knowledge_processing_agent",
        "title": "知识加工智能体",
        "summary": "把原始材料整理成适合知识库沉淀的结构化研究内容。",
        "category": "知识智能体",
        "feature_key": "knowledge_module",
        "execution_mode": "declared_agent_workflow",
        "tags": ["知识入库", "内容加工", "LLM"],
        "nodes": [
            {"id": "knowledge_processing_input", "label": "原始材料输入", "processor": "input", "kind": "source", "x": 36, "y": 88, "description": "接收原始材料、标题和来源说明。"},
            {"id": "knowledge_processing_prepare", "label": "入库规则装配", "processor": "prompt_prepare", "kind": "planner", "x": 336, "y": 88, "description": "组织知识入库的结构化输出约束。"},
            {"id": "knowledge_processing_llm", "label": "知识加工", "processor": "llm_generation", "kind": "llm", "x": 648, "y": 88, "description": "调用模型生成结构化知识正文。"},
            {"id": "knowledge_processing_output", "label": "结果封装", "processor": "output", "kind": "output", "x": 952, "y": 88, "description": "输出加工摘要、关键要点和结构化正文。"},
        ],
        "edges": [
            {"id": "edge_knowledge_processing_1", "from": "knowledge_processing_input", "to": "knowledge_processing_prepare"},
            {"id": "edge_knowledge_processing_2", "from": "knowledge_processing_prepare", "to": "knowledge_processing_llm"},
            {"id": "edge_knowledge_processing_3", "from": "knowledge_processing_llm", "to": "knowledge_processing_output"},
        ],
    },
    "knowledge_graph_agent": {
        "id": "knowledge_graph_agent",
        "title": "知识图谱构建智能体",
        "summary": "把知识条目抽取为 QKV、主题、实体、方法、观点和验证信号，再聚合成可浏览的知识图谱。",
        "category": "知识智能体",
        "feature_key": "knowledge_module",
        "execution_mode": "declared_agent_workflow",
        "tags": ["知识图谱", "QKV", "实体归一", "聚合"],
        "nodes": [
            {"id": "knowledge_graph_input", "label": "知识条目输入", "processor": "input", "kind": "source", "x": 36, "y": 88, "description": "接收当前租户或平台范围内的知识条目。"},
            {"id": "knowledge_graph_qkv", "label": "QKV 抽取", "processor": "qkv_extract", "kind": "planner", "x": 308, "y": 88, "description": "从知识条目中提取问题、关键词和可复用知识值。"},
            {"id": "knowledge_graph_normalize", "label": "实体归一", "processor": "entity_normalize", "kind": "context", "x": 590, "y": 88, "description": "把别名、简写和重复指代归并到统一实体。"},
            {"id": "knowledge_graph_cluster", "label": "主题聚类", "processor": "topic_cluster", "kind": "planner", "x": 876, "y": 88, "description": "把主题、实体和方法聚合成图谱中心节点。"},
            {"id": "knowledge_graph_edge", "label": "关系推断", "processor": "edge_infer", "kind": "llm_or_rule", "x": 1164, "y": 88, "description": "生成 belongs_to / supports / explains 等关系。"},
            {"id": "knowledge_graph_render", "label": "图谱封装", "processor": "output", "kind": "output", "x": 1452, "y": 88, "description": "输出前端可渲染的知识图谱节点、边和详情数据。"},
        ],
        "edges": [
            {"id": "edge_knowledge_graph_1", "from": "knowledge_graph_input", "to": "knowledge_graph_qkv"},
            {"id": "edge_knowledge_graph_2", "from": "knowledge_graph_qkv", "to": "knowledge_graph_normalize"},
            {"id": "edge_knowledge_graph_3", "from": "knowledge_graph_normalize", "to": "knowledge_graph_cluster"},
            {"id": "edge_knowledge_graph_4", "from": "knowledge_graph_cluster", "to": "knowledge_graph_edge"},
            {"id": "edge_knowledge_graph_5", "from": "knowledge_graph_edge", "to": "knowledge_graph_render"},
        ],
    },
    "knowledge_asset_agent": {
        "id": "knowledge_asset_agent",
        "title": "知识资产台账智能体",
        "summary": "把知识条目整理成可审阅的知识资产台账，呈现词条、QKV、关系摘要和成熟度分层。",
        "category": "知识智能体",
        "feature_key": "knowledge_module",
        "execution_mode": "declared_agent_workflow",
        "tags": ["知识资产", "词条台账", "关系摘要", "QKV"],
        "nodes": [
            {"id": "knowledge_asset_input", "label": "知识条目输入", "processor": "input", "kind": "source", "x": 36, "y": 88, "description": "接收当前租户或平台范围内的知识条目集合。"},
            {"id": "knowledge_asset_profile", "label": "QKV 画像", "processor": "qkv_extract", "kind": "planner", "x": 320, "y": 88, "description": "抽取每条知识的提问、关键词、结论值和证据点。"},
            {"id": "knowledge_asset_relation", "label": "关系归并", "processor": "relation_merge", "kind": "context", "x": 616, "y": 88, "description": "把主题、实体、方法和验证信号归并成知识关系摘要。"},
            {"id": "knowledge_asset_grade", "label": "成熟度分层", "processor": "maturity_grade", "kind": "planner", "x": 914, "y": 88, "description": "根据向量化、结构完整度和关系丰富度计算成熟度。"},
            {"id": "knowledge_asset_render", "label": "资产台账封装", "processor": "output", "kind": "output", "x": 1212, "y": 88, "description": "输出知识资产总览、关系摘要和条目列表。"},
        ],
        "edges": [
            {"id": "edge_knowledge_asset_1", "from": "knowledge_asset_input", "to": "knowledge_asset_profile"},
            {"id": "edge_knowledge_asset_2", "from": "knowledge_asset_profile", "to": "knowledge_asset_relation"},
            {"id": "edge_knowledge_asset_3", "from": "knowledge_asset_relation", "to": "knowledge_asset_grade"},
            {"id": "edge_knowledge_asset_4", "from": "knowledge_asset_grade", "to": "knowledge_asset_render"},
        ],
    },
}


def normalize_declared_agent_workflow_definition(payload):
    source = payload if isinstance(payload, dict) else {}
    nodes = []
    seen_ids = set()
    for index, item in enumerate(source.get("nodes") if isinstance(source.get("nodes"), list) else []):
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("id") or f"node_{index + 1}").strip() or f"node_{index + 1}"
        if node_id in seen_ids:
            node_id = f"{node_id}_{index + 1}"
        seen_ids.add(node_id)
        nodes.append(
            {
                "id": node_id,
                "label": str(item.get("label") or node_id).strip() or node_id,
                "processor": str(item.get("processor") or "passthrough").strip() or "passthrough",
                "kind": str(item.get("kind") or "runtime").strip() or "runtime",
                "x": int(item.get("x") or 0),
                "y": int(item.get("y") or 0),
                "description": str(item.get("description") or "").strip(),
                "state_key": str(item.get("state_key") or "").strip(),
                "params": copy.deepcopy(item.get("params") or {}),
            }
        )
    node_ids = {item["id"] for item in nodes}
    edges = []
    seen_edges = set()
    for index, item in enumerate(source.get("edges") if isinstance(source.get("edges"), list) else []):
        if not isinstance(item, dict):
            continue
        from_id = str(item.get("from") or "").strip()
        to_id = str(item.get("to") or "").strip()
        if from_id not in node_ids or to_id not in node_ids or from_id == to_id:
            continue
        pair = (from_id, to_id)
        if pair in seen_edges:
            continue
        seen_edges.add(pair)
        edges.append(
            {
                "id": str(item.get("id") or f"edge_{index + 1}").strip() or f"edge_{index + 1}",
                "from": from_id,
                "to": to_id,
            }
        )
    return {
        "id": str(source.get("id") or "").strip(),
        "title": str(source.get("title") or "").strip(),
        "summary": str(source.get("summary") or "").strip(),
        "category": str(source.get("category") or "").strip(),
        "feature_key": str(source.get("feature_key") or "").strip(),
        "execution_mode": str(source.get("execution_mode") or "declared_agent_workflow").strip() or "declared_agent_workflow",
        "tags": [str(item).strip() for item in (source.get("tags") if isinstance(source.get("tags"), list) else []) if str(item).strip()],
        "nodes": nodes,
        "edges": edges,
    }


def _declared_workflow_topological_node_ids(definition):
    nodes = definition.get("nodes") if isinstance(definition.get("nodes"), list) else []
    edges = definition.get("edges") if isinstance(definition.get("edges"), list) else []
    incoming = {item["id"]: 0 for item in nodes}
    outgoing = {item["id"]: [] for item in nodes}
    for edge in edges:
        if edge["from"] in outgoing and edge["to"] in incoming:
            outgoing[edge["from"]].append(edge["to"])
            incoming[edge["to"]] += 1
    queue = [item["id"] for item in nodes if incoming[item["id"]] == 0]
    ordered = []
    while queue:
        current = queue.pop(0)
        ordered.append(current)
        for target in outgoing.get(current, []):
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    if len(ordered) != len(nodes):
        return [item["id"] for item in nodes]
    return ordered


def run_declared_agent_workflow(definition, executor_registry=None, runtime=None, initial_state=None):
    normalized = normalize_declared_agent_workflow_definition(definition)
    registry = executor_registry if isinstance(executor_registry, dict) else {}
    runtime_data = dict(runtime or {})
    state = dict(initial_state or {})
    node_lookup = {item["id"]: item for item in normalized["nodes"]}
    ordered_node_ids = _declared_workflow_topological_node_ids(normalized)
    node_results = {}
    steps = []
    started_at = time.time()
    for node_id in ordered_node_ids:
        node = node_lookup[node_id]
        executor = registry.get(node["id"]) or registry.get(node["processor"])
        node_started = time.time()
        if executor is None:
            result = {
                "status": "skipped",
                "detail": "当前节点未注册执行器，按设计态展示。",
                "output": None,
                "context_preview": {},
            }
        else:
            result = executor(
                state=state,
                runtime=runtime_data,
                node=node,
                upstream=node_results,
            ) or {}
        output = copy.deepcopy(result.get("output"))
        state_updates = copy.deepcopy(result.get("state_updates") or {})
        runtime_updates = copy.deepcopy(result.get("runtime_updates") or {})
        if isinstance(state_updates, dict):
            state.update(state_updates)
        if isinstance(runtime_updates, dict):
            runtime_data.update(runtime_updates)
        state_key = str(node.get("state_key") or result.get("state_key") or "").strip()
        if state_key:
            state[state_key] = output
        node_result = {
            "id": node_id,
            "label": node["label"],
            "processor": node["processor"],
            "kind": node["kind"],
            "status": str(result.get("status") or "ok").strip() or "ok",
            "detail": str(result.get("detail") or "").strip(),
            "output": output,
            "context_preview": copy.deepcopy(result.get("context_preview") or {}),
            "elapsed_ms": int((time.time() - node_started) * 1000),
        }
        node_results[node_id] = node_result
        steps.append(
            {
                "key": node_id,
                "title": node["label"],
                "processor": node["processor"],
                "status": node_result["status"],
                "detail": node_result["detail"],
                "elapsed_ms": node_result["elapsed_ms"],
            }
        )
    return {
        "workflow": normalized,
        "runtime": runtime_data,
        "state": state,
        "node_results": node_results,
        "steps": steps,
        "elapsed_ms": int((time.time() - started_at) * 1000),
    }


def build_declared_agent_workflow_meta(definition, execution=None, extras=None):
    normalized = normalize_declared_agent_workflow_definition(definition)
    payload = {
        "id": normalized["id"],
        "title": normalized["title"],
        "summary": normalized["summary"],
        "category": normalized["category"],
        "feature_key": normalized["feature_key"],
        "execution_mode": normalized["execution_mode"],
        "tags": copy.deepcopy(normalized.get("tags") or []),
        "graph": {
            "nodes": copy.deepcopy(normalized["nodes"]),
            "edges": copy.deepcopy(normalized["edges"]),
        },
    }
    if isinstance(execution, dict):
        payload["execution"] = {
            "elapsed_ms": int(execution.get("elapsed_ms") or 0),
            "steps": copy.deepcopy(execution.get("steps") or []),
            "node_results": copy.deepcopy(execution.get("node_results") or {}),
        }
    if isinstance(extras, dict):
        payload.update(copy.deepcopy(extras))
    return payload


def build_default_hermes_agent_workflow_definition():
    return copy.deepcopy(DECLARED_AGENT_WORKFLOW_CATALOG["hermes_agent"])


def build_default_review_draft_workflow_definition():
    return copy.deepcopy(DECLARED_AGENT_WORKFLOW_CATALOG["review_generate_draft"])


def build_default_review_polish_workflow_definition():
    return copy.deepcopy(DECLARED_AGENT_WORKFLOW_CATALOG["review_polish_input"])


def build_default_review_compose_workflow_definition():
    return copy.deepcopy(DECLARED_AGENT_WORKFLOW_CATALOG["review_compose_draft"])


def build_default_review_watchlist_analysis_workflow_definition():
    return copy.deepcopy(DECLARED_AGENT_WORKFLOW_CATALOG["review_watchlist_analysis"])


def build_default_review_voice_enhancement_workflow_definition():
    return copy.deepcopy(DECLARED_AGENT_WORKFLOW_CATALOG["review_voice_enhancement"])


def build_default_smart_indicator_workflow_definition():
    return copy.deepcopy(DECLARED_AGENT_WORKFLOW_CATALOG["smart_indicator_agent"])


def build_default_knowledge_query_workflow_definition():
    return copy.deepcopy(DECLARED_AGENT_WORKFLOW_CATALOG["knowledge_query_agent"])


def build_default_evidence_chain_workflow_definition():
    return copy.deepcopy(DECLARED_AGENT_WORKFLOW_CATALOG["evidence_chain_agent"])


def build_default_knowledge_processing_workflow_definition():
    return copy.deepcopy(DECLARED_AGENT_WORKFLOW_CATALOG["knowledge_processing_agent"])


def build_default_knowledge_graph_workflow_definition():
    return copy.deepcopy(DECLARED_AGENT_WORKFLOW_CATALOG["knowledge_graph_agent"])


def build_default_knowledge_asset_workflow_definition():
    return copy.deepcopy(DECLARED_AGENT_WORKFLOW_CATALOG["knowledge_asset_agent"])


def build_agent_workflow_center_payload(forecast_workflow_meta=None):
    workflows = [
        build_declared_agent_workflow_meta(definition)
        for definition in (
            normalize_declared_agent_workflow_definition(item)
            for item in DECLARED_AGENT_WORKFLOW_CATALOG.values()
        )
    ]
    if isinstance(forecast_workflow_meta, dict):
        workflows.append(
            {
                "id": "forecast_model",
                "title": str(forecast_workflow_meta.get("title") or "预测算法工作流").strip() or "预测算法工作流",
                "summary": str(forecast_workflow_meta.get("summary") or "").strip(),
                "category": "预测智能体",
                "feature_key": "stock_forecast",
                "execution_mode": "editable_graph_workflow",
                "tags": ["Admin", "图形编排", "预测算法"],
                "graph": copy.deepcopy(forecast_workflow_meta.get("graph") or {}),
                "preview": copy.deepcopy(forecast_workflow_meta.get("preview") or {}),
                "catalog": copy.deepcopy(forecast_workflow_meta.get("catalog") or []),
            }
        )
    return {
        "summary": {
            "workflow_count": len(workflows),
            "categories": sorted({item.get("category") or "" for item in workflows if item.get("category")}),
        },
        "workflows": workflows,
    }
