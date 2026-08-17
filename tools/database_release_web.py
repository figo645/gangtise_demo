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
    get_database_release_package_plan,
    get_database_release_package_review,
    generate_database_release_delta,
    list_database_release_targets,
    list_database_release_rollbacks,
    list_simulation_batches,
    start_database_release,
    start_database_release_packages,
    start_database_rollback,
    start_production_to_staging_sync,
    scan_database_release_delta,
    review_database_release_delta,
)


APP_HOST = os.environ.get("DATA_IMPORT_WEB_HOST", os.environ.get("DATABASE_RELEASE_WEB_HOST", "127.0.0.1"))
APP_PORT = int(os.environ.get("DATA_IMPORT_WEB_PORT", os.environ.get("DATABASE_RELEASE_WEB_PORT", "5051")))
app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")
app.config.update(
    SECRET_KEY=os.environ.get("DATA_IMPORT_WEB_SECRET_KEY") or os.environ.get("DATABASE_RELEASE_WEB_SECRET_KEY") or secrets.token_urlsafe(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=os.environ.get("DATA_IMPORT_WEB_COOKIE_SECURE", "0") == "1",
)


def _is_unlocked():
    """The standalone console no longer uses a second execution password."""
    return True


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


def _require_unlock(fn):
    """Compatibility decorator retained for route readability; no password gate remains."""
    return fn


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


@app.get("/api/release-plan")
def release_plan():
    try:
        return jsonify({"ok": True, **get_database_release_package_plan(request.args.get("target") or "staging")})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.get("/api/diff-scan")
def diff_scan():
    try:
        return jsonify({"ok": True, **scan_database_release_delta(request.args.get("target") or "staging")})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Unable to scan database release delta")
        return jsonify({"ok": False, "error": "database_release_diff_scan_failed", "detail": str(exc)}), 503


@app.get("/api/delta-review")
def delta_review():
    target = str(request.args.get("target") or "staging").strip().lower()
    try:
        return jsonify({
            "ok": True,
            **review_database_release_delta(
                target,
                include_schema=request.args.get("include_schema", "true").lower() != "false",
                include_master_data=request.args.get("include_master_data", "true").lower() != "false",
                include_runtime_data=request.args.get("include_runtime_data", "false").lower() == "true",
            ),
        })
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Unable to prepare database release delta review")
        return jsonify({"ok": False, "error": "database_release_delta_review_failed", "detail": str(exc)}), 503


@app.get("/api/package-review")
def package_review():
    try:
        return jsonify({"ok": True, **get_database_release_package_review(request.args.get("package_id"))})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:
        app.logger.exception("Unable to read database release package")
        return jsonify({"ok": False, "error": "database_release_package_review_failed", "detail": str(exc)}), 503


@app.post("/api/generate-delta")
@_require_csrf
@_require_unlock
def generate_delta():
    payload = request.get_json(silent=True) or {}
    target = str(payload.get("target") or "").strip().lower()
    try:
        result = generate_database_release_delta(
            target,
            include_schema=payload.get("include_schema") is not False,
            include_master_data=payload.get("include_master_data") is not False,
            include_runtime_data=payload.get("include_runtime_data") is True,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Unable to generate database release delta")
        return jsonify({"ok": False, "error": "database_release_delta_generation_failed", "detail": str(exc)}), 500
    return jsonify({"ok": True, **result}), 201


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


@app.post("/api/reviewed-release")
@_require_csrf
@_require_unlock
def reviewed_release():
    payload = request.get_json(silent=True) or {}
    target = str(payload.get("target") or "").strip().lower()
    try:
        job = start_database_release_packages(
            target,
            package_ids=payload.get("package_ids") or [],
            confirm_production=target == "production" and payload.get("confirm_production") is True,
        )
    except ValueError as exc:
        error = str(exc)
        return jsonify({"ok": False, "error": error}), 409 if error == "database_release_job_running" else 400
    return jsonify({"ok": True, "job": job}), 202


@app.post("/api/production-to-staging-sync")
@_require_csrf
@_require_unlock
def production_to_staging_sync():
    try:
        job = start_production_to_staging_sync()
    except ValueError as exc:
        error = str(exc)
        return jsonify({"ok": False, "error": error}), 409 if error == "database_release_job_running" else 400
    except Exception as exc:
        app.logger.exception("Unable to create Production-to-Staging sync task")
        return jsonify({"ok": False, "error": "production_to_staging_task_create_failed", "detail": str(exc)}), 500
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
    return jsonify({"ok": True, "password_required": False, "message": "数据库操作无需独立口令。"})


LEGACY_SIMULATION_ONLY_PAGE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>数据导入控制台</title><style>
:root{--ink:#16283d;--muted:#65778a;--line:#d8e2ec;--paper:#f6f9fc;--blue:#1769aa;--red:#b42318;--gold:#a76d10}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:14px ui-sans-serif,system-ui,"PingFang SC",sans-serif}.shell{max-width:1040px;margin:0 auto;padding:30px 22px}.head{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;border-bottom:1px solid var(--line);padding-bottom:20px}.head h1{margin:0;font-size:22px}.head p{margin:7px 0 0;color:var(--muted);line-height:1.6}.grid{display:grid;grid-template-columns:.9fr 1.1fr;gap:18px;margin-top:22px}.panel{background:#fff;border:1px solid var(--line);border-radius:8px;padding:18px}.panel h2{font-size:15px;margin:0 0 12px}.row{display:flex;gap:9px;flex-wrap:wrap;align-items:end}.field{display:grid;gap:6px;min-width:220px;color:var(--muted);font-size:12px}select,input{height:38px;border:1px solid var(--line);border-radius:6px;padding:0 10px;font:inherit;color:var(--ink);background:#fff}button{border:1px solid var(--blue);border-radius:6px;background:#fff;color:var(--blue);padding:9px 13px;font:600 13px inherit;cursor:pointer}button.primary{background:var(--blue);color:#fff}button.danger{border-color:var(--red);color:var(--red)}button:disabled{opacity:.48;cursor:wait}.notice{margin-top:12px;color:var(--muted);font-size:12px;line-height:1.65}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.stat{padding:12px;background:#f8fbfe;border:1px solid #e6edf3;border-radius:6px}.stat b{display:block;font-size:16px;margin-top:5px}.stat span{font-size:11px;color:var(--muted)}.batch{padding:13px 0;border-top:1px solid var(--line);display:flex;gap:12px;justify-content:space-between;align-items:center}.batch:first-child{border-top:0}.code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink);word-break:break-all}.meta{font-size:12px;color:var(--muted);margin-top:5px;line-height:1.55}.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);padding:10px 15px;background:#16283d;color:#fff;border-radius:6px;opacity:0;transition:.2s;pointer-events:none}.toast.show{opacity:1}.modal{position:fixed;inset:0;background:rgba(18,35,55,.42);display:none;place-items:center;padding:20px}.modal.show{display:grid}.modal .panel{width:min(420px,100%)}@media(max-width:760px){.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}.head{display:block}.batch{align-items:flex-start;flex-direction:column}}
</style><body><main class="shell"><header class="head"><div><h1>数据导入控制台</h1><p>独立运行于本机 5051 端口。当前仅管理带“模拟数据”标签的财经老王粉丝、自选股与评论批次。</p></div><button onclick="load(true)">刷新状态</button></header><section class="stats" id="stats" style="margin-top:20px"></section><section class="grid"><div class="panel"><h2>新建导入批次</h2><div class="row"><label class="field">目标数据库<select id="target" onchange="loadBatches()"></select></label><button id="create" class="primary" onclick="createBatch()">导入模拟粉丝数据</button></div><div class="notice">每次导入会新建独立批次，包含模拟账户、粉丝自选股及评论，所有记录均带有“模拟数据”标签、批次编号和时间戳。删除时只会删除该批次的模拟记录。</div></div><div class="panel"><h2>已导入批次</h2><div id="batches" class="notice">正在读取...</div></div></section></main><div id="toast" class="toast"></div><div id="modal" class="modal"><div class="panel"><h2 id="modalTitle">验证操作口令</h2><div id="modalBody"></div></div></div><script>
"""; r"""
const csrf='__CSRF_TOKEN__';let overview={},submitting=false;const $=id=>document.getElementById(id);function esc(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}function toast(t){$('toast').textContent=t;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),2800)}async function api(path,opt={}){const r=await fetch(path,{...opt,headers:{'Content-Type':'application/json','X-Data-Import-CSRF-Token':csrf,...(opt.headers||{})}});const d=await r.json().catch(()=>({}));if(!r.ok||d.ok===false)throw Object.assign(new Error(d.error||('HTTP '+r.status)),{status:r.status});return d}function render(){const targets=overview.targets||[],selected=$('target').value||'local';$('target').innerHTML=targets.map(x=>`<option value="${esc(x.name)}" ${x.name===selected?'selected':''}>${esc(x.label)} (${esc(x.host)}/${esc(x.database)})</option>`).join('');$('stats').innerHTML=[['导入范围','模拟数据','不会写入或覆盖真实业务数据'],['当前授权',overview.unlocked?'已验证':'未验证',overview.unlocked?'可创建或删除批次':'执行操作时需要口令'],['可用目标',String(targets.length),'本地、Staging、Production 使用相同流程']].map(x=>`<div class="stat"><span>${x[0]}</span><b>${x[1]}</b><span>${x[2]}</span></div>`).join('');$('create').disabled=submitting}async function loadBatches(){const target=$('target').value||'local';const host=$('batches');host.textContent='正在读取导入批次...';try{const d=await api('/api/batches?target='+encodeURIComponent(target),{headers:{}});const rows=d.batches||[];host.innerHTML=rows.length?rows.map(x=>`<div class="batch"><div><div class="code">${esc(x.batch_code)}</div><div class="meta">${esc(x.tenant_slug)} · ${esc(x.created_at)} · 账号 ${x.user_count||0} · 自选股 ${x.watchlist_count||0} · 评论 ${x.comment_count||0}</div></div><button class="danger" onclick="requestDelete('${esc(x.batch_code)}')">删除批次</button></div>`).join(''):'当前目标尚未导入模拟数据。'}catch(e){host.textContent='读取失败：'+e.message}}async function load(message){try{overview=await api('/api/overview',{headers:{}});render();await loadBatches();if(message)toast('状态已刷新')}catch(e){toast('读取状态失败：'+e.message)}}function closeModal(){$('modal').classList.remove('show');window.pending=null}function askPassword(next){$('modalTitle').textContent='验证数据导入操作口令';$('modalBody').innerHTML='<p class="notice">请输入操作口令后继续。授权仅在当前会话有效 10 分钟。</p><input id="password" type="password" autocomplete="one-time-code" placeholder="操作口令"><div class="row" style="justify-content:flex-end;margin-top:14px"><button onclick="closeModal()">取消</button><button class="primary" onclick="unlockAndRun()">验证并继续</button></div>';window.pending=next;$('modal').classList.add('show');setTimeout(()=>$('password').focus(),0)}async function unlockAndRun(){const p=$('password').value;if(!p)return toast('请输入操作口令');try{await api('/api/unlock',{method:'POST',body:JSON.stringify({password:p})});overview.unlocked=true;render();const next=window.pending;closeModal();await next()}catch(e){toast(e.status===429?'口令尝试过多，请稍后再试':'操作口令错误')}}function confirmAction(title,body,ok){$('modalTitle').textContent=title;$('modalBody').innerHTML=`<p class="notice">${body}</p><div class="row" style="justify-content:flex-end;margin-top:14px"><button onclick="closeModal()">取消</button><button class="primary" onclick="window.confirmedAction()">确认</button></div>`;window.confirmedAction=async()=>{closeModal();await ok()};$('modal').classList.add('show')}function protectedAction(action){if(overview.unlocked)return action();askPassword(action)}function createBatch(){if(submitting)return;const target=$('target').value||'local';protectedAction(()=>confirmAction('确认导入模拟数据',`将在 ${target} 创建一组带独立批次编号的模拟粉丝、自选股与评论。`,async()=>{submitting=true;render();try{const d=await api('/api/batches',{method:'POST',body:JSON.stringify({target,tenant_slug:'laowang'})});toast('数据导入完成：'+d.batch_code);await loadBatches()}catch(e){toast('导入失败：'+e.message)}finally{submitting=false;render()}}))}function requestDelete(batch){const target=$('target').value||'local';protectedAction(()=>confirmAction('确认删除导入批次',`确定删除 ${batch} 的全部模拟账户、自选股与评论吗？真实数据不会受影响。`,async()=>{try{await api('/api/batches/'+encodeURIComponent(batch),{method:'DELETE',body:JSON.stringify({target})});toast('导入批次已删除');await loadBatches()}catch(e){toast('删除失败：'+e.message)}}))}load();</script></body></html>"""


PAGE = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>数据导入控制台</title><style>
:root{--ink:#16283d;--muted:#65778a;--line:#d8e2ec;--paper:#f6f9fc;--blue:#1769aa;--red:#b42318;--gold:#a76d10}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:14px ui-sans-serif,system-ui,"PingFang SC",sans-serif}.shell{max-width:1180px;margin:0 auto;padding:30px 22px}.head{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;border-bottom:1px solid var(--line);padding-bottom:20px}.head h1{margin:0;font-size:22px}.head p{margin:7px 0 0;color:var(--muted);line-height:1.6}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:22px}.panel{background:#fff;border:1px solid var(--line);border-radius:8px;padding:18px}.panel h2{font-size:15px;margin:0 0 12px}.row{display:flex;gap:9px;flex-wrap:wrap;align-items:end}.field{display:grid;gap:6px;min-width:210px;color:var(--muted);font-size:12px}select,input{height:38px;border:1px solid var(--line);border-radius:6px;padding:0 10px;font:inherit;color:var(--ink);background:#fff}button{border:1px solid var(--blue);border-radius:6px;background:#fff;color:var(--blue);padding:9px 13px;font:600 13px inherit;cursor:pointer}button.primary{background:var(--blue);color:#fff}button.danger{border-color:var(--red);color:var(--red)}button:disabled{opacity:.48;cursor:wait}.notice{margin-top:12px;color:var(--muted);font-size:12px;line-height:1.65}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.stat{padding:12px;background:#f8fbfe;border:1px solid #e6edf3;border-radius:6px}.stat b{display:block;font-size:16px;margin-top:5px}.stat span{font-size:11px;color:var(--muted)}.batch,.rollback{padding:13px 0;border-top:1px solid var(--line);display:flex;gap:12px;justify-content:space-between;align-items:center}.batch:first-child,.rollback:first-child{border-top:0}.code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink);word-break:break-all}.meta{font-size:12px;color:var(--muted);margin-top:5px;line-height:1.55}pre{min-height:190px;max-height:360px;overflow:auto;background:#11253b;color:#dceafa;padding:14px;border-radius:6px;white-space:pre-wrap;font:12px/1.65 ui-monospace,monospace}.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);padding:10px 15px;background:#16283d;color:#fff;border-radius:6px;opacity:0;transition:.2s;pointer-events:none}.toast.show{opacity:1}.modal{position:fixed;inset:0;background:rgba(18,35,55,.42);display:none;place-items:center;padding:20px}.modal.show{display:grid}.modal .panel{width:min(440px,100%)}@media(max-width:760px){.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}.head{display:block}.batch,.rollback{align-items:flex-start;flex-direction:column}}
</style><body><main class="shell"><header class="head"><div><h1>数据导入控制台</h1><p>本机 5051 端口。全量同步、版本化增量导入、回滚和模拟数据导入由同一个控制台管理。</p></div><button onclick="load(true)">刷新状态</button></header><section class="stats" id="stats" style="margin-top:20px"></section><section class="grid"><div class="panel"><h2>数据库全量与增量导入</h2><div class="row"><label class="field">目标环境<select id="releaseTarget"></select></label><label class="field">导入内容<select id="package"></select></label><button id="release" class="primary" onclick="startRelease()">开始导入</button><button id="cancel" class="danger" onclick="cancelRelease()" hidden>取消任务</button></div><div class="notice">“当前完整数据库”会导出本地开发库、恢复至远端临时库、执行校验后切换，并保留原库作为回滚点。增量包从 <code>database_release_packages</code> 按日期和版本顺序执行。</div><h2 style="margin-top:22px">回滚记录</h2><div id="rollbacks" class="notice">正在读取...</div></div><div class="panel"><h2>模拟数据导入</h2><div class="row"><label class="field">目标数据库<select id="simulationTarget" onchange="loadBatches()"></select></label><button id="create" class="primary" onclick="createBatch()">导入模拟粉丝数据</button></div><div class="notice">每次导入新建独立批次，包含模拟账户、粉丝自选股和评论。所有记录有“模拟数据”标签、批次编号和时间戳；删除仅影响指定批次。</div><h2 style="margin-top:22px">已导入模拟批次</h2><div id="batches" class="notice">正在读取...</div></div></section><section class="panel" style="margin-top:18px"><h2>导入任务日志</h2><pre id="log">正在读取...</pre></section></main><div id="toast" class="toast"></div><div id="modal" class="modal"><div class="panel"><h2 id="modalTitle">验证操作口令</h2><div id="modalBody"></div></div></div><script>
const csrf='__CSRF_TOKEN__';let overview={},submitting=false,poll=null;const $=id=>document.getElementById(id);function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function toast(t){$('toast').textContent=t;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),2800)}async function api(path,opt={}){const r=await fetch(path,{...opt,headers:{'Content-Type':'application/json','X-Data-Import-CSRF-Token':csrf,...(opt.headers||{})}});const d=await r.json().catch(()=>({}));if(!r.ok||d.ok===false)throw Object.assign(new Error(d.error||('HTTP '+r.status)),{status:r.status});return d}function busy(){return submitting||['queued','running','cancelling'].includes(String((overview.job||{}).status||''))}function render(){const j=overview.job||{},targets=overview.targets||[],releaseTargets=overview.release_targets||[];const target=$('simulationTarget').value||'local',releaseTarget=$('releaseTarget').value||'staging',pkg=$('package').value||'__pending__';$('simulationTarget').innerHTML=targets.map(x=>`<option value="${esc(x.name)}" ${x.name===target?'selected':''}>${esc(x.label)} (${esc(x.host)}/${esc(x.database)})</option>`).join('');$('releaseTarget').innerHTML=releaseTargets.map(x=>`<option value="${esc(x.name)}" ${x.name===releaseTarget?'selected':''}>${esc(x.label)} (${esc(x.host)}/${esc(x.database)})</option>`).join('');const type={schema:'表结构增量',master_data:'主数据增量',data:'业务数据增量'};$('package').innerHTML=`<option value="__pending__">全部剩余增量（推荐）</option><option value="__full__">当前完整数据库（全量同步）</option>`+(overview.packages||[]).map(x=>`<option value="${esc(x.id)}" ${x.id===pkg?'selected':''}>${esc(`${x.date} · ${x.version} · ${type[x.type]||x.type} · ${x.title||''}`)}</option>`).join('');$('stats').innerHTML=[['任务状态',j.status||'idle',j.target||'暂无任务'],['任务编号',j.id||'--',j.started_at||'--'],['当前授权',overview.unlocked?'已验证':'未验证',overview.unlocked?'有效 10 分钟':'执行操作时验证'],['可用增量包',String((overview.packages||[]).length),'可选单个版本或全部待执行版本']].map(x=>`<div class="stat"><span>${x[0]}</span><b>${esc(x[1])}</b><span>${esc(x[2])}</span></div>`).join('');$('release').disabled=busy();$('create').disabled=submitting;$('cancel').hidden=!['queued','running'].includes(j.status);if(poll)clearTimeout(poll);if(['queued','running','cancelling'].includes(j.status))poll=setTimeout(()=>load(),1000)}async function loadLog(){try{$('log').textContent=await fetch('/api/log',{cache:'no-store'}).then(r=>r.text());$('log').scrollTop=$('log').scrollHeight}catch(e){$('log').textContent='日志读取失败：'+e.message}}async function loadRollbacks(){const host=$('rollbacks'),targets=overview.release_targets||[];const rows=await Promise.all(targets.map(async t=>{try{return {t,d:await api('/api/rollbacks?target='+encodeURIComponent(t.name),{headers:{}})}}catch(e){return {t,error:e.message}}}));host.innerHTML=rows.map(x=>`<div class="rollback"><div><b>${esc(x.t.label)}</b><div class="meta">${x.error?esc(x.error):(x.d.records||[]).map(r=>esc(`${r.name} · ${r.size}`)).join('<br>')||'暂无可回滚备份'}</div></div>${x.error?'':(x.d.records||[]).map(r=>`<button onclick="requestRollback('${esc(x.t.name)}','${esc(r.name)}')">回滚</button>`).join(' ')}</div>`).join('')}async function loadBatches(){const host=$('batches'),target=$('simulationTarget').value||'local';host.textContent='正在读取导入批次...';try{const d=await api('/api/batches?target='+encodeURIComponent(target),{headers:{}}),rows=d.batches||[];host.innerHTML=rows.length?rows.map(x=>`<div class="batch"><div><div class="code">${esc(x.batch_code)}</div><div class="meta">${esc(x.tenant_slug)} · ${esc(x.created_at)} · 账号 ${x.user_count||0} · 自选股 ${x.watchlist_count||0} · 评论 ${x.comment_count||0}</div></div><button class="danger" onclick="requestDelete('${esc(x.batch_code)}')">删除批次</button></div>`).join(''):'当前目标尚未导入模拟数据。'}catch(e){host.textContent='读取失败：'+e.message}}async function load(message){try{overview=await api('/api/overview',{headers:{}});render();await Promise.all([loadLog(),loadRollbacks(),loadBatches()]);if(message)toast('状态已刷新')}catch(e){toast('读取状态失败：'+e.message)}}function closeModal(){$('modal').classList.remove('show');window.pending=null}function askPassword(next){$('modalTitle').textContent='验证数据导入操作口令';$('modalBody').innerHTML='<p class="notice">请输入操作口令后继续。授权仅在当前会话有效 10 分钟。</p><input id="password" type="password" autocomplete="one-time-code" placeholder="操作口令"><div class="row" style="justify-content:flex-end;margin-top:14px"><button onclick="closeModal()">取消</button><button class="primary" onclick="unlockAndRun()">验证并继续</button></div>';window.pending=next;$('modal').classList.add('show');setTimeout(()=>$('password').focus(),0)}async function unlockAndRun(){const p=$('password').value;if(!p)return toast('请输入操作口令');try{await api('/api/unlock',{method:'POST',body:JSON.stringify({password:p})});overview.unlocked=true;render();const next=window.pending;closeModal();await next()}catch(e){toast(e.status===429?'口令尝试过多，请稍后再试':'操作口令错误')}}function confirmAction(title,body,ok){$('modalTitle').textContent=title;$('modalBody').innerHTML=`<p class="notice">${body}</p><div class="row" style="justify-content:flex-end;margin-top:14px"><button onclick="closeModal()">取消</button><button class="primary" onclick="window.confirmedAction()">确认</button></div>`;window.confirmedAction=async()=>{closeModal();await ok()};$('modal').classList.add('show')}function protectedAction(action){if(overview.unlocked)return action();askPassword(action)}function startRelease(){if(busy())return toast('已有数据导入任务正在执行');const target=$('releaseTarget').value,pkg=$('package').value,label=pkg==='__full__'?'本地完整数据库':pkg==='__pending__'?'全部剩余增量':'所选增量包';protectedAction(()=>confirmAction('确认开始数据导入',`确定将 ${label} 导入 ${target} 吗？全量同步会在目标端保留回滚备份。`,async()=>{submitting=true;render();try{await api('/api/release',{method:'POST',body:JSON.stringify({target,package_id:pkg,confirm_production:target==='production'})});toast('数据导入任务已创建');await load()}catch(e){toast('导入未启动：'+e.message)}finally{submitting=false;render()}}))}function cancelRelease(){const j=overview.job||{};if(!j.id)return;protectedAction(()=>confirmAction('确认取消数据导入','已完成的增量包不会自动回退。',async()=>{try{await api('/api/cancel',{method:'POST',body:JSON.stringify({job_id:j.id})});toast('已发送取消请求');await load()}catch(e){toast('取消失败：'+e.message)}}))}function requestRollback(target,name){protectedAction(()=>confirmAction('确认数据库回滚',`确定将 ${target} 回滚到 ${name} 吗？`,async()=>{try{await api('/api/rollback',{method:'POST',body:JSON.stringify({target,backup_name:name,confirm_production:target==='production'})});toast('回滚任务已创建');await load()}catch(e){toast('回滚未启动：'+e.message)}}))}function createBatch(){if(submitting)return;const target=$('simulationTarget').value||'local';protectedAction(()=>confirmAction('确认导入模拟数据',`将在 ${target} 创建一组带独立批次编号的模拟粉丝、自选股和评论。`,async()=>{submitting=true;render();try{const d=await api('/api/batches',{method:'POST',body:JSON.stringify({target,tenant_slug:'laowang'})});toast('模拟数据已导入：'+d.batch_code);await loadBatches()}catch(e){toast('导入失败：'+e.message)}finally{submitting=false;render()}}))}function requestDelete(batch){const target=$('simulationTarget').value||'local';protectedAction(()=>confirmAction('确认删除导入批次',`确定删除 ${batch} 的全部模拟账户、自选股和评论吗？真实数据不会受影响。`,async()=>{try{await api('/api/batches/'+encodeURIComponent(batch),{method:'DELETE',body:JSON.stringify({target})});toast('导入批次已删除');await loadBatches()}catch(e){toast('删除失败：'+e.message)}}))}load();</script></body></html>"""

# Keep this fixed-direction operation separate from ordinary local releases.
# The page string remains self-contained so the 5051 controller has no asset
# build dependency.
PAGE = PAGE.replace(
    '<section class="panel" style="margin-top:18px"><h2>导入任务日志</h2>',
    '<section class="panel" style="margin-top:18px"><h2>Production 覆盖 Staging</h2>'
    '<div class="row"><button id="productionStagingSync" class="danger" onclick="startProductionToStagingSync()">一键导入 Production 到 Staging</button></div>'
    '<div class="notice">固定方向：Production 仅读，Staging 会被完整替换。系统会先在 Staging 创建临时库、恢复 Production 快照并校验；成功后才切换。原 Staging 会保留为可回滚备份。</div>'
    '</section><section class="panel" style="margin-top:18px"><h2>导入任务日志</h2>',
)


# Bootstrap-based operational console. It stays fully local so the release
# controller remains usable on an isolated workstation or server network.
PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>数据库发布控制台</title>
  <link rel="stylesheet" href="/static/vendor/bootstrap.min.css">
  <style>
    :root { --ops-navy:#163a5f; --ops-blue:#2f74c0; --ops-teal:#198d84; --ops-bg:#f4f7fa; --ops-line:#d8e2eb; --ops-muted:#637487; }
    * { box-sizing:border-box; }
    body { min-width:320px; background:var(--ops-bg); color:#21364a; font-family:"PingFang SC","Microsoft YaHei",sans-serif; letter-spacing:0; }
    .ops-navbar { background:var(--ops-navy); box-shadow:0 2px 12px rgba(12,43,75,.18); }
    .ops-brand { color:#fff; font-weight:750; font-size:16px; }
    .ops-brand-mark { display:inline-grid; place-items:center; width:27px; height:27px; margin-right:8px; border:1px solid rgba(255,255,255,.34); border-radius:6px; font-size:12px; }
    .ops-page { max-width:1320px; padding-top:28px; padding-bottom:46px; }
    .ops-eyebrow { color:var(--ops-blue); font-size:12px; font-weight:750; }
    .ops-title { margin:3px 0 0; font-size:28px; font-weight:750; color:#17344f; }
    .ops-subtitle { margin:8px 0 0; color:var(--ops-muted); font-size:14px; }
    .ops-panel { border:1px solid var(--ops-line); border-radius:8px; box-shadow:none; background:#fff; }
    .ops-panel .card-header { padding:16px 18px; border-bottom:1px solid var(--ops-line); background:#fff; }
    .ops-panel .card-body { padding:18px; }
    .ops-section-title { margin:0; color:#17344f; font-size:15px; font-weight:750; }
    .ops-section-copy { margin:4px 0 0; color:var(--ops-muted); font-size:12px; line-height:1.6; }
    .ops-stat { min-height:104px; padding:17px; border:1px solid var(--ops-line); border-radius:7px; background:#fff; }
    .ops-stat-label { color:var(--ops-muted); font-size:12px; }
    .ops-stat-value { margin-top:6px; color:#17344f; font-size:21px; font-weight:750; line-height:1.1; word-break:break-word; }
    .ops-stat-note { margin-top:8px; color:var(--ops-muted); font-size:11px; line-height:1.45; }
    .ops-release-form { display:grid; grid-template-columns:minmax(180px,1fr) minmax(250px,1.35fr) auto; gap:12px; align-items:end; }
    .ops-release-plan { display:flex; flex-wrap:wrap; gap:7px; align-items:center; margin-top:12px; color:var(--ops-muted); font-size:12px; }
    .ops-danger-panel { border-color:#e4b6b3; background:#fffafb; }
    .ops-danger-panel .card-header { border-bottom-color:#efd1cf; background:#fff8f8; }
    .ops-log { min-height:280px; max-height:520px; margin:0; overflow:auto; padding:16px; border-radius:6px; background:#10263c; color:#dceaf5; white-space:pre-wrap; font:12px/1.68 ui-monospace,SFMono-Regular,Menlo,monospace; }
    .ops-timeline { max-height:316px; overflow:auto; }
    .ops-event { display:grid; grid-template-columns:10px minmax(0,1fr); column-gap:10px; padding:0 0 13px; }
    .ops-event:last-child { padding-bottom:0; }
    .ops-event-dot { width:9px; height:9px; margin-top:5px; border-radius:50%; background:#8aa5bd; }
    .ops-event-dot.active { background:var(--ops-blue); }.ops-event-dot.succeeded { background:var(--ops-teal); }.ops-event-dot.failed { background:#b42318; }.ops-event-dot.cancelled { background:#896817; }
    .ops-event-title { color:#28455f; font-size:12px; font-weight:700; }
    .ops-event-detail,.ops-event-time { margin-top:3px; color:var(--ops-muted); font-size:11px; line-height:1.5; }
    .ops-list-row { display:flex; gap:14px; align-items:center; justify-content:space-between; padding:13px 0; border-top:1px solid #e5edf4; }
    .ops-list-row:first-child { padding-top:0; border-top:0; }
    .ops-rollback-scroll { max-height:520px; overflow-y:auto; padding-right:2px; }
    .ops-rollback-group + .ops-rollback-group { margin-top:18px; }
    .ops-rollback-heading { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:8px; color:#27455f; font-size:13px; font-weight:750; }
    .ops-rollback-item { display:flex; align-items:center; justify-content:space-between; gap:12px; min-width:0; padding:11px 12px; border-color:#e5edf4; }
    .ops-rollback-item-copy { min-width:0; }
    .ops-rollback-size { margin-top:3px; color:var(--ops-muted); font-size:11px; }
    .ops-code { color:#294964; font:12px ui-monospace,SFMono-Regular,Menlo,monospace; overflow-wrap:anywhere; }
    .ops-empty { color:var(--ops-muted); font-size:13px; padding:9px 0; }
    .modal-content { border:0; border-radius:8px; box-shadow:0 18px 44px rgba(17,43,69,.25); }
    .modal-header { border-bottom-color:var(--ops-line); }.modal-footer { border-top-color:var(--ops-line); }
    .toast-container { z-index:1090; }
    @media (max-width:991px) { .ops-release-form { grid-template-columns:1fr 1fr; }.ops-release-form .ops-action-group { grid-column:1/-1; } }
    @media (max-width:575px) { .ops-page { padding-top:20px; }.ops-title { font-size:23px; }.ops-release-form { grid-template-columns:1fr; }.ops-release-form .ops-action-group { grid-column:auto; }.ops-list-row { align-items:flex-start; flex-direction:column; }.ops-rollback-item { align-items:flex-start; flex-direction:column; }.ops-rollback-item .btn { width:100%; }.ops-navbar .btn { margin-top:8px; } }
  </style>
</head>
<body>
  <nav class="navbar ops-navbar navbar-dark">
    <div class="container ops-page py-0">
      <span class="navbar-brand mb-0 ops-brand"><span class="ops-brand-mark">DB</span>数据库发布控制台</span>
      <div class="d-flex align-items-center gap-2 flex-wrap justify-content-end">
        <span id="navAuthState" class="badge text-bg-success">免口令操作</span>
        <button class="btn btn-sm btn-outline-light" type="button" onclick="load(true)">刷新状态</button>
      </div>
    </div>
  </nav>

  <main class="container ops-page">
    <header class="mb-4">
      <div class="ops-eyebrow">DATABASE OPERATIONS · 5051</div>
      <h1 class="ops-title">发布、回滚与环境同步</h1>
      <p class="ops-subtitle">数据库操作无需独立口令。一次仅允许一个任务运行，任务日志与阶段进度会实时更新。</p>
    </header>

    <section class="row g-3 mb-4" aria-label="任务概览">
      <div class="col-6 col-xl-3"><div class="ops-stat"><div class="ops-stat-label">任务状态</div><div class="ops-stat-value" id="jobStatus">读取中</div><div class="ops-stat-note" id="jobStatusNote">正在加载任务状态</div></div></div>
      <div class="col-6 col-xl-3"><div class="ops-stat"><div class="ops-stat-label">当前任务</div><div class="ops-stat-value" id="jobId">--</div><div class="ops-stat-note" id="jobStartedAt">尚未创建任务</div></div></div>
      <div class="col-6 col-xl-3"><div class="ops-stat"><div class="ops-stat-label">当前运行环境</div><div class="ops-stat-value" id="jobTarget">--</div><div class="ops-stat-note" id="jobOperation">等待任务</div></div></div>
      <div class="col-6 col-xl-3"><div class="ops-stat"><div class="ops-stat-label">操作保护</div><div class="ops-stat-value" id="authStatus">免口令</div><div class="ops-stat-note" id="authStatusNote">页面访问控制、CSRF 和任务锁仍然有效</div></div></div>
    </section>

    <section class="row g-3">
      <div class="col-12 col-xl-8">
        <div class="card ops-panel h-100">
          <div class="card-header"><h2 class="ops-section-title">数据库全量与增量导入</h2><p class="ops-section-copy">完整数据库导入会先在目标侧恢复到临时库并校验，通过后才切换；增量包按日期和版本顺序执行。</p></div>
          <div class="card-body">
            <div class="ops-release-form">
              <div><label class="form-label small text-secondary" for="releaseTarget">目标环境</label><select id="releaseTarget" class="form-select" onchange="loadReleasePlan()"></select></div>
              <div><label class="form-label small text-secondary" for="package">导入内容</label><select id="package" class="form-select"></select></div>
              <div class="ops-action-group d-flex gap-2 flex-wrap"><button id="release" class="btn btn-primary" type="button" onclick="startRelease()">开始导入</button><button id="cancel" class="btn btn-outline-danger" type="button" onclick="cancelRelease()" hidden>取消任务</button></div>
            </div>
            <div class="alert alert-primary py-2 px-3 mt-3 mb-0 small">本地完整库导入会保留目标现有数据库作为回滚点。增量导入已完成的包不会因取消而自动回退。</div>
            <div id="releasePlanHint" class="ops-release-plan">正在比较本地发布包与目标环境...</div>
            <div class="border rounded-2 bg-light p-3 mt-3">
              <div class="d-flex justify-content-between align-items-start gap-3 flex-wrap"><div><h3 class="fs-6 fw-bold mb-1">本地与目标差异生成</h3><p class="small text-secondary mb-0">重新扫描后生成新的版本化增量包。默认仅处理安全的结构与主数据变更，不删除目标独有记录。</p></div><button id="scanDelta" class="btn btn-sm btn-outline-primary" type="button" onclick="scanDatabaseDelta()">扫描本地差异</button></div>
              <div class="d-flex flex-wrap gap-3 mt-3 small">
                <label class="form-check mb-0"><input id="deltaSchema" class="form-check-input" type="checkbox" checked onchange="clearDeltaReview()"> <span id="deltaSchemaLabel" class="form-check-label">表结构新增</span></label>
                <label class="form-check mb-0"><input id="deltaMasterData" class="form-check-input" type="checkbox" checked onchange="clearDeltaReview()"> <span id="deltaMasterDataLabel" class="form-check-label">主数据新增与更新</span></label>
                <label class="form-check mb-0 text-danger-emphasis"><input id="deltaRuntimeData" class="form-check-input" type="checkbox" checked onchange="clearDeltaReview()"> <span id="deltaRuntimeDataLabel" class="form-check-label">业务运行数据新增与更新（高风险）</span></label>
              </div>
              <div class="d-flex align-items-center gap-2 flex-wrap mt-3"><button id="generateDelta" class="btn btn-sm btn-primary" type="button" onclick="generateDatabaseDelta()">生成待推送增量</button><span id="deltaScanResult" class="small text-secondary">尚未扫描。本操作只读取本地与目标数据库。</span></div>
              <div id="deltaReviewPanel" class="mt-3 d-none" aria-live="polite"></div>
            </div>
          </div>
        </div>
      </div>
      <div class="col-12 col-xl-4">
        <div class="card ops-panel ops-danger-panel h-100">
          <div class="card-header"><h2 class="ops-section-title text-danger-emphasis">Production 覆盖 Staging</h2><p class="ops-section-copy">固定方向，不可反向选择。</p></div>
          <div class="card-body d-flex flex-column"><p class="small text-secondary mb-3">Production 只读。Staging 会完整替换；原 Staging 保留为可回滚备份。恢复与一致性校验失败时，现有 Staging 不会切换。</p><div class="mt-auto"><button id="productionStagingSync" class="btn btn-outline-danger w-100" type="button" onclick="startProductionToStagingSync()">一键导入 Production 到 Staging</button></div></div>
        </div>
      </div>

      <div class="col-12 col-xl-6">
        <div class="card ops-panel h-100">
          <div class="card-header"><h2 class="ops-section-title">回滚记录</h2><p class="ops-section-copy">选择目标环境已有的备份库，创建独立回滚任务。</p></div>
          <div class="card-body ops-rollback-scroll" id="rollbacks"><div class="ops-empty">正在读取回滚记录...</div></div>
        </div>
      </div>
      <div class="col-12 col-xl-6">
        <div class="card ops-panel h-100">
          <div class="card-header"><h2 class="ops-section-title">模拟数据导入</h2><p class="ops-section-copy">模拟粉丝、自选股和评论具有独立批次标签，可按批次删除。</p></div>
          <div class="card-body"><div class="row g-2 align-items-end"><div class="col-sm"><label class="form-label small text-secondary" for="simulationTarget">目标数据库</label><select id="simulationTarget" class="form-select" onchange="loadBatches()"></select></div><div class="col-sm-auto"><button id="create" class="btn btn-outline-primary w-100" type="button" onclick="createBatch()">导入模拟数据</button></div></div><hr class="my-3"><div id="batches"><div class="ops-empty">正在读取模拟数据批次...</div></div></div>
        </div>
      </div>

      <div class="col-12 col-xl-5">
        <div class="card ops-panel h-100">
          <div class="card-header"><h2 class="ops-section-title">实时执行进度</h2><p class="ops-section-copy" id="progressText">等待任务创建</p></div>
          <div class="card-body"><div class="progress mb-3" role="progressbar" aria-label="任务进度"><div id="progressBar" class="progress-bar progress-bar-striped progress-bar-animated" style="width:0%"></div></div><div class="ops-timeline" id="taskTimeline"><div class="ops-empty">当前没有执行事件。</div></div></div>
        </div>
      </div>
      <div class="col-12 col-xl-7">
        <div class="card ops-panel h-100">
          <div class="card-header d-flex align-items-center justify-content-between gap-3"><div><h2 class="ops-section-title">任务日志</h2><p class="ops-section-copy">显示当前或最近一次任务的最后 50,000 字符。</p></div><span id="logStatus" class="badge text-bg-light border">自动刷新</span></div>
          <div class="card-body"><pre id="log" class="ops-log">正在读取...</pre></div>
        </div>
      </div>
    </section>
  </main>

  <div class="toast-container position-fixed bottom-0 end-0 p-3"><div id="toast" class="toast align-items-center text-bg-dark border-0" role="status" aria-live="polite"><div class="d-flex"><div class="toast-body" id="toastBody"></div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="关闭"></button></div></div></div>
  <div class="modal fade" id="operationModal" tabindex="-1" aria-hidden="true"><div class="modal-dialog modal-dialog-centered"><div class="modal-content"><div class="modal-header"><h2 id="modalTitle" class="modal-title fs-6 fw-bold">确认数据库操作</h2><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button></div><div id="modalBody" class="modal-body"></div></div></div></div>

  <script src="/static/vendor/bootstrap.bundle.min.js"></script>
  <script>
    const csrf = '__CSRF_TOKEN__';
    const $ = (id) => document.getElementById(id);
    const operationModal = new bootstrap.Modal($('operationModal'));
    const toastInstance = new bootstrap.Toast($('toast'), { delay: 3200 });
    let overview = {};
    let releasePlan = null;
    let deltaScan = null;
    let selectGeneratedDelta = false;
    let generatedPackageIds = [];
    let submitting = false;
    let poll = null;
    let pendingAction = null;

    function esc(value) { return String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])); }
    function toast(message) { $('toastBody').textContent = message; toastInstance.show(); }
    async function api(path, options = {}) {
      const response = await fetch(path, { ...options, headers: {'Content-Type':'application/json', 'X-Data-Import-CSRF-Token':csrf, ...(options.headers || {})} });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) throw Object.assign(new Error(payload.error || ('HTTP ' + response.status)), { status: response.status });
      return payload;
    }
    function isBusy() { return submitting || ['queued','running','cancelling'].includes(String((overview.job || {}).status || '')); }
    function operationName(value) { return ({release:'数据库导入', rollback:'数据库回滚', production_to_staging:'Production 到 Staging 同步'})[value] || (value || '等待任务'); }
    function statusClass(value) { return ({succeeded:'text-bg-success', failed:'text-bg-danger', cancelled:'text-bg-warning', running:'text-bg-primary', queued:'text-bg-primary', cancelling:'text-bg-warning'})[value] || 'text-bg-secondary'; }
    function renderSelect(select, rows, selected) { select.innerHTML = rows.map((item) => `<option value="${esc(item.name)}" ${item.name === selected ? 'selected' : ''}>${esc(item.label)} (${esc(item.host)}/${esc(item.database)})</option>`).join(''); }
    function currentReleasePlan(target) { return releasePlan && releasePlan.target === target ? releasePlan : null; }
    function renderReleasePlanHint(plan) {
      if (!plan) { $('releasePlanHint').textContent = '正在比较本地发布包与目标环境...'; return; }
      if (plan.error) { $('releasePlanHint').innerHTML = `<span class="text-danger">无法读取目标差异：${esc(plan.error)}</span>`; return; }
      const summary = plan.summary || {};
      const byType = summary.by_type || {};
      const typeLabel = {schema:'表结构', master_data:'主数据', data:'业务数据'};
      const badges = Object.keys(typeLabel).map((type) => `<span class="badge text-bg-light border">${typeLabel[type]}待推送 ${Number((byType[type] || {}).pending || 0)}</span>`).join('');
      const mismatch = Number(summary.checksum_mismatch_total || 0);
      if (summary.baseline_verification_required) {
        $('releasePlanHint').innerHTML = `<span>相对 ${esc(plan.target)}：</span>${badges}<span class="text-secondary">历史版本包已归档，不参与当前差异发布。</span>`;
        return;
      }
      $('releasePlanHint').innerHTML = `<span>相对 ${esc(plan.target)}：</span>${badges}${mismatch ? `<span class="badge text-bg-danger">${mismatch} 个校验不一致</span>` : '<span class="text-success">已校验</span>'}`;
    }
    function renderTaskTimeline(job) {
      const events = job.events || [];
      $('taskTimeline').innerHTML = events.length ? events.slice().reverse().map((event) => `<div class="ops-event"><span class="ops-event-dot ${esc(event.status)}"></span><div><div class="ops-event-title">${esc(event.title)}</div><div class="ops-event-detail">${esc(event.detail)}</div><div class="ops-event-time">${esc(event.at)}</div></div></div>`).join('') : '<div class="ops-empty">当前没有执行事件。</div>';
    }
    function render() {
      const job = overview.job || {};
      const targets = overview.targets || [];
      const releaseTargets = overview.release_targets || [];
      const selectedSimulation = $('simulationTarget').value || 'local';
      const selectedRelease = $('releaseTarget').value || 'staging';
      const selectedPackage = selectGeneratedDelta ? '__pending__' : ($('package').value || '__pending__');
      renderSelect($('simulationTarget'), targets, selectedSimulation);
      renderSelect($('releaseTarget'), releaseTargets, selectedRelease);
      const targetPlan = currentReleasePlan(selectedRelease);
      const typeLabels = {schema:'表结构增量', master_data:'主数据增量', data:'业务数据增量'};
      const packageRows = targetPlan ? (targetPlan.packages || []) : (overview.packages || []).map((item) => ({...item, status:'pending'}));
      const pendingRows = packageRows.filter((item) => item.status === 'pending');
      const pendingLabel = targetPlan ? `相对目标的全部待推送增量（${pendingRows.length} 个）` : '相对目标的全部待推送增量（比较中）';
      $('package').innerHTML = `<option value="__pending__" ${selectedPackage === '__pending__' ? 'selected' : ''}>${pendingLabel}</option><option value="__full__" ${selectedPackage === '__full__' ? 'selected' : ''}>当前完整数据库（全量同步）</option>` + pendingRows.map((item) => `<option value="${esc(item.id)}" ${item.id === selectedPackage ? 'selected' : ''}>${esc(`${item.date} · ${item.version} · ${typeLabels[item.type] || item.type} · ${item.title || ''}`)}</option>`).join('');
      selectGeneratedDelta = false;
      renderReleasePlanHint(targetPlan);
      $('jobStatus').innerHTML = `<span class="badge ${statusClass(job.status)}">${esc(job.status || 'idle')}</span>`;
      $('jobStatusNote').textContent = (job.progress || {}).message || '暂无正在执行的任务';
      $('jobId').textContent = job.id || '--';
      $('jobStartedAt').textContent = job.started_at || '尚未创建任务';
      $('jobTarget').textContent = job.target || '--';
      $('jobOperation').textContent = operationName(job.operation);
      $('authStatus').textContent = '免口令';
      $('authStatusNote').textContent = '页面访问控制、CSRF 和任务锁仍然有效';
      $('navAuthState').className = 'badge text-bg-success';
      $('navAuthState').textContent = '免口令操作';
      const progress = job.progress || {};
      const total = Number(progress.total_steps || 0);
      const completed = Number(progress.completed_steps || 0);
      const percent = total > 0 ? Math.max(0, Math.min(100, Math.round(completed * 100 / total))) : (['succeeded','failed','cancelled'].includes(job.status) ? 100 : 0);
      $('progressBar').style.width = `${percent}%`;
      $('progressBar').textContent = total > 0 ? `${completed}/${total}` : (job.status || 'idle');
      $('progressText').textContent = progress.message || '等待任务创建';
      $('release').disabled = isBusy();
      $('create').disabled = isBusy();
      $('productionStagingSync').disabled = isBusy();
      $('scanDelta').disabled = isBusy();
      $('generateDelta').disabled = isBusy();
      $('cancel').hidden = !['queued','running'].includes(job.status);
      $('logStatus').textContent = ['queued','running','cancelling'].includes(job.status) ? '每秒刷新' : '最近任务';
      renderTaskTimeline(job);
      if (poll) clearTimeout(poll);
      if (['queued','running','cancelling'].includes(job.status)) poll = setTimeout(() => load(), 1000);
    }
    async function loadLog() { try { $('log').textContent = await fetch('/api/log', {cache:'no-store'}).then((response) => response.text()); $('log').scrollTop = $('log').scrollHeight; } catch (error) { $('log').textContent = '日志读取失败：' + error.message; } }
    function renderRollbackGroup(row) {
      const records = row.payload?.records || [];
      if (row.error) return `<section class="ops-rollback-group"><div class="ops-rollback-heading"><span>${esc(row.target.label)}</span></div><div class="alert alert-warning py-2 px-3 mb-0 small">读取失败：${esc(row.error)}</div></section>`;
      const items = records.length ? records.map((record) => `<div class="list-group-item ops-rollback-item"><div class="ops-rollback-item-copy"><div class="ops-code">${esc(record.name)}</div><div class="ops-rollback-size">备份容量：${esc(record.size)}</div></div><button type="button" class="btn btn-sm btn-outline-secondary flex-shrink-0" onclick="requestRollback('${esc(row.target.name)}','${esc(record.name)}')">回滚</button></div>`).join('') : '<div class="ops-empty px-1">暂无可回滚备份。</div>';
      return `<section class="ops-rollback-group"><div class="ops-rollback-heading"><span>${esc(row.target.label)}</span><span class="badge text-bg-light border">${records.length} 个备份</span></div><div class="list-group">${items}</div></section>`;
    }
    async function loadRollbacks() {
      const rows = await Promise.all((overview.release_targets || []).map(async (target) => { try { return { target, payload: await api('/api/rollbacks?target=' + encodeURIComponent(target.name), {headers:{}}) }; } catch (error) { return { target, error: error.message }; } }));
      $('rollbacks').innerHTML = rows.length ? rows.map(renderRollbackGroup).join('') : '<div class="ops-empty">没有可用的远端目标。</div>';
    }
    async function loadBatches() {
      const target = $('simulationTarget').value || 'local';
      $('batches').innerHTML = '<div class="ops-empty">正在读取模拟数据批次...</div>';
      try { const payload = await api('/api/batches?target=' + encodeURIComponent(target), {headers:{}}); const rows = payload.batches || []; $('batches').innerHTML = rows.length ? rows.map((row) => `<div class="ops-list-row"><div><div class="ops-code">${esc(row.batch_code)}</div><div class="small text-secondary mt-1">${esc(row.tenant_slug)} · ${esc(row.created_at)} · 账号 ${row.user_count || 0} · 自选股 ${row.watchlist_count || 0} · 评论 ${row.comment_count || 0}</div></div><button type="button" class="btn btn-sm btn-outline-danger" onclick="requestDelete('${esc(row.batch_code)}')">删除批次</button></div>`).join('') : '<div class="ops-empty">当前目标尚未导入模拟数据。</div>'; } catch (error) { $('batches').innerHTML = `<div class="ops-empty text-danger">读取失败：${esc(error.message)}</div>`; }
    }
    function riskBadge(level) { const labels = {low:'低风险', medium:'中风险', high:'高风险', blocked:'已阻断', none:'无差异'}; const classes = {low:'text-bg-success', medium:'text-bg-warning', high:'text-bg-danger', blocked:'text-bg-dark', none:'text-bg-light border'}; return `<span class="badge ${classes[level] || 'text-bg-secondary'}">${labels[level] || level}</span>`; }
    function sectionLabel(type) { return ({schema:'表结构增量', master_data:'主数据增量', data:'业务数据增量'})[type] || type; }
    function renderReviewSection(section) {
      const changes = section.changes || [];
      const blockers = section.blockers || [];
      const changeText = changes.length ? changes.map((item) => `<div class="small border-bottom py-2"><code>${esc(item.table || '--')}</code><span class="ms-2 text-secondary">${esc(item.action || (item.upsert_rows ? `upsert ${item.upsert_rows} 行` : '差异记录'))}</span>${item.column ? `<span class="ms-2 text-secondary">字段 ${esc(item.column)}</span>` : ''}${item.constraint ? `<span class="ms-2 text-secondary">约束 ${esc(item.constraint)}</span>` : ''}${item.index ? `<span class="ms-2 text-secondary">索引 ${esc(item.index)}</span>` : ''}</div>`).join('') : '<div class="ops-empty">没有可生成的差异。</div>';
      const blockerText = blockers.length ? `<div class="alert alert-warning py-2 px-3 mt-3 mb-0 small"><strong>阻断项</strong>${blockers.map((item) => `<div class="mt-1"><code>${esc(item.table || '--')}</code> · ${esc(item.column || '')} ${esc(item.reason || '需要人工处理')}</div>`).join('')}</div>` : '';
      const sqlText = section.sql_preview ? `<details class="mt-3"><summary class="small text-primary" style="cursor:pointer">查看 SQL 预览（${Number(section.statement_count || 0)} 条语句）${section.sql_preview_truncated ? ' · 已截取前 120,000 字符' : ''}</summary><pre class="ops-log mt-2" style="max-height:260px">${esc(section.sql_preview)}</pre></details>` : '';
      return `<div class="card border mb-2"><div class="card-header d-flex justify-content-between align-items-center gap-2 py-2"><strong class="small">${sectionLabel(section.type)}</strong><span>${riskBadge(section.risk_level)}</span></div><div class="card-body py-2"><div class="small text-secondary mb-2">${esc(section.risk_note || '')} · ${Number(section.sql_chars || 0)} 字符 · ${Number(section.line_count || 0)} 行</div>${changeText}${blockerText}${sqlText}</div></div>`;
    }
    function renderDeltaReview(review, generated = []) {
      const panel = $('deltaReviewPanel');
      if (!panel) return;
      if (!review) { panel.classList.add('d-none'); panel.innerHTML = ''; return; }
      const sections = review.sections || [];
      const blockers = review.blockers || [];
      const generatedHtml = generated.length ? `<div class="alert alert-success py-2 px-3 mt-3 mb-0 small"><div class="fw-bold">已生成版本化增量包</div>${generated.map((item) => `<div class="d-flex align-items-center gap-2 flex-wrap mt-1"><code>${esc(item.version)}</code><span>${esc(sectionLabel(item.type))}</span><button class="btn btn-sm btn-outline-success py-0" type="button" onclick="reviewPackage('${encodeURIComponent(item.id)}')">查看 SQL</button></div>`).join('')}<button class="btn btn-sm btn-success mt-2" type="button" onclick="releaseReviewedPackages()">审核后导入本次增量</button></div>` : '';
      panel.innerHTML = `<div class="d-flex justify-content-between align-items-center gap-2 mb-2"><div><div class="small fw-bold">增量审核清单</div><div class="small text-secondary">扫描时间 ${esc(review.generated_at || '--')} · 目标 ${esc(review.target || '--')}</div></div>${review.requires_manual_review ? '<span class="badge text-bg-warning">需要人工审核</span>' : '<span class="badge text-bg-success">可按规则审核</span>'}</div>${sections.map(renderReviewSection).join('')}${blockers.length ? `<div class="alert alert-danger py-2 px-3 small mb-0">${blockers.length} 项差异被规则阻断，未生成可执行 SQL。请处理后重新扫描。</div>` : ''}${generatedHtml}`;
      panel.classList.remove('d-none');
    }
    function clearDeltaReview() { generatedPackageIds = []; renderDeltaReview(null); }
    function renderDeltaScan(result) {
      const host = $('deltaScanResult');
      if (!result) { host.textContent = '尚未扫描。本操作只读取本地与目标数据库。'; return; }
      if (result.error) { host.innerHTML = `<span class="text-danger">扫描失败：${esc(result.error)}</span>`; return; }
      const safe = result.safe_release_delta || {};
      const summary = result.summary || {};
      const runtime = (result.excluded_runtime_tables || []).length || Number(((result.summary || {}).runtime_data_difference_tables || 0));
      const schemaCount = Number((safe.schema || []).length);
      const masterCount = Number((safe.master_data || []).length);
      const businessCount = Number((safe.business_data || []).length) + runtime;
      $('deltaSchemaLabel').textContent = `表结构新增（${schemaCount}）`;
      $('deltaMasterDataLabel').textContent = `主数据新增与更新（${masterCount}）`;
      $('deltaRuntimeDataLabel').textContent = `业务运行数据新增与更新（${businessCount}，高风险）`;
      $('generateDelta').textContent = businessCount || schemaCount || masterCount ? `生成 ${schemaCount + masterCount + businessCount} 张差异表的增量` : '生成待推送增量';
      host.innerHTML = `<span class="text-success">已完成扫描并生成审核清单：</span>结构 ${schemaCount} · 主数据 ${masterCount} · 业务数据 ${Number((safe.business_data || []).length)}；运行态差异 ${runtime} 张。<span class="text-secondary"> 报告：${esc(result.report_path || '--')}</span>`;
      if (Number(summary.schema_difference_tables || 0) || Number(summary.data_difference_tables || 0)) host.title = '差异详情已写入报告；生成时将再次执行新扫描。';
      renderDeltaReview(result);
    }
    async function scanDatabaseDelta() {
      if (isBusy()) return toast('当前已有发布任务运行');
      const target = $('releaseTarget').value || 'staging';
      $('scanDelta').disabled = true;
      $('deltaScanResult').textContent = `正在扫描本地与 ${target} 的结构和数据差异，请稍候...`;
      try {
        const query = `target=${encodeURIComponent(target)}&include_schema=${$('deltaSchema').checked}&include_master_data=${$('deltaMasterData').checked}&include_runtime_data=${$('deltaRuntimeData').checked}`;
        deltaScan = await api('/api/delta-review?' + query, {headers:{}});
        renderDeltaScan(deltaScan);
        toast('本地与目标差异扫描完成');
      } catch (error) {
        deltaScan = {error:error.message};
        renderDeltaScan(deltaScan);
      } finally { $('scanDelta').disabled = false; }
    }
    function generateDatabaseDelta() {
      if (isBusy()) return toast('当前已有发布任务运行');
      const target = $('releaseTarget').value || 'staging';
      const includeSchema = $('deltaSchema').checked;
      const includeMasterData = $('deltaMasterData').checked;
      const includeRuntimeData = $('deltaRuntimeData').checked;
      if (!includeSchema && !includeMasterData && !includeRuntimeData) return toast('请至少选择一种差异类型');
      const runtimeCount = (deltaScan && deltaScan.excluded_runtime_tables || []).length;
      const scope = [includeSchema ? '表结构' : '', includeMasterData ? '主数据' : '', includeRuntimeData ? `业务运行数据（${runtimeCount} 张差异表）` : ''].filter(Boolean).join('、');
      protectedAction(() => confirmAction('确认生成待推送增量', `将重新扫描本地与 ${esc(target)} 的差异，并为 ${esc(scope)} 生成新的版本化 SQL 包。不会执行导入；业务运行数据不会删除目标独有记录。`, async () => {
        $('generateDelta').disabled = true;
        $('deltaScanResult').textContent = '正在重新扫描并生成版本化增量包，请稍候...';
        try {
          const result = await api('/api/generate-delta', {method:'POST', body:JSON.stringify({target, include_schema:includeSchema, include_master_data:includeMasterData, include_runtime_data:includeRuntimeData})});
          const generated = result.generated_packages || [];
          const blockers = result.blockers || [];
          deltaScan = {target, report_path:result.report_path, safe_release_delta:result.safe_release_delta, summary:{}, excluded_runtime_tables:[], sections:[]};
          renderDeltaScan(deltaScan);
          $('deltaScanResult').innerHTML += generated.length ? `<br><span class="text-success">已生成 ${generated.length} 个增量包：</span> ${generated.map((item) => esc(item.version + ' · ' + item.type)).join('；')}` : '<br><span class="text-secondary">未发现可生成的安全增量。</span>';
          if (blockers.length) $('deltaScanResult').innerHTML += `<br><span class="text-warning-emphasis">${blockers.length} 项高风险差异未生成，请在报告中处理。</span>`;
          toast(generated.length ? '待推送增量已生成，请在上方选择并导入' : '没有可生成的安全增量');
          generatedPackageIds = generated.map((item) => item.id);
          renderDeltaReview(result.review || {target, sections:[], blockers, requires_manual_review:true}, generated);
          selectGeneratedDelta = generated.length > 0;
          await load();
        } catch (error) { $('deltaScanResult').innerHTML = `<span class="text-danger">生成失败：${esc(error.message)}</span>`; }
        finally { $('generateDelta').disabled = false; }
      }));
    }
    async function reviewPackage(encodedId) {
      try {
        const result = await api('/api/package-review?package_id=' + encodedId, {headers:{}});
        const panel = $('deltaReviewPanel');
        panel.classList.remove('d-none');
        panel.innerHTML = `<div class="card border"><div class="card-header d-flex justify-content-between align-items-center gap-2 py-2"><strong class="small">${esc(result.package.version)} · ${esc(sectionLabel(result.package.type))}</strong>${riskBadge(result.risk_level)}</div><div class="card-body py-2"><div class="small text-secondary mb-2">校验和 ${esc(result.package.checksum)} · ${Number(result.statement_count || 0)} 条语句 · ${Number(result.sql_chars || 0)} 字符</div><pre class="ops-log" style="max-height:420px">${esc(result.sql)}${result.sql_truncated ? '\n\n-- 预览已截取 --' : ''}</pre></div></div>`;
      } catch (error) { toast('读取增量包失败：' + error.message); }
    }
    function releaseReviewedPackages() {
      if (!generatedPackageIds.length) return toast('当前没有本次审核生成的增量包');
      const target = $('releaseTarget').value || 'staging';
      protectedAction(() => confirmAction('确认导入已审核增量', `将本次审核生成的 ${generatedPackageIds.length} 个版本包导入 ${esc(target)}。系统不会附带导入其他待推送包。`, async () => {
        try {
          await api('/api/reviewed-release', {method:'POST', body:JSON.stringify({target, package_ids:generatedPackageIds, confirm_production:target === 'production'})});
          toast('已创建审核增量导入任务');
          await load();
        } catch (error) { toast('导入未启动：' + error.message); }
      }));
    }
    async function loadReleasePlan() {
      const target = $('releaseTarget').value || 'staging';
      releasePlan = null;
      renderReleasePlanHint(null);
      try { releasePlan = await api('/api/release-plan?target=' + encodeURIComponent(target), {headers:{}}); render(); }
      catch (error) { releasePlan = {target, error:error.message, packages:[], summary:{}}; render(); }
    }
    async function load(showToast) { try { overview = await api('/api/overview', {headers:{}}); render(); await Promise.all([loadReleasePlan(), loadLog(), loadRollbacks(), loadBatches()]); if (showToast) toast('状态已刷新'); } catch (error) { toast('读取状态失败：' + error.message); } }
    function showModal(title, body, actions) { $('modalTitle').textContent = title; $('modalBody').innerHTML = `${body}<div class="modal-footer px-0 pb-0 mt-4">${actions}</div>`; operationModal.show(); }
    function closeModal() { operationModal.hide(); pendingAction = null; }
    function confirmAction(title, description, action, confirmClass = 'btn-primary', confirmLabel = '确认执行') { showModal(title, `<p class="small text-secondary mb-0">${description}</p>`, `<button type="button" class="btn btn-light border" onclick="closeModal()">取消</button><button type="button" class="btn ${confirmClass}" onclick="confirmModalAction()">${confirmLabel}</button>`); pendingAction = action; }
    async function confirmModalAction() { operationModal.hide(); const action = pendingAction; pendingAction = null; await action(); }
    function protectedAction(action) { return action(); }
    function startRelease() { if (isBusy()) return toast('已有数据导入任务正在执行'); const target = $('releaseTarget').value; const packageId = $('package').value; const targetPlan = currentReleasePlan(target); if (packageId === '__pending__' && (!targetPlan || targetPlan.error)) return toast('请等待目标差异比较完成'); if (packageId === '__pending__' && !Number((targetPlan.summary || {}).pending_total || 0)) return toast('当前没有待推送增量'); if (packageId === '__pending__' && Number((targetPlan.summary || {}).checksum_mismatch_total || 0)) return toast('存在校验不一致的发布包，请新建版本后再推送'); const label = packageId === '__full__' ? '本地完整数据库' : packageId === '__pending__' ? '相对目标的待推送增量' : '所选增量包'; protectedAction(() => confirmAction('确认开始数据导入', `确定将 ${esc(label)} 导入 ${esc(target)} 吗？全量同步会在目标端保留回滚备份。`, async () => { submitting = true; render(); try { await api('/api/release', {method:'POST', body:JSON.stringify({target, package_id:packageId, confirm_production:target === 'production'})}); toast('数据导入任务已创建'); await load(); } catch (error) { toast('导入未启动：' + error.message); } finally { submitting = false; render(); } })); }
    function startProductionToStagingSync() { if (isBusy()) return toast('已有数据导入任务正在执行'); protectedAction(() => confirmAction('确认用 Production 完整覆盖 Staging', 'Production 只读。Staging 的全部数据会被替换，原 Staging 数据库会保留为回滚备份。恢复、校验通过后才会最终切换。', async () => { submitting = true; render(); try { await api('/api/production-to-staging-sync', {method:'POST', body:JSON.stringify({})}); toast('Production 到 Staging 同步任务已创建'); await load(); } catch (error) { toast('同步未启动：' + error.message); } finally { submitting = false; render(); } }, 'btn-danger', '确认覆盖 Staging')); }
    function cancelRelease() { const job = overview.job || {}; if (!job.id) return; protectedAction(() => confirmAction('确认取消数据导入', '当前步骤会被停止。已完成的增量包不会自动回退。', async () => { try { await api('/api/cancel', {method:'POST', body:JSON.stringify({job_id:job.id})}); toast('已发送取消请求'); await load(); } catch (error) { toast('取消失败：' + error.message); } }, 'btn-danger', '确认取消')); }
    function requestRollback(target, backupName) { protectedAction(() => confirmAction('确认数据库回滚', `确定将 ${esc(target)} 回滚到 ${esc(backupName)} 吗？`, async () => { try { await api('/api/rollback', {method:'POST', body:JSON.stringify({target, backup_name:backupName, confirm_production:target === 'production'})}); toast('回滚任务已创建'); await load(); } catch (error) { toast('回滚未启动：' + error.message); } })); }
    function createBatch() { if (isBusy()) return; const target = $('simulationTarget').value || 'local'; protectedAction(() => confirmAction('确认导入模拟数据', `将在 ${esc(target)} 创建一组带独立批次编号的模拟粉丝、自选股和评论。`, async () => { submitting = true; render(); try { const result = await api('/api/batches', {method:'POST', body:JSON.stringify({target, tenant_slug:'laowang'})}); toast('模拟数据已导入：' + result.batch_code); await loadBatches(); } catch (error) { toast('导入失败：' + error.message); } finally { submitting = false; render(); } })); }
    function requestDelete(batch) { const target = $('simulationTarget').value || 'local'; protectedAction(() => confirmAction('确认删除导入批次', `确定删除 ${esc(batch)} 的全部模拟账户、自选股和评论吗？真实数据不会受影响。`, async () => { try { await api('/api/batches/' + encodeURIComponent(batch), {method:'DELETE', body:JSON.stringify({target})}); toast('导入批次已删除'); await loadBatches(); } catch (error) { toast('删除失败：' + error.message); } }, 'btn-danger', '确认删除')); }
    load();
  </script>
</body>
</html>"""
PAGE = PAGE.replace(
    '</body></html>',
    '''<script>
(function () {
  const originalRender = render;
  render = function () {
    originalRender();
    const button = $('productionStagingSync');
    if (button) button.disabled = busy();
  };
  window.startProductionToStagingSync = function () {
    if (busy()) return toast('已有数据导入任务正在执行');
    protectedAction(() => confirmAction(
      '确认用 Production 完整覆盖 Staging',
      'Production 只读。Staging 的全部数据会被替换，原 Staging 数据库会保留为回滚备份。恢复、校验通过后才会最终切换。',
      async () => {
        submitting = true;
        render();
        try {
          await api('/api/production-to-staging-sync', {method: 'POST', body: JSON.stringify({})});
          toast('Production 到 Staging 同步任务已创建');
          await load();
        } catch (error) {
          toast('同步未启动：' + error.message);
        } finally {
          submitting = false;
          render();
        }
      }
    ));
  };
})();
</script></body></html>''',
)


if __name__ == "__main__":
    app.run(host=APP_HOST, port=APP_PORT, debug=False, use_reloader=False)
