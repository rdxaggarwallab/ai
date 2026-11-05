import io
from datetime import datetime, timedelta, timezone

import pytest

from app import create_app
from app.extensions import db
from app.models import User
from app.security import hash_password
from tests.test_api import app, client_for  # noqa: F401  (fixture reuse)


def make_user(app, email, role, password="password123"):
    with app.app_context():
        db.session.add(User(email=email, name=email.split("@")[0], role=role,
                            password_hash=hash_password(password)))
        db.session.commit()
    c = app.test_client()
    assert c.post("/api/auth/login", json={"email": email, "password": password}).status_code == 200
    return c


def user_id(app, email):
    with app.app_context():
        return db.session.query(User).filter_by(email=email).one().id


# ---- admin ------------------------------------------------------------------

def test_admin_manages_users(app):
    admin = make_user(app, "admin@x.com", "admin")
    s = client_for(app, "s@x.com")
    sid = user_id(app, "s@x.com")

    assert s.get("/api/admin/users").status_code == 403
    users = admin.get("/api/admin/users").json
    assert {u["email"] for u in users} == {"admin@x.com", "s@x.com"}
    assert len(admin.get("/api/admin/users?q=S@X").json) == 1

    assert admin.patch(f"/api/admin/users/{sid}", json={"role": "boss"}).status_code == 400
    assert admin.patch(f"/api/admin/users/{sid}", json={"role": "ta"}).json["role"] == "ta"

    aid = user_id(app, "admin@x.com")
    assert admin.patch(f"/api/admin/users/{aid}", json={"role": "student"}).status_code == 400

    assert admin.post(f"/api/admin/users/{sid}/password", json={"password": "short"}).status_code == 400
    assert admin.post(f"/api/admin/users/{sid}/password", json={"password": "newpassword1"}).status_code == 200
    c = app.test_client()
    assert c.post("/api/auth/login", json={"email": "s@x.com", "password": "newpassword1"}).status_code == 200


# ---- TAs per course ---------------------------------------------------------

def test_ta_only_manages_assigned_courses(app):
    t = client_for(app, "t@x.com", "teacher")
    ta = make_user(app, "ta@x.com", "ta")
    stu = client_for(app, "s@x.com")
    c1 = t.post("/api/courses", json={"code": "A1", "title": "A"}).json["id"]
    c2 = t.post("/api/courses", json={"code": "B1", "title": "B"}).json["id"]

    assert ta.post(f"/api/courses/{c1}/assignments", json={"title": "x"}).status_code == 403
    assert t.post(f"/api/courses/{c1}/staff", json={"email": "s@x.com"}).status_code == 400  # not a TA
    assert t.post(f"/api/courses/{c1}/staff", json={"email": "nobody@x.com"}).status_code == 404
    assert t.post(f"/api/courses/{c1}/staff", json={"email": "ta@x.com"}).status_code == 201
    assert t.post(f"/api/courses/{c1}/staff", json={"email": "ta@x.com"}).status_code == 409
    assert ta.post(f"/api/courses/{c1}/staff", json={"email": "ta@x.com"}).status_code == 403

    assert ta.post(f"/api/courses/{c1}/assignments", json={"title": "x"}).status_code == 201
    assert ta.post(f"/api/courses/{c2}/assignments", json={"title": "x"}).status_code == 403
    assert [u["email"] for u in t.get(f"/api/courses/{c1}/staff").json] == ["ta@x.com"]
    assert stu.get(f"/api/courses/{c1}/staff").status_code == 403

    taid = user_id(app, "ta@x.com")
    assert t.delete(f"/api/courses/{c1}/staff/{taid}").status_code == 200
    assert ta.post(f"/api/courses/{c1}/assignments", json={"title": "y"}).status_code == 403


# ---- due dates, late work ---------------------------------------------------

def setup_course(app):
    t = client_for(app, "t@x.com", "teacher")
    s = client_for(app, "s@x.com")
    cid = t.post("/api/courses", json={"code": "C1", "title": "C"}).json["id"]
    s.post(f"/api/courses/{cid}/enroll")
    return t, s, cid


def upload(s, aid):
    return s.post(f"/api/assignments/{aid}/submissions",
                  data={"file": (io.BytesIO(b"print(1)"), "a.py")})


def test_due_date_keeps_timezone(app):
    t, _, cid = setup_course(app)
    # 23:59 in India (UTC+5:30) is 18:29 UTC
    a = t.post(f"/api/courses/{cid}/assignments",
               json={"title": "x", "due_at": "2026-12-01T23:59:00+05:30"}).json
    assert a["due_at"].startswith("2026-12-01T18:29:00")
    b = t.post(f"/api/courses/{cid}/assignments",
               json={"title": "y", "due_at": "2026-12-01T18:29:00.000Z"}).json
    assert b["due_at"] == a["due_at"]
    assert t.post(f"/api/courses/{cid}/assignments",
                  json={"title": "z", "due_at": "not a date"}).status_code == 400


def test_late_submission_marked_and_penalised(app):
    t, s, cid = setup_course(app)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    on_time = t.post(f"/api/courses/{cid}/assignments",
                     json={"title": "ok", "due_at": future, "late_penalty_percent": 20}).json["id"]
    late = t.post(f"/api/courses/{cid}/assignments",
                  json={"title": "late", "due_at": past, "late_penalty_percent": 20}).json["id"]
    closed = t.post(f"/api/courses/{cid}/assignments",
                    json={"title": "closed", "due_at": past, "allow_late": False}).json["id"]
    assert t.post(f"/api/courses/{cid}/assignments",
                  json={"title": "bad", "late_penalty_percent": 150}).status_code == 400

    r1 = upload(s, on_time).json
    r2 = upload(s, late).json
    assert r1["late"] is False and r2["late"] is True
    assert upload(s, closed).status_code == 400

    g = t.put(f"/api/submissions/{r2['id']}/grade", json={"points": 50}).json["grade"]
    assert g["points"] == 50 and g["penalty_percent"] == 20 and g["final_points"] == 40
    g = t.put(f"/api/submissions/{r1['id']}/grade", json={"points": 50}).json["grade"]
    assert g["final_points"] == 50


# ---- security ---------------------------------------------------------------

def test_login_rate_limited(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
                      "UPLOAD_DIR": str(tmp_path), "JWT_COOKIE_CSRF_PROTECT": False})
    with app.app_context():
        db.create_all()
        c = app.test_client()
        codes = [c.post("/api/auth/login", json={"email": "a@x.com", "password": "x"}).status_code
                 for _ in range(11)]
        assert codes[:10] == [401] * 10 and codes[10] == 429


def test_production_requires_real_secret(monkeypatch):
    monkeypatch.setenv("LMS_ENV", "production")
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://"})
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 40)
    app = create_app({"SQLALCHEMY_DATABASE_URI": "sqlite://"})
    assert app.config["JWT_COOKIE_SECURE"] is True


def test_cli_create_admin(app):
    runner = app.test_cli_runner()
    r = runner.invoke(args=["create-admin", "boss@x.com", "Boss", "--password", "password123"])
    assert "Created admin" in r.output, r.output
    with app.app_context():
        assert db.session.query(User).filter_by(email="boss@x.com").one().role == "admin"
