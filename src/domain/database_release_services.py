"""Admin-owned database release operations.

This replaces the standalone local Flask controller. Destructive database
operations stay allow-listed, single-flight, and are exposed only through the
main application's Admin API.
"""

import os
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2


ROOT = Path(__file__).resolve().parents[2]
PREPARE_SCRIPT = ROOT / "scripts" / "prepare_database_release.sh"
PACKAGE_SCRIPT = ROOT / "scripts" / "apply_database_release_package.sh"
ROLLBACK_SCRIPT = ROOT / "scripts" / "rollback_database_release.sh"
PACKAGES_DIR = ROOT / "database_release_packages"
CONFIG_FILE = Path(os.environ.get("DATABASE_RELEASE_CONFIG", str(ROOT / ".database_release.env")))
_config_loaded = False
_release_lock = threading.Lock()
_release_job = {"status": "idle", "id": "", "target": "", "operation": "", "log": "", "started_at": "", "finished_at": "", "returncode": None}

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
        if package_type in {"master_data", "data"} and values.get("RELEASE_VERSION") and payload.exists():
            packages.append({
                "id": str(config_path.parent.relative_to(ROOT)),
                "date": config_path.parent.parent.name,
                "version": values["RELEASE_VERSION"],
                "type": package_type,
                "title": values.get("TITLE", ""),
            })
    return packages


def get_database_release_job():
    with _release_lock:
        return dict(_release_job)


def _set_job(**values):
    with _release_lock:
        _release_job.update(values)


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
    log_path = ROOT / ".deploy" / f"admin_{operation}_{job_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        _set_job(status="running", log=str(log_path))
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, text=True)
        _set_job(pid=process.pid)
        return_code = process.wait()
    _set_job(status="succeeded" if return_code == 0 else "failed", returncode=return_code, finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))


def _start_job(target, command, operation):
    with _release_lock:
        if _release_job.get("status") in {"queued", "running"}:
            raise ValueError("database_release_job_running")
        job_id = time.strftime("%Y%m%d_%H%M%S")
        _release_job.update({"status": "queued", "id": job_id, "target": target["name"], "operation": operation, "log": "", "started_at": time.strftime("%Y-%m-%d %H:%M:%S"), "finished_at": "", "returncode": None})
    threading.Thread(target=_run_process, args=(command, target, job_id, operation), daemon=True).start()
    return get_database_release_job()


def start_database_release(target_name, package_id="", confirm_production=False):
    target = get_database_release_target(target_name)
    if not target or target["name"] not in {"staging", "production"}:
        raise ValueError("database_release_target_invalid")
    if target["name"] == "production" and confirm_production is not True:
        raise ValueError("production_confirmation_required")
    package_ids = {item["id"] for item in list_database_release_packages()}
    normalized_package = str(package_id or "").strip()
    if normalized_package and normalized_package not in package_ids:
        raise ValueError("database_release_package_invalid")
    command = [str(PACKAGE_SCRIPT), str(ROOT / normalized_package)] if normalized_package else [str(PREPARE_SCRIPT)]
    return _start_job(target, command, "release")


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
        log_path = Path(_release_job.get("log") or "") if _release_job.get("log") else None
    if not log_path or not log_path.exists():
        return "等待任务日志...\n"
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
