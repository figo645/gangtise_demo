# 知识库问答能力设计优化方案

## 1. 目标

当前系统已经具备知识录入、向量召回、知识问答、Hermes 知识优先回答等基础能力，但整体仍更接近“租户级知识库检索 + 问答”，还没有完全达到类似 NotebookLM 的“围绕知识源集合持续问答”的产品形态。

本方案目标是把现有知识库能力优化为：

- 用户上传知识源后，可围绕该批知识持续问答
- Hermes 支持明确限定知识范围，而不是默认查全租户知识
- 回答结果具备更强的来源可解释性
- 知识源、问答、记忆、图谱、工作流形成统一资产层


## 2. 当前能力评估

## 2.1 已有能力

当前代码中，知识库已经具备以下能力：

- 手工知识录入
- 文件解析预览
- URL 预览
- 知识异步入库
- 向量召回
- 纯检索模式问答
- 检索后交给模型生成回答
- Hermes 知识优先问答
- Hermes 附件临时上下文问答
- 知识图谱展示
- Hermes 回答沉淀为知识源

关键接口与模块：

- [src/web/api_kol.py](/Users/xuchenfei/PycharmProjects/gangtise_demo/src/web/api_kol.py)
- [src/domain/ai_services.py](/Users/xuchenfei/PycharmProjects/gangtise_demo/src/domain/ai_services.py)
- [templates/h5.html](/Users/xuchenfei/PycharmProjects/gangtise_demo/templates/h5.html)
- [templates/kol_workbench.html](/Users/xuchenfei/PycharmProjects/gangtise_demo/templates/kol_workbench.html)

## 2.2 当前工作方式

当前知识问答主链路是：

1. 用户提交问题
2. 系统做知识召回
3. 可选做大模型过滤
4. 可选做大模型回答生成
5. 返回回答、命中结果、工作流元信息

Hermes 主链路是：

1. 读取会话和记忆
2. 做范围守卫
3. 做意图识别
4. 固定优先执行 `knowledge.search`
5. 再执行平台内工具
6. 最后可选互联网补充
7. 合成回答并写入记忆

从能力上讲，这已经不是单纯的 FAQ 检索，而是一个基础的 RAG 问答体系。


## 3. 当前与 NotebookLM 形态的差距

## 3.1 缺少“知识源集合”这一层

当前知识条目是以单条知识或整租户知识库为主要组织方式。

NotebookLM 类产品的核心不只是“有知识”，而是：

- 用户明确知道当前正在围绕哪一组知识源问答
- 一次对话绑定一组 source
- 后续追问默认沿用该组 source

当前系统还没有一个正式的：

- notebook
- source_set
- knowledge_workspace

这样的中间对象。

## 3.2 缺少会话级知识范围绑定

虽然代码里已有 `selected_knowledge_ids` 机制，但现在更像“临时限定几条知识”，而不是完整的知识工作区。

当前不足：

- 不能优雅管理多份 source
- 不能把会话长期绑定到一个知识集合
- 不能方便切换“这个问题基于哪组资料”

## 3.3 上传文件更像临时附件，而不是正式知识源

当前 Hermes 支持上传文件解析，然后把解析结果作为本轮附件上下文参与问答。

这意味着：

- 可以做一次性问答
- 但默认不会自动变成一个可复用的知识源集合
- 用户对“这份文件现在属于哪个知识工作区”感知不强

## 3.4 来源型回答展示不够强

当前已经有：

- matches
- citations
- source policy

但还不够像 NotebookLM，因为还缺：

- 回答与原文片段的强绑定
- 来源卡片可展开原文
- 多来源命中聚合展示
- 同一问题到底引用了哪几份 source 的清晰展示

## 3.5 知识对象层级还不够完整

当前知识资产已经有 embedding 和图谱，但从产品能力角度仍建议补齐：

- knowledge_source
- knowledge_document
- knowledge_chunk
- knowledge_entity
- knowledge_relation
- knowledge_source_set
- knowledge_session_binding
- knowledge_qa_trace

否则后续做 source-based QA、source-based memory、source-based graph 会比较别扭。


## 4. 优化目标形态

建议把知识库能力分成四层。

## 4.1 第一层：知识源层

这是用户真正感知到的“上传了什么资料”。

对象建议：

- `knowledge_source`
  - 表示一份具体来源
  - 例如 PDF、DOCX、URL、手工输入、Hermes回答沉淀

建议字段：

- `source_id`
- `tenant_slug`
- `source_type`
- `source_name`
- `source_title`
- `source_status`
- `origin_url`
- `file_name`
- `mime_type`
- `created_by`
- `created_at`
- `updated_at`
- `visibility_scope`

