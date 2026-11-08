"""Route and upload tests using mocked database and external-service calls."""
import io
import os
import re
import time
import unittest
from unittest.mock import DEFAULT, Mock, patch

import psycopg
from authlib.integrations.base_client.errors import OAuthError
from cloudinary.exceptions import Error as CloudinaryError
from PIL import Image
from flask import redirect

# Import the shared app with test-only settings; database queries below are mocked.
with patch.dict(os.environ, {
    'APP_SECRET_KEY': 'test-only-key',
    'DATABASE_URL': 'postgresql://test:test@database.invalid/unused',
    'AUTH0_DOMAIN': 'test.auth0.com', 'AUTH0_CLIENT_ID': 'test-client',
    'AUTH0_CLIENT_SECRET': 'test-secret',
}):
    from app import app
import auth
import databasepostgresql as database


class AppTests(unittest.TestCase):
    def setUp(self):
        queries = ('get_account', 'link_auth0_user', 'set_admin', 'get_members',
                   'set_membership', 'get_event', 'get_events', 'add_event',
                   'update_event', 'get_checkin', 'get_checkout', 'add_checkin', 'set_event_codes')
        patcher = patch.multiple(database, **dict.fromkeys(queries, DEFAULT))
        self.db = patcher.start()
        self.addCleanup(patcher.stop)
        self.app = app
        original_config = self.app.config.copy()
        self.addCleanup(self.app.config.update, original_config)
        self.app.config.update({
            'TESTING': True, 'SECRET_KEY': 'test-only-key',
            # Queries are mocked; no connection is made to this placeholder.
            'DATABASE_URL': 'postgresql://test:test@database.invalid/unused',
            'AUTH0_DOMAIN': 'test.auth0.com', 'AUTH0_CLIENT_ID': 'test-client',
            'AUTH0_CLIENT_SECRET': 'test-secret', 'ADMIN_EMAILS': {'admin@example.com'},
            'CLOUDINARY_CLOUD_NAME': 'test', 'CLOUDINARY_API_KEY': 'test',
            'CLOUDINARY_API_SECRET': 'test', 'SESSION_COOKIE_SECURE': False,
        })
        self.client = self.app.test_client()
        self.auth0 = Mock()
        self.auth0.authorize_redirect.return_value = redirect('https://test.auth0.com/authorize')
        auth_client = patch.object(auth.oauth, 'auth0', self.auth0)
        auth_client.start()
        self.addCleanup(auth_client.stop)
        self.account = dict(user_id=1, username='auth0|member', auth0_sub='auth0|member',
                            email='member@example.com', display_name='Member',
                            is_admin=False, approved=True, pending=False)
        self.event = dict(event_id=1, event_date='2026-11-07', start_time='09:00',
                          end_time='12:00', event_title='Park Cleanup', event_locat='Park',
                          event_descrip='Help clean up.', graphic_link=None,
                          graphic_public_id=None, checkin_code='ABC123', checkout_code='XYZ789',
                          attending=0)
        self.db['get_account'].return_value = self.account
        self.db['link_auth0_user'].return_value = self.account
        self.db['get_event'].return_value = self.event
        self.db['get_events'].return_value = [self.event]
        self.db['get_members'].return_value = []
        self.db['get_checkin'].return_value = None
        self.db['get_checkout'].return_value = None
        self.db['add_event'].return_value = 2

    def sign_in(self, **values):
        self.account.update(values)
        with self.client.session_transaction() as session:
            session.permanent = True
            session.update(user_id=1, auth0_sub='auth0|member')

    def callback(self, **values):
        info = dict(sub='auth0|member', email='member@example.com', email_verified=True, name='Member')
        info.update(values)
        self.auth0.authorize_access_token.return_value = {'userinfo': info}
        return self.client.get('/callback')

    def post(self, path, **values):
        page = self.client.get('/')
        if page.status_code == 302:
            page = self.client.get(page.location)
        token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data)[1].decode()
        response = self.client.post(path, data={'csrf_token': token, **values})
        self.addCleanup(response.request.environ['wsgi.input'].close)
        return response

    def form(self, **values):
        return dict(date='2026-11-07', start_time='09:00', end_time='12:00',
                    title='Park Cleanup', location='Park', description='Help clean up.', **values)

    def image(self, name='poster.png'):
        stream = io.BytesIO()
        Image.new('RGB', (10, 10)).save(stream, 'PNG')
        stream.seek(0)
        return stream, name

    def test_public_welcome_and_protected_routes(self):
        self.assertIn(b'Create an account', self.client.get('/').data)
        for path in ('/admin/events', '/member/events', '/admin/members'):
            self.assertTrue(self.client.get(path).location.startswith('/login?'))

    def test_core_pages_render(self):
        self.sign_in(is_admin=True)
        self.db['get_members'].return_value = [self.account]
        for path in ('/admin/events', '/admin/events/create', '/admin/events/1/edit',
                     '/admin/events/1', '/admin/members', '/admin/events/1/codes'):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.account['is_admin'] = False
        for path in ('/member/events', '/member/events/1', '/member/events/1/checkin', '/loggedout'):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_callback_links_verified_identity_without_storing_tokens(self):
        self.assertEqual(self.callback().location, '/')
        self.db['link_auth0_user'].assert_called_once_with('auth0|member', 'member@example.com', 'Member', False)
        with self.client.session_transaction() as session:
            self.assertEqual(session['user_id'], 1)
            self.assertNotIn('access_token', session)
        self.assertEqual(self.client.get('/').location, '/member/events')

    def test_admin_bootstrap_and_landing_page(self):
        self.account['is_admin'] = True
        self.callback(email='Admin@Example.com')
        self.assertTrue(self.db['link_auth0_user'].call_args.args[-1])
        self.assertEqual(self.client.get('/').location, '/admin/events')

    def test_unverified_or_incomplete_identity_does_not_link(self):
        for values in ({'email_verified': False}, {'sub': ''}, {'email': ''}):
            self.assertEqual(self.callback(**values).status_code, 403)
        self.db['link_auth0_user'].assert_not_called()

    def test_login_failure_and_conflicting_account(self):
        self.auth0.authorize_access_token.side_effect = OAuthError('invalid_grant')
        with self.assertRaises(OAuthError):
            self.client.get('/callback')
        with self.client.session_transaction() as session:
            self.assertNotIn('user_id', session)
        self.auth0.authorize_access_token.side_effect = None
        self.db['link_auth0_user'].side_effect = ValueError('conflicting email')
        with self.assertRaises(ValueError):
            self.callback()
        with self.client.session_transaction() as session:
            self.assertNotIn('user_id', session)

    def test_pending_members_cannot_execute_protected_routes(self):
        self.account.update(approved=False, pending=True)
        self.assertEqual(self.callback().location, '/membership')
        for rule in self.app.url_map.iter_rules():
            if rule.rule.startswith(('/admin/', '/member/')):
                path = rule.rule.replace('<int:event_id>', '1').replace('<int:user_id>', '1')
                if 'GET' in rule.methods:
                    expected = 403 if path.startswith('/admin/') else 302
                    self.assertEqual(self.client.get(path).status_code, expected, path)
                if 'POST' in rule.methods:
                    self.assertEqual(self.post(path).status_code, 403, path)
        self.db['add_event'].assert_not_called()
        self.db['add_checkin'].assert_not_called()

    def test_members_cannot_execute_any_admin_route(self):
        self.sign_in()
        for rule in self.app.url_map.iter_rules():
            if rule.rule.startswith('/admin/'):
                path = rule.rule.replace('<int:event_id>', '1').replace('<int:user_id>', '1')
                if 'GET' in rule.methods:
                    self.assertEqual(self.client.get(path).status_code, 403, path)
                if 'POST' in rule.methods:
                    self.assertEqual(self.post(path).status_code, 403, path)

    def test_admin_membership_actions(self):
        self.sign_in(is_admin=True)
        for action in ('approve', 'decline', 'revoke'):
            self.assertEqual(self.post('/admin/members/2/membership', action=action).status_code, 302)
            self.db['set_membership'].assert_called_with(2, action == 'approve')
        self.assertEqual(self.post('/admin/members/2/membership', action='invalid').status_code, 400)

    def test_role_and_membership_changes_apply_on_next_request(self):
        self.sign_in(is_admin=True)
        self.assertEqual(self.client.get('/admin/events').status_code, 200)
        self.account['is_admin'] = False
        self.assertEqual(self.client.get('/admin/events').status_code, 403)
        self.account['approved'] = False
        self.assertEqual(self.client.get('/member/events').location, '/membership')

    def test_expired_or_mismatched_session_requires_login(self):
        self.sign_in()
        with self.client.session_transaction() as session:
            session['auth0_sub'] = 'different-identity'
        self.assertTrue(self.client.get('/member/events').location.startswith('/login?'))

        # Flask rejects a signed cookie older than the configured eight hours.
        serializer = self.app.session_interface.get_signing_serializer(self.app)
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp',
                   return_value=int(time.time()) - 9 * 3600):
            expired_cookie = serializer.dumps({'_permanent': True, 'user_id': 1,
                                               'auth0_sub': 'auth0|member'})
        self.client.set_cookie(self.app.config['SESSION_COOKIE_NAME'], expired_cookie)
        self.assertTrue(self.client.get('/member/events').location.startswith('/login?'))

    def test_csrf_logout_and_admin_cli(self):
        self.sign_in(is_admin=True)
        self.assertEqual(self.client.post('/logout').status_code, 400)
        self.assertIn('/v2/logout?', self.post('/logout').location)
        runner = self.app.test_cli_runner()
        self.assertEqual(runner.invoke(args=['set-admin', 'Admin@Example.com']).exit_code, 0)
        self.db['set_admin'].assert_called_with('admin@example.com', True)
        runner.invoke(args=['set-admin', 'admin@example.com', '--revoke'])
        self.db['set_admin'].assert_called_with('admin@example.com', False)

    def test_local_host_normalization_and_safe_return(self):
        for path in ('/login', '/signup'):
            self.assertEqual(self.client.get(path, base_url='http://127.0.0.1:5001').location,
                             'http://localhost:5001' + path)
        self.client.get('/login?next=//untrusted.example')
        with self.client.session_transaction() as session:
            self.assertEqual(session['next'], '/')
        self.client.get('/signup')
        self.assertEqual(self.auth0.authorize_redirect.call_args.kwargs['screen_hint'], 'signup')

    def test_existing_checkin_and_checkout_rules(self):
        self.sign_in()
        self.post('/member/events/1/handlecheckin', code='WRONG')
        self.db['add_checkin'].assert_not_called()
        self.post('/member/events/1/handlecheckin', code='abc123')
        self.assertEqual(self.db['add_checkin'].call_args.args[:2], (1, 1))
        self.assertIn('never+checked+in', self.post('/member/events/1/handlecheckout', code='XYZ789').location)

    def test_generated_codes_accept_lowercase_member_input(self):
        self.sign_in(is_admin=True)
        self.assertEqual(self.post('/admin/events/1/handlecodes').status_code, 302)
        event_id, checkin_code, checkout_code = self.db['set_event_codes'].call_args.args
        self.assertEqual(event_id, 1)
        self.assertNotEqual(checkin_code, checkout_code)
        self.event.update(checkin_code=checkin_code, checkout_code=checkout_code)
        self.account['is_admin'] = False
        self.post('/member/events/1/handlecheckin', code=checkin_code.lower())
        self.assertEqual(self.db['add_checkin'].call_args.args[:2], (1, 1))
        # Codes already saved by the original implementation may be lowercase.
        self.event['checkin_code'] = checkin_code.lower()
        self.db['add_checkin'].reset_mock()
        self.post('/member/events/1/handlecheckin', code=checkin_code.upper())
        self.db['add_checkin'].assert_called_once()

    @patch('posters.cloudinary.uploader.destroy', return_value={'result': 'ok'})
    @patch('posters.cloudinary.uploader.upload')
    def test_poster_create_replace_and_remove(self, upload, destroy):
        self.sign_in(is_admin=True)
        upload.return_value = {'secure_url': 'https://images.example/new.png', 'public_id': 'new'}
        self.assertEqual(self.post('/admin/events/create', **self.form(flyer=self.image())).status_code, 302)
        self.assertEqual(self.db['add_event'].call_args.args[-2:], ('https://images.example/new.png', 'new'))
        self.event.update(graphic_link='https://images.example/old.png', graphic_public_id='old')
        self.post('/admin/events/1/edit', **self.form(flyer=self.image()))
        self.assertEqual(destroy.call_args.args[0], 'old')
        self.post('/admin/events/1/edit', **self.form(remove_poster='yes'))
        self.assertEqual(self.db['update_event'].call_args.args[-2:], (None, None))
        self.assertIn(b'https://images.example/old.png', self.client.get('/member/events/1').data)

    @patch('posters.cloudinary.uploader.upload')
    def test_invalid_images_never_reach_cloudinary(self, upload):
        self.sign_in(is_admin=True)
        for image in ((io.BytesIO(b'not an image'), 'poster.png'), self.image('poster.svg'),
                      (io.BytesIO(b'x' * (5 * 1024 * 1024 + 1)), 'poster.png')):
            self.assertEqual(self.post('/admin/events/create', **self.form(flyer=image)).status_code, 400)
        upload.assert_not_called()
        self.db['add_event'].assert_not_called()

    @patch('posters.cloudinary.uploader.destroy', return_value={'result': 'ok'})
    @patch('posters.cloudinary.uploader.upload')
    def test_storage_and_database_failures_preserve_event(self, upload, destroy):
        self.sign_in(is_admin=True)
        upload.side_effect = CloudinaryError('offline')
        with self.assertRaises(CloudinaryError):
            self.post('/admin/events/1/edit', **self.form(flyer=self.image()))
        self.db['update_event'].assert_not_called()
        upload.side_effect = None
        upload.return_value = {'secure_url': 'https://images.example/new.png', 'public_id': 'new'}
        self.db['update_event'].side_effect = psycopg.OperationalError('offline')
        with self.assertRaises(psycopg.OperationalError):
            self.post('/admin/events/1/edit', **self.form(flyer=self.image()))
        self.assertEqual(destroy.call_args.args[0], 'new')


if __name__ == '__main__':
    unittest.main()
