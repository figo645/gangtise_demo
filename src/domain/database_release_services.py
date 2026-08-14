"""Admin-owned database release operations.

This replaces the standalone local Flask controller. Destructive database
operations stay allow-listed, single-flight, and are exposed only through the
main application's Admin API.
"""

import os
import json
import re
import signal
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2


ROOT = Path(__file__).resolve().parents[2]
PREPARE_SCRIPT = ROOT / "scripts" / "prepare_database_release.sh"
PACKAGE_SCRIPT = ROOT / "scripts" / "apply_database_release_package.sh"
PACKAGE_BATCH_SCRIPT = ROOT / "scripts" / "apply_database_release_packages.sh"
ROLLBACK_SCRIPT = ROOT / "scripts" / "rollback_database_release.sh"
PACKAGES_DIR = ROOT / "database_release_packages"
RELEASE_STATE_FILE = ROOT / ".deploy" / "database_release_last_job.json"
CONFIG_FILE = Path(os.environ.get("DATABASE_RELEASE_CONFIG", str(ROOT / ".database_release.env")))
_config_loaded = False
_release_lock = threading.Lock()
_release_job = {"status": "idle", "id": "", "target": "", "operation": "", "log": "", "started_at": "", "finished_at": "", "returncode": None, "pid": None, "package_plan": [], "progress": {}, "events": [], "cancel_requested": False, "cancel_requested_at": "", "cancellable": False}
_release_job_loaded = False

SIMULATION_LABEL = "模拟数据"
SIMULATED_FAN_SEED = [
    ("演示粉丝-小陈", "600519", "贵州茅台", "高端白酒", "品牌护城河仍在，想继续跟踪渠道动销和估值变化。"),
    ("演示粉丝-小陈", "300750", "宁德时代", "动力电池", "关注储能需求和海外订单能否改善。"),
    ("演示粉丝-小周", "688981", "中芯国际", "半导体制造", "希望了解成熟制程景气和产能利用率的验证节奏。"),
    ("演示粉丝-小周", "00700", "腾讯控股", "港股互联网", "关注回购、广告业务和财报兑现。"),
    ("演示粉丝-小林", "600036", "招商银行", "银行", "想跟踪息差、资产质量和分红的变化。"),
]


def _load_release_config():
    global _config_loaded
    if _config_loaded:
        return
    _config_loaded = True
    if not CONFIG_FILE.exists():
        return
    for raw_line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_database_release_target(name):
    _load_release_config()
    normalized = str(name or "").strip().lower()
    if normalized not in {"local", "staging", "production"}:
        return None
    prefix = {"local": "LOCAL", "staging": "STAGING", "production": "PRODUCTION"}[normalized]
    default_host = {"local": "127.0.0.1", "staging": "129.211.65.53", "production": "47.105.48.193"}[normalized]
    db_host = str(os.environ.get(f"DATABASE_RELEASE_{prefix}_DB_HOST", default_host) or "").strip()
    if not db_host:
        return None
    return {
        "name": normalized,
        "db_name": str(os.environ.get(f"DATABASE_RELEASE_{prefix}_DB_NAME", "sprint_dashboard") or "sprint_dashboard").strip(),
        "db_user": str(os.environ.get(f"DATABASE_RELEASE_{prefix}_DB_USER", "postgres") or "postgres").strip(),
        "db_host": db_host,
        "db_port": str(os.environ.get(f"DATABASE_RELEASE_{prefix}_DB_PORT", "5432") or "5432").strip(),
        "db_password": str(os.environ.get(f"DATABASE_RELEASE_{prefix}_DB_PASSWORD", "your_password") or ""),
    }


def list_database_release_targets(include_local=True):
    names = ("local", "staging", "production") if include_local else ("staging", "production")
    labels = {"local": "本地开发库", "staging": "Staging", "production": "Production"}
    rows = []
    for name in names:
        target = get_database_release_target(name)
        if target:
            rows.append({"name": name, "label": labels[name], "host": target["db_host"], "database": target["db_name"]})
    return rows


def list_database_release_packages():
    packages = []
    for config_path in sorted(PACKAGES_DIR.glob("*/*/release.env"), reverse=True):
        values = {}
        for raw_line in config_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
        package_type = values.get("PACKAGE_TYPE", "")
        payload = config_path.parent / f"{package_type}.sql"
        if package_type in {"schema", "master_data", "data"} and values.get("RELEASE_VERSION") and payload.exists():
            packages.append({
                "id": str(config_path.parent.relative_to(ROOT)),
                "date": config_path.parent.parent.name,
                "version": values["RELEASE_VERSION"],
                "type": package_type,
                "title": values.get("TITLE", ""),
            })
    return packages


