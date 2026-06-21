-- Run this file as a superuser or a role with CREATE ROLE / CREATE DATABASE privileges.
-- Default connection target for this project:
--   host: 129.211.65.53
--   port: 5432
--   database: sprint_dashboard
--   user: postgres

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'postgres'
    ) THEN
        CREATE ROLE postgres LOGIN PASSWORD 'your_password';
    END IF;
END $$;

SELECT 'CREATE DATABASE sprint_dashboard OWNER postgres'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = 'sprint_dashboard'
)\gexec

GRANT ALL PRIVILEGES ON DATABASE sprint_dashboard TO postgres;
