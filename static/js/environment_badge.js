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
    style.textContent = '#runtime-environment-badge{position:fixed;top:12px;right:14px;z-index:2147483000;display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border:1px solid rgba(22,128,72,.24);border-radius:999px;background:#effaf3;color:#167848;font:600 11px/1.2 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;box-shadow:0 3px 12px rgba(22,120,70,.12);pointer-events:none;white-space:nowrap}#runtime-environment-badge:before{content:"";width:6px;height:6px;border-radius:50%;background:#20a464;box-shadow:0 0 0 3px rgba(32,164,100,.12)}@media(max-width:480px){#runtime-environment-badge{top:8px;right:8px;font-size:10px;padding:4px 7px}}';
    document.head.appendChild(style);
    const badge = document.createElement('div');
    badge.id = 'runtime-environment-badge';
    badge.setAttribute('role', 'status');
    badge.setAttribute('aria-label', label);
    badge.textContent = label;
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
