"""Admin-owned database release operations.

This replaces the standalone local Flask controller. Destructive database
operations stay allow-listed, single-flight, and are exposed only through the
main application's Admin API.
"""

import os
import json
import re
import hashlib
import shlex
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
PRODUCTION_TO_STAGING_SCRIPT = ROOT / "scripts" / "sync_production_to_staging.sh"
STAGING_TO_PRODUCTION_SCRIPT = ROOT / "scripts" / "sync_staging_to_production.sh"
CLEAR_DATABASE_SCRIPT = ROOT / "scripts" / "clear_database_release.sh"
PACKAGES_DIR = ROOT / "database_release_packages"
RELEASE_STATE_FILE = ROOT / ".deploy" / "database_release_last_job.json"
CONFIG_FILE = Path(os.environ.get("DATABASE_RELEASE_CONFIG", str(ROOT / ".database_release.env")))
_config_loaded = False
_release_lock = threading.Lock()
_delta_generation_lock = threading.Lock()
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
                "delta_target": values.get("DELTA_TARGET", "").strip().lower(),
            })
    return packages


def _database_release_package_checksum(package):
    package_type = str((package or {}).get("type") or "").strip()
    package_id = str((package or {}).get("id") or "").strip()
    payload_path = ROOT / package_id / f"{package_type}.sql"
    if package_type not in {"schema", "master_data", "data"} or not payload_path.is_file():
        raise ValueError("database_release_package_invalid")
    payload = payload_path.read_bytes()
    # Historical packages use their SQL-only checksum. Target-specific deltas
    # additionally bind their destination into the checksum and release ledger.
    delta_target = str((package or {}).get("delta_target") or "").strip().lower()
    if delta_target:
        payload += b"\nDELTA_TARGET=" + delta_target.encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _build_database_release_package_plan(target, packages, released_checksums, ledger_initialized=True):
    """Classify immutable local packages against a target release ledger.

    A missing target ledger is not evidence that every historical SQL package
    still needs to run. Replaying a data package in that state could overwrite
    data that was already introduced by a previous full release, so packages
    stay unverified until the target baseline is reconciled.
    """
    normalized_target = str((target or {}).get("name") or "").strip().lower()
    released = dict(released_checksums or {})
    legacy_ledger_initialized = any(
        not str(item.get("delta_target") or "").strip()
        and str(released.get(item.get("version")) or "")
        for item in (packages or [])
    )
    rows = []
    summary = {
        "pending_total": 0,
        "applied_total": 0,
        "checksum_mismatch_total": 0,
        "unverified_total": 0,
        "ledger_initialized": bool(ledger_initialized),
        "baseline_verification_required": False,
        "by_type": {
            name: {"pending": 0, "applied": 0, "checksum_mismatch": 0, "unverified": 0}
            for name in ("schema", "master_data", "data")
        },
    }
    for package in sorted(packages or [], key=lambda item: (item.get("date") or "", item.get("version") or "", item.get("id") or "")):
        row = dict(package)
        checksum = _database_release_package_checksum(row)
        released_checksum = str(released.get(row.get("version")) or "")
        is_targeted_delta = bool(row.get("delta_target")) and row.get("delta_target") == normalized_target
        if is_targeted_delta and not released_checksum:
            status = "pending"
        elif not is_targeted_delta and not released_checksum and not legacy_ledger_initialized:
            status = "unverified"
        elif not released_checksum:
            status = "pending"
        elif released_checksum == checksum:
            status = "applied"
        else:
            status = "checksum_mismatch"
        package_type = row.get("type") if row.get("type") in summary["by_type"] else "data"
        row.update({"target": normalized_target, "checksum": checksum, "released_checksum": released_checksum, "status": status})
        rows.append(row)
        summary[f"{status}_total"] += 1
        summary["by_type"][package_type][status] += 1
    summary["baseline_verification_required"] = bool(summary["unverified_total"])
    summary["auto_apply_allowed"] = not summary["checksum_mismatch_total"]
    return {"target": normalized_target, "packages": rows, "summary": summary}


