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

import psycopg2
from flask import Flask, jsonify, request, send_file, session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.domain.database_release_services import (  # noqa: E402
    build_database_release_overview,
    cancel_database_release,
    get_database_release_schema_summary,
    verify_database_release_schema,
    get_database_release_log,
    generate_database_release_schema,
    get_database_table_inventory,
    scan_database_release_schema,
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
        "mode": "full_and_schema_safe_release",
        "release_targets": release_overview["targets"],
        "job": release_overview["job"],
    })


@app.get("/api/overview/schema-summary")
def overview_schema_summary():
    """Read-only local-to-target structural statistics for the overview."""
    return jsonify({"ok": True, "summary": get_database_release_schema_summary()})


@app.get("/api/schema-diff/scan")
def schema_diff_scan():
    """Fast metadata-only scan; it never hashes or reads business rows."""
    target = request.args.get("target") or "staging"
    try:
        return jsonify({"ok": True, "scan": scan_database_release_schema(target)})
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/api/schema-inventory")
def schema_inventory():
    target = request.args.get("target") or "staging"
    try:
        return jsonify({"ok": True, "inventory": get_database_table_inventory(target)})
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/api/schema-diff/verify")
def schema_diff_verify():
    """Final read-only schema and migration-ledger equivalence check."""
    target = request.args.get("target") or "staging"
    try:
        return jsonify({"ok": True, "verification": verify_database_release_schema(target)})
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/schema-diff/generate")
@_require_csrf
def schema_diff_generate():
    payload = request.get_json(silent=True) or {}
    try:
        result = generate_database_release_schema(payload.get("target") or "staging")
        return jsonify({"ok": True, "result": result}), 201
    except (ValueError, RuntimeError, psycopg2.Error) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Schema package generation failed")
        return jsonify({"ok": False, "error": f"database_release_schema_generate_failed: {exc.__class__.__name__}"}), 500


