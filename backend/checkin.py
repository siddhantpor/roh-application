#!/usr/bin/env python

#-----------------------------------------------------------------------
# checkin.py
# Routes for the check-in / check-out / hours subsystem.
#
# Written as init(app) + app.add_url_rule(...) in the style of
# Dondero's auth.py, so these routes can be registered on ANY Flask
# app: runcheckin.py (standalone, for developing this subsystem) now,
# the team's app.py at integration time. Each handler follows his
# add() / handle_add() pattern from penny.py: authenticate, authorize,
# read the form, validate, call database, then render a page (GET) or
# redirect back to one (POST).
#
# Screens (Figma): S10 member check-in page (three states: not checked
# in / checked in / checked out), S6 admin codes, S11a admin review
# hours list, S11b admin edit one member's hours.
#
# For now check-in can happen any time. Please change later
# (Tanisha: check-in should open ~15 min before event start).
#
# For now anyone logged in who knows the code can check in, RSVP or
# not. Need to change if we want to require an RSVP of "going": add
#     elif database.get_rsvp(user_id, event_id) != True:
#         msg = 'You have not RSVP\'d to this event.'
# to the chain in handle_member_checkin, before the add_checkin call.
#
# For now "Reason for change" on the edit page is shown but not
# stored (no column for it). Need to change if we want to keep it.
#-----------------------------------------------------------------------

import datetime
import zoneinfo
import secrets
import flask
import string 
import auth
import database

#-----------------------------------------------------------------------
# Design choices (see README.md, "Design choices")
#-----------------------------------------------------------------------

# Times are stored in UTC (ISO 8601 text) and shown to people in this
# zone. Change here if the org moves.
LOCAL_TIMEZONE = zoneinfo.ZoneInfo('America/New_York')

# Codes: 6 chars from this alphabet (no 0/O or 1/I, which are easy to
# misread when an admin reads a code out loud).
CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
CODE_LENGTH = 6

DIGITS = string.digits

#-----------------------------------------------------------------------
# Route registration
#-----------------------------------------------------------------------

def init(app):

    # Member side (S10)
    app.add_url_rule('/member/events/<int:event_id>/checkin',
        'member_checkin', member_checkin, methods=['GET'])
    app.add_url_rule('/member/events/<int:event_id>/handlecheckin',
        'handle_member_checkin', handle_member_checkin, methods=['POST'])
    app.add_url_rule('/member/events/<int:event_id>/handlecheckout',
        'handle_member_checkout', handle_member_checkout,
        methods=['POST'])

    # Admin side (S6, S11a, S11b)
    app.add_url_rule('/admin/events/<int:event_id>/codes',
        'admin_codes', admin_codes, methods=['GET'])
    app.add_url_rule('/admin/events/<int:event_id>/handlecodes',
        'handle_admin_codes', handle_admin_codes, methods=['POST'])
    app.add_url_rule('/admin/events/<int:event_id>/hours',
        'admin_hours', admin_hours, methods=['GET'])
    app.add_url_rule('/admin/events/<int:event_id>/handleapprove',
        'handle_admin_approve', handle_admin_approve, methods=['POST'])
    app.add_url_rule('/admin/events/<int:event_id>/handleapproveall',
        'handle_admin_approve_all', handle_admin_approve_all,
        methods=['POST'])
    app.add_url_rule('/admin/events/<int:event_id>/hours/<int:user_id>',
        'admin_edit_hours', admin_edit_hours, methods=['GET'])
    app.add_url_rule(
        '/admin/events/<int:event_id>/hours/<int:user_id>/handleedit',
        'handle_admin_edit_hours', handle_admin_edit_hours,
        methods=['POST'])

#-----------------------------------------------------------------------
# Member: one page, three states (S10)
#-----------------------------------------------------------------------

def member_checkin(event_id):

    auth.authenticate()
    username = auth.get_username()
    user_id = database.get_user_id(username)

    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)

    checkin = database.get_checkin(user_id, event_id)
    checkout = database.get_checkout(user_id, event_id)

    # Which of the three states the page is in.
    if checkin is None:
        state = 'not_checked_in'
    elif checkout is None:
        state = 'checked_in'
    else:
        state = 'checked_out'

    # Strings the template shows. All times local.
    checkin_display = None
    checkout_display = None
    duration_display = None
    if checkin is not None:
        checkin_display = _format_time(checkin['time'])
        if checkout is None:
            duration_display = _format_duration(
                _hours_between(checkin['time'], _now_utc()))
        else:
            checkout_display = _format_time(checkout['time'])
            duration_display = _format_duration(
                _hours_between(checkin['time'], checkout['time']))

    msg = flask.request.args.get('msg')
    if msg is None:
        msg = ''

    html_code = flask.render_template('check-in/member/checkin.html',
        username=username, event=event, state=state,
        checkin_display=checkin_display,
        checkout_display=checkout_display,
        duration_display=duration_display,
        event_when=_format_event_when(event), msg=msg)
    response = flask.make_response(html_code)
    return response

