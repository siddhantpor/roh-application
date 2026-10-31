## Set up prototype instructions

```
source .venv/bin/activate
```

Run check-in subsystem:

```
python backend/runcheckin.py PORT
```

In another terminal, run event management subsystem:

```
python backend/app.py
```

Then, navigate to these screens:<br>
http://127.0.0.1:5001/admin/events<br>
http://127.0.0.1:5001/member/events<br>
http://127.0.0.1:5001/admin/events/create

Demo:

- Event creation for admins (events table in neon is updated accordingly)
- As a student checkin into event 1
- As an admin

Overview of three tier system:

- Frontend: HTML and CSS templates
- Backend: Flask routes and Python based logic
- Data: PostgreSQL hosted on Neon
