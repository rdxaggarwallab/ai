"""Adversarial API tests written by the testing session (2026-11-06).

Every test asserts the behaviour we WANT. Tests named test_bug_* failed when this
report was written: each one is a reproducible bug (see notes/test-report-2026-11-06.md).
Tests named test_guard_* passed: they are attacks the app already blocks; keep them
as regression tests.
"""
import io
from datetime import datetime, timedelta, timezone

import pytest

from conftest import client_for, make_app, set_role, join
from app.extensions import db


# ---------------------------------------------------------------- helpers

def course(app, teacher_email="t@x.com", code="C1"):
    t = client_for(app, teacher_email, "teacher")
    cid = t.post("/api/courses", json={"code": code, "title": "Course"}).json["id"]
    return t, cid


def enrolled_student(app, email, cid):
    s = client_for(app, email)
    assert join(s, cid).status_code == 201
    return s


def file_assignment(t, cid, **kw):
    r = t.post(f"/api/courses/{cid}/assignments", json={"title": "A", **kw})
    assert r.status_code == 201, r.json
    return r.json["id"]


def upload(s, aid, name="a.py", data=b"print(1)"):
    return s.post(f"/api/assignments/{aid}/submissions", data={"file": (io.BytesIO(data), name)})


# ---------------------------------------------------------------- IDOR / permissions (guards)

def test_guard_student_cannot_read_other_students_work(app):
    t, cid = course(app)
    a = enrolled_student(app, "a@x.com", cid)
    b = enrolled_student(app, "b@x.com", cid)
    aid = file_assignment(t, cid)
    sid = upload(a, aid).json["id"]
    assert b.get(f"/api/submissions/{sid}/file").status_code == 403
    assert b.get(f"/api/submissions/{sid}/code").status_code == 403
    assert b.get(f"/api/assignments/{aid}/submissions").json == []
    assert b.put(f"/api/submissions/{sid}/grade", json={"points": 1}).status_code == 403
    assert b.post(f"/api/submissions/{sid}/regrade").status_code == 403
    assert b.post(f"/api/assignments/{aid}/regrade").status_code == 403


def test_guard_unenrolled_student_cannot_see_course(app):
    t, cid = course(app)
    file_assignment(t, cid)
    outsider = client_for(app, "o@x.com")
    assert outsider.get(f"/api/courses/{cid}/assignments").status_code == 403


def test_guard_ta_limited_to_assigned_course(app):
    t, c1 = course(app)
    t2, c2 = course(app, "t2@x.com", "C2")
    client_for(app, "ta@x.com")
    set_role(app, "ta@x.com", "ta")
    ta = app.test_client()
    ta.post("/api/auth/login", json={"email": "ta@x.com", "password": "password123"})
    assert t.post(f"/api/courses/{c1}/staff", json={"email": "ta@x.com"}).status_code == 201
    s = enrolled_student(app, "s@x.com", c2)
    a2 = file_assignment(t2, c2)
    sid = upload(s, a2).json["id"]
    assert ta.post(f"/api/courses/{c2}/assignments", json={"title": "x"}).status_code == 403
    assert ta.patch(f"/api/assignments/{a2}", json={"title": "x"}).status_code == 403
    assert ta.put(f"/api/submissions/{sid}/grade", json={"points": 1}).status_code == 403
    assert ta.get(f"/api/submissions/{sid}/file").status_code == 403
    assert ta.get(f"/api/courses/{c2}/staff").status_code == 403
    # a TA can't add more TAs, even to its own course
    assert ta.post(f"/api/courses/{c1}/staff", json={"email": "ta@x.com"}).status_code == 403


def test_guard_teacher_cannot_edit_other_teachers_assignment(app):
    t1, c1 = course(app)
    t2, _ = course(app, "t2@x.com", "C2")
    aid = file_assignment(t1, c1)
    assert t2.patch(f"/api/assignments/{aid}", json={"title": "pwned"}).status_code == 403
    assert t2.post(f"/api/courses/{c1}/staff", json={"email": "x@x.com"}).status_code == 403


@pytest.mark.parametrize("points", [-1, 101, "nan", "inf", "-inf", "1e309", None, "abc"])
def test_guard_grade_points_validated(app, points):
    t, cid = course(app)
    s = enrolled_student(app, "s@x.com", cid)
    sid = upload(s, file_assignment(t, cid)).json["id"]
    assert t.put(f"/api/submissions/{sid}/grade", json={"points": points}).status_code == 400


