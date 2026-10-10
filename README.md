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
