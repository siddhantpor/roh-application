#!/usr/bin/env python

#-----------------------------------------------------------------------
# databasepostgresql.py
# PostgreSQL (Neon) version of the database functions, written against
# the team schema (accounts / events / rsvps / attendance / volunteerhours)
# plus migrate_checkin.sql. Same functions and return values as
# databasesqlite.py; routes don't know which one they got.
#
# Schema differences from the SQLite dev version, handled here:
#   - one `attendance` table with is_checkin true/false instead of
#     checkins + checkouts
#   - real date/time/timestamp/boolean columns instead of text/0-1;
#     converted to the same strings/bools the SQLite version returns
#   - event_starttime / event_endtime instead of start_time / end_time
#-----------------------------------------------------------------------

import os
import datetime
import dotenv
import psycopg
import psycopg_pool

dotenv.load_dotenv()
_DATABASE_URL = os.environ['DATABASE_URL']

_connection_pool = psycopg_pool.ConnectionPool(_DATABASE_URL, open=True)

#-----------------------------------------------------------------------
# Accounts
#-----------------------------------------------------------------------

def get_user_id(username):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT user_id FROM accounts WHERE username = %s
                ''', [username])
            table = cursor.fetchall()
            if len(table) != 1:
                return None
            return table[0][0]

#-----------------------------------------------------------------------

def is_admin(username):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT is_admin FROM accounts WHERE username = %s
                ''', [username])
            table = cursor.fetchall()
            if len(table) != 1:
                return False
            return table[0][0] is True

#-----------------------------------------------------------------------
# Events
#-----------------------------------------------------------------------

def get_event(event_id):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT event_id, event_date, event_starttime, event_endtime,
                       event_title, event_descrip, event_locat,
                       graphic_link, checkin_code, checkout_code
                FROM events WHERE event_id = %s
                ''', [event_id])
            table = cursor.fetchall()
            if len(table) != 1:
                return None
            row = table[0]
            return {'event_id': row[0], 'event_date': _date_text(row[1]),
                'start_time': _time_text(row[2]),
                'end_time': _time_text(row[3]),
                'event_title': row[4], 'event_descrip': row[5],
                'event_locat': row[6], 'graphic_link': row[7],
                'checkin_code': row[8], 'checkout_code': row[9]}

#-----------------------------------------------------------------------

def set_event_codes(event_id, checkin_code, checkout_code):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''
                UPDATE events
                SET checkin_code = %s, checkout_code = %s
                WHERE event_id = %s
                ''', [checkin_code, checkout_code, event_id])
            connection.commit()
            return cursor.rowcount == 1

#-----------------------------------------------------------------------
# RSVPs (read only here)
#-----------------------------------------------------------------------

def get_rsvp(user_id, event_id):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT accepted FROM rsvps
                WHERE user_id = %s AND event_id = %s
                ORDER BY time DESC LIMIT 1
                ''', [user_id, event_id])
            table = cursor.fetchall()
            if len(table) != 1:
                return None
            return table[0][0] is True

#-----------------------------------------------------------------------
# Check-ins and check-outs: rows in `attendance`, is_checkin true/false
#-----------------------------------------------------------------------

def get_checkin(user_id, event_id):
    return _get_record(True, user_id, event_id)

def get_checkout(user_id, event_id):
    return _get_record(False, user_id, event_id)

def add_checkin(user_id, event_id, time):
    return _add_record(True, user_id, event_id, time)

def add_checkout(user_id, event_id, time):
    return _add_record(False, user_id, event_id, time)

#-----------------------------------------------------------------------

def _get_record(is_checkin, user_id, event_id):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT time, approved FROM attendance
                WHERE user_id = %s AND event_id = %s AND is_checkin = %s
                ''', [user_id, event_id, is_checkin])
            table = cursor.fetchall()
            if len(table) != 1:
                return None
            return {'time': _timestamp_text(table[0][0]),
                    'approved': table[0][1] is True}

#-----------------------------------------------------------------------

def _add_record(is_checkin, user_id, event_id, time):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            try:
                cursor.execute('''
                    INSERT INTO attendance
                        (user_id, event_id, time, approved, is_checkin)
                    VALUES (%s, %s, %s, false, %s)
                    ''', [user_id, event_id, time, is_checkin])
            except psycopg.errors.UniqueViolation:
                connection.rollback()
                return False   # already recorded (needs the UNIQUE
                               # constraint from migrate_checkin.sql)
            connection.commit()
            return True

#-----------------------------------------------------------------------
# Admin review
#-----------------------------------------------------------------------

def get_attendance(event_id):

    attendance = []
    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            # Check-in rows LEFT JOINed to their check-out row, so a
            # member who never checked out still appears.
            cursor.execute('''
                SELECT a.user_id, a.display_name,
                       c.time, c.approved, o.time, o.approved
                FROM attendance c
                JOIN accounts a ON a.user_id = c.user_id
                LEFT JOIN attendance o
                    ON o.user_id = c.user_id AND o.event_id = c.event_id
                   AND o.is_checkin = false
                WHERE c.event_id = %s AND c.is_checkin = true
                ORDER BY a.display_name
                ''', [event_id])
            for row in cursor.fetchall():
                checkin_time = _timestamp_text(row[2])
                checkout_time = _timestamp_text(row[4])
                attendance.append({'user_id': row[0],
                    'display_name': row[1],
                    'checkin_time': checkin_time,
                    'checkin_approved': row[3] is True,
                    'checkout_time': checkout_time,
                    'checkout_approved': row[5] is True,
                    'hours': _hours_between(checkin_time, checkout_time)})
    return attendance

