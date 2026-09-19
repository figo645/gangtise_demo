#!/usr/bin/env python3
"""Build an evidence-based requirements and defect audit from the live codebase."""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "用户故事盘点_业务技术需求.csv"
AUDIT_DATE = "2026-09-18"
OUTPUT = ROOT / f"用户故事盘点_业务技术需求_审计更新_{AUDIT_DATE}.csv"
BUG_OUTPUT = ROOT / f"Bug修复与质量问题统计_{AUDIT_DATE}.csv"
METHOD_OUTPUT = ROOT / "Codex需求工时与Token审计说明.md"


EVIDENCE = {
    "US001": ("已实现", "templates/tenant_portal.html；src/web/pages.py", "2026-06-07 至 2026-09-18", "门户展示与租户配置已由服务端提供。"),
    "US002": ("已实现", "src/web/api_core.py；templates/admin.html", "2026-06-07 至 2026-09-18", "租户门户配置可在后台维护。"),
    "US003": ("已实现", "src/web/api_core.py；src/domain/core_services.py", "2026-06-07 至 2026-09-18", "门户草稿与发布状态已落库。"),
    "US004": ("已实现", "sql/postgres/131_review_rich_content_html.sql；tests/test_review_rich_content_bdd.py", "2026-09-16", "复盘富文本支持图片粘贴/上传，HTML 独立保留。"),
    "US005": ("已实现", "src/domain/core_services.py；templates/admin.html", "2026-06-07 至 2026-09-18", "模块排序及显隐由配置控制。"),
    "US006": ("已实现", "templates/h5.html；src/web/pages.py", "2026-06-07 至 2026-09-18", "H5 入口和会话跳转已实现。"),
    "US007": ("已实现", "templates/h5.html；src/domain/market_services.py", "2026-07-11 至 2026-09-18", "基本面展示读取市场/宏观/行业数据。"),
    "US008": ("部分实现", "src/domain/market_services.py；tests/test_watchlist_akshare_provider.py", "2026-07-11 至 2026-09-18", "日K与分时具备按需数据链路；免费源可用性仍需运行时监控。"),
    "US009": ("已实现", "src/web/api_core.py: api_add_user_watchlist_item；src/domain/core_services.py", "2026-07-11 至 2026-09-18", "自选股由当前认证用户维度持久化。"),
    "US010": ("部分实现", "src/web/api_core.py；src/domain/workbench_services.py", "2026-07-11 至 2026-09-18", "K线标注与复盘引用链路存在；完整标注运营流程需继续验收。"),
    "US011": ("已实现", "src/web/api_core.py；templates/h5.html", "2026-06-07 至 2026-09-18", "粉丝端可读已发布复盘。"),
    "US012": ("部分实现", "src/web/api_kol.py；src/domain/review_services.py", "2026-08-31 至 2026-09-18", "草稿、AI 优化和审核流已存在；生产流程需持续回归。"),
    "US013": ("部分实现", "src/web/api_kol.py；src/domain/knowledge_graph_services.py", "2026-07-12 至 2026-09-18", "语音作为知识录入类型，转写依赖外部能力。"),
    "US014": ("部分实现", "src/web/api_kol.py: knowledge/file-preview；src/domain/knowledge_graph_services.py", "2026-07-12 至 2026-09-18", "文件预览与入库存在，文件解析范围依赖格式/外部服务。"),
    "US015": ("已实现", "src/web/api_core.py；src/domain/dm_services.py", "2026-05-20 至 2026-09-18", "站内消息与互动记录已实现。"),
    "US016": ("废弃", "需求表确认废弃；当前采用统一消息/互动洞察。", "不适用", "不再按旧工作台处理模型建设。"),
    "US017": ("废弃", "需求表确认废弃；播报改由 daily_finance_broadcast。", "不适用", "不维护旧群发复盘提醒。"),
    "US018": ("已实现", "src/domain/ai_services.py；tests/test_hermes_gangtise_capabilities.py", "2026-07-11 至 2026-09-18", "Hermes 个股分析通过受控工具链执行。"),
    "US019": ("已实现", "src/web/api_core.py；src/domain/ai_services.py", "2026-07-11 至 2026-09-18", "Hermes 对话、会话和回答合成已实现。"),
    "US020": ("废弃", "需求表确认废弃；现行能力使用受治理的功能级模型与工作流。", "不适用", "不开放任意自定义 Skill。"),
    "US021": ("部分实现", "src/web/api_kol.py: /api/kol/knowledge/*；src/domain/knowledge_graph_services.py", "2026-07-12 至 2026-09-18", "知识录入和资产浏览存在，功能开关当前默认收敛。"),
    "US022": ("部分实现", "src/web/api_kol.py；src/domain/knowledge_graph_services.py", "2026-07-12 至 2026-09-18", "可新增/处理知识，细粒度历史编辑仍需验收。"),
    "US023": ("已实现", "src/domain/ai_services.py；src/domain/knowledge_graph_services.py", "2026-07-12 至 2026-09-18", "Hermes 支持知识检索与引用材料。"),
    "US024": ("已实现", "src/web/api_core.py；templates/admin.html", "2026-06-07 至 2026-09-18", "Admin 租户管理存在。"),
    "US025": ("已实现", "src/web/api_core.py；src/domain/core_services.py；tests/test_fan_dav_relationship_regression_bdd.py", "2026-08-13 至 2026-09-18", "单页编辑、角色、所属大V下拉与批量导入已实现。"),
    "US026": ("已实现", "src/runtime.py；src/domain/core_services.py", "2026-07-12 至 2026-09-18", "功能开关驱动菜单与接口边界。"),
    "US027": ("已实现", "src/web/api_core.py；src/domain/core_services.py", "2026-05-20 至 2026-09-18", "访问审计可查看。"),
    "US028": ("已实现", "src/runtime.py：工作流定义；src/domain/ai_services.py", "2026-07-11 至 2026-09-18", "预测/智能体工作流有声明式元数据。"),
    "US029": ("部分实现", "src/domain/market_services.py；templates/h5.html", "2026-07-11 至 2026-09-18", "市场分析结果可展示，预测精度与覆盖面不应视为已验收。"),
    "US030": ("部分实现", "templates/kol_workbench.html；src/domain/workbench_services.py", "2026-07-09 至 2026-09-18", "运营/互动图表已实现，指标口径持续迭代。"),
    "US031": ("已实现", "templates/admin.html；src/domain/core_services.py", "2026-07-09 至 2026-09-18", "智能面板与提示词配置有管理入口。"),
    "US032": ("部分实现", "templates/h5.html；src/web/api_quiz.py；src/domain/quiz_services.py", "2026-09-16 至 2026-09-18", "盲盒活动与互动数据存在，完整社区能力未完成。"),
    "US033": ("部分实现", "src/web/api_kol.py: fan_qr_import；src/runtime.py: fan_qr_import", "2026-09-15 至 2026-09-18", "二维码导入功能受开关治理；当前登录注册已恢复普通填写模式。"),
    "US034": ("已实现", "src/web/pages.py；templates/h5.html；templates/kol_workbench.html；templates/admin.html", "2026-07-12 至 2026-09-18", "多端共用后端租户与角色口径。"),
    "US035": ("部分实现", "src/domain/core_services.py；templates/admin.html", "2026-06-07 至 2026-09-18", "租户品牌/门户配置可维护，视觉资产治理未完全验收。"),
    "US036": ("部分实现", "src/domain/knowledge_graph_services.py；sql/postgres/*knowledge*.sql", "2026-07-12 至 2026-09-18", "PostgreSQL 知识数据层存在，但模块处于收敛开关状态。"),
    "US037": ("部分实现", "src/domain/ai_services.py；src/runtime.py", "2026-07-11 至 2026-09-18", "编排、拦截、工具调用与审计已实现；仍需继续拆分治理。"),
    "US038": ("部分实现", "src/web/api_core.py；src/domain/core_services.py", "2026-08-13 至 2026-09-18", "关键业务状态已后端化；前端仍有少量体验态 LocalStorage。"),
    "US039": ("部分实现", "src/runtime.py；src/domain/core_services.py", "2026-07-12 至 2026-09-18", "功能开关支持限制能力，但没有独立一期只读发布模式验收证据。"),
    "US040": ("未完成", "未找到面向粉丝共性问题的独立汇总任务/页面。", "不适用", "互动洞察不等同于自动共性问题归纳。"),
    "US041": ("未完成", "src/runtime.py 有防截图水印开关；未见盗版追溯闭环。", "2026-08-31", "仅水印相关开关，不足以满足追溯。"),
    "US042": ("未完成", "未找到多平台分发适配器。", "不适用", "未实现。"),
    "US043": ("部分实现", "src/domain/market_services.py；tests/test_gangtise_provider_bdd.py；tests/test_daily_finance_broadcast_bdd.py", "2026-08-18 至 2026-09-18", "Gangtise 接口、积分测试和播报接入已存在；外部返回稳定性需监控。"),
    "US044": ("部分实现", "src/runtime.py；templates/login.html；src/domain/ai_services.py", "2026-08-31 至 2026-09-18", "模型与功能权限有控制，完整合规策略和免责声明统一性仍需验收。"),
    "US045": ("部分实现", "src/domain/market_services.py；templates/h5.html", "2026-08-18 至 2026-09-18", "自选股/指标/主题展示存在，自动研究板块归纳仍有限。"),
    "US046": ("部分实现", "src/domain/workbench_services.py；src/web/api_kol.py", "2026-08-19 至 2026-09-18", "自选股观察和互动分析存在，完整预警触达未完成。"),
    "US047": ("部分实现", "src/domain/market_services.py；templates/h5.html；templates/kol_workbench.html", "2026-09-17 至 2026-09-18", "大V可配置市场4、行业10、宏观6项；尚非通用模板字段引擎。"),
    "US048": ("部分实现", "src/domain/market_services.py；tests/test_watchlist_akshare_provider.py", "2026-08-19 至 2026-09-18", "数据源与K线降级已实现，第三方免费源不稳定性仍存在。"),
    "US049": ("未完成", "未找到独立的自选股板块映射管理页。", "不适用", "展示配置不等于完整主题分组管理。"),
    "US050": ("未完成", "未找到规则配置与触达任务闭环。", "不适用", "未实现。"),
    "US051": ("已实现", "src/domain/core_services.py；sql/postgres/*dashboard*.sql", "2026-07-09 至 2026-09-18", "智能Dashboard草稿/发布配置持久化。"),
    "US052": ("部分实现", "src/domain/review_services.py；src/web/api_kol.py", "2026-08-31 至 2026-09-18", "复盘发布、富文本和图片已实现，内容库治理未完全验收。"),
    "US053": ("废弃", "需求表确认废弃；不维护独立群发模板任务。", "不适用", "由播报/消息能力取代。"),
    "US054": ("部分实现", "src/web/api_core.py；src/domain/workbench_services.py", "2026-08-26 至 2026-09-18", "个股互动接口和分析存在，端到端留言审核需继续验收。"),
    "US055": ("未完成", "未找到复盘评论完整前台流程。", "不适用", "未实现。"),
    "US056": ("部分实现", "src/domain/workbench_services.py；src/web/api_kol.py", "2026-08-26 至 2026-09-18", "部分评论/互动数据处理存在，线程和审核配置未完整验证。"),
    "US057": ("已实现", "src/domain/ai_services.py；src/web/api_kol.py", "2026-08-29 至 2026-09-18", "Hermes 使用统计与模型治理有数据接口。"),
    "US058": ("已实现", "src/runtime.py；src/domain/ai_services.py", "2026-08-29 至 2026-09-18", "Hermes 拦截配置与审计已实现。"),
    "US059": ("已实现", "src/web/api_core.py；src/domain/core_services.py；tests/test_fan_dav_relationship_regression_bdd.py", "2026-09-17", "Admin与大V复用用户管理及批量导入服务。"),
    "US060": ("已实现", "src/web/api_core.py；src/domain/ai_services.py；SSE路由", "2026-08-26 至 2026-09-18", "部分模型任务支持进度/流式反馈。"),
    "US061": ("已实现", "templates/admin.html；templates/kol_workbench.html；src/web/api_core.py", "2026-09-17", "用户编辑与详情合为单页。"),
    "US062": ("已实现", "src/runtime.py；templates/admin.html；templates/h5.html", "2026-07-12 至 2026-09-18", "功能开关联动可见菜单/模块。"),
    "US063": ("已实现", "src/web/api_kol.py；src/domain/knowledge_graph_services.py", "2026-07-12 至 2026-09-18", "知识查询和资产图谱有独立接口。"),
    "US064": ("废弃", "需求表确认废弃。", "不适用", "不再采用粗粒度DM开关。"),
    "US065": ("部分实现", "src/runtime.py；src/web/api_core.py", "2026-08-31 至 2026-09-18", "粉丝/大V互动开关存在，全部互动路径需持续回归。"),
    "US066": ("废弃", "需求表确认废弃。", "不适用", "采用现有消息与洞察能力。"),
    "US067": ("已实现", "src/app_setup.py；src/web/*；src/domain/*", "2026-08-20 至 2026-09-18", "入口、路由与领域服务已拆分。"),
    "US068": ("部分实现", "src/domain/*；src/runtime.py", "2026-08-20 至 2026-09-18", "领域层与外部依赖已有分层，但连接池/供应商适配仍持续优化。"),
    "US069": ("部分实现", "scripts/process_scheduler.py；scripts/process_worker.py；scripts/stop*.sh", "2026-09-02 至 2026-09-16", "独立Worker/Scheduler已引入，进程重复和性能问题仍需持续治理。"),
    "US070": ("未完成", "templates/h5.html、templates/admin.html、templates/kol_workbench.html 仍为大型模板。", "不适用", "尚未完成巨石模板拆分。"),
    "US071": ("已实现", "架构/发布/容量治理脚本及BDD；git 7ec7ecd", "2026-09-02 至 2026-09-16", "已有架构评估、进程生命周期和发布治理工作。"),
    "US072": ("部分实现", "sql/postgres；src/domain/core_services.py", "2026-08-08 至 2026-09-18", "主业务已使用Postgres；仍有兼容/回退代码需清理。"),
    "US073": ("已实现", "src/web/api_core.py；src/domain/ai_services.py", "2026-08-31 至 2026-09-18", "Hermes新建与历史会话已支持。"),
    "US074": ("已实现", "src/web/api_kol.py；src/domain/ai_services.py", "2026-08-29 至 2026-09-18", "记忆统计、备份/清理治理接口存在。"),
    "US075": ("部分实现", "src/web/api_kol.py；src/domain/ai_services.py", "2026-08-29 至 2026-09-18", "使用统计有实现；逐需求Token审计不由应用层保存。"),
    "US076": ("部分实现", "src/runtime.py；templates/kol_workbench.html；templates/admin.html", "2026-09-15 至 2026-09-18", "工作流元数据和任务中心可见，编排可视化仍不完整。"),
    "US077": ("部分实现", "src/web/api_kol.py；src/domain/knowledge_graph_services.py", "2026-07-12 至 2026-09-18", "知识资产和图谱接口存在，功能默认收敛。"),
    "US078": ("部分实现", "src/domain/review_services.py；tests/test_review_rich_content_bdd.py", "2026-08-31 至 2026-09-18", "复盘双层内容/富文本已实现，完整生产编排需继续验收。"),
    "US079": ("部分实现", "src/domain/review_services.py；src/web/api_core.py", "2026-08-26 至 2026-09-18", "K线标注可作为复盘输入，自动归纳质量待持续验证。"),
    "US080": ("部分实现", "templates/h5.html；templates/kol_workbench.html；static/echarts.min.js", "2026-08-08 至 2026-09-18", "核心图表使用ECharts，仍可能保留旧图表实现。"),
    "US081": ("已实现", "src/runtime.py: FEATURE_LLM_BINDINGS；sql/postgres/120_strict_llm_feature_bindings.sql", "2026-09-15", "功能级模型绑定采用严格配置，无默认回退设计。"),
    "US082": ("已实现", "tests/run_full_system_bdd_report.py；发布/路由/承压BDD", "2026-08-12 至 2026-09-18", "API清单、BDD与运行治理基线已存在。"),
    "US083": ("部分实现", "src/domain/market_services.py；sql/postgres/136_market_snapshot_intraday_on_demand.sql；tests/test_market_on_demand_refresh_bdd.py", "2026-08-18 至 2026-09-18", "市场/行业/宏观按租户配置、共享快照与盘中按需刷新已实现；实时性和供应商稳定性需监控。"),
}


