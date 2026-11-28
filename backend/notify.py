"""Email (and someday SMS) notifications for volunteers.

Email goes out through SMTP2GO's http api. If SMTP2GO_API_KEY isn't set
(local dev, teammates' machines) nothing is sent and we just log what
would have gone out. SMS is a stub for now, see send_sms.
"""
import datetime
import hmac
import threading
import zoneinfo

import flask
import requests

import auth
import databasepostgresql as database
import utils

SMTP2GO_URL = 'https://api.smtp2go.com/v3/email/send'
LOCAL_TIMEZONE = zoneinfo.ZoneInfo('America/New_York')
REMINDER_HOURS = 24
# admin digest goes out monday mornings (0 = monday)
DIGEST_WEEKDAY = 0
DIGEST_HOUR = 8
# how often the lazy check in before_request is allowed to actually run
LAZY_CHECK_SECONDS = 30 * 60
_last_lazy_check = 0.0
_lazy_lock = threading.Lock()


def init(app):
    app.config['SMTP2GO_API_KEY'] = app.config.get('SMTP2GO_API_KEY', '')
    app.config['NOTIFY_FROM'] = app.config.get('NOTIFY_FROM', '')
    app.config['TASKS_TOKEN'] = app.config.get('TASKS_TOKEN', '')
    app.add_url_rule('/my-profile/notifications', view_func=handle_prefs, methods=['POST'])
    app.add_url_rule('/tasks/send-reminders', view_func=handle_send_reminders, methods=['POST'])
    # it's called by curl, not a form, so no csrf token. the token header is the check instead
    app.extensions['csrf'].exempt(handle_send_reminders)
    app.before_request(_lazy_reminder_check)


def prefs_for_profile(user_id):
    # used by the my profile page
    return database.get_notify_prefs(user_id)


def handle_prefs():
    auth.authenticate()
    user_id = auth.get_user()['user_id']
    phone = flask.request.form.get('phone', '').strip()
    if phone and not _looks_like_phone(phone):
        flask.flash('That phone number does not look right.')
        return flask.redirect(flask.url_for('my_profile'))
    flags = {flag: flask.request.form.get(flag) == 'on' for flag in database.NOTIFY_FLAGS}
    if not phone:
        flags['notify_sms'] = False
    database.set_notify_prefs(user_id, phone, flags)
    if auth.get_user()['is_admin']:
        admin_flags = {flag: flask.request.form.get(flag) == 'on' for flag in database.ADMIN_FLAGS}
        database.set_admin_notify_prefs(user_id, admin_flags)
    flask.flash('Notification settings saved.')
    return flask.redirect(flask.url_for('my_profile'))


def _looks_like_phone(phone):
    digits = ''.join(ch for ch in phone if ch.isdigit())
    return 10 <= len(digits) <= 15

#-----------------------------------------------------------------------

def send_email(to, subject, body):
    # returns True if it was actually sent
    key = flask.current_app.config['SMTP2GO_API_KEY']
    sender = flask.current_app.config['NOTIFY_FROM']
    if not key or not sender:
        flask.current_app.logger.info('email not configured, would send to %s: %s', to, subject)
        return False
    try:
        response = requests.post(SMTP2GO_URL, timeout=10,
            headers={'X-Smtp2go-Api-Key': key, 'Content-Type': 'application/json'},
            json={'sender': sender, 'to': [to], 'subject': subject, 'text_body': body})
        response.raise_for_status()
    except requests.RequestException as ex:
        # a broken email should never break the page the admin is on
        flask.current_app.logger.warning('email to %s failed: %s', to, ex)
        return False
    return True


def send_sms(to, body):
    # TODO: hook up a real provider. Twilio's free trial only lets you send
    # their canned templates to 5 verified numbers so it's useless for us,
    # and SMTP2GO's sms costs money. For now just log it.
    flask.current_app.logger.info('sms not configured, would text %s: %s', to, body)
    return False


def _send(person, subject, body, sms_body=None):
    send_email(person['email'], subject, body)
    if sms_body and person['notify_sms'] and person['phone']:
        send_sms(person['phone'], sms_body)

#-----------------------------------------------------------------------

def _when(event):
    return utils.format_date(event['event_date']) + ' at ' + utils.format_time(event['start_time'])


def _event_lines(event):
    lines = [event['event_title'], 'When: ' + _when(event)]
    if event.get('event_locat'):
        lines.append('Where: ' + event['event_locat'])
    return '\n'.join(lines)


