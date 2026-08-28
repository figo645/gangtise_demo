-- Development-data visibility must never remove access to DAv/Admin accounts.
-- A full local database deployment may contain historic provenance marks from
-- the former all-user bootstrap. Clear those marks before the production app
-- starts applying its visibility filter.

UPDATE users
SET is_simulated = 0,
    simulation_label = ''
WHERE role IN ('dav', 'admin')
  AND COALESCE(is_simulated, 0) <> 0;

-- Replace the generic provenance trigger so only investor identities can be
-- tagged as local development data. Other business tables retain their
-- existing generic provenance behavior.
CREATE OR REPLACE FUNCTION gangtise_mark_local_simulated_write()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_TABLE_NAME = 'users' AND NEW.role IN ('dav', 'admin') THEN
        NEW.is_simulated := 0;
        NEW.simulation_label := '';
        RETURN NEW;
    END IF;

    IF COALESCE(NULLIF(current_setting('gangtise.simulated_write', true), '')::integer, 0) = 1 THEN
        NEW.is_simulated := 1;
        NEW.simulation_label := '本机模拟数据';
    END IF;
    RETURN NEW;
END;
$$;
