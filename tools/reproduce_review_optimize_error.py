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


def wait_for(session_id, expr, timeout=90):
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
        wait_for(session_id, "typeof openReviewTriggerModal === 'function' && document.querySelector('#review-trigger-modal-content')")
        execute(
            session_id,
            """
            window.__reviewErrors = [];
            window.__reviewToasts = [];
            window.onerror = function(message, source, lineno, colno, error) {
              window.__reviewErrors.push({ type: 'error', message: String(message || ''), source: String(source || ''), lineno, colno, stack: error && error.stack ? String(error.stack) : '' });
            };
            window.addEventListener('unhandledrejection', function(event) {
              const reason = event && event.reason;
              window.__reviewErrors.push({ type: 'unhandledrejection', message: reason && reason.message ? String(reason.message) : String(reason || '') , stack: reason && reason.stack ? String(reason.stack) : '' });
            });
            if (typeof showToast === 'function') {
              const originalShowToast = showToast;
              window.showToast = function(message) {
                window.__reviewToasts.push(String(message || ''));
                return originalShowToast.apply(this, arguments);
              };
            }
            return true;
            """,
        )
        execute(
            session_id,
            """
            window.__prepareDavReview = (async function() {
              const dav = (typeof DEMO_PROFILE_USERS !== 'undefined' ? DEMO_PROFILE_USERS : []).find((item) => item && item.role === 'dav');
              if (!dav) {
                throw new Error('dav_user_not_found');
              }
              if (typeof renderDemoProfile === 'function') {
                renderDemoProfile(dav);
              } else {
                window.CURRENT_DEMO_PROFILE = dav;
              }
              const user = getActiveDemoUser();
              openReviewTriggerModal('manual');
              reviewTriggerDraft.manualHtml = '<p>' + '今天主要看港股互联网、AI算力、半导体三条线。'.repeat(40) + '</p>';
              reviewTriggerDraft.selectedWatchlist = getTenantWatchlistFocus(user.tenant.id).slice(0, 3);
              reviewTriggerDraft.optimizeRuleMode = 'default';
              reviewTriggerDraft.aiPrompt = '';
              reviewTriggerDraft.promptTags = [];
              reviewTriggerDraft.flowStage = 'optimize_rule';
              renderReviewTriggerModal(user);
              return {
                user: user && user.username,
                role: user && user.role,
                watchlistCount: (reviewTriggerDraft.selectedWatchlist || []).length,
                hasLlm: typeof hasConfiguredGeneralLlm === 'function' ? hasConfiguredGeneralLlm() : false,
              };
            })().then(function(result) {
              window.__prepareDavReviewResolved = result;
              return result;
            }).catch(function(error) {
              window.__prepareDavReviewResolved = { error: error && error.message ? String(error.message) : String(error || '') };
              throw error;
            });
            return true;
            """,
        )
        wait_for(session_id, "window.__prepareDavReviewResolved || false", timeout=20)
        execute(session_id, "submitReviewSmartOptimize(); return true;")
        wait_for(
            session_id,
            "(window.__reviewErrors && window.__reviewErrors.length > 0) || reviewTriggerDraft.flowStage === 'draft_review' || (reviewDraftGenerating === false && reviewTriggerDraft.flowStage === 'optimize_rule')",
            timeout=180,
        )
        result = execute(
            session_id,
            """
            return {
              flowStage: reviewTriggerDraft.flowStage,
              previewReady: reviewTriggerDraft.previewReady,
              reviewDraftGenerating,
              jobState: reviewDraftJobState ? {
                status: reviewDraftJobState.status || '',
                summary: reviewDraftJobState.summary || '',
                error_message: reviewDraftJobState.error_message || '',
              } : null,
              generatedLength: String(reviewTriggerDraft.generatedPreviewText || '').length,
              draftLength: String(reviewTriggerDraft.draftReviewText || '').length,
              errors: window.__reviewErrors || [],
              toasts: window.__reviewToasts || [],
              bodyText: document.getElementById('review-trigger-modal-content') ? document.getElementById('review-trigger-modal-content').innerText.slice(0, 1200) : '',
            };
            """,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("errors"):
            return 2
        if result.get("flowStage") != "draft_review":
            return 1
        return 0
    finally:
        close_session(session_id)


if __name__ == "__main__":
    sys.exit(main())
