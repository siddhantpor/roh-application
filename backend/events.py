"""Existing event pages, admin membership review, and poster forms."""
import datetime

import flask

import databasepostgresql as database
import posters

def init_app(app):
    app.add_url_rule('/admin/events', view_func=admin_events)
    app.add_url_rule('/admin/events/create', view_func=create_event, methods=['GET', 'POST'])
    app.add_url_rule('/admin/events/<int:event_id>/edit', view_func=edit_event, methods=['GET', 'POST'])
    app.add_url_rule('/admin/events/<int:event_id>', view_func=admin_event_detail)
    app.add_url_rule('/admin/events/<int:event_id>/attendees', view_func=admin_attendees)
    app.add_url_rule('/admin/members', view_func=members)
    app.add_url_rule('/admin/members/<int:user_id>/membership',
                     view_func=update_membership, methods=['POST'])
    app.add_url_rule('/member/events', view_func=member_events)
    app.add_url_rule('/member/events/<int:event_id>', view_func=member_event_detail)


def _event_or_404(event_id):
    event = database.get_event(event_id)
    if event is None:
        flask.abort(404, 'That event does not exist.')
    return event


def admin_events():
    return flask.render_template('event-management/admin/events.html',
                                 admin_events=database.get_events())


def create_event():
    return _event_form()


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
            return flask.redirect(flask.url_for('admin_event_detail', event_id=event_id))
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


def admin_event_detail(event_id):
    return flask.render_template('event-management/admin/event_details.html', event=_event_or_404(event_id))


def admin_attendees(event_id):
    _event_or_404(event_id)
    members = []  # Attendee directory remains part of the event-management work.
    return flask.render_template('event-management/admin/attendees.html', event_id=event_id, members=members,
        going=sum(m['status'] == 'Going' for m in members),
        pending=sum(m['status'] == 'Pending' for m in members),
        not_going=sum(m['status'] == 'Not Going' for m in members))


def members():
    return flask.render_template('event-management/admin/members.html', members=database.get_members())


def update_membership(user_id):
    action = flask.request.form.get('action')
    if action not in ('approve', 'decline', 'revoke'):
        flask.abort(400, 'Choose a valid membership action.')
    if not database.set_membership(user_id, action == 'approve'):
        flask.abort(404, 'No eligible volunteer account was found.')
    flask.flash('Membership approved.' if action == 'approve' else
                ('Membership declined.' if action == 'decline' else 'Membership access revoked.'))
    return flask.redirect(flask.url_for('members'))


def member_events():
    return flask.render_template('event-management/member/events.html',
                                 upcoming_events=[], other_events=database.get_events())


def member_event_detail(event_id):
    return flask.render_template('event-management/member/event_details.html',
                                 event=_event_or_404(event_id))
