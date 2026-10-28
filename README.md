# roh-application

rays of hope | cos 333

### Install and run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python backend/app.py
```

Open http://localhost:5001. Volunteers can sign up with an email and password and users listed in `ADMIN_EMAILS` are sent to the admin pages. Stop the server with `Ctrl+C`.

## Project layout

- `backend/app.py` – Flask routes
- `backend/auth.py` – Auth0 login/signup/logout and route protection
- `frontend/templates/` – Jinja templates (`event-management/admin/`, `event-management/member/`, shared header/footer)
- `frontend/static/css/style.css` – styles
- `frontend/static/images/` – committed images
- `.env.example` – environment variables needed to run the app