## 4.2 第二层：知识内容层

这是供召回和问答真正使用的内容层。

对象建议：

- `knowledge_document`
- `knowledge_chunk`
- `knowledge_embedding`
- `knowledge_metadata`

其中：

- source 是“来源”
- document 是“文档对象”
- chunk 是“最小检索单元”

## 4.3 第三层：知识工作区层

这是最接近 NotebookLM 的核心层。

对象建议：

- `knowledge_workspace`
- `knowledge_workspace_source`

作用：

- 一个 workspace 可以挂多份 source
- 用户围绕 workspace 持续问答
- 可以切换不同主题的知识工作区

示例：

- 港股互联网估值框架
- 2026Q2 大V复盘资料集
- 智能指标设计资料包

## 4.4 第四层：知识问答层

对象建议：

- `knowledge_qa_session`
- `knowledge_qa_turn`
- `knowledge_qa_trace`

作用：

- 保存某次问答绑定了哪个 workspace
- 记录本轮用了哪些 source、哪些 chunk
- 记录最终回答、引用、过滤结果和模型信息


## 5. Hermes 在知识问答中的新定位

Hermes 不应该只做“租户大脑”，还应该支持两种知识问答模式。

## 5.1 模式一：租户全局知识问答

适合：

- 泛知识检索
- 平台功能说明
- 方法论问答
- 广义研究问答

特征：

- 默认查当前租户知识库
- 知识优先，再补平台工具，最后可选互联网

## 5.2 模式二：知识工作区问答

适合：

- 用户刚上传了一组文件
- 用户想围绕某个专题资料包持续问答
- 用户要做类似 NotebookLM 的“只基于这些资料”对话

特征：

- 当前会话显式绑定某个 workspace
- 回答默认只从 workspace 内 source 检索
- 不再默认查全租户知识库
- 可切换为“扩展到租户知识”或“补互联网”

这两种模式应共用同一个 Hermes 内核，但用不同的 scope。


## 6. 前端产品形态建议

## 6.1 H5 端 Hermes

当前 H5 Hermes 建议增加一个更明确的“知识源模式”。

建议交互：

1. 默认是“租户知识”
2. 用户点击“知识源”
3. 可以：
   - 上传文件
   - 选择已有知识源
   - 新建知识工作区
   - 把若干知识源加入当前工作区
4. 顶部显示当前问答范围

显示建议：

- 当前范围：租户知识
- 当前范围：知识工作区《港股互联网估值框架》
- 当前范围：仅本轮附件

## 6.2 工作台知识专区

大V工作台应成为知识源经营中心，而不只是录入台。

建议拆成 4 个子区：

- 知识源
- 知识工作区
- 知识问答
- 知识图谱

### 知识源

展示：

- 已上传文件
- 手工录入知识
- URL 知识
- Hermes 沉淀知识

### 知识工作区

展示：

- 每个工作区有哪些 source
- 可新增 / 移除 source
- 可开始围绕该工作区问答

### 知识问答

展示：

- 当前 workspace
- 回答
- 来源引用
- 命中 source

### 知识图谱

展示：

- 不再以文件为节点
- 而是以知识主题、实体、关系、结论、方法为节点


## 7. 数据模型建议

建议新增或补齐以下对象。

## 7.1 knowledge_source

代表“知识源”。

建议字段：

- `id`
- `tenant_slug`
- `workspace_id`
- `source_type`
- `title`
- `source_name`
- `summary`
- `origin_url`
- `file_name`
- `mime_type`
- `status`
- `created_by`
- `created_at`
- `updated_at`

## 7.2 knowledge_workspace

代表“知识工作区 / notebook”。

建议字段：

- `id`
- `tenant_slug`
- `name`
- `description`
- `scope_mode`
- `default_web_answer`
- `default_submit_to_model`
- `created_by`
- `created_at`
- `updated_at`

## 7.3 knowledge_workspace_source

代表 workspace 与 source 的绑定关系。

建议字段：

- `id`
- `workspace_id`
- `source_id`
- `display_order`
- `created_at`

## 7.4 knowledge_qa_session

代表围绕某个 workspace 的问答会话。

建议字段：

- `id`
- `tenant_slug`
- `workspace_id`
- `user_role`
- `user_profile_id`
- `entry_point`
- `scope_mode`
- `created_at`
- `updated_at`

## 7.5 knowledge_qa_turn

代表每轮问答。

建议字段：

- `id`
- `session_id`
- `question_text`
- `answer_text`
- `submit_to_model`
- `web_answer`
- `used_source_ids_json`
- `used_chunk_ids_json`
- `llm_model_json`
- `trace_json`
- `created_at`


