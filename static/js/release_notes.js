(function () {
  const currentRelease = {
    id: 'v1.6-20260831',
    version: 'v1.6',
    date: '2026-08-31',
    isMajor: true,
    title: '小金智能体统一编排',
    summary: '本次更新把小金智能体收敛为可审计的六类投研场景，由 Admin 配置的 LLM 先理解任务，再分发到 Gangtise 研究能力或通用对话能力。',
    features: [
      { tag: 'SIX SCENARIOS', title: '六类能力统一入口', copy: '支持今日个股观察、今日大盘观察、个股深化研究、个股看点摘要、多支自选股综合分析和多轮闲聊。' },
      { tag: 'LLM PLANNER', title: '先理解，再执行', copy: '用户原始问题先交给 Admin 配置的 LLM；一句话包含多个目的时拆成独立任务，信息不足时先澄清。' },
      { tag: 'TRACEABLE AI', title: '研究结果可追溯', copy: '研究任务按场景调用 Gangtise API 并直出原文；会话记忆、模型、工具、Skills 规则与审计轨迹统一留存。' }
    ]
  };
  const history = [
    { version: 'v1.5', title: '受控交付与环境同步', copy: 'Staging 验证、增量发布、环境全量同步与可回滚交付。' },
    { version: 'v1.4', title: '治理、交付与质量闭环', copy: '账号合规、渠道归因、模型映射、BDD 与系统学习手册。' },
    { version: 'v1.3', title: '知识、复盘与真实数据闭环', copy: 'Gangtise 数据接入、复盘向导、知识分层与共用证据链。' },
    { version: 'v1.2', title: 'Hermes 研究 Agent', copy: '意图路由、知识优先召回、图表、会话记忆和使用治理。' },
    { version: 'v1.1', title: '多租户与生产工作台', copy: '普通用户、大V、Admin 三角色，租户隔离与经营工作台。' }
  ];
  const state = { surface: '', root: null, initialized: false, keydownBound: false };

  function storageKey() {
    return `gangtise.release-notes.seen.${currentRelease.id}.${state.surface || 'default'}`;
  }
  function hasSeen() {
    try { return window.localStorage.getItem(storageKey()) === '1'; } catch (error) { return false; }
  }
  function markSeen() {
    try { window.localStorage.setItem(storageKey(), '1'); } catch (error) { /* Storage can be unavailable in restricted browsers. */ }
  }
  function updateTriggers() {
    document.querySelectorAll('[data-release-notes-trigger]').forEach((trigger) => {
      trigger.classList.toggle('is-unread', !hasSeen());
      trigger.setAttribute('aria-label', hasSeen() ? '查看版本历史' : '查看最新版本更新');
    });
  }
  function renderHistory() {
    return history.map((item) => `<div class="release-notes-history-item"><div class="release-notes-history-version">${item.version}</div><div><div class="release-notes-history-title">${item.title}</div><div class="release-notes-history-copy">${item.copy}</div></div></div>`).join('');
  }
  function mount() {
    if (state.root) return state.root;
    const root = document.createElement('div');
    root.className = 'release-notes-overlay';
    root.id = 'release-notes-modal';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-labelledby', 'release-notes-title');
    root.innerHTML = `
      <section class="release-notes-dialog">
        <div class="release-notes-hero">
          <div class="release-notes-hero-top">
            <div><div class="release-notes-kicker">VERSION UPDATE</div><div class="release-notes-title" id="release-notes-title">${currentRelease.title}</div><div class="release-notes-release">${currentRelease.version} · ${currentRelease.date}</div></div>
            <button class="release-notes-close" type="button" data-release-notes-close aria-label="关闭版本更新" title="关闭">×</button>
          </div>
        </div>
        <div class="release-notes-body">
          <p class="release-notes-intro">${currentRelease.summary}</p>
          <div class="release-notes-feature-grid">${currentRelease.features.map((item) => `<article class="release-notes-feature"><div class="release-notes-feature-tag">${item.tag}</div><div class="release-notes-feature-title">${item.title}</div><div class="release-notes-feature-copy">${item.copy}</div></article>`).join('')}</div>
          <div class="release-notes-history" id="release-notes-history"><button class="release-notes-history-toggle" type="button" data-release-notes-history><span>查看历史版本</span><span aria-hidden="true">+</span></button><div class="release-notes-history-list">${renderHistory()}</div></div>
          <div class="release-notes-actions"><button class="release-notes-primary" type="button" data-release-notes-close>我知道了</button></div>
        </div>
      </section>`;
    root.addEventListener('click', (event) => { if (event.target === root) close(); });
    root.querySelectorAll('[data-release-notes-close]').forEach((button) => button.addEventListener('click', close));
    root.querySelector('[data-release-notes-history]').addEventListener('click', toggleHistory);
    document.body.appendChild(root);
    state.root = root;
    return root;
  }
  function toggleHistory() {
    const historyRoot = state.root && state.root.querySelector('#release-notes-history');
    if (!historyRoot) return;
    const expanded = historyRoot.classList.toggle('is-expanded');
    const symbol = historyRoot.querySelector('[data-release-notes-history] span:last-child');
    if (symbol) symbol.textContent = expanded ? '−' : '+';
  }
  function open() {
    const root = mount();
    markSeen();
    updateTriggers();
    root.classList.add('is-open');
    document.body.classList.add('release-notes-open');
    root.querySelector('[data-release-notes-close]').focus();
  }
  function close() {
    if (!state.root) return;
    state.root.classList.remove('is-open');
    document.body.classList.remove('release-notes-open');
  }
  function maybeAutoOpen() {
    if (!state.initialized || !currentRelease.isMajor || hasSeen()) return false;
    open();
    return true;
  }
  function init(options) {
    options = options || {};
    state.surface = String(options.surface || state.surface || 'default');
    state.initialized = true;
    document.querySelectorAll('[data-release-notes-trigger]').forEach((trigger) => {
      if (trigger.dataset.releaseNotesBound === 'true') return;
      trigger.dataset.releaseNotesBound = 'true';
      trigger.addEventListener('click', open);
    });
    if (!state.keydownBound) {
      state.keydownBound = true;
      document.addEventListener('keydown', (event) => { if (event.key === 'Escape') close(); });
    }
    updateTriggers();
    if (options.autoShow) window.setTimeout(maybeAutoOpen, Number(options.autoDelay || 420));
  }
  window.GangtiseReleaseNotes = { init, open, close, maybeAutoOpen, currentRelease, history };
})();
