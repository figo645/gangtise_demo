"""Deterministic regression coverage for the H5 and DAv workbench surfaces.

These scenarios render the real Flask routes and inspect the client contracts
that drive user interactions. They never submit LLM generation work or mutate
business data. Existing page bootstrap logic may perform its normal read-only
database and market-provider probes, including fallback rendering when data is
unavailable.
"""

from __future__ import annotations

import unittest

import app as app_entry
import src.web.hooks as web_hooks
import src.web.pages as web_pages


TENANT_SLUG = "laowang"


def _scenario(
    scenario_id: str,
    surface: str,
    name: str,
    given: str,
    when: str,
    then: str,
    required: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = (),
    check: str = "html_contract",
) -> dict[str, object]:
    return {
        "id": scenario_id,
        "surface": surface,
        "name": name,
        "given": given,
        "when": when,
        "then": then,
        "required": required,
        "forbidden": forbidden,
        "check": check,
    }


BDD_SCENARIOS = (
    _scenario(
        "h5-splash", "H5", "开屏与租户品牌", "用户打开租户 H5。", "页面完成首屏渲染。", "开屏、品牌名称和投资箴言均可用。",
        ('id="h5-splash-screen"', 'id="h5-splash-product-name"', 'id="h5-splash-quote"', 'initH5SplashScreen();'),
    ),
    _scenario(
        "h5-mobile", "H5", "移动端安全区域适配", "用户在移动端访问 H5。", "视口与开屏样式加载。", "页面必须使用动态视口和安全区域间距。",
        ('min-height:100dvh', 'env(safe-area-inset-bottom)', '@media (max-width:575.98px)'),
    ),
    _scenario(
        "h5-market-tabs", "H5", "市场四分类切换", "用户位于市场页面。", "切换自选股、热门行业、市场一览和宏观经济。", "四个标签与对应面板都存在。",
        ('market-watchlist-tab', 'market-sector-tab', 'market-overview-tab', 'market-macro-tab', 'market-watchlist-panel', 'market-sector-panel', 'market-overview-panel', 'market-macro-panel'),
    ),
    _scenario(
        "h5-market-sources", "H5", "市场与宏观数据来源说明", "用户查看市场一览或宏观经济。", "阅读数据来源。", "页面明确只读取后台快照，不伪造实时值。",
        ('market-overview-source-note', 'market-sector-source-note', 'market-macro-source-note', '页面只读取数据库快照'),
    ),
    _scenario(
        "h5-market-index-detail", "H5", "市场指数统一详情", "用户点击上证或深证指数。", "系统打开指标详情。", "页面从统一指标库构建详情，不跳转为自选股详情。",
        ('function buildWorkbenchDashboardDetailCard', 'findWorkbenchBaseIndicator(indicatorCode)', '基础指标由统一数据源和指标库维护'),
        ("openWatchlistDetail(indicatorCode, 'overview');",),
    ),
    _scenario(
        "h5-watchlist-search", "H5", "自选股模糊搜索", "用户要添加自选股。", "输入中文、拼音或代码。", "搜索输入框、建议列表和键盘选择逻辑均存在。",
        ('watchlist-stock-code-input', 'watchlist-stock-suggestion-list', 'handleWatchlistStockCodeInput', 'selectWatchlistSuggestionByIndex'),
    ),
    _scenario(
        "h5-watchlist-server-owned", "H5", "自选股服务端持久化", "用户管理自选股。", "页面加载或刷新。", "浏览器不保存本地自选股副本。",
        (), ('gangtise_demo_added_watchlist_codes', 'gangtise_demo_removed_watchlist_codes', 'gangtise_demo_watchlist_annotations'),
    ),
    _scenario(
        "h5-watchlist-comments", "H5", "个股评论与身份展示", "用户查看个股详情。", "打开评论区。", "评论区使用当前登录账户身份，不信任页面提交的昵称。",
        ('/api/watchlist/${encodeURIComponent(stockCode)}/comments', 'user_name: String(user.name || user.username || \'\').trim()'),
    ),
    _scenario(
        "h5-fundamental-read-only", "H5", "粉丝端基本面只读", "普通用户查看基本面智能指标。", "打开任意指标详情。", "详情只能查看，新增、修改和移除要前往大V工作台。",
        ('openFundamentalDashboardIndicatorDetail', '这里仅供查看详情；指标的新增、修改和移除请前往大V工作台'),
    ),
    _scenario(
        "h5-fundamental-no-ops-alerts", "H5", "基本面不展示运维预警", "用户查看按板块归纳的自选股。", "页面渲染初始内容或刷新自选股。", "只展示行情与研究摘要，不展示数据源连通性预警或预警计数。",
        ('查看最新行情与研究摘要',), ('fund-stock-alert-row', 'fund-board-tab-count', '需关注数据源刷新与连通状态'),
    ),
    _scenario(
        "h5-fundamental-news-list", "H5", "基本面新闻查询页", "用户在基本面查看综合归纳要闻。", "点击更多、按来源筛选或搜索关键词。", "进入独立新闻列表页，条目复用统一详情弹窗，不叠加新闻列表弹窗。",
        ('id="page-fund-news-list"', 'function openFundNewsList', 'function updateFundNewsListQuery', 'function showFundNewsDetail'),
        ('id="fund-news-modal"', 'function openFundNewsModal'),
    ),
    _scenario(
        "h5-watermark", "H5", "水印功能开关", "管理员启用 H5 水印。", "用户进入 H5。", "页面具备用户名与日期水印容器。",
        ('id="h5-watermark-layer"', 'renderH5Watermark', 'h5_watermark'),
    ),
    _scenario(
        "h5-review-entry", "H5", "复盘生产入口", "大V在 H5 发起复盘。", "打开复盘生产区。", "复盘独立工作区、期间选择和发布入口均可用。",
        ('id="review-production-page"', 'openReviewTriggerModal()', 'id="review-period-row"', 'publishReviewDraft()'),
    ),
    _scenario(
        "h5-review-stages", "H5", "复盘三阶段审核", "大V录入复盘材料。", "依次生成 Draft、选择自选股并审核预览。", "用户输入、规则和结构化自选股分析均可继续编辑。",
        ('智能优化规则', 'Draft 审核与详细修改', '重新生成自选股分析', 'id="review-structured-combined-text"'),
    ),
    _scenario(
        "h5-review-jobs", "H5", "复盘任务恢复与停止", "复盘异步任务正在运行。", "用户重新进入页面或点击停止生成。", "页面可恢复任务状态，并调用同一取消接口。",
        ('function loadActiveReviewJobs()', 'cancelReviewAsyncJob()', '/api/review/jobs/${encodeURIComponent(jobCode)}/cancel'),
    ),
    _scenario(
        "h5-review-api", "H5", "复盘 API 编排", "大V提交复盘。", "执行 Draft、结构化预览和发布。", "三个阶段必须调用统一服务端 API。",
        ('/api/review/generate-draft', '/api/review/prepare-preview', '/api/review/publish'),
    ),
    _scenario(
        "h5-review-published", "H5", "已发布复盘阅读与删除", "大V查看已发布复盘。", "打开详情或删除一篇复盘。", "阅读入口和受权限保护的删除动作均存在。",
        ('openReviewArticleDetail', 'deletePublishedReviewArticle', '/api/tenant/${encodeURIComponent(tenantSlug)}/reviews/${encodeURIComponent(reviewId)}'),
    ),
    _scenario(
        "h5-messages-read-only", "H5", "消息中心站内信模式", "粉丝互动能力关闭。", "用户查看任意消息。", "回复区隐藏并明确提示当前不开放回复。",
        ('id="dm-quick-asks"', 'id="dm-input-bar" style="display:none"', '当前为站内信查看模式，暂不开放回复', '暂不支持回复'),
    ),
    _scenario(
        "h5-hermes-session", "H5", "小金会话与自动滚动", "用户进入小金智能体。", "切换会话或发送新问题。", "会话列表、历史恢复和到底部滚动逻辑均存在。",
        ('id="hermes-chat-thread"', 'function resetHermesScrollPosition()', 'handleHermesComposerSubmit()', '/api/hermes/sessions'),
    ),
    _scenario(
        "h5-hermes-thinking", "H5", "小金思考默认收起", "回答携带思考过程。", "用户主动点击展开。", "思考过程默认不展开，状态由用户动作决定。",
        ('function handleHermesThinkingDisclosureToggle(disclosure)', 'thinkingExpanded === true ? \' open\' : \'\''),
    ),
    _scenario(
        "h5-hermes-no-knowledge-save", "H5", "小金不再写入知识源", "用户获得小金回答。", "查看回答操作。", "页面不得出现将答案加入知识源的入口。",
        (), ('function saveHermesAnswerAsKnowledge(entryId)', 'function buildHermesKnowledgePayload(entry, artifact)', '加入知识源'),
    ),
    _scenario(
        "h5-dav-dashboard", "H5 大V工作台", "大V智能看板入口", "大V进入 H5 工作台。", "查看智能指标看板。", "大V拥有草稿、发布、恢复和指标编辑入口。",
        ('const hasDavCapabilities = isDavCapableUser(user);', 'id="wb-dashboard-preview"', 'publishFundDashboard()', 'resetFundDashboardDraft()', 'openWorkbenchSmartIndicatorEditor'),
    ),
    _scenario(
        "h5-dav-library", "H5 大V工作台", "大V指标库折叠管理", "租户已有多个已保存指标。", "打开 H5 大V工作台。", "页面只显示最近三个指标，其余通过更多和管理弹窗查看。",
        ('function renderWorkbenchSmartIndicatorLibrary()', 'function openWorkbenchSmartIndicatorLibraryModal()', 'const recentItems = items.slice(0, 3)', '更多（${remainingCount}）', '管理指标'),
    ),
    _scenario(
        "h5-dav-formula", "H5 大V工作台", "指标标签与公式编辑", "大V输入 CPI、PPI、行业或市场指标。", "构造加减乘除公式。", "系统使用标签、公式 token 和可移除的误匹配标签。",
        ('canonicalizeWorkbenchSmartPrompt', 'tokenizeWorkbenchSmartPrompt', 'formula_tokens', 'toggleWorkbenchSmartTag'),
    ),
    _scenario(
        "h5-dav-direct-reference", "H5 大V工作台", "单一已注册指标直接引用", "大V输入一个已注册指标名称。", "生成预览并确认展示。", "系统复用指标定义而不是创建重复智能指标。",
        ('function getWorkbenchDirectPreviewCandidate', 'preview.direct_reference === true', '已直接引用指标，无需等待生成'),
    ),
    _scenario(
        "h5-dav-dashboard-removal", "H5 大V工作台", "从看板移除不删除定义", "大V要移除一个展示指标。", "确认从 Dashboard 移除。", "只移除看板引用，定义、快照和历史数据保留。",
        ('function removeWorkbenchDashboardIndicator(index)', "syncTenantDashboardState('remove_indicator'", '只移除看板投影，不删除指标定义、历史数据或指标库记录。'),
    ),
    _scenario(
        "h5-dav-indicator-api", "H5 大V工作台", "智能指标统一 API", "大V预览、保存或更新智能指标。", "提交标签和公式。", "请求统一指向租户 smart-indicators API。",
        ('/api/tenant/${encodeURIComponent(tenantSlug)}/smart-indicators', "action: 'preview'", "action: 'save'"),
    ),
    _scenario(
        "web-shell", "Web 大V工作台", "桌面工作台主导航", "大V进入桌面工作台。", "查看工作台导航。", "概览、粉丝、复盘、指标、看板和已发布内容均可进入。",
        ('data-section="overview"', 'data-section="fans"', 'data-section="review"', 'data-section="dashboard"', 'data-section="indicator-smart"', 'data-section="published"', 'function showWorkbenchSection'),
    ),
    _scenario(
        "web-fans", "Web 大V工作台", "粉丝与经营分析", "大V进入粉丝或经营分析。", "切换漏斗、渠道、营收和分层。", "粉丝运营和四类经营分析使用租户范围接口。",
        ('workbench-section-fans', 'workbench-section-biz-dashboard', "showWorkbenchAnalyticsSection('funnel')", "showWorkbenchAnalyticsSection('channel')", "showWorkbenchAnalyticsSection('revenue')", "showWorkbenchAnalyticsSection('segment')", '/api/kol/business-analytics?tenant='),
    ),
    _scenario(
        "web-review-production", "Web 大V工作台", "桌面复盘生产", "大V在桌面工作台发起复盘。", "生成 Draft、预览并发布。", "桌面端使用与 H5 相同的复盘三阶段 API。",
        ('function kwGenerateReviewDraftWithLlm()', 'function kwRequestReviewStructuredPreview()', 'function kwPublishReviewContent', '/api/review/generate-draft', '/api/review/prepare-preview', '/api/review/publish'),
    ),
    _scenario(
        "web-review-jobs", "Web 大V工作台", "桌面复盘任务恢复", "复盘任务在后台运行。", "工作台重新加载或用户取消任务。", "任务列表、轮询和取消调用与 H5 使用相同服务端作业。",
        ('function kwLoadActiveReviewJobs()', 'function kwStartAsyncJobPolling', '/api/review/jobs?tenant_slug=', '/api/review/jobs/${encodeURIComponent(jobCode)}/cancel'),
    ),
    _scenario(
        "web-published-reviews", "Web 大V工作台", "已发布复盘管理", "大V查看已发布复盘。", "删除一篇已发布复盘。", "删除必须走租户范围 API 并刷新列表状态。",
        ('function kwDeletePublishedReview(reviewId)', '/api/tenant/${encodeURIComponent(tenantSlug)}/reviews/${encodeURIComponent(normalizedReviewId)}', 'kwSyncPublishedReviewState'),
    ),
    _scenario(
        "web-dashboard", "Web 大V工作台", "桌面智能指标看板", "大V进入 Dashboard。", "切换布局或点击空位。", "空位只能通过智能指标编辑器添加，不使用旧白盒拼卡片。",
        ('kwRenderSmartDashboardLayoutRow', 'kwOpenSmartIndicatorEditor', 'function kwGenerateFundDashboard(layout)', '请点击空白格新增智能指标'),
    ),
    _scenario(
        "web-indicator-library", "Web 大V工作台", "桌面指标定义维护", "大V查看已保存智能指标。", "编辑、加入草稿或删除定义。", "指标库和看板投影区分明确。",
        ('function kwRenderSmartIndicatorLibrary()', 'kwOpenSmartIndicatorLibraryDetail', 'kwAddExistingIndicatorToDraft', 'kwDeleteSmartIndicator', '删除指标定义'),
    ),
    _scenario(
        "web-indicator-formula", "Web 大V工作台", "桌面标签公式计算", "大V输入市场、行业、宏观或个股标签。", "生成预览。", "前端发送标签、抑制标签和公式 token 给统一 API。",
        ('kwCanonicalizeSmartPrompt', 'kwTokenizeSmartPrompt', 'selected_tag_codes', 'suppressed_tag_codes', 'formula_tokens'),
    ),
    _scenario(
        "web-indicator-direct-reference", "Web 大V工作台", "桌面直接引用不重复建指标", "大V仅引用一个已注册指标。", "确认展示。", "直接将已有 indicator_code 加入草稿。",
        ('function kwGetDirectPreviewCandidate', 'preview.direct_reference === true', '已直接引用指标，无需重复生成', 'nextCards[slotIndex] = { indicatorCode: preview.indicator_code }'),
    ),
    _scenario(
        "web-indicator-removal", "Web 大V工作台", "桌面看板移除保留定义", "大V从当前 Dashboard 移除指标。", "确认移除。", "只保存草稿引用变化，不调用删除指标定义 API。",
        ('function kwRemoveSmartDashboardCard(index)', '已从草稿移除，指标定义仍保留'),
        ("kwDeleteSmartIndicator('${escapeAttr(item.indicatorCode || item.indicator_code || '')}')",),
    ),
    _scenario(
        "web-dashboard-sync", "Web 大V工作台", "桌面看板服务端失败可见", "服务端拒绝保存 Dashboard。", "工作台同步草稿、发布或恢复。", "同步函数校验租户、抛出失败并返回确认载荷。",
        ("if (!tenantSlug) throw new Error('tenant_missing');", "throw new Error(payload.error || 'dashboard_sync_failed');", 'return payload;'),
    ),
    _scenario(
        "web-dashboard-publish", "Web 大V工作台", "桌面看板发布与恢复", "大V有一个 Dashboard 草稿。", "发布或恢复。", "发布与恢复使用统一 dashboard API，失败会反馈给用户。",
        ("kwSyncFundDashboard('publish'", "kwSyncFundDashboard('reset_draft'", '发布失败，请稍后重试', '恢复失败，请稍后重试'),
    ),
    _scenario(
        "web-hermes-operations", "Web 大V工作台", "桌面 Hermes 运营视图", "大V打开 Hermes 运营页。", "读取用量、记忆和能力沉淀。", "所有读取都限定在当前租户。",
        ('/api/kol/hermes/usage-stats?tenant=', '/api/kol/hermes/memory-summary?tenant=', '/api/kol/hermes/capability-growth?tenant='),
    ),
    _scenario(
        "web-watchlist-operations", "Web 大V工作台", "桌面自选与评论洞察", "大V查看自选股池或互动洞察。", "打开评论详情。", "工作台提供大V自选、粉丝自选和评论洞察入口。",
        ('workbench-section-watchlist-pool', 'workbench-section-watchlist-insights', 'openKwWatchlistComments', 'kw-fan-watchlist-sector-chart'),
    ),
    _scenario(
        "web-feature-guards", "Web 大V工作台", "桌面功能开关保护", "管理员关闭某个模块。", "大V通过直链尝试打开。", "页面会根据功能开关回退到概览。",
        ("section === 'dashboard' && !isWorkbenchFeatureEnabled('fundamental_analysis')", "section === 'review' || section === 'published'", "showWorkbenchSection('overview')"),
    ),
    _scenario(
        "cross-review-contract", "跨端一致性", "H5 与 Web 复盘同源", "大V从 H5 或 Web 发起复盘。", "执行三个复盘阶段。", "两端均使用 generate-draft、prepare-preview、publish 三个 API。",
        ('/api/review/generate-draft', '/api/review/prepare-preview', '/api/review/publish'), check="cross_contract"),
    _scenario(
        "cross-indicator-contract", "跨端一致性", "H5 与 Web 指标同源", "大V从 H5 或 Web 编辑智能指标。", "预览或保存指标。", "两端均调用同一个 tenant smart-indicators API，并传递公式 token。",
        ('/api/tenant/${encodeURIComponent(tenantSlug)}/smart-indicators', 'formula_tokens'), check="cross_contract"),
    _scenario(
        "cross-dashboard-contract", "跨端一致性", "H5 与 Web 看板同源", "大V在任一端维护 Dashboard。", "保存草稿、发布、恢复或移除。", "两端均使用同一个 tenant dashboard API。",
        ('/api/tenant/${encodeURIComponent(tenantSlug)}/dashboard', "'save_draft'", "'publish'", "'reset_draft'"), check="cross_contract"),
    _scenario(
        "cross-direct-indicator", "跨端一致性", "两端均避免重复指标定义", "用户只引用一个已注册基础指标。", "生成预览。", "H5 和 Web 都启用 direct_reference 快路径。",
        ('direct_reference === true', 'DirectPreviewCandidate'), check="cross_contract"),
    _scenario(
        "cross-review-payload", "跨端一致性", "Web 不再附加 H5 没有的复盘字段", "大V从桌面端发布复盘。", "构造 publish 请求。", "Web 不得额外发送知识附件或智能卡片载荷。",
        (), ('knowledge_attachments: kwGetReviewSelectedKnowledge()', 'selected_cards: kwGetReviewSelectedCards()'), check="web_only"),
    _scenario(
        "security-dav-admin-page", "权限边界", "大V访问 Admin 显示友好提示", "已登录用户角色为大V。", "直接访问 /admin。", "页面返回 403，但显示权限不足和联系管理员指引。", check="dav_admin_page"),
    _scenario(
        "security-dav-admin-api", "权限边界", "大V调用 Admin API 被拒绝", "已登录用户角色为大V。", "请求 /api/admin/site-config。", "API 返回结构化 403 admin_required，不泄露后台数据。", check="dav_admin_api"),
)


