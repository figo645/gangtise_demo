-- Market Overview is collected exclusively by market_snapshot_sync from
-- AKShare. Remove all Gangtise endpoint metadata from its nine source rows.
UPDATE indicator_source_defs
SET provider = 'AKShare',
    base_url = '',
    path = 'akshare://market_snapshot',
    method = 'SNAPSHOT',
    auth_type = 'none',
    headers_json = '{}',
    query_json = '{}',
    body_json = '{}',
    response_mapping_json = '{"value_path":"value","time_path":"updated_at","status_path":"available","connector_type":"akshare_snapshot","extractor_type":"market_snapshot","request_blueprint":{"snapshot_type":"market_overview","provider":"AKShare"}}',
    response_sample_json = '{"provider":"AKShare","connector_type":"akshare_snapshot","extractor_type":"market_snapshot","status":"configured","record_summary":"由 market_snapshot_sync 写入 PostgreSQL 快照，不调用 Gangtise。"}',
    source_status = 'configured',
    enabled = 1,
    last_test_status = '',
    last_http_status = NULL,
    last_tested_at = '',
    last_test_detail = 'AKShare 市场快照源',
    updated_at = CURRENT_TIMESTAMP::text
WHERE indicator_code IN (
    'source_shanghai_index', 'source_shenzhen_index', 'source_hsi',
    'source_hscei', 'source_hscci', 'source_dji', 'source_nasdaq',
    'source_sp500', 'source_nikkei'
);

UPDATE indicator_definitions
SET provider = 'AKShare',
    description = '由 AKShare 市场快照统一采集，用于市场一览展示。',
    owner = 'AKShare 市场快照',
    updated_at = CURRENT_TIMESTAMP::text
WHERE indicator_code IN (
    'source_shanghai_index', 'source_shenzhen_index', 'source_hsi',
    'source_hscei', 'source_hscci', 'source_dji', 'source_nasdaq',
    'source_sp500', 'source_nikkei'
);

-- The old aggregate industry EDB has no presentation use after the Shenwan
-- AKShare snapshot was introduced. Delete its API configuration and stale
-- landed values so it cannot be selected or displayed as a data source.
DELETE FROM indicator_mapping_rules WHERE indicator_code = 'source_industry_index' OR source_code = 'source_industry_index';
DELETE FROM indicator_source_tests WHERE source_code = 'source_industry_index';
DELETE FROM indicator_clean_jobs WHERE source_code = 'source_industry_index';
DELETE FROM indicator_raw_records WHERE source_code = 'source_industry_index';
DELETE FROM indicator_load_batches WHERE source_code = 'source_industry_index';
DELETE FROM indicator_latest_values WHERE indicator_code = 'source_industry_index';
DELETE FROM indicator_series WHERE indicator_code = 'source_industry_index';
DELETE FROM indicator_anomalies WHERE indicator_code = 'source_industry_index';
DELETE FROM indicator_kline_points WHERE indicator_code = 'source_industry_index';
DELETE FROM indicator_source_defs WHERE indicator_code = 'source_industry_index' OR source_code = 'source_industry_index';
DELETE FROM indicator_definitions WHERE indicator_code = 'source_industry_index';
