#!/usr/bin/env python

#-----------------------------------------------------------------------
# databasesqlite.py
# SQLite version of the database functions (check-in / check-out /
# hours). For local dev; databasepostgresql.py is the Neon version.
# One function per query, dicts out.
#-----------------------------------------------------------------------

import sqlite3
import contextlib
import datetime
from flask import current_app

#-----------------------------------------------------------------------

def _connect(readonly=False):
    uri = 'file:' + current_app.config['SQLITE_PATH'] + ('?mode=ro' if readonly else '?mode=rw')
    connection = sqlite3.connect(uri, uri=True, isolation_level=None)
    connection.execute('PRAGMA foreign_keys = ON')
    return connection

#-----------------------------------------------------------------------
# Accounts
#-----------------------------------------------------------------------

def get_user_id(username):

    with contextlib.closing(
        _connect(readonly=True)) as connection:

        with contextlib.closing(connection.cursor()) as cursor:

            query_str = '''
                SELECT user_id FROM accounts WHERE username = ?
                '''
            cursor.execute(query_str, [username])
            table = cursor.fetchall()
            if len(table) != 1:
                return None
            return table[0][0]

#-----------------------------------------------------------------------

def is_admin(username):

    with contextlib.closing(
        _connect(readonly=True)) as connection:

        with contextlib.closing(connection.cursor()) as cursor:

            query_str = '''
                SELECT is_admin FROM accounts WHERE username = ?
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

    with contextlib.closing(
        _connect(readonly=True)) as connection:

        with contextlib.closing(connection.cursor()) as cursor:

            query_str = '''
                SELECT event_id, event_date, start_time, end_time,
                       event_title, event_descrip, event_locat,
                       graphic_link, checkin_code, checkout_code, graphic_public_id,
                       (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = events.event_id AND r.accepted = 1)
                FROM events WHERE event_id = ?
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
                'checkin_code': row[8], 'checkout_code': row[9],
                'graphic_public_id': row[10], 'attending': row[11]}
            return event

#-----------------------------------------------------------------------

def set_event_codes(event_id, checkin_code, checkout_code):

    with contextlib.closing(
        _connect()) as connection:

        with contextlib.closing(connection.cursor()) as cursor:

            query_str = '''
                UPDATE events
                SET checkin_code = ?, checkout_code = ?
                WHERE event_id = ?
                '''
            cursor.execute(query_str,
                [checkin_code, checkout_code, event_id])
            return cursor.rowcount == 1

#-----------------------------------------------------------------------
# RSVPs (read only here; writing RSVPs is the event-management
# subsystem's job)
#-----------------------------------------------------------------------

def get_rsvp(user_id, event_id):

    with contextlib.closing(
        _connect(readonly=True)) as connection:

        with contextlib.closing(connection.cursor()) as cursor:

            query_str = '''
                SELECT accepted FROM rsvps
                WHERE user_id = ? AND event_id = ?
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

# The two tables have identical shapes, so the real work is shared.
# The table name is substituted into the SQL with an f-string, which
# is safe ONLY because it comes from our own code, never from the user.
# Values from the user always go through the ? placeholders.

def _get_record(table_name, user_id, event_id):

    with contextlib.closing(
        _connect(readonly=True)) as connection:

        with contextlib.closing(connection.cursor()) as cursor:

            query_str = f'''
                SELECT time, approved FROM {table_name}
                WHERE user_id = ? AND event_id = ?
                '''
            cursor.execute(query_str, [user_id, event_id])
            table = cursor.fetchall()
            if len(table) != 1:
                return None
            record = {'time': table[0][0], 'approved': table[0][1] == 1}
            return record

#-----------------------------------------------------------------------

def _add_record(table_name, user_id, event_id, time):

    with contextlib.closing(
        _connect()) as connection:

        with contextlib.closing(connection.cursor()) as cursor:

            query_str = f'''
                INSERT INTO {table_name} (user_id, event_id, time, approved)
                VALUES (?, ?, ?, 0)
                '''
            try:
                cursor.execute(query_str, [user_id, event_id, time])
            except sqlite3.IntegrityError:
                return False   # already checked in/out of this event
            return True

#-----------------------------------------------------------------------
# Admin review of an event's attendance
#-----------------------------------------------------------------------

def get_attendance(event_id):

    attendance = []

    with contextlib.closing(
        _connect(readonly=True)) as connection:

        with contextlib.closing(connection.cursor()) as cursor:

            # LEFT JOIN so a member who checked in but never checked
            # out still appears, with NULL for the checkout columns.
            query_str = '''
                SELECT a.user_id, a.display_name,
                       c.time, c.approved, o.time, o.approved
                FROM checkins c
                JOIN accounts a ON a.user_id = c.user_id
                LEFT JOIN checkouts o
                    ON o.user_id = c.user_id AND o.event_id = c.event_id
                WHERE c.event_id = ?
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

    # Replace both records in one transaction. A None time means
    # "no record", so an admin can clear a bad checkout.

    with contextlib.closing(
        _connect()) as connection:

        with contextlib.closing(connection.cursor()) as cursor:

            cursor.execute('BEGIN')

            for table_name, time in [('checkins', checkin_time),
                                     ('checkouts', checkout_time)]:
                query_str = f'''
                    DELETE FROM {table_name}
                    WHERE user_id = ? AND event_id = ?
                    '''
                cursor.execute(query_str, [user_id, event_id])
                if time is not None:
                    query_str = f'''
                        INSERT INTO {table_name}
                            (user_id, event_id, time, approved)
                        VALUES (?, ?, ?, ?)
                        '''
                    cursor.execute(query_str,
                        [user_id, event_id, time, 1 if approved else 0])

            cursor.execute('COMMIT')

