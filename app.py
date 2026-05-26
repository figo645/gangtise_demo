import os
import json
import sqlite3
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, g
import random
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from hmac import compare_digest

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("GANGTISE_DEMO_SECRET_KEY", os.urandom(32)),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

AUTH_PASSWORD = os.environ.get("GANGTISE_DEMO_PASSWORD", "gangtise")
AUTH_SESSION_KEY = "gangtise_auth"
DB_PATH = os.environ.get("GANGTISE_DEMO_DB", os.path.join(os.path.dirname(__file__), "gangtise_demo.db"))
SITE_CONFIG_KEY = "site_config"

DEFAULT_SITE_CONFIG = {
    "default_theme": "light",
    "default_accent": "blue",
    "feature_flags": {
        "fundamental_analysis": True,
        "watchlist": True,
        "daily_review": True,
        "community": False,
        "hermes": False,
        "vip": False,
        "dm": False,
        "workbench": False,
    },
}

# Mock data
CHANNELS = ["微信生态", "抖音", "微博", "小红书", "直接流量"]
FUNNEL_LAYERS = ["公域曝光", "私域沉淀", "主动意向", "付费转化", "VIP深度"]

def gen_funnel_data():
    base = [980000, 245000, 62000, 18500, 4200]
    return [{"layer": FUNNEL_LAYERS[i], "count": base[i], "rate": round(base[i]/base[0]*100, 2)} for i in range(5)]

def gen_channel_data():
    data = [
        {"name": "微信生态", "users": 420000, "conversion": 3.8, "revenue": 2840000, "color": "#07C160"},
        {"name": "抖音", "users": 310000, "conversion": 2.9, "revenue": 1920000, "color": "#FE2C55"},
        {"name": "微博", "users": 125000, "conversion": 2.1, "revenue": 680000, "color": "#E6162D"},
        {"name": "小红书", "users": 89000, "conversion": 4.2, "revenue": 920000, "color": "#FF2442"},
        {"name": "直接流量", "users": 36000, "conversion": 6.8, "revenue": 1240000, "color": "#C8A96E"},
    ]
    return data

def gen_kol_data():
    kols = [
        {"name": "财经老王", "platform": "抖音", "followers": 2800000, "gmv": 1240000, "commission": 186000, "tier": "S级"},
        {"name": "投资女神Lisa", "platform": "小红书", "followers": 1560000, "gmv": 890000, "commission": 133500, "tier": "S级"},
        {"name": "宏观策略师", "platform": "微信", "followers": 980000, "gmv": 620000, "commission": 93000, "tier": "A级"},
        {"name": "量化小白", "platform": "微博", "followers": 720000, "gmv": 380000, "commission": 57000, "tier": "A级"},
        {"name": "港股研究员", "platform": "抖音", "followers": 450000, "gmv": 210000, "commission": 31500, "tier": "B级"},
    ]
    return kols

def gen_market_data():
    indices = [
        {"name": "上证指数", "value": 3428.56, "change": 0.82, "change_pct": 0.024},
        {"name": "深证成指", "value": 10892.34, "change": -12.45, "change_pct": -0.114},
        {"name": "恒生指数", "value": 23156.78, "change": 234.12, "change_pct": 1.021},
        {"name": "纳斯达克", "value": 19234.56, "change": 89.34, "change_pct": 0.466},
        {"name": "黄金", "value": 3342.80, "change": 18.60, "change_pct": 0.559},
    ]
    return indices

def gen_news_feed():
    news = [
        {"title": "美联储6月议息会议前瞻：降息预期升温，市场如何定价？", "tag": "宏观", "time": "10分钟前", "hot": True},
        {"title": "【深度】新能源车渗透率突破50%，产业链投资机会梳理", "tag": "行业", "time": "32分钟前", "hot": True},
        {"title": "高盛最新报告：A股估值修复空间测算", "tag": "券商研报", "time": "1小时前", "hot": False},
        {"title": "专家会议纪要：某头部消费品牌Q2经营数据点评", "tag": "专家纪要", "time": "2小时前", "hot": False},
        {"title": "另类数据：卫星图像显示主要港口吞吐量环比回升8%", "tag": "另类数据", "time": "3小时前", "hot": False},
        {"title": "DeepSeek最新研究：AI算力需求2026年增速预测上调至180%", "tag": "科技", "time": "4小时前", "hot": True},
    ]
    return news

def gen_revenue_trend():
    months = []
    base_date = datetime(2025, 6, 1)
    for i in range(12):
        d = base_date + timedelta(days=30*i)
        months.append({
            "month": d.strftime("%Y-%m"),
            "revenue": int(800000 + i * 180000 + random.randint(-50000, 80000)),
            "users": int(12000 + i * 2800 + random.randint(-500, 1200)),
        })
    return months

