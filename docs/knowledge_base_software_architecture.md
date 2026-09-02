# 知识库软件设计架构

## 1. 文档目标

本文件描述当前项目中“知识库能力”的软件设计架构，并给出面向后续演进的推荐架构。

这里关注的是技术实现，不是产品文案。重点包括：

- 模块分层
- 核心对象模型
- 数据流
- Hermes 与知识库的协作方式
- 工作流与异步链路
- 当前问题
- 推荐演进方向


## 2. 当前知识库能力边界

当前知识库已经覆盖以下能力：

- 手工录入知识
- 文件解析预览
- URL 内容预览
- 知识异步入库
- 向量化与向量召回
- 知识图谱展示
- 知识检索问答
- 证据链检索问答
- Hermes 知识优先问答
- Hermes 回答沉淀为知识源

当前更接近：

- 租户级知识库
- 租户级知识召回
- 租户级研究问答

还没有完全演进为：

- NotebookLM 式知识工作区
- 多 source 会话级问答
- 完整知识源集合管理系统


## 3. 当前代码结构

与知识库直接相关的主要模块：

- [src/web/api_kol.py](/Users/xuchenfei/PycharmProjects/gangtise_demo/src/web/api_kol.py)
- [src/web/api_experience.py](/Users/xuchenfei/PycharmProjects/gangtise_demo/src/web/api_experience.py)
- [src/domain/ai_services.py](/Users/xuchenfei/PycharmProjects/gangtise_demo/src/domain/ai_services.py)
- [src/domain/knowledge_graph_services.py](/Users/xuchenfei/PycharmProjects/gangtise_demo/src/domain/knowledge_graph_services.py)
- [src/domain/core_services.py](/Users/xuchenfei/PycharmProjects/gangtise_demo/src/domain/core_services.py)
- [templates/h5.html](/Users/xuchenfei/PycharmProjects/gangtise_demo/templates/h5.html)
- [templates/kol_workbench.html](/Users/xuchenfei/PycharmProjects/gangtise_demo/templates/kol_workbench.html)

当前责任大致如下：

### 3.1 Web 层

负责暴露接口：

- `/api/kol/knowledge/manual`
- `/api/kol/knowledge/ingest`
- `/api/kol/knowledge/file-preview`
- `/api/kol/knowledge/url-preview`
- `/api/kol/knowledge/query`
- `/api/kol/knowledge-graph`
- `/api/admin/knowledge-items`
- `/api/admin/knowledge-graph`
- `/api/hermes/query`

主要职责：

- 参数接收
- 基础校验
- 调用领域服务
- 返回 JSON

### 3.2 Domain 层

当前知识库的大部分核心逻辑集中在 `ai_services.py` 中，包括：

- 文本 embedding
- 知识召回
- LLM 过滤
- LLM 问答生成
- Hermes 工具链
- Hermes 知识优先路由
- 知识备份/管理统计的一部分

`knowledge_graph_services.py` 主要负责：

- 知识图谱结构整理
- 图谱节点/边组织

### 3.3 前端模板层

`h5.html` 与 `kol_workbench.html` 承担：

- 知识录入表单
- 文件上传入口
- 知识问答展示
- Hermes 附件问答入口
- 知识图谱展示入口


## 4. 当前逻辑分层模型

当前知识库实际上已经形成了一套简化分层：

```text
前端页面
  -> Web API
    -> Domain Service
      -> 向量库 / Postgres
      -> LLM
      -> 图谱构造
      -> Hermes Agent
```

但这套分层还不够干净，因为：

- Web 层与 Domain 层耦合仍重
- Domain 层承担了过多基础设施职责
- 缺少独立 repository / storage / retrieval / orchestration 分层


## 5. 当前知识库核心对象

从现有行为看，系统实际已经在使用这些逻辑对象。

## 5.1 Tenant Knowledge Hub

这是当前最核心的知识组织方式。

特点：

- 以租户为边界
- 一个租户拥有一组知识
- Hermes 默认优先检索当前租户知识

当前它是事实上的核心对象，但不是完全清晰的数据模型对象。

## 5.2 Knowledge Entry

知识条目是当前最基础的知识对象。

典型属性包括：

- id
- title
- summary
- body
- source_detail
- knowledge_type
- tags
- created_at

这是前端和后端当前共同使用的主对象。

## 5.3 Knowledge Embedding Record

这是检索用对象，主要存在于 `knowledge_embeddings` 中。

作用：

- 保存文本向量
- 保存检索元数据
- 作为 RAG 召回基础

## 5.4 Knowledge Graph Node

图谱层对象不是文件对象，而是知识关系对象。

当前图谱已经在往真正知识节点靠近，节点类型更像：

- topic
- entity
- method
- claim
- signal

这比“文件节点图”更合理。

## 5.5 Hermes Memory Related Knowledge Context

Hermes 与知识库不是分离的。

当前 Hermes 会读取：

- 租户知识
- 附件上下文
- 用户记忆
- 会话记忆

然后合成回答。


## 6. 当前核心数据流

## 6.1 知识入库数据流

当前逻辑大致是：

