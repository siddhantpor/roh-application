"""Rays of Hope - event management prototype.

Data lives in memory for now; swap EVENTS / MEMBERS for a real database later.
"""

import datetime
import os
import uuid

import flask
from werkzeug.utils import secure_filename

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app = flask.Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-secret")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

# The signed-in member, until real authentication exists.
CURRENT_USER = "Chinmaya Saran"

MEMBERS = [
    "Cindy Lin", "Siddhant Porwal", "Chinmaya Saran", "Chinmayi Ramasubramanian",
    "Lucy Wang", "Robert Dondero", "Haluca Ohiles", "Julien Mpano",
    "Christopher Eisgruber", "Ada Lovelace",
]

EVENTS = {
    "1": {
        "id": "1",
        "title": "Leadership Workshop",
        "date": datetime.date(2026, 10, 4),
        "start_time": datetime.time(16, 0),
        "end_time": datetime.time(18, 0),
        "location": "Somerset, NJ",
        "description": (
            "Join us for an empowering workshop that will help you get back "
            "in the rhythm with school, build positive habits, and set goals "
            "for a successful year.\n\n"
            "We are doing headshots for all members throughout the morning. "
            "All members should wear their polo shirts. If you do not have one "
            "please reach out to Ms. Lisa or Ms. Ty no later than Sunday, "
            "September 13th."
        ),
        "condensed_description": "An empowering workshop on habits and goal-setting.",
        "flyer": "images/leadership-workshop.jpg",
        "rsvps": {
            "Cindy Lin": "not_going",
            "Chinmaya Saran": "going",
            "Siddhant Porwal": "going",
            "Lucy Wang": "going",
            "Robert Dondero": "going",
            "Haluca Ohiles": "going",
            "Julien Mpano": "going",
            "Christopher Eisgruber": "not_going",
        },
    },
}

STATUS_LABELS = {"going": "Going", "pending": "Pending", "not_going": "Not Going"}


def rsvp_status(event, member):
    return event["rsvps"].get(member, "pending")


def rsvp_counts(event):
    counts = {"going": 0, "pending": 0, "not_going": 0}
    for member in MEMBERS:
        counts[rsvp_status(event, member)] += 1
    return counts


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_event_form(form):
    """Return (fields, errors) from the create-event form."""
    errors = []
    fields = {
        "title": form.get("title", "").strip(),
        "location": form.get("location", "").strip(),
        "description": form.get("description", "").strip(),
        "condensed_description": form.get("condensed_description", "").strip(),
    }
    for key, label in (("title", "Event title"), ("location", "Location")):
        if not fields[key]:
            errors.append(f"{label} is required.")

    try:
        fields["date"] = datetime.date.fromisoformat(form.get("date", ""))
    except ValueError:
        errors.append("A valid date is required.")
    try:
        fields["start_time"] = datetime.time.fromisoformat(form.get("start_time", ""))
        fields["end_time"] = datetime.time.fromisoformat(form.get("end_time", ""))
        if fields["end_time"] <= fields["start_time"]:
            errors.append("End time must be after start time.")
    except ValueError:
        errors.append("Valid start and end times are required.")

    return fields, errors


@app.template_filter("pretty_time")
def pretty_time(value):
    return value.strftime("%-I:%M %p")


@app.context_processor
def inject_globals():
    return {"current_user": CURRENT_USER, "status_labels": STATUS_LABELS}


@app.route("/")
@app.route("/events")
def events():
    upcoming = sorted(EVENTS.values(), key=lambda e: (e["date"], e["start_time"]))
    return flask.render_template(
        "events.html",
        events=upcoming,
        counts={e["id"]: rsvp_counts(e) for e in upcoming},
    )


@app.route("/events/new", methods=["GET", "POST"])
def create_event():
    if flask.request.method == "GET":
        return flask.render_template("create_event.html", form={}, errors=[])

    fields, errors = parse_event_form(flask.request.form)

    flyer = flask.request.files.get("flyer")
    if flyer and flyer.filename and not allowed_file(flyer.filename):
        errors.append("Flyer must be an image (png, jpg, gif, webp).")

    if errors:
        return flask.render_template(
            "create_event.html", form=flask.request.form, errors=errors
        ), 400

    event_id = uuid.uuid4().hex[:8]
    fields["flyer"] = None
    if flyer and flyer.filename:
        filename = f"{event_id}_{secure_filename(flyer.filename)}"
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        flyer.save(os.path.join(UPLOAD_DIR, filename))
        fields["flyer"] = f"uploads/{filename}"

    EVENTS[event_id] = {"id": event_id, "rsvps": {}, **fields}
    return flask.redirect(flask.url_for("event_detail", event_id=event_id))


@app.route("/events/<event_id>")
def event_detail(event_id):
    event = EVENTS.get(event_id) or flask.abort(404)
    return flask.render_template(
        "event_detail.html",
        event=event,
        counts=rsvp_counts(event),
        my_status=rsvp_status(event, CURRENT_USER),
    )


@app.route("/events/<event_id>/rsvp", methods=["POST"])
def rsvp(event_id):
    event = EVENTS.get(event_id) or flask.abort(404)
    status = flask.request.form.get("status")
    if status not in ("going", "not_going"):
        flask.abort(400)
    event["rsvps"][CURRENT_USER] = status
    return flask.redirect(flask.url_for("event_detail", event_id=event_id))


@app.route("/events/<event_id>/attendees")
def attendees(event_id):
    event = EVENTS.get(event_id) or flask.abort(404)
    query = flask.request.args.get("q", "").strip()
    members = [
        {"name": m, "status": rsvp_status(event, m)}
        for m in MEMBERS
        if query.lower() in m.lower()
    ]
    return flask.render_template(
        "attendees.html",
        event=event,
        members=members,
        counts=rsvp_counts(event),
        query=query,
    )


@app.errorhandler(413)
def file_too_large(_error):
    return flask.render_template(
        "create_event.html",
        form={},
        errors=["Flyer must be 5 MB or smaller."],
    ), 413


if __name__ == "__main__":
    app.run(debug=True, port=5001)
