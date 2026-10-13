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
import time
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

PASSWORD_HASH_ITERATIONS = 600_000
SESSION_DURATION_SECONDS = 8 * 60 * 60
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "").lower() in {"1", "true", "yes"}
teacher_sessions: dict[str, tuple[str, float]] = {}


class LoginRequest(BaseModel):
    username: str
    password: str


def require_teacher(
    session_token: str | None = Cookie(default=None, alias="session_token"),
) -> str:
    session = teacher_sessions.get(session_token or "")
    if session is None or session[1] <= time.time():
        if session_token:
            teacher_sessions.pop(session_token, None)
        raise HTTPException(status_code=401, detail="Teacher login required")
    return session[0]


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/auth/session")
def get_teacher_session(
    session_token: str | None = Cookie(default=None, alias="session_token"),
):
    session = teacher_sessions.get(session_token or "")
    if session is None or session[1] <= time.time():
        if session_token:
            teacher_sessions.pop(session_token, None)
        return JSONResponse(
            {"authenticated": False},
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse(
        {"authenticated": True, "username": session[0]},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/auth/login")
def login(credentials: LoginRequest):
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
    expired_sessions = [
        token for token, (_, expires_at) in teacher_sessions.items()
        if expires_at <= now
    ]
    for token in expired_sessions:
        teacher_sessions.pop(token)

    session_token = secrets.token_urlsafe(32)
    teacher_sessions[session_token] = (
        credentials.username,
        now + SESSION_DURATION_SECONDS,
    )
    login_response = JSONResponse(
        {"authenticated": True, "username": credentials.username},
        headers={"Cache-Control": "no-store"},
    )
    login_response.set_cookie(
        "session_token",
        session_token,
        max_age=SESSION_DURATION_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
        path="/",
    )
    return login_response


@app.post("/auth/logout")
def logout(
    session_token: str | None = Cookie(default=None, alias="session_token"),
):
    if session_token:
        teacher_sessions.pop(session_token, None)
    logout_response = JSONResponse(
        {"authenticated": False},
        headers={"Cache-Control": "no-store"},
    )
    logout_response.delete_cookie(
        "session_token",
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
    )
    return logout_response


@app.get("/activities")
def get_activities():
    return activities


@app.post("/activities/{activity_name}/signup")
def signup_for_activity(
    activity_name: str,
    email: str,
    _teacher: str = Depends(require_teacher),
):
    """Sign up a student for an activity"""
    # Validate activity exists
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Get the specific activity
    activity = activities[activity_name]

    # Validate student is not already signed up
    if email in activity["participants"]:
        raise HTTPException(
            status_code=400,
            detail="Student is already signed up"
        )

    # Add student
    activity["participants"].append(email)
    return {"message": f"Signed up {email} for {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister_from_activity(
    activity_name: str,
    email: str,
    _teacher: str = Depends(require_teacher),
):
    """Unregister a student from an activity"""
    # Validate activity exists
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Get the specific activity
    activity = activities[activity_name]

    # Validate student is signed up
    if email not in activity["participants"]:
        raise HTTPException(
            status_code=400,
            detail="Student is not signed up for this activity"
        )

    # Remove student
    activity["participants"].remove(email)
    return {"message": f"Unregistered {email} from {activity_name}"}
