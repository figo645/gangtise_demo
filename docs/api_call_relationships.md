# API 调用关系图

本文描述当前程序的主要 API 调用关系。页面端通过 HTTP 调用 Flask API，API 层负责认证、租户隔离和参数校验，领域服务层负责业务编排，数据访问统一落到 PostgreSQL 或外部数据服务。

## 1. 系统总览

```mermaid
flowchart TB
    Browser[浏览器 / H5 / Admin / 大V工作台]
    Pages[页面路由\n/pages.py]
    CoreAPI[核心 API\napi_core.py]
    ExperienceAPI[用户体验 API\napi_experience.py]
    KolAPI[大V与复盘 API\napi_kol.py]
    DomainCore[核心领域服务\ncore_services.py]
    DomainMarket[行情与指标服务\nmarket_services.py]
    DomainAI[AI、Hermes 与复盘服务\nai_services.py]
    DomainWorkbench[工作台服务\nworkbench_services.py]
    DomainKnowledge[知识图谱与知识库服务\nknowledge_graph_services.py]
    DomainRelease[数据库发布服务\ndatabase_release_services.py]
    AsyncWorker[用户异步任务 Worker\nuser_async_jobs]
    TaskCenter[管理定时任务中心\nadmin task center]
    PostgreSQL[(PostgreSQL\n业务数据 / 配置 / 日志 / 任务)]
    AKShare[AKShare\n市场与行业数据]
    Gangtise[Gangtise OpenAPI\n个股研究 / Agent SSE]
    LLM[通用大模型\nOpenAI-compatible]
    News[新闻源 / RSS]

    Browser --> Pages
    Browser --> CoreAPI
    Browser --> ExperienceAPI
    Browser --> KolAPI
    Pages --> DomainCore
    CoreAPI --> DomainCore
    CoreAPI --> DomainMarket
    CoreAPI --> DomainAI
    ExperienceAPI --> DomainCore
    ExperienceAPI --> DomainAI
    KolAPI --> DomainCore
    KolAPI --> DomainMarket
    KolAPI --> DomainAI
    KolAPI --> DomainWorkbench
    KolAPI --> DomainKnowledge
    CoreAPI --> DomainRelease
    DomainCore --> PostgreSQL
    DomainMarket --> PostgreSQL
    DomainAI --> PostgreSQL
    DomainWorkbench --> PostgreSQL
    DomainKnowledge --> PostgreSQL
    DomainRelease --> PostgreSQL
    DomainMarket --> AKShare
    DomainMarket --> Gangtise
    DomainMarket --> News
    DomainAI --> Gangtise
    DomainAI --> LLM
    AsyncWorker --> DomainCore
    AsyncWorker --> DomainAI
    AsyncWorker --> PostgreSQL
    TaskCenter --> DomainCore
    TaskCenter --> DomainMarket
    TaskCenter --> PostgreSQL
```

## 2. 页面到 API 分区

```mermaid
flowchart LR
    H5[H5 页面\n/h5] --> H5API[用户、行情、复盘、Hermes、私信 API]
    Admin[Admin 页面\n/admin] --> AdminAPI[分析、用户、任务、指标、配置、发布 API]
    KOL[大V工作台\n/kol-workbench] --> KOLAPI[工作台、知识、智能看板、粉丝管理 API]
    Login[登录页\n/login / login.html] --> AuthAPI[认证、注册、账号设置 API]

    H5API --> Core[/api/core\n行情 / 自选股 / 标注 / 评论]
    H5API --> Experience[/api/experience\nHermes / 社区 / 私信 / AI]
    H5API --> Review[/api/review\n复盘提交 / 查询 / 取消]
    AdminAPI --> Analytics[/api/admin/analytics\n漏斗 / 渠道 / 大V / 营收 / 分层 / 积分]
    AdminAPI --> Governance[/api/admin/governance\n任务 / 配置 / 指标 / 用户 / 发布]
    KOLAPI --> Workbench[/api/kol/workbench\n大V业务数据与能力增长]
    KOLAPI --> Knowledge[/api/kol/knowledge\n知识输入 / 查询 / 图谱]
    KOLAPI --> Smart[智能看板 / 指标定义 / 粉丝观察]
    AuthAPI --> Session[会话与权限]

    Core --> Analytics
    Experience --> Review
    Review --> Async[异步任务状态 API\n/api/jobs/<job_code>]
    Governance --> Async
```

## 3. API 路由清单与领域归属