## 8. 工作流建议

## 8.1 知识入库工作流

建议工作流：

1. source_input
2. source_parse
3. source_clean
4. chunk_split
5. tag_extract
6. entity_extract
7. embedding_write
8. graph_emit
9. source_publish

适用于：

- 手工知识
- 文件知识
- URL 知识
- Hermes 回答沉淀知识

## 8.2 知识工作区问答工作流

建议工作流：

1. session_load
2. workspace_scope_load
3. source_resolve
4. chunk_retrieve
5. relevance_filter
6. answer_synthesis
7. citation_bind
8. memory_write
9. analytics_emit

这里和现有 Hermes 工作流最大的区别是：

- 检索范围优先是 workspace
- 不是全租户知识库

## 8.3 知识回答转知识源工作流

当前已经支持“加入知识源”，建议把这条链路正式化。

建议流程：

1. answer_pick
2. structure_extract
3. source_type_mark
4. tag_and_entity_extract
5. source_create
6. embedding_write
7. workspace_attach_optional


## 9. 回答展示设计建议

NotebookLM 风格最重要的不是“能答”，而是“回答看起来是基于资料答的”。

建议回答区域拆成三块：

## 9.1 主回答

展示：

- 直接回答
- 简洁摘要

## 9.2 关键依据

展示：

- 2 到 4 条依据
- 每条依据标明来自哪份 source

## 9.3 来源面板

展示：

- 命中的 source 列表
- 每份 source 命中的片段摘要
- 可展开看更多原文

理想体验：

- 用户看到回答，不会怀疑这是“模型空想”
- 用户能立刻知道结论来自哪几份知识源


## 10. 与知识图谱的关系

知识图谱不应把“文件、URL、语音、手工输入”直接当成图谱主体。

更合理的方式是：

- source 是入口层
- 图谱主体是“真正知识”

建议图谱节点类型：

- topic
- entity
- method
- claim
- evidence
- signal
- risk

建议图谱边类型：

- supports
- contradicts
- belongs_to
- validates
- derived_from
- related_to

这样知识图谱才能更像 Obsidian / NotebookLM 风格，而不是“文件管理图”。


## 11. Admin 侧建议

Admin 不仅要看知识条目，还应能看：

- 租户知识源总量
- 工作区数量
- 每个 workspace 的问答次数
- 热门 source
- 热门问题
- 模型消耗
- 召回命中率
- source 被引用次数

建议新增 4 类管理视图：

1. 知识源总览
2. 工作区总览
3. 知识问答统计
4. 引用与命中分析


## 12. 实施优先级建议

建议按以下顺序推进。

## Phase 1

先补知识工作区模型。

目标：

- 建立 `knowledge_workspace`
- 建立 `knowledge_workspace_source`
- Hermes 支持按 workspace 问答

## Phase 2

再补来源型问答展示。

目标：

- 回答绑定 source
- 回答绑定 chunk
- UI 可查看来源片段

## Phase 3

再补上传即问答即入工作区。

目标：

- 文件上传后可选择“仅本轮使用”或“加入工作区”
- 工作区支持持续问答

## Phase 4

最后统一图谱、记忆、知识源问答统计。

目标：

- 知识图谱真正知识化
- Hermes 记忆与 workspace 打通
- Admin 具备知识问答运营视图


## 13. 结合当前代码的务实判断

当前系统已经具备以下基础：

- 知识入库接口
- 文件 / URL 解析
- 向量召回
- 知识问答接口
- Hermes 知识优先调度
- Hermes 附件上下文
- 回答沉淀知识源
- 知识图谱展示

所以这不是从零开始做 NotebookLM 形态，而是：

- 在现有知识库和 Hermes 上补一层 `workspace/source_set`
- 再补回答来源展示
- 再补前端知识源工作区交互

这条路径是可行的，而且比完全重做成本低得多。


## 14. 结论

当前知识库已经符合“基础知识问答能力”。

Hermes 也已经能做“基于租户知识的针对性问答”。

但如果目标是类似 NotebookLM 的产品体验，当前还缺：

- 知识工作区
- 会话级 source scope
- 来源型回答展示
- 知识源与图谱的更清晰资产层

建议下一步优先做：

1. `knowledge_workspace`
2. Hermes 按 workspace 问答
3. 回答引用 source/chunk 展示
4. 上传文件 -> 选择加入工作区 -> 围绕该工作区持续问答

这样可以最小代价把现有系统升级成更接近 NotebookLM 的知识问答产品。
