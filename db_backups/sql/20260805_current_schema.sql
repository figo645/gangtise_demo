-- Current schema backup
-- Source database: /Users/xuchenfei/PycharmProjects/gangtise_demo/gangtise_demo.db
-- Generated at: 2026-08-06 02:07:40

CREATE TABLE access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                path TEXT NOT NULL,
                method TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                user_agent TEXT,
                referrer TEXT
            );
CREATE INDEX idx_access_logs_created_at ON access_logs(created_at);
CREATE INDEX idx_access_logs_ip ON access_logs(ip);
CREATE INDEX idx_access_logs_path ON access_logs(path);
CREATE TABLE app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                tenant_slug TEXT NOT NULL,
                advisor_name TEXT,
                phone TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
CREATE TABLE indicator_definitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
CREATE INDEX idx_indicator_definitions_source_type ON indicator_definitions(source_type);
CREATE TABLE indicator_source_defs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
CREATE INDEX idx_indicator_source_defs_indicator_code ON indicator_source_defs(indicator_code);
CREATE TABLE indicator_source_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_code TEXT NOT NULL,
                tested_at TEXT NOT NULL,
                success INTEGER NOT NULL,
                http_status INTEGER,
                latency_ms INTEGER,
                response_sample TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT ''
            );
CREATE INDEX idx_indicator_source_tests_source_code ON indicator_source_tests(source_code, tested_at DESC);
CREATE TABLE indicator_load_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_code TEXT NOT NULL UNIQUE,
                load_type TEXT NOT NULL DEFAULT 'mock_seed',
                source_code TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                total_points INTEGER NOT NULL DEFAULT 0,
                total_indicators INTEGER NOT NULL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
CREATE TABLE indicator_latest_values (
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
CREATE TABLE indicator_series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                indicator_code TEXT NOT NULL,
                point_time TEXT NOT NULL,
                point_value REAL NOT NULL,
                point_status TEXT NOT NULL DEFAULT 'attention',
                is_simulated INTEGER NOT NULL DEFAULT 1,
                source_code TEXT NOT NULL DEFAULT '',
                batch_code TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
CREATE INDEX idx_indicator_series_indicator_code ON indicator_series(indicator_code, point_time DESC);
CREATE TABLE indicator_anomalies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                indicator_code TEXT NOT NULL,
                anomaly_time TEXT NOT NULL,
                anomaly_value REAL NOT NULL DEFAULT 0,
                severity TEXT NOT NULL DEFAULT '中',
                anomaly_status TEXT NOT NULL DEFAULT 'attention',
                anomaly_label TEXT NOT NULL DEFAULT '',
                batch_code TEXT NOT NULL DEFAULT '',
                is_simulated INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
CREATE INDEX idx_indicator_anomalies_indicator_code ON indicator_anomalies(indicator_code, anomaly_time DESC);
CREATE TABLE indicator_kline_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                indicator_code TEXT NOT NULL,
                point_date TEXT NOT NULL,
                open_value REAL NOT NULL,
                high_value REAL NOT NULL,
                low_value REAL NOT NULL,
                close_value REAL NOT NULL,
                ma5 REAL,
                ma10 REAL,
                ma20 REAL,
                batch_code TEXT NOT NULL DEFAULT '',
                is_simulated INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
CREATE INDEX idx_indicator_kline_points_indicator_code ON indicator_kline_points(indicator_code, point_date DESC);
CREATE TABLE indicator_raw_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
CREATE INDEX idx_indicator_raw_records_source_code ON indicator_raw_records(source_code, fetched_at DESC);
CREATE TABLE indicator_mapping_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
CREATE INDEX idx_indicator_mapping_rules_indicator_code ON indicator_mapping_rules(indicator_code, source_code);
CREATE TABLE indicator_clean_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_code TEXT NOT NULL UNIQUE,
                source_code TEXT NOT NULL,
                indicator_code TEXT NOT NULL,
                raw_record_id INTEGER,
                mapping_rule_code TEXT NOT NULL DEFAULT '',
                job_status TEXT NOT NULL DEFAULT 'pending',
                cleaned_points INTEGER NOT NULL DEFAULT 0,
                result_summary TEXT NOT NULL DEFAULT '',
                result_payload TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                finished_at TEXT NOT NULL DEFAULT ''
            );
CREATE INDEX idx_indicator_clean_jobs_source_code ON indicator_clean_jobs(source_code, created_at DESC);