BUGS = [
    ("BUG-001", "US083", "行情快照", "盘中市场/行业读取日K，页面展示昨日收盘", "实时市场指标失真", "优先读取日K而非盘中分钟数据", "盘中按需共享刷新，分钟线优先、日K降级", "tests/test_market_on_demand_refresh_bdd.py", "已修复", "2026-09-18", "2026-09-18", "a8f48a9", "需持续验证供应商实时返回"),
    ("BUG-002", "US083", "任务中心", "停止市场同步后状态不能恢复，无法重新启动", "任务卡一直显示执行中", "停止标记和运行记录状态未协调", "补充强制停止与状态恢复控制", "tests/test_market_snapshot_bdd.py", "已修复", "2026-09-17", "2026-09-18", "61c6a31,11634ac", "手工按钮需反馈"),
    ("BUG-003", "US043", "财经播报", "Gangtise HTTP 200 但被判定无正文", "午晚报任务失败且未推送", "仅按预设时段标记/字段取正文，未兼容实际返回结构", "按实际记录匹配与可读内容字段提取", "tests/test_daily_finance_broadcast_bdd.py", "已修复", "2026-09-16", "2026-09-18", "a13254e,61c6a31", "需真实接口回归"),
    ("BUG-004", "US009", "自选股", "添加或删除前端提示失败，但服务端实际成功", "用户重复操作且体验错误", "前端响应解析/刷新时序与200结果不一致", "统一成功响应与刷新处理", "tests/test_fan_dav_relationship_regression_bdd.py", "已修复", "2026-09-15", "2026-09-17", "be4d704", "含空自选股状态"),
    ("BUG-005", "US025", "账户权限", "新粉丝首次登录落入大V工作台", "角色越权式错误入口", "首次会话角色/导航状态未锁定", "运行时角色锁定并做粉丝-大V回归", "tests/test_fan_dav_relationship_regression_bdd.py", "已修复", "2026-09-15", "2026-09-17", "7ec7ecd,be4d704", "需覆盖新注册路径"),
    ("BUG-006", "US032", "H5盲盒", "盲盒在移动端层级/定位错误或不可见", "遮挡或无法触达活动入口", "fixed定位未相对底部导航和安全区计算", "调整相对底部导航的位置并支持拖拽", "H5体验面回归BDD", "已修复", "2026-09-16", "2026-09-18", "a13254e,aac4403", "不同设备需人工验收"),
    ("BUG-007", "US043", "新闻标注", "直接V4检索新闻模式调用失败或结果不可用", "新闻列表无法稳定生成", "模型/端点/外网检索假设不成立", "恢复新闻源采集，避免将检索依赖作为主链路", "新闻/路由BDD", "已修复", "2026-09-15", "2026-09-15", "c2e4c80", "当前不做V4新闻标注展示"),
    ("BUG-008", "US083", "基本面", "Admin/H5市场或行业指标空白、快照不完整", "Top10与市场概览无法显示", "共享快照任务未涵盖租户配置或数据源回退不完整", "增加共享任务、租户指标配置与数据可用提示", "tests/test_market_snapshot_bdd.py", "已修复", "2026-09-17", "2026-09-18", "61c6a31,11634ac", "实时数据仍需外部源监控"),
    ("BUG-009", "US008", "个股详情", "601818光大银行详情没有数据", "个股详情不可用", "证券代码/供应商映射或降级链路缺失", "强化AKShare/Sina供应商和代码标准化", "tests/test_watchlist_akshare_provider.py", "已修复", "2026-09-18", "2026-09-18", "3997b23", "应补真实源用例"),
    ("BUG-010", "US059", "批量用户导入", "模型解析预览报 item is not defined", "无法批量新建账户", "前端变量引用未定义", "修正解析结果变量并增加重复用户名标识", "tests/test_fan_dav_relationship_regression_bdd.py", "已修复", "2026-09-17", "2026-09-17", "be4d704", "大V无需选择所属大V"),
    ("BUG-011", "US004", "复盘富文本", "AI生成后上传图片丢失", "复盘内容失真", "富文本HTML与AI文本覆盖写入", "富文本HTML独立保存并保留图片", "tests/test_review_rich_content_bdd.py", "已修复", "2026-09-16", "2026-09-16", "7ec7ecd", "已迁移富文本字段"),
]


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()


