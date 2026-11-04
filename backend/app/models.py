from datetime import datetime, timezone

from .extensions import db

ROLES = ("admin", "teacher", "ta", "student")


def now():
    return datetime.now(timezone.utc)


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


class Assignment(db.Model):
    __tablename__ = "assignments"
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    due_at = db.Column(db.DateTime(timezone=True))
    max_points = db.Column(db.Integer, nullable=False, default=100)

    def to_dict(self):
        return {
            "id": self.id,
            "course_id": self.course_id,
            "title": self.title,
            "description": self.description,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "max_points": self.max_points,
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

    def to_dict(self):
        return {
            "id": self.id,
            "assignment_id": self.assignment_id,
            "student": self.student.name,
            "student_id": self.student_id,
            "original_name": self.original_name,
            "submitted_at": self.submitted_at.isoformat(),
            "grade": self.grade.to_dict() if self.grade else None,
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
                "graded_at": self.graded_at.isoformat()}
