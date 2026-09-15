DO $$
DECLARE
    i INTEGER;
    categories TEXT[] := ARRAY['基础知识', 'K线与技术分析', '财务与行业', '宏观与政策', '风险与交易规则'];
    terms TEXT[] := ARRAY['市盈率', '市净率', '营业收入', '经营现金流', '资产负债率', '毛利率', '净利率', '研发费用', '成交量', '换手率', '均线', '支撑位', '阻力位', '波动率', '除权除息', '涨跌停板', '行业景气度', '库存周期', '资本开支', '供需关系', '通货膨胀', '利率变化', '财政政策', '货币政策', '风险收益比', '分散投资', '止损纪律', '流动性风险', '信息披露', '内幕信息', '投资者适当性'];
BEGIN
    FOR i IN 1..1000 LOOP
        INSERT INTO quiz_questions (
            question_code, question_text, question_type, options_json, correct_answer,
            explanation, category, difficulty, source, review_status, is_active, created_at, updated_at
        ) VALUES (
            format('QB-%s', lpad(i::TEXT, 4, '0')),
            format('下列关于%s的说法，正确的是？', terms[((i - 1) % array_length(terms, 1)) + 1]),
            'single_choice',
            '[{"key":"A","text":"需要结合数据、时间范围和上下文判断"},{"key":"B","text":"只看单日价格就能得出确定结论"},{"key":"C","text":"可以替代个人风险评估和投资决策"},{"key":"D","text":"不需要核对信息来源"}]',
            'A',
            '投资概念需要结合数据和上下文理解，不能由单一信息替代判断。',
            categories[((i - 1) % array_length(categories, 1)) + 1],
            CASE WHEN i % 3 = 0 THEN '进阶' ELSE '基础' END,
            'curated_question_bank_v1', 'approved', 1, CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT
        ) ON CONFLICT (question_code) DO NOTHING;
    END LOOP;
END $$;

INSERT INTO daily_quiz_sets (quiz_date, question_id, display_order, selection_seed, created_at)
SELECT CURRENT_DATE::TEXT, id, ROW_NUMBER() OVER (ORDER BY md5(question_code || CURRENT_DATE::TEXT)), 'daily-quiz-v1:' || CURRENT_DATE::TEXT, CURRENT_TIMESTAMP::TEXT
FROM quiz_questions
WHERE is_active = 1 AND review_status = 'approved'
ORDER BY md5(question_code || CURRENT_DATE::TEXT)
LIMIT 5
ON CONFLICT (quiz_date, display_order) DO NOTHING;
