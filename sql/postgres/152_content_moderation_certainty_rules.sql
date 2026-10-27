-- Deterministic upside promises must remain visible in the admin rule catalog.
-- The moderation service also enforces the R6 combination as a safety fallback.
INSERT INTO content_moderation_keywords (keyword, category, risk_level, description)
VALUES
    ('肯定涨', '收益承诺', 'high', '以确定性语气承诺证券价格上涨'),
    ('肯定上涨', '收益承诺', 'high', '以确定性语气承诺证券价格上涨'),
    ('一定涨', '收益承诺', 'high', '以确定性语气承诺证券价格上涨'),
    ('一定上涨', '收益承诺', 'high', '以确定性语气承诺证券价格上涨'),
    ('必然上涨', '收益承诺', 'high', '以确定性语气承诺证券价格上涨'),
    ('稳涨', '收益承诺', 'high', '暗示证券价格确定上涨'),
    ('只涨不跌', '收益承诺', 'high', '否定证券投资下跌风险'),
    ('绝不下跌', '收益承诺', 'high', '否定证券投资下跌风险')
ON CONFLICT (keyword) DO NOTHING;
