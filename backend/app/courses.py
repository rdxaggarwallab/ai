from flask import Blueprint, abort, request

from .extensions import db
from .models import Course, Enrollment
from .security import can_manage, can_view, is_enrolled, login_required

bp = Blueprint("courses", __name__)


@bp.get("")
@login_required()
def list_courses(user):
    courses = db.session.query(Course).order_by(Course.code).all()
    enrolled = {
        e.course_id
        for e in db.session.query(Enrollment).filter_by(user_id=user.id).all()
    }
    return [
        {**c.to_dict(), "enrolled": c.id in enrolled, "can_manage": can_manage(user, c)}
        for c in courses
    ]


@bp.post("")
@login_required("teacher", "admin")
def create_course(user):
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    title = (data.get("title") or "").strip()
    if not code or not title:
        abort(400, "Code and title are required")
    if db.session.query(Course).filter_by(code=code).first():
        abort(409, "Course code already exists")
    course = Course(code=code, title=title,
                    description=data.get("description", ""), teacher_id=user.id)
    db.session.add(course)
    db.session.commit()
    return course.to_dict(), 201


@bp.get("/<int:course_id>")
@login_required()
def get_course(user, course_id):
    course = db.get_or_404(Course, course_id)
    return {**course.to_dict(), "enrolled": is_enrolled(user, course),
            "can_manage": can_manage(user, course), "can_view": can_view(user, course)}


@bp.post("/<int:course_id>/enroll")
@login_required("student")
def enroll(user, course_id):
    course = db.get_or_404(Course, course_id)
    if is_enrolled(user, course):
        abort(409, "Already enrolled")
    db.session.add(Enrollment(user_id=user.id, course_id=course.id))
    db.session.commit()
    return {"ok": True}, 201
