from flask import Blueprint, abort

from .extensions import db, limiter
from .models import Course, CourseStaff, Enrollment, new_join_code
from .security import can_manage, can_view, is_enrolled, login_required
from .validate import body, get_str

bp = Blueprint("courses", __name__)


def course_dict(user, c, enrolled):
    staff = can_manage(user, c)
    return {**c.to_dict(staff=staff), "enrolled": enrolled, "can_manage": staff}


@bp.get("")
@login_required()
def list_courses(user):
    """Students see the courses they joined; teachers and TAs the ones they teach; admins all."""
    enrolled = {e.course_id for e in db.session.query(Enrollment).filter_by(user_id=user.id)}
    q = db.session.query(Course)
    if user.role == "student":
        q = q.filter(Course.id.in_(enrolled or {-1}))
    elif user.role == "teacher":
        q = q.filter(Course.teacher_id == user.id)
    elif user.role == "ta":
        staffed = {r.course_id for r in db.session.query(CourseStaff).filter_by(user_id=user.id)}
        q = q.filter(Course.id.in_(staffed or {-1}))
    return [course_dict(user, c, c.id in enrolled) for c in q.order_by(Course.code).all()]


@bp.post("")
@login_required("teacher", "admin")
def create_course(user):
    data = body()
    code = get_str(data, "code", required=True, max_len=30, label="Course code").strip().upper()
    title = get_str(data, "title", required=True, max_len=200).strip()
    description = get_str(data, "description", max_len=5000)
    if db.session.query(Course).filter_by(code=code).first():
        abort(409, "Course code already exists")
    course = Course(code=code, title=title, description=description, teacher_id=user.id)
    db.session.add(course)
    db.session.commit()
    return course_dict(user, course, False), 201


@bp.get("/<int:course_id>")
@login_required()
def get_course(user, course_id):
    course = db.get_or_404(Course, course_id)
    view = can_view(user, course)
    if not view and user.role == "student":
        abort(404, "Course not found")  # don't reveal courses a student hasn't joined
    return {**course_dict(user, course, is_enrolled(user, course)), "can_view": view}


@bp.post("/join")
@login_required("student")
@limiter.limit("20 per minute")
def join(user):
    """Enroll with the join code the teacher gives out."""
    code = get_str(body(), "join_code", required=True, max_len=20, label="Join code")
    course = db.session.query(Course).filter_by(join_code=code.strip().upper()).first()
    if course is None:
        abort(404, "No course with that join code")
    if is_enrolled(user, course):
        abort(409, "You're already in this course")
    db.session.add(Enrollment(user_id=user.id, course_id=course.id))
    db.session.commit()
    return course_dict(user, course, True), 201


@bp.post("/<int:course_id>/join-code")
@login_required("teacher", "admin")
def new_code(user, course_id):
    """Make a new join code (e.g. if the old one was shared too widely)."""
    course = db.get_or_404(Course, course_id)
    if not can_manage(user, course):
        abort(403, "Not your course")
    course.join_code = new_join_code()
    db.session.commit()
    return {"join_code": course.join_code}
