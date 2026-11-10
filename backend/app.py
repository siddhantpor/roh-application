"""The shared Flask app: setup, event pages, and membership review."""
import datetime
import os
from pathlib import Path

import click
import dotenv
import flask
from flask_wtf.csrf import CSRFProtect

import auth
import checkin
import databasepostgresql as database
import posters
import utils

backend_dir = Path(__file__).resolve().parent
dotenv.load_dotenv(backend_dir.parent / '.env')
dotenv.load_dotenv(backend_dir / '.env')

app = flask.Flask(__name__, template_folder="../frontend/templates", static_folder="../frontend/static")
app.config.update(
    SECRET_KEY=os.getenv('APP_SECRET_KEY'),
    DATABASE_URL=os.getenv('DATABASE_URL', ''),
    AUTH0_DOMAIN=os.getenv('AUTH0_DOMAIN', ''),
    AUTH0_CLIENT_ID=os.getenv('AUTH0_CLIENT_ID', ''),
    AUTH0_CLIENT_SECRET=os.getenv('AUTH0_CLIENT_SECRET', ''),
    ADMIN_EMAILS={e.strip().lower() for e in os.getenv('ADMIN_EMAILS', '').split(',') if e.strip()},
    CLOUDINARY_CLOUD_NAME=os.getenv('CLOUDINARY_CLOUD_NAME', ''),
    CLOUDINARY_API_KEY=os.getenv('CLOUDINARY_API_KEY', ''),
    CLOUDINARY_API_SECRET=os.getenv('CLOUDINARY_API_SECRET', ''),
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true',
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=8),
    SESSION_REFRESH_EACH_REQUEST=False,
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,
    POSTER_MAX_BYTES=5 * 1024 * 1024,
)
if not app.secret_key:
    raise RuntimeError('Set APP_SECRET_KEY in .env (see backend/.env.example).')
if not app.config['DATABASE_URL']:
    raise RuntimeError('Set DATABASE_URL to your Neon connection URL.')

database.init_app(app)
CSRFProtect(app)
auth.init(app)
checkin.init(app)
utils.init(app)


@app.route('/')
@app.route('/index')
def index():
    user = auth.get_user()
    if user is None:
        return flask.render_template('welcome.html')
    if not user['is_admin'] and not user['approved']:
        return flask.redirect('/membership')
    return flask.redirect('/admin/events' if user['is_admin'] else '/member/events')


@app.route('/admin/events')
def events():
    auth.authenticate_admin()
    admin_events = database.get_events()
    return flask.render_template('event-management/admin/events.html', admin_events=admin_events)


@app.route('/admin/events/create')
def admin_create_event():
    auth.authenticate_admin()
    return flask.render_template('event-management/admin/create_event.html', event=None, values={})


@app.route('/admin/events/<int:event_id>/edit')
def admin_edit_event(event_id):
    auth.authenticate_admin()
    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)
    values = {'date': event['event_date'], 'title': event['event_title'],
              'start_time': event['start_time'], 'end_time': event['end_time'],
              'location': event['event_locat'], 'description': event['event_descrip']}
    return flask.render_template('event-management/admin/create_event.html', event=event, values=values)


@app.route('/admin/events/create', methods=['POST'])
@app.route('/admin/events/<int:event_id>/edit', methods=['POST'])
def save_event(event_id=None):
    auth.authenticate_admin()
    event = database.get_event(event_id) if event_id is not None else None
    if event_id is not None and event is None:
        flask.abort(404)
    form = {key: flask.request.form.get(key, '').strip() for key in
            ('date', 'start_time', 'end_time', 'title', 'description', 'location')}
    url = event['graphic_link'] if event else None
    public_id = event['graphic_public_id'] if event else None
    uploaded_id = None
    _validate_event(form)
    flyer = flask.request.files.get('flyer')
    remove = flask.request.form.get('remove_poster') == 'yes'
    if remove and flyer and flyer.filename:
        flask.abort(400)
    if flyer and flyer.filename:
        url, public_id = posters.upload(flyer)
        uploaded_id = public_id
    elif remove:
        url, public_id = None, None

    # If the database write fails, remove any image uploaded by this request.
    try:
        if event is None:
            event_id = database.add_event(form['date'], form['start_time'], form['end_time'],
                form['title'], form['description'], form['location'], url, public_id)
        else:
            database.update_event(event_id, form['date'], form['start_time'], form['end_time'],
                form['title'], form['description'], form['location'], url, public_id)
    except Exception:
        if uploaded_id:
            posters.delete(uploaded_id)
        raise
    if event and event['graphic_public_id'] and event['graphic_public_id'] != public_id:
        posters.delete(event['graphic_public_id'])
    flask.flash('Event saved.')
    return flask.redirect(flask.url_for('admin_event_detail', event_id=event_id))


