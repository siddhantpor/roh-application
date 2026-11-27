"""Email (and someday SMS) notifications for volunteers.

Email goes out through SMTP2GO's http api. If SMTP2GO_API_KEY isn't set
(local dev, teammates' machines) nothing is sent and we just log what
would have gone out. SMS is a stub for now, see send_sms.
"""
import datetime

import flask
import requests

import databasepostgresql as database
import utils

SMTP2GO_URL = 'https://api.smtp2go.com/v3/email/send'


def init(app):
    app.config['SMTP2GO_API_KEY'] = app.config.get('SMTP2GO_API_KEY', '')
    app.config['NOTIFY_FROM'] = app.config.get('NOTIFY_FROM', '')

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
