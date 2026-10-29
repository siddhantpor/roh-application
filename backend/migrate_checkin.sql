-- migrate_checkin.sql
-- Additions the check-in subsystem needs on the team's Neon database.
-- Additive only: no DROP, no data touched. Run once in Neon's SQL Editor.

-- 1. Per-event codes (NULL until an admin generates them).
ALTER TABLE events
    ADD COLUMN IF NOT EXISTS checkin_code  text,
    ADD COLUMN IF NOT EXISTS checkout_code text;

-- 2. One check-in row and one check-out row per member per event.
--    Lets "you already checked in" be a key violation instead of a lookup.
ALTER TABLE attendance
    ADD CONSTRAINT attendance_one_per_member_event
    UNIQUE (user_id, event_id, is_checkin);

-- 3. (Not check-in's, but auth will need it.) No two accounts with the same username.
ALTER TABLE accounts
    ADD CONSTRAINT accounts_username_unique UNIQUE (username);
