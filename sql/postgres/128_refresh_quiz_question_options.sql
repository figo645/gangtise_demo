DO $$
DECLARE
    i INTEGER;
    category_index INTEGER;
    correct_index INTEGER;
    category_name TEXT;
    term TEXT;
    new_question_text TEXT;
    correct_text TEXT;
    d1 TEXT;
    d2 TEXT;
    d3 TEXT;
    correct_key TEXT;
    option_json TEXT;
BEGIN
    FOR i IN 1..1000 LOOP
        category_index := ((i - 1) % 5) + 1;
        correct_index := (i - 1) % 4;
        category_name := (ARRAY['基础知识', 'K线与技术分析', '财务与行业', '宏观与政策', '风险与交易规则'])[category_index];
        term := (ARRAY['市盈率', '市净率', '营业收入', '经营现金流', '资产负债率', '毛利率', '净利率', '研发费用', '成交量', '换手率', '均线', '支撑位', '阻力位', '波动率', '除权除息', '涨跌停板', '行业景气度', '库存周期', '资本开支', '供需关系', '通货膨胀', '利率变化', '财政政策', '货币政策', '风险收益比', '分散投资', '止损纪律', '流动性风险', '信息披露', '内幕信息', '投资者适当性'])[((i - 1) % 31) + 1];
        IF category_index = 1 THEN
            new_question_text := format('关于%s，哪项做法更符合基础知识的审慎理解？', term);
            correct_text := '先明确指标定义和计算口径'; d1 := '把任何高数值都当成绝对利好'; d2 := '只根据股票名称判断价值'; d3 := '忽略数据的时间范围';
        ELSIF category_index = 2 THEN
            new_question_text := format('分析%s的技术信号时，哪项做法更合理？', term);
            correct_text := '结合价格、成交量和观察周期'; d1 := '只看一根 K 线预测未来走势'; d2 := '用技术图形替代公司基本面'; d3 := '认为指标信号没有失效可能';
        ELSIF category_index = 3 THEN
            new_question_text := format('研究%s时，哪项做法更接近财务与行业分析？', term);
            correct_text := '结合财务质量、行业位置和现金流'; d1 := '只看收入增速不看利润质量'; d2 := '把行业平均值当成个股结论'; d3 := '忽略负债和资本开支';
        ELSIF category_index = 4 THEN
            new_question_text := format('面对%s相关宏观或政策信息，哪项分析更稳妥？', term);
            correct_text := '分析政策影响的对象、时间和传导路径'; d1 := '政策发布后所有股票都会同向上涨'; d2 := '只看标题不看政策正文'; d3 := '忽略政策执行和预期差异';
        ELSE
            new_question_text := format('涉及%s时，哪项做法更符合风险管理原则？', term);
            correct_text := '先核实信息并评估自身风险承受能力'; d1 := '用全部资金追逐单一热点'; d2 := '把问答结果当作具体买卖指令'; d3 := '认为历史收益可以保证未来收益';
        END IF;
        correct_key := (ARRAY['A', 'B', 'C', 'D'])[correct_index + 1];
        option_json := CASE correct_index
            WHEN 0 THEN jsonb_build_array(jsonb_build_object('key','A','text',correct_text), jsonb_build_object('key','B','text',d1), jsonb_build_object('key','C','text',d2), jsonb_build_object('key','D','text',d3))::TEXT
            WHEN 1 THEN jsonb_build_array(jsonb_build_object('key','A','text',d1), jsonb_build_object('key','B','text',correct_text), jsonb_build_object('key','C','text',d2), jsonb_build_object('key','D','text',d3))::TEXT
            WHEN 2 THEN jsonb_build_array(jsonb_build_object('key','A','text',d1), jsonb_build_object('key','B','text',d2), jsonb_build_object('key','C','text',correct_text), jsonb_build_object('key','D','text',d3))::TEXT
            ELSE jsonb_build_array(jsonb_build_object('key','A','text',d1), jsonb_build_object('key','B','text',d2), jsonb_build_object('key','C','text',d3), jsonb_build_object('key','D','text',correct_text))::TEXT
        END;
        UPDATE quiz_questions SET question_text=new_question_text, options_json=option_json, correct_answer=correct_key, explanation='正确选项强调了该类信息的分析口径；其余选项属于常见的过度简化或风险误判。', category=category_name, updated_at=CURRENT_TIMESTAMP::TEXT WHERE question_code=format('QB-%s', lpad(i::TEXT, 4, '0'));
    END LOOP;
END $$;