def gen_user_segments():
    return [
        {"segment": "免费用户", "count": 186000, "pct": 72.4},
        {"segment": "基础会员", "count": 42000, "pct": 16.3},
        {"segment": "专业会员", "count": 18500, "pct": 7.2},
        {"segment": "机构VIP", "count": 4200, "pct": 1.6},
        {"segment": "KOL合伙人", "count": 620, "pct": 0.5},
    ]


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                path TEXT NOT NULL,
                method TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                user_agent TEXT,
                referrer TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_created_at ON access_logs(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_ip ON access_logs(ip)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_path ON access_logs(path)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        row = conn.execute(
            "SELECT setting_key FROM app_settings WHERE setting_key = ?",
            (SITE_CONFIG_KEY,),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                (
                    SITE_CONFIG_KEY,
                    json.dumps(DEFAULT_SITE_CONFIG, ensure_ascii=False),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
        conn.commit()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def _merge_site_config(base, override):
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_site_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_site_config():
    cached = g.get("site_config")
    if cached is not None:
        return cached
    db = get_db()
    row = db.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = ?",
        (SITE_CONFIG_KEY,),
    ).fetchone()
    config = dict(DEFAULT_SITE_CONFIG)
    if row and row["setting_value"]:
        try:
            stored = json.loads(row["setting_value"])
            if isinstance(stored, dict):
                config = _merge_site_config(config, stored)
        except Exception:
            app.logger.exception("Failed to parse site config")
    g.site_config = config
    return config


def save_site_config(config):
    merged = _merge_site_config(DEFAULT_SITE_CONFIG, config or {})
    db = get_db()
    db.execute(
        """
        INSERT INTO app_settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at = excluded.updated_at
        """,
        (
            SITE_CONFIG_KEY,
            json.dumps(merged, ensure_ascii=False),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    db.commit()
    g.site_config = merged
    return merged


@app.context_processor
def inject_site_config():
    return {"site_config": get_site_config()}


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def is_authenticated():
    return session.get(AUTH_SESSION_KEY) is True


def safe_next_target(target):
    if not target:
        return "/"
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return "/"
    if not target.startswith("/") or target.startswith("//"):
        return "/"
    return target


def get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()
    return request.remote_addr or "unknown"


def should_log_request():
    return not request.path.startswith("/static/") and not request.path.startswith("/api/")


def record_access(response):
    if not should_log_request():
        return response
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO access_logs (ip, path, method, status_code, created_at, user_agent, referrer)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                get_client_ip(),
                request.path,
                request.method,
                response.status_code,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                request.headers.get("User-Agent", ""),
                request.headers.get("Referer", ""),
            ),
        )
        db.commit()
    except Exception:
        app.logger.exception("Failed to write access log")
    return response


@app.before_request
def require_password_gate():
    public_paths = {"/login", "/unlock", "/logout"}
    if request.path.startswith("/static/") or request.path in public_paths:
        return None
    if is_authenticated():
        return None
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "auth_required"}), 401
    return redirect(url_for("login", next=safe_next_target(request.full_path.rstrip("?"))))


@app.after_request
def log_access(response):
    return record_access(response)

# Routes
@app.route("/login", methods=["GET"])
def login():
    next_target = safe_next_target(request.args.get("next", "/"))
    return render_template("login.html", next_target=next_target, error=None)


@app.route("/unlock", methods=["POST"])
def unlock():
    next_target = safe_next_target(request.form.get("next", "/"))
    password = request.form.get("password", "")
    if not compare_digest(password, AUTH_PASSWORD):
        return render_template("login.html", next_target=next_target, error="密码错误")
    session[AUTH_SESSION_KEY] = True
    session.permanent = True
    return redirect(next_target)


@app.route("/logout")
def logout():
    session.pop(AUTH_SESSION_KEY, None)
    return redirect(url_for("login"))


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/h5")
def h5():
    market = gen_market_data()
    news = gen_news_feed()
    return render_template("h5.html", market=market, news=news)

@app.route("/admin")
def admin():
    kols = gen_kol_data()
    segments = gen_user_segments()
    access_stats = get_access_summary()
    return render_template("admin.html", kols=kols, segments=segments, access_stats=access_stats)

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

# API endpoints
@app.route("/api/funnel")
def api_funnel():
    return jsonify(gen_funnel_data())

@app.route("/api/channels")
def api_channels():
    return jsonify(gen_channel_data())

@app.route("/api/kols")
def api_kols():
    return jsonify(gen_kol_data())

@app.route("/api/revenue")
def api_revenue():
    return jsonify(gen_revenue_trend())

@app.route("/api/segments")
def api_segments():
    return jsonify(gen_user_segments())

@app.route("/api/market")
def api_market():
    return jsonify(gen_market_data())


def get_access_summary():
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS c FROM access_logs").fetchone()["c"]
    unique_ips = db.execute("SELECT COUNT(DISTINCT ip) AS c FROM access_logs").fetchone()["c"]
    today = datetime.now().strftime("%Y-%m-%d")
    today_count = db.execute(
        "SELECT COUNT(*) AS c FROM access_logs WHERE created_at >= ?",
        (f"{today} 00:00:00",),
    ).fetchone()["c"]
    path_rows = db.execute(
        """
        SELECT path, COUNT(*) AS c
        FROM access_logs
        GROUP BY path
        ORDER BY c DESC, path ASC
        LIMIT 10
        """
    ).fetchall()
    ip_rows = db.execute(
        """
        SELECT ip, COUNT(*) AS c
        FROM access_logs
        GROUP BY ip
        ORDER BY c DESC, ip ASC
        LIMIT 10
        """
    ).fetchall()
    daily_rows = db.execute(
        """
        SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS c
        FROM access_logs
        GROUP BY day
        ORDER BY day DESC
        LIMIT 14
        """
    ).fetchall()
    recent_rows = db.execute(
        """
        SELECT ip, path, method, status_code, created_at
        FROM access_logs
        ORDER BY id DESC
        LIMIT 50
        """
    ).fetchall()
    return {
        "summary": {
            "total": total,
            "unique_ips": unique_ips,
            "today": today_count,
            "paths": len(path_rows),
        },
        "top_paths": [{"path": r["path"], "count": r["c"]} for r in path_rows],
        "top_ips": [{"ip": r["ip"], "count": r["c"]} for r in ip_rows],
        "daily_counts": [{"day": r["day"], "count": r["c"]} for r in reversed(daily_rows)],
        "recent_logs": [dict(r) for r in recent_rows],
    }


@app.route("/api/admin/access-stats")
def api_admin_access_stats():
    return jsonify(get_access_summary())


