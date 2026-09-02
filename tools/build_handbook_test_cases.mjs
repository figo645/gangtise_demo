import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "/Users/xuchenfei/PycharmProjects/gangtise_demo/static/downloads";
const outputPath = `${outputDir}/gangtise_role_test_cases.xlsx`;

const headers = ["用例ID", "角色", "模块", "场景", "前置条件", "操作步骤", "预期结果", "优先级", "测试类型", "状态", "备注"];
const cases = [
  ["INV-AUTH-001", "普通用户", "账户与合规", "新用户账号注册", "未登录；用户名未被占用", "打开注册；填写昵称、用户名、密码；提交", "创建投资者账户并进入合规确认，不创建跨租户关系", "P0", "功能", "待执行", "覆盖字段校验、重复用户名、密码长度"],
  ["INV-AUTH-002", "普通用户", "账户与合规", "合规确认与渠道登记", "完成注册或首次登录", "阅读权益与合规内容；勾选确认；选择渠道并提交", "确认状态和渠道写入用户资料，Admin 渠道分析可见", "P0", "功能", "待执行", "渠道选项必须与 Admin 一致"],
  ["INV-AUTH-003", "普通用户", "账户与合规", "账号密码登录与退出", "已有 active 投资者账号", "使用正确密码登录；退出；再次登录", "登录状态持久化；退出后受限页重定向登录；再次登录恢复自身资料", "P0", "回归", "待执行", "检查最近账号与保存密码策略"],
  ["INV-AUTH-004", "普通用户", "账户与合规", "无效密码和停用账号", "准备错误密码或停用账号", "尝试登录", "显示明确错误，不建立会话，不泄露账号信息", "P1", "异常", "待执行", ""],
  ["INV-MKT-001", "普通用户", "市场行情", "首页核心指数与市场摘要", "已登录；Gangtise 数据可用", "进入 H5 首页；刷新市场模块", "展示来源、更新时间与真实数据；缺失时显示不可用说明", "P0", "功能", "待执行", "禁止模拟行情"],
  ["INV-WL-001", "普通用户", "自选股", "按股票代码搜索", "已登录", "输入 601988；选择搜索候选项", "返回中国银行等正确候选；进入详情使用匹配的证券代码", "P0", "功能", "待执行", "覆盖名称、代码、无匹配"],
  ["INV-WL-002", "普通用户", "自选股", "查看个股详情与日K线", "已有可查询证券", "进入详情；查看价格、K线和区间指标", "价格、日期和来源可追溯；ECharts 可悬浮、缩放；容器不空白或溢出", "P0", "回归", "待执行", "高风险：真实行情与图表渲染"],
  ["INV-WL-003", "普通用户", "自选股", "新增和移除自选", "已登录；有可查询证券", "添加自选；刷新；移除自选", "列表与详情状态一致，仅影响当前用户/租户允许范围", "P1", "功能", "待执行", ""],
  ["INV-WL-004", "普通用户", "K线标注", "保存、编辑和删除K线标注", "已进入个股详情", "创建标注；刷新；编辑或删除", "标注持久化且仅本租户可见；复盘归纳可读取有效标注", "P0", "功能", "待执行", ""],
  ["INV-COM-001", "普通用户", "评论互动", "发表评论并即时看到结果", "评论互动开关开启；已进入详情", "输入评论；提交；刷新页面", "评论立即显示；保存不依赖大模型；标签和行业统计更新", "P0", "回归", "待执行", "覆盖保存失败与空评论"],
  ["INV-COM-002", "普通用户", "评论互动", "互动开关关闭", "Admin 关闭评论互动", "尝试从页面与 API 发评论", "页面受限且接口拒绝；已有评论仍按权限展示", "P0", "权限", "待执行", ""],
  ["INV-REV-001", "普通用户", "复盘阅读", "阅读新发布复盘", "大V已发布复盘", "进入复盘列表；打开详情", "最新发布内容立即出现；主题和摘要来源正确；无自选股时不显示虚构自选归纳", "P0", "回归", "待执行", ""],
  ["INV-KNO-001", "普通用户", "知识专区", "查看租户知识结构", "所属租户已有知识", "进入知识专区；切换分层 Tab；打开词条", "展示可读百科与词条摘要，不显示 Admin QKV 治理字段", "P1", "功能", "待执行", ""],
  ["INV-DM-001", "普通用户", "消息", "区分大V对话和系统消息", "所属租户存在两类消息", "进入消息列表；切换消息类型；打开会话", "标题、提示和会话内容匹配普通用户视角", "P1", "体验", "待执行", ""],
  ["INV-HER-001", "普通用户", "Hermes", "访问开关关闭时的限制", "Admin 关闭 investor_access_enabled", "尝试进入 Hermes 与直接调用 API", "前台入口不可用，接口执行受限并返回可解释结果", "P0", "权限", "待执行", ""],
  ["INV-HER-002", "普通用户", "Hermes", "指数K线图请求", "普通用户 Hermes 开启；市场数据可用", "提问：展示最近3个月上证指数的K线图并解读", "路由到指数K线和分析；图表可见、可交互，文字不替代图表", "P0", "回归", "待执行", ""],
  ["INV-HER-003", "普通用户", "Hermes", "线性图请求", "普通用户 Hermes 开启；市场数据可用", "提问：展示最近3个月上证指数的历史数据线图", "输出线性趋势图而非K线；Tooltip和缩放可用", "P0", "回归", "待执行", ""],
  ["DAV-AUTH-001", "研究型大V", "入口与权限", "登录后选择 H5 或工作台", "已有 active dav 账号", "登录；进入入口选择；分别打开 H5 和工作台", "大V可使用两个租户内入口，不能访问 /admin", "P0", "权限", "待执行", ""],
  ["DAV-REV-001", "研究型大V", "复盘生产", "只用用户输入生成并发布", "登录大V；无须选择自选股", "输入主题和用户内容；生成 Draft；编辑确认；发布", "自选股为可选项；发布时生成摘要；前台立即可见", "P0", "功能", "待执行", ""],
  ["DAV-REV-002", "研究型大V", "复盘生产", "带自选股的归纳", "已有自选股及可选K线标注", "选择自选股；完成 Draft 确认；生成归纳并发布", "自选股归纳基于选择标的及可用标注；用户可继续编辑", "P0", "功能", "待执行", ""],
  ["DAV-REV-003", "研究型大V", "复盘生产", "发布成功和失败反馈", "准备正常与异常请求", "点击确认发布；观察页面及目标列表", "成功/失败均有可感知反馈；成功后不等待异步队列才显示", "P0", "异常", "待执行", ""],
  ["DAV-ING-001", "研究型大V", "语音录入", "多次口述追加与清空", "浏览器允许录音或测试数据可用", "录制一次；再次录制；切到手动撰写；清空", "转录追加到用户输入；可继续手动编辑；清空符合明确范围", "P0", "体验", "待执行", ""],
  ["DAV-ING-002", "研究型大V", "文件与URL", "文件/URL内容回填手动撰写", "准备可解析文件或 URL", "上传或解析；返回编辑区；继续修改", "内容进入同一用户输入编辑区，不覆盖既有内容", "P1", "功能", "待执行", ""],
  ["DAV-KNO-001", "研究型大V", "知识录入", "文本、文件和URL加入知识源", "登录大V", "通过三种方式录入；打开知识源与百科", "出现新的知识源、可读词条和关系；不是仅加入聊天上下文", "P0", "功能", "待执行", ""],
  ["DAV-KNO-002", "研究型大V", "知识专区", "分层和图谱浏览", "租户存在知识资产", "在 Web/H5 切换知识层级；查看图谱控制", "大V使用可理解词条层；关系图可展开/收缩层级且不展示管理QKV", "P1", "体验", "待执行", ""],
  ["DAV-HER-001", "研究型大V", "Hermes", "新会话、旧会话与长期记忆", "已有至少一条会话", "发起新会话；打开旧会话续问；刷新", "新会话隔离短期上下文；旧会话可继续；长期偏好按用户/租户保存", "P0", "功能", "待执行", ""],
  ["DAV-HER-002", "研究型大V", "Hermes", "个股K线与分析", "Gangtise 数据可用", "提问：中国银行这支股票的K线图以及分析", "展示K线与可读分析；不是只返回“偏向K线图”或Markdown原文", "P0", "回归", "待执行", ""],
  ["DAV-HER-003", "研究型大V", "Hermes", "知识优先证据链", "租户有相关知识和无关知识", "针对已录入材料提问；再问无材料问题", "优先召回相关租户知识；无匹配时说明缺口，不混入其他租户内容", "P0", "回归", "待执行", ""],
  ["DAV-FAN-001", "研究型大V", "粉丝经营", "查看付费样本与定价收入", "租户有粉丝和付费标记", "进入工作台经营概览；设置/查看定价", "付费样本数、收入估算和注册标注一致，不展示模拟收入", "P1", "功能", "待执行", ""],
  ["DAV-FAN-002", "研究型大V", "评论分析", "行业板块分布图", "租户有多个行业的评论", "打开粉丝个股观察；查看行业图表", "图表有非空数据、尺寸正确、来源为本租户评论标签", "P0", "回归", "待执行", ""],
  ["ADM-AUTH-001", "平台 Admin", "账户与权限", "Admin 登录", "账号 admin/admin123 active", "登录后访问 /admin", "成功进入 Admin；访问日志不清除 admin 会话", "P0", "回归", "待执行", ""],
  ["ADM-AUTH-002", "平台 Admin", "账户与权限", "大V/投资者访问 Admin", "分别登录 dav、investor", "访问 /admin、/intern-handbook、/api/admin/*", "页面返回403或登录受限；API 返回 admin_required", "P0", "权限", "待执行", ""],
  ["ADM-USR-001", "平台 Admin", "用户与租户", "查看用户角色、租户和渠道", "存在多角色、多租户用户", "在用户管理筛选和查看详情", "角色、tenant、渠道、付费样本和状态一致", "P1", "功能", "待执行", ""],
  ["ADM-FLG-001", "平台 Admin", "功能开关", "Hermes访问范围开关", "可修改配置", "切换投资者 Hermes、提示词范围和互联网补充；保存", "刷新前台后入口、提示与接口路由一致变化", "P0", "回归", "待执行", ""],
  ["ADM-FLG-002", "平台 Admin", "功能开关", "互动与登录策略开关", "可修改配置", "切换评论互动、微信登录、H5受限测试；保存", "相应前台展示与后端接口同时受限/开放", "P0", "权限", "待执行", ""],
  ["ADM-LLM-001", "平台 Admin", "模型治理", "默认模型与功能级模型映射", "已配置多个模型", "修改 Hermes/复盘/知识/语音功能映射；保存；触发功能", "调用记录使用对应模型；未映射功能回退默认模型", "P0", "功能", "待执行", ""],
  ["ADM-HER-001", "平台 Admin", "Hermes治理", "调用、工具动作和算力统计", "已有 Hermes 记录", "查看今日/本月/人均、工具统计、用户排行、算力池", "指标基于真实调用与 token 记录，筛选和汇总一致", "P1", "数据", "待执行", ""],
  ["ADM-HER-002", "平台 Admin", "记忆治理", "按时间备份和清理记忆", "目标租户有历史记忆", "选择1/3/6/12个月或全部；先备份再清理", "只作用目标租户和时间范围；备份可下载/验证；清理影响可追溯", "P0", "高风险", "待执行", ""],
  ["ADM-KNO-001", "平台 Admin", "知识治理", "跨租户知识、词条与QKV查看", "至少两个租户有知识", "切换租户；进入来源、词条、图谱和治理页", "Admin可查看治理信息；租户选择和数据统计一致", "P1", "功能", "待执行", ""],
  ["ADM-DATA-001", "平台 Admin", "数据治理", "指标湖和Gangtise数据来源", "数据服务可用或模拟故障", "查看指标专区；触发数据查询；模拟数据源失败", "每条数据来源可见；失败显示错误/不可用，不展示随机模拟值", "P0", "回归", "待执行", ""],
  ["ADM-AUD-001", "平台 Admin", "运营与审计", "访问、渠道、浏览与评论分析", "产生跨入口访问和评论数据", "查看运营分析、访问审计、评论统计", "统计维度、租户范围和原始记录能相互对应", "P1", "数据", "待执行", ""],
  ["ADM-DB-001", "平台 Admin", "数据库发布", "无二次口令的写操作", "登录 Admin；未解锁发布口令", "尝试备份/发布/回滚/模拟批次写操作", "服务端拒绝并返回 database_release_password_required", "P0", "权限", "待执行", ""],
  ["ADM-DB-002", "平台 Admin", "数据库发布", "二次口令授权后执行操作", "已输入正确发布口令", "解锁；执行一次受控操作；确认会话期限", "操作可执行且审计清晰；过期后再次要求二次口令", "P0", "高风险", "待执行", ""],
];