#-----------------------------------------------------------------------
# Hours (for the member "My Hours" view). Only approved pairs count.
#-----------------------------------------------------------------------

def get_hours(user_id, start_date, end_date):

    hours = []

    with contextlib.closing(
        _connect(readonly=True)) as connection:

        with contextlib.closing(connection.cursor()) as cursor:

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
                WHERE c.user_id = ?
                  AND c.approved = 1 AND o.approved = 1
                  AND e.event_date BETWEEN ? AND ?
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

@contextlib.contextmanager
def _transaction():
    with contextlib.closing(_connect()) as connection:
        connection.execute('BEGIN')
        with connection:
            yield connection

# Integrated account/event operations. Both adapters expose the same interface.
def get_account(user_id):
    with _transaction() as connection:
        row = connection.execute('''
            SELECT user_id, username, email, display_name, is_admin, auth0_sub, approved, pending
            FROM accounts WHERE user_id = ?
        ''', [user_id]).fetchone()
    if row is None:
        return None
    return dict(zip(('user_id', 'username', 'email', 'display_name', 'is_admin',
                     'auth0_sub', 'approved', 'pending'), row),
                is_admin=bool(row[4]), approved=bool(row[6]), pending=bool(row[7]))


def link_auth0_user(subject, email, name, bootstrap_admin=False):
    with _transaction() as connection:
        row = connection.execute('SELECT user_id FROM accounts WHERE auth0_sub = ?', [subject]).fetchone()
        if row:
            user_id = row[0]
        else:
            matches = connection.execute(
                'SELECT user_id, auth0_sub FROM accounts WHERE lower(email) = ?', [email]).fetchall()
            if len(matches) > 1 or (matches and matches[0][1] is not None):
                raise ValueError('Email is ambiguous or already linked')
            if matches:
                user_id = matches[0][0]
                connection.execute('''
                    UPDATE accounts SET auth0_sub = ?, display_name = ?,
                        is_admin = CASE WHEN ? THEN ? ELSE is_admin END
                    WHERE user_id = ? AND auth0_sub IS NULL
                ''', [subject, name, bootstrap_admin, True, user_id])
            else:
                user_id = connection.execute('''
                    INSERT INTO accounts (username, password, email, display_name, is_admin,
                                          approved, pending, auth0_sub)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING user_id
                ''', [subject, '', email, name, bootstrap_admin, bootstrap_admin, not bootstrap_admin, subject]).fetchone()[0]
    return get_account(user_id)


def set_admin(email, enabled):
    with _transaction() as connection:
        matches = connection.execute(
            'SELECT user_id FROM accounts WHERE lower(email) = ? AND auth0_sub IS NOT NULL',
            [email]).fetchall()
        if len(matches) != 1:
            return False
        connection.execute('UPDATE accounts SET is_admin = ? WHERE user_id = ?', [enabled, matches[0][0]])
    return True


def update_event(event_id, event_date, start_time, end_time, event_title, event_descrip,
                 event_locat, graphic_link, graphic_public_id):
    with _transaction() as connection:
        connection.execute('''
            UPDATE events SET event_date = ?, start_time = ?, end_time = ?,
                event_title = ?, event_descrip = ?, event_locat = ?,
                graphic_link = ?, graphic_public_id = ? WHERE event_id = ?
        ''', [event_date, start_time, end_time, event_title, event_descrip, event_locat,
              graphic_link, graphic_public_id, event_id])


def add_event(event_date, start_time, end_time, event_title, event_descrip, event_locat,
                 graphic_link=None, graphic_public_id=None):
    with _transaction() as connection:
        return connection.execute('''
            INSERT INTO events (event_date, start_time, end_time, event_title,
                                event_descrip, event_locat, graphic_link, graphic_public_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING event_id
        ''', [event_date, start_time, end_time, event_title, event_descrip, event_locat,
              graphic_link, graphic_public_id]).fetchone()[0]


def get_events():
    with _transaction() as connection:
        ids = connection.execute('SELECT event_id FROM events ORDER BY event_date, start_time').fetchall()
    return [get_event(row[0]) for row in ids]


def set_rsvp(user_id, event_id, accepted):
    with _transaction() as connection:
        connection.execute('''INSERT INTO rsvps (user_id, event_id, accepted, time)
            VALUES (?, ?, ?, ?) ON CONFLICT(user_id, event_id)
            DO UPDATE SET accepted=excluded.accepted, time=excluded.time''',
            [user_id, event_id, accepted, datetime.datetime.now(datetime.timezone.utc).isoformat()])


def get_attendees(event_id):
    with _transaction() as connection:
        rows = connection.execute('''SELECT a.display_name, r.accepted
            FROM accounts a LEFT JOIN rsvps r ON a.user_id = r.user_id AND r.event_id = ?
            WHERE a.is_admin = 0 ORDER BY a.display_name''', [event_id]).fetchall()
    return [{'name': row[0], 'status': 'Pending' if row[1] is None else
             ('Going' if row[1] else 'Not Going')} for row in rows]


def migrate():
    with _transaction() as connection:
        for table, column in [('accounts', 'auth0_sub'), ('events', 'graphic_public_id')]:
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info({table})')}
            if column not in columns:
                connection.execute(f'ALTER TABLE {table} ADD COLUMN {column} TEXT')
        connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS accounts_auth0_sub_unique ON accounts(auth0_sub)')


def get_members():
    with _transaction() as connection:
        rows = connection.execute('''
            SELECT user_id, display_name, email, is_admin, approved, pending, auth0_sub
            FROM accounts ORDER BY pending DESC, display_name
        ''').fetchall()
    return [dict(zip(('user_id', 'name', 'email', 'is_admin', 'approved', 'pending', 'auth0_sub'), row))
            for row in rows]