def _validate_event(form):
    if not form['title'] or not form['location']:
        flask.abort(400)
    if len(form['title']) > 200 or len(form['location']) > 300 or len(form['description']) > 10000:
        flask.abort(400)
    try:
        datetime.date.fromisoformat(form['date'])
        start = datetime.time.fromisoformat(form['start_time'])
        end = datetime.time.fromisoformat(form['end_time'])
    except ValueError:
        flask.abort(400)
    if start.tzinfo or end.tzinfo or end <= start:
        flask.abort(400)


@app.route('/admin/events/<int:event_id>')
def admin_event_detail(event_id):
    auth.authenticate_admin()
    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)
    return flask.render_template('event-management/admin/event_details.html', event=event)


@app.route('/admin/events/<int:event_id>/attendees')
def admin_attendees(event_id):
    auth.authenticate_admin()
    if database.get_event(event_id) is None:
        flask.abort(404)
    members = database.get_event_rsvps(event_id)
    going = len([m for m in members if m['status'] == 'Going'])
    pending = len([m for m in members if m['status'] == 'Pending'])
    not_going = len([m for m in members if m['status'] == 'Not Going'])
    return flask.render_template('event-management/admin/attendees.html',
                                 event_id=event_id, members=members, going=going,
                                 pending=pending, not_going=not_going)


@app.route('/admin/members')
def members():
    auth.authenticate_admin()
    return flask.render_template('event-management/admin/members.html', members=database.get_members())


@app.route('/admin/members/<int:user_id>/membership', methods=['POST'])
def update_membership(user_id):
    auth.authenticate_admin()
    action = flask.request.form.get('action')
    if action not in ('approve', 'decline', 'revoke'):
        flask.abort(400, 'Choose a valid membership action.')
    if not database.set_membership(user_id, action == 'approve'):
        flask.abort(404, 'No eligible volunteer account was found.')
    flask.flash('Membership approved.' if action == 'approve' else
                ('Membership declined.' if action == 'decline' else 'Membership access revoked.'))
    return flask.redirect('/admin/members')


@app.route('/member/events')
def member_events():
    auth.authenticate_member()
    rsvps = database.get_rsvps_for_user(auth.get_user()['user_id'])
    upcoming_events, other_events = [], []
    for event in database.get_events():
        event['rsvp'] = rsvps.get(event['event_id'])
        (upcoming_events if event['rsvp'] is True else other_events).append(event)
    return flask.render_template('event-management/member/events.html',
                                 upcoming_events=upcoming_events, other_events=other_events)


@app.route('/member/events/<int:event_id>')
def member_event_detail(event_id):
    auth.authenticate_member()
    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)
    rsvp = database.get_rsvp(auth.get_user()['user_id'], event_id)
    return flask.render_template('event-management/member/event_details.html', event=event, rsvp=rsvp)


@app.route('/member/events/<int:event_id>/rsvp', methods=['POST'])
def member_rsvp(event_id):
    auth.authenticate_member()
    if database.get_event(event_id) is None:
        flask.abort(404)
    accepted = flask.request.form.get('rsvp') == 'yes'
    time = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    database.add_rsvp(auth.get_user()['user_id'], event_id, accepted, time)
    return flask.redirect(flask.url_for('member_event_detail', event_id=event_id))


@app.after_request
def prevent_page_caching(response):
    # Do not cache account pages on shared computers after logout.
    if flask.request.endpoint != 'static':
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.cli.command('set-admin')
@click.argument('email')
@click.option('--revoke', is_flag=True, help='Remove admin access.')
def set_admin(email, revoke):
    """Grant/revoke an existing, linked account's admin access."""
    if not database.set_admin(email.strip().lower(), not revoke):
        raise click.ClickException('Expected one linked account with that email. Log in first.')
    click.echo('Updated admin access.')


if __name__ == '__main__':
    app.run(port=5001, debug=os.getenv('FLASK_DEBUG') == '1')
