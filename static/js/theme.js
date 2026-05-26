(function () {
  const THEME_KEY = 'gangtise_theme_mode';
  const ACCENT_KEY = 'gangtise_theme_accent';

  function applyTheme(mode, accent) {
    const body = document.body;
    if (!body) return;
    body.classList.remove('theme-light', 'theme-dark');
    body.classList.add(mode === 'dark' ? 'theme-dark' : 'theme-light');
    body.dataset.accent = accent || 'blue';
  }

  function initGangtiseTheme() {
    const config = window.SITE_CONFIG || {};
    const mode = localStorage.getItem(THEME_KEY) || config.default_theme || 'light';
    const accent = localStorage.getItem(ACCENT_KEY) || config.default_accent || 'blue';
    applyTheme(mode, accent);
  }

  function setGangtiseTheme(mode) {
    localStorage.setItem(THEME_KEY, mode);
    applyTheme(mode, localStorage.getItem(ACCENT_KEY) || 'blue');
  }

  function setGangtiseAccent(accent) {
    localStorage.setItem(ACCENT_KEY, accent);
    applyTheme(localStorage.getItem(THEME_KEY) || 'light', accent);
  }

  window.initGangtiseTheme = initGangtiseTheme;
  window.setGangtiseTheme = setGangtiseTheme;
  window.setGangtiseAccent = setGangtiseAccent;
})();
