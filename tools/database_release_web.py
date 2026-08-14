#!/usr/bin/env python3
"""Local data-import console.

Run from the repository root with: python3 tools/database_release_web.py

This service owns database data import operations: full local-to-remote
sync, versioned incremental packages, rollback, and tagged simulation data.
It listens on 127.0.0.1:5051 by default.
"""

import os
import secrets
import sys
import time
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
    create_simulation_batch,
    delete_simulation_batch,
    get_database_release_log,
    list_database_release_targets,
    list_database_release_rollbacks,
    list_simulation_batches,
    start_database_release,
    start_database_rollback,
)


APP_HOST = os.environ.get("DATA_IMPORT_WEB_HOST", os.environ.get("DATABASE_RELEASE_WEB_HOST", "127.0.0.1"))
APP_PORT = int(os.environ.get("DATA_IMPORT_WEB_PORT", os.environ.get("DATABASE_RELEASE_WEB_PORT", "5051")))
UNLOCK_TTL_SECONDS = 10 * 60
MAX_UNLOCK_FAILURES = 5
UNLOCK_FAILURE_WINDOW_SECONDS = 5 * 60
_unlock_failures = {}

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("DATA_IMPORT_WEB_SECRET_KEY") or os.environ.get("DATABASE_RELEASE_WEB_SECRET_KEY") or secrets.token_urlsafe(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=os.environ.get("DATA_IMPORT_WEB_COOKIE_SECURE", "0") == "1",
)


def _operation_password():
    return str(os.environ.get("DATA_IMPORT_OPERATION_PASSWORD") or os.environ.get("DATABASE_RELEASE_OPERATION_PASSWORD") or "536953")


def _is_unlocked():
    return float(session.get("data_import_unlock_until") or 0) > time.time()


def _csrf_token():
    token = session.get("data_import_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["data_import_csrf_token"] = token
    return token


def _client_key():
    return request.remote_addr or "unknown"


def _unlock_rate_limited():
    attempts = [stamp for stamp in _unlock_failures.get(_client_key(), []) if stamp > time.time() - UNLOCK_FAILURE_WINDOW_SECONDS]
    _unlock_failures[_client_key()] = attempts
    return len(attempts) >= MAX_UNLOCK_FAILURES


def _record_unlock_failure():
    _unlock_failures.setdefault(_client_key(), []).append(time.time())


def _require_csrf(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        supplied = request.headers.get("X-Data-Import-CSRF-Token", "")
        if not supplied or not compare_digest(supplied, session.get("data_import_csrf_token", "")):
            return jsonify({"ok": False, "error": "csrf_validation_failed"}), 403
        return fn(*args, **kwargs)
    return wrapped


def _require_unlock(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not _is_unlocked():
            return jsonify({"ok": False, "error": "operation_password_required"}), 423
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
    return PAGE.replace("__CSRF_TOKEN__", _csrf_token())


@app.get("/api/overview")
def overview():
    release_overview = build_database_release_overview()
    return jsonify({
        "ok": True,
        "unlocked": _is_unlocked(),
        "targets": list_database_release_targets(include_local=True),
        "release_targets": release_overview["targets"],
        "packages": release_overview["packages"],
        "job": release_overview["job"],
    })


@app.post("/api/release")
@_require_csrf
@_require_unlock
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
@_require_unlock
def cancel_release():
    try:
        return jsonify({"ok": True, "job": cancel_database_release((request.get_json(silent=True) or {}).get("job_id"))}), 202
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409


@app.get("/api/rollbacks")
def rollbacks():
    try:
        return jsonify({"ok": True, "records": list_database_release_rollbacks(request.args.get("target") or "staging")})
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/rollback")
@_require_csrf
@_require_unlock
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


@app.get("/api/batches")
def batches():
    target = str(request.args.get("target") or "local").strip().lower()
    try:
        return jsonify({"ok": True, "batches": list_simulation_batches(target)})
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"data_import_query_failed:{exc}"}), 503


@app.post("/api/batches")
@_require_csrf
@_require_unlock
def create_batch():
    payload = request.get_json(silent=True) or {}
    try:
        batch_code = create_simulation_batch(payload.get("target") or "local", payload.get("tenant_slug") or "laowang")
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"data_import_create_failed:{exc}"}), 503
    return jsonify({"ok": True, "batch_code": batch_code}), 201


