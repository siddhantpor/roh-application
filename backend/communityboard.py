import flask

import auth
import checkin
import databasepostgresql as database


def init(app):
    app.add_url_rule('/community-board', 'community_board', community_board)
    app.add_url_rule('/admin/community-board/create', 'admin_create_post', admin_create_post,
                     methods=['GET', 'POST'])


def community_board():
    auth.authenticate_member()
    posts = database.get_posts()
    for post in posts:
        post['created_at'] = post['created_at'].astimezone(checkin.LOCAL_TIMEZONE)
    role = 'admin' if auth.is_admin() else 'member'
    return flask.render_template(f'community-board/{role}/board.html', posts=posts)


def admin_create_post():
    auth.authenticate_admin()
    if flask.request.method == 'POST':
        post_title = flask.request.form.get('post_title', '').strip()
        body = flask.request.form.get('body', '').strip()
        if not post_title or not body:
            flask.abort(400)
        database.add_post(auth.get_user()['user_id'], post_title, body)
        flask.flash('Post published.')
        return flask.redirect(flask.url_for('community_board'))
    return flask.render_template('community-board/admin/create_post.html')
