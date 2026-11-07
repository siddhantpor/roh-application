-- Additive migration for the team's PostgreSQL/Neon schema (not the obsolete
-- SQLite-shaped roh_postgres.sql). Does not drop tables or rewrite data.
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS auth0_sub TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS accounts_auth0_sub_unique ON accounts(auth0_sub);
ALTER TABLE events ADD COLUMN IF NOT EXISTS graphic_public_id TEXT;
