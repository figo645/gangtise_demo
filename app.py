from flask import Flask, render_template, jsonify, request
import random
from datetime import datetime, timedelta

app = Flask(__name__)

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

# Routes
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
    return render_template("admin.html", kols=kols, segments=segments)

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
    return jsonify({"success": True, "kol_id": kol_id, "msg_id": random.randint(100,999), "auto_reply": "感谢您的消息！我会尽快回复。如果是紧急问题，可以在我的直播间提问哦～"})

@app.route("/api/kol/workbench")
def api_kol_workbench():
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

if __name__ == "__main__":
    app.run(debug=True, port=5000)
