import copy
import time


DECLARED_AGENT_WORKFLOW_CATALOG = {
    "hermes_agent": {
        "id": "hermes_agent",
        "title": "小金智能体",
        "summary": "小金智能体的真实非线性主链路：先读取会话记忆，再由 Admin 默认 LLM 拆解任务并按安全、澄清、闲聊、单场景研究或组合研究分支路由；Gangtise 研究正文原样返回，最后写回会话与用户记忆。",
        "category": "对话智能体",
        "feature_key": "hermes",
        "execution_mode": "declared_agent_workflow",
        "tags": ["H5", "Admin 默认 LLM", "六类场景", "多任务拆解", "Gangtise 直出", "会话记忆"],
        "nodes": [
            {"id": "question_input", "label": "问题输入校验", "processor": "input", "kind": "source", "x": 650, "y": 32, "description": "接收 H5 当前轮问题、附件、知识范围和消息快照。空值直接拒绝；当前问题优先于旧消息，避免前端清空输入后丢失文本。"},
            {"id": "session_load", "label": "会话记忆装载", "processor": "session_load", "kind": "context", "x": 650, "y": 176, "description": "读取当前会话最近轮次、摘要、意图和证券对象。"},
            {"id": "memory_read", "label": "用户记忆读取", "processor": "memory_read", "kind": "context", "x": 650, "y": 320, "description": "读取关注证券、长期主题、表达偏好和用户画像；仅用已确认实体承接指代。"},
            {"id": "scope_guard", "label": "基础技术校验", "processor": "input_validation", "kind": "guardrail", "x": 650, "y": 464, "description": "只检查请求格式、空值、权限、长度和附件技术约束，不判断意图、不做关键词拦截。"},
            {"id": "intent_router", "label": "LLM 意图拆解", "processor": "router", "kind": "llm", "x": 650, "y": 608, "description": "第一轮语义处理：使用 Admin 当前默认模型，把用户原始问题结合记忆拆成一个或多个任务，输出 execute / clarify / chat / refuse。"},
            {"id": "semantic_interception", "label": "语义拦截 Skill", "processor": "semantic_interception", "kind": "guardrail", "x": 650, "y": 752, "description": "默认关闭。启用后由 Admin 配置的 Skill 再调用默认 LLM 判断是否命中语义规则，并记录规则、版本、理由和最终动作。"},
            {"id": "refuse_branch", "label": "安全收口", "processor": "branch", "kind": "decision", "visual_only": True, "x": 30, "y": 800, "description": "条件：Planner 或语义拦截 Skill 产生 block / redirect。直接说明处理边界，不调用研究 API。"},
            {"id": "clarify_branch", "label": "信息澄清", "processor": "branch", "kind": "decision", "visual_only": True, "x": 330, "y": 800, "description": "条件：disposition = clarify。对象、时间或任务不明确时先反问，不盲猜、不扣费。"},
            {"id": "chat_branch", "label": "多轮闲聊", "processor": "branch", "kind": "decision", "visual_only": True, "x": 630, "y": 800, "description": "条件：disposition = chat。通用投资问题和闲聊由 Admin 默认 LLM 继续回答。"},
            {"id": "single_branch", "label": "单场景研究", "processor": "branch", "kind": "decision", "visual_only": True, "x": 930, "y": 800, "description": "条件：disposition = execute 且 tasks 数量为 1。进入对应研究能力。"},
            {"id": "composite_branch", "label": "组合研究", "processor": "branch", "kind": "decision", "visual_only": True, "x": 1230, "y": 800, "description": "条件：disposition = execute 且 tasks 数量大于等于 2。任务拆解后串行执行，保留部分成功结果。"},
            {"id": "human_review_branch", "label": "人工审核", "processor": "branch", "kind": "decision", "visual_only": True, "x": 1530, "y": 800, "description": "条件：语义拦截 Skill = human_review。停止研究工具调用，返回人工审核提示并保留审计记录。"},
            {"id": "chat_answer_branch", "label": "闲聊回答生成", "processor": "llm_generation", "kind": "llm", "visual_only": True, "x": 630, "y": 980, "description": "场景 6：多轮闲聊由 Admin 默认 LLM 生成回答，并承接会话记忆。"},
            {"id": "contract_validation", "label": "任务契约校验", "processor": "contract_validation", "kind": "guardrail", "visual_only": True, "x": 930, "y": 980, "description": "检查证券、时间范围、任务参数和付费能力约束，空值或模糊条件返回澄清。"},
            {"id": "task_decomposition", "label": "组合任务拆解", "processor": "task_decomposition", "kind": "planner", "visual_only": True, "x": 1230, "y": 980, "description": "将用户一句话拆成多个独立任务，保留每个任务的场景、证券和时间范围。"},
            {"id": "stock_today_capability", "label": "今日个股观察", "processor": "gangtise_agent_sse", "kind": "tooling", "visual_only": True, "x": 30, "y": 1160, "description": "场景 1：今日行情、逻辑、要闻、风险。调用 Gangtise Agent SSE：/application/open-ai/ai/chat/sse，mode=deep_research。"},
            {"id": "market_today_capability", "label": "今日大盘分析", "processor": "gangtise_agent_sse", "kind": "tooling", "visual_only": True, "x": 330, "y": 1160, "description": "场景 2a：指数表现、板块资金、情绪展望。调用 Gangtise Agent SSE：/application/open-ai/ai/chat/sse，mode=deep_research。"},
            {"id": "one_pager_capability", "label": "个股结构化分析报告", "processor": "gangtise_one_pager", "kind": "tooling", "visual_only": True, "x": 630, "y": 1160, "description": "场景 3：深化研究，非当日研究。调用 /application/open-ai/agent/one-pager，指数不支持。"},
            {"id": "highlights_capability", "label": "个股看点摘要", "processor": "gangtise_stock_summary", "kind": "tooling", "visual_only": True, "x": 930, "y": 1160, "description": "场景 4：精炼看点，最多 6000 个证券。调用 /application/open-ai/stock-summary/getList，不能替代完整观察报告。"},
            {"id": "multi_watchlist_capability", "label": "多自选股综合分析", "processor": "gangtise_multi_stock_sse", "kind": "tooling", "visual_only": True, "x": 1230, "y": 1160, "description": "场景 5：与复盘一致的多股综合分析，调用复盘使用的 Gangtise 多股票 Agent SSE 能力。"},
            {"id": "serial_dispatch", "label": "串行任务执行", "processor": "serial_dispatch", "kind": "planner", "visual_only": True, "x": 1230, "y": 1320, "description": "按任务顺序调用能力，避免重复发送和并发污染；单项失败不丢失已完成结果。"},
            {"id": "market_split_capability", "label": "上证 + 深证拆解", "processor": "gangtise_market_split", "kind": "planner", "visual_only": True, "x": 930, "y": 1320, "description": "场景 2b：用户同时询问上证和深证时，拆成两个场景 2a 的 Gangtise Agent SSE 调用，再汇总两份观察报告。"},
            {"id": "shanghai_market_capability", "label": "上证指数观察", "processor": "gangtise_agent_sse", "kind": "tooling", "visual_only": True, "x": 810, "y": 1500, "description": "双指数拆解的第一项：以“今天上证综合指数的分析观察报告”调用 Gangtise Agent SSE。"},
            {"id": "shenzhen_market_capability", "label": "深证指数观察", "processor": "gangtise_agent_sse", "kind": "tooling", "visual_only": True, "x": 1050, "y": 1500, "description": "双指数拆解的第二项：以“今天深证成份指数的分析观察报告”调用 Gangtise Agent SSE。"},
            {"id": "tool_dispatch", "label": "任务级工具调度", "processor": "tool_dispatch", "kind": "tooling", "x": 650, "y": 1690, "description": "真实执行节点：单任务或组合任务按服务端契约调用 Gangtise SSE、一页通、看点或复盘多股接口；部分失败保留成功结果。"},
            {"id": "answer_synthesis", "label": "回答策略与直出", "processor": "llm_synthesis", "kind": "llm", "x": 650, "y": 1840, "description": "真实执行节点：澄清直接追问；Gangtise 研究正文原样直出；闲聊才使用 Admin 默认 LLM 合成。"},
            {"id": "result_assembly", "label": "结果汇合", "processor": "result_assembly", "kind": "output", "visual_only": True, "x": 650, "y": 1990, "description": "统一汇合拒绝、澄清、闲聊、单任务和组合任务结果。"},
            {"id": "memory_extract", "label": "本轮记忆提炼", "processor": "memory_extract", "kind": "planner", "x": 650, "y": 2140, "description": "提炼最近证券、主题、任务意图、表达偏好和用户行为标签。"},
            {"id": "memory_write", "label": "会话与用户记忆写回", "processor": "memory_write", "kind": "storage", "x": 650, "y": 2290, "description": "写入问答原文、会话工作记忆、用户事实记忆和任务标签。"},
            {"id": "user_profile_update", "label": "用户画像更新", "processor": "user_profile_update", "kind": "storage", "x": 650, "y": 2440, "description": "更新关注对象、研究深度、兴趣主题、功能偏好和会话历史。"},
            {"id": "artifact_render", "label": "H5 结果渲染", "processor": "artifact", "kind": "output", "x": 650, "y": 2590, "description": "返回当前 H5 兼容的文本、结构化工件、任务轨迹、澄清问题和记忆状态。"},
        ],
        "edges": [
            {"id": "edge_hermes_1", "from": "question_input", "to": "session_load"},
            {"id": "edge_hermes_2", "from": "session_load", "to": "memory_read"},
            {"id": "edge_hermes_3", "from": "memory_read", "to": "scope_guard"},
            {"id": "edge_hermes_4", "from": "scope_guard", "to": "intent_router"},
            {"id": "edge_hermes_5", "from": "intent_router", "to": "semantic_interception"},
            {"id": "edge_hermes_refuse", "from": "semantic_interception", "to": "refuse_branch", "label": "拒绝", "condition": "Planner 或 Skill = refuse / block / redirect"},
            {"id": "edge_hermes_clarify", "from": "semantic_interception", "to": "clarify_branch", "label": "需补充", "condition": "Planner 或 Skill = clarify"},
            {"id": "edge_hermes_chat", "from": "semantic_interception", "to": "chat_branch", "label": "闲聊", "condition": "execute + chat"},
            {"id": "edge_hermes_single", "from": "semantic_interception", "to": "single_branch", "label": "单任务", "condition": "execute + 1 task"},
            {"id": "edge_hermes_composite", "from": "semantic_interception", "to": "composite_branch", "label": "多任务", "condition": "execute + 2+ tasks"},
            {"id": "edge_hermes_human_review", "from": "semantic_interception", "to": "human_review_branch", "label": "人工审核", "condition": "Skill = human_review"},
            {"id": "edge_hermes_single_contract", "from": "single_branch", "to": "contract_validation"},
            {"id": "edge_hermes_stock", "from": "contract_validation", "to": "stock_today_capability", "label": "今日个股", "condition": "stock_today_observation"},
            {"id": "edge_hermes_market", "from": "contract_validation", "to": "market_today_capability", "label": "今日大盘", "condition": "market_today_observation"},
            {"id": "edge_hermes_market_split", "from": "contract_validation", "to": "market_split_capability", "label": "上证 + 深证", "condition": "双指数拆解"},
            {"id": "edge_hermes_onepager", "from": "contract_validation", "to": "one_pager_capability", "label": "深化研究", "condition": "stock_one_pager"},
            {"id": "edge_hermes_highlights", "from": "contract_validation", "to": "highlights_capability", "label": "精炼看点", "condition": "stock_highlights"},
            {"id": "edge_hermes_multi", "from": "contract_validation", "to": "multi_watchlist_capability", "label": "多自选股", "condition": "multi_watchlist_analysis"},
            {"id": "edge_hermes_chat_answer", "from": "chat_branch", "to": "chat_answer_branch", "label": "LLM", "condition": "Admin 默认模型"},
            {"id": "edge_hermes_composite_decompose", "from": "composite_branch", "to": "task_decomposition"},
            {"id": "edge_hermes_serial", "from": "task_decomposition", "to": "serial_dispatch", "label": "按序", "condition": "tasks[]"},
            {"id": "edge_hermes_composite_tool", "from": "serial_dispatch", "to": "tool_dispatch"},
            {"id": "edge_hermes_stock_tool", "from": "stock_today_capability", "to": "tool_dispatch"},
            {"id": "edge_hermes_market_tool", "from": "market_today_capability", "to": "tool_dispatch"},
            {"id": "edge_hermes_shanghai", "from": "market_split_capability", "to": "shanghai_market_capability", "label": "第 1 项", "condition": "上证综合指数"},
            {"id": "edge_hermes_shenzhen", "from": "market_split_capability", "to": "shenzhen_market_capability", "label": "第 2 项", "condition": "深证成份指数"},
            {"id": "edge_hermes_shanghai_tool", "from": "shanghai_market_capability", "to": "tool_dispatch", "label": "场景 2a"},
            {"id": "edge_hermes_shenzhen_tool", "from": "shenzhen_market_capability", "to": "tool_dispatch", "label": "场景 2a"},
            {"id": "edge_hermes_onepager_tool", "from": "one_pager_capability", "to": "tool_dispatch"},
            {"id": "edge_hermes_highlights_tool", "from": "highlights_capability", "to": "tool_dispatch"},
            {"id": "edge_hermes_multi_tool", "from": "multi_watchlist_capability", "to": "tool_dispatch"},
            {"id": "edge_hermes_chat_tool", "from": "chat_answer_branch", "to": "answer_synthesis"},
            {"id": "edge_hermes_direct_answer", "from": "tool_dispatch", "to": "answer_synthesis", "label": "研究原文直出"},
            {"id": "edge_hermes_refuse_answer", "from": "refuse_branch", "to": "answer_synthesis"},
            {"id": "edge_hermes_clarify_answer", "from": "clarify_branch", "to": "answer_synthesis"},
            {"id": "edge_hermes_human_review_answer", "from": "human_review_branch", "to": "answer_synthesis"},
            {"id": "edge_hermes_answer_result", "from": "answer_synthesis", "to": "result_assembly"},
            {"id": "edge_hermes_memory_extract", "from": "result_assembly", "to": "memory_extract"},
            {"id": "edge_hermes_memory_write", "from": "memory_extract", "to": "memory_write"},
            {"id": "edge_hermes_profile", "from": "memory_write", "to": "user_profile_update"},
            {"id": "edge_hermes_render", "from": "user_profile_update", "to": "artifact_render"},
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
                "visual_only": item.get("visual_only") is True,
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
                "label": str(item.get("label") or "").strip(),
                "condition": str(item.get("condition") or "").strip(),
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
        if node.get("visual_only"):
            result = {
                "status": "design_only",
                "detail": "设计态分支节点，仅用于展示路由条件，不参与运行时执行。",
                "output": None,
                "context_preview": {},
            }
        elif executor is None:
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
