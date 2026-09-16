(function () {
  'use strict';

  const STORAGE_KEY = 'gangtise.analytics.anonymous_id.v1';
  const SESSION_KEY = 'gangtise.analytics.session_id.v1';
  const recentEvents = new Map();

  function getStableId(key) {
    try {
      const current = window.localStorage.getItem(key);
      if (current) return current;
      const generated = window.crypto && window.crypto.randomUUID
        ? window.crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      window.localStorage.setItem(key, generated);
      return generated;
    } catch (error) {
      return '';
    }
  }

  function surfaceFromLocation() {
    const configured = String(window.USER_APP_SURFACE || '').trim().toLowerCase();
    if (configured === 'web') return 'web';
    const path = window.location.pathname || '';
    if (path === '/admin' || path.startsWith('/admin/')) return 'admin';
    if (path.startsWith('/kol-workbench')) return 'web';
    if (path.startsWith('/tenant/')) return 'tenant_portal';
    if (path === '/h5' || path.startsWith('/h5/')) return 'h5';
    return 'unknown';
  }

  function currentTenant() {
    const active = window.ACTIVE_TENANT || {};
    const portal = window.TENANT_PORTAL || {};
    return String(active.slug || (portal.tenant || {}).slug || '').trim().toLowerCase();
  }

  function currentUser() {
    const user = window.CURRENT_DEMO_PROFILE || {};
    const tenant = user.tenant || {};
    return {
      tenant_slug: String(user.tenant_slug || tenant.slug || currentTenant()).trim().toLowerCase(),
      user_role: String(user.role || '').trim().toLowerCase(),
      user_profile_id: String(user.username || '').trim(),
    };
  }

  function cleanProperties(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    const result = {};
    Object.keys(value).slice(0, 24).forEach((key) => {
      if (!key || key.startsWith('__')) return;
      const item = value[key];
      if (item === null || ['string', 'number', 'boolean'].includes(typeof item)) {
        result[String(key).slice(0, 64)] = typeof item === 'string' ? item.slice(0, 240) : item;
      }
    });
    return result;
  }

  function postEvent(payload) {
    const body = JSON.stringify(payload);
    try {
      return fetch('/api/analytics/events', {
        method: 'POST',
        credentials: 'same-origin',
        keepalive: true,
        headers: { 'Content-Type': 'application/json' },
        body,
      }).catch(() => null);
    } catch (error) {
      return Promise.resolve(null);
    }
  }

  window.trackAnalyticsEvent = function trackAnalyticsEvent(eventName, payload) {
    const data = payload && typeof payload === 'object' ? payload : {};
    const name = String(eventName || '').trim().slice(0, 80);
    const feature = String(data.feature_key || '').trim().slice(0, 160);
    if (!name || !feature) return Promise.resolve(null);
    const dedupeKey = `${name}:${feature}:${String(data.object_id || '')}`;
    const now = Date.now();
    if (recentEvents.has(dedupeKey) && now - recentEvents.get(dedupeKey) < 500) return Promise.resolve(null);
    recentEvents.set(dedupeKey, now);
    const user = currentUser();
    return postEvent({
      event_name: name,
      event_category: data.event_category || 'interaction',
      feature_key: feature,
      surface: data.surface || surfaceFromLocation(),
      tenant_slug: data.tenant_slug || user.tenant_slug || currentTenant(),
      anonymous_id: getStableId(STORAGE_KEY),
      session_id: getStableId(SESSION_KEY),
      object_type: data.object_type || '',
      object_id: data.object_id || '',
      duration_ms: data.duration_ms,
      success: typeof data.success === 'boolean' ? data.success : undefined,
      error_code: data.error_code || '',
      properties: cleanProperties(data.properties),
    });
  };

  const sessionStartedKey = `${SESSION_KEY}.started`;
  try {
    if (!window.sessionStorage.getItem(sessionStartedKey)) {
      window.sessionStorage.setItem(sessionStartedKey, String(Date.now()));
      window.trackAnalyticsEvent('session_start', {
        feature_key: `${surfaceFromLocation()}.session`,
        event_category: 'navigation',
      });
    }
  } catch (error) {
    window.trackAnalyticsEvent('session_start', {
      feature_key: `${surfaceFromLocation()}.session`,
      event_category: 'navigation',
    });
  }

  window.addEventListener('pagehide', () => {
    let duration = undefined;
    try {
      const started = Number(window.sessionStorage.getItem(sessionStartedKey) || 0);
      if (started) duration = Math.max(0, Date.now() - started);
    } catch (error) { /* keep unload reporting best-effort */ }
    window.trackAnalyticsEvent('session_end', {
      feature_key: `${surfaceFromLocation()}.session`,
      event_category: 'navigation',
      duration_ms: duration,
    });
  });

  function camelToSnake(value) {
    return String(value || '').replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();
  }

  function analyticsClickTarget(target) {
    if (!target || !target.closest) return;
    const explicit = target.closest('[data-analytics-event][data-analytics-feature]');
    if (explicit) {
      window.trackAnalyticsEvent(explicit.dataset.analyticsEvent, {
        feature_key: explicit.dataset.analyticsFeature,
        event_category: explicit.dataset.analyticsCategory || 'interaction',
        object_type: explicit.dataset.analyticsObjectType || '',
        object_id: explicit.dataset.analyticsObjectId || '',
        properties: { action: explicit.dataset.analyticsAction || 'click' },
      });
      return;
    }
    const node = target.closest('button, a, [role="button"], [onclick]');
    if (!node) return;
    const handler = String(node.getAttribute('onclick') || '');
    const surface = surfaceFromLocation();
    let match = handler.match(/switchTab\(['"]([^'"]+)/);
    if (match) {
      window.trackAnalyticsEvent('navigation_click', { feature_key: `${surface}.tab.${camelToSnake(match[1])}`, event_category: 'navigation' });
      return;
    }
    match = handler.match(/showWorkbenchSection\(['"]([^'"]+)/);
    if (match) {
      window.trackAnalyticsEvent('navigation_click', { feature_key: `kol_workbench.${camelToSnake(match[1])}`, event_category: 'navigation' });
      return;
    }
    match = handler.match(/showSection\(['"]([^'"]+)/);
    if (match) {
      window.trackAnalyticsEvent('navigation_click', { feature_key: `admin.${camelToSnake(match[1])}`, event_category: 'navigation' });
      return;
    }
    match = handler.match(/showHermesSubsection\(['"]([^'"]+)/);
    if (match) {
      window.trackAnalyticsEvent('navigation_click', { feature_key: `admin.hermes.${camelToSnake(match[1])}`, event_category: 'navigation' });
      return;
    }
    match = handler.match(/(open|submit|save|delete|remove|add|create|publish|search|query|cancel|retry|preview|refresh|load|switch|toggle|select|set|apply|choose|handle)[A-Za-z0-9_]*/);
    if (!match) return;
    const action = camelToSnake(match[0]);
    window.trackAnalyticsEvent('feature_action', {
      feature_key: `${surface}.action.${action}`,
      properties: { control: node.tagName.toLowerCase() },
    });
  }

  document.addEventListener('click', (event) => analyticsClickTarget(event.target), true);
})();
