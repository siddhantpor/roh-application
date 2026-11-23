import flask

import auth
import checkin
import databasepostgresql as database


def init(app):
    app.add_url_rule('/community-board', 'community_board', community_board)
    app.add_url_rule('/admin/community-board/create', 'admin_create_post', admin_save_post,
                     methods=['GET', 'POST'])
    app.add_url_rule('/admin/community-board/<int:post_id>/edit', 'admin_edit_post',
                     admin_save_post, methods=['GET', 'POST'])


def community_board():
    auth.authenticate_member()
    posts = database.get_posts()
    for post in posts:
        post['created_at'] = post['created_at'].astimezone(checkin.LOCAL_TIMEZONE)
        if post['edited_at']:
            post['edited_at'] = post['edited_at'].astimezone(checkin.LOCAL_TIMEZONE)
    role = 'admin' if auth.is_admin() else 'member'
    return flask.render_template(f'community-board/{role}/board.html', posts=posts)


def admin_save_post(post_id=None):
    auth.authenticate_admin()
    post = database.get_post(post_id) if post_id is not None else None
    if post_id is not None and post is None:
        flask.abort(404)
    if flask.request.method == 'POST':
        post_title = flask.request.form.get('post_title', '').strip()
        body = flask.request.form.get('body', '').strip()
        if not post_title or not body:
            flask.abort(400)
        if post is None:
            post_id = database.add_post(auth.get_user()['user_id'], post_title, body)
            flask.flash('Post published.')
        else:
            database.update_post(post_id, post_title, body)
            flask.flash('Post saved.')
        return flask.redirect(flask.url_for('community_board', _anchor=f'post-{post_id}'))
    return flask.render_template('community-board/admin/create_post.html', post=post)
