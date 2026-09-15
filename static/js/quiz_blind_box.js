(function () {
  'use strict';
  let payload = null;
  let index = 0;
  let answers = {};
  let submitted = false;
  let dragState = null;
  let suppressNextOpen = false;

  function blindBoxPositionKey() {
    return 'gangtise_quiz_blind_box_position:' + (tenantSlug() || 'default');
  }
  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }
  function applyDraggedPosition(button, left, top, persist) {
    const maxLeft = Math.max(8, window.innerWidth - button.offsetWidth - 8);
    const maxTop = Math.max(8, window.innerHeight - button.offsetHeight - 8);
    const next = {
      left: clamp(Number(left) || 0, 8, maxLeft),
      top: clamp(Number(top) || 0, 8, maxTop),
    };
    button.dataset.dragged = '1';
    button.style.left = `${next.left}px`;
    button.style.top = `${next.top}px`;
    button.style.bottom = 'auto';
    button.style.transform = 'none';
    if (persist) {
      try { window.localStorage.setItem(blindBoxPositionKey(), JSON.stringify(next)); } catch (error) { /* storage is optional */ }
    }
    return next;
  }
  function restoreDraggedPosition(button) {
    if (!button || button.dataset.dragged === '1') return false;
    try {
      const saved = JSON.parse(window.localStorage.getItem(blindBoxPositionKey()) || 'null');
      if (saved && Number.isFinite(Number(saved.left)) && Number.isFinite(Number(saved.top))) {
        applyDraggedPosition(button, saved.left, saved.top, false);
        return true;
      }
    } catch (error) { /* storage is optional */ }
    return false;
  }

  function tenantSlug() {
    const portal = window.TENANT_PORTAL || {};
    const active = window.ACTIVE_TENANT || {};
    return String((portal.tenant || {}).slug || active.slug || active.tenant_slug || '').trim().toLowerCase();
  }
  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }
  function host() { return document.getElementById('quiz-blind-box-modal'); }
  function close() { const modal = host(); if (modal) modal.classList.remove('is-open'); }
  function positionH5BlindBox() {
    const button = document.querySelector('.h5-quiz-blind-box');
    const profile = document.getElementById('nav-profile');
    const nav = document.querySelector('.h5-bottom-nav');
    if (!button || !profile || !nav) return;
    if (button.dataset.dragged === '1') {
      if (dragState) {
        applyDraggedPosition(button, dragState.left, dragState.top, false);
      } else {
        applyDraggedPosition(button, parseFloat(button.style.left), parseFloat(button.style.top), false);
      }
      return;
    }
    if (restoreDraggedPosition(button)) return;
    const profileRect = profile.getBoundingClientRect();
    const navRect = nav.getBoundingClientRect();
    const half = (button.offsetWidth || 44) / 2;
    const safe = 8;
    const center = profileRect.left + profileRect.width / 2;
    const left = Math.max(safe + half, Math.min(window.innerWidth - safe - half, center));
    const isSidebar = window.getComputedStyle(nav).flexDirection === 'column';
    const bottom = isSidebar
      ? Math.max(12, window.innerHeight - profileRect.top + 10)
      : Math.max(12, window.innerHeight - navRect.top + 10);
    button.style.left = `${left}px`;
    button.style.bottom = `${bottom}px`;
  }
  function bindBlindBoxDrag() {
    const button = document.querySelector('.h5-quiz-blind-box');
    if (!button || button.dataset.dragBound === '1') return;
    button.dataset.dragBound = '1';
    button.addEventListener('pointerdown', event => {
      if (event.button !== undefined && event.button !== 0) return;
      const rect = button.getBoundingClientRect();
      dragState = {
        pointerId: event.pointerId,
        offsetX: event.clientX - rect.left,
        offsetY: event.clientY - rect.top,
        left: rect.left,
        top: rect.top,
        moved: false,
      };
      button.setPointerCapture?.(event.pointerId);
    });
    button.addEventListener('pointermove', event => {
      if (!dragState || dragState.pointerId !== event.pointerId) return;
      const left = event.clientX - dragState.offsetX;
      const top = event.clientY - dragState.offsetY;
      if (Math.hypot(left - dragState.left, top - dragState.top) > 6) dragState.moved = true;
      if (!dragState.moved) return;
      event.preventDefault();
      dragState.left = left;
      dragState.top = top;
      applyDraggedPosition(button, left, top, false);
    });
    const finishDrag = event => {
      if (!dragState || (event && dragState.pointerId !== event.pointerId)) return;
      const moved = dragState.moved;
      if (moved) {
        const finalPosition = applyDraggedPosition(button, dragState.left, dragState.top, true);
        dragState.left = finalPosition.left;
        dragState.top = finalPosition.top;
        suppressNextOpen = true;
      }
      if (event && button.hasPointerCapture?.(event.pointerId)) button.releasePointerCapture(event.pointerId);
      dragState = null;
      if (suppressNextOpen) window.setTimeout(() => { suppressNextOpen = false; }, 0);
    };
    button.addEventListener('pointerup', finishDrag);
    button.addEventListener('pointercancel', finishDrag);
    button.addEventListener('lostpointercapture', event => finishDrag(event));
  }
  function render() {
    const modal = host();
    const content = document.getElementById('quiz-blind-box-content');
    if (!modal || !content || !payload) return;
    if (submitted) {
      const result = payload.result || {};
      const attempt = result.attempt || {};
      content.innerHTML = `<div class="quiz-card-head"><div><div class="quiz-card-title">今日答题完成</div><div class="quiz-card-desc">知识积累比猜测涨跌更重要</div></div><button class="quiz-close" data-quiz-close>×</button></div><div class="quiz-result-score">${escapeHtml(attempt.score || 0)} 分</div><div class="quiz-muted">答对 ${escapeHtml(attempt.correct_count || 0)} / ${escapeHtml(attempt.total_count || 0)} 题</div><div style="margin-top:16px">${(result.answers || []).map(item => `<div class="quiz-result-row"><strong>${item.is_correct ? '回答正确' : '需要复习'} · ${escapeHtml(item.question_text)}</strong><div class="quiz-muted">正确答案：${escapeHtml(item.correct_answer)}。${escapeHtml(item.explanation)}</div></div>`).join('')}</div>`;
      return;
    }
    const questions = payload.questions || [];
    const question = questions[index];
    if (!question) return;
    content.innerHTML = `<div class="quiz-card-head"><div><div class="quiz-card-title">今日股市问答</div><div class="quiz-card-desc">${escapeHtml(question.category)} · ${escapeHtml(question.difficulty)} · 每日 5 题</div></div><button class="quiz-close" data-quiz-close>×</button></div><div class="quiz-progress">第 ${index + 1} / ${questions.length} 题</div><div class="quiz-question">${escapeHtml(question.question_text)}</div><div class="quiz-options">${(question.options || []).map(option => `<button class="quiz-option ${answers[question.id] === option.key ? 'selected' : ''}" data-quiz-answer="${escapeHtml(option.key)}">${escapeHtml(option.key)}. ${escapeHtml(option.text)}</button>`).join('')}</div><div class="quiz-actions"><button class="quiz-button" data-quiz-next ${answers[question.id] ? '' : 'disabled'}>${index === questions.length - 1 ? '提交答案' : '下一题'}</button></div>`;
  }
  async function open() {
    const modal = host();
    if (!modal) return;
    modal.classList.add('is-open');
    const content = document.getElementById('quiz-blind-box-content');
    content.innerHTML = '<div class="quiz-muted">正在打开今日盲盒...</div>';
    try {
      const response = await fetch('/api/quiz/daily?tenant=' + encodeURIComponent(tenantSlug()), {credentials:'same-origin'});
      const next = await response.json();
      if (!response.ok || !next.ok) throw new Error(next.error || 'quiz_load_failed');
      payload = next;
      if (payload.attempt && payload.attempt.completed_at) {
        const resultResponse = await fetch('/api/quiz/daily', {credentials:'same-origin'});
        if (!resultResponse.ok) throw new Error('quiz_history_unavailable');
        content.innerHTML = '<div class="quiz-card-head"><div><div class="quiz-card-title">本次答题完成</div><div class="quiz-card-desc">可以再次打开盲盒，新的答题记录会单独保存</div></div><button class="quiz-close" data-quiz-close>×</button></div><div class="quiz-result-score">' + escapeHtml(payload.attempt.score || 0) + ' 分</div><div class="quiz-muted">本次答题记录已保存</div><div class="quiz-actions"><button class="quiz-button" data-quiz-retry>再做一次</button></div>';
        return;
      }
      const startResponse = await fetch('/api/quiz/daily/start', {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tenant_slug:tenantSlug(), quiz_date:payload.quiz_date})});
      const startPayload = await startResponse.json();
      if (startResponse.ok && startPayload.ok) payload.attempt = startPayload.attempt;
      index = 0; answers = {}; submitted = false; render();
    } catch (error) { content.innerHTML = '<div class="quiz-card-title">盲盒暂时无法打开</div><div class="quiz-muted" style="margin-top:10px">请先登录后再试。</div><div class="quiz-actions"><button class="quiz-button" data-quiz-close>关闭</button></div>'; }
  }
  async function next() {
    const questions = payload.questions || [];
    if (!answers[questions[index].id]) return;
    if (index < questions.length - 1) { index += 1; render(); return; }
    const response = await fetch('/api/quiz/daily/submit', {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tenant_slug:tenantSlug(), quiz_date:payload.quiz_date, attempt_id:payload.attempt && payload.attempt.id, answers:answers})});
    const result = await response.json();
    if (!response.ok || !result.ok) { window.alert('提交失败，请稍后重试'); return; }
    payload.result = result.result; submitted = true; render();
  }
  async function retry() {
    const response = await fetch('/api/quiz/daily/start', {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify({tenant_slug:tenantSlug(), quiz_date:payload.quiz_date})});
    const result = await response.json();
    if (!response.ok || !result.ok) { window.alert('暂时无法重新开始，请稍后重试'); return; }
    payload.attempt = result.attempt; index = 0; answers = {}; submitted = false; render();
  }
  document.addEventListener('click', event => {
    if (event.target.closest('[data-quiz-open]')) {
      if (suppressNextOpen) { suppressNextOpen = false; return; }
      open();
    }
    if (event.target.closest('[data-quiz-close]') || event.target === host()) close();
    const option = event.target.closest('[data-quiz-answer]');
    if (option && payload && !submitted) { answers[payload.questions[index].id] = option.dataset.quizAnswer; render(); }
    if (event.target.closest('[data-quiz-next]')) next();
    if (event.target.closest('[data-quiz-retry]')) retry();
  });
  document.addEventListener('DOMContentLoaded', () => {
    bindBlindBoxDrag();
    positionH5BlindBox();
  });
  window.addEventListener('resize', positionH5BlindBox, {passive:true});
  window.addEventListener('orientationchange', positionH5BlindBox, {passive:true});
  if (window.visualViewport) window.visualViewport.addEventListener('resize', positionH5BlindBox, {passive:true});
})();
