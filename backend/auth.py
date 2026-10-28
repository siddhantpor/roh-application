#!/usr/bin/env python

#-----------------------------------------------------------------------
# auth.py  (STUB: not real authentication)
#
# Placeholder until we picks Auth0 or home-grown auth. It exposes
# the same three functions that both of Dondero's Penny versions
# expose, so routes written against it don't change when the real
# auth.py replaces this file:
#
#     auth.init(app)          register auth routes on the app
#     auth.authenticate()     call at the top of every protected route;
#                             does not return unless a user is logged in
#     auth.get_username()     the logged-in user's username
#
# What this stub does instead of logging in: it keeps a username in
# the Flask session, and provides /login?as=<username> so you can
# switch users from the address bar while developing. Any username in
# the accounts table works (alice, bob, carol, tdouglas).
#-----------------------------------------------------------------------

import flask

#-----------------------------------------------------------------------

def init(app):

    app.add_url_rule('/login', 'login', login, methods=['GET'])
    app.add_url_rule('/logout', 'logout', logout, methods=['GET'])

#-----------------------------------------------------------------------

def login():

    # DEV ONLY: /login?as=alice logs in as alice, no password.
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

# Copied verbatim from Dondero's PennyAuthHomeGrown auth.py.

def authenticate():

    username = flask.session.get('username')
    if username is None:
        response = flask.redirect(flask.url_for('login'))
        flask.session['original_url'] = flask.request.url
        flask.abort(response)
