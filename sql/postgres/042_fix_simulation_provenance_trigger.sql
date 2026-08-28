-- Fix the generic provenance trigger introduced by 041.
-- NEW is a record whose fields depend on the table firing the trigger. Do not
-- combine TG_TABLE_NAME with NEW.role in one boolean expression: PostgreSQL
-- may evaluate NEW.role for tables that do not have that column.

CREATE OR REPLACE FUNCTION gangtise_mark_local_simulated_write()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_TABLE_NAME = 'users' THEN
        IF NEW.role IN ('dav', 'admin') THEN
            NEW.is_simulated := 0;
            NEW.simulation_label := '';
            RETURN NEW;
        END IF;
    END IF;

    IF COALESCE(NULLIF(current_setting('gangtise.simulated_write', true), '')::integer, 0) = 1 THEN
        NEW.is_simulated := 1;
        NEW.simulation_label := '本机模拟数据';
    END IF;
    RETURN NEW;
END;
$$;