@app.delete("/api/batches/<batch_code>")
@_require_csrf
@_require_unlock
def delete_batch(batch_code):
    payload = request.get_json(silent=True) or {}
    try:
        delete_simulation_batch(payload.get("target") or "local", batch_code)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"data_import_delete_failed:{exc}"}), 503
    return jsonify({"ok": True})


@app.post("/api/unlock")
@_require_csrf
def unlock():
    if _unlock_rate_limited():
        return jsonify({"ok": False, "error": "too_many_password_attempts"}), 429
    password = str((request.get_json(silent=True) or {}).get("password") or "")
    if not compare_digest(password, _operation_password()):
        _record_unlock_failure()
        return jsonify({"ok": False, "error": "operation_password_invalid"}), 403
    _unlock_failures.pop(_client_key(), None)
    session["data_import_unlock_until"] = time.time() + UNLOCK_TTL_SECONDS
    return jsonify({"ok": True, "ttl_seconds": UNLOCK_TTL_SECONDS})


LEGACY_SIMULATION_ONLY_PAGE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>数据导入控制台</title><style>
:root{--ink:#16283d;--muted:#65778a;--line:#d8e2ec;--paper:#f6f9fc;--blue:#1769aa;--red:#b42318;--gold:#a76d10}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:14px ui-sans-serif,system-ui,"PingFang SC",sans-serif}.shell{max-width:1040px;margin:0 auto;padding:30px 22px}.head{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;border-bottom:1px solid var(--line);padding-bottom:20px}.head h1{margin:0;font-size:22px}.head p{margin:7px 0 0;color:var(--muted);line-height:1.6}.grid{display:grid;grid-template-columns:.9fr 1.1fr;gap:18px;margin-top:22px}.panel{background:#fff;border:1px solid var(--line);border-radius:8px;padding:18px}.panel h2{font-size:15px;margin:0 0 12px}.row{display:flex;gap:9px;flex-wrap:wrap;align-items:end}.field{display:grid;gap:6px;min-width:220px;color:var(--muted);font-size:12px}select,input{height:38px;border:1px solid var(--line);border-radius:6px;padding:0 10px;font:inherit;color:var(--ink);background:#fff}button{border:1px solid var(--blue);border-radius:6px;background:#fff;color:var(--blue);padding:9px 13px;font:600 13px inherit;cursor:pointer}button.primary{background:var(--blue);color:#fff}button.danger{border-color:var(--red);color:var(--red)}button:disabled{opacity:.48;cursor:wait}.notice{margin-top:12px;color:var(--muted);font-size:12px;line-height:1.65}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.stat{padding:12px;background:#f8fbfe;border:1px solid #e6edf3;border-radius:6px}.stat b{display:block;font-size:16px;margin-top:5px}.stat span{font-size:11px;color:var(--muted)}.batch{padding:13px 0;border-top:1px solid var(--line);display:flex;gap:12px;justify-content:space-between;align-items:center}.batch:first-child{border-top:0}.code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink);word-break:break-all}.meta{font-size:12px;color:var(--muted);margin-top:5px;line-height:1.55}.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);padding:10px 15px;background:#16283d;color:#fff;border-radius:6px;opacity:0;transition:.2s;pointer-events:none}.toast.show{opacity:1}.modal{position:fixed;inset:0;background:rgba(18,35,55,.42);display:none;place-items:center;padding:20px}.modal.show{display:grid}.modal .panel{width:min(420px,100%)}@media(max-width:760px){.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}.head{display:block}.batch{align-items:flex-start;flex-direction:column}}
</style><body><main class="shell"><header class="head"><div><h1>数据导入控制台</h1><p>独立运行于本机 5051 端口。当前仅管理带“模拟数据”标签的财经老王粉丝、自选股与评论批次。</p></div><button onclick="load(true)">刷新状态</button></header><section class="stats" id="stats" style="margin-top:20px"></section><section class="grid"><div class="panel"><h2>新建导入批次</h2><div class="row"><label class="field">目标数据库<select id="target" onchange="loadBatches()"></select></label><button id="create" class="primary" onclick="createBatch()">导入模拟粉丝数据</button></div><div class="notice">每次导入会新建独立批次，包含模拟账户、粉丝自选股及评论，所有记录均带有“模拟数据”标签、批次编号和时间戳。删除时只会删除该批次的模拟记录。</div></div><div class="panel"><h2>已导入批次</h2><div id="batches" class="notice">正在读取...</div></div></section></main><div id="toast" class="toast"></div><div id="modal" class="modal"><div class="panel"><h2 id="modalTitle">验证操作口令</h2><div id="modalBody"></div></div></div><script>
"""; r"""
const csrf='__CSRF_TOKEN__';let overview={},submitting=false;const $=id=>document.getElementById(id);function esc(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}function toast(t){$('toast').textContent=t;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),2800)}async function api(path,opt={}){const r=await fetch(path,{...opt,headers:{'Content-Type':'application/json','X-Data-Import-CSRF-Token':csrf,...(opt.headers||{})}});const d=await r.json().catch(()=>({}));if(!r.ok||d.ok===false)throw Object.assign(new Error(d.error||('HTTP '+r.status)),{status:r.status});return d}function render(){const targets=overview.targets||[],selected=$('target').value||'local';$('target').innerHTML=targets.map(x=>`<option value="${esc(x.name)}" ${x.name===selected?'selected':''}>${esc(x.label)} (${esc(x.host)}/${esc(x.database)})</option>`).join('');$('stats').innerHTML=[['导入范围','模拟数据','不会写入或覆盖真实业务数据'],['当前授权',overview.unlocked?'已验证':'未验证',overview.unlocked?'可创建或删除批次':'执行操作时需要口令'],['可用目标',String(targets.length),'本地、Staging、Production 使用相同流程']].map(x=>`<div class="stat"><span>${x[0]}</span><b>${x[1]}</b><span>${x[2]}</span></div>`).join('');$('create').disabled=submitting}async function loadBatches(){const target=$('target').value||'local';const host=$('batches');host.textContent='正在读取导入批次...';try{const d=await api('/api/batches?target='+encodeURIComponent(target),{headers:{}});const rows=d.batches||[];host.innerHTML=rows.length?rows.map(x=>`<div class="batch"><div><div class="code">${esc(x.batch_code)}</div><div class="meta">${esc(x.tenant_slug)} · ${esc(x.created_at)} · 账号 ${x.user_count||0} · 自选股 ${x.watchlist_count||0} · 评论 ${x.comment_count||0}</div></div><button class="danger" onclick="requestDelete('${esc(x.batch_code)}')">删除批次</button></div>`).join(''):'当前目标尚未导入模拟数据。'}catch(e){host.textContent='读取失败：'+e.message}}async function load(message){try{overview=await api('/api/overview',{headers:{}});render();await loadBatches();if(message)toast('状态已刷新')}catch(e){toast('读取状态失败：'+e.message)}}function closeModal(){$('modal').classList.remove('show');window.pending=null}function askPassword(next){$('modalTitle').textContent='验证数据导入操作口令';$('modalBody').innerHTML='<p class="notice">请输入操作口令后继续。授权仅在当前会话有效 10 分钟。</p><input id="password" type="password" autocomplete="one-time-code" placeholder="操作口令"><div class="row" style="justify-content:flex-end;margin-top:14px"><button onclick="closeModal()">取消</button><button class="primary" onclick="unlockAndRun()">验证并继续</button></div>';window.pending=next;$('modal').classList.add('show');setTimeout(()=>$('password').focus(),0)}async function unlockAndRun(){const p=$('password').value;if(!p)return toast('请输入操作口令');try{await api('/api/unlock',{method:'POST',body:JSON.stringify({password:p})});overview.unlocked=true;render();const next=window.pending;closeModal();await next()}catch(e){toast(e.status===429?'口令尝试过多，请稍后再试':'操作口令错误')}}function confirmAction(title,body,ok){$('modalTitle').textContent=title;$('modalBody').innerHTML=`<p class="notice">${body}</p><div class="row" style="justify-content:flex-end;margin-top:14px"><button onclick="closeModal()">取消</button><button class="primary" onclick="window.confirmedAction()">确认</button></div>`;window.confirmedAction=async()=>{closeModal();await ok()};$('modal').classList.add('show')}function protectedAction(action){if(overview.unlocked)return action();askPassword(action)}function createBatch(){if(submitting)return;const target=$('target').value||'local';protectedAction(()=>confirmAction('确认导入模拟数据',`将在 ${target} 创建一组带独立批次编号的模拟粉丝、自选股与评论。`,async()=>{submitting=true;render();try{const d=await api('/api/batches',{method:'POST',body:JSON.stringify({target,tenant_slug:'laowang'})});toast('数据导入完成：'+d.batch_code);await loadBatches()}catch(e){toast('导入失败：'+e.message)}finally{submitting=false;render()}}))}function requestDelete(batch){const target=$('target').value||'local';protectedAction(()=>confirmAction('确认删除导入批次',`确定删除 ${batch} 的全部模拟账户、自选股与评论吗？真实数据不会受影响。`,async()=>{try{await api('/api/batches/'+encodeURIComponent(batch),{method:'DELETE',body:JSON.stringify({target})});toast('导入批次已删除');await loadBatches()}catch(e){toast('删除失败：'+e.message)}}))}load();</script></body></html>"""


PAGE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>数据导入控制台</title><style>
:root{--ink:#16283d;--muted:#65778a;--line:#d8e2ec;--paper:#f6f9fc;--blue:#1769aa;--red:#b42318;--gold:#a76d10}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:14px ui-sans-serif,system-ui,"PingFang SC",sans-serif}.shell{max-width:1180px;margin:0 auto;padding:30px 22px}.head{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;border-bottom:1px solid var(--line);padding-bottom:20px}.head h1{margin:0;font-size:22px}.head p{margin:7px 0 0;color:var(--muted);line-height:1.6}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:22px}.panel{background:#fff;border:1px solid var(--line);border-radius:8px;padding:18px}.panel h2{font-size:15px;margin:0 0 12px}.row{display:flex;gap:9px;flex-wrap:wrap;align-items:end}.field{display:grid;gap:6px;min-width:210px;color:var(--muted);font-size:12px}select,input{height:38px;border:1px solid var(--line);border-radius:6px;padding:0 10px;font:inherit;color:var(--ink);background:#fff}button{border:1px solid var(--blue);border-radius:6px;background:#fff;color:var(--blue);padding:9px 13px;font:600 13px inherit;cursor:pointer}button.primary{background:var(--blue);color:#fff}button.danger{border-color:var(--red);color:var(--red)}button:disabled{opacity:.48;cursor:wait}.notice{margin-top:12px;color:var(--muted);font-size:12px;line-height:1.65}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.stat{padding:12px;background:#f8fbfe;border:1px solid #e6edf3;border-radius:6px}.stat b{display:block;font-size:16px;margin-top:5px}.stat span{font-size:11px;color:var(--muted)}.batch,.rollback{padding:13px 0;border-top:1px solid var(--line);display:flex;gap:12px;justify-content:space-between;align-items:center}.batch:first-child,.rollback:first-child{border-top:0}.code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink);word-break:break-all}.meta{font-size:12px;color:var(--muted);margin-top:5px;line-height:1.55}pre{min-height:190px;max-height:360px;overflow:auto;background:#11253b;color:#dceafa;padding:14px;border-radius:6px;white-space:pre-wrap;font:12px/1.65 ui-monospace,monospace}.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);padding:10px 15px;background:#16283d;color:#fff;border-radius:6px;opacity:0;transition:.2s;pointer-events:none}.toast.show{opacity:1}.modal{position:fixed;inset:0;background:rgba(18,35,55,.42);display:none;place-items:center;padding:20px}.modal.show{display:grid}.modal .panel{width:min(440px,100%)}@media(max-width:760px){.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}.head{display:block}.batch,.rollback{align-items:flex-start;flex-direction:column}}
</style><body><main class="shell"><header class="head"><div><h1>数据导入控制台</h1><p>本机 5051 端口。全量同步、版本化增量导入、回滚和模拟数据导入由同一个控制台管理。</p></div><button onclick="load(true)">刷新状态</button></header><section class="stats" id="stats" style="margin-top:20px"></section><section class="grid"><div class="panel"><h2>数据库全量与增量导入</h2><div class="row"><label class="field">目标环境<select id="releaseTarget"></select></label><label class="field">导入内容<select id="package"></select></label><button id="release" class="primary" onclick="startRelease()">开始导入</button><button id="cancel" class="danger" onclick="cancelRelease()" hidden>取消任务</button></div><div class="notice">“当前完整数据库”会导出本地开发库、恢复至远端临时库、执行校验后切换，并保留原库作为回滚点。增量包从 <code>database_release_packages</code> 按日期和版本顺序执行。</div><h2 style="margin-top:22px">回滚记录</h2><div id="rollbacks" class="notice">正在读取...</div></div><div class="panel"><h2>模拟数据导入</h2><div class="row"><label class="field">目标数据库<select id="simulationTarget" onchange="loadBatches()"></select></label><button id="create" class="primary" onclick="createBatch()">导入模拟粉丝数据</button></div><div class="notice">每次导入新建独立批次，包含模拟账户、粉丝自选股和评论。所有记录有“模拟数据”标签、批次编号和时间戳；删除仅影响指定批次。</div><h2 style="margin-top:22px">已导入模拟批次</h2><div id="batches" class="notice">正在读取...</div></div></section><section class="panel" style="margin-top:18px"><h2>导入任务日志</h2><pre id="log">正在读取...</pre></section></main><div id="toast" class="toast"></div><div id="modal" class="modal"><div class="panel"><h2 id="modalTitle">验证操作口令</h2><div id="modalBody"></div></div></div><script>
const csrf='__CSRF_TOKEN__';let overview={},submitting=false,poll=null;const $=id=>document.getElementById(id);function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function toast(t){$('toast').textContent=t;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),2800)}async function api(path,opt={}){const r=await fetch(path,{...opt,headers:{'Content-Type':'application/json','X-Data-Import-CSRF-Token':csrf,...(opt.headers||{})}});const d=await r.json().catch(()=>({}));if(!r.ok||d.ok===false)throw Object.assign(new Error(d.error||('HTTP '+r.status)),{status:r.status});return d}function busy(){return submitting||['queued','running','cancelling'].includes(String((overview.job||{}).status||''))}function render(){const j=overview.job||{},targets=overview.targets||[],releaseTargets=overview.release_targets||[];const target=$('simulationTarget').value||'local',releaseTarget=$('releaseTarget').value||'staging',pkg=$('package').value||'__pending__';$('simulationTarget').innerHTML=targets.map(x=>`<option value="${esc(x.name)}" ${x.name===target?'selected':''}>${esc(x.label)} (${esc(x.host)}/${esc(x.database)})</option>`).join('');$('releaseTarget').innerHTML=releaseTargets.map(x=>`<option value="${esc(x.name)}" ${x.name===releaseTarget?'selected':''}>${esc(x.label)} (${esc(x.host)}/${esc(x.database)})</option>`).join('');const type={schema:'表结构增量',master_data:'主数据增量',data:'业务数据增量'};$('package').innerHTML=`<option value="__pending__">全部剩余增量（推荐）</option><option value="__full__">当前完整数据库（全量同步）</option>`+(overview.packages||[]).map(x=>`<option value="${esc(x.id)}" ${x.id===pkg?'selected':''}>${esc(`${x.date} · ${x.version} · ${type[x.type]||x.type} · ${x.title||''}`)}</option>`).join('');$('stats').innerHTML=[['任务状态',j.status||'idle',j.target||'暂无任务'],['任务编号',j.id||'--',j.started_at||'--'],['当前授权',overview.unlocked?'已验证':'未验证',overview.unlocked?'有效 10 分钟':'执行操作时验证'],['可用增量包',String((overview.packages||[]).length),'可选单个版本或全部待执行版本']].map(x=>`<div class="stat"><span>${x[0]}</span><b>${esc(x[1])}</b><span>${esc(x[2])}</span></div>`).join('');$('release').disabled=busy();$('create').disabled=submitting;$('cancel').hidden=!['queued','running'].includes(j.status);if(poll)clearTimeout(poll);if(['queued','running','cancelling'].includes(j.status))poll=setTimeout(()=>load(),1000)}async function loadLog(){try{$('log').textContent=await fetch('/api/log',{cache:'no-store'}).then(r=>r.text());$('log').scrollTop=$('log').scrollHeight}catch(e){$('log').textContent='日志读取失败：'+e.message}}async function loadRollbacks(){const host=$('rollbacks'),targets=overview.release_targets||[];const rows=await Promise.all(targets.map(async t=>{try{return {t,d:await api('/api/rollbacks?target='+encodeURIComponent(t.name),{headers:{}})}}catch(e){return {t,error:e.message}}}));host.innerHTML=rows.map(x=>`<div class="rollback"><div><b>${esc(x.t.label)}</b><div class="meta">${x.error?esc(x.error):(x.d.records||[]).map(r=>esc(`${r.name} · ${r.size}`)).join('<br>')||'暂无可回滚备份'}</div></div>${x.error?'':(x.d.records||[]).map(r=>`<button onclick="requestRollback('${esc(x.t.name)}','${esc(r.name)}')">回滚</button>`).join(' ')}</div>`).join('')}async function loadBatches(){const host=$('batches'),target=$('simulationTarget').value||'local';host.textContent='正在读取导入批次...';try{const d=await api('/api/batches?target='+encodeURIComponent(target),{headers:{}}),rows=d.batches||[];host.innerHTML=rows.length?rows.map(x=>`<div class="batch"><div><div class="code">${esc(x.batch_code)}</div><div class="meta">${esc(x.tenant_slug)} · ${esc(x.created_at)} · 账号 ${x.user_count||0} · 自选股 ${x.watchlist_count||0} · 评论 ${x.comment_count||0}</div></div><button class="danger" onclick="requestDelete('${esc(x.batch_code)}')">删除批次</button></div>`).join(''):'当前目标尚未导入模拟数据。'}catch(e){host.textContent='读取失败：'+e.message}}async function load(message){try{overview=await api('/api/overview',{headers:{}});render();await Promise.all([loadLog(),loadRollbacks(),loadBatches()]);if(message)toast('状态已刷新')}catch(e){toast('读取状态失败：'+e.message)}}function closeModal(){$('modal').classList.remove('show');window.pending=null}function askPassword(next){$('modalTitle').textContent='验证数据导入操作口令';$('modalBody').innerHTML='<p class="notice">请输入操作口令后继续。授权仅在当前会话有效 10 分钟。</p><input id="password" type="password" autocomplete="one-time-code" placeholder="操作口令"><div class="row" style="justify-content:flex-end;margin-top:14px"><button onclick="closeModal()">取消</button><button class="primary" onclick="unlockAndRun()">验证并继续</button></div>';window.pending=next;$('modal').classList.add('show');setTimeout(()=>$('password').focus(),0)}async function unlockAndRun(){const p=$('password').value;if(!p)return toast('请输入操作口令');try{await api('/api/unlock',{method:'POST',body:JSON.stringify({password:p})});overview.unlocked=true;render();const next=window.pending;closeModal();await next()}catch(e){toast(e.status===429?'口令尝试过多，请稍后再试':'操作口令错误')}}function confirmAction(title,body,ok){$('modalTitle').textContent=title;$('modalBody').innerHTML=`<p class="notice">${body}</p><div class="row" style="justify-content:flex-end;margin-top:14px"><button onclick="closeModal()">取消</button><button class="primary" onclick="window.confirmedAction()">确认</button></div>`;window.confirmedAction=async()=>{closeModal();await ok()};$('modal').classList.add('show')}function protectedAction(action){if(overview.unlocked)return action();askPassword(action)}function startRelease(){if(busy())return toast('已有数据导入任务正在执行');const target=$('releaseTarget').value,pkg=$('package').value,label=pkg==='__full__'?'本地完整数据库':pkg==='__pending__'?'全部剩余增量':'所选增量包';protectedAction(()=>confirmAction('确认开始数据导入',`确定将 ${label} 导入 ${target} 吗？全量同步会在目标端保留回滚备份。`,async()=>{submitting=true;render();try{await api('/api/release',{method:'POST',body:JSON.stringify({target,package_id:pkg,confirm_production:target==='production'})});toast('数据导入任务已创建');await load()}catch(e){toast('导入未启动：'+e.message)}finally{submitting=false;render()}}))}function cancelRelease(){const j=overview.job||{};if(!j.id)return;protectedAction(()=>confirmAction('确认取消数据导入','已完成的增量包不会自动回退。',async()=>{try{await api('/api/cancel',{method:'POST',body:JSON.stringify({job_id:j.id})});toast('已发送取消请求');await load()}catch(e){toast('取消失败：'+e.message)}}))}function requestRollback(target,name){protectedAction(()=>confirmAction('确认数据库回滚',`确定将 ${target} 回滚到 ${name} 吗？`,async()=>{try{await api('/api/rollback',{method:'POST',body:JSON.stringify({target,backup_name:name,confirm_production:target==='production'})});toast('回滚任务已创建');await load()}catch(e){toast('回滚未启动：'+e.message)}}))}function createBatch(){if(submitting)return;const target=$('simulationTarget').value||'local';protectedAction(()=>confirmAction('确认导入模拟数据',`将在 ${target} 创建一组带独立批次编号的模拟粉丝、自选股和评论。`,async()=>{submitting=true;render();try{const d=await api('/api/batches',{method:'POST',body:JSON.stringify({target,tenant_slug:'laowang'})});toast('模拟数据已导入：'+d.batch_code);await loadBatches()}catch(e){toast('导入失败：'+e.message)}finally{submitting=false;render()}}))}function requestDelete(batch){const target=$('simulationTarget').value||'local';protectedAction(()=>confirmAction('确认删除导入批次',`确定删除 ${batch} 的全部模拟账户、自选股和评论吗？真实数据不会受影响。`,async()=>{try{await api('/api/batches/'+encodeURIComponent(batch),{method:'DELETE',body:JSON.stringify({target})});toast('导入批次已删除');await loadBatches()}catch(e){toast('删除失败：'+e.message)}}))}load();</script></body></html>"""


if __name__ == "__main__":
    app.run(host=APP_HOST, port=APP_PORT, debug=False, use_reloader=False)