```mermaid
flowchart TB
    subgraph Core[api_core.py]
        C1[市场与行情\n/api/market\n/api/market-overview\n/api/market-sectors\n/api/market-snapshot/refresh]
        C2[自选股\n/api/watchlist\n/api/watchlist/items\n/api/watchlist/search\n/api/watchlist/<stock_code>]
        C3[评论与标注\n/api/watchlist/<stock_code>/comments\n/api/watchlist/<stock_code>/annotations\n/api/tenant/<tenant>/watchlist-comment-analytics]
        C4[复盘与异步任务\n/api/review/voice-transcribe\n/api/review/prepare-preview\n/api/review/publish-embed\n/api/jobs/<job_code>]
        C5[Admin 数据与治理\n/api/admin/funnel-analytics\n/api/admin/channels\n/api/admin/revenue-analytics\n/api/admin/kol-analytics\n/api/admin/user-segments\n/api/admin/points]
        C6[Admin 任务与指标\n/api/admin/tasks\n/api/admin/task-runs\n/api/admin/indicator-*\n/api/admin/token-usage]
        C7[认证与账号\n/api/h5/auth-options\n/api/h5/login/password\n/api/h5/register/password\n/api/h5/account-settings]
        C8[用户管理与配置\n/api/admin/users\n/api/kol/users\n/api/admin/site-config\n/api/admin/simulation-data-policy]
    end

    subgraph Experience[api_experience.py]
        E1[Hermes\n/api/hermes/modes\n/api/hermes/query\n/api/hermes/sessions\n/api/hermes/usage/current]
        E2[社区与积分\n/api/community/*\n/api/user/profile\n/api/user/points-rules]
        E3[私信与 AI\n/api/dm/*\n/api/ai-analysis\n/api/ai/allocation\n/api/ai/forecast]
    end

    subgraph KOL[api_kol.py]
        K1[工作台与门户\n/api/kol/workbench\n/api/kol/portal-cms]
        K2[知识与图谱\n/api/kol/knowledge/*\n/api/admin/knowledge-*\n/api/evidence-chain/query]
        K3[复盘任务\n/api/review/jobs\n/api/review/generate-draft\n/api/review/compose-draft\n/api/review/jobs/<job>/cancel]
        K4[智能看板与粉丝观察\n/api/tenant/<tenant>/dashboard\n/api/tenant/<tenant>/smart-indicators\n/api/tenant/<tenant>/fan-stock-observation]
        K5[大V管理\n/api/kol/users\n/api/kol/business-analytics\n/api/kol/broadcast\n/api/kol/reply]
    end

    C1 --> Market[market_services.py]
    C2 --> Market
    C3 --> Market
    C4 --> ReviewSvc[ai_services.py + core_services.py]
    C5 --> CoreSvc[core_services.py]
    C6 --> CoreSvc
    C7 --> CoreSvc
    C8 --> CoreSvc
    E1 --> HermesSvc[ai_services.py]
    E2 --> CoreSvc
    E3 --> AISvc[ai_services.py]
    K1 --> WorkbenchSvc[workbench_services.py]
    K2 --> KnowledgeSvc[knowledge_graph_services.py + ai_services.py]
    K3 --> ReviewSvc
    K4 --> WorkbenchSvc
    K5 --> CoreSvc
```

## 4. 复盘两阶段调用链

```mermaid
sequenceDiagram
    participant U as 大V H5
    participant API as api_kol.py
    participant DB as PostgreSQL
    participant W as user_async_jobs Worker
    participant AI as ai_services.py
    participant LLM as 通用大模型
    participant H as api_core.py

    U->>API: POST /api/review/generate-draft
    API->>DB: INSERT user_async_jobs(status=pending)
    API-->>U: job_code + queued
    U->>H: GET /api/jobs/<job_code>
    W->>DB: claim pending job
    W->>AI: generate_review_draft_with_llm()
    AI->>DB: progress: llm_preparing
    AI->>LLM: call_openai_compatible_llm()
    LLM-->>AI: Draft 文本
    AI->>DB: progress: llm_postprocessing
    W->>DB: status=success + result_json
    H-->>U: Draft 结果

    U->>API: POST /api/review/prepare-preview
    API->>DB: INSERT user_async_jobs(status=pending)
    API-->>U: job_code + queued
    U->>H: GET /api/jobs/<job_code>
    W->>AI: compose_review_structured_preview()
    AI->>AI: 读取自选股、标注、评论与行业聚合
    AI->>LLM: 生成结构化预览摘要
    W->>DB: status=success + preview result
    H-->>U: 自选股分析预览
```

## 5. 复盘任务取消链路

```mermaid
sequenceDiagram
    participant U as 大V H5
    participant API as /api/review/jobs/<job>/cancel
    participant DB as user_async_jobs
    participant W as Worker
    participant LLM as 模型请求

    U->>API: POST cancel
    API->>DB: 校验租户、身份、任务类型
    API->>DB: status=cancelled, finished_at=now
    API-->>U: 已停止，原始输入保留
    alt 任务仍在队列
        W->>DB: claim 时发现 cancelled
        W-->>W: 不执行
    else 模型请求已发出
        LLM-->>W: 晚到返回
        W->>DB: 检查 cancelled
        W-->>W: 丢弃结果，不回写 success/failed
    end
```

