from flask import Blueprint, abort, request

from .extensions import db
from .models import ROLES, Course, CourseStaff, User
from .security import can_manage, hash_password, login_required

bp = Blueprint("admin", __name__)


# ---- Admin: user management -------------------------------------------------

@bp.get("/admin/users")
@login_required("admin")
def list_users(admin):
    q = db.session.query(User)
    search = (request.args.get("q") or "").strip().lower()
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(db.func.lower(User.email).like(like), db.func.lower(User.name).like(like)))
    return [u.to_dict() for u in q.order_by(User.name).all()]


@bp.patch("/admin/users/<int:user_id>")
@login_required("admin")
def update_user(admin, user_id):
    user = db.get_or_404(User, user_id)
    data = request.get_json(silent=True) or {}
    role = data.get("role")
    if role is not None:
        if role not in ROLES:
            abort(400, "Invalid role")
        if user.id == admin.id and role != "admin":
            abort(400, "You can't remove your own admin role")
        user.role = role
    if data.get("name"):
        user.name = data["name"].strip()
    db.session.commit()
    return user.to_dict()


@bp.post("/admin/users/<int:user_id>/password")
@login_required("admin")
def reset_password(admin, user_id):
    user = db.get_or_404(User, user_id)
    password = (request.get_json(silent=True) or {}).get("password") or ""
    if len(password) < 8:
        abort(400, "Password must be at least 8 characters")
    user.password_hash = hash_password(password)
    db.session.commit()
    return {"ok": True}


# ---- Course staff (TAs) -----------------------------------------------------

def _managed_course(user, course_id):
    course = db.get_or_404(Course, course_id)
    # Only the course's teacher or an admin assigns TAs (TAs can't add other TAs).
    if not (user.role == "admin" or course.teacher_id == user.id):
        abort(403, "Only the course teacher or an admin can manage TAs")
    return course


@bp.get("/courses/<int:course_id>/staff")
@login_required()
def list_staff(user, course_id):
    course = db.get_or_404(Course, course_id)
    if not can_manage(user, course):
        abort(403, "Not allowed")
    rows = db.session.query(CourseStaff).filter_by(course_id=course.id).all()
    return [r.user.to_dict() for r in rows]


@bp.post("/courses/<int:course_id>/staff")
@login_required("teacher", "admin")
def add_staff(user, course_id):
    course = _managed_course(user, course_id)
    email = ((request.get_json(silent=True) or {}).get("email") or "").strip().lower()
    ta = db.session.query(User).filter_by(email=email).first()
    if ta is None:
        abort(404, "No user with that email")
    if ta.role != "ta":
        abort(400, "That user is not a TA. An admin must give them the TA role first")
    if db.session.query(CourseStaff).filter_by(user_id=ta.id, course_id=course.id).first():
        abort(409, "Already a TA for this course")
    db.session.add(CourseStaff(user_id=ta.id, course_id=course.id))
    db.session.commit()
    return ta.to_dict(), 201


@bp.delete("/courses/<int:course_id>/staff/<int:user_id>")
@login_required("teacher", "admin")
def remove_staff(user, course_id, user_id):
    course = _managed_course(user, course_id)
    row = db.session.query(CourseStaff).filter_by(user_id=user_id, course_id=course.id).first()
    if row is None:
        abort(404, "Not a TA for this course")
    db.session.delete(row)
    db.session.commit()
    return {"ok": True}
