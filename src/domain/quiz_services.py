"""Database-backed daily quiz blind box services."""

import json
import random
from datetime import date, datetime, timedelta

from src.domain.core_services import get_db

QUESTION_BANK_SIZE = 1000
DAILY_QUIZ_SIZE = 5

_FAMILIES = [
    ("基础知识", "下列关于{term}的说法，正确的是？", "投资概念需要结合数据和上下文理解，不能由单一信息替代判断。"),
    ("K线与技术分析", "在不考虑其他信息时，{term}通常表示什么？", "技术指标需要结合周期、成交量和基本面综合判断。"),
    ("财务与行业", "分析{term}时，投资者通常应重点关注什么？", "单一指标不能代表企业全部经营情况，应结合财务质量和行业环境。"),
    ("宏观与政策", "关于{term}，下列哪项更符合审慎研究原则？", "宏观信息需要核对发布时间、影响范围和传导路径。"),
    ("风险与交易规则", "面对{term}相关信息，较稳妥的做法是？", "先核实信息和自身风险承受能力，不把知识问答当作买卖建议。"),
]
_TERMS = [
    "市盈率", "市净率", "营业收入", "经营现金流", "资产负债率", "毛利率", "净利率", "研发费用",
    "成交量", "换手率", "均线", "支撑位", "阻力位", "波动率", "除权除息", "涨跌停板",
    "行业景气度", "库存周期", "资本开支", "供需关系", "通货膨胀", "利率变化", "财政政策", "货币政策",
    "风险收益比", "分散投资", "止损纪律", "流动性风险", "信息披露", "内幕信息", "投资者适当性",
]


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _options(index):
    category = _FAMILIES[index % len(_FAMILIES)][0]
    choices = {
        "基础知识": ["先明确指标定义和计算口径", "把任何高数值都当成绝对利好", "只根据股票名称判断价值", "忽略数据的时间范围"],
        "K线与技术分析": ["结合价格、成交量和观察周期", "只看一根 K 线预测未来走势", "用技术图形替代公司基本面", "认为指标信号没有失效可能"],
        "财务与行业": ["结合财务质量、行业位置和现金流", "只看收入增速不看利润质量", "把行业平均值当成个股结论", "忽略负债和资本开支"],
        "宏观与政策": ["分析政策影响的对象、时间和传导路径", "政策发布后所有股票都会同向上涨", "只看标题不看政策正文", "忽略政策执行和预期差异"],
        "风险与交易规则": ["先核实信息并评估自身风险承受能力", "用全部资金追逐单一热点", "把问答结果当作具体买卖指令", "认为历史收益可以保证未来收益"],
    }[category]
    correct_index = index % 4
    rotated = [{"key": key, "text": choices[(position - correct_index) % 4]} for position, key in enumerate("ABCD")]
    return rotated, "ABCD"[correct_index]


def seed_quiz_question_bank(target=QUESTION_BANK_SIZE):
    db = get_db()
    row = db.execute("SELECT COUNT(*) AS count FROM quiz_questions WHERE is_active = 1").fetchone()
    current = int((dict(row or {}).get("count") or 0))
    inserted = 0
    for index in range(current, int(target)):
        category, template, explanation = _FAMILIES[index % len(_FAMILIES)]
        options, correct = _options(index)
        now = _now()
        db.execute(
            """INSERT INTO quiz_questions
            (question_code, question_text, question_type, options_json, correct_answer, explanation,
             category, difficulty, source, review_status, is_active, created_at, updated_at)
            VALUES (?, ?, 'single_choice', ?, ?, ?, ?, ?, 'curated_question_bank_v1', 'approved', 1, ?, ?)
            ON CONFLICT(question_code) DO NOTHING""",
            (f"QB-{index + 1:04d}", template.format(term=_TERMS[index % len(_TERMS)]),
             json.dumps(options, ensure_ascii=False), correct, explanation, category,
             "基础" if index % 3 else "进阶", now, now),
        )
        inserted += 1
    db.commit()
    return {"target": int(target), "existing": current, "inserted": inserted, "total": max(current, int(target))}


