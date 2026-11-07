"""Application setup. Run with `python backend/app.py` or Flask's CLI."""
import os
from contextlib import closing
from datetime import timedelta
from pathlib import Path

import click
import dotenv
import flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import HTTPException

import auth
import checkin
import database
import events


def create_app(test_config=None):
    backend_dir = Path(__file__).resolve().parent
    dotenv.load_dotenv(backend_dir.parent / '.env')
    dotenv.load_dotenv(backend_dir / '.env')
    app = flask.Flask(__name__, template_folder='../frontend/templates',
                      static_folder='../frontend/static')
    app.config.from_mapping(
        SECRET_KEY=os.getenv('APP_SECRET_KEY'),
        DATABASE_URL=os.getenv('DATABASE_URL', ''),
        SQLITE_PATH=str(backend_dir / 'roh.sqlite'),
        AUTH0_DOMAIN=os.getenv('AUTH0_DOMAIN', ''),
        AUTH0_CLIENT_ID=os.getenv('AUTH0_CLIENT_ID', ''),
        AUTH0_CLIENT_SECRET=os.getenv('AUTH0_CLIENT_SECRET', ''),
        ADMIN_EMAILS={e.strip().lower() for e in os.getenv('ADMIN_EMAILS', '').split(',') if e.strip()},
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if not app.secret_key:
        raise RuntimeError('Set APP_SECRET_KEY in .env (see backend/.env.example).')

    database.init_app(app)
    auth.init_app(app)
    CSRFProtect(app)
    app.register_blueprint(events.bp)
    app.register_blueprint(checkin.bp)

    @app.get('/')
    @app.get('/index')
    def index():
        auth.authenticate()
        endpoint = 'events.admin_events' if auth.is_admin() else 'events.member_events'
        return flask.redirect(flask.url_for(endpoint))

    @app.errorhandler(HTTPException)
    def http_error(error):
        return flask.render_template('error.html', error=error), error.code

    @app.errorhandler(500)
    def server_error(error):
        return flask.render_template('error.html', error=error), 500

    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        if flask.request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.cli.command('init-db')
    def init_db():
        """Create the local demo database; refuse to overwrite existing tables."""
        if app.config['DATABASE_URL']:
            raise click.ClickException('init-db is SQLite only. See README for PostgreSQL migrations.')
        import sqlite3
        with closing(sqlite3.connect(app.config['SQLITE_PATH'])) as connection:
            if connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                raise click.ClickException('Database already has tables; use migrate-db to preserve data.')
            connection.executescript((backend_dir / 'roh.sql').read_text())
        click.echo('Created local demo database.')

    @app.cli.command('migrate-db')
    def migrate_db():
        """Apply the additive Auth0/poster migration without resetting data."""
        database.migrate()
        click.echo('Applied Auth0/poster migration.')

    @app.cli.command('set-admin')
    @click.argument('email')
    @click.option('--revoke', is_flag=True, help='Remove admin access.')
    def set_admin(email, revoke):
        """Grant/revoke an existing, linked account's admin access."""
        if not database.set_admin(email.strip().lower(), not revoke):
            raise click.ClickException('Expected one linked account with that email. Log in first.')
        click.echo('Updated admin access.')

    return app


if __name__ == '__main__':
    create_app().run(port=5001, debug=os.getenv('FLASK_DEBUG') == '1')