def _release_job_snapshot():
    return {
        "status": _release_job.get("status") or "idle",
        "id": _release_job.get("id") or "",
        "target": _release_job.get("target") or "",
        "operation": _release_job.get("operation") or "",
        "log": _release_job.get("log") or "",
        "started_at": _release_job.get("started_at") or "",
        "finished_at": _release_job.get("finished_at") or "",
        "returncode": _release_job.get("returncode"),
        "pid": _release_job.get("pid"),
        "package_plan": list(_release_job.get("package_plan") or []),
        "progress": dict(_release_job.get("progress") or {}),
        "events": list(_release_job.get("events") or []),
        "cancel_requested": bool(_release_job.get("cancel_requested")),
        "cancel_requested_at": _release_job.get("cancel_requested_at") or "",
        "cancellable": bool(_release_job.get("cancellable")),
    }


def _persist_release_job():
    RELEASE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = RELEASE_STATE_FILE.with_suffix(".tmp")
    temporary_file.write_text(json.dumps(_release_job_snapshot(), ensure_ascii=False), encoding="utf-8")
    temporary_file.replace(RELEASE_STATE_FILE)


def _load_persisted_release_job():
    global _release_job_loaded
    if _release_job_loaded:
        return
    _release_job_loaded = True
    if not RELEASE_STATE_FILE.exists():
        return
    try:
        restored = json.loads(RELEASE_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return
    if not isinstance(restored, dict):
        return
    allowed_statuses = {"queued", "running", "cancelling", "cancelled", "succeeded", "failed"}
    if restored.get("status") not in allowed_statuses:
        return
    _release_job.update({key: restored.get(key) for key in _release_job_snapshot() if key in restored})
    if "cancellable" not in restored and _release_job.get("status") in {"queued", "running"}:
        _release_job["cancellable"] = True
    # A restarted controller cannot observe the original child process. Keep
    # the last log visible and make the interrupted state explicit.
    if _release_job.get("status") in {"queued", "running", "cancelling"}:
        _release_job.update({
            "status": "cancelled" if _release_job.get("status") == "cancelling" else "failed",
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "returncode": _release_job.get("returncode") if _release_job.get("returncode") is not None else (-15 if _release_job.get("status") == "cancelling" else -1),
            "cancellable": False,
        })
        log_path = Path(_release_job.get("log") or "")
        if log_path:
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as log:
                    log.write("\n[controller] 发布控制器在任务执行期间重启；原任务状态无法继续追踪，请核对目标库后重新发起。\n")
            except OSError:
                pass
        _persist_release_job()


def get_database_release_job():
    with _release_lock:
        _load_persisted_release_job()
        return _release_job_snapshot()


def _set_job(**values):
    with _release_lock:
        _load_persisted_release_job()
        _release_job.update(values)
        _persist_release_job()


def _record_release_event(stage, title, detail="", status="info"):
    """Append a durable, UI-facing release event without losing raw logs."""
    with _release_lock:
        _load_persisted_release_job()
        events = list(_release_job.get("events") or [])
        events.append({
            "sequence": (events[-1].get("sequence", len(events)) if events else 0) + 1,
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "stage": str(stage or "execution"),
            "title": str(title or "执行明细"),
            "detail": str(detail or ""),
            "status": str(status or "info"),
        })
        # The raw task log remains complete. The timeline keeps enough recent
        # events for a page refresh without making the state file unbounded.
        _release_job["events"] = events[-100:]
        _persist_release_job()


def _is_cancel_requested(job_id):
    with _release_lock:
        _load_persisted_release_job()
        return _release_job.get("id") == job_id and bool(_release_job.get("cancel_requested"))


def _mark_job_cancelled(job_id, returncode=-15):
    with _release_lock:
        _load_persisted_release_job()
        if _release_job.get("id") != job_id:
            return
        _release_job.update({
            "status": "cancelled",
            "returncode": returncode,
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pid": None,
            "cancellable": False,
            "progress": {
                **dict(_release_job.get("progress") or {}),
                "state": "cancelled",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        })
        _persist_release_job()
    _record_release_event("cancelled", "任务已取消", f"发布进程已停止，返回码：{returncode}", "cancelled")


def _transition_job_to_running(job_id, log_path):
    with _release_lock:
        _load_persisted_release_job()
        if _release_job.get("id") != job_id or _release_job.get("cancel_requested"):
            return False
        _release_job.update({"status": "running", "log": str(log_path), "cancellable": True})
        _persist_release_job()
    _record_release_event("worker", "后台发布线程已启动", "正在创建独立发布进程。", "active")
    return True


def _attach_release_process(job_id, pid):
    with _release_lock:
        _load_persisted_release_job()
        if _release_job.get("id") != job_id:
            return True
        _release_job.update({"pid": pid})
        cancel_requested = bool(_release_job.get("cancel_requested"))
        _persist_release_job()
    _record_release_event("process", "发布进程已创建", f"进程 PID：{pid}；开始执行数据库命令。", "active")
    return cancel_requested


def _terminate_release_process_group(pid):
    if not pid:
        return
    try:
        # Every release process owns a separate session so its psql, pg_dump,
        # pg_restore, and shell children stop together.
        os.killpg(int(pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        return


def _run_process(command, target, job_id, operation):
    env = os.environ.copy()
    env.update({
        "DATABASE_RELEASE_TARGET": target["name"],
        "REMOTE_DB_NAME": target["db_name"],
        "REMOTE_DB_USER": target["db_user"],
        "REMOTE_DB_HOST": target["db_host"],
        "REMOTE_DB_PORT": target["db_port"],
        "REMOTE_DB_PASSWORD": target["db_password"],
        "CONFIRM_DATABASE_REPLACE": "YES",
    })
    log_path = Path(_release_job.get("log") or ROOT / ".deploy" / f"admin_{operation}_{job_id}.log")
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"[controller] 开始 {operation} 任务 {job_id}\n")
            log.flush()
            if not _transition_job_to_running(job_id, log_path):
                log.write("[controller] 已在启动前收到取消请求，任务未执行。\n")
                log.flush()
                _mark_job_cancelled(job_id)
                return
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
            if _attach_release_process(job_id, process.pid):
                log.write("[controller] 已收到取消请求，正在终止发布进程。\n")
                log.flush()
                _terminate_release_process_group(process.pid)
            for line in iter(process.stdout.readline, ""):
                log.write(line)
                log.flush()
                _update_release_progress_from_log(line)
            process.stdout.close()
            return_code = process.wait()
        if _is_cancel_requested(job_id):
            _mark_job_cancelled(job_id, returncode=return_code if return_code else -15)
        else:
            _set_job(status="succeeded" if return_code == 0 else "failed", returncode=return_code, finished_at=time.strftime("%Y-%m-%d %H:%M:%S"), pid=None, cancellable=False)
            if return_code == 0:
                _record_release_event("completed", "数据库任务执行完成", "所有命令已完成，结果校验通过。", "succeeded")
            else:
                _record_release_event("failed", "数据库任务执行失败", f"发布进程返回码：{return_code}。请查看原始日志定位失败命令。", "failed")
    except Exception as exc:
        try:
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"[controller] 无法启动任务：{exc}\n")
        except OSError:
            pass
        if _is_cancel_requested(job_id):
            _mark_job_cancelled(job_id)
        else:
            _set_job(status="failed", log=str(log_path), returncode=-1, finished_at=time.strftime("%Y-%m-%d %H:%M:%S"), pid=None, cancellable=False)
            _record_release_event("failed", "发布进程无法启动", str(exc), "failed")


def _update_release_progress_from_log(line):
    text = str(line or "").strip()
    if not text:
        return
    stage = "execution"
    title = "执行明细"
    event_status = "info"
    if text.startswith("==> "):
        stage = "stage"
        title = text[4:]
        event_status = "active"
    elif text.startswith("Validated:"):
        stage = "validation"
        title = "临时数据库校验结果"
        event_status = "succeeded"
    elif re.search(r"\b(error|failed|unavailable|missing|invalid)\b", text, re.IGNORECASE):
        stage = "error"
        title = "执行错误"
        event_status = "failed"
    _record_release_event(stage, title, text, event_status)
    stage_markers = (
        ("==> [preflight]", "preflight", text.replace("==> [preflight]", "").strip()),
        ("==> Exporting complete local database:", "exporting", "正在导出本地完整数据库"),
        ("==> Restoring ", "restoring", "正在恢复至目标临时数据库"),
        ("Validated:", "validating", "正在校验临时数据库"),
        ("Database preparation complete.", "completed", "完整数据库发布完成"),
        ("[controller] 开始", "starting", "发布进程已启动"),
    )
    for prefix, state, message in stage_markers:
        if text.startswith(prefix):
            _set_job(progress={
                **dict(_release_job.get("progress") or {}),
                "state": state,
                "message": message,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            return
    if text.startswith("==> Switching "):
        _record_release_event("switching", "开始最终数据库切换", "即将替换目标库名称；此阶段不可取消。", "active")
        _set_job(cancellable=False, progress={
            **dict(_release_job.get("progress") or {}),
            "state": "switching",
            "message": "正在执行最终数据库切换，此阶段不可取消",
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        return
    match = re.search(r"^==> \[(\d+)/(\d+)\] (开始增量包|增量包完成)", text)
    if not match:
        return
    current = int(match.group(1))
    total = int(match.group(2))
    is_complete = match.group(3) == "增量包完成"
    _set_job(progress={
        "current_step": current,
        "completed_steps": current if is_complete else max(0, current - 1),
        "total_steps": total,
        "state": "completed_step" if is_complete else "running_step",
        "message": f"{match.group(3)}：第 {current}/{total} 个增量包",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })


def _start_job(target, command, operation, package_plan=None):
    with _release_lock:
        _load_persisted_release_job()
        if _release_job.get("status") in {"queued", "running", "cancelling"}:
            raise ValueError("database_release_job_running")
        job_id = time.strftime("%Y%m%d_%H%M%S")
        log_path = ROOT / ".deploy" / f"admin_{operation}_{job_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"[controller] 任务已创建：{operation} {job_id}\n"
            f"[controller] 目标环境：{target['name']} · 数据库：{target['db_host']}:{target['db_port']}/{target['db_name']}\n"
            "[controller] 状态：已落盘，正在启动发布进程。\n",
            encoding="utf-8",
        )
        package_count = len(package_plan or [])
        _release_job.update({"status": "queued", "id": job_id, "target": target["name"], "operation": operation, "log": str(log_path), "started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "finished_at": "", "returncode": None, "pid": None, "package_plan": list(package_plan or []), "cancel_requested": False, "cancel_requested_at": "", "cancellable": True, "progress": {"current_step": 0, "completed_steps": 0, "total_steps": package_count, "state": "queued", "message": "任务已落盘，等待启动发布进程", "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}, "events": [
            {"sequence": 1, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "stage": "created", "title": "任务已创建并持久化", "detail": f"目标：{target['name']} · {target['db_host']}:{target['db_port']}/{target['db_name']}", "status": "succeeded"},
            {"sequence": 2, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "stage": "queued", "title": "等待后台发布线程", "detail": "任务已交给主应用后台执行，页面会每秒刷新状态。", "status": "active"},
        ]})
        _persist_release_job()
        snapshot = _release_job_snapshot()
    threading.Thread(target=_run_process, args=(command, target, job_id, operation), daemon=True).start()
    return snapshot


def cancel_database_release(job_id=""):
    """Request cancellation of the current database release or rollback job.

    Incremental SQL executes inside a package transaction. A cancellation can
    stop the active package but cannot undo packages which were already
    committed. Full releases are cancellable before their database switch.
    """
    normalized_job_id = str(job_id or "").strip()
    with _release_lock:
        _load_persisted_release_job()
        status = str(_release_job.get("status") or "")
        if status not in {"queued", "running", "cancelling"}:
            raise ValueError("database_release_job_not_running")
        if normalized_job_id and normalized_job_id != _release_job.get("id"):
            raise ValueError("database_release_job_mismatch")
        if not _release_job.get("cancellable"):
            raise ValueError("database_release_job_not_cancellable")
        pid = _release_job.get("pid")
        _release_job.update({
            "status": "cancelling",
            "cancel_requested": True,
            "cancel_requested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cancellable": False,
            "progress": {
                **dict(_release_job.get("progress") or {}),
                "state": "cancelling",
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        })
        log_path = Path(_release_job.get("log") or "")
        _persist_release_job()
        snapshot = _release_job_snapshot()
    _record_release_event("cancelling", "已收到管理员取消请求", "正在向发布进程发送停止信号。", "active")
    try:
        if log_path:
            with log_path.open("a", encoding="utf-8") as log:
                log.write("[controller] 管理员请求取消任务；正在终止当前发布进程。\n")
    except OSError:
        pass
    _terminate_release_process_group(pid)
    return snapshot


def start_database_release(target_name, package_id="", confirm_production=False):
    target = get_database_release_target(target_name)
    if not target or target["name"] not in {"staging", "production"}:
        raise ValueError("database_release_target_invalid")
    if target["name"] == "production" and confirm_production is not True:
        raise ValueError("production_confirmation_required")
    packages = list_database_release_packages()
    package_ids = {item["id"] for item in packages}
    normalized_package = str(package_id or "").strip()
    if normalized_package == "__full__":
        normalized_package = ""
    if normalized_package and normalized_package != "__pending__" and normalized_package not in package_ids:
        raise ValueError("database_release_package_invalid")
    if normalized_package == "__pending__":
        package_plan = sorted(packages, key=lambda item: (item.get("date") or "", item.get("version") or "", item.get("id") or ""))
        command = [str(PACKAGE_BATCH_SCRIPT), *[str(ROOT / item["id"]) for item in package_plan]]
        return _start_job(target, command, "release", package_plan=package_plan)
    package_plan = [item for item in packages if item["id"] == normalized_package]
    command = [str(PACKAGE_SCRIPT), str(ROOT / normalized_package)] if normalized_package else [str(PREPARE_SCRIPT)]
    return _start_job(target, command, "release", package_plan=package_plan)


def list_database_release_rollbacks(target_name):
    target = get_database_release_target(target_name)
    if not target or target["name"] not in {"staging", "production"}:
        raise ValueError("database_release_target_invalid")
    try:
        with psycopg2.connect(host=target["db_host"], port=target["db_port"], dbname="postgres", user=target["db_user"], password=target["db_password"], connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database WHERE datname LIKE %s ORDER BY datname DESC", (f"{target['db_name']}_backup_%",))
                return [{"name": row[0], "size": row[1]} for row in cursor.fetchall()]
    except Exception as exc:
        raise RuntimeError(f"database_rollback_records_unavailable:{exc}") from exc


def start_database_rollback(target_name, backup_name, confirm_production=False):
    target = get_database_release_target(target_name)
    if not target or target["name"] not in {"staging", "production"}:
        raise ValueError("database_release_target_invalid")
    if target["name"] == "production" and confirm_production is not True:
        raise ValueError("production_confirmation_required")
    normalized_backup = str(backup_name or "").strip()
    if normalized_backup not in {item["name"] for item in list_database_release_rollbacks(target["name"])}:
        raise ValueError("database_rollback_backup_invalid")
    return _start_job(target, [str(ROLLBACK_SCRIPT), normalized_backup], "rollback")


def get_database_release_log(limit=50000):
    with _release_lock:
        _load_persisted_release_job()
        log_path = Path(_release_job.get("log") or "") if _release_job.get("log") else None
    if not log_path or not log_path.exists():
        return "暂无发布或回滚任务日志。发起任务后会在这里实时显示执行过程。\n"
    return log_path.read_text(encoding="utf-8", errors="replace")[-max(1024, min(int(limit or 50000), 100000)):]


def _simulation_connection(target):
    return psycopg2.connect(host=target["db_host"], port=target["db_port"], dbname=target["db_name"], user=target["db_user"], password=target["db_password"], connect_timeout=5)


def _ensure_simulation_schema(cursor):
    cursor.execute((ROOT / "sql" / "postgres" / "032_simulated_fan_data_management.sql").read_text(encoding="utf-8"))


def list_simulation_batches(target_name):
    target = get_database_release_target(target_name)
    if not target:
        raise ValueError("database_release_target_invalid")
    with _simulation_connection(target) as connection:
        with connection.cursor() as cursor:
            _ensure_simulation_schema(cursor)
            cursor.execute("""SELECT b.batch_code, b.tenant_slug, b.batch_label, b.created_at, b.created_by, b.notes,
                (SELECT COUNT(*) FROM users u WHERE u.simulation_batch_code = b.batch_code AND u.is_simulated = 1) AS user_count,
                (SELECT COUNT(*) FROM fan_stock_observation_events e WHERE e.simulation_batch_code = b.batch_code AND e.is_simulated = 1) AS watchlist_count,
                (SELECT COUNT(*) FROM watchlist_comments c WHERE c.simulation_batch_code = b.batch_code AND c.is_simulated = 1) AS comment_count
                FROM simulated_data_batches b ORDER BY b.created_at DESC, b.batch_code DESC""")
            columns = [item[0] for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def create_simulation_batch(target_name, tenant_slug):
    target = get_database_release_target(target_name)
    normalized_tenant = str(tenant_slug or "laowang").strip().lower()
    if not target or normalized_tenant != "laowang":
        raise ValueError("simulation_target_or_tenant_invalid")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_code = f"sim_fans_{normalized_tenant}_{stamp}"
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _simulation_connection(target) as connection:
        with connection.cursor() as cursor:
            _ensure_simulation_schema(cursor)
            cursor.execute("INSERT INTO simulated_data_batches (batch_code, tenant_slug, batch_label, created_at, created_by, notes) VALUES (%s, %s, %s, %s, %s, %s)", (batch_code, normalized_tenant, SIMULATION_LABEL, created_at, "admin_database_release", "模拟粉丝、自选股与个股评论"))
            names = sorted({row[0] for row in SIMULATED_FAN_SEED})
            name_map = {name: f"{name}-{stamp[-6:]}" for name in names}
            for index, name in enumerate(names, start=1):
                cursor.execute("""INSERT INTO users (username, password, role, tenant_slug, advisor_name, phone, status, created_at, updated_at, labels_json, source_label, is_simulated, simulation_batch_code, simulation_label)
                    VALUES (%s, %s, 'investor', %s, %s, %s, 'active', %s, %s, %s, %s, 1, %s, %s)""", (name_map[name], "demo123", normalized_tenant, "财经老王", f"1390000{index:04d}", created_at, created_at, '["模拟数据", "演示粉丝"]', SIMULATION_LABEL, batch_code, SIMULATION_LABEL))
            for index, (name, code, stock_name, sector, comment) in enumerate(SIMULATED_FAN_SEED, start=1):
                event_at = (datetime.now() - timedelta(minutes=index * 7)).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("""INSERT INTO fan_stock_observation_events (tenant_slug, user_profile_id, user_role, stock_code, stock_name, sector_name, event_type, entry_point, source_detail, created_at, is_simulated, simulation_batch_code, simulation_label)
                    VALUES (%s, %s, 'investor', %s, %s, %s, 'watchlist_add', 'simulation_seed', %s, %s, 1, %s, %s)""", (normalized_tenant, name_map[name], code, stock_name, sector, SIMULATION_LABEL, event_at, batch_code, SIMULATION_LABEL))
                cursor.execute("""INSERT INTO watchlist_comments (tenant_slug, stock_code, stock_name, comment_text, label_tags_json, keyword_tags_json, sentiment_label, topic_label, comment_summary, labeling_source, labeling_model_key, labeling_model_name, created_by_user_id, created_by_name, created_by_role, source_client, created_at, updated_at, is_simulated, simulation_batch_code, simulation_label)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'simulation_seed', '', '', %s, %s, 'investor', 'simulation_seed', %s, %s, 1, %s, %s)""", (normalized_tenant, code, stock_name, comment, '["模拟数据", "个股关注"]', f'["{sector}"]', "中性", sector, "模拟粉丝个股评论", name_map[name], name_map[name], event_at, event_at, batch_code, SIMULATION_LABEL))
    return batch_code


def delete_simulation_batch(target_name, batch_code):
    target = get_database_release_target(target_name)
    normalized_batch = str(batch_code or "").strip()
    if not target or not normalized_batch:
        raise ValueError("simulation_target_or_batch_invalid")
    with _simulation_connection(target) as connection:
        with connection.cursor() as cursor:
            _ensure_simulation_schema(cursor)
            cursor.execute("SELECT 1 FROM simulated_data_batches WHERE batch_code = %s", (normalized_batch,))
            if not cursor.fetchone():
                raise ValueError("simulation_batch_not_found")
            cursor.execute("DELETE FROM watchlist_comments WHERE simulation_batch_code = %s AND is_simulated = 1", (normalized_batch,))
            cursor.execute("DELETE FROM fan_stock_observation_events WHERE simulation_batch_code = %s AND is_simulated = 1", (normalized_batch,))
            cursor.execute("DELETE FROM users WHERE simulation_batch_code = %s AND is_simulated = 1", (normalized_batch,))
            cursor.execute("DELETE FROM simulated_data_batches WHERE batch_code = %s", (normalized_batch,))


def build_database_release_overview():
    return {
        "targets": list_database_release_targets(include_local=False),
        "simulation_targets": list_database_release_targets(include_local=True),
        "packages": list_database_release_packages(),
        "job": get_database_release_job(),
    }
