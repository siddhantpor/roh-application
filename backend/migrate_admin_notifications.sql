-- Admin side of notifications. Run once in Neon, after migrate_notifications.sql.
-- Additive only.

ALTER TABLE accounts ADD COLUMN IF NOT EXISTS notify_admin_signup boolean NOT NULL DEFAULT TRUE;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS notify_admin_hours boolean NOT NULL DEFAULT FALSE;

-- remembers when a scheduled job (like the weekly admin digest) last ran
CREATE TABLE IF NOT EXISTS task_runs (
    name text PRIMARY KEY,
    last_run timestamp NOT NULL);
