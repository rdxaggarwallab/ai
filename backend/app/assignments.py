import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, request, send_file
from .extensions import db, limiter
from .grader import grade_submission, sanitize_tests
from .models import Assignment, Course, Grade, Submission, now
from .security import can_manage, can_view, is_enrolled, login_required
from .validate import body, get_bool, get_int, get_number, get_str

bp = Blueprint("assignments", __name__)

ALLOWED_EXT = {".py", ".ipynb", ".pdf", ".zip", ".txt", ".md", ".png", ".jpg"}
MAX_CODE = 100_000  # characters for code typed in the editor or tests
KINDS = ("file", "code")


@bp.get("/courses/<int:course_id>/assignments")
@login_required()
def list_assignments(user, course_id):
    course = db.get_or_404(Course, course_id)
    if not can_view(user, course):
        abort(403, "Enroll in this course first")
    items = db.session.query(Assignment).filter_by(course_id=course.id).order_by(Assignment.id).all()
    staff = can_manage(user, course)
    return [a.to_dict(staff=staff) for a in items]


@bp.post("/courses/<int:course_id>/assignments")
@login_required("teacher", "ta", "admin")
def create_assignment(user, course_id):
    course = db.get_or_404(Course, course_id)
    if not can_manage(user, course):
        abort(403, "Not your course")
    a = Assignment(course_id=course.id)
    apply_fields(a, body(), creating=True)
    db.session.add(a)
    db.session.commit()
    return a.to_dict(staff=True), 201


@bp.patch("/assignments/<int:assignment_id>")
@login_required("teacher", "ta", "admin")
def update_assignment(user, assignment_id):
    a = db.get_or_404(Assignment, assignment_id)
    if not can_manage(user, db.session.get(Course, a.course_id)):
        abort(403, "Not your course")
    apply_fields(a, body(), creating=False)
    db.session.commit()
    return a.to_dict(staff=True)


def apply_fields(a, data, creating):
    """Validate and set assignment fields. On update, only fields present in data change."""
    def given(k):
        return creating or k in data

    if given("title"):
        a.title = get_str(data, "title", required=True, max_len=200).strip()
    if given("description"):
        a.description = get_str(data, "description", max_len=20_000)
    if given("due_at"):
        a.due_at = parse_due(data.get("due_at"))
    if given("max_points"):
        a.max_points = get_int(data, "max_points", default=100, lo=1, hi=10_000, label="Points")
    if given("late_penalty_percent"):
        a.late_penalty_percent = get_int(data, "late_penalty_percent", default=0, lo=0, hi=100,
                                         label="Late penalty")
    if given("max_attempts"):
        a.max_attempts = get_int(data, "max_attempts", default=20, lo=1, hi=1000, label="Attempts")
    if given("allow_late"):
        a.allow_late = get_bool(data, "allow_late", default=True, label="Accept late work")
    if given("kind"):
        kind = data.get("kind", "file")
        if kind not in KINDS:
            abort(400, "Kind must be 'file' or 'code'")
        a.kind = kind
    for field in ("starter_code", "test_code"):
        if given(field):
            setattr(a, field, sanitize_tests(get_str(data, field, max_len=MAX_CODE)))
    if a.autograded and a.kind != "code":
        abort(400, "Autograder tests need a 'code' assignment (students submit solution.py)")


def parse_due(value):
    """Parse an ISO date. The browser sends UTC ('...Z'); a time without a zone is taken as UTC."""
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        abort(400, "Due date must be a date like 2026-12-01T18:30:00Z")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        abort(400, "Due date must be a date like 2026-12-01T18:30:00Z")
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def display_name(filename: str) -> str:
    """A safe file name to show and offer for download. Keeps non-English letters
    (उत्तर.pdf stays उत्तर.pdf); drops folders, control characters and odd symbols.
    The file itself is always stored under a random name."""
    name = unicodedata.normalize("NFC", filename).replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w.\- ()]", "_", name, flags=re.UNICODE).strip(" .")
    stem, ext = os.path.splitext(name)
    return (stem[:100] or "file") + ext[:10]


def _per_user():
    from flask_jwt_extended import get_jwt_identity
    return f"user:{get_jwt_identity()}"


