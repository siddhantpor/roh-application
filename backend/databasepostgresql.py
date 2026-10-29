#!/usr/bin/env python

#-----------------------------------------------------------------------
# databasepostgresql.py
# PostgreSQL (Neon) version of the database functions for the check-in /
# check-out / hours subsystem. Same functions, same return values as
# databasesqlite.py; only the connection code and placeholders differ.
# References: Dondero's PennyAuth0 databasepostgresql.py (psycopg_pool,
# %s placeholders, explicit connection.commit() on writes).
#-----------------------------------------------------------------------

import os
import datetime
import dotenv
import psycopg
import psycopg_pool

#-----------------------------------------------------------------------

dotenv.load_dotenv()
_DATABASE_URL = os.environ['DATABASE_URL']

_connection_pool = psycopg_pool.ConnectionPool(_DATABASE_URL)

#-----------------------------------------------------------------------
# Accounts
#-----------------------------------------------------------------------

def get_user_id(username):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            query_str = '''
                SELECT user_id FROM accounts WHERE username = %s
                '''
            cursor.execute(query_str, [username])
            table = cursor.fetchall()
            if len(table) != 1:
                return None
            return table[0][0]

#-----------------------------------------------------------------------

def is_admin(username):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            query_str = '''
                SELECT is_admin FROM accounts WHERE username = %s
                '''
            cursor.execute(query_str, [username])
            table = cursor.fetchall()
            if len(table) != 1:
                return False
            return table[0][0] == 1

#-----------------------------------------------------------------------
# Events
#-----------------------------------------------------------------------

def get_event(event_id):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            query_str = '''
                SELECT event_id, event_date, start_time, end_time,
                       event_title, event_descrip, event_locat,
                       graphic_link, checkin_code, checkout_code
                FROM events WHERE event_id = %s
                '''
            cursor.execute(query_str, [event_id])
            table = cursor.fetchall()
            if len(table) != 1:
                return None
            row = table[0]
            event = {'event_id': row[0], 'event_date': row[1],
                'start_time': row[2], 'end_time': row[3],
                'event_title': row[4], 'event_descrip': row[5],
                'event_locat': row[6], 'graphic_link': row[7],
                'checkin_code': row[8], 'checkout_code': row[9]}
            return event

#-----------------------------------------------------------------------

def set_event_codes(event_id, checkin_code, checkout_code):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            query_str = '''
                UPDATE events
                SET checkin_code = %s, checkout_code = %s
                WHERE event_id = %s
                '''
            cursor.execute(query_str,
                [checkin_code, checkout_code, event_id])
            connection.commit()
            return cursor.rowcount == 1

#-----------------------------------------------------------------------
# RSVPs (read only; writing RSVPs is the event-management subsystem)
#-----------------------------------------------------------------------

def get_rsvp(user_id, event_id):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            query_str = '''
                SELECT accepted FROM rsvps
                WHERE user_id = %s AND event_id = %s
                '''
            cursor.execute(query_str, [user_id, event_id])
            table = cursor.fetchall()
            if len(table) != 1:
                return None          # no RSVP at all
            return table[0][0] == 1  # True = going, False = not going

#-----------------------------------------------------------------------
# Check-ins and check-outs
#-----------------------------------------------------------------------

def get_checkin(user_id, event_id):

    return _get_record('checkins', user_id, event_id)

#-----------------------------------------------------------------------

def get_checkout(user_id, event_id):

    return _get_record('checkouts', user_id, event_id)

#-----------------------------------------------------------------------

def add_checkin(user_id, event_id, time):

    return _add_record('checkins', user_id, event_id, time)

#-----------------------------------------------------------------------

def add_checkout(user_id, event_id, time):

    return _add_record('checkouts', user_id, event_id, time)

#-----------------------------------------------------------------------

# The two tables have identical shapes.
# The table name is substituted into the SQL with an f-string
# Values from the user always go through the %s placeholders.

def _get_record(table_name, user_id, event_id):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            query_str = f'''
                SELECT time, approved FROM {table_name}
                WHERE user_id = %s AND event_id = %s
                '''
            cursor.execute(query_str, [user_id, event_id])
            table = cursor.fetchall()
            if len(table) != 1:
                return None
            record = {'time': table[0][0], 'approved': table[0][1] == 1}
            return record

#-----------------------------------------------------------------------

def _add_record(table_name, user_id, event_id, time):

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            query_str = f'''
                INSERT INTO {table_name} (user_id, event_id, time, approved)
                VALUES (%s, %s, %s, 0)
                '''
            try:
                cursor.execute(query_str, [user_id, event_id, time])
            except psycopg.errors.UniqueViolation:
                # Postgres aborts the transaction on any error, so the
                # connection must be rolled back before it is reused.
                connection.rollback()
                return False   # already checked in/out of this event
            connection.commit()
            return True

#-----------------------------------------------------------------------
# Admin review of an event's attendance
#-----------------------------------------------------------------------

def get_attendance(event_id):

    attendance = []

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            # LEFT JOIN so a member who checked in but never checked
            # out still appears, with NULL for the checkout columns.
            query_str = '''
                SELECT a.user_id, a.display_name,
                       c.time, c.approved, o.time, o.approved
                FROM checkins c
                JOIN accounts a ON a.user_id = c.user_id
                LEFT JOIN checkouts o
                    ON o.user_id = c.user_id AND o.event_id = c.event_id
                WHERE c.event_id = %s
                ORDER BY a.display_name
                '''
            cursor.execute(query_str, [event_id])
            table = cursor.fetchall()
            for row in table:
                record = {'user_id': row[0], 'display_name': row[1],
                    'checkin_time': row[2],
                    'checkin_approved': row[3] == 1,
                    'checkout_time': row[4],
                    'checkout_approved': row[5] == 1,
                    'hours': _hours_between(row[2], row[4])}
                attendance.append(record)

    return attendance

