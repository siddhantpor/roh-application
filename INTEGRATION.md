# Integration notes

Run the single application with `python backend/app.py`; see [README.md](README.md)
for configuration, migrations, and account setup.

`auth`, `events`, and `checkin` are Blueprints registered in `create_app()`.
All routes use `databasepostgresql.py` and the same application-owned pool.
`runcheckin.py` is a compatibility launcher for the same app.

The integration covers Auth0 identity linking, backend role/membership checks,
account approval, and Cloudinary posters. The welcome page is retained. Existing
event dashboard layouts are preserved for the team to develop further.

The membership screen is `/admin/members`; poster controls are on event create/edit.
The existing check-in and admin hours-review routes remain available. RSVP forms,
attendee integration, My Hours, and dashboard navigation are separate UI work.
Clickable cards, displayed date formatting, and the dashboard edit button also
remain with that work. The backend edit route is available for poster replacement.
Custom error pages are deferred; basic access checks and upload validation remain.
