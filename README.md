# Rays of Hope

One Flask application serves the existing event and check-in pages. Auth0 handles
identity, PostgreSQL stores accounts and events, and Cloudinary stores event posters.

## Run locally

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you do not already have a `.env`, copy `backend/.env.example` to `.env`.
Fill in:

- `APP_SECRET_KEY`: a random, stable session-signing secret. Generate one with
  `python -c 'import secrets; print(secrets.token_hex(32))'`.
- `DATABASE_URL`: your PostgreSQL/Neon connection URL, including its required SSL options.
- `AUTH0_DOMAIN`: your Auth0 domain without `https://`.
- `AUTH0_CLIENT_ID` and `AUTH0_CLIENT_SECRET`: your Regular Web Application's credentials.
- `ADMIN_EMAILS`: comma-separated verified emails to make admins on first account linking.
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET`: server-side upload credentials.

Keep `.env` out of version control. Use `SESSION_COOKIE_SECURE=false` for local HTTP
and `true` for deployed HTTPS. Leave `FLASK_DEBUG=0` outside local debugging.

In Auth0 application settings, register:

- Allowed Callback URLs: `http://localhost:5001/callback`
- Allowed Logout URLs: `http://localhost:5001/loggedout`

Enable the application's email/password connection and verify your signup email.

For the existing team PostgreSQL database, apply the additive migration:

```bash
python -m flask --app backend/app migrate-db
```

This adds `accounts.auth0_sub` and `events.graphic_public_id`; it does not reset data.
The existing check-in columns/constraints must already be present; see
`backend/migrate_checkin.sql` if they have not been applied. Do not rerun seed scripts
against a database containing real accounts or attendance.

For an empty PostgreSQL database, run `backend/roh_postgres.sql` in its SQL editor
first. It creates the required tables without demo accounts.

Start the app:

```bash
python backend/app.py
```

Open **http://localhost:5001**. One server handles the whole application.

## Accounts and permissions

1. Sign up through Auth0, verify the email, and log in again.
2. The callback links Auth0's unique `sub` to an application account. A verified
   email can link a single existing account that has not already been linked.
3. New volunteers wait at `/membership`. An admin approves, declines, or revokes
   access at `/admin/members` (also linked from the existing admin event page).
4. `accounts.is_admin` controls administration; `accounts.approved` controls volunteer
   membership. The backend checks these on each request, including check-in routes.

`ADMIN_EMAILS` only applies on first linking. For an already-linked account:

```bash
python -m flask --app backend/app set-admin 'person@example.com'
python -m flask --app backend/app set-admin 'person@example.com' --revoke
```

The command changes the database selected by `DATABASE_URL`. It does not create an
Auth0 account or set a password. Removing admin access leaves membership approval
unchanged. The session lasts eight hours; logout clears it and logs out of Auth0.

## Event posters

Admins use `/admin/events/create` or `/admin/events/<id>/edit`. The browser posts the
file to Flask; Flask validates it and uploads it to Cloudinary. PostgreSQL stores
`graphic_link` and `graphic_public_id` on the event. Existing event detail pages
show the stored image. JPEG, PNG, and WebP are accepted, up to 5 MB and 25 megapixels.
Replacement saves the new reference before deleting the old image. Failed storage
cleanup is logged for manual retry. Cloudinary credentials never reach templates.
The edit route is available directly; wiring the dashboard edit button remains
with the event UI work.

## Code map

- `backend/app.py`: configuration, shared app setup, and admin/migration commands.
- `backend/auth.py`: Auth0 routes, sessions, and access checks.
- `backend/events.py`: existing event routes, membership review, and event forms.
- `backend/checkin.py`: existing check-in, codes, and hours-review logic.
- `backend/databasepostgresql.py`: direct SQL queries and one connection pool.
- `backend/posters.py`: image validation and Cloudinary upload/deletion.
- `frontend/templates/` and `frontend/static/`: Jinja pages and existing styling.

Blueprints group route functions; registering them on `create_app()` makes them
part of one Flask server. A protected request goes through the shared auth check,
then its route queries PostgreSQL and renders a template. No frontend state library
or separate API server is involved.

## Verification and remaining work

```bash
python -m unittest discover -s backend -p 'test_*.py' -v
```

Default tests mock database/external-service calls. To run the PostgreSQL checks,
set `TEST_DATABASE_URL` to a disposable test database connection URL, then rerun the
command. These checks create a uniquely named schema and remove only that schema.
They do not run the demo seed script or use `DATABASE_URL` as a fallback.

Manually verify real signup, email verification, admin approval, direct admin URL
rejection as a volunteer, logout, and poster upload/replacement/removal. The reported
live login failure still needs its exact error and service logs to diagnose.

Clickable event cards, displayed date formatting, dashboard edit buttons/navigation,
RSVP forms, attendee-directory integration, and the My Hours summary screen remain
with the event/volunteer UI work. Custom error pages are deferred; Flask's default
error responses are used. Authorization, file validation, and upload-failure cleanup
remain part of the authentication and poster features. Existing check-in
and admin hours-review routes are retained. The check-in time window, RSVP gating,
and persistence of hours-edit reasons remain unfinished. The Auth0 hosted page is
branded in Auth0's dashboard. Render deployment configuration is a separate step.
