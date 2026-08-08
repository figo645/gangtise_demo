import json
import sys
import time
from urllib import error, request


WEBDRIVER = "http://127.0.0.1:4444"


def http_json(method, path, payload=None):
    data = None
    headers = {"Content-Type": "application/json;charset=UTF-8"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = request.Request(WEBDRIVER + path, data=data, method=method, headers=headers)
    with request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body or "{}")


def execute(session_id, script, args=None):
    payload = {"script": script, "args": args or []}
    result = http_json("POST", f"/session/{session_id}/execute/sync", payload)
    return result.get("value")


def wait_for(session_id, expr, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
      value = execute(session_id, f"return Boolean({expr});")
      if value:
        return True
      time.sleep(0.25)
    raise RuntimeError(f"timeout waiting for: {expr}")


def open_session():
    payload = {
        "capabilities": {
            "alwaysMatch": {
                "browserName": "safari",
                "acceptInsecureCerts": True,
            }
        }
    }
    result = http_json("POST", "/session", payload)
    session_id = result.get("sessionId") or ((result.get("value") or {}).get("sessionId"))
    if not session_id:
        raise RuntimeError(f"failed to create session: {result}")
    return session_id


def close_session(session_id):
    try:
        http_json("DELETE", f"/session/{session_id}")
    except Exception:
        pass


def navigate(session_id, url):
    http_json("POST", f"/session/{session_id}/url", {"url": url})


def verify_h5_review_scroll(session_id):
    navigate(session_id, "http://127.0.0.1:5001/h5?tenant=laowang")
    wait_for(session_id, "typeof openReviewTriggerModal === 'function' && document.querySelector('#review-trigger-modal-content')")
    result = execute(
        session_id,
        """
        const user = (typeof getActiveDemoUser === 'function') ? getActiveDemoUser() : null;
        if (!user) return { ok: false, reason: 'no_active_user' };
        if (user.role !== 'dav' && typeof switchDemoProfile === 'function') {
          const dav = (window.H5_LOGIN_USERS || []).find((item) => item && item.role === 'dav');
          if (dav) {
            switchDemoProfile(dav.username || dav.profile_id || dav.id || '');
          }
        }
        const active = (typeof getActiveDemoUser === 'function') ? getActiveDemoUser() : user;
        openReviewTriggerModal('manual');
        const modal = document.getElementById('review-trigger-modal');
        const sheet = modal && modal.querySelector('.modal-sheet');
        const host = document.getElementById('review-trigger-modal-content');
        if (!sheet || !host) return { ok: false, reason: 'missing_modal' };
        reviewTriggerDraft.manualHtml = '<p>' + '测试内容。'.repeat(200) + '</p>';
        reviewTriggerDraft.selectedWatchlist = getTenantWatchlistFocus(active.tenant.id).slice(0, 3);
        reviewTriggerDraft.flowStage = 'intake';
        renderReviewTriggerModal(active);
        sheet.scrollTop = Math.max(0, sheet.scrollHeight - sheet.clientHeight - 48);
        const before = sheet.scrollTop;
        openReviewOptimizeRuleStep();
        const afterRule = sheet.scrollTop;
        reviewTriggerDraft.aiPrompt = '更口语化，但保留原始观点';
        reviewDraftGenerating = true;
        reviewDraftJobState = { status: 'running', progress_stage: 'processing', progress_percent: 42, summary: 'mock progress', result: { live_log: [{ stage: 'processing', at: 'now', text: 'mock log' }] } };
        renderReviewTriggerModal(active);
        const afterProgress = sheet.scrollTop;
        reviewDraftGenerating = false;
        reviewDraftJobState = null;
        closeReviewTriggerModal();
        return {
          ok: true,
          before,
          afterRule,
          afterProgress,
          driftRule: Math.abs(afterRule - before),
          driftProgress: Math.abs(afterProgress - before),
        };
        """,
    )
    return result


def verify_h5_smart_indicator_scroll(session_id):
    navigate(session_id, "http://127.0.0.1:5001/h5?tenant=laowang")
    wait_for(session_id, "typeof renderWorkbenchSmartIndicatorEditorModal === 'function'")
    result = execute(
        session_id,
        """
        const fakeTags = Array.from({ length: 24 }, (_, index) => ({
          tag_code: `indicator:test_${index + 1}`,
          label: `测试指标标签 ${index + 1} 号`,
          tag_type: 'indicator',
          category: '测试分类',
          subtitle: '测试标签',
          selected_indicators: [{ indicator_code: `test_${index + 1}`, indicator_name: `测试指标 ${index + 1}` }],
        }));
        setTenantSmartCatalog({
          tenant_smart_indicators: [],
          base_indicators: [],
          available_tags: fakeTags,
        });
        wbSmartIndicatorDraft = {
          slotIndex: 0,
          indicatorName: '',
          promptText: '【测试指标 1】*2',
          selectedTagCodes: fakeTags.map((item) => item.tag_code),
          preview: null,
          tagPoolExpanded: true,
        };
        renderWorkbenchSmartIndicatorEditorModal();
        const modal = document.getElementById('dashboard-cell-modal');
        const sheet = modal && modal.querySelector('.modal-sheet');
        if (!sheet) return { ok: false, reason: 'missing_modal' };
        sheet.scrollTop = Math.max(0, sheet.scrollHeight - sheet.clientHeight - 48);
        const before = sheet.scrollTop;
        wbSmartIndicatorDraft.preview = {
          indicator_name: 'CPI智能指标',
          value: '201.7',
          unit: '',
          algorithm_detail: 'CPI*2',
          interpretation: '用于测试滚动位置是否保留',
        };
        renderWorkbenchSmartIndicatorEditorModal();
        const after = sheet.scrollTop;
        closeWorkbenchSmartIndicatorEditor();
        return {
          ok: true,
          before,
          after,
          drift: Math.abs(after - before),
          ratioBefore: sheet.scrollHeight > sheet.clientHeight ? before / (sheet.scrollHeight - sheet.clientHeight) : 0,
        };
        """,
    )
    return result


def verify_workbench_review_scroll(session_id):
    navigate(session_id, "http://127.0.0.1:5001/kol-workbench?tenant=laowang")
    wait_for(session_id, "typeof kwOpenReviewTriggerModal === 'function' && document.querySelector('#kw-review-trigger-modal-content')")
    result = execute(
        session_id,
        """
        kwOpenReviewTriggerModal('manual');
        const modal = document.getElementById('kw-review-trigger-modal');
        const sheet = modal && modal.querySelector('.kw-review-modal-sheet');
        if (!sheet) return { ok: false, reason: 'missing_modal' };
        kwReviewDraft.manualHtml = '<p>' + '工作台测试内容。'.repeat(240) + '</p>';
        kwReviewDraft.selectedWatchlist = getKwTenantWatchlistFocus().slice(0, 3);
        kwRenderReviewTriggerModal();
        sheet.scrollTop = Math.max(0, sheet.scrollHeight - sheet.clientHeight - 48);
        const before = sheet.scrollTop;
        kwReviewDraftGenerating = true;
        kwReviewDraftJobState = { status: 'running', progress_stage: 'processing', progress_percent: 38, summary: 'mock progress', result: { live_log: [{ stage: 'processing', at: 'now', text: 'mock log' }] } };
        kwRenderReviewTriggerModal();
        const after = sheet.scrollTop;
        kwReviewDraftGenerating = false;
        kwReviewDraftJobState = null;
        kwCloseReviewTriggerModal();
        return { ok: true, before, after, drift: Math.abs(after - before) };
        """,
    )
    return result


def main():
    session_id = open_session()
    try:
        results = {
            "h5_review": verify_h5_review_scroll(session_id),
            "h5_smart_indicator": verify_h5_smart_indicator_scroll(session_id),
            "workbench_review": verify_workbench_review_scroll(session_id),
        }
        print(json.dumps(results, ensure_ascii=False, indent=2))
        for key, value in results.items():
            if not value.get("ok"):
                return 1
            if value.get("drift", 0) > 24 or value.get("driftRule", 0) > 24 or value.get("driftProgress", 0) > 24:
                return 2
        return 0
    finally:
        close_session(session_id)


if __name__ == "__main__":
    sys.exit(main())