function colLetter(index) {
  let output = "";
  let value = index;
  while (value > 0) {
    const remainder = (value - 1) % 26;
    output = String.fromCharCode(65 + remainder) + output;
    value = Math.floor((value - 1) / 26);
  }
  return output;
}

function formatSheet(sheet, rows, title, subtitle) {
  const lastCol = colLetter(headers.length);
  const lastRow = rows.length + 4;
  sheet.showGridLines = false;
  sheet.getRange(`A1:${lastCol}1`).merge();
  sheet.getRange("A1").values = [[title]];
  sheet.getRange(`A2:${lastCol}2`).merge();
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange(`A1:${lastCol}1`).format = { fill: "#1E5F99", font: { bold: true, color: "#FFFFFF", size: 16 }, horizontalAlignment: "left", verticalAlignment: "center" };
  sheet.getRange(`A2:${lastCol}2`).format = { fill: "#EAF3FB", font: { color: "#355B7A", size: 10 }, horizontalAlignment: "left", verticalAlignment: "center", wrapText: true };
  sheet.getRange(`A1:${lastCol}1`).format.rowHeight = 28;
  sheet.getRange(`A2:${lastCol}2`).format.rowHeight = 30;
  sheet.getRange(`A4:${lastCol}4`).values = [headers];
  sheet.getRange(`A5:${lastCol}${lastRow}`).values = rows;
  sheet.getRange(`A4:${lastCol}4`).format = { fill: "#DDECF8", font: { bold: true, color: "#234A6B" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
  sheet.getRange(`A4:${lastCol}${lastRow}`).format.borders = { preset: "insideHorizontal", style: "thin", color: "#D9E4EE" };
  sheet.getRange(`A5:${lastCol}${lastRow}`).format.wrapText = true;
  sheet.getRange(`A5:${lastCol}${lastRow}`).format.verticalAlignment = "top";
  sheet.getRange(`A4:${lastCol}${lastRow}`).format.rowHeight = 34;
  sheet.getRange(`A5:A${lastRow}`).format.font = { bold: true, color: "#2F74C0" };
  sheet.getRange(`H5:H${lastRow}`).format.horizontalAlignment = "center";
  sheet.getRange(`I5:J${lastRow}`).format.horizontalAlignment = "center";
  sheet.getRange(`A4:${lastCol}${lastRow}`).format.autofitColumns();
  const widths = [15, 14, 16, 25, 28, 42, 42, 10, 12, 12, 30];
  widths.forEach((width, index) => { sheet.getRange(`${colLetter(index + 1)}1`).format.columnWidth = width; });
  sheet.freezePanes.freezeRows(4);
  sheet.getRange(`H5:H${lastRow}`).conditionalFormats.add("containsText", { text: "P0", format: { fill: "#FDEBEC", font: { color: "#B74343", bold: true } } });
  sheet.getRange(`H5:H${lastRow}`).conditionalFormats.add("containsText", { text: "P1", format: { fill: "#FFF4DD", font: { color: "#9B6100", bold: true } } });
  sheet.getRange(`H5:H${lastRow}`).conditionalFormats.add("containsText", { text: "P2", format: { fill: "#EAF7EF", font: { color: "#1D7A51", bold: true } } });
}

const workbook = Workbook.create();
const guide = workbook.worksheets.add("使用说明");
guide.showGridLines = false;
guide.getRange("A1:F1").merge();
guide.getRange("A1").values = [["Gangtise 按角色模块功能测试用例库"]];
guide.getRange("A2:F2").merge();
guide.getRange("A2").values = [["当前系统版本 · 2026-08-13 | 以角色、租户、真实数据与配置生效为测试主线"]];
guide.getRange("A1:F1").format = { fill: "#1E5F99", font: { bold: true, color: "#FFFFFF", size: 17 }, horizontalAlignment: "left", verticalAlignment: "center" };
guide.getRange("A2:F2").format = { fill: "#EAF3FB", font: { color: "#355B7A" }, wrapText: true };
guide.getRange("A1:F1").format.rowHeight = 32;
guide.getRange("A2:F2").format.rowHeight = 28;
guide.getRange("A4:B9").values = [
  ["使用方式", "说明"],
  ["全量用例", "按角色、模块、优先级、测试类型和状态筛选；执行时填写状态与备注。"],
  ["角色工作表", "为普通用户、研究型大V和平台Admin分别提供独立可执行清单。"],
  ["优先级", "P0 为阻断风险；P1 为主要流程；P2 为体验和增强项。"],
  ["关键判断", "先确认角色与租户，再确认真实数据来源，最后确认配置是否同时约束页面与 API。"],
  ["测试边界", "市场或指标数据失败时，应说明不可用原因，不能通过模拟数据或虚构结论替代。"],
];
guide.getRange("A4:B4").format = { fill: "#DDECF8", font: { bold: true, color: "#234A6B" } };
guide.getRange("A4:B9").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D9E4EE" };
guide.getRange("A4:B9").format.wrapText = true;
guide.getRange("A4:B9").format.verticalAlignment = "top";
guide.getRange("A1").format.columnWidth = 24;
guide.getRange("B1").format.columnWidth = 90;
guide.freezePanes.freezeRows(4);

formatSheet(workbook.worksheets.add("全量用例"), cases, "全量测试用例", "共覆盖普通用户、研究型大V和平台Admin。可按角色、模块、优先级和状态筛选。");
formatSheet(workbook.worksheets.add("普通用户"), cases.filter((item) => item[1] === "普通用户"), "普通用户测试用例", "覆盖账户、市场、自选股、互动、复盘、知识、消息与Hermes。");
formatSheet(workbook.worksheets.add("研究型大V"), cases.filter((item) => item[1] === "研究型大V"), "研究型大V测试用例", "覆盖大V入口、复盘生产、多模态录入、知识、Hermes和粉丝经营。");
formatSheet(workbook.worksheets.add("平台Admin"), cases.filter((item) => item[1] === "平台 Admin"), "平台Admin测试用例", "覆盖权限、开关、模型、Hermes/知识治理、数据审计和数据库发布控制。");

const overview = await workbook.inspect({ kind: "table", range: "全量用例!A1:K12", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 11 });
if (!overview.ndjson.includes("INV-AUTH-001")) throw new Error("Workbook verification failed");
const endCase = workbook.worksheets.getItem("全量用例").getRange(`A${cases.length + 4}`).values;
if (endCase?.[0]?.[0] !== "ADM-DB-002") throw new Error("Workbook verification failed");
const rendered = await workbook.render({ sheetName: "全量用例", range: "A1:K16", scale: 1.2, format: "png" });
await fs.mkdir(outputDir, { recursive: true });
await fs.writeFile("/private/tmp/gangtise_role_test_cases_preview.png", new Uint8Array(await rendered.arrayBuffer()));
const exportFile = await SpreadsheetFile.exportXlsx(workbook);
await exportFile.save(outputPath);
console.log(outputPath);