def _events_link():
    return flask.url_for('member_events', _external=True)

#-----------------------------------------------------------------------

def account_approved(user_id):
    # always sent, there's no checkbox for this one. only happens once since
    # the admin page only lets you approve a pending account
    account = database.get_account(user_id)
    if account is None or not account['email']:
        return
    name = account['display_name'] or 'there'
    body = ('Hi ' + name + ',\n\n'
            'Your Rays of Hope volunteer account has been approved. You can now '
            'RSVP to events and check in to log your hours.\n\n' + _events_link() + '\n')
    send_email(account['email'], 'Your Rays of Hope account is approved', body)


def new_event(event_id):
    event = database.get_event(event_id)
    if event is None:
        return
    body = ('A new volunteer event was just posted:\n\n' + _event_lines(event) +
            '\n\nRSVP here: ' + _events_link() + '\n')
    for person in database.get_members_to_notify('notify_new_event'):
        send_email(person['email'], 'New event: ' + event['event_title'], body)


def event_changed(event_id):
    # only people who said yes to this event
    event = database.get_event(event_id)
    if event is None:
        return
    body = ('An event you RSVP\'d to was updated. Here are the current details:\n\n' +
            _event_lines(event) + '\n\n' + _events_link() + '\n')
    for person in database.get_rsvped_to_notify(event_id, 'notify_changes'):
        send_email(person['email'], 'Updated: ' + event['event_title'], body)


def rsvp_confirmed(user_id, event_id):
    prefs = database.get_notify_prefs(user_id)
    account = database.get_account(user_id)
    event = database.get_event(event_id)
    if not prefs or not prefs['notify_rsvp'] or account is None or event is None:
        return
    body = ('Thanks for signing up! You RSVP\'d yes to:\n\n' + _event_lines(event) +
            '\n\nWhen you get there, ask the coordinator for the check-in code and '
            'enter it on the events page to log your hours.\n' + _events_link() + '\n')
    send_email(account['email'], 'You\'re signed up for ' + event['event_title'], body)


#-----------------------------------------------------------------------
# Reminders. Render's free tier has no cron, so there's a route that a
# github actions workflow pings every hour, and as a backup the app
# checks on its own every so often when someone loads a page.
#-----------------------------------------------------------------------

def send_due_reminders():
    # anything starting in the next REMINDER_HOURS that we haven't reminded yet.
    # returns how many people got one.
    now = datetime.datetime.now(LOCAL_TIMEZONE).replace(tzinfo=None)
    until = now + datetime.timedelta(hours=REMINDER_HOURS)
    count = 0
    for person in database.get_reminders_due(now, until):
        event = person['event']
        body = ('Reminder: you RSVP\'d to an event that starts soon.\n\n' +
                _event_lines(event) + '\n\nSee you there!\n' + _events_link() + '\n')
        sms = 'Rays of Hope reminder: ' + event['event_title'] + ' is ' + _when(event)
        _send(person, 'Tomorrow: ' + event['event_title'], body, sms)
        database.add_reminder_sent(person['user_id'], event['event_id'],
                                   datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None))
        count += 1
    return count


def handle_send_reminders():
    token = flask.current_app.config['TASKS_TOKEN']
    given = flask.request.headers.get('X-Tasks-Token', '')
    if not token or not hmac.compare_digest(token, given):
        flask.abort(403)
    return {'sent': send_due_reminders(), 'digest': send_admin_digest_if_due()}


def _lazy_reminder_check():
    global _last_lazy_check
    if flask.request.path.startswith('/static') or flask.request.path.startswith('/tasks'):
        return
    now = datetime.datetime.now().timestamp()
    with _lazy_lock:
        if now - _last_lazy_check < LAZY_CHECK_SECONDS:
            return
        _last_lazy_check = now
    try:
        send_due_reminders()
        send_admin_digest_if_due()
    except Exception as ex:
        # never let this take down a normal page
        flask.current_app.logger.warning('reminder check failed: %s', ex)

#-----------------------------------------------------------------------
# Admin side
#-----------------------------------------------------------------------

def _members_link():
    return flask.url_for('members', _external=True)


