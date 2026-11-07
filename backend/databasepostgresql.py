"""PostgreSQL queries for accounts, events, RSVPs, and attendance."""
import atexit
import datetime
from flask import current_app
import psycopg
import psycopg_pool

def init_app(app):
    pool = psycopg_pool.ConnectionPool(app.config['DATABASE_URL'], open=False)
    app.extensions['database_pool'] = pool
    atexit.register(pool.close)


def _get_pool():
    pool = current_app.extensions['database_pool']
    if pool.closed:
        pool.open()
    return pool

#-----------------------------------------------------------------------
# Accounts
#-----------------------------------------------------------------------

def get_user_id(username):

    with _get_pool().connection() as connection:
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

    with _get_pool().connection() as connection:
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

    with _get_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT e.event_id, e.event_date, e.event_starttime,
                       e.event_endtime, e.event_title, e.event_descrip,
                       e.event_locat, e.graphic_link, e.checkin_code,
                       e.checkout_code, e.graphic_public_id,
                       (SELECT COUNT(*) FROM
                           (SELECT DISTINCT ON (user_id) accepted FROM rsvps
                            WHERE event_id = e.event_id ORDER BY user_id, time DESC) latest
                         WHERE latest.accepted = true)
                FROM events e WHERE e.event_id = %s
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
                'checkin_code': row[8], 'checkout_code': row[9],
                'graphic_public_id': row[10], 'attending': row[11]}

#-----------------------------------------------------------------------

def set_event_codes(event_id, checkin_code, checkout_code):

    with _get_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''
                UPDATE events
                SET checkin_code = %s, checkout_code = %s
                WHERE event_id = %s
                ''', [checkin_code, checkout_code, event_id])
            connection.commit()
            return cursor.rowcount == 1

#-----------------------------------------------------------------------

def get_events():
    events = []
    with _get_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT 
                    e.event_id, e.event_date, e.event_starttime,
                    e.event_endtime, e.event_title, e.event_descrip,
                    e.event_locat, e.graphic_link, e.checkin_code,
                    e.checkout_code, e.graphic_public_id,
                    (SELECT COUNT(*) FROM
                           (SELECT DISTINCT ON (user_id) accepted FROM rsvps
                            WHERE event_id = e.event_id ORDER BY user_id, time DESC) latest
                         WHERE latest.accepted = true)
                FROM events e
                ORDER BY e.event_date, e.event_starttime
                ''')
            for row in cursor.fetchall():
                events.append({
                    'event_id': row[0],
                    'event_date': _date_text(row[1]),
                    'start_time': _time_text(row[2]),
                    'end_time': _time_text(row[3]),
                    'event_title': row[4], 
                    'event_descrip': row[5],
                    'event_locat': row[6], 
                    'graphic_link': row[7],
                    'checkin_code': row[8], 
                    'checkout_code': row[9],
                    'graphic_public_id': row[10], 'attending': row[11]})
    return events

#-----------------------------------------------------------------------

#-----------------------------------------------------------------------
# RSVPs
#-----------------------------------------------------------------------

def get_rsvp(user_id, event_id):

    with _get_pool().connection() as connection:
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

    with _get_pool().connection() as connection:
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

    with _get_pool().connection() as connection:
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
    with _get_pool().connection() as connection:
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
    with _get_pool().connection() as connection:
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
    with _get_pool().connection() as connection:
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
# Conversions: PostgreSQL gives date/time/datetime objects.
# Routes and templates use ISO strings.
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

# Account linking, membership, and event poster operations.
def get_account(user_id):
    with _get_pool().connection() as connection:
        row = connection.execute('''
            SELECT user_id, username, email, display_name, is_admin, auth0_sub, approved, pending
            FROM accounts WHERE user_id = %s
        ''', [user_id]).fetchone()
    if row is None:
        return None
    return {'user_id': row[0], 'username': row[1], 'email': row[2],
            'display_name': row[3], 'is_admin': bool(row[4]), 'auth0_sub': row[5],
            'approved': bool(row[6]), 'pending': bool(row[7])}


