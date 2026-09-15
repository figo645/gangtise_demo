#!/usr/bin/env python3
"""Standalone 5051 console for full local-to-target database migration.

Full migration, controlled environment synchronization, user-business-data
cleanup, cancellation, rollback, status, logs, and the reviewed diff workflow
are exposed. Incremental package execution, simulation imports, and destructive
database clears are intentionally not part of this service.
"""

import hashlib
import os
import secrets
import sys
from functools import wraps
from hmac import compare_digest
from pathlib import Path

from flask import Flask, jsonify, request, send_file, session

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
    start_production_to_staging_sync,
    start_staging_to_production_sync,
    list_database_release_rollbacks,
    start_database_release,
    start_database_rollback,
    get_user_data_cleanup_backup_sql_path,
    list_user_data_cleanup_backups,
    start_user_data_cleanup,
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


@app.post("/api/production-to-staging-sync")
@_require_csrf
def production_to_staging_sync():
    payload = request.get_json(silent=True) or {}
    try:
        job = start_production_to_staging_sync(confirm=payload.get("confirm") is True)
    except ValueError as exc:
        error = str(exc)
        return jsonify({"ok": False, "error": error}), 409 if error == "database_release_job_running" else 400
    return jsonify({"ok": True, "job": job}), 202


@app.post("/api/staging-to-production-sync")
@_require_csrf
def staging_to_production_sync():
    payload = request.get_json(silent=True) or {}
    try:
        job = start_staging_to_production_sync(confirm=payload.get("confirm") is True)
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


@app.post("/api/user-data/cleanup")
@_require_csrf
def user_data_cleanup():
    """Clear user-generated business data while retaining every account."""
    payload = request.get_json(silent=True) or {}
    target = str(payload.get("target") or "").strip().lower()
    mode = str(payload.get("mode") or "all_user_business_data").strip()
    if mode != "all_user_business_data":
        return jsonify({"ok": False, "error": "user_data_cleanup_mode_invalid"}), 400
    try:
        job = start_user_data_cleanup(
            target,
            mode,
            usernames=[],
            confirmation=payload.get("confirmation"),
            confirm_production=payload.get("confirm_production") is True,
        )
    except ValueError as exc:
        error = str(exc)
        return jsonify({"ok": False, "error": error}), 409 if error == "database_release_job_running" else 400
    return jsonify({"ok": True, "job": job}), 202


@app.get("/api/user-data/backups")
def user_data_backups():
    try:
        records = list_user_data_cleanup_backups(request.args.get("target") or "staging")
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "records": records})