def write_requirements() -> None:
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as source_file:
        rows = list(csv.DictReader(source_file))
        source_fields = list(rows[0].keys())

    audit_fields = [
        "代码实现状态", "实现证据（代码/BDD/迁移）", "实现活动时间范围（Git）", "审计结论",
        "Codex Token 输入（会话估算）", "Codex Token 输出（会话估算）", "Codex Token 总计（会话估算）", "Token 数据质量",
        "Codex 会话归因开始时间", "Codex 会话归因结束时间", "Codex 累计会话运行时长（小时）", "会话归因人天（8小时）", "工时数据质量",
        "关联Bug数", "关联Bug编号", "最后审计时间", "审计基线提交",
    ]
    bug_by_requirement: dict[str, list[str]] = {}
    for bug in BUGS:
        bug_by_requirement.setdefault(bug[1], []).append(bug[0])

    for row in rows:
        requirement_id = row["需求ID"]
        status, evidence, period, conclusion = EVIDENCE.get(
            requirement_id,
            ("待审计", "未建立当前代码证据映射。", "不可审计", "需要补充代码和测试证据。"),
        )
        bugs = bug_by_requirement.get(requirement_id, [])
        row.update({
            "代码实现状态": status,
            "实现证据（代码/BDD/迁移）": evidence,
            "实现活动时间范围（Git）": period,
            "审计结论": conclusion,
            "Codex Token 输入（会话估算）": "0",
            "Codex Token 输出（会话估算）": "0",
            "Codex Token 总计（会话估算）": "0",
            "Token 数据质量": "待会话归因；不是供应商账单Token。",
            "Codex 会话归因开始时间": "",
            "Codex 会话归因结束时间": "",
            "Codex 累计会话运行时长（小时）": "0",
            "会话归因人天（8小时）": "0",
            "工时数据质量": "待会话归因；Git提交范围不等同于连续Codex人时。",
            "关联Bug数": str(len(bugs)),
            "关联Bug编号": ",".join(bugs) if bugs else "",
            "最后审计时间": AUDIT_DATE,
            "审计基线提交": git_head(),
        })

    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=source_fields + audit_fields)
        writer.writeheader()
        writer.writerows(rows)


