import hashlib
import json
import unittest
from http.cookies import SimpleCookie

from fastapi import HTTPException

from src import app as activity_app


class StudentRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.original_activities = activity_app.activities
        self.original_students = activity_app.students
        self.original_student_sessions = activity_app.student_sessions.copy()
        self.original_teacher_sessions = activity_app.teacher_sessions.copy()
        activity_app.activities = {
            "Chess Club": {
                "category": "Academic",
                "schedule": "Fridays, 3:30 PM - 5:00 PM",
                "max_participants": 2,
                "participants": ["existing@mergington.edu"],
            },
            "Art Club": {
                "category": "Arts & Culture",
                "schedule": "Thursdays, 3:30 PM - 5:00 PM",
                "max_participants": 10,
                "participants": ["new.student@mergington.edu"],
            },
            "Debate Team": {
                "category": "Academic",
                "schedule": "Fridays, 4:00 PM - 5:30 PM",
                "max_participants": 12,
                "participants": ["another.student@mergington.edu"],
            }
        }
        activity_app.students = {}
        activity_app.student_sessions.clear()
        activity_app.teacher_sessions.clear()

    def tearDown(self):
        activity_app.activities = self.original_activities
        activity_app.students = self.original_students
        activity_app.student_sessions.clear()
        activity_app.student_sessions.update(self.original_student_sessions)
        activity_app.teacher_sessions.clear()
        activity_app.teacher_sessions.update(self.original_teacher_sessions)

    def create_student_account(self, email, password):
        salt = b"test-student-salt"
        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            activity_app.PASSWORD_HASH_ITERATIONS,
        ).hex()
        activity_app.students = {
            email: {"salt": salt.hex(), "password_hash": password_hash}
        }

    def test_student_login_creates_http_only_session(self):
        email = "new.student@mergington.edu"
        self.create_student_account(email, "assigned-password")

        response = activity_app.student_login(
            activity_app.StudentLoginRequest(
                email=email.upper(),
                password="assigned-password",
            ),
            None,
        )

        cookie = SimpleCookie()
        cookie.load(response.headers["set-cookie"])
        token = cookie["student_session_token"].value
        self.assertTrue(cookie["student_session_token"]["httponly"])
        self.assertEqual(activity_app.require_student(token), email)
        self.assertEqual(
            json.loads(response.body),
            {"authenticated": True, "email": email},
        )

    def test_student_registration_rejects_duplicates_and_full_activities(self):
        activity_app.student_sessions["student-token"] = (
            "new.student@mergington.edu",
            activity_app.time.time() + 60,
        )
        student_email = activity_app.require_student("student-token")

        activity_app.register_for_activity("Chess Club", student_email)

        with self.assertRaises(HTTPException) as duplicate:
            activity_app.register_for_activity(
                "Chess Club",
                student_email.upper(),
            )
        self.assertEqual(duplicate.exception.status_code, 400)
        self.assertEqual(
            duplicate.exception.detail,
            "Student is already signed up",
        )

        with self.assertRaises(HTTPException) as full:
            activity_app.register_for_activity(
                "Chess Club",
                "another.student@mergington.edu",
            )
        self.assertEqual(full.exception.status_code, 400)
        self.assertEqual(full.exception.detail, "Activity is full")
        self.assertEqual(
            activity_app.activities["Chess Club"]["participants"],
            [
                "existing@mergington.edu",
                "new.student@mergington.edu",
            ],
        )

    def test_teacher_can_still_register_and_unregister_students(self):
        activity_app.signup_for_activity(
            "Chess Club",
            "new.student@mergington.edu",
            "teacher",
        )
        activity_app.unregister_from_activity(
            "Chess Club",
            "new.student@mergington.edu",
            "teacher",
        )

        self.assertEqual(
            activity_app.activities["Chess Club"]["participants"],
            ["existing@mergington.edu"],
        )

    def test_student_registration_requires_an_authenticated_session(self):
        with self.assertRaises(HTTPException) as unauthorized:
            activity_app.require_student(None)

        self.assertEqual(unauthorized.exception.status_code, 401)
        self.assertEqual(
            unauthorized.exception.detail,
            "Student login required",
        )

    def test_my_activities_only_returns_activities_for_authenticated_identity(self):
        student_activities = activity_app.get_student_activities(
            "new.student@mergington.edu"
        )

        self.assertEqual(list(student_activities), ["Art Club"])
        self.assertEqual(student_activities["Art Club"]["category"], "Arts & Culture")
        self.assertEqual(
            student_activities["Art Club"]["schedule"],
            "Thursdays, 3:30 PM - 5:00 PM",
        )

        activity_app._unregister_participant(
            "Art Club",
            "new.student@mergington.edu",
        )
        self.assertEqual(
            activity_app.get_student_activities("new.student@mergington.edu"),
            {},
        )

        other_students_activities = activity_app.get_student_activities(
            "another.student@mergington.edu"
        )
        self.assertEqual(list(other_students_activities), ["Debate Team"])

    def test_my_activities_endpoint_takes_identity_only_from_student_session(self):
        operation = activity_app.app.openapi()["paths"]["/student/activities"]["get"]
        parameters = operation.get("parameters", [])

        self.assertFalse(
            any(parameter["in"] == "query" for parameter in parameters)
        )
        self.assertIn(
            ("student_session_token", "cookie"),
            [(parameter["name"], parameter["in"]) for parameter in parameters],
        )
        self.assertEqual(
            activity_app.get_student_activities("unknown@mergington.edu"),
            {},
        )


if __name__ == "__main__":
    unittest.main()
