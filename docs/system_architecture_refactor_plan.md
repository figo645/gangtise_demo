# 系统架构评估与重构方案

## 1. 结论

当前系统已经从单一 `app.py` 迈出了一步，但整体仍然属于：

- 单体 Flask 应用
- 全局服务聚合
- 进程内后台线程
- 大型模板直出
- 同步数据库访问

从通用性、可扩展性、承压能力看，当前更适合原型验证和中低强度业务运行，不适合直接作为高并发、强稳定性要求的生产架构长期演进。

综合判断：

- 通用性：5/10
- 可扩展性：4/10
- 运维可用性：3/10
- 当前承压能力：3/10


## 2. 当前架构现状

### 2.1 入口与运行方式

- `app.py` 已经变成薄入口，但仍直接使用 Flask 内建运行方式。
- 启动阶段会自动执行数据库初始化、默认数据补充、后台任务线程启动。

关键文件：

- [app.py](/Users/xuchenfei/PycharmProjects/gangtise_demo/app.py)
- [src/app_setup.py](/Users/xuchenfei/PycharmProjects/gangtise_demo/src/app_setup.py)
- [src/domain/core_services.py](/Users/xuchenfei/PycharmProjects/gangtise_demo/src/domain/core_services.py)

### 2.2 当前分层情况

当前代码目录已经拆出 `src/web`、`src/domain`，但底层仍然高度耦合：

- `src/runtime.py` 承担了 app、配置、第三方依赖、全局变量、运行时状态
- `src/services.py` 使用 `import *` 聚合多个领域模块
- `web -> services -> domain -> runtime` 之间耦合偏重

这意味着目录结构看似分层，但依赖方向并不干净。

### 2.3 当前大文件情况

后端核心大文件：

- `src/domain/ai_services.py`：7821 行
- `src/domain/core_services.py`：6047 行
- `src/domain/market_services.py`：3597 行
- `src/domain/workbench_services.py`：914 行
- `src/web/api_core.py`：1259 行

前端模板大文件：

- `templates/h5.html`：13550 行
- `templates/kol_workbench.html`：11222 行
- `templates/admin.html`：9681 行

这类文件体量已经明显超出可长期维护的舒适区。


## 3. 核心问题评估

## 3.1 Web 进程内直接跑后台线程

当前存在两类典型后台循环：

- 管理任务中心轮询
- 用户异步任务轮询

相关实现位于：

- [src/domain/core_services.py](/Users/xuchenfei/PycharmProjects/gangtise_demo/src/domain/core_services.py)

典型问题：

- 一旦切换到 `gunicorn` 多 worker，每个 worker 都可能启动一套后台线程
- 多实例部署时会重复调度、重复消费
- 后台任务生命周期依附于 Web 进程，不利于故障恢复
- 无法独立扩展异步能力

这是当前架构最优先要处理的问题。

## 3.2 数据库连接方式不适合高并发

当前数据库访问主要通过 `psycopg2.connect(...)` 直接建立连接：

- 无统一连接池
- 无统一事务边界
- 无 Repository 抽象
- 无读写分离预留点
- 无统一超时、重试、慢查询治理

这会导致：

- 高并发时连接建立成本高
- 连接耗尽风险高
- 数据访问逻辑散落
- 性能问题难定位

## 3.3 服务边界仍不清晰

虽然文件从单一 `app.py` 拆出，但核心业务仍存在以下问题：

- 路由层知道过多业务细节
- 领域服务混合编排逻辑和底层访问逻辑
- 外部依赖调用没有单独基础设施层
- 共享函数通过 `import *` 重新聚合，边界继续变模糊

直接后果是：

- 新功能接入成本高
- 老功能改动容易牵一发而动全身
- 单测难写
- 回归风险高

## 3.4 前端模板仍是巨石结构

H5、Workbench、Admin 都是超大 HTML 模板，通常包含：

- 页面结构
- 大量内联脚本
- 大量内联样式
- 跨模块 UI 状态处理

问题包括：

- 组件复用困难
- 单点改动回归范围大
- 多人并行开发冲突高
- 页面性能和可维护性差

## 3.5 缺乏可靠的容量评估基础

