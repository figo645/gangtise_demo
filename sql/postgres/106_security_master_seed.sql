-- Initial security identity catalog. This is master data, not quote data.
-- Gangtise search results are upserted into the same table when new names or
-- codes are searched.

INSERT INTO security_master
    (security_code, stock_code, name, market, industry, security_type,
     search_aliases, source, is_active, created_at, updated_at)
VALUES
    ('600519.SH', '600519', '贵州茅台', 'SH', '高端白酒', 'stock', '', 'gangtise_openapi', 1, CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT),
    ('300750.SZ', '300750', '宁德时代', 'SZ', '动力电池', 'stock', '', 'gangtise_openapi', 1, CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT),
    ('00700.HK', '00700', '腾讯控股', 'HK', '港股互联网', 'stock', '', 'gangtise_openapi', 1, CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT),
    ('688981.SH', '688981', '中芯国际', 'SH', '半导体制造', 'stock', '', 'gangtise_openapi', 1, CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT),
    ('600036.SH', '600036', '招商银行', 'SH', '银行', 'stock', '', 'gangtise_openapi', 1, CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT),
    ('601988.SH', '601988', '中国银行', 'SH', '银行', 'stock', '', 'gangtise_openapi', 1, CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT),
    ('601939.SH', '601939', '建设银行', 'SH', '银行', 'stock', '', 'gangtise_openapi', 1, CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT),
    ('003015.SZ', '003015', '日久光电', 'SZ', '消费电子材料', 'stock', '日久光新', 'gangtise_openapi', 1, CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT)
ON CONFLICT (security_code) DO UPDATE SET
    stock_code = EXCLUDED.stock_code,
    name = EXCLUDED.name,
    market = EXCLUDED.market,
    industry = EXCLUDED.industry,
    security_type = EXCLUDED.security_type,
    search_aliases = EXCLUDED.search_aliases,
    source = EXCLUDED.source,
    is_active = EXCLUDED.is_active,
    updated_at = EXCLUDED.updated_at;
