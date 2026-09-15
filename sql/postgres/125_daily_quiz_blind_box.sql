CREATE TABLE IF NOT EXISTS quiz_questions (
    id BIGSERIAL PRIMARY KEY,
    question_code TEXT NOT NULL UNIQUE,
    question_text TEXT NOT NULL,
    question_type TEXT NOT NULL DEFAULT 'single_choice',
    options_json TEXT NOT NULL DEFAULT '[]',
    correct_answer TEXT NOT NULL,
    explanation TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '基础知识',
    difficulty TEXT NOT NULL DEFAULT '基础',
    source TEXT NOT NULL DEFAULT 'curated_question_bank_v1',
    review_status TEXT NOT NULL DEFAULT 'approved',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quiz_questions_active_category ON quiz_questions(is_active, category, difficulty);

CREATE TABLE IF NOT EXISTS daily_quiz_sets (
    id BIGSERIAL PRIMARY KEY,
    quiz_date TEXT NOT NULL,
    question_id BIGINT NOT NULL REFERENCES quiz_questions(id),
    display_order INTEGER NOT NULL,
    selection_seed TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (quiz_date, display_order),
    UNIQUE (quiz_date, question_id)
);
CREATE INDEX IF NOT EXISTS idx_daily_quiz_sets_date ON daily_quiz_sets(quiz_date, display_order);

CREATE TABLE IF NOT EXISTS user_quiz_attempts (
    id BIGSERIAL PRIMARY KEY,
    tenant_slug TEXT NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users(id),
    quiz_date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    total_count INTEGER NOT NULL DEFAULT 5,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    UNIQUE (user_id, quiz_date)
);
CREATE INDEX IF NOT EXISTS idx_user_quiz_attempts_tenant_date ON user_quiz_attempts(tenant_slug, quiz_date, completed_at);

CREATE TABLE IF NOT EXISTS user_quiz_answers (
    id BIGSERIAL PRIMARY KEY,
    attempt_id BIGINT NOT NULL REFERENCES user_quiz_attempts(id) ON DELETE CASCADE,
    question_id BIGINT NOT NULL REFERENCES quiz_questions(id),
    selected_answer TEXT NOT NULL DEFAULT '',
    correct_answer_snapshot TEXT NOT NULL,
    is_correct INTEGER NOT NULL DEFAULT 0,
    answered_at TEXT NOT NULL,
    UNIQUE (attempt_id, question_id)
);
CREATE INDEX IF NOT EXISTS idx_user_quiz_answers_attempt ON user_quiz_answers(attempt_id);
