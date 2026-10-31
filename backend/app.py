import flask
import databasepostgresql as database

app = flask.Flask(__name__, template_folder="../frontend/templates", static_folder="../frontend/static")

@app.route("/admin/events")
def events():
    admin_events = database.get_events()
    return flask.render_template("event-management/admin/events.html", admin_events=admin_events)

@app.route("/admin/events/create")
def admin_create_event():
    return flask.render_template("event-management/admin/create_event.html")

@app.route("/admin/events/create", methods=["POST"])
def handle_admin_create_event():
    form = flask.request.form
    # TODO: Integrate w/ Cloudinary + implement flyer upload logic.
    database.add_event(form["date"], form["start_time"], form["end_time"],
                       form["title"].strip(), form.get("description", "").strip(),
                       form["location"].strip())
    return flask.redirect("/admin/events")

@app.route("/admin/events/<int:event_id>")
def admin_event_detail(event_id):
    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)
    return flask.render_template("event-management/admin/event_details.html", event=event)

@app.route("/admin/events/<event_id>/attendees")
def admin_attendees(event_id):
    members = []  # TODO: Integrate w/ Cindy's database work!
    going = len([m for m in members if m["status"] == "Going"])
    pending = len([m for m in members if m["status"] == "Pending"])
    not_going = len([m for m in members if m["status"] == "Not Going"])
    return flask.render_template("event-management/admin/attendees.html",
                                 event_id=event_id, members=members, going=going,
                                 pending=pending, not_going=not_going)

@app.route("/member/events")
def member_events():
    upcoming_events = []  # TODO: Integrate w/ Chinmaya's Auth0!
    other_events = database.get_events()
    return flask.render_template("event-management/member/events.html",
                                 upcoming_events=upcoming_events,
                                 other_events=other_events)

@app.route("/member/events/<int:event_id>")
def member_event_detail(event_id):
    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)
    return flask.render_template("event-management/member/event_details.html", event=event)

if __name__ == "__main__":
    app.run(debug=True, port=5001)
