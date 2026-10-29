-- seed_neon.sql
-- Demo rows for the team's Neon schema, for testing. Safe to re-run:
-- it only deletes rows it inserted (usernames below, titles below).
DELETE FROM attendance WHERE user_id IN (SELECT user_id FROM accounts WHERE username IN ('tdouglas','alice','bob','carol'));
DELETE FROM rsvps      WHERE user_id IN (SELECT user_id FROM accounts WHERE username IN ('tdouglas','alice','bob','carol'));
DELETE FROM volunteerhours WHERE user_id IN (SELECT user_id FROM accounts WHERE username IN ('tdouglas','alice','bob','carol'));
DELETE FROM accounts WHERE username IN ('tdouglas','alice','bob','carol');
DELETE FROM events WHERE event_title IN ('Park Cleanup','Food Bank Sorting');

INSERT INTO accounts (username, password, email, is_admin, display_name, approved, pending) VALUES
 ('tdouglas', 'x', 'tdouglas@example.com', true,  'Tyneisha Douglas', true, false),
 ('alice',    'x', 'alice@example.com',    false, 'Alice',            true, false),
 ('bob',      'x', 'bob@example.com',      false, 'Bob',              true, false),
 ('carol',    'x', 'carol@example.com',    false, 'Carol',            true, false);

INSERT INTO events (event_date, event_starttime, event_endtime, event_title, event_descrip, event_locat, checkin_code, checkout_code) VALUES
 ('2026-11-07', '09:00', '12:00', 'Park Cleanup',      'Bring gloves. Closed-toe shoes required.',   'Mercer County Park',        'ABC123', 'XYZ789'),
 ('2026-11-14', '13:00', '16:00', 'Food Bank Sorting', 'Sorting donations at the Trenton food bank.', 'Trenton Area Soup Kitchen', NULL,     NULL);

INSERT INTO rsvps (user_id, event_id, time, accepted)
SELECT a.user_id, e.event_id, '2026-10-20T15:00:00', (a.username <> 'carol')
FROM accounts a, events e
WHERE a.username IN ('alice','bob','carol') AND e.event_title = 'Park Cleanup';

-- alice: in + out (unapproved); bob: in only.
INSERT INTO attendance (user_id, event_id, time, approved, is_checkin)
SELECT a.user_id, e.event_id, t.time, false, t.is_checkin
FROM (VALUES ('alice', '2026-11-07T14:02:00'::timestamp, true),
             ('alice', '2026-11-07T16:58:00'::timestamp, false),
             ('bob',   '2026-11-07T14:10:00'::timestamp, true)) AS t(username, time, is_checkin)
JOIN accounts a ON a.username = t.username
JOIN events e ON e.event_title = 'Park Cleanup';
