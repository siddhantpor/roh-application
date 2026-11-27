-- migrate_pin.sql
-- Exact meeting-spot pin for events. Additive only: no DROP, no data touched.
-- Run once in Neon's SQL Editor. Old events keep NULLs and fall back to the location text.
ALTER TABLE events
    ADD COLUMN IF NOT EXISTS event_lat double precision,
    ADD COLUMN IF NOT EXISTS event_lng double precision;