class ExperienceSurfaceRegressionBddTest(unittest.TestCase):
    """BDD scenarios that are safe to run in local, staging, and CI environments."""

    @classmethod
    def setUpClass(cls):
        cls._original_is_authenticated = web_hooks.is_authenticated
        cls._original_hook_current_user = web_hooks.get_current_authenticated_user
        cls._original_page_current_user = web_pages.get_current_authenticated_user
        cls._active_user = {
            "id": "experience-bdd-dav",
            "username": "experience-bdd-dav",
            "name": "体验回归大V",
            "role": "dav",
            "tenant_slug": TENANT_SLUG,
            "advisor_name": "财经老王",
        }
        web_hooks.is_authenticated = lambda: True
        web_hooks.get_current_authenticated_user = lambda: cls._active_user
        web_pages.get_current_authenticated_user = lambda: cls._active_user
        app_entry.app.config.update(TESTING=True)
        cls.client = app_entry.app.test_client()
        cls._surface_html = {}
        for surface, route in (("H5", f"/h5?tenant={TENANT_SLUG}"), ("H5 大V工作台", f"/h5?tenant={TENANT_SLUG}"), ("Web 大V工作台", f"/kol-workbench?tenant={TENANT_SLUG}")):
            response = cls.client.get(route)
            if response.status_code != 200:
                raise AssertionError(f"{surface} page did not render: HTTP {response.status_code}")
            cls._surface_html[surface] = response.get_data(as_text=True)

    @classmethod
    def tearDownClass(cls):
        web_hooks.is_authenticated = cls._original_is_authenticated
        web_hooks.get_current_authenticated_user = cls._original_hook_current_user
        web_pages.get_current_authenticated_user = cls._original_page_current_user

    def _run_scenario(self, scenario: dict[str, object]):
        check = str(scenario["check"])
        if check == "dav_admin_page":
            response = self.client.get("/admin")
            self.assertEqual(response.status_code, 403)
            html = response.get_data(as_text=True)
            self.assertIn("用户权限不足", html)
            self.assertIn("联系系统管理员申请更高权限", html)
            self.assertIn("返回大V工作台", html)
            return
        if check == "dav_admin_api":
            response = self.client.get("/api/admin/site-config")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.get_json().get("error"), "admin_required")
            return

        if check == "cross_contract":
            html_sources = (self._surface_html["H5 大V工作台"], self._surface_html["Web 大V工作台"])
        elif check == "web_only":
            html_sources = (self._surface_html["Web 大V工作台"],)
        else:
            html_sources = (self._surface_html[str(scenario["surface"])],)

        for token in scenario.get("required", ()):
            for html in html_sources:
                self.assertIn(token, html)
        for token in scenario.get("forbidden", ()):
            for html in html_sources:
                self.assertNotIn(token, html)


def _install_scenarios():
    for scenario in BDD_SCENARIOS:
        method_name = "test_bdd_" + str(scenario["id"]).replace("-", "_")

        def test_method(self, scenario=scenario):
            self._run_scenario(scenario)

        test_method.__name__ = method_name
        test_method.__doc__ = str(scenario["name"])
        setattr(ExperienceSurfaceRegressionBddTest, method_name, test_method)


_install_scenarios()


if __name__ == "__main__":
    unittest.main()
