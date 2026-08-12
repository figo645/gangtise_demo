#!/usr/bin/env python3
"""Local-only web controller for full PostgreSQL database releases.

The database operation remains in scripts/prepare_database_release.sh. This
service provides a safe, allow-listed UI and job status around that operation.
"""

import os
import secrets
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta

from flask import Flask, jsonify, render_template_string, request


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "prepare_database_release.sh"
PACKAGE_SCRIPT = ROOT / "scripts" / "apply_database_release_package.sh"
ROLLBACK_SCRIPT = ROOT / "scripts" / "rollback_database_release.sh"
PACKAGES_DIR = ROOT / "database_release_packages"
HOST = os.environ.get("DATABASE_RELEASE_HOST", "127.0.0.1")
PORT = int(os.environ.get("DATABASE_RELEASE_PORT", "5051"))
CONFIG_FILE = Path(
    os.environ.get("DATABASE_RELEASE_CONFIG", str(ROOT / ".database_release.env"))
)
if CONFIG_FILE.exists():
    for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
TOKEN = os.environ.get("DATABASE_RELEASE_TOKEN", "").strip()


def _target(name):
    if name not in {"local", "staging", "production"}:
        return None
    prefix = {"local": "LOCAL", "staging": "STAGING", "production": "PRODUCTION"}[name]
    default_host = {"local": "127.0.0.1", "staging": "129.211.65.53", "production": "47.105.48.193"}[name]
    db_host = os.environ.get(f"DATABASE_RELEASE_{prefix}_DB_HOST", default_host).strip()
    if not db_host:
        return None
    return {
        "name": name,
        "db_name": os.environ.get(f"DATABASE_RELEASE_{prefix}_DB_NAME", "sprint_dashboard"),
        "db_user": os.environ.get(f"DATABASE_RELEASE_{prefix}_DB_USER", "postgres"),
        "db_host": db_host,
        "db_port": os.environ.get(
            f"DATABASE_RELEASE_{prefix}_DB_PORT", "5432"
        ),
        "db_password": os.environ.get(f"DATABASE_RELEASE_{prefix}_DB_PASSWORD", "your_password"),
    }


def simulation_targets():
    return [name for name in ("local", "staging", "production") if _target(name)]


def release_packages():
    packages = []
    for config_path in sorted(PACKAGES_DIR.glob("*/*/release.env"), reverse=True):
        values = {}
        for line in config_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
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


def rollback_records(target):
    import psycopg2

    try:
        with psycopg2.connect(
            host=target["db_host"], port=target["db_port"], dbname="postgres",
            user=target["db_user"], password=target["db_password"], connect_timeout=5,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT datname, pg_size_pretty(pg_database_size(datname)) "
                    "FROM pg_database WHERE datname LIKE %s ORDER BY datname DESC",
                    (f"{target['db_name']}_backup_%",),
                )
                return [{"name": row[0], "size": row[1]} for row in cursor.fetchall()]
    except Exception:
        return []


SIMULATION_LABEL = "模拟数据"
SIMULATED_FAN_SEED = [
    ("演示粉丝-小陈", "600519", "贵州茅台", "高端白酒", "品牌护城河仍在，想继续跟踪渠道动销和估值变化。"),
    ("演示粉丝-小陈", "300750", "宁德时代", "动力电池", "关注储能需求和海外订单能否改善。"),
    ("演示粉丝-小周", "688981", "中芯国际", "半导体制造", "希望了解成熟制程景气和产能利用率的验证节奏。"),
    ("演示粉丝-小周", "00700", "腾讯控股", "港股互联网", "关注回购、广告业务和财报兑现。"),
    ("演示粉丝-小林", "600036", "招商银行", "银行", "想跟踪息差、资产质量和分红的变化。"),
]


def _simulation_connection(target):
    import psycopg2

    return psycopg2.connect(
        host=target["db_host"], port=target["db_port"], dbname=target["db_name"],
        user=target["db_user"], password=target["db_password"], connect_timeout=5,
    )


