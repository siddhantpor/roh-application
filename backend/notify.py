"""Email (and someday SMS) notifications for volunteers.

Email goes out through SMTP2GO's http api. If SMTP2GO_API_KEY isn't set
(local dev, teammates' machines) nothing is sent and we just log what
would have gone out. SMS is a stub for now, see send_sms.
"""
import datetime

import flask
import requests

import auth
import databasepostgresql as database
import utils

SMTP2GO_URL = 'https://api.smtp2go.com/v3/email/send'


def init(app):
    app.config['SMTP2GO_API_KEY'] = app.config.get('SMTP2GO_API_KEY', '')
    app.config['NOTIFY_FROM'] = app.config.get('NOTIFY_FROM', '')
    app.add_url_rule('/my-profile/notifications', view_func=handle_prefs, methods=['POST'])


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
