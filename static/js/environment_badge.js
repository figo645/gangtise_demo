(function () {
  'use strict';

  function labelFor(target) {
    if (target === 'staging') return '环境：Staging 测试';
    if (target === 'local') return '环境：本地开发';
    return '';
  }

  function render(target) {
    const label = labelFor(target);
    if (!label || document.getElementById('runtime-environment-badge')) return;
    const style = document.createElement('style');
    style.textContent = '#runtime-environment-badge{position:fixed;top:12px;right:14px;z-index:2147483000;display:inline-flex;align-items:center;gap:5px;min-width:24px;min-height:24px;padding:3px 6px;border:1px solid rgba(22,128,72,.24);border-radius:999px;background:#effaf3;color:#167848;font:600 11px/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;box-shadow:0 3px 12px rgba(22,120,70,.12);cursor:pointer;transition:padding .18s ease,background .18s ease}#runtime-environment-badge:hover,#runtime-environment-badge:focus-visible{background:#e2f6ea;outline:2px solid rgba(32,164,100,.28);outline-offset:2px}#runtime-environment-badge:before{content:"";width:6px;height:6px;flex:0 0 6px;border-radius:50%;background:#20a464;box-shadow:0 0 0 3px rgba(32,164,100,.12)}#runtime-environment-badge .runtime-environment-label{display:none;white-space:nowrap}#runtime-environment-badge .runtime-environment-chevron{display:inline-block;font-size:10px;line-height:1;transform:rotate(0deg);transition:transform .18s ease}#runtime-environment-badge[aria-expanded="true"]{padding-inline:8px}#runtime-environment-badge[aria-expanded="true"] .runtime-environment-label{display:inline}#runtime-environment-badge[aria-expanded="true"] .runtime-environment-chevron{transform:rotate(180deg)}@media(max-width:480px){#runtime-environment-badge{top:8px;right:8px}}';
    document.head.appendChild(style);
    const badge = document.createElement('button');
    badge.id = 'runtime-environment-badge';
    badge.type = 'button';
    badge.setAttribute('aria-expanded', 'false');
    badge.setAttribute('aria-controls', 'runtime-environment-label');
    badge.setAttribute('aria-label', label);
    badge.innerHTML = '<span id="runtime-environment-label" class="runtime-environment-label"></span><span class="runtime-environment-chevron" aria-hidden="true">⌄</span>';
    badge.querySelector('.runtime-environment-label').textContent = label;
    badge.addEventListener('click', () => {
      const expanded = badge.getAttribute('aria-expanded') === 'true';
      badge.setAttribute('aria-expanded', expanded ? 'false' : 'true');
      badge.setAttribute('aria-label', expanded ? `${label}，点击展开` : `${label}，点击收起`);
    });
    document.body.appendChild(badge);
  }

  function boot() {
    fetch('/api/runtime-environment', { credentials: 'same-origin', cache: 'no-store' })
      .then((response) => response.ok ? response.json() : null)
      .then((payload) => {
        if (payload && payload.ok !== false) render(String(payload.target || '').toLowerCase());
      })
      .catch(() => { /* Environment decoration must never block page use. */ });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
