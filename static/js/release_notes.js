(function () {
  const currentRelease = {
    id: 'v1.5-20260818',
    version: 'v1.5',
    date: '2026-08-18',
    isMajor: true,
    title: '受控交付与环境同步',
    summary: '本次更新把数据库发布从单一导入动作升级为可验证、可回滚的环境交付流程。',
    features: [
      { tag: 'DEFAULT PATH', title: '日常增量发布', copy: '先在 Staging 完整验证，再审核结构、主数据和业务数据差异，向 Production 发布版本化增量。' },
      { tag: 'FULL PROMOTION', title: '环境全量同步', copy: 'Staging 到 Production 全量发布先恢复临时库，校验 pgvector、表和迁移后才切换。' },
      { tag: 'ROLLBACK READY', title: '可回滚交付', copy: '全量切换会保留目标环境原数据库作为回滚备份；任务过程提供实时日志与阶段状态。' }
    ]
  };
  const history = [
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