#-----------------------------------------------------------------------

def handle_member_checkin(event_id):

    auth.authenticate()
    username = auth.get_username()
    user_id = database.get_user_id(username)

    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)

    code = flask.request.form.get('code')
    if (code is None) or (code.strip() == ''):
        msg = 'Enter the check-in code.'
    elif event['checkin_code'] is None:
        msg = ('This event has no check-in code yet. '
            'Ask a director.')
    elif _clean_code(code) != event['checkin_code']:
        msg = (f'That code doesn\'t match {event["event_title"]}. '
            'Check the spelling, or ask a director.')
    else:
        successful = database.add_checkin(user_id, event_id, _now_utc())
        if not successful:
            msg = 'You already checked in to this event.'
        else:
            msg = ''

    # Post/redirect/get: the page re-reads the database and shows the
    # right state; a browser refresh won't resubmit the form.
    return flask.redirect(_member_url(event_id, msg))

#-----------------------------------------------------------------------

def handle_member_checkout(event_id):

    auth.authenticate()
    username = auth.get_username()
    user_id = database.get_user_id(username)

    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)

    code = flask.request.form.get('code')
    if (code is None) or (code.strip() == ''):
        msg = 'Enter the check-out code.'
    elif event['checkout_code'] is None:
        msg = ('This event has no check-out code yet. '
            'Ask a director.')
    elif _clean_code(code) != event['checkout_code']:
        msg = (f'That code doesn\'t match {event["event_title"]}. '
            'Check the spelling, or ask a director.')
    elif database.get_checkin(user_id, event_id) is None:
        msg = 'You never checked in to this event.'
    else:
        successful = database.add_checkout(user_id, event_id, _now_utc())
        if not successful:
            msg = 'You already checked out of this event.'
        else:
            msg = ''

    return flask.redirect(_member_url(event_id, msg))

#-----------------------------------------------------------------------
# Admin: codes (S6)
#-----------------------------------------------------------------------

def admin_codes(event_id):

    auth.authenticate()
    username = auth.get_username()
    if not database.is_admin(username):
        return _not_authorized()

    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)

    html_code = flask.render_template('check-in/admin/codes.html',
        username=username, event=event,
        event_when=_format_event_when(event))
    response = flask.make_response(html_code)
    return response

#-----------------------------------------------------------------------

def handle_admin_codes(event_id):

    auth.authenticate()
    username = auth.get_username()
    if not database.is_admin(username):
        return _not_authorized()

    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)

    # (Re)generating replaces both codes. Members who already checked
    # in keep their records; only future entries need the new codes.
    checkin_code = _generate_code()
    checkout_code = _generate_code()
    while checkout_code == checkin_code:
        checkout_code = _generate_code()
    database.set_event_codes(event_id, checkin_code, checkout_code)

    return flask.redirect(flask.url_for('admin_codes', event_id=event_id))

#-----------------------------------------------------------------------
# Admin: review hours list (S11a)
#-----------------------------------------------------------------------

def admin_hours(event_id):

    auth.authenticate()
    username = auth.get_username()
    if not database.is_admin(username):
        return _not_authorized()

    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)

    # Split into the two sections on S11a. "Ready" = has a check-out
    # (so hours can be computed); "still checked in" = no check-out.
    ready = []
    still_in = []
    for record in database.get_attendance(event_id):
        _add_display_fields(record)
        if record['checkout_time'] is None:
            still_in.append(record)
        else:
            ready.append(record)
    unapproved = [r for r in ready if not r['approved']]

    msg = flask.request.args.get('msg')
    if msg is None:
        msg = ''

    html_code = flask.render_template('check-in/admin/hours.html',
        username=username, event=event,
        event_when=_format_event_when(event),
        ready=ready, still_in=still_in,
        unapproved_count=len(unapproved), msg=msg)
    response = flask.make_response(html_code)
    return response

#-----------------------------------------------------------------------

