import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, request, send_file
from werkzeug.utils import secure_filename

from .extensions import db
from .models import Assignment, Course, Grade, Submission, now
from .security import can_manage, can_view, is_enrolled, login_required

bp = Blueprint("assignments", __name__)

ALLOWED_EXT = {".py", ".ipynb", ".pdf", ".zip", ".txt", ".md", ".png", ".jpg"}


@bp.get("/courses/<int:course_id>/assignments")
@login_required()
def list_assignments(user, course_id):
    course = db.get_or_404(Course, course_id)
    if not can_view(user, course):
        abort(403, "Enroll in this course first")
    items = db.session.query(Assignment).filter_by(course_id=course.id).order_by(Assignment.id).all()
    return [a.to_dict() for a in items]


@bp.post("/courses/<int:course_id>/assignments")
@login_required("teacher", "ta", "admin")
def create_assignment(user, course_id):
    course = db.get_or_404(Course, course_id)
    if not can_manage(user, course):
        abort(403, "Not your course")
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        abort(400, "Title is required")
    try:
        due_at = parse_due(data.get("due_at"))
        max_points = int(data.get("max_points", 100))
        penalty = int(data.get("late_penalty_percent", 0))
    except (ValueError, TypeError):
        abort(400, "Invalid due date, points or penalty")
    if max_points < 1:
        abort(400, "Points must be at least 1")
    if not 0 <= penalty <= 100:
        abort(400, "Late penalty must be between 0 and 100")
    a = Assignment(course_id=course.id, title=title, description=data.get("description", ""),
                   due_at=due_at, max_points=max_points,
                   allow_late=bool(data.get("allow_late", True)), late_penalty_percent=penalty)
    db.session.add(a)
    db.session.commit()
    return a.to_dict(), 201


def parse_due(value):
    """Parse an ISO date. The browser sends UTC ('...Z'); a time without a zone is taken as UTC."""
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


@bp.post("/assignments/<int:assignment_id>/submissions")
@login_required("student")
def submit(user, assignment_id):
    a = db.get_or_404(Assignment, assignment_id)
    course = db.session.get(Course, a.course_id)
    if not is_enrolled(user, course):
        abort(403, "Enroll in this course first")
    if not a.allow_late and a.is_late(now()):
        abort(400, "The deadline has passed and late submissions are not accepted")
    f = request.files.get("file")
    if not f or not f.filename:
        abort(400, "No file uploaded")
    original = secure_filename(f.filename) or "file"
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED_EXT:
        abort(400, f"File type not allowed. Allowed: {', '.join(sorted(ALLOWED_EXT))}")

    # Stored under a random name outside any web root; never executed.
    folder = os.path.join(current_app.config["UPLOAD_DIR"], str(a.id))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{uuid.uuid4().hex}{ext}")
    f.save(path)

    s = Submission(assignment_id=a.id, student_id=user.id, file_path=path, original_name=original)
    db.session.add(s)
    db.session.commit()
    return s.to_dict(), 201


@bp.get("/assignments/<int:assignment_id>/submissions")
@login_required()
def list_submissions(user, assignment_id):
    a = db.get_or_404(Assignment, assignment_id)
    course = db.session.get(Course, a.course_id)
    q = db.session.query(Submission).filter_by(assignment_id=a.id)
    if not can_manage(user, course):
        q = q.filter_by(student_id=user.id)  # students see only their own
    return [s.to_dict() for s in q.order_by(Submission.submitted_at.desc()).all()]


@bp.get("/submissions/<int:submission_id>/file")
@login_required()
def download(user, submission_id):
    s = db.get_or_404(Submission, submission_id)
    course = db.session.get(Course, s.assignment.course_id)
    if s.student_id != user.id and not can_manage(user, course):
        abort(403, "Not allowed")
    return send_file(s.file_path, as_attachment=True, download_name=s.original_name)


@bp.put("/submissions/<int:submission_id>/grade")
@login_required("teacher", "ta", "admin")
def grade(user, submission_id):
    s = db.get_or_404(Submission, submission_id)
    course = db.session.get(Course, s.assignment.course_id)
    if not can_manage(user, course):
        abort(403, "Not your course")
    data = request.get_json(silent=True) or {}
    try:
        points = float(data["points"])
    except (KeyError, ValueError, TypeError):
        abort(400, "Points are required")
    if not 0 <= points <= s.assignment.max_points:
        abort(400, f"Points must be between 0 and {s.assignment.max_points}")
    g = s.grade or Grade(submission_id=s.id, graded_by=user.id, points=points)
    g.points, g.feedback, g.graded_by = points, data.get("feedback", ""), user.id
    db.session.add(g)
    db.session.commit()
    return s.to_dict()


@bp.get("/grades")
@login_required("student")
def my_grades(user):
    subs = (db.session.query(Submission).filter_by(student_id=user.id)
            .order_by(Submission.submitted_at.desc()).all())
    return [{**s.to_dict(), "assignment": s.assignment.title,
             "max_points": s.assignment.max_points,
             "course_id": s.assignment.course_id} for s in subs]
