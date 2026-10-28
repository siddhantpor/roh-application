# roh-application
rays of hope | cos 333

## Running locally

### 1. Register the app with Auth0 (one time)

- On auth0.com, go to Applications → Applications → Create Application, choose "Regular Web Applications".
- Note the Domain, Client ID, and Client Secret.
- Set **Allowed Callback URLs** to `http://localhost:5001/callback`.
- Set **Allowed Logout URLs** to `http://localhost:5001/loggedout`.
- Save changes.

### 2. Create `.env` in the repo root

```bash
cp .env.example .env
```

Fill in the Auth0 values, a random `APP_SECRET_KEY` (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`), and a comma-separated list of `ADMIN_EMAILS`.

### 3. Install and run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python backend/app.py
```

Then open http://localhost:5001 (use `localhost`, not `127.0.0.1`, or the Auth0 redirect won't match). Volunteers can sign up with an email and password; users listed in `ADMIN_EMAILS` are sent to the admin pages. Stop the server with `Ctrl+C`.

## Project layout

- `backend/app.py` – Flask routes
- `backend/auth.py` – Auth0 login/signup/logout and route protection
- `frontend/templates/` – Jinja templates (`event-management/admin/`, `event-management/member/`, shared header/footer)
- `frontend/static/css/style.css` – styles
- `frontend/static/images/` – committed images
- `.env.example` – environment variables needed to run the app