def test_guard_path_tricks_in_filename(app, tmp_path):
    t, cid = course(app)
    s = enrolled_student(app, "s@x.com", cid)
    aid = file_assignment(t, cid)
    r = upload(s, aid, name="../../../../etc/passwd.py")
    assert r.status_code == 201
    assert "/" not in r.json["original_name"] and ".." not in r.json["original_name"]
    from app.models import Submission
    path = db.session.get(Submission, r.json["id"]).file_path
    assert path.startswith(str(tmp_path))
    assert upload(s, aid, name="evil.exe").status_code == 400
    assert upload(s, aid, name="evil.py.exe").status_code == 400


def test_guard_oversized_upload_rejected(app):
    t, cid = course(app)
    s = enrolled_student(app, "s@x.com", cid)
    r = upload(s, file_assignment(t, cid), name="big.pdf", data=b"0" * (21 * 1024 * 1024))
    assert r.status_code == 413 and "error" in r.json


def test_guard_student_never_sees_hidden_tests_or_log(app):
    t, cid = course(app)
    s = enrolled_student(app, "s@x.com", cid)
    r = t.post(f"/api/courses/{cid}/assignments", json={
        "title": "code", "kind": "code", "test_code": "def test_x():\n    assert True\n"})
    aid = r.json["id"]
    view = s.get(f"/api/courses/{cid}/assignments").json[0]
    assert "test_code" not in view
    sub = s.post(f"/api/assignments/{aid}/submissions", json={"code": "x = 1"}).json
    assert "log" not in (sub["autograde"] or {})


# ---------------------------------------------------------------- CSRF