#-----------------------------------------------------------------------

def update_attendance(user_id, event_id, checkin_time, checkout_time,
    approved):

    # Replace both rows in one transaction. None time = no row.
    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''
                DELETE FROM attendance
                WHERE user_id = %s AND event_id = %s
                ''', [user_id, event_id])
            for is_checkin, time in [(True, checkin_time),
                                     (False, checkout_time)]:
                if time is not None:
                    cursor.execute('''
                        INSERT INTO attendance
                            (user_id, event_id, time, approved, is_checkin)
                        VALUES (%s, %s, %s, %s, %s)
                        ''', [user_id, event_id, time, approved, is_checkin])
            connection.commit()

#-----------------------------------------------------------------------
# Hours (approved check-in + check-out pairs only)
#-----------------------------------------------------------------------

def get_hours(user_id, start_date, end_date):

    hours = []
    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT e.event_id, e.event_title, e.event_date, c.time, o.time
                FROM attendance c
                JOIN attendance o
                    ON o.user_id = c.user_id AND o.event_id = c.event_id
                   AND o.is_checkin = false
                JOIN events e ON e.event_id = c.event_id
                WHERE c.user_id = %s AND c.is_checkin = true
                  AND c.approved = true AND o.approved = true
                  AND e.event_date BETWEEN %s AND %s
                ORDER BY e.event_date
                ''', [user_id, start_date, end_date])
            for row in cursor.fetchall():
                hours.append({'event_id': row[0], 'event_title': row[1],
                    'event_date': _date_text(row[2]),
                    'hours': _hours_between(_timestamp_text(row[3]),
                                            _timestamp_text(row[4]))})
    return hours

#-----------------------------------------------------------------------
# Conversions: Postgres gives date/time/datetime objects; the SQLite
# version (and the routes) use ISO strings.
#-----------------------------------------------------------------------

def _date_text(d):
    return None if d is None else d.isoformat()

def _time_text(t):
    return None if t is None else t.strftime('%H:%M')

def _timestamp_text(ts):
    return None if ts is None else ts.replace(microsecond=0).isoformat()

def _hours_between(checkin_time, checkout_time):

    if checkin_time is None or checkout_time is None:
        return None
    seconds = (datetime.datetime.fromisoformat(checkout_time)
        - datetime.datetime.fromisoformat(checkin_time)).total_seconds()
    if seconds < 0:
        return None
    return round(seconds / 3600, 2)

#-----------------------------------------------------------------------

# For testing (python databasepostgresql.py). Assumes seed_neon.sql was
# just run. Leaves the database as it found it.

def _test():
    alice = get_user_id('alice'); bob = get_user_id('bob')
    carol = get_user_id('carol')
    print('----------------------------------')
    print('Testing get_user_id() / is_admin()')
    print('----------------------------------')
    print(alice is not None, get_user_id('nobody'))
    print(is_admin('tdouglas'), is_admin('alice'))
    print()

    print('----------------------------------')
    print('Testing get_event()')
    print('----------------------------------')
    with _connection_pool.connection() as c:
        park = c.execute("SELECT event_id FROM events WHERE event_title='Park Cleanup'").fetchone()[0]
        food = c.execute("SELECT event_id FROM events WHERE event_title='Food Bank Sorting'").fetchone()[0]
    e = get_event(park)
    print(e['event_title'], e['event_date'], e['start_time'], e['end_time'], e['checkin_code'])
    print(get_event(food)['checkin_code'])   # None
    print(get_event(999999))                 # None
    print()

    print('----------------------------------')
    print('Testing get_rsvp()')
    print('----------------------------------')
    print(get_rsvp(alice, park), get_rsvp(carol, park), get_rsvp(alice, food))  # True False None
    print()

    print('----------------------------------')
    print('Testing get_checkin() / get_checkout()')
    print('----------------------------------')
    print(get_checkin(alice, park))   # 14:02, unapproved
    print(get_checkout(bob, park))    # None
    print()

    print('----------------------------------')
    print('Testing add_checkin() (duplicate should fail)')
    print('----------------------------------')
    print(add_checkin(carol, park, '2026-11-07T14:20:00'))  # True
    print(add_checkin(carol, park, '2026-11-07T14:21:00'))  # False
    print()

    print('----------------------------------')
    print('Testing get_attendance()')
    print('----------------------------------')
    for record in get_attendance(park):
        print(record)
    print()

    print('----------------------------------')
    print('Testing update_attendance() then get_hours()')
    print('----------------------------------')
    print(get_hours(alice, '2026-01-01', '2026-12-31'))   # []
    update_attendance(alice, park, '2026-11-07T14:00:00', '2026-11-07T17:00:00', True)
    print(get_hours(alice, '2026-01-01', '2026-12-31'))   # 3.0
    print(get_hours(alice, '2026-12-01', '2026-12-31'))   # []
    print()

    print('----------------------------------')
    print('Testing set_event_codes()')
    print('----------------------------------')
    print(set_event_codes(food, 'AAA111', 'BBB222'))   # True
    print(get_event(food)['checkin_code'])             # AAA111
    print(set_event_codes(999999, 'x', 'y'))           # False
    print()

    # Put things back the way seed_neon.sql left them.
    update_attendance(alice, park, '2026-11-07T14:02:00', '2026-11-07T16:58:00', False)
    update_attendance(carol, park, None, None, False)
    set_event_codes(food, None, None)

if __name__ == '__main__':
    _test()
    _connection_pool.close()
