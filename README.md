# roh-application
rays of hope | cos 333

## Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5001. Stop the server with `Ctrl+C`.

## Project layout

- `app.py` – Flask routes and in-memory sample data
- `templates/` – Jinja templates (events list, create event, event detail, attendees)
- `static/css/style.css` – styles
- `static/images/` – committed images (sample flyer)
- `static/uploads/` – user-uploaded flyers (git-ignored)

## Database (local dev)

There are two interchangeable backends, in Dondero's Penny layout:

- `backend/databasepostgresql.py` + `backend/roh_postgres.sql`: the real one (Neon).
  Needs `DATABASE_URL` in `backend/.env` (see `backend/.env.example`).
- `backend/databasesqlite.py` + `backend/roh.sql`: dev only, zero setup, runs on any laptop.

`backend/database.py` picks Postgres when `DATABASE_URL` is set and SQLite otherwise;
the rest of the code just does `import database`. Both modules have a `_test()`;
`python3 databasesqlite.py` / `python3 databasepostgresql.py` runs it and the output
of the two must be identical.

To build the SQLite database:

```bash
cd backend
sqlite3 roh.sqlite < roh.sql
```

(or, without the `sqlite3` tool:
`python3 -c "import sqlite3; c=sqlite3.connect('roh.sqlite'); c.executescript(open('roh.sql').read()); c.commit()"`)

`roh.sqlite` is git-ignored; rebuild it from `roh.sql` whenever the schema changes.

### Differences from the schema in ProjectOverview.pdf (Section 6)

All of these are needed by the check-in / hours subsystem. Need to discuss:

1. `checkins` and `checkouts` are keyed by `(user_id, event_id)`, not
   `user_id` alone. With `user_id` alone a member could only ever check
   in to one event, ever.
2. `events` has `checkin_code` and `checkout_code` columns. The overview
   has no column for the per-event codes.
3. `events` has `start_time` and `end_time` (the event templates use
   them; Tanisha asked for end times on Oct 14).
4. `events.event_id` is `INTEGER PRIMARY KEY` so SQLite auto-assigns it.
   In Postgres this becomes `BIGSERIAL` / `GENERATED AS IDENTITY`.
5. `volunteerhours` is dropped. Hours are *derived* from an approved
   checkin + checkout pair (`checkout.time - checkin.time`), so storing
   them separately would just be a second copy that can go stale. If
   the team wants it anyway, it's easy to add back.

## Design choices (check-in / hours subsystem)


1. **Who can check in?** Anyone logged in who knows the code, RSVP or not (matches how
   the current Google Form works, where walk-ins happen). The Project Overview says
   "available to students who have RSVP'd" for now all can log in
2. **When can you check in?** Any time, for now. Tanisha asked for check-in to open
   about 15 minutes before the event start; not implemented yet (noted at the top of
   `checkin.py`).
3. **Codes.** 6 characters from an alphabet with no 0/O or 1/I (`CODE_ALPHABET`), made
   with `secrets`, not `random`. 
5. **Hours.** Not stored. Computed from an approved check-in + approved check-out pair.
   An admin cannot approve a row that has no check-out time.