def _question_dict(row, include_answer=False):
    item = dict(row)
    payload = {"id": int(item["id"]), "question_code": item["question_code"], "question_text": item["question_text"],
               "question_type": item["question_type"], "options": json.loads(item.get("options_json") or "[]"),
               "category": item["category"], "difficulty": item["difficulty"]}
    if include_answer:
        payload.update({"correct_answer": item["correct_answer"], "explanation": item["explanation"]})
    return payload


def get_or_create_daily_quiz_set(quiz_date=None, count=DAILY_QUIZ_SIZE):
    quiz_date = quiz_date or date.today().isoformat()
    db = get_db()
    rows = db.execute("SELECT q.* FROM daily_quiz_sets s JOIN quiz_questions q ON q.id=s.question_id WHERE s.quiz_date=? ORDER BY s.display_order", (quiz_date,)).fetchall()
    if len(rows) == count:
        return [_question_dict(row) for row in rows]
    seed_quiz_question_bank()
    rng = random.Random(f"daily-quiz-v1:{quiz_date}")
    candidates = list(db.execute("SELECT * FROM quiz_questions WHERE is_active=1 AND review_status='approved' ORDER BY id").fetchall())
    recent_dates = [(date.fromisoformat(quiz_date) - timedelta(days=i)).isoformat() for i in range(1, 8)]
    recent = db.execute("SELECT question_id FROM daily_quiz_sets WHERE quiz_date IN ({})".format(",".join("?" * len(recent_dates))), tuple(recent_dates)).fetchall()
    recent_ids = {int(item["question_id"]) for item in recent}
    fresh = [row for row in candidates if int(row["id"]) not in recent_ids]
    rng.shuffle(fresh)
    selected = (fresh + candidates)[:count]
    if len(selected) < count:
        raise RuntimeError("quiz_question_bank_insufficient")
    db.execute("DELETE FROM daily_quiz_sets WHERE quiz_date=?", (quiz_date,))
    for order, row in enumerate(selected, 1):
        db.execute("INSERT INTO daily_quiz_sets (quiz_date, question_id, display_order, selection_seed, created_at) VALUES (?, ?, ?, ?, ?)", (quiz_date, row["id"], order, f"daily-quiz-v1:{quiz_date}", _now()))
    db.commit()
    return [_question_dict(row) for row in selected]


def get_daily_quiz_payload(user, tenant_slug):
    quiz_date = date.today().isoformat()
    questions = get_or_create_daily_quiz_set(quiz_date)
    attempt = get_db().execute("SELECT id, attempt_no, started_at, completed_at, score, correct_count, total_count FROM user_quiz_attempts WHERE user_id=? AND quiz_date=? ORDER BY attempt_no DESC LIMIT 1", (int(user["id"]), quiz_date)).fetchone()
    return {"quiz_date": quiz_date, "total": len(questions), "questions": questions, "attempt": dict(attempt) if attempt else None, "tenant_slug": tenant_slug}


def start_quiz_attempt(user, tenant_slug, quiz_date):
    db = get_db()
    existing = db.execute("SELECT * FROM user_quiz_attempts WHERE user_id=? AND quiz_date=? AND completed_at='' ORDER BY attempt_no DESC LIMIT 1", (int(user["id"]), quiz_date)).fetchone()
    if existing:
        return dict(existing)
    latest = db.execute("SELECT COALESCE(MAX(attempt_no), 0) AS attempt_no FROM user_quiz_attempts WHERE user_id=? AND quiz_date=?", (int(user["id"]), quiz_date)).fetchone()
    attempt_no = int((dict(latest or {}).get("attempt_no") or 0)) + 1
    db.execute("INSERT INTO user_quiz_attempts (tenant_slug, user_id, quiz_date, attempt_no, started_at, total_count) VALUES (?, ?, ?, ?, ?, ?)", (tenant_slug, int(user["id"]), quiz_date, attempt_no, _now(), DAILY_QUIZ_SIZE))
    db.commit()
    return dict(db.execute("SELECT * FROM user_quiz_attempts WHERE user_id=? AND quiz_date=? AND attempt_no=?", (int(user["id"]), quiz_date, attempt_no)).fetchone())