@pytest.fixture
def csrf_app(tmp_path):
    app = make_app(tmp_path, JWT_COOKIE_CSRF_PROTECT=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.engine.dispose()
        db.drop_all()


def test_guard_csrf_header_required(csrf_app):
    t = client_for(csrf_app, "t@x.com", "teacher")  # register itself needs no token
    r = t.post("/api/courses", json={"code": "C1", "title": "x"})
    assert r.status_code == 401 and "CSRF" in r.json.get("msg", "")
    token = t.get_cookie("csrf_access_token").value
    r = t.post("/api/courses", json={"code": "C1", "title": "x"}, headers={"X-CSRF-TOKEN": token})
    assert r.status_code == 201
    cid = r.json["id"]
    assert t.post(f"/api/courses/{cid}/assignments", json={"title": "a"},
                  headers={"X-CSRF-TOKEN": "wrong"}).status_code == 401


def test_bug_logout_is_not_csrf_protected_and_does_not_revoke_token(csrf_app):
    """Logout only deletes the cookie. A copied token keeps working for up to 8 hours."""
    t = client_for(csrf_app, "t@x.com", "teacher")
    stolen = t.get_cookie("access_token_cookie").value
    assert t.post("/api/auth/logout").status_code == 200   # no CSRF token needed
    other = csrf_app.test_client()
    other.set_cookie("access_token_cookie", stolen)
    assert other.get("/api/auth/me").status_code == 401, "token still valid after logout"


# ---------------------------------------------------------------- sessions / roles

def test_bug_password_reset_does_not_end_existing_sessions(app):
    s = client_for(app, "s@x.com")             # e.g. an attacker who knew the old password
    client_for(app, "admin@x.com")
    set_role(app, "admin@x.com", "admin")
    admin = app.test_client()
    admin.post("/api/auth/login", json={"email": "admin@x.com", "password": "password123"})
    uid = s.get("/api/auth/me").json["id"]
    assert admin.post(f"/api/admin/users/{uid}/password",
                      json={"password": "newpassword1"}).status_code == 200
    assert s.get("/api/auth/me").status_code == 401, "old session still works after reset"


def test_bug_demoted_teacher_still_manages_own_course(app):
    t, cid = course(app)
    set_role(app, "t@x.com", "student")
    assert t.get("/api/auth/me").json["role"] == "student"
    # can_manage() only compares course.teacher_id, so the demoted user keeps full control.
    r = t.get(f"/api/courses/{cid}")  # now a student who hasn't joined: 404, or no control
    assert r.status_code == 404 or r.json["can_manage"] is False
    assert t.get(f"/api/courses/{cid}/staff").status_code == 403


def test_bug_anyone_can_self_register_as_teacher(app):
    r = app.test_client().post("/api/auth/register", json={
        "email": "random@internet.com", "name": "x", "password": "password123", "role": "teacher"})
    assert r.status_code == 400, "self-registration as teacher is open to anyone"


# ---------------------------------------------------------------- rate limiting

def test_bug_rate_limit_shared_by_everyone_behind_proxy(tmp_path):
    """In the real setup every request reaches Flask from the proxy (Vite / web container),
    so all users share one login bucket: 10 wrong passwords from anyone lock out everyone."""
    app = make_app(tmp_path, RATELIMIT_ENABLED=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
        client_for(app, "good@x.com")
        attacker = app.test_client()
        for _ in range(10):
            attacker.post("/api/auth/login", json={"email": "x@x.com", "password": "nope"},
                          environ_base={"REMOTE_ADDR": "172.18.0.5"},
                          headers={"X-Forwarded-For": "203.0.113.9"})
        victim = app.test_client()
        r = victim.post("/api/auth/login", json={"email": "good@x.com", "password": "password123"},
                        environ_base={"REMOTE_ADDR": "172.18.0.5"},
                        headers={"X-Forwarded-For": "198.51.100.7"})
        db.session.remove()
        db.engine.dispose()
        db.drop_all()
        assert r.status_code == 200, f"victim locked out by someone else's attempts ({r.status_code})"


# ---------------------------------------------------------------- input validation (500s)

@pytest.mark.parametrize("path,body", [
    ("/api/auth/login", {"email": ["a"], "password": "x"}),
    ("/api/auth/login", {"email": "s@x.com", "password": 12345678}),
    ("/api/auth/register", {"email": "z@x.com", "name": ["x"], "password": "password123"}),
    ("/api/auth/register", {"email": "z@x.com", "name": "x", "password": ["p"] * 9}),
])
def test_bug_auth_type_confusion_returns_500(app, path, body):
    client_for(app, "s@x.com")
    r = app.test_client().post(path, json=body)
    assert r.status_code in (400, 401), f"{path} {body} -> {r.status_code}"


@pytest.mark.parametrize("body", [
    {"title": 123},
    {"title": "x", "description": {"a": 1}},
    {"title": "x", "due_at": 1700000000},
    {"title": "x", "max_points": 10 ** 12},
    {"title": "x", "starter_code": ["x"]},
    {"title": "x", "kind": ["code"]},
])
def test_bug_assignment_type_confusion_returns_500(app, body):
    t, cid = course(app)
    r = t.post(f"/api/courses/{cid}/assignments", json=body)
    assert r.status_code == 400, f"{body} -> {r.status_code}"


@pytest.mark.parametrize("body", [{"code": 123, "title": "x"}, {"code": "X1", "title": "x", "description": [1]},
                                  {"code": "X" * 40, "title": "x"}])
def test_bug_course_type_confusion_returns_500(app, body):
    t = client_for(app, "t@x.com", "teacher")
    assert t.post("/api/courses", json=body).status_code == 400


def test_bug_grade_feedback_non_string_returns_500(app):
    t, cid = course(app)
    s = enrolled_student(app, "s@x.com", cid)
    sid = upload(s, file_assignment(t, cid)).json["id"]
    r = t.put(f"/api/submissions/{sid}/grade", json={"points": 5, "feedback": {"x": 1}})
    assert r.status_code == 400


def test_bug_allow_late_string_false_is_treated_as_true(app):
    t, cid = course(app)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    aid = file_assignment(t, cid, due_at=past, allow_late="false")
    s = enrolled_student(app, "s@x.com", cid)
    assert upload(s, aid).status_code == 400, "allow_late='false' accepted late work"


def test_bug_unicode_filename_rejected(app):
    """secure_filename() strips non-ASCII: 'उत्तर.pdf' becomes 'pdf' with no extension."""
    t, cid = course(app)
    s = enrolled_student(app, "s@x.com", cid)
    aid = file_assignment(t, cid)
    r = upload(s, aid, name="उत्तर.pdf", data=b"%PDF-1.4")
    assert r.status_code == 201, r.json
    r = upload(s, aid, name="résumé final.pdf", data=b"%PDF-1.4")
    assert r.status_code == 201 and r.json["original_name"].endswith(".pdf")


def test_bug_lowering_max_points_leaves_grades_above_max(app):
    t, cid = course(app)
    s = enrolled_student(app, "s@x.com", cid)
    aid = file_assignment(t, cid)
    sid = upload(s, aid).json["id"]
    t.put(f"/api/submissions/{sid}/grade", json={"points": 90})
    assert t.patch(f"/api/assignments/{aid}", json={"max_points": 10}).status_code == 200
    g = s.get("/api/grades").json[0]
    assert g["grade"]["final_points"] <= g["max_points"], f"{g['grade']['final_points']}/{g['max_points']}"


def test_bug_no_submission_limit_or_rate_limit(app):
    """A student can upload 20 MB files in a loop and fill the server's disk."""
    t, cid = course(app)
    s = enrolled_student(app, "s@x.com", cid)
    aid = file_assignment(t, cid)
    codes = [upload(s, aid).status_code for _ in range(60)]
    assert 429 in codes or 400 in codes, "60 uploads in a row all accepted"
