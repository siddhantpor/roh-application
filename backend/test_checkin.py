"""Integrated tests: python -m unittest discover -s backend -p 'test_*.py' -v.

Uses a temporary SQLite database and mocked external SDK responses. Never resets
local/Neon data and never provides a development authentication bypass.
"""
import io
from contextlib import closing
import re
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from authlib.integrations.base_client.errors import OAuthError
from cloudinary.exceptions import Error as CloudinaryError
from PIL import Image

from app import create_app
import database


class IntegratedAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app({
            'TESTING': True, 'SECRET_KEY': 'test-only-key', 'DATABASE_URL': '',
            'SQLITE_PATH': str(Path(self.temp.name) / 'test.sqlite'),
            'AUTH0_DOMAIN': 'test.auth0.com', 'AUTH0_CLIENT_ID': 'test-client',
            'AUTH0_CLIENT_SECRET': 'test-secret', 'ADMIN_EMAILS': {'admin@example.com'},
            'CLOUDINARY_CLOUD_NAME': 'test', 'CLOUDINARY_API_KEY': 'test',
            'CLOUDINARY_API_SECRET': 'test', 'WTF_CSRF_ENABLED': True,
        })
        self.client = self.app.test_client()
        self.auth0 = Mock()
        self.app.extensions['auth0_client'] = self.auth0
        result = self.app.test_cli_runner().invoke(args=['init-db'])
        self.assertEqual(result.exit_code, 0, result.output)

    def login(self, username='alice', email=None, verified=True, subject=None):
        self.auth0.authorize_access_token.return_value = {'userinfo': {
            'sub': subject or 'auth0|' + username, 'email': email or username + '@example.com',
            'email_verified': verified, 'name': username.title(),
        }}
        return self.client.get('/callback')

    def csrf(self, path='/'):
        response = self.client.get(path, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        return re.search(rb'name="csrf_token" value="([^"]+)"', response.data)[1].decode()

    def post(self, path, data=None):
        payload = {'csrf_token': self.csrf()}
        payload.update(data or {})
        response = self.client.post(path, data=payload)
        self.addCleanup(response.request.environ['wsgi.input'].close)
        self.addCleanup(response.close)
        return response

    def event(self, event_id=1):
        with self.app.app_context():
            return database.get_event(event_id)

    def form(self, **changes):
        data = dict(title='Community Day', date='2026-12-01', start_time='09:00',
                    end_time='12:00', location='Princeton', description='Join us')
        data.update(changes)
        return data

    def image(self, filename='poster.png'):
        stream = io.BytesIO()
        Image.new('RGB', (20, 20), 'green').save(stream, format='PNG')
        stream.seek(0)
        return stream, filename

    def test_logged_out_routes_redirect(self):
        for path in ('/member/events', '/admin/events', '/member/events/1/checkin'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.startswith('/login?next='))

    def test_public_welcome_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome to the community', response.data)
        self.assertIn(b'Create an account', response.data)

    def test_new_member_waits_for_admin_approval(self):
        response = self.login('newcomer')
        self.assertEqual(response.location, '/membership')
        with self.app.app_context():
            user_id = database.get_user_id('auth0|newcomer')
            user = database.get_account(user_id)
            self.assertFalse(user['approved'])
            self.assertTrue(user['pending'])
        response = self.client.get('/membership')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Awaiting review', response.data)
        self.assertNotIn(b'My Hours', response.data)
        self.assertNotIn(b'Manage Events', response.data)
        self.assertEqual(self.client.get('/').location, '/membership')
        # Attempt every protected endpoint with valid CSRF; none may execute.
        token = self.csrf()
        for rule in self.app.url_map.iter_rules():
            if not rule.rule.startswith(('/member/', '/admin/')):
                continue
            path = rule.rule.replace('<int:event_id>', '1').replace('<int:user_id>', '2')
            for method in rule.methods & {'GET', 'POST'}:
                with self.subTest(path=path, method=method):
                    response = self.client.open(path, method=method, data={'csrf_token': token})
                    expected = 302 if method == 'GET' and path.startswith('/member/') else 403
                    self.assertEqual(response.status_code, expected)
                    if expected == 302:
                        self.assertEqual(response.location, '/membership')
        self.assertEqual(self.post('/logout').status_code, 302)

    def test_admin_approves_and_revokes_existing_member_session(self):
        self.login('newcomer')
        volunteer = self.client
        with self.app.app_context():
            user_id = database.get_user_id('auth0|newcomer')
        self.client = self.app.test_client()
        self.login('tdouglas')
        self.assertIn(b'newcomer@example.com', self.client.get('/admin/members').data)
        path = f'/admin/members/{user_id}/membership'
        self.assertEqual(self.client.post(path, data={'action': 'approve'}).status_code, 400)
        self.assertEqual(self.post(path, {'action': 'approve'}).status_code, 302)
        self.assertIn(volunteer.get('/membership').location, ('/', '/index'))
        self.assertEqual(volunteer.get('/member/events').status_code, 200)
        self.assertEqual(volunteer.get('/admin/members').status_code, 403)
        # Revocation blocks the next request without logging the volunteer out.
        self.assertEqual(self.post(path, {'action': 'revoke'}).status_code, 302)
        self.assertEqual(volunteer.get('/member/events').location, '/membership')
        self.assertIn(b'Access not approved', volunteer.get('/membership').data)
        with self.app.app_context():
            self.assertIsNotNone(database.get_account(user_id))

    def test_declined_membership_persists_on_login_and_can_be_reconsidered(self):
        self.login('newcomer')
        with self.app.app_context():
            user_id = database.get_user_id('auth0|newcomer')
        self.login('tdouglas')
        path = f'/admin/members/{user_id}/membership'
        self.post(path, {'action': 'decline'})
        self.login('newcomer')
        self.assertIn(b'Access not approved', self.client.get('/membership').data)
        self.assertEqual(self.post('/member/events/1/rsvp', {'response': 'going'}).status_code, 403)
        self.login('tdouglas')
        self.post(path, {'action': 'approve'})
        self.login('newcomer')
        self.assertEqual(self.client.get('/member/events').status_code, 200)

    def test_membership_changes_preserve_history_and_cannot_disable_admins(self):
        self.login()  # link Alice, whose seeded attendance/RSVP history must survive
        self.login('tdouglas')
        self.assertEqual(self.post('/admin/members/1/membership', {'action': 'decline'}).status_code, 404)
        self.assertEqual(self.post('/admin/members/999/membership', {'action': 'approve'}).status_code, 404)
        self.assertEqual(self.post('/admin/members/2/membership', {'action': 'bad'}).status_code, 400)
        self.post('/admin/members/2/membership', {'action': 'revoke'})
        with self.app.app_context():
            self.assertIsNotNone(database.get_checkin(2, 1))
            self.assertIsNotNone(database.get_checkout(2, 1))
            self.assertTrue(database.get_rsvp(2, 1))
        self.login()
        self.assertEqual(self.client.get('/member/events').location, '/membership')

    def test_existing_account_link_and_refresh(self):
        self.assertEqual(self.login().status_code, 302)
        response = self.client.get('/member/events')
        self.assertIn(b'Park Cleanup', response.data)
        self.assertIn(b'Welcome back, Alice.', response.data)
        self.assertNotIn(b'Manage Events', response.data)
        with self.app.app_context():
            user = database.get_account(database.get_user_id('alice'))
            self.assertEqual(user['auth0_sub'], 'auth0|alice')
            self.assertEqual(database.get_rsvp(user['user_id'], 1), True)
        with self.client.session_transaction() as session:
            self.assertNotIn('access_token', session)
            self.assertNotIn('userinfo', session)
        self.assertEqual(self.client.get('/member/events').status_code, 200)

    def test_role_landing_pages_and_navigation(self):
        self.login('tdouglas')
        self.assertEqual(self.client.get('/').location, '/admin/events')
        response = self.client.get('/admin/events')
        self.assertIn(b'Manage Events', response.data)
        self.assertIn(b'Manage Volunteers', response.data)
        self.assertIn(b'Review membership requests', response.data)
        self.assertNotIn(b'href="/member/events"', response.data)
        self.assertNotIn(b'href="/member/hours"', response.data)
        self.login()
        self.assertEqual(self.client.get('/').location, '/member/events')
        response = self.client.get('/member/events')
        self.assertIn(b'Volunteer Events', response.data)
        self.assertIn(b'href="/member/hours"', response.data)
        self.assertNotIn(b'href="/admin/', response.data)
        self.assertNotIn(b'Check-in code', response.data)

    def test_admin_dashboard_request_count_tracks_approval(self):
        from flask import template_rendered
        contexts = []
        def record_template(sender, template, context, **extra):
            contexts.append(context)
        self.login('newcomer')
        with self.app.app_context():
            user_id = database.get_user_id('auth0|newcomer')
        self.login('tdouglas')
        with template_rendered.connected_to(record_template, self.app):
            self.client.get('/admin/events')
            self.assertEqual(contexts[-1]['pending_count'], 1)
            self.post(f'/admin/members/{user_id}/membership', {'action': 'approve'})
            self.client.get('/admin/events')
            self.assertEqual(contexts[-1]['pending_count'], 0)

    def test_existing_linked_account_admin_grant_uses_cli(self):
        self.login('newcomer')
        self.app.config['ADMIN_EMAILS'].add('newcomer@example.com')
        self.login('newcomer')
        self.assertEqual(self.client.get('/admin/events').status_code, 403)
        result = self.app.test_cli_runner().invoke(args=['set-admin', 'newcomer@example.com'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.client.get('/admin/events').status_code, 200)

    def test_login_requires_configuration_and_handles_service_failure(self):
        from requests.exceptions import ConnectionError
        self.app.config['AUTH0_CLIENT_SECRET'] = ''
        self.assertEqual(self.client.get('/login').status_code, 503)
        self.app.config['AUTH0_CLIENT_SECRET'] = 'test-secret'
        self.auth0.authorize_redirect.side_effect = ConnectionError('offline')
        self.assertEqual(self.client.get('/login').status_code, 502)

    def test_session_requires_linked_matching_subject(self):
        with self.client.session_transaction() as session:
            session.update(user_id=1, expires_at=time.time()+3600)
        self.assertEqual(self.client.get('/admin/events').status_code, 302)
        self.login()
        with self.client.session_transaction() as session:
            session['auth0_sub'] = 'auth0|different'
        self.assertEqual(self.client.get('/member/events').status_code, 302)

    def test_new_signup_and_bootstrap_admin(self):
        self.assertEqual(self.login('newcomer').status_code, 302)
        self.assertEqual(self.client.get('/admin/events').status_code, 403)
        self.assertEqual(self.login('admin').status_code, 302)
        self.assertEqual(self.client.get('/admin/events').status_code, 200)
        self.assertEqual(self.client.get('/').location, '/admin/events')

    def test_unverified_and_conflicting_identity_rejected(self):
        self.assertEqual(self.login(verified=False).status_code, 403)
        with self.client.session_transaction() as session:
            self.assertNotIn('user_id', session)
        self.login()
        self.assertEqual(self.login(subject='auth0|someone-else').status_code, 403)
        with self.app.app_context():
            self.assertEqual(database.get_account(2)['auth0_sub'], 'auth0|alice')

    def test_duplicate_email_rejected(self):
        with closing(sqlite3.connect(self.app.config['SQLITE_PATH'])) as connection, connection:
            connection.execute("UPDATE accounts SET email='alice@example.com' WHERE username='bob'")
        self.assertEqual(self.login().status_code, 403)

    def test_auth_failure_clears_session(self):
        self.login()
        self.auth0.authorize_access_token.side_effect = OAuthError('invalid_state')
        self.assertEqual(self.client.get('/callback').status_code, 400)
        self.assertEqual(self.client.get('/member/events').status_code, 302)

    def test_safe_login_return_and_signup(self):
        from flask import redirect
        self.auth0.authorize_redirect.return_value = redirect('https://test.auth0.com/authorize')
        for destination in ('https://evil.test', '//evil.test', '/\\evil.test', '/\nevil.test'):
            self.client.get('/login', query_string={'next': destination})
            with self.client.session_transaction() as session:
                self.assertEqual(session['next'], '/')
        self.client.get('/signup', query_string={'next': '/member/hours'})
        self.assertEqual(self.auth0.authorize_redirect.call_args.kwargs['screen_hint'], 'signup')
        self.assertEqual(self.login().location, '/member/hours')

    def test_local_ip_login_and_signup_switch_hosts_before_oauth(self):
        from flask import redirect
        self.auth0.authorize_redirect.return_value = redirect('https://test.auth0.com/authorize')
        for path in ('/login', '/signup'):
            with self.subTest(path=path):
                self.auth0.authorize_redirect.reset_mock()
                response = self.client.get(path, base_url='http://127.0.0.1:5001',
                                           query_string={'next': '/member/hours'})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, f'http://localhost:5001{path}?next=/member/hours')
                self.auth0.authorize_redirect.assert_not_called()
                response = self.client.get(response.location)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(self.auth0.authorize_redirect.call_args.args[0],
                                 'http://localhost:5001/callback')

    def test_deployed_login_keeps_its_own_host(self):
        from flask import redirect
        self.auth0.authorize_redirect.return_value = redirect('https://test.auth0.com/authorize')
        response = self.client.get('/signup', base_url='https://volunteer.example.org')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.auth0.authorize_redirect.call_args.args[0],
                         'https://volunteer.example.org/callback')

    def test_expiration_and_old_stub_session(self):
        self.login()
        with self.client.session_transaction() as session:
            session['expires_at'] = time.time() - 1
        self.assertEqual(self.client.get('/member/events').status_code, 302)
        with self.client.session_transaction() as session:
            session.clear()
            session['username'] = 'tdouglas'
        self.assertEqual(self.client.get('/admin/events').status_code, 302)

    def test_admin_revocation_takes_effect_during_session(self):
        self.login('admin')
        self.assertEqual(self.client.get('/admin/events').status_code, 200)
        runner = self.app.test_cli_runner()
        self.assertEqual(runner.invoke(args=['set-admin', 'admin@example.com', '--revoke']).exit_code, 0)
        self.assertEqual(self.client.get('/admin/events').status_code, 403)
        self.login('admin')  # bootstrap does not silently re-grant revoked access
        self.assertEqual(self.client.get('/admin/events').status_code, 403)

    def test_every_admin_route_blocks_regular_users(self):
        self.login()
        token = self.csrf()
        for rule in self.app.url_map.iter_rules():
            if not rule.rule.startswith('/admin/'):
                continue
            path = rule.rule.replace('<int:event_id>', '1').replace('<int:user_id>', '2')
            for method in rule.methods & {'GET', 'POST'}:
                with self.subTest(path=path, method=method):
                    response = self.client.open(path, method=method, data={'csrf_token': token})
                    self.assertEqual(response.status_code, 403)

    def test_csrf_and_logout(self):
        self.login()
        self.assertEqual(self.client.post('/logout').status_code, 400)
        self.assertEqual(self.client.get('/logout').status_code, 405)
        self.assertEqual(self.client.post('/member/events/1/rsvp', data={'response': 'going'}).status_code, 400)
        response = self.post('/logout')
        self.assertTrue(response.location.startswith('https://test.auth0.com/v2/logout?'))
        self.assertEqual(self.client.get('/member/events').status_code, 302)

    def test_cookie_and_cache_settings(self):
        response = self.login()
        cookie = response.headers['Set-Cookie']
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Lax', cookie)
        self.assertIn('Expires=', cookie)
        self.assertEqual(self.client.get('/member/events').headers['Cache-Control'], 'no-store')

    def test_all_page_templates_render(self):
        self.login('tdouglas')
        for path in ('/admin/events', '/admin/events/create', '/admin/events/1', '/admin/events/1/edit',
                     '/admin/events/1/attendees', '/admin/members', '/admin/events/1/codes',
                     '/admin/events/1/hours', '/admin/events/1/hours/2', '/member/events',
                     '/member/events/1', '/member/events/1/checkin', '/member/hours', '/loggedout'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get('/admin/events/999').status_code, 404)
        self.assertEqual(self.client.get('/member/events/999').status_code, 404)

    def test_event_create_edit_and_validation(self):
        self.login('tdouglas')
        response = self.post('/admin/events/create', self.form())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.event(3)['event_title'], 'Community Day')
        response = self.post('/admin/events/3/edit', self.form(title='Updated'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.event(3)['event_title'], 'Updated')
        for values in (self.form(title='  '), self.form(date='bad'), self.form(end_time='08:00')):
            self.assertEqual(self.post('/admin/events/3/edit', values).status_code, 400)
            self.assertEqual(self.event(3)['event_title'], 'Updated')

    def test_rsvp_and_attendees(self):
        self.login('carol')
        self.assertEqual(self.post('/member/events/2/rsvp', {'response': 'going'}).status_code, 302)
        self.assertEqual(self.event(2)['attending'], 1)
        self.assertIn(b'Your RSVP: Going', self.client.get('/member/events/2').data)
        self.post('/member/events/2/rsvp', {'response': 'not_going'})
        self.assertEqual(self.event(2)['attending'], 0)
        self.assertEqual(self.post('/member/events/2/rsvp', {'response': 'bad'}).status_code, 400)
        self.login('tdouglas')
        self.assertIn(b'Carol', self.client.get('/admin/events/2/attendees').data)

    def test_checkin_checkout_and_duplicate(self):
        self.login('carol')
        response = self.post('/member/events/1/handlecheckin', {'code': 'NOPE'})
        self.assertIn('msg=', response.location)
        response = self.post('/member/events/1/handlecheckin', {'code': 'abc 123'})
        self.assertNotIn('msg=', response.location)
        response = self.post('/member/events/1/handlecheckin', {'code': 'ABC123'})
        self.assertIn('already', response.location)
        self.post('/member/events/1/handlecheckout', {'code': 'XYZ789'})
        self.assertIn(b'Thanks for volunteering', self.client.get('/member/events/1/checkin').data)

    def test_checkout_requires_checkin(self):
        self.login('carol')
        response = self.post('/member/events/1/handlecheckout', {'code': 'XYZ789'})
        self.assertIn('never', response.location)

    def test_admin_hours_approve_edit_reject(self):
        self.login('tdouglas')
        response = self.post('/admin/events/1/handleapprove', {'user_id': '3'})
        self.assertIn('still', response.location)
        response = self.post('/admin/events/1/hours/2/handleedit', {
            'action': 'save', 'checkin_time': '2026-11-07T09:00',
            'checkout_time': '2026-11-07T12:00', 'reason': 'rounded',
        })
        self.assertIn('approved', response.location)
        with self.app.app_context():
            self.assertEqual(database.get_hours(2, '2026-01-01', '2026-12-31')[0]['hours'], 3.0)
        self.login()
        self.assertIn(b'3.00 hours', self.client.get('/member/hours').data)
        self.login('tdouglas')
        self.post('/admin/events/1/hours/2/handleedit', {'action': 'reject'})
        with self.app.app_context():
            self.assertIsNone(database.get_checkin(2, 1))

    def test_approve_all_and_code_generation(self):
        self.login('tdouglas')
        self.post('/admin/events/1/handleapproveall')
        with self.app.app_context():
            self.assertTrue(database.get_checkin(2, 1)['approved'])
            self.assertFalse(database.get_checkin(3, 1)['approved'])
        self.post('/admin/events/2/handlecodes')
        event = self.event(2)
        self.assertEqual(len(event['checkin_code']), 6)
        self.assertNotEqual(event['checkin_code'], event['checkout_code'])

    @patch('posters.cloudinary.uploader.destroy', return_value={'result': 'ok'})
    @patch('posters.cloudinary.uploader.upload')
    def test_poster_create_display_replace_remove(self, upload, destroy):
        self.login('tdouglas')
        upload.return_value = {'secure_url': 'https://res.cloudinary.com/test/first.png', 'public_id': 'first'}
        self.assertEqual(self.post('/admin/events/create', self.form(flyer=self.image())).status_code, 302)
        self.assertEqual(self.event(3)['graphic_public_id'], 'first')
        self.assertIn(b'https://res.cloudinary.com/test/first.png', self.client.get('/member/events/3').data)
        upload.return_value = {'secure_url': 'https://res.cloudinary.com/test/second.png', 'public_id': 'second'}
        self.post('/admin/events/3/edit', self.form(flyer=self.image()))
        self.assertEqual(self.event(3)['graphic_public_id'], 'second')
        self.assertEqual(destroy.call_args.args[0], 'first')
        self.post('/admin/events/3/edit', self.form(remove_poster='yes'))
        self.assertIsNone(self.event(3)['graphic_link'])
        self.assertEqual(destroy.call_args.args[0], 'second')
        self.assertFalse(upload.call_args.kwargs['overwrite'])

    @patch('posters.cloudinary.uploader.upload')
    def test_invalid_and_oversized_images_never_upload(self, upload):
        self.login('tdouglas')
        for flyer in ((io.BytesIO(b'fake'), 'fake.png'), self.image('fake.svg'),
                      (io.BytesIO(b'x' * (5 * 1024 * 1024 + 1)), 'big.png')):
            self.assertEqual(self.post('/admin/events/create', self.form(flyer=flyer)).status_code, 400)
        upload.assert_not_called()
        self.assertIsNone(self.event(3))
        response = self.post('/admin/events/create', self.form(flyer=(io.BytesIO(b'x' * (7 * 1024 * 1024)), 'big.png')))
        self.assertEqual(response.status_code, 413)

    @patch('posters.cloudinary.uploader.upload', side_effect=CloudinaryError('offline'))
    def test_upload_failure_preserves_event(self, upload):
        self.login('tdouglas')
        response = self.post('/admin/events/1/edit', self.form(flyer=self.image()))
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.event(1)['event_title'], 'Park Cleanup')
        self.assertIn(b'Community Day', response.data)  # retain submitted form fields

    @patch('posters.cloudinary.uploader.destroy', return_value={'result': 'ok'})
    @patch('posters.cloudinary.uploader.upload', return_value={'secure_url': 'https://test/new.png', 'public_id': 'new'})
    def test_database_failure_cleans_new_upload(self, upload, destroy):
        self.login('tdouglas')
        with patch('databasesqlite.update_event', side_effect=sqlite3.OperationalError('write failed')):
            with self.assertRaises(sqlite3.OperationalError):
                self.post('/admin/events/1/edit', self.form(flyer=self.image()))
        destroy.assert_called_once()
        self.assertEqual(destroy.call_args.args[0], 'new')
        self.assertEqual(self.event(1)['event_title'], 'Park Cleanup')

    @patch('posters.cloudinary.uploader.destroy', side_effect=CloudinaryError('offline'))
    @patch('posters.cloudinary.uploader.upload', return_value={'secure_url': 'https://test/new.png', 'public_id': 'new'})
    def test_failed_old_poster_cleanup_keeps_saved_event(self, upload, destroy):
        self.login('tdouglas')
        self.post('/admin/events/1/edit', self.form(flyer=self.image()))
        with self.assertLogs(self.app.logger, level='ERROR') as logs:
            response = self.post('/admin/events/1/edit', self.form(remove_poster='yes'))
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.event(1)['graphic_link'])
        self.assertIn('public_id=new', logs.output[0])

    def test_missing_upload_config_does_not_block_events_without_posters(self):
        self.login('tdouglas')
        self.app.config['CLOUDINARY_API_SECRET'] = ''
        self.assertEqual(self.post('/admin/events/create', self.form()).status_code, 302)
        self.assertEqual(self.post('/admin/events/3/edit', self.form(flyer=self.image())).status_code, 502)

    def test_init_refuses_existing_db_and_migration_is_repeatable(self):
        runner = self.app.test_cli_runner()
        self.assertNotEqual(runner.invoke(args=['init-db']).exit_code, 0)
        for _ in range(2):
            self.assertEqual(runner.invoke(args=['migrate-db']).exit_code, 0)
        self.assertEqual(self.event(1)['event_title'], 'Park Cleanup')

    def test_migrate_existing_data_without_new_columns(self):
        # Simulate the previous SQLite schema in this test database only.
        with closing(sqlite3.connect(self.app.config['SQLITE_PATH'])) as connection, connection:
            connection.execute('DROP INDEX IF EXISTS accounts_auth0_sub_unique')
            # Recreate the legacy schema from the original seed text, preserving all seed rows.
            schema = Path(__file__).with_name('roh.sql').read_text()
            schema = schema.replace('    auth0_sub    TEXT UNIQUE,\n', '')
            schema = schema.replace('    graphic_public_id TEXT,        -- Cloudinary identifier for replacement/deletion\n', '')
            connection.executescript(schema)
        result = self.app.test_cli_runner().invoke(args=['migrate-db'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.event(1)['event_title'], 'Park Cleanup')
        self.assertEqual(self.login().status_code, 302)


if __name__ == '__main__':
    unittest.main()
