-- Add Auth0 identity linking and Cloudinary poster references without resetting data.
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS auth0_sub TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS accounts_auth0_sub_unique ON accounts(auth0_sub);
ALTER TABLE events ADD COLUMN IF NOT EXISTS graphic_public_id TEXT;
