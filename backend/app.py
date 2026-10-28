import os
import flask
import auth

app = flask.Flask(__name__, template_folder="../frontend/templates", static_folder="../frontend/static")
app.secret_key = os.environ["APP_SECRET_KEY"]
auth.init(app)

@app.route("/")
def index():
    auth.authenticate()
    if auth.is_admin():
        return flask.redirect(flask.url_for("events"))
    return flask.redirect(flask.url_for("member_events"))

@app.route("/admin/events")
def events():
    auth.authenticate_admin()
    events = []  # TODO: Integrate w/ Cindy's database work!
    return flask.render_template("event-management/admin/events.html", events=events)

@app.route("/admin/events/create")
def admin_create_event():
    auth.authenticate_admin()
    return flask.render_template("event-management/admin/create_event.html")

@app.route("/admin/events/<event_id>")
def admin_event_detail(event_id):
    auth.authenticate_admin()
    event = None  # TODO: Integrate w/ Cindy's database work!
    return flask.render_template("event-management/admin/event_details.html", event=event)

@app.route("/admin/events/<event_id>/attendees")
def admin_attendees(event_id):
    auth.authenticate_admin()
    members = []  # TODO: Integrate w/ Cindy's database work!
    going = len([m for m in members if m["status"] == "Going"])
    pending = len([m for m in members if m["status"] == "Pending"])
    not_going = len([m for m in members if m["status"] == "Not Going"])
    return flask.render_template("event-management/admin/attendees.html",
                                 event_id=event_id, members=members, going=going,
                                 pending=pending, not_going=not_going)

@app.route("/member/events")
def member_events():
    auth.authenticate()
    upcoming_events = []  # TODO: Integrate w/ Cindy's database work!
    other_events = []  # TODO: Integrate w/ Cindy's database work!
    return flask.render_template("event-management/member/events.html",
                                 upcoming_events=upcoming_events,
                                 other_events=other_events)

@app.route("/member/events/<event_id>")
def member_event_detail(event_id):
    auth.authenticate()
    event = None  # TODO: Integrate w/ Cindy's database work!
    return flask.render_template("event-management/member/event_details.html", event=event)

if __name__ == "__main__":
    app.run(debug=True, port=5001)
