# Rays of Hope

## Run locally

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you do not already have a `.env`, copy `backend/.env.example` to `.env`.
Fill in required credentials from shared doc. Use `SESSION_COOKIE_SECURE=false` for local HTTP
and `true` for deployed HTTPS. Leave `FLASK_DEBUG=0` outside local debugging.

Use the existing Neon database, which already has `accounts.auth0_sub` (with a
unique index) and `events.graphic_public_id`. The app does not create or change
the database schema on startup.

Start the app:

```bash
python backend/app.py
```

Open **http://localhost:5001**. One server handles the whole application.

Unexpected Auth0, Cloudinary, and database failures currently use Flask's default
error page. Custom recovery messages are deferred.

## Accounts

1. New volunteers wait at `/membership`. An admin approves, declines, or revokes
   access at `/admin/members` (also linked from the existing admin event page).
2. `accounts.is_admin` controls administration; `accounts.approved` controls volunteer
   membership. The backend checks these on each request, including check-in routes.

`ADMIN_EMAILS` only applies on first linking. For an already-linked account:

```bash
python -m flask --app backend/app set-admin 'person@example.com'
python -m flask --app backend/app set-admin 'person@example.com' --revoke
```

## Event posters

Admins use `/admin/events/create` or `/admin/events/<id>/edit`. The browser posts the
file to Flask; Flask validates it and uploads it to Cloudinary. PostgreSQL stores
`graphic_link` and `graphic_public_id` on the event. Existing event detail pages
show the stored image. JPEG, PNG, and WebP are accepted, up to 5 MB and 25 megapixels.

## Code map

- `backend/app.py`: shared app setup, event routes, membership review, and the admin command.
- `backend/auth.py`: Auth0 routes, sessions, and access checks.
- `backend/checkin.py`: existing check-in, codes, and hours-review logic.
- `backend/databasepostgresql.py`: direct SQL queries and one connection pool.
- `backend/posters.py`: image validation and Cloudinary upload/deletion.
- `frontend/templates/` and `frontend/static/`: Jinja pages and existing styling.

Event routes use `@app.route` in `app.py`. `auth.init(app)` and `checkin.init(app)`
register their routes on that same application. Each protected route calls
`authenticate_admin()` or `authenticate_member()` before querying PostgreSQL
and rendering a template.
