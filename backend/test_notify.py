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
                   'set_membership', 'get_members', 'update_event', 'get_checkin', 'get_checkout',
                   'get_admins_to_notify', 'set_admin_notify_prefs', 'get_task_last_run',
                   'set_task_last_run', 'get_admin_digest', 'add_checkout', 'set_display_name')
        patcher = patch.multiple(database, **dict.fromkeys(queries, DEFAULT))
        self.db = patcher.start()
        self.addCleanup(patcher.stop)
        original_config = app.config.copy()
        self.addCleanup(app.config.update, original_config)
        app.config.update({
            'TESTING': True, 'WTF_CSRF_ENABLED': True, 'SESSION_COOKIE_SECURE': False,
            'EMAIL_BACKEND': 'smtp2go', 'SMTP2GO_API_KEY': 'key', 'NOTIFY_FROM': 'roh@example.com',
            'TASKS_TOKEN': 'tok',
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
                          notify_changes=True, notify_reminder=True, notify_sms=False,
                          notify_admin_signup=True, notify_admin_hours=False)
        self.admins = [dict(user_id=9, name='Boss', email='boss@example.com', phone='',
                            notify_sms=False)]
        self.db['get_account'].return_value = self.account
        self.db['get_event'].return_value = self.event
        self.db['get_events'].return_value = [self.event]
        self.db['get_rsvps_for_user'].return_value = {}
        self.db['get_notify_prefs'].return_value = self.prefs
        self.db['get_members'].return_value = []
        self.db['get_checkin'].return_value = None
        self.db['get_checkout'].return_value = None
        self.db['set_membership'].return_value = True
        self.db['get_admins_to_notify'].return_value = self.admins
        self.db['get_task_last_run'].return_value = None
        self.db['get_reminders_due'].return_value = []

    def sign_in(self, **values):
        self.account.update(values)
        with self.client.session_transaction() as session:
            session.permanent = True
            session.update(user_id=1, auth0_sub='auth0|member')

    def post(self, path, token_page='/my-profile', **values):
        page = self.client.get(token_page)
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
        self.assertEqual(response.get_json()['sent'], 1)
        self.db['add_reminder_sent'].assert_called_once()
        self.assertEqual(self.db['add_reminder_sent'].call_args[0][:2], (1, 1))

    def test_send_email_uses_gmail_when_configured(self):
        app.config.update({'EMAIL_BACKEND': 'gmail', 'GMAIL_USER': 'roh@gmail.com',
                           'GMAIL_APP_PASSWORD': 'abcd'})
        with app.test_request_context(), patch.object(notify.smtplib, 'SMTP_SSL') as smtp_ssl:
            smtp = smtp_ssl.return_value.__enter__.return_value
            self.assertTrue(self.real_send_email('x@example.com', 'subj', 'body'))
            smtp_ssl.assert_called_once_with('smtp.gmail.com', 465, timeout=15)
            smtp.login.assert_called_once_with('roh@gmail.com', 'abcd')
            msg = smtp.send_message.call_args[0][0]
            self.assertEqual(msg['To'], 'x@example.com')
            self.assertEqual(msg['Subject'], 'subj')
            smtp.login.side_effect = notify.smtplib.SMTPAuthenticationError(535, b'bad')
            self.assertFalse(self.real_send_email('x@example.com', 'subj', 'body'))

    def test_send_email_calls_smtp2go_only_with_key(self):
        with app.test_request_context(), patch.object(notify.requests, 'post') as post:
            self.assertTrue(self.real_send_email('x@example.com', 'subj', 'body'))
            self.assertEqual(post.call_args[0][0], notify.SMTP2GO_URL)
            self.assertEqual(post.call_args[1]['headers']['X-Smtp2go-Api-Key'], 'key')
            self.assertEqual(post.call_args[1]['json']['to'], ['x@example.com'])
            post.reset_mock()
            app.config['EMAIL_BACKEND'] = 'off'
            self.assertFalse(self.real_send_email('x@example.com', 'subj', 'body'))
            post.assert_not_called()
            # backend picked but not filled in: still no crash, nothing sent
            app.config.update({'EMAIL_BACKEND': 'smtp2go', 'SMTP2GO_API_KEY': ''})
            self.assertFalse(self.real_send_email('x@example.com', 'subj', 'body'))
            post.assert_not_called()

    def test_admin_signup_email_only_on_first_name(self):
        self.sign_in(display_name='', pending=True, approved=False)
        self.post('/profile', token_page='/profile', display_name='New Kid')
        self.send_email.assert_called_once()
        self.assertEqual(self.send_email.call_args[0][0], 'boss@example.com')
        self.db['get_admins_to_notify'].assert_called_with('notify_admin_signup')
        self.send_email.reset_mock()
        self.sign_in(display_name='New Kid')
        self.post('/profile', display_name='Newer Kid')
        self.send_email.assert_not_called()

    def test_hours_review_email_on_checkout(self):
        self.sign_in()
        self.db['get_checkin'].return_value = {'time': '2026-12-01T14:00:00'}
        self.db['add_checkout'].return_value = True
        self.post('/member/events/1/handlecheckout', code='XYZ789')
        self.db['get_admins_to_notify'].assert_called_with('notify_admin_hours')
        self.assertIn('Hours to review', self.send_email.call_args[0][1])

    def test_admin_checkboxes_saved_for_admins_only(self):
        self.sign_in()
        self.post('/my-profile/notifications', notify_admin_signup='on')
        self.db['set_admin_notify_prefs'].assert_not_called()
        self.sign_in(is_admin=True)
        self.post('/my-profile/notifications', notify_admin_hours='on')
        self.db['set_admin_notify_prefs'].assert_called_once_with(
            1, {'notify_admin_signup': False, 'notify_admin_hours': True})

    def test_digest_due_logic(self):
        import datetime
        monday_9 = datetime.datetime(2026, 11, 30, 9, 0)      # a monday
        self.assertEqual(notify._last_digest_due(monday_9), datetime.datetime(2026, 11, 30, 8, 0))
        monday_7 = datetime.datetime(2026, 11, 30, 7, 0)
        self.assertEqual(notify._last_digest_due(monday_7), datetime.datetime(2026, 11, 23, 8, 0))
        thursday = datetime.datetime(2026, 12, 3, 19, 0)
        self.assertEqual(notify._last_digest_due(thursday), datetime.datetime(2026, 11, 30, 8, 0))

    def test_digest_sends_once(self):
        self.db['get_admin_digest'].return_value = dict(
            pending_accounts=[dict(name='New Kid', email='k@example.com')],
            pending_hours=[], events_held=[], new_rsvps=3, new_posts=[],
            upcoming=[dict(event_title='Park Cleanup', event_date='2026-12-05',
                           start_time='09:00', attending=4)])
        with app.test_request_context():
            self.assertTrue(notify.send_admin_digest_if_due())
            body = self.send_email.call_args[0][2]
            self.assertIn('New Kid', body)
            self.assertIn('3 new RSVP', body)
            self.assertIn('4 attending', body)
            self.db['set_task_last_run'].assert_called_once()
            # pretend it just ran
            import datetime
            self.db['get_task_last_run'].return_value = datetime.datetime.now()
            self.assertFalse(notify.send_admin_digest_if_due())


if __name__ == '__main__':
    unittest.main()