def link_auth0_user(subject, email, name, bootstrap_admin=False):
    with _get_pool().connection() as connection:
        row = connection.execute('SELECT user_id FROM accounts WHERE auth0_sub = %s', [subject]).fetchone()
        if row:
            user_id = row[0]
        else:
            matches = connection.execute(
                'SELECT user_id, auth0_sub FROM accounts WHERE lower(email) = %s', [email]).fetchall()
            if len(matches) > 1 or (matches and matches[0][1] is not None):
                raise ValueError('Email is ambiguous or already linked')
            if matches:
                user_id = matches[0][0]
                connection.execute('''
                    UPDATE accounts SET auth0_sub = %s, display_name = %s,
                        is_admin = CASE WHEN %s THEN %s ELSE is_admin END
                    WHERE user_id = %s AND auth0_sub IS NULL
                ''', [subject, name, bootstrap_admin, True, user_id])
            else:
                user_id = connection.execute('''
                    INSERT INTO accounts (username, password, email, display_name, is_admin,
                                          approved, pending, auth0_sub)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING user_id
                ''', [subject, '', email, name, bootstrap_admin, bootstrap_admin, not bootstrap_admin, subject]).fetchone()[0]
    return get_account(user_id)


def set_admin(email, enabled):
    with _get_pool().connection() as connection:
        matches = connection.execute(
            'SELECT user_id FROM accounts WHERE lower(email) = %s AND auth0_sub IS NOT NULL',
            [email]).fetchall()
        if len(matches) != 1:
            return False
        connection.execute('UPDATE accounts SET is_admin = %s WHERE user_id = %s', [enabled, matches[0][0]])
    return True


def update_event(event_id, event_date, start_time, end_time, event_title, event_descrip,
                 event_locat, graphic_link, graphic_public_id):
    with _get_pool().connection() as connection:
        connection.execute('''
            UPDATE events SET event_date = %s, event_starttime = %s, event_endtime = %s,
                event_title = %s, event_descrip = %s, event_locat = %s,
                graphic_link = %s, graphic_public_id = %s WHERE event_id = %s
        ''', [event_date, start_time, end_time, event_title, event_descrip, event_locat,
              graphic_link, graphic_public_id, event_id])


def add_event(event_date, start_time, end_time, event_title, event_descrip, event_locat,
                 graphic_link=None, graphic_public_id=None):
    with _get_pool().connection() as connection:
        return connection.execute('''
            INSERT INTO events (event_date, event_starttime, event_endtime, event_title,
                                event_descrip, event_locat, graphic_link, graphic_public_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING event_id
        ''', [event_date, start_time, end_time, event_title, event_descrip, event_locat,
              graphic_link, graphic_public_id]).fetchone()[0]


def migrate():
    from pathlib import Path
    with _get_pool().connection() as connection:
        connection.execute(Path(__file__).with_name('migrate_auth_posters.sql').read_text())


def get_members():
    with _get_pool().connection() as connection:
        rows = connection.execute('''
            SELECT user_id, display_name, email, is_admin, approved, pending, auth0_sub
            FROM accounts ORDER BY pending DESC, display_name
        ''').fetchall()
    return [{'user_id': row[0], 'name': row[1], 'email': row[2],
             'is_admin': bool(row[3]), 'approved': bool(row[4]),
             'pending': bool(row[5]), 'auth0_sub': row[6]} for row in rows]


def set_membership(user_id, approved):
    # Keep the account and its volunteer history. Admins cannot be disabled here.
    with _get_pool().connection() as connection:
        cursor = connection.execute('''
            UPDATE accounts SET approved = %s, pending = %s
            WHERE user_id = %s AND COALESCE(is_admin, FALSE) = FALSE
              AND auth0_sub IS NOT NULL
        ''', [approved, False, user_id])
        return cursor.rowcount == 1