def new_pending_account(user_id):
    # a volunteer finished signing up and is waiting on the members page
    account = database.get_account(user_id)
    if account is None or not account['pending']:
        return
    body = (account['display_name'] + ' (' + (account['email'] or 'no email') + ') just '
            'signed up and is waiting for approval.\n\nReview here: ' + _members_link() + '\n')
    for admin in database.get_admins_to_notify('notify_admin_signup'):
        send_email(admin['email'], 'New volunteer waiting for approval: ' + account['display_name'],
                   body)


def hours_need_review(user_id, event_id):
    # someone just checked out. off by default for admins, it's a lot of mail
    account = database.get_account(user_id)
    event = database.get_event(event_id)
    if account is None or event is None:
        return
    body = (account['display_name'] + ' checked out of ' + event['event_title'] + ' (' +
            _when(event) + ') and their hours are waiting for review.\n\n' +
            flask.url_for('admin_volunteer_hours', _external=True) + '\n')
    for admin in database.get_admins_to_notify('notify_admin_hours'):
        send_email(admin['email'], 'Hours to review: ' + account['display_name'], body)


#-----------------------------------------------------------------------
# Weekly admin digest
#-----------------------------------------------------------------------

def _last_digest_due(now):
    # most recent monday 8am that is not in the future
    due = now.replace(hour=DIGEST_HOUR, minute=0, second=0, microsecond=0)
    due -= datetime.timedelta(days=(now.weekday() - DIGEST_WEEKDAY) % 7)
    if due > now:
        due -= datetime.timedelta(days=7)
    return due


def send_admin_digest_if_due():
    # returns True if it sent one. safe to call as often as you like, task_runs
    # remembers the last time so it only goes once a week even if a monday
    # ping is missed and it catches up on tuesday
    now = datetime.datetime.now(LOCAL_TIMEZONE).replace(tzinfo=None)
    due = _last_digest_due(now)
    last = database.get_task_last_run('admin_digest')
    if last is not None and last >= due:
        return False
    send_admin_digest(due - datetime.timedelta(days=7), due)
    database.set_task_last_run('admin_digest', now)
    return True


def send_admin_digest(since, until):
    # since/until are local naive datetimes, usually a week apart
    since_utc = since.replace(tzinfo=LOCAL_TIMEZONE).astimezone(datetime.timezone.utc).replace(tzinfo=None)
    until_utc = until.replace(tzinfo=LOCAL_TIMEZONE).astimezone(datetime.timezone.utc).replace(tzinfo=None)
    data = database.get_admin_digest(since_utc, until_utc, since.date(), until.date())
    lines = ['Rays of Hope, week of ' + utils.format_date(since.date().isoformat()) + '\n']

    lines.append('NEEDS YOUR ATTENTION')
    if data['pending_accounts']:
        lines.append(str(len(data['pending_accounts'])) + ' volunteer(s) waiting for approval:')
        for a in data['pending_accounts']:
            lines.append('  - ' + a['name'] + ' (' + (a['email'] or '') + ')')
        lines.append('  ' + _members_link())
    else:
        lines.append('No volunteers waiting for approval.')
    if data['pending_hours']:
        lines.append('Hours waiting for review:')
        for h in data['pending_hours']:
            lines.append('  - ' + h['event_title'] + ' (' + utils.format_date(h['event_date']) +
                         '): ' + str(h['people']) + ' volunteer(s)')
        lines.append('  ' + flask.url_for('admin_volunteer_hours', _external=True))
    else:
        lines.append('No hours waiting for review.')

    lines.append('\nLAST WEEK')
    if data['events_held']:
        for e in data['events_held']:
            lines.append('  - ' + e['event_title'] + ' (' + utils.format_date(e['event_date']) +
                         '): ' + str(e['checkins']) + ' checked in')
    else:
        lines.append('  No events.')
    lines.append('  ' + str(data['new_rsvps']) + ' new RSVP(s)')
    if data['new_posts']:
        lines.append('  Community board:')
        for p in data['new_posts']:
            lines.append('    - "' + p['post_title'] + '" by ' + p['author'] + ', ' +
                         str(p['reactions']) + ' reaction(s)')

    lines.append('\nCOMING UP (next 7 days)')
    if data['upcoming']:
        for e in data['upcoming']:
            lines.append('  - ' + e['event_title'] + ', ' + _when(e) + ': ' +
                         str(e['attending']) + ' attending')
    else:
        lines.append('  Nothing scheduled.')

    body = '\n'.join(lines) + '\n'
    for admin in database.get_admins_to_notify():
        send_email(admin['email'], 'Rays of Hope weekly summary', body)