现有测试主要是：

- 路由烟测
- BDD 片段测试
- 少量默认数据测试

当前缺少：

- 并发压测
- 数据库性能压测
- 队列积压验证
- LLM 超时和降级验证
- 任务重复执行验证
- 页面资源性能分析

因此目前不能严肃给出“最大承载量”结论，只能做工程估算。


## 4. 当前承压能力估算

以下为工程估算，不是压测实测结果。

### 4.1 在当前架构下的保守判断

如果保持当前模式：

- 单机部署
- Python 与 Postgres 同机
- Hermes / 复盘 / 知识图谱 / 智能指标功能同时存在

则可大致判断为：

- 轻量页面浏览和普通 CRUD：几十个并发活跃用户
- 带 Hermes / 复盘生成 / 知识检索的重路径：5 到 20 个并发重任务
- 轻使用场景下：几百 DAU 可运行
- 中高强度研究生产场景：容易出现抖动与积压

### 4.2 当前瓶颈来源

- Web、调度、异步任务共处一个进程体系
- Flask 请求链路是同步的
- 数据库无池化
- 外部 LLM 和行情接口延迟直接进入主链路
- 大模板和大脚本增加页面端负担
- 缺少缓存、限流、熔断和异步隔离


## 5. 重构目标

重构目标不是推倒重来，而是逐步迁移到适合产品持续增长的架构。

目标如下：

- Web 服务只负责请求接入、鉴权、参数校验和响应组装
- 业务编排下沉到应用层
- 业务规则收敛到领域层
- 数据库、LLM、向量检索、行情、文件解析下沉到基础设施层
- 后台任务从 Web 进程剥离为独立 Worker
- 前端从巨石模板逐步拆为模块化页面资源
- 增加性能、容量、错误率、队列积压等基础观测能力


## 6. 目标架构建议

建议目标架构：

- Web API Service
- Worker Service
- Scheduler Service
- Postgres 主数据库
- pgvector 向量能力
- Redis 缓存与限流层
- Nginx / Gunicorn 生产运行层

说明：

- 现阶段 pgvector 继续和 Postgres 放在一起是合理的
- 不必一开始引入过重的微服务体系
- 重点是先把“执行面”拆开，而不是先把“部署单元”拆到很细


## 7. 建议目录结构

建议重构后的目录：

```text
src/
  app/
    factory.py
    config.py
    middleware/
  modules/
    hermes/
      api.py
      service.py
      workflow.py
      repository.py
      schemas.py
    review/
      api.py
      service.py
      workflow.py
      repository.py
    dashboard/
      api.py
      service.py
      repository.py
    knowledge/
      api.py
      service.py
      graph_service.py
      repository.py
    admin/
      api.py
      service.py
      repository.py
    user/
      api.py
      service.py
      repository.py
  infra/
    db/
      pool.py
      uow.py
      repositories/
    llm/
      client.py
      registry.py
    market/
      quote_client.py
      index_client.py
    vector/
      embedding_client.py
      search_repository.py
    cache/
      redis_client.py
    files/
      parser.py
      ocr.py
      audio.py
  worker/
    main.py
    scheduler.py
    jobs/
```


## 8. 分阶段重构方案

## 8.1 第一阶段：稳定运行面

目标：

- 从开发态切到可生产运行的最小形态

动作：

- 引入 app factory
- 区分 `dev / prod` 配置
- `app.py` 只保留入口组装
- 启动脚本改为 `gunicorn`
- 去除依赖 Flask reloader 的启动逻辑

阶段产出：

- 应用可通过 `gunicorn` 稳定运行
- 启动行为更可控
- 后续拆 Worker 不会受 Web 进程启动方式影响

## 8.2 第二阶段：拆出 Worker 与 Scheduler

目标：

- 不再由 Web 进程直接轮询后台任务

动作：

- 将 `user_async_jobs` 消费迁移到独立 Worker
- 将 admin task center 迁移到独立 Scheduler 或 Worker 内定时任务模块
- 保留数据库任务表，先不强行引入重型任务框架
- 如果后续任务继续增多，再考虑 Celery / Dramatiq / RQ

阶段产出：

