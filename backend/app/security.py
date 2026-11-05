from functools import wraps

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import abort
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from .extensions import db
from .models import Course, CourseStaff, Enrollment, User

_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def check_password(hashed: str, pw: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except VerifyMismatchError:
        return False


def current_user() -> User:
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        abort(401, "User no longer exists")
    return user


def login_required(*roles):
    """Require a logged-in user, optionally with one of the given roles."""

    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = current_user()
            if roles and user.role not in roles:
                abort(403, "Not allowed for your role")
            return fn(user, *args, **kwargs)

        return wrapper

    return deco


def can_manage(user: User, course: Course) -> bool:
    """Admins manage all courses, teachers their own, TAs only courses they're assigned to."""
    if user.role == "admin" or course.teacher_id == user.id:
        return True
    if user.role == "ta":
        return (
            db.session.query(CourseStaff)
            .filter_by(user_id=user.id, course_id=course.id)
            .first()
            is not None
        )
    return False


def is_enrolled(user: User, course: Course) -> bool:
    return (
        db.session.query(Enrollment)
        .filter_by(user_id=user.id, course_id=course.id)
        .first()
        is not None
    )


def can_view(user: User, course: Course) -> bool:
    return can_manage(user, course) or is_enrolled(user, course)
