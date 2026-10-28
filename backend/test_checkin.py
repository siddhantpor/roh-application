#!/usr/bin/env python

#-----------------------------------------------------------------------
# test_checkin.py
# Quick tests for the check-in routes, using Flask's test client (no
# server, no browser). Rebuilds roh.sqlite from roh.sql first.
#
#     cd backend
#     python test_checkin.py
#-----------------------------------------------------------------------

import sqlite3
import runcheckin
import database

#-----------------------------------------------------------------------

def rebuild_db():
    with sqlite3.connect('roh.sqlite') as connection:
        connection.executescript(open('roh.sql').read())

def login(client, username):
    client.get('/login?as=' + username)

def check(label, got, expected):
    status = 'ok  ' if got == expected else 'FAIL'
    print(f'{status} {label}: {got!r}')

#-----------------------------------------------------------------------

def main():
    rebuild_db()
    app = runcheckin.app
    app.config['WTF_CSRF_ENABLED'] = False   # not testing CSRF here
    client = app.test_client()

    # Logged out -> redirected to login
    r = client.get('/member/events/1/checkin')
    check('logged out redirects', r.headers['Location'], '/login')

    # Member: wrong code, right code, duplicate, checkout
    login(client, 'carol')
    r = client.post('/member/events/1/handlecheckin', data={'code': 'NOPE'})
    check('wrong code', 'msg=' in r.headers['Location'], True)
    r = client.post('/member/events/1/handlecheckin', data={'code': 'abc 123'})
    check('right code (spaces, lowercase)', 'msg=' in r.headers['Location'], False)
    r = client.post('/member/events/1/handlecheckin', data={'code': 'ABC123'})
    check('duplicate check-in', 'already' in r.headers['Location'], True)
    r = client.post('/member/events/1/handlecheckout', data={'code': 'XYZ789'})
    check('checkout', 'msg=' in r.headers['Location'], False)
    r = client.get('/member/events/1/checkin')
    check('page shows checked out', b'Thanks for volunteering' in r.data, True)

    # Admin wall
    r = client.get('/admin/events/1/hours')
    check('member blocked from admin', b'not authorized' in r.data, True)

    # Admin: approve, edit, reject
    login(client, 'tdouglas')
    r = client.post('/admin/events/1/handleapprove', data={'user_id': '3'})
    check('approve still-checked-in refused', 'still' in r.headers['Location'], True)
    r = client.post('/admin/events/1/hours/2/handleedit', data={
        'action': 'save', 'checkin_time': '2026-11-07T09:00',
        'checkout_time': '2026-11-07T12:00', 'reason': 'rounded'})
    check('edit + approve alice', 'approved' in r.headers['Location'], True)
    check('alice hours = 3.0',
        database.get_hours(2, '2026-01-01', '2026-12-31')[0]['hours'], 3.0)
    r = client.post('/admin/events/1/hours/4/handleedit', data={'action': 'reject'})
    check('reject carol', database.get_checkin(4, 1), None)

    # Admin: codes
    r = client.post('/admin/events/2/handlecodes')
    event = database.get_event(2)
    check('codes generated', len(event['checkin_code']), 6)

    rebuild_db()

if __name__ == '__main__':
    main()
