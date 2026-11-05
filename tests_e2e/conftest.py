"""Shared fixtures for the adversarial API tests.

Run from the repo root:
    cd backend && python -m pytest -q ../tests_e2e
Uses in-memory SQLite by default. Set LMS_TEST_DB to a PostgreSQL URL to run
against a real database (some type/overflow bugs only show up there), e.g.
    LMS_TEST_DB=postgresql://lms:lms@localhost:5432/lms_test
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402

DB_URL = os.environ.get("LMS_TEST_DB", "sqlite://")


def make_app(tmp_path, **extra):
    cfg = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": DB_URL,
        "UPLOAD_DIR": str(tmp_path),
        "JWT_COOKIE_CSRF_PROTECT": False,
        "RATELIMIT_ENABLED": False,
    }
    cfg.update(extra)
    return create_app(cfg)


@pytest.fixture
def app(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.engine.dispose()
        db.drop_all()


def client_for(app, email, role="student", password="password123"):
    c = app.test_client()
    r = c.post("/api/auth/register", json={"email": email, "name": email.split("@")[0],
                                           "password": password, "role": role})
    assert r.status_code == 201, r.json
    return c


def set_role(app, email, role):
    from app.models import User
    u = db.session.query(User).filter_by(email=email).one()
    u.role = role
    db.session.commit()
    return u.id