def _ensure_simulation_schema(cursor):
    migration = ROOT / "sql" / "postgres" / "032_simulated_fan_data_management.sql"
    cursor.execute(migration.read_text(encoding="utf-8"))


def simulation_batches(target):
    try:
        with _simulation_connection(target) as connection:
            with connection.cursor() as cursor:
                _ensure_simulation_schema(cursor)
                cursor.execute(
                    """
                    SELECT b.batch_code, b.tenant_slug, b.batch_label, b.created_at, b.created_by, b.notes,
                           (SELECT COUNT(*) FROM users u WHERE u.simulation_batch_code = b.batch_code AND u.is_simulated = 1) AS user_count,
                           (SELECT COUNT(*) FROM fan_stock_observation_events e WHERE e.simulation_batch_code = b.batch_code AND e.is_simulated = 1) AS watchlist_count,
                           (SELECT COUNT(*) FROM watchlist_comments c WHERE c.simulation_batch_code = b.batch_code AND c.is_simulated = 1) AS comment_count
                    FROM simulated_data_batches b
                    ORDER BY b.created_at DESC, b.batch_code DESC
                    """
                )
                columns = [item[0] for item in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as exc:
        return {"error": str(exc)}


def create_simulation_batch(target, tenant_slug):
    normalized_tenant = str(tenant_slug or "laowang").strip().lower()
    if normalized_tenant != "laowang":
        raise ValueError("当前只允许为财经老王租户创建模拟粉丝数据")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_code = f"sim_fans_{normalized_tenant}_{stamp}"
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _simulation_connection(target) as connection:
        with connection.cursor() as cursor:
            _ensure_simulation_schema(cursor)
            cursor.execute(
                "INSERT INTO simulated_data_batches (batch_code, tenant_slug, batch_label, created_at, created_by, notes) VALUES (%s, %s, %s, %s, %s, %s)",
                (batch_code, normalized_tenant, SIMULATION_LABEL, created_at, "database_release_web", "模拟粉丝、自选股与个股评论"),
            )
            user_names = sorted({row[0] for row in SIMULATED_FAN_SEED})
            batch_suffix = stamp[-6:]
            simulated_user_names = {name: f"{name}-{batch_suffix}" for name in user_names}
            for index, username in enumerate(user_names, start=1):
                simulated_username = simulated_user_names[username]
                cursor.execute(
                    """
                    INSERT INTO users (username, password, role, tenant_slug, advisor_name, phone, status, created_at, updated_at, labels_json, source_label, is_simulated, simulation_batch_code, simulation_label)
                    VALUES (%s, %s, 'investor', %s, %s, %s, 'active', %s, %s, %s, %s, 1, %s, %s)
                    """,
                    (simulated_username, "demo123", normalized_tenant, "财经老王", f"1390000{index:04d}", created_at, created_at, '["模拟数据", "演示粉丝"]', SIMULATION_LABEL, batch_code, SIMULATION_LABEL),
                )
            for index, (username, code, name, sector, comment) in enumerate(SIMULATED_FAN_SEED, start=1):
                simulated_username = simulated_user_names[username]
                event_at = (datetime.now() - timedelta(minutes=index * 7)).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute(
                    """
                    INSERT INTO fan_stock_observation_events (tenant_slug, user_profile_id, user_role, stock_code, stock_name, sector_name, event_type, entry_point, source_detail, created_at, is_simulated, simulation_batch_code, simulation_label)
                    VALUES (%s, %s, 'investor', %s, %s, %s, 'watchlist_add', 'simulation_seed', %s, %s, 1, %s, %s)
                    """,
                    (normalized_tenant, simulated_username, code, name, sector, SIMULATION_LABEL, event_at, batch_code, SIMULATION_LABEL),
                )
                cursor.execute(
                    """
                    INSERT INTO watchlist_comments (tenant_slug, stock_code, stock_name, comment_text, label_tags_json, keyword_tags_json, sentiment_label, topic_label, comment_summary, labeling_source, labeling_model_key, labeling_model_name, created_by_user_id, created_by_name, created_by_role, source_client, created_at, updated_at, is_simulated, simulation_batch_code, simulation_label)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'simulation_seed', '', '', %s, %s, 'investor', 'simulation_seed', %s, %s, 1, %s, %s)
                    """,
                    (normalized_tenant, code, name, comment, '["模拟数据", "个股关注"]', f'["{sector}"]', "中性", sector, "模拟粉丝个股评论", simulated_username, simulated_username, event_at, event_at, batch_code, SIMULATION_LABEL),
                )
    return batch_code


def delete_simulation_batch(target, batch_code):
    normalized_batch = str(batch_code or "").strip()
    if not normalized_batch:
        raise ValueError("模拟批次不能为空")
    with _simulation_connection(target) as connection:
        with connection.cursor() as cursor:
            _ensure_simulation_schema(cursor)
            cursor.execute("SELECT 1 FROM simulated_data_batches WHERE batch_code = %s", (normalized_batch,))
            if not cursor.fetchone():
                raise ValueError("模拟批次不存在")
            cursor.execute("DELETE FROM watchlist_comments WHERE simulation_batch_code = %s AND is_simulated = 1", (normalized_batch,))
            cursor.execute("DELETE FROM fan_stock_observation_events WHERE simulation_batch_code = %s AND is_simulated = 1", (normalized_batch,))
            cursor.execute("DELETE FROM users WHERE simulation_batch_code = %s AND is_simulated = 1", (normalized_batch,))
            cursor.execute("DELETE FROM simulated_data_batches WHERE batch_code = %s", (normalized_batch,))


app = Flask(__name__)
lock = threading.Lock()
job = {"status": "idle", "id": "", "target": "", "log": "", "started_at": "", "finished_at": ""}


def authorized():
    return not TOKEN or secrets.compare_digest(request.headers.get("X-Release-Token", ""), TOKEN)


def run_release(target, job_id):
    package_id = target.pop("package_id", "")
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_RELEASE_TARGET": target["name"],
            "REMOTE_DB_NAME": target["db_name"],
            "REMOTE_DB_USER": target["db_user"],
            "REMOTE_DB_HOST": target["db_host"],
            "REMOTE_DB_PORT": target["db_port"],
            "REMOTE_DB_PASSWORD": target["db_password"],
            "CONFIRM_DATABASE_REPLACE": "YES",
        }
    )
    log_path = ROOT / ".deploy" / f"web_release_{job_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        with lock:
            job["status"] = "running"
        command = [str(PACKAGE_SCRIPT), str(ROOT / package_id)] if package_id else [str(SCRIPT)]
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        with lock:
            job["pid"] = process.pid
            job["log"] = str(log_path)
        code = process.wait()
    with lock:
        job["status"] = "succeeded" if code == 0 else "failed"
        job["error_hint"] = ""
        job["returncode"] = code
        job["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def run_rollback(target, backup_name, job_id):
    env = os.environ.copy()
    env.update({
        "DATABASE_RELEASE_TARGET": target["name"], "REMOTE_DB_NAME": target["db_name"],
        "REMOTE_DB_USER": target["db_user"], "REMOTE_DB_HOST": target["db_host"],
        "REMOTE_DB_PORT": target["db_port"], "REMOTE_DB_PASSWORD": target["db_password"],
    })
    log_path = ROOT / ".deploy" / f"web_rollback_{job_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        with lock:
            job["status"] = "running"
        process = subprocess.Popen([str(ROLLBACK_SCRIPT), backup_name], cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, text=True)
        with lock:
            job["pid"] = process.pid
            job["log"] = str(log_path)
        code = process.wait()
    with lock:
        job["status"] = "succeeded" if code == 0 else "failed"
        job["returncode"] = code
        job["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


HTML = """
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>数据库预发布</title><style>
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#eef3f8;background:#0d1b2a}
body{max-width:860px;margin:0 auto;padding:32px 20px}main{background:#13283b;border:1px solid #29445c;border-radius:10px;padding:24px}
h1{font-size:22px;margin:0 0 8px}p,.meta{color:#a8b7c5;font-size:13px;line-height:1.6}.targets{display:flex;gap:12px;margin:24px 0}
button{border:0;border-radius:6px;padding:11px 18px;color:#fff;background:#1d6fa5;font-size:14px;cursor:pointer}button.production{background:#a34a43}button:disabled{opacity:.45;cursor:not-allowed}
button.rollback{background:#8a5b28;padding:8px 12px;font-size:12px}
select{margin:10px 0;padding:9px;background:#0b1825;color:#eef3f8;border:1px solid #3b5b72;border-radius:5px;max-width:100%}
pre{background:#09131f;border:1px solid #29445c;padding:16px;min-height:220px;white-space:pre-wrap;overflow:auto;font:12px/1.6 ui-monospace,monospace;color:#dce8f0}
.status{padding:10px 12px;border-left:3px solid #4ea3d8;background:#102235}.warning{color:#f2c078}
.rollback-section{margin-top:24px;border-top:1px solid #29445c;padding-top:18px}.rollback-row{display:flex;justify-content:space-between;align-items:center;gap:12px;border-top:1px solid #29445c;padding:10px 0}.rollback-name{font:11px ui-monospace,monospace;color:#dce8f0}.rollback-meta{font-size:11px;color:#a8b7c5}
.simulation-section{margin-top:24px;border-top:1px solid #29445c;padding-top:18px}.simulation-row{display:flex;justify-content:space-between;align-items:center;gap:12px;border-top:1px solid #29445c;padding:12px 0}.simulation-name{font:11px ui-monospace,monospace;color:#dce8f0}.simulation-stats{color:#a8b7c5;font-size:12px;margin-top:4px}.simulation-actions{display:flex;gap:8px}.simulation-create{background:#27745d}.simulation-delete{background:#a34a43;padding:8px 12px;font-size:12px}
</style></head><body><main><h1>数据库全量预发布</h1>
<p>选择全量数据库预发布时，将本地开发库完整同步到选定环境。选择增量包时，只执行该包的主数据或数据变更。两种方式都不会启动 Python 应用。</p>
<div class="status" id="status">状态：空闲（尚未执行发布任务）</div>
<div class="meta">发布内容：<select id="package"><option value="">全量数据库预发布</option>{% for p in packages %}<option value="{{ p.id }}">{{ p.date }} · {{ p.version }} · {{ '数据增量' if p.type == 'data' else '主数据增量' }} · {{ p.title }}</option>{% endfor %}</select></div><div class="targets">
<button onclick="release('staging')" id="staging">同步 Staging</button>
<button onclick="release('production')" id="production" class="production">同步 Production</button></div>
<div class="meta" id="targets-meta">已配置目标：{{ configured|join('、') or '暂无，请检查环境配置' }}</div><div class="meta" id="meta"></div><div class="meta warning" id="hint"></div><pre id="log">等待任务...</pre><section class="rollback-section"><h2 style="font-size:16px;margin:0 0 6px">回滚记录</h2><p style="margin:0 0 12px">回滚会将备份库切换为当前库，并保留现有数据库作为新的回滚点。</p><div id="rollback-records">加载中...</div></section><section class="simulation-section"><h2 style="font-size:16px;margin:0 0 6px">模拟粉丝数据</h2><p style="margin:0 0 12px">创建财经老王租户的模拟粉丝账号、自选股和个股评论。全部记录带“模拟数据”标签、批次号和时间戳；删除按批次执行，不影响真实数据。</p><div class="meta">目标环境：<select id="simulation-target" onchange="loadSimulations()">{% for target in simulation_targets %}<option value="{{ target }}">{{ '本地开发库（Mac）' if target == 'local' else target }}</option>{% endfor %}</select> <button class="simulation-create" onclick="createSimulation()">创建模拟批次</button></div><div class="meta">模拟账号密码统一为 <code>demo123</code>。</div><div id="simulation-records">加载中...</div></section></main><script>
let timer=null;
function statusText(d){
 const labels={idle:'空闲（尚未执行发布任务）',queued:'排队中（等待启动）',running:'执行中',succeeded:'已完成',failed:'失败'};
 return '状态：'+(labels[d.status]||d.status)+(d.target?'（'+d.target+'）':'');
}
async function release(target){
  const package_id=document.getElementById('package').value;
  const operation=package_id?'选中的数据库增量包':'本地完整数据库';
  if(target==='production'&&!confirm('即将向生产环境发布'+operation+'，继续吗？'))return;
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
  const r=await fetch('/api/releases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target,package_id})});
  const d=await r.json(); if(!r.ok){alert(d.error||'无法创建任务');document.querySelectorAll('button').forEach(b=>b.disabled=false);return}
  poll();
}
async function poll(){const r=await fetch('/api/releases/current');const d=await r.json();
 document.getElementById('status').textContent=statusText(d);document.getElementById('meta').textContent=d.log||'';document.getElementById('hint').textContent=d.error_hint||'';
 if(d.log){const t=await fetch('/api/releases/log');document.getElementById('log').textContent=await t.text()}
 if(['running','queued'].includes(d.status))timer=setTimeout(poll,1500);else document.querySelectorAll('button').forEach(b=>b.disabled=false)}
async function loadRollbacks(){const container=document.getElementById('rollback-records');const targets={{ configured|tojson }};const responses=await Promise.all(targets.map(async target=>({target,response:await fetch('/api/rollbacks?target='+target)})));let html='';for(const item of responses){const data=await item.response.json();html+=`<div class="rollback-meta" style="margin-top:10px">${item.target}</div>`;if(!item.response.ok){html+=`<div class="rollback-meta">${data.error||'读取失败'}</div>`;continue}html+=data.records.length?data.records.map(r=>`<div class="rollback-row"><div><div class="rollback-name">${r.name}</div><div class="rollback-meta">${r.size}</div></div><button class="rollback" onclick="rollback('${item.target}','${r.name}')">回滚</button></div>`).join(''):'<div class="rollback-meta">暂无可用回滚记录</div>';}container.innerHTML=html;}
async function rollback(target,name){if(!confirm('确认将 '+target+' 回滚到 '+name+'？当前数据库会保留为新的回滚点。'))return;document.querySelectorAll('button').forEach(b=>b.disabled=true);const r=await fetch('/api/rollbacks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target,backup_name:name})});const d=await r.json();if(!r.ok){alert(d.error||'无法创建回滚任务');document.querySelectorAll('button').forEach(b=>b.disabled=false);return}poll();}
async function loadSimulations(){const host=document.getElementById('simulation-records');const target=document.getElementById('simulation-target').value;const r=await fetch('/api/simulations?target='+target);const d=await r.json();if(!r.ok){host.textContent=d.error||'读取失败';return}host.innerHTML=d.batches.length?d.batches.map(b=>`<div class="simulation-row"><div><div class="simulation-name">${b.batch_code}</div><div class="simulation-stats">${b.tenant_slug} · ${b.batch_label} · ${b.created_at}<br>账号 ${b.user_count} · 自选 ${b.watchlist_count} · 评论 ${b.comment_count}</div></div><div class="simulation-actions"><button class="simulation-delete" onclick="deleteSimulation('${b.batch_code}')">删除批次</button></div></div>`).join(''):'暂无模拟粉丝数据';}
async function createSimulation(){const target=document.getElementById('simulation-target').value;if(!confirm('将在 '+target+' 创建一批财经老王模拟粉丝账号、自选股和评论。账号密码为 demo123，继续吗？'))return;const r=await fetch('/api/simulations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target,tenant_slug:'laowang'})});const d=await r.json();if(!r.ok){alert(d.error||'创建失败');return}alert('已创建模拟批次：'+d.batch_code);loadSimulations();}
async function deleteSimulation(batchCode){const target=document.getElementById('simulation-target').value;if(!confirm('确认删除模拟批次 '+batchCode+'？仅删除带“模拟数据”标签的账号、自选和评论。'))return;const r=await fetch('/api/simulations/'+encodeURIComponent(batchCode),{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({target})});const d=await r.json();if(!r.ok){alert(d.error||'删除失败');return}loadSimulations();}
poll();loadRollbacks();loadSimulations();</script></body></html>
"""


ROLLBACK_HTML = """
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>数据库回滚记录</title><style>
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#eef3f8;background:#0d1b2a}body{max-width:860px;margin:0 auto;padding:32px 20px}main{background:#13283b;border:1px solid #29445c;border-radius:10px;padding:24px}h1{font-size:22px;margin:0 0 8px}p{color:#a8b7c5;font-size:13px;line-height:1.6}.row{display:flex;justify-content:space-between;align-items:center;border-top:1px solid #29445c;padding:14px 0;gap:16px}.name{font:12px ui-monospace,monospace}.meta{color:#a8b7c5;font-size:12px}button{border:0;border-radius:6px;padding:8px 12px;color:#fff;background:#8a5b28;font-size:12px;cursor:pointer}button:disabled{opacity:.45}</style></head><body><main><h1>数据库回滚记录</h1><p>回滚会将选中的完整数据库备份切换为当前库，并将当前库保留为新的回滚点。仅显示全量数据库预发布生成的备份。</p><div id="records">加载中...</div></main><script>
async function load(){const r=await fetch('/api/rollbacks?target=staging');const d=await r.json();const host=document.getElementById('records');if(!r.ok){host.textContent=d.error||'读取失败';return}host.innerHTML=d.records.length?d.records.map(x=>`<div class="row"><div><div class="name">${x.name}</div><div class="meta">${x.size}</div></div><button onclick="rollback('${x.name}')">回滚到此版本</button></div>`).join(''):'暂无可用回滚记录';}
async function rollback(name){if(!confirm('确认将 staging 回滚到 '+name+'？当前数据库会保留为新的回滚点。'))return;const r=await fetch('/api/rollbacks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target:'staging',backup_name:name})});const d=await r.json();if(!r.ok){alert(d.error||'无法创建回滚任务');return}alert('回滚任务已启动，请返回发布首页查看日志。');}
load();</script></body></html>
"""


@app.get("/")
def index():
    if not authorized():
        return "Unauthorized", 401
    configured = [name for name in ("staging", "production") if _target(name)]
    return render_template_string(
        HTML,
        configured=configured,
        simulation_targets=simulation_targets(),
        packages=release_packages(),
    )


@app.get("/rollbacks")
def rollback_page():
    if not authorized():
        return "Unauthorized", 401
    return render_template_string(ROLLBACK_HTML)


@app.post("/api/releases")
def create_release():
    if not authorized():
        return jsonify(error="Unauthorized"), 401
    payload = request.get_json(silent=True) or {}
    target_name = str(payload.get("target", "")).lower()
    package_id = str(payload.get("package_id", "")).strip()
    target = _target(target_name) if target_name in {"staging", "production"} else None
    if not target:
        return jsonify(error="目标未配置，或目标不在允许列表中"), 400
    if package_id and package_id not in {item["id"] for item in release_packages()}:
        return jsonify(error="增量包不存在或未通过目录校验"), 400
    if package_id:
        target["package_id"] = package_id
    with lock:
        if job["status"] in {"queued", "running"}:
            return jsonify(error="已有数据库发布任务正在执行"), 409
        job.update(status="queued", id=time.strftime("%Y%m%d_%H%M%S"), target=target_name,
                   started_at=time.strftime("%Y-%m-%d %H:%M:%S"), finished_at="", log="", returncode=None)
        job_id = job["id"]
    threading.Thread(target=run_release, args=(target, job_id), daemon=True).start()
    return jsonify(job), 202


@app.get("/api/rollbacks")
def list_rollbacks():
    if not authorized():
        return jsonify(error="Unauthorized"), 401
    target_name = str(request.args.get("target", "staging")).lower()
    target = _target(target_name) if target_name in {"staging", "production"} else None
    if not target:
        return jsonify(error="目标未配置"), 400
    return jsonify(records=rollback_records(target))


@app.post("/api/rollbacks")
def create_rollback():
    if not authorized():
        return jsonify(error="Unauthorized"), 401
    payload = request.get_json(silent=True) or {}
    target_name = str(payload.get("target", "")).lower()
    backup_name = str(payload.get("backup_name", "")).strip()
    target = _target(target_name) if target_name in {"staging", "production"} else None
    if not target or backup_name not in {record["name"] for record in rollback_records(target)}:
        return jsonify(error="回滚记录不存在或目标未配置"), 400
    with lock:
        if job["status"] in {"queued", "running"}:
            return jsonify(error="已有数据库任务正在执行"), 409
        job.update(status="queued", id=time.strftime("%Y%m%d_%H%M%S"), target=target_name, started_at=time.strftime("%Y-%m-%d %H:%M:%S"), finished_at="", log="", returncode=None)
        job_id = job["id"]
    threading.Thread(target=run_rollback, args=(target, backup_name, job_id), daemon=True).start()
    return jsonify(job), 202


@app.get("/api/simulations")
def list_simulations():
    if not authorized():
        return jsonify(error="Unauthorized"), 401
    target_name = str(request.args.get("target", "staging")).lower()
    target = _target(target_name) if target_name in {"local", "staging", "production"} else None
    if not target:
        return jsonify(error="目标未配置"), 400
    result = simulation_batches(target)
    if isinstance(result, dict) and result.get("error"):
        return jsonify(error=result["error"]), 503
    return jsonify(batches=result)


@app.post("/api/simulations")
def create_simulation():
    if not authorized():
        return jsonify(error="Unauthorized"), 401
    payload = request.get_json(silent=True) or {}
    target_name = str(payload.get("target", "")).lower()
    target = _target(target_name) if target_name in {"local", "staging", "production"} else None
    if not target:
        return jsonify(error="目标未配置"), 400
    try:
        batch_code = create_simulation_batch(target, payload.get("tenant_slug"))
    except Exception as exc:
        return jsonify(error=str(exc)), 503
    return jsonify(ok=True, batch_code=batch_code), 201


@app.delete("/api/simulations/<batch_code>")
def remove_simulation(batch_code):
    if not authorized():
        return jsonify(error="Unauthorized"), 401
    payload = request.get_json(silent=True) or {}
    target_name = str(payload.get("target", "")).lower()
    target = _target(target_name) if target_name in {"local", "staging", "production"} else None
    if not target:
        return jsonify(error="目标未配置"), 400
    try:
        delete_simulation_batch(target, batch_code)
    except ValueError as exc:
        return jsonify(error=str(exc)), 404
    except Exception as exc:
        return jsonify(error=str(exc)), 503
    return jsonify(ok=True)


@app.get("/api/releases/current")
def current_release():
    if not authorized():
        return jsonify(error="Unauthorized"), 401
    with lock:
        return jsonify(job)


@app.get("/api/releases/log")
def release_log():
    if not authorized():
        return "Unauthorized", 401
    with lock:
        path = Path(job.get("log", "")) if job.get("log") else None
    if not path or not path.exists():
        return "等待任务日志...\n", 200, {"Content-Type": "text/plain; charset=utf-8"}
    return path.read_text(encoding="utf-8", errors="replace")[-50000:], 200, {"Content-Type": "text/plain; charset=utf-8"}


if __name__ == "__main__":
    if not SCRIPT.exists():
        raise SystemExit(f"Missing release script: {SCRIPT}")
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