@bp.post("/assignments/<int:assignment_id>/submissions")
@login_required("student")
@limiter.limit("10 per minute", key_func=_per_user)  # per student, not per school network
def submit(user, assignment_id):
    a = db.get_or_404(Assignment, assignment_id)
    course = db.session.get(Course, a.course_id)
    if not is_enrolled(user, course):
        abort(403, "Enroll in this course first")
    if not a.allow_late and a.is_late(now()):
        abort(400, "The deadline has passed and late submissions are not accepted")
    used = db.session.query(Submission).filter_by(assignment_id=a.id, student_id=user.id).count()
    if used >= a.max_attempts:
        abort(400, f"You've used all {a.max_attempts} attempts for this assignment")

    # Stored under a random name outside any web root. Only the sandboxed grader runs it.
    folder = os.path.join(current_app.config["UPLOAD_DIR"], str(a.id))
    os.makedirs(folder, exist_ok=True)

    if a.kind == "code":
        code = request.form.get("code")
        if code is None:
            code = body().get("code")
        if not isinstance(code, str) or not code.strip():
            abort(400, "No code submitted")
        if len(code) > MAX_CODE:
            abort(400, "Code is too long")
        original, path = "solution.py", os.path.join(folder, f"{uuid.uuid4().hex}.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(code)
    else:
        f = request.files.get("file")
        if not f or not f.filename:
            abort(400, "No file uploaded")
        original = display_name(f.filename)
        ext = os.path.splitext(original)[1].lower()
        if ext not in ALLOWED_EXT:
            abort(400, f"File type not allowed. Allowed: {', '.join(sorted(ALLOWED_EXT))}")
        path = os.path.join(folder, f"{uuid.uuid4().hex}{ext}")
        f.save(path)

    s = Submission(assignment_id=a.id, student_id=user.id, file_path=path, original_name=original,
                   grading_status="pending" if a.autograded else "none")
    db.session.add(s)
    db.session.commit()
    if a.autograded and current_app.config.get("GRADE_INLINE"):
        grade_submission(s)  # tests/dev only; normally the grade-worker process does this
    return s.to_dict(), 201


@bp.get("/submissions/<int:submission_id>/code")
@login_required()
def get_code(user, submission_id):
    """Text of a code submission, so students can reopen their last attempt in the editor."""
    s = db.get_or_404(Submission, submission_id)
    course = db.session.get(Course, s.assignment.course_id)
    if s.student_id != user.id and not can_manage(user, course):
        abort(403, "Not allowed")
    if s.assignment.kind != "code":
        abort(400, "Not a code submission")
    with open(s.file_path, encoding="utf-8", errors="replace") as fh:
        return {"code": fh.read()}


@bp.post("/submissions/<int:submission_id>/regrade")
@login_required("teacher", "ta", "admin")
def regrade(user, submission_id):
    s = db.get_or_404(Submission, submission_id)
    if not can_manage(user, db.session.get(Course, s.assignment.course_id)):
        abort(403, "Not your course")
    if not s.assignment.autograded:
        abort(400, "This assignment has no autograder tests")
    s.grading_status = "pending"
    db.session.commit()
    return s.to_dict(staff=True)


@bp.post("/assignments/<int:assignment_id>/regrade")
@login_required("teacher", "ta", "admin")
def regrade_all(user, assignment_id):
    a = db.get_or_404(Assignment, assignment_id)
    if not can_manage(user, db.session.get(Course, a.course_id)):
        abort(403, "Not your course")
    if not a.autograded:
        abort(400, "This assignment has no autograder tests")
    n = (db.session.query(Submission).filter_by(assignment_id=a.id)
         .update({"grading_status": "pending"}))
    db.session.commit()
    return {"queued": n}


@bp.get("/assignments/<int:assignment_id>/submissions")
@login_required()
def list_submissions(user, assignment_id):
    a = db.get_or_404(Assignment, assignment_id)
    course = db.session.get(Course, a.course_id)
    q = db.session.query(Submission).filter_by(assignment_id=a.id)
    staff = can_manage(user, course)
    if not staff:
        q = q.filter_by(student_id=user.id)  # students see only their own
    return [s.to_dict(staff=staff) for s in q.order_by(Submission.submitted_at.desc()).all()]


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
    data = body()
    points = round(get_number(data, "points", lo=0, hi=s.assignment.max_points), 2)
    feedback = get_str(data, "feedback", max_len=10_000)
    g = s.grade or Grade(submission_id=s.id, graded_by=user.id, points=points)
    g.points, g.feedback, g.graded_by = points, feedback, user.id
    db.session.add(g)
    db.session.commit()
    return s.to_dict(staff=True)


@bp.get("/grades")
@login_required("student")
def my_grades(user):
    subs = (db.session.query(Submission).filter_by(student_id=user.id)
            .order_by(Submission.submitted_at.desc()).all())
    return [{**s.to_dict(), "assignment": s.assignment.title,
             "max_points": s.assignment.max_points,
             "course_id": s.assignment.course_id} for s in subs]