```text
手工输入 / 文件 / URL / Hermes回答
  -> 预览或整理
  -> 创建异步任务
  -> 后台处理
  -> 文本清洗
  -> embedding 生成
  -> 写入 knowledge_embeddings
  -> 更新租户知识数据
```

主要入口：

- `knowledge/manual`
- `knowledge/ingest`

当前特点：

- 入库是异步化的
- 支持多来源
- 已经具备基本知识沉淀链路

## 6.2 知识问答数据流

当前知识问答链路：

```text
用户问题
  -> query_text
  -> embedding
  -> 向量召回
  -> 候选知识命中
  -> 可选 LLM 过滤
  -> 可选 LLM 回答生成
  -> 返回 answer + matches + workflow_meta
```

这个链路已经是标准 RAG 的简化实现。

## 6.3 Hermes 知识问答数据流

当前 Hermes 链路：

```text
用户问题
  -> session_load
  -> memory_read
  -> scope_guard
  -> intent_router
  -> knowledge.search
  -> attachment.context
  -> watchlist/detail/dashboard/evidence
  -> synthesis
  -> memory_extract
  -> memory_write
  -> user_profile_update
```

其中最关键的是：

- `knowledge.search` 固定优先
- 附件作为临时上下文参与本轮问答
- 互联网信息只能后置补充


## 7. 当前架构的优点

## 7.1 知识库已经不是静态列表

它已经具备：

- 向量检索
- 问答生成
- Hermes 调用
- 图谱扩展

这说明基础方向是对的。

## 7.2 知识与 Hermes 没有割裂

当前不是两个系统：

- 一个是知识库
- 一个是 AI 问答

而是 Hermes 已经把知识库作为首要来源。

这是后续进化成研究型 Agent 的好基础。

## 7.3 已有异步任务基础

知识入库是通过异步任务执行的，这使得：

- 文件解析
- embedding 生成
- 知识沉淀

不会完全阻塞页面请求。

## 7.4 已有图谱能力

知识库不是只停留在向量层，还已经有图谱层入口，这给后续扩展：

- 关系检索
- 主题聚合
- 证据链可视化

提供了基础。


## 8. 当前架构存在的问题

## 8.1 Domain 层过重

当前 `ai_services.py` 承担了太多职责：

- embedding
- retrieval
- filter
- answer generation
- Hermes tool execution
- memory persistence
- admin analytics

这会导致：

- 可维护性差
- 测试边界不清晰
- 后续迭代风险高

## 8.2 缺少知识库专属模块边界

目前没有真正独立的：

- knowledge_service
- knowledge_repository
- knowledge_retrieval_engine
- knowledge_workspace_service

这使得知识库被散落在多个模块中。

## 8.3 缺少 workspace/source_set 层

当前知识组织还是：

- 以租户整体知识库为主
- 单条 knowledge 为最小显式对象

缺少：

- 一组知识源
- 一个知识工作区
- 一次会话明确绑定一组知识

这也是当前还不像 NotebookLM 的关键原因。

## 8.4 知识问答与证据链问答仍部分复用同一实现

当前 `knowledge_query` 和 `evidence_chain` 共用较多底层逻辑。

这短期没问题，但长期会导致两个产品能力边界混淆：

- 知识问答更偏 notebook/source QA
- 证据链更偏 research trace / citation reasoning

后续应该逻辑复用，但产品对象明确分离。

## 8.5 前端交互还不是知识工作区模式

当前前端更像：

- 录入知识
- 查知识
- Hermes 顺带问

还不是：

- 建立知识源集合
- 进入知识工作区
- 持续围绕这组知识问答


## 9. 推荐的软件设计分层

建议将知识库拆成以下结构。

```text
src/modules/knowledge/
  api.py
  service.py
  retrieval.py
  workspace.py
  graph.py
  repository.py
  schemas.py

src/modules/hermes/
  api.py
  service.py
  tools.py
  memory.py
  orchestration.py

src/infra/
  db/
  vector/
  llm/
  files/
```

职责建议如下。

## 9.1 knowledge/api.py

只负责：

- 接口定义
- 请求参数读取
- 返回结构统一

## 9.2 knowledge/service.py

负责：

- 知识录入
- 知识编辑
- 知识查询
- source 管理

## 9.3 knowledge/retrieval.py

负责：

- embedding 查询
- hybrid search
- rerank
- chunk 召回

## 9.4 knowledge/workspace.py

负责：

- knowledge workspace/notebook
- source set 绑定
- workspace 范围问答

## 9.5 knowledge/graph.py

负责：

- 图谱节点生成
- 关系边生成
- 图谱聚合与裁剪

## 9.6 knowledge/repository.py

负责：

- knowledge source CRUD
- workspace CRUD
- chunk / embedding / relation 读写

## 9.7 hermes/tools.py

负责：

- `knowledge.search`
- `attachment.context`
- `evidence.search`
- `workspace.search`

Hermes 不直接关心知识怎么存，只调用标准工具协议。


## 10. 推荐的核心数据模型

## 10.1 knowledge_source

表示一个知识来源。

建议字段：

- `id`
- `tenant_slug`
- `source_type`
- `title`
- `source_name`
- `origin_url`
- `file_name`
- `mime_type`
- `created_by`
- `status`
- `created_at`
- `updated_at`

