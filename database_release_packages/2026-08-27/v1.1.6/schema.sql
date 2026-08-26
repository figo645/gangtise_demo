-- Keep this package aligned with sql/postgres/035_local_simulation_data_visibility.sql.
CREATE OR REPLACE FUNCTION gangtise_mark_local_simulated_write()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF COALESCE(NULLIF(current_setting('gangtise.simulated_write', true), '')::integer, 0) = 1 THEN
        NEW.is_simulated := 1;
        NEW.simulation_label := '本机模拟数据';
    END IF;
    RETURN NEW;
END;
$$;

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'users', 'user_watchlist_items', 'fan_stock_observation_events', 'watchlist_kline_annotations',
        'watchlist_comments', 'hermes_conversation_turns', 'hermes_session_memory', 'hermes_user_memory',
        'hermes_user_profiles', 'knowledge_embeddings', 'review_voice_embeddings', 'user_async_jobs',
        'token_usage_logs', 'indicator_latest_values', 'indicator_series', 'indicator_anomalies',
        'indicator_kline_points', 'indicator_raw_records', 'indicator_load_batches', 'indicator_source_tests',
        'indicator_clean_jobs'
    ]
    LOOP
        IF to_regclass('public.' || table_name) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS is_simulated INTEGER NOT NULL DEFAULT 0', table_name);
            EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS simulation_label TEXT NOT NULL DEFAULT ''''', table_name);
            EXECUTE format(
                'ALTER TABLE %I ALTER COLUMN is_simulated SET DEFAULT COALESCE(NULLIF(current_setting(''gangtise.simulated_write'', true), '''')::integer, 0)',
                table_name
            );
            EXECUTE format(
                'ALTER TABLE %I ALTER COLUMN simulation_label SET DEFAULT CASE WHEN COALESCE(NULLIF(current_setting(''gangtise.simulated_write'', true), '''')::integer, 0) = 1 THEN ''本机模拟数据'' ELSE '''' END',
                table_name
            );
            EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (is_simulated)', 'idx_' || table_name || '_is_simulated', table_name);
            EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', 'trg_' || table_name || '_local_simulation_provenance', table_name);
            EXECUTE format(
                'CREATE TRIGGER %I BEFORE INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION gangtise_mark_local_simulated_write()',
                'trg_' || table_name || '_local_simulation_provenance',
                table_name
            );
        END IF;
    END LOOP;
END $$;