- Web 进程只处理前台请求
- 异步任务可单独扩容
- 多实例部署不再重复执行任务

## 8.3 第三阶段：数据库访问层下沉

目标：

- 建立统一数据库访问规范

动作：

- 建立连接池
- 建立 Repository
- 建立 Unit of Work
- 统一事务提交与回滚边界
- 将 SQL 调用从业务函数中逐步剥离

优先拆分的仓储：

- 用户与租户
- Hermes memory / profile
- review jobs
- knowledge / embeddings
- dashboard / indicators
- admin settings

阶段产出：

- 数据访问可观测、可测试
- 更容易做性能治理和故障恢复

## 8.4 第四阶段：按业务域重构服务层

目标：

- 让服务边界真正清晰

优先业务域：

- Hermes
- Review
- Dashboard / Indicators
- Knowledge / Graph
- Admin / Config

每个域内部建议分：

- API 层
- Application Service
- Domain Service
- Repository

阶段产出：

- 新功能能在单域内闭环开发
- 影响面缩小
- 更适合持续迭代

## 8.5 第五阶段：前端模板去巨石化

目标：

- 提高前端维护性和复用性

动作：

- 将 H5 / Workbench / Admin 拆成页面壳 + partials
- JS 按功能模块独立文件化
- CSS 按页面与组件拆分
- 图谱、Hermes、复盘、Dashboard 等高复杂区单独模块化

说明：

- 当前阶段不一定需要立即上完整 SPA
- 但必须结束一个模板上万行的方式

阶段产出：

- 前端回归面变小
- 更利于 UI 持续重构
- 更容易做按模块加载与性能优化

## 8.6 第六阶段：补齐观测与容量治理

目标：

- 建立可量化的稳定性和容量基线

必须补齐：

- 请求耗时
- 错误率
- DB 慢查询
- Worker 队列深度
- 任务处理时延
- LLM 调用耗时与失败率
- 每租户算力消耗
- 页面资源体积与首屏性能

同时补：

- 压测脚本
- 基线吞吐报告
- SLO / SLA 指标
- 限流与熔断策略


## 9. 推荐的优先级排序

如果只按投入产出比排序，建议顺序如下：

1. 剥离 Web 进程内后台线程
2. 引入数据库连接池与 Repository
3. 真正按业务域拆 Hermes / Review / Knowledge / Dashboard
4. 拆前端巨石模板
5. 增加缓存、限流、观测和压测体系

这是最务实的路线。


## 10. 重构后的承载预期

以下仍为工程估算。

### 10.1 单机增强版

条件：

- Web / Worker 分离
- DB 连接池
- Redis 缓存
- Gunicorn 运行

预期：

- 轻交互并发可提升到 100 到 300
- 重 AI 任务并发可提升到 20 到 50

### 10.2 小规模多实例版

条件：

- 2 台 Web
- 1 台 Worker
- 独立 Postgres

预期：

- 轻交互并发可到 500+
- 重任务吞吐按 Worker 水平扩容

### 10.3 后续进一步演进方向

当 Hermes、知识图谱、智能指标生成继续变重时，再考虑：

- 向量检索独立服务化
- 行情采集独立服务化
- SSE / WebSocket 流式响应
- 多级缓存
- 模型调用统一网关


## 11. 结合当前仓库的直接实施建议

结合当前代码状态，建议先做四件事：

1. 将任务中心和用户异步任务从 Web 进程中移出
2. 建立 DB 连接池和 Repository 层
3. 将 Hermes / Review / Knowledge / Dashboard 四大域真正拆开
4. 将 `h5.html`、`kol_workbench.html`、`admin.html` 拆成模块化资源

这四步完成后，系统的通用性、扩展性和承压能力都会有实质改善。


## 12. 下一步建议

建议下一步直接产出一份“实施级拆分清单”，内容包括：

- 每一阶段改哪些文件
- 每个模块如何迁移
- 哪些函数先迁
- 哪些接口先保兼容
- 如何做灰度切换
- 如何验证功能不回归

如果需要，可以在本文件基础上继续补一版：

- 《系统架构重构实施清单》
- 《模块迁移顺序与风险回退方案》
- 《容量压测与监控建设方案》
