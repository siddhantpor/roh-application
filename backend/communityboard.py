import flask

import auth
import checkin
import databasepostgresql as database

# TODO: Show administrators which members have reacted to a post and when (e.g., for roll call).

REACTIONS = {'thumbs_up': '👍', 'laugh': '😄', 'hooray': '🎉',
             'heart': '❤️', 'rocket': '🚀', 'eyes': '👀'}


def init(app):
    app.add_url_rule('/community-board', 'community_board', community_board)
    app.add_url_rule('/admin/community-board/create', 'admin_create_post', admin_save_post,
                     methods=['GET', 'POST'])
    app.add_url_rule('/admin/community-board/<int:post_id>/edit', 'admin_edit_post',
                     admin_save_post, methods=['GET', 'POST'])
    app.add_url_rule('/community-board/<int:post_id>/react', 'react_to_post', react_to_post,
                     methods=['POST'])


def community_board():
    auth.authenticate_member()
    posts = database.get_posts()
    counts = database.get_reaction_counts()
    mine = database.get_user_reactions(auth.get_user()['user_id'])
    for post in posts:
        post['created_at'] = post['created_at'].astimezone(checkin.LOCAL_TIMEZONE)
        if post['edited_at']:
            post['edited_at'] = post['edited_at'].astimezone(checkin.LOCAL_TIMEZONE)
        _add_reactions(post, counts.get(post['post_id'], {}), mine.get(post['post_id']))
    role = 'admin' if auth.is_admin() else 'member'
    return flask.render_template(f'community-board/{role}/board.html', posts=posts,
                                 reactions=REACTIONS)


def react_to_post(post_id):
    auth.authenticate_member()
    reaction = flask.request.form.get('reaction', '')
    if reaction not in REACTIONS:
        flask.abort(400)
    if database.get_post(post_id) is None:
        flask.abort(404)
    user_id = auth.get_user()['user_id']
    database.toggle_reaction(post_id, user_id, reaction)
    if flask.request.form.get('ajax') == '1':
        post = {'post_id': post_id}
        _add_reactions(post, database.get_reaction_counts(post_id).get(post_id, {}),
                       database.get_user_reactions(user_id).get(post_id))
        return flask.render_template('community-board/reactions.html', post=post,
                                     reactions=REACTIONS)
    return flask.redirect(flask.url_for('community_board', _anchor=f'post-{post_id}'))


def _add_reactions(post, post_counts, my_reaction):
    post['my_reaction'] = my_reaction
    post['reactions'] = [
        {'name': name, 'emoji': emoji, 'count': post_counts[name], 'mine': name == my_reaction}
        for name, emoji in REACTIONS.items() if post_counts.get(name)]


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
