import os
import urllib.parse
import flask
import dotenv
import authlib.integrations.flask_client

dotenv.load_dotenv()
AUTH0_DOMAIN = os.environ["AUTH0_DOMAIN"]
AUTH0_CLIENT_ID = os.environ["AUTH0_CLIENT_ID"]
AUTH0_CLIENT_SECRET = os.environ["AUTH0_CLIENT_SECRET"]
ADMIN_EMAILS = {
    e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
}

oauth = authlib.integrations.flask_client.OAuth()


def init(app):
    oauth.init_app(app)
    oauth.register(
        "auth0",
        client_id=AUTH0_CLIENT_ID,
        client_secret=AUTH0_CLIENT_SECRET,
        client_kwargs={"scope": "openid profile email"},
        server_metadata_url=f"https://{AUTH0_DOMAIN}/.well-known/openid-configuration",
    )

    app.add_url_rule("/login", "login", login)
    app.add_url_rule("/signup", "signup", signup)
    app.add_url_rule("/callback", "callback", callback, methods=["GET", "POST"])
    app.add_url_rule("/logout", "logout", logout)
    app.add_url_rule("/loggedout", "loggedout", loggedout)


def _redirect_to_auth0(**params):
    next_url = flask.request.args.get("next", "/")
    # Only allow redirects back into this app
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"
    flask.session["next"] = next_url
    redirect_uri = flask.url_for("callback", _external=True)
    return oauth.auth0.authorize_redirect(redirect_uri=redirect_uri, **params)


def login():
    return _redirect_to_auth0()


def signup():
    return _redirect_to_auth0(screen_hint="signup")


def callback():
    token = oauth.auth0.authorize_access_token()
    userinfo = token["userinfo"]
    flask.session["user"] = {
        "id": userinfo["sub"],
        "email": userinfo.get("email", "").lower(),
        "name": userinfo.get("name", ""),
    }
    # TODO: Create/look up the volunteer in the database (keyed by user email)
    return flask.redirect(flask.session.pop("next", "/"))


def logout():
    flask.session.clear()
    return flask.redirect(
        f"https://{AUTH0_DOMAIN}/v2/logout?"
        + urllib.parse.urlencode(
            {
                "returnTo": flask.url_for("loggedout", _external=True),
                "client_id": AUTH0_CLIENT_ID,
            }
        )
    )


def loggedout():
    return flask.render_template("loggedout.html")


def get_user():
    return flask.session.get("user")


def is_admin():
    user = get_user()
    return user is not None and user["email"] in ADMIN_EMAILS


# Do not return unless the user is logged in
def authenticate():
    if get_user() is None:
        next_url = flask.request.full_path.rstrip("?")
        flask.abort(flask.redirect(flask.url_for("login", next=next_url)))


# Do not return unless the user is a logged-in admin
def authenticate_admin():
    authenticate()
    if not is_admin():
        flask.abort(403)
