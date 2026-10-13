# Mergington High School Activities API

A super simple FastAPI application that allows students to view and sign up for extracurricular activities.

## Features

- View all available extracurricular activities
- Teachers can sign up and unregister students after logging in
- Update the activity catalog by editing `activities.json`
- Filter and sort activities, including by category and schedule

## Getting Started

1. Install the dependencies:

   ```
   pip install fastapi uvicorn
   ```

2. Run the application:

   ```
   python app.py
   ```

3. Open your browser and go to:
   - API documentation: http://localhost:8000/docs
   - Alternative documentation: http://localhost:8000/redoc

## API Endpoints

| Method | Endpoint                                                          | Description                                                         |
| ------ | ----------------------------------------------------------------- | ------------------------------------------------------------------- |
| GET    | `/activities`                                                     | Get all activities with their details and current participant count |
| POST   | `/auth/login`                                                      | Log in as a teacher                                                 |
| POST   | `/auth/logout`                                                     | Log out the current teacher                                         |
| POST   | `/activities/{activity_name}/signup?email=student@mergington.edu` | Teacher-only student signup                                         |
| DELETE | `/activities/{activity_name}/unregister?email=student@mergington.edu` | Teacher-only student unregister                                     |

## Teacher accounts

Teacher credentials are read from `teachers.json` beside `app.py`. The file
stores PBKDF2-SHA256 password hashes and random salts, never plaintext passwords.
It starts empty. Generate a record with this command; enter the assigned password
at the hidden prompt, then copy the output into the `teachers` object in
`teachers.json`:

```sh
python - <<'PY'
import getpass
import hashlib
import json
import secrets

username = input("Username: ")
password = getpass.getpass("Assigned password: ")
salt = secrets.token_bytes(16)
password_hash = hashlib.pbkdf2_hmac(
    "sha256", password.encode("utf-8"), salt, 600000
).hex()
print(json.dumps({
    username: {"salt": salt.hex(), "password_hash": password_hash}
}, indent=2))
PY
```

Restart the server after editing the file. Teacher sessions use an HTTP-only,
SameSite=Strict cookie, expire after eight hours, and are cleared when the
server restarts. Set `COOKIE_SECURE=true` when serving the site over HTTPS.
The session store is in memory, so run a single application worker.

Only teacher-authenticated requests can modify activity registrations; students
can continue to view activities and participant lists without logging in.

## Data Model

The initial activity catalog is stored in `activities.json` beside `app.py`.
Edit that file to change activity names, descriptions, schedules, capacities,
categories, or initial participant lists. Set `schedule_days` to the activity's
weekdays and `start_time` in 24-hour `HH:MM` format to keep day-and-time sorting
accurate; keep `schedule` as the human-readable version shown to students. The
server reads the file at startup, so restart it after making changes.

The application uses a simple data model with meaningful identifiers:

1. **Activities** - Uses activity name as identifier:

   - Description
   - Schedule
   - Maximum number of participants allowed
   - List of student emails who are signed up

2. **Students** - Uses email as identifier:
   - Name
   - Grade level

Signup and unregister changes are kept in memory and reset when the server
restarts. To change the starting participant list, edit `activities.json`.
