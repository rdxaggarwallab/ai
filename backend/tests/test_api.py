import io

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "UPLOAD_DIR": str(tmp_path),
        "JWT_COOKIE_CSRF_PROTECT": False,
    })
    with app.app_context():
        db.create_all()
        yield app


def client_for(app, email, role="student"):
    c = app.test_client()
    r = c.post("/api/auth/register", json={"email": email, "name": email.split("@")[0],
                                           "password": "password123", "role": role})
    assert r.status_code == 201, r.json
    return c


def test_register_login_me(app):
    client_for(app, "s@x.com")
    c = app.test_client()
    assert c.post("/api/auth/login", json={"email": "s@x.com", "password": "wrong"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "s@x.com", "password": "password123"}).status_code == 200
    assert c.get("/api/auth/me").json["role"] == "student"


def test_cannot_self_register_as_admin(app):
    r = app.test_client().post("/api/auth/register", json={
        "email": "a@x.com", "name": "a", "password": "password123", "role": "admin"})
    assert r.status_code == 400


def test_full_flow(app):
    t = client_for(app, "t@x.com", "teacher")
    s = client_for(app, "s@x.com")
    other = client_for(app, "o@x.com")

    assert s.post("/api/courses", json={"code": "AI101", "title": "x"}).status_code == 403
    cid = t.post("/api/courses", json={"code": "ai101", "title": "Intro to AI"}).json["id"]

    aid = t.post(f"/api/courses/{cid}/assignments",
                 json={"title": "HW1", "max_points": 10}).json["id"]

    # must enroll before seeing or submitting
    assert s.get(f"/api/courses/{cid}/assignments").status_code == 403
    assert s.post(f"/api/courses/{cid}/enroll").status_code == 201
    assert len(s.get(f"/api/courses/{cid}/assignments").json) == 1

    bad = s.post(f"/api/assignments/{aid}/submissions",
                 data={"file": (io.BytesIO(b"x"), "evil.exe")})
    assert bad.status_code == 400
    sub = s.post(f"/api/assignments/{aid}/submissions",
                 data={"file": (io.BytesIO(b"print(1)"), "hw1.py")})
    assert sub.status_code == 201
    sid = sub.json["id"]

    # privacy: other students can't download or see it
    assert other.get(f"/api/submissions/{sid}/file").status_code == 403
    assert s.get(f"/api/submissions/{sid}/file").data == b"print(1)"

    assert t.put(f"/api/submissions/{sid}/grade", json={"points": 11}).status_code == 400
    assert s.put(f"/api/submissions/{sid}/grade", json={"points": 10}).status_code == 403
    assert t.put(f"/api/submissions/{sid}/grade",
                 json={"points": 9, "feedback": "Nice"}).status_code == 200

    grades = s.get("/api/grades").json
    assert grades[0]["grade"]["points"] == 9 and grades[0]["assignment"] == "HW1"


def test_other_teacher_cannot_manage(app):
    t1 = client_for(app, "t1@x.com", "teacher")
    t2 = client_for(app, "t2@x.com", "teacher")
    cid = t1.post("/api/courses", json={"code": "R1", "title": "Robotics"}).json["id"]
    assert t2.post(f"/api/courses/{cid}/assignments", json={"title": "x"}).status_code == 403


def test_requires_login(app):
    assert app.test_client().get("/api/courses").status_code == 401
