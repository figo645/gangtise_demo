#!/usr/bin/env python3
"""Standalone 5051 console for full local-to-target database migration.

Only full migration, cancellation, rollback, status, and logs are exposed.
Incremental packages, simulation imports, destructive clears, and environment
copy shortcuts are intentionally not part of this service.
"""

import hashlib
import os
import secrets
import sys
from functools import wraps
from hmac import compare_digest
from pathlib import Path

from flask import Flask, jsonify, request, session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.domain.database_release_services import (  # noqa: E402
    build_database_release_overview,
    cancel_database_release,
    get_database_release_log,
    generate_database_release_delta,
    review_database_release_delta,
    scan_database_release_delta,
    start_database_release_delta,
    list_database_release_rollbacks,
    start_database_release,
    start_database_rollback,
)

APP_HOST = os.environ.get("DATA_IMPORT_WEB_HOST", os.environ.get("DATABASE_RELEASE_WEB_HOST", "127.0.0.1"))
APP_PORT = int(os.environ.get("DATA_IMPORT_WEB_PORT", os.environ.get("DATABASE_RELEASE_WEB_PORT", "5051")))


def _load_database_release_secret_key():
    configured = str(
        os.environ.get("DATA_IMPORT_WEB_SECRET_KEY")
        or os.environ.get("DATABASE_RELEASE_WEB_SECRET_KEY")
        or ""
    ).strip()
    if configured:
        return configured
    secret_file = Path(
        os.environ.get("DATA_IMPORT_WEB_SECRET_FILE")
        or os.environ.get("DATABASE_RELEASE_WEB_SECRET_FILE")
        or str(ROOT / ".deploy" / "database_release_web.secret")
    )
    try:
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        existing = secret_file.read_text(encoding="utf-8").strip() if secret_file.exists() else ""
        if len(existing) >= 32:
            return existing
        generated = secrets.token_urlsafe(48)
        secret_file.write_text(generated + "\n", encoding="utf-8")
        secret_file.chmod(0o600)
        return generated
    except OSError:
        return hashlib.sha256(str(ROOT).encode("utf-8")).hexdigest()


