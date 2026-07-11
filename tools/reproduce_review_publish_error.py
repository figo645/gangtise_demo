import json
import sys
import time
from urllib import request


WEBDRIVER = "http://127.0.0.1:4444"


def http_json(method, path, payload=None, timeout=120):
    data = None
    headers = {"Content-Type": "application/json;charset=UTF-8"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = request.Request(WEBDRIVER + path, data=data, method=method, headers=headers)
    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body or "{}")


def execute(session_id, script, args=None):
    payload = {"script": script, "args": args or []}
    result = http_json("POST", f"/session/{session_id}/execute/sync", payload)
    return result.get("value")


def wait_for(session_id, expr, timeout=120):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = execute(session_id, f"return ({expr});")
        if last:
            return last
        time.sleep(0.5)
    raise RuntimeError(f"timeout waiting for: {expr}; last={last!r}")


def open_session():
    result = http_json(
        "POST",
        "/session",
        {
            "capabilities": {
                "alwaysMatch": {
                    "browserName": "safari",
                    "acceptInsecureCerts": True,
                }
            }
        },
    )
    session_id = result.get("sessionId") or ((result.get("value") or {}).get("sessionId"))
    if not session_id:
        raise RuntimeError(result)
    return session_id


def close_session(session_id):
    try:
        http_json("DELETE", f"/session/{session_id}")
    except Exception:
        pass


def navigate(session_id, url):
    http_json("POST", f"/session/{session_id}/url", {"url": url})


def main():
    session_id = open_session()
    try:
        navigate(session_id, "http://127.0.0.1:5001/h5?tenant=laowang")
        wait_for(session_id, "typeof publishReviewDraft === 'function' && typeof renderDemoProfile === 'function'")
        execute(
            session_id,
            """
            window.__reviewErrors = [];
            window.__reviewToasts = [];
            window.addEventListener('unhandledrejection', function(event) {
              const reason = event && event.reason;
              window.__reviewErrors.push({ type: 'unhandledrejection', message: reason && reason.message ? String(reason.message) : String(reason || '') });
            });
            window.onerror = function(message, source, lineno, colno, error) {
              window.__reviewErrors.push({ type: 'error', message: String(message || ''), source: String(source || ''), lineno, colno, stack: error && error.stack ? String(error.stack) : '' });
            };
            if (typeof showToast === 'function') {
              const originalShowToast = showToast;
              window.showToast = function(message) {
                window.__reviewToasts.push(String(message || ''));
                return originalShowToast.apply(this, arguments);
              };
            }
            const dav = (typeof DEMO_PROFILE_USERS !== 'undefined' ? DEMO_PROFILE_USERS : []).find((item) => item && item.role === 'dav');
            if (!dav) throw new Error('dav_user_not_found');
            renderDemoProfile(dav);
            openReviewTriggerModal('manual');
            reviewTriggerDraft.manualHtml = '<p>' + '发布验证：今天市场主线聚焦港股互联网、AI算力和半导体。'.repeat(24) + '</p>';
            reviewTriggerDraft.selectedWatchlist = getTenantWatchlistFocus(dav.tenant.id).slice(0, 3);
            reviewTriggerDraft.generatedPreviewText = '这是智能优化后的复盘草稿。重点关注港股互联网、AI算力和半导体三条线，并保留风险提示。';
            reviewTriggerDraft.draftReviewText = '这是智能优化后的复盘草稿。重点关注港股互联网、AI算力和半导体三条线，并保留风险提示。';
            reviewTriggerDraft.flowStage = 'preview';
            reviewTriggerDraft.previewReady = true;
            renderReviewTriggerModal(getActiveDemoUser());
            return true;
            """,
        )
        execute(session_id, "publishReviewDraft(); return true;")
        wait_for(
            session_id,
            "(window.__reviewErrors && window.__reviewErrors.length > 0) || (window.__reviewToasts && window.__reviewToasts.includes('复盘已发布并入向量库')) || document.body.innerText.includes('复盘发布失败')",
            timeout=180,
        )
        result = execute(
            session_id,
            """
            return {
              errors: window.__reviewErrors || [],
              toasts: window.__reviewToasts || [],
              flowStage: reviewTriggerDraft.flowStage,
              previewReady: reviewTriggerDraft.previewReady,
              bodyText: document.body ? document.body.innerText.slice(0, 1200) : '',
            };
            """,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get('errors'):
            return 2
        if '复盘已发布并入向量库' not in result.get('toasts', []):
            return 1
        return 0
    finally:
        close_session(session_id)


if __name__ == '__main__':
    sys.exit(main())