@app.post("/api/schema-diff/release")
@_require_csrf
def schema_diff_release():
    payload = request.get_json(silent=True) or {}
    if payload.get("review_confirmed") is not True:
        return jsonify({"ok": False, "error": "database_release_schema_review_confirmation_required"}), 400
    try:
        job = start_database_release_delta(
            payload.get("target") or "staging",
            payload.get("report_path"),
            payload.get("diff_fingerprint"),
            payload.get("package_ids") or [],
            confirm_production=payload.get("confirm_production") is True,
            schema_only=True,
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
</style><style>
.shell{max-width:1480px;width:100%;min-height:100vh;display:grid;grid-template-columns:232px minmax(0,1fr);gap:28px;align-items:start;padding:24px 28px}.shell>.console-sidebar{grid-column:1;grid-row:1 / span 99}.shell> :not(.console-sidebar){grid-column:2}.console-sidebar{position:sticky;top:24px;background:#102b46;color:#e7f0f8;border-radius:12px;padding:18px 12px;box-shadow:0 10px 30px rgba(16,43,70,.12)}.console-brand{padding:4px 10px 18px;border-bottom:1px solid rgba(231,240,248,.16);margin-bottom:12px}.console-brand strong{display:block;font-size:16px;letter-spacing:.02em}.console-brand span{display:block;margin-top:5px;color:#9fb7ca;font-size:11px}.console-nav{display:grid;gap:4px}.console-nav-item{width:100%;display:flex;align-items:center;gap:10px;border:1px solid transparent;border-radius:8px;padding:11px 10px;background:transparent;color:#bad0e0;text-align:left;font-size:13px}.console-nav-item:hover{background:rgba(255,255,255,.07);color:#fff}.console-nav-item.active{background:#1b5d8f;border-color:#4489ba;color:#fff;box-shadow:0 4px 12px rgba(0,0,0,.12)}.console-nav-icon{width:22px;height:22px;display:grid;place-items:center;border-radius:6px;background:rgba(255,255,255,.09);font-size:11px;font-weight:800}.console-nav-caption{display:block;color:#7896ac;font-size:10px;margin:16px 10px 6px}.console-content-section.is-hidden{display:none!important}.overview-difference-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}.overview-difference-card{border:1px solid var(--line);border-radius:8px;padding:14px;background:#f8fbfe}.overview-difference-card.unavailable{background:#fff8f7;border-color:#e5aaa4}.overview-difference-head{display:flex;justify-content:space-between;gap:10px;align-items:baseline}.overview-difference-head h3{margin:0;font-size:14px}.overview-difference-status{font-size:11px;color:#218653;font-weight:700}.overview-difference-card.unavailable .overview-difference-status{color:var(--red)}.overview-difference-total{font-size:25px;font-weight:750;margin:12px 0 3px}.overview-difference-label{font-size:11px;color:var(--muted)}.overview-difference-breakdown{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.overview-difference-breakdown span{font-size:11px;color:var(--muted);padding:4px 6px;background:#fff;border:1px solid #e6edf3;border-radius:999px}.overview-difference-error{margin-top:10px;font-size:12px;color:var(--red);line-height:1.55}.inventory-toolbar{display:flex;justify-content:space-between;gap:12px;align-items:end;flex-wrap:wrap}.inventory-summary{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.inventory-count{min-width:112px;padding:9px 12px;border:1px solid var(--line);border-radius:7px;background:#f8fbfe;font-size:12px}.inventory-count strong{display:block;font-size:16px;margin-bottom:2px}.inventory-count-label{display:block}.inventory-count-difference{display:block;margin-top:6px;color:var(--red);font-size:11px;font-weight:700}.inventory-count-unavailable{display:block;margin-top:6px;color:var(--red);font-size:11px;font-weight:700}.inventory-table-wrap{overflow:auto;border:1px solid var(--line);border-radius:8px}.inventory-table{width:100%;min-width:980px;border-collapse:collapse;font-size:12px}.inventory-table th{background:#f7fafc;color:var(--muted);font-size:11px;text-align:left;white-space:nowrap}.inventory-table th,.inventory-table td{padding:11px 12px;border-bottom:1px solid #edf1f5;vertical-align:top}.inventory-table tr:last-child td{border-bottom:0}.inventory-table .table-name{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink);font-size:11px}.inventory-badge{display:inline-flex;padding:4px 7px;border-radius:999px;background:#eaf3fa;color:#1e5f8f;font-size:11px;white-space:nowrap}.inventory-status{white-space:nowrap}.inventory-status.mismatch{color:var(--red);font-weight:700}.inventory-filter{max-width:300px}@media(max-width:860px){.shell{display:block;padding:14px}.console-sidebar{position:static;margin-bottom:16px}.console-nav{display:flex;overflow-x:auto;padding-bottom:2px}.console-nav-item{min-width:132px;justify-content:flex-start}.console-nav-caption{display:none}.shell> :not(.console-sidebar){width:100%}.head{display:block}.head button{margin-top:14px}.stats{grid-template-columns:1fr 1fr}.overview-difference-grid{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
</style><style>
.inventory-summary{display:grid;gap:10px;margin:14px 0}.inventory-difference-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.inventory-difference-summary>div{padding:11px 12px;border:1px solid #dceaf3;border-radius:7px;background:#f8fbfe}.inventory-difference-summary strong{display:block;font-size:19px}.inventory-difference-summary span{display:block;margin-top:3px;color:var(--muted);font-size:11px}.inventory-count-grid{display:flex;gap:8px;flex-wrap:wrap}.inventory-count-detail{display:block;margin-top:6px;color:var(--muted);font-size:11px}.inventory-scan-note{color:var(--muted);font-size:11px;line-height:1.5}@media(max-width:860px){.inventory-difference-summary{grid-template-columns:1fr}}
</style><style>
.schema-review{margin-top:14px;border:1px solid #b9d5e8;border-radius:9px;background:#f8fcff;padding:14px}.schema-review-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.schema-review-head h3{margin:0;font-size:14px}.schema-review-head p{margin:5px 0 0;font-size:12px;color:var(--muted);line-height:1.6}.schema-review-status{font-size:11px;font-weight:700;color:#1769aa;white-space:nowrap}.schema-review-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:14px}.schema-review-stat{border:1px solid #dceaf3;border-radius:7px;padding:10px;background:#fff}.schema-review-stat strong{display:block;font-size:18px;margin-bottom:3px}.schema-review-stat span{font-size:11px;color:var(--muted)}.schema-review-block{margin-top:12px;border-top:1px solid #dceaf3;padding-top:12px}.schema-review-block h4{margin:0 0 7px;font-size:12px}.schema-review-list{display:flex;flex-wrap:wrap;gap:6px}.schema-review-list span{padding:4px 7px;border:1px solid #dceaf3;border-radius:999px;background:#fff;font-size:11px;color:var(--ink)}.schema-review-warning{padding:10px 11px;border-radius:7px;background:#fff8e8;border:1px solid #f0d58a;color:#7a5510;font-size:12px;line-height:1.6}.schema-review-danger{padding:10px 11px;border-radius:7px;background:#fff5f3;border:1px solid #e5aaa4;color:var(--red);font-size:12px;line-height:1.6}.schema-review-confirm{display:flex;gap:8px;align-items:flex-start;margin-top:14px;padding-top:12px;border-top:1px solid #dceaf3;font-size:12px;line-height:1.55;color:var(--ink);cursor:pointer}.schema-review-confirm input{margin-top:3px;accent-color:var(--blue)}.schema-review-raw{margin-top:12px;font-size:12px;color:var(--muted)}.schema-review-raw summary{cursor:pointer;color:var(--blue);font-weight:600}@media(max-width:760px){.schema-review-grid{grid-template-columns:1fr}}
</style></head><body><main class="shell">
<aside class="console-sidebar" aria-label="数据库迁移导航"><div class="console-brand"><strong>数据库发布控制台</strong><span>5051 · 安全升级与数据治理</span></div><span class="console-nav-caption">工作区</span><nav class="console-nav"><button class="console-nav-item active" type="button" data-console-section="overview"><span class="console-nav-icon">总</span><span>总览</span></button><button class="console-nav-item" type="button" data-console-section="full-release"><span class="console-nav-icon">全</span><span>全量发布</span></button><button class="console-nav-item" type="button" data-console-section="schema-release"><span class="console-nav-icon">构</span><span>结构安全升级</span></button><button class="console-nav-item" type="button" data-console-section="cleanup"><span class="console-nav-icon">清</span><span>数据清理</span></button><button class="console-nav-item" type="button" data-console-section="inventory"><span class="console-nav-icon">表</span><span>表结构与分层</span></button><button class="console-nav-item" type="button" data-console-section="operations"><span class="console-nav-icon">记</span><span>回滚记录</span></button></nav></aside>
<header class="head"><div><div class="eyebrow">DATABASE RELEASE CONTROL</div><h1>数据库迁移</h1><p>5051 数据迁移控制台。日常升级仅执行零业务数据写入的结构安全升级；全量替换、同步、清理与回滚均保留独立保护流程。</p></div><button id="refresh" type="button" onclick="refreshStatus(this)">刷新状态</button></header>
<section class="stats" id="stats"></section>
<section id="overview-dashboard" class="panel"><div class="section-title"><div><h2>本地与目标环境结构差异</h2><p>仅比较表、字段、索引、约束与迁移账本元数据；不会读取、计算或修改业务数据。</p></div><span class="eyebrow">只读统计</span></div><div id="overview-difference-grid" class="overview-difference-grid"><div class="notice">正在读取 Staging 与 Production 的结构摘要...</div></div><div id="overview-difference-meta" class="notice"></div></section>
<div class="release-actions-grid">
<section class="panel action-panel" style="margin-top:18px"><div class="section-title"><div><h2>全量迁移</h2><p>以本地完整数据库为来源，先恢复到目标临时库校验，通过后才切换目标数据库。</p></div><span class="eyebrow">高影响操作</span></div><div class="row"><label class="field">目标环境<select id="releaseTarget"></select></label><button id="release" class="primary primary-action" type="button" onclick="startRelease(this)">开始全量迁移</button><button id="cancel" class="danger" type="button" onclick="cancelRelease(this)" hidden>停止任务</button></div><div class="warning" style="margin-top:14px">目标环境的用户及其关联业务数据会在切换前恢复；校验未通过时不会替换目标数据库，原数据库会保留为回滚点。</div></section>
<section class="panel source-panel" style="margin-top:16px"><div class="section-title"><div><h2>生产 → Staging 全量同步</h2><p>将 Production 的完整数据库快照恢复到 Staging 临时库，校验通过后再切换；适合在 Staging 上验证全量发布或结构安全升级。</p></div><span class="eyebrow" style="color:#9a6700">高风险 · 仅 Staging</span></div><div class="row"><div class="field"><span>同步方向</span><strong>Production → Staging</strong></div><button id="productionToStaging" class="primary" style="background:#9a6700;border-color:#9a6700" type="button" onclick="startProductionToStaging(this)">从生产同步到 Staging</button></div><div class="warning" style="margin-top:14px">这会替换 Staging 当前数据库内容。Staging 原数据库会先重命名为备份，生产环境凭据不会直接覆盖 Staging 的受保护配置；确认前请确保没有正在进行的 staging 测试。</div></section>
<section class="panel publish-panel" style="margin-top:16px"><div class="section-title"><div><h2>Staging → Production 全量发布</h2><p>将经过 Staging 验证的完整数据库快照发布到 Production；只有临时库校验通过后才切换生产数据库。</p></div><span class="eyebrow" style="color:var(--red)">高风险 · 需确认</span></div><div class="row"><div class="field"><span>发布方向</span><strong>Staging → Production</strong></div><button id="stagingToProduction" class="primary" style="background:var(--red);border-color:var(--red)" type="button" onclick="startStagingToProduction(this)">从 Staging 发布到 Production</button></div><div class="warning" style="margin-top:14px">Production 当前数据库会在切换前保留为回滚备份。此操作会覆盖 Production 的数据库内容，不会执行任何发布，直到你在确认框中再次确认。</div></section>
</div>
<section class="panel cleanup-panel" style="margin-top:16px"><div class="section-title"><div><h2>清除用户业务数据</h2><p>保留所有用户账户、密码、角色和租户归属；清除站内信、智能体会话、记忆、自选股、评论、标注、洞见草稿/发布内容、访问与用量记录、订阅订单等用户产生的数据。</p></div><span class="eyebrow" style="color:var(--red)">不可逆 · 先备份</span></div><div class="row"><label class="field">目标环境<select id="cleanupTarget"></select></label><button id="cleanupStart" class="danger" type="button" onclick="startUserDataCleanup(this)">清除全部用户业务数据</button></div><div class="warning" style="margin-top:14px">执行前会自动生成完整 PostgreSQL dump 和可恢复的 SQL 文件，并保留该目标环境最近 2 份清理前备份。指标、行情、行业、宏观主数据、租户配置、订阅产品和扫码邀请配置不受影响。</div><label class="cleanup-confirm" style="margin-top:14px">请输入确认文本 <strong>CLEAR ALL USER BUSINESS DATA</strong><input id="cleanupConfirmation" autocomplete="off" placeholder="CLEAR ALL USER BUSINESS DATA"></label><div id="cleanupStatus" class="notice">尚未执行用户业务数据清理。</div><div class="panel-heading" style="margin-top:16px"><h2>清理前备份</h2><span>最近 2 份 · 可下载 SQL</span></div><div id="userDataBackups" class="notice">正在读取...</div></section>
<section class="panel secondary-panel" style="margin-top:16px"><div class="section-title"><div><h2>生产结构安全升级</h2><p>只比较本地与目标库的表结构元数据，不读取、不覆盖业务内容。仅允许新增表、字段、索引和约束；如历史记录缺少规范的租户登记，仅补齐对应的租户元数据，其他危险差异会阻断执行。</p></div><span class="eyebrow">零业务内容写入</span></div><div class="row"><label class="field">目标环境<select id="schemaDiffTarget"></select></label><button id="schemaDiffScan" type="button" onclick="scanSchemaDiff()">比较并生成结构包</button><button id="schemaDiffRelease" class="primary" type="button" onclick="releaseSchemaDiff()" disabled>确认审核后应用</button></div><div id="schemaDiffStatus" class="notice">执行前会重新比较结构；Production 应用前自动创建完整回滚备份。</div><div id="schemaDiffWorkflow" class="workflow" aria-live="polite"></div><div id="schemaDiffReview" class="schema-review" aria-live="polite"><div class="notice">先比较并生成结构包，随后在这里完成差异审核。</div></div><details class="schema-review-raw"><summary>原始结构审计数据</summary><pre id="schemaDiffReport" style="max-height:260px;min-height:100px;margin-top:8px">暂无结构安全升级报告</pre></details></section>
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
  Promise.all([load(),loadOverviewSchemaSummary()]).then(()=>{if(button){button.classList.remove('is-loading');button.classList.add('is-success');button.setAttribute('aria-busy','false');button.textContent='已刷新'}toast('状态已刷新')}).catch(e=>{if(button){button.classList.remove('is-loading');button.classList.add('is-failure');button.setAttribute('aria-busy','false');button.textContent='刷新失败'}toast('读取状态失败：'+e.message)}).finally(()=>setTimeout(()=>{if(button){button.disabled=false;button.classList.remove('is-success','is-failure');button.removeAttribute('aria-busy');button.textContent='刷新状态'}},1200));
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
	  host.innerHTML='<div class="workflow-title">'+esc(job.operation==='release'?'结构安全升级流程':'全量迁移流程')+' · 已完成 '+esc(progress.workflow_completed_steps||0)+' / '+esc(progress.workflow_total_steps||nodes.length)+' 步</div>'+nodes.map(n=>'<div class="workflow-node '+esc(n.status)+'"><div class="workflow-dot">'+esc(n.order)+'</div><div><div class="workflow-label">'+esc(n.label)+'</div><div class="workflow-detail">'+(n.status==='active'?'正在执行':n.status==='succeeded'?'已完成':n.status==='failed'?'失败':'等待执行')+'</div></div><div class="workflow-status">'+(n.status==='active'?'进行中':n.status==='succeeded'?'完成':n.status==='failed'?'失败':'未开始')+'</div></div>').join('');
}
setInterval(renderJobWorkflow,500);renderJobWorkflow();
</script>
<script>
function diffText(value){return JSON.stringify(value,null,2)}
async function diffRequest(path,body){return api(path,{method:'POST',body:JSON.stringify(body)})}
function copyReleaseTargets(targetId){const source=document.getElementById('releaseTarget'),target=document.getElementById(targetId);if(!source||!target)return;const selected=target.value;target.innerHTML=source.innerHTML;if([...target.options].some(option=>option.value===selected))target.value=selected}
function renderSchemaDiffTargets(){copyReleaseTargets('schemaDiffTarget')}
renderSchemaDiffTargets();
const baseRender=render;
render=function(){baseRender();if(typeof renderSchemaDiffTargets==='function')renderSchemaDiffTargets();const j=overview.job||{},running=['queued','running','cancelling'].includes(j.status);if(document.getElementById('release'))document.getElementById('release').textContent=running&&j.operation==='full_release'?'全量迁移中...':'开始全量迁移';if(document.getElementById('productionToStaging'))document.getElementById('productionToStaging').textContent=running&&j.operation==='production_to_staging'?'同步中...':'从生产同步到 Staging';if(document.getElementById('stagingToProduction')){document.getElementById('stagingToProduction').disabled=busy();document.getElementById('stagingToProduction').textContent=running&&j.operation==='staging_to_production'?'Production 发布中...':'从 Staging 发布到 Production'}if(document.getElementById('cleanupStart'))document.getElementById('cleanupStart').textContent=running&&j.operation==='user_data_cleanup'?'清理中...':'清除全部用户业务数据';if(document.getElementById('cancel')){document.getElementById('cancel').disabled=j.status==='cancelling';document.getElementById('cancel').textContent=j.status==='cancelling'?'停止中...':'停止任务'}};
let schemaDiffPlan=null,schemaDiffScanResult=null,schemaDiffReviewInventory=null,schemaDiffReviewConfirmed=false,schemaDiffFlowStage=0,schemaDiffFlowFailed=false,schemaDiffFinalVerificationTarget='',schemaDiffSubmittedJobId='',schemaDiffSubmittedTarget='';
function schemaReviewChips(items,emptyText){const rows=Array.isArray(items)?items:[];return rows.length?'<div class="schema-review-list">'+rows.map(item=>'<span>'+esc(item)+'</span>').join('')+'</div>':'<div class="notice">'+esc(emptyText)+'</div>'}
function resetSchemaDiffReleaseButton(){const button=document.getElementById('schemaDiffRelease');if(!button)return;button.classList.remove('is-loading','is-success','is-failure');button.removeAttribute('aria-busy');button.textContent='确认审核后应用'}
function resetSchemaDiffSubmissionState(){schemaDiffSubmittedJobId='';schemaDiffSubmittedTarget='';resetSchemaDiffReleaseButton()}
function updateSchemaDiffReleaseAvailability(){const button=document.getElementById('schemaDiffRelease'),blockers=schemaDiffPlan?.blockers||[],hasPackage=Boolean(schemaDiffPlan?.generated_packages?.length),hasSubmittedJob=Boolean(schemaDiffSubmittedJobId);if(button){button.disabled=hasSubmittedJob||!hasPackage||Boolean(blockers.length)||!schemaDiffReviewConfirmed;if(!hasSubmittedJob)resetSchemaDiffReleaseButton()}}
function renderFinalSchemaVerification(verification){
  const host=document.getElementById('schemaDiffReview');if(!host||!verification)return;
  const status=verification.ok?'通过':'未通过',items=verification.differences||[],observed=verification.non_structural_migration_ledger_difference||{},observedItems=[...(observed.local_only||[]).map(name=>'本地历史主数据账本：'+name),...(observed.target_only||[]).map(name=>'目标历史主数据账本：'+name),...(observed.checksum_mismatch||[]).map(name=>'历史主数据账本 checksum 不一致：'+name)];
  host.insertAdjacentHTML('beforeend','<div class="schema-review-block '+(verification.ok?'schema-review-warning':'schema-review-danger')+'"><h4>最终结构等价核验</h4><div><strong>'+esc(status)+'</strong> · '+esc(verification.note||'仅核对结构和迁移账本。')+'</div>'+(items.length?schemaReviewChips(items,''):'<div class="notice">结构和结构迁移 checksum 已一致。</div>')+(observedItems.length?'<div class="schema-review-block schema-review-warning"><h4>历史主数据迁移账本观察项</h4><div>这些记录不代表表结构漂移，且不会由结构安全升级自动补写；请在主数据发布或人工审计时处理。</div>'+schemaReviewChips(observedItems,'')+'</div>':'')+'</div>');
}
async function verifySchemaDiff(target,afterPlan){
  try{const data=await api('/api/schema-diff/verify?target='+encodeURIComponent(target));renderFinalSchemaVerification(data.verification||{});return data.verification||{}}catch(error){renderFinalSchemaVerification({ok:false,differences:['核验失败：'+error.message]});return {ok:false}}
}
async function loadFinalSchemaVerification(target){
  if(!target||schemaDiffFinalVerificationTarget===target)return;
  schemaDiffFinalVerificationTarget=target;
  await verifySchemaDiff(target);
}
function renderSchemaDiffReview(inventory){
  const host=document.getElementById('schemaDiffReview');if(!host)return;
  if(inventory!==undefined)schemaDiffReviewInventory=inventory;inventory=schemaDiffReviewInventory;
  const scan=schemaDiffScanResult?.scan||{},schema=scan.schema||{},summary=scan.summary||{},migration=scan.schema_migration_difference||{};
  const plan=schemaDiffPlan||{},actions=(plan.details||{}).schema||[],blockers=plan.blockers||[],packages=plan.generated_packages||[];
  if(!schemaDiffPlan){host.innerHTML='<div class="notice">先比较并生成结构包，随后在这里完成差异审核。</div>';return}
  const actionLabels=actions.map(action=>action.action==='reconcile_missing_tenant_registry_references'?'补齐缺失租户登记 · '+String(action.table||'')+' → tenant_registry':[action.action,action.table,action.column||action.index||action.constraint||action.migration].filter(Boolean).join(' · '));
  const inventoryRows=(inventory?.rows||[]).filter(row=>row.schema_status&&!['一致','目标暂不可用','发布控制表（忽略）'].includes(row.schema_status));
  const inventoryLabels=inventoryRows.map(row=>row.table_name+' · '+row.category_label+' · '+row.status);
  const inventorySection=inventory?.error?'<div class="schema-review-warning">表结构与数据分层交叉核对暂不可用：'+esc(inventory.error)+'</div>':'<div class="schema-review-warning">分层清单交叉核对：发现 '+esc(inventoryLabels.length)+' 个本地/目标表存在性差异。该清单仅核对表存在性；字段、索引与约束漂移以本次结构扫描为准。</div>'+schemaReviewChips(inventoryLabels,'表存在性与分层清单一致。');
  const reviewState=blockers.length?'存在阻断项，不能应用。':packages.length?'请审阅所有项目并勾选确认后再应用。':'未生成结构包：无需写入结构，流程将继续执行最终等价核验。';
  host.innerHTML='<div class="schema-review-head"><div><h3>差异审核</h3><p>以下内容来自本次扫描和生成的结构包，应用前将再次校验差异指纹。</p></div><span class="schema-review-status">'+esc(blockers.length?'已阻断':packages.length?'待审核':'无需应用')+'</span></div>'
    +'<div class="schema-review-grid"><div class="schema-review-stat"><strong>'+esc(actions.length)+'</strong><span>拟执行新增操作</span></div><div class="schema-review-stat"><strong>'+esc(summary.schema_difference_tables||0)+'</strong><span>已有表定义差异</span></div><div class="schema-review-stat"><strong>'+esc(blockers.length)+'</strong><span>阻断项</span></div></div>'
    +'<div class="schema-review-block"><h4>拟执行的结构操作</h4>'+schemaReviewChips(actionLabels,'没有新增操作；不会创建结构包。')+'</div>'
    +'<div class="schema-review-block"><h4>表结构扫描差异</h4>'+schemaReviewChips((schema.local_only_tables||[]).map(name=>'仅本地：'+name),'没有仅本地表。')+schemaReviewChips((schema.target_only_tables||[]).map(name=>'仅目标：'+name),'没有仅目标表。')+schemaReviewChips((schema.different_tables||[]).map(name=>'定义不同：'+name),'没有已有表定义差异。')+'</div>'
    +'<div class="schema-review-block"><h4>迁移账本差异</h4>'+schemaReviewChips((migration.local_only||[]).map(name=>'仅本地迁移：'+name),'没有仅本地迁移。')+schemaReviewChips((migration.target_only||[]).map(name=>'仅目标迁移：'+name),'没有仅目标迁移。')+schemaReviewChips((migration.checksum_mismatch||[]).map(name=>'校验和不一致：'+name),'没有迁移校验和不一致。')+'</div>'
    +'<div class="schema-review-block"><h4>与表结构与数据分层的交叉核对</h4>'+inventorySection+'</div>'
    +(blockers.length?'<div class="schema-review-block schema-review-danger">结构包已被阻断：'+schemaReviewChips(blockers.map(item=>item.table||item.reason||'未说明原因'),'')+'</div>':'')
    +(packages.length&&!blockers.length?'<label class="schema-review-confirm"><input id="schemaDiffReviewConfirmed" type="checkbox" '+(schemaDiffReviewConfirmed?'checked':'')+' onchange="confirmSchemaDiffReview(this.checked)"><span>我已审阅本次差异、分层交叉核对和拟执行操作，确认只应用上述新增结构及明确列出的租户登记补齐；我理解应用前系统会再次校验差异指纹。</span></label>':'<div class="schema-review-block schema-review-warning">'+esc(reviewState)+'</div>');
}
function confirmSchemaDiffReview(confirmed){schemaDiffReviewConfirmed=Boolean(confirmed);schemaDiffFlowStage=confirmed?4:2;renderSchemaDiffWorkflow();updateSchemaDiffReleaseAvailability();document.getElementById('schemaDiffStatus').textContent=confirmed?'审核确认完成，可以提交结构包应用。':'请完成差异审核确认后再应用结构包。'}
function schemaWorkflowDetail(key,status){if(status==='active')return '当前节点';if(status!=='succeeded')return '等待执行';const noSchemaPackage=!schemaDiffPlan?.generated_packages?.length;if(noSchemaPackage&&key==='confirm')return '无需用户确认';if(noSchemaPackage&&key==='execute')return '无需应用';if(key==='verify')return '已核验';if(key==='completed')return '流程闭环完成';return '已完成'}
function renderSchemaDiffWorkflow(){const host=document.getElementById('schemaDiffWorkflow');if(!host)return;const nodes=[['compare','比较结构'],['generate','生成结构包'],['review','差异审核'],['confirm','用户确认'],['execute','应用结构包'],['verify','最终结构等价核验'],['completed','完成与记录']];host.innerHTML='<div class="workflow-title">结构安全升级流程 · 已完成 '+Math.min(schemaDiffFlowStage,7)+' / 7 步</div>'+nodes.map((n,i)=>{const status=schemaDiffFlowFailed&&i===schemaDiffFlowStage?'failed':i<schemaDiffFlowStage?'succeeded':i===schemaDiffFlowStage?'active':'pending',detail=schemaWorkflowDetail(n[0],status);return '<div class="workflow-node '+status+'"><div class="workflow-dot">'+(i+1)+'</div><div><div class="workflow-label">'+n[1]+'</div><div class="workflow-detail">'+detail+'</div></div><div class="workflow-status">'+(status==='active'?'进行中':status==='failed'?'失败':status==='succeeded'?(detail==='无需用户确认'||detail==='无需应用'?'自动通过':'完成'):'未开始')+'</div></div>'}).join('')}
async function scanSchemaDiff(){const button=document.getElementById('schemaDiffScan');if(button&&button.disabled)return false;try{schemaDiffPlan=null;schemaDiffScanResult=null;schemaDiffReviewInventory=null;schemaDiffReviewConfirmed=false;schemaDiffFlowStage=0;schemaDiffFlowFailed=false;schemaDiffFinalVerificationTarget='';resetSchemaDiffSubmissionState();renderSchemaDiffWorkflow();renderSchemaDiffReview();updateSchemaDiffReleaseAvailability();const select=document.getElementById('schemaDiffTarget');const target=select.value||'staging';const targetLabel=select.options[select.selectedIndex]?.textContent||target;if(button){button.disabled=true;button.classList.add('is-loading');button.setAttribute('aria-busy','true');button.textContent='正在比较...'}document.getElementById('schemaDiffStatus').textContent='正在读取 '+targetLabel+' 的结构元数据，不读取业务数据...';document.getElementById('schemaDiffReport').textContent='目标环境：'+targetLabel+'\n正在比较表、字段、索引和约束...';const scan=await api('/api/schema-diff/scan?target='+encodeURIComponent(target));schemaDiffScanResult=scan;schemaDiffFlowStage=1;renderSchemaDiffWorkflow();document.getElementById('schemaDiffStatus').textContent='结构比较完成，正在生成 '+targetLabel+' 的幂等结构包...';const generated=await diffRequest('/api/schema-diff/generate',{target});schemaDiffPlan=generated.result||{};let inventory=null;try{const inventoryResponse=await api('/api/schema-inventory?target='+encodeURIComponent(target));inventory=inventoryResponse.inventory||{}}catch(error){inventory={error:error.message}}schemaDiffFlowStage=2;renderSchemaDiffWorkflow();renderSchemaDiffReview(inventory);document.getElementById('schemaDiffReport').textContent=diffText({scan:scan.scan,generated:schemaDiffPlan,inventory});const blockers=schemaDiffPlan.blockers||[];const packages=schemaDiffPlan.generated_packages||[];if(blockers.length){document.getElementById('schemaDiffStatus').textContent='结构升级被阻断，请处理审核区中的阻断项。'}else if(packages.length){document.getElementById('schemaDiffStatus').textContent='结构包已生成。预期新增表会在最终核验前显示为差异；请完成审核确认后应用，最终严格等价核验会在应用完成后执行。'}else{document.getElementById('schemaDiffStatus').textContent='没有新增结构包，正在执行最终结构等价核验...';const verification=await verifySchemaDiff(target);schemaDiffFinalVerificationTarget=target;if(verification.ok){schemaDiffFlowStage=7;document.getElementById('schemaDiffStatus').textContent='无需应用结构包，全部步骤已核验通过。'}else{document.getElementById('schemaDiffStatus').textContent='最终结构等价核验未通过，请根据审核结果处理差异。'}}renderSchemaDiffWorkflow();updateSchemaDiffReleaseAvailability();if(button){button.classList.add('is-success')}return true}catch(e){document.getElementById('schemaDiffStatus').textContent='结构升级准备失败：'+e.message;document.getElementById('schemaDiffReport').textContent='结构升级准备未完成。';if(button)button.classList.add('is-failure');return false}finally{if(button){button.disabled=false;button.classList.remove('is-loading');button.removeAttribute('aria-busy');button.textContent='比较并生成结构包';setTimeout(()=>button.classList.remove('is-success','is-failure'),2200)}}}
async function releaseSchemaDiff(){const button=document.getElementById('schemaDiffRelease');if(!schemaDiffPlan||!schemaDiffReviewConfirmed||!schemaDiffPlan.generated_packages||!schemaDiffPlan.generated_packages.length||button&&button.disabled)return;const target=schemaDiffPlan.target;const production=target==='production';if(!window.confirm('确认将已审核的结构包应用到 '+target+'？只执行审核区列出的新增结构及明确列出的租户登记补齐，不修改或覆盖业务内容。'+(production?' Production 执行前会创建完整回滚备份。':'')))return;try{button.disabled=true;button.classList.add('is-loading');button.setAttribute('aria-busy','true');button.textContent='正在应用...';schemaDiffFlowStage=4;renderSchemaDiffWorkflow();document.getElementById('schemaDiffStatus').textContent='正在重新校验结构指纹并提交应用任务...';const data=await diffRequest('/api/schema-diff/release',{target,report_path:schemaDiffPlan.report_path,diff_fingerprint:schemaDiffPlan.diff_fingerprint,package_ids:schemaDiffPlan.generated_packages.map(item=>item.id),review_confirmed:true,confirm_production:production});const job=data.job||{};if(!job.id)throw new Error('database_release_job_id_missing');schemaDiffSubmittedJobId=job.id;schemaDiffSubmittedTarget=target;document.getElementById('schemaDiffStatus').textContent='结构安全升级任务已创建：'+job.id;button.classList.remove('is-loading');button.classList.add('is-success');button.setAttribute('aria-busy','false');button.textContent='已提交';await load()}catch(e){document.getElementById('schemaDiffStatus').textContent='结构包未应用：'+e.message;button.classList.remove('is-loading');button.classList.add('is-failure');button.removeAttribute('aria-busy');button.disabled=false;button.textContent='确认审核后应用'}}
renderSchemaDiffWorkflow();
function syncSchemaDiffWorkflowFromJob(){const job=overview.job||{},packages=job.package_plan||[];const isSchemaRelease=job.operation==='release'&&packages.some(item=>item&&item.type==='schema');const isCurrentSubmission=Boolean(schemaDiffPlan&&schemaDiffSubmittedJobId&&job.id===schemaDiffSubmittedJobId&&job.target===schemaDiffSubmittedTarget&&job.target===schemaDiffPlan.target);if(!isSchemaRelease||!isCurrentSubmission)return;const events=job.events||[],failure=[...events].reverse().find(item=>item&&item.status==='failed'&&item.stage==='error')||[...events].reverse().find(item=>item&&item.status==='failed');const finalVerificationStarted=events.some(item=>/Final schema equivalence verification/.test(String((item||{}).title||'')+' '+String((item||{}).detail||'')));const transactionCommitted=events.some(item=>/Schema package SQL transaction committed|Package workflow committed/.test(String((item||{}).title||'')+' '+String((item||{}).detail||'')));const status=document.getElementById('schemaDiffStatus'),release=document.getElementById('schemaDiffRelease');if(job.status==='failed'){schemaDiffFlowStage=finalVerificationStarted?5:4;schemaDiffFlowFailed=true;renderSchemaDiffWorkflow();if(status)status.textContent='结构安全升级失败：'+String((failure||{}).detail||job.progress?.message||'请查看迁移日志。')+(transactionCommitted?' 结构包 SQL 已提交，但最终严格核验未通过；请根据审核结果处理剩余差异。':' 本次 SQL 事务已回滚，未部分写入。');if(finalVerificationStarted)loadFinalSchemaVerification(job.target);if(release)release.disabled=true;return}if(job.status==='succeeded'){schemaDiffFlowStage=7;schemaDiffFlowFailed=false;renderSchemaDiffWorkflow();if(status)status.textContent='结构安全升级完成，最终结构等价核验已通过。';loadFinalSchemaVerification(job.target);if(release){release.disabled=true;release.classList.remove('is-loading','is-failure');release.classList.add('is-success');release.removeAttribute('aria-busy');release.textContent='已完成'}return}if(['queued','running','cancelling'].includes(job.status)){schemaDiffFlowStage=finalVerificationStarted?5:4;schemaDiffFlowFailed=false;renderSchemaDiffWorkflow();if(status)status.textContent=finalVerificationStarted?'正在进行最终结构等价核验...':'结构包正在应用，尚未进入最终核验。';if(release)release.disabled=true}}
const schemaDiffBaseRender=render;
render=function(){schemaDiffBaseRender();syncSchemaDiffWorkflowFromJob()};
document.getElementById('schemaDiffTarget').addEventListener('change',()=>{schemaDiffPlan=null;schemaDiffScanResult=null;schemaDiffReviewInventory=null;schemaDiffReviewConfirmed=false;schemaDiffFlowStage=0;schemaDiffFlowFailed=false;schemaDiffFinalVerificationTarget='';resetSchemaDiffSubmissionState();renderSchemaDiffWorkflow();renderSchemaDiffReview();updateSchemaDiffReleaseAvailability();document.getElementById('schemaDiffStatus').textContent='目标环境已变更，请重新比较并生成结构包。'});
const consolePages={};
function setupConsoleWorkspace(){
  const secondary=[...document.querySelectorAll('.secondary-panel')];
  const inventory=document.createElement('section');
  inventory.id='page-inventory';inventory.className='panel console-content-section is-hidden';inventory.dataset.consolePage='inventory';
  inventory.innerHTML='<div class="section-title"><div><h2>表结构与数据分层</h2><p>以数据库表为单位展示所有权、结构差异及 MDM 主数据差异。仅受管主数据按业务键比较；账户、用户内容、运行数据和环境配置均不因自然差异标红。</p></div><span class="eyebrow">MDM governance</span></div><div class="inventory-toolbar"><label class="field" style="max-width:300px">目标环境<select id="inventoryTarget"></select></label><label class="field inventory-filter">筛选表名或分类<input id="inventoryFilter" type="search" placeholder="例如：用户、主数据、comments"></label><button id="inventoryRefresh" type="button" onclick="loadTableInventory(this)">刷新清单</button></div><div id="inventorySummary" class="inventory-summary"><div class="notice">正在读取结构与主数据差异...</div></div><div id="inventoryRows" class="inventory-table-wrap"><div class="notice" style="padding:14px">尚未加载。</div></div>';
  const monitor=document.querySelector('.monitor-grid');if(monitor)monitor.parentNode.insertBefore(inventory,monitor);
  consolePages.overview=[document.getElementById('stats'),document.getElementById('overview-dashboard')];
  consolePages['full-release']=[document.querySelector('.release-actions-grid'),monitor];
  consolePages['schema-release']=[secondary[0]];
  consolePages.cleanup=[document.querySelector('.cleanup-panel')];
  consolePages.inventory=[inventory];
  consolePages.operations=[document.querySelector('.rollback-panel')];
  Object.values(consolePages).flat().filter(Boolean).forEach(node=>node.classList.add('console-content-section'));
  const target=document.getElementById('inventoryTarget');
  target.innerHTML=(overview.release_targets||[]).map(item=>'<option value="'+esc(item.name)+'">'+esc(item.label)+' ('+esc(item.host)+'/'+esc(item.database)+')</option>').join('')||'<option value="staging">Staging</option><option value="production">Production</option>';
  document.getElementById('inventoryFilter').addEventListener('input',()=>filterTableInventory());
  document.querySelectorAll('[data-console-section]').forEach(button=>button.addEventListener('click',()=>setConsoleSection(button.dataset.consoleSection)));
  setConsoleSection('overview');
}
function setConsoleSection(name){
  const visible=new Set(consolePages[name]||[]);
  Object.values(consolePages).flat().filter(Boolean).forEach(node=>node.classList.toggle('is-hidden',!visible.has(node)));
  document.querySelectorAll('[data-console-section]').forEach(button=>button.classList.toggle('active',button.dataset.consoleSection===name));
  if(name==='inventory')loadTableInventory();
}
function renderTableInventory(data){
  const rows=data.rows||[],summary=data.counts||{},differenceCounts=data.difference_counts||{},differenceSummary=data.difference_summary||{},managedTables=data.data_scan?.managed_tables||[],targetWarning=data.target_error?'<div class="notice" style="grid-column:1/-1;color:var(--red)">'+esc(data.target_error)+'</div>':'';document.getElementById('inventorySummary').innerHTML=targetWarning+'<div class="inventory-difference-summary"><div><strong>'+esc(differenceSummary.schema_tables||0)+'</strong><span>结构差异表</span></div><div><strong>'+esc(differenceSummary.data_tables||0)+'</strong><span>主数据差异表</span></div><div><strong>'+esc(managedTables.length)+'</strong><span>受管 MDM 表</span></div></div><div class="inventory-count-grid">'+Object.entries(summary).map(([label,count])=>{const item=differenceCounts[label]||{},schemaDiff=Number(item.schema||0),dataDiff=Number(item.data||0);return '<div class="inventory-count"><strong>'+esc(count)+'</strong><span class="inventory-count-label">'+esc(label)+'</span><span class="inventory-count-detail">结构差异 '+esc(schemaDiff)+' · 主数据差异 '+esc(dataDiff)+'</span></div>'}).join('')+'</div>'+(data.data_scan?.performed?'<div class="inventory-scan-note">主数据比较范围：'+esc(managedTables.join('、')||'当前环境无受管主数据表')+'。'+esc(data.data_scan.method||'仅受管主数据')+'</div>':'');
  document.getElementById('inventoryRows').innerHTML='<table class="inventory-table"><thead><tr><th>表名</th><th>数据分类</th><th>归属模块</th><th>结构状态</th><th>MDM 主数据状态</th><th>说明</th><th>发布策略</th></tr></thead><tbody>'+rows.map(row=>'<tr data-inventory-text="'+esc([row.table_name,row.category_label,row.owner,row.description,row.policy,row.schema_status,row.data_status].join(' '))+'"><td class="table-name">'+esc(row.table_name)+'</td><td><span class="inventory-badge">'+esc(row.category_label)+'</span></td><td>'+esc(row.owner)+'</td><td class="inventory-status '+(['一致','发布控制表（忽略）'].includes(row.schema_status)?'':'mismatch')+'">'+esc(row.schema_status)+'</td><td class="inventory-status '+(row.data_status==='有差异'?'mismatch':'')+'">'+esc(row.data_status)+'</td><td>'+esc(row.description)+'</td><td>'+esc(row.policy)+'</td></tr>').join('')+'</tbody></table>';filterTableInventory();
}
function filterTableInventory(){const query=(document.getElementById('inventoryFilter')?.value||'').trim().toLowerCase();document.querySelectorAll('#inventoryRows tbody tr').forEach(row=>{row.hidden=Boolean(query&&!String(row.dataset.inventoryText||'').toLowerCase().includes(query))})}
async function loadTableInventory(button){const target=document.getElementById('inventoryTarget')?.value||'staging';try{if(button){button.disabled=true;button.classList.add('is-loading');button.textContent='读取中...'}const data=await api('/api/schema-inventory?target='+encodeURIComponent(target));renderTableInventory(data.inventory||{});if(button){button.classList.add('is-success')}}catch(error){document.getElementById('inventoryRows').innerHTML='<div class="notice" style="padding:14px;color:var(--red)">表结构清单读取失败：'+esc(error.message)+'</div>'}finally{if(button){button.disabled=false;button.classList.remove('is-loading');button.textContent='刷新清单';setTimeout(()=>button.classList.remove('is-success'),1200)}}}
let overviewSchemaSummary=null;
function renderOverviewStatistics(){
  const summary=overviewSchemaSummary||{},targets=summary.targets||[];
  const byName=Object.fromEntries(targets.map(item=>[item.target,item]));
  const localCount=(byName.staging?.summary||byName.production?.summary||{}).local_table_count;
  const statItems=[
    ['本地结构表',localCount==null?'--':localCount,summary.source?.database||'等待只读扫描'],
    ['Staging 结构差异',byName.staging?.available?(byName.staging.summary.structural_difference_count||0):'不可用',byName.staging?.available?'与本地开发库比较':(byName.staging?.error||'等待扫描')],
    ['Production 结构差异',byName.production?.available?(byName.production.summary.structural_difference_count||0):'不可用',byName.production?.available?'与本地开发库比较':(byName.production?.error||'等待扫描')],
    ['统计口径','只读','不读取、不修改业务数据'],
  ];
  const stats=document.getElementById('stats');
  if(stats)stats.innerHTML=statItems.map(item=>'<div class="stat"><span>'+esc(item[0])+'</span><b>'+esc(item[1])+'</b><span>'+esc(item[2])+'</span></div>').join('');
  const host=document.getElementById('overview-difference-grid');
  const meta=document.getElementById('overview-difference-meta');
  if(!host)return;
  if(!targets.length){host.innerHTML='<div class="notice">正在读取 Staging 与 Production 的结构摘要...</div>';if(meta)meta.textContent='';return}
  host.innerHTML=targets.map(item=>{
    if(!item.available)return '<article class="overview-difference-card unavailable"><div class="overview-difference-head"><h3>'+esc(item.label)+'</h3><span class="overview-difference-status">暂不可用</span></div><div class="overview-difference-error">'+esc(item.error||'未能读取结构摘要。')+'</div></article>';
    const value=item.summary||{};
    const parts=[
      ['仅本地表',value.local_only_tables],['仅目标表',value.target_only_tables],['表定义不同',value.schema_difference_tables],
      ['本地迁移',value.migration_local_only],['目标迁移',value.migration_target_only],['校验和不一致',value.migration_checksum_mismatch],
    ];
    return '<article class="overview-difference-card"><div class="overview-difference-head"><h3>'+esc(item.label)+'</h3><span class="overview-difference-status">可用</span></div><div class="overview-difference-total">'+esc(value.structural_difference_count||0)+'</div><div class="overview-difference-label">项结构或迁移账本差异</div><div class="overview-difference-breakdown">'+parts.map(part=>'<span>'+esc(part[0])+' '+esc(part[1]||0)+'</span>').join('')+'</div></article>';
  }).join('');
  if(meta)meta.textContent='来源：'+esc(summary.source?.label||'本地开发库')+' · '+esc(summary.source?.host||'--')+'/'+esc(summary.source?.database||'--')+' · 统计时间：'+esc(summary.generated_at||'--');
}
async function loadOverviewSchemaSummary(){
  try{const data=await api('/api/overview/schema-summary');overviewSchemaSummary=data.summary||{};renderOverviewStatistics()}catch(error){
    overviewSchemaSummary={targets:[{target:'staging',label:'Staging',available:false,error:'结构摘要读取失败：'+error.message,summary:{}},{target:'production',label:'Production',available:false,error:'结构摘要读取失败：'+error.message,summary:{}}]};
    renderOverviewStatistics();
  }
}
setupConsoleWorkspace();
const overviewWorkspaceRender=render;
render=function(){overviewWorkspaceRender();renderOverviewStatistics()};
loadOverviewSchemaSummary();
</script></body></html>'''


if __name__ == "__main__":
    app.run(host=APP_HOST, port=APP_PORT, debug=False, use_reloader=False)
