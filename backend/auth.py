"""Auth0 proves identity; database flags control membership and admin access."""
from urllib.parse import urlencode, urlsplit

import flask
from authlib.integrations.flask_client import OAuth

import databasepostgresql as database

oauth = OAuth()


def init(app):
    oauth.init_app(app)
    oauth.register(
        'auth0', client_id=app.config['AUTH0_CLIENT_ID'],
        client_secret=app.config['AUTH0_CLIENT_SECRET'],
        client_kwargs={'scope': 'openid profile email'},
        server_metadata_url=f"https://{app.config['AUTH0_DOMAIN']}/.well-known/openid-configuration",
    )
    app.add_url_rule('/login', view_func=login)
    app.add_url_rule('/signup', view_func=signup)
    app.add_url_rule('/callback', view_func=callback)
    app.add_url_rule('/logout', view_func=logout, methods=['POST'])
    app.add_url_rule('/membership', view_func=membership)
    app.add_url_rule('/loggedout', view_func=loggedout)

    @app.context_processor
    def auth_context():
        user = get_user()
        return {'current_user': user}


def _safe_next(value):
    # Backslashes/control characters can be interpreted as external redirects by browsers.
    if not value or not value.startswith('/') or value.startswith('//'):
        return '/'
    if '\\' in value or any(ord(char) < 32 for char in value):
        return '/'
    parsed = urlsplit(value)
    return value if not parsed.netloc and not parsed.scheme else '/'


def _start_login(**params):
    # Flask prints 127.0.0.1 when starting locally, but Auth0 allows localhost.
    # Switch hosts before saving OAuth state so the callback receives its cookie.
    url = urlsplit(flask.request.url)
    if url.hostname == '127.0.0.1':
        host = 'localhost' + (f':{url.port}' if url.port else '')
        return flask.redirect(url._replace(netloc=host).geturl())
    flask.session['next'] = _safe_next(flask.request.args.get('next'))
    return oauth.auth0.authorize_redirect(flask.url_for('callback', _external=True), **params)


def login():
    return _start_login()


def signup():
    return _start_login(screen_hint='signup')


def callback():
    # Authlib validates OAuth state, OIDC nonce, issuer, signature and expiry.
    token = oauth.auth0.authorize_access_token()
    next_url = _safe_next(flask.session.get('next'))
    flask.session.clear()
    userinfo = token.get('userinfo', {})
    if not userinfo.get('sub') or not userinfo.get('email'):
        flask.abort(403)
    if userinfo.get('email_verified') is not True:
        flask.abort(403, 'Verify your email address with Auth0 before logging in.')
    user = database.link_auth0_user(
        userinfo['sub'], userinfo['email'].strip().lower(),
        userinfo.get('name') or userinfo['email'],
        userinfo['email'].strip().lower() in flask.current_app.config['ADMIN_EMAILS'],
    )
    flask.session.permanent = True
    flask.session.update(user_id=user['user_id'], auth0_sub=userinfo['sub'])
    if not user['is_admin'] and not user['approved']:
        return flask.redirect(flask.url_for('membership'))
    return flask.redirect(next_url)


def logout():
    flask.session.clear()
    return flask.redirect(f"https://{flask.current_app.config['AUTH0_DOMAIN']}/v2/logout?" + urlencode({
        'returnTo': flask.url_for('loggedout', _external=True),
        'client_id': flask.current_app.config['AUTH0_CLIENT_ID'],
    }))


def membership():
    authenticate()
    user = get_user()
    if user['is_admin'] or user['approved']:
        return flask.redirect(flask.url_for('index'))
    return flask.render_template('membership.html')


def loggedout():
    return flask.render_template('loggedout.html')


def get_user():
    # flask.g lasts for one request, so templates and routes share this lookup.
    if 'current_user' in flask.g:
        return flask.g.current_user

    flask.g.current_user = None
    user_id = flask.session.get('user_id')
    if user_id is None:
        return None

    user = database.get_account(user_id)
    if user and user['auth0_sub'] and user['auth0_sub'] == flask.session.get('auth0_sub'):
        flask.g.current_user = user
    else:
        flask.session.clear()
    return flask.g.current_user


def get_username():
    user = get_user()
    return user['username'] if user else None


def is_admin():
    user = get_user()
    return bool(user and user['is_admin'])


def authenticate():
    if get_user() is None:
        next_url = flask.request.full_path.rstrip('?') if flask.request.method == 'GET' else '/'
        flask.abort(flask.redirect(flask.url_for('login', next=next_url)))


def authenticate_admin():
    authenticate()
    if not is_admin():
        flask.abort(403, 'Administrator access is required.')


def authenticate_member():
    authenticate()
    user = get_user()
    if not user['is_admin'] and not user['approved']:
        if flask.request.method in ('GET', 'HEAD'):
            flask.abort(flask.redirect('/membership'))
        flask.abort(403, 'Organization membership approval is required.')