def submit_quiz_attempt(user, tenant_slug, quiz_date, answers, attempt_id=None):
    db = get_db()
    attempt = dict(db.execute("SELECT * FROM user_quiz_attempts WHERE id=? AND user_id=? AND quiz_date=?", (attempt_id, int(user["id"]), quiz_date)).fetchone() or {}) if attempt_id else start_quiz_attempt(user, tenant_slug, quiz_date)
    if not attempt:
        raise ValueError("quiz_attempt_not_found")
    if attempt.get("completed_at"):
        return build_quiz_result(db, attempt["id"])
    rows = db.execute("SELECT q.* FROM daily_quiz_sets s JOIN quiz_questions q ON q.id=s.question_id WHERE s.quiz_date=? ORDER BY s.display_order", (quiz_date,)).fetchall()
    answer_map = answers if isinstance(answers, dict) else {}
    correct_count = 0
    for row in rows:
        selected = str(answer_map.get(str(row["id"])) or answer_map.get(row["question_code"]) or "").strip().upper()
        correct = int(selected == str(row["correct_answer"]).upper())
        correct_count += correct
        db.execute("INSERT INTO user_quiz_answers (attempt_id, question_id, selected_answer, correct_answer_snapshot, is_correct, answered_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(attempt_id, question_id) DO NOTHING", (attempt["id"], row["id"], selected, row["correct_answer"], correct, _now()))
    db.execute("UPDATE user_quiz_attempts SET completed_at=?, score=?, correct_count=?, total_count=? WHERE id=?", (_now(), correct_count * 20, correct_count, len(rows), attempt["id"]))
    db.commit()
    return build_quiz_result(db, attempt["id"])


def build_quiz_result(db, attempt_id):
    attempt = dict(db.execute("SELECT * FROM user_quiz_attempts WHERE id=?", (attempt_id,)).fetchone())
    rows = db.execute("SELECT q.*, a.selected_answer, a.is_correct FROM user_quiz_answers a JOIN quiz_questions q ON q.id=a.question_id WHERE a.attempt_id=? ORDER BY q.id", (attempt_id,)).fetchall()
    return {"attempt": attempt, "answers": [{**_question_dict(row, True), "selected_answer": row["selected_answer"], "is_correct": bool(row["is_correct"])} for row in rows]}


def build_quiz_admin_stats(tenant_slug=None, days=30):
    db = get_db()
    where = "WHERE quiz_date >= ?"
    params = [(date.today() - timedelta(days=int(days))).isoformat()]
    if tenant_slug:
        where += " AND tenant_slug=?"
        params.append(tenant_slug)
    row = db.execute(f"SELECT COUNT(*) AS opens, COUNT(*) FILTER (WHERE completed_at <> '') AS completed, (AVG(score) FILTER (WHERE completed_at <> ''))::double precision AS average_score, COALESCE(SUM(correct_count), 0) AS correct, COALESCE(SUM(total_count) FILTER (WHERE completed_at <> ''), 0) AS total FROM user_quiz_attempts {where}", tuple(params)).fetchone()
    stats = dict(row or {})
    opens = int(stats.get("opens") or 0)
    stats["completion_rate"] = round((int(stats.get("completed") or 0) / opens) * 100, 1) if opens else 0
    category_rows = db.execute(
        f"""SELECT q.category, COUNT(*) AS answered, SUM(a.is_correct) AS correct
        FROM user_quiz_answers a
        JOIN user_quiz_attempts ua ON ua.id = a.attempt_id
        JOIN quiz_questions q ON q.id = a.question_id
        {where} AND ua.completed_at <> ''
        GROUP BY q.category ORDER BY (COUNT(*) - COALESCE(SUM(a.is_correct), 0)) DESC, q.category""",
        tuple(params),
    ).fetchall()
    stats["category_breakdown"] = []
    for category_row in category_rows:
        category = dict(category_row)
        answered = int(category.get("answered") or 0)
        correct = int(category.get("correct") or 0)
        stats["category_breakdown"].append({
            "category": category.get("category") or "未分类",
            "answered": answered,
            "correct": correct,
            "wrong": max(answered - correct, 0),
            "accuracy": round((correct / answered) * 100, 1) if answered else 0,
        })
    return stats


def prepare_daily_quiz_set(force=False):
    bank = seed_quiz_question_bank()
    questions = get_or_create_daily_quiz_set()
    return {"question_bank": bank, "daily_count": len(questions), "quiz_date": date.today().isoformat(), "source": "database_question_bank"}