#-----------------------------------------------------------------------

def update_attendance(user_id, event_id, checkin_time, checkout_time,
    approved):

    # Replace both records in one transaction. psycopg runs everything
    # on this connection as one transaction until commit(), so there is
    # no manual BEGIN here (unlike the SQLite version). A None time
    # means "no record", so an admin can clear a bad checkout.

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:

            for table_name, time in [('checkins', checkin_time),
                                     ('checkouts', checkout_time)]:
                query_str = f'''
                    DELETE FROM {table_name}
                    WHERE user_id = %s AND event_id = %s
                    '''
                cursor.execute(query_str, [user_id, event_id])
                if time is not None:
                    query_str = f'''
                        INSERT INTO {table_name}
                            (user_id, event_id, time, approved)
                        VALUES (%s, %s, %s, %s)
                        '''
                    cursor.execute(query_str,
                        [user_id, event_id, time, 1 if approved else 0])

            connection.commit()

#-----------------------------------------------------------------------
# Hours (for the member "My Hours" view). Only approved pairs count.
#-----------------------------------------------------------------------

def get_hours(user_id, start_date, end_date):

    hours = []

    with _connection_pool.connection() as connection:
        with connection.cursor() as cursor:
            # Inner JOIN this time: an event only counts toward hours
            # if BOTH an approved checkin and an approved checkout
            # exist. Dates are 'YYYY-MM-DD' text, so string comparison
            # is the same as date comparison.
            query_str = '''
                SELECT e.event_id, e.event_title, e.event_date,
                       c.time, o.time
                FROM checkins c
                JOIN checkouts o
                    ON o.user_id = c.user_id AND o.event_id = c.event_id
                JOIN events e ON e.event_id = c.event_id
                WHERE c.user_id = %s
                  AND c.approved = 1 AND o.approved = 1
                  AND e.event_date BETWEEN %s AND %s
                ORDER BY e.event_date
                '''
            cursor.execute(query_str, [user_id, start_date, end_date])
            table = cursor.fetchall()
            for row in table:
                record = {'event_id': row[0], 'event_title': row[1],
                    'event_date': row[2],
                    'hours': _hours_between(row[3], row[4])}
                hours.append(record)

    return hours

#-----------------------------------------------------------------------

def _hours_between(checkin_time, checkout_time):

    # Both are ISO 8601 strings, e.g. '2026-11-07T14:02:00'.
    # Returns hours rounded to 2 decimals, or None if either is missing.
    if checkin_time is None or checkout_time is None:
        return None
    t_in = datetime.datetime.fromisoformat(checkin_time)
    t_out = datetime.datetime.fromisoformat(checkout_time)
    seconds = (t_out - t_in).total_seconds()
    if seconds < 0:
        return None   # checkout before checkin: admin needs to fix it
    return round(seconds / 3600, 2)

#-----------------------------------------------------------------------

# For testing (run: python databasepostgresql.py). Identical to the SQLite version's _test().

def _test():
    print('----------------------------------')
    print('Testing get_user_id() / is_admin()')
    print('----------------------------------')
    print(get_user_id('alice'), get_user_id('nobody'))
    print(is_admin('tdouglas'), is_admin('alice'))
    print()

    print('----------------------------------')
    print('Testing get_event()')
    print('----------------------------------')
    print(get_event(1))
    print(get_event(2)['checkin_code'])   # None: no codes yet
    print(get_event(99))                  # None: no such event
    print()

    print('----------------------------------')
    print('Testing get_rsvp()')
    print('----------------------------------')
    print(get_rsvp(2, 1), get_rsvp(4, 1), get_rsvp(2, 2))  # True False None
    print()

    print('----------------------------------')
    print('Testing get_checkin() / get_checkout()')
    print('----------------------------------')
    print(get_checkin(2, 1))   # alice's checkin
    print(get_checkout(3, 1))  # bob has no checkout: None
    print()

    print('----------------------------------')
    print('Testing add_checkin() (duplicate should fail)')
    print('----------------------------------')
    print(add_checkin(4, 1, '2026-11-07T14:20:00'))  # True
    print(add_checkin(4, 1, '2026-11-07T14:21:00'))  # False (duplicate)
    print()

    print('----------------------------------')
    print('Testing get_attendance()')
    print('----------------------------------')
    for record in get_attendance(1):
        print(record)
    print()

    print('----------------------------------')
    print('Testing update_attendance() then get_hours()')
    print('----------------------------------')
    print(get_hours(2, '2026-01-01', '2026-12-31'))   # [] : not approved yet
    update_attendance(2, 1, '2026-11-07T14:00:00', '2026-11-07T17:00:00',
        True)
    print(get_hours(2, '2026-01-01', '2026-12-31'))   # 3.0 hours
    print(get_hours(2, '2026-12-01', '2026-12-31'))   # [] : out of range
    print()

    print('----------------------------------')
    print('Testing set_event_codes()')
    print('----------------------------------')
    print(set_event_codes(2, 'AAA111', 'BBB222'))   # True
    print(get_event(2)['checkin_code'])             # AAA111
    print(set_event_codes(99, 'x', 'y'))            # False
    print()

    # Put things back the way roh_postgres.sql left them.
    update_attendance(2, 1, '2026-11-07T14:02:00', '2026-11-07T16:58:00',
        False)
    update_attendance(4, 1, None, None, False)
    set_event_codes(2, None, None)

if __name__ == '__main__':
    _test()
    _connection_pool.close()   # otherwise the pool's threads complain at exit
