from datetime import datetime, timezone

from .extensions import db

ROLES = ("admin", "teacher", "ta", "student")


def now():
    return datetime.now(timezone.utc)


def as_utc(dt):
    """Treat naive datetimes (e.g. from SQLite) as UTC so comparisons are safe."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def iso(dt):
    return as_utc(dt).isoformat() if dt else None


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    created_at = db.Column(db.DateTime(timezone=True), default=now)

    def to_dict(self):
        return {"id": self.id, "email": self.email, "name": self.name, "role": self.role}


class Course(db.Model):
    __tablename__ = "courses"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now)
    teacher = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "title": self.title,
            "description": self.description,
            "teacher": self.teacher.name if self.teacher else None,
            "teacher_id": self.teacher_id,
        }


class Enrollment(db.Model):
    __tablename__ = "enrollments"
    __table_args__ = (db.UniqueConstraint("user_id", "course_id"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now)


class CourseStaff(db.Model):
    """TAs assigned to help with a specific course."""
    __tablename__ = "course_staff"
    __table_args__ = (db.UniqueConstraint("user_id", "course_id"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    user = db.relationship("User")


class Assignment(db.Model):
    __tablename__ = "assignments"
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    due_at = db.Column(db.DateTime(timezone=True))
    max_points = db.Column(db.Integer, nullable=False, default=100)
    allow_late = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    late_penalty_percent = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    def is_late(self, when):
        return self.due_at is not None and as_utc(when) > as_utc(self.due_at)

    def to_dict(self):
        return {
            "id": self.id,
            "course_id": self.course_id,
            "title": self.title,
            "description": self.description,
            "due_at": iso(self.due_at),
            "max_points": self.max_points,
            "allow_late": self.allow_late,
            "late_penalty_percent": self.late_penalty_percent,
        }


class Submission(db.Model):
    __tablename__ = "submissions"
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    submitted_at = db.Column(db.DateTime(timezone=True), default=now)
    student = db.relationship("User")
    assignment = db.relationship("Assignment")
    grade = db.relationship("Grade", uselist=False, back_populates="submission")

    @property
    def late(self):
        return self.assignment.is_late(self.submitted_at)

    def to_dict(self):
        grade = None
        if self.grade:
            grade = self.grade.to_dict()
            penalty = self.assignment.late_penalty_percent if self.late else 0
            grade["penalty_percent"] = penalty
            grade["final_points"] = round(self.grade.points * (100 - penalty) / 100, 2)
        return {
            "id": self.id,
            "assignment_id": self.assignment_id,
            "student": self.student.name,
            "student_id": self.student_id,
            "original_name": self.original_name,
            "submitted_at": iso(self.submitted_at),
            "late": self.late,
            "grade": grade,
        }


class Grade(db.Model):
    __tablename__ = "grades"
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(
        db.Integer, db.ForeignKey("submissions.id"), unique=True, nullable=False
    )
    points = db.Column(db.Float, nullable=False)
    feedback = db.Column(db.Text, default="")
    graded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    graded_at = db.Column(db.DateTime(timezone=True), default=now)
    submission = db.relationship("Submission", back_populates="grade")

    def to_dict(self):
        return {"points": self.points, "feedback": self.feedback,
                "graded_at": iso(self.graded_at)}