@app.get("/api/user-data/backups/<target>/<backup_id>/sql")
def user_data_backup_sql(target, backup_id):
    try:
        sql_path = get_user_data_cleanup_backup_sql_path(target, backup_id)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return send_file(sql_path, as_attachment=True, download_name=sql_path.name, mimetype="application/sql")


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
:root{--ink:#172b4d;--muted:#667085;--line:#d9e2ec;--paper:#f5f8fb;--blue:#1769aa;--red:#b42318}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:14px ui-sans-serif,system-ui,"PingFang SC",sans-serif}.shell{max-width:1120px;margin:0 auto;padding:28px 20px}.head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;border-bottom:1px solid var(--line);padding-bottom:20px}.head h1{margin:0;font-size:24px}.head p{margin:8px 0 0;color:var(--muted);line-height:1.7}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:18px}.panel{background:#fff;border:1px solid var(--line);border-radius:8px;padding:18px}.panel h2{font-size:16px;margin:0 0 12px}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:end}.field{display:grid;gap:6px;min-width:240px;color:var(--muted);font-size:12px;flex:1}select{height:40px;border:1px solid var(--line);border-radius:6px;padding:0 10px;background:#fff;color:var(--ink);font:inherit}button{border:1px solid var(--blue);border-radius:6px;background:#fff;color:var(--blue);padding:10px 14px;font:600 13px inherit;cursor:pointer;touch-action:manipulation;transition:transform .12s ease,box-shadow .12s ease,background-color .12s ease,color .12s ease,border-color .12s ease}button:not(:disabled):active{transform:translateY(1px);box-shadow:inset 0 1px 3px rgba(23,43,77,.16)}button:focus-visible{outline:3px solid rgba(23,105,170,.24);outline-offset:2px}button.primary{background:var(--blue);color:#fff}button.danger{border-color:var(--red);color:var(--red)}button:disabled{opacity:.48;cursor:wait}.notice{margin-top:12px;color:var(--muted);font-size:12px;line-height:1.75}.warning{background:#fff8e8;border:1px solid #f0d58a;color:#7a5510;border-radius:6px;padding:11px 12px;font-size:12px;line-height:1.7}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px}.stat{padding:12px;background:#f8fbfe;border:1px solid #e6edf3;border-radius:6px}.stat b{display:block;font-size:16px;margin-top:5px}.stat span{font-size:11px;color:var(--muted)}.rollback-table-wrap{overflow-x:auto;margin-top:4px}.rollback-table{width:100%;border-collapse:collapse;min-width:680px;font-size:12px}.rollback-table th{padding:10px 12px;background:#f7fafc;color:var(--muted);font-size:11px;font-weight:700;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}.rollback-table td{padding:11px 12px;border-bottom:1px solid #edf1f5;vertical-align:middle}.rollback-table tbody tr:last-child td{border-bottom:0}.rollback-table .backup-name{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink);font-size:11px}.rollback-table .action-cell{text-align:right;white-space:nowrap}.rollback-table .empty-cell{text-align:center;color:var(--muted);padding:18px}.meta{font-size:12px;color:var(--muted);margin-top:5px;line-height:1.5}pre{min-height:180px;max-height:380px;overflow:auto;background:#11253b;color:#dceafa;padding:14px;border-radius:6px;white-space:pre-wrap;font:12px/1.65 ui-monospace,monospace}.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);padding:10px 15px;background:#16283d;color:#fff;border-radius:6px;opacity:0;transition:.2s;pointer-events:none}.toast.show{opacity:1}.modal{position:fixed;inset:0;background:rgba(18,35,55,.42);display:none;place-items:center;padding:20px}.modal.show{display:grid}.modal .panel{width:min(480px,100%)}@media(max-width:760px){.grid{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}.head{display:block}.head button{margin-top:14px}}
</style><style>
button.is-loading{background:var(--blue);border-color:var(--blue);color:#fff;min-width:112px;cursor:wait;opacity:1}
button.is-loading::before{content:"";display:inline-block;width:12px;height:12px;margin-right:7px;vertical-align:-2px;border:2px solid rgba(255,255,255,.45);border-top-color:#fff;border-radius:50%;animation:diff-scan-spin .75s linear infinite}
button.is-success{border-color:#218653;color:#218653}
button.is-failure{border-color:var(--red);color:var(--red)}
@keyframes diff-scan-spin{to{transform:rotate(360deg)}}
</style><style>
button.is-pressed:not(:disabled){transform:translateY(1px);box-shadow:inset 0 1px 3px rgba(23,43,77,.16)}
</style><style>
.workflow{display:grid;gap:8px;margin-top:14px}.workflow-title{font-size:12px;font-weight:700;color:var(--ink);margin-bottom:2px}.workflow-node{display:grid;grid-template-columns:28px 1fr auto;gap:9px;align-items:center;padding:9px 10px;border:1px solid var(--line);border-radius:7px;background:#fbfdff}.workflow-node.active{border-color:#6aa8d8;background:#eef7ff}.workflow-node.succeeded{border-color:#9bcab1;background:#f1faf4}.workflow-node.failed{border-color:#e5aaa4;background:#fff5f3}.workflow-dot{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;background:#e7edf2;color:var(--muted);font-size:11px;font-weight:700}.workflow-node.active .workflow-dot{background:var(--blue);color:#fff}.workflow-node.succeeded .workflow-dot{background:#218653;color:#fff}.workflow-node.failed .workflow-dot{background:var(--red);color:#fff}.workflow-label{font-weight:600;font-size:12px}.workflow-detail{font-size:11px;color:var(--muted);margin-top:2px}.workflow-status{font-size:11px;color:var(--muted);white-space:nowrap}.workflow-node.active .workflow-status{color:var(--blue);font-weight:700}.workflow-node.succeeded .workflow-status{color:#218653}.workflow-node.failed .workflow-status{color:var(--red)}
</style><style>
.section-title{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:14px}.section-title h2{margin:0}.section-title p{margin:5px 0 0;color:var(--muted);font-size:12px;line-height:1.6}.eyebrow{color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.primary-action{border-color:#0f5b96;background:#0f5b96;box-shadow:0 5px 12px rgba(23,105,170,.18)}.action-panel{border-top:3px solid var(--blue)}.source-panel{border-top:3px solid #b7791f;background:#fffdf8}.publish-panel{border-top:3px solid var(--red);background:#fffafa}.secondary-panel{border-top:3px solid #91a9bd}.cleanup-panel{border-top:3px solid var(--red);background:#fffafa}.cleanup-confirm{display:grid;gap:6px;max-width:460px;color:var(--muted);font-size:12px}.cleanup-confirm input{height:40px;border:1px solid #e5aaa4;border-radius:6px;padding:0 10px;font:inherit;color:var(--ink)}.monitor-grid{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1.4fr);gap:16px;margin-top:16px}.monitor-grid .panel{min-width:0}.panel-heading{display:flex;justify-content:space-between;align-items:baseline;gap:10px;border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:12px}.panel-heading h2{margin:0}.panel-heading span{font-size:11px;color:var(--muted)}.rollback-panel{margin-top:16px}.release-note{margin-top:14px;padding:10px 12px;background:#f7fafc;border:1px solid #e6edf3;border-radius:6px;color:var(--muted);font-size:11px;line-height:1.7}@media(max-width:760px){.monitor-grid{grid-template-columns:1fr}.section-title{display:block}.section-title button{margin-top:12px;width:100%}}
</style><style>
.release-actions-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:18px;align-items:stretch}.release-actions-grid>.panel{margin-top:0!important;height:100%}@media(max-width:980px){.release-actions-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:640px){.release-actions-grid{grid-template-columns:1fr}}
</style></head><body><main class="shell">
<header class="head"><div><div class="eyebrow">DATABASE RELEASE CONTROL</div><h1>数据库迁移</h1><p>5051 数据迁移控制台。先确认目标环境，再选择全量替换或差异迁移；所有任务都保留日志和回滚点。</p></div><button id="refresh" type="button" onclick="refreshStatus(this)">刷新状态</button></header>
<section class="stats" id="stats"></section>
<div class="release-actions-grid">
<section class="panel action-panel" style="margin-top:18px"><div class="section-title"><div><h2>全量迁移</h2><p>以本地完整数据库为来源，先恢复到目标临时库校验，通过后才切换目标数据库。</p></div><span class="eyebrow">高影响操作</span></div><div class="row"><label class="field">目标环境<select id="releaseTarget"></select></label><button id="release" class="primary primary-action" type="button" onclick="startRelease(this)">开始全量迁移</button><button id="cancel" class="danger" type="button" onclick="cancelRelease(this)" hidden>停止任务</button></div><div class="warning" style="margin-top:14px">目标环境的用户及其关联业务数据会在切换前恢复；校验未通过时不会替换目标数据库，原数据库会保留为回滚点。</div></section>
<section class="panel source-panel" style="margin-top:16px"><div class="section-title"><div><h2>生产 → Staging 全量同步</h2><p>将 Production 的完整数据库快照恢复到 Staging 临时库，校验通过后再切换；适合在 Staging 上验证差异迁移。</p></div><span class="eyebrow" style="color:#9a6700">高风险 · 仅 Staging</span></div><div class="row"><div class="field"><span>同步方向</span><strong>Production → Staging</strong></div><button id="productionToStaging" class="primary" style="background:#9a6700;border-color:#9a6700" type="button" onclick="startProductionToStaging(this)">从生产同步到 Staging</button></div><div class="warning" style="margin-top:14px">这会替换 Staging 当前数据库内容。Staging 原数据库会先重命名为备份，生产环境凭据不会直接覆盖 Staging 的受保护配置；确认前请确保没有正在进行的 staging 测试。</div></section>
<section class="panel publish-panel" style="margin-top:16px"><div class="section-title"><div><h2>Staging → Production 全量发布</h2><p>将经过 Staging 验证的完整数据库快照发布到 Production；只有临时库校验通过后才切换生产数据库。</p></div><span class="eyebrow" style="color:var(--red)">高风险 · 需确认</span></div><div class="row"><div class="field"><span>发布方向</span><strong>Staging → Production</strong></div><button id="stagingToProduction" class="primary" style="background:var(--red);border-color:var(--red)" type="button" onclick="startStagingToProduction(this)">从 Staging 发布到 Production</button></div><div class="warning" style="margin-top:14px">Production 当前数据库会在切换前保留为回滚备份。此操作会覆盖 Production 的数据库内容，不会执行任何发布，直到你在确认框中再次确认。</div></section>
</div>
<section class="panel cleanup-panel" style="margin-top:16px"><div class="section-title"><div><h2>清除用户业务数据</h2><p>保留所有用户账户、密码、角色和租户归属；清除站内信、智能体会话、记忆、自选股、评论、标注、洞见草稿/发布内容、访问与用量记录、订阅订单等用户产生的数据。</p></div><span class="eyebrow" style="color:var(--red)">不可逆 · 先备份</span></div><div class="row"><label class="field">目标环境<select id="cleanupTarget"></select></label><button id="cleanupStart" class="danger" type="button" onclick="startUserDataCleanup(this)">清除全部用户业务数据</button></div><div class="warning" style="margin-top:14px">执行前会自动生成完整 PostgreSQL dump 和可恢复的 SQL 文件，并保留该目标环境最近 2 份清理前备份。指标、行情、行业、宏观主数据、租户配置、订阅产品和扫码邀请配置不受影响。</div><label class="cleanup-confirm" style="margin-top:14px">请输入确认文本 <strong>CLEAR ALL USER BUSINESS DATA</strong><input id="cleanupConfirmation" autocomplete="off" placeholder="CLEAR ALL USER BUSINESS DATA"></label><div id="cleanupStatus" class="notice">尚未执行用户业务数据清理。</div><div class="panel-heading" style="margin-top:16px"><h2>清理前备份</h2><span>最近 2 份 · 可下载 SQL</span></div><div id="userDataBackups" class="notice">正在读取...</div></section>
<section class="panel secondary-panel" style="margin-top:16px"><div class="section-title"><div><h2>差异迁移</h2><p>扫描后系统会自动完成差异校验和执行计划准备，确认无阻断项后再执行。</p></div><span class="eyebrow">日常路径</span></div><div class="row"><label class="field">目标环境<select id="diffTarget"></select></label><label style="display:flex;gap:6px;align-items:center;font-size:12px;color:var(--muted)"><input id="diffSchema" type="checkbox" checked> 表结构</label><label style="display:flex;gap:6px;align-items:center;font-size:12px;color:var(--muted)"><input id="diffMaster" type="checkbox" checked> 主数据</label><label style="display:flex;gap:6px;align-items:center;font-size:12px;color:var(--muted)"><input id="diffRuntime" type="checkbox"> 业务数据</label><button id="diffScan" type="button" onclick="scanDiff()">扫描并准备差异</button><button id="diffRelease" class="primary" type="button" onclick="releaseDiff()" disabled>确认执行差异迁移</button></div><div id="diffStatus" class="notice">请先扫描并准备差异。系统会在后台完成预览和计划生成，业务数据默认不包含用户运行数据。</div><div id="diffWorkflow" class="workflow" aria-live="polite"></div><pre id="diffReport" style="max-height:260px;min-height:100px;margin-top:12px">暂无差异报告</pre></section>
<section class="monitor-grid"><section class="panel"><div class="panel-heading"><h2>任务进度</h2><span>当前任务与执行流程</span></div><div id="progress" class="notice">正在读取...</div></section><section class="panel"><div class="panel-heading"><h2>迁移日志</h2><span>实时输出</span></div><pre id="log">正在读取...</pre></section></section>
<section class="panel rollback-panel"><div class="panel-heading"><h2>回滚记录</h2><span>每个目标环境保留最近可用备份</span></div><div id="rollbacks" class="notice">正在读取...</div><div class="release-note">回滚只用于恢复已完成切换的目标数据库。执行前请核对目标环境、备份名称和应用连接配置。</div></section>
</main><div id="toast" class="toast"></div><div id="modal" class="modal"><div class="panel"><h2 id="modalTitle">确认操作</h2><div id="modalBody"></div></div></div>
<script>
const csrf='__CSRF_TOKEN__';let overview={},submitting=false,poll=null;const $=id=>document.getElementById(id);function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function toast(t){$('toast').textContent=t;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),3000)}async function api(path,opt={}){const r=await fetch(path,{...opt,credentials:'same-origin',headers:{'Content-Type':'application/json','X-Data-Import-CSRF-Token':csrf,...(opt.headers||{})}});const d=await r.json().catch(()=>({}));if(!r.ok||d.ok===false)throw Object.assign(new Error(d.error||('HTTP '+r.status)),{status:r.status});return d}function busy(){return submitting||['queued','running','cancelling'].includes(String((overview.job||{}).status||''))}function render(){const j=overview.job||{},targets=overview.release_targets||[];const selected=$('releaseTarget').value||'staging';$('releaseTarget').innerHTML=targets.map(x=>'<option value="'+esc(x.name)+'" '+(x.name===selected?'selected':'')+'>'+esc(x.label)+' ('+esc(x.host)+'/'+esc(x.database)+')</option>').join('');const cleanupSelected=$('cleanupTarget').value||'staging';$('cleanupTarget').innerHTML=targets.map(x=>'<option value="'+esc(x.name)+'" '+(x.name===cleanupSelected?'selected':'')+'>'+esc(x.label)+' ('+esc(x.host)+'/'+esc(x.database)+')</option>').join('');if(typeof renderDiffTargets==='function')renderDiffTargets();const p=j.progress||{};$('stats').innerHTML=[['任务状态',j.status||'idle',j.target||'暂无任务'],['任务编号',j.id||'--',j.started_at||'--'],['当前阶段',p.message||'等待执行',p.updated_at||'--'],['迁移模式','全量迁移','增量、模拟导入和清空功能已移除']].map(x=>'<div class="stat"><span>'+esc(x[0])+'</span><b>'+esc(x[1])+'</b><span>'+esc(x[2])+'</span></div>').join('');$('progress').innerHTML='<b>'+esc(p.message||'暂无运行中的迁移任务')+'</b><div class="meta">状态：'+esc(j.status||'idle')+' · 完成步骤：'+esc(p.completed_steps||0)+' / '+esc(p.total_steps||1)+'</div>';if(j.operation==='user_data_cleanup'&&['queued','running','cancelling'].includes(j.status))$('cleanupStatus').textContent='用户业务数据清理任务正在执行：'+(p.message||j.status);$('release').disabled=busy();$('productionToStaging').disabled=busy();$('cleanupStart').disabled=busy();$('cancel').hidden=!['queued','running','cancelling'].includes(j.status);if(poll)clearTimeout(poll);if(['queued','running','cancelling'].includes(j.status))poll=setTimeout(()=>load(),1000)}async function loadLog(){try{$('log').textContent=await fetch('/api/log',{cache:'no-store',credentials:'same-origin'}).then(r=>r.text());$('log').scrollTop=$('log').scrollHeight}catch(e){$('log').textContent='日志读取失败：'+e.message}}async function loadRollbacks(){
  const host=$('rollbacks');
  const rows=await Promise.all((overview.release_targets||[]).map(async t=>{
    try{return {t,d:await api('/api/rollbacks?target='+encodeURIComponent(t.name))}}
    catch(e){return {t,error:e.message}}
  }));
  const tableRows=rows.flatMap(x=>{
    if(x.error)return ['<tr><td>'+esc(x.t.label)+'</td><td colspan="3">读取失败：'+esc(x.error)+'</td></tr>'];
    const records=x.d.records||[];
    if(!records.length)return ['<tr><td>'+esc(x.t.label)+'</td><td colspan="3" class="empty-cell">暂无可回滚备份</td></tr>'];
    return records.map(r=>'<tr><td>'+esc(x.t.label)+'</td><td class="backup-name">'+esc(r.name)+'</td><td>'+esc(r.size)+'</td><td class="action-cell"><button type="button" data-rollback-target="'+esc(x.t.name)+'" data-rollback-name="'+esc(r.name)+'" onclick="requestRollback(this.dataset.rollbackTarget,this.dataset.rollbackName)">回滚</button></td></tr>');
  });
  host.innerHTML='<div class="rollback-table-wrap"><table class="rollback-table"><thead><tr><th>目标环境</th><th>备份数据库</th><th>大小</th><th class="action-cell">操作</th></tr></thead><tbody>'+tableRows.join('')+'</tbody></table></div>';
}async function loadUserDataBackups(){const target=$('cleanupTarget').value||'staging';const host=$('userDataBackups');try{const data=await api('/api/user-data/backups?target='+encodeURIComponent(target));const records=data.records||[];if(!records.length){host.innerHTML='<div class="notice">暂无已完成的用户业务数据清理备份。</div>';return}host.innerHTML='<div class="rollback-table-wrap"><table class="rollback-table"><thead><tr><th>备份时间</th><th>目标环境</th><th>备份编号</th><th>SQL</th></tr></thead><tbody>'+records.map(r=>'<tr><td>'+esc(r.cleanup_completed_at||r.created_at)+'</td><td>'+esc(r.target)+'</td><td class="backup-name">'+esc(r.backup_id)+'</td><td class="action-cell">'+(r.sql_available?'<a href="/api/user-data/backups/'+encodeURIComponent(r.target)+'/'+encodeURIComponent(r.backup_id)+'/sql" download>下载 SQL</a>':'不可用')+'</td></tr>').join('')+'</tbody></table></div>'}catch(e){host.textContent='备份记录读取失败：'+e.message}}function startUserDataCleanup(){if(busy())return toast('已有数据库任务正在执行');const target=$('cleanupTarget').value||'staging';const confirmation=$('cleanupConfirmation').value.trim();if(confirmation!=='CLEAR ALL USER BUSINESS DATA')return toast('请输入正确的确认文本');const production=target==='production';confirmAction('确认清除全部用户业务数据','将清除 '+esc(target)+' 中所有用户产生的业务数据，包括站内信、智能体会话、自选股、评论、标注、洞见、订单和统计记录；所有用户账户仍会保留。执行前会先生成完整 dump 和 SQL 备份。'+(production?' 这是 Production 操作，请再次核对目标环境。':''),async()=>{submitting=true;render();$('cleanupStatus').textContent='正在创建备份并启动清理任务...';try{await api('/api/user-data/cleanup',{method:'POST',body:JSON.stringify({target,mode:'all_user_business_data',confirmation,confirm_production:production})});toast('用户业务数据清理任务已创建');await load()}catch(e){$('cleanupStatus').textContent='清理未启动：'+e.message;toast('清理未启动：'+e.message)}finally{submitting=false;render();await loadUserDataBackups()}},'确认清除')}$('cleanupTarget').addEventListener('change',loadUserDataBackups);async function load(message){try{overview=await api('/api/overview');render();await Promise.all([loadLog(),loadRollbacks(),loadUserDataBackups()]);if(message)toast('状态已刷新')}catch(e){toast('读取状态失败：'+e.message)}}function closeModal(){$('modal').classList.remove('show')}function confirmAction(title,body,ok,button='确认执行'){$('modalTitle').textContent=title;$('modalBody').innerHTML='<p class="notice">'+body+'</p><div class="row" style="justify-content:flex-end;margin-top:14px"><button type="button" onclick="closeModal()">取消</button><button class="primary" type="button" id="confirmAction">'+button+'</button></div>';$('modal').classList.add('show');$('confirmAction').onclick=async()=>{closeModal();await ok()}}function startRelease(){if(busy())return toast('已有全量迁移任务正在执行');const target=$('releaseTarget').value;const production=target==='production';confirmAction('确认全量迁移','将本地完整数据库迁移到 '+esc(target)+'。目标环境用户及关联业务数据会被保留，目标数据库会先备份。'+(production?' 这是 Production 操作，请确认目标环境和备份策略。':''),async()=>{submitting=true;render();try{await api('/api/release',{method:'POST',body:JSON.stringify({target,package_id:'__full__',confirm_production:production})});toast('全量迁移任务已创建');await load()}catch(e){toast('迁移未启动：'+e.message)}finally{submitting=false;render()}},'确认开始')}function startProductionToStaging(){if(busy())return toast('已有数据库任务正在执行');confirmAction('确认从生产同步到 Staging','这会用 Production 的完整数据库替换 Staging；Staging 原数据库会先保留为备份。请确认当前没有正在进行的 Staging 测试。',async()=>{submitting=true;render();try{await api('/api/production-to-staging-sync',{method:'POST',body:JSON.stringify({confirm:true})});toast('生产到 Staging 全量同步任务已创建');await load()}catch(e){toast('同步未启动：'+e.message)}finally{submitting=false;render()}},'确认同步')}function cancelRelease(){const j=overview.job||{};if(!j.id)return;confirmAction('停止数据库任务','仅允许在数据库切换前停止。已经切换完成的任务不能通过停止回退，请使用回滚。',async()=>{try{await api('/api/cancel',{method:'POST',body:JSON.stringify({job_id:j.id})});toast('已发送停止请求');await load()}catch(e){toast('停止失败：'+e.message)}} ,'确认停止')}function requestRollback(target,name){confirmAction('确认数据库回滚','将 '+esc(target)+' 回滚到 '+esc(name)+'。',async()=>{try{await api('/api/rollback',{method:'POST',body:JSON.stringify({target,backup_name:name,confirm_production:target==='production'})});toast('回滚任务已创建');await load()}catch(e){toast('回滚未启动：'+e.message)}} ,'确认回滚')}load();
</script>
<script>
function refreshStatus(button){
  if(button&&button.disabled)return;
  if(button){button.disabled=true;button.classList.remove('is-success','is-failure');button.classList.add('is-loading');button.setAttribute('aria-busy','true');button.textContent='刷新中...'}
  load().then(()=>{if(button){button.classList.remove('is-loading');button.classList.add('is-success');button.setAttribute('aria-busy','false');button.textContent='已刷新'}toast('状态已刷新')}).catch(e=>{if(button){button.classList.remove('is-loading');button.classList.add('is-failure');button.setAttribute('aria-busy','false');button.textContent='刷新失败'}toast('读取状态失败：'+e.message)}).finally(()=>setTimeout(()=>{if(button){button.disabled=false;button.classList.remove('is-success','is-failure');button.removeAttribute('aria-busy');button.textContent='刷新状态'}},1200));
}
function markButtonPressed(button){
  if(!button||button.disabled||button.classList.contains('is-loading'))return;
  button.classList.add('is-pressed');
  setTimeout(()=>button.classList.remove('is-pressed'),180);
}
document.addEventListener('pointerdown',event=>markButtonPressed(event.target.closest('button')),{passive:true});
document.addEventListener('keydown',event=>{
  if(event.key==='Enter'||event.key===' '){markButtonPressed(event.target.closest('button'))}
});
function startStagingToProduction(button){
  if(busy())return toast('已有数据库任务正在执行');
  confirmAction('确认从 Staging 发布到 Production','这会用 Staging 的完整数据库替换 Production；Production 原数据库会先保留为回滚备份。临时数据库会先完成恢复和校验，校验通过后才切换生产库。请确认已完成 Staging 验证。',async()=>{
    submitting=true;
    if(button){button.disabled=true;button.classList.remove('is-success','is-failure');button.classList.add('is-loading');button.setAttribute('aria-busy','true');button.textContent='正在发布...'}
    render();
    try{
      await api('/api/staging-to-production-sync',{method:'POST',body:JSON.stringify({confirm:true})});
      toast('Staging 到 Production 发布任务已创建');
      await load();
    }catch(e){
      toast('发布未启动：'+e.message);
      if(button){button.classList.remove('is-loading');button.classList.add('is-failure');button.removeAttribute('aria-busy');button.disabled=false;button.textContent='发布失败'}
    }finally{
      submitting=false;
      render();
    }
  },'确认发布到 Production');
}
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
async function scanDiff(){const button=document.getElementById('diffScan');if(button&&button.disabled)return false;try{if(button){button.disabled=true;button.classList.remove('is-success','is-failure');button.classList.add('is-loading');button.setAttribute('aria-busy','true');button.textContent='正在准备...'}renderDiffTargets();document.getElementById('diffReport').textContent='正在连接目标数据库并计算差异摘要，请稍候...';document.getElementById('diffStatus').textContent='正在扫描差异。扫描完成后系统会自动核对并准备执行计划。';const target=document.getElementById('diffTarget').value||'staging';const data=await api('/api/diff/scan?target='+encodeURIComponent(target));document.getElementById('diffReport').textContent=diffText(data.scan);document.getElementById('diffStatus').textContent='扫描完成，正在自动准备执行计划...';diffPlan=null;const planData=await diffRequest('/api/diff/generate',diffPayload());diffPlan=planData.result||{};const blockers=diffPlan.blockers||[];document.getElementById('diffReport').textContent=diffText(diffPlan);document.getElementById('diffStatus').textContent=blockers.length?'差异已准备，但存在阻断项，请查看报告。':'差异已准备完成，可以确认执行。';document.getElementById('diffRelease').disabled=!diffPlan.generated_packages||!diffPlan.generated_packages.length||blockers.length>0;if(button){button.classList.add('is-success')}return true}catch(e){document.getElementById('diffReport').textContent='差异准备未完成。请查看上方状态信息。';document.getElementById('diffStatus').textContent='差异准备失败：'+e.message;if(button){button.classList.add('is-failure')}return false}finally{if(button){button.disabled=false;button.classList.remove('is-loading');button.removeAttribute('aria-busy');button.textContent='扫描并准备差异';setTimeout(()=>button.classList.remove('is-success','is-failure'),2200)}}}
async function releaseDiff(){const button=document.getElementById('diffRelease');if(!diffPlan||!diffPlan.generated_packages||!diffPlan.generated_packages.length||button&&button.disabled)return;const target=diffPlan.target;const production=target==='production';if(!window.confirm('确认执行 '+target+' 差异迁移？执行前会重新扫描并核验差异报告，目标用户数据不会被本地用户表覆盖。'))return;try{if(button){button.disabled=true;button.classList.add('is-loading');button.setAttribute('aria-busy','true');button.textContent='正在提交...'}document.getElementById('diffStatus').textContent='正在提交差异迁移任务，请稍候...';const data=await diffRequest('/api/diff/release',{target,report_path:diffPlan.report_path,diff_fingerprint:diffPlan.diff_fingerprint,package_ids:diffPlan.generated_packages.map(item=>item.id),confirm_production:production});document.getElementById('diffStatus').textContent='差异迁移任务已创建：'+(data.job||{}).id;if(button){button.classList.remove('is-loading');button.classList.add('is-success');button.setAttribute('aria-busy','false');button.textContent='已提交'}await load()}catch(e){document.getElementById('diffStatus').textContent='差异迁移未启动：'+e.message;if(button){button.classList.remove('is-loading');button.classList.add('is-failure');button.removeAttribute('aria-busy');button.disabled=false;button.textContent='确认执行差异迁移'}}}
renderDiffTargets();
let diffFlowStage=0;
const diffFlowNodes=[['scan','扫描并准备差异'],['execute','执行差异迁移'],['completed','完成与记录']];
function renderDiffWorkflow(){
  const host=document.getElementById('diffWorkflow');if(!host)return;
  host.innerHTML='<div class="workflow-title">差异迁移流程 · 已完成 '+Math.min(diffFlowStage,2)+' / 3 步</div>'+diffFlowNodes.map((n,i)=>{const status=i<diffFlowStage?'succeeded':i===diffFlowStage?'active':'pending';return '<div class="workflow-node '+status+'"><div class="workflow-dot">'+(i+1)+'</div><div><div class="workflow-label">'+n[1]+'</div><div class="workflow-detail">'+(status==='active'?'当前节点':status==='succeeded'?'已完成':'等待执行')+'</div></div><div class="workflow-status">'+(status==='active'?'进行中':status==='succeeded'?'完成':'未开始')+'</div></div>'}).join('');
}
const originalScanDiff=scanDiff,originalReleaseDiff=releaseDiff;
scanDiff=async function(){diffFlowStage=0;renderDiffWorkflow();const succeeded=await originalScanDiff();if(succeeded){diffFlowStage=1}renderDiffWorkflow();return succeeded};
releaseDiff=async function(){diffFlowStage=Math.max(diffFlowStage,1);renderDiffWorkflow();try{await originalReleaseDiff();diffFlowStage=2;renderDiffWorkflow()}catch(e){renderDiffWorkflow();throw e}};
renderDiffWorkflow();
const baseRender=render;
render=function(){baseRender();const j=overview.job||{},running=['queued','running','cancelling'].includes(j.status);if(document.getElementById('release'))document.getElementById('release').textContent=running&&j.operation==='full_release'?'全量迁移中...':'开始全量迁移';if(document.getElementById('productionToStaging'))document.getElementById('productionToStaging').textContent=running&&j.operation==='production_to_staging'?'同步中...':'从生产同步到 Staging';if(document.getElementById('stagingToProduction')){document.getElementById('stagingToProduction').disabled=busy();document.getElementById('stagingToProduction').textContent=running&&j.operation==='staging_to_production'?'Production 发布中...':'从 Staging 发布到 Production'}if(document.getElementById('cleanupStart'))document.getElementById('cleanupStart').textContent=running&&j.operation==='user_data_cleanup'?'清理中...':'清除全部用户业务数据';if(document.getElementById('cancel')){document.getElementById('cancel').disabled=j.status==='cancelling';document.getElementById('cancel').textContent=j.status==='cancelling'?'停止中...':'停止任务'}if(typeof diffPlan!=='undefined'&&document.getElementById('diffRelease')&&running)document.getElementById('diffRelease').disabled=true};
</script></body></html>'''


if __name__ == "__main__":
    app.run(host=APP_HOST, port=APP_PORT, debug=False, use_reloader=False)