## 6. 行情、行业与指标数据链路

```mermaid
flowchart LR
    Scheduler[admin task center\nmarket_snapshot_sync\n每 5 分钟]
    Manual[Admin 手动执行\n/api/admin/tasks/<task>/run]
    MarketAPI[/api/market-overview\n/api/market-sectors]
    WatchAPI[/api/watchlist/<stock_code>]
    MarketSvc[market_services.py]
    Cache[(PostgreSQL\nmarket snapshots / indicator lake)]
    AK[AKShare]
    H5[H5 / Admin / 大V工作台]

    Scheduler --> MarketSvc
    Manual --> MarketSvc
    MarketSvc --> AK
    AK --> MarketSvc
    MarketSvc --> Cache
    H5 --> MarketAPI
    H5 --> WatchAPI
    MarketAPI --> MarketSvc
    WatchAPI --> MarketSvc
    MarketSvc --> Cache
```

## 7. Hermes 调用链

```mermaid
sequenceDiagram
    participant U as H5 / 大V工作台
    participant API as api_experience.py
    participant Core as core_services.py
    participant AI as ai_services.py
    participant Tools as Hermes 工具注册表
    participant Data as 本地数据服务
    participant G as Gangtise Agent SSE
    participant LLM as 通用大模型
    participant DB as PostgreSQL

    U->>API: POST /api/hermes/query
    API->>Core: 认证、租户范围、能力检查
    Core->>AI: Hermes 路由与上下文编排
    AI->>DB: 读取会话、用户记忆、画像
    AI->>Tools: 根据意图选择受控工具
    alt 行情 / 自选股 / 指标
        Tools->>Data: 读取本地缓存与指标湖
        Data-->>Tools: 结构化数据
    else 当日个股或市场研究
        Tools->>G: /application/open-ai/ai/chat/sse
        G-->>Tools: SSE 研究结果
    else 知识、解释或产品问题
        Tools->>LLM: 本地上下文 + 用户问题
        LLM-->>Tools: 生成回答
    end
    Tools-->>AI: 工具结果
    AI->>LLM: 需要综合时进行答案合成
    AI->>DB: 保存会话、用量与记忆元数据
    AI-->>API: answer + mode + tool trace
    API-->>U: JSON / 流式结果
```

## 8. 管理后台治理链路

```mermaid
flowchart TB
    Admin[Admin 页面]
    Config[配置 API\n/api/admin/site-config\n/api/admin/gangtise-credentials]
    Tasks[任务 API\n/api/admin/tasks\n/api/admin/task-runs]
    Indicators[指标 API\n/api/admin/indicator-*]
    Users[用户 API\n/api/admin/users\n/api/kol/users]
    Release[发布 API\n/api/admin/database-release/*]
    Metrics[分析 API\n/api/admin/funnel-analytics\n/api/admin/channels\n/api/admin/revenue-analytics\n/api/admin/kol-analytics\n/api/admin/user-segments\n/api/admin/points]
    Core[core_services.py]
    Market[market_services.py]
    ReleaseSvc[database_release_services.py]
    DB[(PostgreSQL)]

    Admin --> Config
    Admin --> Tasks
    Admin --> Indicators
    Admin --> Users
    Admin --> Release
    Admin --> Metrics
    Config --> Core
    Tasks --> Core
    Tasks --> Market
    Indicators --> Market
    Users --> Core
    Release --> ReleaseSvc
    Metrics --> Core
    Core --> DB
    Market --> DB
    ReleaseSvc --> DB
```

## 9. 关键设计约束

- 所有 API 先经过登录会话、角色能力和租户范围校验，再进入领域服务。
- `user_async_jobs` 是复盘、语音、知识等用户异步任务的统一状态源；页面通过 `/api/jobs/<job_code>` 查询进度。
- `is_simulated` 只用于本机模拟数据的生产可见性隔离，不应阻止用户异步任务被 worker 领取。
- 市场一览和行业板块数据统一由 `market_snapshot_sync` 写入 PostgreSQL，展示 API 只读取缓存，不应在页面请求中重复扣费拉取。
- Gangtise 仅用于明确声明的个股研究、Agent SSE 等能力；本地指标、行业和市场快照走本地数据服务。
- 发布、删除、取消类写操作必须使用 POST/DELETE，并在服务端再次校验租户、身份和目标对象，不能只依赖前端隐藏按钮。

