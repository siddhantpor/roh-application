"""Server-rendered event pages, RSVP forms, and the volunteer hours summary."""
import datetime

import flask

import auth
import database
import posters

bp = flask.Blueprint('events', __name__)


bp.before_request(auth.protect_request)


def _event_or_404(event_id):
    event = database.get_event(event_id)
    if event is None:
        flask.abort(404, 'That event does not exist.')
    return event


@bp.get('/admin/events')
def admin_events():
    return flask.render_template('event-management/admin/events.html', admin_events=database.get_events())


@bp.route('/admin/events/create', methods=['GET', 'POST'])
def create_event():
    return _event_form()


@bp.route('/admin/events/<int:event_id>/edit', methods=['GET', 'POST'])
def edit_event(event_id):
    return _event_form(_event_or_404(event_id))


def _event_form(event=None):
    values = {} if event is None else {
        'date': event['event_date'], 'title': event['event_title'],
        'start_time': event['start_time'], 'end_time': event['end_time'],
        'location': event['event_locat'], 'description': event['event_descrip'],
    }
    status = 200
    if flask.request.method == 'POST':
        values = {key: flask.request.form.get(key, '').strip() for key in
                  ('date', 'title', 'start_time', 'end_time', 'location', 'description')}
        uploaded_id = None
        try:
            _validate_event(values)
            flyer = flask.request.files.get('flyer')
            remove = flask.request.form.get('remove_poster') == 'yes'
            if remove and flyer and flyer.filename:
                raise ValueError('Choose either a replacement poster or Remove poster.')
            url = event['graphic_link'] if event else None
            public_id = event['graphic_public_id'] if event else None
            if flyer and flyer.filename:
                url, public_id = posters.upload(flyer)
                uploaded_id = public_id
            elif remove:
                url, public_id = None, None
            args = [values[key] for key in ('date', 'start_time', 'end_time', 'title', 'description', 'location')]
            try:
                if event:
                    database.update_event(event['event_id'], *args, url, public_id)
                    event_id = event['event_id']
                else:
                    event_id = database.add_event(*args, url, public_id)
            except Exception:
                if uploaded_id:
                    posters.delete(uploaded_id)
                raise
            # Delete the old asset only after its replacement is saved successfully.
            if event and event['graphic_public_id'] and event['graphic_public_id'] != public_id:
                if not posters.delete(event['graphic_public_id']):
                    flask.flash('Event saved. The old poster could not be removed from storage; an administrator must retry cleanup.')
            flask.flash('Event saved.')
            return flask.redirect(flask.url_for('events.admin_event_detail', event_id=event_id))
        except ValueError as error:
            flask.flash(str(error))
            status = 400
        except posters.PosterServiceError as error:
            flask.flash(str(error))
            status = 502
    return flask.render_template('event-management/admin/create_event.html', event=event, values=values), status


def _validate_event(values):
    if not values['title'] or not values['location']:
        raise ValueError('Title and location are required.')
    if len(values['title']) > 200 or len(values['location']) > 300 or len(values['description']) > 10000:
        raise ValueError('Use a title under 200 characters, location under 300, and description under 10,000.')
    try:
        datetime.date.fromisoformat(values['date'])
        start = datetime.time.fromisoformat(values['start_time'])
        end = datetime.time.fromisoformat(values['end_time'])
        if start.tzinfo or end.tzinfo or end <= start:
            raise ValueError
    except ValueError:
        raise ValueError('Enter a valid date and times, with the end time after the start time.') from None


@bp.get('/admin/events/<int:event_id>')
def admin_event_detail(event_id):
    return flask.render_template('event-management/admin/event_details.html', event=_event_or_404(event_id))


@bp.get('/admin/events/<int:event_id>/attendees')
def admin_attendees(event_id):
    _event_or_404(event_id)
    members = database.get_attendees(event_id)
    return flask.render_template('event-management/admin/attendees.html', event_id=event_id, members=members,
        going=sum(m['status'] == 'Going' for m in members),
        pending=sum(m['status'] == 'Pending' for m in members),
        not_going=sum(m['status'] == 'Not Going' for m in members))


@bp.get('/admin/members')
def members():
    return flask.render_template('event-management/admin/members.html', members=database.get_members())


@bp.post('/admin/members/<int:user_id>/membership')
def update_membership(user_id):
    action = flask.request.form.get('action')
    if action not in ('approve', 'decline', 'revoke'):
        flask.abort(400, 'Choose a valid membership action.')
    if not database.set_membership(user_id, action == 'approve'):
        flask.abort(404, 'No eligible volunteer account was found.')
    flask.flash('Membership approved.' if action == 'approve' else
                ('Membership declined.' if action == 'decline' else 'Membership access revoked.'))
    return flask.redirect(flask.url_for('events.members'))


@bp.get('/member/events')
def member_events():
    user_id = auth.get_user()['user_id']
    registered, other = [], []
    for event in database.get_events():
        (registered if database.get_rsvp(user_id, event['event_id']) else other).append(event)
    return flask.render_template('event-management/member/events.html', registered_events=registered, other_events=other)


@bp.get('/member/events/<int:event_id>')
def member_event_detail(event_id):
    return flask.render_template('event-management/member/event_details.html', event=_event_or_404(event_id),
        rsvp=database.get_rsvp(auth.get_user()['user_id'], event_id))


@bp.post('/member/events/<int:event_id>/rsvp')
def rsvp(event_id):
    _event_or_404(event_id)
    response = flask.request.form.get('response')
    if response not in ('going', 'not_going'):
        flask.abort(400, 'Choose Going or Not Going.')
    database.set_rsvp(auth.get_user()['user_id'], event_id, response == 'going')
    flask.flash('Your RSVP has been saved.')
    return flask.redirect(flask.url_for('events.member_event_detail', event_id=event_id))


@bp.get('/member/hours')
def member_hours():
    records = database.get_hours(auth.get_user()['user_id'], '0001-01-01', '9999-12-31')
    return flask.render_template('event-management/member/hours.html', records=records,
                                 total=sum(record['hours'] or 0 for record in records))