@app.route("/api/admin/access-logs")
def api_admin_access_logs():
    limit = min(int(request.args.get("limit", 50)), 200)
    db = get_db()
    rows = db.execute(
        """
        SELECT ip, path, method, status_code, created_at, user_agent, referrer
        FROM access_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/site-config")
def api_site_config():
    return jsonify(get_site_config())


@app.route("/api/admin/site-config", methods=["GET", "POST"])
def api_admin_site_config():
    if request.method == "GET":
        return jsonify(get_site_config())
    payload = request.get_json(silent=True) or {}
    current = get_site_config()
    feature_flags = dict(current.get("feature_flags", {}))
    incoming_flags = payload.get("feature_flags", {})
    for key in feature_flags:
        if key in incoming_flags:
            feature_flags[key] = bool(incoming_flags[key])
    next_config = _merge_site_config(
        current,
        {
            "default_theme": payload.get("default_theme", current.get("default_theme", "light")),
            "default_accent": payload.get("default_accent", current.get("default_accent", "blue")),
            "feature_flags": feature_flags,
        },
    )
    return jsonify({"success": True, "site_config": save_site_config(next_config)})

@app.route("/api/ai-analysis", methods=["POST"])
def api_ai_analysis():
    from flask import request
    topic = request.json.get("topic", "市场分析")
    responses = {
        "宏观经济": "基于最新宏观数据，美联储降息预期升温，国内货币政策保持宽松。建议关注利率敏感型资产，适当增配债券及高股息板块。风险提示：地缘政治不确定性仍存。",
        "A股策略": "当前A股估值处于历史中位偏低水平，外资持续流入信号积极。科技成长与高股息防御双主线并行，建议均衡配置。关注Q2财报季业绩超预期机会。",
        "港股机会": "港股互联网板块受益于AI应用落地加速，估值修复逻辑清晰。南向资金持续净流入，流动性改善。重点关注平台经济政策边际变化。",
        "新能源": "新能源车渗透率突破50%里程碑，产业链进入成熟期竞争。电池技术迭代加速，固态电池商业化时间表前移。关注具备技术壁垒的核心零部件企业。",
        "AI科技": "AI算力需求持续超预期，国产替代加速推进。DeepSeek等国内大模型商业化落地提速，应用层投资机会涌现。关注算力基础设施及AI应用双主线。",
    }
    result = responses.get(topic, f"针对{topic}的深度分析：基于冈底斯平台整合的券商研报、专家会议纪要及另类数据，当前该领域呈现结构性机会。建议结合个人风险偏好，参考KOL合伙人的专业解读后做出投资决策。")
    return jsonify({"topic": topic, "analysis": result, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "source": "冈底斯AI分析引擎 (DeepSeek + Kimi 2.6)"})

def gen_community_posts():
    return [
        {"id":1,"author":"财经老王","avatar":"👑","tier":"大V","badge":"S级合伙人","platform":"抖音","time":"8分钟前",
         "content":"今天美联储会议纪要出来了，核心信号是通胀预期下修+就业市场降温，降息窗口正在打开。A股科技板块短期受益，但要注意节奏，不要追高。我的操作思路：分批建仓AI算力ETF，止损设在近期低点下方3%。","likes":342,"comments":87,"shares":56,"tags":["宏观","A股","AI"],"hot":True,"points_reward":50},
        {"id":2,"author":"投资女神Lisa","avatar":"💎","tier":"大V","badge":"S级合伙人","platform":"小红书","time":"23分钟前",
         "content":"港股互联网这波反弹我觉得还没结束。南向资金连续12个交易日净流入，机构在悄悄加仓。平台经济监管边际改善是核心逻辑，估值还在历史低位。我已经在某互联网龙头上建了底仓，等待催化剂。","likes":218,"comments":64,"shares":31,"tags":["港股","互联网"],"hot":True,"points_reward":50},
        {"id":3,"author":"宏观策略师","avatar":"🎯","tier":"大V","badge":"A级合伙人","platform":"微信","time":"1小时前",
         "content":"分享一个另类数据视角：冈底斯卫星数据显示，长三角工业园区夜间灯光指数环比+6.2%，这是工业活动回暖的先行信号。结合PMI数据，Q2经济复苏力度可能超预期。关注顺周期板块。","likes":156,"comments":43,"shares":28,"tags":["另类数据","宏观","顺周期"],"hot":False,"points_reward":30},
        {"id":4,"author":"量化小白","avatar":"📊","tier":"认证用户","badge":"A级合伙人","platform":"微博","time":"2小时前",
         "content":"用冈底斯的Hermes跑了一个新能源板块的量化筛选，结果很有意思：固态电池产业链中，有3家公司的专利申请数量在过去6个月翻倍，但股价还没有反应。这种信息差就是alpha的来源。","likes":98,"comments":29,"shares":19,"tags":["量化","新能源","固态电池"],"hot":False,"points_reward":30},
        {"id":5,"author":"港股研究员","avatar":"🏙️","tier":"认证用户","badge":"B级合伙人","platform":"抖音","time":"3小时前",
         "content":"刚参加完某消费品牌的专家电话会议（冈底斯平台组织），核心观点：Q2动销数据好于预期，渠道库存已经基本出清，下半年有望量价齐升。这类一手信息真的很难在公开渠道找到。","likes":76,"comments":22,"shares":14,"tags":["消费","专家纪要"],"hot":False,"points_reward":30},
        {"id":6,"author":"普通用户_阿明","avatar":"😊","tier":"普通","badge":"","platform":"","time":"4小时前",
         "content":"第一次用冈底斯的Hermes分析工具，选了「研报精读」模式，把高盛的A股报告喂进去，AI给出的摘要和关键数据提取真的很准。比自己读省了至少2小时。积分也涨了，感觉很值！","likes":45,"comments":18,"shares":8,"tags":["使用体验","Hermes"],"hot":False,"points_reward":10},
    ]

def gen_community_events():
    return [
        {"id":1,"title":"【大V直播】财经老王：下半年A股配置策略","type":"直播","date":"2026-05-22 20:00","host":"财经老王","participants":2840,"points":100,"status":"报名中","badge":"🔴 即将开始"},
        {"id":2,"title":"【研报解读挑战赛】最佳分析师评选","type":"活动","date":"2026-05-20 ~ 06-05","host":"冈底斯官方","participants":1260,"points":500,"status":"进行中","badge":"🏆 进行中"},
        {"id":3,"title":"【专家会议】新能源产业链Q2展望","type":"会议","date":"2026-05-24 14:00","host":"行业专家团","participants":680,"points":200,"status":"报名中","badge":"🎙️ 专家"},
        {"id":4,"title":"【积分翻倍】本周发帖积分×2","type":"活动","date":"2026-05-20 ~ 05-26","host":"冈底斯官方","participants":5600,"points":0,"status":"进行中","badge":"⚡ 限时"},
    ]

def gen_user_profile():
    return {
        "name": "投研达人_小陈",
        "level": 4,
        "level_name": "资深分析师",
        "points": 3840,
        "points_to_next": 5000,
        "compute_credits": 128,
        "badges": ["早鸟用户","研报达人","社区贡献者"],
        "posts": 23,
        "likes_received": 456,
        "following": 12,
        "followers": 89,
        "tier": "专业会员",
    }

def gen_points_rules():
    return [
        {"action":"每日登录","points":5,"limit":"每日1次"},
        {"action":"发布帖子","points":10,"limit":"每日5次"},
        {"action":"帖子获赞","points":2,"limit":"无上限"},
        {"action":"参与活动","points":50,"limit":"每活动1次"},
        {"action":"邀请好友注册","points":100,"limit":"每人1次"},
        {"action":"完成AI分析任务","points":20,"limit":"每日3次"},
        {"action":"大V帖子互动","points":5,"limit":"每日10次"},
        {"action":"分享内容到社交平台","points":15,"limit":"每日3次"},
    ]

def gen_compute_exchange():
    return [
        {"name":"Hermes基础算力包","credits":50,"compute":"100次AI分析","desc":"适合日常使用"},
        {"name":"Hermes专业算力包","credits":200,"compute":"500次AI分析","desc":"适合深度研究"},
        {"name":"Hermes量化算力包","credits":500,"compute":"1500次AI分析+量化回测","desc":"适合量化策略"},
        {"name":"大V直播门票","credits":100,"compute":"1场专属直播","desc":"与大V实时互动"},
        {"name":"专家会议席位","credits":200,"compute":"1场专家电话会议","desc":"一手行业信息"},
    ]

HERMES_MODES = {
    "研报精读": {
        "icon": "📋",
        "desc": "上传或选择研报，AI提炼核心观点、关键数据、风险提示",
        "steps": ["选择研报来源", "选择分析深度", "获取结构化摘要"],
        "options": [
            {"label": "高盛 A股策略报告", "tag": "券商研报"},
            {"label": "中金 新能源深度", "tag": "券商研报"},
            {"label": "摩根士丹利 港股展望", "tag": "券商研报"},
            {"label": "国泰君安 AI算力专题", "tag": "券商研报"},
        ]
    },
    "专家纪要速读": {
        "icon": "🎙️",
        "desc": "专家会议纪要AI摘要，提炼核心观点和数据",
        "steps": ["选择行业方向", "选择时间范围", "获取纪要摘要"],
        "options": [
            {"label": "新能源产业链", "tag": "行业"},
            {"label": "AI与算力", "tag": "行业"},
            {"label": "消费复苏", "tag": "行业"},
            {"label": "医药生物", "tag": "行业"},
        ]
    },
    "另类数据解读": {
        "icon": "🛰️",
        "desc": "卫星图像、消费数据、舆情等另类数据的AI解读",
        "steps": ["选择数据类型", "选择分析维度", "获取信号解读"],
        "options": [
            {"label": "卫星工业活动指数", "tag": "另类数据"},
            {"label": "消费热力图", "tag": "另类数据"},
            {"label": "社交媒体情绪", "tag": "另类数据"},
            {"label": "港口吞吐量", "tag": "另类数据"},
        ]
    },
    "投资组合诊断": {
        "icon": "🔬",
        "desc": "输入持仓，AI分析风险敞口、相关性、优化建议",
        "steps": ["输入持仓结构", "选择风险偏好", "获取诊断报告"],
        "options": [
            {"label": "偏成长型组合", "tag": "风格"},
            {"label": "偏价值型组合", "tag": "风格"},
            {"label": "均衡配置组合", "tag": "风格"},
            {"label": "高股息防御组合", "tag": "风格"},
        ]
    },
    "市场情绪扫描": {
        "icon": "📡",
        "desc": "实时扫描市场情绪指标，识别极端情绪和拐点信号",
        "steps": ["选择市场范围", "选择情绪维度", "获取情绪报告"],
        "options": [
            {"label": "A股全市场", "tag": "市场"},
            {"label": "港股市场", "tag": "市场"},
            {"label": "美股科技板块", "tag": "市场"},
            {"label": "大宗商品", "tag": "市场"},
        ]
    },
    "量化因子筛选": {
        "icon": "⚙️",
        "desc": "基于多因子模型筛选股票，支持自定义因子权重",
        "steps": ["选择因子组合", "设置筛选条件", "获取股票列表"],
        "options": [
            {"label": "动量+质量因子", "tag": "因子"},
            {"label": "低估值+高股息", "tag": "因子"},
            {"label": "成长+盈利改善", "tag": "因子"},
            {"label": "技术面突破", "tag": "因子"},
        ]
    },
}

HERMES_RESPONSES = {
    "研报精读_高盛 A股策略报告": "【高盛A股策略报告精读】\n\n核心观点：维持A股「超配」评级，目标点位上调至4200点。\n\n关键数据：\n• 外资净流入连续8周正值，累计+420亿\n• 企业盈利预测上调3.2%\n• 估值PE 12.8x，低于历史均值15%\n\n主要逻辑：政策宽松周期+盈利复苏共振，科技板块受益AI应用落地。\n\n风险提示：地缘政治、汇率波动、房地产尾部风险。\n\n冈底斯评级：★★★★☆ 高质量研报",
    "专家纪要速读_新能源产业链": "【新能源产业链专家纪要摘要】\n\n会议时间：2026年5月18日\n参与专家：3位产业链核心专家\n\n核心观点：\n• 固态电池量产时间表提前至2027年Q3\n• 碳酸锂价格底部已现，Q3有望反弹\n• 海外市场拓展加速，欧洲工厂投产在即\n\n数据亮点：\n• 某头部电池企业Q2出货量环比+18%\n• 储能业务占比提升至35%\n\n投资含义：产业链底部已过，关注技术壁垒强的核心零部件企业。",
    "另类数据解读_卫星工业活动指数": "【卫星工业活动指数解读】\n\n数据时间：2026年5月第3周\n覆盖范围：长三角、珠三角、京津冀三大工业区\n\n核心信号：\n• 夜间灯光指数：+6.2%（环比）\n• 工厂烟囱热成像活跃度：+4.8%\n• 停车场占用率（工业园区）：+9.1%\n\n综合判断：工业活动明显回暖，领先PMI约2-3周。预计5月PMI数据将超预期。\n\n交叉验证：与货运数据、用电量数据形成三重共振，信号可靠性高。\n\n冈底斯信号强度：🟢🟢🟢🟢⚪ 强烈看多",
    "市场情绪扫描_A股全市场": "【A股市场情绪扫描报告】\n\n扫描时间：2026-05-20 实时\n\n情绪指标：\n• 恐贪指数：62（偏贪婪区间）\n• 融资余额：+3.2%（周环比）\n• 北向资金：今日净流入+28亿\n• 涨停板数量：47只（近期高位）\n\n情绪解读：市场处于温和乐观状态，未到极度贪婪。短期动能较强，但需警惕情绪过热后的回调风险。\n\n历史对比：当前情绪水平对应历史上未来1个月正收益概率约68%。\n\n操作建议：可适度参与，但控制仓位，避免追高。",
}

# New routes
@app.route("/api/community/posts")
def api_community_posts():
    return jsonify(gen_community_posts())

@app.route("/api/community/events")
def api_community_events():
    return jsonify(gen_community_events())

@app.route("/api/community/like", methods=["POST"])
def api_community_like():
    post_id = request.json.get("post_id")
    return jsonify({"success": True, "post_id": post_id, "points_earned": 2})

@app.route("/api/user/profile")
def api_user_profile():
    return jsonify(gen_user_profile())

@app.route("/api/user/points-rules")
def api_points_rules():
    return jsonify(gen_points_rules())

@app.route("/api/user/compute-exchange")
def api_compute_exchange():
    return jsonify(gen_compute_exchange())

@app.route("/api/hermes/modes")
def api_hermes_modes():
    return jsonify(list(HERMES_MODES.keys()))

@app.route("/api/hermes/mode-detail")
def api_hermes_mode_detail():
    mode = request.args.get("mode", "研报精读")
    return jsonify(HERMES_MODES.get(mode, {}))

@app.route("/api/hermes/analyze", methods=["POST"])
def api_hermes_analyze():
    mode = request.json.get("mode", "研报精读")
    option = request.json.get("option", "")
    key = f"{mode}_{option}"
    result = HERMES_RESPONSES.get(key, f"【{mode} · {option}】\n\n基于冈底斯平台整合的多维度数据，AI已完成深度分析。\n\n核心发现：该领域当前呈现结构性机会，关键指标向好。建议结合个人风险偏好，参考大V合伙人的专业解读后做出投资决策。\n\n数据来源：券商研报库 + 专家纪要库 + 另类数据库\nAI引擎：DeepSeek R2 + Kimi 2.6 RAG架构\n分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return jsonify({
        "mode": mode,
        "option": option,
        "result": result,
        "compute_used": 1,
        "points_earned": 20,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })

def gen_dm_conversations():
    return [
        {"id":1,"kol_name":"财经老王","kol_avatar":"👑","tier":"S级","last_msg":"好的，我周四直播会详细讲这个方向，记得来看","time":"5分钟前","unread":1,"vip_only":False},
        {"id":2,"kol_name":"投资女神Lisa","kol_avatar":"💎","tier":"S级","last_msg":"港股互联网的配置建议我已经发到专属频道了","time":"2小时前","unread":0,"vip_only":False},
        {"id":3,"kol_name":"量化老师陈明","kol_avatar":"📊","tier":"A级","last_msg":"[付费内容] 本周多因子模型调仓建议","time":"昨天","unread":0,"vip_only":True},
        {"id":4,"kol_name":"全球宏观James","kol_avatar":"🌐","tier":"A级","last_msg":"美联储会议纪要解读已更新，查看详情","time":"昨天","unread":0,"vip_only":False},
        {"id":5,"kol_name":"新能源猎手阿强","kol_avatar":"⚡","tier":"B级","last_msg":"固态电池调研纪要整理好了，分享给你","time":"3天前","unread":0,"vip_only":False},
    ]

def gen_dm_messages(kol_id):
    conversations = {
        1: [
            {"id":1,"sender":"kol","content":"欢迎关注我的专属频道！我会在这里分享一些不方便公开发的深度观点。","time":"2026-05-18 09:00","type":"text"},
            {"id":2,"sender":"user","content":"老王好！想请教一下，AI算力板块现在还能追吗？感觉涨了不少了","time":"2026-05-18 10:30","type":"text"},
            {"id":3,"sender":"kol","content":"好问题。短期确实有些过热，但中长期逻辑没变。我的建议是分批建仓，不要一把梭。具体标的我周四直播会讲。","time":"2026-05-18 11:00","type":"text"},
            {"id":4,"sender":"user","content":"明白，那我先建1/3仓位，等回调再加","time":"2026-05-20 08:15","type":"text"},
            {"id":5,"sender":"kol","content":"好的，我周四直播会详细讲这个方向，记得来看","time":"2026-05-20 08:20","type":"text"},
        ],
        2: [
            {"id":1,"sender":"kol","content":"Hi～欢迎加入我的专属圈子！港股互联网是我的核心研究方向，有问题随时问。","time":"2026-05-17 14:00","type":"text"},
            {"id":2,"sender":"user","content":"Lisa姐，南向资金最近流入很多，是不是该加仓港股了？","time":"2026-05-19 09:00","type":"text"},
            {"id":3,"sender":"kol","content":"港股互联网的配置建议我已经发到专属频道了","time":"2026-05-20 10:00","type":"text"},
            {"id":4,"sender":"kol","content":"简单说：当前估值20%分位，南向连续14天净买入，我觉得可以加到标配+5%。但注意分散，别只买一只。","time":"2026-05-20 10:02","type":"text"},
        ],
        3: [
            {"id":1,"sender":"kol","content":"欢迎！我的频道主要分享量化策略和因子研究，每周更新调仓建议。","time":"2026-05-15 09:00","type":"text"},
            {"id":2,"sender":"kol","content":"[付费内容] 本周多因子模型调仓建议","time":"2026-05-19 20:00","type":"paid","price":50,"preview":"本周价值因子持续占优，动量因子衰减...（解锁查看完整内容）"},
        ],
    }
    return conversations.get(kol_id, [
        {"id":1,"sender":"kol","content":"欢迎关注！有投研问题随时交流。","time":"2026-05-18 09:00","type":"text"},
    ])

def gen_kol_workbench():
    return {
        "kol_name": "财经老王",
        "kol_avatar": "👑",
        "tier": "S级合伙人",
        "stats": {
            "total_followers": 2800000,
            "vip_subscribers": 4200,
            "monthly_revenue": 186000,
            "revenue_change": 12.5,
            "unread_messages": 23,
            "pending_replies": 8,
            "today_views": 12800,
            "engagement_rate": 4.2,
        },
        "recent_fans": [
            {"name":"投研达人_小陈","time":"5分钟前","msg":"老王好！AI算力还能追吗？","tier":"专业会员"},
            {"name":"价值猎人小林","time":"23分钟前","msg":"请问港股互联网怎么看？","tier":"基础会员"},
            {"name":"量化新手_阿明","time":"1小时前","msg":"想学习多因子模型，有推荐吗？","tier":"免费用户"},
            {"name":"机构用户_张总","time":"2小时前","msg":"能否安排一次闭门交流？","tier":"机构VIP"},
            {"name":"小白投资者","time":"3小时前","msg":"新能源板块现在能入吗？","tier":"基础会员"},
        ],
        "broadcast_history": [
            {"id":1,"content":"本周策略更新：科技板块逢低布局，AI算力+国产替代双主线","time":"2026-05-20 08:00","reach":3200,"open_rate":68},
            {"id":2,"content":"紧急提醒：美联储会议纪要偏鸽，短期利好风险资产","time":"2026-05-19 22:30","reach":4100,"open_rate":82},
            {"id":3,"content":"周末复盘：本周操作回顾与下周展望","time":"2026-05-18 18:00","reach":2800,"open_rate":55},
        ],
    }

@app.route("/api/dm/conversations")
def api_dm_conversations():
    return jsonify(gen_dm_conversations())

@app.route("/api/dm/messages/<int:kol_id>")
def api_dm_messages(kol_id):
    return jsonify(gen_dm_messages(kol_id))

@app.route("/api/dm/send", methods=["POST"])
def api_dm_send():
    kol_id = request.json.get("kol_id")
    content = request.json.get("content", "")
    history = request.json.get("history", [])
    # 大V 角色画像 + 上下文感知（合规：用"关注/参考/可考虑"措辞，不出现"买/卖/必涨/必跌"）
    KOL_PERSONA = {
        1: {"name":"财经老王","style":"宏观+科技，偏稳健","focus":["AI算力","半导体","美联储","降息"]},
        2: {"name":"投资女神Lisa","style":"港股+互联网，价值派","focus":["港股","互联网","南向资金","平台经济"]},
        3: {"name":"量化老师陈明","style":"量化+因子，数据驱动","focus":["因子","量化","回测","动量","价值"]},
        4: {"name":"全球宏观James","style":"宏观+大宗，海外视角","focus":["美联储","美元","黄金","大宗"]},
        5: {"name":"新能源猎手阿强","style":"产业链调研，新能源","focus":["新能源","固态电池","锂电","光伏"]},
    }
    persona = KOL_PERSONA.get(kol_id, KOL_PERSONA[1])
    text = content.lower()
    turn = len(history) + 1

    # 关键词触发的多轮回复（每个大V不同风格）
    def reply_for(kw_match):
        base = persona["name"]
        if "买" in content or "卖" in content or "推荐" in content or "代码" in content:
            return f"我只能基于公开数据分享研究观点，无法给具体买卖建议哦。你可以参考冈底斯Hermes的「AI资产配置」做组合规划，或在「AI行情预判」看历史区间和模型推演的概率分布，结合自己的风险偏好判断。"
        if "新能源" in text or "电池" in text or "锂" in text:
            if kol_id == 5:
                return f"我刚跑完一轮产业链调研：固态电池量产时间表略有提前迹象，中游材料端景气度在恢复。可以关注以下三个维度：①电解质技术路线分化 ②碳酸锂价格底部信号 ③海外工厂投产节奏。具体标的我不点名，避免合规风险，你可以用Hermes的量化因子筛选自己跑一下。"
            return f"新能源这条线我不是最强的，建议直接看新能源猎手阿强的频道，他的产业链调研做得很扎实。从宏观角度，当下新能源板块处于估值修复阶段，可以适度关注。"
        if "港股" in text or "互联网" in text or "恒生" in text:
            if kol_id == 2:
                return f"港股互联网这波我跟得比较紧。当前估值大约在历史20-25%分位，南向资金已经连续14个交易日净买入。但要注意两点：①Q2财报季验证基本面 ②美联储路径不确定性。我个人会把仓位控制在标配+5%以内，分批操作。"
            return f"港股不是我的主战场，建议看Lisa的频道。从大方向看，估值确实有修复空间，但短期波动会比较大，注意控制仓位。"
        if "ai" in text or "算力" in text or "科技" in text or "芯片" in text:
            if kol_id == 1:
                return f"AI算力短期确实热，但要拆开看：①云厂商资本开支节奏 ②国产替代订单兑现度 ③估值消化空间。我现在是逢回调关注，不追高。具体节奏，可以参考Hermes里高盛和中金最新的研报精读，我也是基于这些证据做判断的。"
            return f"科技板块我会更多看宏观资金面和外资流向，不做个股推荐。可以参考一下大V老王的频道，他对这条线跟得更细。"
        if "宏观" in text or "美联储" in text or "降息" in text or "美元" in text:
            if kol_id == 4:
                return f"美联储这边我跟最紧：CME利率期货显示年内降息2次概率68%，鲍威尔最近讲话偏鸽。美元指数承压，对应：①新兴市场股票偏好上升 ②黄金中长期支撑 ③大宗商品反弹。这些只是大类资产框架，不是具体建议哈。"
            return f"宏观层面，降息预期升温对风险资产是利好，但要警惕预期透支后的回吐。建议看James的频道，他对海外宏观跟得更深。"
        if "量化" in text or "因子" in text:
            if kol_id == 3:
                return f"我跑了最新一轮多因子回测：价值因子最近4周相对动量因子超额+3.2%，建议把组合往价值方向调一调。这只是因子层面的判断，不构成个股推荐。你可以在Hermes里用「量化因子筛选」自己跑一遍。"
            return f"量化的事建议找陈明老师，他这块比我专业。"
        if turn <= 2:
            return f"你这个问题挺好。我先简单回应：基于我最近跟踪的数据（{('、'.join(persona['focus'][:2]))}方向），目前的情况是结构性机会大于系统性机会。要不你具体说说你的关注点？是想看赛道、还是想做资产配置？"
        if turn <= 4:
            return f"明白。我补充一下数据视角：冈底斯平台最近的研报数据库里，{persona['focus'][0]}相关研报量周环比+12%，机构关注度在抬升。但研报关注≠股价上涨，仅作信号参考。你的仓位结构是怎样的？我可以帮你从大方向上看一下平衡性。"
        return f"咱们聊了几轮，我建议你这样做：①用Hermes的「AI资产配置」生成一份组合参考 ②用「AI行情预判」看一下你关注标的的历史走势区间 ③有具体观点了，再回来跟我对一对。最终决策一定是你自己做，我们这边只能给数据和研究框架。"

    reply = reply_for(content)
    return jsonify({
        "success": True,
        "kol_id": kol_id,
        "msg_id": random.randint(100,999),
        "auto_reply": reply,
        "disclaimer": "以上为大V个人研究观点，仅供参考，不构成投资建议",
        "turn": turn,
    })

@app.route("/api/ai/allocation", methods=["POST"])
def api_ai_allocation():
    risk = request.json.get("risk", "稳健")
    horizon = request.json.get("horizon", "中期(6-12月)")
    # 合规：给区间不给单点，标注模型来源
    PROFILES = {
        "保守": {
            "alloc":[{"name":"股票","ratio":20,"range":"15-25%","color":"#E74C3C"},
                     {"name":"债券","ratio":50,"range":"45-55%","color":"#3498DB"},
                     {"name":"黄金","ratio":15,"range":"10-20%","color":"#F39C12"},
                     {"name":"现金","ratio":15,"range":"10-20%","color":"#9A9590"}],
            "expected_return":"3-5%/年(回测区间)","max_drawdown":"-5% ~ -8%",
            "rebalance":"季度再平衡","sector":["高股息","公用事业","必需消费"]
        },
        "稳健": {
            "alloc":[{"name":"股票","ratio":45,"range":"40-50%","color":"#E74C3C"},
                     {"name":"债券","ratio":30,"range":"25-35%","color":"#3498DB"},
                     {"name":"黄金","ratio":10,"range":"5-15%","color":"#F39C12"},
                     {"name":"现金","ratio":15,"range":"10-20%","color":"#9A9590"}],
            "expected_return":"6-10%/年(回测区间)","max_drawdown":"-10% ~ -15%",
            "rebalance":"季度再平衡","sector":["科技","消费","医药","金融"]
        },
        "积极": {
            "alloc":[{"name":"股票","ratio":70,"range":"65-75%","color":"#E74C3C"},
                     {"name":"债券","ratio":10,"range":"5-15%","color":"#3498DB"},
                     {"name":"黄金","ratio":10,"range":"5-15%","color":"#F39C12"},
                     {"name":"现金","ratio":10,"range":"5-15%","color":"#9A9590"}],
            "expected_return":"10-18%/年(回测区间)","max_drawdown":"-18% ~ -25%",
            "rebalance":"月度再平衡","sector":["科技成长","新能源","半导体","港股互联网"]
        },
        "激进": {
            "alloc":[{"name":"股票","ratio":85,"range":"80-90%","color":"#E74C3C"},
                     {"name":"债券","ratio":0,"range":"0-5%","color":"#3498DB"},
                     {"name":"黄金","ratio":5,"range":"0-10%","color":"#F39C12"},
                     {"name":"现金","ratio":10,"range":"5-15%","color":"#9A9590"}],
            "expected_return":"15-30%/年(回测区间)","max_drawdown":"-30% ~ -45%",
            "rebalance":"月度再平衡","sector":["AI算力","固态电池","创新药","小盘成长"]
        },
    }
    p = PROFILES.get(risk, PROFILES["稳健"])
    return jsonify({
        "risk": risk, "horizon": horizon,
        "allocation": p["alloc"],
        "expected_return": p["expected_return"],
        "max_drawdown": p["max_drawdown"],
        "rebalance": p["rebalance"],
        "sector_focus": p["sector"],
        "data_source": "基于冈底斯回测引擎(2015-2026)+ 多因子模型 + Black-Litterman 框架",
        "disclaimer": "本配置方案为模型推演结果，基于历史数据回测，不构成投资建议。市场有风险，实际收益可能与回测区间显著偏离。",
        "compute_used": 5,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })

@app.route("/api/ai/forecast", methods=["POST"])
def api_ai_forecast():
    """行情预判：历史可解读，未来仅区间不解读"""
    import math
    target = request.json.get("target", "上证指数")
    target_type = request.json.get("type", "大盘")
    # 30天历史 + 20天未来
    TARGETS = {
        "上证指数":     {"base":3428.56,"vol":0.012,"trend":0.0008},
        "沪深300":      {"base":3920.20,"vol":0.013,"trend":0.0007},
        "恒生指数":     {"base":23156.78,"vol":0.018,"trend":0.0012},
        "纳斯达克":     {"base":19234.56,"vol":0.015,"trend":0.0009},
        "贵州茅台":     {"base":1685.20,"vol":0.014,"trend":0.0004},
        "宁德时代":     {"base":248.50,"vol":0.022,"trend":0.0010},
        "中证白酒":     {"base":12450.30,"vol":0.016,"trend":-0.0003},
        "新能源ETF":    {"base":0.882,"vol":0.021,"trend":0.0008},
    }
    cfg = TARGETS.get(target, TARGETS["上证指数"])
    base, vol, trend = cfg["base"], cfg["vol"], cfg["trend"]
    random.seed(hash(target) & 0xFFFF)
    history = []
    price = base * (1 - trend*15)
    for i in range(30):
        price = price * (1 + trend + random.uniform(-vol, vol))
        history.append(round(price, 2))
    # 未来 20 天：三条带状区间 (看空/中性/看好)
    last = history[-1]
    bear = []
    base_line = []
    bull = []
    for i in range(1, 21):
        # 区间宽度随时间增大 (类似 fan chart)
        width = vol * math.sqrt(i) * 1.96
        center = last * (1 + trend * i)
        bear.append(round(center * (1 - width), 2))
        base_line.append(round(center, 2))
        bull.append(round(center * (1 + width), 2))
    # 历史可解读
    pct_30d = round((history[-1]/history[0]-1)*100, 2)
    high = max(history); low = min(history)
    history_commentary = [
        f"过去30个交易日累计涨跌：{('+' if pct_30d>=0 else '')}{pct_30d}%",
        f"区间高点 {high}（第{history.index(high)+1}个交易日），区间低点 {low}（第{history.index(low)+1}个交易日）",
        f"振幅 {round((high-low)/low*100,2)}%，{'波动较大' if vol>0.018 else '波动温和'}",
        f"近5日趋势：{'温和上行' if history[-1]>history[-6] else '温和回调'}，量能{'放大' if random.random()>0.5 else '收敛'}",
    ]
    # 相关性 (合规：仅展示数据，不解读)
    correlations = [
        {"name":"北向资金净流入","corr":round(random.uniform(0.4,0.78),2)},
        {"name":"美元指数(反向)","corr":round(-random.uniform(0.3,0.62),2)},
        {"name":"10Y国债收益率","corr":round(random.uniform(-0.4,0.35),2)},
        {"name":"VIX恐慌指数(反向)","corr":round(-random.uniform(0.5,0.75),2)},
        {"name":"原油价格","corr":round(random.uniform(-0.2,0.4),2)},
    ]
    return jsonify({
        "target": target,
        "type": target_type,
        "history": history,
        "forecast_bear": bear,
        "forecast_base": base_line,
        "forecast_bull": bull,
        "history_commentary": history_commentary,
        "forecast_disclaimer": "⚠️ 未来区间为模型基于历史波动率推演的概率分布，不构成方向判断和投资建议。实际走势受多重因素影响，可能显著偏离区间。",
        "correlations": correlations,
        "data_source": "冈底斯多因子模型 + 历史波动率Monte Carlo推演 + RAG数据库",
        "compute_used": 8,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    return jsonify(gen_kol_workbench())

@app.route("/api/kol/broadcast", methods=["POST"])
def api_kol_broadcast():
    content = request.json.get("content", "")
    target = request.json.get("target", "all")
    return jsonify({"success": True, "reach": random.randint(2000, 5000), "content": content, "target": target})

@app.route("/api/kol/reply", methods=["POST"])
def api_kol_reply():
    fan_name = request.json.get("fan_name", "")
    content = request.json.get("content", "")
    is_paid = request.json.get("is_paid", False)
    return jsonify({"success": True, "fan_name": fan_name, "is_paid": is_paid, "revenue": 50 if is_paid else 0})

@app.route("/prd")
def prd():
    return render_template("prd.html")

init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