app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")
app.config.update(
    SECRET_KEY=_load_database_release_secret_key(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=os.environ.get("DATA_IMPORT_WEB_COOKIE_SECURE", "0") == "1",
)


def _csrf_token():
    token = session.get("data_import_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["data_import_csrf_token"] = token
    return token


def _require_csrf(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        supplied = request.headers.get("X-Data-Import-CSRF-Token", "")
        if not supplied or not compare_digest(supplied, session.get("data_import_csrf_token", "")):
            return jsonify({"ok": False, "error": "csrf_validation_failed"}), 403
        return fn(*args, **kwargs)

    return wrapped


@app.after_request
def _security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'"
    return response


@app.get("/")
def index():
    rendered = PAGE.replace("__CSRF_TOKEN__", _csrf_token())
    return rendered.replace("<body>", _CSRF_RECOVERY + "<body>", 1)


@app.get("/api/csrf")
def csrf():
    return jsonify({"ok": True, "csrf_token": _csrf_token()})


@app.get("/api/overview")
def overview():
    release_overview = build_database_release_overview()
    return jsonify({
        "ok": True,
        "mode": "full_and_diff_migration",
        "release_targets": release_overview["targets"],
        "job": release_overview["job"],
    })


@app.get("/api/diff/scan")
def diff_scan():
    target = request.args.get("target") or "staging"
    try:
        return jsonify({"ok": True, "scan": scan_database_release_delta(target)})
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/diff/review")
@_require_csrf
def diff_review():
    payload = request.get_json(silent=True) or {}
    try:
        review = review_database_release_delta(
            payload.get("target") or "staging",
            include_schema=payload.get("include_schema", True) is True,
            include_master_data=payload.get("include_master_data", True) is True,
            include_runtime_data=payload.get("include_runtime_data", False) is True,
        )
        return jsonify({"ok": True, "review": review})
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/diff/generate")
@_require_csrf
def diff_generate():
    payload = request.get_json(silent=True) or {}
    try:
        result = generate_database_release_delta(
            payload.get("target") or "staging",
            include_schema=payload.get("include_schema", True) is True,
            include_master_data=payload.get("include_master_data", True) is True,
            include_runtime_data=payload.get("include_runtime_data", False) is True,
        )
        return jsonify({"ok": True, "result": result}), 201
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/diff/release")
@_require_csrf
def diff_release():
    payload = request.get_json(silent=True) or {}
    try:
        job = start_database_release_delta(
            payload.get("target") or "staging",
            payload.get("report_path"),
            payload.get("diff_fingerprint"),
            payload.get("package_ids") or [],
            confirm_production=payload.get("confirm_production") is True,
        )
        return jsonify({"ok": True, "job": job}), 202
    except ValueError as exc:
        error = str(exc)
        return jsonify({"ok": False, "error": error}), 409 if error in {"database_release_job_running", "database_release_diff_stale"} else 400


@app.post("/api/release")
@_require_csrf
def release():
    payload = request.get_json(silent=True) or {}
    target = str(payload.get("target") or "").strip().lower()
    try:
        job = start_database_release(
            target,
            package_id=payload.get("package_id"),
            confirm_production=target == "production" and payload.get("confirm_production") is True,
        )
    except ValueError as exc:
        error = str(exc)
        return jsonify({"ok": False, "error": error}), 409 if error == "database_release_job_running" else 400
    return jsonify({"ok": True, "job": job}), 202


@app.post("/api/cancel")
@_require_csrf
def cancel_release():
    try:
        job = cancel_database_release((request.get_json(silent=True) or {}).get("job_id"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True, "job": job}), 202


@app.get("/api/rollbacks")
def rollbacks():
    try:
        records = list_database_release_rollbacks(request.args.get("target") or "staging")
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "records": records})


@app.post("/api/rollback")
@_require_csrf
def rollback():
    payload = request.get_json(silent=True) or {}
    target = str(payload.get("target") or "").strip().lower()
    try:
        job = start_database_rollback(
            target,
            payload.get("backup_name"),
            confirm_production=target == "production" and payload.get("confirm_production") is True,
        )
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    return jsonify({"ok": True, "job": job}), 202


@app.get("/api/log")
def log():
    return app.response_class(get_database_release_log(), mimetype="text/plain; charset=utf-8")


_CSRF_RECOVERY = r"""<script>
(function () {
  const originalFetch = window.fetch.bind(window);
  window.fetch = async function (input, options) {
    const response = await originalFetch(input, options);
    if (response.status !== 403) return response;
    let body;
    try { body = await response.clone().json(); } catch (error) { return response; }
    if (!body || body.error !== 'csrf_validation_failed') return response;
    const tokenResponse = await originalFetch('/api/csrf', {cache: 'no-store', credentials: 'same-origin'});
    const tokenBody = await tokenResponse.json();
    if (!tokenResponse.ok || !tokenBody.csrf_token) return response;
    const retryOptions = Object.assign({}, options || {});
    const headers = new Headers((options && options.headers) || {});
    headers.set('X-Data-Import-CSRF-Token', tokenBody.csrf_token);
    retryOptions.headers = headers;
    retryOptions.credentials = 'same-origin';
    return originalFetch(input, retryOptions);
  };
})();
</script>"""


PAGE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>数据库迁移 · 5051</title>
<style>
:root{--ink:#172b4d;--muted:#667085;--line:#d9e2ec;--paper:#f5f8fb;--blue:#1769aa;--red:#b42318}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:14px ui-sans-serif,system-ui,"PingFang SC",sans-serif}.shell{max-width:1120px;margin:0 auto;padding:28px 20px}.head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;border-bottom:1px solid var(--line);padding-bottom:20px}.head h1{margin:0;font-size:24px}.head p{margin:8px 0 0;color:var(--muted);line-height:1.7}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:18px}.panel{background:#fff;border:1px solid var(--line);border-radius:8px;padding:18px}.panel h2{font-size:16px;margin:0 0 12px}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:end}.field{display:grid;gap:6px;min-width:240px;color:var(--muted);font-size:12px;flex:1}select{height:40px;border:1px solid var(--line);border-radius:6px;padding:0 10px;background:#fff;color:var(--ink);font:inherit}button{border:1px solid var(--blue);border-radius:6px;background:#fff;color:var(--blue);padding:10px 14px;font:600 13px inherit;cursor:pointer}button.primary{background:var(--blue);color:#fff}button.danger{border-color:var(--red);color:var(--red)}button:disabled{opacity:.48;cursor:wait}.notice{margin-top:12px;color:var(--muted);font-size:12px;line-height:1.75}.warning{background:#fff8e8;border:1px solid #f0d58a;color:#7a5510;border-radius:6px;padding:11px 12px;font-size:12px;line-height:1.7}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px}.stat{padding:12px;background:#f8fbfe;border:1px solid #e6edf3;border-radius:6px}.stat b{display:block;font-size:16px;margin-top:5px}.stat span{font-size:11px;color:var(--muted)}.rollback{padding:12px 0;border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:10px;align-items:center}.rollback:first-child{border-top:0}.meta{font-size:12px;color:var(--muted);margin-top:5px;line-height:1.5}pre{min-height:180px;max-height:380px;overflow:auto;background:#11253b;color:#dceafa;padding:14px;border-radius:6px;white-space:pre-wrap;font:12px/1.65 ui-monospace,monospace}.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);padding:10px 15px;background:#16283d;color:#fff;border-radius:6px;opacity:0;transition:.2s;pointer-events:none}.toast.show{opacity:1}.modal{position:fixed;inset:0;background:rgba(18,35,55,.42);display:none;place-items:center;padding:20px}.modal.show{display:grid}.modal .panel{width:min(480px,100%)}@media(max-width:760px){.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}.head{display:block}.head button{margin-top:14px}.rollback{align-items:flex-start;flex-direction:column}}
</style><style>
.workflow{display:grid;gap:8px;margin-top:14px}.workflow-title{font-size:12px;font-weight:700;color:var(--ink);margin-bottom:2px}.workflow-node{display:grid;grid-template-columns:28px 1fr auto;gap:9px;align-items:center;padding:9px 10px;border:1px solid var(--line);border-radius:7px;background:#fbfdff}.workflow-node.active{border-color:#6aa8d8;background:#eef7ff}.workflow-node.succeeded{border-color:#9bcab1;background:#f1faf4}.workflow-node.failed{border-color:#e5aaa4;background:#fff5f3}.workflow-dot{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;background:#e7edf2;color:var(--muted);font-size:11px;font-weight:700}.workflow-node.active .workflow-dot{background:var(--blue);color:#fff}.workflow-node.succeeded .workflow-dot{background:#218653;color:#fff}.workflow-node.failed .workflow-dot{background:var(--red);color:#fff}.workflow-label{font-weight:600;font-size:12px}.workflow-detail{font-size:11px;color:var(--muted);margin-top:2px}.workflow-status{font-size:11px;color:var(--muted);white-space:nowrap}.workflow-node.active .workflow-status{color:var(--blue);font-weight:700}.workflow-node.succeeded .workflow-status{color:#218653}.workflow-node.failed .workflow-status{color:var(--red)}
</style></head><body><main class="shell">
<header class="head"><div><h1>数据库迁移</h1><p>5051 数据迁移控制台。支持本地到 Staging 或 Production 的全量替换与差异迁移。</p></div><button type="button" onclick="load(true)">刷新状态</button></header>
<section class="stats" id="stats"></section>
<section class="panel" style="margin-top:18px"><h2>执行全量迁移</h2><div class="row"><label class="field">目标环境<select id="releaseTarget"></select></label><button id="release" class="primary" type="button" onclick="startRelease()">开始全量迁移</button><button id="cancel" class="danger" type="button" onclick="cancelRelease()" hidden>停止任务</button></div><div class="warning" style="margin-top:14px">迁移会先导出本地完整数据库，在目标环境创建临时数据库并执行结构更新；目标环境的用户及其关联业务数据会在切换前恢复。校验未通过时不会替换目标数据库，原数据库会保留为回滚点。</div></section>
<section class="panel" style="margin-top:18px"><h2>执行差异迁移</h2><div class="row"><label class="field">目标环境<select id="diffTarget"></select></label><label style="display:flex;gap:6px;align-items:center;font-size:12px;color:var(--muted)"><input id="diffSchema" type="checkbox" checked> 表结构</label><label style="display:flex;gap:6px;align-items:center;font-size:12px;color:var(--muted)"><input id="diffMaster" type="checkbox" checked> 主数据</label><label style="display:flex;gap:6px;align-items:center;font-size:12px;color:var(--muted)"><input id="diffRuntime" type="checkbox"> 业务数据</label><button type="button" onclick="scanDiff()">扫描差异</button><button type="button" onclick="reviewDiff()">生成预览</button><button class="primary" type="button" onclick="generateDiff()">生成差异计划</button><button id="diffRelease" class="primary" type="button" onclick="releaseDiff()" disabled>确认执行差异迁移</button></div><div id="diffStatus" class="notice">先扫描并生成差异计划。差异报告指纹变化后，旧计划会自动失效。业务数据默认不包含用户运行数据。</div><div id="diffWorkflow" class="workflow" aria-live="polite"></div><pre id="diffReport" style="max-height:260px;min-height:100px;margin-top:12px">暂无差异报告</pre></section>
<section class="grid"><section class="panel"><h2>任务进度</h2><div id="progress" class="notice">正在读取...</div><h2 style="margin-top:22px">回滚记录</h2><div id="rollbacks" class="notice">正在读取...</div></section><section class="panel"><h2>迁移日志</h2><pre id="log">正在读取...</pre></section></section>
</main><div id="toast" class="toast"></div><div id="modal" class="modal"><div class="panel"><h2 id="modalTitle">确认操作</h2><div id="modalBody"></div></div></div>
<script>
const csrf='__CSRF_TOKEN__';let overview={},submitting=false,poll=null;const $=id=>document.getElementById(id);function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function toast(t){$('toast').textContent=t;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),3000)}async function api(path,opt={}){const r=await fetch(path,{...opt,credentials:'same-origin',headers:{'Content-Type':'application/json','X-Data-Import-CSRF-Token':csrf,...(opt.headers||{})}});const d=await r.json().catch(()=>({}));if(!r.ok||d.ok===false)throw Object.assign(new Error(d.error||('HTTP '+r.status)),{status:r.status});return d}function busy(){return submitting||['queued','running','cancelling'].includes(String((overview.job||{}).status||''))}function render(){const j=overview.job||{},targets=overview.release_targets||[];const selected=$('releaseTarget').value||'staging';$('releaseTarget').innerHTML=targets.map(x=>'<option value="'+esc(x.name)+'" '+(x.name===selected?'selected':'')+'>'+esc(x.label)+' ('+esc(x.host)+'/'+esc(x.database)+')</option>').join('');if(typeof renderDiffTargets==='function')renderDiffTargets();const p=j.progress||{};$('stats').innerHTML=[['任务状态',j.status||'idle',j.target||'暂无任务'],['任务编号',j.id||'--',j.started_at||'--'],['当前阶段',p.message||'等待执行',p.updated_at||'--'],['迁移模式','全量迁移','增量、模拟导入和清空功能已移除']].map(x=>'<div class="stat"><span>'+esc(x[0])+'</span><b>'+esc(x[1])+'</b><span>'+esc(x[2])+'</span></div>').join('');$('progress').innerHTML='<b>'+esc(p.message||'暂无运行中的迁移任务')+'</b><div class="meta">状态：'+esc(j.status||'idle')+' · 完成步骤：'+esc(p.completed_steps||0)+' / '+esc(p.total_steps||1)+'</div>';$('release').disabled=busy();$('cancel').hidden=!['queued','running','cancelling'].includes(j.status);if(poll)clearTimeout(poll);if(['queued','running','cancelling'].includes(j.status))poll=setTimeout(()=>load(),1000)}async function loadLog(){try{$('log').textContent=await fetch('/api/log',{cache:'no-store',credentials:'same-origin'}).then(r=>r.text());$('log').scrollTop=$('log').scrollHeight}catch(e){$('log').textContent='日志读取失败：'+e.message}}async function loadRollbacks(){const host=$('rollbacks');const rows=await Promise.all((overview.release_targets||[]).map(async t=>{try{return {t,d:await api('/api/rollbacks?target='+encodeURIComponent(t.name))}}catch(e){return {t,error:e.message}}}));host.innerHTML=rows.map(x=>'<div class="rollback"><div><b>'+esc(x.t.label)+'</b><div class="meta">'+(x.error?esc(x.error):((x.d.records||[]).map(r=>esc(r.name+' · '+r.size)).join('<br>')||'暂无可回滚备份'))+'</div></div>'+(x.error?'':(x.d.records||[]).map(r=>'<button type="button" onclick="requestRollback(\''+esc(x.t.name)+'\',\''+esc(r.name)+'\')">回滚</button>').join(' '))+'</div>').join('')}async function load(message){try{overview=await api('/api/overview');render();await Promise.all([loadLog(),loadRollbacks()]);if(message)toast('状态已刷新')}catch(e){toast('读取状态失败：'+e.message)}}function closeModal(){$('modal').classList.remove('show')}function confirmAction(title,body,ok,button='确认执行'){$('modalTitle').textContent=title;$('modalBody').innerHTML='<p class="notice">'+body+'</p><div class="row" style="justify-content:flex-end;margin-top:14px"><button type="button" onclick="closeModal()">取消</button><button class="primary" type="button" id="confirmAction">'+button+'</button></div>';$('modal').classList.add('show');$('confirmAction').onclick=async()=>{closeModal();await ok()}}function startRelease(){if(busy())return toast('已有全量迁移任务正在执行');const target=$('releaseTarget').value;const production=target==='production';confirmAction('确认全量迁移','将本地完整数据库迁移到 '+esc(target)+'。目标环境用户及关联业务数据会被保留，目标数据库会先备份。'+(production?' 这是 Production 操作，请确认目标环境和备份策略。':''),async()=>{submitting=true;render();try{await api('/api/release',{method:'POST',body:JSON.stringify({target,package_id:'__full__',confirm_production:production})});toast('全量迁移任务已创建');await load()}catch(e){toast('迁移未启动：'+e.message)}finally{submitting=false;render()}},'确认开始')}function cancelRelease(){const j=overview.job||{};if(!j.id)return;confirmAction('停止全量迁移','仅允许在数据库切换前停止。已经切换完成的任务不能通过停止回退，请使用回滚。',async()=>{try{await api('/api/cancel',{method:'POST',body:JSON.stringify({job_id:j.id})});toast('已发送停止请求');await load()}catch(e){toast('停止失败：'+e.message)}} ,'确认停止')}function requestRollback(target,name){confirmAction('确认数据库回滚','将 '+esc(target)+' 回滚到 '+esc(name)+'。',async()=>{try{await api('/api/rollback',{method:'POST',body:JSON.stringify({target,backup_name:name,confirm_production:target==='production'})});toast('回滚任务已创建');await load()}catch(e){toast('回滚未启动：'+e.message)}} ,'确认回滚')}load();
</script>
<script>
function renderJobWorkflow(){
  const job=overview.job||{}, progress=job.progress||{};
  let host=document.getElementById('workflowNodes');
  if(!host){host=document.createElement('div');host.id='workflowNodes';host.className='workflow';const progressHost=document.getElementById('progress');if(progressHost)progressHost.insertAdjacentElement('afterend',host)}
  const nodes=Array.isArray(progress.workflow)?progress.workflow:[];
  if(!nodes.length){host.innerHTML='<div class="workflow-title">任务流程</div><div class="workflow-detail">尚无正在执行的迁移任务</div>';return}
  host.innerHTML='<div class="workflow-title">'+esc(job.operation==='release'?'差异迁移流程':'全量迁移流程')+' · 已完成 '+esc(progress.workflow_completed_steps||0)+' / '+esc(progress.workflow_total_steps||nodes.length)+' 步</div>'+nodes.map(n=>'<div class="workflow-node '+esc(n.status)+'"><div class="workflow-dot">'+esc(n.order)+'</div><div><div class="workflow-label">'+esc(n.label)+'</div><div class="workflow-detail">'+(n.status==='active'?'正在执行':n.status==='succeeded'?'已完成':n.status==='failed'?'失败':'等待执行')+'</div></div><div class="workflow-status">'+(n.status==='active'?'进行中':n.status==='succeeded'?'完成':n.status==='failed'?'失败':'未开始')+'</div></div>').join('');
}
setInterval(renderJobWorkflow,500);renderJobWorkflow();
</script>
<script>
let diffPlan=null;
function diffPayload(){return {target:document.getElementById('diffTarget').value||'staging',include_schema:document.getElementById('diffSchema').checked,include_master_data:document.getElementById('diffMaster').checked,include_runtime_data:document.getElementById('diffRuntime').checked}}
function diffText(value){return JSON.stringify(value,null,2)}
async function diffRequest(path,body){return api(path,{method:'POST',body:JSON.stringify(body)})}
function renderDiffTargets(){const source=document.getElementById('releaseTarget'),target=document.getElementById('diffTarget');if(!source||!target)return;target.innerHTML=source.innerHTML}
async function scanDiff(){try{renderDiffTargets();const target=document.getElementById('diffTarget').value||'staging';const data=await api('/api/diff/scan?target='+encodeURIComponent(target));document.getElementById('diffReport').textContent=diffText(data.scan);document.getElementById('diffStatus').textContent='差异扫描完成。扫描只读，不会修改目标数据库。';}catch(e){document.getElementById('diffStatus').textContent='差异扫描失败：'+e.message}}
async function reviewDiff(){try{const data=await diffRequest('/api/diff/review',diffPayload());document.getElementById('diffReport').textContent=diffText(data.review);document.getElementById('diffStatus').textContent=data.review.blockers.length?'预览发现阻断项，不能生成执行计划。':'预览完成，可生成差异计划。';}catch(e){document.getElementById('diffStatus').textContent='差异预览失败：'+e.message}}
async function generateDiff(){try{const data=await diffRequest('/api/diff/generate',diffPayload());diffPlan=data.result;document.getElementById('diffRelease').disabled=!diffPlan.generated_packages.length||diffPlan.blockers.length>0;document.getElementById('diffReport').textContent=diffText(diffPlan);document.getElementById('diffStatus').textContent=diffPlan.blockers.length?'差异计划存在阻断项，禁止执行。':'差异计划已生成，执行前会重新核验报告指纹。';}catch(e){document.getElementById('diffStatus').textContent='差异计划生成失败：'+e.message}}
async function releaseDiff(){if(!diffPlan||!diffPlan.generated_packages.length)return;const target=diffPlan.target;const production=target==='production';if(!window.confirm('确认执行 '+target+' 差异迁移？执行前会重新扫描并核验差异报告，目标用户数据不会被本地用户表覆盖。'))return;try{const data=await diffRequest('/api/diff/release',{target,report_path:diffPlan.report_path,diff_fingerprint:diffPlan.diff_fingerprint,package_ids:diffPlan.generated_packages.map(item=>item.id),confirm_production:production});document.getElementById('diffStatus').textContent='差异迁移任务已创建：'+(data.job||{}).id;document.getElementById('diffRelease').disabled=true;await load()}catch(e){document.getElementById('diffStatus').textContent='差异迁移未启动：'+e.message}}
renderDiffTargets();
let diffFlowStage=0;
const diffFlowNodes=[['scan','扫描差异'],['review','生成预览'],['plan','生成差异计划'],['execute','执行差异迁移'],['completed','完成与记录']];
function renderDiffWorkflow(){
  const host=document.getElementById('diffWorkflow');if(!host)return;
  host.innerHTML='<div class="workflow-title">差异迁移流程 · 已完成 '+Math.min(diffFlowStage,4)+' / 5 步</div>'+diffFlowNodes.map((n,i)=>{const status=i<diffFlowStage?'succeeded':i===diffFlowStage?'active':'pending';return '<div class="workflow-node '+status+'"><div class="workflow-dot">'+(i+1)+'</div><div><div class="workflow-label">'+n[1]+'</div><div class="workflow-detail">'+(status==='active'?'当前节点':status==='succeeded'?'已完成':'等待执行')+'</div></div><div class="workflow-status">'+(status==='active'?'进行中':status==='succeeded'?'完成':'未开始')+'</div></div>'}).join('');
}
const originalScanDiff=scanDiff,originalReviewDiff=reviewDiff,originalGenerateDiff=generateDiff,originalReleaseDiff=releaseDiff;
scanDiff=async function(){diffFlowStage=0;renderDiffWorkflow();try{await originalScanDiff();diffFlowStage=1;renderDiffWorkflow()}catch(e){renderDiffWorkflow();throw e}};
reviewDiff=async function(){diffFlowStage=Math.max(diffFlowStage,1);renderDiffWorkflow();try{await originalReviewDiff();diffFlowStage=2;renderDiffWorkflow()}catch(e){renderDiffWorkflow();throw e}};
generateDiff=async function(){diffFlowStage=Math.max(diffFlowStage,2);renderDiffWorkflow();try{await originalGenerateDiff();diffFlowStage=3;renderDiffWorkflow()}catch(e){renderDiffWorkflow();throw e}};
releaseDiff=async function(){diffFlowStage=Math.max(diffFlowStage,3);renderDiffWorkflow();try{await originalReleaseDiff();diffFlowStage=4;renderDiffWorkflow()}catch(e){renderDiffWorkflow();throw e}};
renderDiffWorkflow();
</script></body></html>'''


if __name__ == "__main__":
    app.run(host=APP_HOST, port=APP_PORT, debug=False, use_reloader=False)
