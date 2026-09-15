"""BDD contract tests for the database-backed quiz blind box."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_schema_defines_persistent_question_and_attempt_tables():
    sql = (ROOT / "sql/postgres/125_daily_quiz_blind_box.sql").read_text(encoding="utf-8")
    for table in ("quiz_questions", "daily_quiz_sets", "user_quiz_attempts", "user_quiz_answers"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "UNIQUE (user_id, quiz_date)" in sql
    assert "REFERENCES users(id)" in sql


def test_question_bank_is_1000_item_idempotent_and_does_not_call_llm():
    source = (ROOT / "src/domain/quiz_services.py").read_text(encoding="utf-8")
    assert "QUESTION_BANK_SIZE = 1000" in source
    assert "ON CONFLICT(question_code) DO NOTHING" in source
    assert "curated_question_bank_v1" in source
    assert "call_openai" not in source.lower()
    assert "localStorage" not in source


def test_daily_set_is_shared_and_excludes_recent_dates_where_possible():
    source = (ROOT / "src/domain/quiz_services.py").read_text(encoding="utf-8")
    assert "daily-quiz-v1:{quiz_date}" in source
    assert "range(1, 8)" in source
    assert "DAILY_QUIZ_SIZE = 5" in source


def test_answer_endpoint_does_not_expose_answers_before_submit():
    source = (ROOT / "src/domain/quiz_services.py").read_text(encoding="utf-8")
    assert "_question_dict(row)" in source
    assert "_question_dict(row, True)" in source
    assert "correct_answer_snapshot" in source


def test_admin_task_and_both_surfaces_use_same_api_component():
    task_source = (ROOT / "src/domain/market_services.py").read_text(encoding="utf-8")
    assert '"task_code": "daily_quiz_set_prepare"' in task_source
    assert '"schedule_value": "08:00"' in task_source
    for template in ("templates/h5.html", "templates/tenant_portal.html"):
        source = (ROOT / template).read_text(encoding="utf-8")
        assert "/static/js/quiz_blind_box.js" in source
        assert 'data-quiz-open' in source
        assert 'id="quiz-blind-box-modal"' in source
        assert '🎁' in source
        assert '>盲盒</span>' in source
    css = (ROOT / "static/css/quiz_blind_box.css").read_text(encoding="utf-8")
    assert "left:calc(50% + min(162.5px, 41.6667vw))" in css
    assert "right:auto" in css


def test_kol_workbench_has_stats_but_no_floating_blind_box_marker():
    source = (ROOT / "templates/kol_workbench.html").read_text(encoding="utf-8")
    assert "kw-quiz-stats-card" in source
    assert "api/kol/quiz/stats" in source
    assert 'data-quiz-open' not in source
    assert "quiz_blind_box.css" not in source


def test_stats_distinguish_opened_and_completed_attempts():
    source = (ROOT / "src/domain/quiz_services.py").read_text(encoding="utf-8")
    assert "AS opens" in source
    assert "AS completed" in source
    assert "completion_rate" in source


def test_question_bank_uses_domain_specific_distractors_and_rotates_correct_key():
    source = (ROOT / "src/domain/quiz_services.py").read_text(encoding="utf-8")
    migration = (ROOT / "sql/postgres/128_refresh_quiz_question_options.sql").read_text(encoding="utf-8")
    assert "财务质量、行业位置和现金流" in source
    assert "政策影响的对象、时间和传导路径" in source
    assert "jsonb_build_object('key','A'" in migration
    assert "correct_key" in migration
    assert "category_name" in migration


def test_completed_users_can_start_multiple_persisted_attempts_per_day():
    schema = (ROOT / "sql/postgres/129_allow_quiz_retries.sql").read_text(encoding="utf-8")
    source = (ROOT / "src/domain/quiz_services.py").read_text(encoding="utf-8")
    client = (ROOT / "static/js/quiz_blind_box.js").read_text(encoding="utf-8")
    assert "attempt_no" in schema
    assert "uq_user_quiz_attempts_user_date_no" in schema
    assert "MAX(attempt_no)" in source
    assert "data-quiz-retry" in client
    assert "attempt_id:payload.attempt" in client


def test_interaction_observation_renders_quiz_statistics():
    source = (ROOT / "templates/kol_workbench.html").read_text(encoding="utf-8")
    assert "答题盲盒互动" in source
    assert "kw-watch-quiz-stats" in source
    assert "loadKwInteractionQuizStats" in source
    assert "kw-watch-quiz-chart" in source
    assert "题型得分与失分分布" in source
    assert "kw-watch-quiz-category-chart" in source
    assert "category_breakdown" in source
    assert "window.GangtiseEcharts.render" in source


def test_quiz_stats_uses_valid_postgres_filtered_average_expression():
    source = (ROOT / "src/domain/quiz_services.py").read_text(encoding="utf-8")
    assert "(AVG(score) FILTER (WHERE completed_at <> ''))::double precision" in source
