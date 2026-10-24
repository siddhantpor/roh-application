import flask

app = flask.Flask(__name__, template_folder="../frontend/templates", static_folder="../frontend/static")

@app.route("/admin/events")
def events():
    events = []  # TODO: Integrate w/ Cindy's database work!
    return flask.render_template("event-management/admin/events.html", events=events)

@app.route("/admin/events/create")
def admin_create_event():
    return flask.render_template("event-management/admin/create_event.html")

@app.route("/admin/events/<event_id>")
def admin_event_detail(event_id):
    event = None  # TODO: Integrate w/ Cindy's database work!
    return flask.render_template("event-management/admin/event_details.html", event=event)

@app.route("/admin/events/<event_id>/attendees")
def admin_attendees(event_id):
    return flask.render_template("event-management/admin/attendees.html")

@app.route("/member/events")
def member_events():
    upcoming_events = []  # TODO: Integrate w/ Cindy's database work!
    other_events = []  # TODO: Integrate w/ Cindy's database work!
    return flask.render_template("event-management/member/events.html",
                                 upcoming_events=upcoming_events,
                                 other_events=other_events)

@app.route("/member/events/<event_id>")
def member_event_detail(event_id):
    event = None  # TODO: Integrate w/ Cindy's database work!
    return flask.render_template("event-management/member/event_details.html", event=event)

if __name__ == "__main__":
    app.run(debug=True, port=5001)
