-- Correct an historical master-data mapping that selected US CPI for source_cpi.
-- The affected derived CPI indicator is invalidated so it cannot be presented
-- as China CPI before a successful re-sync from the verified NBS source.

UPDATE indicator_definitions
SET
    indicator_name = '中国CPI同比指数',
    description = '国家统计局发布的全国居民消费价格同比指数（上年同月=100）。',
    provider = 'Gangtise OpenAPI / 国家统计局',
    updated_at = TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')
WHERE indicator_code = 'source_cpi';

DELETE FROM indicator_latest_values
WHERE indicator_code IN ('source_cpi', 'laowang_cpi');

DELETE FROM indicator_series
WHERE indicator_code IN ('source_cpi', 'laowang_cpi');

DELETE FROM indicator_kline_points
WHERE indicator_code IN ('source_cpi', 'laowang_cpi');

DELETE FROM indicator_anomalies
WHERE indicator_code IN ('source_cpi', 'laowang_cpi');
