#!/usr/bin/env python

#-----------------------------------------------------------------------
# auth.py
# STUB until we pick Auth0 or home-grown auth. Same interface as the
# real thing will have:
#     init(app)          registers the auth routes
#     authenticate()     call first in every protected route
#     get_username()     logged-in username
# Login is fake: /login?as=alice puts 'alice' in the session.
#-----------------------------------------------------------------------

import flask

#-----------------------------------------------------------------------

def init(app):

    app.add_url_rule('/login', 'login', login, methods=['GET'])
    app.add_url_rule('/logout', 'logout', logout, methods=['GET'])

#-----------------------------------------------------------------------

def login():

    # No password: pick a user from the accounts table.
    username = flask.request.args.get('as')
    if username is None or username.strip() == '':
        html_code = ('<p>Stub login. Pick a user: '
            '<a href="/login?as=alice">alice</a>, '
            '<a href="/login?as=bob">bob</a>, '
            '<a href="/login?as=carol">carol</a>, '
            '<a href="/login?as=tdouglas">tdouglas (admin)</a></p>')
        response = flask.make_response(html_code)
        return response

    flask.session['username'] = username.strip()
    original_url = flask.session.get('original_url', '/')
    response = flask.redirect(original_url)
    return response

#-----------------------------------------------------------------------

def logout():

    flask.session.clear()
    html_code = '<p>Logged out. <a href="/login">Log in</a></p>'
    response = flask.make_response(html_code)
    return response

#-----------------------------------------------------------------------

def get_username():

    return flask.session.get('username')

#-----------------------------------------------------------------------

def authenticate():

    username = flask.session.get('username')
    if username is None:
        response = flask.redirect(flask.url_for('login'))
        flask.session['original_url'] = flask.request.url
        flask.abort(response)
