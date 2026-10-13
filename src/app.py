"""
High School Management System API

A super simple FastAPI application that allows students to view and sign up
for extracurricular activities at Mergington High School.
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from copy import deepcopy
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Mergington High School API",
              description="API for viewing and signing up for extracurricular activities")

# Mount the static files directory
current_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=os.path.join(Path(__file__).parent,
          "static")), name="static")

# In-memory activity database
with (current_dir / "activities.json").open(encoding="utf-8") as activities_file:
    activities = json.load(activities_file)

with (current_dir / "teachers.json").open(encoding="utf-8") as teachers_file:
    teachers = json.load(teachers_file)["teachers"]

with (current_dir / "students.json").open(encoding="utf-8") as students_file:
    students = json.load(students_file)["students"]

PASSWORD_HASH_ITERATIONS = 600_000
SESSION_DURATION_SECONDS = 8 * 60 * 60
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "").lower() in {"1", "true", "yes"}
teacher_sessions: dict[str, tuple[str, float]] = {}
student_sessions: dict[str, tuple[str, float]] = {}
activity_lock = threading.Lock()
session_lock = threading.Lock()


class LoginRequest(BaseModel):
    username: str
    password: str


class StudentLoginRequest(BaseModel):
    email: str
    password: str


def _active_session(
    session_token: str | None,
    sessions: dict[str, tuple[str, float]],
) -> str | None:
    with session_lock:
        session = sessions.get(session_token or "")
        if session is None:
            return None
        if session[1] <= time.time():
            sessions.pop(session_token or "", None)
            return None
        return session[0]


def require_teacher(
    session_token: str | None = Cookie(default=None, alias="session_token"),
) -> str:
    username = _active_session(session_token, teacher_sessions)
    if username is None:
        raise HTTPException(status_code=401, detail="Teacher login required")
    return username


def require_student(
    session_token: str | None = Cookie(default=None, alias="student_session_token"),
) -> str:
    email = _active_session(session_token, student_sessions)
    if email is None:
        raise HTTPException(status_code=401, detail="Student login required")
    return email


def _set_session_cookie(response: JSONResponse, cookie_name: str, token: str) -> None:
    response.set_cookie(
        cookie_name,
        token,
        max_age=SESSION_DURATION_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
        path="/",
    )


def _clear_session_cookie(response: JSONResponse, cookie_name: str) -> None:
    response.delete_cookie(
        cookie_name,
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
    )


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/auth/session")
def get_teacher_session(
    session_token: str | None = Cookie(default=None, alias="session_token"),
):
    username = _active_session(session_token, teacher_sessions)
    if username is None:
        return JSONResponse(
            {"authenticated": False},
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        {"authenticated": True, "username": username},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/auth/login")
def login(
    credentials: LoginRequest,
    student_session_token: str | None = Cookie(
        default=None, alias="student_session_token"
    ),
):
    teacher = teachers.get(credentials.username)
    salt = bytes.fromhex(teacher["salt"]) if teacher else b"invalid-teacher-salt"
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        credentials.password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    expected_hash = teacher["password_hash"] if teacher else "0" * 64
    if not hmac.compare_digest(password_hash, expected_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    now = time.time()
    session_token = secrets.token_urlsafe(32)
    with session_lock:
        for token in [
            token for token, (_, expires_at) in teacher_sessions.items()
            if expires_at <= now
        ]:
            teacher_sessions.pop(token)
        teacher_sessions[session_token] = (
            credentials.username,
            now + SESSION_DURATION_SECONDS,
        )
        if student_session_token:
            student_sessions.pop(student_session_token, None)
    login_response = JSONResponse(
        {"authenticated": True, "username": credentials.username},
        headers={"Cache-Control": "no-store"},
    )
    _set_session_cookie(login_response, "session_token", session_token)
    _clear_session_cookie(login_response, "student_session_token")
    return login_response


@app.get("/auth/student/session")
def get_student_session(
    session_token: str | None = Cookie(
        default=None, alias="student_session_token"
    ),
):
    email = _active_session(session_token, student_sessions)
    if email is None:
        return JSONResponse(
            {"authenticated": False},
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        {"authenticated": True, "email": email},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/auth/student/login")
def student_login(
    credentials: StudentLoginRequest,
    teacher_session_token: str | None = Cookie(
        default=None, alias="session_token"
    ),
):
    email = credentials.email.strip().lower()
    student = students.get(email)
    salt = bytes.fromhex(student["salt"]) if student else b"invalid-student-salt"
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        credentials.password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    expected_hash = student["password_hash"] if student else "0" * 64
    if not hmac.compare_digest(password_hash, expected_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    now = time.time()
    session_token = secrets.token_urlsafe(32)
    with session_lock:
        for token in [
            token for token, (_, expires_at) in student_sessions.items()
            if expires_at <= now
        ]:
            student_sessions.pop(token)
        student_sessions[session_token] = (
            email,
            now + SESSION_DURATION_SECONDS,
        )
        if teacher_session_token:
            teacher_sessions.pop(teacher_session_token, None)
    login_response = JSONResponse(
        {"authenticated": True, "email": email},
        headers={"Cache-Control": "no-store"},
    )
    _set_session_cookie(login_response, "student_session_token", session_token)
    _clear_session_cookie(login_response, "session_token")
    return login_response


@app.post("/auth/logout")
def logout(
    session_token: str | None = Cookie(default=None, alias="session_token"),
):
    with session_lock:
        if session_token:
            teacher_sessions.pop(session_token, None)
    logout_response = JSONResponse(
        {"authenticated": False},
        headers={"Cache-Control": "no-store"},
    )
    _clear_session_cookie(logout_response, "session_token")
    return logout_response


@app.post("/auth/student/logout")
def student_logout(
    session_token: str | None = Cookie(
        default=None, alias="student_session_token"
    ),
):
    with session_lock:
        if session_token:
            student_sessions.pop(session_token, None)
    logout_response = JSONResponse(
        {"authenticated": False},
        headers={"Cache-Control": "no-store"},
    )
    _clear_session_cookie(logout_response, "student_session_token")
    return logout_response


@app.get("/activities")
def get_activities():
    with activity_lock:
        return deepcopy(activities)


@app.get("/student/activities")
def get_student_activities(student_email: str = Depends(require_student)):
    """Return only activities registered to the authenticated student."""
    normalized_email = student_email.strip().lower()
    with activity_lock:
        return {
            name: deepcopy(activity)
            for name, activity in activities.items()
            if any(
                participant.strip().lower() == normalized_email
                for participant in activity["participants"]
            )
        }


@app.post("/activities/{activity_name}/signup")
def signup_for_activity(
    activity_name: str,
    email: str,
    _teacher: str = Depends(require_teacher),
):
    """Sign up a student for an activity"""
    return _add_participant(activity_name, email)


@app.post("/activities/{activity_name}/register")
def register_for_activity(
    activity_name: str,
    student_email: str = Depends(require_student),
):
    """Register the authenticated student for an activity."""
    return _add_participant(activity_name, student_email)


def _add_participant(activity_name: str, email: str):
    normalized_email = email.strip().lower()
    with activity_lock:
        # Validate activity exists
        if activity_name not in activities:
            raise HTTPException(status_code=404, detail="Activity not found")

        activity = activities[activity_name]

        # Reject duplicate registrations before checking capacity.
        if any(
            participant.strip().lower() == normalized_email
            for participant in activity["participants"]
        ):
            raise HTTPException(
                status_code=400,
                detail="Student is already signed up",
            )

        if len(activity["participants"]) >= activity["max_participants"]:
            raise HTTPException(status_code=400, detail="Activity is full")

        activity["participants"].append(normalized_email)
    return {"message": f"Signed up {normalized_email} for {activity_name}"}


def _unregister_participant(activity_name: str, email: str):
    normalized_email = email.strip().lower()
    with activity_lock:
        # Validate activity exists
        if activity_name not in activities:
            raise HTTPException(status_code=404, detail="Activity not found")

        activity = activities[activity_name]

        # Validate student is signed up
        registered_email = next(
            (
                participant
                for participant in activity["participants"]
                if participant.strip().lower() == normalized_email
            ),
            None,
        )
        if registered_email is None:
            raise HTTPException(
                status_code=400,
                detail="Student is not signed up for this activity",
            )

        activity["participants"].remove(registered_email)
    return {"message": f"Unregistered {registered_email} from {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister_from_activity(
    activity_name: str,
    email: str,
    _teacher: str = Depends(require_teacher),
):
    """Unregister a student from an activity"""
    return _unregister_participant(activity_name, email)