def write_bugs() -> None:
    fields = [
        "BugID", "关联需求ID", "业务域", "问题标题", "现象/影响", "根因", "修复方案",
        "验证用例或BDD", "状态", "首次发现时间", "修复完成时间", "关联提交", "备注",
    ]
    with BUG_OUTPUT.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(fields)
        writer.writerows(BUGS)


def write_methodology() -> None:
    METHOD_OUTPUT.write_text(
        f"# Codex 需求工时与 Token 审计说明\n\n"
        f"审计日期：{AUDIT_DATE}  \n"
        f"代码基线：`{git_head()}`\n\n"
        "## 结论\n\n"
        "- 本次更新以当前代码、迁移、路由、BDD 文件和 Git 提交为实现证据；原需求表中的旧实现说明不作为当前事实。\n"
        "- 本机 Codex 线程历史未保存供应商真实 input/output token usage；原始 Token 字段保留为“不可审计”。\n"
        "- 另有一组“会话归因”字段：使用本地可见 userMessage/agentMessage 文本的离线 Token 估算，并按用户请求关键词关联需求；一轮命中多个需求时均分，不能视为供应商账单。\n"
        "- 会话归因的运行时长来自用户请求到可见助手回复的时间差，按命中需求均分，再以 `累计小时 / 8` 计算人天；它不是连续人工工时。\n"
        "- 无法命中具体需求的轮次保留在归因明细中的 `UNCLASSIFIED`，不强行分配。\n\n"
        "## 产物\n\n"
        f"- `{OUTPUT.name}`：83 项需求的当前实现证据、状态和审计字段。\n"
        f"- `{BUG_OUTPUT.name}`：11 项从真实问题记录整理出的缺陷台账。\n\n"
        "- `Codex需求Token工时归因汇总_2026-09-18.csv`：按需求的可见会话 Token 和估算工时汇总。\n"
        "- `Codex需求Token工时归因明细_2026-09-18.csv`：每轮请求的需求命中与分配明细。\n\n"
        "## 后续可审计化建议\n\n"
        "1. 在每次需求开始时记录需求ID、Codex thread/turn ID 和开始时间。\n"
        "2. 将模型 API 返回的 usage（prompt/completion/total tokens）写入独立的不可变审计表，并关联需求ID。\n"
        "3. 仅基于同一需求ID下的已关闭工作段累计时长；空闲等待与并行任务分别记录，禁止从 Git 提交跨度推算。\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    write_requirements()
    write_bugs()
    write_methodology()
    print(f"wrote {OUTPUT.name}")
    print(f"wrote {BUG_OUTPUT.name}")
    print(f"wrote {METHOD_OUTPUT.name}")