def handle_admin_approve(event_id):

    # The green "Approve" pill on one row: approve as-is, no edits.

    auth.authenticate()
    username = auth.get_username()
    if not database.is_admin(username):
        return _not_authorized()

    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)

    user_id = flask.request.form.get('user_id')
    record = None
    if (user_id is not None) and user_id.isdigit():
        record = _get_attendance_record(event_id, int(user_id))

    if record is None:
        msg = 'The approval was unsuccessful: no such entry'
    elif record['checkout_time'] is None:
        msg = ('The approval was unsuccessful: still checked in '
            '(no check-out time)')
    else:
        database.update_attendance(record['user_id'], event_id,
            record['checkin_time'], record['checkout_time'], True)
        msg = f'Approved {record["display_name"]}'

    return flask.redirect(
        flask.url_for('admin_hours', event_id=event_id, msg=msg))

#-----------------------------------------------------------------------

def handle_admin_approve_all(event_id):

    # "Approve all N": every ready, not-yet-approved row.

    auth.authenticate()
    username = auth.get_username()
    if not database.is_admin(username):
        return _not_authorized()

    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)

    count = 0
    for record in database.get_attendance(event_id):
        if record['checkout_time'] is None:
            continue
        if record['checkin_approved'] and record['checkout_approved']:
            continue
        database.update_attendance(record['user_id'], event_id,
            record['checkin_time'], record['checkout_time'], True)
        count += 1

    msg = f'Approved {count} entries'
    return flask.redirect(
        flask.url_for('admin_hours', event_id=event_id, msg=msg))

#-----------------------------------------------------------------------
# Admin: edit one member's hours (S11b)
#-----------------------------------------------------------------------

def admin_edit_hours(event_id, user_id):

    auth.authenticate()
    username = auth.get_username()
    if not database.is_admin(username):
        return _not_authorized()

    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)

    record = _get_attendance_record(event_id, user_id)
    if record is None:
        flask.abort(404)
    _add_display_fields(record)

    msg = flask.request.args.get('msg')
    if msg is None:
        msg = ''

    html_code = flask.render_template('check-in/admin/edit_hours.html',
        username=username, event=event,
        event_when=_format_event_when(event), record=record, msg=msg)
    response = flask.make_response(html_code)
    return response

#-----------------------------------------------------------------------

def handle_admin_edit_hours(event_id, user_id):

    # Two buttons on S11b post here: action=save ("Save & Approve")
    # and action=reject ("Reject entry").

    auth.authenticate()
    username = auth.get_username()
    if not database.is_admin(username):
        return _not_authorized()

    event = database.get_event(event_id)
    if event is None:
        flask.abort(404)

    record = _get_attendance_record(event_id, user_id)
    if record is None:
        flask.abort(404)

    action = flask.request.form.get('action')

    if action == 'reject':
        # Delete both records: the member checked in by mistake, or
        # the entry can't be trusted. They can check in again.
        database.update_attendance(user_id, event_id, None, None, False)
        msg = f'Rejected {record["display_name"]}\'s entry'
        return flask.redirect(
            flask.url_for('admin_hours', event_id=event_id, msg=msg))

    checkin_local = flask.request.form.get('checkin_time')
    checkout_local = flask.request.form.get('checkout_time')
    reason = flask.request.form.get('reason')   # shown, not stored (yet)

    checkin_time = _to_utc(checkin_local)
    checkout_time = _to_utc(checkout_local)

    if checkin_time is None:
        msg = 'Enter a valid check-in time.'
    elif checkout_time is None:
        msg = 'Enter a valid check-out time.'
    elif checkout_time < checkin_time:
        msg = 'Check-out is before check-in.'
    elif (reason is None) or (reason.strip() == ''):
        msg = 'Enter a reason for the change.'
    else:
        database.update_attendance(user_id, event_id,
            checkin_time, checkout_time, True)
        msg = f'Saved and approved {record["display_name"]}'
        return flask.redirect(
            flask.url_for('admin_hours', event_id=event_id, msg=msg))

    return flask.redirect(flask.url_for('admin_edit_hours',
        event_id=event_id, user_id=user_id, msg=msg))

#-----------------------------------------------------------------------
# Helpers
#-----------------------------------------------------------------------

def _not_authorized():

    html_code = 'You are not authorized to view this page.'
    response = flask.make_response(html_code)
    return response

#-----------------------------------------------------------------------