def get_database_release_package_plan(target_name):
    """Return the local package delta for Staging or Production.

    This is deliberately release-package based rather than a destructive live
    database diff. Every pending change has an immutable SQL payload, type and
    checksum before it can be sent to a target environment.
    """
    target = get_database_release_target(target_name)
    if not target or target["name"] not in {"staging", "production"}:
        raise ValueError("database_release_target_invalid")
    released_checksums = {}
    ledger_initialized = False
    try:
        with psycopg2.connect(
            host=target["db_host"], port=target["db_port"], dbname=target["db_name"],
            user=target["db_user"], password=target["db_password"], connect_timeout=5,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('public.database_release_packages')")
                if cursor.fetchone()[0]:
                    cursor.execute(
                        """SELECT release_version, checksum_sha256
                           FROM database_release_packages
                           WHERE target_environment = %s AND status = 'succeeded'""",
                        (target["name"],),
                    )
                    released_checksums = {str(version): str(checksum) for version, checksum in cursor.fetchall()}
                    ledger_initialized = bool(released_checksums)
    except Exception as exc:
        raise RuntimeError(f"database_release_plan_unavailable:{exc}") from exc
    return _build_database_release_package_plan(
        target, list_database_release_packages(), released_checksums, ledger_initialized=ledger_initialized,
    )


def _database_release_diff_report_path(target_name):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return ROOT / ".deploy" / f"database_diff_local_to_{target_name}_{stamp}.json"


def _load_database_release_diff_tools():
    # Loaded lazily because the CLI audit tool obtains release targets from this
    # module. The late import keeps the Web controller and the CLI reusable.
    from tools.audit_database_release_diff import audit, build_incremental_delta
    from src.domain.core_services import get_local_app_db_target
    return audit, build_incremental_delta, get_local_app_db_target


def scan_database_release_delta(target_name):
    """Read local and target metadata/data summaries without modifying either DB."""
    target = get_database_release_target(target_name)
    if not target or target["name"] not in {"staging", "production"}:
        raise ValueError("database_release_target_invalid")
    audit, _, get_local_app_db_target = _load_database_release_diff_tools()
    report = audit(get_local_app_db_target(), target)
    output = _database_release_diff_report_path(target["name"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "target": target["name"],
        "report_path": str(output.relative_to(ROOT)),
        "summary": report["summary"],
        "safe_release_delta": report["safe_release_delta"],
        "schema_migration_difference": report["schema_migration_difference"],
        "excluded_runtime_tables": report["data"]["runtime_data_difference_tables"],
        "raw_master_data_difference_tables": report["data"]["raw_master_data_difference_tables"],
    }


def _database_release_review_section(section_type, section):
    """Convert a generated-but-not-written delta section into UI-safe review data."""
    normalized_type = str(section_type or "").strip()
    sql_text = str((section or {}).get("sql") or "").strip()
    blockers = list((section or {}).get("blockers") or [])
    if normalized_type == "schema":
        changes = list((section or {}).get("actions") or [])
        risk_level = "blocked" if blockers else ("low" if changes else "none")
        risk_note = "仅包含新增表、字段、约束或索引；不会删除目标端对象。"
    elif normalized_type == "master_data":
        changes = list((section or {}).get("details") or [])
        risk_level = "blocked" if blockers else ("medium" if changes else "none")
        risk_note = "按业务主键执行幂等 upsert，目标端独有记录会保留。"
    else:
        changes = list((section or {}).get("details") or [])
        risk_level = "blocked" if blockers else ("high" if changes else "none")
        risk_note = "包含运行或业务记录 upsert，需人工核对影响范围后发布。"
    preview_limit = 120000
    return {
        "type": normalized_type,
        "risk_level": risk_level,
        "risk_note": risk_note,
        "changes": changes,
        "blockers": blockers,
        "statement_count": sum(1 for line in sql_text.splitlines() if line.strip().endswith(";")),
        "line_count": len(sql_text.splitlines()),
        "sql_chars": len(sql_text),
        "sql_preview": sql_text[:preview_limit],
        "sql_preview_truncated": len(sql_text) > preview_limit,
    }


def review_database_release_delta(target_name, include_schema=True, include_master_data=True, include_runtime_data=False):
    """Build a read-only, visual-review model before a release package is written."""
    target = get_database_release_target(target_name)
    if not target or target["name"] not in {"staging", "production"}:
        raise ValueError("database_release_target_invalid")
    _, build_incremental_delta, get_local_app_db_target = _load_database_release_diff_tools()
    delta = build_incremental_delta(
        get_local_app_db_target(),
        target,
        include_schema=bool(include_schema),
        include_master_data=bool(include_master_data),
        include_runtime_data=bool(include_runtime_data),
    )
    sections = [
        _database_release_review_section("schema", delta["schema"]),
        _database_release_review_section("master_data", delta["master_data"]),
        _database_release_review_section("data", delta["runtime_data"]),
    ]
    blockers = [
        {"type": section["type"], **blocker}
        for section in sections
        for blocker in section["blockers"]
    ]
    return {
        "target": target["name"],
        "generated_at": delta["report"]["generated_at"],
        "safe_release_delta": delta["report"]["safe_release_delta"],
        "summary": delta["report"]["summary"],
        "sections": sections,
        "blockers": blockers,
        "can_generate": bool(any(section["statement_count"] for section in sections)) and not blockers,
        "requires_manual_review": bool(any(section["risk_level"] in {"medium", "high"} for section in sections)),
    }


def get_database_release_package_review(package_id):
    """Read a local immutable package for visual inspection without executing it."""
    normalized_id = str(package_id or "").strip()
    package = next((item for item in list_database_release_packages() if item["id"] == normalized_id), None)
    if not package:
        raise ValueError("database_release_package_invalid")
    payload_path = ROOT / package["id"] / f"{package['type']}.sql"
    sql_text = payload_path.read_text(encoding="utf-8")
    risk_level = {"schema": "low", "master_data": "medium", "data": "high"}.get(package["type"], "high")
    preview_limit = 180000
    return {
        "package": {**package, "checksum": _database_release_package_checksum(package)},
        "risk_level": risk_level,
        "statement_count": sum(1 for line in sql_text.splitlines() if line.strip().endswith(";")),
        "line_count": len(sql_text.splitlines()),
        "sql_chars": len(sql_text),
        "sql": sql_text[:preview_limit],
        "sql_truncated": len(sql_text) > preview_limit,
    }


def _next_database_release_version(offset=0):
    versions = []
    for package in list_database_release_packages():
        match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", str(package.get("version") or ""))
        if match:
            versions.append(tuple(int(value) for value in match.groups()))
    major, minor, patch = max(versions, default=(1, 0, -1))
    return f"v{major}.{minor}.{patch + 1 + offset}"


def _write_generated_database_release_package(package_type, version, title, sql_text, target_name):
    package_dir = PACKAGES_DIR / datetime.now().strftime("%Y-%m-%d") / version
    if package_dir.exists():
        raise RuntimeError("database_release_generated_version_exists")
    package_dir.mkdir(parents=True, exist_ok=False)
    (package_dir / "release.env").write_text(
        "\n".join((
            f"RELEASE_VERSION={shlex.quote(version)}",
            f"PACKAGE_TYPE={shlex.quote(package_type)}",
            f"DELTA_TARGET={shlex.quote(target_name)}",
            f"TITLE={shlex.quote(title)}",
            "",
        )),
        encoding="utf-8",
    )
    (package_dir / f"{package_type}.sql").write_text(
        "-- Generated by the local-to-target delta scanner.\n"
        "-- Additive only: target-only rows and destructive schema changes are excluded.\n\n"
        + sql_text.rstrip() + "\n",
        encoding="utf-8",
    )
    return {
        "id": str(package_dir.relative_to(ROOT)),
        "version": version,
        "type": package_type,
        "title": title,
        "delta_target": target_name,
    }


def generate_database_release_delta(target_name, include_schema=True, include_master_data=True, include_runtime_data=False):
    """Create new versioned SQL packages from a fresh local-to-target diff.

    No target database is written here. The generated package must still be
    selected and applied through the normal release operation.
    """
    target = get_database_release_target(target_name)
    if not target or target["name"] not in {"staging", "production"}:
        raise ValueError("database_release_target_invalid")
    with _delta_generation_lock:
        _, build_incremental_delta, get_local_app_db_target = _load_database_release_diff_tools()
        delta = build_incremental_delta(
            get_local_app_db_target(),
            target,
            include_schema=bool(include_schema),
            include_master_data=bool(include_master_data),
            include_runtime_data=bool(include_runtime_data),
        )
        report_path = _database_release_diff_report_path(target["name"])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(delta["report"], ensure_ascii=False, indent=2), encoding="utf-8")
        generated, blockers = [], []
        sections = (
            ("schema", "表结构增量", delta["schema"]),
            ("master_data", "主数据增量", delta["master_data"]),
            ("data", "业务运行数据增量", delta["runtime_data"]),
        )
        for package_type, label, section in sections:
            section_blockers = list(section.get("blockers") or [])
            if section_blockers:
                blockers.extend({"type": package_type, **item} for item in section_blockers)
                continue
            sql_text = str(section.get("sql") or "").strip()
            if not sql_text:
                continue
            version = _next_database_release_version(len(generated))
            generated.append(
                _write_generated_database_release_package(
                    package_type, version, f"本地到 {target['name']} {label}", sql_text, target["name"],
                )
            )
        review_sections = [
            _database_release_review_section("schema", delta["schema"]),
            _database_release_review_section("master_data", delta["master_data"]),
            _database_release_review_section("data", delta["runtime_data"]),
        ]
        return {
            "target": target["name"],
            "report_path": str(report_path.relative_to(ROOT)),
            "generated_packages": generated,
            "blockers": blockers,
            "safe_release_delta": delta["report"]["safe_release_delta"],
            "details": {
                "schema": delta["schema"].get("actions") or [],
                "master_data": delta["master_data"].get("details") or [],
                "runtime_data": delta["runtime_data"].get("details") or [],
            },
            "review": {
                "sections": review_sections,
                "blockers": blockers,
                "requires_manual_review": bool(any(section["risk_level"] in {"medium", "high"} for section in review_sections)),
            },
        }


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


def _run_process(command, target, job_id, operation, extra_env=None):
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
    # Source credentials are supplied only to operations that need a second
    # database endpoint, such as Production -> Staging cloning.
    env.update({str(key): str(value) for key, value in (extra_env or {}).items()})
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
        ("==> Exporting complete Production database:", "exporting", "正在导出 Production 完整数据库"),
        ("==> Exporting complete Staging database:", "exporting", "正在导出 Staging 完整数据库"),
        ("==> Restoring ", "restoring", "正在恢复至目标临时数据库"),
        ("Validated:", "validating", "正在校验临时数据库"),
        ("==> Validating Production and Staging temporary database equivalence", "validating", "正在校验 Production 与 Staging 临时库一致性"),
        ("==> Validating Staging and Production temporary database equivalence", "validating", "正在校验 Staging 与 Production 临时库一致性"),
        ("Database preparation complete.", "completed", "完整数据库发布完成"),
        ("Production-to-Staging sync complete.", "completed", "Production 已完整同步到 Staging"),
        ("Staging-to-Production sync complete.", "completed", "Staging 已完整同步到 Production"),
        ("Database clear complete.", "completed", "目标数据库已清空，可继续执行本地完整数据库导入"),
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
    if text.startswith("==> Terminating connections") or text.startswith("==> Retaining current database"):
        _record_release_event("switching", "正在清空目标数据库", "目标库连接已处理，原数据库将保留为可回滚备份；此阶段不可取消。", "active")
        _set_job(cancellable=False, progress={
            **dict(_release_job.get("progress") or {}),
            "state": "switching",
            "message": "正在清空目标数据库并保留回滚备份，此阶段不可取消",
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


def _start_job(target, command, operation, package_plan=None, extra_env=None):
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
    threading.Thread(target=_run_process, args=(command, target, job_id, operation, extra_env), daemon=True).start()
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
        release_plan = get_database_release_package_plan(target["name"])
        if release_plan["summary"].get("checksum_mismatch_total"):
            raise ValueError("database_release_package_checksum_mismatch")
        # Historical packages without a target ledger are archived for this
        # workflow. They remain protected from explicit replay, but they must
        # not prevent a normal "remaining delta" request from becoming the
        # clear no-op it is when no target-specific package is pending.
        package_plan = sorted(
            (item for item in release_plan["packages"] if item.get("status") == "pending"),
            key=lambda item: (item.get("date") or "", item.get("version") or "", item.get("id") or ""),
        )
        if not package_plan:
            raise ValueError("database_release_no_pending_packages")
        command = [str(PACKAGE_BATCH_SCRIPT), *[str(ROOT / item["id"]) for item in package_plan]]
        return _start_job(target, command, "release", package_plan=package_plan)
    package_plan = [item for item in packages if item["id"] == normalized_package]
    if normalized_package:
        release_plan = get_database_release_package_plan(target["name"])
        selected_status = next((item.get("status") for item in release_plan["packages"] if item.get("id") == normalized_package), "")
        if selected_status == "unverified":
            raise ValueError("database_release_baseline_verification_required")
        if selected_status == "checksum_mismatch":
            raise ValueError("database_release_package_checksum_mismatch")
    command = [str(PACKAGE_SCRIPT), str(ROOT / normalized_package)] if normalized_package else [str(PREPARE_SCRIPT)]
    return _start_job(target, command, "release", package_plan=package_plan)


def start_database_clear(target_name, confirmation="", confirm_production=False):
    """Create a destructive task that replaces the target with an empty DB."""
    target = get_database_release_target(target_name)
    if not target or target["name"] not in {"staging", "production"}:
        raise ValueError("database_release_target_invalid")
    expected = f"CLEAR {target['name'].upper()}"
    if str(confirmation or "").strip() != expected:
        raise ValueError("database_clear_confirmation_required")
    if target["name"] == "production" and confirm_production is not True:
        raise ValueError("production_confirmation_required")
    return _start_job(target, [str(CLEAR_DATABASE_SCRIPT)], "clear_database")


def start_database_release_packages(target_name, package_ids, confirm_production=False):
    """Publish exactly the packages reviewed in the current UI workflow."""
    target = get_database_release_target(target_name)
    if not target or target["name"] not in {"staging", "production"}:
        raise ValueError("database_release_target_invalid")
    if target["name"] == "production" and confirm_production is not True:
        raise ValueError("production_confirmation_required")
    requested = []
    for package_id in package_ids or []:
        normalized = str(package_id or "").strip()
        if normalized and normalized not in requested:
            requested.append(normalized)
    packages = list_database_release_packages()
    package_by_id = {item["id"]: item for item in packages}
    if not requested or any(package_id not in package_by_id for package_id in requested):
        raise ValueError("database_release_package_invalid")
    plan = get_database_release_package_plan(target["name"])
    plan_by_id = {item["id"]: item for item in plan["packages"]}
    selected = [plan_by_id[package_id] for package_id in requested if package_id in plan_by_id]
    if len(selected) != len(requested):
        raise ValueError("database_release_package_invalid")
    if any(item.get("status") != "pending" for item in selected):
        raise ValueError("database_release_package_not_pending")
    selected.sort(key=lambda item: (item.get("date") or "", item.get("version") or "", item.get("id") or ""))
    command = [str(PACKAGE_BATCH_SCRIPT), *[str(ROOT / item["id"]) for item in selected]]
    return _start_job(target, command, "release", package_plan=selected)


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


def start_production_to_staging_sync():
    """Create a single-flight task which makes Staging a Production copy.

    The task only accepts this fixed direction. The source credentials are
    passed to the worker as private process environment, never persisted in
    release state or task logs.
    """
    production = get_database_release_target("production")
    staging = get_database_release_target("staging")
    if not production or production["name"] != "production":
        raise ValueError("production_source_unavailable")
    if not staging or staging["name"] != "staging":
        raise ValueError("staging_target_unavailable")
    if (
        production["db_host"], production["db_port"], production["db_name"]
    ) == (
        staging["db_host"], staging["db_port"], staging["db_name"]
    ):
        raise ValueError("production_and_staging_must_differ")
    source_env = {
        "PRODUCTION_DB_NAME": production["db_name"],
        "PRODUCTION_DB_USER": production["db_user"],
        "PRODUCTION_DB_HOST": production["db_host"],
        "PRODUCTION_DB_PORT": production["db_port"],
        "PRODUCTION_DB_PASSWORD": production["db_password"],
        "CONFIRM_PRODUCTION_TO_STAGING_SYNC": "YES",
    }
    return _start_job(
        staging,
        [str(PRODUCTION_TO_STAGING_SCRIPT)],
        "production_to_staging",
        extra_env=source_env,
    )


def start_staging_to_production_sync():
    """Create the fixed-direction full publish from Staging to Production."""
    staging = get_database_release_target("staging")
    production = get_database_release_target("production")
    if not staging or staging["name"] != "staging":
        raise ValueError("staging_source_unavailable")
    if not production or production["name"] != "production":
        raise ValueError("production_target_unavailable")
    if (
        staging["db_host"], staging["db_port"], staging["db_name"]
    ) == (
        production["db_host"], production["db_port"], production["db_name"]
    ):
        raise ValueError("staging_and_production_must_differ")
    source_env = {
        "STAGING_DB_NAME": staging["db_name"],
        "STAGING_DB_USER": staging["db_user"],
        "STAGING_DB_HOST": staging["db_host"],
        "STAGING_DB_PORT": staging["db_port"],
        "STAGING_DB_PASSWORD": staging["db_password"],
        "CONFIRM_STAGING_TO_PRODUCTION_SYNC": "YES",
    }
    return _start_job(
        production,
        [str(STAGING_TO_PRODUCTION_SCRIPT)],
        "staging_to_production",
        extra_env=source_env,
    )


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
