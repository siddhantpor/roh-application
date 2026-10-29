# Integrating the check-in / hours subsystem (branch `chinmayi/check-in-hours`)

## What this branch adds

```
backend/
  database.py            picks databasepostgresql (DATABASE_URL set) or databasesqlite
  databasepostgresql.py  real backend (Neon)
  databasesqlite.py      dev backend, zero setup
  roh.sql / roh_postgres.sql   schema + seed data
  .env.example
  auth.py                STUB (see "Auth" below)
  checkin.py             all check-in / codes / review-hours routes, as init(app)
  runcheckin.py          standalone dev app; delete or keep after integration
  test_checkin.py        route tests (python test_checkin.py)
frontend/
  static/css/check-in.css
  templates/check-in/    index, header, footer, member/checkin.html,
                         admin/{codes,hours,edit_hours}.html
README.md                Database + Design choices sections
requirements.txt         + psycopg[binary], psycopg-pool, python-dotenv, Flask-WTF
.gitignore               + *.sqlite
```

Nothing in Lucy's `backend/app.py`, her templates, or `style.css` is modified.

## To plug the routes into the team app

In the team's `app.py`, after `app = flask.Flask(...)`:

```python
import auth
import checkin
...
app.secret_key = os.environ['APP_SECRET_KEY']    # sessions need it
flask_wtf.csrf.CSRFProtect(app)                   # every POST form has {{csrf_token()}}
auth.init(app)
checkin.init(app)
```

and make sure `template_folder` / `static_folder` point at `frontend/` (Lucy's app
already does). That's it; the routes, templates and database layer need no edits.

Then link the pages from the existing ones:
- member events page: the "Check-in Locked" `.code-card` -> link to
  `/member/events/<id>/checkin`
- admin event details: links to `/admin/events/<id>/codes` and `/admin/events/<id>/hours`

## Auth

`auth.py` is a stub with the same interface as both of Dondero's Penny versions:
`init(app)`, `authenticate()`, `get_username()`. To swap in the real thing:

- Home-grown: replace `auth.py` with Dondero's PennyAuthHomeGrown `auth.py`, add
  `login.html` and `signup.html`, and make `database.get_password` / `add_user`
  (two more Penny-pattern functions against the `accounts` table).
- Auth0: replace `auth.py` with PennyAuth0's, add `AUTH0_*` to `.env`, add `authlib`
  to requirements. `get_username()` then returns the Auth0 name; the `accounts` table
  needs a row per user with that username (or map by email).

`checkin.py` does not change in either case.

## Database

- `accounts`, `events`, `rsvps` are shared with the other subsystems. The columns this
  branch relies on: `accounts(user_id, username, display_name, is_admin)`,
  `events(event_id, event_date, start_time, end_time, event_title, event_locat,
  checkin_code, checkout_code)`, `rsvps(user_id, event_id, accepted)`.
- Schema differences from the Project Overview: README.md, "Database".
- Whoever writes `get_events()` etc. for the event pages: please put them in
  `databasesqlite.py` AND `databasepostgresql.py` in the same pattern, so there's one
  database module, not several.

## Known TODOs (each marked in the code)

- Check-in time window (open ~15 min before start): `checkin.py` header comment.
- Require RSVP to check in: `checkin.py` header comment, two lines to add.
- "Reason for change" on the edit page is shown, not stored: needs a column.
- "Go to My Hours" links to `/member/hours` (Chinmaya's screen 12). The database
  function for it, `get_hours(user_id, start_date, end_date)`, already exists.
- `volunteerhours` table from the overview is not used (hours are derived).