def _member_url(event_id, msg):

    if msg == '':
        return flask.url_for('member_checkin', event_id=event_id)
    return flask.url_for('member_checkin', event_id=event_id, msg=msg)

#-----------------------------------------------------------------------

def _get_attendance_record(event_id, user_id):

    for record in database.get_attendance(event_id):
        if record['user_id'] == user_id:
            return record
    return None

#-----------------------------------------------------------------------

def _add_display_fields(record):

    # Local-time strings for the admin pages. 'approved' means both
    # halves are approved.
    record['checkin_display'] = _format_time(record['checkin_time'])
    record['checkout_display'] = _format_time(record['checkout_time'])
    record['checkin_input'] = _to_local(record['checkin_time'])
    record['checkout_input'] = _to_local(record['checkout_time'])
    record['duration_display'] = _format_duration(record['hours'])
    record['approved'] = (record['checkin_approved']
        and record['checkout_approved'])
    return record

#-----------------------------------------------------------------------

def load_words(path):
    words = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2:
                words.append(parts[1])
    return words

WORDS = load_words("eff_large_wordlist.txt")

#-----------------------------------------------------------------------

def _generate_code():
    word = secrets.choice(WORDS)
    digits = ''.join(secrets.choice(DIGITS) for _ in range(3))
    return f"{word}{digits}"

#-----------------------------------------------------------------------

def _clean_code(code):

    # Members type codes on phones: ignore case and spaces.
    return code.strip().upper().replace(' ', '')

#-----------------------------------------------------------------------

def _now_utc():

    # ISO 8601, seconds precision, no tz suffix: matches the seed data
    # in roh.sql, e.g. '2026-11-07T14:02:00'.
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.replace(microsecond=0, tzinfo=None).isoformat()

#-----------------------------------------------------------------------

def _hours_between(utc_a, utc_b):

    # Same rule as database._hours_between, kept here for "time so far"
    # (check-in to now), which the database never sees.
    if utc_a is None or utc_b is None:
        return None
    seconds = (datetime.datetime.fromisoformat(utc_b)
        - datetime.datetime.fromisoformat(utc_a)).total_seconds()
    if seconds < 0:
        return None
    return round(seconds / 3600, 2)

#-----------------------------------------------------------------------

def _to_local_datetime(utc_text):

    utc = datetime.datetime.fromisoformat(utc_text).replace(
        tzinfo=datetime.timezone.utc)
    return utc.astimezone(LOCAL_TIMEZONE)

#-----------------------------------------------------------------------

def _to_local(utc_text):

    # '2026-11-07T14:02:00' (UTC) -> '2026-11-07T09:02' (local), which
    # is the format an <input type="datetime-local"> wants. None -> ''.
    if utc_text is None:
        return ''
    return _to_local_datetime(utc_text).strftime('%Y-%m-%dT%H:%M')

#-----------------------------------------------------------------------

def _to_utc(local_text):

    # Inverse of _to_local, for admin-edited times. Blank -> None.
    # Unparseable -> None (callers check).
    if (local_text is None) or (local_text.strip() == ''):
        return None
    try:
        local = datetime.datetime.fromisoformat(local_text.strip())
    except ValueError:
        return None
    local = local.replace(tzinfo=LOCAL_TIMEZONE)
    utc = local.astimezone(datetime.timezone.utc)
    return utc.replace(microsecond=0, tzinfo=None).isoformat()

#-----------------------------------------------------------------------

def _format_time(utc_text):

    # '2026-11-07T14:02:00' -> '9:02 AM' (local), as on the Figma.
    if utc_text is None:
        return None
    local = _to_local_datetime(utc_text)
    return local.strftime('%I:%M %p').lstrip('0')

#-----------------------------------------------------------------------

def _format_duration(hours):

    # 1.2 -> '1h 12m', as on the Figma. None -> None.
    if hours is None:
        return None
    minutes = int(round(hours * 60))
    return f'{minutes // 60}h {minutes % 60:02d}m'

#-----------------------------------------------------------------------

def _format_event_when(event):

    # '2026-11-07' + '09:00' -> 'Sat, Nov 7, 9:00 AM', as on the Figma.
    try:
        day = datetime.date.fromisoformat(event['event_date'])
    except (TypeError, ValueError):
        return event['event_date']
    text = day.strftime('%a, %b ') + str(day.day)
    if event['start_time']:
        try:
            start = datetime.time.fromisoformat(event['start_time'])
            text += ', ' + start.strftime('%I:%M %p').lstrip('0')
        except ValueError:
            pass
    return text
