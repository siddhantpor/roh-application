#!/usr/bin/env python

#-----------------------------------------------------------------------
# test_checkin.py
# Route tests with Flask's test client (no server). Rebuilds
# roh.sqlite from roh.sql first.
#
#     cd backend
#     python test_checkin.py
#-----------------------------------------------------------------------

import os
import sqlite3
import runcheckin
import database

#-----------------------------------------------------------------------

def rebuild_db():
    # SQLite: rebuild from roh.sql. Postgres (DATABASE_URL set): re-run
    # seed_neon.sql, which only touches the demo rows.
    if os.environ.get('DATABASE_URL'):
        import psycopg
        with psycopg.connect(os.environ['DATABASE_URL']) as connection:
            connection.execute(open('seed_neon.sql').read())
    else:
        with sqlite3.connect('roh.sqlite') as connection:
            connection.executescript(open('roh.sql').read())

def login(client, username):
    client.get('/login?as=' + username)

def event_id_of(title):
    # ids differ between SQLite (always 1, 2) and a reseeded Postgres.
    for event_id in range(1, 200):
        event = database.get_event(event_id)
        if event is not None and event['event_title'] == title:
            return event_id
    raise Exception('seed event not found: ' + title)

def check(label, got, expected):
    status = 'ok  ' if got == expected else 'FAIL'
    print(f'{status} {label}: {got!r}')

#-----------------------------------------------------------------------

def main():
    rebuild_db()
    app = runcheckin.app
    app.config['WTF_CSRF_ENABLED'] = False   # not testing CSRF here
    client = app.test_client()
    park = event_id_of('Park Cleanup')
    food = event_id_of('Food Bank Sorting')
    alice = database.get_user_id('alice')
    bob = database.get_user_id('bob')
    carol = database.get_user_id('carol')

    # Logged out -> redirected to login
    r = client.get(f'/member/events/{park}/checkin')
    check('logged out redirects', r.headers['Location'], '/login')

    # Member: wrong code, right code, duplicate, checkout
    login(client, 'carol')
    r = client.post(f'/member/events/{park}/handlecheckin', data={'code': 'NOPE'})
    check('wrong code', 'msg=' in r.headers['Location'], True)
    r = client.post(f'/member/events/{park}/handlecheckin', data={'code': 'abc 123'})
    check('right code (spaces, lowercase)', 'msg=' in r.headers['Location'], False)
    r = client.post(f'/member/events/{park}/handlecheckin', data={'code': 'ABC123'})
    check('duplicate check-in', 'already' in r.headers['Location'], True)
    r = client.post(f'/member/events/{park}/handlecheckout', data={'code': 'XYZ789'})
    check('checkout', 'msg=' in r.headers['Location'], False)
    r = client.get(f'/member/events/{park}/checkin')
    check('page shows checked out', b'Thanks for volunteering' in r.data, True)

    # Admin wall
    r = client.get(f'/admin/events/{park}/hours')
    check('member blocked from admin', b'not authorized' in r.data, True)

    # Admin: approve, edit, reject
    login(client, 'tdouglas')
    r = client.post(f'/admin/events/{park}/handleapprove', data={'user_id': str(bob)})
    check('approve still-checked-in refused', 'still' in r.headers['Location'], True)
    r = client.post(f'/admin/events/{park}/hours/{alice}/handleedit', data={
        'action': 'save', 'checkin_time': '2026-11-07T09:00',
        'checkout_time': '2026-11-07T12:00', 'reason': 'rounded'})
    check('edit + approve alice', 'approved' in r.headers['Location'], True)
    check('alice hours = 3.0',
        database.get_hours(alice, '2026-01-01', '2026-12-31')[0]['hours'], 3.0)
    r = client.post(f'/admin/events/{park}/hours/{carol}/handleedit', data={'action': 'reject'})
    check('reject carol', database.get_checkin(carol, park), None)

    # Admin: codes
    r = client.post(f'/admin/events/{food}/handlecodes')
    event = database.get_event(food)
    check('codes generated', len(event['checkin_code']), 6)

    if os.environ.get('DATABASE_URL'):
        import databasepostgresql
        databasepostgresql._connection_pool.close()

    rebuild_db()

if __name__ == '__main__':
    main()

