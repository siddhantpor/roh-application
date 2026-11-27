-- Run once against Neon before deploying the notification stuff.
-- Only adds things, doesn't drop anything.

ALTER TABLE accounts ADD COLUMN IF NOT EXISTS phone text;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS notify_new_event boolean NOT NULL DEFAULT TRUE;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS notify_rsvp boolean NOT NULL DEFAULT TRUE;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS notify_changes boolean NOT NULL DEFAULT TRUE;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS notify_reminder boolean NOT NULL DEFAULT TRUE;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS notify_sms boolean NOT NULL DEFAULT FALSE;

-- so we don't remind the same person about the same event twice
CREATE TABLE IF NOT EXISTS reminders_sent (
    user_id integer NOT NULL REFERENCES accounts(user_id),
    event_id integer NOT NULL REFERENCES events(event_id),
    sent_at timestamp NOT NULL,
    PRIMARY KEY (user_id, event_id));
