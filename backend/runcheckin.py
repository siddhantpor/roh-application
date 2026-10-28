#!/usr/bin/env python

#-----------------------------------------------------------------------
# runcheckin.py
# Standalone Flask app for developing the check-in / hours subsystem
# on its own. Dondero's penny.py + runserver.py in one file.
#
#     cd backend
#     python runcheckin.py 5001
#     open http://localhost:5001
#
# At integration time the team's app does the same two init() calls
# (auth.init(app), checkin.init(app)) and this file can go away.
#-----------------------------------------------------------------------

import os
import sys
import dotenv
import flask
import flask_wtf.csrf
import auth
import checkin

#-----------------------------------------------------------------------

dotenv.load_dotenv()
# Sessions are signed with this key. Set APP_SECRET_KEY in .env; the
# fallback is only so the app starts on a fresh laptop with no .env.
_APP_SECRET_KEY = os.environ.get('APP_SECRET_KEY', 'dev-only-not-secret')

#-----------------------------------------------------------------------

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIR = os.path.join(_BACKEND_DIR, '..', 'frontend')

app = flask.Flask(__name__,
    template_folder=os.path.join(_FRONTEND_DIR, 'templates'),
    static_folder=os.path.join(_FRONTEND_DIR, 'static'))
app.secret_key = _APP_SECRET_KEY
flask_wtf.csrf.CSRFProtect(app)   # every POST form needs {{csrf_token()}}

auth.init(app)
checkin.init(app)

#-----------------------------------------------------------------------

@app.route('/', methods=['GET'])
@app.route('/index', methods=['GET'])
def index():

    html_code = flask.render_template('check-in/index.html',
        username=auth.get_username())
    response = flask.make_response(html_code)
    return response

#-----------------------------------------------------------------------

def main():

    if len(sys.argv) != 2:
        print(f'usage: {sys.argv[0]} port', file=sys.stderr)
        sys.exit(1)

    try:
        port = int(sys.argv[1])
    except Exception:
        print(f'{sys.argv[0]}: Port must be an integer.',
            file=sys.stderr)
        sys.exit(1)

    try:
        app.run(host='0.0.0.0', port=port, debug=True)
    except Exception as ex:
        print(f'{sys.argv[0]}: {ex}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