## 10.2 knowledge_document

表示 source 清洗后的正文对象。

建议字段：

- `id`
- `source_id`
- `tenant_slug`
- `title`
- `summary`
- `body_text`
- `raw_payload_json`
- `created_at`

## 10.3 knowledge_chunk

表示最小召回单元。

建议字段：

- `id`
- `document_id`
- `chunk_index`
- `chunk_text`
- `chunk_summary`
- `metadata_json`
- `created_at`

## 10.4 knowledge_workspace

表示知识工作区。

建议字段：

- `id`
- `tenant_slug`
- `name`
- `description`
- `scope_mode`
- `created_by`
- `created_at`
- `updated_at`

## 10.5 knowledge_workspace_source

表示 workspace 与 source 的绑定。

建议字段：

- `id`
- `workspace_id`
- `source_id`
- `display_order`
- `created_at`

## 10.6 knowledge_qa_session

表示围绕知识工作区的问答会话。

建议字段：

- `id`
- `tenant_slug`
- `workspace_id`
- `user_role`
- `user_profile_id`
- `entry_point`
- `created_at`
- `updated_at`

## 10.7 knowledge_qa_turn

表示某轮问答。

建议字段：

- `id`
- `session_id`
- `question_text`
- `answer_text`
- `used_source_ids_json`
- `used_chunk_ids_json`
- `llm_model_json`
- `trace_json`
- `created_at`


## 11. 推荐的工作流设计

## 11.1 知识入库工作流

```text
source_input
  -> source_parse
  -> source_clean
  -> chunk_split
  -> tag_extract
  -> entity_extract
  -> embedding_write
  -> graph_emit
  -> source_publish
```

## 11.2 知识问答工作流

```text
qa_input
  -> scope_resolve
  -> retrieve_chunks
  -> rerank
  -> answer_synthesis
  -> citation_bind
  -> qa_trace_write
```

## 11.3 Hermes 知识工作区问答工作流

```text
session_load
  -> memory_read
  -> workspace_scope_load
  -> intent_router
  -> workspace.search
  -> attachment.context
  -> answer_synthesis
  -> memory_write
  -> analytics_emit
```


## 12. Hermes 与知识库的架构协作方式

Hermes 应该作为知识问答的上层编排器，而不是知识库本身。

推荐职责边界：

### 知识库负责

- source 管理
- document/chunk/embedding 存储
- workspace 管理
- retrieval
- citation material

### Hermes 负责

- 意图识别
- 范围守卫
- 会话上下文
- 用户记忆
- 多工具协调
- 最终回答组织

### 两者之间通过工具协议连接

例如：

- `knowledge.search`
- `workspace.search`
- `attachment.context`
- `evidence.search`

这样 Hermes 可替换、知识库也可独立演进。


## 13. 当前到目标架构的迁移建议

建议分四步。

## 13.1 第一步：抽出 knowledge 模块

把当前知识相关逻辑从 `ai_services.py` 中整理成独立知识模块。

优先抽：

- `build_knowledge_query_response`
- `search_knowledge_embeddings`
- `fetch_live_knowledge_hub`
- `build_knowledge_chat_prompts`

## 13.2 第二步：补 workspace/source_set

建立：

- `knowledge_workspace`
- `knowledge_workspace_source`

并给 Hermes 增加 workspace 范围问答模式。

## 13.3 第三步：回答引用结构化

让问答结果不只是返回 `answer + matches`，而是返回：

- answer
- key_points
- source_cards
- chunk_citations

## 13.4 第四步：与图谱、记忆、Admin 统计打通

最终形成：

- 知识源资产层
- 问答会话层
- 图谱层
- Hermes 记忆层
- Admin 运营统计层


## 14. 最终推荐目标架构

推荐目标架构如下：

```text
前端 H5 / 大V工作台 / Admin
  -> Knowledge API / Hermes API
    -> Knowledge Application Layer
      -> Source Service
      -> Workspace Service
      -> Retrieval Service
      -> Graph Service
    -> Hermes Application Layer
      -> Intent Router
      -> Tool Dispatcher
      -> Memory Manager
      -> Answer Synthesizer
    -> Infrastructure
      -> Postgres
      -> pgvector
      -> LLM
      -> File Parser
      -> Async Worker
```

这个结构的好处：

- 知识库可独立演进
- Hermes 可复用知识能力
- 可继续做 NotebookLM 型体验
- 可继续扩到证据链、复盘、智能指标解释


## 15. 结论

当前知识库系统已经具备了知识问答的基础软件架构，但还处于：

- 租户知识库 + RAG 问答
- Hermes 知识优先编排
- 图谱与知识沉淀并存

的阶段。

要升级成更完整、更清晰的软件架构，建议重点推进：

1. 独立知识模块化
2. 引入 workspace/source_set
3. 回答来源结构化
4. 将 Hermes 与知识库通过标准工具协议解耦

这样既能保留你当前已经完成的能力，也能为后续做 NotebookLM 型知识问答、研究工作区、知识图谱协同和 Agent 化运营打下稳定基础。
