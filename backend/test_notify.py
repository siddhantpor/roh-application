"""Tests for the notification stuff. Database and smtp2go calls are mocked."""
import os
import re
import unittest
from unittest.mock import DEFAULT, patch

from flask import redirect

with patch.dict(os.environ, {
    'APP_SECRET_KEY': 'test-only-key',
    'DATABASE_URL': 'postgresql://test:test@database.invalid/unused',
    'AUTH0_DOMAIN': 'test.auth0.com', 'AUTH0_CLIENT_ID': 'test-client',
    'AUTH0_CLIENT_SECRET': 'test-secret',
}):
    from app import app
import auth
import databasepostgresql as database
import notify


class NotifyTests(unittest.TestCase):
    def setUp(self):
        queries = ('get_account', 'get_event', 'get_events', 'get_rsvps_for_user', 'add_rsvp',
                   'get_notify_prefs', 'set_notify_prefs', 'get_members_to_notify',
                   'get_rsvped_to_notify', 'get_reminders_due', 'add_reminder_sent',
                   'set_membership', 'get_members', 'update_event', 'get_checkin', 'get_checkout')
        patcher = patch.multiple(database, **dict.fromkeys(queries, DEFAULT))
        self.db = patcher.start()
        self.addCleanup(patcher.stop)
        original_config = app.config.copy()
        self.addCleanup(app.config.update, original_config)
        app.config.update({
            'TESTING': True, 'WTF_CSRF_ENABLED': True, 'SESSION_COOKIE_SECURE': False,
            'SMTP2GO_API_KEY': 'key', 'NOTIFY_FROM': 'roh@example.com', 'TASKS_TOKEN': 'tok',
        })
        self.client = app.test_client()
        auth_client = patch.object(auth.oauth, 'auth0')
        auth_client.start()
        self.addCleanup(auth_client.stop)
        # don't let the lazy check fire during tests
        notify._last_lazy_check = float('inf')
        self.addCleanup(setattr, notify, '_last_lazy_check', 0.0)
        self.real_send_email = notify.send_email
        sent = patch.object(notify, 'send_email', return_value=True)
        self.send_email = sent.start()
        self.addCleanup(sent.stop)

        self.account = dict(user_id=1, username='auth0|member', auth0_sub='auth0|member',
                            email='member@example.com', display_name='Member',
                            is_admin=False, approved=True, pending=False)
        self.event = dict(event_id=1, event_date='2026-12-01', start_time='09:00',
                          end_time='12:00', event_title='Park Cleanup', event_locat='Park',
                          event_descrip='Help clean up.', graphic_link=None,
                          graphic_public_id=None, checkin_code='ABC123', checkout_code='XYZ789',
                          attending=0)
        self.prefs = dict(phone='', notify_new_event=True, notify_rsvp=True,
                          notify_changes=True, notify_reminder=True, notify_sms=False)
        self.db['get_account'].return_value = self.account
        self.db['get_event'].return_value = self.event
        self.db['get_events'].return_value = [self.event]
        self.db['get_rsvps_for_user'].return_value = {}
        self.db['get_notify_prefs'].return_value = self.prefs
        self.db['get_members'].return_value = []
        self.db['get_checkin'].return_value = None
        self.db['get_checkout'].return_value = None
        self.db['set_membership'].return_value = True

    def sign_in(self, **values):
        self.account.update(values)
        with self.client.session_transaction() as session:
            session.permanent = True
            session.update(user_id=1, auth0_sub='auth0|member')

    def post(self, path, **values):
        page = self.client.get('/my-profile')
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data)[1].decode()
        response = self.client.post(path, data={'csrf_token': token, **values})
        self.addCleanup(response.request.environ['wsgi.input'].close)
        return response

    def test_profile_shows_prefs(self):
        self.sign_in()
        self.prefs['notify_rsvp'] = False
        self.prefs['phone'] = '609-555-0100'
        page = self.client.get('/my-profile').data
        self.assertIn(b'name="notify_new_event" checked', page)
        self.assertIn(b'name="notify_rsvp" >', page)
        self.assertIn(b'609-555-0100', page)

    def test_save_prefs(self):
        self.sign_in()
        response = self.post('/my-profile/notifications', notify_new_event='on',
                             notify_reminder='on', notify_sms='on', phone='(609) 555-0100')
        self.assertEqual(response.status_code, 302)
        self.db['set_notify_prefs'].assert_called_once_with(1, '(609) 555-0100', {
            'notify_new_event': True, 'notify_rsvp': False, 'notify_changes': False,
            'notify_reminder': True, 'notify_sms': True})

    def test_sms_off_without_phone_and_bad_phone_rejected(self):
        self.sign_in()
        self.post('/my-profile/notifications', notify_sms='on', phone='')
        self.assertFalse(self.db['set_notify_prefs'].call_args[0][2]['notify_sms'])
        self.db['set_notify_prefs'].reset_mock()
        self.post('/my-profile/notifications', phone='12')
        self.db['set_notify_prefs'].assert_not_called()

    def test_approval_email(self):
        self.sign_in(is_admin=True)
        self.post('/admin/members/1/membership', action='approve')
        self.send_email.assert_called_once()
        self.assertEqual(self.send_email.call_args[0][0], 'member@example.com')
        self.assertIn('approved', self.send_email.call_args[0][1])
        self.send_email.reset_mock()
        self.post('/admin/members/1/membership', action='decline')
        self.send_email.assert_not_called()

    def test_rsvp_email_respects_checkbox(self):
        self.sign_in()
        self.post('/member/events/1/rsvp', rsvp='yes')
        self.assertEqual(self.send_email.call_count, 1)
        self.assertIn('Park Cleanup', self.send_email.call_args[0][1])
        self.prefs['notify_rsvp'] = False
        self.post('/member/events/1/rsvp', rsvp='yes')
        self.assertEqual(self.send_email.call_count, 1)
        self.post('/member/events/1/rsvp', rsvp='no')
        self.assertEqual(self.send_email.call_count, 1)

    def test_new_event_and_change_emails(self):
        people = [dict(user_id=2, name='A', email='a@example.com', phone='', notify_sms=False),
                  dict(user_id=3, name='B', email='b@example.com', phone='', notify_sms=False)]
        self.db['get_members_to_notify'].return_value = people
        self.db['get_rsvped_to_notify'].return_value = people[:1]
        with app.test_request_context():
            notify.new_event(1)
            self.assertEqual(self.send_email.call_count, 2)
            self.db['get_members_to_notify'].assert_called_with('notify_new_event')
            notify.event_changed(1)
            self.assertEqual(self.send_email.call_count, 3)
            self.db['get_rsvped_to_notify'].assert_called_with(1, 'notify_changes')

    def test_reminder_route_needs_token(self):
        self.db['get_reminders_due'].return_value = [dict(
            user_id=1, name='Member', email='member@example.com', phone='', notify_sms=False,
            event=dict(event_id=1, event_title='Park Cleanup', event_date='2026-12-01',
                       start_time='09:00', event_locat='Park'))]
        self.assertEqual(self.client.post('/tasks/send-reminders').status_code, 403)
        self.assertEqual(self.client.post('/tasks/send-reminders',
                                          headers={'X-Tasks-Token': 'wrong'}).status_code, 403)
        response = self.client.post('/tasks/send-reminders', headers={'X-Tasks-Token': 'tok'})
        self.assertEqual(response.get_json(), {'sent': 1})
        self.db['add_reminder_sent'].assert_called_once()
        self.assertEqual(self.db['add_reminder_sent'].call_args[0][:2], (1, 1))

    def test_send_email_calls_smtp2go_only_with_key(self):
        with app.test_request_context(), patch.object(notify.requests, 'post') as post:
            self.assertTrue(self.real_send_email('x@example.com', 'subj', 'body'))
            self.assertEqual(post.call_args[0][0], notify.SMTP2GO_URL)
            self.assertEqual(post.call_args[1]['headers']['X-Smtp2go-Api-Key'], 'key')
            self.assertEqual(post.call_args[1]['json']['to'], ['x@example.com'])
            post.reset_mock()
            app.config['SMTP2GO_API_KEY'] = ''
            self.assertFalse(self.real_send_email('x@example.com', 'subj', 'body'))
            post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
