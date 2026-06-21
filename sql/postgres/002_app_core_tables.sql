-- Core application tables migrated from SQLite to Postgres.

CREATE TABLE IF NOT EXISTS access_logs (
    id BIGSERIAL PRIMARY KEY,
    ip TEXT NOT NULL,
    path TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    user_agent TEXT NOT NULL DEFAULT '',
    referrer TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_access_logs_created_at ON access_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_access_logs_ip ON access_logs(ip);
CREATE INDEX IF NOT EXISTS idx_access_logs_path ON access_logs(path);

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    role TEXT NOT NULL,
    tenant_slug TEXT NOT NULL,
    advisor_name TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS indicator_definitions (
    id BIGSERIAL PRIMARY KEY,
    indicator_code TEXT NOT NULL UNIQUE,
    indicator_name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    unit TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'mock',
    source_type_label TEXT NOT NULL DEFAULT '模拟指标',
    provider TEXT NOT NULL DEFAULT '',
    status_hint TEXT NOT NULL DEFAULT 'attention',
    assessment_template TEXT NOT NULL DEFAULT '',
    alert_template TEXT NOT NULL DEFAULT '',
    watchers_json TEXT NOT NULL DEFAULT '[]',
    display_config_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_indicator_definitions_source_type ON indicator_definitions(source_type);

CREATE TABLE IF NOT EXISTS indicator_source_defs (
    id BIGSERIAL PRIMARY KEY,
    source_code TEXT NOT NULL UNIQUE,
    indicator_code TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',
    method TEXT NOT NULL DEFAULT 'GET',
    auth_type TEXT NOT NULL DEFAULT 'none',
    headers_json TEXT NOT NULL DEFAULT '{}',
    query_json TEXT NOT NULL DEFAULT '{}',
    body_json TEXT NOT NULL DEFAULT '{}',
    response_mapping_json TEXT NOT NULL DEFAULT '{}',
    response_sample_json TEXT NOT NULL DEFAULT '{}',
    source_status TEXT NOT NULL DEFAULT 'draft',
    enabled INTEGER NOT NULL DEFAULT 1,
    last_test_status TEXT NOT NULL DEFAULT '',
    last_http_status INTEGER,
    last_tested_at TEXT NOT NULL DEFAULT '',
    last_test_detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_indicator_source_defs_indicator_code ON indicator_source_defs(indicator_code);

CREATE TABLE IF NOT EXISTS indicator_source_tests (
    id BIGSERIAL PRIMARY KEY,
    source_code TEXT NOT NULL,
    tested_at TEXT NOT NULL,
    success INTEGER NOT NULL,
    http_status INTEGER,
    latency_ms INTEGER,
    response_sample TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_indicator_source_tests_source_code
ON indicator_source_tests(source_code, tested_at DESC);

CREATE TABLE IF NOT EXISTS indicator_load_batches (
    id BIGSERIAL PRIMARY KEY,
    batch_code TEXT NOT NULL UNIQUE,
    load_type TEXT NOT NULL DEFAULT 'mock_seed',
    source_code TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    total_points INTEGER NOT NULL DEFAULT 0,
    total_indicators INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS indicator_latest_values (
    indicator_code TEXT PRIMARY KEY,
    latest_value TEXT NOT NULL DEFAULT '',
    latest_status TEXT NOT NULL DEFAULT 'attention',
    latest_assessment TEXT NOT NULL DEFAULT '',
    latest_alert TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    is_simulated INTEGER NOT NULL DEFAULT 1,
    source_code TEXT NOT NULL DEFAULT '',
    batch_code TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS indicator_series (
    id BIGSERIAL PRIMARY KEY,
    indicator_code TEXT NOT NULL,
    point_time TEXT NOT NULL,
    point_value DOUBLE PRECISION NOT NULL,
    point_status TEXT NOT NULL DEFAULT 'attention',
    is_simulated INTEGER NOT NULL DEFAULT 1,
    source_code TEXT NOT NULL DEFAULT '',
    batch_code TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_indicator_series_indicator_code
ON indicator_series(indicator_code, point_time DESC);

CREATE TABLE IF NOT EXISTS indicator_anomalies (
    id BIGSERIAL PRIMARY KEY,
    indicator_code TEXT NOT NULL,
    anomaly_time TEXT NOT NULL,
    anomaly_value DOUBLE PRECISION NOT NULL DEFAULT 0,
    severity TEXT NOT NULL DEFAULT '中',
    anomaly_status TEXT NOT NULL DEFAULT 'attention',
    anomaly_label TEXT NOT NULL DEFAULT '',
    batch_code TEXT NOT NULL DEFAULT '',
    is_simulated INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_indicator_anomalies_indicator_code
ON indicator_anomalies(indicator_code, anomaly_time DESC);

CREATE TABLE IF NOT EXISTS indicator_kline_points (
    id BIGSERIAL PRIMARY KEY,
    indicator_code TEXT NOT NULL,
    point_date TEXT NOT NULL,
    open_value DOUBLE PRECISION NOT NULL,
    high_value DOUBLE PRECISION NOT NULL,
    low_value DOUBLE PRECISION NOT NULL,
    close_value DOUBLE PRECISION NOT NULL,
    ma5 DOUBLE PRECISION,
    ma10 DOUBLE PRECISION,
    ma20 DOUBLE PRECISION,
    batch_code TEXT NOT NULL DEFAULT '',
    is_simulated INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_indicator_kline_points_indicator_code
ON indicator_kline_points(indicator_code, point_date DESC);

CREATE TABLE IF NOT EXISTS indicator_raw_records (
    id BIGSERIAL PRIMARY KEY,
    source_code TEXT NOT NULL,
    indicator_code TEXT NOT NULL,
    fetch_mode TEXT NOT NULL DEFAULT 'sample',
    raw_payload TEXT NOT NULL,
    http_status INTEGER,
    success INTEGER NOT NULL DEFAULT 1,
    fetched_at TEXT NOT NULL,
    batch_code TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_indicator_raw_records_source_code
ON indicator_raw_records(source_code, fetched_at DESC);

CREATE TABLE IF NOT EXISTS indicator_mapping_rules (
    id BIGSERIAL PRIMARY KEY,
    rule_code TEXT NOT NULL UNIQUE,
    indicator_code TEXT NOT NULL,
    source_code TEXT NOT NULL,
    value_path TEXT NOT NULL DEFAULT '',
    time_path TEXT NOT NULL DEFAULT '',
    status_path TEXT NOT NULL DEFAULT '',
    unit_override TEXT NOT NULL DEFAULT '',
    default_status TEXT NOT NULL DEFAULT 'attention',
    transform_expr TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_indicator_mapping_rules_indicator_code
ON indicator_mapping_rules(indicator_code, source_code);

CREATE TABLE IF NOT EXISTS indicator_clean_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_code TEXT NOT NULL UNIQUE,
    source_code TEXT NOT NULL,
    indicator_code TEXT NOT NULL,
    raw_record_id BIGINT,
    mapping_rule_code TEXT NOT NULL DEFAULT '',
    job_status TEXT NOT NULL DEFAULT 'pending',
    cleaned_points INTEGER NOT NULL DEFAULT 0,
    result_summary TEXT NOT NULL DEFAULT '',
    result_payload TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_indicator_clean_jobs_source_code
ON indicator_clean_jobs(source_code, created_at DESC);
