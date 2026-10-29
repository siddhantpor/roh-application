-- roh.sql
-- Schema + seed data for the Rays of Hope app (SQLite, local dev).
-- Build the database from this file with:
--     sqlite3 roh.sqlite < roh.sql
-- See README.md for how this differs from the ProjectOverview schema.

DROP TABLE IF EXISTS accounts;
CREATE TABLE accounts (
    user_id      INTEGER PRIMARY KEY,
    username     TEXT NOT NULL UNIQUE,
    password     TEXT,            -- hash, filled in by whoever does auth
    email        TEXT,
    is_admin     INTEGER NOT NULL DEFAULT 0,   -- SQLite has no BOOLEAN; 0/1
    display_name TEXT,
    approved     INTEGER NOT NULL DEFAULT 0,
    pending      INTEGER NOT NULL DEFAULT 1
);
-- One admin, three members. Passwords are NULL until auth is done.
INSERT INTO accounts (username, email, is_admin, display_name, approved, pending)
    VALUES ('tdouglas', 'tdouglas@example.com', 1, 'Tyneisha Douglas', 1, 0);
INSERT INTO accounts (username, email, is_admin, display_name, approved, pending)
    VALUES ('alice', 'alice@example.com', 0, 'Alice', 1, 0);
INSERT INTO accounts (username, email, is_admin, display_name, approved, pending)
    VALUES ('bob', 'bob@example.com', 0, 'Bob', 1, 0);
INSERT INTO accounts (username, email, is_admin, display_name, approved, pending)
    VALUES ('carol', 'carol@example.com', 0, 'Carol', 1, 0);

DROP TABLE IF EXISTS events;
CREATE TABLE events (
    event_id      INTEGER PRIMARY KEY,
    event_date    TEXT NOT NULL,   -- 'YYYY-MM-DD'
    start_time    TEXT,            -- 'HH:MM' (24h)
    end_time      TEXT,            -- 'HH:MM' (24h)
    event_title   TEXT NOT NULL,
    event_descrip TEXT,
    event_locat   TEXT,
    graphic_link  TEXT,            -- Cloudinary URL, later
    checkin_code  TEXT,            -- NULL until an admin generates it
    checkout_code TEXT             -- NULL until an admin generates it
);
-- Event 1 already has codes (so check-in can be tested right away).
-- Event 2 has none yet (so "generate codes" can be tested).
INSERT INTO events (event_date, start_time, end_time, event_title,
                    event_descrip, event_locat, checkin_code, checkout_code)
    VALUES ('2026-11-07', '09:00', '12:00', 'Park Cleanup',
            'Bring gloves. Closed-toe shoes required.',
            'Mercer County Park', 'ABC123', 'XYZ789');
INSERT INTO events (event_date, start_time, end_time, event_title,
                    event_descrip, event_locat)
    VALUES ('2026-11-14', '13:00', '16:00', 'Food Bank Sorting',
            'Sorting donations at the Trenton food bank.',
            'Trenton Area Soup Kitchen');

DROP TABLE IF EXISTS rsvps;
CREATE TABLE rsvps (
    user_id  INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    accepted INTEGER NOT NULL,   -- 1 = going, 0 = not going
    time     TEXT NOT NULL,      -- ISO 8601 UTC, e.g. '2026-10-27T18:40:00'
    PRIMARY KEY (user_id, event_id)
);
-- alice and bob are going to event 1; carol is not.
INSERT INTO rsvps VALUES (2, 1, 1, '2026-10-20T15:00:00');
INSERT INTO rsvps VALUES (3, 1, 1, '2026-10-21T09:30:00');
INSERT INTO rsvps VALUES (4, 1, 0, '2026-10-21T10:00:00');

-- checkins / checkouts: one row per (member, event). The time is
-- stamped by the server when the member submits the correct code.
-- approved is 0 until an admin reviews it.
DROP TABLE IF EXISTS checkins;
CREATE TABLE checkins (
    user_id  INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    time     TEXT NOT NULL,      -- ISO 8601 UTC
    approved INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, event_id)
);

DROP TABLE IF EXISTS checkouts;
CREATE TABLE checkouts (
    user_id  INTEGER NOT NULL,
    event_id INTEGER NOT NULL,
    time     TEXT NOT NULL,      -- ISO 8601 UTC
    approved INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, event_id)
);
-- alice already checked in and out of event 1 (unapproved), so the
-- admin review screen has something to show. bob checked in only.
INSERT INTO checkins  VALUES (2, 1, '2026-11-07T14:02:00', 0);
INSERT INTO checkouts VALUES (2, 1, '2026-11-07T16:58:00', 0);
INSERT INTO checkins  VALUES (3, 1, '2026-11-07T14:10:00', 0);
